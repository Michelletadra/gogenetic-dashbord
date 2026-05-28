"""OAuth2 helper para Bling API v3."""
import base64
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE    = Path(__file__).parent / "bling_tokens.json"
AUTH_URL      = "https://www.bling.com.br/Api/v3/oauth/authorize"
TOKEN_URL     = "https://www.bling.com.br/Api/v3/oauth/token"
REDIRECT_URI  = os.getenv("BLING_REDIRECT_URI", "http://localhost:8501")
CLIENT_ID     = os.getenv("BLING_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET", "")


def get_auth_url() -> str:
    """Gera a URL de autorização para o usuário clicar."""
    return (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&state=bling_dashboard"
        f"&redirect_uri={REDIRECT_URI}"
    )


def _basic_auth() -> str:
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()


def exchange_code(code: str) -> dict:
    """Troca o código de autorização por access_token + refresh_token."""
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type":  "application/x-www-form-urlencoded",
            "Accept":        "application/json",
        },
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))
    ).isoformat()
    _save(tokens)
    return tokens


def _refresh(refresh_tok: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type":  "application/x-www-form-urlencoded",
            "Accept":        "application/json",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_tok,
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))
    ).isoformat()
    _save(tokens)
    return tokens


def _save(tokens: dict):
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))


def load() -> dict:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}


def get_valid_token() -> Optional[str]:
    """Retorna um access_token válido, renovando se necessário."""
    tokens = load()
    if not tokens:
        return None
    expires_at = datetime.fromisoformat(tokens.get("expires_at", "2000-01-01"))
    if datetime.now() < expires_at - timedelta(minutes=5):
        return tokens.get("access_token")
    if tokens.get("refresh_token"):
        try:
            new_tokens = _refresh(tokens["refresh_token"])
            return new_tokens.get("access_token")
        except Exception:
            return None
    return None


def is_connected() -> bool:
    return get_valid_token() is not None
