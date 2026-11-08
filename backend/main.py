"""Garage API: security middleware, hybrid-lite RAG (TF-IDF), tool-using agent, CNN-style vision scan."""
import io, json, math, os, re, threading, time, urllib.request, uuid
from collections import Counter, defaultdict, deque
from pathlib import Path
import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Garage API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["https://localhost", "capacitor://localhost", "http://localhost"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
SEC = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' https://ipwho.is https://api.open-meteo.com https://vpic.nhtsa.dot.gov; frame-ancestors 'self'; base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}
HITS: dict = defaultdict(deque)
METRICS, START = Counter(), time.time()
LIMIT, WINDOW, MAX_BODY = 60, 60, 2 * 1024 * 1024

@app.middleware("http")
async def guard(req: Request, call_next):
    if req.url.path.startswith("/api"):
        ip = (req.headers.get("x-forwarded-for", "") or (req.client.host if req.client else "?")).split(",")[0].strip()
        q, now = HITS[ip], time.time()
        while q and now - q[0] > WINDOW: q.popleft()
        if len(q) >= LIMIT: return JSONResponse({"detail": "rate limit"}, 429, headers=SEC)
        q.append(now); METRICS["api_requests"] += 1
        if int(req.headers.get("content-length") or 0) > MAX_BODY + 4096: return JSONResponse({"detail": "too large"}, 413, headers=SEC)
    res = await call_next(req)
    res.headers["X-Request-ID"] = uuid.uuid4().hex[:12]
    for k, v in SEC.items(): res.headers[k] = v
    return res

KB = [
    ("controls", "Steer with the on-screen wheel, A and D keys or tilt. W or gas accelerates, S or brake slows. Shift or the nitro button boosts. Press C for cockpit camera."),
    ("combo", "A near miss happens when you pass a car within about 3.4 metres without touching it. Chained near misses within 4 seconds multiply the bonus: 50 points times the combo."),
    ("nitro", "Nitro lifts the speed cap from 46 to 62 metres per second and adds acceleration. It drains at 34 per second and recharges at 3 per second, so save it for clear straights."),
    ("fuel", "Fuel drains faster with speed and gas. Green fuel cans restore 30. Fuel Saver mode drains 2.2 times faster and spawns cans less often. Coast to save fuel."),
    ("crash", "A collision adds damage based on closing speed, cuts your speed to 35 percent and resets the combo. At 100 damage the car is wrecked. Brake early and avoid the oncoming left lanes."),
    ("lanes", "The road has four lanes. The two left lanes carry oncoming traffic and score double points but are dangerous. The two right lanes move in your direction at lower speeds."),
    ("night", "Night Rush adds headlights, 1.5 times the traffic and 1.2 times coin value. Watch taillight glows to judge distance."),
    ("scoring", "Score comes from distance, doubled in the oncoming lanes, plus 25 per coin and near-miss bonuses. Your best score is saved on this device."),
]
KB += [
    ("upgrades", "Earn coins during runs; the wallet is saved on your device. In the Garage menu upgrade engine for 3 metres per second more top speed, tyres for 6 percent more grip, nitro cell for 10 percent less drain and fuel tank for 8 percent less burn, up to level 5 each. Each level costs 150 coins times the next level number."),
    ("weather", "Live Weather uses real conditions for your city. Rain gives 20 percent less steering grip and 25 percent weaker brakes with wet reflective roads. Fog shortens visibility. Night appears when it is dark where you are."),
    ("gamepad", "Gamepads work: left stick steers, right trigger or A accelerates, left trigger or B brakes, X or right bumper fires nitro."),
    ("director", "The AI Director adjusts traffic density after each run based on damage and score so the game stays challenging but fair. Heavy damage lowers traffic, clean high-scoring runs raise it."),
    ("leaderboard", "Enter a name in the menu before driving. Your score is posted when the run ends and the top ten appear on the landing page. Scores are sanity checked on the server."),
    ("achievements", "Achievements: Combo King for five chained near misses, Clean Driver for two kilometres without damage, Coin Hoarder for thirty coins in one run. Each pays a 100 coin bonus."),
    ("scan", "AI Scene Scan sends a frame of the game to the CNN-style vision endpoint, which reports clear road, busy scene or low visibility using edge density and brightness."),
    ("time", "Time Attack gives 60 seconds on the clock. Every coin adds 2 seconds up to 99. When time runs out the run ends and your score is posted like any other mode."),
    ("parking", "Parking mode: a green bay glows ahead in your right-hand lanes. Slow below about 12 kilometres per hour inside it and hold for just over one second to park. Each parking scores 300 plus 50 per success so far. Missing three bays ends the run. Top speed is limited to 24 metres per second."),
]
STOP = set("a an and are as at be by do does for from how i in is it of on or the to what when with you your my me can tips".split())
TOK = lambda t: [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP]
DOCS = [(n, Counter(TOK(n + " " + n + " " + t))) for n, t in KB]
DF = Counter(w for _, c in DOCS for w in c)
IDF = {w: math.log((1 + len(DOCS)) / (1 + d)) + 1 for w, d in DF.items()}

def rag_search(q: str, k: int = 2):
    qv = Counter(TOK(q)); out = []
    for i, (name, c) in enumerate(DOCS):
        dot = sum(qv[w] * c[w] * IDF.get(w, 0) ** 2 for w in qv if w in c)
        nrm = math.sqrt(sum((v * IDF[w]) ** 2 for w, v in c.items())) * math.sqrt(sum((v * IDF.get(w, 0)) ** 2 for w, v in qv.items())) or 1
        out.append((dot / nrm, name, KB[i][1]))
    return [o for o in sorted(out, reverse=True)[:k] if o[0] > 0.05]

def director(t: dict) -> float:
    x = 1.0
    if t["damage"] >= 60: x -= 0.25
    elif t["damage"] < 20 and t["score"] > 1500: x += 0.25
    if t["fuel"] < 15: x -= 0.1
    return round(min(1.5, max(0.6, x)), 2)

def analyse_run(t: dict):
    tips = []
    if t["damage"] >= 60: tips.append("Heavy damage: brake earlier and keep to the right lanes.")
    if t["fuel"] < 25: tips.append("Fuel was low: ease off the gas and collect green cans.")
    if t["coins"] < 5: tips.append("Few coins: line up with coin rows in your lane.")
    if t["mode"] == "night": tips.append("Night Rush: use taillight glow to judge gaps.")
    return tips or ["Clean run. Chain near misses for bigger combos."]

def llm(question, context):
    key = os.environ.get("GROQ_API_KEY")
    if not key: return None
    body = json.dumps({"model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), "max_tokens": 220, "messages": [
        {"role": "system", "content": "You are Garage's driving coach. Answer in under 80 words using only the context."},
        {"role": "user", "content": f"Context: {context}\nQuestion: {question}"}]}).encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", body, {"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "garage/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception: return None

