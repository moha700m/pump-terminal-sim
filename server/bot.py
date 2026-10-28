#!/usr/bin/env python3
"""صيّاد الجوال — PAPER trading bot on LIVE pump.fun data (PumpPortal public websocket).
NO wallet, NO keys, NO signing, NO real orders. Virtual balance only."""
import asyncio, json, time, os, sqlite3, threading, urllib.request, random
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import websockets
D=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(D)
STATE=f"{D}/state.json"; RUGS=f"{D}/rugs.json"; DB=f"{D}/trades.db"; PORT=8811
SUPPLY=1_000_000_000; FEE=0.01; LAT_PEN=0.02  # 1% pump fee each side + 2% latency/MEV haircut each side
DEF_RULES={"maxSpendSol":5.34,"devMax":10,"bundleMax":20,"blacklist":True,"exitOnMove":True,"tp":60,"sl":25,
 "sizePct":3,"maxOpen":5,"goal":5,"minBuyers":10,"minVolSol":4,"watchSec":45,"maxHoldMin":10}
def load(p,d):
  try: return json.load(open(p))
  except Exception: return d
S=load(STATE,None) or {"running":True,"start":1000.0,"cash":1000.0,"rules":DEF_RULES,"pos":{},"stats":{"wins":0,"loss":0,"skip":0,"seen":0,"trades":0,"realized":0.0},
  "sessionStart":time.time(),"goalHit":False}
S["rules"]={**DEF_RULES,**S.get("rules",{})}
RUG=set(load(RUGS,[])); FEED=[]; SKIPS=load(f"{D}/skips.json",[]); SOLUSD=[100.0]; T={}  # live token map
LOCK=threading.RLock(); WS=[None]; SUBQ=[]; STARTED=time.time(); MSGS=[0]
db=sqlite3.connect(DB,check_same_thread=False)
db.execute("create table if not exists trades(ts real,mint text,sym text,side text,sol real,usd real,price real,pnl real,reason text)")
db.execute("create table if not exists events(ts real,mint text,sym text,kind text,reason text)")
def log(*a): print(time.strftime("%F %T"),*a,flush=True)
def ev(t,kind,why,v=None):
  e={"ts":time.time(),"mint":t["mint"],"n":t["sym"][:12],"kind":kind,"why":why,"v":v}
  FEED.append(e); del FEED[:-80]
  db.execute("insert into events values(?,?,?,?,?)",(e["ts"],e["mint"],e["n"],kind,why)); db.commit()
def save():
  with LOCK:
    json.dump(S,open(STATE+".tmp","w")); os.replace(STATE+".tmp",STATE)
    json.dump(sorted(RUG),open(RUGS,"w")); json.dump(SKIPS[-200:],open(f"{D}/skips.json","w"))
def price(t): return t["vS"]/t["vT"]  # SOL per token
def buy_out(t,sol):  # constant-product bonding curve
  sol_in=sol*(1-FEE); k=t["vS"]*t["vT"]; return (t["vT"]-k/(t["vS"]+sol_in))*(1-LAT_PEN)
def sell_out(t,tok):
  k=t["vS"]*t["vT"]; return (t["vS"]-k/(t["vT"]+tok))*(1-FEE)*(1-LAT_PEN)
def equity():
  v=S["cash"]
  for m,p in S["pos"].items():
    t=T.get(m); v+= (sell_out(t,p["tok"])*SOLUSD[0]) if t else p["usd"]
  return v
def sub(keys,on=True): pass  # trades come from pump.fun swap-api polling (PumpPortal trade stream needs a paid key)
def skip(t,why):
  t["done"]=True; S["stats"]["skip"]+=1; SKIPS.append([t["sym"][:12],why,time.time()]); ev(t,"skip",why); sub([t["mint"]],False)
