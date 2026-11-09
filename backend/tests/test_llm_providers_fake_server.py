"""LLM provider tests. Run from backend/:  python -m tests.test_llm_providers_fake_server

TIER: the REAL `groq` and `google-genai` SDKs (the versions in requirements.txt) talking to a LOCAL FAKE HTTP
SERVER that imitates the two APIs' wire formats. No network, no API keys, no cost.
It verifies request format, response parsing, error handling, timeouts, fallback, secret hygiene and that the
event loop is never blocked. It does NOT verify that the real Groq/Gemini services accept the configured model
names or keys: for that run scripts/verify_llm_providers.py locally with your keys.
"""
import asyncio, json, logging, os, secrets, sys, threading, time, warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
warnings.filterwarnings("ignore")
os.environ.update(MONGODB_URL="mongodb://127.0.0.1:1", DATABASE_NAME="unused", JWT_SECRET_KEY=secrets.token_urlsafe(48))

from app.core.config import Settings
from app.services import llm
from app.services.llm import GeminiProvider, GroqProvider, LLMProviderError, LLMUnavailableError

GROQ_KEY, GEMINI_KEY = "gsk_TESTKEY_aaaaaaaaaaaaaaaaaaaa", "AIzaTESTKEY_bbbbbbbbbbbbbbbbbbbb"
results = []
def check(name, cond, extra=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))

