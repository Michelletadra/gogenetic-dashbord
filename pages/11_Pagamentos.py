"""Página 11 — Gestão de Pagamentos.

Área de análise e decisão: NÃO efetua pagamentos. Serve para priorizar,
selecionar, aprovar e preparar a lista de pagamentos com base no saldo
manual das contas bancárias.
"""
import io
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from utils import (GLOBAL_CSS, NOME_YOU, brl, kpi_card, sidebar_header,
                    get_empresas_disponiveis, load_companies_data,
                    load_companies_vencidas, load_plano_contas,
                    load_bling_categorias)
import db_pagamentos as db

st.set_page_config(page_title="Pagamentos | GoGenetic", page_icon="🧾", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

sidebar_header()
usuario_atual = st.session_state.get("name", "")

STATUS_FLOW = ["Pendente de análise", "Selecionado para pagamento", "Aguardando aprovação",
               "Aprovado para pagamento", "Programado", "Pago", "Adiado", "Cancelado"]
STATUS_APROVADOS = {"Aprovado para pagamento", "Programado", "Pago"}
PRIORIDADES = ["Crítico", "Alto", "Médio", "Baixo"]
CORES_PRIORIDADE = {"Crítico": "#EF4444", "Alto": "#F97316", "Médio": "#F5A623", "Baixo": "#10B981"}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    disponiveis    = get_empresas_disponiveis()
    empresa_sel    = st.selectbox("🏢 Empresa", ["Todas"] + disponiveis, key="pgto_empresa")
    empresas_ativas = disponiveis if empresa_sel == "Todas" else [empresa_sel]
    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True, key="pgto_refresh"):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ Cache: 5 min · Horizonte: hoje + 60 dias + vencidos")

st.markdown("""
<p class="page-title">🧾 Gestão de Pagamentos</p>
<p class="page-sub">Análise, priorização e aprovação de pagamentos — nenhum pagamento é
efetuado automaticamente por aqui.</p>
""", unsafe_allow_html=True)

hoje     = date.today()
hoje_str = hoje.strftime("%Y-%m-%d")
dt_fim_futuro = (hoje + timedelta(days=60)).strftime("%Y-%m-%d")

# ── Carrega pagamentos pendentes (vencidos + próximos 60 dias) ────────────────
with st.spinner("Carregando pagamentos pendentes..."):
    _dados_map = load_companies_data(empresas_ativas, hoje_str, dt_fim_futuro)
    _venc_map  = load_companies_vencidas(empresas_ativas)

    pendentes_raw = []
    for nome in empresas_ativas:
        for item in _dados_map[nome]["contas_pagar"]:
            pendentes_raw.append({**item, "empresa": nome, "_vencido": False})
        for item in _venc_map[nome]["pagar"]:
            pendentes_raw.append({**item, "empresa": nome, "_vencido": True})

    # Categoria (plano de contas eGestor / categorias Bling) — mapa por empresa
    categoria_map = {}
    for nome in empresas_ativas:
        if nome == NOME_YOU:
            cats = load_bling_categorias()
            categoria_map[nome] = {k: (v.get("subgrupo") or "Sem Categoria") for k, v in cats.items()}
        else:
            plano = load_plano_contas(nome)
            categoria_map[nome] = {}
            for p in plano:
                try:
                    categoria_map[nome][int(p["codigo"])] = p.get("nome") or "Sem Categoria"
                except (TypeError, ValueError, KeyError):
                    continue

    overrides = db.list_overrides(empresas_ativas)
    contas_bancarias = db.list_contas_bancarias()
    saldos_latest = db.ultimos_saldos()

conta_por_id   = {c["id"]: c for c in contas_bancarias}
NAO_DEFINIDA   = "— Não definida —"
conta_nome_opcoes = [NAO_DEFINIDA] + [c["nome"] for c in contas_bancarias]
conta_id_to_nome  = {c["id"]: c["nome"] for c in contas_bancarias}
conta_nome_to_id  = {c["nome"]: c["id"] for c in contas_bancarias}


# ── Monta DataFrame analítico ──────────────────────────────────────────────────
def _prioridade_auto(vencido: bool, dias) -> str:
    if vencido or (dias is not None and dias < 0):
        return "Crítico"
    if dias is not None and dias <= 3:
        return "Alto"
    if dias is not None and dias <= 7:
        return "Médio"
    return "Baixo"


