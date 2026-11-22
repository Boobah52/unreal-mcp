"""An MCP tool must not claim success when Unreal is entirely absent.

Uses the real subprocess and MCP v1 ClientSession. Each argument set is
handpicked against exposed Python tool signatures; errors from invalid input
schemas do NOT satisfy the test. No UE or external TCP endpoints are contacted.
"""
import asyncio
import os
from pathlib import Path
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1] / "Python" / "unreal_mcp_server.py"

EXAMPLES = {
    "get_actors_in_level": {},
    "find_actors_by_name": {"pattern": "Test"},
    "spawn_actor": {"name": "TestActor", "type": "CUBE"},
    "delete_actor": {"name": "TestActor"},
    "set_actor_transform": {"name": "TestActor", "location": [1.0, 2.0, 3.0]},
    "get_actor_properties": {"name": "TestActor"},
    "set_actor_property": {"name": "TestActor", "property_name": "bHidden", "property_value": True},
    "spawn_blueprint_actor": {"blueprint_name": "BP_Test", "actor_name": "Instance"},
    "create_blueprint": {"name": "BP_Test", "parent_class": "Actor"},
    "add_component_to_blueprint": {
        "blueprint_name": "BP_Test", "component_type": "StaticMeshComponent", "component_name": "TestMesh",
    },
    "set_static_mesh_properties": {"blueprint_name": "BP_Test", "component_name": "TestMesh"},
    "set_component_property": {
        "blueprint_name": "BP_Test", "component_name": "TestMesh",
        "property_name": "bVisible", "property_value": True,
    },
    "set_physics_properties": {"blueprint_name": "BP_Test", "component_name": "TestMesh"},
    "compile_blueprint": {"blueprint_name": "BP_Test"},
    "set_blueprint_property": {
        "blueprint_name": "BP_Test", "property_name": "bCanBeDamaged", "property_value": True,
    },
    "add_blueprint_event_node": {"blueprint_name": "BP_Test", "event_name": "BeginPlay"},
    "add_blueprint_input_action_node": {"blueprint_name": "BP_Test", "action_name": "Jump"},
    "add_blueprint_function_node": {
        "blueprint_name": "BP_Test", "target": "Self", "function_name": "PrintString",
    },
    "connect_blueprint_nodes": {
        "blueprint_name": "BP_Test", "source_node_id": "A", "source_pin": "Then",
        "target_node_id": "B", "target_pin": "Execute",
    },
    "add_blueprint_variable": {
        "blueprint_name": "BP_Test", "variable_name": "Enabled", "variable_type": "Boolean",
    },
    "add_blueprint_get_self_component_reference": {
        "blueprint_name": "BP_Test", "component_name": "TestMesh",
    },
    "add_blueprint_self_reference": {"blueprint_name": "BP_Test"},
    "find_blueprint_nodes": {"blueprint_name": "BP_Test"},
    "create_input_mapping": {"action_name": "Jump", "key": "SpaceBar"},
    "create_umg_widget_blueprint": {"widget_name": "WBP_Test"},
    "add_text_block_to_widget": {
        "widget_name": "WBP_Test", "text_block_name": "Title",
    },
    "add_button_to_widget": {"widget_name": "WBP_Test", "button_name": "Action"},
    "bind_widget_event": {
        "widget_name": "WBP_Test", "widget_component_name": "Action", "event_name": "OnClicked",
    },
    "add_widget_to_viewport": {"widget_name": "WBP_Test"},
    "set_text_block_binding": {
        "widget_name": "WBP_Test", "text_block_name": "Title", "binding_property": "TitleText",
    },
}


class AllToolsDisconnectedTests(unittest.TestCase):
    def test_all_tools_fail_closed_without_unreal(self):
        async def check():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=30)
                    tool_list = await asyncio.wait_for(session.list_tools(), timeout=15)
                    offered = {t.name for t in tool_list.tools}
                    self.assertEqual(offered, set(EXAMPLES),
                                     f"Tool matrix drift: absent {set(EXAMPLES)-offered}; "
                                     f"untested {offered-set(EXAMPLES)}")
                    not_errors = []
                    wrong_errors = []
                    for name, arguments in EXAMPLES.items():
                        try:
                            result = await asyncio.wait_for(
                                session.call_tool(name, arguments), timeout=12
                            )
                        except Exception as ex:
                            wrong_errors.append(f"{name}: unexpected protocol exception {ex}")
                            continue
                        if not result.isError:
                            not_errors.append(f"{name}: {str(result)[:220]}")
                        elif "Unreal" not in str(result) and "connection" not in str(result).lower():
                            wrong_errors.append(f"{name}: error not attributable to disconnected UE: {str(result)[:220]}")
                    self.assertFalse(not_errors, "FALSE SUCCESS:\n" + "\n".join(not_errors))
                    self.assertFalse(wrong_errors, "INVALID OR UNRELATED ERRORS:\n" + "\n".join(wrong_errors))

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
