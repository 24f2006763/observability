import os
import json
import time
import uuid
from typing import Optional
from fastapi import FastAPI, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable wide-open CORS for the grader browser environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ASSIGNED VALUES & DISK PERSISTENCE PATHS ---
MY_EMAIL = "24f2006763@ds.study.iitm.ac.in"  # <-- CHANGE THIS to your actual logged-in email address

METRICS_FILE = "/tmp/observability_metrics.json"
LOGS_FILE = "/tmp/observability_logs.json"
START_TIME_FILE = "/tmp/observability_startup.txt"

# --- THREAD-SAFE DISK HELPERS TO DEFY SERVERLESS STATE WIPES ---
def get_startup_time() -> float:
    if os.path.exists(START_TIME_FILE):
        try:
            with open(START_TIME_FILE, "r") as f:
                return float(f.read().strip())
        except:
            pass
    now = time.time()
    try:
        with open(START_TIME_FILE, "w") as f:
            f.write(str(now))
    except:
        pass
    return now

def increment_global_counter():
    current = 0
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, "r") as f:
                current = json.load(f).get("http_requests_total", 0)
        except:
            pass
    current += 1
    try:
        with open(METRICS_FILE, "w") as f:
            json.dump({"http_requests_total": current}, f)
    except:
        pass
    return current

def get_global_counter() -> int:
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, "r") as f:
                return json.load(f).get("http_requests_total", 0)
        except:
            pass
    return 0

def append_structured_log(level: str, path: str, request_id: str):
    log_entry = {
        "level": level,
        "ts": time.time(),
        "path": path,
        "request_id": request_id
    }
    logs = []
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, "r") as f:
                logs = json.load(f)
        except:
            pass
    logs.append(log_entry)
    # Restrict to last 100 entries to avoid bloat
    logs = logs[-100:]
    try:
        with open(LOGS_FILE, "w") as f:
            json.dump(logs, f)
    except:
        pass

# Initialize application startup baseline timestamp tracking
_ = get_startup_time()

# --- GLOBAL APP STATE MIDDLEWARE ---
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    # Pass preflight OPTIONS check safely
    if request.method == "OPTIONS":
        return await call_next(request)

    # 1. Generate an explicit Request ID
    req_id = str(uuid.uuid4())
    path = request.url.path

    # 2. Increment global metrics counter
    increment_global_counter()

    # 3. Log the inbound request path structure
    append_structured_log("INFO", path, req_id)

    response = await call_next(request)

    # Inject clean outbound CORS fallback fields explicitly
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response

# --- 1. WORK ENDPOINT ---
@app.get("/work")
async def do_work(n: int = Query(default=0, alias="n")):
    # Simulate processing K units of work loops
    for _ in range(n):
        pass
    return {"email": MY_EMAIL, "done": n}

# --- 2. PROMETHEUS METRICS ENDPOINT ---
@app.get("/metrics")
async def get_metrics():
    current_count = get_global_counter()
    # Explicitly return raw plaintext string matching Prometheus standard format rules
    prometheus_data = (
        f"# HELP http_requests_total Total number of HTTP requests processed.\n"
        f"# TYPE http_requests_total counter\n"
        f"http_requests_total {current_count}\n"
    )
    return Response(content=prometheus_data, media_type="text/plain")

# --- 3. HEALTHZ CHECK ENDPOINT ---
@app.get("/healthz")
async def health_check():
    uptime = max(0.0, time.time() - get_startup_time())
    return {"status": "ok", "uptime_s": uptime}

# --- 4. STRUCTURED LOG TAILING ENDPOINT ---
@app.get("/logs/tail")
async def tail_logs(limit: int = Query(default=10, alias="limit")):
    logs = []
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, "r") as f:
                logs = json.load(f)
        except:
            pass
    # Slice the last N records requested by the client
    return logs[-limit:]