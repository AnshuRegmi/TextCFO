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