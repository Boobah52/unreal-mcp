# Unreal MCP transport contract and independent verification gates

Status: DEVELOPMENT / UNMERGED. This historic project has NOT passed Unreal
compilation, PIE, gameplay, headset, visual or independent high-effort review.
Never interpret a green remote Python test as end-user Unreal functionality.

## Published instructions actually followed

1. JSON Lines specification: https://jsonlines.org/
   Direct wording: "UTF-8 Encoding"; "Each Line is a Valid JSON Value";
   "Line Terminator is '\n'". We apply this framing to the *internal
   Python-to-Unreal TCP bridge*, not to the official MCP stdio protocol.
2. Epic UE 5.8 FSocket::Recv:
   https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Sockets/FSocket/Recv?application_version=5.8
   Direct wording: "Reads a chunk of data from a connected socket".
   Epic specifies that BytesRead is the actual number read. A single Recv
   cannot establish an entire request or UTF-8 character.
3. Epic UE 5.8 FSocket API:
   https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Sockets/FSocket?application_version=5.8
   Send accepts Data, Count and BytesSent. Progress must use encoded bytes
   actually sent, not a count of Unicode FString characters.
4. Windows native C++ test compiler:
   https://github.com/ilammy/msvc-dev-cmd
   Direct wording: "This sets up the environment for compiling C/C++ code
   from command line." Workflow pins the version used by Microsoft's
   Calculator CI rather than bypassing Windows STL/compiler checks:
   https://github.com/microsoft/calculator/blob/main/.github/workflows/action-ci.yml

## Explicit wire contract

- Host: loopback 127.0.0.1, port 55557 in the example.
- One request and one response per TCP connection.
- Request is a UTF-8 JSON object containing a nonempty string "command"
  and optional object "params", followed by LF. CRLF is accepted.
- Response is a UTF-8 JSON object followed by LF. Python MUST wait for LF
  before reporting that a response completed.
- Request limit 1 MiB and response limit 8 MiB, excluding terminators.
- NUL bytes, empty lines, oversized frames, invalid JSON and invalid
  request field types are errors, not success.
- Accumulate raw bytes until the delimiter, then decode as UTF-8 and parse
  JSON. Never decode a partial network packet in isolation.
- When sending, use the UTF-8 converted byte length, inspect BytesSent,
  and continue until full transmission or an explicit bounded error.
- Actor lookup with a truly empty level is success. A disconnected editor
  must yield an error, never an apparently empty level.
- All seven bundled Python example scripts have been updated to use the
  command field and LF terminator; direct callers using the legacy
  "type" field or no LF require equivalent changes.

Example request on the internal TCP wire, terminated by LF:

    {"command":"create_blueprint","params":{"name":"BP_Test","parent_class":"Actor"}}

The native Unreal response has to be observed in UE, not invented based on
what a Python stand-in returned.

## Evidence levels

| Level | Test | Evidence allows | Not proven |
|---|---|---|---|
| A | Python fake-socket tests | Serializing requests and errors | Real TCP |
| B | OS loopback TCP tests | Fragmented bytes, UTF-8, network responses | Unreal |
| C | Actual MCP client + running stdio server | MCP startup and tool registration | UE tool execution |
| D | MCP client -> server -> TCP -> fake native backend | Python-side command chain | Blueprint creation in UE |
| E | Compile/run exact standalone C++ framer | Bounded byte framing native algorithm | UE module compilation |
| F | Static Python/C++ source checks | Known command names and envelope agreement | Native runtime |
| G | Separate UE 5.8 clean plugin build | Native compilation against actual engine | PIE/gameplay |
| H | UE PIE, screenshots, telemetry, asset inspection | Verified specific user-visible result | Generality beyond tested task |

A–F are the maximum layers accessible to the currently configured GitHub
Actions runners. G–H have not been performed and require a licensed UE runner.

## Reproducing the remote tests

Run in a separate checkout of the review branch:

    python -m pip install -e ./Python
    python -m unittest discover -s tests -p 'test_unreal_bridge*.py' -v
    python -m unittest discover -s tests -p 'test_native_protocol_contract.py' -v
    python -m unittest discover -s tests -p 'test_mcp*.py' -v
    python -m unittest discover -s tests -p 'test_native_line_framing_compiled.py' -v

Check exact GitHub Actions run URLs and logs for Windows and Ubuntu.
The test harness requires C++17 and uses MSVC on Windows, Clang/GCC on Linux.

## Native UE acceptance that is STILL REQUIRED

1. Use a separate UE 5.8 development project, not a running AIFWEEN gym.
2. Record clean native build results and exact warnings, module versions,
   installed engine version and user-visible enabled-plugin state.
3. Through real stdio MCP and the actual Unreal TCP listener, create a
   Blueprint, add a component, compile, place an actor and inspect the asset.
4. Preserve end-user PNGs, observed asset state, compiler logs and runtime
   telemetry; run PIE and verify the outcome, not only a status message.
5. Test fragmentation, large Unicode replies, rejected malformed and
   oversized frames, reconnects, invalid parameters, genuine empty scene,
   editor disconnection and cancellation during shutdown.
6. Independently review socket ownership and the game-thread future/promise
   synchronization before merging. The legacy native bridge uses a forced
   thread kill; shutdown behavior is not verified.
7. Define backup and rollback before integrating into any active project.

## Non-claims

No Unreal Editor has run in this CI environment. The C++ framer is compiled
outside UE, and UE-specific socket, conversion and thread functions were
not compiled here. Fake server responses must NEVER be labeled native UE
success. No user-view PNGs or headset evidence exist for this branch.
