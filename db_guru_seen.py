"""Rastreia quais pedidos do Guru já foram exibidos como 'novos' no dashboard,
pra destacar só os que apareceram desde a última vez que a página foi aberta
(tabela 'guru_orders_seen' no Supabase — mesmo padrão do db_faturar_tracking.py)."""
import os


def _secret(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, "")
        except Exception:
            pass
    return val


_CLIENT = None


def _sb():
    global _CLIENT
    if _CLIENT is None:
        from supabase import create_client
        _CLIENT = create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    return _CLIENT


def get_seen_ids() -> set:
    try:
        rows = _sb().table("guru_orders_seen").select("guru_id").execute().data
        return {r["guru_id"] for r in rows}
    except Exception:
        return set()


def mark_seen(ids: list):
    ids = [str(i) for i in ids if i]
    if not ids:
        return
    try:
        _sb().table("guru_orders_seen").upsert([{"guru_id": i} for i in ids]).execute()
    except Exception:
        pass
