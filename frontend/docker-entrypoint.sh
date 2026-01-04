#!/bin/sh
set -e

# If node_modules is missing or empty in the mounted volume, install dependencies there
if [ ! -d "/app/node_modules" ] || [ -z "$(ls -A /app/node_modules 2>/dev/null)" ]; then
  echo "[entrypoint] node_modules is missing or empty, installing dependencies..."
  npm install --silent
else
  echo "[entrypoint] node_modules already present, skipping install"
fi

# Exec the container command
exec "$@"
