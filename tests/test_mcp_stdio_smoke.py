"""MCP server/client smoke test using the published Python SDK stdio workflow.

Source procedure: https://github.com/modelcontextprotocol/python-sdk/tree/main/examples
This launches the real MCP server and queries its exposed tools, but DOES NOT
run Unreal Engine or test native plugin functions.
"""
import asyncio
import os
from pathlib import Path
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1] / "Python" / "unreal_mcp_server.py"


class McpEntrypointTests(unittest.TestCase):
    def test_stdio_startup_and_tool_discovery(self):
        async def check():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=20)
                    result = await asyncio.wait_for(session.list_tools(), timeout=20)
                    names = {tool.name for tool in result.tools}
                    for required in ("get_actors_in_level", "create_blueprint", "compile_blueprint", "spawn_actor"):
                        self.assertIn(required, names)
                    self.assertGreater(len(names), 10)

        asyncio.run(check())

    def test_actor_lookup_reports_disconnected_editor_as_error(self):
        # Fresh CI runners have no Unreal listener. An empty success result
        # must never be mistaken for a verified empty Unreal level.
        async def check():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=20)
                    response = await asyncio.wait_for(
                        session.call_tool("get_actors_in_level", {}), timeout=20
                    )
                    self.assertTrue(
                        response.isError,
                        "Disconnected Unreal must be an MCP error, not an empty level",
                    )
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