# ------------------------------------------------------------------ fake server
BEHAVIOR = {"groq": {"mode": "ok", "text": "groq answer"}, "gemini": {"mode": "ok", "text": "gemini answer"}}
REQUESTS: list[dict] = []; LOCK = threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def handle(self):
        try: super().handle()
        except (BrokenPipeError, ConnectionResetError): pass
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try: body = json.loads(raw)
        except Exception: body = None
        which = "groq" if "chat/completions" in self.path else "gemini"
        with LOCK: REQUESTS.append({"which": which, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        b = BEHAVIOR[which]; mode = b["mode"]
        if mode == "slow": time.sleep(b.get("delay", 1.0)); mode = "ok"
        if mode in ("429", "500", "401", "404"):
            payload = {"error": {"message": f"upstream said {mode}; echoing credentials {GROQ_KEY} {GEMINI_KEY}", "type": "x", "code": int(mode), "status": "ERR"}}
            return self._send(int(mode), payload)
        if mode == "badjson": return self._send_raw(200, b"<html>not json</html>")
        if which == "groq":
            text = "" if mode == "empty" else b["text"]
            return self._send(200, {"id": "c1", "object": "chat.completion", "created": 1, "model": "m", "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "length" if mode == "empty" else "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        if mode == "blocked": return self._send(200, {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 1}})
        text = "" if mode == "empty" else b["text"]
        return self._send(200, {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP", "index": 0}], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2}, "modelVersion": "fake"})
    def _send(self, code, payload): self._send_raw(code, json.dumps(payload).encode(), "application/json")
    def _send_raw(self, code, data, ctype="text/html"):
        try:  # the client may already have timed out (that is what the slow scenarios test)
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_address[1]}"
def reset(groq="ok", gemini="ok", **kw):
    BEHAVIOR["groq"].update(mode=groq, text="groq answer", **kw); BEHAVIOR["gemini"].update(mode=gemini, text="gemini answer", **kw); REQUESTS.clear()
def groq(model="fake-groq-model", timeout=5, effort=None): return GroqProvider(GROQ_KEY, model, timeout, 777, 0.2, reasoning_effort=effort, base_url=BASE)
def gemini(model="fake-gemini-model", timeout=5): return GeminiProvider(GEMINI_KEY, model, timeout, 888, 0.3, base_url=BASE)

class Capture(logging.Handler):
    def __init__(self): super().__init__(logging.DEBUG); self.lines = []
    def emit(self, record): self.lines.append(record.getMessage() + (" | " + str(record.exc_info[1]) if record.exc_info else ""))
cap = Capture(); logging.getLogger().addHandler(cap); logging.getLogger().setLevel(logging.DEBUG)

async def main():
    print("=== Groq SDK -> fake server: request format and parsing ===")
    reset(); p = groq(); out = await p.generate("SYS PROMPT", "USER PROMPT"); req = REQUESTS[-1]
    check("returns the assistant message text", out == "groq answer")
    check("POST .../chat/completions with Bearer key", req["path"].endswith("/chat/completions") and req["headers"].get("authorization") == f"Bearer {GROQ_KEY}", req["path"])
    b = req["body"]
    check("body: model, system+user messages, temperature, max_completion_tokens", b["model"] == "fake-groq-model" and [m["role"] for m in b["messages"]] == ["system", "user"] and b["messages"][0]["content"] == "SYS PROMPT" and b["messages"][1]["content"] == "USER PROMPT" and b["temperature"] == 0.2 and b["max_completion_tokens"] == 777, b)
    check("reasoning_effort is NOT sent unless configured", "reasoning_effort" not in b)
    reset(); await groq(effort="low").generate("s", "u"); check("reasoning_effort sent when configured", REQUESTS[-1]["body"].get("reasoning_effort") == "low")

    print("=== Gemini SDK -> fake server: request format and parsing ===")
    reset(); g = gemini(); out = await g.generate("SYS PROMPT", "USER PROMPT"); req = REQUESTS[-1]; b = req["body"]
    check("returns the candidate text", out == "gemini answer")
    check("POST .../models/<model>:generateContent with x-goog-api-key (google-genai 3.0.0 uses API version v1)", "/models/fake-gemini-model:generateContent" in req["path"] and req["headers"].get("x-goog-api-key") == GEMINI_KEY, req["path"])
    check("body: systemInstruction, user contents, temperature, maxOutputTokens", b["systemInstruction"]["parts"][0]["text"] == "SYS PROMPT" and b["contents"][0]["parts"][0]["text"] == "USER PROMPT" and b["generationConfig"]["temperature"] == 0.3 and b["generationConfig"]["maxOutputTokens"] == 888, b)

    print("=== failure modes -> LLMProviderError (never the raw upstream message) ===")
    for name, make in (("Groq", groq), ("Gemini", gemini)):
        key = "groq" if name == "Groq" else "gemini"
        for mode in ("429", "500", "401", "404", "badjson"):
            reset(**{key: mode}); caught = None
            try: await make().generate("s", "u")
            except LLMProviderError as e: caught = e
            except Exception as e: caught = e
            ok = isinstance(caught, LLMProviderError) and GROQ_KEY not in str(caught) and GEMINI_KEY not in str(caught) and "echoing" not in str(caught) and "echoing" not in repr(caught)
            check(f"{name}: HTTP/format failure '{mode}' -> LLMProviderError with a safe reason ({getattr(caught, 'reason', type(caught).__name__)})", ok, repr(caught))
        reset(**{key: "500"}); 
        try: await make().generate("s", "u")
        except Exception: pass
        check(f"{name}: a 500 triggers exactly ONE upstream request (no hidden SDK retries; fallback does the retrying)", sum(1 for r in REQUESTS if r["which"] == key) == 1, sum(1 for r in REQUESTS if r["which"] == key))
    reset(groq="empty"); check("Groq: empty content -> generate() returns '' (orchestrator will fall back)", (await groq().generate("s", "u")) == "")
    reset(gemini="blocked"); check("Gemini: blocked / no candidates -> '' (orchestrator will fall back)", (await gemini().generate("s", "u")) == "")

    print("=== timeouts and the event loop ===")
    for name, make, key in (("Groq", lambda: groq(timeout=1), "groq"), ("Gemini", lambda: gemini(timeout=1), "gemini")):
        reset(**{key: "slow", "delay": 4.0}); t0 = time.perf_counter(); err = None
        try: await make().generate("s", "u")
        except LLMProviderError as e: err = e
        dt = time.perf_counter() - t0
        check(f"{name}: slow upstream (4s) with a 1s timeout fails fast ({dt:.1f}s) as LLMProviderError", err is not None and dt < 3.5, (err, dt))
    reset(groq="slow", delay=1.2); lags = []; stop = False
    async def ticker():
        last = time.perf_counter()
        while not stop:
            await asyncio.sleep(0.02); now = time.perf_counter(); lags.append(now - last); last = now
    tk = asyncio.create_task(ticker()); await groq(timeout=5).generate("s", "u"); stop = True; await tk
    check(f"event loop stays responsive during a 1.2s blocking SDK call (max tick gap {max(lags):.3f}s)", max(lags) < 0.25 and len(lags) > 30, max(lags))
    reset(groq="slow", delay=1.0); t0 = time.perf_counter(); await asyncio.gather(*[groq().generate("s", "u") for _ in range(5)])
    check("5 concurrent calls overlap in worker threads (not serialised)", time.perf_counter() - t0 < 3.0, time.perf_counter() - t0)

    print("=== orchestrator: Groq primary, Gemini fallback (real SDKs) ===")
    def use(*providers): llm._providers = list(providers)
    reset(); use(groq(), gemini()); text, name = await llm.generate_answer("s", "u")
    check("both healthy -> Groq answers, Gemini never called", (text, name) == ("groq answer", "groq") and not any(r["which"] == "gemini" for r in REQUESTS))
    reset(groq="429"); use(groq(), gemini()); text, name = await llm.generate_answer("s", "u")
    check("Groq 429 -> falls back to Gemini", (text, name) == ("gemini answer", "gemini") and [r["which"] for r in REQUESTS] == ["groq", "gemini"], REQUESTS and [r["which"] for r in REQUESTS])
    for mode in ("500", "401", "404", "badjson", "empty"):
        reset(groq=mode); use(groq(), gemini()); text, name = await llm.generate_answer("s", "u")
        check(f"Groq '{mode}' -> Gemini answers", name == "gemini" and text == "gemini answer")
    reset(groq="slow", delay=4.0); use(groq(timeout=1), gemini()); t0 = time.perf_counter(); text, name = await llm.generate_answer("s", "u")
    check("Groq timeout -> Gemini answers quickly", name == "gemini" and time.perf_counter() - t0 < 3.5)
    reset(groq="500", gemini="500"); use(groq(), gemini()); err = None
    try: await llm.generate_answer("s", "u")
    except LLMUnavailableError as e: err = e
    check("both providers fail -> LLMUnavailableError", err is not None)
    reset(gemini="429"); use(gemini()); err = None
    try: await llm.generate_answer("s", "u")
    except LLMUnavailableError: err = True
    check("only Gemini configured and failing -> LLMUnavailableError", err is True)
    reset(); use(gemini()); check("only Gemini configured -> used", (await llm.generate_answer("s", "u"))[1] == "gemini")
    reset(); use(); err = None
    try: await llm.generate_answer("s", "u")
    except LLMUnavailableError: err = True
    check("no providers configured -> LLMUnavailableError (no network attempted)", err is True and REQUESTS == [])
    class Boom:
        name = "boom"
        async def generate(self, s, u): raise RuntimeError(f"secret in message {GROQ_KEY}")
    reset(); use(Boom(), gemini()); text, name = await llm.generate_answer("s", "u")
    check("an unexpected exception in a provider still falls back", name == "gemini")

    print("=== configuration and secret hygiene ===")
    base = dict(_env_file=None, MONGODB_URL="mongodb://x", DATABASE_NAME="d", JWT_SECRET_KEY="j" * 40)
    check("keys absent -> no providers", llm.build_providers(Settings(**base)) == [])
    check("blank keys ('KEY=' in .env) are treated as not configured", llm.build_providers(Settings(**base, GROQ_API_KEY="  ", GEMINI_API_KEY="")) == [])
    ps = llm.build_providers(Settings(**base, GROQ_API_KEY=GROQ_KEY, GEMINI_API_KEY=GEMINI_KEY))
    check("both keys -> [groq, gemini] in that order, with default models", [p.name for p in ps] == ["groq", "gemini"] and ps[0]._model == "openai/gpt-oss-120b" and ps[1]._model == "gemini-flash-latest")
    ps = llm.build_providers(Settings(**base, GROQ_API_KEY=GROQ_KEY, GROQ_MODEL="qwen/qwen3.6-27b", GEMINI_API_KEY=GEMINI_KEY, GEMINI_MODEL="gemini-3.6-flash", GROQ_REASONING_EFFORT="low"))
    check("model names and reasoning effort are configurable", ps[0]._model == "qwen/qwen3.6-27b" and ps[1]._model == "gemini-3.6-flash" and ps[0]._effort == "low")
    s = Settings(**base, GROQ_API_KEY=GROQ_KEY, GEMINI_API_KEY=GEMINI_KEY)
    check("settings repr/str never show the keys", GROQ_KEY not in repr(s) and GEMINI_KEY not in repr(s) and GROQ_KEY not in str(s) and GROQ_KEY not in s.model_dump_json())
    try: Settings(**base, GROQ_REASONING_EFFORT="max"); bad = False
    except Exception as e: bad = "max" not in str(e) or True
    check("invalid GROQ_REASONING_EFFORT rejected", bad)
    blob = "\n".join(cap.lines)
    check("log lines were produced (so the secret check is meaningful)", any("LLM provider" in l for l in cap.lines), len(cap.lines))
    check("API keys and upstream error text never appear in any log line (including the SDKs' own loggers)", GROQ_KEY not in blob and GEMINI_KEY not in blob and "echoing" not in blob and "secret in message" not in blob, [l for l in cap.lines if "TESTKEY" in l or "echoing" in l][:2])
    check("failures are logged by provider + error type/status only", any("groq failed" in l and "HTTP 429" in l for l in cap.lines) or any("groq failed: RateLimitError" in l for l in cap.lines), [l for l in cap.lines if "groq failed" in l][:3])

asyncio.run(main())
server.shutdown()
print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
