"""OAuth2 Bling API v3 — tokens persistidos no Supabase (o disco do Streamlit
Cloud é apagado a cada reboot/redeploy, então um arquivo local não sobrevive)."""
import base64, json, logging, os, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = Path(__file__).parent / "bling_tokens.json"  # cache local best-effort
log = logging.getLogger("integracoes")
_LOCK_RENOVACAO = threading.Lock()   # evita duas renovações simultâneas com o mesmo refresh token
_AVISO_PERSISTENCIA = None           # motivo, se o token novo não pôde ser gravado no Supabase
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


def _headers_token() -> dict:
    h = {"Authorization": f"Basic {_basic()}", "Content-Type": "application/x-www-form-urlencoded",
         "Accept": "application/json"}
    # Migração JWT (developer.bling.com.br/migracao-jwt): token opaco descontinuado,
    # data de bloqueio "em definição". Ligar com BLING_ENABLE_JWT=1 depois de
    # confirmar que a coluna bling_tokens.access_token aceita 3.000 caracteres.
    if _env("BLING_ENABLE_JWT") in ("1", "true", "sim"):
        h["enable-jwt"] = "1"
    return h


def _json_token(resp) -> dict:
    """Valida a resposta do /oauth/token antes de usar (antes: resp.json() cru)."""
    ctype = (resp.headers.get("Content-Type") or "").lower()
    corpo = (resp.text or "").strip()
    if not corpo or "html" in ctype or corpo.startswith("<"):
        raise RuntimeError(f"Bling /oauth/token respondeu {resp.status_code} sem JSON "
                           f"(Content-Type: {ctype or 'vazio'})")
    try:
        dados = json.loads(corpo)
    except ValueError:
        raise RuntimeError(f"Bling /oauth/token respondeu {resp.status_code} com JSON inválido")
    if not isinstance(dados, dict) or not dados.get("access_token"):
        raise RuntimeError(f"Bling /oauth/token respondeu {resp.status_code} sem access_token")
    return dados


def aviso_persistencia():
    """Motivo pelo qual o último token renovado não foi gravado no Supabase (ou None)."""
    return _AVISO_PERSISTENCIA


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
    global _AVISO_PERSISTENCIA
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
        _AVISO_PERSISTENCIA = None
    except Exception as e:
        # Antes era silencioso: no Streamlit Cloud o arquivo local some no reboot,
        # então perder esta gravação = perder o refresh token.
        _AVISO_PERSISTENCIA = f"token renovado mas não gravado no banco ({type(e).__name__})"
        log.error("bling_token_nao_persistido tipo=%s", type(e).__name__)

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
        headers=_headers_token(),
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Bling recusou a autorização (HTTP {resp.status_code}): {(resp.text or '')[:200]}")
    _save(_json_token(resp))


def _refresh(refresh_token: str) -> Optional[str]:
    if not refresh_token:
        return None
    try:
        resp = requests.post(
            TOKEN_URL,
            headers=_headers_token(),
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=15,
        )
        if resp.status_code != 200:
            log.error("bling_refresh_falhou status=%s", resp.status_code)
            return None
        tokens = _json_token(resp)
        _save(tokens)
        return tokens.get("access_token")
    except Exception as e:
        log.error("bling_refresh_falhou tipo=%s", type(e).__name__)
        return None


def renovar_agora() -> Optional[str]:
    """Força renovação (usado quando a API responde 401 com um token que
    parecia válido). Serializada pelo mesmo lock de get_token()."""
    with _LOCK_RENOVACAO:
        return _refresh(_load().get("refresh_token", ""))


def get_token() -> Optional[str]:
    """Retorna access_token válido ou None."""
    def _valido(tk):
        if not tk or not tk.get("access_token"):
            return None
        exp = _parse_dt(tk.get("expires_at") or "2000-01-01T00:00:00+00:00")
        return tk["access_token"] if datetime.now(timezone.utc) < exp - timedelta(minutes=5) else None

    tokens = _load()
    if not tokens or not tokens.get("access_token"):
        return None
    if _valido(tokens):
        return tokens["access_token"]

    # Token expirado — renova uma vez só, mesmo com várias threads pedindo ao mesmo tempo:
    # quem chega depois relê o banco e aproveita o token que a primeira já renovou.
    with _LOCK_RENOVACAO:
        tokens = _load()
        ok = _valido(tokens)
        if ok:
            return ok
        return _refresh((tokens or {}).get("refresh_token", ""))


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
            params={"limite": 1},
            timeout=15,
        )
        if r.status_code == 200:
            return None
        if r.status_code == 429 and _retries > 0:
            time.sleep(3)
            return connection_error(_retries=_retries - 1)
        if r.status_code == 401:
            return "Token recusado pelo Bling (401) — reconecte."
        if r.status_code == 403:
            return "Acesso negado pelo Bling (403) — verifique escopos do aplicativo ou bloqueio de IP."
        corpo = " ".join((r.text or "")[:200].split())
        return f"API do Bling respondeu {r.status_code}: {corpo}"
    except Exception as e:
        return f"Erro ao chamar API do Bling: {e}"


def disconnect():
    try:
        _sb().table("bling_tokens").delete().eq("id", 1).execute()
    except Exception:
        pass
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
