# podman build -t winkickoff-pi:local ./pi-agent/
# podman run -it --rm --name winkickoff-pi -v .:/projects:rw,Z,U -v pi-winkickoff:/home/pi/.pi --network=host --userns=keep-id winkickoff-pi:local
# podman exec -it winkickoff-pi sh
#
# disable telemetry
# !!cat > ~/.pi/agent/settings.json <<EOF
# {
# 	"enableInstallTelemetry":false
# }
# EOF
#
# Add your model
# !!cat > ~/.pi/agent/models.json << EOF
# {
#   "providers": {
#     "llama-cpp": {
#       "baseUrl": "http://localhost:8088/v1",
#       "api": "openai-completions",
#       "apiKey": "?",
#       "models": [
#         {
#           "id": "Qwen3.6-35B",
#           "name": "Qwen3.6-35B",
#           "contextWindow": 262144,
#           "maxTokens": 196608
#         }
#       ]
#     }
#   }
# }
# EOF
#
# !!cat > ~/.pi/agent/mcp.json <<EOF
# {
#   "mcpServers": {
#     "winkickoff": {
#       "type": "http",
#       "url": "http://127.0.0.1:47831/mcp",
#       "headers": {
#         "Authorization": "Bearer ????????????"
#       }
#     }
#   }
# }
# EOF

FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        file && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @earendil-works/pi-coding-agent && \
    npm cache clean --force && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p \
        /projects \
        /projects/specification \
        /projects/sources \
        /home/pi \
        /home/pi/.pi/agent && \
    chmod -R 777 /projects /home/pi

WORKDIR /projects

ENV HOME=/home/pi
ENV PI_CODING_AGENT_DIR=/home/pi/.pi/agent
ENV PI_SKIP_VERSION_CHECK=1

ENV XDG_CONFIG_HOME=/home/pi/.config
ENV XDG_CACHE_HOME=/home/pi/.cache
ENV XDG_DATA_HOME=/home/pi/.local/share

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

CMD ["pi"]
