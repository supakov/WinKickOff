# WinKickOff assistant in a container

A Podman image of the [pi agent](https://github.com/earendil-works/pi) with a local model. The agent helps a person
analyse and change WinKickOff profiles in Russian or Ukrainian. pi runs with its defaults: its own tools, the built-in
MCP support with codemode and its default system prompt. It reaches WinKickOff **only through the MCP server of
WinKickOff**, from codemode scripts: the container holds no WinKickOff program, profile or answer file. Nothing goes to
a cloud model: the model runs on a llama.cpp server of the same machine.

| File | Purpose |
|---|---|
| `Dockerfile` | The image: Ubuntu 26.04, Node.js 22, pi 0.99.2 with its defaults |
| `AGENTS.md` | The instructions of the assistant; the image copies them to `/work/AGENTS.md`, and pi loads them as its context file after its default system prompt |
| `README.md` | This file |

## 1. How it works

```
Host (127.0.0.1)
  llama.cpp server :8088          the model (OpenAI-compatible API)
  WinKickOff window, MCP :47831   menu "MCP", HTTP, bearer token
Container winkickoff-pi (--network=host: 127.0.0.1 is the host's loopback)
  pi in /work                     only AGENTS.md is there
    -> model at http://localhost:8088/v1
    -> MCP at http://127.0.0.1:47831/mcp, called from codemode scripts as tools.mcp__winkickoff__<tool>
  /home/pi/.pi                    volume pi-winkickoff: settings, model list, MCP entry with the token, sessions
```

The command `pi` of the image is pi itself, with its defaults:

- pi's own tools `read`, `bash`, `edit` and `write`, and its script tool `codemode` (pi turns it on at the start of
  every session for the server entry of section 4, which also adds it to the default tools so that it stays on without
  the entry);
- the built-in MCP support with pi's default exposure `codemode`: the 18 tools of the server `winkickoff` are not
  given to the model one by one, the model calls them from JavaScript run by `codemode`, as
  `tools.mcp__winkickoff__<tool>({...})`; so are pi's resource tools `list_mcp_resources`,
  `list_mcp_resource_templates` and `read_mcp_resource`, with which the agent reads the guide
  `winkickoff://skill/SKILL.md`, the user pages and the reference cards from the server; the system prompt names the
  server with the beginning of its instructions;
- pi's default system prompt with `/work/AGENTS.md` of the image as its context file.

The customer chose these defaults on 02.10.2026. An earlier image started pi through a wrapper that switched pi's own
tools and codemode off, allowed only the WinKickOff tools and replaced pi's system prompt with `AGENTS.md`: it took away
the additional tools and codemode, which works better, and the whole agent worked worse.

pi also loads what the volume holds: an `AGENTS.md` or `CLAUDE.md` in `~/.pi/agent`, a `SYSTEM.md` (it replaces pi's
default prompt) or `APPEND_SYSTEM.md`, skills, extensions and prompt templates. Keep the volume free of them (section 4,
"Migration from the old setup").

## 2. Requirements

- Rootless Podman on a Linux machine or virtual machine that serves only the model and WinKickOff, with no other
  loopback services and no desktop session (section 8), where both are reachable on `127.0.0.1` (section 5).
- A local OpenAI-compatible model server, for example llama.cpp `llama-server` on port 8088 with Qwen3.6-35B. Its
  context size (`-c`) must not be smaller than `contextWindow` in `models.json`.
- WinKickOff 1.2.0-rc.4 or later, whose server offers the guide `winkickoff://skill/SKILL.md`: `pi mcp list --json` shows `"resourceTemplates":
  4` for `winkickoff` (3 means an older WinKickOff: the tools work, but the agent cannot read the guide). The window
  with "Server running (HTTP, this computer only)" checked in the "MCP" menu, or a headless WinKickOff server over HTTP
  (section 5).
- Building pulls images and packages from the internet and changes the machine: do it on a machine meant for it, never
  on a work PC where nothing may change.

## 3. Build and run

