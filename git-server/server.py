#!/usr/bin/env python3
"""
Git HTTP Server + VHS/Analog-Horror Web UI
  - Git smart HTTP (clone / push / pull) com Basic Auth
  - Video/Audio WebRTC calling com sinalização HTTP polling
  - Intro analog-horror: TV de tubo, voz filtrada, visualizador de frequências
  - Chat em tempo real, navegador de arquivos, log de commits
"""

import os, sys, subprocess, json, hmac, hashlib, time, threading, secrets, base64, shutil, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from collections import defaultdict
from pathlib import Path

PORT      = 5000
BASE_DIR  = Path(__file__).parent.resolve()
BARE_REPO = BASE_DIR / "repo.git"
WORKSPACE = BASE_DIR / "workspace"
STATIC    = BASE_DIR / "static"
_SK       = os.environ.get("GIT_SERVER_SECRET", secrets.token_hex(32))
GIT_USER  = os.environ.get("GIT_SERVER_USER",     "admin")
GIT_PASS  = os.environ.get("GIT_SERVER_PASSWORD", "admin")

_ws_lock = threading.Lock()

def refresh_workspace():
    with _ws_lock:
        try:
            chk = subprocess.run(["git","--git-dir",str(BARE_REPO),"rev-parse","HEAD"],
                                 capture_output=True, text=True)
            if chk.returncode != 0: return "Empty — push commits first"
            if WORKSPACE.exists():
                v = subprocess.run(["git","-C",str(WORKSPACE),"rev-parse","--git-dir"],
                                   capture_output=True, text=True)
                if v.returncode != 0: shutil.rmtree(WORKSPACE, ignore_errors=True)
            if not WORKSPACE.exists():
                r = subprocess.run(["git","clone","--local",str(BARE_REPO),str(WORKSPACE)],
                                   capture_output=True, text=True)
                return "Cloned OK" if r.returncode == 0 else r.stderr.strip()
            r = subprocess.run(["git","-C",str(WORKSPACE),"pull","--ff-only"],
                               capture_output=True, text=True)
            return r.stdout.strip() or r.stderr.strip() or "Up to date"
        except Exception as e: return f"Error: {e}"

class RateLimiter:
    def __init__(self, limit=120, window=60):
        self.limit=limit; self.window=window
        self._h=defaultdict(list); self._l=threading.Lock()
    def allowed(self, ip):
        now=time.time()
        with self._l:
            self._h[ip]=[t for t in self._h[ip] if now-t<self.window]
            if len(self._h[ip])>=self.limit: return False
            self._h[ip].append(now); return True

class Sessions:
    TTL=86400
    def __init__(self, secret):
        self._k=secret.encode(); self._s={}; self._l=threading.Lock()
    def _sign(self,t): return hmac.new(self._k,t.encode(),hashlib.sha256).hexdigest()
    def create(self,user):
        tok=secrets.token_urlsafe(32); c=f"{tok}.{self._sign(tok)}"
        with self._l: self._s[tok]={"user":user,"at":time.time()}
        return c
    def validate(self,c):
        if not c or "." not in c: return None
        tok,sig=c.rsplit(".",1)
        if not hmac.compare_digest(sig,self._sign(tok)): return None
        with self._l:
            s=self._s.get(tok)
            if not s: return None
            if time.time()-s["at"]>self.TTL: del self._s[tok]; return None
            return s["user"]
    def delete(self,c):
        if c and "." in c:
            with self._l: self._s.pop(c.rsplit(".",1)[0],None)

class Chat:
    def __init__(self): self._m=[]; self._l=threading.Lock()
    def post(self,user,text):
        m={"user":user,"text":text[:1000],"ts":time.strftime("%H:%M:%S")}
        with self._l:
            self._m.append(m)
            if len(self._m)>200: self._m=self._m[-200:]
        return m
    def all(self):
        with self._l: return list(self._m)

class Signaling:
    def __init__(self): self._q=defaultdict(list); self._l=threading.Lock()
    def send(self,to,msg):
        with self._l:
            if len(self._q[to])>80: return False
            self._q[to].append({**msg,"_ts":time.time()}); return True
    def poll(self,user):
        with self._l: msgs=list(self._q[user]); self._q[user]=[]; return msgs

class Presence:
    TTL=25
    def __init__(self): self._u={}; self._l=threading.Lock()
    def beat(self,user):
        with self._l: self._u[user]=time.time()
    def online(self):
        now=time.time()
        with self._l: return sorted([u for u,t in self._u.items() if now-t<self.TTL])
    def remove(self,user):
        with self._l: self._u.pop(user,None)

_TEXT_EXTS={".py",".js",".ts",".tsx",".jsx",".html",".htm",".css",".scss",
            ".json",".yaml",".yml",".toml",".ini",".cfg",".conf",".md",
            ".txt",".sh",".bash",".c",".cpp",".h",".java",".go",".rs",
            ".rb",".php",".sql",".xml",".csv",".env",".gitignore",".ino",
            ".nix",".lock",".vue",".dart",".kt",".swift"}

def safe_path(base,rel):
    try:
        p=(base/unquote(rel.lstrip("/"))).resolve(); br=base.resolve()
        if p==br or str(p).startswith(str(br)+os.sep): return p
    except: pass
    return None

def list_dir(p):
    items=[]
    try:
        for e in sorted(p.iterdir(),key=lambda x:(x.is_file(),x.name.lower())):
            if e.name.startswith(".") and e.name not in (".env",): continue
            items.append({"name":e.name,"type":"file" if e.is_file() else "dir",
                          "size":e.stat().st_size if e.is_file() else None})
    except: pass
    return {"items":items}

def read_file(p):
    ext=p.suffix.lower()
    if ext not in _TEXT_EXTS: return {"error":"Binary file — preview not supported"}
    try:
        c=p.read_text(errors="replace")
        if len(c)>300_000: c=c[:300_000]+"\n\n[... truncated ...]"
        return {"content":c,"ext":ext.lstrip(".")}
    except Exception as e: return {"error":str(e)}

def git_log(n=60):
    try:
        r=subprocess.run(["git","--git-dir",str(BARE_REPO),"log",f"-{n}",
                          "--pretty=format:%H|%an|%ae|%ar|%s"],capture_output=True,text=True)
        out=[]
        for line in r.stdout.strip().splitlines():
            parts=line.split("|",4)
            if len(parts)==5:
                h,name,email,rel,msg=parts
                out.append({"hash":h[:8],"full":h,"author":name,"email":email,"rel":rel,"msg":msg})
        return out
    except: return []

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CYBERFUNTECH SERVER</title>
<link href="https://fonts.googleapis.com/css2?family=VT323&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/monokai.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#050709;--sf:#0b0f13;--bd:#1a2030;
  --tx:#d4e0c0;--mu:#6a7a5a;--ac:#b8ff60;
  --rd:#ff3a2a;--yw:#ffcc00;--gr:#39ff14;
  --cobalt:#0e16b0;--cobalt2:#1a23cc;--phosphor:#39ff14
}
html,body{width:100%;height:100%;overflow:hidden;background:#000}
body{font-family:'VT323',monospace;color:var(--tx);animation:bFlk 10s infinite}
@keyframes bFlk{0%,97%,100%{opacity:1}97.5%{opacity:.88}98.5%{opacity:.96}}

/* ── VHS global layers ── */
#vhs-canvas{position:fixed;inset:0;pointer-events:none;z-index:9000;opacity:.05}
#scanlines{position:fixed;inset:0;pointer-events:none;z-index:9001;
  background:repeating-linear-gradient(to bottom,transparent 0,transparent 2px,
  rgba(0,0,0,.28) 2px,rgba(0,0,0,.28) 4px)}
#chroma{position:fixed;inset:0;pointer-events:none;z-index:9002;mix-blend-mode:screen;
  opacity:0;animation:chPulse 7s infinite}
@keyframes chPulse{0%,93%,100%{opacity:0}95%{opacity:.2}97%{opacity:.07}}
#tracking{position:fixed;left:0;right:0;height:3px;pointer-events:none;z-index:9003;
  background:rgba(255,255,255,.8);opacity:0;animation:trLine 14s infinite}
@keyframes trLine{0%,100%{opacity:0;top:-4px}4%{opacity:1;top:0}52%{opacity:.3;top:100%}56%{opacity:0}}
#glitch-flash{position:fixed;inset:0;z-index:8500;pointer-events:none;opacity:0;background:white}
#vhs-hud{position:fixed;top:0;left:0;right:0;pointer-events:none;z-index:9004;
  padding:10px 16px;display:flex;justify-content:space-between;align-items:flex-start;font-size:20px}
.hud-play{color:var(--rd);animation:blP 1s step-end infinite}
@keyframes blP{0%,100%{opacity:1}50%{opacity:0}}
.hud-right{text-align:right;color:var(--phosphor);line-height:1.4}
.hud-mid{color:var(--yw);letter-spacing:2px}
#tracking-msg{position:fixed;bottom:36px;right:14px;font-size:22px;color:var(--yw);
  z-index:9004;opacity:0;animation:trMsg 20s infinite}
