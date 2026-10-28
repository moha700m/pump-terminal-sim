#!/usr/bin/env python3
# Publishes paper-only public_state.json to GitHub Pages repo (live/state.json) every ~120s via gh api. No secrets written.
import subprocess,json,base64,time,os
D=os.path.dirname(os.path.abspath(__file__)); R="repos/moha700m/pump-terminal-sim/contents/live/state.json"
while True:
  try:
    b=base64.b64encode(open(f"{D}/public_state.json","rb").read()).decode()
    sha=subprocess.run(["gh","api",R,"--jq",".sha"],capture_output=True,text=True).stdout.strip()
    a=["gh","api","-X","PUT",R,"-f","message=paper state update","-f",f"content={b}"]+(["-f",f"sha={sha}"] if sha else [])
    r=subprocess.run(a,capture_output=True,text=True,timeout=60)
    print(time.strftime("%F %T"),"push",200 if r.returncode==0 else r.stderr[:200],flush=True)
  except Exception as e: print(time.strftime("%F %T"),"err",e,flush=True)
  time.sleep(120)
