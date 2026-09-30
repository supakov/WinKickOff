# MCP server

The program can run as an MCP server (Model Context Protocol): through it an AI assistant (Claude Code, Claude Desktop
or another MCP client) reads the rule catalog, the open profile, check results, a preview of the answer file and the
documentation shipped with the program, and, with the user's permission, changes the open profile and creates new
files. It is an option for administrators who work with an AI assistant; building an answer file does not need it.

The server is off by default. A running server accepts connections only from this computer: it listens on the address
127.0.0.1 and is not reachable over the network. Account passwords and the product key are never passed by any tool:
the assistant only sees whether a password is set (`has_password`) and whether a key is set (`has_product_key`).

Two ways to connect:

- HTTP: the server runs inside the program window. The assistant sees the open profile, and its changes appear in the
  tree as unsaved changes, as after your own clicks. This is how Claude Code connects.
- stdio: the client itself starts a separate copy of the program without a window and talks to it through the standard
  input and output. This is how Claude Desktop connects; Claude Code can do it too.

## Modes

Three modes; each one includes the previous one.

| Mode | What the assistant may do |
|---|---|
| "Read only" | Read the catalog: groups, rules, dependencies, descriptions; the open profile without secrets; the list of presets and saved profiles; a comparison of the open profile with another one by name; the profile check and the build in memory (without the PowerShell check); a preview of the answer file and of the embedded scripts from a copy without secrets; the message list at the bottom of the window; the program's documentation. Nothing changes, not even the selection in the tree |
| "Read and change the open profile" | In addition: switch rules on and off with the same dependency cascade as in the tree; switch a group on, off or back to its defaults; change rule parameters; change the name, author and comment of the profile; open a preset or a saved profile by name (with unsaved changes the request is refused unless the assistant explicitly asked to drop them); select a node in the tree. All of it changes only the profile in memory: the window shows unsaved changes, and you save |
| "Change and create files" | In addition: save the open profile under a new name into the `profiles` folder and write an answer file under a new name into the `output` folder. Existing files are never replaced |

Only the user changes the mode: the switch in the "MCP" menu of the window (the monitor has the same three items) or the
`--mode` flag on the command line of a server without a window. The mode cannot be changed through the protocol. The
mode is not saved: every start of the program and every server without a window begins in "Read only", autostart too.
Switching to "Change and create files" asks for confirmation once per window session. A mode change applies to the
next request; the server need not be restarted and the client need not reconnect. A tool that needs a higher mode
returns the error `mode_required` to the assistant, with the hint that the mode is changed in the "MCP" menu.

## What never happens through MCP

In no mode and at no request of the assistant:

- applying rules to this computer, returning to the Windows defaults, checking on this PC (an audit);
- starting PowerShell, including the syntax check of the scripts;
- deleting, replacing or renaming files, wherever they are;
- importing, updating, renaming or deleting ADMX templates;
- changing the program settings: language, theme, the permission to apply on this PC, port, token, mode, autostart;
- reading or writing passwords and the product key; changing accounts, languages and installation data;
- reading the files of the `profiles`, `output`, `logs` and `admx` folders and `settings.json` as they are;
- paths on disk: the tools accept names only, and files are created only in the program's `profiles` and `output` folders;
- controlling the server from inside the protocol: stopping it, changing the mode, changing the token.

The server simply has no such tools, and the program's tests check it.

## How to start the server

The "MCP" menu, the check box "Server running (HTTP, this computer only)". The server takes the port from the settings,
47831 by default; another one can be set in the monitor (0 means any free port, the number is then visible after the
start), but only while the server is stopped. If another program holds the port, the server does not start and the
window says so.

While the server runs, the status bar shows on the right "MCP: 127.0.0.1:47831, Read only, 12 requests, last
14:02:11"; a double click on that text opens the monitor. The item "Start the server with the program (read only)" is
remembered in the settings; the server then starts together with the window, always in "Read only".

A change of the language, the theme or the shown templates rebuilds the window, but the server keeps running with the
same port and token: a request that arrives during the rebuild waits for the new window. Closing the program stops the
server.

## Monitor

