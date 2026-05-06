"""
Orchestrator — connects to MCP server + RAG + LLM.

This is the MCP flow:
  1. Connect to tally_mcp.py as MCP client
  2. Discover available tools dynamically
  3. User asks question
  4. Retrieve business context from RAG
  5. Send to LLM with tool descriptions
  6. LLM decides which tool to call
  7. We call the tool via MCP protocol
  8. Feed result back to LLM
  9. LLM formats final answer
"""

import asyncio
import json
import re
import os
import sys
import requests
import httpx
from datetime import date
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
MODEL = os.getenv("MODEL", "arcee-ai/trinity-large-preview:free")

# Lines 32-37: MCP Client Section Header
# ─────────────────────────────────────────────────
#  MCP Client — connects to tally_mcp.py server
# ─────────────────────────────────────────────────

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Lines 40-110: TallyMCPClient Class (SKELETON)
class TallyMCPClient:
    """Connects to tally_mcp.py as a real MCP server process."""

    def __init__(self):
        self.session = None
        self.tools = []  # Discovered dynamically from server

    async def connect(self):
        """Start the MCP server as a subprocess and connect to it."""
        # This launches tally_mcp.py as a separate process
        # and communicates via stdin/stdout (MCP stdio transport)
        python_path = sys.executable  # Use same Python as current process
        server_params = StdioServerParameters(
            command=python_path,
            args=["tally_mcp.py"],
        )

        # stdio_client returns a context manager
        self._transport = stdio_client(server_params)
        streams = await self._transport.__aenter__()
        read_stream, write_stream = streams

        self.session = ClientSession(read_stream, write_stream)
        await self.session.__aenter__()
        await self.session.initialize()

        # DISCOVER tools dynamically — this is the MCP magic
        tools_result = await self.session.list_tools()
        self.tools = tools_result.tools

        print(f"🔌 Connected to MCP server")
        print(f"🔧 Discovered {len(self.tools)} tools:")
        for t in self.tools:
            print(f"   - {t.name}: {t.description[:60]}...")

    async def call_tool(self, name: str, arguments: dict = None) -> str:
        """Call a tool on the MCP server by name."""
        if arguments is None:
            arguments = {}

        result = await self.session.call_tool(name, arguments)

        # Extract text from result
        if result.content:
            texts = []
            for block in result.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
            return "\n".join(texts)
        return "No result returned."

    async def disconnect(self):
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._transport:
            await self._transport.__aexit__(None, None, None)

    def get_tool_descriptions(self) -> str:
        """Format tool list for the LLM prompt."""
        lines = []
        for t in self.tools:
            # Build argument description
            args = []
            if t.inputSchema and "properties" in t.inputSchema:
                for prop_name, prop_info in t.inputSchema["properties"].items():
                    args.append(prop_name)

            args_str = ", ".join(args) if args else "none"
            lines.append(f"  - {t.name}({args_str}): {t.description}")
        return "\n".join(lines)


# Lines 112-124: RAG Section Header + Import
# ─────────────────────────────────────────────────
#  RAG — retrieve business context
# ─────────────────────────────────────────────────

RAG_ENABLED = False
try:
    from rag import get_relevant_context, search_ledgers
    if os.path.exists(os.path.join(os.path.dirname(__file__), "chroma_db")):
        RAG_ENABLED = True
        print("📚 RAG enabled")
except ImportError:
    print("📚 RAG not available (chromadb not installed)")

