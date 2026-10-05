# WinKickOff MCP server: resources, limits and transports

Part of [tools.md](tools.md). Read it for documents served as resources, the limits, the differences between a server with a window and one without, and errors that come from the protocol rather than from a tool.

## Resources

Readable in every mode. Prefer tools; some clients cannot read resources by themselves. pi reads them with
`list_mcp_resources`, `list_mcp_resource_templates` and `read_mcp_resource`; with its default exposure `codemode` from a
script, as `await tools.read_mcp_resource({"server": "winkickoff", "uri": "..."})`.

| URI | Content |
|---|---|
| `winkickoff://status` | Same as `get_status` |
| `winkickoff://profile` | Same as `get_profile` |
| `winkickoff://messages` | Same as `get_messages` |
| `winkickoff://catalog/groups` | Whole group tree, program language |
| `winkickoff://catalog/rules` | All built-in rules `{id, title, enabled, level}` (about 33 KB) and `imports` |
| `winkickoff://catalog/rules/{id}` | One rule as `get_rule`, always in the program language |
| `winkickoff://docs/reference/{file}` | English reference card, `00-architecture.md` to `20-explorer-namespaces.md` and `README.md` |
| `winkickoff://docs/user/{lang}/{file}` | User page; `lang` `en`, `ru`, `uk`; files `README.md`, `quick-start.md`, `profiles.md`, `install-and-check.md`, `safety.md`, `rules.md`, `admx.md`, `mcp.md`, `this-pc.md` |

- A rule's `doc` maps to a card by file name: `docs/technical/reference/07-defender.md#...` is
  `winkickoff://docs/reference/07-defender.md`.
- Documents are cut at 64 KB without a marker. `rules.md` is longer; use `list_rules` instead.
- Not readable: settings, logs, raw profiles, built files, imported templates. They give "resource not found" (-32002).

## Limits

| Limit | Value |
|---|---|
| Result size | 200,000 bytes (`result_too_large`) |
| `list_rules` | `limit` 1-500, default 100 |
| `set_rules` | 1-200 items |
| `set_param` | string up to 4000 characters; array up to 200 items, joined up to 4000 |
| `set_profile_info` | `name` 1-80, `author` 0-80, `comment` 0-2000 |
| File names | 80 characters |
| Window timeouts | reads 5 s, writes 30 s, plus 5 s grace |
| Concurrency | tool calls run one at a time; HTTP answers 503 above 4 requests at once (also to calls a script starts together) |
| Client side | Claude Code warns at 10,000 tokens and stores results over about 25,000 tokens in a file; pi shows about 20 KB of a direct result and cuts the middle; a pi `codemode` script gets the whole result, and what it returns is cut above about 10,000 tokens |

## Window and stdio

| | Window (HTTP, `has_window` true) | No window (stdio, or headless `--mcp http`) |
|---|---|---|
| `has_window` | true | false |
| Profile | The profile open in the window, shared with the person | Its own copy: `--profile`, else the window's last profile, else Office |
| Mode | "MCP" menu or the "Monitor..." window; takes effect at the next call | `--mode` in the client configuration, fixed for the process |
| Saving | The person: "Save profile" (Ctrl+S), "Save profile as..."; or `save_profile` | Only `save_profile` (mode `files`); unsaved edits are lost when the process ends |
| `show_item` | Selects the node | `{shown: false, reason: "no window"}` |
| Busy, timeouts | Yes | Never |
| Clients | Claude Code, pi | Claude Code, pi, Claude Desktop (always stdio) |

The window's HTTP server runs only while the window is open and "Server running (HTTP, this computer only)" is checked
in the "MCP" menu. Its address is `http://127.0.0.1:<port>/mcp` (default port 47831), with a bearer token. A headless
`--mcp http` server (a Linux host or a virtual machine) has `transport` `http` but `has_window` false and behaves
like stdio: its own profile copy, mode fixed by `--mode`. Decide by `has_window`, never by `transport`.

## Protocol and HTTP errors

These come from the client or the connection, not from a tool:

- `-32602` "Unknown tool: X": wrong tool name. `-32002` "resource not found": wrong URI.
- `-32600` "not initialized: send initialize first", or on HTTP "Mcp-Session-Id header required": the client must
  reconnect.
- HTTP `401`: the token is wrong or was renewed ("New access token" in the "MCP" menu). The person copies the client
  configuration again.
- HTTP `404` after a restart of the window: the session is gone; the client reconnects.
- HTTP `421`: the `Host` of the request is neither `127.0.0.1:<port>` nor `localhost:<port>` (for example
  `host.containers.internal`, a LAN address or another port). Use `http://127.0.0.1:<port>/mcp`.
- Connection refused with `localhost` in the URL: Node (Claude Code, pi) resolves `localhost` to `::1` first and the
  server listens on IPv4 only; use `127.0.0.1`.
- HTTP `503`: more than 4 requests at once; make one call at a time.

## Never available

No tool exists for these, in any mode: applying, auditing or reverting settings on the PC; UAC prompts; running
PowerShell (so no syntax check); deleting, replacing or renaming files; importing, updating, exporting, renaming or
deleting ADMX templates and catalog files; program settings (language, theme, permission to apply, port, token, mode,
autostart); passwords and product keys in either direction; changing accounts, languages and installation data; paths
as arguments; controlling the server.
