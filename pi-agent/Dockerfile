# The WinKickOff assistant: the pi agent with a local model that works ONLY through the MCP tools of WinKickOff.
# Setup, networking, security and troubleshooting: README.md next to this file.
#
# Build (from the folder of this file) and run. Nothing is mounted except the volume with pi's settings:
#   podman build -t winkickoff-pi:local .
#   podman run -it --rm --name winkickoff-pi -v pi-winkickoff:/home/pi/.pi --network=host winkickoff-pi:local
# A second shell in the running container (for the setup below, or "pi mcp list"):
#   podman exec -it winkickoff-pi sh
#
# One-time setup of the volume (in that second shell; inside pi prefix each command with !!):
#
# cat > ~/.pi/agent/settings.json <<'EOF'
# {
#   "enableInstallTelemetry": false,
#   "defaultProvider": "llama-cpp",
#   "defaultModel": "Qwen3.6-35B"
# }
# EOF
#
# cat > ~/.pi/agent/models.json <<'EOF'
# {
#   "providers": {
#     "llama-cpp": {
#       "baseUrl": "http://localhost:8088/v1",
#       "api": "openai-completions",
#       "apiKey": "none",
#       "models": [
#         { "id": "Qwen3.6-35B", "name": "Qwen3.6-35B", "contextWindow": 262144, "maxTokens": 196608 }
#       ]
#     }
#   }
# }
# EOF
#
# The MCP entry: "Copy client configuration (HTTP)" in the "MCP" menu of the WinKickOff window, plus "exposure": "direct"
# (required: the image loads no codemode, so other exposures leave the agent without tools). Keep the name winkickoff
# (the wrapper below allows only the tools of a server with this name) and no other server in this file.
# cat > ~/.pi/agent/mcp.json <<'EOF'
# {
#   "mcpServers": {
#     "winkickoff": {
#       "type": "http",
#       "url": "http://127.0.0.1:47831/mcp",
#       "headers": { "Authorization": "Bearer <token copied from the window>" },
#       "exposure": "direct"
#     }
#   }
# }
# EOF

# The full image name: Podman does not have to resolve a short name (it may refuse or ask which registry to use).
FROM docker.io/library/ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

