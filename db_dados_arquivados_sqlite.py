"""Backend SQLite para desenvolvimento local — arquivo de dados históricos."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "dados_arquivados.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init():
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS dados_arquivados (
            empresa   TEXT NOT NULL,
            chave     TEXT NOT NULL,
            dados     TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (empresa, chave)
        );
        """)


_init()


def get_arquivado(empresa: str, chave: str):
    with _conn() as conn:
        row = conn.execute(
            "SELECT dados FROM dados_arquivados WHERE empresa = ? AND chave = ?",
            (empresa, chave),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["dados"])


def salvar_arquivado(empresa: str, chave: str, dados) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dados_arquivados (empresa, chave, dados) VALUES (?, ?, ?)",
            (empresa, chave, json.dumps(dados, ensure_ascii=False)),
        )
