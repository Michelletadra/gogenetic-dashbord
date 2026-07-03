"""OAuth2 Bling API v3 — autenticação simples via arquivo."""
import base64, json, os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = Path(__file__).parent / "bling_tokens.json"
TOKEN_URL  = "https://www.bling.com.br/Api/v3/oauth/token"
AUTH_URL   = "https://www.bling.com.br/Api/v3/oauth/authorize"


def _env(key: str) -> str:
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, "")
    except Exception:
        return ""


def _basic() -> str:
    return base64.b64encode(f"{_env('BLING_CLIENT_ID')}:{_env('BLING_CLIENT_SECRET')}".encode()).decode()


def get_auth_url() -> str:
    redirect = _env("BLING_REDIRECT_URI") or "http://localhost:8501"
    return (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={_env('BLING_CLIENT_ID')}"
        f"&state=bling_dashboard"
        f"&redirect_uri={redirect}"
    )


def _save(tokens: dict):
    tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))
    ).isoformat()
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))


def _load() -> dict:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text())
        except Exception:
            pass
    return {}


def exchange_code(code: str):
    """Troca código OAuth pelo access_token e salva."""
    redirect = _env("BLING_REDIRECT_URI") or "http://localhost:8501"
    resp = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {_basic()}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} — {resp.text}")
    _save(resp.json())


def _refresh(refresh_token: str) -> Optional[str]:
    try:
        resp = requests.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {_basic()}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        tokens = resp.json()
        _save(tokens)
        return tokens.get("access_token")
    except Exception:
        return None


def get_token() -> Optional[str]:
    """Retorna access_token válido ou None."""
    tokens = _load()
    if not tokens or not tokens.get("access_token"):
        return None

    expires_at = datetime.fromisoformat(tokens.get("expires_at", "2000-01-01"))
    if datetime.now() < expires_at - timedelta(minutes=5):
        return tokens["access_token"]

    # Token expirado — tenta refresh
    return _refresh(tokens.get("refresh_token", ""))


def is_connected() -> bool:
    token = get_token()
    if not token:
        return False
    try:
        r = requests.get(
            "https://api.bling.com.br/Api/v3/empresas",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


def disconnect():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
