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
                    self.assertIn(
                        "Cannot inspect level: no response from Unreal",
                        str(response),
                        "Error must originate from the disconnected Unreal guard",
                    )
        asyncio.run(check())

    def test_disconnected_editor_must_fail_closed_for_search_and_mutation(self):
        """MCP isError is the authoritative client-visible failure signal."""
        async def check():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=20)
                    requests = [
                        ("find_actors_by_name", {"pattern": "UnlikelyActor_7283"}),
                        ("delete_actor", {"name": "UnlikelyActor_7283"}),
                        ("create_blueprint", {"name": "BP_Disconnected_7283", "parent_class": "Actor"}),
                        ("compile_blueprint", {"blueprint_name": "BP_Disconnected_7283"}),
                    ]
                    for name, args in requests:
                        with self.subTest(tool=name):
                            result = await asyncio.wait_for(
                                session.call_tool(name, args), timeout=20
                            )
                            self.assertTrue(
                                result.isError,
                                f"{name}: missing real Unreal must be MCP isError; got {result}",
                            )
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
