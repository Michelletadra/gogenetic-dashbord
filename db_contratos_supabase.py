"""Backend Supabase — módulo de contratos (produção)."""
import os
from datetime import date
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

# Singleton — cria o cliente uma única vez por processo
_CLIENT = None

def _sb():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    return _CLIENT

# ── Status automático ─────────────────────────────────────────────────────────
def compute_status(data_termino, renovacao_automatica, status_manual="ATIVO"):
    """Calcula status real com base em datas. Respeita overrides manuais."""
    import pandas as pd
    MANUAL_OVERRIDES = {"ENCERRADO", "RESCINDIDO", "EM NEGOCIAÇÃO", "SUSPENSO", "VENCIDO"}
    if status_manual in MANUAL_OVERRIDES:
        return status_manual
    if not data_termino:
        return "ATIVO"
    try:
        term = pd.to_datetime(data_termino).date()
    except Exception:
        return status_manual or "ATIVO"
    hoje = date.today()
    delta = (term - hoje).days
    if delta < 0:
        return "RENOVAÇÃO AUTOMÁTICA" if renovacao_automatica else "VENCIDO"
    if delta <= 30:  return "VENCENDO 30D"
    if delta <= 60:  return "VENCENDO 60D"
    if delta <= 90:  return "VENCENDO 90D"
    return "ATIVO"

def _enrich(rows):
    """Achata join clientes e calcula status_real."""
    result = []
    for r in rows:
        r["cliente_nome"] = (r.pop("clientes", None) or {}).get("nome", "")
        r["status_real"] = compute_status(
            r.get("data_termino"), r.get("renovacao_automatica"), r.get("status")
        )
        result.append(r)
    return result

# ── Init (no-op no Supabase) ──────────────────────────────────────────────────
def init_contratos():
    pass  # tabelas criadas via SQL no Supabase Dashboard

# ── Contratos ─────────────────────────────────────────────────────────────────
def list_contratos(status=None, empresa=None, cliente_id=None,
                   tipo=None, internacional=None, white_label=None,
                   recorrente=None, tem_comissao=None, busca=None):
    q = _sb().table("contratos").select("*, clientes(nome)") \
             .order("data_termino", nullsfirst=False) \
             .order("contratante")
    if status:
        if isinstance(status, list):
            q = q.in_("status", status)
        else:
            q = q.eq("status", status)
    if empresa:
        q = q.eq("empresa_gg", empresa)
    if cliente_id:
        q = q.eq("cliente_id", cliente_id)
    if tipo:
        q = q.eq("tipo_contrato", tipo)
    if internacional is not None:
        q = q.eq("internacional", 1 if internacional else 0)
    if white_label is not None:
        q = q.eq("white_label", 1 if white_label else 0)
    if recorrente is not None:
        q = q.eq("recorrente", 1 if recorrente else 0)
    if tem_comissao is not None:
        q = q.eq("tem_comissao", 1 if tem_comissao else 0)
    if busca:
        q = q.or_(f"contratante.ilike.%{busca}%,servico_principal.ilike.%{busca}%")
    rows = q.execute().data
    return _enrich(rows)

def get_contrato(id):
    r = _sb().table("contratos").select("*, clientes(nome)") \
             .eq("id", id).single().execute().data
    if not r:
        return None
    r["cliente_nome"] = (r.pop("clientes", None) or {}).get("nome", "")
    r["status_real"]  = compute_status(
        r.get("data_termino"), r.get("renovacao_automatica"), r.get("status")
    )
    return r

def insert_contrato(data) -> int:
    SKIP = {"id", "cliente_nome", "status_real", "created_at", "updated_at"}
    d = {k: v for k, v in data.items() if k not in SKIP}
    r = _sb().table("contratos").insert(d).execute()
    return r.data[0]["id"]

def update_contrato(id, data):
    SKIP = {"id", "cliente_nome", "status_real"}
    d = {k: v for k, v in data.items() if k not in SKIP}
    d["updated_at"] = str(date.today())
    _sb().table("contratos").update(d).eq("id", id).execute()

def delete_contrato(id):
    _sb().table("contratos").delete().eq("id", id).execute()

# ── Parcelas ──────────────────────────────────────────────────────────────────
def list_parcelas(contrato_id):
    return _sb().table("contrato_parcelas").select("*") \
                .eq("contrato_id", contrato_id).order("numero").execute().data

def insert_parcela(data) -> int:
    d = {k: v for k, v in data.items() if k not in ("id", "created_at")}
    r = _sb().table("contrato_parcelas").insert(d).execute()
    return r.data[0]["id"]

def delete_parcela(id):
    _sb().table("contrato_parcelas").delete().eq("id", id).execute()

# ── Aditivos ──────────────────────────────────────────────────────────────────
def list_aditivos(contrato_id):
    return _sb().table("contrato_aditivos").select("*") \
                .eq("contrato_id", contrato_id).order("numero_aditivo").execute().data

def insert_aditivo(data) -> int:
    d = {k: v for k, v in data.items() if k not in ("id", "created_at")}
    r = _sb().table("contrato_aditivos").insert(d).execute()
    return r.data[0]["id"]

def delete_aditivo(id):
    _sb().table("contrato_aditivos").delete().eq("id", id).execute()

# ── Resumo para dashboard ─────────────────────────────────────────────────────
def resumo_contratos():
    todos       = list_contratos()
    ativos      = [c for c in todos if c["status_real"] not in ("ENCERRADO","RESCINDIDO","VENCIDO")]
    vencidos    = [c for c in todos if c["status_real"] == "VENCIDO"]
    v30         = [c for c in todos if c["status_real"] == "VENCENDO 30D"]
    v60         = [c for c in todos if c["status_real"] in ("VENCENDO 30D","VENCENDO 60D")]
    v90         = [c for c in todos if c["status_real"] in ("VENCENDO 30D","VENCENDO 60D","VENCENDO 90D")]
    encerrados  = [c for c in todos if c["status_real"] in ("ENCERRADO","RESCINDIDO")]
    renov_auto  = [c for c in ativos if c.get("renovacao_automatica")]
    internac    = [c for c in ativos if c.get("internacional")]
    wl          = [c for c in ativos if c.get("white_label")]
    recorrentes = [c for c in ativos if c.get("recorrente")]

    receita_rec       = sum(c.get("valor_recorrente") or 0 for c in ativos)
    valor_total_ativo = sum(c.get("valor_total")      or 0 for c in ativos)

    return {
        "qtd_ativos":        len(ativos),
        "qtd_vencidos":      len(vencidos),
        "qtd_vencendo_30":   len(v30),
        "qtd_vencendo_60":   len(v60),
        "qtd_vencendo_90":   len(v90),
        "qtd_encerrados":    len(encerrados),
        "qtd_renovacao_auto":len(renov_auto),
        "qtd_internacionais":len(internac),
        "qtd_white_label":   len(wl),
        "qtd_recorrentes":   len(recorrentes),
        "receita_recorrente":receita_rec,
        "valor_total_ativo": valor_total_ativo,
        "todos":             todos,
    }