def enter(t):
  R=S["rules"]; usd=S["cash"]*R["sizePct"]/100; sol=usd/SOLUSD[0]
  deployed=sum(p["sol"] for p in S["pos"].values())
  if deployed+sol>R["maxSpendSol"]: return skip(t,"cap: max spend reached")
  tok=buy_out(t,sol); S["cash"]-=usd
  S["pos"][t["mint"]]={"sym":t["sym"][:12],"sol":sol,"usd":usd,"tok":tok,"entry":sol/tok,"ts":time.time(),"peak":0,"dev":t["dev"],"bundle":list(t["bundle"])}
  S["stats"]["trades"]+=1; t["done"]=True
  why=f"buyers {len(t['buyers'])} · vol {t['vol']:.1f} SOL · curve {prog(t):.0f}% · dev {devpct(t):.0f}% · bundle {bpct(t):.0f}%"
  db.execute("insert into trades values(?,?,?,?,?,?,?,?,?)",(time.time(),t["mint"],t["sym"],"buy",sol,usd,price(t),0,why)); db.commit()
  ev(t,"buy",why,-usd); save(); log("BUY",t["sym"],round(usd,2),why)
def exitp(m,why):
  p=S["pos"].pop(m); t=T.get(m)
  usd=sell_out(t,p["tok"])*SOLUSD[0] if t else 0.0
  pnl=usd-p["usd"]; S["cash"]+=usd; S["stats"]["realized"]+=pnl; S["stats"]["wins" if pnl>0 else "loss"]+=1
  db.execute("insert into trades values(?,?,?,?,?,?,?,?,?)",(time.time(),m,p["sym"],"sell",0,usd,price(t) if t else 0,pnl,why)); db.commit()
  ev(t or {"mint":m,"sym":p["sym"]},"win" if pnl>0 else "loss",why,pnl); log("SELL",p["sym"],round(pnl,2),why)
  save()
devpct=lambda t:max(0,t["devTok"])/SUPPLY*100
bpct=lambda t:sum(max(0,v) for v in t["bundleTok"].values())/SUPPLY*100
prog=lambda t:max(0,min(100,(t["vS"]-30)/85*100))
def on_create(x):
  m=x["mint"]; t={"mint":m,"sym":x.get("symbol") or "?","dev":x["traderPublicKey"],"t0":time.time(),"vS":x["vSolInBondingCurve"],"vT":x["vTokensInBondingCurve"],
    "devTok":x.get("initialBuy",0) or 0,"buyers":set(),"vol":x.get("solAmount",0) or 0,"bundle":set(),"bundleTok":{},"done":False,"last":time.time(),"devSold":False,"peakS":x["vSolInBondingCurve"]}
  T[m]=t; S["stats"]["seen"]+=1
  if S["rules"]["blacklist"] and t["dev"] in RUG: return skip(t,"dev wallet = known rug (blacklist)")
  sub([m])
def on_trade(x):
  t=T.get(x.get("mint"));
  if not t: return
  w=x["traderPublicKey"]; tok=x.get("tokenAmount",0) or 0; side=x["txType"]
  t["vS"]=x.get("vSolInBondingCurve",t["vS"]); t["vT"]=x.get("vTokensInBondingCurve",t["vT"]); t["vol"]+=x.get("solAmount",0) or 0; t["last"]=time.time()
  t["peakS"]=max(t["peakS"],t["vS"])
  early=x.get("_ts",0)-t.get("firstTs",x.get("_ts",0))<=1.5
  if side=="buy":
    t["buyers"].add(w)
    if w==t["dev"]: t["devTok"]+=tok
    elif early: t["bundle"].add(w); t["bundleTok"][w]=t["bundleTok"].get(w,0)+tok
  else:
    if w==t["dev"]:
      t["devTok"]-=tok; t["devSold"]=True
    if w in t["bundleTok"]: t["bundleTok"][w]-=tok
  p=S["pos"].get(t["mint"])
  if p and S["rules"]["exitOnMove"] and side=="sell":
    if w==t["dev"]: return exitp(t["mint"],"dev sold → exit now")
    if w in p["bundle"] and tok>SUPPLY*0.005: return exitp(t["mint"],"bundle wallet dumping → exit now")
  # rug detection -> blacklist creator forever
  if t["devSold"] and t["vS"]<t["peakS"]*0.5 and t["peakS"]>35 and t["dev"] not in RUG:
    RUG.add(t["dev"]); log("RUG blacklisted",t["dev"][:8],t["sym"])
