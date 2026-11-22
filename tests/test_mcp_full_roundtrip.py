"""Real MCP client -> stdio subprocess -> TCP -> fake Unreal reply.

This checks the entire Python/MCP command path, not Unreal Engine itself.
SDK procedure: https://github.com/modelcontextprotocol/python-sdk/tree/main/examples
Socket procedure: https://docs.python.org/3/library/socketserver.html
"""
import asyncio
import json
import os
from pathlib import Path
import socketserver
import sys
import threading
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1] / "Python" / "unreal_mcp_server.py"


class LocalServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class BackendHandler(socketserver.BaseRequestHandler):
    def handle(self):
        raw = b""
        self.request.settimeout(5)
        while True:
            chunk = self.request.recv(4096)
            if not chunk:
                raise ConnectionError("No complete JSON request from MCP server")
            raw += chunk
            if b"\n" not in raw:
                continue
            framed, separator, extra = raw.partition(b"\n")
            if extra:
                raise ValueError("Extra bytes after one JSON request")
            request = json.loads(framed.decode("utf-8"))
            break
        self.server.received.append(request)
        response = {
            "status": "success",
            "result": {
                "marker": "mcp-roundtrip-verified",
                "echo": request,
            },
        }
        if request["command"] == "get_actors_in_level":
            response["result"]["actors"] = []
        if request["command"] == "find_actors_by_name":
            response["result"]["actors"] = [
                {"name": "ActorFound", "class": "StaticMeshActor"}
            ]
        if request["params"].get("name") == "ForceNativeError":
            response = {"status": "error", "error": "native-rejection-marker"}
        self.request.sendall(json.dumps(response).encode("utf-8") + b"\n")


class McpRealProcessRoundtripTests(unittest.TestCase):
    def test_mcp_tool_crosses_actual_tcp_and_returns_reply(self):
        # The application's existing bridge uses TCP port 55557.
        # This CI-only stand-in never contacts the public network.
        backend = LocalServer(("127.0.0.1", 55557), BackendHandler)
        backend.received = []
        thread = threading.Thread(target=backend.serve_forever, daemon=True)
        thread.start()

        async def run_client():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await asyncio.wait_for(session.initialize(), timeout=20)
                    response = await asyncio.wait_for(
                        session.call_tool(
                            "create_blueprint",
                            {"name": "BP_RemoteTest", "parent_class": "Actor"},
                        ),
                        timeout=20,
                    )
                    self.assertFalse(response.isError, response)
                    self.assertIn("mcp-roundtrip-verified", str(response))
                    empty_level = await asyncio.wait_for(
                        session.call_tool("get_actors_in_level", {}), timeout=20
                    )
                    self.assertFalse(
                        empty_level.isError,
                        "A valid empty actor list must remain a non-error",
                    )
                    found = await asyncio.wait_for(
                        session.call_tool("find_actors_by_name", {"pattern": "ActorFound"}),
                        timeout=20,
                    )
                    self.assertFalse(found.isError, found)
                    self.assertIn("ActorFound", str(found))
                    for command, args in (
                        ("delete_actor", {"name": "ActorFound"}),
                        ("compile_blueprint", {"blueprint_name": "BP_RemoteTest"}),
                    ):
                        result = await asyncio.wait_for(
                            session.call_tool(command, args), timeout=20
                        )
                        self.assertFalse(result.isError, result)
                    rejected = await asyncio.wait_for(
                        session.call_tool("delete_actor", {"name": "ForceNativeError"}),
                        timeout=20,
                    )
                    self.assertTrue(rejected.isError, rejected)
                    self.assertIn("native-rejection-marker", str(rejected))


        try:
            asyncio.run(run_client())
            self.assertEqual(len(backend.received), 6, backend.received)
            self.assertEqual(backend.received[0]["command"], "create_blueprint")
            self.assertEqual(
                backend.received[0]["params"],
                {"name": "BP_RemoteTest", "parent_class": "Actor"},
            )
            self.assertEqual(
                [command["command"] for command in backend.received],
                ["create_blueprint", "get_actors_in_level", "find_actors_by_name",
                 "delete_actor", "compile_blueprint", "delete_actor"],
            )
        finally:
            backend.shutdown()
            backend.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
