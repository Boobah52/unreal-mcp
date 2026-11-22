"""Actual TCP exchange between production Python bridge and compiled C++ framer.

The C++ stand-in uses the EXACT header included by MCPServerRunnable.cpp.
No Unreal Engine is installed or executed. Echo-hex is synthetic evidence.
"""
import ast
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import typing
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "Python" / "unreal_mcp_server.py"
HEADER_DIR = ROOT / "MCPGameProject/Plugins/UnrealMCP/Source/UnrealMCP/Private"
SOURCE = ROOT / "tests/native_tcp_standin.cpp"


def make_bridge(port):
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    matches = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "UnrealConnection"]
    if len(matches) != 1:
        raise AssertionError("Production bridge class missing")
    namespace = {
        "socket": socket,
        "json": json,
        "logger": logging.getLogger("test-native-tcp"),
        "UNREAL_HOST": "127.0.0.1",
        "UNREAL_PORT": port,
        "Dict": typing.Dict,
        "Any": typing.Any,
        "Optional": typing.Optional,
    }
    exec(compile(ast.Module(body=matches, type_ignores=[]), str(BRIDGE), "exec"),
         namespace)
    return namespace["UnrealConnection"]()


def compile_standin(executable, build_dir):
    if os.name == "nt":
        compiler = shutil.which("cl")
        if compiler is None:
            raise AssertionError("Windows C++ acceptance requires configured MSVC")
        args = [compiler, "/nologo", "/std:c++17", "/EHsc", "/W4",
                "/WX", "/utf-8", "/I" + str(HEADER_DIR),
                str(SOURCE), "/Fo:" + str(build_dir / "native_standin.obj"),
                "/Fe:" + str(executable), "/link", "Ws2_32.lib"]
    else:
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            raise AssertionError("Linux C++17 compiler required")
        args = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(HEADER_DIR), str(SOURCE), "-o", str(executable)]
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=90)


def launch_standin(executable):
    process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1)
    ready = queue.Queue(maxsize=1)

    def reader():
        ready.put(process.stdout.readline())

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        line = ready.get(timeout=8).strip()
        if not line.startswith("READY "):
            raise AssertionError("C++ stand-in failed to start: " + line)
        port = int(line.split()[1])
        return process, port, t
    except BaseException:
        process.kill()
        process.communicate(timeout=5)
        raise


class CppTcpEndToEndTests(unittest.TestCase):
    def test_python_bridge_to_compiled_native_framer(self):
        with tempfile.TemporaryDirectory() as temporary:
            build_dir = Path(temporary)
            executable = build_dir / (
                "native_tcp_standin.exe" if os.name == "nt" else "native_tcp_standin"
            )
            compile_standin(executable, build_dir)
            process, port, thread = launch_standin(executable)
            try:
                thread.join(timeout=2)
                bridge = make_bridge(port)
                cases = [
                    ("create_blueprint", {"name": "café 🐝", "parent_class": "Actor"}),
                    ("large_payload", {"data": "Z" * 20000}),
                ]
                for command, params in cases:
                    with self.subTest(command=command):
                        result = bridge.send_command(command, params)
                        self.assertEqual(result["status"], "ok", result)
                        decoded = bytes.fromhex(result["hex"])
                        self.assertNotIn(b"\x00", decoded)
                        self.assertEqual(
                            json.loads(decoded.decode("utf-8")),
                            {"command": command, "params": params},
                        )
                        self.assertNotIn(b"\n", decoded)

                # Force TCP fragmentation: every byte is a separate send call.
                payload = b'{"command":"split","params":{}}\n'
                with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                    sock.settimeout(5)
                    for byte in payload:
                        sock.sendall(bytes([byte]))
                        time.sleep(0.001)
                    raw = bytearray()
                    while b"\n" not in raw:
                        chunk = sock.recv(4096)
                        self.assertTrue(chunk, "C++ endpoint closed before complete response")
                        raw.extend(chunk)
                    response = json.loads(bytes(raw).decode("utf-8"))
                    self.assertEqual(response["status"], "ok", response)
                    self.assertEqual(bytes.fromhex(response["hex"]), payload[:-1])

                # A 4th independent connection confirms per-command reconnects.
                result = bridge.send_command("get_actors_in_level", {})
                self.assertEqual(result["status"], "ok", result)
                self.assertEqual(
                    json.loads(bytes.fromhex(result["hex"]).decode("utf-8")),
                    {"command": "get_actors_in_level", "params": {}},
                )
                process.wait(timeout=8)
                self.assertEqual(process.returncode, 0, process.stderr.read())
                self.assertIn("COMPLETE 4", process.stdout.read())
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
