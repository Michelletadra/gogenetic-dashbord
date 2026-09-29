"""Baixa automática de créditos a partir do eGestor.

Regra (definida pela Michelle em 2026-09-29):
- Quando um serviço/OS no eGestor está com a SITUAÇÃO "Consumo de crédito"
  (no lugar de "Em execução", por exemplo), o sistema dá baixa do valor total
  do pedido na carteira de créditos do cliente.
- De qual crédito sai: o que vence antes sai antes (FIFO por vencimento). Se
  o primeiro não cobrir, continua no próximo. Se acabar o saldo, o restante
  fica negativo no último crédito e aparece como alerta.
- Cada pedido é baixado UMA única vez (registro em creditos_auto_log).
  Se alguém apagar a movimentação automática, o pedido não volta a ser baixado.
- Se não der pra decidir sozinho (cliente não encontrado, mais de um cliente
  com nome parecido, cliente sem crédito válido), o pedido fica 'pendente'
  e aparece na tela para alguém resolver. É tentado de novo a cada execução.

Este módulo não depende do Streamlit: roda dentro do app (ao abrir a tela ou
no botão "Sincronizar") e também sozinho, de hora em hora, pelo GitHub Actions
(`python creditos_sync.py`). Os logs NÃO mostram nomes de clientes nem valores,
porque o repositório é público e os logs do GitHub Actions também.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import date, timedelta

import db_creditos as db

RESPONSAVEL_AUTO = "Automático (eGestor)"
ORIGEM_AUTO = "auto_egestor"


def _cfg(key: str, default: str) -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def situacao_gatilho() -> str:
    """Nome da situação no eGestor que dispara a baixa (sem acento, minúsculo)."""
    return normalizar(_cfg("CREDITO_SITUACAO_GATILHO", "consumo de credito"))


def normalizar(txt) -> str:
    txt = unicodedata.normalize("NFKD", str(txt or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c)).lower()
    txt = re.sub(r"[^a-z0-9 ]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


_SUFIXOS = {"ltda", "me", "epp", "eireli", "sa", "s a", "ss", "mei"}


def _nome_base(txt) -> str:
    """Nome sem sufixos societários, pra comparar razão social x nome curto."""
    palavras = [p for p in normalizar(txt).split() if p not in _SUFIXOS]
    return " ".join(palavras)


def _texto_situacao(valor) -> str:
    if isinstance(valor, dict):
        return str(valor.get("nome") or valor.get("descricao") or valor.get("situacao") or "")
    return str(valor or "")


def _textos_tags(tags) -> list:
    if not tags:
        return []
    itens = tags if isinstance(tags, list) else str(tags).split(",")
    out = []
    for t in itens:
        out.append(str(t.get("nome") or t.get("tag") or "") if isinstance(t, dict) else str(t))
    return out


def tem_gatilho(servico: dict, gatilho: str | None = None) -> bool:
    """True se a situação da OS (ou, por segurança, uma tag) é o gatilho."""
    gatilho = gatilho or situacao_gatilho()
    candidatos = [_texto_situacao(servico.get("situacaoOS")),
                  _texto_situacao(servico.get("situacao"))]
    candidatos += _textos_tags(servico.get("tags"))
    return any(gatilho and gatilho in normalizar(c) for c in candidatos)


def encontrar_cliente(nome_contato: str, clientes: list):
    """Devolve (cliente, motivo). cliente=None quando não dá pra decidir."""
    alvo = _nome_base(nome_contato)
    if not alvo:
        return None, "Pedido sem nome de cliente no eGestor"
    exatos = [c for c in clientes if _nome_base(c.get("nome")) == alvo]
    if len(exatos) == 1:
        return exatos[0], ""
    if len(exatos) > 1:
        return None, "Mais de um cliente com o mesmo nome na carteira de créditos"
    parecidos = []
    for c in clientes:
        n = _nome_base(c.get("nome"))
        if n and len(n) >= 4 and len(alvo) >= 4 and (alvo in n or n in alvo):
            parecidos.append(c)
    if len(parecidos) == 1:
        return parecidos[0], ""
    if len(parecidos) > 1:
        return None, "Mais de um cliente com nome parecido na carteira de créditos"
    return None, "Cliente não encontrado na carteira de créditos"


def chave_empresa(nome: str) -> str:
    """Nome fixo da empresa pro registro de baixas, independente de como o
    nome aparece nos Secrets (dashboard, app de Créditos e GitHub Actions
    podem ter variações). Evita que o mesmo pedido seja visto como "novo"
    só porque o nome da empresa foi escrito diferente em algum lugar."""
    n = normalizar(nome)
    if "pesquisa" in n:
        return "GoGenetic Pesquisa"
    if "solucoes" in n:
        return "GoGenetic Soluções"
    if "solos" in n:
        return "GoSolos"
    return nome


def _saldos_por_credito(creditos: list, movs: list) -> dict:
    """Mesma regra da tela: UTILIZAÇÃO/USO/AJUSTE debitam, ESTORNO devolve."""
    debito = {}
    for m in movs:
        cid = m.get("credito_id")
        v = float(m.get("valor") or 0)
        debito[cid] = debito.get(cid, 0.0) + (-v if m.get("tipo") == "ESTORNO" else v)
    return {c["id"]: float(c.get("valor_original") or 0) - debito.get(c["id"], 0.0)
            for c in creditos}


def planejar_baixa(valor: float, creditos_cliente: list, saldos: dict, hoje: date):
    """Divide o valor entre os créditos do cliente (vence antes, sai antes).

    Devolve (lista de (credito, valor)), ou ([], motivo) se não houver crédito
    utilizável. Créditos expirados/cancelados (por status ou pela data de
    vencimento) não entram."""
    def _vence(c):
        return str(c.get("data_vencimento") or "")[:10]

    elegiveis = []
    for c in creditos_cliente:
        if (c.get("status") or "").upper() not in ("VÁLIDO", "VALIDO", "UTILIZADO"):
            continue
        venc = _vence(c)
        if venc and venc < hoje.isoformat():
            continue
        elegiveis.append(c)
    if not elegiveis:
        return [], "Cliente sem crédito válido para dar baixa"

    # Sem vencimento vai pro fim da fila; empate: o mais antigo primeiro.
    elegiveis.sort(key=lambda c: (_vence(c) or "9999-12-31", str(c.get("created_at") or ""), c["id"]))

    plano, restante = [], round(float(valor), 2)
    for c in elegiveis:
        if restante <= 0:
            break
        disp = round(saldos.get(c["id"], 0.0), 2)
        if disp <= 0:
            continue
        usar = min(disp, restante)
        plano.append((c, usar))
        restante = round(restante - usar, 2)
    if restante > 0:
        # Acabou o saldo: o que sobrar fica negativo no último crédito da fila.
        ultimo = elegiveis[-1]
        if plano and plano[-1][0]["id"] == ultimo["id"]:
            plano[-1] = (ultimo, round(plano[-1][1] + restante, 2))
        else:
            plano.append((ultimo, restante))
    return plano, ""


def sincronizar(clients: dict, dias: int = 90, hoje: date | None = None) -> dict:
    """Procura OS com a situação-gatilho nos últimos `dias` e dá baixa.

    `clients`: {nome_empresa: EgestorClient}. Devolve um resumo com contagens
    e a lista de erros por empresa (sem dados de clientes)."""
    hoje = hoje or date.today()
    gatilho = situacao_gatilho()
    resumo = {"encontrados": 0, "baixados": 0, "pendentes": 0, "ja_processados": 0,
              "valor_baixado": 0.0, "erros": []}

    dt_ini = (hoje - timedelta(days=dias)).isoformat()
    dt_fim = (hoje + timedelta(days=1)).isoformat()
    candidatos = []
    for empresa, client in clients.items():
        try:
            servicos = client.get_servicos(dt_ini, dt_fim)
        except Exception as e:
            resumo["erros"].append(f"{empresa}: falha ao ler o eGestor ({type(e).__name__})")
            continue
        for s in servicos:
            if s.get("codigo") is not None and tem_gatilho(s, gatilho):
                candidatos.append((empresa, s))
    resumo["encontrados"] = len(candidatos)
    if not candidatos:
        return resumo

    clientes = db.list_clientes()
    creditos = db.list_creditos()
    movs = db.list_movimentacoes()
    saldos = _saldos_por_credito(creditos, movs)
    cred_por_cli = {}
    for c in creditos:
        cred_por_cli.setdefault(c.get("cliente_id"), []).append(c)

    for empresa_nome, s in candidatos:
        empresa = chave_empresa(empresa_nome)
        codigo = str(s.get("codigo"))
        try:
            if not db.claim_auto_log(empresa, codigo):
                resumo["ja_processados"] += 1
                continue
        except Exception as e:
            resumo["erros"].append(
                f"Tabela creditos_auto_log indisponível — rode sql_creditos_auto.sql no Supabase ({type(e).__name__})")
            break

        valor = round(float(s.get("valorTotal") or 0), 2)
        info = {"nome_contato": s.get("nomeContato"), "valor": valor,
                "dt_venda": s.get("dtVenda"),
                "situacao": _texto_situacao(s.get("situacaoOS")) or _texto_situacao(s.get("situacao"))}

        def _pendente(motivo, cliente_id=None):
            db.update_auto_log(empresa, codigo, {**info, "status": "pendente",
                                                 "cliente_id": cliente_id, "detalhe": motivo})
            resumo["pendentes"] += 1

        try:
            if valor <= 0:
                _pendente("Pedido com valor zero no eGestor")
                continue
            cli, motivo = encontrar_cliente(s.get("nomeContato"), clientes)
            if not cli:
                _pendente(motivo)
                continue
            plano, motivo = planejar_baixa(valor, cred_por_cli.get(cli["id"], []), saldos, hoje)
            if not plano:
                _pendente(motivo, cli["id"])
                continue

            partes = []
            for cr, v in plano:
                db.insert_movimentacao({
                    "credito_id":        cr["id"],
                    "tipo":              "UTILIZAÇÃO",
                    "valor":             float(v),
                    "data":              hoje.isoformat(),
                    "responsavel":       RESPONSAVEL_AUTO,
                    "observacao":        "Baixa automática: situação 'Consumo de crédito' no eGestor",
                    "descricao_servico": f"Pedido #{codigo} ({empresa})",
                    "codigo_servico":    codigo,
                    "servico_empresa":   empresa,
                    "origem":            ORIGEM_AUTO,
                })
                saldos[cr["id"]] = round(saldos.get(cr["id"], 0.0) - v, 2)
                if saldos[cr["id"]] <= 0 and (cr.get("status") or "").upper() != "UTILIZADO":
                    db.update_credito(cr["id"], {"status": "UTILIZADO"})
                    cr["status"] = "UTILIZADO"
                partes.append(f"crédito #{cr['id']}: {v:.2f}")
            negativo = min((saldos[cr["id"]] for cr, _ in plano), default=0)
            detalhe = "; ".join(partes)
            if negativo < 0:
                detalhe += f" — SALDO NEGATIVO ({negativo:.2f}): cobrar do cliente"
            db.update_auto_log(empresa, codigo, {**info, "status": "baixado",
                                                 "cliente_id": cli["id"], "detalhe": detalhe})
            resumo["baixados"] += 1
            resumo["valor_baixado"] += valor
        except Exception as e:
            try:
                _pendente(f"Erro ao dar baixa ({type(e).__name__}) — tentar de novo")
            except Exception:
                pass
            resumo["erros"].append(f"{empresa}: erro ao processar um pedido ({type(e).__name__})")
    return resumo


def clients_from_env() -> dict:
    """Clientes eGestor a partir das mesmas variáveis usadas pelo dashboard."""
    from egestor_api import EgestorClient
    empresas = [
        (_cfg("GOGENETIC_PESQUISA_NOME", "GoGenetic Pesquisa"), _cfg("GOGENETIC_PESQUISA_TOKEN", "")),
        (_cfg("GOGENETIC_SOLUCOES_NOME", "GoGenetic Soluções"), _cfg("GOGENETIC_SOLUCOES_TOKEN", "")),
        (_cfg("GOSOLOS_NOME", "GoSolos"), _cfg("GOSOLOS_TOKEN", "")),
    ]
    return {nome: EgestorClient(tok, nome) for nome, tok in empresas if tok}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    dias = int(_cfg("CREDITO_SYNC_DIAS", "365"))
    clients = clients_from_env()
    if not clients:
        print("Nenhum token do eGestor configurado.")
        sys.exit(1)
    r = sincronizar(clients, dias=dias)
    # Só contagens — nada de nomes de clientes ou valores (logs são públicos).
    print(f"Empresas lidas: {len(clients)} | pedidos com a situação: {r['encontrados']} | "
          f"baixados agora: {r['baixados']} | pendentes: {r['pendentes']} | "
          f"já processados: {r['ja_processados']}")
    for e in r["erros"]:
        print("AVISO:", e)
    sys.exit(1 if r["erros"] and not (r["baixados"] or r["encontrados"]) else 0)
