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
| `winkickoff/references/concepts.md` | Rules, levels, phases, groups, presets, data forms, the build, deliberate decisions |

The skill follows the open Agent Skills format (agentskills.io): a folder named like the skill with a `SKILL.md` file
and optional `references/`. The portable build ships this folder next to `WinKickOff.exe`.

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
  `"skills": ["/projects/WinKickOff/skills/winkickoff"]`.
- In the pi container of this repository (`pi-agent/`, the repository mounted at `/projects`):

  ```bash
  mkdir -p ~/.pi/agent/skills
  ln -s /projects/WinKickOff/skills/winkickoff ~/.pi/agent/skills/winkickoff
  ```

- Run `/reload` in pi after adding it. A small local model may not load the skill by itself: start the task with
  `/skill:winkickoff`, and run it again after the conversation was compacted.
- Expose the WinKickOff tools with `"exposure": "direct"` in `~/.pi/agent/mcp.json` (see `pi-agent/README.md`), so the
  model sees them as `mcp__winkickoff__<tool>`.

## Updating

The skill describes WinKickOff 1.2.0-rc.1 and catalog 0.5. When the MCP tools, the presets or the rule catalog change,
update the skill together with the code, and copy the folder again to every place where it is installed.