# bash: the person's own "!" commands in pi. ripgrep and fd-find: the interactive pi looks for them at every start and
# would otherwise download them from GitHub into the volume. curl: the Node.js download below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        ripgrep \
        fd-find && \
    rm -rf /var/lib/apt/lists/*

ENV HOME=/home/pi
ENV PI_CODING_AGENT_DIR=/home/pi/.pi/agent
ENV PI_SKIP_VERSION_CHECK=1
# No install ping to pi.dev, not even on the first start of a new volume, before settings.json exists.
ENV PI_TELEMETRY=0
ENV XDG_CONFIG_HOME=/home/pi/.config
ENV XDG_CACHE_HOME=/home/pi/.cache
ENV XDG_DATA_HOME=/home/pi/.local/share

# Node.js from the official release archive, checked against the SHA-256 pinned here (nodejs.org/dist/v<version>/
# SHASUMS256.txt). Not the NodeSource package: it depends on a script interpreter the agent must not have. Another
# version: --build-arg NODE_VERSION=... with both checksums of that release.
ARG NODE_VERSION=22.23.3
ARG NODE_SHA256_AMD64=1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af
ARG NODE_SHA256_ARM64=5ced2d48d1d7198739b7f86804de0171aefb6823b684b12341d3321afc3cb0b2
RUN arch="$(dpkg --print-architecture)" && \
    case "$arch" in \
        amd64) node_arch=x64; sum="$NODE_SHA256_AMD64" ;; \
        arm64) node_arch=arm64; sum="$NODE_SHA256_ARM64" ;; \
        *) echo "no Node.js archive for $arch" >&2; exit 1 ;; \
    esac && \
    archive="node-v${NODE_VERSION}-linux-${node_arch}.tar.gz" && \
    curl -fsSLo "/tmp/$archive" "https://nodejs.org/dist/v${NODE_VERSION}/$archive" && \
    echo "$sum  /tmp/$archive" | sha256sum -c - && \
    mkdir -p /opt/node && \
    tar -xzf "/tmp/$archive" -C /opt/node --strip-components=1 --no-same-owner && \
    rm -f "/tmp/$archive"
# /opt/node/bin after /usr/local/bin: the command "pi" is the wrapper below, not npm's own link.
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/node/bin

# The tested pi version (MCP is built in since 0.99.0, Node.js 22.19 or later); --ignore-scripts as pi's documentation
# installs it, so no package script runs as root during the build. Another version: --build-arg PI_VERSION=x.y.z
ARG PI_VERSION=0.99.2
RUN npm install -g --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}" && \
    npm cache clean --force

# The command "pi" is a wrapper in /usr/local/bin (ahead of npm's own pi in PATH), so the same restrictions hold for the
# CMD of the image, for "podman exec ... pi" and for print, json and rpc modes, whatever the volume contains:
#   --no-extensions -e builtin:mcp   only the built-in MCP extension (no codemode, no tool search, no extension from
#                                    the volume or a package can add a tool)
#   --no-builtin-tools, --exclude-tools ...   read, bash, edit, write, grep, find, ls and powershell are off and cannot
#                                    be switched on (not by /reload, not by settings.json)
#   --tools ...                      the only tools pi may give the model: the 18 tools of the MCP server named
#                                    winkickoff (exposure direct) and list_mcp_resources, list_mcp_resource_templates
#                                    and read_mcp_resource; another server in mcp.json adds no tool
#   --no-skills, --no-context-files, --no-prompt-templates   no skill, no AGENTS.md or CLAUDE.md and no prompt
#                                    template from the volume or from / is loaded
#   --system-prompt /work/AGENTS.md  the instructions of this image replace pi's default prompt for a coding agent
#   --append-system-prompt /dev/null an empty addendum in place of an APPEND_SYSTEM.md in the volume
# Subcommands (pi mcp list, pi config, pi install, ...) take no session flags and get the arguments unchanged.
RUN real="$(npm prefix -g)/bin/pi" && \
    test -x "$real" && \
    test "$real" != /usr/local/bin/pi && \
    printf '%s\n' \
        '#!/bin/sh' \
        '# pi restricted to the WinKickOff MCP tools; written by the Dockerfile of the image.' \
        'case "${1-}" in' \
        '  install|remove|uninstall|update|list|config|auth|mcp) exec @PI@ "$@" ;;' \
        'esac' \
        'exec @PI@ --no-extensions -e builtin:mcp --no-builtin-tools --exclude-tools read,bash,edit,write,grep,find,ls,powershell,codemode,tool_search --tools mcp__winkickoff__check_profile,mcp__winkickoff__diff_profile,mcp__winkickoff__get_messages,mcp__winkickoff__get_profile,mcp__winkickoff__get_rule,mcp__winkickoff__get_status,mcp__winkickoff__list_groups,mcp__winkickoff__list_profiles,mcp__winkickoff__list_rules,mcp__winkickoff__load_profile,mcp__winkickoff__preview_build,mcp__winkickoff__save_profile,mcp__winkickoff__set_group,mcp__winkickoff__set_param,mcp__winkickoff__set_profile_info,mcp__winkickoff__set_rules,mcp__winkickoff__show_item,mcp__winkickoff__write_answer_file,list_mcp_resources,list_mcp_resource_templates,read_mcp_resource --no-skills --no-context-files --no-prompt-templates --system-prompt /work/AGENTS.md --append-system-prompt /dev/null "$@"' \
        > /usr/local/bin/pi && \
    sed -i "s|@PI@|$real|g" /usr/local/bin/pi && \
    chmod 755 /usr/local/bin/pi && \
    test "$(command -v pi)" = /usr/local/bin/pi && \
    pi --version

RUN mkdir -p /home/pi/.pi/agent /work && \
    chmod -R 777 /home/pi

# The folder pi starts in holds only the instructions of the assistant.
WORKDIR /work
COPY AGENTS.md /work/AGENTS.md

CMD ["pi"]