def tick():
  R=S["rules"]; now=time.time()
  for m,t in list(T.items()):
    if t["done"]:
      if m not in S["pos"] and now-t["last"]>600: T.pop(m,None)
      continue
    age=now-t["t0"]
    if not S["running"] or S["goalHit"]:
      if age>R["watchSec"]: skip(t,"bot stopped" if not S["running"] else "goal hit — no new entries")
      continue
    if R["blacklist"] and t["dev"] in RUG: skip(t,"dev wallet = known rug"); continue
    if devpct(t)>R["devMax"]: skip(t,f"dev holds {devpct(t):.0f}% > {R['devMax']}%"); continue
    if bpct(t)>R["bundleMax"]: skip(t,f"bundle {len(t['bundle'])} wallets hold {bpct(t):.0f}%"); continue
    if t["devSold"]: skip(t,"dev already selling"); continue
    if age<R["watchSec"]: continue
    if len(S["pos"])>=R["maxOpen"]: skip(t,"max open positions"); continue
    if len(t["buyers"])>=R["minBuyers"] and t["vol"]>=R["minVolSol"] and 3<prog(t)<70: enter(t)
    else: skip(t,f"weak: {len(t['buyers'])} buyers, {t['vol']:.1f} SOL vol")
  for m,p in list(S["pos"].items()):
    t=T.get(m)
    if not t:
      t=T[m]={"mint":m,"sym":p["sym"],"dev":p["dev"],"t0":p["ts"],"vS":p.get("vS",30),"vT":p.get("vT",1.07e9),"devTok":0,"buyers":set(),"vol":0,"bundle":set(p["bundle"]),
        "bundleTok":{},"done":True,"last":time.time(),"devSold":False,"peakS":p.get("vS",30)}; sub([m])
    p["vS"],p["vT"]=t["vS"],t["vT"]
    val=sell_out(t,p["tok"])*SOLUSD[0]; ch=(val/p["usd"]-1)*100; p["peak"]=max(p["peak"],ch); p["now"]=ch
    if ch>=R["tp"]: exitp(m,f"take-profit +{ch:.0f}%")
    elif ch<=-R["sl"]: exitp(m,f"stop-loss {ch:.0f}%")
    elif p["peak"]>=30 and ch<p["peak"]-25: exitp(m,f"trailing stop (peak +{p['peak']:.0f}%)")
    elif now-p["ts"]>R["maxHoldMin"]*60: exitp(m,f"time exit {ch:+.0f}%")
    elif not S["running"]: exitp(m,f"user stop → closed {ch:+.0f}%")
  if equity()>=S["start"]*R["goal"] and not S["goalHit"]: S["goalHit"]=True; log("GOAL HIT")
def snap():
  st=S["stats"]; eq=equity()
  return {"paper":True,"running":S["running"],"goalHit":S["goalHit"],"start":S["start"],"cash":round(S["cash"],2),"equity":round(eq,2),"solusd":SOLUSD[0],
   "stats":st,"rules":S["rules"],"rugs":len(RUG),"watching":sum(1 for t in T.values() if not t["done"]),"msgs":MSGS[0],"uptime":int(time.time()-STARTED),
   "pos":[{"mint":m,"n":p["sym"],"usd":round(p["usd"],2),"ch":round(p.get("now",0),1),"age":int(time.time()-p["ts"])} for m,p in S["pos"].items()],
   "feed":FEED[-40:][::-1],"skips":SKIPS[-30:][::-1],"ts":time.time(),"source":"PumpPortal new-token websocket + pump.fun swap-api trades (live)"}
async def ws_loop():
  while True:
    try:
      async with websockets.connect("wss://pumpportal.fun/api/data",ping_interval=20) as w:
        WS[0]=w; await w.send(json.dumps({"method":"subscribeNewToken"}))
        log("ws connected")
        async def sender():
          while True:
            while SUBQ: await w.send(json.dumps(SUBQ.pop(0)))
            await asyncio.sleep(0.2)
        st=asyncio.create_task(sender())
        try:
          async for raw in w:
            x=json.loads(raw); MSGS[0]+=1
            with LOCK:
              try:
                if x.get("txType")=="create" and "vSolInBondingCurve" in x: on_create(x)
                elif x.get("txType") in("buy","sell"): on_trade(x)
              except Exception as e: log("msg err",repr(e))
        finally: st.cancel()
    except Exception as e: log("ws error",repr(e)); await asyncio.sleep(5)
