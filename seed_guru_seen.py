"""Marca todos os pedidos do Guru dos últimos 2 anos como 'já vistos', pra
não inundar o destaque de 'pedidos novos' com o histórico inteiro na
primeira execução da feature. Rodar uma única vez, localmente:

    python seed_guru_seen.py
"""
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

from guru_api import GuruClient
import db_guru_seen
import os

token = os.getenv("GURU_API_TOKEN")
if not token:
    raise SystemExit("GURU_API_TOKEN não encontrado no .env")

client = GuruClient(token)
dt_ini = (date.today() - timedelta(days=730)).strftime("%Y-%m-%d")
dt_fim = date.today().strftime("%Y-%m-%d")

txs = client.get_transacoes(dt_ini, dt_fim)
ids = [t.get("id") for t in txs if t.get("id")]
print(f"{len(ids)} pedidos encontrados no histórico, marcando como vistos...")
db_guru_seen.mark_seen(ids)
print("Pronto.")