# Lines 126-156: LLM Communication
# ─────────────────────────────────────────────────
#  LLM Communication
# ─────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def call_llm(messages: list[dict]) -> str:
    """Call OpenRouter LLM with retry logic."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            # Raise exception to trigger tenacity retry
            raise Exception(f"LLM Error: {data['error']}")

        return data["choices"][0]["message"]["content"]

# Lines 158-173: parse_tool_call Function
def parse_tool_call(text: str):
    """Parse TOOL_CALL: tool_name(arg1="val1") from LLM output."""
    match = re.search(r"TOOL_CALL:\s*(\w+)\((.*?)\)", text, re.DOTALL)
    if not match:
        return None, None

    tool_name = match.group(1)
    args_str = match.group(2).strip()

    kwargs = {}
    if args_str:
        for arg_match in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', args_str):
            kwargs[arg_match.group(1)] = arg_match.group(2)

    return tool_name, kwargs

# Lines 175-280: handle_query Function
# ─────────────────────────────────────────────────
#  Main Query Handler
# ─────────────────────────────────────────────────

async def handle_query(
    mcp_client: TallyMCPClient,
    user_id: str,
    query: str,
    conversation_history: dict,
) -> str:
    """
    Full flow:
      1. RAG: retrieve business context
      2. Build prompt with discovered tools
      3. LLM decides tool call or direct answer
      4. Execute tool via MCP protocol
      5. Feed result back, repeat until final answer
    """
    today = date.today().strftime("%Y-%m-%d (YYYYMMDD: %Y%m%d)")

    # ── RAG: Get relevant business rules ──
    rag_context = ""
    if RAG_ENABLED:
        try:
            rag_context = get_relevant_context(query, n=2)
        except Exception:
            pass

    # ── Build system prompt with DISCOVERED tools ──
    tool_list = mcp_client.get_tool_descriptions()

    system_prompt = f"""You are a Tally accounting BI assistant. You answer business questions using live data from Tally Prime.

You have these tools available (discovered from the MCP server):
{tool_list}

RULES:
1. To call a tool, respond EXACTLY: TOOL_CALL: tool_name(arg1="value1", arg2="value2")
2. Call ONE tool at a time. Wait for the result before calling another.
3. When you have enough data, give a clear answer with NO tool call.
4. NEVER invent data. If a tool returns an error, say so.
5. Format currency as ₹X,XX,XXX.
6. Keep answers concise — this is a chat interface.

Today's date: {today}"""

    if rag_context:
        system_prompt += f"""

BUSINESS CONTEXT (from company knowledge base):
{rag_context}

Use this context to provide better analysis (e.g., flag overdue payments, check margins against targets)."""

    # ── Conversation history ──
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history[user_id])
    messages.append({"role": "user", "content": query})

    # ── Tool-calling loop ──
    max_rounds = 5

    for round_num in range(max_rounds):
        try:
            llm_response = await call_llm(messages)
        except Exception as e:
            print(f"  [Error] LLM failed after retries: {e}")
            return "⚠️ The AI brain is currently overloaded. Please try again in a minute."

        print(f"  [Round {round_num + 1}] LLM: {llm_response[:150]}")

        tool_name, kwargs = parse_tool_call(llm_response)

        if tool_name is None:
            # No tool call — this is the final answer
            conversation_history[user_id].append(
                {"role": "user", "content": query}
            )
            conversation_history[user_id].append(
                {"role": "assistant", "content": llm_response}
            )
            # Trim history
            if len(conversation_history[user_id]) > 20:
                conversation_history[user_id] = conversation_history[user_id][-20:]
            return llm_response

        # ── Call tool via MCP protocol ──
        print(f"  [MCP call] {tool_name}({kwargs})")
        try:
            tool_result = await mcp_client.call_tool(tool_name, kwargs)
        except Exception as e:
            tool_result = f"Tool error: {e}"
        print(f"  [Result] {tool_result[:150]}...")

        # Feed result back
        messages.append({"role": "assistant", "content": llm_response})
        messages.append({
            "role": "user",
            "content": f"TOOL_RESULT for {tool_name}:\n{tool_result}",
        })

    return "Could not complete analysis. Please try a simpler question."

# Lines 282-310: Test Section (leave empty stub)
async def main():
    pass  # Will be filled in Week 2

if __name__ == "__main__":
    asyncio.run(main())