"""Anotações livres por serviço (usado na aba 'A Faturar' de 7_Servicos.py),
persistidas no Supabase pra sobreviver a reboots do Streamlit Cloud."""
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


def get_notas(codigos: list) -> dict:
    """Retorna {codigo: nota} pros códigos informados."""
    codigos = [str(c) for c in codigos if c]
    if not codigos:
        return {}
    try:
        rows = _sb().table("servico_notas").select("codigo,nota").in_("codigo", codigos).execute().data
        return {r["codigo"]: r.get("nota", "") for r in rows}
    except Exception:
        return {}


def save_nota(codigo, nota: str):
    codigo = str(codigo)
    try:
        if nota:
            _sb().table("servico_notas").upsert({"codigo": codigo, "nota": nota}).execute()
        else:
            _sb().table("servico_notas").delete().eq("codigo", codigo).execute()
    except Exception:
        pass
