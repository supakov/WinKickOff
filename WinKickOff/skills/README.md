# Agent skills for WinKickOff

This folder holds an Agent Skill for AI assistants that **use** WinKickOff through its MCP server. The skill teaches
the assistant how to work with WinKickOff safely: read the rule catalog, explain rules in the person's language,
adjust the open profile only in the mode the person allows, check it and prepare an answer file that is tested in a
virtual machine first.

It is not for developers of WinKickOff; they follow `AGENTS.md` in the repository root.

## Contents

| Path | What it is |
|---|---|
| `winkickoff/SKILL.md` | The skill: golden rules, first steps, tools by mode, errors, short workflows |
| `winkickoff/references/tools.md` | Exact reference of the 18 tools and the resources of the MCP server |
| `winkickoff/references/workflows.md` | Recipes for 23 typical requests |
| `winkickoff/references/server.md` | Resources, limits, a server with or without a window, protocol errors |
| `winkickoff/references/concepts.md` | Rules, levels, phases, groups, presets, data forms, the build |
| `winkickoff/references/decisions.md` | Deliberate decisions not to "fix", window labels in Russian and Ukrainian |

The skill follows the open Agent Skills format (agentskills.io): a folder named like the skill with a `SKILL.md` file
and optional `references/`. The portable build ships this folder next to `WinKickOff.exe`.

## Reading the skill over MCP

The WinKickOff MCP server also serves this folder as resources, in every mode: `winkickoff://skill/SKILL.md` and
`winkickoff://skill/references/{file}` (`tools.md`, `server.md`, `workflows.md`, `concepts.md`, `decisions.md`). When it serves them, the
`instructions` the server sends at the handshake tell an agent that has not loaded the skill to read
`winkickoff://skill/SKILL.md` first (pi shows these instructions only for `codemode` and `deferred` exposure; the pi
container names the resource in its own instructions). So a client without a skill installer, or
an agent without file tools, can still follow the skill: it reads the resource with its resource tool (in pi,
`read_mcp_resource`) instead of a file. The server takes the folder from next to the program (`WinKickOff/skills/winkickoff`
from sources, `skills\winkickoff` next to `WinKickOff.exe`); without it the server simply has no skill resources.

## Before you install it: connect the MCP server

The skill only explains how to use the WinKickOff tools; it does not connect them. Connect the WinKickOff MCP server
to your assistant first, as described in [the MCP page of the user documentation](../../docs/user/en/mcp.md) (in the
portable build: `docs\user\en\mcp.md` next to `WinKickOff.exe`; also in Russian and Ukrainian). In short: the window
offers "Copy client configuration (stdio)" and "Copy client configuration (HTTP)" in its "MCP" menu.

The server starts read-only. In the window you switch the mode in the "MCP" menu. For a stdio server (Claude Desktop,
a stdio entry of Claude Code or pi), the mode is the `--mode` flag of the client configuration and stays there for
every session: keep `--mode read` (or no `--mode`) in the stored configuration, raise it only for a task, then set it
back.

## Claude Code

Copy the folder `winkickoff` (not this whole folder) into one of these places:

- for you on this computer: `%USERPROFILE%\.claude\skills\winkickoff\` (on Linux and macOS `~/.claude/skills/winkickoff/`);
- for one project: `<project>\.claude\skills\winkickoff\`.

Then the skill loads by itself when you talk about WinKickOff, or you call it with `/winkickoff`. After adding a new
skill folder, start a new session. Copy the folder rather than linking it: links on Windows need extra rights.

## Claude Desktop and claude.ai

1. Turn on "Code execution and file creation" in the settings (Capabilities). Team and Enterprise owners must allow
   skills for the organisation first.
2. Make a ZIP file whose root is the folder `winkickoff`: inside the archive there must be `winkickoff/SKILL.md` and
   `winkickoff/references/...`. On Windows: right-click the folder `winkickoff`, "Send to", "Compressed (zipped)
   folder".
3. Upload it: "Customize", "Skills", the "+" button, "Create skill", "Upload a skill", then pick the ZIP (older
   versions: "Settings", "Features").

Claude Desktop reaches WinKickOff only through stdio (`WinKickOff-mcp.exe`), so it works with its own copy of the
profile and never sees the open window. claude.ai in the browser cannot reach a server on your computer at all; there
the skill can only explain concepts.

If the upload is refused, check that the folder in the ZIP is named exactly `winkickoff`. The files of this repository
use Windows line endings; if an upload ever complains about the file format, convert `SKILL.md` to Unix line endings
in the copy you zip.

## pi coding agent

- Copy or link the folder into pi's skills folder: `~/.pi/agent/skills/winkickoff/`.
- Or list the path in `~/.pi/agent/settings.json` under `"skills"`, for example
  `"skills": ["/path/to/WinKickOff/skills/winkickoff"]`.
- The pi container of this repository (`pi-agent/`) holds no copy of the repository and no file tools: there the agent
  reads the skill from the server (`winkickoff://skill/SKILL.md`, see "Reading the skill over MCP" above).
- Run `/reload` in pi after adding it. A small local model may not load the skill by itself: start the task with
  `/skill:winkickoff`, and run it again after the conversation was compacted.
- Expose the WinKickOff tools with `"exposure": "direct"` in `~/.pi/agent/mcp.json` (see `pi-agent/README.md`), so the
  model sees them as `mcp__winkickoff__<tool>`.

## Updating

The skill describes WinKickOff 1.2.0-rc.4 and catalog 0.5. When the MCP tools, the presets or the rule catalog change,
update the skill together with the code, and copy the folder again to every place where it is installed.