@keyframes trMsg{0%,87%,100%{opacity:0}88%{opacity:1}93%{opacity:.5}95%{opacity:0}}
#sub-text{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);font-size:18px;
  color:rgba(180,220,120,.45);letter-spacing:3px;z-index:8100;min-width:300px;text-align:center;
  text-shadow:1px 0 rgba(255,50,50,.4),-1px 0 rgba(50,200,255,.4)}

/* ── ANALOG HORROR INTRO ─────────────────────────────── */
#intro{position:fixed;inset:0;background:#000;z-index:8000;
  display:flex;align-items:center;justify-content:center}
/* CRT TV frame */
.crt-tv{
  position:relative;
  width:min(700px,90vw);
  aspect-ratio:4/3;
  background:#111;
  border-radius:28px;
  padding:18px;
  box-shadow:
    0 0 0 4px #1a1a1a,
    0 0 0 8px #2a2a2a,
    0 0 60px rgba(0,0,0,.9),
    inset 0 0 30px rgba(0,0,0,.8);
}
/* Screen inside TV */
.crt-screen{
  width:100%;height:100%;
  background:var(--cobalt);
  border-radius:12px;
  position:relative;
  overflow:hidden;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;
  /* Screen curvature via border-radius + padding */
}
/* Screen scanlines (denser for CRT) */
.crt-screen::before{
  content:'';position:absolute;inset:0;z-index:10;pointer-events:none;
  background:repeating-linear-gradient(to bottom,transparent 0,transparent 1px,
    rgba(0,0,0,.35) 1px,rgba(0,0,0,.35) 2px);
  border-radius:inherit
}
/* Screen reflection */
.crt-screen::after{
  content:'';position:absolute;
  top:-20%;left:-10%;width:55%;height:60%;
  background:radial-gradient(ellipse at center,rgba(255,255,255,.06) 0%,transparent 70%);
  pointer-events:none;z-index:11;border-radius:50%;transform:rotate(-25deg)
}
/* Vignette on the cobalt screen */
.crt-vignette{
  position:absolute;inset:0;z-index:12;pointer-events:none;border-radius:inherit;
  background:radial-gradient(ellipse at center,transparent 50%,rgba(0,0,8,.7) 100%)
}
/* Screen flicker */
.crt-screen{animation:scrFlk 6s infinite}
@keyframes scrFlk{0%,96%,100%{filter:brightness(1)}97%{filter:brightness(.9)}98%{filter:brightness(1.02)}}

.slide{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:20px;text-align:center;padding:28px;
  opacity:0;transition:opacity .35s;z-index:5}
.slide.active{opacity:1}

.hero-logo{max-width:68%;max-height:48%;object-fit:contain;
  filter:contrast(1.1) saturate(1.1) brightness(.95);
  image-rendering:auto;border-radius:4px}
.logo-enter{animation:lgShrink 2.8s cubic-bezier(.2,.8,.3,1) forwards}
@keyframes lgShrink{
  0%{transform:scale(5);opacity:0;filter:brightness(3) blur(10px) saturate(2)}
  20%{opacity:1;filter:brightness(1.5) blur(3px)}
  100%{transform:scale(1);opacity:1;filter:contrast(1.1) saturate(1.1) brightness(.95)}
}
.ilabel{font-size:clamp(16px,3.2vw,28px);letter-spacing:5px;color:#c0c8ff;
  text-shadow:2px 0 rgba(255,80,80,.5),-2px 0 rgba(80,200,255,.5);
  animation:lbFlk 4s infinite}
@keyframes lbFlk{0%,91%,100%{opacity:1}92%{opacity:.6}94%{opacity:.9}}
.ititle{font-size:clamp(22px,5vw,52px);letter-spacing:7px;color:#e0e8ff;
  text-shadow:3px 0 rgba(255,60,60,.6),-3px 0 rgba(60,200,255,.6),0 0 30px rgba(180,200,255,.3)}
.iwarn{font-size:clamp(14px,3vw,32px);letter-spacing:4px;color:var(--rd);
  animation:wPulse 1.8s ease-in-out infinite}
