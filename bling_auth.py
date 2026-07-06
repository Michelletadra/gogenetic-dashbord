"""OAuth2 Bling API v3 — tokens persistidos no Supabase (o disco do Streamlit
Cloud é apagado a cada reboot/redeploy, então um arquivo local não sobrevive)."""
import base64, json, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = Path(__file__).parent / "bling_tokens.json"  # cache local best-effort
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


_SB_CLIENT = None


def _sb():
    global _SB_CLIENT
    if _SB_CLIENT is None:
        from supabase import create_client
        _SB_CLIENT = create_client(_env("SUPABASE_URL"), _env("SUPABASE_KEY"))
    return _SB_CLIENT


def _parse_dt(s: str) -> datetime:
    """Sempre retorna um datetime com timezone (UTC), aceitando strings com ou sem offset."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _save(tokens: dict):
    tokens = dict(tokens)
    tokens["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
    ).isoformat()

    try:
        _sb().table("bling_tokens").upsert({
            "id": 1,
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": tokens["expires_at"],
        }).execute()
    except Exception:
        pass  # se o Supabase falhar, ainda temos o arquivo local como fallback

    try:
        TOKEN_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))
    except Exception:
        pass


def _load() -> dict:
    try:
        rows = _sb().table("bling_tokens").select("*").eq("id", 1).execute().data
        if rows:
            r = rows[0]
            return {
                "access_token": r["access_token"],
                "refresh_token": r.get("refresh_token"),
                "expires_at": r["expires_at"],
            }
    except Exception:
        pass

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

    expires_at = _parse_dt(tokens.get("expires_at") or "2000-01-01T00:00:00+00:00")
    if datetime.now(timezone.utc) < expires_at - timedelta(minutes=5):
        return tokens["access_token"]

    # Token expirado — tenta refresh
    return _refresh(tokens.get("refresh_token", ""))


def is_connected() -> bool:
    return connection_error() is None


def connection_error(_retries: int = 2) -> Optional[str]:
    """Retorna None se conectado, ou uma string com o motivo da falha."""
    tokens = _load()
    if not tokens or not tokens.get("access_token"):
        return "Nenhum token salvo — clique em Conectar ao Bling."
    token = get_token()
    if not token:
        return "Token expirado e o refresh falhou — reconecte."
    try:
        r = requests.get(
            "https://api.bling.com.br/Api/v3/categorias/receitas-despesas",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            return None
        if r.status_code == 429 and _retries > 0:
            time.sleep(3)
            return connection_error(_retries=_retries - 1)
        return f"API do Bling respondeu {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return f"Erro ao chamar API do Bling: {e}"


def disconnect():
    try:
        _sb().table("bling_tokens").delete().eq("id", 1).execute()
    except Exception:
        pass
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
