# T22. MCP server inside the editor: stdio and HTTP, read-only by default

Status: done in code (30.09.2026), version 1.2.0-rc.1; acceptance with real clients (Claude Code, Claude Desktop) in a VM
pending. Stage 8. Dependencies: T21. Implementation notes: ToolError lives in `mcp/errors.py`; dialogs are counted by
`MainWindow._dialog()` instead of a `modal()` context manager; `McpService.configure(paths, settings, on_save=None)`;
`start_http(port, token, server)` returns the bound server and `serve(httpd)` is the thread body; HTTP tests run on the
customer's PC as well (loopback port 0 raised no firewall dialog); the release notes are `docs/releases/v1.2.0-rc.1.md`.
An adversarial review (five lenses, 01.10.2026) produced 44 findings; 43 were fixed in code, tests and documentation,
one was rejected (invalid tool arguments stay a tool error with `isError`, as the 2025-11-25 specification prefers,
instead of the JSON-RPC `-32602` the 2025-06-18 text lists).

This is the final design for the MCP server (Model Context Protocol) of WinKickOff 1.2. It is the synthesis of three
candidate designs (security-first, spec-first, usability-first) as the two judges recommended: the security-first design
is the base, trimmed with the discipline of the usability-first design and completed with the protocol findings of the
spec-first design, then revised against the 24 findings of the review of the first draft. The document was written
against commit bd0ce14 (editor 1.1.0-rc.4, catalog 0.5). Nothing in the repository or on the customer's PC was changed
while preparing it; the implementation follows section 12.

Facts checked in the sources: `tests/test_sources.py` forbids `import socket`, `import urllib`, `import http.client`
and `import requests` in `winkickoff/` and lets `http.server`, `socketserver` and `from socket import ...` through only by
accident of the regex; `winkickoff/__main__.py` is three lines (`from winkickoff.app import run`) and `app.py` imports
`tkinter` and `tkinter.messagebox` at module level, so today every `python -m winkickoff` invocation imports Tk before any
argument is looked at; `app.py` holds `initial_profile`, `_fatal` and `load_catalog_or_die`; `core/log.py` installs one
`RotatingFileHandler` on `logs/winkickoff.log` and returns early when one is already installed; `core/paths.py` puts
presets in `paths.data / "profiles"` (`_internal\profiles` in the frozen build) and user profiles in `paths.profiles`
(next to the exe); `core/settings.py` validates every field on load and writes an explicit dict on save; the window's
`self.settings` is rewritten by `remember_file`, `save_settings` and `on_close`, and every window rebuild loads it again;
`MainWindow.write_build` is the only place that writes an answer file; the window's Build runs `check_scripts`
(PowerShell) before it writes; all 36 `messagebox` and `filedialog` calls of the `ui/` package live in `main_window.py`
(`data_forms.py` has none); `is_busy` does not exist yet, only the `_busy` flag of `set_busy`; the customer's profiles
carry Cyrillic names (`profiles/Профіль.json` is the fixture of `test_portable.py` and `test_settings.py`); the WORKFLOW table
of `main_window.py` holds eight tuples starting with `("", N_(`; `tools/build.ps1` runs everything inside
`dist\WinKickOff` before `Compress-Archive`; the task index ends at T21.

## 0. Decisions where the inputs disagreed

Every contradiction between the three designs, the threat model, the UI notes and the review is resolved here; the
sections below follow these decisions without repeating the alternatives.

| Question | Decision | Reason |
|---|---|---|
| Is the mode persisted in `settings.json`? | No. Every start of the window and of a headless process begins in `read`. Autostart, when switched on, starts in `read` only. | The customer asked for read-only by default and no file management by default; a persisted `edit` or `files` mode combined with autostart would let an agent write before the user has seen the window (threat 22). |
| Can an MCP call replace an existing file? | No. `save_profile` and `write_answer_file` refuse an existing name; there is no `overwrite` argument and no deletion. | Silent replacement of the customer's saved profile is a supply-chain attack on the next installation (threat model section 4, item 10); a confirmation dialog raised from a server thread is fragile. |
| Can any tool start `powershell.exe`? | No, in no mode: not the audit, not the apply, not the parse-only syntax check `pscheck.check_scripts`. | The customer's PC rule and threat model section 4, items 1, 2 and 9. `validate_profile` and `validate_xml` are pure Python and cover the agent's needs. `write_answer_file` therefore writes without the PowerShell syntax check the window runs, and says so in its result (section 4.3). |
| Apply scripts written by a tool? | No. `plan_apply`, `write_apply_scripts` and `save_apply_scripts` are not in 1.2. | An `Apply.ps1` on disk written at an agent's request is one double click away from the forbidden apply. |
| Where does the token live and who writes it? | In `settings.json`, generated with `secrets.token_urlsafe(32)` on the first start of a server from the window, rotated from the menu. The live window's `self.settings` is the single writer; a headless process never writes settings and takes the token from `--token` or from `settings.mcp_token`. Open question 1 of section 11 asks the customer to confirm persistence. | All three designs chose persistence: a per-start token forces the user to edit the client configuration at every start, which ends with the check being removed. `settings.json` lies next to `profiles/*.json`, which already hold passwords in plain text, so a reader of the folder gains nothing new. Two writers of `settings.json` (a service object and the window, or a headless process and the window) would let the next window save overwrite the token silently (review finding 8). |
| Mode refusal, window busy, window timeout: protocol error or tool error? | Tool error (`isError: true` with a text and a structured `error` field). Only the standard JSON-RPC codes and `-32002` exist. | Clients show tool results to the model and may hide protocol errors; four standard codes are simpler than custom ones. |
| Are tools above the current mode listed in `tools/list`? | Yes, always all tools, each description starting with its mode tag. | Clients cache the list; the mode can change while the server runs (next row). |
| Can the mode change while the server runs? | Yes, from the menu and the monitor; it applies to the next call. Port and autostart change only while stopped. | The user should not have to restart the server and reconnect the client to grant or revoke `edit`. |
| Protocol version answered? | The requested version when it is `2024-11-05`, `2025-03-26` or `2025-06-18`; otherwise `2025-06-18`. | A supported requested version keeps older SDK clients connected; a 2025-11-25 client accepts 2025-06-18 (verified in the TypeScript SDK). |
| When is a session initialized? | When the `initialize` result is sent. `notifications/initialized` is recorded for the monitor only. `ping` is answered at any time, on HTTP also without a session id. | MCP 2025-06-18 says the client SHOULD NOT send requests before the initialize response; it does not require the server to refuse requests between the result and the notification. On Streamable HTTP the notification is a separate fire-and-forget POST and `ThreadingHTTPServer` gives no ordering, so a `tools/list` may be processed before it (review finding 7). The `-32600` refusal stays only for requests on a session that has never seen `initialize`, which is what dual-era fallback needs. |
| Batches (JSON arrays)? | Refused with `-32600`. | Removed in 2025-06-18; the SDK clients never send them. |
| `outputSchema` published? | No. `structuredContent` is returned without a schema. | The TypeScript client validates `structuredContent` against `outputSchema` strictly and throws on any mismatch. |
| Sessions on HTTP? | Strict, as the 2025-06-18 text: issued at `initialize`, `400` when missing (except for `ping`), `404` when unknown, `DELETE` ends one. No idle expiry: a session lives until the server stops, the client sends `DELETE` or it is evicted as the oldest of 16. | A client that outlived a program restart gets `404` and re-initializes, as the specification requires. An idle expiry mitigates nothing on loopback behind a bearer token and would give a Claude Code session that stayed open over lunch a `404` on its next call (review finding 24). |
| Foreign `Host` header? | `421 Misdirected Request`. | The precise status for a request that reached the wrong server. |
| `Origin: null`? | Refused with `403`. | `null` is what a browser sends from a sandboxed or file page; there is no legitimate client that sends it. |
| `401` body and `WWW-Authenticate`? | Empty body, no `WWW-Authenticate`; every path other than `/mcp` answers `404` with an empty body, including `/.well-known/*`. | A `WWW-Authenticate` challenge sends SDK clients into an OAuth discovery that cannot succeed; the `404` makes that discovery fail fast. |
| Monitor: argument values? | Whitelisted scalars only: rule ids, group ids, profile names, booleans, integers, enumeration values. Free text (comment, author, string parameter values) appears as `<text, N chars>`. No request or response bodies, no headers, no token. | The customer wants to watch what the agent asked for (judge 2); free text is the injection channel to the user (threat 21). |
| Request log on disk? | No. The journal is memory only (`deque(maxlen=1000)`). Errors go to the process log file as one line per failure (tool name and exception class); tracebacks at DEBUG only. | Nothing new on disk for the window, `test_portable.py` keeps its exact file list, no free text from arguments in a file the customer might paste to an agent (review finding 19). |
| Log file of a headless process? | `logs/mcp-stdio-<pid>.log` or `logs/mcp-http-<pid>.log`, opened lazily, never `logs/winkickoff.log`. | A stdio process started by Claude Desktop while the window is open would otherwise share one `RotatingFileHandler` target with the window; on Windows `doRollover` renames the file, the rename fails while another process holds it open, and records are lost (review finding 9). |
| Number of tools | 18 (10 read, 6 edit, 2 files), see section 4. | The usability-first design showed 17 tools cover the use cases; `search_rules` is folded into `list_rules`, `set_rule` into `set_rules`, `reset_group` into `set_group`. |
| Where does the package live? | `winkickoff/mcp/`, a sibling of `core/` and `ui/`. | `core/` keeps its rule of importing nothing that listens on a socket; the network allow list of `test_sources.py` points at one file. |
| `set_language` from the server? | Never. Texts in a requested language come from per-language `CatalogTexts.load` instances cached in `tools.py`. Imported ADMX texts follow the process language and every rule says which language its texts are in. | `i18n` is process-global and not thread-safe; `with_imports` bakes ADML texts into the catalog once, in the process language (review finding 23). |
| Does a headless process write `settings.json`? | Never. `--mcp stdio` and `--mcp http` read settings and write nothing (no `last_profile`, no recent list, no token). | A stdio server spawned by Claude Desktop must leave the user's settings alone, and a second writer of `settings.json` next to the window breaks the token (see the token row). |
| Second executable in the portable build? | Yes, `WinKickOff-mcp.exe` (console) next to `WinKickOff.exe` in the same one-folder build, built from a spec file in CI only. | A `--noconsole` process has `sys.stdin` and `sys.stdout` set to `None` unless the parent passed pipes; a protocol channel must not depend on that. `WinKickOff.exe --mcp stdio` still tries the inherited handles. |
| HTTP tests on the customer's PC? | Behind `WINKICKOFF_HTTP_TESTS=1` until the CI run and the customer confirm that binding `127.0.0.1:0` raises no firewall dialog; then the gate is removed. | Open question 6 of section 11; a firewall dialog would be a visible system change in spirit. |
| `show_item` in `read` mode? | No, in `edit`. `read` changes nothing in the window, not even the selection. | Consistent with "read-only by default" as the customer worded it; moving it to `read` later is one line. |
| `plan_apply` and `list_imports` as tools? | Not in 1.2. `get_status` lists the shown imports; the apply plan is a candidate for 1.3. | Fewer tools; nothing in the plan is needed for the read and edit use cases. |
| Profile names: ASCII or Unicode? | Unicode: NFC-normalised, alphanumeric by `str.isalnum()` plus space, underscore, dot and hyphen. | The customer's profiles are Cyrillic and the target users are Ukrainian; an ASCII-only name check would hide `Профіль.json` from `list_profiles`, `diff_profile` and `load_profile` and let `save_profile` create only names the window cannot show as the customer's own (review finding 3). |
| How large may a result be? | `MAX_RESULT_BYTES = 200_000`; default `limit` 100; the unpaginated rules resource lists built-in rules only. | Claude Code's default tool output limit is 25,000 tokens, roughly 100 KB (`MAX_MCP_OUTPUT_TOKENS` raises it); a 2 MB result would be truncated or refused by the client instead of answered with `result_too_large` by the server (review finding 17). |

## 1. Goals and non-goals

Goals:

1. An MCP server (protocol revision 2025-06-18, JSON-RPC 2.0) inside WinKickOff with two transports: stdio (an AI client
   starts WinKickOff as a subprocess, no window) and Streamable HTTP on `127.0.0.1` (started and stopped from the running
   window; also headless for tests and a VM). It works with Claude Code (stdio and HTTP), Claude Desktop (stdio) and any
   client built on the official SDKs, including dual-era clients that probe with `server/discover` first.
2. Read-only by default on both transports: the AI client can read the catalog, the open profile with secrets redacted,
   validation results, a redacted preview of the answer file and the documentation shipped with the program. Two further
   modes, `edit` (change the open profile in memory) and `files` (create new files inside `profiles/` and `output/`), are
   off at every start and switched on by the user for the current session only.
3. Start, stop and monitoring from the tkinter window: an `MCP` menu, a monitor window with the request journal, a status
   bar segment. The user sees every change the agent made as an unsaved change in the tree, as after their own clicks.
4. Standard library only, `unittest` only, no third-party MCP SDK: the JSON-RPC framing, the MCP handshake and the HTTP
   handler on `http.server` are written by hand.
5. The customer rules stay intact: nothing on the PC changes because an AI client asked; the server never runs PowerShell,
   never elevates, never deletes, never imports templates, never changes settings, never returns a password or a product
   key. The test suite proves it without a window, without a network beyond loopback port 0 and without `powershell.exe`.
6. Small modules with one job each and four new concepts for the reader of the code: mode, workspace, bridge, journal.

Non-goals (out of 1.2; several are out for good):

1. Server-Sent Events, server-initiated notifications, `resources/subscribe`, `listChanged`, prompts, sampling,
   elicitation, tasks, progress notifications, resumability. Every POST is answered with `application/json`, every GET
   with `405`; the 2025-03-26 and 2025-06-18 texts allow it and the SDK clients handle it.
2. OAuth. Authentication is a static bearer token generated by the program.
3. TLS, IPv6 `[::1]` (a second loopback listener is a candidate for 1.3, section 11), non-loopback binding, a bind
   address setting of any kind, remote use.