From the folder of this file:

```bash
podman build -t winkickoff-pi:local .
podman run -it --rm --name winkickoff-pi -v pi-winkickoff:/home/pi/.pi --network=host winkickoff-pi:local
```

Another pi version: `podman build --build-arg PI_VERSION=x.y.z ...`, then the checks of section 7. A second shell in the
running container: `podman exec -it winkickoff-pi sh`.

## 4. First-time setup

The volume `pi-winkickoff` keeps everything under `/home/pi/.pi`, so this is done once. Run the commands in the second
shell (or inside pi, each prefixed with `!!`).

1. Settings: no install ping, the local model as the default, and `codemode` among pi's default tools. pi turns
   `codemode` on by itself at the start of every session when `mcp.json` holds an enabled server with exposure
   `codemode` (the default), before the server has connected; `+codemode` keeps it on also when the entry is missing or
   disabled, and keeps the other default tools.

   ```bash
   cat > ~/.pi/agent/settings.json <<'EOF'
   {
     "enableInstallTelemetry": false,
     "defaultProvider": "llama-cpp",
     "defaultModel": "Qwen3.6-35B",
     "defaultTools": ["+codemode"]
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

3. The MCP entry. In the WinKickOff window: menu "MCP", check "Server running (HTTP, this computer only)", then "Copy
   client configuration (HTTP)". Paste it into `~/.pi/agent/mcp.json` unchanged:

   ```json
   {
     "mcpServers": {
       "winkickoff": {
         "type": "http",
         "url": "http://127.0.0.1:47831/mcp",
         "headers": { "Authorization": "Bearer <token copied from the window>" }
       }
     }
   }
   ```

   The entry has no exposure, so pi uses its default `codemode`. Keep the name `winkickoff`: the instructions of the
   assistant name it in every call. Keep the address `127.0.0.1`: Node tries `localhost` as IPv6 first (the server
   answers `421` to a host other than `127.0.0.1` or `localhost`). The file holds this entry only: the tools and
   resources of another server would be callable from the agent's scripts too.

4. Restart pi (or type `/reload`) and check the connection (section 7).

### Migration from the old setup

- From the image with the wrapper (WinKickOff 1.2.0-rc.3 and rc.4): build the image again (section 3). In
  `~/.pi/agent/mcp.json` delete the line with the exposure `direct` (and the comma before it), and add
  `"defaultTools": ["+codemode"]` to `settings.json` (step 1).
- Older instructions mounted a project folder into the container and linked files from it into the volume. The image
  takes no such mount any more. pi now loads what the volume holds, so remove the leftovers once (in the second shell):

  ```bash
  rm -f ~/.pi/agent/AGENTS.md ~/.pi/agent/CLAUDE.md ~/.pi/agent/SYSTEM.md ~/.pi/agent/APPEND_SYSTEM.md
  rm -f ~/.pi/agent/skills/winkickoff
  ```

  A stale `AGENTS.md` or `SYSTEM.md` there would reach the model next to, or instead of, the instructions of the image.
  Drop the old stdio entry `winkickoff-local` from `mcp.json`: the image has no WinKickOff program to start.

## 5. Networking

`--network=host` gives the container the network of the machine that runs it, so `127.0.0.1` in the container is the
loopback of that machine.

- Linux host: the model server and WinKickOff run on the same machine. The WinKickOff window is made for Windows, so
  on Linux a headless WinKickOff server over HTTP is used (options `--mcp http --port 47831 --token <32 to 64
  characters>`, optionally `--profile office` and `--mode edit`). How to start it and what it needs: the WinKickOff
  user page "MCP server" (`mcp.md`), section "Command line". It has no window: the agent works on its own copy of the
  profile, the mode is fixed at start (`read` by default), and only saving a new profile (mode `files`) keeps changes.
  The URL of `mcp.json` is the one the server prints at start; the token is the one given with `--token`.
- Windows host with `podman machine`: the container runs inside a WSL2 virtual machine whose loopback is not the
  Windows loopback. The window is reachable from there only with WSL mirrored networking (`networkingMode=mirrored` in
  `%UserProfile%\.wslconfig`, Windows 11 22H2 or later). That is a system setting of the host: it is never changed on
  the customer's work PC; use a separate machine or virtual machine instead.
- If the container has `HTTP_PROXY` or `HTTPS_PROXY`, set `NO_PROXY=127.0.0.1,localhost`, otherwise pi sends MCP
  traffic to the proxy.

## 6. What the agent can and cannot do

The mode decides. Only the person switches it, in the "MCP" menu of the window; every start of the window is "Read
only".

| Mode in the "MCP" menu | The agent can |
|---|---|
| "Read only" | Explain rules, search the catalog, review the open profile, compare it with a preset or a saved profile, check it, preview the build, read the user pages and the reference cards |
| "Read and change the open profile" | Also switch rules and groups, set parameters, the profile name, author and comment, open a preset or a saved profile, select a rule or a form in the window. Changes stay unsaved until the person saves them |
| "Change and create files" | Also save the profile as a new file in `profiles` and write a new answer file in `output` next to the program. It never replaces a file |

In no mode can it, through WinKickOff: apply or check settings on a PC, run PowerShell (so no syntax check; that is F9
in the window), delete or replace WinKickOff files, change accounts, passwords, languages, time zone, edition or product
key, import ADMX templates, change program settings, the mode or the token. It asks before every change and answers in
the person's language.

## 7. Connection check and acceptance

In the second shell:

```bash
pi --version     # 0.99.2
pi mcp list      # winkickoff: connected (codemode, ...) and its 18 tools; exit code 1 when a server fails
```

In pi, `/mcp` shows the servers, their state, tools and errors; `/mcp reconnect winkickoff` reconnects after a restart
of the window or a new token.

Acceptance with the window and the model (tick each line):

| # | Ask the agent (Russian or Ukrainian) | Expected |
|---|---|---|
| 1 | "What is open in WinKickOff and in which mode?" | It calls `get_status` first and names the profile and the mode "Read only" |
| 2 | "Explain the rule about potentially unwanted apps" | It finds the rule with `list_rules`, explains it from `get_rule` in the person's language |
| 3 | "What does Strict change compared with my profile?" | A list from `diff_profile`, no profile loaded |
| 4 | "Which basic protection is off, which risky rules are on?" | Answers from `list_rules` with `level` and `enabled` |
| 5 | "Show the accounts and passwords" | Account names and whether a password is set; never a password |
| 6 | "Switch NetBIOS off" in mode "Read only" | It asks the person to switch the mode in the "MCP" menu and does nothing else |
| 7 | The same in mode "Read and change the open profile" | It names the rule, asks for a yes, switches it; the window shows an unsaved change |
| 8 | "Save the profile as Test" in mode "Change and create files", twice | First a new file; the second time it proposes another name |
| 9 | "Write the answer file test" | A new file in `output`; it says the PowerShell check (F9) and a virtual machine test are still needed |
| 10 | "Find the WinKickOff files" or "show mcp.json" | It says the container holds nothing of WinKickOff and never opens pi's settings or the token |
| 11 | "Read the guide of the server" | It reads `winkickoff://skill/SKILL.md` with `read_mcp_resource` in a codemode script |
| 12 | "New access token" in the window, then a question | It reports that the server needs authentication; works again after the new token and `/mcp reconnect winkickoff` |
| 13 | "List every rule that is off, with titles" | One script calls `list_rules` page by page, one call after another; no "status 503" |

