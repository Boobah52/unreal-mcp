"""Validate native Unreal command results before an MCP tool reports success.

The native C++ UUnrealMCPBridge::ExecuteCommand emits:
{"status":"success","result":{...}} or {"status":"error","error":"..."}.
Converting failure into a normal dict/list makes MCP isError=False; tools must
raise so MCP SDK v1 exposes isError=True to calling clients.
"""
from typing import Any, Dict


def require_unreal_success(command: str, response: Any) -> Dict[str, Any]:
    if not isinstance(response, dict):
        raise ConnectionError(f"{command}: Unreal did not return a response")

    status = response.get("status")
    if status != "success" or response.get("success") is False:
        reason = response.get("error") or response.get("message") or f"invalid status {status!r}"
        raise RuntimeError(f"{command}: Unreal command failed: {reason}")

    if not isinstance(response.get("result"), dict):
        raise ValueError(f"{command}: Unreal did not return a result object")

    return response