class Score(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9 _.\-]{1,16}$"); score: int = Field(ge=0, le=10**7)
    dist: int = Field(ge=0, le=10**7); coins: int = Field(ge=0, le=10**4)

SB_URL, SB_KEY = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_KEY", "")
def _sb(method, path, body=None):
    req = urllib.request.Request(f"{SB_URL}/rest/v1/{path}", json.dumps(body).encode() if body is not None else None,
        {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY, "Content-Type": "application/json", "Prefer": "return=minimal", "User-Agent": "garage/1.0"}, method=method)
    with urllib.request.urlopen(req, timeout=6) as r: return json.loads(r.read() or "null")

DB, LOCK = Path("/tmp/garage_scores.json"), threading.Lock()
def _load():
    try: return json.loads(DB.read_text())
    except Exception: return []

@app.get("/api/scores")
def top():
    if SB_URL and SB_KEY:
        try: return _sb("GET", "scores?select=name,score&order=score.desc&limit=10")
        except Exception: pass
    return sorted(_load(), key=lambda r: -r["score"])[:10]

@app.post("/api/scores")
def add(s: Score):
    METRICS["scores_posted"] += 1
    if s.score > s.dist * 0.16 + s.coins * 25 + 60000: raise HTTPException(422, "implausible score")
    if SB_URL and SB_KEY:
        try:
            _sb("POST", "scores", {"name": s.name, "score": s.score, "dist": s.dist, "coins": s.coins}); return {"ok": True}
        except Exception: pass
    with LOCK:
        rows = sorted(_load() + [s.model_dump()], key=lambda r: -r["score"])[:200]
        DB.write_text(json.dumps(rows))
    return {"ok": True}

