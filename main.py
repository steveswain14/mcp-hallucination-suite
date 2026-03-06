import os
import secrets
import smtplib
from email.mime.text import MIMEText
from typing import Any

import psycopg2
import psycopg2.extras
import stripe
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from suppressor_suite import meta_suppressor

app = FastAPI()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")

DOCS_URL = "https://mcp-hallucination-suite-production.up.railway.app/docs"


# ── Database helpers ──────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key           TEXT PRIMARY KEY,
                    email         TEXT NOT NULL,
                    tier          TEXT NOT NULL DEFAULT 'free',
                    request_count INTEGER NOT NULL DEFAULT 0,
                    request_limit INTEGER NOT NULL DEFAULT 500,
                    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_keys (
                    session_id TEXT PRIMARY KEY,
                    api_key    TEXT NOT NULL
                )
            """)
            # Add request_limit column to existing tables that predate this migration
            cur.execute("""
                ALTER TABLE api_keys
                    ADD COLUMN IF NOT EXISTS request_limit INTEGER NOT NULL DEFAULT 500
            """)
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()


# ── Email helper ──────────────────────────────────────────────────────────────

def send_api_key_email(to_email: str, api_key: str):
    body = (
        f"Thank you for subscribing to mcp-hallucination-suite Pro!\n\n"
        f"Your API key is:\n\n    {api_key}\n\n"
        f"Pass it in the X-API-Key header with every request.\n\n"
        f"Full API documentation: {DOCS_URL}\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = "Your mcp-hallucination-suite API key"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        smtp.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())


# ── API key validation ────────────────────────────────────────────────────────

def require_api_key(x_api_key: str | None) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM api_keys WHERE key = %s", (x_api_key,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return dict(row)


def increment_request_count(key: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE api_keys SET request_count = request_count + 1 WHERE key = %s",
                (key,),
            )
        conn.commit()


# ── Request model ─────────────────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    agent_turn: dict[str, Any]
    run: list[str] | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validate")
def validate(body: ValidateRequest, x_api_key: str | None = Header(default=None)):
    row = require_api_key(x_api_key)
    if row["request_count"] >= row["request_limit"]:
        raise HTTPException(status_code=429, detail="Request limit reached. Upgrade to Pro.")
    result = meta_suppressor.suppress(agent_turn=body.agent_turn, run=body.run)
    increment_request_count(row["key"])
    return result


@app.get("/register/free")
def register_free():
    key = secrets.token_urlsafe(32)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (key, email, tier, request_limit) VALUES (%s, %s, %s, %s)",
                (key, "", "free", 500),
            )
        conn.commit()
    return {"api_key": key, "tier": "free", "request_limit": 500}


@app.get("/activate/{session_id}", response_class=HTMLResponse)
def activate(session_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT api_key FROM pending_keys WHERE session_id = %s", (session_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    api_key = row[0]
    html = f"""<!DOCTYPE html>
<html>
<head><title>Your API Key</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:60px auto;padding:0 20px">
  <h1>Your Pro API Key</h1>
  <p>Here is your API key. Keep it safe — it grants access to your Pro account.</p>
  <div style="background:#f4f4f4;border:1px solid #ccc;border-radius:6px;padding:16px 24px;font-size:1.3em;font-family:monospace;word-break:break-all">
    {api_key}
  </div>
  <h2>How to use it</h2>
  <p>Include it in the <code>X-API-Key</code> header with every request:</p>
  <pre style="background:#f4f4f4;border:1px solid #ccc;border-radius:6px;padding:16px">X-API-Key: {api_key}</pre>
  <p>Full documentation: <a href="{DOCS_URL}">{DOCS_URL}</a></p>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_details", {}).get("email") or session.get("customer_email", "")
        key = secrets.token_urlsafe(32)
        session_id = session.get("id", "")
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO api_keys (key, email, tier, request_limit) VALUES (%s, %s, %s, %s)",
                    (key, email, "pro", 100000),
                )
                cur.execute(
                    "INSERT INTO pending_keys (session_id, api_key) VALUES (%s, %s)",
                    (session_id, key),
                )
            conn.commit()

    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
