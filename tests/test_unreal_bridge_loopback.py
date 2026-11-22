"""Real TCP loopback tests of the bridge's JSON request/response contract.

These use the production UnrealConnection class and an actual OS TCP socket.
The listening server is an isolated Python stand-in, NOT Unreal Engine.
Python docs: https://docs.python.org/3/library/socket.html
"""
import ast
import json
import logging
from pathlib import Path
import socket
import socketserver
import threading
import time
import typing
import unittest

BRIDGE_FILE = Path(__file__).resolve().parents[1] / "Python" / "unreal_mcp_server.py"


class LocalBridgeServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class RequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        raw_request = b""
        self.request.settimeout(3)
        while True:
            chunk = self.request.recv(4096)
            if not chunk:
                raise ConnectionError("Client closed before sending JSON request")
            raw_request += chunk
            try:
                command = json.loads(raw_request.decode("utf-8"))
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        self.server.requests.append((command, raw_request))
        if command["command"] == "fail":
            data = json.dumps({"status": "error", "error": "expected rejection"}).encode("utf-8")
            self.request.sendall(data)
        elif command["command"] == "unicode":
            data = json.dumps({"status": "ok", "message": "café 🐝"}, ensure_ascii=False).encode("utf-8")
            cut = data.index("é".encode("utf-8")) + 1
            self.request.sendall(data[:cut])
            time.sleep(0.10)
            self.request.sendall(data[cut:])
        else:
            data = json.dumps({"status": "ok", "success": True, "command": command["command"]}).encode("utf-8")
            self.request.sendall(data)


def load_real_bridge_class():
    tree = ast.parse(BRIDGE_FILE.read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "UnrealConnection"]
    if len(classes) != 1:
        raise AssertionError("Could not locate exactly one UnrealConnection in production source")
    namespace = {
        "socket": socket,
        "json": json,
        "logger": logging.getLogger("test-loopback"),
        "UNREAL_HOST": "127.0.0.1",
        "UNREAL_PORT": 0,
        "Dict": typing.Dict,
        "Any": typing.Any,
        "Optional": typing.Optional,
    }
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(BRIDGE_FILE), "exec"), namespace)
    return namespace


class ActualTcpContractTests(unittest.TestCase):
    def setUp(self):
        self.server = LocalBridgeServer(("127.0.0.1", 0), RequestHandler)
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        namespace = load_real_bridge_class()
        namespace["UNREAL_PORT"] = self.server.server_address[1]
        self.bridge = namespace["UnrealConnection"]()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_two_real_socket_round_trips_use_json(self):
        first = self.bridge.send_command("get_actors_in_level", {})
        second = self.bridge.send_command("compile_blueprint", {"blueprint_name": "BP_Trial"})
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["command"], "compile_blueprint")
        self.assertEqual(len(self.server.requests), 2)
        self.assertEqual(self.server.requests[1][0]["params"]["blueprint_name"], "BP_Trial")
        self.assertTrue(all(bytes([0]) not in raw for _, raw in self.server.requests))

    def test_real_server_error_is_preserved(self):
        actual = self.bridge.send_command("fail", {})
        self.assertEqual(actual["status"], "error")
        self.assertEqual(actual["error"], "expected rejection")

    def test_fragmented_utf8_response_is_accepted(self):
        # UTF-8 character is intentionally split across two socket writes.
        # Python socket.recv() is permitted to return a partial byte sequence.
        result = self.bridge.send_command("unicode", {})
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["message"], "café 🐝")


if __name__ == "__main__":
    unittest.main()
