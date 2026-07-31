"""Backend SQLite para Gestão de Pagamentos (desenvolvimento local)."""
import sqlite3
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(__file__).parent / "data" / "pagamentos.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS contas_bancarias (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nome         TEXT NOT NULL,
            banco        TEXT,
            saldo_minimo REAL DEFAULT 0,
            ativo        INTEGER DEFAULT 1,
            criado_em    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS saldos_bancarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conta_id        INTEGER REFERENCES contas_bancarias(id) ON DELETE CASCADE,
            valor           REAL NOT NULL DEFAULT 0,
            saldo_reservado REAL NOT NULL DEFAULT 0,
            data_referencia TEXT NOT NULL,
            observacao      TEXT,
            usuario         TEXT,
            criado_em       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS pagamentos_overrides (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa           TEXT NOT NULL,
            codigo            TEXT NOT NULL,
            selecionado       INTEGER DEFAULT 0,
            conta_origem_id   INTEGER REFERENCES contas_bancarias(id) ON DELETE SET NULL,
            centro_custo      TEXT,
            projeto           TEXT,
            valor_juros       REAL DEFAULT 0,
            valor_desconto    REAL DEFAULT 0,
            prioridade_manual TEXT,
            status            TEXT DEFAULT 'Pendente de análise',
            observacao        TEXT,
            valor_aprovado    REAL,
            atualizado_em     TEXT DEFAULT (datetime('now','localtime')),
            atualizado_por    TEXT,
            UNIQUE(empresa, codigo)
        );

        CREATE TABLE IF NOT EXISTS pagamentos_historico (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa        TEXT NOT NULL,
            codigo         TEXT NOT NULL,
            acao           TEXT NOT NULL,
            valor_anterior TEXT,
            valor_novo     TEXT,
            usuario        TEXT,
            criado_em      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS rodadas_pagamento (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            criado_em      TEXT DEFAULT (datetime('now','localtime')),
            usuario        TEXT,
            total_titulos  INTEGER DEFAULT 0,
            valor_bruto    REAL DEFAULT 0,
            valor_juros    REAL DEFAULT 0,
            valor_desconto REAL DEFAULT 0,
            valor_liquido  REAL DEFAULT 0,
            saldos_antes   TEXT,
            pagamentos     TEXT,
            alertas        TEXT,
            observacao     TEXT
        );
        """)


init_db()


def _row(r) -> dict:
    return dict(r) if r is not None else None


# ── Contas bancárias ───────────────────────────────────────────────────────────

def list_contas_bancarias(somente_ativas: bool = True) -> list:
    with _conn() as conn:
        sql = "SELECT * FROM contas_bancarias"
        if somente_ativas:
            sql += " WHERE ativo = 1"
        sql += " ORDER BY nome"
        return [_row(r) for r in conn.execute(sql).fetchall()]


def insert_conta_bancaria(nome: str, banco: str = "", saldo_minimo: float = 0) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO contas_bancarias (nome, banco, saldo_minimo) VALUES (?,?,?)",
            (nome, banco, saldo_minimo),
        )
        return cur.lastrowid


def update_conta_bancaria(id, data: dict):
    if not data:
        return
    cols = ", ".join(f"{k}=?" for k in data)
    with _conn() as conn:
        conn.execute(f"UPDATE contas_bancarias SET {cols} WHERE id=?", (*data.values(), id))


def desativar_conta_bancaria(id):
    with _conn() as conn:
        conn.execute("UPDATE contas_bancarias SET ativo=0 WHERE id=?", (id,))


# ── Saldos ─────────────────────────────────────────────────────────────────────

def insert_saldo(conta_id, valor: float, saldo_reservado: float = 0,
                  data_referencia: date = None, observacao: str = "", usuario: str = "") -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO saldos_bancarios (conta_id, valor, saldo_reservado, data_referencia, observacao, usuario) "
            "VALUES (?,?,?,?,?,?)",
            (conta_id, valor, saldo_reservado, (data_referencia or date.today()).isoformat(), observacao, usuario),
        )
        return cur.lastrowid


def ultimos_saldos() -> dict:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM saldos_bancarios ORDER BY data_referencia DESC, criado_em DESC"
        ).fetchall()
    latest = {}
    for r in rows:
        r = _row(r)
        if r["conta_id"] not in latest:
            latest[r["conta_id"]] = r
    return latest


def historico_saldos(conta_id) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM saldos_bancarios WHERE conta_id=? ORDER BY data_referencia DESC, criado_em DESC",
            (conta_id,),
        ).fetchall()
        return [_row(r) for r in rows]


# ── Overrides ──────────────────────────────────────────────────────────────────

def list_overrides(empresas: list = None) -> dict:
    with _conn() as conn:
        if empresas:
            marks = ",".join("?" * len(empresas))
            rows = conn.execute(
                f"SELECT * FROM pagamentos_overrides WHERE empresa IN ({marks})", empresas
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pagamentos_overrides").fetchall()
    out = {}
    for r in rows:
        r = _row(r)
        r["selecionado"] = bool(r["selecionado"])
        out[(r["empresa"], str(r["codigo"]))] = r
    return out


def upsert_override(empresa: str, codigo: str, data: dict):
    data = dict(data)
    if "selecionado" in data:
        data["selecionado"] = 1 if data["selecionado"] else 0
    data["atualizado_em"] = datetime.now().isoformat()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM pagamentos_overrides WHERE empresa=? AND codigo=?", (empresa, str(codigo))
        ).fetchone()
        if existing:
            cols = ", ".join(f"{k}=?" for k in data)
            conn.execute(
                f"UPDATE pagamentos_overrides SET {cols} WHERE id=?",
                (*data.values(), existing["id"]),
            )
        else:
            data["empresa"], data["codigo"] = empresa, str(codigo)
            cols = ", ".join(data.keys())
            marks = ", ".join("?" * len(data))
            conn.execute(
                f"INSERT INTO pagamentos_overrides ({cols}) VALUES ({marks})", tuple(data.values())
            )


def registrar_historico(empresa: str, codigo: str, acao: str,
                         valor_anterior=None, valor_novo=None, usuario: str = ""):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO pagamentos_historico (empresa, codigo, acao, valor_anterior, valor_novo, usuario) "
            "VALUES (?,?,?,?,?,?)",
            (empresa, str(codigo), acao,
             str(valor_anterior) if valor_anterior is not None else None,
             str(valor_novo) if valor_novo is not None else None, usuario),
        )


def historico_titulo(empresa: str, codigo: str) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pagamentos_historico WHERE empresa=? AND codigo=? ORDER BY criado_em DESC",
            (empresa, str(codigo)),
        ).fetchall()
        return [_row(r) for r in rows]


# ── Rodadas ────────────────────────────────────────────────────────────────────

def salvar_rodada(data: dict) -> int:
    import json
    payload = dict(data)
    for campo in ("saldos_antes", "pagamentos", "alertas"):
        if campo in payload and not isinstance(payload[campo], str):
            payload[campo] = json.dumps(payload[campo], ensure_ascii=False, default=str)
    with _conn() as conn:
        cols = ", ".join(payload.keys())
        marks = ", ".join("?" * len(payload))
        cur = conn.execute(f"INSERT INTO rodadas_pagamento ({cols}) VALUES ({marks})", tuple(payload.values()))
        return cur.lastrowid


def list_rodadas(limit: int = 20) -> list:
    import json
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM rodadas_pagamento ORDER BY criado_em DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        r = _row(r)
        for campo in ("saldos_antes", "pagamentos", "alertas"):
            if r.get(campo):
                try:
                    r[campo] = json.loads(r[campo])
                except Exception:
                    pass
        out.append(r)
    return out