def montar_df(pendentes: list) -> pd.DataFrame:
    rows = []
    for item in pendentes:
        empresa = item["empresa"]
        codigo  = str(item.get("codigo"))
        ov      = overrides.get((empresa, codigo), {})
        dtVenc  = pd.to_datetime(item.get("dtVenc"), errors="coerce")
        dias    = (dtVenc.date() - hoje).days if pd.notna(dtVenc) else None
        vencido = bool(item.get("_vencido")) or (dias is not None and dias < 0)

        cod_plano = item.get("codPlanoContas")
        try:
            categoria = categoria_map.get(empresa, {}).get(int(cod_plano), "Sem Categoria") if cod_plano else "Sem Categoria"
        except (TypeError, ValueError):
            categoria = "Sem Categoria"

        valor    = float(item.get("valor") or 0)
        juros    = float(ov.get("valor_juros") or 0)
        desconto = float(ov.get("valor_desconto") or 0)
        conta_id = ov.get("conta_origem_id")

        rows.append({
            "empresa": empresa, "codigo": codigo,
            "Selecionar": bool(ov.get("selecionado", False)),
            "Fornecedor": item.get("nomeContato") or "—",
            "Descrição": item.get("descricao") or "",
            "Categoria": categoria,
            "Centro de Custo": ov.get("centro_custo") or "",
            "Projeto": ov.get("projeto") or "",
            "Vencimento": dtVenc.date() if pd.notna(dtVenc) else None,
            "Valor": valor,
            "Juros/Multa": juros,
            "Desconto": desconto,
            "Valor Final": round(valor + juros - desconto, 2),
            "Prioridade": ov.get("prioridade_manual") or _prioridade_auto(vencido, dias),
            "Conta de Origem": conta_id_to_nome.get(conta_id, NAO_DEFINIDA),
            "Status": ov.get("status") or "Pendente de análise",
            "Observação": ov.get("observacao") or "",
            "_vencido": vencido,
            "_dias": dias,
            "_prioridade_auto": _prioridade_auto(vencido, dias),
            "_valor_aprovado": ov.get("valor_aprovado"),
        })
    cols = ["empresa", "codigo", "Selecionar", "Fornecedor", "Descrição", "Categoria",
            "Centro de Custo", "Projeto", "Vencimento", "Valor", "Juros/Multa", "Desconto",
            "Valor Final", "Prioridade", "Conta de Origem", "Status", "Observação",
            "_vencido", "_dias", "_prioridade_auto", "_valor_aprovado"]
    return pd.DataFrame(rows, columns=cols)


df = montar_df(pendentes_raw)

# ── Duplicados (heurística: mesmo fornecedor + valor + vencimento) ────────────
# Vira uma coluna do próprio df (não uma máscara posicional à parte) para
# sobreviver corretamente a filtros e reordenação da tabela mais abaixo.
if not df.empty:
    chave_dup = df["Fornecedor"].astype(str) + "|" + df["Valor"].round(2).astype(str) + "|" + df["Vencimento"].astype(str)
    df["_duplicado"] = chave_dup.duplicated(keep=False) & (df["Fornecedor"] != "—")
else:
    df["_duplicado"] = pd.Series(dtype=bool)

# ── Saldos das contas ──────────────────────────────────────────────────────────
def saldo_info(conta_id):
    """Retorna dict com valor, reservado, disponível e status de atualização."""
    s = saldos_latest.get(conta_id)
    if not s:
        limite = float(conta_por_id.get(conta_id, {}).get("limite_credito") or 0)
        return {"valor": 0.0, "reservado": 0.0, "limite": limite, "disponivel": limite,
                "data_ref": None, "cor": "🔴", "legenda": "Sem saldo informado"}
    valor      = float(s["valor"] or 0)
    reservado  = float(s["saldo_reservado"] or 0)
    limite     = float(conta_por_id.get(conta_id, {}).get("limite_credito") or 0)
    data_ref   = pd.to_datetime(s["data_referencia"]).date()
    dias_uteis = int(np.busday_count(data_ref, hoje)) if data_ref <= hoje else 0
    if data_ref == hoje:
        cor, legenda = "🟢", "Confirmado hoje"
    elif dias_uteis <= 1:
        cor, legenda = "🟡", f"Herdado do dia anterior ({data_ref.strftime('%d/%m/%Y')})"
    else:
        cor, legenda = "🔴", f"Saldo não confirmado hoje — usando saldo do dia {data_ref.strftime('%d/%m/%Y')} ({dias_uteis} dias úteis)"
    return {"valor": valor, "reservado": reservado, "limite": limite,
            "disponivel": valor - reservado + limite,
            "data_ref": data_ref, "cor": cor, "legenda": legenda}


