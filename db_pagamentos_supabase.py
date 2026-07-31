"""Backend Supabase para Gestão de Pagamentos (produção)."""
import os
from datetime import date, datetime

from supabase import create_client


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
        _CLIENT = create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    return _CLIENT


# ── Contas bancárias ───────────────────────────────────────────────────────────

def list_contas_bancarias(somente_ativas: bool = True) -> list:
    q = _sb().table("contas_bancarias").select("*").order("nome")
    if somente_ativas:
        q = q.eq("ativo", True)
    return q.execute().data


def insert_conta_bancaria(nome: str, banco: str = "", saldo_minimo: float = 0) -> int:
    r = _sb().table("contas_bancarias").insert({
        "nome": nome, "banco": banco, "saldo_minimo": saldo_minimo,
    }).execute()
    return r.data[0]["id"]


def update_conta_bancaria(id, data: dict):
    _sb().table("contas_bancarias").update(data).eq("id", id).execute()


def desativar_conta_bancaria(id):
    _sb().table("contas_bancarias").update({"ativo": False}).eq("id", id).execute()


# ── Saldos (histórico, sempre insere — nunca sobrescreve) ─────────────────────

def insert_saldo(conta_id, valor: float, saldo_reservado: float = 0,
                  data_referencia: date = None, observacao: str = "", usuario: str = "") -> int:
    r = _sb().table("saldos_bancarios").insert({
        "conta_id": conta_id,
        "valor": valor,
        "saldo_reservado": saldo_reservado,
        "data_referencia": (data_referencia or date.today()).isoformat(),
        "observacao": observacao,
        "usuario": usuario,
    }).execute()
    return r.data[0]["id"]


def ultimos_saldos() -> dict:
    """Retorna {conta_id: registro_mais_recente} olhando data_referencia e depois
    criado_em, já que várias contas podem não ter saldo atualizado no mesmo dia."""
    rows = (_sb().table("saldos_bancarios").select("*")
            .order("data_referencia", desc=True).order("criado_em", desc=True)
            .execute().data)
    latest = {}
    for r in rows:
        if r["conta_id"] not in latest:
            latest[r["conta_id"]] = r
    return latest


def historico_saldos(conta_id) -> list:
    return (_sb().table("saldos_bancarios").select("*").eq("conta_id", conta_id)
            .order("data_referencia", desc=True).order("criado_em", desc=True)
            .execute().data)


# ── Overrides de pagamento (seleção, conta de origem, status, campos manuais) ──

def list_overrides(empresas: list = None) -> dict:
    """Retorna {(empresa, codigo): registro}."""
    q = _sb().table("pagamentos_overrides").select("*")
    if empresas:
        q = q.in_("empresa", empresas)
    rows = q.execute().data
    return {(r["empresa"], str(r["codigo"])): r for r in rows}


def upsert_override(empresa: str, codigo: str, data: dict):
    payload = {"empresa": empresa, "codigo": str(codigo),
               "atualizado_em": datetime.now().isoformat(), **data}
    _sb().table("pagamentos_overrides").upsert(payload, on_conflict="empresa,codigo").execute()


def registrar_historico(empresa: str, codigo: str, acao: str,
                         valor_anterior=None, valor_novo=None, usuario: str = ""):
    _sb().table("pagamentos_historico").insert({
        "empresa": empresa, "codigo": str(codigo), "acao": acao,
        "valor_anterior": str(valor_anterior) if valor_anterior is not None else None,
        "valor_novo": str(valor_novo) if valor_novo is not None else None,
        "usuario": usuario,
    }).execute()


def historico_titulo(empresa: str, codigo: str) -> list:
    return (_sb().table("pagamentos_historico").select("*")
            .eq("empresa", empresa).eq("codigo", str(codigo))
            .order("criado_em", desc=True).execute().data)


# ── Rodadas de pagamento (relatório/snapshot) ──────────────────────────────────

def salvar_rodada(data: dict) -> int:
    r = _sb().table("rodadas_pagamento").insert(data).execute()
    return r.data[0]["id"]


def list_rodadas(limit: int = 20) -> list:
    return (_sb().table("rodadas_pagamento").select("*")
            .order("criado_em", desc=True).limit(limit).execute().data)
