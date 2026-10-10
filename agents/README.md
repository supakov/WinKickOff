# WinKickOff assistant for any AI agent

`AGENTS.md` in this folder holds the instructions of an assistant that helps a person with WinKickOff profiles: it
explains rules, reviews and compares profiles, finds weak protection, changes the open profile on request and, when the
person allows it, studies the settings of the computer the program runs on. It is not tied to one agent: any AI agent
whose client connects MCP servers and loads a file of instructions can use it. The assistant reaches WinKickOff only
through its MCP server and never through files or commands.

## 1. A folder for the assistant

Give the assistant an empty folder of its own, with nothing of WinKickOff in it: not the program folder, not the
profiles, not the answer files. An agent that sees program files starts reading them instead of using the tools.

Copy `AGENTS.md` into that folder under the name your client loads:

| Client | File in the folder |
|---|---|
| Codex CLI, Cursor, OpenCode and other clients that read `AGENTS.md` | `AGENTS.md` as it is |
| Claude Code | `CLAUDE.md` with the single line `@AGENTS.md` next to `AGENTS.md`, or `AGENTS.md` copied as `CLAUDE.md` |
| Gemini CLI | `GEMINI.md`, or `AGENTS.md` with `"contextFileName": "AGENTS.md"` in its settings |
| A chat client with a field for system instructions (Claude Desktop project instructions, LM Studio, Open WebUI) | Paste the text of `AGENTS.md` into that field |

Start the client in that folder.

## 2. Connect the MCP server

In the WinKickOff window, menu "MCP":

1. Switch on "Server running (HTTP, this computer only)" and choose "Copy client configuration (HTTP)", or choose "Copy
   client configuration (stdio)" for a client that starts the server itself.
2. Paste the copied entry into the MCP settings of your client under the name `winkickoff`. The HTTP entry holds the
   access token: keep it out of chats and shared folders. "New access token" makes the old one useless.
3. Restart or reconnect the client and ask the assistant "what can you do?": its first call reads the state of the
   program.

A client on another machine reaches the HTTP server only through `127.0.0.1` of the computer that runs WinKickOff; the
server refuses every other address.

## 3. What the assistant may do

The person chooses the mode in the "MCP" menu; the assistant never changes it:

| Mode | The assistant may |
|---|---|
| "Read only" | Read the catalog, the open profile without secrets, compare and check it |
| "Read and change the open profile" | Also switch rules, change parameters and open profiles; the window shows unsaved changes |
| "Change and create files" | Also save a new profile and write a new answer file; existing files are never replaced |

"Allow reading the settings of this PC" in the same menu lets the assistant read the computer the program runs on: which
protections take effect, which do not and what was found instead. The read changes nothing, runs without administrator
rights and is never saved: it is off at every start. The assistant never applies settings, never runs other commands,
never sees passwords or product keys and never imports templates.

## 4. Before you rely on it

- The assistant asks before every change and reports what a switch changed in cascade.
- A profile it calls valid only builds in memory. Build the final file in the window ("Build autounattend.xml...",
  F9), which also checks the PowerShell syntax, and install it in a virtual machine first.
- The assistant speaks the language of the person and uses the labels of the window in that language.
