"""
Migração SQLite → Supabase para contratos, parcelas e aditivos.

Uso:
    python migrate_contratos_supabase.py           # migra se Supabase estiver vazio
    python migrate_contratos_supabase.py --force   # limpa e re-migra
"""
import sys
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from supabase import create_client

SQLITE_PATH = Path(__file__).parent / "data" / "creditos.db"
FORCE = "--force" in sys.argv

def _sqlite():
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    return conn

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", ""))

# ── Verifica se já existe dados ───────────────────────────────────────────────
r = sb.table("contratos").select("id", count="exact").execute()
existing = r.count or 0

if existing > 0:
    if FORCE:
        print(f"⚠️  --force: limpando {existing} contratos no Supabase...")
        sb.table("contrato_aditivos").delete().gt("id", 0).execute()
        sb.table("contrato_parcelas").delete().gt("id", 0).execute()
        sb.table("contratos").delete().gt("id", 0).execute()
        print("   Limpo ✓")
    else:
        print(f"⚠️  Já existem {existing} contrato(s) no Supabase. Use --force para re-migrar.")
        sys.exit(1)

# ── Mapeamento de clientes SQLite → Supabase ──────────────────────────────────
print("\n🔗 Mapeando clientes SQLite → Supabase...")

sqlite_clientes = {}  # sqlite_id → nome
with _sqlite() as conn:
    for row in conn.execute("SELECT id, nome FROM clientes").fetchall():
        sqlite_clientes[row["id"]] = row["nome"]

sb_clientes = {}  # nome → supabase_id
for row in sb.table("clientes").select("id, nome").execute().data:
    sb_clientes[row["nome"]] = row["id"]

client_map = {}  # sqlite_id → supabase_id
not_found = []
for sq_id, nome in sqlite_clientes.items():
    if nome in sb_clientes:
        client_map[sq_id] = sb_clientes[nome]
    else:
        not_found.append(nome)

print(f"   {len(client_map)}/{len(sqlite_clientes)} clientes mapeados")
if not_found:
    print(f"   ⚠️  Não encontrados no Supabase: {', '.join(not_found)}")

# ── Migração de contratos ─────────────────────────────────────────────────────
SKIP = {"id", "created_at", "updated_at", "cliente_nome", "status_real"}

print("\n📋 Migrando contratos...")
with _sqlite() as conn:
    contratos_sqlite = [dict(r) for r in conn.execute("SELECT * FROM contratos").fetchall()]

contrato_id_map = {}  # sqlite_id → supabase_id
ok = 0
erros = 0

for c in contratos_sqlite:
    sq_id = c["id"]
    d = {k: v for k, v in c.items() if k not in SKIP}

    # Remapeia cliente_id para o ID do Supabase
    if d.get("cliente_id"):
        d["cliente_id"] = client_map.get(d["cliente_id"])  # None se não encontrado

    try:
        r = sb.table("contratos").insert(d).execute()
        sb_id = r.data[0]["id"]
        contrato_id_map[sq_id] = sb_id
        icon = "🟢" if c.get("status") != "ENCERRADO" else "⚪"
        print(f"  {icon} {c.get('contratante','?'):<30} id={sq_id}→{sb_id}")
        ok += 1
    except Exception as e:
        print(f"  ❌ Erro contrato id={sq_id} ({c.get('contratante','?')}): {e}")
        erros += 1

print(f"\n   ✅ {ok} contratos migrados, {erros} erro(s)")

# ── Migração de parcelas ──────────────────────────────────────────────────────
print("\n📦 Migrando parcelas...")
with _sqlite() as conn:
    parcelas_sqlite = [dict(r) for r in conn.execute(
        "SELECT * FROM contrato_parcelas"
    ).fetchall()]

ok_p = 0
skip_p = 0
erros_p = 0

for p in parcelas_sqlite:
    sq_cid = p.get("contrato_id")
    if sq_cid not in contrato_id_map:
        skip_p += 1
        continue
    d = {k: v for k, v in p.items() if k not in ("id", "created_at")}
    d["contrato_id"] = contrato_id_map[sq_cid]
    try:
        sb.table("contrato_parcelas").insert(d).execute()
        ok_p += 1
    except Exception as e:
        print(f"  ❌ Erro parcela: {e}")
        erros_p += 1

print(f"   ✅ {ok_p} parcelas migradas, {skip_p} ignoradas, {erros_p} erro(s)")

# ── Migração de aditivos ──────────────────────────────────────────────────────
print("\n📎 Migrando aditivos...")
with _sqlite() as conn:
    aditivos_sqlite = [dict(r) for r in conn.execute(
        "SELECT * FROM contrato_aditivos"
    ).fetchall()]

ok_a = 0
erros_a = 0

for a in aditivos_sqlite:
    sq_cid = a.get("contrato_id")
    if sq_cid not in contrato_id_map:
        continue
    d = {k: v for k, v in a.items() if k not in ("id", "created_at")}
    d["contrato_id"] = contrato_id_map[sq_cid]
    try:
        sb.table("contrato_aditivos").insert(d).execute()
        ok_a += 1
    except Exception as e:
        print(f"  ❌ Erro aditivo: {e}")
        erros_a += 1

print(f"   ✅ {ok_a} aditivos migrados, {erros_a} erro(s)")

print(f"""
🎉 Migração concluída!
   Contratos : {ok}
   Parcelas  : {ok_p}
   Aditivos  : {ok_a}
""")
