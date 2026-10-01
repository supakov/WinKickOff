# pi agent container

A Podman image that runs the [pi coding agent](https://github.com/earendil-works/pi) with a local model, with the
WinKickOff repository mounted at `/projects`. The agent works on the code and the documentation and talks to the
WinKickOff MCP server, and nothing is sent to a cloud model: the model runs on a llama.cpp server of the same machine.

State on 01.10.2026: the image was added by a team member; the connection to the MCP server of the WinKickOff window
works. The CI job `pi-agent-container` builds the image on every push and runs `check_container.py` in it: the tests,
the dash check and pi's connection to headless WinKickOff servers over stdio and HTTP pass. The steps of the acceptance
test (section 8) that need the window and the model have not been done yet.

## 1. Contents of this folder

| File | Purpose |
|---|---|
| `Dockerfile` | The image: Ubuntu 26.04, Python 3.14, Node.js 22, git, ripgrep, pi from npm |
| `AGENTS.md` | Instructions for the agent in the container; pi loads them after step 3 of section 4 |
| `README.md` | This file: build, setup, connection to WinKickOff, tests, security, known issues |
| `check_container.py` | Checks of the image (section 6): the tools, the tests and the dash check as the agent runs them, WinKickOff's headless commands, pi's MCP connection over stdio and HTTP. CI runs it; a person can run it in the container |

The repository map for every agent is the root [`AGENTS.md`](../AGENTS.md); pi loads it by itself, because it reads
the `AGENTS.md` of every folder from `/` down to its working folder.

## 2. How the pieces fit

```
Host (127.0.0.1)
  llama.cpp server :8088 (OpenAI-compatible API, the model)
  WinKickOff window, MCP server :47831 (menu MCP, HTTP, bearer token)
Container winkickoff-pi (--network=host, so 127.0.0.1 is the host's loopback)
  pi                     -> model at http://localhost:8088/v1
                         -> MCP at http://127.0.0.1:47831/mcp (or a stdio server started inside)
  /projects              the repository (bind mount, read-write)
  /home/pi/.pi           volume pi-winkickoff: settings, model list, MCP entry with the token, sessions
```

## 3. Requirements

- Rootless Podman. The commands below come from the `Dockerfile` and were written for a Linux host: `Z` relabels the
  mount for SELinux, `U` gives the mounted files to the container user, and `--userns=keep-id` makes that user the
  host user, so nothing changes owner on the host. On Windows Podman runs the container inside a WSL2 virtual
  machine; see section 5.3 before using it there. These commands have not been tried on Windows.
- A local OpenAI-compatible model server, for example llama.cpp `llama-server` on port 8088. Its context size (`-c`)
  must not be smaller than `contextWindow` in `models.json`.
- WinKickOff 1.2.0-rc.1 or later: the MCP server of the window (menu "MCP"), or the stdio server inside the container.
- pi 0.99.0 or later. MCP is built into pi since 0.99.0 (29.09.2026), so no extension is needed. The image installs
  the tested pi 0.99.2; another version: `podman build --build-arg PI_VERSION=x.y.z ...`, then run section 6.

An agent never builds or runs this image on the customer's work PC: building pulls images and packages and changes the
machine. A person does it on their own machine or in a virtual machine (root `AGENTS.md`, rule 1).

## 4. Build, run and first-time setup

From the repository root:

```bash
podman build -t winkickoff-pi:local ./pi-agent/
podman run -it --rm --name winkickoff-pi -v .:/projects:rw,Z,U -v pi-winkickoff:/home/pi/.pi --network=host --userns=keep-id winkickoff-pi:local
```

The image sets `PI_TELEMETRY=0`, so even the first start with a new volume sends no install ping to `pi.dev`.

The container starts `pi` in `/projects`. A second shell in the running container: `podman exec -it winkickoff-pi sh`.
The volume `pi-winkickoff` keeps everything under `/home/pi/.pi` between runs, so the setup below is done once. Run
these commands in that second shell (or inside pi, prefixed with `!!`, as the comments of the `Dockerfile` show).

1. Settings: no install ping, and the local model as the default.

   ```bash
   cat > ~/.pi/agent/settings.json <<'EOF'
   {
     "enableInstallTelemetry": false,
     "defaultProvider": "llama-cpp",
     "defaultModel": "Qwen3.6-35B"
   }
   EOF
   ```

2. The model. A server without a key still needs some `apiKey` value, otherwise pi hides its models.

   ```bash
   cat > ~/.pi/agent/models.json <<'EOF'
   {
     "providers": {
       "llama-cpp": {
         "baseUrl": "http://localhost:8088/v1",
         "api": "openai-completions",
         "apiKey": "none",
         "models": [
           { "id": "Qwen3.6-35B", "name": "Qwen3.6-35B", "contextWindow": 262144, "maxTokens": 196608 }
         ]
       }
     }
   }
   EOF
   ```

3. The instructions of this folder. pi reads `~/.pi/agent/AGENTS.md` first and then the `AGENTS.md` of every folder
   down to its working folder (`/projects/AGENTS.md`, the repository map). The link keeps the file current after every
   `git pull`; nothing is copied into the volume.

   ```bash
   ln -sf /projects/pi-agent/AGENTS.md ~/.pi/agent/AGENTS.md
   ```

4. The MCP server entry: section 5.1 (HTTP, the open window) or 5.2 (stdio inside the container), or both.

5. Restart pi (or type `/reload`) and check from the second shell:

   ```bash
   pi --version
   pi mcp list
   ```

   `pi mcp list` connects to every configured server and prints its state, its tools and any error; it exits with 1
   when a server fails, so it is the quickest connection test. `python3 /projects/pi-agent/check_container.py --quick`
   checks the image and pi's MCP client against headless servers of its own, without touching the volume.

## 5. Connecting to WinKickOff

### 5.1 HTTP: the open window

In the WinKickOff window: menu "MCP", "Server running", then "Copy client configuration (HTTP)". The copied entry is in
the format pi reads. Put it into `~/.pi/agent/mcp.json`, and add `exposure` and `description`:

```json
{
  "mcpServers": {
    "winkickoff": {
      "type": "http",
      "url": "http://127.0.0.1:47831/mcp",
      "headers": { "Authorization": "Bearer <token copied from the window>" },
      "exposure": "direct",
      "description": "WinKickOff editor: the rule catalog and the profile open in the window"
    }
  }
}
```

- Keep `127.0.0.1` in the URL. Node resolves `localhost` to the IPv6 address first, and the server listens on IPv4
  only. The server also refuses with `421` any request whose `Host` is not `127.0.0.1` or `localhost`, so a URL with
  `host.containers.internal` or an IP address of the host never works; the server listens on the loopback only anyway.
- `exposure`: pi's default `codemode` hides the tools behind one `codemode` tool, and the model has to write
  JavaScript to call them. `direct` declares the 18 WinKickOff tools as ordinary tools named `mcp__winkickoff__<tool>`,
  which is easier for a local model. Switching is possible at any time in `/mcp`, "Exposure". Which works better with
  the local model is part of the acceptance test.
- The token is stored in this file in clear text, inside the volume. pi can read it from an environment variable
  instead: `"Authorization": "Bearer ${WINKICKOFF_MCP_TOKEN}"` with `-e WINKICKOFF_MCP_TOKEN=...` on `podman run`;
  either way every command the model runs can see it. After "New access token" in the window every client with the
  old token gets `401` ("MCP server requires authentication"): put in the new token and run
  `/mcp reconnect winkickoff`.
- If the container has `HTTP_PROXY` or `HTTPS_PROXY`, pi sends MCP traffic through the proxy as well; set
  `NO_PROXY=127.0.0.1,localhost`.

### 5.2 stdio inside the container

The container has Python 3.14, so pi can start a headless WinKickOff server itself. It needs no network and no token,
but it works on its own copy of a profile, not on the open window (see the user page `docs/user/en/mcp.md`). This suits
work on the rule catalog: after a change of `WinKickOff/rules/` the agent sees the new catalog once the person types
`/mcp reconnect winkickoff-local`.

```json
{
  "mcpServers": {
    "winkickoff-local": {
      "command": "python3",
      "args": ["-m", "winkickoff", "--mcp", "stdio", "--mode", "read", "--profile", "office"],
      "cwd": "/projects/WinKickOff",
      "env": { "PYTHONPATH": "/projects/WinKickOff" },
      "exposure": "direct"
    }
  }
}
```

Each server process writes `WinKickOff/logs/mcp-stdio-<pid>.log` in the mounted folder (not versioned). The mode is
fixed by `--mode` in this entry, and the person who edits the entry chooses it; `--mode files` lets the agent create
files in `WinKickOff/profiles/` and `WinKickOff/output/`.

### 5.3 Networking

`--network=host` gives the container the network of the machine that runs it, so `127.0.0.1` in the container is the
loopback of that machine.

- Linux host: the WinKickOff server and llama.cpp run on the same machine, for example the headless
  `python3 -m winkickoff --mcp http --port 47831 --token <token>` from a clone (the window is made for Windows); the
  URLs above work as they are.
- Windows host with `podman machine`: the container runs inside a WSL2 virtual machine, and its loopback is the loopback
  of that virtual machine. The window's server on the Windows loopback is reachable from there only with WSL mirrored
  networking (`networkingMode=mirrored` in `%UserProfile%\.wslconfig`, Windows 11 22H2 or later); without it the
  container cannot reach the window, and the stdio server of section 5.2 is the way. Changing `.wslconfig` changes the
  system and is never done by an agent on the customer's PC.

### 5.4 What pi does with the WinKickOff tools

Read in the pi sources (0.99.2) and our server code. The CI job confirms the handshake, the sessions and the full
tool list over stdio and HTTP; the rest is part of the acceptance test.

| Topic | Behaviour |
|---|---|
| Handshake | pi asks for protocol 2025-11-25 and accepts the 2025-06-18 our server answers; client name `pi` and its version appear in the monitor |
| Session | pi keeps the `Mcp-Session-Id`, opens no event stream after the `405` to GET, sends `DELETE` when it closes, and re-initializes once after a `404` |
| Modes | The tool list is the same in every mode; a refused call is a tool error `mode_required`. Only the person switches the mode, in the window |
| Results | With `direct` the model gets the text of the result; WinKickOff puts the same JSON there as in `structuredContent`. A tool error (`isError`) reaches the model as an error |
| Large results | pi shows at most 20 KB of a tool result to the model; it keeps the start and the end, cuts the middle and saves the full text in `/tmp/pi-mcp-<hex>.txt`. Narrow queries (`group`, `query`, `limit`) avoid it |
| Resources | pi lists and reads the `winkickoff://` resources through its own tools `list_mcp_resources`, `list_mcp_resource_templates` and `read_mcp_resource` |
| Parallel calls | pi runs the tool calls of one model message in parallel, and our server serves at most 4 requests at once and answers `503` to the next; pi does not retry a tool call. One WinKickOff call at a time is safest |
| Timeout | 60 s per request by default (`"timeout"` in the entry); WinKickOff answers writes within 30 s |
| Commands | `/mcp` lists servers, tools, errors and exposure; `/mcp reconnect <server>`; `/reload` after editing `mcp.json`; `pi mcp list` outside a session |

## 6. Working on the repository in the container

- `/projects` is the repository of the host, read-write: every change lands on the host disk at once.
- Python 3.14 comes from Ubuntu 26.04, the version the project requires. There is no tkinter, no PowerShell and no
  Windows in the image: the tests of the window are skipped, and the PowerShell checks are not available.
- Tests: `cd /projects/WinKickOff && python3 -m unittest discover -s tests` must end with `OK`. In CI on 01.10.2026:
  651 tests, 96 skipped: the window tests (no tkinter, no display), the PowerShell checks and a few tests of Windows
  behaviour.
  `test_docs` also fails on dashes and on text files with LF line endings. Some tests start their own MCP servers on
  `127.0.0.1` port 0 and a headless child process that writes a log into `WinKickOff/logs/`. On a mount backed by a
  Windows disk `test_docs` and the child process tests are slow.
- `python3 /projects/pi-agent/check_container.py` runs everything the CI job runs: the tools of the image, the tests,
  the dash check, WinKickOff's headless commands and `pi mcp list` against a stdio server and an HTTP server it starts
  on a free port with a random token. pi gets a temporary agent folder, so the volume and its token stay untouched;
  no model is needed. `--quick` leaves out the tests.
- WinKickOff itself: only `python3 -m winkickoff` with `--mcp`, `--mcp-config` or `--version` works here; without them
  it starts the window, which needs tkinter. `--profile` takes a preset id, the name of a saved profile or an absolute
  Linux path. The last profile of a Windows window is a Windows path, so a headless server here falls back to the
  Office preset.
- Line endings: every file of the repository is stored with CRLF (`.gitattributes`: `* -text`). pi's `edit` tool keeps
  the line endings of an existing file; its `write` tool writes what the model gives, normally LF. `AGENTS.md` of this
  folder gives the command that converts a new file to CRLF.
- Git uses the identity of the clone's `.git/config`, so a commit made in the container carries the name of the person
  who owns the clone. The container has no credentials for GitHub: pushing is done on the host.

## 7. Security

pi asks no confirmation before it runs a command or changes a file. The container is the boundary, so it matters what
the container can reach.

| What the container reaches | Risk | What to do |
|---|---|---|
| `/projects`, read-write, including `.git/` | A file in `.git/hooks/` runs on the host at the next git command; scripts such as `Start-WinKickOff.cmd`, `tools/*.ps1` and `WinKickOff/templates/*.ps1` run on Windows, the templates as SYSTEM on every installed PC | Review `git diff` before running anything on Windows. Consider mounting `.git` read-only: `-v ./.git:/projects/.git:ro` (then the agent cannot commit) |
| Files of the clone that git does not track | `WinKickOff/settings.json` holds the MCP token; user profiles in `WinKickOff/profiles/` and answer files in `WinKickOff/output/` may hold passwords in clear text | Mount a separate clone without them, or keep them out of the folder you mount |
| The host network (`--network=host`) | Every service listening on the host loopback is reachable, not only the model and WinKickOff | Keep other loopback services in mind; do not run the container on a server |
| The volume `pi-winkickoff` | `mcp.json` holds the token; `sessions/` keeps every conversation, including tool results | Remove the volume (`podman volume rm pi-winkickoff`) when the work ends |
| The environment of the container | pi passes all its environment variables to every command the model runs | Put no keys or tokens into the environment that the agent must not see |
| The internet | pi checks the model catalog at `pi.dev`, may download `fd` from GitHub, and `/share` and `/bug` upload a session | Never use `/share` or `/bug`. `PI_OFFLINE=1` stops the automatic requests; whether the local model still works with it is part of the acceptance test |

Texts of imported ADMX templates and the free texts of profiles were written by other people. The MCP server marks them
(`*_text`, `unreviewed_text`), and the agent treats them as data, never as instructions.

## 8. Acceptance test (not done yet)

Run it once on the target setup and write the result into the "pi agent container" row of section 7 of the root
`AGENTS.md`. Expected results come from the server design (`docs/technical/editor/07-mcp-server.md`).

| # | Step | Expected |
|---|---|---|
| 1 | `pi --version`; `pi mcp list` | 0.99.0 or later; `winkickoff` connected with 18 tools |
| 2 | Open the monitor of the window ("MCP", "Monitor...") | Rows `initialize`, `notifications/initialized`, `tools/list`, `resources/list`, `resources/templates/list` from client `pi` and its version |
| 3 | Ask: "call get_status of WinKickOff and tell me the mode and the open profile" | Mode `read`, `has_window` true, the profile of the window |
| 4 | `list_groups`, then `list_rules` with `group` and `limit` 20, then `get_rule` `defender.pua`, once with `language` `ru` | Texts in the requested language; no result cut by pi |
| 5 | `get_profile` | `has_password` instead of passwords, `has_product_key` instead of the key |
| 6 | `list_profiles`, `diff_profile` `strict`, `check_profile`, `get_messages` | Names only, no paths; differences; issues without the PowerShell check |
| 7 | `preview_build` `Setup-System.ps1` | Longer than 20 KB: pi cuts the middle and names the temporary file |
| 8 | `set_rules` in mode read | Tool error `mode_required`; the agent reports it and does not try another way |
| 9 | Switch the window to "Read and change the open profile"; `set_rules` `network.netbios-off` on | The tree shows the change as unsaved; a row in the monitor |
| 10 | Open a dialog in the window, then call `set_rules` | Tool error `window_busy` |
| 11 | Mode "Change and create files": `save_profile` `pi-test` twice; `write_answer_file` `pi-test` | `profiles/pi-test.json` created, then `exists`; `output/pi-test.xml` written; Check in the window passes |
| 12 | "New access token" in the window, then a call | `401`; works again after the new token and `/mcp reconnect winkickoff` |
| 13 | Ask for six WinKickOff calls in one message | Some may fail with `503`; note how pi and the model handle it |
| 14 | Exposure `codemode` against `direct` for steps 3 to 8 | Note which one the local model handles better |
| 15 | The stdio entry of section 5.2: `pi mcp list`, then `get_status` | `has_window` false, transport `stdio`; a log file in `WinKickOff/logs/` (the connection itself is checked by CI) |
| 16 | `python3 /projects/pi-agent/check_container.py` on the target machine | `All checks passed.` (CI passes it in a fresh image) |
| 17 | The agent edits an existing file and creates a new one; check line endings and dashes with the commands of `AGENTS.md` | The edited file stays CRLF; the new one is converted |
| 18 | `PI_OFFLINE=1` (add `-e PI_OFFLINE=1` to `podman run`) | The local model and the MCP server still work |

## 9. Notes on the image

Findings of the review of 01.10.2026. The first five were applied the same day and pass in CI; the others are
suggestions.

| Finding | Effect | State |
|---|---|---|
| `npm install -g @earendil-works/pi-coding-agent` had no version | Every rebuild could bring another pi; before 0.99.0 there is no MCP | Applied: `ARG PI_VERSION=0.99.2` |
| No `--ignore-scripts` | pi's own documentation installs with it, so no package script runs as root during the build | Applied |
| No `fd-find` | pi downloaded `fd` from GitHub into the volume when it needed it | Applied (pi accepts `fdfind`) |
| Telemetry was switched off by a manual step | The first start of a new volume could send the install ping before `settings.json` existed | Applied: `ENV PI_TELEMETRY=0`; `ENV PI_OFFLINE=1` may follow after step 18 of section 8 |
| `FROM ubuntu:26.04` was a short name | Podman may refuse a short name or ask which registry to use | Applied: `FROM docker.io/library/ubuntu:26.04` |
| Node.js comes from the NodeSource script piped into `bash` as root | The build trusts a remote script; pi needs Node.js 22.19 or later (CI: 22.23) | Suggestion: keep it, or use a Node.js image as pi's documentation does |
| `/projects/specification` and `/projects/sources` | Hidden by the bind mount of the repository; WinKickOff does not use them | Remove the two folders from the `mkdir` |
| `chmod -R 777 /projects /home/pi` | Wider than needed | With `--userns=keep-id` the volume needs only to be writable by the user |
| No `python3-tk`, no PowerShell | Window tests skipped, no PowerShell syntax check | Intended: the window and PowerShell are checked on Windows |

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "MCP servers need attention" at the start of pi | A configured server failed to connect | `/mcp` shows the server, its source file and the full error |
| `pi mcp list`: connection refused | The server of the window is stopped, the port differs, or the container cannot reach the host loopback | Start the server; compare the port with the monitor; on Windows see section 5.3 |
| `421` | The URL names a host other than `127.0.0.1` or `localhost` | Use `http://127.0.0.1:<port>/mcp` |
| `401` | The token is wrong or was replaced | Copy the configuration again from the window |
| `503` on a tool call | More than 4 calls at once | Ask the agent for one WinKickOff call at a time |
| No tools of the server in the model's list | Exposure `codemode` or `deferred`, or the server failed | `/mcp`: look at the state and the exposure |
| `/model` shows no model | No `apiKey`, or `models.json` is not valid JSON | Add `"apiKey": "none"`; check the file |
| The model stops with a context error | `contextWindow` is larger than the `-c` of llama-server | Make them equal |
| `fatal: detected dubious ownership` | The files belong to another user than the container user | Run with `--userns=keep-id`, or `git config --global --add safe.directory /projects` in the container |
| A changed file shows every line as changed in `git diff` | It was written with LF | Convert it to CRLF with the command in `AGENTS.md` |