saldo_por_conta = {c["id"]: saldo_info(c["id"]) for c in contas_bancarias}

# Pagamentos selecionados somados por conta de origem (na visão atual/carregada)
sel_por_conta_nome = df[df["Selecionar"]].groupby("Conta de Origem")["Valor Final"].sum().to_dict()

saldo_total_disponivel = sum(s["disponivel"] for s in saldo_por_conta.values())
saldo_total_reservado  = sum(s["reservado"] for s in saldo_por_conta.values())
total_selecionado      = float(df.loc[df["Selecionar"], "Valor Final"].sum()) if not df.empty else 0.0
saldo_projetado_total  = saldo_total_disponivel - total_selecionado

vence_hoje = float(df.loc[df["_dias"] == 0, "Valor Final"].sum()) if not df.empty else 0.0
vence_7    = float(df.loc[(df["_dias"] >= 0) & (df["_dias"] <= 7), "Valor Final"].sum()) if not df.empty else 0.0
vence_15   = float(df.loc[(df["_dias"] >= 0) & (df["_dias"] <= 15), "Valor Final"].sum()) if not df.empty else 0.0
vence_30   = float(df.loc[(df["_dias"] >= 0) & (df["_dias"] <= 30), "Valor Final"].sum()) if not df.empty else 0.0

