#!/bin/sh
set -e

# Ensure /app/storage is writable by appuser (fixes Docker named volume ownership)
if [ -d /app/storage ] && [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /app/storage 2>/dev/null || true
    exec gosu appuser "$@"
else
    exec "$@"
fi
