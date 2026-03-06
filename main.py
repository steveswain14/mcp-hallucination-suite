import os
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from suppressor_suite import meta_suppressor

app = FastAPI()

VALID_KEYS = set(
    k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()
)


def require_api_key(x_api_key: str | None) -> None:
    if not x_api_key or x_api_key not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class ValidateRequest(BaseModel):
    agent_turn: dict[str, Any]
    run: list[str] | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validate")
def validate(body: ValidateRequest, x_api_key: str | None = Header(default=None)):
    require_api_key(x_api_key)
    return meta_suppressor.suppress(agent_turn=body.agent_turn, run=body.run)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
