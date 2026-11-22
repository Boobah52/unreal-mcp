"""Check real MCP tools accept a valid *simulated* native success envelope.

This is an integration test of the Python-side outcome contract only. The
loopback endpoint is NOT Unreal Engine; no Blueprint or gameplay is created.
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
from test_mcp_all_disconnected import EXAMPLES

SERVER = Path(__file__).resolve().parents[1] / "Python" / "unreal_mcp_server.py"


class LocalServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class FakeNativeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        raw = bytearray()
        self.request.settimeout(10)
        while b"\n" not in raw:
            chunk = self.request.recv(8192)
            if not chunk:
                raise ConnectionError("Fake native backend received an incomplete request")
            raw.extend(chunk)
        request, terminator, leftover = bytes(raw).partition(b"\n")
        if leftover:
            raise ValueError("Fake native backend received multiple commands")
        obj = json.loads(request.decode("utf-8"))
        self.server.requests.append(obj)
        response = {
            "status": "success",
            "result": {
                "success": True,
                "mock_native_transport": True,
                "actors": [{"name": "TestMatch", "class": "StaticMeshActor"}],
            },
        }
        if self.server.reject_native:
            response = {"status": "error", "error": "native-rejection-for-tool"}
        self.request.sendall(json.dumps(response).encode("utf-8") + b"\n")


class AllToolsNativeSuccessEnvelopeTests(unittest.TestCase):
    def test_all_registered_tools_accept_native_success_envelope(self):
        server = LocalServer(("127.0.0.1", 55557), FakeNativeHandler)
        server.requests = []
        server.reject_native = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        async def check():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=20)
                    failures = []
                    for name, arguments in EXAMPLES.items():
                        try:
                            output = await asyncio.wait_for(
                                session.call_tool(name, arguments), timeout=12
                            )
                            if output.isError:
                                failures.append(f"{name}: {str(output)[:300]}")
                        except Exception as ex:
                            failures.append(f"{name}: exception {ex}")
                    self.assertFalse(failures,
                                     "Positive native-envelope regressions:\n" + "\n".join(failures))
                    server.reject_native = True
                    native_errors = []
                    for name, arguments in EXAMPLES.items():
                        try:
                            output = await asyncio.wait_for(
                                session.call_tool(name, arguments), timeout=12
                            )
                            if not output.isError or "native-rejection-for-tool" not in str(output):
                                native_errors.append(f"{name}: {str(output)[:300]}")
                        except Exception as ex:
                            native_errors.append(f"{name}: exception {ex}")
                    self.assertFalse(
                        native_errors,
                        "Native error envelopes were not propagated:\n" + "\n".join(native_errors),
                    )

        try:
            asyncio.run(check())
            self.assertEqual(len(server.requests), 2 * len(EXAMPLES),
                             "One native request per tool required")
            commands = [v["command"] for v in server.requests]
            self.assertEqual(set(commands), set(EXAMPLES),
                             "MCP tool names and native dispatch names drifted")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
