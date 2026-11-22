"""Cross-language protocol contract checks, performed without Unreal headers.

These checks prevent a Python/client envelope from silently disagreeing with
the native C++ receive/dispatch code. They are static source checks ONLY.
JSON protocol background: https://www.rfc-editor.org/rfc/rfc8259
"""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PY_BRIDGE = ROOT / "Python/unreal_mcp_server.py"
NATIVE_RECEIVER = ROOT / "MCPGameProject/Plugins/UnrealMCP/Source/UnrealMCP/Private/MCPServerRunnable.cpp"
NATIVE_DISPATCH = ROOT / "MCPGameProject/Plugins/UnrealMCP/Source/UnrealMCP/Private/UnrealMCPBridge.cpp"


class NativeProtocolContractTests(unittest.TestCase):
    def test_live_cpp_receiver_reads_python_command_field(self):
        py = PY_BRIDGE.read_text(encoding="utf-8")
        cpp = NATIVE_RECEIVER.read_text(encoding="utf-8")
        self.assertIn('"command": command', py, "Python must transmit command key")
        start = cpp.index("uint32 FMCPServerRunnable::Run()")
        end = cpp.index("void FMCPServerRunnable::Stop()", start)
        actual_receiver = cpp[start:end]
        self.assertIn(
            'TryGetStringField(TEXT("command"), CommandType)',
            actual_receiver,
            'Active C++ Run loop must read the same "command" key Python transmits',
        )

    def test_python_command_names_have_native_dispatch_cases(self):
        text = NATIVE_DISPATCH.read_text(encoding="utf-8")
        native = set(re.findall(r'CommandType\s*==\s*TEXT\("([^"]+)"\)', text))
        python_commands = set()
        for path in (ROOT / "Python/tools").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "attr", None) != "send_command":
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    python_commands.add(node.args[0].value)
        self.assertGreater(len(python_commands), 10)
        self.assertFalse(
            python_commands - native,
            f"Python sends commands absent from C++ ExecuteCommand: {sorted(python_commands - native)}",
        )

    def test_all_bundled_example_scripts_use_native_wire_contract(self):
        paths = sorted((ROOT / "Python/scripts").rglob("*.py"))
        self.assertGreaterEqual(len(paths), 7)
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                ast.parse(text)
                self.assertNotIn('"type": command', text)
                self.assertIn('"command": command', text)
                self.assertIn(
                    "sock.sendall((command_json + '\\n').encode('utf-8'))",
                    text,
                )


if __name__ == "__main__":
    unittest.main()