4. The 2026-07-28 stateless revision (`server/discover`). The server answers it with `-32601`, which makes dual-era
   clients fall back to `initialize`.
5. Any MCP tool that runs a process: no PowerShell syntax check, no audit, no apply, no undo, no revert, no opening of
   folders or URLs.
6. Overwriting, deleting or renaming any file through MCP; ADMX import through MCP; settings changes through MCP; control
   of the server from inside the protocol.
7. Editing accounts, languages and installation data through MCP (candidates for 1.3, section 11).

## 2. Modes

Three modes, ordered, named `read`, `edit`, `files`. Each mode includes the previous one. Every tool declares the
minimum mode it needs. The current mode is one value held by `McpService.mode` and read at every `tools/call`, so a
change in the window applies to the next call.

| Mode | The agent may | Default |
|---|---|---|
| `read` | Read the catalog, groups, rules, dependencies and translated texts; read the open profile (redacted); list presets and saved profile names; compare the open profile with a named one; run the pure Python checks (`validate_profile`, `Renderer.build`, `validate_xml`); read a redacted preview of the answer file and of the embedded scripts; read the messages panel. Nothing is written, nothing in memory changes, not even the selection. | Yes, at every start of the window and of every headless process |
| `edit` | Everything in `read`, plus: switch rules on and off with the same cascade the window applies (`Resolver` plus linked policies), switch a group on, off or back to its defaults, set rule parameters, set the profile name, author and comment, load a preset or a saved profile into the window by name (refused while unsaved changes exist unless `force`), select a node in the tree. All of it changes only the profile in memory; the window shows the unsaved marker and the user saves by hand. | Off |
| `files` | Everything in `edit`, plus: save the open profile under a new validated name inside `profiles/`, write an answer file under a new validated name inside `output/`. Existing files are never replaced. | Off |

Never available in any mode. The tool registry has no handler for these, and `tests/test_mcp_tools.py::
test_forbidden_functions_unreachable` proves it by patching them with failing side effects and calling every tool and
resource in `files` mode:

- `apply.launch_elevated`, `apply.run_audit`, `MainWindow.apply_now`, `revert_now`, `audit_selected`: a UAC prompt
  triggered by an agent is the social-engineering path the customer rule forbids; an audit is generated code run on the
  PC and its report leaks the machine state to the AI vendor.
- `pscheck.check_scripts`: spawns `powershell.exe -ExecutionPolicy Bypass`.
- `admx.save_import`, `admx.read_templates` on a caller-given folder, `admx.rename_import`, `admx.delete_import`
  (`shutil.rmtree`), `MainWindow.import_templates`.
- Any deletion, overwrite or rename of a file, anywhere.
- `Settings` reads or writes through the protocol: `allow_apply`, language, theme, recent files, the MCP port, the
  token, the mode itself, autostart. An agent must not raise its own permissions.
- Passwords and product keys in either direction: no tool returns them, no tool sets them.
- Raw contents of `profiles/*.json`, `output/*.xml`, `logs/*`, `settings.json`, `admx/**`.
- Tools that accept a file system path. Every file argument is a name checked by `check_name` and resolved inside one
  fixed folder; no tool schema has a property whose name contains `path` (asserted by a test).
- Server control from inside the protocol: no stop, restart, mode change or token rotation.
- `change_language`, `change_theme`, `show_templates` and the other window rebuilds; `_open_folder`, `os.startfile`.

How the mode is chosen:

- Command line (stdio and headless HTTP): `--mode read|edit|files`, default `read`. The user writes the flag into the AI
  client configuration by hand. There is no `--allow-all`. The "Copy client configuration (stdio)" action of the window
  writes `--mode edit` only when the window is in `edit` or `files` mode and never writes `--mode files`.
- Settings: the mode is not persisted. `settings.json` keeps the port, the token and the autostart flag; autostart
  always starts in `read`.
- Window: three radio items in the `MCP` menu and the same combo box in the monitor. Selecting `edit` is immediate.
  Selecting `files` asks once per session with `messagebox.askyesno(icon="warning", default="no")`: "Clients will be
  able to create profiles and answer files inside the program folder. Existing files are never replaced. Continue?".
  Closing the window resets the mode; the next start is `read` again.
- The mode is orthogonal to `settings.allow_apply`: the MCP layer never reads that flag and never reaches the apply code.

## 3. Architecture

### 3.1 New modules

All under `WinKickOff/winkickoff/`. `mcp/` imports nothing from `ui/` and never imports `tkinter` (a test asserts it);
`ui/` holds the two window-side files. Sizes are estimates of lines including docstrings.

