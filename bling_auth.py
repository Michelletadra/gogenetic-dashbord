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
def _secret(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return default

def _redirect_uri() -> str:
    return _secret("BLING_REDIRECT_URI", "http://localhost:8501")

def _client_id() -> str:
    return _secret("BLING_CLIENT_ID", "")

def _client_secret() -> str:
    return _secret("BLING_CLIENT_SECRET", "")


def get_auth_url() -> str:
    """Gera a URL de autorização para o usuário clicar."""
    return (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={_client_id()}"
        f"&state=bling_dashboard"
        f"&redirect_uri={_redirect_uri()}"
    )


def _basic_auth() -> str:
    credentials = f"{_client_id()}:{_client_secret()}"
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
            "redirect_uri": _redirect_uri(),
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


def _supabase_save(tokens: dict):
    """Persiste tokens no Supabase (sobrevive restarts do Streamlit Cloud)."""
    try:
        from supabase import create_client
        url = _secret("SUPABASE_URL")
        key = _secret("SUPABASE_KEY")
        if not url or not key:
            return
        sb = create_client(url, key)
        sb.table("settings").upsert(
            {"key": "bling_tokens", "value": tokens}
        ).execute()
    except Exception:
        pass


def _supabase_load() -> dict:
    """Carrega tokens do Supabase."""
    try:
        from supabase import create_client
        url = _secret("SUPABASE_URL")
        key = _secret("SUPABASE_KEY")
        if not url or not key:
            return {}
        sb = create_client(url, key)
        r = sb.table("settings").select("value").eq("key", "bling_tokens").execute()
        if r.data:
            raw = r.data[0]["value"]
            return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass
    return {}


def _save(tokens: dict):
    try:
        TOKEN_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))
    except Exception:
        pass
    # Mantém em session_state para sobreviver reloads sem arquivo
    try:
        import streamlit as st
        st.session_state["_bling_tokens"] = tokens
    except Exception:
        pass
    # Persiste no Supabase para sobreviver restarts do Streamlit Cloud
    _supabase_save(tokens)


def load() -> dict:
    # 1) session_state (mais fresco)
    try:
        import streamlit as st
        if "_bling_tokens" in st.session_state:
            return st.session_state["_bling_tokens"]
    except Exception:
        pass
    # 2) arquivo local
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text())
        except Exception:
            pass
    # 3) Supabase (persiste entre restarts)
    sb_tokens = _supabase_load()
    if sb_tokens:
        return sb_tokens
    # 4) secrets do Streamlit Cloud (tokens iniciais — fallback)
    try:
        import streamlit as st
        if "bling_tokens" in st.secrets:
            return dict(st.secrets["bling_tokens"])
    except Exception:
        pass
    return {}


def get_valid_token(force_refresh: bool = False) -> Optional[str]:
    """Retorna um access_token válido, renovando se necessário.
    force_refresh=True ignora o timestamp e sempre tenta renovar.
    """
    tokens = load()
    if not tokens:
        return None
    if not force_refresh:
        expires_at = datetime.fromisoformat(tokens.get("expires_at", "2000-01-01"))
        if datetime.now() < expires_at - timedelta(minutes=5):
            return tokens.get("access_token")
    if tokens.get("refresh_token"):
        try:
            new_tokens = _refresh(tokens["refresh_token"])
            return new_tokens.get("access_token")
        except Exception:
            # Refresh falhou — devolve o token atual mesmo que expirado
            return tokens.get("access_token") if not force_refresh else None
    return tokens.get("access_token") if not force_refresh else None


def is_connected() -> bool:
    return get_valid_token() is not None