class Telemetry(BaseModel):
    score: int = Field(ge=0, le=10**9); dist: int = Field(ge=0, le=10**8); coins: int = Field(ge=0, le=10**5)
    damage: int = Field(ge=0, le=200); fuel: int = Field(ge=-5, le=100); mode: str = Field(pattern="^(highway|night|fuel|time|park)$")

class Msg(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    telemetry: Telemetry | None = None

@app.get("/api/health")
def health(): return {"ok": True}

@app.get("/api/metrics")
def metrics(): return {**METRICS, "uptime_s": int(time.time() - START)}

@app.post("/api/agent")
def agent(m: Msg):
    METRICS["agent_calls"] += 1
    trace = [f"plan: intent={'coach' if m.telemetry else 'question'}"]; parts = []
    if m.telemetry:
        trace.append("tool: analyse_run(telemetry)"); parts += analyse_run(m.telemetry.model_dump())
    trace.append("tool: rag_search(message)"); hits = rag_search(m.message)
    if hits:
        parts += [h[2] for h in hits[: 1 if m.telemetry else 2]]; trace.append("sources: " + ", ".join(h[1] for h in hits))
    elif not parts: parts.append("I couldn't find that in the Garage knowledge base. Try asking about controls, combos, nitro, fuel, crashes or lanes.")
    txt = " ".join(parts); out = llm(m.message, txt)
    if out: txt = out; trace.append("llm: groq")
    trace.append("compose: answer")
    dr = {"traffic": director(m.telemetry.model_dump())} if m.telemetry else None
    if dr: trace.append(f"director: traffic x{dr['traffic']}")
    return {"answer": txt, "trace": trace, "director": dr}

@app.post("/api/cnn")
async def cnn(file: UploadFile = File(...)):
    METRICS["cnn_calls"] += 1
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"): raise HTTPException(415, "jpeg/png/webp only")
    raw = await file.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY: raise HTTPException(413, "max 2 MB")
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)); im.verify(); im = Image.open(io.BytesIO(raw)).convert("L").resize((64, 64))
    except Exception: raise HTTPException(400, "invalid image")
    x = np.asarray(im, dtype=np.float32) / 255
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], np.float32); ky = kx.T
    def conv(a, k): return sum(k[i, j] * a[i:i + a.shape[0] - 2, j:j + a.shape[1] - 2] for i in range(3) for j in range(3))
    f = np.maximum(np.hypot(conv(x, kx), conv(x, ky)), 0)
    p = f[: f.shape[0] // 2 * 2, : f.shape[1] // 2 * 2].reshape(31, 2, 31, 2).max((1, 3))
    edge, bright = float(p.mean()), float(x.mean())
    label = "low visibility" if bright < .25 else "busy scene" if edge > .45 else "clear road"
    return {"label": label, "edge_density": round(edge, 3), "brightness": round(bright, 3), "note": "heuristic Sobel+ReLU+maxpool, not a trained model"}

WEB = Path(__file__).resolve().parent.parent / "web"
if WEB.exists(): app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
