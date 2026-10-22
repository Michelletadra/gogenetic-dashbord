"""Regras determinísticas da Fase 2 (Fluxo e Contratos) — sem Streamlit, testáveis.

Nada aqui grava dados: só lê listas já carregadas e devolve números/tabelas.
"""
from __future__ import annotations

import unicodedata
from datetime import date, timedelta
from typing import Iterable, Optional


# ── Situação das parcelas de contrato ──────────────────────────────────────────
# O campo `situacao` vem das planilhas de origem (texto livre). Classificação
# conservadora: o que não for reconhecido fica como "nao_classificada" e é
# mostrado à parte — nunca entra na projeção como receita.
PENDENTE, FATURADA, CANCELADA, NAO_CLASSIFICADA = "pendente", "faturada", "cancelada", "nao_classificada"


def _norm(txt) -> str:
    s = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def classificar_parcela(p: dict) -> str:
    sit = _norm(p.get("situacao"))
    if "CANCEL" in sit:
        return CANCELADA
    if str(p.get("numero_nf") or "").strip():
        return FATURADA
    if any(k in sit for k in ("FATUR", "PAGO", "PAGA", "RECEB", "EMITID", "QUITAD", "LIQUID", "NF ")):
        # "A FATURAR" contém "FATUR" mas é pendente — tratado abaixo
        if "A FATURAR" in sit:
            return PENDENTE
        return FATURADA
    if sit == "" or any(k in sit for k in ("ESPERA", "ABERT", "PENDENT", "A FATURAR", "PREVIST")):
        return PENDENTE
    return NAO_CLASSIFICADA


