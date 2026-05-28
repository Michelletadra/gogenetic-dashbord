"""Backend Supabase para créditos (produção)."""
import os
from supabase import create_client

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    return create_client(url, key)

# ── Clientes ──────────────────────────────────────────────────────────────────
def list_clientes(busca=None):
    q = _sb().table("clientes").select("*").order("nome")
    if busca:
        q = q.ilike("nome", f"%{busca}%")
    return q.execute().data

def get_cliente(id):
    return _sb().table("clientes").select("*").eq("id", id).single().execute().data

def insert_cliente(data) -> int:
    r = _sb().table("clientes").insert(data).execute()
    return r.data[0]["id"]

def update_cliente(id, data):
    _sb().table("clientes").update(data).eq("id", id).execute()

def delete_cliente(id):
    _sb().table("clientes").delete().eq("id", id).execute()

# ── Notas Fiscais ─────────────────────────────────────────────────────────────
def list_notas(cliente_id=None, busca=None):
    q = _sb().table("notas_fiscais").select("*, clientes(nome)").order("data_emissao", desc=True)
    if cliente_id:
        q = q.eq("cliente_id", cliente_id)
    rows = q.execute().data
    for r in rows:
        r["cliente_nome"] = (r.pop("clientes", None) or {}).get("nome", "")
    if busca:
        rows = [r for r in rows if busca.lower() in r.get("numero_nf","").lower()
                or busca.lower() in r.get("cliente_nome","").lower()]
    return rows

def get_nota(id):
    return _sb().table("notas_fiscais").select("*").eq("id", id).single().execute().data

def insert_nota(data) -> int:
    r = _sb().table("notas_fiscais").insert(data).execute()
    return r.data[0]["id"]

def update_nota(id, data):
    _sb().table("notas_fiscais").update(data).eq("id", id).execute()

def delete_nota(id):
    _sb().table("notas_fiscais").delete().eq("id", id).execute()

# ── Créditos ──────────────────────────────────────────────────────────────────
def list_creditos(status=None, cliente_id=None):
    q = _sb().table("creditos").select("*, clientes(nome), notas_fiscais(numero_nf)").order("data_vencimento")
    if status:
        q = q.in_("status", status)
    if cliente_id:
        q = q.eq("cliente_id", cliente_id)
    rows = q.execute().data
    for r in rows:
        r["cliente_nome"] = (r.pop("clientes", None) or {}).get("nome", "")
        r["numero_nf"]    = (r.pop("notas_fiscais", None) or {}).get("numero_nf", "")
    return rows

def insert_credito(data) -> int:
    r = _sb().table("creditos").insert(data).execute()
    return r.data[0]["id"]

def update_credito(id, data):
    _sb().table("creditos").update(data).eq("id", id).execute()

def delete_credito(id):
    _sb().table("creditos").delete().eq("id", id).execute()

# ── Movimentações ─────────────────────────────────────────────────────────────
def list_movimentacoes(credito_id=None, cliente_id=None):
    if cliente_id:
        cred_ids = [c["id"] for c in list_creditos(cliente_id=cliente_id)]
        if not cred_ids:
            return []
        q = _sb().table("movimentacoes").select(
            "*, creditos(valor_original, clientes(nome))"
        ).in_("credito_id", cred_ids).order("created_at", desc=True)
    else:
        q = _sb().table("movimentacoes").select(
            "*, creditos(valor_original, clientes(nome))"
        ).order("created_at", desc=True)
        if credito_id:
            q = q.eq("credito_id", credito_id)
    rows = q.execute().data
    for r in rows:
        cr  = r.pop("creditos", None) or {}
        cli = cr.pop("clientes", None) or {}
        r["valor_original"] = cr.get("valor_original", 0)
        r["cliente_nome"]   = cli.get("nome", "")
    return rows

def insert_movimentacao(data) -> int:
    r = _sb().table("movimentacoes").insert(data).execute()
    return r.data[0]["id"]

# ── Resumo por cliente ────────────────────────────────────────────────────────
def resumo_cliente(cliente_id) -> dict:
    creds = list_creditos(cliente_id=cliente_id)
    notas = list_notas(cliente_id=cliente_id)
    validos   = [c for c in creds if c["status"] == "VÁLIDO"]
    expirados = [c for c in creds if c["status"] == "EXPIRADO"]
    saldo = lambda lst: sum((c.get("valor_original") or 0) - (c.get("valor_utilizado") or 0) for c in lst)
    return {
        "qtd_validos":    len(validos),
        "qtd_expirados":  len(expirados),
        "saldo_valido":   saldo(validos),
        "saldo_expirado": saldo(expirados),
        "total_utilizado": sum(c.get("valor_utilizado") or 0 for c in creds),
        "qtd_notas":      len(notas),
    }
