#!/bin/bash
set -e

# Define gateway token
if [ -z "$OPENCLAW_GATEWAY_TOKEN" ]; then
    export OPENCLAW_GATEWAY_TOKEN="generate-your-secure-token-here"
fi

echo "[Init] Starting OpenClaw Gateway on port 18789..."
openclaw gateway run --port 18789 --allow-unconfigured &
GATEWAY_PID=$!

echo "[Init] Starting Settings API bridge on port 5174..."
cd /app/chat-ui/ui
node api-server.js &
API_PID=$!

echo "[Init] Starting Nginx for serving SPA and proxying..."
nginx -g 'daemon off;' &
NGINX_PID=$!

# Wait for any process to exit
wait -n $GATEWAY_PID $API_PID $NGINX_PID
echo "[Panic] One of the background processes exited. Terminating container..."
exit 1