import datetime
K=30*1.073e9
def fetch_trades(m,cursor_seen):
  r=urllib.request.Request(f"https://swap-api.pump.fun/v2/coins/{m}/trades?limit=50",headers={"User-Agent":"Mozilla/5.0"})
  return json.load(urllib.request.urlopen(r,timeout=8)).get("trades",[])
async def poll_loop():
  loop=asyncio.get_running_loop()
  while True:
    with LOCK: ms=[m for m,t in T.items() if (not t["done"]) or m in S["pos"]]
    if not ms: await asyncio.sleep(1)
    for m in ms:
      try: tr=await loop.run_in_executor(None,fetch_trades,m,None)
      except Exception as e: await asyncio.sleep(1); continue
      with LOCK:
        t=T.get(m)
        if not t: continue
        seen=t.setdefault("seenIds",set())
        for x in reversed(tr):
          if x["slotIndexId"] in seen: continue
          seen.add(x["slotIndexId"]); MSGS[0]+=1
          ts=datetime.datetime.fromisoformat(x["timestamp"].replace("Z","+00:00")).timestamp()
          t.setdefault("firstTs",ts)
          p=float(x["priceSol"]) or 1e-12
          if x.get("program","pump")!="pump": t["vS"]=115.0  # graduated/migrated: treat as curve-complete
          y={"mint":m,"traderPublicKey":x["userAddress"],"txType":x["type"],"tokenAmount":float(x["baseAmount"]),"solAmount":float(x["amountSol"]),
             "vSolInBondingCurve":(K*p)**0.5,"vTokensInBondingCurve":(K/p)**0.5,"_ts":ts}
          try: on_trade(y)
          except Exception as e: log("trade err",repr(e))
      await asyncio.sleep(0.3)
async def main_loop():
  n=0
  while True:
    await asyncio.sleep(1); n+=1
    with LOCK: tick()
    if n%60==1:
      try: SOLUSD[0]=float(json.load(urllib.request.urlopen("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",timeout=8))["price"])
      except Exception: pass
    if n%10==0:
      save(); open(f"{D}/status.txt","w").write(time.strftime("%F %T"))
      with LOCK: json.dump(snap(),open(f"{D}/public_state.json","w"))
class H(SimpleHTTPRequestHandler):
  def __init__(s,*a,**k): super().__init__(*a,directory=ROOT,**k)
  def log_message(s,*a): pass
  def js(s,o,c=200):
    b=json.dumps(o).encode(); s.send_response(c); s.send_header("Content-Type","application/json"); s.send_header("Content-Length",len(b)); s.end_headers(); s.wfile.write(b)
  def do_GET(s):
    if s.path.startswith("/api/state"):
      with LOCK: return s.js(snap())
    if s.path.startswith("/api/stream"):
      s.send_response(200); s.send_header("Content-Type","text/event-stream"); s.send_header("Cache-Control","no-cache"); s.end_headers()
      try:
        while True:
          with LOCK: d=json.dumps(snap())
          s.wfile.write(f"data: {d}\n\n".encode()); s.wfile.flush(); time.sleep(1.5)
      except Exception: return
    if s.path.startswith("/server/"): return s.js({"err":"forbidden"},403)
    return super().do_GET()
  def do_POST(s):
    b=json.loads(s.rfile.read(int(s.headers.get("Content-Length",0)) or 0) or b"{}")
    with LOCK:
      if s.path=="/api/run": S["running"]=bool(b.get("running")); log("USER", "START" if S["running"] else "STOP")
      elif s.path=="/api/rules":
        for k,v in b.items():
          if k in DEF_RULES: S["rules"][k]=type(DEF_RULES[k])(v)
      elif s.path=="/api/reset": S.update(cash=equity(),start=equity(),goalHit=False,sessionStart=time.time())
      else: return s.js({"err":"?"},404)
    save(); return s.js({"ok":True})
if __name__=="__main__":
  threading.Thread(target=lambda:ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever(),daemon=True).start()
  log("paper bot up on",PORT,"running=",S["running"])
  async def m(): await asyncio.gather(ws_loop(),main_loop(),poll_loop())
  asyncio.run(m())
