#!/bin/bash
# Fully shut down (process level). Normally use the Stop switch instead.
pkill -f /workspace/pump-terminal/server/watchdog.sh; pkill -f /workspace/pump-terminal/server/push.py; pkill -f /workspace/pump-terminal/server/bot.py; echo stopped