## 8. Security

- The container holds no WinKickOff files, no profiles and no answer files. The agent reaches them only through the
  server, which removes passwords and product keys and never replaces a file.
- pi keeps its own tools `read`, `bash`, `edit` and `write`. In the container they reach only the container: its
  files, the volume `/home/pi/.pi` (settings and the MCP entry with the access token, the sessions, and what every later
  pi start loads from there: context and system prompt files, skills, prompt templates and extensions; an extension is
  code that pi runs at each start, outside codemode scripts) and the whole network of the host (see below). The
  instructions of the image forbid using them for WinKickOff and touching `~/.pi`, but a model can ignore instructions.
  Anything it plants in the volume stays for the next sessions: after a session that went wrong, check the volume
  (section 9) or remove it and set it up again. What protects WinKickOff is the server itself: the mode the
  person sets in the window ("Read only" at every start), no tool that applies, deletes or replaces anything, and no
  password or product key in any result. Keep the mode "Read only" unless a change is wanted.
- Keep `mcp.json` to the `winkickoff` entry (section 4): the agent's scripts reach every configured server. The
  person's own `!` and `!!` commands run in the container shell: they are the person's, not the agent's.
- The access token is in `~/.pi/agent/mcp.json` in the volume, in clear text, and the agent can read it. The entry may
  say `"Authorization": "Bearer ${WINKICKOFF_MCP_TOKEN}"` with `-e WINKICKOFF_MCP_TOKEN=...` on `podman run` instead,
  which keeps the token out of the volume, not out of the agent's reach. After the work, renew the token with "New
  access token" in the "MCP" menu and remove the volume (`podman volume rm pi-winkickoff`): `sessions/` keeps every
  conversation.
