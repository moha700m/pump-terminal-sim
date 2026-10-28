#!/bin/bash
# Keeps ONE paper bot + ONE pusher alive. Stop trading = UI Stop switch (bot keeps running, no new entries).
cd /workspace/pump-terminal/server
for l in bot.log push.log; do [ -f $l ] && [ $(stat -c %s $l) -gt 5000000 ] && { cp $l $l.1; : > $l; }; done
B="python3 -u /workspace/pump-terminal/server/bot.py"; P="python3 -u /workspace/pump-terminal/server/push.py"
BP=$(pgrep -f "$B"|head -1)
if [ -n "$BP" ] && [ -f status.txt ] && [ $(( $(date +%s)-$(stat -c %Y status.txt) )) -gt 300 ]; then echo "$(date '+%F %T') stale -> restart" >> bot.log; kill $BP; sleep 3; kill -9 $BP 2>/dev/null; fi
pgrep -f "$B" >/dev/null || { nohup nice -n 5 $B >> bot.log 2>&1 & echo "bot started $!"; }
pgrep -f "$P" >/dev/null || { nohup nice -n 10 $P >> push.log 2>&1 & echo "pusher started $!"; }
