"""Isolated JSON/TCP contract tests for UnrealConnection.

Run: python -m unittest discover -s tests -v
The real Unreal Editor/UE version is NOT exercised by these tests.
"""
import ast
import json
import logging
from pathlib import Path
import socket as socket_module
import types
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "Python" / "unreal_mcp_server.py"


class FakeSocket:
    def __init__(self):
        self.written = []
        self.responses = [b'{"status":"ok","success":true}\n']

    def settimeout(self, _): pass
    def setsockopt(self, *_): pass
    def connect(self, _): pass
    def sendall(self, data): self.written.append(data)
    def recv(self, _): return self.responses.pop(0) if self.responses else b""
    def close(self): pass


class BridgeContractTests(unittest.TestCase):
    def setUp(self):
        self.opened = []

        def open_socket(*_):
            s = FakeSocket()
            self.opened.append(s)
            return s

        fake_socket = types.SimpleNamespace(
            AF_INET=socket_module.AF_INET,
            SOCK_STREAM=socket_module.SOCK_STREAM,
            IPPROTO_TCP=socket_module.IPPROTO_TCP,
            TCP_NODELAY=socket_module.TCP_NODELAY,
            SOL_SOCKET=socket_module.SOL_SOCKET,
            SO_KEEPALIVE=socket_module.SO_KEEPALIVE,
            SO_RCVBUF=socket_module.SO_RCVBUF,
            SO_SNDBUF=socket_module.SO_SNDBUF,
            socket=open_socket,
            timeout=socket_module.timeout,
        )
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        nodes = [
            n for n in tree.body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef))
            and n.name in ("UnrealConnection", "get_unreal_connection")
        ]
        self.assertEqual(len(nodes), 2)
        self.ns = {
            "socket": fake_socket,
            "json": json,
            "logger": logging.getLogger("UnrealMCP-test"),
            "UNREAL_HOST": "127.0.0.1",
            "UNREAL_PORT": 55557,
            "Dict": dict,
            "Any": object,
            "Optional": __import__("typing").Optional,
            "_unreal_connection": None,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), self.ns)

    def test_bridge_accessor_does_not_emit_undocumented_probe(self):
        bridge = self.ns["get_unreal_connection"]()
        self.assertIs(bridge, self.ns["get_unreal_connection"]())
        self.assertEqual(self.opened, [])

    def test_one_json_command_per_tcp_connection(self):
        bridge = self.ns["get_unreal_connection"]()
        self.assertEqual(bridge.send_command("get_actors_in_level", {})["status"], "ok")
        self.assertEqual(
            bridge.send_command("compile_blueprint", {"blueprint_name": "BP_Test"})["status"],
            "ok",
        )
        self.assertEqual(len(self.opened), 2)
        self.assertEqual([len(sock.written) for sock in self.opened], [1, 1])
        wire = [sock.written[0] for sock in self.opened]
        self.assertEqual(json.loads(wire[0].decode("utf-8"))["command"], "get_actors_in_level")
        self.assertEqual(json.loads(wire[1].decode("utf-8"))["params"], {"blueprint_name": "BP_Test"})
        for payload in wire:
            self.assertTrue(payload.endswith(b"\n"), "Native transport requires newline frames")
            self.assertEqual(payload.count(b"\n"), 1)
            self.assertNotIn(bytes([0]), payload)
            self.assertIsInstance(json.loads(payload.decode("utf-8")), dict)

    def test_unterminated_response_is_not_success(self):
        # The native contract is one JSON line per connection. A fragment that
        # happens to be parseable is not a completed framed response.
        def factory(*_):
            sock = FakeSocket()
            sock.responses = [b'{"status":"ok"}']  # No terminating LF.
            self.opened.append(sock)
            return sock

        self.ns["socket"].socket = factory
        actual = self.ns["get_unreal_connection"]().send_command("ping", {})
        self.assertEqual(actual["status"], "error", actual)
        self.assertIn("before response LF terminator", actual["error"])

    def test_fragmented_utf8_response_with_lf(self):
        def factory(*_):
            sock = FakeSocket()
            sock.responses = [b'{"status":"ok","message":"caf\xc3',
                              b'\xa9"}\r', b'\n']
            self.opened.append(sock)
            return sock

        self.ns["socket"].socket = factory
        actual = self.ns["get_unreal_connection"]().send_command("ping", {})
        self.assertEqual(actual["status"], "ok", actual)
        self.assertEqual(actual["message"], "café")


if __name__ == "__main__":
    unittest.main()