# ── 1. RESUMO FINANCEIRO SUPERIOR ──────────────────────────────────────────────
st.markdown("<div class='section-title'>Resumo Financeiro</div>", unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
kpi_card(c1, "🏦", "Saldo Disponível", brl(saldo_total_disponivel), f"Reservado: {brl(saldo_total_reservado)}", border="rgba(36,183,140,0.3)")
kpi_card(c2, "✅", "Selecionado p/ Pagar", brl(total_selecionado), f"{int(df['Selecionar'].sum()) if not df.empty else 0} título(s)", border="rgba(126,22,184,0.3)")
kpi_card(c3, "📊", "Saldo Projetado", brl(saldo_projetado_total), "Disponível − Selecionado",
         border="rgba(239,68,68,0.4)" if saldo_projetado_total < 0 else "rgba(36,183,140,0.4)",
         value_class="kpi-negative" if saldo_projetado_total < 0 else "kpi-positive")

c6, c7, c8, c9, c10 = st.columns(5)
kpi_card(c6, "📅", "Vence Hoje", brl(vence_hoje), "", border="rgba(255,103,47,0.4)")
kpi_card(c7, "🗓️", "Próx. 7 dias", brl(vence_7), "", border="rgba(245,166,35,0.4)")
kpi_card(c8, "🗓️", "Próx. 15 dias", brl(vence_15), "", border="rgba(245,166,35,0.3)")
kpi_card(c9, "🗓️", "Próx. 30 dias", brl(vence_30), "", border="rgba(126,22,184,0.2)")
kpi_card(c10, "🔒", "Reservado (crítico)", brl(saldo_total_reservado), "Definido manualmente por conta", border="rgba(126,22,184,0.2)")

st.caption(f"🕒 Dados de pagamentos carregados às {datetime.now().strftime('%H:%M')} · "
           f"Saldos conforme último lançamento manual por conta.")

# ── 2. QUADRO DE SALDOS DAS CONTAS ─────────────────────────────────────────────
st.markdown("<div class='section-title'>💰 Saldos das Contas Bancárias</div>", unsafe_allow_html=True)

if not contas_bancarias:
    st.info("Nenhuma conta bancária cadastrada ainda. Cadastre a primeira abaixo.")
else:
    quadro_rows = []
    for c in contas_bancarias:
        s = saldo_por_conta[c["id"]]
        selecionado_conta = float(sel_por_conta_nome.get(c["nome"], 0.0))
        projetado = s["disponivel"] - selecionado_conta
        quadro_rows.append({
            "": s["cor"], "Conta": c["nome"], "Banco": c.get("banco") or "",
            "Saldo Atual": brl(s["valor"]), "Saldo Reservado": brl(s["reservado"]),
            "Limite Crédito": brl(s["limite"]),
            "Saldo Disponível": brl(s["disponivel"]),
            "Pagamentos Selecionados": brl(selecionado_conta),
            "Saldo Projetado": brl(projetado), "_projetado_num": projetado,
            "_legenda": s["legenda"],
        })
    df_quadro = pd.DataFrame(quadro_rows)

    def _estilo_projetado(row):
        cor = "color:#EF4444;font-weight:700" if row["_projetado_num"] < 0 else ""
        return [cor if col == "Saldo Projetado" else "" for col in row.index]

    st.dataframe(
        df_quadro.style.apply(_estilo_projetado, axis=1).hide(axis="columns", subset=["_projetado_num", "_legenda"]),
        use_container_width=True, hide_index=True,
    )
    for r in quadro_rows:
        if r["_projetado_num"] < 0:
            st.error(f"🔴 **{r['Conta']}** ficaria com saldo projetado negativo de {brl(r['_projetado_num'])} — {r['_legenda']}")
        st.caption(f"{r['']} {r['Conta']}: {r['_legenda']}")

    st.markdown(f"**Total consolidado — Disponível:** {brl(saldo_total_disponivel)} · "
                f"**Projetado:** {brl(saldo_projetado_total)}")

with st.expander("✏️ Atualizar saldo de uma conta"):
    if contas_bancarias:
        conta_edit = st.selectbox("Conta", contas_bancarias, format_func=lambda c: c["nome"], key="pgto_conta_edit")
        atual = saldo_por_conta.get(conta_edit["id"], {}) if conta_edit else {}
        ce1, ce2, ce3 = st.columns(3)
        novo_valor      = ce1.number_input("Saldo atual (R$)", value=float(atual.get("valor", 0.0)), step=100.0, key="pgto_novo_saldo")
        novo_reservado  = ce2.number_input("Saldo reservado (R$)", value=float(atual.get("reservado", 0.0)), step=100.0, key="pgto_novo_reservado")
        data_ref        = ce3.date_input("Data de referência", value=hoje, key="pgto_data_ref")
        observ_saldo    = st.text_input("Observação (ex: saldo após conciliação, aguardando compensação)", key="pgto_obs_saldo")
        if st.button("💾 Registrar novo saldo", key="pgto_btn_saldo"):
            db.insert_saldo(conta_edit["id"], novo_valor, novo_reservado, data_ref, observ_saldo, usuario_atual)
            st.success(f"Saldo de {conta_edit['nome']} registrado por {usuario_atual}.")
            st.rerun()
        hist = db.historico_saldos(conta_edit["id"]) if conta_edit else []
        if hist:
            st.caption("Histórico (mais recente primeiro):")
            df_hist = pd.DataFrame(hist)[["data_referencia", "valor", "saldo_reservado", "usuario", "observacao", "criado_em"]]
            df_hist.columns = ["Data Ref.", "Valor", "Reservado", "Usuário", "Observação", "Lançado em"]
            st.dataframe(df_hist, use_container_width=True, hide_index=True)

with st.expander("✏️ Editar limites de uma conta"):
    if contas_bancarias:
        conta_lim = st.selectbox("Conta", contas_bancarias, format_func=lambda c: c["nome"], key="pgto_conta_limite")
        cl1, cl2, cl3 = st.columns(3)
        banco_edit   = cl1.text_input("Banco", value=conta_lim.get("banco") or "", key="pgto_edit_banco")
        minimo_edit  = cl2.number_input("Saldo mínimo desejado (R$)", value=float(conta_lim.get("saldo_minimo") or 0),
                                         step=100.0, key="pgto_edit_minimo")
        limite_edit  = cl3.number_input("Limite de crédito / cheque especial (R$)", value=float(conta_lim.get("limite_credito") or 0),
                                         step=100.0, min_value=0.0, key="pgto_edit_limite")
        if st.button("💾 Salvar limites", key="pgto_btn_editar_limites"):
            db.update_conta_bancaria(conta_lim["id"], {
                "banco": banco_edit.strip(), "saldo_minimo": minimo_edit, "limite_credito": limite_edit,
            })
            st.success(f"Limites de '{conta_lim['nome']}' atualizados.")
            st.rerun()
    else:
        st.caption("Cadastre uma conta primeiro.")

with st.expander("➕ Cadastrar nova conta bancária"):
    nc1, nc2, nc3, nc4 = st.columns(4)
    nome_nova  = nc1.text_input("Nome da conta", placeholder="Ex: Itaú CC 12345", key="pgto_nova_conta_nome")
    banco_novo = nc2.text_input("Banco", placeholder="Ex: Itaú", key="pgto_nova_conta_banco")
    minimo_novo = nc3.number_input("Saldo mínimo desejado (R$)", value=0.0, step=100.0, key="pgto_nova_conta_min")
    limite_novo = nc4.number_input("Limite de crédito / cheque especial (R$)", value=0.0, step=100.0,
                                    min_value=0.0, key="pgto_nova_conta_limite")
    if st.button("➕ Cadastrar conta", key="pgto_btn_nova_conta"):
        if nome_nova.strip():
            db.insert_conta_bancaria(nome_nova.strip(), banco_novo.strip(), minimo_novo, limite_novo)
            st.success(f"Conta '{nome_nova}' cadastrada.")
            st.rerun()
        else:
            st.warning("Informe um nome para a conta.")

# ── 3. LISTA ANALÍTICA DE PAGAMENTOS ───────────────────────────────────────────
st.markdown("<div class='section-title'>📋 Lista Analítica de Pagamentos</div>", unsafe_allow_html=True)

if df.empty:
    st.success("Nenhum pagamento pendente no período analisado. ✅")
else:
    fc1, fc2, fc3 = st.columns([2, 2, 2])
    busca      = fc1.text_input("🔎 Buscar (fornecedor/descrição)", key="pgto_busca")
    fornec_opt = fc2.multiselect("Fornecedor", sorted(df["Fornecedor"].unique()), key="pgto_f_fornec")
    categ_opt  = fc3.multiselect("Categoria", sorted(df["Categoria"].unique()), key="pgto_f_categ")

    fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2])
    prio_opt   = fc4.multiselect("Prioridade", PRIORIDADES, key="pgto_f_prio")
    status_opt = fc5.multiselect("Status", STATUS_FLOW, key="pgto_f_status")
    conta_opt  = fc6.multiselect("Conta bancária", conta_nome_opcoes, key="pgto_f_conta")
    venc_range = fc7.date_input("Vencimento entre", value=(), key="pgto_f_venc")

    df_filtrado = df.copy()
    if busca:
        b = busca.lower()
        df_filtrado = df_filtrado[df_filtrado["Fornecedor"].str.lower().str.contains(b, na=False) |
                                   df_filtrado["Descrição"].str.lower().str.contains(b, na=False)]
    if fornec_opt:
        df_filtrado = df_filtrado[df_filtrado["Fornecedor"].isin(fornec_opt)]
    if categ_opt:
        df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(categ_opt)]
    if prio_opt:
        df_filtrado = df_filtrado[df_filtrado["Prioridade"].isin(prio_opt)]
    if status_opt:
        df_filtrado = df_filtrado[df_filtrado["Status"].isin(status_opt)]
    if conta_opt:
        df_filtrado = df_filtrado[df_filtrado["Conta de Origem"].isin(conta_opt)]
    if isinstance(venc_range, tuple) and len(venc_range) == 2:
        d_ini, d_fim = venc_range
        df_filtrado = df_filtrado[(df_filtrado["Vencimento"] >= d_ini) & (df_filtrado["Vencimento"] <= d_fim)]

    df_filtrado = df_filtrado.sort_values(["_vencido", "Vencimento"], ascending=[False, True]).reset_index(drop=True)

    st.caption("💡 Marque na coluna ✓ os pagamentos da rodada. Edições são salvas automaticamente "
               "e a seleção não se perde ao trocar filtros.")

    display_cols = ["Selecionar", "Fornecedor", "Descrição", "Categoria", "Centro de Custo",
                     "Projeto", "Vencimento", "Valor", "Juros/Multa", "Desconto", "Valor Final",
                     "Prioridade", "Conta de Origem", "Status", "Observação"]

    edited_df = st.data_editor(
        df_filtrado,
        column_order=display_cols,
        column_config={
            "Selecionar": st.column_config.CheckboxColumn("✓"),
            "Fornecedor": st.column_config.Column(disabled=True),
            "Descrição": st.column_config.Column(disabled=True),
            "Categoria": st.column_config.Column(disabled=True),
            "Centro de Custo": st.column_config.TextColumn("Centro de Custo"),
            "Projeto": st.column_config.TextColumn("Projeto/Área"),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", disabled=True),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", disabled=True),
            "Juros/Multa": st.column_config.NumberColumn("Juros/Multa", format="R$ %.2f", min_value=0.0, step=1.0),
            "Desconto": st.column_config.NumberColumn("Desconto", format="R$ %.2f", min_value=0.0, step=1.0),
            "Valor Final": st.column_config.NumberColumn("Valor Final", format="R$ %.2f", disabled=True),
            "Prioridade": st.column_config.SelectboxColumn("Prioridade", options=PRIORIDADES),
            "Conta de Origem": st.column_config.SelectboxColumn("Conta de Origem", options=conta_nome_opcoes),
            "Status": st.column_config.SelectboxColumn("Status", options=STATUS_FLOW),
            "Observação": st.column_config.TextColumn("Observação"),
        },
        hide_index=True, use_container_width=True, height=460, key="pgto_editor",
    )

    # ── Persiste diffs imediatamente (garante que a seleção sobrevive a filtros) ──
    changed = False
    for i in range(len(df_filtrado)):
        orig = df_filtrado.iloc[i]
        new  = edited_df.iloc[i]
        empresa, codigo = orig["empresa"], orig["codigo"]
        diffs, hist_eventos = {}, []

        if bool(new["Selecionar"]) != bool(orig["Selecionar"]):
            diffs["selecionado"] = bool(new["Selecionar"])
            hist_eventos.append(("selecionado", orig["Selecionar"], new["Selecionar"]))
        if str(new["Centro de Custo"] or "") != str(orig["Centro de Custo"] or ""):
            diffs["centro_custo"] = new["Centro de Custo"]
        if str(new["Projeto"] or "") != str(orig["Projeto"] or ""):
            diffs["projeto"] = new["Projeto"]
        if float(new["Juros/Multa"] or 0) != float(orig["Juros/Multa"] or 0):
            diffs["valor_juros"] = float(new["Juros/Multa"] or 0)
        if float(new["Desconto"] or 0) != float(orig["Desconto"] or 0):
            diffs["valor_desconto"] = float(new["Desconto"] or 0)
        if new["Prioridade"] != orig["Prioridade"]:
            diffs["prioridade_manual"] = new["Prioridade"]
        if new["Conta de Origem"] != orig["Conta de Origem"]:
            diffs["conta_origem_id"] = conta_nome_to_id.get(new["Conta de Origem"])
            hist_eventos.append(("conta de origem", orig["Conta de Origem"], new["Conta de Origem"]))
        if new["Status"] != orig["Status"]:
            diffs["status"] = new["Status"]
            hist_eventos.append(("status", orig["Status"], new["Status"]))
            if new["Status"] in STATUS_APROVADOS and orig["Status"] not in STATUS_APROVADOS:
                novo_juros    = float(new["Juros/Multa"] or 0)
                novo_desc     = float(new["Desconto"] or 0)
                diffs["valor_aprovado"] = round(float(orig["Valor"]) + novo_juros - novo_desc, 2)
        if str(new["Observação"] or "") != str(orig["Observação"] or ""):
            diffs["observacao"] = new["Observação"]

        if diffs:
            diffs["atualizado_por"] = usuario_atual
            db.upsert_override(empresa, codigo, diffs)
            for campo, antes, depois in hist_eventos:
                db.registrar_historico(empresa, codigo, f"{campo} alterado", antes, depois, usuario_atual)
            changed = True

    if changed:
        st.rerun()

    # ── Painel da rodada (usa a seleção já editada nesta mesma execução) ───────
    df_work = edited_df.copy()
    df_work["Valor Final"] = (df_work["Valor"] + df_work["Juros/Multa"] - df_work["Desconto"]).round(2)
    sel = df_work[df_work["Selecionar"]]

    st.markdown("<div class='section-title'>📌 Painel da Rodada de Pagamento</div>", unsafe_allow_html=True)
    p1, p2, p3, p4 = st.columns(4)
    kpi_card(p1, "🧮", "Qtd. Selecionados", str(len(sel)), border="rgba(126,22,184,0.3)")
    kpi_card(p2, "💵", "Total Bruto", brl(sel["Valor"].sum()), border="rgba(126,22,184,0.2)")
    kpi_card(p3, "➕➖", "Juros/Descontos", f"{brl(sel['Juros/Multa'].sum())} / -{brl(sel['Desconto'].sum())}", border="rgba(126,22,184,0.2)")
    kpi_card(p4, "✅", "Total Líquido", brl(sel["Valor Final"].sum()), border="rgba(36,183,140,0.4)", value_class="kpi-positive")

    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        st.markdown("**Por Conta Bancária**")
        if not sel.empty:
            st.dataframe(sel.groupby("Conta de Origem")["Valor Final"].sum().reset_index()
                         .rename(columns={"Valor Final": "Total"}).assign(Total=lambda d: d["Total"].apply(brl)),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("Nenhum pagamento selecionado.")
    with pcol2:
        st.markdown("**Por Fornecedor**")
        if not sel.empty:
            st.dataframe(sel.groupby("Fornecedor")["Valor Final"].sum().reset_index()
                         .rename(columns={"Valor Final": "Total"}).sort_values("Total", ascending=False)
                         .assign(Total=lambda d: d["Total"].apply(brl)),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("—")
    with pcol3:
        st.markdown("**Por Categoria / Centro de Custo**")
        if not sel.empty:
            st.dataframe(sel.groupby(["Categoria", "Centro de Custo"])["Valor Final"].sum().reset_index()
                         .rename(columns={"Valor Final": "Total"})
                         .assign(Total=lambda d: d["Total"].apply(brl)),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("—")

    criticos_fora = df_work[(df_work["Prioridade"] == "Crítico") & (~df_work["Selecionar"])]
    if not criticos_fora.empty:
        st.warning(f"⚠️ **{len(criticos_fora)} pagamento(s) crítico(s) ficaram de fora da seleção**, "
                   f"totalizando {brl(criticos_fora['Valor Final'].sum())}: " +
                   ", ".join(f"{r['Fornecedor']} ({brl(r['Valor Final'])})" for _, r in criticos_fora.head(5).iterrows()))

    # ── 6. REGRAS E ALERTAS ────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>⚠️ Alertas</div>", unsafe_allow_html=True)
    alertas = []

    for conta_nome, total_sel in sel.groupby("Conta de Origem")["Valor Final"].sum().items():
        if conta_nome == NAO_DEFINIDA:
            continue
        cid = conta_nome_to_id.get(conta_nome)
        disponivel = saldo_por_conta.get(cid, {}).get("disponivel", 0.0)
        if total_sel > disponivel:
            alertas.append(("🔴", f"**{conta_nome}**: total selecionado ({brl(total_sel)}) ultrapassa o "
                                    f"saldo disponível ({brl(disponivel)}). Impacto: faltariam {brl(total_sel - disponivel)}. "
                                    f"Sugestão: remover pagamentos dessa conta ou trocar a conta de origem."))
        else:
            minimo = conta_por_id.get(cid, {}).get("saldo_minimo", 0) or 0
            projetado = disponivel - total_sel
            if projetado < minimo:
                alertas.append(("🟠", f"**{conta_nome}**: saldo projetado ({brl(projetado)}) ficará abaixo do "
                                        f"mínimo definido ({brl(minimo)}). Sugestão: revisar quais pagamentos manter nesta conta."))

    venc_nao_sel = df_work[df_work["_vencido"] & (~df_work["Selecionar"])]
    if not venc_nao_sel.empty:
        alertas.append(("🔴", f"{len(venc_nao_sel)} pagamento(s) **vencido(s) não selecionado(s)**, totalizando "
                               f"{brl(venc_nao_sel['Valor Final'].sum())}. Sugestão: revisar e decidir (pagar ou adiar com justificativa)."))

    dup_rows = df_work[df_work["_duplicado"]] if "_duplicado" in df_work.columns else pd.DataFrame()
    if not dup_rows.empty:
        alertas.append(("🟠", f"{len(dup_rows)} título(s) parecem **duplicados** (mesmo fornecedor, valor e vencimento). "
                               f"Sugestão: conferir antes de aprovar para evitar pagamento em duplicidade."))

    sem_conta_sel = sel[sel["Conta de Origem"] == NAO_DEFINIDA]
    if not sem_conta_sel.empty:
        alertas.append(("🟠", f"{len(sem_conta_sel)} pagamento(s) selecionado(s) **sem conta de origem definida**, "
                               f"totalizando {brl(sem_conta_sel['Valor Final'].sum())}. Defina a conta antes de aprovar."))

    diverg = df_work[df_work["Status"].isin(STATUS_APROVADOS) & df_work["_valor_aprovado"].notna() &
                      (df_work["_valor_aprovado"].round(2) != df_work["Valor Final"].round(2))]
    if not diverg.empty:
        alertas.append(("🟠", f"{len(diverg)} pagamento(s) têm **divergência entre o valor aprovado e o valor final atual** "
                               f"(juros/desconto alterados após a aprovação). Sugestão: revalidar a aprovação."))

    if not alertas:
        st.success("Nenhum alerta identificado na seleção atual. ✅")
    else:
        for cor, msg in alertas:
            (st.error if cor == "🔴" else st.warning)(msg)

    st.caption("ℹ️ Orçamento por categoria/centro de custo ainda não está cadastrado no dashboard — "
               "esse alerta específico não está disponível até que uma fonte de orçamento seja definida.")

    # ── 8. RELATÓRIO DA RODADA ─────────────────────────────────────────────────
    st.markdown("<div class='section-title'>📄 Relatório da Rodada</div>", unsafe_allow_html=True)
    obs_rodada = st.text_area("Observações da rodada (adiamentos, justificativas, etc.)", key="pgto_obs_rodada")

    rc1, rc2 = st.columns(2)
    with rc1:
        if st.button("💾 Salvar rodada (registrar aprovação)", key="pgto_salvar_rodada", disabled=sel.empty):
            snapshot = {
                "usuario": usuario_atual,
                "total_titulos": int(len(sel)),
                "valor_bruto": float(sel["Valor"].sum()),
                "valor_juros": float(sel["Juros/Multa"].sum()),
                "valor_desconto": float(sel["Desconto"].sum()),
                "valor_liquido": float(sel["Valor Final"].sum()),
                "saldos_antes": {c["nome"]: saldo_por_conta[c["id"]]["disponivel"] for c in contas_bancarias},
                "pagamentos": sel[["empresa", "codigo", "Fornecedor", "Categoria", "Centro de Custo",
                                    "Vencimento", "Valor Final", "Conta de Origem", "Status"]].astype(str).to_dict("records"),
                "alertas": [f"{c} {m}" for c, m in alertas],
                "observacao": obs_rodada,
            }
            db.salvar_rodada(snapshot)
            st.success(f"Rodada salva por {usuario_atual} com {len(sel)} pagamento(s) — {brl(sel['Valor Final'].sum())}.")

    def to_excel_bytes(dfs: dict) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for nome_aba, d in dfs.items():
                d.to_excel(writer, index=False, sheet_name=nome_aba[:31])
        return buf.getvalue()

    with rc2:
        df_relatorio = sel.drop(columns=["_vencido", "_dias", "_prioridade_auto", "_valor_aprovado", "empresa", "codigo"], errors="ignore")
        df_saldos_rel = pd.DataFrame([
            {"Conta": c["nome"], "Saldo Disponível Antes": saldo_por_conta[c["id"]]["disponivel"],
             "Selecionado": sel_por_conta_nome.get(c["nome"], 0.0),
             "Saldo Projetado": saldo_por_conta[c["id"]]["disponivel"] - sel_por_conta_nome.get(c["nome"], 0.0)}
            for c in contas_bancarias
        ])
        st.download_button(
            "📥 Baixar relatório (Excel)",
            data=to_excel_bytes({"Pagamentos Selecionados": df_relatorio, "Saldos das Contas": df_saldos_rel}),
            file_name=f"rodada_pagamentos_{hoje.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with st.expander("🕓 Rodadas salvas anteriormente"):
        rodadas = db.list_rodadas(10)
        if not rodadas:
            st.caption("Nenhuma rodada salva ainda.")
        for r in rodadas:
            st.markdown(f"**{r['criado_em'][:16].replace('T', ' ')}** · {r.get('usuario','—')} · "
                        f"{r['total_titulos']} título(s) · Líquido: {brl(r['valor_liquido'])}")
            if r.get("observacao"):
                st.caption(r["observacao"])
