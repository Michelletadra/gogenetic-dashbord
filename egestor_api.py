import time
import threading
from typing import Optional

import requests

BASE_URL = "https://api.egestor.com.br/api"
TOKEN_URL = f"{BASE_URL}/oauth/access_token"
API_URL = f"{BASE_URL}/v1"


class EgestorClient:
    def __init__(self, personal_token: str, company_name: str):
        self.personal_token = personal_token
        self.company_name = company_name
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._request_times: list = []
        self._lock = threading.RLock()   # protege token + rate-limit em chamadas paralelas

    def _get_access_token(self) -> str:
        with self._lock:
            now = time.time()
            if self._access_token and now < self._token_expires_at - 60:
                return self._access_token
            resp = requests.post(
                TOKEN_URL,
                json={"grant_type": "personal", "personal_token": self.personal_token},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = now + data.get("expires_in", 900)
            return self._access_token

    def _rate_limit(self):
        with self._lock:
            now = time.time()
            self._request_times = [t for t in self._request_times if now - t < 60]
            if len(self._request_times) >= 55:
                wait = 61 - (now - self._request_times[0])
                if wait > 0:
                    time.sleep(wait)
            self._request_times.append(time.time())

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        self._rate_limit()
        token = self._get_access_token()
        resp = requests.get(
            f"{API_URL}/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=20,
        )
        if resp.status_code == 429:
            time.sleep(65)
            return self._get(endpoint, params)
        resp.raise_for_status()
        return resp.json()

    def _get_all_pages(self, endpoint: str, params: Optional[dict] = None) -> list:
        params = dict(params or {})
        all_data: list = []
        page = 1
        while True:
            params["page"] = page
            result = self._get(endpoint, params)
            batch = result.get("data", [])
            all_data.extend(batch)
            if page >= result.get("last_page", 1):
                break
            page += 1
        return all_data

    def get_empresa(self) -> dict:
        return self._get("empresa")

    def get_vendas(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("vendas", {
            "tipo": 50,
            "dtTipo": "dtVenda",
            "dtIni": dt_ini,
            "dtFim": dt_fim,
            "fields": "codigo,dtVenda,valorTotal,valorFinanc,nomeContato,codVendedor,nomeVendedor,situacao",
            "orderBy": "nomeVendedor,asc",
        })

    def get_faturamento(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("recebimentos", {
            "situFin": 40,
            "dtTipo": "dtPgto",
            "dtIni": dt_ini,
            "dtFim": dt_fim,
            "fields": "codigo,descricao,valor,dtPgto,nomeContato,situacao,origem",
        })

    def get_contas_receber(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("recebimentos", {
            "situFin": 20,
            "dtTipo": "dtVenc",
            "dtIni": dt_ini,
            "dtFim": dt_fim,
            "fields": "codigo,descricao,valor,dtVenc,nomeContato,situacao,origem",
        })

    def get_contas_pagar(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("pagamentos", {
            "situFin": 10,
            "dtTipo": "dtVenc",
            "dtIni": dt_ini,
            "dtFim": dt_fim,
            "fields": "codigo,descricao,valor,dtVenc,nomeContato,situacao,origem",
        })

    def get_vencidas_receber(self) -> list:
        from datetime import date, timedelta
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._get_all_pages("recebimentos", {
            "situFin": 20,
            "dtTipo": "dtVenc",
            "dtIni": "2020-01-01",
            "dtFim": ontem,
            "fields": "codigo,descricao,valor,dtVenc,nomeContato,situacao",
        })

    def get_vencidas_pagar(self) -> list:
        from datetime import date, timedelta
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._get_all_pages("pagamentos", {
            "situFin": 10,
            "dtTipo": "dtVenc",
            "dtIni": "2020-01-01",
            "dtFim": ontem,
            "fields": "codigo,descricao,valor,dtVenc,nomeContato,situacao",
        })

    def get_servicos(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("vendas", {
            "tipo": 10,
            "dtTipo": "dtVenda",
            "dtIni": dt_ini,
            "dtFim": dt_fim,
            "fields": "codigo,nomeContato,nomeVendedor,dtVenda,dtEntrega,valorTotal,situacao,situacaoOS,tags,ativo",
            "orderBy": "dtVenda,desc",
        })

    def get_pagamentos_realizados(self, dt_ini: str, dt_fim: str) -> list:
        """Pagamentos efetivamente pagos (situFin=30), ordenados por dtPgto."""
        return self._get_all_pages("pagamentos", {
            "situFin": 30,
            "dtTipo": "dtPgto",
            "dtIni": dt_ini,
            "dtFim": dt_fim,
            "fields": "codigo,descricao,valor,dtPgto,dtVenc,nomeContato,situacao,codPlanoContas,origem",
        })

    def get_plano_contas(self) -> list:
        """Retorna todos os registros do plano de contas."""
        return self._get_all_pages("planoContas", {})

    def get_vendas_12m(self) -> list:
        from datetime import date
        dt_fim = date.today()
        dt_ini = dt_fim.replace(year=dt_fim.year - 1)
        return self._get_all_pages("vendas", {
            "tipo": 50,
            "dtTipo": "dtVenda",
            "dtIni": dt_ini.strftime("%Y-%m-%d"),
            "dtFim": dt_fim.strftime("%Y-%m-%d"),
            "fields": "codigo,dtVenda,valorTotal,nomeContato,nomeVendedor",
        })