| Module | Responsibility | Lines |
|---|---|---|
| `mcp/__init__.py` | `PROTOCOL_VERSION = "2025-06-18"`, `SUPPORTED_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")` (versions the server echoes), `HEADER_VERSIONS = SUPPORTED_VERSIONS + ("2025-11-25",)` (accepted in the HTTP header), `MODES = ("read", "edit", "files")`, `allows(current, required) -> bool`, `SERVER_NAME = "winkickoff"`, `ENDPOINT = "/mcp"`, `DEFAULT_PORT = 47831`, limits (`MAX_MESSAGE_BYTES = 1_000_000` for one stdio line and for one HTTP body alike, `DRAIN_LIMIT = 4_000_000`, `BRIDGE_TIMEOUT = 5.0`, `WRITE_TIMEOUT = 30.0`, `MAX_RESULT_BYTES = 200_000`, `DEFAULT_LIMIT = 100`, `MAX_LIMIT = 500`, `MAX_CONCURRENT = 4`, `MAX_SESSIONS = 16`) | 55 |
| `mcp/jsonrpc.py` | `JsonRpcError(Exception)` with `code`, `message`, `data`; constants `PARSE_ERROR = -32700`, `INVALID_REQUEST = -32600`, `METHOD_NOT_FOUND = -32601`, `INVALID_PARAMS = -32602`, `INTERNAL_ERROR = -32603`, `RESOURCE_NOT_FOUND = -32002`; `parse_message(text: bytes | str) -> dict` (rejects arrays with `INVALID_REQUEST` "batches are not supported", requires `jsonrpc == "2.0"`, `id` a string or an integer and never null when present, `params` an object when present); `response(id, result)`, `error_response(id, code, message, data=None)`; `dumps(obj) -> bytes` (`ensure_ascii=False`, `separators=(",", ":")`, UTF-8, asserts no newline) | 140 |
| `mcp/schema.py` | A small JSON Schema checker for tool arguments: `type` (a string or a list of strings, any of which may match), `properties`, `required`, `additionalProperties`, `enum`, `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, `items` (nested schema, so object schemas inside arrays work), `minItems`, `maxItems`; `check(schema, value) -> list[str]` (paths and reasons). `integer` never accepts a boolean. Nothing else of JSON Schema is needed; the exact schema texts of `set_param.value` and `set_rules.items` are given in section 4.2 and are the test fixtures of the checker | 150 |
| `mcp/redact.py` | `clean_text(text, limit) -> str` (removes C0 and C1 control characters except `\n` and `\t`, removes U+200B to U+200F, U+202A to U+202E, U+2060 to U+2064, U+2066 to U+2069, U+FEFF, truncates at `limit` with the suffix ` [truncated]`); caps `TITLE = 200`, `SUMMARY = 400`, `EFFECT = 2000`, `EXPLAIN = 4000`, `OTHER = 400`; `clean_json(value) -> value` (walks a JSON-like structure); `redact_profile(data) -> dict` (from `Profile.to_dict()`: every `accounts[].password` becomes the boolean `has_password`, `install.product_key` becomes `has_product_key`); `redact_differences(diffs) -> list[dict]` (kind `install`, key `product_key`: `before` and `after` replaced by `"<hidden>"`); `redacted_copy(profile) -> Profile` (deep copy with passwords and the product key blanked, used for the preview build); `assert_redacted_build(result: BuildResult) -> None` (structural check of section 4.4, raises `RedactionError`); `check_name(name: str) -> str | None` (the reason a file name is refused, `None` when accepted; the rule of section 3.7); `safe_child(folder: Path, name: str, suffix: str) -> Path` (`check_name`, not starting with `preset-`; resolves, requires `resolved.parent == folder.resolve()`, refuses symlinks and reparse points on the folder and on the file) | 190 |
| `mcp/workspace.py` | `Snapshot` frozen dataclass (`catalog`, `profile` copy, `resources`, `paths`, `dirty`, `profile_file: str`, `selected: str`, `issues: list[Issue]`, `language`); `class Workspace(Protocol)` with `snapshot() -> Snapshot`, `set_rules(items: list[tuple[str, bool]]) -> list[Change]`, `set_group(group_id, action) -> list[Change]`, `set_param(rule_id, name, value) -> None`, `set_profile_info(name, author, comment) -> None`, `load_profile(path, force) -> list[str]`, `show_item(item) -> bool`, `save_profile_to(path) -> None`, `write_answer_file_to(path) -> list[Issue]`, `is_busy() -> bool`; `HeadlessWorkspace(paths, catalog, profile, resources)` implementing it with `Resolver`, `linked.redundant` (the six lines of `_drop_redundant`), `validate_profile`, `Renderer`, `Profile.save` and `render.write_answer_file`; helpers `profile_file(paths, name) -> Path` (the preset ids `office`, `strict`, `laptop`, `home` resolve to `paths.data / "profiles" / "preset-<id>.json"`, everything else to `safe_child(paths.profiles, name, ".json")`) and `list_profile_files(paths) -> list[dict]` (scans `paths.data / "profiles"` for `preset-*.json` and `paths.profiles` for user files; the two folders differ in the frozen build, `_internal\profiles` versus the folder next to the exe, and coincide only when running from sources) | 290 |
| `mcp/bridge.py` | `Bridge`: `queue.Queue[Item]` where `Item` holds `fn: Callable[[Workspace], Any]`, `writes: bool`, `future: concurrent.futures.Future`, `deadline: float` (monotonic), `state: "queued" | "running" | "abandoned" | "done"` guarded by a `threading.Lock`, and `journal_seq` (the journal entry to annotate); `run(fn, *, writes, timeout) -> Any` from server threads; `attach(workspace)` / `detach()`; `pump(max_items=20, budget=0.05)` called from the tkinter main thread through `after(50, ...)`; `fail_all(exc)` on stop; `InlineBridge` subclass whose `run` calls `fn` directly under an `RLock` (headless) | 150 |
| `mcp/tools.py` | `ToolSpec(name, title, description, mode, input_schema, annotations, handler)`; `ToolRegistry` with `specs() -> list[dict]` for `tools/list`, `call(name, arguments, mode, bridge, texts) -> dict` (mode check, argument validation with `schema.check`, then handler); the 18 handlers of section 4; `texts(language) -> CatalogTexts` cached per code from `CatalogTexts.load(paths.rules, code)`; every handler receives `(bridge, args, texts)` and returns a JSON object that `call` wraps into `{"content": [{"type": "text", "text": json}], "structuredContent": obj, "isError": false}`; failures raised as `ToolError(kind, message, data)` become `isError: true` with `structuredContent: {"error": kind, ...}` | 650 |
| `mcp/resources.py` | `ResourceRegistry`: static entries and templates of section 5, `list()`, `templates()`, `read(uri, bridge) -> dict`; URI parsing is a hand-written split on `://` and `/` plus the ASCII file name regex of section 5 (the current `test_sources.py` regex would let `from urllib.parse import urlsplit` through, but ten lines of splitting do not justify a second look-alike exception) | 170 |
| `mcp/protocol.py` | `Session` dataclass (`id`, `created`, `last_seen`, `client_name`, `client_version`, `protocol_version`, `initialized: bool` (set when the `initialize` result is produced), `acknowledged: bool` (set by `notifications/initialized`, monitor only), `transport`); `McpServer(tools, resources, service_state, info)` with `handle(message: dict, session: Session) -> dict | None` (returns `None` for notifications): `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, `resources/list`, `resources/templates/list`, `resources/read`, `notifications/cancelled` and other notifications ignored, everything else `-32601`; a request other than `initialize` and `ping` on a session that has not seen `initialize` gets `-32600 "not initialized: send initialize first"`; every handler wrapped: `JsonRpcError` becomes an error response, any other exception becomes `-32603 "internal error"` without traceback; the failure is logged as `"%s: %s"` (method or tool name, exception class name) at ERROR on `logging.getLogger("winkickoff.mcp")` and the traceback at DEBUG only, so no argument text reaches a log file at the default level; the journal entry is written here so both transports log the same way | 310 |
| `mcp/journal.py` | `Entry(seq, time, transport, client, method, tool, args: str, ok: bool, ms: int, note: str)` where `args` is the whitelisted scalar rendering (`rule_id=x enabled=true`, free text as `<text, 120 chars>`); `Journal` with `collections.deque(maxlen=1000)`, a `threading.Lock`, `append`, `annotate(seq, note)` (used by the bridge for "completed after timeout"), `since(seq)`, `count`, `last_time`. No headers, no bodies, no token, no file | 100 |
| `mcp/httpserver.py` | The only module allowed to import `http.server`, `socketserver` and names from `socket`. `McpHttpServer(ThreadingHTTPServer)` with `allow_reuse_address = False`, `daemon_threads = True`, `block_on_close = False`, `request_queue_size = 8`, a `server_bind` override that on win32 sets `SO_EXCLUSIVEADDRUSE` before `super().server_bind()` (section 3.4) and a `serving = threading.Event()` set by the serving thread; `McpHandler(BaseHTTPRequestHandler)` of section 3.4; `start_http(port, token, server, journal) -> McpHttpServer` binding the literal `("127.0.0.1", port)` and reading the port back from `server_address[1]`; `serve(httpd)` (the wrapper the serving thread runs: `httpd.serving.set()` then `serve_forever(poll_interval=0.5)`) | 350 |
| `mcp/stdio.py` | `serve_stdio(reader: BinaryIO, writer: BinaryIO, server: McpServer, session: Session) -> int`: the line loop of section 3.3; `open_std_streams() -> tuple[BinaryIO, BinaryIO] | None` (`sys.stdin.buffer` and `sys.stdout.buffer` when present, else `os.fdopen(0, "rb", buffering=0)` and `os.fdopen(1, "wb", buffering=0)` after `os.fstat` succeeds on both descriptors, else `None`) | 120 |
| `mcp/service.py` | `McpService`: owns `mode`, `port`, the running `McpHttpServer` and its thread, the `Bridge`, the `Journal`, the `McpServer`, a reference to the live `Settings` object and a `save_settings` callback (both given by `configure`, section 3.4); `configure(settings, save_settings)`, `start_http(port) -> int` (bound port; generates and saves the token through the callback when `settings.mcp_token` is empty; main thread only), `stop(join_timeout=3.0)`, `attach(workspace)`, `detach()`, `set_mode(mode)`, `rotate_token()` (stops, generates, saves through the callback), `running -> bool`, `status() -> ServiceStatus(running, port, mode, requests, last_time, sessions)`, `client_config(kind: "stdio" | "http", paths) -> str`. One instance per process, created in `app.run()` | 240 |
| `mcp/cli.py` | `parse_args(argv) -> tuple[Namespace, list[str]]` (`argparse`, `allow_abbrev=False`, `parse_known_args`; extras are an error only when `--mcp` or `--mcp-config` is present), `run_headless(args) -> int` (section 3.6), `print_client_config(kind) -> int` (`--mcp-config`), `emit(text) -> bool` (writes to `sys.stdout` when it exists, otherwise logs "no console: use python.exe or WinKickOff-mcp.exe for this flag" and returns `False`, on which the caller exits 3); `main(argv) -> int` for the second executable; imports nothing from `winkickoff.app` and nothing from `tkinter`; the only file of `mcp/` allowed to use `print` (usage, `--version`, `--mcp-config`, all through `emit`) | 190 |
| `mcp_main.py` (package root) | Console entry for the second executable: `from winkickoff.mcp.cli import main; sys.exit(main(["--mcp", "stdio"] + sys.argv[1:]))`, so the client snippet is just `WinKickOff-mcp.exe --mode read` | 10 |
| `__main__.py` (rewritten) | The dispatcher of section 3.6: parses `sys.argv[1:]` with `winkickoff.mcp.cli.parse_args`, runs `run_headless` for `--mcp`, `--mcp-config` and `--version` before `winkickoff.app` is imported, and only otherwise imports `winkickoff.app` and calls `run(args, extras)`. A parser error (`SystemExit(2)`) with `--mcp` or `--mcp-config` on the command line exits 2 as a console program; without them it is shown through `winkickoff.app._fatal` (the window path, where `tkinter` is allowed) | 40 |
| `core/startup.py` | `initial_profile(paths, catalog, settings)` and `DEFAULT_PRESET` moved out of `app.py`, imported by `app.py` and `mcp/cli.py`; no tkinter import | 40 |
| `ui/mcp_workspace.py` | `WindowWorkspace(window)`: the `Workspace` protocol implemented on `MainWindow`, calling the dialog-free methods of section 3.5; runs only on the main thread (called from `Bridge.pump`); `install_pump(window, bridge) -> str` returns the `after` id that the window stores and cancels in `destroy()`; the pump is installed only when the window has a service and the service is attached | 180 |
| `ui/mcp_window.py` | `McpMonitor(tk.Toplevel)` of section 7.2 | 340 |

Changed modules: `__main__.py` (the dispatcher above), `app.py` (`run(args, extras)` receives parsed arguments, logs
and ignores `extras`, owns the service, calls `service.configure` in `create_app`, `_fatal` kept for the window path
only, `initial_profile` imported from `core/startup.py`), `core/log.py` (`setup_logging(paths, filename="winkickoff.log")`
and a `delay` argument), `ui/main_window.py` (menu, status segment, the `modal()` counter around every dialog, dialog-free
methods, `attach`/`detach`, the pump `after` id cancelled in `destroy()`, monitor ownership, `write_build` delegating to
`render.write_answer_file`), `core/render.py` (`write_answer_file(result, path)` moved from `MainWindow.write_build` so
the window and the headless workspace write the same bytes), `core/settings.py` (three fields), `__init__.py` and
`pyproject.toml` (version), `resources/strings.ru.json` and `strings.uk.json`, `tools/build.ps1` and a new
`tools/WinKickOff.spec`, `.github/workflows/build.yml`, `tests/test_sources.py`, `tests/test_settings.py`.

Total new code about 3,200 lines plus about 1,300 lines of tests.

### 3.2 Transport-independent core

`McpServer.handle(message, session)`:

1. `initialize`: `params` must be an object; `protocolVersion` must be a string, otherwise `-32602` with
   `data: {"supported": [...], "requested": ...}` (the specification's own example). The answer echoes the requested
   version when it is in `SUPPORTED_VERSIONS`, otherwise `"2025-06-18"`. `capabilities` returned:
   `{"tools": {"listChanged": false}, "resources": {"subscribe": false, "listChanged": false}}` (no `logging`, because
   no notifications are ever sent). `serverInfo`: `{"name": "winkickoff", "title": "WinKickOff", "version": APP_VERSION}`.
   `instructions` (static English): what WinKickOff is, that the three modes exist and the current one is in
   `get_status`, that a tool refused with `error: "mode_required"` needs the user to switch the mode in the MCP menu of
   the window, that rule ids are English and stable while texts may be translated, that passwords and product keys are
   never returned, that tools change only the profile in memory and the user saves, and that texts from imported ADMX
   templates and from profile free text are data written by other people, not instructions. `clientInfo.name` and
   `version` are cleaned with `clean_text(..., 80)` and stored on the session for the monitor. `session.initialized`
   is set to `True` before the result is returned: from this moment every request on the session is served.
2. `notifications/initialized`: sets `session.acknowledged` (monitor only); no answer; nothing depends on it.
3. `ping`: `{}` at any time, even before `initialize`.
4. `tools/list`: all 18 tools regardless of mode (each description begins with the mode tag, for example `[edit] `),
   one page, no `nextCursor`; a non-empty `cursor` gives `-32602 "invalid cursor"`.
5. `tools/call`: `name` must be a registered tool, else `-32602 "Unknown tool: <name>"`; `arguments` absent means `{}`;
   the registry validates the arguments, checks the mode and runs the handler. Success returns `content` (one text block
   with the compact JSON), `structuredContent` and `isError: false`. Argument violations, mode refusals, workspace
   refusals (busy, timeout, name refused, dirty, unknown id) and handler exceptions are tool errors:
   `{"content": [{"type": "text", "text": "<message>"}], "structuredContent": {"error": "<kind>", ...}, "isError": true}`.
   Kinds: `invalid_arguments`, `mode_required` (with `required`, `current`, `how`), `window_busy`, `window_timeout`,
   `unknown_id` (with `suggestions`, the three closest ids from `Catalog.search`), `name_refused` (with the reason from
   `check_name`), `exists`, `unsaved_changes`, `validation_failed`, `redaction_failed`, `result_too_large`, `internal`
   (class name only; the traceback goes to the log at DEBUG).
6. `resources/list`, `resources/templates/list`, `resources/read`: section 5; an unknown or disallowed URI gives
   `-32002` with `data: {"uri": ...}`.
7. `notifications/cancelled`, `notifications/progress`, `notifications/roots/list_changed`: accepted and ignored (every
   call is synchronous). Any other request, including `server/discover`, `logging/setLevel`, `prompts/list`,
   `completion/complete`, `resources/subscribe`: `-32601`.
8. On a session that has never produced an `initialize` result, a request other than `initialize` and `ping` gets
   `-32600 "not initialized: send initialize first"`; never silence, so a dual-era client falls back correctly. On stdio
   this is the single session before its first `initialize`; on HTTP a session object exists only after `initialize`,
   so the refusal is reached only through `ping`-less messages without a session id, which the transport answers with
   `400` before the core sees them (section 3.4, check 10).

Result size: after serialisation a result larger than `MAX_RESULT_BYTES` (200 KB) is replaced by a `result_too_large`
tool error ("narrow the query: use group, query, limit and offset"); the tools that can grow have `limit` (default 100,
at most 500) and `offset`. The user documentation names `MAX_MCP_OUTPUT_TOKENS` for Claude Code users who want larger
answers; the server limit stays below the client default so that the server, not the client, reports the overflow.

Concurrency: `McpServer.handle` holds one `threading.Lock` around `tools/call` and `resources/read`, so tool execution
is serialised; `ping`, `initialize` and the lists do not take it.

### 3.3 stdio transport

- `serve_stdio` reads `reader.readline(MAX_MESSAGE_BYTES + 1)` in the main thread of the headless process (Windows has
  no `select` on pipes; blocking reads are the only portable choice). When the returned chunk does not end with `b"\n"`
  and is not the final chunk before EOF, the line is over-long: the loop keeps calling `readline(MAX_MESSAGE_BYTES + 1)`
  and discarding the chunks until one ends with `b"\n"` or EOF, then answers a single `-32700` with `id: null` and
  continues with the next line; the tail of an over-long line is never parsed as a message. Invalid UTF-8 or invalid JSON
  is answered with `-32700` and `id: null` as well, and the loop continues. EOF ends the loop; the function returns 0 and
  the process exits. `KeyboardInterrupt` and `BrokenPipeError` return 0 as well. One limit, `MAX_MESSAGE_BYTES` (1 MB),
  applies to a stdio line and to an HTTP body alike.
- Every answer is one line: `dumps(obj) + b"\n"`, then `writer.flush()`. `json.dumps` with `ensure_ascii=False` and no
  `indent` never emits a raw newline (U+2028 and U+2029 are not newlines for `readline`); a defensive assertion guards it.
- stdout carries nothing else. `setup_logging(paths, filename=f"mcp-stdio-{os.getpid()}.log", delay=True)` runs before
  anything else so `logging.lastResort` never fires; the file handler is the only handler; `logging.captureWarnings(True)`
  routes Python warnings into the log; `print` is used only in `mcp/cli.py` for usage, `--version` and `--mcp-config`
  (`test_sources.py` forbids `print(` in the rest of `mcp/`). `sys.stderr` may be `None` without harm; Claude Desktop's
  `mcp-server-winkickoff.log` stays empty and the user documentation points at `logs\mcp-stdio-<pid>.log`.
- Log files of headless processes: one file per process (`mcp-stdio-<pid>.log`, `mcp-http-<pid>.log`), so no two
  processes ever share a `RotatingFileHandler` target and `doRollover` never meets a file another process holds open;
  `delay=True` opens the file at the first record. `run_headless` removes files matching `logs/mcp-*.log*` older than
  seven days at start (housekeeping of its own files, not reachable through the protocol, tested with a stale fixture).
  The window keeps `logs/winkickoff.log` exactly as today, so `test_portable.py` keeps its file list.
- One `Session(transport="stdio")`; `initialize` is still required before other requests (section 3.2, item 8).
- Termination: the client closes stdin (EOF), then `TerminateProcess`; nothing runs in other threads, so nothing needs
  cleanup.

### 3.4 HTTP transport

Bind: `("127.0.0.1", port)` only. The host string is a constant in `httpserver.py`; there is no setting, flag or
argument for it. `test_sources.py` asserts that `start_http` in `winkickoff/mcp/httpserver.py` contains the literal
`("127.0.0.1",`, and that no file in the package contains `0\.0\.0\.0`, `"::"` or `bind\(\s*\(\s*""` (the last three
patterns are safe package-wide; an unrestricted empty-tuple pattern would match the WORKFLOW table of `main_window.py`
eight times).

Port: `settings.mcp_port`, default `47831`, or `0` for an OS-chosen port; the bound port is read back from
`server_address[1]` and shown in the UI. `allow_reuse_address = False`, so a second WinKickOff or any other program gets
`OSError`, which the UI reports as "port 47831 is used by another program; choose another port in the monitor". No
attempt is made to talk to a foreign listener.

Port squatting (threat 6): on Windows a listening socket without `SO_EXCLUSIVEADDRUSE` can be hijacked by another
process of the same user that binds the same address with `SO_REUSEADDR` and receives the new connections, including the
bearer token Claude Code sends. `McpHttpServer.server_bind` therefore sets `SO_EXCLUSIVEADDRUSE` on win32 before
`super().server_bind()`; the module imports `from socket import SOL_SOCKET, SO_EXCLUSIVEADDRUSE` (guarded for non-Windows,
where the name does not exist). `test_sources.py` adds `winkickoff/mcp/httpserver.py` to an explicit allow list for
`from socket import` with the comment "loopback listener, off by default, started by the user, task T22", and the test
`test_exclusive_bind` (win32 only, behind the HTTP gate) binds a second socket with `SO_REUSEADDR` to the bound port and
asserts `OSError`.

Handler `McpHandler(BaseHTTPRequestHandler)`:

- `protocol_version = "HTTP/1.1"` on the wire, but every response carries an exact `Content-Length` and `Connection:
  close`, and `close_connection = True` after every response: no keep-alive, no idle handler threads, `shutdown()`
  returns within the poll interval. `timeout = 30` (socket read timeout). `server_version = "WinKickOff"`,
  `sys_version = ""`, so no Python or product version reaches an unauthenticated caller. `log_message` and `log_error`
  write to `logging.getLogger("winkickoff.mcp.http")` at DEBUG with the request line only.
- A `threading.BoundedSemaphore(MAX_CONCURRENT)` around the dispatch: beyond four concurrent requests the handler
  answers `503` with `Retry-After: 1`.
- Order of checks for every request; each failing check ends the request with a minimal response and no JSON-RPC
  processing, so banner grabbing gets nothing before authentication:
  1. `Host` must equal `127.0.0.1:<port>` or `localhost:<port>` (host part case-insensitive); else `421`, empty body.
     `localhost` stays in the allow list for hand-written clients such as curl; the documented URL is always
     `http://127.0.0.1:<port>/mcp`, because Node 17+ resolves `localhost` to `::1` first and this server listens on IPv4
     only (section 6, troubleshooting).
  2. `Origin`, if present, must equal `http://127.0.0.1:<port>` or `http://localhost:<port>`; else `403`. `null` is
     refused. This is the DNS rebinding and CSRF check the specification requires. No CORS headers, ever.
  3. `Authorization` must be `Bearer <token>` compared with `hmac.compare_digest`; missing or wrong gives `401` with an
     empty body and no `WWW-Authenticate`. The token is never accepted in the query string.
  4. Path must be exactly `/mcp` with no query string; everything else, including `/.well-known/*`, gives `404` with an
     empty body.
  5. Method: `POST` continues; `DELETE` ends the session named by `Mcp-Session-Id` (`204`, or `404` if unknown); `GET`
     returns `405` with `Allow: POST, DELETE` (no SSE stream is offered; the TypeScript client treats `405` on GET as
     "no stream"); `OPTIONS`, `HEAD` and everything else `405`.
  6. `MCP-Protocol-Version` (case-insensitive): absent means `2025-03-26`; a value in `HEADER_VERSIONS` is accepted;
     anything else `400`.
  7. `Transfer-Encoding` present: `411`. `Content-Length` missing: `411`. `Content-Length` larger than
     `MAX_MESSAGE_BYTES`: the handler first drains the body, reading and discarding `min(Content-Length, DRAIN_LIMIT)`
     bytes in 64 KB chunks under the socket timeout, then answers `413` and closes. Without the drain Windows sends RST
     for the unread bytes and Node's fetch reports "socket hang up" instead of the status. A body larger than
     `DRAIN_LIMIT` (4 MB) is answered `413` after the first 4 MB and the connection is closed; that client sees the RST,
     which is acceptable for a request no SDK client ever sends. Otherwise the body is read with exactly the declared
     length.
  8. `Content-Type` must start with `application/json` (parameters such as `charset=utf-8` allowed); else `415`.
     `Accept` absent, `*/*` or containing `application/json` is accepted (the SDK sends both media types; refusing a
     hand-written client for a missing `text/event-stream` gains nothing); else `406`.
  9. Body parsing: an array gives `400` with a JSON-RPC `-32600` body; other parse errors `400` with a `-32700` body
     (`id: null`).
  10. Session: an `initialize` request creates a `Session` with `id = secrets.token_urlsafe(24)`, marks it
      `initialized` together with the result and returns the id in `Mcp-Session-Id`. A `ping` request is answered with
      or without a session id. Any other message must carry `Mcp-Session-Id`; missing gives `400`, unknown gives `404`
      (the client re-initializes, as the specification requires; the SDK clients do it on their own). At most 16
      sessions; the oldest by `last_seen` is evicted. There is no idle expiry: a session ends when the server stops, on
      `DELETE`, or by eviction. Sessions are not authentication (the token is); they exist to know the client name for
      the monitor and to give a restarted server a clean `404`.
  11. Dispatch: a notification or a response body gives `202` with an empty body; a request gives `200`,
      `Content-Type: application/json; charset=utf-8`, exact `Content-Length`, `Cache-Control: no-store`, the JSON-RPC
      response. Server exceptions become a `-32603` body, still `200` (the JSON-RPC layer carries the error).
- Threads: `ThreadingHTTPServer` gives one thread per connection; with `Connection: close` a thread lives for one
  request. The serving thread `threading.Thread(target=serve, args=(httpd,), name="mcp-http", daemon=True)` runs the
  wrapper `serve`, which sets `httpd.serving` and then calls `serve_forever(poll_interval=0.5)`.
- Stop: `McpService.stop()` sets `_stopping` and then, only when `httpd.serving.is_set()` and `thread.is_alive()`, calls
  `httpd.shutdown()` from the calling thread (never from the serving thread); in every other case (the thread never
  entered `serve_forever`, died, or was never started) it skips `shutdown()`, because `BaseServer.shutdown()` waits on an
  event that only `serve_forever` sets and would block the tkinter main thread forever. Then `server_close()`,
  `thread.join(3.0)`, `bridge.fail_all(RuntimeError("server stopped"))`, one log line. `block_on_close = False` and
  `Connection: close` make this return at once even with a client connected. A test calls `stop()` on a service whose
  serving thread was never started and asserts it returns within one second.

Token and settings ownership. The window's `self.settings` is the only object that writes `settings.json`.
`create_app` loads `Settings`, passes them to `service.configure(settings, save_settings)` before the window exists,
and the window then holds the same object as `self.settings`; after a window rebuild `create_app` loads the settings again
and calls `configure` again with the new object and the new window's `save_settings`. Token generation happens inside
`service.start_http` on the main thread when `settings.mcp_token` is empty or invalid: `settings.mcp_token =
secrets.token_urlsafe(32)` (43 characters, regex `^[A-Za-z0-9_-]{32,64}$`) followed by the `save_settings` callback,
which is `window.save_settings`. "New access token" in the menu calls `service.rotate_token()`: stops a running server,
sets the new value on the same object and saves through the same callback. A headless process never writes the token:
`--mcp http` takes `--token` from the command line or `settings.mcp_token` from the file and exits 2 with "no access
token: start the server once from the window or pass --token" when both are empty. The token is never logged, never
drawn in clear text in a widget (the monitor shows `abcd...wxyz` with a "Copy token" button), and reaches the clipboard
only through the copy actions. Where the token lives ("settings.json in the program folder") is stated in the user
document. The test `test_token_survives_window_rebuild` rotates the token, destroys the window with a restart state,
builds the next window through `create_app`, calls `save_settings` and asserts the file still holds the rotated value.

Windows Firewall: a listener bound to `127.0.0.1` should create no rule and no prompt (loopback traffic is not filtered);
this is confirmed by the CI run and the VM acceptance before the HTTP tests run on the customer's PC (section 9, section 11).

### 3.5 Bridge between server threads and the tkinter main thread

- Rule: no tkinter call, no `Profile` access and no `Catalog` construction from a server thread. `Catalog` objects are
  immutable after `with_imports` and may be read from any thread; `Profile` is not thread-safe and is only ever touched
  on the main thread.
- Every read tool starts with `snapshot = bridge.run(lambda ws: ws.snapshot(), writes=False, timeout=BRIDGE_TIMEOUT)`.
  `snapshot()` runs on the main thread and returns the shared catalog reference, `profile.copy()` (a deep copy of a small
  object, milliseconds), the dirty flag, the selection, the current issues and the language. Heavy work
  (`Renderer.build`, `validate_profile`, `validate_xml`, rendering of actions) then runs on the server thread against
  the copy, so reads never block the UI for longer than a deep copy.
- Write tools submit one closure with `writes=True` and `timeout=WRITE_TIMEOUT` that performs the whole change on the
  main thread (`ws.set_rules(...)`), which is what the window does today when the user clicks; the closure returns the
  list of `Change` and the new issues. One tree refresh per call, not per rule.
- `Bridge.run`: creates an `Item` with a `Future` and `deadline = monotonic() + timeout`, puts it on the queue and waits
  `future.result(timeout)`. On `TimeoutError` it takes the item lock: if the state is still `queued`, it sets
  `abandoned` and raises `ToolError("window_timeout", "the editor window did not answer in N s (busy, modal dialog or
  restarting)")`; if the state is `running`, the closure has already started on the main thread and cannot be undone, so
  `run` waits up to `BRIDGE_TIMEOUT` more for the result and returns it when it arrives; if even that expires it raises
  `window_timeout`, and when the closure finishes later, `pump` annotates the journal entry with "completed after
  timeout". `Future.cancel()` is not used: it fails once `set_running_or_notify_cancel()` was called and would make the
  late change invisible to the journal.
- `Bridge.pump` (main thread, every 50 ms while attached) takes items; under the item lock it skips items whose state is
  `abandoned` or whose `deadline` has passed (failing their future with `window_timeout` so a waiting caller returns at
  once) and marks the rest `running` before calling the closure. A closure that started completes and its change is
  visible in the window as an unsaved change; the design text and `mcp.md` state this: a change reported as
  `window_timeout` may still have landed, and `get_profile` shows the truth.
- Busy and modal states. `MainWindow` gets a modal counter `self._modal = 0` and a context manager `self.modal()`
  (increment on enter, decrement on exit) wrapped around every `messagebox` and `filedialog` call of the `ui/` package;
  today all 36 calls live in `main_window.py` and `data_forms.py` has none, and a source test keeps it so:
  every line of `winkickoff/ui/**/*.py` that contains `messagebox.` or `filedialog.` must be inside a `with self.modal():`
  block, checked by requiring the same line or the nearest preceding non-blank line to contain `with self.modal():`
  (multi-line calls put the call on the first line after the `with`). `is_busy()` returns `self._busy or self._modal > 0
  or self.grab_current() is not None`: native Windows dialogs (`MessageBoxW`, the common file dialogs) do not set a Tk
  grab, so the counter is what catches `confirm_discard` ("Save changes?"), `_finish_build`'s `asksaveasfilename` (which
  opens after `set_busy(False)`) and every other dialog; the grab covers Tk-drawn dialogs and any future ones. `pump`
  runs from `after` while a dialog is open (Tk timers keep ticking under the nested Windows message loop); it checks
  `ws.is_busy()` and, for write closures, fails the future with `ToolError("window_busy", ...)` immediately while reads
  proceed (the busy thread of a build never touches `profile`, and a dialog only reads it). Whether `after` fires under
  `MessageBoxW` is verified in the VM acceptance (section 12, step 11): a read call must be answered while a message box
  is open; should it not tick on some Windows build, reads time out with `window_timeout` after `BRIDGE_TIMEOUT`, which
  the documentation states as the fallback behaviour.
- Window rebuild (language, theme, ADMX change): `MainWindow.destroy()` cancels the pump `after` id
  (`self._pump_after`) and calls `service.detach()` next to `menu_margins.stop()`, before `super().destroy()`, so no
  callback fires on a destroyed interpreter; queued futures wait; the new window's `__init__` calls
  `service.attach(WindowWorkspace(self))` and installs the pump again, so a call that arrives during the rebuild is
  served by the new window or times out with a clear error. The `McpService` is created in `app.run()` and passed to
  `create_app(..., service=service)`; `MainWindow.__init__` keeps `service: McpService | None = None`: with `None` the
  window is inert (MCP menu items disabled, no `attach`, no pump, no status refresh), so `test_portable.py`,
  `test_ui_smoke.py` and every test that constructs windows directly stay unchanged. A test destroys a window with an
  attached service and pumps `update()` afterwards without a `TclError`.
- Headless: `InlineBridge.run` calls the closure directly on the reader thread under an `RLock`.

Dialog-free methods added to `MainWindow` (the halves of existing methods that follow a dialog; the window's own
handlers call them too, so behaviour stays single-sourced): `apply_rule_states(items) -> list[Change]` (from
`toggle_item`: `resolver.set_rule` per item, `_drop_redundant`, `_apply_changes`, `refresh_marks`, `mark_dirty`,
`show_item`; a partly covered linked policy is refused with the text of the window's own question instead of asking),
`apply_group_action(group_id, action)` (`on`, `off`, `defaults` onto `resolver.set_group` and `reset_group`, with the
same imported-group refusal as the window), `set_param_value(rule_id, name, value) -> str | None` (the validated core
of `_set_param` and `_set_param_text`, returning the error text instead of showing it), `set_profile_info(name, author,
comment)`, `save_profile_to(path)` (the tail of `save_profile_as` with the `preset-` refusal, recent list and title
update), `write_answer_file_to(path) -> list[Issue]` (`run_checks(with_powershell=False)` plus
`render.write_answer_file`, refused when validation has errors; appends the `info` issue of section 4.3),
`current_issues() -> list[Issue]`, `is_busy() -> bool`, `modal()`. `load_profile_file(path)` and `select_node(item)`
already exist; `load_profile_file` gains a `confirm: bool = True` argument so the workspace can refuse instead of asking.

### 3.6 Headless operation

`winkickoff/__main__.py` is the dispatcher for `python -m winkickoff` and for `WinKickOff.exe` (which PyInstaller
builds from it). It parses the arguments with `winkickoff.mcp.cli.parse_args` first; for `--mcp`, `--mcp-config` and
`--version` it calls `run_headless` and exits with its code before `winkickoff.app` is imported; only for the window path
does it import `winkickoff.app` and call `run(args, extras)`. `app.py` keeps its module-level `tkinter` import because
the headless path never reaches it; `mcp/cli.py`, `mcp_main.py` and `core/startup.py` do not import `app.py`. The proof
is a subprocess test: `python -X importtime -m winkickoff --version` and `python -X importtime -m winkickoff --mcp stdio
--profile <preset>` with an empty stdin (EOF at once, exit 0) must produce an `importtime` trace on stderr that contains
no line for `tkinter` or `_tkinter`; the second run writes only `logs/mcp-stdio-<pid>.log` inside the project folder,
which the test removes afterwards. The old formulation ("tkinter absent from `sys.modules` after `run_headless`") is
dropped: it could not be observed from outside the process and was false on the previous dispatcher.

`run_headless` for `--mcp stdio`: `paths = app_paths()`, `setup_logging(paths, filename=f"mcp-stdio-{pid}.log",
delay=True)`, `logging.captureWarnings(True)`, the log housekeeping of section 3.3, `Settings.load` (never saved),
language from `--language` or `settings.language` applied once with `set_language` (the process is headless, so the
global is safe), `load_catalog(paths.rules, docs_root=paths.docs_root)` inside `try/except CatalogError` (log and exit
2, no `tk.Tk`), `with_imports(catalog, paths.admx, settings.admx, language())`, `Resources.load`, the profile from
`--profile` else `startup.initial_profile(paths, catalog, settings)`, then `HeadlessWorkspace` behind an `InlineBridge`
and the transport loop.

`--mcp http` headless serves the same workspace behind the HTTP transport with `serve_forever` in the main thread and
`Ctrl+C` to stop; the log file is `mcp-http-<pid>.log`; the token comes from `--token` or `settings.mcp_token` and is
never generated or saved by this process (section 3.4); it exists for tests and VM use and gets one line of
documentation.

`--version` and `--mcp-config` go through `cli.emit`: with a console the text is printed and the exit code is 0; in a
`--noconsole` process without inherited handles (`sys.stdout is None`) the text cannot be shown, so `emit` logs one line
and the process exits 3. The user document says these two flags are for `python.exe` and `WinKickOff-mcp.exe`, not for
`WinKickOff.exe`.

### 3.7 File names

`check_name(name)` accepts a profile or answer file name when all of the following hold, and otherwise returns the
first failing reason as a short English text used in the `name_refused` error: after `unicodedata.normalize("NFC")`
the name has 1 to 80 code points; every character satisfies `c.isalnum()` or is one of space, `_`, `.`, `-`; the first
character is alphanumeric; the name has no leading or trailing space or dot; it does not contain `..`; it contains no
`/` or `\` (already excluded by the character rule, asserted separately); its stem compared case-insensitively is not a
reserved device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`). `str.isalnum()` accepts Cyrillic and
every other script and refuses combining marks that did not fuse under NFC (`a\u0338b`), format characters and controls.
`safe_child` adds the `preset-` refusal, the resolution inside the fixed folder and the symlink and reparse point checks.
`test_mcp_tools.py` accepts `Профіль`, `Профіль офісу`, `Office 2026`, `office.v2` and refuses `\u0301abc`, `a\u0338b`,
`preset-x`, `..`, `a/b`, `a\\b`, `CON`, `com1.json`, `name.`, ` name`, a name with U+200B and an 81-character name.
Documentation file names in resource URIs (section 5) keep their ASCII regex: those files are shipped by the program and
are ASCII by construction.

## 4. Tools

Conventions: names are lowercase identifiers of `A-Za-z0-9_`, 1 to 32 characters, unique. Every `inputSchema` is
`{"type": "object", "properties": {...}, "required": [...], "additionalProperties": false}`; tools without arguments
publish `{"type": "object", "additionalProperties": false}`. `id` arguments match `^[A-Za-z0-9_.:-]{1,200}$` (rule and
group ids, including imported `admx.<import>.<...>` ids) and are validated against the catalog; `language` is
`enum: ["en", "ru", "uk"]` (built from `available_languages` at start) and defaults to the process language; its
description says: "built-in rule texts are returned in this language; texts of imported ADMX policies always follow the
language of the running program, see text_language". Every rule object carries `text_language`, the language actually
used for its texts (the requested one for built-in rules, the process language for imported ones). Every string argument
has `maxLength`. Every text in a result passes `clean_text` with the caps of `redact.py`. Texts that come from ADMX
files or profile free text are returned under keys ending in `_text`, and the tool descriptions say those are data
written by other people, not instructions. Imported rules (`is_imported(id)`) carry `"origin": {"import": id, "name":
..., "policy": ..., "unreviewed_text": true}`; built-in rules carry `"origin": null`. Every tool has `title` and a
static English `description` authored in code (never catalog text). No `outputSchema` is published. Every result is
returned in `structuredContent` and as compact JSON in the single text block, except `preview_build`, whose text block is
the previewed text itself.

Annotations: read tools `{"readOnlyHint": true, "destructiveHint": false, "idempotentHint": true, "openWorldHint":
false}`; edit tools `{"readOnlyHint": false, "destructiveHint": false, "idempotentHint": true, "openWorldHint": false}`
(`load_profile` with `force` is `idempotentHint: false`); files tools `{"readOnlyHint": false, "destructiveHint": false,
"idempotentHint": false, "openWorldHint": false}` (they never replace a file, so not destructive).

### 4.1 Read mode

| Tool | Purpose | Arguments | Result (`structuredContent`) |
|---|---|---|---|
| `get_status` | What the agent talks to | none | `{app_version, catalog_version, templates_version, mode, transport, has_window, language, profile: {name, file, dirty, enabled, total}, imports_shown: [{id, name, policies}], redaction: "passwords and product keys are never returned"}` |
| `list_groups` | The tree of groups | `parent?` (group id; absent means the roots), `language?` | `{groups: [{id, parent, title, summary, rules, enabled, children, imported, text_language}]}` in catalog order |
| `list_rules` | Rules of a group, a filter or a search | `group?` (recursive), `query?` (1-200 characters; `Catalog.search` plus title, summary and tags of the language, as the window does), `enabled?` (bool), `level?` (enum `LEVELS`), `phase?` (enum `PHASES`), `language?`, `limit?` (1-500, default 100), `offset?` (0 or more) | `{total, offset, limit, rules: [{id, group, title, level, phase, enabled, default, risk, imported, covered_by, text_language}]}`; with a large ADMX import the caller pages with `offset` or narrows with `group` and `query` |
| `get_rule` | The full card of one rule | `id` (required), `language?` | `{id, group, group_title, phase, level, title, summary, effect, risk, versions, default, enabled, tags, requires, required_by, conflicts, same_values, dependents (Resolver.dependents), linked: {rule, equal, covered} or null, params: [{name, type, title, value, default, min, max, values: [{value, title}]}], actions: [{type, text}] (render_action with the current parameters), verify_steps, rollback_steps, doc: "docs/technical/reference/NN-x.md#anchor" or null, origin, text_language}`; an unknown id is a tool error `unknown_id` with the three closest ids from `Catalog.search` |
| `get_profile` | The open profile, redacted | none | `redact_profile(profile.to_dict(catalog))` plus `{file, dirty, enabled_count, changed_from_defaults: [ids]}`; accounts appear as `{name, display_name, group, description_text, has_password}`, `install` has `has_product_key` instead of `product_key`, `comment_text` and `author_text` are the free texts |
| `list_profiles` | Presets and saved profiles by name | none | `{profiles: [{name (file stem without preset-), kind: "preset" or "user", title_text, modified, catalog_version}], unlisted}`; presets from `paths.data / "profiles"`, user files from `paths.profiles`; names only, never absolute paths; files whose stem fails `check_name` are counted in `unlisted` (with the Unicode rule of section 3.7 the customer's Cyrillic profiles are listed) |
| `diff_profile` | Differences between the open profile and a named one | `name` (required; a preset id or a saved profile name, 1-80 characters, checked by `check_name`) | `{other: name, differences: redact_differences(profile.diff(other, catalog))}` with `{kind, key, before, after}` rows; the other profile is loaded through `profile_file` and `safe_child` |
| `check_profile` | The same as F7 without PowerShell, on a copy | `language?` | `{ok, errors, warnings, issues: [{level, target, message, doc}], build: {rules, warnings} or null, language, issues_language}` (`validate_profile`, `Renderer.build`, `validate_xml`); never PowerShell; `issues_language` is the process language, in which `tr()` renders the messages |
| `preview_build` | The text the build would write, from a copy without secrets | `part?` (enum: `autounattend.xml` default, `Setup-System.ps1`, `Setup-User.ps1`, `Post-OOBE.ps1`) | text block with the text; `structuredContent: {part, parts, bytes, truncated, redacted: true}`; built from `redacted_copy(profile)` so `<Password><Value>`, `<ProductKey><Key>` and the `Extensions/Profile` JSON hold no secret by construction, then re-checked structurally with `assert_redacted_build` (a `redaction_failed` tool error rather than the text when it fails); never writes |
| `get_messages` | The messages panel of the window (headless: the last check) | none | `{issues: [{level, target, message, doc}], issues_language}` |

### 4.2 Edit mode

| Tool | Purpose | Arguments | Result |
|---|---|---|---|
| `set_rules` | Switch rules on or off with the cascade of the tree | `items` (array of `{id, enabled}`, 1-200; exact schema below) | `{changes: [{id, enabled, reason}], refused: [{id, reason}], dirty: true, issues_errors}`; one main-thread closure, one tree refresh; a partly covered linked imported policy is refused with the text of the window's own question |
| `set_group` | The group check box | `id` (required), `action` (enum `on`, `off`, `defaults`) | as `set_rules`; an imported group can only be switched off (same rule as the window) |
| `set_param` | One rule parameter | `id`, `name` (1-64), `value` (exact schema below) | `{id, name, value, dirty: true}`; validated with the parameter type, `min`, `max`, `values` and `validate.list_problem` as the window does; the change is rejected and the profile restored when `validate_profile` afterwards reports an error that was not there before (`validation_failed` with the messages) |
| `set_profile_info` | Name, author, comment of the open profile | `name?` (1-80), `author?` (0-80), `comment?` (0-2000) | `{name, author, comment, dirty: true}`; control characters stripped |
| `load_profile` | Open a preset or a saved profile in the window | `name` (required, checked by `check_name`), `force?` (bool, default false) | `{name, file, warnings}`; refused with `unsaved_changes` when the window is dirty and `force` is false; with `force` the unsaved changes are dropped without a dialog and the journal shows it |
| `show_item` | Point the window at a rule, group or form | `item` (`r:<rule>`, `g:<group>`, `data:accounts`, `data:languages`, `data:install`; 1-140) | `{shown: bool, reason?}` (`false` with `"no window"` headless) |

Exact schemas the checker must validate (they are also fixtures of `test_mcp_protocol.py` for `schema.check`):

```json
"set_rules": {"type": "object", "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 200,
  "items": {"type": "object", "properties": {"id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,200}$"},
  "enabled": {"type": "boolean"}}, "required": ["id", "enabled"], "additionalProperties": false}}},
  "required": ["items"], "additionalProperties": false}

"set_param.value": {"type": ["string", "integer", "boolean", "array"], "maxLength": 4000,
  "items": {"type": "string", "maxLength": 4000}, "maxItems": 200}
```

`schema.check` applies `maxLength` only when the value is a string, `items` and `maxItems` only when it is an array,
and refuses a boolean for `integer`. The handler additionally caps the joined length of an array value at 4000
characters (`invalid_arguments`).

### 4.3 Files mode

| Tool | Purpose | Arguments | Result |
|---|---|---|---|
| `save_profile` | Save the open profile as `profiles/<name>.json` | `name` (required, 1-80, checked by `check_name`) | `{file: "profiles/<name>.json", dirty: false}`; target through `safe_child` (refuses `preset-*`, refuses an existing file with `exists`: "choose another name, WinKickOff never replaces files through MCP"); runs `ws.save_profile_to(path)` on the main thread, which updates the title and the recent list |
| `write_answer_file` | Build and write `output/<name>.xml` (real build with secrets; text not returned) | `name` (required, 1-80, checked by `check_name`) | `{file: "output/<name>.xml", rules, issues}`; refuses an existing file; runs `ws.write_answer_file_to(path)`, which refuses when validation has errors. Unlike the window's Build, no PowerShell syntax check runs (section 0), so every result carries an `issues` entry `{level: "info", target: "powershell", message: "PowerShell syntax not checked (use Check in the window)"}`; the tool description and `mcp.md` say the same. The user renames the file to `autounattend.xml` when copying it to the installation media (documented) |

### 4.4 Redaction, always on

- `get_profile`, `diff_profile`, `winkickoff://profile` go through `redact_profile` and `redact_differences`.
- `preview_build` builds from `redacted_copy(profile)` and then runs `assert_redacted_build(result)`, a structural check
  of the build: every `<Value>` element under a `<Password>` element in the XML is empty or absent, every `<Key>` under
  `<ProductKey>` is empty or absent, and the JSON in `Extensions/Profile` parses with every `accounts[].password == ""`
  and `install.product_key == ""`. A substring search for the secret values is not used: short or common passwords
  (`1`, `Admin`, `2026`) are substrings of ordinary content and would make the tool refuse exactly the starter profiles
  this toolkit produces.
- Tool error messages are composed by the program from identifiers; the journal never holds argument values beyond the
  whitelisted scalars (section 7.2); the log holds tool names and exception class names, never argument text (section
  3.1, `protocol.py`).
- `tests/test_mcp_tools.py::test_no_secret_leaves_any_tool` builds a profile with the password `Zq9!secretPW-7731` and
  the product key `ABCDE-FGHIJ-KLMNO-PQRST-UVWXY` (long and unique, so a substring assertion is meaningful in the test),
  calls every registered tool with representative arguments and every resource in `files` mode, and asserts that neither
  string appears in any result, in the journal or in the log records captured with `assertLogs("winkickoff.mcp",
  level="DEBUG")`. The test attaches its own handler to the `winkickoff.mcp` logger instead of relying on
  `setup_logging`, which returns early when an earlier test in the same process already installed a file handler.

### 4.5 Candidates for 1.3, not in 1.2

`plan_apply` (the apply plan as text, nothing rendered or run), editing of installation, languages and accounts through
a `set_data` tool (passwords and product keys stay excluded), a `check_profile` with the PowerShell syntax check behind
its own opt-in with a semaphore and a cool-down, a stdio-to-window attach mode for Claude Desktop (section 11), a second
listener on `[::1]`.

## 5. Resources

Capability `resources: {"subscribe": false, "listChanged": false}`. URIs use the custom scheme `winkickoff:`
(RFC 3986). `resources/list` returns the fixed entries and one entry per documentation file the templates can address
(about 60 entries, one page); `resources/templates/list` returns the templates; `resources/read` returns
`{"contents": [{"uri", "mimeType", "text"}]}` and resolves against an allow list built at start, never from request text
to a path. All resources are read-only and available in every mode. Every resource result is subject to
`MAX_RESULT_BYTES` like a tool result.

| URI | Content | mimeType |
|---|---|---|
| `winkickoff://status` | Same JSON as `get_status` | `application/json` |
| `winkickoff://profile` | Same JSON as `get_profile` (redacted) | `application/json` |
| `winkickoff://catalog/groups` | The whole group tree with counts | `application/json` |
| `winkickoff://catalog/rules` | Ids, titles and state of the built-in rules only (about 250 rows, well under 200 KB) plus `{"imports": [{id, name, policies}], "note": "imported policies are listed by list_rules with group or query"}` | `application/json` |
| `winkickoff://messages` | The messages panel | `application/json` |
| `winkickoff://catalog/rules/{id}` (template) | Same JSON as `get_rule` in the process language | `application/json` |
| `winkickoff://docs/reference/{file}` (template) | A file of `docs/technical/reference/*.md` shipped with the program; `{file}` must match `^[A-Za-z0-9][A-Za-z0-9-]{0,60}\.md$` and be in the listing taken at start; capped at 64 KB | `text/markdown` |
| `winkickoff://docs/user/{lang}/{file}` (template) | A file of `docs/user/{ru,uk,en}/*.md` under the same rules | `text/markdown` |

Documentation files are resolved from `paths.docs_root`, checked with `resolved.is_relative_to(...)` after the allow
list, and passed through `clean_text(text, 65536)`. Unknown scheme, unknown path, a file name outside the allow list or a
missing file: `-32002` with `data: {"uri": ...}`. The appendices, the technical editor documentation, `AGENTS.md`,
`settings.json` and `logs/` are not addressable.

## 6. Command line

`python -m winkickoff` and `WinKickOff.exe` share the dispatcher `winkickoff/__main__.py` and the parser
`mcp.cli.parse_args` (`argparse`, `allow_abbrev=False`, `parse_known_args`). Without `--mcp`, `--mcp-config` and
`--version` the window starts as today: unknown extra arguments (a file dropped onto the shortcut, a Windows "Open with"
path, anything `Start-WinKickOff.cmd` forwards through `%*`) are logged at INFO and ignored, exactly as they are ignored
today. Strict parsing (extras are an error, exit 2) applies only when `--mcp` or `--mcp-config` is present. A parser
error on the window path (for example `--mode bad` without `--mcp`) is shown in a `messagebox` through `app._fatal`
instead of being written to a `None` stderr.

| Flag | Meaning |
|---|---|
| `--mcp stdio` | Headless stdio server (section 3.3); no window; exit 0 on EOF, 2 on a start-up error, 3 when no usable standard streams exist. Must be started with `python.exe`, never `pythonw.exe`. |
| `--mcp http` | Headless HTTP server on `127.0.0.1` (for tests and a VM); runs until Ctrl+C; never writes settings; needs `--token` or a token already in `settings.json`. |
| `--port N` | Port for `--mcp http` (0 or 1024-65535; default `settings.mcp_port`). |
| `--token TOKEN` | Bearer token for `--mcp http` (regex `^[A-Za-z0-9_-]{32,64}$`); overrides `settings.mcp_token` for this process only. |
| `--mode read|edit|files` | Mode (default `read`). |
| `--profile NAME_OR_PATH` | A preset id (`office`, `strict`, `laptop`, `home`), a saved profile name in `profiles/`, or an absolute path. A path is accepted here because the command line is written by the user into the client configuration, the same trust level as the window's Open dialog. Default: `initial_profile()` (the last profile of the window, else the Office preset). |
| `--language CODE` | Text language (`en`, `ru`, `uk`); default `settings.language`, then Windows. |
| `--mcp-config stdio|http` | Print the client configuration JSON to stdout and exit (console only; the same text as the copy actions of the window), so a developer can run `claude mcp add-json winkickoff "$(python -m winkickoff --mcp-config stdio)"`. For `python.exe` and `WinKickOff-mcp.exe`; in `WinKickOff.exe` without a console it exits 3. |
| `--version` | Print `WinKickOff 1.2.0-rc.1` and exit; the same console rule as `--mcp-config`. |

The `--noconsole` problem and its solution. `WinKickOff.exe` is built with `--noconsole`; in such a process `sys.stdin`,
`sys.stdout` and `sys.stderr` are `None` when started from a shell. A parent that redirects pipes usually gives valid
handles 0, 1 and 2 through `STARTF_USESTDHANDLES`, and CPython then creates the stream objects, but a protocol channel
must not depend on how a given client spawns the process. Two layers, both in 1.2:

1. Code: `stdio.open_std_streams()` uses `sys.stdin.buffer` and `sys.stdout.buffer` when they exist, otherwise
   `os.fdopen(0, "rb", buffering=0)` and `os.fdopen(1, "wb", buffering=0)` after `os.fstat` succeeds on both
   descriptors; when nothing works it logs "no standard streams: start the stdio server from python.exe or
   WinKickOff-mcp.exe" and exits 3. `--version` and `--mcp-config` use `cli.emit` with the same exit code 3.
2. Build: `tools/build.ps1` switches from the long `PyInstaller` command line to the spec file `tools/WinKickOff.spec`
   kept in the repository: two `Analysis` objects (`winkickoff/__main__.py` and `winkickoff/mcp_main.py`), two `EXE`
   objects (`name="WinKickOff", console=False` and `name="WinKickOff-mcp", console=True`) and one `COLLECT`, so both
   executables share `_internal\`. `build.ps1` runs `PyInstaller --noconfirm --clean tools\WinKickOff.spec` and its
   artifact check requires both `dist\WinKickOff\WinKickOff.exe` and `dist\WinKickOff\WinKickOff-mcp.exe`.
   `.github/workflows/build.yml` checks the same and adds a smoke step that runs after `Compress-Archive` has written
   the zip: copy `dist\WinKickOff` to `$env:RUNNER_TEMP\smoke`, pipe one `initialize` line into
   `WinKickOff-mcp.exe` there with PowerShell, assert the answer contains `"protocolVersion"`, and assert afterwards
   that `dist\WinKickOff` contains no `logs`, `profiles` or `output` folder and no `settings.json` (running the exe
   inside `dist\WinKickOff` before the zip would ship those folders and a log file inside the release). This is the
   only concrete proof against the `--noconsole` risk, and it runs in CI or a VM only; the customer's PC never builds.
   `app_paths()` derives the root from `sys.executable`, so both executables share `settings.json`, `profiles/`,
   `output/`, `logs/`, `admx/`.

Documented commands: from the build `WinKickOff-mcp.exe` (recommended; `--mcp stdio` is implied by `mcp_main.py`),
`WinKickOff.exe --mcp stdio` (works when the client passes pipes); from sources `python -m winkickoff --mcp stdio`.

Client configuration snippets produced by `McpService.client_config` (the words `APPDATA` and similar are forbidden in
package sources by `test_sources.py`; the location of `claude_desktop_config.json` is stated in the user document only):

```json
{"mcpServers": {"winkickoff": {"command": "C:\\...\\WinKickOff\\WinKickOff-mcp.exe", "args": ["--mode", "read"]}}}
{"mcpServers": {"winkickoff": {"type": "http", "url": "http://127.0.0.1:47831/mcp", "headers": {"Authorization": "Bearer <token>"}}}}
```

From sources the stdio snippet is `"command": "<python.exe>", "args": ["-m", "winkickoff", "--mcp", "stdio"]` with
`sys.executable` and `pythonw.exe` replaced by `python.exe` when needed; the user starts the client from the `WinKickOff`
folder or the snippet names the module by its absolute path (`--profile` and `app_paths()` do not depend on the working
directory). `--mode edit` is appended when the window mode is `edit` or `files`; `--mode files` is never written.

Claude Code commands for the user documentation: `claude mcp add winkickoff -- "C:\...\WinKickOff-mcp.exe" --mode read`
and `claude mcp add --transport http winkickoff http://127.0.0.1:47831/mcp --header "Authorization: Bearer <token>"`.
The URL must use `127.0.0.1`, never `localhost`: Node 17+ resolves `localhost` to `::1` first, the server listens on
IPv4 only, and the client would see "connection refused" or a slow Happy Eyeballs fallback; `mcp.md` and its
troubleshooting section say so, and the copy actions never produce the `localhost` form. Claude Desktop: the stdio
snippet pasted into its configuration file. Claude Desktop cannot use the HTTP server (custom connectors must be reachable
from the internet, which this server never is), so it drives its own headless copy of the profile through stdio, not the
open window; the documentation says so.

## 7. UI

### 7.1 MCP menu

`_build_menu()` adds `self._build_mcp_menu(self._top_menu("MCP"))` after the ADMX menu (label untranslated like
"ADMX"). Items, all through `tr()`; every item is disabled when the window was built with `service=None`:

- checkbutton "Server running (HTTP, this computer only)" bound to `self.mcp_running_var`, command `toggle_mcp_server`:
  start calls `service.start_http(self.settings.mcp_port)` (which may generate the token into `self.settings` and save
  through `self.save_settings`); a bind error shows `messagebox.showerror` (inside `self.modal()`) with "The MCP server
  did not start: port {0} is used by another program. Choose another port in the monitor." and resets the variable,
  like `toggle_allow_apply`; stop calls `service.stop()`.
- separator; radiobuttons "Read only", "Read and change the open profile", "Change and create files" bound to
  `self.mcp_mode_var` (`read`, `edit`, `files`), command `change_mcp_mode`; `files` asks the warning of section 2 and
  falls back to the previous value on "No"; enabled while the server runs (the mode is live).
- separator; "Monitor..." (`open_mcp_monitor`), "Copy client configuration (stdio)", "Copy client configuration (HTTP)"
  (contains the token; disabled while the server is stopped, because with port 0 the port is known only then; the status
  bar says "Configuration with the access token copied to the clipboard" and the journal gets an event without the
  value), "New access token" (asks `askyesno` "Clients configured with the old token stop working. Continue?"; calls
  `service.rotate_token()`, which stops a running server, sets `self.settings.mcp_token` and saves through
  `self.save_settings`).
- separator; checkbutton "Start the server with the program (read only)" bound to `settings.mcp_autostart`, saved at
  once through `self.save_settings`.
- "Documentation" opening `docs/user/<lang>/mcp.md` through the existing `open_doc`.

### 7.2 Monitor window (`ui/mcp_window.py`)

`McpMonitor(tk.Toplevel)`, one instance per main window (`self.mcp_monitor`), `transient` to the main window,
`withdraw` on close so reopening keeps the filters, styled with the existing theme helpers, `_style_text` and `font_mono`:

- Row 1: state label ("Stopped" or "Running on http://127.0.0.1:47831/mcp, mode: read only, clients seen: 2"),
  "Start"/"Stop" button, "Port" `ttk.Spinbox` (0 or 1024-65535; 0 shown with the hint "0 = any free port") editable
  only while stopped and saved on change through `window.save_settings`, "Mode" read-only `ttk.Combobox` with the three
  translated titles (live, the `files` warning applies), "Start with the program (read only)" check box.
- Row 2: token masked as `abcd...wxyz` in a label, "Copy token", "Copy client configuration (stdio)", "Copy client
  configuration (HTTP)". The token is never drawn in clear text.
- Table `ttk.Treeview(columns=("time", "transport", "client", "method", "tool", "arguments", "ms", "result"))`, newest
  at the bottom, auto-scroll when the view is at the end; `arguments` shows the whitelisted scalars of the journal entry
  (`id=edge.signin-off enabled=true`, `name=<text, 12 chars>`); `result` shows `ok`, `error <code>`, or the program's
  short note (`mode_required`, `window_busy`, `window_timeout`, `unknown_tool`, `exists`, `completed after timeout`);
  error rows tagged in the theme's error colour. No request or response bodies, no headers, no token anywhere in the
  window.
- Filter row: substring `ttk.Entry` on method and tool, "Errors only" check box, transport `ttk.Combobox` (`all`, `http`,
  `stdio`); filtering re-renders from the ring buffer.
- Buttons: "Copy row", "Copy visible rows" (tab separated, through `clipboard_clear()` and `clipboard_append()`),
  "Clear", "Close".
- A note line: "stdio servers started by a client run as separate processes and are not shown here; they log into
  logs\mcp-stdio-<pid>.log".
- Refresh: `self.after(250, self._refresh)` reads `Journal.since(self._seen_seq)`; the `after` id is stored and
  cancelled in `destroy`. Server threads never call into the monitor.

### 7.3 Status bar

A second right-aligned label next to the existing status label (built in `_build_body`), `self.mcp_status_var`:
"MCP: off" or "MCP: 127.0.0.1:47831, read only, 12 requests, last 14:02:11"; refreshed by the bridge pump only when
`Journal.count` changed, and immediately on start, stop and mode change. Double-click opens the monitor. With
`service=None` the label shows "MCP: off" and never changes.

Every new string goes through `tr()` and gets its `ru` and `uk` lines in `resources/strings.ru.json` and
`strings.uk.json` (about 50 strings; `test_i18n.py` fails otherwise). Identifiers (`read`, `edit`, `files`, tool names,
JSON keys, header names, URIs) never go through `tr()`.

### 7.4 Lifecycle in `__main__.py` and `app.py`

```python
# winkickoff/__main__.py
def main(argv: list[str] | None = None) -> int:
    from winkickoff.mcp.cli import parse_args, run_headless   # no tkinter behind this import
    raw = sys.argv[1:] if argv is None else argv
    try:
        args, extras = parse_args(raw)
    except SystemExit as exc:
        if any(a.startswith("--mcp") for a in raw):
            return int(exc.code or 2)          # console use: argparse already wrote the message
        from winkickoff.app import _fatal      # window path: show the message
        _fatal(str(exc))
    if args.mcp or args.mcp_config or args.version:
        return run_headless(args)
    from winkickoff.app import run             # the only place that imports tkinter
    run(args, extras)
    return 0
```

```python
# winkickoff/app.py
def run(args, extras: list[str]) -> None:
    if extras:
        log.info("ignored arguments: %s", extras)
    service = McpService()
    state = None
    try:
        while True:
            root = create_app(state=state, service=service)
            root.mainloop()
            state = getattr(root, "restart_state", None)
            if not state:
                break
    finally:
        service.stop(join_timeout=3.0)
```

`create_app(..., service=None)` keeps its signature for `test_portable.py` (which patches `app.app_paths` and
`app._enable_dpi_awareness` and calls `create_app(withdraw=True)`). When `service` is not `None`, `create_app` calls
`service.configure(settings, save_settings=lambda: root.save_settings())` after the window exists (the callback binds to
the window that owns `settings`), and `MainWindow.__init__` calls `service.attach(WindowWorkspace(self))` and stores the
`after` id of `install_pump`; `destroy()` cancels that id and calls `service.detach()` before `super().destroy()`. When
`service` is `None` the window is inert: no service object is created, no pump runs, the MCP menu is disabled. Autostart:
`create_app` calls `service.start_http(settings.mcp_port)` in `read` mode after the window exists when
`settings.mcp_autostart` is set and the service is not running; a bind error becomes a `problems` entry shown by
`show_problems`. The server keeps its port and token across window rebuilds (language, theme, ADMX), so client
configurations stay valid; `configure` is called again with the freshly loaded settings of the new window, which already
contain the token because the previous window saved it. After `mainloop()` returns for good, `run()` stops the server
explicitly; a daemon thread frozen at interpreter shutdown while holding a lock or a socket can produce a fatal error on
exit, so cleanup never relies on daemon status.

## 8. Settings fields

Added to `core/settings.py` (dataclass fields, validated in `load` like `geometry` and `admx`, written by `save` in the
explicit `data` dict; `test_round_trip_without_leftovers` asserts the symmetry):

| Field | Type, default | Validation in `load` |
|---|---|---|
| `mcp_port` | `int`, `47831` | `isinstance(v, int) and not isinstance(v, bool) and (v == 0 or 1024 <= v <= 65535)`, else default |
| `mcp_token` | `str`, `""` | regex `^[A-Za-z0-9_-]{32,64}$`, else `""` (a new token is generated and saved at the next start of a server from the window) |
| `mcp_autostart` | `bool`, `False` | `data.get("mcp_autostart") is True` |

Not stored: the mode (always `read` at start), the running state, the bound port, sessions, the journal. `allow_apply`
stays orthogonal: it has no effect on MCP and MCP cannot change it. Writer: only the window's `self.settings` through
`save_settings`, `remember_file` and the menu actions; the service holds a reference to that object and a callback, never
its own `Settings`; headless processes never write. `tests/test_settings.py` gets: defaults, damaged values
(`"mcp_port": "80"`, `true`, `70000`, `-1`, `"mcp_token": "short"`), the round trip.

Documentation of the fields: the settings row of `WinKickOff/README.md` ("Where things are stored"),
`docs/technical/editor/03-data-model.md` (settings section), the user document `mcp.md` (where the token lives, how to
rotate it, that a headless HTTP server needs `--token` or a token saved by the window).

## 9. Tests

All tests use `unittest`, temporary folders from `tempfile.TemporaryDirectory()`, `AppPaths` built as in
`tests/test_ui_smoke.py::setUpClass` (root in the temporary folder, `data=ROOT`, `docs_root=ROOT.parent`, so `data`
and `root` differ as in the frozen build), and mock `apply_module.launch_elevated` and `run_audit` on every window. No
test starts PowerShell, opens a visible window (withdrawn or alpha 0 off-screen), writes outside the temporary folder
(the two `-X importtime` subprocesses write one log file inside the project's `logs/` and remove it), or binds anything
but `127.0.0.1` port `0`. Runner unchanged: `python -m unittest discover -s tests -v`. The HTTP and window-HTTP tests are
guarded by `@unittest.skipUnless(os.environ.get("WINKICKOFF_HTTP_TESTS") == "1", ...)`; CI sets the variable; the guard
is removed after the customer confirms that the loopback bind raises no firewall dialog (open question 6). Log
assertions attach their own handler to the `winkickoff.mcp` logger (`assertLogs` or a `StringIO` handler) and never read
the file written by `setup_logging`, which returns early when a handler is already installed.

| Module | Covers |
|---|---|
| `tests/test_mcp_protocol.py` | `jsonrpc.parse_message` on every malformed shape (array, null id, float id, missing method, params not an object, `jsonrpc` missing); `dumps` compact UTF-8 without newlines (a string with U+2028 and with `\n` inside); `schema.check` on each supported keyword, including `type` as a list, nested object `items`, and the exact `set_rules` and `set_param.value` schemas of section 4.2 (a boolean refused for `integer`, an object refused for `value`, `maxLength` ignored for an integer); `McpServer.handle` in memory with a `HeadlessWorkspace` on the real catalog: `initialize` echoes 2025-03-26 and 2025-06-18, answers 2025-06-18 for 2025-11-25 and `"1.0.0"`, gives `-32602` with `data.supported` for a non-string; capabilities shape; `instructions` present; a request before any `initialize` gets `-32600`; a `tools/list` right after the `initialize` result and before `notifications/initialized` succeeds; `ping` before initialize works; `server/discover` gets `-32601`; `notifications/initialized` returns `None` and sets `acknowledged`; `tools/list` lists exactly the 18 names with `title`, `description`, an object schema with `additionalProperties: false`, annotations consistent with the mode, names matching the regex, and no `outputSchema`; unknown tool `-32602`; a handler exception becomes a tool error with the class name only, and `assertLogs("winkickoff.mcp", "ERROR")` shows `"<tool>: <ExceptionClass>"` without the argument text while the traceback appears only at DEBUG; `notifications/cancelled` ignored; the result size cap (patched to 1 KB) produces `result_too_large`; one journal entry per handled message |
| `tests/test_mcp_tools.py` | `HeadlessWorkspace` from `load_catalog(ROOT / "rules")`, the Office preset and `Resources.load`; every tool in `read`, `edit` and `files` mode; the mode refusal shape (`mode_required` with `required`, `current`, `how`); `get_rule` for a built-in and an imported rule (a temporary ADMX import from the `test_admx.py` fixtures) with `origin` and `text_language` (`uk` requested: the built-in rule reports `uk`, the imported one the process language); `list_rules` paging (default `limit` 100) and `query` in `uk`; `get_rule` with an unknown id returns three suggestions; `check_profile` equals `validate_profile` plus `validate_xml`; `preview_build` equals `Renderer.build` on `redacted_copy`, passes `assert_redacted_build`, and `assert_redacted_build` fails on a build of the unredacted profile; `preview_build` works with the passwords `1`, `a`, `Admin` and `2026` (the substring trap); `set_rules` cascade equals `Resolver.set_rule` plus `linked.redundant`; `set_group` `defaults` equals `reset_group`; `set_param` rejects a bad value with the `list_problem` text and rejects a value that introduces a validation error, restoring the profile; `set_profile_info` strips control characters; `load_profile` refuses when dirty without `force`; `list_profiles` with `AppPaths` whose `data` and `root` differ lists the four presets from `data/profiles` and the user files from `root/profiles`, and `profile_file("office")` resolves against `data`; `check_name` accepts and refuses the names of section 3.7; `save_profile` refuses `preset-x`, `..`, `a/b`, `CON`, a trailing dot, a name with a control character, an existing name, a symlink or junction when one can be created (skipped when not permitted), writes `profiles/Профіль.json` that loads back equal; `write_answer_file` refuses an existing file, writes bytes equal to `render.write_answer_file(Renderer.build(...))` and returns the `info` issue about the PowerShell check; `clean_text` strips control and bidi characters and truncates; `test_no_secret_leaves_any_tool` (section 4.4); `test_forbidden_functions_unreachable`: `mock.patch` of `apply.launch_elevated`, `apply.run_audit`, `pscheck.check_scripts`, `admx.save_import`, `admx.delete_import`, `admx.rename_import`, `admx.read_templates`, `Settings.save`, `os.startfile`, `shutil.rmtree`, `Path.unlink`, `os.remove` with side effects that fail the test, then every tool and resource called in `files` mode; `test_no_path_arguments`: no tool schema has a property whose name contains `path` |
| `tests/test_mcp_resources.py` | Lists, templates, reads of status, profile (redacted), a rule, a reference card and a user page; `winkickoff://catalog/rules` holds built-in rules only, under 200 KB, with the imports note when an import is shown; refusals of `..`, absolute paths, a file outside the two folders, `settings.json`, `logs/winkickoff.log`, `AGENTS.md`, an unknown scheme; the 64 KB cap |
| `tests/test_mcp_stdio.py` | `serve_stdio` with `io.BytesIO` streams: a full session (initialize, tools/list before initialized, initialized, tools/call, EOF); one JSON object per line; nothing written for notifications; invalid UTF-8 and invalid JSON give `-32700` and the loop continues; an over-long line (1 MB + 10 bytes, whose tail is itself a valid `ping` request) followed by a valid request produces exactly one `-32700` with `id: null` and then the valid answer; the writer never receives anything but JSON lines; `open_std_streams` with `sys.stdin = None` and `os.fstat` raising returns `None`; the two `-X importtime` subprocess tests of section 3.6 (`--version`, and `--mcp stdio --profile <preset path>` with empty stdin) assert exit codes 0 and no `tkinter` line in the trace; a bad flag with `--mcp` exits 2; the log housekeeping removes a stale `mcp-stdio-1.log` fixture and keeps a fresh one |
| `tests/test_mcp_cli.py` | `parse_args` for every flag; `parse_known_args` on the window path returns extras for a dropped file path and raises `SystemExit(2)` for the same extras with `--mcp stdio`; `--mode files` never appears in a stdio snippet; `--mcp-config` output is valid JSON with the expected keys and the URL uses `127.0.0.1`; `emit` with `sys.stdout = None` returns `False` and logs; `run_headless` with a catalog error exits 2; the headless stdio path never calls `Settings.save` (patched to fail); `--mcp http` with an empty token and no `--token` exits 2 before binding |
| `tests/test_mcp_http.py` | `start_http(0, ...)` in a thread; `http.client.HTTPConnection("127.0.0.1", port, timeout=5)` (allowed in `tests/`): initialize issues `Mcp-Session-Id` and `application/json`; `tools/list` on the new session before `notifications/initialized` succeeds; `202` empty for `notifications/initialized`; `tools/list` and `tools/call` bodies; `ping` without a session id `200`; missing token `401` with an empty body and no `WWW-Authenticate`; wrong token `401`; foreign `Origin` `403`, `Origin: null` `403`, absent `Origin` accepted; foreign `Host` `421`, `Host: localhost:<port>` accepted; GET `405` with `Allow`; OPTIONS `405`; `/other` and `/.well-known/oauth-protected-resource` `404` with an empty body; array body `400` with `-32600`; bad JSON `400` with `-32700`; a 2 MB body sent in full receives status `413` (not a reset); chunked `411`; `Content-Type: text/plain` `415`; `MCP-Protocol-Version: 1.0` `400`, `2025-11-25` and absent accepted; missing session `400`; unknown session `404`; DELETE `204` then `404`; the 17th session evicts the oldest; `503` when five requests block at once (a tool handler patched to wait on an event); `Connection: close` on every response; `Server: WinKickOff` without a version; a second `start_http` on the same port raises `OSError`; on win32 a second socket with `SO_REUSEADDR` on the bound port raises `OSError` (`test_exclusive_bind`); `stop()` returns within 3 s while a client holds an open socket without sending; `stop()` on a service whose serving thread was never started (the thread object created, `start()` never called) returns within one second; the journal has one entry per request and no token text |
| `tests/test_mcp_window.py` | `@unittest.skipUnless(TK_OK)` and the HTTP gate: `MainWindow(paths, catalog, profile, resources, Settings(language="en", theme="light"), service=McpService())` withdrawn, `service.configure(settings, win.save_settings)`; HTTP on port 0; requests sent from a helper thread while the test pumps `win.update()` in a deadline loop (the loop of `test_audit_on_this_pc_shows_statuses`); `set_rules` changes `win.profile`, the tree marks and `win.dirty`; `show_item` selects the node; `win._busy = True` makes writes answer `window_busy` while reads succeed; `with win.modal():` behaves the same, and a mocked `grab_current` too; `messagebox.askyesnocancel` patched to a function that pumps `update()` for 300 ms while inside `modal()` answers a read and refuses a write; `destroy()` with an attached service and `update()` afterwards raise no `TclError`; `destroy()` with a restart state, a second window attached to the same service answers a call queued in between; a write closure that started before the client timeout completes and the journal row is annotated "completed after timeout"; `service.stop()` fails the queued futures; a mode change from the menu applies to the next call; "New access token" stops the server and changes `win.settings.mcp_token`; `test_token_survives_window_rebuild` (section 3.4); the status label changes on start and stop; `McpMonitor` opens, shows rows and closes without errors, and the password of a test profile is absent from every widget text; `create_app(withdraw=True, service=McpService())` with `mcp_autostart` in a temporary `settings.json` starts the server in `read` and `service.stop()` stops it |
| `tests/test_settings.py` | The three new fields (section 8) |
| `tests/test_sources.py` | New rules: `NETWORK_MODULES = {"winkickoff/mcp/httpserver.py"}` is the only file allowed to match `\b(?:from|import) (http\.server|socketserver)\b` or `\bfrom socket import\b`, with a comment "loopback listener, off by default, started by the user, task T22"; that file's `start_http` must contain the literal `("127.0.0.1",`; no file in the package contains `0\.0\.0\.0`, `"::"` or `bind\(\s*\(\s*""`; `print(` is forbidden in `winkickoff/mcp/**` except `cli.py`, and in `mcp_main.py`; `winkickoff/mcp/**`, `core/startup.py` and `__main__.py` contain no `tkinter` import (`test_mcp_package_has_no_tkinter`); every `messagebox.` and `filedialog.` occurrence in `winkickoff/ui/**` is inside `with self.modal():` (section 3.5); the old outgoing-network pattern (`socket`, `urllib`, `http.client`, `requests`) stays for the whole package |
| `tests/test_portable.py` | Unchanged assertions hold (a window built by `create_app(withdraw=True)` has no service, so no pump and no server; the journal is memory only; the window logs into `logs/winkickoff.log` as before); one added assertion: after a headless stdio session in memory (initialize, tools/list, one call) with the log routed to a temporary folder, that folder holds only `mcp-stdio-<pid>.log` |
| `tests/test_i18n.py`, `tests/test_docs.py` | Unchanged; they enforce the translations and the documentation of section 10 |

Expected count: about 236 + 100 tests.

## 10. Documentation and metadata

New files:

- `docs/technical/editor/todo/T22-mcp-server.md` (this document, with the status line updated as work proceeds) and its
  row in `docs/technical/editor/todo/README.md`; `docs/technical/editor/README.md` table entry for `todo/` ("Tasks
  T01-T22", the stale "T01-T17" is fixed) and a row for `07-mcp-server.md`.
- `docs/technical/editor/07-mcp-server.md`: protocol subset and version handling, the HTTP checks in order, sessions
  (no idle expiry, `404` means re-initialize), token ownership (the window's settings object is the only writer), modes
  and the never-available list, the bridge with its deadline rule and the "completed after timeout" case, the modal
  counter, the workspace protocol, the tool table, redaction (structural check), limits (`MAX_RESULT_BYTES` 200 KB,
  `MAX_MESSAGE_BYTES` 1 MB), the journal format, headless operation and its log files, the dispatcher in `__main__.py`,
  client configuration for Claude Code and Claude Desktop, and the reasons for JSON-only responses, strict sessions,
  `SO_EXCLUSIVEADDRUSE` and the second executable.
- `docs/user/ru/mcp.md` (source), `docs/user/uk/mcp.md`, `docs/user/en/mcp.md` with identical H1 and H2 sequences: what
  the server is, that it is off by default and listens only on this computer, the three modes and that only the user
  can change them, what never happens (apply, audit, delete, import, passwords, keys), that an answer file written
  through MCP skipped the PowerShell syntax check, how to start it and read the monitor, the token and its rotation and
  where it lives, connecting Claude Code (stdio and HTTP with the exact `claude mcp add` commands, the URL with
  `127.0.0.1` and why not `localhost`, `MAX_MCP_OUTPUT_TOKENS` for large answers) and Claude Desktop (stdio; the
  configuration file location named here), the second executable and which flags need a console, the log files
  `logs\winkickoff.log` (window) and `logs\mcp-stdio-<pid>.log` (client-started servers), that imported ADMX texts are
  unreviewed and follow the program language, troubleshooting (port in use, token changed, `404` after a program
  restart means the client reconnects, no answer while a build or a dialog is open, a change reported as timed out may
  still have landed, `pythonw` cannot serve stdio, `localhost` in the URL). A row in the documents table of
  `docs/user/<lang>/README.md` and in `docs/README.md` if it lists user files.
- `docs/releases/v1.2.0-rc.1.md` with `## Русский`, `## Українська`, `## English` (pattern `v1.1.0-rc.4.md`); the
  release notes mention the second executable and the possibility of antivirus false positives on two executables.
- `WinKickOff/tools/WinKickOff.spec`.

Updated files:

- `AGENTS.md`: header date; section 1 (the toolkit sentence gains the MCP server); section 3 tree (`winkickoff/mcp/`,
  `mcp_main.py`, the dispatcher `__main__.py`, `core/startup.py`, `ui/mcp_window.py`, `ui/mcp_workspace.py`,
  `tools/WinKickOff.spec`, `tests/test_mcp_*.py`, `todo/` "T01-T22"); section 5 commands (`python -m winkickoff --mcp
  stdio`, `--mcp http --port 0 --token ...`, `--mcp-config`, the `WINKICKOFF_HTTP_TESTS` gate); section 6 facts
  (loopback and token only; modes forgotten at every start; no apply, audit, delete, import or settings through MCP;
  redaction mandatory and tested; stdio needs `python.exe` or `WinKickOff-mcp.exe`, never `pythonw`; `http.server` and
  `from socket import` allowed in one file only; the journal is memory only; headless processes log to
  `logs/mcp-*-<pid>.log`; the window's settings object is the only writer of `settings.json`; every dialog in `ui/` sits
  inside `with self.modal():`; never start a server on the customer's PC outside `unittest`); section 7 rows (Editor
  tasks, Editor code 1.2.0-rc.1, Release candidate, a new row "MCP server"). Every backticked path must exist
  (`test_docs.py`).
- `WinKickOff/winkickoff/__init__.py` `APP_VERSION = "1.2.0-rc.1"`, `pyproject.toml` `version = "1.2.0rc1"`.
- `WinKickOff/README.md`: state line, the commands, "Where things are stored" (the three settings fields, the second
  executable, the headless log files), the sentence "never goes online" reworded to "writes nothing outside its folder
  and never connects to the internet; the optional MCP server accepts connections only from this computer, on 127.0.0.1,
  when the user starts it, and is read-only by default", the project rule "no network access" gaining the loopback
  exception.
- Root `README.md`: state line, Tools table row for the MCP server, the Safety bullet with the same wording.
- `docs/technical/editor/01-problem-statement.md` (section 4 row "Offline operation" and section 5 constraints: the
  loopback listener as the explicit exception), `02-architecture.md` (the `mcp/` package, the dispatcher, the bridge, a
  section pointing to `07-mcp-server.md`), `03-data-model.md` (settings fields; the JSON shapes of `get_profile`,
  `get_rule` and `check_profile`; the file name rule of section 3.7), `04-testing.md` (the MCP test level, the rule
  "loopback port 0 only, no PowerShell, no server outside unittest on the customer's PC", the environment gate, the
  `-X importtime` subprocess tests).
- `docs/user/<lang>/safety.md`: the "does not go online" paragraph (ru line 36 and the uk and en equivalents) gains one
  sentence about the loopback MCP server that the user starts deliberately.
- `resources/strings.ru.json` and `strings.uk.json`: every new `tr()` string.
- `tests/test_sources.py`: the documented exceptions (section 9) with their comments.
- `.github/workflows/build.yml`: the two-executable check and the smoke step after the zip (section 6).
- `.gitignore`: nothing new (`settings.json`, `**/logs/`, `**/output/`, `build/`, `dist/` are already ignored; the spec
  workpath is checked).

## 11. Risks and open questions

Risks:

1. The written contract "never goes online" appears in four places; an HTTP listener is a policy change. Mitigated by
   the wording ("accepts connections only from this computer"), the code constant, the source test and the off-by-default
   state; the customer confirms the wording (question 1).
2. Prompt injection through catalog texts, ADMX explain texts, profile names and comments: the agent reads them as data.
   Mitigated by `clean_text`, length caps, the `origin.unreviewed_text` marker, the `_text` key convention and the
   `instructions` text; not eliminated, because the AI client decides what to believe. Write modes therefore stay off by
   default and every write is visible in the window as an unsaved change.
3. Secrets in tool results: mitigated by mandatory redaction with a structural check and a negative test; the residual
   risk is a new field added later without redaction, which `test_no_secret_leaves_any_tool` catches as long as the
   fixture profile is kept.
4. The main-thread bridge under a modal dialog: reads are served, writes are refused with `window_busy` through the
   modal counter; the message names the cause. If Tk timers turn out not to tick under a native dialog on some Windows
   build, reads time out with `window_timeout` instead (checked in the VM acceptance).
5. `allow_reuse_address = False` and `SO_EXCLUSIVEADDRUSE` are correct, but a crashed previous instance can leave the
   port in `TIME_WAIT` for up to two minutes; the error message tells the user to wait or pick another port.
6. The 2026-07-28 revision: a modern-only client would not connect; today's Claude Code and Claude Desktop are dual-era.
   Adding `server/discover` later is possible on the same core.
7. Two executables in one folder double the surface for antivirus false positives on the customer's machines; the release
   notes mention it. The spec file replaces a working command-line build; the first CI run may fail on data paths, and
   the existing presets check of `build.ps1` catches missing data.
8. Strict sessions: after a program restart a connected Claude Code gets `404` and must re-initialize; the SDK does this
   on its own, a hand-written client must be told (documented once, in `mcp.md`).
9. JSON-only responses and GET `405`: a client that insists on SSE (the deprecated `--transport sse` of Claude Code)
   will not work; the documentation names `--transport http`.
10. `load_profile` with `force: true` drops unsaved changes without a dialog; the journal shows it and the mode is one
    the user chose. The customer may prefer a dialog (question 5).
11. Cross-thread bugs are the classic tkinter failure; the design allows exactly one crossing point (the bridge), the
    window test with a restart in the middle covers it, `destroy()` cancels the pump before the interpreter goes, and
    `test_mcp_package_has_no_tkinter` keeps `tk` out of `mcp/`.
12. Issue messages from `validate_profile` come out through `tr()` in the process language regardless of a requested
    `language`, and imported ADMX texts do the same; every result says which language its texts are in
    (`issues_language`, `text_language`).
13. A write that started on the main thread just as the client gave up lands after the client saw `window_timeout`;
    the window shows it as an unsaved change, the journal row says "completed after timeout", and the documentation
    tells the agent's user to check with `get_profile`.
14. The modal counter wraps 36 dialog calls in `main_window.py`; a missed one would let a write land under a dialog.
    The source test of section 9 enforces the wrapper for every future dialog in `ui/`.
15. The `-X importtime` subprocess tests depend on the trace format of CPython; it has been stable since 3.7 and the
    test only greps for `tkinter`.

Open questions for the customer:

1. Is the reworded safety sentence acceptable ("connections only from this computer, only when the user starts the
   server, read-only by default")?
2. Persisting the token in `settings.json` (section 3.4) versus a per-start token that must be copied at every start: the
   design chooses persistence, written only by the window; confirm.
3. Should `files` mode exist in 1.2 at all, or is `edit` plus manual saving enough for the first release? The design keeps
   it because "no file management by default" implies an opt-in.
4. Autostart (read only): keep or drop? The design keeps it, off by default.
5. `load_profile` with `force`: keep the explicit flag (logged) or replace it with a dialog in the window that blocks the
   request until answered?
6. Running `tests/test_mcp_http.py` on the customer's PC binds `127.0.0.1:0`; loopback binds should not trigger the
   Windows Firewall dialog. CI runs the suite first; after the customer's confirmation the `WINKICKOFF_HTTP_TESTS` gate
   is removed, otherwise the HTTP tests stay CI-only.
7. Answer file name in `output/`: `<name>.xml` renamed by the user, or a folder `output/<name>/autounattend.xml`?
8. Should imported ADMX rules be visible through MCP in `read` mode at all, given they are unreviewed text? The design
   shows them with the marker.
9. A stdio-to-window attach mode for Claude Desktop (a stdio process forwarding every line to the window's HTTP server
   on loopback) would give Claude Desktop the live window, but it needs an outgoing `http.client` import that
   `test_sources.py` forbids and a second documented exception. Proposed for 1.3, not part of this task.
10. A second listener on `[::1]` so that `localhost` URLs work with Node clients: 1.3 candidate, or is the `127.0.0.1`
    rule in the documentation enough?

## 12. Implementation order

Each step ends with `python -m unittest discover -s tests -v` green, a commit in Russian and a push (AGENTS.md rules).
Nothing is started on the customer's PC outside `unittest`. Estimates are focused working hours for one implementer.

1. Settings, version, startup, dispatcher (3 h): three fields in `core/settings.py` with tests; `APP_VERSION =
   "1.2.0-rc.1"` and `pyproject.toml`; a stub `docs/releases/v1.2.0-rc.1.md` so `test_docs.py` passes; `core/startup.py`
   with `initial_profile` moved out of `app.py`; `render.write_answer_file` moved out of `MainWindow.write_build`;
   `core/log.py` with the `filename` and `delay` arguments; the `__main__.py` dispatcher with a temporary `parse_args`
   stub and `app.run(args, extras)`.
2. JSON-RPC, schema, redaction (4 h): `mcp/__init__.py`, `jsonrpc.py`, `schema.py` (union types, nested items),
   `redact.py` (`check_name`, `assert_redacted_build`), `journal.py`; the parsing, schema and redaction parts of
   `test_mcp_protocol.py` and `test_mcp_tools.py` (the secrets test and the name tests first).
3. Workspace and bridge (5 h): `workspace.py` with `HeadlessWorkspace` on `core/` only and the two-folder profile
   listing, `bridge.py` with `Item`, deadlines and `InlineBridge`; tests against the Office preset with `data != root`.
4. Tools and resources (8 h): `tools.py` with the 18 handlers, `resources.py`, the full registry with schemas,
   annotations and descriptions, the mode gate, `text_language`; `test_mcp_tools.py` and `test_mcp_resources.py`
   including the forbidden-function, no-path and no-secret tests.
5. Protocol, stdio, CLI (5 h): `protocol.py`, `stdio.py` (over-long line drain), `cli.py` (`parse_known_args`, `emit`,
   log housekeeping), `mcp_main.py`, the final `__main__.py`, `test_mcp_protocol.py` (lifecycle), `test_mcp_stdio.py`
   with the `-X importtime` subprocesses, `test_mcp_cli.py`, the `test_portable.py` extension.
6. HTTP transport (6 h): `httpserver.py` (`SO_EXCLUSIVEADDRUSE`, `serving` event, body drain), `service.py`
   (`configure`, start, guarded stop, token through the callback, snippets), `test_mcp_http.py` including the
   never-started-thread stop, the exclusive bind, the 2 MB body, the stop-with-open-socket and bind-conflict
   regressions, the `test_sources.py` rules and the environment gate.
7. Window integration (9 h): the `modal()` counter around all 36 dialog calls and its source test, `is_busy`,
   dialog-free methods in `main_window.py`, `ui/mcp_workspace.py`, `Bridge.pump` through `after` with the id cancelled
   in `destroy`, `attach`/`detach` in `__init__`/`destroy`, service ownership in `app.run()` and
   `create_app(service=...)` with `configure`, autostart, the MCP menu, the status segment, `test_mcp_window.py`
   including the token-survives-rebuild and destroy-without-TclError tests.
8. Monitor window (5 h): `ui/mcp_window.py`, copy actions, filters, the "completed after timeout" note, the monitor part
   of the window test, all `tr()` strings with `ru` and `uk` translations.
9. Build (3 h, CI only): `tools/WinKickOff.spec` with two executables, `tools/build.ps1`, the `build.yml` artifact check
   and the stdio smoke step after the zip with the clean-folder assertion, a CI run with the zip inspected.
10. Documentation (6 h): this file's status line, `07-mcp-server.md`, updates of `01`, `02`, `03`, `04`, the editor
    README, `WinKickOff/README.md`, root `README.md`, `docs/user/{ru,uk,en}/mcp.md`, `safety.md` and `README.md` in
    three languages, the release notes, `AGENTS.md`.
11. Acceptance (3 h, not on the customer's PC beyond the tests): in a VM or on a developer machine, `claude mcp add
    winkickoff -- python -m winkickoff --mcp stdio`, then the HTTP mode from the window with Claude Code, then Claude
    Desktop with the CI-built `WinKickOff-mcp.exe`; confirm the firewall behaviour; open "Save changes?" in the window
    and confirm that a read call is answered while the box is open and a write gets `window_busy` (if reads time out
    instead, record it and update `mcp.md` as section 3.5 says); leave a Claude Code session idle for an hour and
    confirm the next call succeeds; the checklist goes into this file; tag `v1.2.0-rc.1` after the customer's answers
    to the open questions.

Total about 57 hours, nine to ten working days. Steps 1 to 6 need no display and can be reviewed by reading the tests
alone; step 7 is the only one where the window and the server meet, and it is the step to review most carefully.
