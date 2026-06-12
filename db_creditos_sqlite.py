"""Backend SQLite para desenvolvimento local."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "creditos.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Cria as tabelas se não existirem."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS clientes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            tipo        TEXT DEFAULT 'PF',
            cpf_cnpj    TEXT,
            email       TEXT,
            telefone    TEXT,
            observacoes TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS notas_fiscais (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_nf    TEXT NOT NULL,
            cliente_id   INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
            data_emissao TEXT,
            valor_total  REAL DEFAULT 0,
            observacoes  TEXT,
            arquivo_path TEXT,
            created_at   TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS creditos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id       INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
            nota_fiscal_id   INTEGER REFERENCES notas_fiscais(id) ON DELETE SET NULL,
            valor_original   REAL NOT NULL,
            valor_utilizado  REAL DEFAULT 0,
            data_vencimento  TEXT,
            status           TEXT DEFAULT 'VÁLIDO',
            observacoes      TEXT,
            created_at       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS movimentacoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            credito_id  INTEGER REFERENCES creditos(id) ON DELETE CASCADE,
            tipo        TEXT NOT NULL,
            valor       REAL NOT NULL,
            data        TEXT DEFAULT (date('now','localtime')),
            responsavel TEXT,
            observacao  TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );
        """)

# ── Clientes ──────────────────────────────────────────────────────────────────
def list_clientes(busca: str = None):
    with _conn() as conn:
        if busca:
            rows = conn.execute(
                "SELECT * FROM clientes WHERE nome LIKE ? ORDER BY nome",
                (f"%{busca}%",)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    return [dict(r) for r in rows]

def get_cliente(id: int):
    with _conn() as conn:
        r = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    return dict(r) if r else None

def insert_cliente(data: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO clientes (nome,tipo,cpf_cnpj,email,telefone,observacoes) VALUES (?,?,?,?,?,?)",
            (data["nome"], data.get("tipo","PF"), data.get("cpf_cnpj"),
             data.get("email"), data.get("telefone"), data.get("observacoes"))
        )
        return cur.lastrowid

def update_cliente(id: int, data: dict):
    with _conn() as conn:
        conn.execute(
            "UPDATE clientes SET nome=?,tipo=?,cpf_cnpj=?,email=?,telefone=?,observacoes=? WHERE id=?",
            (data["nome"], data.get("tipo","PF"), data.get("cpf_cnpj"),
             data.get("email"), data.get("telefone"), data.get("observacoes"), id)
        )

def delete_cliente(id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM clientes WHERE id=?", (id,))

# ── Notas Fiscais ─────────────────────────────────────────────────────────────
def list_notas(cliente_id: int = None, busca: str = None):
    with _conn() as conn:
        sql = """SELECT nf.*, c.nome as cliente_nome
                 FROM notas_fiscais nf
                 LEFT JOIN clientes c ON c.id = nf.cliente_id
                 WHERE 1=1"""
        params = []
        if cliente_id:
            sql += " AND nf.cliente_id=?"
            params.append(cliente_id)
        if busca:
            sql += " AND (nf.numero_nf LIKE ? OR c.nome LIKE ?)"
            params += [f"%{busca}%", f"%{busca}%"]
        sql += " ORDER BY nf.data_emissao DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def get_nota(id: int):
    with _conn() as conn:
        r = conn.execute("SELECT * FROM notas_fiscais WHERE id=?", (id,)).fetchone()
    return dict(r) if r else None

def insert_nota(data: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO notas_fiscais (numero_nf,cliente_id,data_emissao,valor_total,observacoes,arquivo_path) VALUES (?,?,?,?,?,?)",
            (data["numero_nf"], data["cliente_id"], data.get("data_emissao"),
             data.get("valor_total",0), data.get("observacoes"), data.get("arquivo_path"))
        )
        return cur.lastrowid

def update_nota(id: int, data: dict):
    with _conn() as conn:
        conn.execute(
            "UPDATE notas_fiscais SET numero_nf=?,data_emissao=?,valor_total=?,observacoes=?,arquivo_path=? WHERE id=?",
            (data["numero_nf"], data.get("data_emissao"), data.get("valor_total",0),
             data.get("observacoes"), data.get("arquivo_path"), id)
        )

def delete_nota(id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM notas_fiscais WHERE id=?", (id,))

# ── Créditos ──────────────────────────────────────────────────────────────────
def list_creditos(status: list = None, cliente_id: int = None):
    with _conn() as conn:
        sql = """SELECT cr.*, c.nome as cliente_nome, nf.numero_nf
                 FROM creditos cr
                 LEFT JOIN clientes c ON c.id = cr.cliente_id
                 LEFT JOIN notas_fiscais nf ON nf.id = cr.nota_fiscal_id
                 WHERE 1=1"""
        params = []
        if status:
            sql += f" AND cr.status IN ({','.join('?'*len(status))})"
            params += status
        if cliente_id:
            sql += " AND cr.cliente_id=?"
            params.append(cliente_id)
        sql += " ORDER BY cr.data_vencimento"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def insert_credito(data: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO creditos (cliente_id,nota_fiscal_id,valor_original,valor_utilizado,data_vencimento,status,observacoes) VALUES (?,?,?,?,?,?,?)",
            (data["cliente_id"], data.get("nota_fiscal_id"), data["valor_original"],
             data.get("valor_utilizado",0), data.get("data_vencimento"),
             data.get("status","VÁLIDO"), data.get("observacoes"))
        )
        return cur.lastrowid

def update_credito(id: int, data: dict):
    fields = ", ".join(f"{k}=?" for k in data)
    with _conn() as conn:
        conn.execute(f"UPDATE creditos SET {fields} WHERE id=?", list(data.values()) + [id])

def delete_credito(id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM creditos WHERE id=?", (id,))

# ── Movimentações ─────────────────────────────────────────────────────────────
def list_movimentacoes(credito_id: int = None, cliente_id: int = None):
    with _conn() as conn:
        sql = """SELECT m.*, c.nome as cliente_nome, cr.valor_original
                 FROM movimentacoes m
                 LEFT JOIN creditos cr ON cr.id = m.credito_id
                 LEFT JOIN clientes c ON c.id = cr.cliente_id
                 WHERE 1=1"""
        params = []
        if credito_id:
            sql += " AND m.credito_id=?"
            params.append(credito_id)
        if cliente_id:
            sql += " AND cr.cliente_id=?"
            params.append(cliente_id)
        sql += " ORDER BY m.created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def insert_movimentacao(data: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO movimentacoes (credito_id,tipo,valor,data,responsavel,observacao) VALUES (?,?,?,?,?,?)",
            (data["credito_id"], data["tipo"], data["valor"],
             data.get("data"), data.get("responsavel"), data.get("observacao"))
        )
        return cur.lastrowid

# ── Resumo por cliente ────────────────────────────────────────────────────────
def resumo_cliente(cliente_id: int) -> dict:
    with _conn() as conn:
        r = conn.execute("""
            SELECT
                COUNT(CASE WHEN status='VÁLIDO'   THEN 1 END) as qtd_validos,
                COUNT(CASE WHEN status='EXPIRADO' THEN 1 END) as qtd_expirados,
                COALESCE(SUM(CASE WHEN status='VÁLIDO' THEN valor_original - valor_utilizado END), 0) as saldo_valido,
                COALESCE(SUM(CASE WHEN status='EXPIRADO' THEN valor_original - valor_utilizado END), 0) as saldo_expirado,
                COALESCE(SUM(valor_utilizado), 0) as total_utilizado
            FROM creditos WHERE cliente_id=?
        """, (cliente_id,)).fetchone()
        notas = conn.execute("SELECT COUNT(*) as qtd FROM notas_fiscais WHERE cliente_id=?", (cliente_id,)).fetchone()
    return {**dict(r), "qtd_notas": notas["qtd"]}

# Inicializa banco ao importar
init_db()
