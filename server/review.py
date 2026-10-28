#!/usr/bin/env python3
"""Weekly (or on-demand) review of the PAPER bot: python3 review.py [days=7] -> review-YYYY-MM-DD.md"""
import sqlite3,sys,time,os,collections
D=os.path.dirname(os.path.abspath(__file__)); days=float(sys.argv[1]) if len(sys.argv)>1 else 7; since=time.time()-days*86400
db=sqlite3.connect(f"{D}/trades.db"); db.execute("create table if not exists tokens(ts real,mint text,sym text,dev text,decision text,reason text,age real,buyers int,vol real,curve real,devpct real,top10 real,bundle real,sameamt int)")
tr=db.execute("select ts,mint,sym,side,usd,pnl,reason from trades where ts>=? order by ts",(since,)).fetchall()
buys={};closed=[]
for ts,m,sym,side,usd,pnl,why in tr:
  if side=="buy": buys[m]={"ts":ts,"sym":sym,"why":why,"pnl":0.0,"curve":None}
  elif m in buys:
    buys[m]["pnl"]+=pnl
    if side=="sell": b=buys.pop(m); b["exit"]=why; closed.append(b)
for b in closed:
  r=db.execute("select curve from tokens where mint=? and decision='buy'",(b.get("mint",""),)).fetchone()
  try: b["curve"]=float(b["why"].split("curve ")[1].split("%")[0])
  except Exception: b["curve"]=None
def phase(c): return "?" if c is None else "0-10%" if c<10 else "10-30%" if c<30 else "30-70%" if c<70 else "70%+"
def wr(g): return f"{sum(1 for x in g if x['pnl']>0)}/{len(g)} ({100*sum(1 for x in g if x['pnl']>0)/len(g):.0f}%) · net ${sum(x['pnl'] for x in g):+.2f}"
L=[f"# مراجعة صيّاد الجوال (ورقي) — {time.strftime('%Y-%m-%d %H:%M')} (Asia/Riyadh)","",f"الفترة: آخر {days:g} يوم. **كل الأرقام ورقية — مو فلوس حقيقية.**",""]
L+=[f"## الإجمالي","",f"- صفقات مقفلة: {len(closed)} · {wr(closed) if closed else '—'}",f"- مراكز مفتوحة/غير مكتملة بالفترة: {len(buys)}",""]
byh=collections.defaultdict(list); byp=collections.defaultdict(list)
for b in closed: byh[time.strftime("%H",time.localtime(b["ts"]))].append(b); byp[phase(b["curve"])].append(b)
L+=["## نسبة الربح حسب الساعة (الرياض)","","| الساعة | ربح/الكل · صافي |","|---|---|"]+[f"| {h}:00 | {wr(g)} |" for h,g in sorted(byh.items())]+[""]
L+=["## حسب مرحلة الكيرف عند الدخول","","| المرحلة | ربح/الكل · صافي |","|---|---|"]+[f"| {p} | {wr(g)} |" for p,g in sorted(byp.items())]+[""]
rej=db.execute("select reason,count(*) from tokens where ts>=? and decision='skip' group by reason",(since,)).fetchall()
agg=collections.Counter()
for r,c in rej: agg[r.split(":")[0].split(" holds")[0].split(" holders")[0].split(" ")[0] if r.startswith("weak") else r.split(" ")[0]+" "+(r.split(" ")[1] if len(r.split(" "))>1 else "")]+=c
tot=db.execute("select count(*),sum(decision='buy') from tokens where ts>=?",(since,)).fetchone()
L+=["## أكثر قاعدة رفضت عملات","",f"عملات شافها: {tot[0]} · دخلنا: {tot[1] or 0}","","| السبب | العدد |","|---|---|"]+[f"| {k} | {v} |" for k,v in agg.most_common(10)]+[""]
L+=["## أسوأ الصفقات","","| العملة | صافي | سبب الخروج |","|---|---|---|"]+[f"| ${b['sym']} | ${b['pnl']:+.2f} | {b.get('exit','')} |" for b in sorted(closed,key=lambda x:x["pnl"])[:10]]+["","> تنبيه: التداول الورقي يبالغ بالنتايج (تأخير، MEV، رَق). مو نصيحة مالية."]
out=f"{D}/review-{time.strftime('%Y-%m-%d')}.md"; open(out,"w").write("\n".join(L)); print(out)
