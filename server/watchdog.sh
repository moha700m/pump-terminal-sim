#!/bin/bash
exec 9>/workspace/pump-terminal/server/.watchdog.lock; flock -n 9 || exit 0
while true; do /workspace/pump-terminal/server/ensure.sh 9>&- >/dev/null 2>&1; sleep 60; done
