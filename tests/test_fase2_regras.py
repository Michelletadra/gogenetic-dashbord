"""Fase 2 — regras de Fluxo (projeção) e Contratos (execução). Só dados simulados."""
from datetime import date

from fluxo_regras import (classificar_parcela, parcelas_como_fluxo, projecao_semanal,
                          pior_semana, execucao_contratos, empresa_dashboard,
                          PENDENTE, FATURADA, CANCELADA, NAO_CLASSIFICADA)

HOJE = date(2026, 10, 22)  # quinta-feira


def test_classificacao_parcelas():
    assert classificar_parcela({"situacao": "EM ESPERA"}) == PENDENTE
    assert classificar_parcela({"situacao": "A faturar"}) == PENDENTE
    assert classificar_parcela({"situacao": None}) == PENDENTE
    assert classificar_parcela({"situacao": "Faturado"}) == FATURADA
    assert classificar_parcela({"situacao": "PAGO"}) == FATURADA
    assert classificar_parcela({"situacao": "em espera", "numero_nf": "123"}) == FATURADA
    assert classificar_parcela({"situacao": "Cancelada"}) == CANCELADA
    assert classificar_parcela({"situacao": "aguardando cliente xyz"}) == NAO_CLASSIFICADA


def test_mapa_empresas_explicito():
    assert empresa_dashboard("GG SOLUÇÕES") == "GoGenetic Soluções"
    assert empresa_dashboard("GG PESQUISA") == "GoGenetic Pesquisa"
    assert empresa_dashboard("GOSOLOS") == "GoSolos"
    assert empresa_dashboard("GOGENETIC") == "GoGenetic You"
    assert empresa_dashboard("Outra") is None


def test_parcelas_como_fluxo_filtra_periodo_e_separa_problemas():
    ctrs = [{"id": 1, "contratante": "Cliente A", "empresa_gg": "GG PESQUISA", "nome_contrato": "A"}]
    parc = [
        {"contrato_id": 1, "numero": 1, "data_emissao": "2026-10-30", "valor": 100, "situacao": "EM ESPERA"},
        {"contrato_id": 1, "numero": 2, "data_emissao": "2026-12-30", "valor": 100, "situacao": "EM ESPERA"},
        {"contrato_id": 1, "numero": 3, "data_emissao": "2026-10-25", "valor": 100, "situacao": "FATURADO"},
        {"contrato_id": 1, "numero": 4, "data_emissao": None, "valor": 50, "situacao": "EM ESPERA"},
        {"contrato_id": 1, "numero": 5, "data_emissao": "2026-10-28", "valor": 70, "situacao": "??"},
        {"contrato_id": 1, "numero": 6, "data_emissao": "30/10/2026", "valor": 10, "situacao": ""},
        {"contrato_id": 1, "numero": 7, "data_emissao": None, "valor": 0, "situacao": "EM ESPERA"},  # marcador
    ]
    r = parcelas_como_fluxo(parc, ctrs, HOJE, date(2026, 11, 30))
    assert sorted(p["valor"] for p in r["no_periodo"]) == [10.0, 100.0]
    assert [p["valor"] for p in r["sem_data"]] == [50.0]
    assert [p["valor"] for p in r["nao_classificadas"]] == [70.0]
    assert r["no_periodo"][0]["empresa"] == "GoGenetic Pesquisa"


def test_projecao_nao_inclui_vencidos_e_acumula():
    rec = [{"dtVenc": "2026-10-20", "valor": 999},   # vencido: fora
           {"dtVenc": "2026-10-23", "valor": 100},   # semana 0
           {"dtVenc": "2026-11-03", "valor": 50}]    # semana 2
    ctr = [{"dtVenc": "2026-10-26", "valor": 30}]    # semana 1
    pag = [{"dtVenc": "2026-10-24", "valor": 300}]   # semana 0
    p = projecao_semanal(rec, ctr, pag, HOJE, 13)
    assert len(p) == 13 and p[0]["semana"] == date(2026, 10, 19)
    assert (p[0]["entradas"], p[0]["pagar"], p[0]["acumulado"]) == (100, 300, -200)
    assert p[1]["contratos"] == 30 and p[1]["acumulado"] == -170
    assert p[2]["receber"] == 50 and p[-1]["acumulado"] == -120
    assert pior_semana(p)["semana"] == date(2026, 10, 19)
    # nada é contado duas vezes: soma das semanas = soma dos itens no horizonte
    assert sum(l["liquido"] for l in p) == 100 + 50 + 30 - 300


def test_projecao_fora_do_horizonte():
    p = projecao_semanal([{"dtVenc": "2027-06-01", "valor": 1}], [], [], HOJE, 13)
    assert all(l["entradas"] == 0 for l in p)


def test_execucao_contratos_alertas():
    ctrs = [
        {"id": 1, "contratante": "A", "valor_total": 300, "data_termino": "2027-01-01", "status_real": "ATIVO"},
        {"id": 2, "contratante": "B", "valor_total": 0, "data_termino": None},
    ]
    parc = [
        {"contrato_id": 1, "valor": 100, "situacao": "FATURADO"},
        {"contrato_id": 1, "valor": 100, "situacao": "EM ESPERA"},
        {"contrato_id": 1, "valor": 50, "situacao": "CANCELADO"},
    ]
    ex = {e["id"]: e for e in execucao_contratos(ctrs, parc)}
    a = ex[1]
    assert (a["faturado"], a["a_faturar"], a["parcelado"]) == (100, 100, 200)
    assert round(a["pct_faturado"]) == 33
    assert "parcelas ≠ valor total" in a["alertas"]
    b = ex[2]
    assert set(b["alertas"]) >= {"valor total não informado", "sem data de término", "sem parcelas cadastradas"}
    assert b["pct_faturado"] is None
