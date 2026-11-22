"""Compile and execute EXACT native line framer header in CI; no UE headers needed.

This tests the same C++ header included by MCPServerRunnable.cpp, unlike tests
that merely mimic native behavior in Python. It is not an Unreal compilation.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CXX = ROOT / "tests" / "native_line_framing.cpp"
HEADER_DIR = ROOT / "MCPGameProject" / "Plugins" / "UnrealMCP" / "Source" / "UnrealMCP" / "Private"


class NativeFrameTests(unittest.TestCase):
    def test_native_line_framaer_compiles_and_exercises_fragmentation(self):
        # GitHub hosted Windows and Ubuntu images expose LLVM Clang.
        compiler = shutil.which("clang++") or shutil.which("g++")
        self.assertIsNotNone(compiler, "C++ compiler required for this acceptance test")
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / ("native-frame-test.exe" if os.name == "nt" else "native-frame-test")
            subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 "-I", str(HEADER_DIR), str(CXX), "-o", str(executable)],
                check=True, timeout=90,
            )
            result = subprocess.run([str(executable)], check=True, capture_output=True,
                                    text=True, timeout=25)
            self.assertIn("native line-framing tests passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
