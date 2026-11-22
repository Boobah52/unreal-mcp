"""Block reintroduction of silent MCP error results in any registered tool.

AST-based guard: keeps this test independent of regex formatting and catches
new tools and deleted error validation. The real-client matrix tests behavior.
"""
import ast
from pathlib import Path
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "Python" / "tools"
FILES = ("editor_tools.py", "blueprint_tools.py", "node_tools.py",
         "project_tools.py", "umg_tools.py")
MANUALLY_VALIDATED = {"get_actors_in_level"}


def is_mcp_tool(function):
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            if isinstance(target.value, ast.Name) and target.value.id == "mcp":
                return True
    return False


class NoFalseSuccessSourceGuards(unittest.TestCase):
    def test_registered_mcp_tools_have_fail_closed_errors(self):
        found = {}
        for filename in FILES:
            source = (TOOLS / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef) or not is_mcp_tool(function):
                    continue
                self.assertNotIn(function.name, found, f"Duplicate MCP tool {function.name}")
                found[function.name] = filename
                nested = [node for statement in function.body for node in ast.walk(statement)
                          if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
                calls = [
                    node.func.id for node in nested if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                ]
                if function.name not in MANUALLY_VALIDATED:
                    self.assertIn("require_unreal_success", calls,
                                  f"{filename}:{function.name} missing native outcome guard")
                for node in nested:
                    if not isinstance(node, ast.Return):
                        continue
                    value = node.value
                    if isinstance(value, (ast.Dict, ast.List)) and not (
                        isinstance(value, ast.Dict) and len(value.keys) > 0
                    ):
                        self.fail(f"{filename}:{function.name} returns empty dict/list instead of an error")
                    if isinstance(value, ast.Dict):
                        values = {
                            key.value: val for key, val in zip(value.keys, value.values)
                            if isinstance(key, ast.Constant) and isinstance(key.value, str)
                        }
                        for key in ("success", "status"):
                            v = values.get(key)
                            if isinstance(v, ast.Constant) and v.value in (False, "error"):
                                self.fail(
                                    f"{filename}:{function.name} returns failure as successful MCP result"
                                )
        self.assertEqual(len(found), 30, f"Expected 30 registered tools, found {found}")


if __name__ == "__main__":
    unittest.main()