The "MCP" menu, the item "Monitor...". At the top the state of the server ("Stopped" or "Running on
http://127.0.0.1:47831/mcp, mode: ..., clients seen: N"), the "Start" or "Stop" button, the port, the mode, the
autostart check box; below them the token masked as `abcd...wxyz` and the buttons "Copy token", "Copy client
configuration (stdio)", "Copy client configuration (HTTP)".

The table shows the request journal, newest at the bottom:

| Column | Contents |
|---|---|
| Time | Hour, minute and second of the request |
| Transport | `http` for the server of the window |
| Client | The name and version the client gave when connecting |
| Method | The protocol method: `initialize`, `tools/list`, `tools/call`, `resources/read` and others |
| Tool | The tool name or the resource address |
| Arguments | Identifiers and numbers only: `id=edge.signin-off enabled=true`, `limit=50`. Free text (names, comments, search queries, values) is shown as `<text, N chars>`, lists as `<list, N items>` |
| ms | Processing time |
| Result | `ok`, `error <code>` or a short note of the program: `mode_required` (the mode is too low), `window_busy` (the window is busy), `window_timeout` (the window did not answer in time), `exists` (the file name is taken), `unsaved_changes` (there are unsaved changes), `completed after timeout` (the change landed after the client stopped waiting) |

Rows with errors are coloured. The filter at the bottom selects rows by a substring of the method and the tool; the
"Errors only" check box and the transport list narrow the list. "Copy row" and "Copy visible rows" put rows on the
clipboard (fields separated by tabs), "Clear" empties the table.

The journal lives in memory only (the last thousand entries) and is never written to disk; request bodies, headers and
the token never appear in it. stdio servers started by a client run as separate processes and are not shown in the
monitor.

## Access token

The HTTP server answers only a client that presents the access token (the header `Authorization: Bearer <token>`). The
token is generated at the first start of the server from the window and stored in the file `settings.json` next to the
program (the field `mcp_token`); only the window writes it. Later starts use the same token, so a client is configured
once.

The item "New access token" in the "MCP" menu makes another token: a running server stops, and clients with the old
token stop working until the new configuration is pasted into them. The token is never shown in full, only copied:
"Copy token" in the monitor or "Copy client configuration (HTTP)".

Whoever reads the program folder sees the token, as they see the profiles with passwords in clear text; but the token
only works from this same computer.

## Connecting Claude Code

Over HTTP, to the running window. Start the server, copy the token and run in a terminal:

```
claude mcp add --transport http winkickoff http://127.0.0.1:47831/mcp --header "Authorization: Bearer <token>"
```

Replace the port if you changed it. The address must say `127.0.0.1`, not `localhost`: Claude Code runs on Node, which
resolves `localhost` to the address `::1` (IPv6) first, while the server listens on IPv4 only, so the connection fails.
The item "Copy client configuration (HTTP)" puts the same entry on the clipboard as JSON with the address and the
token; it can be pasted into the `.mcp.json` file of a project folder (the `winkickoff` entry inside `mcpServers`).

Over stdio, a separate copy without a window. From the portable build:

```
claude mcp add winkickoff -- "C:\Path\To\WinKickOff\WinKickOff-mcp.exe" --mode read
```

From the sources, in the `WinKickOff` folder:

```
claude mcp add winkickoff -- python -m winkickoff --mcp stdio
```

The item "Copy client configuration (stdio)" gives a ready entry with the full path (for the sources with the
`PYTHONPATH` variable, so the start folder does not matter). `--mode edit` is added to it when the window is in a change
mode at that moment; `--mode files` is never written automatically. Remember that a stdio server works on its own copy
of the profile, not on the open window (see the next section).

Check: `claude mcp list` in a terminal or `/mcp` in a Claude Code session. Claude Code limits a tool answer to about 25
thousand tokens; the server itself returns at most 200 KB at a time and, above that, asks to narrow the query (group,
search string, `limit`, `offset`). If you need larger answers, set the environment variable `MAX_MCP_OUTPUT_TOKENS`
before starting `claude`.

## Connecting Claude Desktop

Over stdio only: Claude Desktop cannot connect to an HTTP server that is reachable only on this computer. Copy the
configuration (stdio) from the "MCP" menu and paste it into the file `%APPDATA%\Claude\claude_desktop_config.json` (if
the file already has an `mcpServers` section, add the `winkickoff` entry inside it), then restart Claude Desktop.

A stdio server started by a client is a separate process without a window with its own copy of the profile: at start
it opens the last profile of the window (or the profile from `--profile`). It does not see the open window, and its
changes do not appear in the window. In the "Change and create files" mode the assistant can save its copy under a new
name into `profiles`, and then it can be opened in the window. Each such process logs into
`logs\mcp-stdio-<process id>.log`; Claude Desktop's own log for this server (`mcp-server-winkickoff.log`) stays empty,
which is normal.

## Command line

`WinKickOff-mcp.exe` (the portable build) and `python -m winkickoff` (the sources) accept the same flags.
`WinKickOff-mcp.exe` without the `--mcp` flag starts a stdio server.

| Flag | Meaning |
|---|---|
| `--mcp stdio` | A server without a window over the standard input and output; it ends when the client closes the stream |
| `--mcp http` | A server without a window on 127.0.0.1 (for tests and a virtual machine); runs until Ctrl+C; needs `--token` or a token already saved by the window; writes no settings |
| `--port N` | The port for `--mcp http`: 0 or 1024 to 65535; the settings by default |
| `--token TOKEN` | The token for `--mcp http` for this run only (32 to 64 characters: letters, digits, `_` and `-`) |
| `--mode read`, `--mode edit`, `--mode files` | The mode; `read` by default |
| `--profile NAME` | A preset (`office`, `strict`, `laptop`, `memstechtips`), the name of a saved profile in `profiles` or a full path to a file; by default the last profile of the window, else the "Office" preset |
| `--language CODE` | The language of the texts (`en`, `ru`, `uk`); the settings by default, else the Windows language |
| `--mcp-config stdio` or `--mcp-config http` | Print the client configuration (the same one the window copies) and exit |
| `--version` | Print the version and exit |

The flags `--mcp stdio`, `--mcp-config` and `--version` need a console: run them through `python.exe` or
`WinKickOff-mcp.exe`. `pythonw.exe` and `WinKickOff.exe` have no console: a stdio server does not work through them,
and `--version` and `--mcp-config` exit with code 3. Exit codes: 0 normally, 2 on a start-up error or a wrong flag, 3
without a console. Both executables of the portable build share the folders `profiles`, `output`, `logs`, `admx` and
the file `settings.json`.

## Things to keep in mind

- An answer file written through MCP has not passed the PowerShell syntax check that the "Build autounattend.xml"
  button of the window runs; the tool result says so in a separate line. Before using the file, open the profile in the
  window and press "Check" (F7), or build the file with "Build autounattend.xml" (F9). The file lies in `output` under
  the given name; rename it to `autounattend.xml` when copying it to the USB drive.
- Titles and descriptions of built-in rules reach the assistant in the requested language (`en`, `ru`, `uk`). Texts of
  imported ADMX templates were never reviewed and always come in the program language, even when another one was
  requested; the results mark them as unreviewed, and the assistant is told to treat them as data, not instructions.
  Check messages are in the program language as well.
- Everything the assistant changes is visible in the window as unsaved changes; saving stays with you. If the assistant
  opened another profile and dropped unsaved changes, the monitor shows it.
- Logs: the window writes `logs\winkickoff.log`, servers without a window write `logs\mcp-stdio-<process id>.log` and
  `logs\mcp-http-<process id>.log`; files older than seven days are removed at the next start of a server without a
  window. Request texts never reach the logs.

## If something does not work

| Symptom | Cause and what to do |
|---|---|
| The server does not start: the port is in use | Another program or a second WinKickOff holds the port; after a crash the port may stay taken for up to two minutes. Choose another port in the monitor or wait |
| The client gets 401 | The token was changed ("New access token") or pasted with a mistake. Copy the configuration again |
| The client gets 404 after a restart of the program | Client sessions live as long as the server runs. Claude Code reconnects on its own; a hand-written client has to send `initialize` again |
| No answer, the error `window_timeout` or `window_busy` | A build is running or a dialog is open (for example "Save changes?"). Close the dialog. Reads are answered even while a dialog is open; changes are refused meanwhile |
| A change was reported as `window_timeout` but may have landed | The window began the change after the client stopped waiting. Check the tree or ask the assistant to call `get_profile`; in the monitor such a row carries the note `completed after timeout` |
| A stdio server does not answer when started through `pythonw.exe` or `WinKickOff.exe` | These programs have no console. Use `python.exe` or `WinKickOff-mcp.exe` |
| `localhost` in the address, connection refused | Use `http://127.0.0.1:<port>/mcp` |
| The error `mode_required` | Switch the mode in the "MCP" menu or in the monitor; the change applies at once |
| The error `exists` when saving | A file with that name exists; files are never replaced through MCP, choose another name |
| The error `result_too_large` | The answer is larger than 200 KB: narrow the query (group, search string, `limit`, `offset`) |
| The assistant in Claude Desktop does not see changes made in the window | Claude Desktop works on a separate copy of the profile over stdio; save the profile in the window and ask the assistant to open it by name |
