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


# Lines 115-?: handle_query() - Main query processing function
async def handle_query(mcp_client, user_id, query, conversation_history):
    """
    Process a user query by:
    1. Maintaining conversation history
    2. Building context for the LLM
    3. Calling tools via MCP
    4. Returning formatted response
    """
    # Initialize user conversation if needed
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    
    # Add user query to history
    conversation_history[user_id].append({"role": "user", "content": query})
    
    # Build system prompt with available tools
    system_prompt = f"""You are a financial BI assistant for Tally accounting software.
You have access to these tools:
{mcp_client.get_tool_descriptions() if mcp_client else "No tools available"}

For each user question:
1. Understand what data they need
2. Decide which tool(s) to call
3. Format the response professionally

Keep responses concise and clear."""

    # Format conversation history for LLM
    messages = [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in conversation_history[user_id][-10:]  # Keep last 10 messages
    ]
    
    try:
        # Call LLM to get response
        response_text = f"Processed query: {query[:50]}..."
        
        # For now, return a simple response (would call LLM in full implementation)
        conversation_history[user_id].append({"role": "assistant", "content": response_text})
        
        return response_text
    except Exception as e:
        error_msg = f"Error processing query: {str(e)}"
        conversation_history[user_id].append({"role": "assistant", "content": error_msg})
        raise
        return "\n".join(lines)