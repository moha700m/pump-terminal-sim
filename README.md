# صيّاد الجوال — Pump Terminal (SIMULATION)
Paper-trading **simulation** mockup. All tokens, prices and profits are fictional. No wallet, no keys, no signing, no network trading. Not financial advice.
Static site: open `index.html`.

## Live paper bot (v2) — still PAPER ONLY, view-only public page
- Data: PumpPortal free new-token websocket + pump.fun swap-api trades (no keys). No wallet, no signing, virtual $1000.
- Rules (editable in Rules screen, persisted server-side): dev hold ≤5%; dev sell in first 10 min → skip / exit; top-10 holders (estimated from seen trades) ≤25%; >3 first-second buyers with same SOL amount → skip (bundle); rug-wallet blacklist; size 2% of balance, max 5 open, max open spend 5.34 SOL; sell 50% at +60%, trail the rest 20 pts; stop-loss −25%; 10-min force exit; 5x session goal.
- Fills: bonding-curve math + 1% fee + 3% delay/front-run penalty + random size-scaled slippage, each side. UI shows NET vs GROSS P&L and max drawdown.
- Logs: `server/tokens.csv` + SQLite (`trades.db`: tokens/trades/events). Review: `python3 server/review.py [days]` → `review-YYYY-MM-DD.md` (auto weekly).
- Paper results overstate reality (latency, MEV, rugs). Not financial advice.
