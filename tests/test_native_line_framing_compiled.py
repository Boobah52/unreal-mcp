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
        # Match the runner's native compiler/toolchain rather than asking an
        # older Clang to consume a newer MSVC standard library.
        if os.name == "nt":
            compiler = shutil.which("cl")
            self.assertIsNotNone(compiler, "MSVC developer environment required on Windows")
        else:
            compiler = shutil.which("clang++") or shutil.which("g++")
            self.assertIsNotNone(compiler, "C++17 compiler required")
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / ("native-frame-test.exe" if os.name == "nt" else "native-frame-test")
            if os.name == "nt":
                args = [compiler, "/nologo", "/std:c++17", "/EHsc", "/W4",
                        "/WX", "/utf-8", "/I" + str(HEADER_DIR),
                        str(CXX), "/Fe:" + str(executable)]
            else:
                args = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-I", str(HEADER_DIR), str(CXX), "-o", str(executable)]
            subprocess.run(args, check=True, timeout=90)
            result = subprocess.run([str(executable)], check=True, capture_output=True,
                                    text=True, timeout=25)
            self.assertIn("native line-framing tests passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