@keyframes wPulse{0%,100%{opacity:1;text-shadow:2px 0 #f00,-2px 0 rgba(0,150,255,.4)}
  50%{opacity:.65;text-shadow:4px 0 #f00,-4px 0 rgba(0,150,255,.6),0 0 20px #ff0}}
.isub{font-size:clamp(12px,2.5vw,24px);letter-spacing:4px;color:#8090c0;animation:lbFlk 5s infinite}

/* TV antenna top dot */
.tv-dot{position:absolute;top:-8px;left:50%;transform:translateX(-50%);
  width:6px;height:6px;background:#2a2a2a;border-radius:50%}

/* Channel number overlay */
.crt-ch{position:absolute;top:8px;left:10px;font-size:14px;color:rgba(255,255,200,.6);
  letter-spacing:2px;z-index:15;font-family:'VT323',monospace}
.crt-rec{position:absolute;top:8px;right:10px;font-size:14px;color:rgba(255,60,60,.7);
  letter-spacing:1px;z-index:15;animation:blP 1.2s step-end infinite}

/* ── FREQUENCY VISUALIZER PANEL ──────────────────────── */
#freq-panel{
  position:fixed;bottom:60px;left:16px;z-index:8200;
  width:320px;background:rgba(0,4,0,.92);border:1px solid #1a3a10;
  padding:10px;display:none;
  box-shadow:0 0 20px rgba(57,255,20,.08)
}
#freq-panel .fp-title{font-size:14px;color:var(--phosphor);letter-spacing:3px;
  margin-bottom:6px;text-shadow:0 0 8px rgba(57,255,20,.5)}
#freq-canvas{display:block;width:100%;height:80px;image-rendering:pixelated}
.fp-labels{display:flex;justify-content:space-between;font-size:11px;
  color:#2a6a1a;letter-spacing:1px;margin-top:3px}
.fp-ambient{margin-top:8px;border-top:1px solid #1a3a10;padding-top:6px;
  display:flex;gap:12px;font-size:13px}
.fp-amb-item{color:#3a6a2a;display:flex;align-items:center;gap:4px}
.fp-amb-dot{width:6px;height:6px;border-radius:50%;background:var(--phosphor);
  box-shadow:0 0 4px var(--phosphor);animation:blP .9s step-end infinite}
.fp-chain{margin-top:6px;font-size:12px;color:#2a6a1a;line-height:1.6}
.fp-chain span{color:var(--phosphor)}

/* ── LOGIN ── */
#login-screen{position:fixed;inset:0;background:#000;z-index:7000;
  display:none;align-items:center;justify-content:center}
.lbox{position:relative;width:420px;border:2px solid var(--ac);padding:40px 36px;
  background:#030507;box-shadow:0 0 40px rgba(184,255,96,.1)}
.lbox::after{content:'CYBERFUNTECH SYSTEMS v3.1.0';position:absolute;top:-12px;
  left:50%;transform:translateX(-50%);font-size:14px;color:var(--ac);
  background:#000;padding:0 10px;letter-spacing:2px;white-space:nowrap}
.ltitle{text-align:center;margin-bottom:32px}
.ltitle h1{font-size:36px;color:var(--ac);letter-spacing:4px;text-shadow:0 0 18px rgba(184,255,96,.4)}
.ltitle p{font-size:16px;color:var(--rd);letter-spacing:3px;margin-top:4px;animation:wPulse 2s infinite}
.field{margin-bottom:20px}
.field label{display:block;font-size:18px;color:var(--mu);letter-spacing:3px;margin-bottom:4px}
.field input{width:100%;background:#000;border:1px solid var(--bd);
  border-bottom:2px solid var(--ac);padding:10px 12px;color:var(--ac);
  font-family:'VT323',monospace;font-size:22px;letter-spacing:2px;outline:none}
.field input:focus{box-shadow:0 2px 16px rgba(184,255,96,.2)}
.lbtn{width:100%;background:transparent;border:2px solid var(--ac);color:var(--ac);
  font-family:'VT323',monospace;font-size:28px;letter-spacing:6px;padding:10px;
  cursor:pointer;margin-top:8px;transition:all .2s}
.lbtn:hover{background:rgba(184,255,96,.1);box-shadow:0 0 28px rgba(184,255,96,.25)}
.lerr{color:var(--rd);font-size:18px;letter-spacing:2px;text-align:center;
  margin-bottom:12px;min-height:24px;animation:wPulse 1s infinite}

/* ── APP ── */
#app{position:fixed;inset:0;background:var(--bg);z-index:6000;display:none;flex-direction:column;overflow:hidden}
.aheader{background:var(--sf);border-bottom:2px solid var(--bd);
  padding:6px 14px;display:flex;align-items:center;gap:8px;flex-shrink:0;font-size:18px}
.aheader h1{color:var(--ac);letter-spacing:3px;font-size:21px;text-shadow:0 0 10px rgba(184,255,96,.35)}
.cinput{flex:1;background:#000;border:1px solid var(--bd);padding:4px 10px;
  color:var(--mu);font-family:'Share Tech Mono',monospace;font-size:12px;cursor:text}
.hbtn{background:transparent;border:1px solid var(--bd);color:var(--mu);
  font-family:'VT323',monospace;font-size:16px;padding:3px 10px;cursor:pointer;
  letter-spacing:1px;transition:all .15s}
.hbtn:hover{border-color:var(--ac);color:var(--ac)}
.hbtn.call-btn{border-color:#00ccff66;color:#00ccff}
.hbtn.call-btn:hover{background:rgba(0,204,255,.1);box-shadow:0 0 14px rgba(0,204,255,.25)}
.hbtn.call-btn.active{background:rgba(0,204,255,.12);animation:blP .7s step-end infinite}
.hbtn.danger{border-color:var(--rd);color:var(--rd)}
.hbtn.danger:hover{background:rgba(255,58,42,.1)}
.layout{display:flex;flex:1;overflow:hidden}
.sb{width:248px;background:var(--sf);border-right:2px solid var(--bd);
  display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.sb-tabs{display:flex;border-bottom:1px solid var(--bd)}
.sb-tab{flex:1;padding:6px;text-align:center;font-size:16px;cursor:pointer;
  color:var(--mu);border-bottom:2px solid transparent;letter-spacing:1px}
.sb-tab.on{color:var(--ac);border-bottom-color:var(--ac)}
.sb-body{flex:1;overflow-y:auto;padding:6px}
.ti{display:flex;align-items:center;gap:5px;padding:3px 5px;cursor:pointer;
  font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:1px}
.ti:hover{color:var(--ac)}
.ti.sel{color:var(--ac);text-shadow:0 0 8px rgba(184,255,96,.4)}
.back{font-size:15px;color:var(--mu);padding:4px 6px;cursor:pointer}
.back:hover{color:var(--ac)}
.cm-i{padding:5px 6px;border-bottom:1px solid var(--bd)}
.cm-i .hsh{font-family:'Share Tech Mono',monospace;font-size:11px;color:var(--ac)}
.cm-i .ms{font-size:14px;margin-top:1px}
.cm-i .mt{font-size:12px;color:var(--mu);margin-top:1px}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.m-tabs{display:flex;background:var(--sf);border-bottom:1px solid var(--bd)}
.m-tab{padding:5px 14px;font-size:16px;cursor:pointer;color:var(--mu);
  border-bottom:2px solid transparent;letter-spacing:1px}
.m-tab.on{color:var(--tx);border-bottom-color:var(--ac)}
.viewer{flex:1;overflow:auto}
.viewer pre{margin:0;font-size:13px;line-height:1.5}
.viewer pre code{padding:18px!important;display:block;background:#000!important}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;color:var(--mu);gap:10px;font-size:18px;letter-spacing:2px}
.chat{width:258px;background:var(--sf);border-left:2px solid var(--bd);
  display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.chat-hdr{padding:7px 12px;border-bottom:1px solid var(--bd);font-size:18px;
  color:var(--ac);letter-spacing:2px;display:flex;align-items:center;justify-content:space-between}
.chat-dot{width:7px;height:7px;border-radius:50%;background:var(--gr);
  box-shadow:0 0 5px var(--gr);animation:blP 1.5s step-end infinite}
.chat-msgs{flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:5px}
.msg{background:#000;border:1px solid var(--bd);padding:6px 8px}
.msg .usr{font-size:14px;color:var(--ac);letter-spacing:1px}
.msg .txt{font-size:14px;margin-top:2px;word-break:break-word;white-space:pre-wrap;color:var(--tx)}
.msg .ts{font-size:12px;color:var(--mu);margin-top:3px}
.chat-inp{padding:7px;border-top:1px solid var(--bd);display:flex;gap:5px}
.chat-inp textarea{flex:1;background:#000;border:1px solid var(--bd);
  padding:5px 7px;color:var(--ac);font-family:'VT323',monospace;font-size:16px;
  resize:none;height:52px;letter-spacing:1px;outline:none}
.chat-inp textarea:focus{border-color:var(--ac)}
.sbtn{background:transparent;border:1px solid var(--ac);color:var(--ac);
  font-family:'VT323',monospace;font-size:20px;padding:4px 10px;cursor:pointer}

/* ── CALL PANEL ── */
#call-panel{position:fixed;inset:0;z-index:7500;background:rgba(2,5,8,.97);
  display:none;flex-direction:column;overflow:hidden;border:1px solid #00ccff33}
.cp-header{background:#040c12;border-bottom:2px solid #00ccff28;
  padding:8px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0}
.cp-header h2{color:#00ccff;letter-spacing:4px;font-size:22px;text-shadow:0 0 14px rgba(0,204,255,.4)}
.cp-status{font-size:16px;letter-spacing:2px;color:var(--mu)}
.cp-status.live{color:var(--rd);animation:blP .7s step-end infinite}
.cp-status.conn{color:var(--gr)}
.cp-close{margin-left:auto;background:transparent;border:1px solid var(--rd);
  color:var(--rd);font-family:'VT323',monospace;font-size:18px;padding:2px 10px;cursor:pointer}
.cp-close:hover{background:rgba(255,58,42,.15)}
.cp-body{display:flex;flex:1;overflow:hidden;min-height:0}
.vgrid{flex:1;display:grid;gap:6px;padding:10px;
  grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
  align-content:start;overflow-y:auto;background:#020407}
.vgrid-empty{display:flex;align-items:center;justify-content:center;
  width:100%;height:100%;color:var(--mu);font-size:18px;letter-spacing:3px}
.vid-tile{position:relative;background:#000;border:2px solid #00ccff33;
  aspect-ratio:4/3;overflow:hidden}
.vid-tile video{width:100%;height:100%;object-fit:cover;filter:contrast(1.05) saturate(.85)}
.vid-tile::after{content:'';position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(to bottom,transparent 0,transparent 3px,
  rgba(0,0,0,.2) 3px,rgba(0,0,0,.2) 4px)}
.vlabel{position:absolute;bottom:5px;left:7px;font-size:16px;
  color:#00ccff;background:rgba(0,0,0,.75);padding:1px 8px;letter-spacing:2px}
.vlive{position:absolute;top:5px;right:7px;font-size:13px;
  color:var(--rd);animation:blP 1s step-end infinite}
.vid-tile.speaking{border-color:#00ccff99;box-shadow:0 0 20px rgba(0,204,255,.15)}
.cp-users{width:210px;background:#030b10;border-left:2px solid #00ccff18;
  display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.cpu-hdr{padding:8px 12px;border-bottom:1px solid #00ccff18;font-size:16px;
  color:#00ccff;letter-spacing:3px}
.cpu-list{flex:1;overflow-y:auto;padding:6px}
.cpu-user{display:flex;align-items:center;justify-content:space-between;
  padding:5px 7px;border-bottom:1px solid #0a1520;font-size:15px;gap:6px}
.uname{color:var(--tx);letter-spacing:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.udot{width:7px;height:7px;border-radius:50%;background:var(--gr);
  flex-shrink:0;box-shadow:0 0 5px var(--gr)}
.cpu-call-btn{background:transparent;border:1px solid #00ccff55;color:#00ccff;
  font-family:'VT323',monospace;font-size:14px;padding:1px 8px;cursor:pointer;
  letter-spacing:1px;flex-shrink:0;white-space:nowrap}
.cpu-call-btn:hover{background:rgba(0,204,255,.14);border-color:#00ccff}
.cpu-call-btn.self{opacity:.3;pointer-events:none;border-color:var(--mu);color:var(--mu)}
.cpu-call-btn.in-call{border-color:var(--rd);color:var(--rd)}
.cp-controls{background:#030b10;border-top:2px solid #00ccff18;
  padding:10px 20px;display:flex;align-items:center;justify-content:center;
  gap:14px;flex-shrink:0;position:relative}
.ctrl-btn{background:transparent;border:2px solid #00ccff44;color:#00ccff;
  font-family:'VT323',monospace;font-size:19px;padding:7px 16px;cursor:pointer;
  letter-spacing:2px;transition:all .2s;min-width:110px}
.ctrl-btn:hover{background:rgba(0,204,255,.1);border-color:#00ccff}
.ctrl-btn.off{border-color:#ff3a2a88;color:#ff3a2a;background:rgba(255,58,42,.07)}
.ctrl-btn.hangup{border-color:var(--rd);color:var(--rd)}
.ctrl-btn.hangup:hover{background:rgba(255,58,42,.18)}
#local-wrap{position:absolute;bottom:88px;right:14px;width:165px;z-index:7600;
  background:#000;border:2px solid #00ccff55;display:none}
#local-wrap video{width:100%;display:block;filter:contrast(1.05)}
#local-label{position:absolute;bottom:3px;left:5px;font-size:14px;
  color:#00ccff;background:rgba(0,0,0,.8);padding:1px 6px;letter-spacing:1px}
#call-toast{position:fixed;top:58px;left:50%;transform:translateX(-50%);z-index:9500;
  background:#040c12;border:2px solid var(--yw);padding:12px 22px;
  display:none;align-items:center;gap:14px;font-size:18px;letter-spacing:2px;
  box-shadow:0 0 28px rgba(255,204,0,.25)}
.ct-from{color:var(--yw)}
#call-toast button{font-family:'VT323',monospace;font-size:17px;padding:3px 12px;
  cursor:pointer;border:1px solid;letter-spacing:2px;background:transparent}
.ct-ans{border-color:var(--gr)!important;color:var(--gr)!important}
.ct-ans:hover{background:rgba(57,255,20,.12)!important}
.ct-dec{border-color:var(--rd)!important;color:var(--rd)!important}
.ct-dec:hover{background:rgba(255,58,42,.12)!important}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-thumb{background:var(--bd)}
</style>
</head>
<body>

<!-- VHS Layers -->
<canvas id="vhs-canvas"></canvas>
<div id="scanlines"></div>
<div id="chroma"></div>
<div id="tracking"></div>
<div id="glitch-flash"></div>
<div id="vhs-hud">
  <span class="hud-play">▶ PLAY</span>
  <span class="hud-mid" id="hud-sp">SP ◼◼◼◼◻</span>
  <div class="hud-right"><div id="hud-date">--/--/--</div><div id="hud-time">0:00:00</div></div>
</div>
<div id="tracking-msg">TRACKING...</div>
<div id="sub-text"></div>

<!-- FREQUENCY VISUALIZER (shown during speech) -->
<div id="freq-panel">
  <div class="fp-title">// EQ SIGNAL CHAIN — ANALOG FILTER</div>
  <canvas id="freq-canvas" width="300" height="80"></canvas>
  <div class="fp-labels">
    <span>20Hz</span><span>200Hz</span><span>400Hz</span>
    <span>2kHz</span><span>4kHz</span><span>20kHz</span>
  </div>
  <div class="fp-ambient">
    <div class="fp-amb-item"><div class="fp-amb-dot"></div>60Hz HUM</div>
    <div class="fp-amb-item"><div class="fp-amb-dot"></div>15.7kHz CRT</div>
  </div>
  <div class="fp-chain">
    HPF <span>200Hz</span> · BOOST <span>400–2kHz</span> · LPF <span>4kHz</span>
  </div>
</div>

<!-- INTRO (Analog Horror CRT TV style) -->
<div id="intro">
  <div class="crt-tv">
    <div class="tv-dot"></div>
    <div class="crt-screen" id="crt-screen">
      <div class="crt-ch">CH 03</div>
      <div class="crt-rec">● REC</div>
      <!-- Slide 1: BSI -->
      <div id="s1" class="slide active">
        <div class="ilabel" id="s1-top">IN PARTNERSHIP WITH</div>
        <img src="/static/bsi.jpeg" id="bsi-logo" class="hero-logo" alt="BSI">
        <div class="ilabel" id="s1-bot">BUNNY SMILES INCORPORATED</div>
      </div>
      <!-- Slide 2: CyberFun -->
      <div id="s2" class="slide">
        <div class="ilabel">CYBER FUN TECH PRESENTS...</div>
        <img src="/static/cyberfun.jpeg" id="cf-logo" class="hero-logo" alt="CyberFun Tech">
      </div>
      <!-- Slide 3: Warning -->
      <div id="s3" class="slide">
        <div class="ititle">THE CYBERFUNTECH SERVER!</div>
        <div style="height:14px"></div>
        <div class="iwarn">⚠ THIS SERVER CONTAINS CONFIDENTIAL FILES ⚠</div>
        <div class="isub" style="margin-top:10px">ONLY EMPLOYEES MAY ACCESS</div>
      </div>
      <div class="crt-vignette"></div>
    </div>
  </div>
</div>

<!-- LOGIN -->
<div id="login-screen">
  <div class="lbox">
    <div class="ltitle">
      <h1>EMPLOYEE LOGIN</h1>
      <p>⚠ AUTHORIZED PERSONNEL ONLY ⚠</p>
    </div>
    <div id="lerr" class="lerr"></div>
    <div class="field"><label>USER_ID:</label>
      <input id="lu" type="text" value="admin" autocomplete="username"></div>
    <div class="field"><label>PASSCODE:</label>
      <input id="lp" type="password" autocomplete="current-password"></div>
    <button class="lbtn" onclick="login()">[ AUTHENTICATE ]</button>
  </div>
</div>

<!-- APP -->
<div id="app">
  <div class="aheader">
    <span style="color:var(--ac)">▣</span>
    <h1>CYBERFUNTECH SRV</h1>
    <span style="color:var(--rd);font-size:15px;animation:blP 2s step-end infinite">■ SECURE</span>
    <input class="cinput" id="curl" readonly value="..." onclick="this.select()">
    <button class="hbtn" onclick="syncWS()">↺ SYNC</button>
    <button class="hbtn call-btn" id="call-toggle-btn" onclick="toggleCallPanel()">📡 TRANSMIT</button>
    <button class="hbtn danger" onclick="logout()">EXIT</button>
  </div>
  <div class="layout">
    <div class="sb">
      <div class="sb-tabs">
        <div class="sb-tab on" onclick="sTab('f',this)">FILES</div>
        <div class="sb-tab"   onclick="sTab('c',this)">LOG</div>
      </div>
      <div class="sb-body" id="sf"><div id="tree" style="color:var(--mu)">LOADING...</div></div>
      <div class="sb-body" id="sc" style="display:none"><div id="clist" style="color:var(--mu)">LOADING...</div></div>
    </div>
    <div class="main">
      <div class="m-tabs"><div class="m-tab on">VIEWER</div></div>
      <div class="viewer" id="vp">
        <div class="empty"><div style="font-size:40px;opacity:.25">▣</div>SELECT A FILE TO VIEW</div>
      </div>
    </div>
    <div class="chat">
      <div class="chat-hdr">
        <span>// COMMS</span>
        <div class="chat-dot" id="chat-dot" style="opacity:0"></div>
      </div>
      <div class="chat-msgs" id="cm"></div>
      <div class="chat-inp">
        <textarea id="ci" placeholder="MSG..." onkeydown="ck(event)"></textarea>
        <button class="sbtn" onclick="send()">TX</button>
      </div>
    </div>
  </div>
</div>

<!-- CALL PANEL -->
<div id="call-panel">
  <div class="cp-header">
    <span style="color:#00ccff;font-size:22px">◈</span>
    <h2>// TRANSMISSION CHANNEL</h2>
    <span class="cp-status" id="cp-status">STANDBY</span>
    <button class="cp-close" onclick="closeCallPanel()">✕ CLOSE</button>
  </div>
  <div class="cp-body">
    <div class="vgrid" id="vgrid">
      <div class="vgrid-empty">// NO ACTIVE TRANSMISSIONS</div>
    </div>
    <div class="cp-users">
      <div class="cpu-hdr">// PERSONNEL</div>
      <div class="cpu-list" id="cpu-list"><span style="color:var(--mu)">SCANNING...</span></div>
    </div>
  </div>
  <div class="cp-controls">
    <button class="ctrl-btn" id="btn-mic"  onclick="toggleMic()">🎤 MIC ON</button>
    <button class="ctrl-btn" id="btn-cam"  onclick="toggleCam()">📷 CAM ON</button>
    <button class="ctrl-btn hangup"        onclick="hangupAll()">☎ HANG UP</button>
  </div>
</div>

<!-- Local video PiP -->
<div id="local-wrap">
  <video id="local-video" autoplay muted playsinline></video>
  <div id="local-label">YOU</div>
</div>

<!-- Incoming call toast -->
<div id="call-toast">
  <span>📡 INCOMING:</span>
  <span class="ct-from" id="ct-from">---</span>
  <button class="ct-ans" onclick="answerCall()">[ ACCEPT ]</button>
  <button class="ct-dec" onclick="declineCall()">[ DECLINE ]</button>
</div>

<script>
// ─── VHS Noise ───────────────────────────────────────────────────────────────
const nc=document.getElementById('vhs-canvas'),nctx=nc.getContext('2d');
function renderNoise(){
  nc.width=window.innerWidth;nc.height=window.innerHeight;
  const img=nctx.createImageData(nc.width,nc.height);
  for(let i=0;i<img.data.length;i+=4){
    const v=Math.random()>.97?(Math.random()*200|0):0;
    img.data[i]=v;img.data[i+1]=v;img.data[i+2]=v;img.data[i+3]=v?180:0;
  }
  nctx.putImageData(img,0,0);requestAnimationFrame(renderNoise);
}
renderNoise();

// ─── HUD clock ───────────────────────────────────────────────────────────────
let elapsed=0;
setInterval(()=>{
  elapsed++;
  const h=String(Math.floor(elapsed/3600)).padStart(1,'0');
  const m=String(Math.floor(elapsed%3600/60)).padStart(2,'0');
  const s=String(elapsed%60).padStart(2,'0');
  document.getElementById('hud-time').textContent=`${h}:${m}:${s}`;
  const now=new Date();
  document.getElementById('hud-date').textContent=
    `${String(now.getMonth()+1).padStart(2,'0')}/${String(now.getDate()).padStart(2,'0')}/${String(now.getFullYear()).slice(-2)}`;
},1000);

function setSub(t){document.getElementById('sub-text').textContent=t;}
function glitchFlash(cb){
  const f=document.getElementById('glitch-flash');
  let i=0;const steps=[1,.1,.85,.05,.7,0,.95,0];
  (function step(){if(i>=steps.length){f.style.opacity=0;cb&&cb();return;}
    f.style.opacity=steps[i++];setTimeout(step,55);}
  )();
}

// ─── Analog Horror Audio (Web Audio API) ─────────────────────────────────────
const AHAudio=(()=>{
  let ctx=null,humNode=null,crtNode=null,started=false;
  function init(){
    if(started)return;started=true;
    try{
      ctx=new(window.AudioContext||window.webkitAudioContext)();
      // 60Hz electrical hum (sawtooth for richer harmonics)
      humNode=ctx.createOscillator();
      humNode.type='sawtooth';humNode.frequency.value=60;
      const humGain=ctx.createGain();humGain.gain.value=0.018;
      const humLPF=ctx.createBiquadFilter();
      humLPF.type='lowpass';humLPF.frequency.value=280;humLPF.Q.value=1.2;
      humNode.connect(humLPF).connect(humGain).connect(ctx.destination);
      humNode.start();
      // 15734 Hz CRT whine (TV horizontal scan rate)
      crtNode=ctx.createOscillator();
      crtNode.type='sine';crtNode.frequency.value=15734;
      const crtGain=ctx.createGain();crtGain.gain.value=0.0045;
      crtNode.connect(crtGain).connect(ctx.destination);
      crtNode.start();
    }catch(e){console.warn('AHAudio init failed:',e);}
  }
  return{
    start(){if(ctx&&ctx.state==='suspended')ctx.resume();else if(!started)init();},
    resume(){if(ctx&&ctx.state==='suspended')ctx.resume();}
  };
})();

// ─── Frequency Visualizer Canvas ─────────────────────────────────────────────
const FreqViz=(()=>{
  const panel=document.getElementById('freq-panel');
  const canvas=document.getElementById('freq-canvas');
  const ctx=canvas.getContext('2d');
  let raf=null,speaking=false;
  const W=300,H=80;

  // Frequency axis: map Hz to X position (log scale)
  function freqToX(hz){
    const lo=Math.log10(20),hi=Math.log10(22000);
    return ((Math.log10(hz)-lo)/(hi-lo))*W;
  }

  // EQ curve: gain in dB for each frequency
  function eqGain(hz){
    if(hz<200) return -30;           // HPF: hard cut below 200Hz
    if(hz<400) return -8+(hz-200)/200*8;  // slope up to 400Hz
    if(hz<=2000) return 5;           // boost 400-2000Hz
    if(hz<4000) return 5-(hz-2000)/2000*35; // slope down
    return -30;                      // LPF: hard cut above 4000Hz
  }

  function drawFrame(t){
    ctx.clearRect(0,0,W,H);
    // Background
    ctx.fillStyle='#010801';
    ctx.fillRect(0,0,W,H);

    // Grid lines
    ctx.strokeStyle='rgba(57,255,20,.08)';
    ctx.lineWidth=1;
    [200,400,2000,4000].forEach(hz=>{
      const x=freqToX(hz);
      ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();
    });

    // EQ curve fill
    ctx.beginPath();
    for(let x=0;x<W;x++){
      const pct=x/W;
      const hz=Math.pow(10,Math.log10(20)+pct*(Math.log10(22000)-Math.log10(20)));
      const db=eqGain(hz);
      const y=H/2 - (db/35)*H*0.45;
      x===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }
    ctx.lineTo(W,H);ctx.lineTo(0,H);ctx.closePath();
    ctx.fillStyle='rgba(57,255,20,.12)';ctx.fill();

    // EQ curve line
    ctx.beginPath();ctx.lineWidth=1.5;
    const grad=ctx.createLinearGradient(0,0,W,0);
    grad.addColorStop(0,'rgba(57,255,20,.2)');
    grad.addColorStop(freqToX(400)/W,'rgba(57,255,20,.9)');
    grad.addColorStop(freqToX(2000)/W,'rgba(57,255,20,.9)');
    grad.addColorStop(1,'rgba(57,255,20,.2)');
    ctx.strokeStyle=grad;
    for(let x=0;x<=W;x++){
      const pct=x/W;
      const hz=Math.pow(10,Math.log10(20)+pct*(Math.log10(22000)-Math.log10(20)));
      const db=eqGain(hz);
      const y=H/2-(db/35)*H*0.45;
      x===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }
    ctx.stroke();

    // Animated signal bars when speaking
    if(speaking){
      const numBars=28;
      for(let i=0;i<numBars;i++){
        const pct=i/numBars;
        const hz=Math.pow(10,Math.log10(20)+pct*(Math.log10(22000)-Math.log10(20)));
        const db=eqGain(hz);
        const baseH=Math.max(0,(db+30)/65*H*.6);
        const noise=(Math.random()-.3)*baseH*.6;
        const bh=Math.max(1,baseH+noise);
        const bx=freqToX(hz);
        const alpha=(hz>=300&&hz<=3500)?0.7:0.2;
        ctx.fillStyle=`rgba(57,255,20,${alpha})`;
        ctx.fillRect(bx-3,H-bh,5,bh);
      }
      // 60Hz marker
      const hx=freqToX(60);
      ctx.fillStyle='rgba(255,200,0,.6)';ctx.fillRect(hx-1,H-8,2,8);
    }

    // Filter cutoff markers
    ctx.lineWidth=1;ctx.setLineDash([3,3]);
    ctx.strokeStyle='rgba(57,255,20,.35)';
    ctx.beginPath();ctx.moveTo(freqToX(200),0);ctx.lineTo(freqToX(200),H);ctx.stroke();
    ctx.beginPath();ctx.moveTo(freqToX(4000),0);ctx.lineTo(freqToX(4000),H);ctx.stroke();
    ctx.setLineDash([]);
    // center line
    ctx.strokeStyle='rgba(57,255,20,.07)';
    ctx.beginPath();ctx.moveTo(0,H/2);ctx.lineTo(W,H/2);ctx.stroke();

    if(raf)raf=requestAnimationFrame(drawFrame);
  }

  return{
    show(){panel.style.display='block';speaking=true;raf=1;drawFrame(0);},
    hide(){speaking=false;panel.style.display='none';raf=null;}
  };
})();

// ─── Robot voice (analog horror EQ style) ────────────────────────────────────
function robotSpeak(text,onEnd){
  AHAudio.start();
  FreqViz.show();
  if(!window.speechSynthesis){FreqViz.hide();onEnd&&onEnd();return;}
  window.speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(text);
  u.pitch=0.06;u.rate=0.68;u.volume=0.92;
  const voices=window.speechSynthesis.getVoices();
  const pick=voices.find(v=>/David|UK English Male|Fred|Alex|Daniel/i.test(v.name))
    ||voices.find(v=>v.lang.startsWith('en'))||voices[0];
  if(pick)u.voice=pick;
  u.onend=()=>{FreqViz.hide();onEnd&&onEnd();};
  u.onerror=()=>{FreqViz.hide();onEnd&&onEnd();};
  window.speechSynthesis.speak(u);
}

// ─── Intro sequence ───────────────────────────────────────────────────────────
function showSlide(id){document.querySelectorAll('.slide').forEach(s=>s.classList.remove('active'));document.getElementById(id).classList.add('active');}
function startIntro(){setTimeout(slide1,600);}
function slide1(){
  showSlide('s1');
  const bsi=document.getElementById('bsi-logo');
  bsi.classList.remove('logo-enter');void bsi.offsetWidth;bsi.classList.add('logo-enter');
  ['s1-top','s1-bot'].forEach((id,i)=>{
    const el=document.getElementById(id);el.style.opacity='0';
    setTimeout(()=>{el.style.transition='opacity 1s';el.style.opacity='1';},500+i*900);
  });
  setSub('[CH-03]  TAPE-01  //  BSI × CYBERFUNTECH');
  robotSpeak("In partnership with... Bunny Smiles Incorporated.",()=>setTimeout(slide2,700));
  setTimeout(()=>{if(!document.getElementById('s2').classList.contains('active'))slide2();},9000);
}
function slide2(){
  glitchFlash(()=>{
    showSlide('s2');
    const cf=document.getElementById('cf-logo');
    cf.classList.remove('logo-enter');void cf.offsetWidth;cf.classList.add('logo-enter');
    setSub('[CH-03]  CYBERFUNTECH PRESENTS');
    robotSpeak("Cyber Fun Tech... presents...",()=>setTimeout(slide3,800));
    setTimeout(()=>{if(!document.getElementById('s3').classList.contains('active'))slide3();},8000);
  });
}
function slide3(){
  glitchFlash(()=>{
    showSlide('s3');setSub('[WARNING] — RESTRICTED ACCESS SYSTEM');
    robotSpeak("The CyberFunTech Server. This server contains confidential files. Only authorized employees may access.",()=>setTimeout(endIntro,2000));
    setTimeout(()=>{if(document.getElementById('intro').style.display==='none')return;endIntro();},12000);
  });
}
function endIntro(){
  glitchFlash(()=>{document.getElementById('intro').style.display='none';setSub('');checkSession();});
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
const st={user:null,path:'',file:null};
async function checkSession(){
  const r=await get('/api/me');
  if(r&&r.user){st.user=r.user;document.getElementById('login-screen').style.display='none';showApp();}
  else{document.getElementById('login-screen').style.display='flex';}
}
async function login(){
  const u=q('lu').value.trim(),p=q('lp').value,e=q('lerr');e.textContent='';
  AHAudio.resume();
  const r=await post('/login',{user:u,pass:p});
  if(r&&r.ok){st.user=r.user;document.getElementById('login-screen').style.display='none';showApp();}
  else e.textContent='[ ACCESS DENIED — INVALID CREDENTIALS ]';
}
async function logout(){await post('/logout',{});location.reload();}
q('lp').onkeydown=e=>e.key==='Enter'&&login();

// ─── App ──────────────────────────────────────────────────────────────────────
function showApp(){
  document.getElementById('app').style.display='flex';
  q('curl').value=`git clone http://${location.host}/repo.git`;
  loadFiles('');loadCommits();loadChat();
  setInterval(loadChat,2000);
  startPresence();
  startSignalPoll();
}

// ─── Files ───────────────────────────────────────────────────────────────────
async function loadFiles(path){
  st.path=path;const t=q('tree');t.innerHTML='<span style="color:var(--mu)">LOADING...</span>';
  const d=await get(`/api/files?path=${enc(path)}`);
  if(!d||d.error){t.innerHTML=`<span style="color:var(--rd)">${d?.error||'ERROR'}</span>`;return;}
  let h='';
  if(path){const par=path.split('/').slice(0,-1).join('/');h+=`<div class="back" onclick="loadFiles('${esc(par)}')">&lt; ..</div>`;}
  for(const it of d.items){
    const fp=path?`${path}/${it.name}`:it.name;
    const ic=it.type==='dir'?'▸':'▪';
    const oc=it.type==='dir'?`loadFiles('${esc(fp)}')`:`openFile('${esc(fp)}',this)`;
    const sz=it.size!=null?`<span style="color:var(--mu);font-size:12px;margin-left:auto">${fmt(it.size)}</span>`:'';
    h+=`<div class="ti" onclick="${oc}"><span style="color:var(--ac)">${ic}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis">${xss(it.name)}</span>${sz}</div>`;
  }
  t.innerHTML=h||'<span style="color:var(--mu)">EMPTY</span>';
}
async function openFile(path,el){
  document.querySelectorAll('.ti').forEach(e=>e.classList.remove('sel'));el.classList.add('sel');st.file=path;
  const vp=q('vp');vp.innerHTML='<div class="empty">LOADING...</div>';
  const d=await get(`/api/file?path=${enc(path)}`);
  if(!d||d.error){vp.innerHTML=`<div class="empty" style="color:var(--rd)">${xss(d?.error||'ERROR')}</div>`;return;}
  const escaped=d.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  vp.innerHTML=`<pre><code class="language-${d.ext||'plaintext'}">${escaped}</code></pre>`;
  hljs.highlightElement(vp.querySelector('code'));
}
async function loadCommits(){
  const cl=q('clist');const d=await get('/api/commits');
  if(!d?.commits?.length){cl.innerHTML='<span style="color:var(--mu)">NO COMMITS</span>';return;}
  cl.innerHTML=d.commits.map(c=>`<div class="cm-i"><div class="hsh">${c.hash}</div><div class="ms">${xss(c.msg)}</div><div class="mt">${xss(c.author)} · ${c.rel}</div></div>`).join('');
}

// ─── Chat ─────────────────────────────────────────────────────────────────────
let _lastMsgCount=0;
async function loadChat(){
  const d=await get('/api/chat');const box=q('cm');
  if(!d?.messages)return;
  const atBottom=box.scrollHeight-box.scrollTop-box.clientHeight<80;
  const count=d.messages.length;
  if(count>_lastMsgCount&&_lastMsgCount>0){
    const dot=q('chat-dot');dot.style.opacity='1';
    setTimeout(()=>dot.style.opacity='0',1500);
  }
  _lastMsgCount=count;
  if(!count){box.innerHTML='<span style="color:var(--mu);font-size:14px">NO TRANSMISSIONS</span>';return;}
  box.innerHTML=d.messages.map(m=>`<div class="msg"><div class="usr">&gt; ${xss(m.user)}</div><div class="txt">${xss(m.text)}</div><div class="ts">${m.ts}</div></div>`).join('');
  if(atBottom)box.scrollTop=box.scrollHeight;
}
async function send(){
  const inp=q('ci'),txt=inp.value.trim();if(!txt)return;inp.value='';
  await post('/api/chat',{text:txt});await loadChat();
}
function ck(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}
async function syncWS(){await post('/api/sync',{});loadFiles(st.path);loadCommits();}
function sTab(n,el){document.querySelectorAll('.sb-tab').forEach(e=>e.classList.remove('on'));el.classList.add('on');q('sf').style.display=n==='f'?'':'none';q('sc').style.display=n==='c'?'':'none';}

// ═══════════════════════════════════════════════════════════
// ─── WebRTC Video/Audio Calling ──────────────────────────
// ═══════════════════════════════════════════════════════════
const ICE_CFG={iceServers:[
  {urls:'stun:stun.l.google.com:19302'},
  {urls:'stun:stun1.l.google.com:19302'},
  {urls:'stun:stun2.l.google.com:19302'},
  {urls:'stun:stun.cloudflare.com:3478'}
]};

let localStream=null,peerConns={},pendingCandidates={},pendingOffer=null,callPanelOpen=false;
let micOn=true,camOn=true,_signalPollActive=false;

// ─── Presence ────────────────────────────────────────────
function startPresence(){
  const beat=async()=>{await post('/api/presence',{});if(callPanelOpen)updateUserList();};
  beat();setInterval(beat,8000);
}
async function updateUserList(){
  const d=await get('/api/users');if(!d)return;
  const list=q('cpu-list');if(!list)return;
  const users=d.users||[];
  if(!users.length){list.innerHTML='<span style="color:var(--mu)">NO PERSONNEL ONLINE</span>';return;}
  list.innerHTML=users.map(u=>{
    const isMe=u===st.user;
    const inCall=!!peerConns[u];
    let cls='',lbl='',fn='';
    if(isMe){cls='self';lbl='YOU';fn='';}
    else if(inCall){cls='in-call';lbl='HANG UP';fn=`hangupUser('${esc(u)}')`;} 
    else{lbl='CALL';fn=`callUser('${esc(u)}')`;}
    return `<div class="cpu-user"><span class="udot"></span><span class="uname">${xss(u)}</span><button class="cpu-call-btn ${cls}" onclick="${fn}">${lbl}</button></div>`;
  }).join('');
}

// ─── Panel ───────────────────────────────────────────────
async function toggleCallPanel(){
  if(callPanelOpen)closeCallPanel();else await openCallPanel();
}
async function openCallPanel(){
  callPanelOpen=true;
  q('call-panel').style.display='flex';
  q('call-toggle-btn').classList.add('active');
  setCallStatus('STANDBY','');
  updateUserList();
  // Remove empty placeholder
  const grid=q('vgrid');
  if(grid.querySelector('.vgrid-empty'))grid.innerHTML='';
  try{
    localStream=await navigator.mediaDevices.getUserMedia({video:true,audio:true});
    q('local-video').srcObject=localStream;q('local-wrap').style.display='block';
    micOn=true;camOn=true;updateMediaBtns();
  }catch(e){
    try{
      localStream=await navigator.mediaDevices.getUserMedia({video:false,audio:true});
      q('local-wrap').style.display='none';camOn=false;updateMediaBtns();
    }catch(e2){setCallStatus('NO MEDIA ACCESS','');}
  }
}
function closeCallPanel(){
  callPanelOpen=false;
  q('call-panel').style.display='none';
  q('call-toggle-btn').classList.remove('active');
  q('local-wrap').style.display='none';
  if(localStream){localStream.getTracks().forEach(t=>t.stop());localStream=null;}
  hangupAll();
}
function setCallStatus(txt,cls){
  const el=q('cp-status');el.textContent=txt;el.className='cp-status'+(cls?' '+cls:'');
}

// ─── Media controls ───────────────────────────────────────
function toggleMic(){
  if(!localStream)return;micOn=!micOn;
  localStream.getAudioTracks().forEach(t=>t.enabled=micOn);
  // Update all peer connections
  Object.values(peerConns).forEach(pc=>{
    pc.getSenders().filter(s=>s.track?.kind==='audio').forEach(s=>{if(s.track)s.track.enabled=micOn;});
  });
  updateMediaBtns();
}
function toggleCam(){
  if(!localStream)return;camOn=!camOn;
  localStream.getVideoTracks().forEach(t=>t.enabled=camOn);
  updateMediaBtns();
}
function updateMediaBtns(){
  const bm=q('btn-mic'),bc=q('btn-cam');
  bm.textContent=micOn?'🎤 MIC ON':'🔇 MUTED';bm.className='ctrl-btn'+(micOn?'':' off');
  bc.textContent=camOn?'📷 CAM ON':'📷 CAM OFF';bc.className='ctrl-btn'+(camOn?'':' off');
}

// ─── Call user ────────────────────────────────────────────
async function callUser(target){
  if(peerConns[target])return;
  if(!callPanelOpen)await openCallPanel();
  await sleep(200);
  if(!localStream){setCallStatus('NO MEDIA','');return;}
  setCallStatus('CALLING '+target.toUpperCase(),'live');
  const pc=createPC(target);peerConns[target]=pc;
  localStream.getTracks().forEach(t=>pc.addTrack(t,localStream));
  const offer=await pc.createOffer({offerToReceiveAudio:true,offerToReceiveVideo:true});
  await pc.setLocalDescription(offer);
  await post('/api/signal/send',{to:target,msg:{type:'offer',sdp:{type:pc.localDescription.type,sdp:pc.localDescription.sdp},from:st.user}});
  updateUserList();
}

// ─── Hang up ──────────────────────────────────────────────
async function hangupUser(target){
  await post('/api/signal/send',{to:target,msg:{type:'hangup',from:st.user}});
  closePeer(target);
}
function hangupAll(){
  Object.keys(peerConns).forEach(u=>hangupUser(u));
}

// ─── Peer connection ──────────────────────────────────────
function createPC(target){
  const pc=new RTCPeerConnection(ICE_CFG);
  pc.onicecandidate=e=>{
    if(e.candidate){
      post('/api/signal/send',{to:target,msg:{type:'candidate',candidate:{candidate:e.candidate.candidate,sdpMid:e.candidate.sdpMid,sdpMLineIndex:e.candidate.sdpMLineIndex},from:st.user}});
    }
  };
  pc.ontrack=e=>{
    if(e.streams&&e.streams[0])addRemoteVideo(target,e.streams[0]);
  };
  pc.onconnectionstatechange=()=>{
    const s=pc.connectionState;
    if(s==='connected'){setCallStatus('CONNECTED: '+target.toUpperCase(),'conn');}
    else if(['disconnected','failed','closed'].includes(s)){closePeer(target);}
  };
  pc.oniceconnectionstatechange=()=>{
    if(pc.iceConnectionState==='failed'){pc.restartIce&&pc.restartIce();}
  };
  return pc;
}
function closePeer(target){
  if(peerConns[target]){peerConns[target].close();delete peerConns[target];}
  delete pendingCandidates[target];
  removeRemoteVideo(target);
  updateUserList();
  if(!Object.keys(peerConns).length)setCallStatus('STANDBY','');
}

// ─── Remote video ─────────────────────────────────────────
function addRemoteVideo(user,stream){
  const grid=q('vgrid');
  const emp=grid.querySelector('.vgrid-empty');if(emp)emp.remove();
  let tile=document.getElementById('vtile-'+user);
  if(!tile){
    tile=document.createElement('div');tile.className='vid-tile';tile.id='vtile-'+user;
    tile.innerHTML=`<video autoplay playsinline></video><div class="vlabel">${xss(user)}</div><div class="vlive">● LIVE</div>`;
    grid.appendChild(tile);
  }
  const vid=tile.querySelector('video');vid.srcObject=stream;
  // Audio level detection for "speaking" highlight
  try{
    const ac=new AudioContext(),src=ac.createMediaStreamSource(stream);
    const analyser=ac.createAnalyser();analyser.fftSize=256;src.connect(analyser);
    const buf=new Uint8Array(analyser.frequencyBinCount);
    (function check(){
      analyser.getByteFrequencyData(buf);
      const avg=buf.reduce((a,b)=>a+b,0)/buf.length;
      tile.classList.toggle('speaking',avg>10);
      if(document.getElementById('vtile-'+user))requestAnimationFrame(check);
      else ac.close();
    })();
  }catch(e){}
  setCallStatus('CONNECTED: '+user.toUpperCase(),'conn');
  updateUserList();
}
function removeRemoteVideo(user){
  const tile=document.getElementById('vtile-'+user);if(tile)tile.remove();
  const grid=q('vgrid');
  if(!grid.querySelector('.vid-tile'))grid.innerHTML='<div class="vgrid-empty">// NO ACTIVE TRANSMISSIONS</div>';
}

// ─── Signaling ────────────────────────────────────────────
async function startSignalPoll(){
  _signalPollActive=true;
  while(_signalPollActive){
    try{
      const d=await get('/api/signal/poll');
      if(d?.messages){for(const m of d.messages)await handleSignal(m);}
    }catch(e){}
    await sleep(700);
  }
}

async function handleSignal(msg){
  const{type,from,sdp,candidate}=msg;
  if(type==='offer'){
    // Queue candidates that might arrive before we answer
    if(!pendingCandidates[from])pendingCandidates[from]=[];
    pendingOffer=msg;
    q('ct-from').textContent=from.toUpperCase();
    q('call-toast').style.display='flex';
    setTimeout(()=>{if(pendingOffer===msg){pendingOffer=null;q('call-toast').style.display='none';}},30000);
  }
  else if(type==='answer'){
    const pc=peerConns[from];if(!pc)return;
    try{
      await pc.setRemoteDescription(new RTCSessionDescription(sdp));
      // Flush queued candidates
      const queued=pendingCandidates[from]||[];delete pendingCandidates[from];
      for(const c of queued){try{await pc.addIceCandidate(new RTCIceCandidate(c));}catch(e){}}
    }catch(e){console.warn('setRemoteDescription (answer) failed:',e);}
  }
  else if(type==='candidate'){
    const pc=peerConns[from];
    if(!pc||!pc.remoteDescription){
      if(!pendingCandidates[from])pendingCandidates[from]=[];
      pendingCandidates[from].push(candidate);
    }else{
      try{await pc.addIceCandidate(new RTCIceCandidate(candidate));}catch(e){}
    }
  }
  else if(type==='hangup'){closePeer(from);}
}

async function answerCall(){
  q('call-toast').style.display='none';
  const offer=pendingOffer;pendingOffer=null;if(!offer)return;
  if(!callPanelOpen)await openCallPanel();
  await sleep(300);
  if(!localStream){setCallStatus('NO MEDIA','');return;}
  const pc=createPC(offer.from);peerConns[offer.from]=pc;
  localStream.getTracks().forEach(t=>pc.addTrack(t,localStream));
  try{
    await pc.setRemoteDescription(new RTCSessionDescription(offer.sdp));
    // Flush any candidates that arrived before we answered
    const queued=pendingCandidates[offer.from]||[];delete pendingCandidates[offer.from];
    for(const c of queued){try{await pc.addIceCandidate(new RTCIceCandidate(c));}catch(e){}}
    const answer=await pc.createAnswer();
    await pc.setLocalDescription(answer);
    await post('/api/signal/send',{to:offer.from,msg:{type:'answer',sdp:{type:pc.localDescription.type,sdp:pc.localDescription.sdp},from:st.user}});
    updateUserList();
  }catch(e){console.error('answerCall error:',e);closePeer(offer.from);}
}
function declineCall(){
  q('call-toast').style.display='none';
  if(pendingOffer)post('/api/signal/send',{to:pendingOffer.from,msg:{type:'hangup',from:st.user}});
  pendingOffer=null;
}

// ─── Helpers ─────────────────────────────────────────────
function q(id){return document.getElementById(id);}
function enc(s){return encodeURIComponent(s);}
function esc(s){return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'");}
function xss(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmt(b){return b<1024?b+' B':b<1048576?(b/1024).toFixed(1)+' KB':(b/1048576).toFixed(1)+' MB';}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
async function get(url){try{const r=await fetch(url);if(!r.ok)return null;return r.json();}catch{return null;}}
async function post(url,data){try{const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!r.ok)return{};return r.json();}catch{return{};}}

// Preload voices for speech synthesis
if(window.speechSynthesis)window.speechSynthesis.getVoices();
window.addEventListener('load',()=>setTimeout(startIntro,600));
</script>
</body>
</html>"""

# ── Handler ───────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    _rate   = RateLimiter()
    _sess   = Sessions(_SK)
    _chat   = Chat()
    _signal = Signaling()
    _pres   = Presence()

    def do_GET(self):  self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_HEAD(self): self._dispatch("HEAD")

    def _dispatch(self, method):
        if not self._rate.allowed(self.client_address[0]):
            return self._raw(429,"text/plain",b"Too Many Requests\n")
        parsed=urlparse(self.path); path=parsed.path

        if path.startswith("/repo.git"):
            self._git(method,parsed)
        elif path.startswith("/static/") and method in ("GET","HEAD"):
            self._static(path)
        elif path in ("/","/ui") and method in ("GET","HEAD"):
            self._page(method)
        elif path=="/login" and method=="POST":
            self._login()
        elif path=="/logout" and method=="POST":
            self._logout()
        elif path.startswith("/api/"):
            user=self._auth_sess()
            if not user: return self._json(401,{"error":"Unauthorized"})
            self._api(method,path,parsed.query,user)
        else:
            self._raw(404,"text/plain",b"Not Found\n")

    def _static(self,path):
        p=safe_path(STATIC,path[len("/static/"):])
        if p is None or not p.is_file(): return self._raw(404,"text/plain",b"Not Found\n")
        mime,_=mimetypes.guess_type(str(p)); mime=mime or "application/octet-stream"
        data=p.read_bytes()
        self.send_response(200); self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","public, max-age=86400")
        self.end_headers()
        if self.command!="HEAD": self.wfile.write(data)

    def _git(self,method,parsed):
        auth=self.headers.get("Authorization",""); ok=False
        if auth.startswith("Basic "):
            try:
                dec=base64.b64decode(auth[6:]).decode(); u,pw=dec.split(":",1)
                ok=hmac.compare_digest(u,GIT_USER) and hmac.compare_digest(pw,GIT_PASS)
            except: pass
        if not ok:
            self.send_response(401)
            self.send_header("WWW-Authenticate",'Basic realm="Git Server"')
            self.send_header("Content-Length","0"); self.end_headers(); return
        env=os.environ.copy()
        env.update({"GIT_PROJECT_ROOT":str(BASE_DIR),"GIT_HTTP_EXPORT_ALL":"1",
                    "PATH_INFO":parsed.path,"REQUEST_METHOD":method,
                    "QUERY_STRING":parsed.query or "","CONTENT_TYPE":self.headers.get("Content-Type",""),
                    "HTTP_GIT_PROTOCOL":self.headers.get("Git-Protocol",""),
                    "SERVER_PROTOCOL":"HTTP/1.1","SERVER_NAME":"0.0.0.0","SERVER_PORT":str(PORT),
                    "CONTENT_LENGTH":self.headers.get("Content-Length","0")})
        cl=env["CONTENT_LENGTH"]
        body=self.rfile.read(int(cl)) if method=="POST" and cl.isdigit() and int(cl)>0 else b""
        proc=subprocess.Popen(["git","http-backend"],env=env,
                              stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        out,err=proc.communicate(input=body)
        if err: sys.stderr.write(f"[git] {err.decode(errors='replace')}\n")
        sep=b"\r\n\r\n" if b"\r\n\r\n" in out else b"\n\n" if b"\n\n" in out else None
        if not sep: return self._raw(502,"text/plain",b"Bad Gateway\n")
        hdr_raw,_,rbody=out.partition(sep)
        code,headers=200,[]
        for line in hdr_raw.decode(errors="replace").splitlines():
            if line.lower().startswith("status:"):
                try: code=int(line.split(":",1)[1].strip().split()[0])
                except: pass
            elif ":" in line:
                k,_,v=line.partition(":"); headers.append((k.strip(),v.strip()))
        self.send_response(code)
        for k,v in headers: self.send_header(k,v)
        self.end_headers(); self.wfile.write(rbody)

    def _page(self,method="GET"):
        body=_HTML.encode()
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("X-Frame-Options","SAMEORIGIN")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy",
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "fonts.googleapis.com fonts.gstatic.com cdnjs.cloudflare.com; "
            "img-src 'self' data:; media-src 'self' blob:; "
            "connect-src 'self'")
        self.end_headers()
        if method!="HEAD": self.wfile.write(body)

    def _login(self):
        data=self._read_json()
        if not data: return self._json(400,{"error":"Bad request"})
        u,pw=data.get("user","").strip(),data.get("pass","")
        if hmac.compare_digest(u,GIT_USER) and hmac.compare_digest(pw,GIT_PASS):
            cookie=self._sess.create(u); body=json.dumps({"ok":True,"user":u}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Set-Cookie",f"gs_sess={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400")
            self.end_headers(); self.wfile.write(body)
        else:
            time.sleep(0.6); self._json(401,{"ok":False,"error":"Access denied"})

    def _logout(self):
        self._sess.delete(self._cookie("gs_sess")); body=b'{"ok":true}'
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Set-Cookie","gs_sess=; Path=/; HttpOnly; Max-Age=0")
        self.end_headers(); self.wfile.write(body)

    def _api(self,method,path,query,user):
        qs=parse_qs(query)
        if path=="/api/me":
            return self._json(200,{"user":user})
        if path=="/api/files" and method=="GET":
            if not WORKSPACE.exists():
                threading.Thread(target=refresh_workspace,daemon=True).start()
                return self._json(200,{"items":[]})
            rel=qs.get("path",[""])[0]; p=safe_path(WORKSPACE,rel)
            if p is None or not p.exists(): return self._json(400,{"error":"Invalid path"})
            return self._json(200,list_dir(p))
        if path=="/api/file" and method=="GET":
            rel=qs.get("path",[""])[0]; p=safe_path(WORKSPACE,rel)
            if p is None or not p.is_file(): return self._json(404,{"error":"Not found"})
            return self._json(200,read_file(p))
        if path=="/api/commits" and method=="GET":
            return self._json(200,{"commits":git_log()})
        if path=="/api/chat" and method=="GET":
            return self._json(200,{"messages":self._chat.all()})
        if path=="/api/chat" and method=="POST":
            data=self._read_json()
            if not data or not str(data.get("text","")).strip(): return self._json(400,{"error":"Empty"})
            return self._json(200,self._chat.post(user,data["text"].strip()))
        if path=="/api/sync" and method=="POST":
            threading.Thread(target=refresh_workspace,daemon=True).start()
            return self._json(200,{"ok":True})
        if path=="/api/presence" and method=="POST":
            self._pres.beat(user); return self._json(200,{"ok":True})
        if path=="/api/users" and method=="GET":
            return self._json(200,{"users":self._pres.online()})
        if path=="/api/signal/poll" and method=="GET":
            return self._json(200,{"messages":self._signal.poll(user)})
        if path=="/api/signal/send" and method=="POST":
            data=self._read_json()
            if not data: return self._json(400,{"error":"Bad request"})
            to=data.get("to","").strip(); msg=data.get("msg",{})
            if not to or not isinstance(msg,dict): return self._json(400,{"error":"Invalid"})
            msg["from"]=user
            self._signal.send(to,msg)
            return self._json(200,{"ok":True})
        self._json(404,{"error":"Not found"})

    def _raw(self,code,ct,body):
        self.send_response(code); self.send_header("Content-Type",ct)
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def _json(self,code,data):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def _read_json(self):
        try: cl=int(self.headers.get("Content-Length",0)); return json.loads(self.rfile.read(cl))
        except: return None
    def _cookie(self,name):
        for part in self.headers.get("Cookie","").split(";"):
            k,_,v=part.strip().partition("=")
            if k.strip()==name: return v.strip()
        return ""
    def _auth_sess(self): return self._sess.validate(self._cookie("gs_sess"))
    def log_message(self,fmt,*args): sys.stderr.write(f"[{self.address_string()}] {fmt%args}\n")

if __name__=="__main__":
    host=os.environ.get("REPLIT_DEV_DOMAIN","localhost")
    sys.stderr.write("=== CYBERFUNTECH GIT SERVER ===\n")
    sys.stderr.write(f"Port : {PORT}\n")
    sys.stderr.write(f"URL  : http://{host}\n")
    sys.stderr.write(f"Clone: git clone http://{GIT_USER}:{GIT_PASS}@{host}/repo.git\n")
    sys.stderr.write("================================\n")
    sys.stderr.write(f"Workspace: {refresh_workspace()}\n")
    ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