def _data(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    try:
        if len(s) == 10 and s[4] == "-":
            return date.fromisoformat(s)
        if len(s) == 10 and s[2] == "/":
            d, m, a = s.split("/")
            return date(int(a), int(m), int(d))
    except ValueError:
        return None
    return None


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def parcelas_como_fluxo(parcelas: Iterable[dict], contratos: Iterable[dict],
                        dt_ini: date, dt_fim: date) -> dict:
    """Parcelas de contrato PENDENTES (ainda sem faturamento) no período, no
    formato dos itens do Fluxo. Devolve também as não classificadas e as sem
    data, para exibição à parte (não entram na soma)."""
    por_id = {c.get("id"): c for c in contratos}
    no_periodo, sem_data, nao_class = [], [], []
    for p in parcelas:
        classe = classificar_parcela(p)
        if classe in (FATURADA, CANCELADA):
            continue
        c = por_id.get(p.get("contrato_id"), {})
        dt = _data(p.get("data_emissao"))
        valor = _num(p.get("saldo_atual")) or _num(p.get("valor"))
        item = {
            "valor": valor,
            "dtVenc": dt.isoformat() if dt else "",
            "nomeContato": c.get("contratante") or "—",
            "empresa": empresa_dashboard(c.get("empresa_gg")) or (c.get("empresa_gg") or "—"),
            "_empresa_mapeada": empresa_dashboard(c.get("empresa_gg")) is not None,
            "descricao": f"Contrato {c.get('nome_contrato') or c.get('contratante') or p.get('contrato_id')}"
                         f" — Parcela {p.get('numero') or '?'}",
            "situacao": p.get("situacao") or "",
            "_origem": "contrato",
        }
        if classe == PENDENTE and valor == 0 and dt is None:
            # parcela "em espera" sem valor e sem data: marcador do cadastro, não previsão
            continue
        if classe == NAO_CLASSIFICADA:
            nao_class.append(item)
        elif dt is None:
            sem_data.append(item)
        elif dt_ini <= dt <= dt_fim:
            no_periodo.append(item)
    return {"no_periodo": no_periodo, "sem_data": sem_data, "nao_classificadas": nao_class}


# ── Empresa do contrato → empresa do dashboard ─────────────────────────────────
# O cadastro de contratos usa abreviações (campo empresa_gg). Mapeamento
# EXPLÍCITO, baseado na própria página Contratos (EMPRESAS e _EMPRESA_LABEL:
# "GOGENETIC" é exibido como "GG YOU"). Valor fora da lista não é atribuído a
# nenhuma empresa — só aparece em "Todas".
MAPA_EMPRESA_CONTRATO = {
    "GG PESQUISA": "GoGenetic Pesquisa", "GOGENETIC PESQUISA": "GoGenetic Pesquisa",
    "GG SOLUCOES": "GoGenetic Soluções", "GOGENETIC SOLUCOES": "GoGenetic Soluções",
    "GOSOLOS": "GoSolos", "GO SOLOS": "GoSolos",
    "GOGENETIC YOU": "GoGenetic You", "GG YOU": "GoGenetic You", "GOGENETIC": "GoGenetic You",
}


def empresa_dashboard(empresa_gg) -> Optional[str]:
    return MAPA_EMPRESA_CONTRATO.get(_norm(empresa_gg))


# ── Projeção semanal ───────────────────────────────────────────────────────────
def inicio_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def projecao_semanal(receber: Iterable[dict], contratos: Iterable[dict],
                     pagar: Iterable[dict], hoje: date, semanas: int = 13) -> list[dict]:
    """Entradas e saídas esperadas por semana (segunda a domingo), a partir da
    semana de `hoje`. Itens vencidos (antes de hoje) NÃO entram: aparecem à
    parte na página, para não serem tratados como recebimento certo.
    Sem saldo bancário inicial: o acumulado é a posição líquida a partir de zero."""
    s0 = inicio_semana(hoje)
    linhas = [{"semana": s0 + timedelta(weeks=i), "receber": 0.0, "contratos": 0.0,
               "pagar": 0.0} for i in range(semanas)]
    fim = s0 + timedelta(weeks=semanas)

    def _soma(itens, campo):
        for it in itens:
            d = _data(it.get("dtVenc"))
            if d is None or d < hoje or d >= fim:
                continue
            linhas[(inicio_semana(d) - s0).days // 7][campo] += _num(it.get("valor"))

    _soma(receber, "receber")
    _soma(contratos, "contratos")
    _soma(pagar, "pagar")
    acum = 0.0
    for l in linhas:
        l["entradas"] = l["receber"] + l["contratos"]
        l["liquido"] = l["entradas"] - l["pagar"]
        acum += l["liquido"]
        l["acumulado"] = acum
    return linhas


def pior_semana(linhas: list[dict]) -> Optional[dict]:
    """Semana com a menor posição acumulada (ponto de maior aperto)."""
    return min(linhas, key=lambda l: l["acumulado"]) if linhas else None


# ── Execução de contratos (com os dados já existentes) ─────────────────────────
def execucao_contratos(contratos: Iterable[dict], parcelas: Iterable[dict]) -> list[dict]:
    """Por contrato: valor contratado, parcelado, faturado (parcelas com NF ou
    situação de faturada), a faturar (parcelas pendentes) e alertas de cadastro.
    Não usa OS nem recebimentos do ERP — o vínculo contrato↔OS não existe no
    cadastro hoje; isso é dito na tela."""
    por_contrato: dict = {}
    for p in parcelas:
        por_contrato.setdefault(p.get("contrato_id"), []).append(p)
    out = []
    for c in contratos:
        ps = por_contrato.get(c.get("id"), [])
        contratado = _num(c.get("valor_total"))
        parcelado = faturado = a_faturar = nao_class = 0.0
        for p in ps:
            v = _num(p.get("valor"))
            classe = classificar_parcela(p)
            if classe == CANCELADA:
                continue
            parcelado += v
            if classe == FATURADA:
                faturado += v
            elif classe == PENDENTE:
                a_faturar += v
            else:
                nao_class += v
        alertas = []
        if contratado <= 0:
            alertas.append("valor total não informado")
        if not c.get("data_termino"):
            alertas.append("sem data de término")
        if ps and contratado > 0 and abs(parcelado - contratado) > 0.01:
            alertas.append("parcelas ≠ valor total")
        if not ps:
            alertas.append("sem parcelas cadastradas")
        if nao_class:
            alertas.append("parcela com situação não reconhecida")
        out.append({
            "id": c.get("id"),
            "contrato": c.get("nome_contrato") or c.get("contratante") or "—",
            "contratante": c.get("contratante") or "—",
            "empresa": c.get("empresa_gg") or "—",
            "status": c.get("status_real") or c.get("status") or "—",
            "termino": c.get("data_termino") or "",
            "contratado": contratado,
            "parcelado": parcelado,
            "faturado": faturado,
            "a_faturar": a_faturar,
            "nao_classificado": nao_class,
            "pct_faturado": (faturado / contratado * 100) if contratado > 0 else None,
            "n_parcelas": len(ps),
            "alertas": alertas,
        })
    return out