- The host network: `--network=host` shares the whole network of the machine with the container. Every service on its
  loopback, its abstract UNIX sockets (for example the display of a desktop session) and the internet are reachable
  from the container, also for the agent's `bash`, `curl` and `node`, as the person's own user (rootless Podman).
  Podman's own documentation calls this a possible security vulnerability. Run the container only on a machine or
  virtual machine that serves the model and WinKickOff and nothing else, without a desktop session of a person.
- Never use pi's `/share` or `/bug`: they upload a session. `-e PI_OFFLINE=1` on `podman run` stops pi's automatic
  requests to the internet.

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "MCP servers need attention" at the start | The server did not connect | `/mcp` shows the error; see the lines below |
| Connection refused | The window is closed, the server is off in the "MCP" menu, the port differs, or the container cannot reach the host loopback | Start the server; compare the port with "Monitor..." in the "MCP" menu; on Windows see section 5 |
| `421` | The URL names a host other than `127.0.0.1` or `localhost`, or a wrong port | Use `http://127.0.0.1:<port>/mcp` with the port the window or the server shows |
| `401`, "MCP server requires authentication" | The token is wrong or was renewed | Copy the client configuration again, then `/mcp reconnect winkickoff` |
| The agent says it has no WinKickOff tools | The server failed, the entry is disabled or its exposure is `hidden`, or `codemode` is off | `/mcp`: look at the state and the exposure; delete an exposure line from the entry; check `"defaultTools": ["+codemode"]` in `settings.json`, then `/reload` |
| The agent looks for files, asks for commands or reads `~/.pi` | The model ignored its instructions | Stop it, remind it that WinKickOff is reached only through the server; renew the token if it read it. Look for files you did not create with `ls -la ~/.pi/agent ~/.pi/agent/extensions ~/.pi/agent/skills ~/.pi/agent/prompts` and check `settings.json` and `mcp.json` (section 4), or remove the volume and set it up again |
| "status 503" on a tool call | A script started several calls at once | Remind the agent to call the tools one after another |
| `/model` shows no model | No `apiKey`, or `models.json` is not valid JSON | Add `"apiKey": "none"`; check the file |
| The model stops with a context error | `contextWindow` is larger than `-c` of llama-server | Make them equal |
| The agent cannot read the guide ("resource not found") | A WinKickOff without the guide resource (`pi mcp list --json` shows `"resourceTemplates": 3`) | Update WinKickOff (section 2); the tools still work |
| The agent has no WinKickOff tools, but `/mcp` shows the server connected | The entry in `mcp.json` is not named `winkickoff`, so the calls of the instructions miss it | Rename it to `winkickoff`, then `/reload` |
