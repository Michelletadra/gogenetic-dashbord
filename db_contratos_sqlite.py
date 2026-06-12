"""Backend SQLite — módulo de contratos (schema completo)."""
import sqlite3
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent / "data" / "creditos.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ── Schema ────────────────────────────────────────────────────────────────────
def init_contratos():
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS contratos (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            -- vínculo
            cliente_id                 INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            -- identificação
            nome_contrato              TEXT,
            empresa_gg                 TEXT,
            contratante                TEXT NOT NULL,
            cnpj                       TEXT,
            pais                       TEXT DEFAULT 'Brasil',
            -- classificação
            tipo_contrato              TEXT,
            categoria                  TEXT,
            servico_principal          TEXT,
            -- responsáveis
            responsavel_interno        TEXT,
            parceiro_relacionado       TEXT,
            -- flags
            internacional              INTEGER DEFAULT 0,
            white_label                INTEGER DEFAULT 0,
            renovacao_automatica       INTEGER DEFAULT 0,
            recorrente                 INTEGER DEFAULT 0,
            tem_comissao               INTEGER DEFAULT 0,
            -- vigência
            data_assinatura            TEXT,
            data_inicio                TEXT,
            data_termino               TEXT,
            aviso_previo_dias          INTEGER,
            reajuste_automatico        INTEGER DEFAULT 0,
            indice_reajuste            TEXT,
            -- status (manual override; status real computado em runtime)
            status                     TEXT DEFAULT 'ATIVO',
            -- financeiro
            moeda                      TEXT DEFAULT 'BRL',
            valor_total                REAL DEFAULT 0,
            valor_recorrente           REAL DEFAULT 0,
            valor_por_amostra          REAL DEFAULT 0,
            total_parcelas             INTEGER DEFAULT 0,
            valor_parcela              REAL DEFAULT 0,
            forma_pagamento            TEXT,
            comissao_percentual        REAL DEFAULT 0,
            previsao_receita_anual     REAL DEFAULT 0,
            -- amostras
            amostras_contratadas       INTEGER DEFAULT 0,
            amostras_utilizadas        INTEGER DEFAULT 0,
            amostras_bonus             INTEGER DEFAULT 0,
            valor_excedente            REAL DEFAULT 0,
            faixas_comerciais          TEXT,
            -- compliance
            lgpd                       INTEGER DEFAULT 0,
            confidencialidade          INTEGER DEFAULT 0,
            nao_concorrencia           INTEGER DEFAULT 0,
            propriedade_intelectual    INTEGER DEFAULT 0,
            compartilhamento_dados     INTEGER DEFAULT 0,
            internacionalizacao_dados  INTEGER DEFAULT 0,
            -- operacional
            sla_prazo_dias             INTEGER,
            prazo_entrega_dias         INTEGER,
            tipo_analise               TEXT,
            plataforma_vinculada       TEXT,
            pipeline                   TEXT,
            obs_tecnicas               TEXT,
            -- geral
            observacoes                TEXT,
            nome_aba                   TEXT,
            -- controle
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            updated_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS contrato_parcelas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id  INTEGER REFERENCES contratos(id) ON DELETE CASCADE,
            numero       INTEGER,
            data_emissao TEXT,
            valor        REAL DEFAULT 0,
            saldo_atual  REAL DEFAULT 0,
            situacao     TEXT,
            numero_nf    TEXT,
            created_at   TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS contrato_aditivos (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id           INTEGER REFERENCES contratos(id) ON DELETE CASCADE,
            numero_aditivo        INTEGER,
            data                  TEXT,
            tipo                  TEXT,
            descricao             TEXT,
            valor_anterior        REAL,
            valor_novo            REAL,
            data_termino_anterior TEXT,
            data_termino_novo     TEXT,
            responsavel           TEXT,
            created_at            TEXT DEFAULT (datetime('now','localtime'))
        );
        """)

# ── Status automático ─────────────────────────────────────────────────────────
def compute_status(data_termino, renovacao_automatica, status_manual="ATIVO"):
    """Calcula status real com base em datas. Respeita overrides manuais."""
    from datetime import date
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

# ── Contratos ─────────────────────────────────────────────────────────────────
def list_contratos(status=None, empresa=None, cliente_id=None,
                   tipo=None, internacional=None, white_label=None,
                   recorrente=None, tem_comissao=None, busca=None):
    with _conn() as conn:
        sql = """SELECT ct.*, c.nome as cliente_nome
                 FROM contratos ct
                 LEFT JOIN clientes c ON c.id = ct.cliente_id
                 WHERE 1=1"""
        params = []
        if status:
            if isinstance(status, list):
                sql += f" AND ct.status IN ({','.join('?'*len(status))})"
                params += status
            else:
                sql += " AND ct.status=?"; params.append(status)
        if empresa:
            sql += " AND ct.empresa_gg=?"; params.append(empresa)
        if cliente_id:
            sql += " AND ct.cliente_id=?"; params.append(cliente_id)
        if tipo:
            sql += " AND ct.tipo_contrato=?"; params.append(tipo)
        if internacional is not None:
            sql += " AND ct.internacional=?"; params.append(1 if internacional else 0)
        if white_label is not None:
            sql += " AND ct.white_label=?"; params.append(1 if white_label else 0)
        if recorrente is not None:
            sql += " AND ct.recorrente=?"; params.append(1 if recorrente else 0)
        if tem_comissao is not None:
            sql += " AND ct.tem_comissao=?"; params.append(1 if tem_comissao else 0)
        if busca:
            sql += " AND (ct.contratante LIKE ? OR ct.servico_principal LIKE ?)"
            params += [f"%{busca}%", f"%{busca}%"]
        sql += " ORDER BY ct.data_termino NULLS LAST, ct.contratante"
        rows = conn.execute(sql, params).fetchall()
    # Enriquece com status computado
    result = []
    for r in rows:
        d = dict(r)
        d["status_real"] = compute_status(d.get("data_termino"), d.get("renovacao_automatica"), d.get("status"))
        result.append(d)
    return result

def get_contrato(id):
    with _conn() as conn:
        r = conn.execute(
            "SELECT ct.*, c.nome as cliente_nome FROM contratos ct "
            "LEFT JOIN clientes c ON c.id=ct.cliente_id WHERE ct.id=?", (id,)
        ).fetchone()
    if not r: return None
    d = dict(r)
    d["status_real"] = compute_status(d.get("data_termino"), d.get("renovacao_automatica"), d.get("status"))
    return d

def insert_contrato(data) -> int:
    fields = [k for k in data if k not in ("id","cliente_nome","status_real")]
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO contratos ({','.join(fields)}) VALUES ({','.join('?'*len(fields))})",
            [data[f] for f in fields]
        )
        return cur.lastrowid

def update_contrato(id, data):
    data["updated_at"] = str(date.today())
    fields = ", ".join(f"{k}=?" for k in data if k not in ("id","cliente_nome","status_real"))
    vals   = [v for k,v in data.items() if k not in ("id","cliente_nome","status_real")]
    with _conn() as conn:
        conn.execute(f"UPDATE contratos SET {fields} WHERE id=?", vals + [id])

def delete_contrato(id):
    with _conn() as conn:
        conn.execute("DELETE FROM contratos WHERE id=?", (id,))

# ── Parcelas ──────────────────────────────────────────────────────────────────
def list_parcelas(contrato_id):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contrato_parcelas WHERE contrato_id=? ORDER BY numero",
            (contrato_id,)
        ).fetchall()
    return [dict(r) for r in rows]

def insert_parcela(data) -> int:
    fields = [k for k in data if k != "id"]
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO contrato_parcelas ({','.join(fields)}) VALUES ({','.join('?'*len(fields))})",
            [data[f] for f in fields]
        )
        return cur.lastrowid

def delete_parcela(id):
    with _conn() as conn:
        conn.execute("DELETE FROM contrato_parcelas WHERE id=?", (id,))

# ── Aditivos ──────────────────────────────────────────────────────────────────
def list_aditivos(contrato_id):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contrato_aditivos WHERE contrato_id=? ORDER BY numero_aditivo",
            (contrato_id,)
        ).fetchall()
    return [dict(r) for r in rows]

def insert_aditivo(data) -> int:
    fields = [k for k in data if k != "id"]
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO contrato_aditivos ({','.join(fields)}) VALUES ({','.join('?'*len(fields))})",
            [data[f] for f in fields]
        )
        return cur.lastrowid

def delete_aditivo(id):
    with _conn() as conn:
        conn.execute("DELETE FROM contrato_aditivos WHERE id=?", (id,))

# ── Resumo para dashboard ─────────────────────────────────────────────────────
def resumo_contratos():
    todos = list_contratos()
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

    receita_rec = sum(c.get("valor_recorrente") or 0 for c in ativos)
    valor_total_ativo = sum(c.get("valor_total") or 0 for c in ativos)

    return {
        "qtd_ativos": len(ativos),
        "qtd_vencidos": len(vencidos),
        "qtd_vencendo_30": len(v30),
        "qtd_vencendo_60": len(v60),
        "qtd_vencendo_90": len(v90),
        "qtd_encerrados": len(encerrados),
        "qtd_renovacao_auto": len(renov_auto),
        "qtd_internacionais": len(internac),
        "qtd_white_label": len(wl),
        "qtd_recorrentes": len(recorrentes),
        "receita_recorrente": receita_rec,
        "valor_total_ativo": valor_total_ativo,
        "todos": todos,
    }

# Inicializa ao importar
init_contratos()
