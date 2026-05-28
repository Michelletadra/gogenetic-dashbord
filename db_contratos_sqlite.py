"""Backend SQLite — módulo de contratos."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "creditos.db"

def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_contratos():
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS contratos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id       INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            nome_aba         TEXT,
            empresa          TEXT,
            contratante      TEXT NOT NULL,
            data_assinatura  TEXT,
            data_vencimento  TEXT,
            valor_total      REAL DEFAULT 0,
            valor_parcela    REAL DEFAULT 0,
            total_parcelas   INTEGER DEFAULT 0,
            valor_consumido  REAL DEFAULT 0,
            saldo            REAL DEFAULT 0,
            status           TEXT DEFAULT 'ATIVO',
            situacao         TEXT,
            servico          TEXT,
            kit_info         TEXT,
            amostras_info    TEXT,
            info_pagamento   TEXT,
            observacoes      TEXT,
            created_at       TEXT DEFAULT (datetime('now','localtime'))
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
        """)

# ── Contratos ─────────────────────────────────────────────────────────────────
def list_contratos(status=None, empresa=None, cliente_id=None):
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
                sql += " AND ct.status=?"
                params.append(status)
        if empresa:
            sql += " AND ct.empresa=?"
            params.append(empresa)
        if cliente_id:
            sql += " AND ct.cliente_id=?"
            params.append(cliente_id)
        sql += " ORDER BY ct.data_vencimento"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def get_contrato(id):
    with _conn() as conn:
        r = conn.execute(
            """SELECT ct.*, c.nome as cliente_nome
               FROM contratos ct LEFT JOIN clientes c ON c.id=ct.cliente_id
               WHERE ct.id=?""", (id,)
        ).fetchone()
    return dict(r) if r else None

def insert_contrato(data) -> int:
    fields = [k for k in data if k != "id"]
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO contratos ({','.join(fields)}) VALUES ({','.join('?'*len(fields))})",
            [data[f] for f in fields]
        )
        return cur.lastrowid

def update_contrato(id, data):
    fields = ", ".join(f"{k}=?" for k in data)
    with _conn() as conn:
        conn.execute(f"UPDATE contratos SET {fields} WHERE id=?", list(data.values()) + [id])

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

# ── Resumo para dashboard ─────────────────────────────────────────────────────
def resumo_contratos():
    with _conn() as conn:
        r = conn.execute("""
            SELECT
                COUNT(CASE WHEN status='ATIVO'     THEN 1 END) as qtd_ativos,
                COUNT(CASE WHEN status='ENCERRADO' THEN 1 END) as qtd_encerrados,
                COALESCE(SUM(CASE WHEN status='ATIVO' THEN valor_total END), 0)  as valor_total_ativo,
                COALESCE(SUM(CASE WHEN status='ATIVO' THEN saldo       END), 0)  as saldo_total_ativo,
                COALESCE(SUM(CASE WHEN status='ATIVO' THEN valor_consumido END), 0) as consumido_total
            FROM contratos
        """).fetchone()
    return dict(r)

# Inicializa ao importar
init_contratos()
