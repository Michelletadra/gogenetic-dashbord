"""
9_Realizado.py — Despesas efetivamente pagas, agrupadas por plano de contas.
Regras:
  • Sempre usa data de PAGAMENTO (dtPgto), nunca vencimento.
  • Só exibe registros com situacao=30 (pago).
  • Não mistura previsto com realizado.
  • Apenas empresas eGestor (Bling/You não suportado).
"""

from __future__ import annotations

import calendar
import io
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import (
    BRAND,
    GLOBAL_CSS,
    MESES_PT,
    NOMES,
    NOME_YOU,
    brl,
    get_empresas_disponiveis,
    kpi_card,
    load_bling_pagamentos_realizados,
    load_bling_realizados_12m,
    load_pagamentos_realizados,
    load_plano_contas,
    load_realizados_12m,
    plotly_layout,
    sidebar_header,
    soma,
    load_companies_realizados_12m,
    _parallel,
)

# ── Página ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Realizado · GoGenetic", page_icon="💸", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()

# ── Paleta fixa ───────────────────────────────────────────────────────────────
_PALETTE = [
    "#7E16B8", "#10B981", "#F59E0B", "#EF4444", "#3B82F6",
    "#EC4899", "#14B8A6", "#F97316", "#8B5CF6", "#06B6D4",
    "#84CC16", "#6B7280",
]
MESES_INV = {v: k for k, v in MESES_PT.items()}


def _palette(cats: list[str]) -> dict[str, str]:
    return {c: _PALETTE[i % len(_PALETTE)] for i, c in enumerate(sorted(set(cats)))}


# ── Helpers de data ───────────────────────────────────────────────────────────
today = date.today()

def _mes_anterior(ref: date) -> tuple[date, date]:
    primeiro = ref.replace(day=1)
    ultimo_ant = primeiro - timedelta(days=1)
    return ultimo_ant.replace(day=1), ultimo_ant

def _ultimo_dia(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Inclui You se Bling estiver conectado
    _empresas_disp = get_empresas_disponiveis()   # NOMES + [You] se conectado
    empresa_opcoes = ["Todas"] + _empresas_disp
    empresa_sel = st.selectbox("🏢 Empresa", empresa_opcoes)

    if empresa_sel != "Todas" and empresa_sel in BRAND:
        st.image(BRAND[empresa_sel]["logo"], use_column_width=True)

    st.markdown("---")

    modo = st.radio("📅 Modo de período", ["Predefinido", "Mês específico"], horizontal=True)

    if modo == "Mês específico":
        anos_disp = list(range(today.year, today.year - 4, -1))
        ano_sel = st.selectbox("Ano", anos_disp, index=0)
        meses_disp = [MESES_PT[m] for m in range(1, 13) if date(ano_sel, m, 1) <= today]
        mes_default_idx = today.month - 1 if ano_sel == today.year else len(meses_disp) - 1
        mes_nome = st.selectbox("Mês", meses_disp, index=mes_default_idx)
        mes_num  = MESES_INV[mes_nome]
        dt_ini = date(ano_sel, mes_num, 1)
        dt_fim = min(_ultimo_dia(ano_sel, mes_num), today)
        _label_periodo = f"{mes_nome}/{ano_sel}"
        _is_mes_atual  = (ano_sel == today.year and mes_num == today.month)
    else:
        _mes_ant = _mes_anterior(today)
        period_map: dict[str, tuple[date, date]] = {
            "Este mês":        (today.replace(day=1), today),
            "Mês anterior":    _mes_ant,
            "Últimos 30 dias": (today - timedelta(days=30), today),
            "Últimos 60 dias": (today - timedelta(days=60), today),
            "Últimos 90 dias": (today - timedelta(days=90), today),
            "Este ano":        (date(today.year, 1, 1), today),
            "Personalizado":   None,  # type: ignore[assignment]
        }
        periodo_sel = st.selectbox("Período", list(period_map.keys()))
        if periodo_sel == "Personalizado":
            c1, c2 = st.columns(2)
            dt_ini = c1.date_input("De",  today.replace(day=1))
            dt_fim = c2.date_input("Até", today)
        else:
            dt_ini, dt_fim = period_map[periodo_sel]  # type: ignore[misc]
        _label_periodo = periodo_sel
        _is_mes_atual  = (periodo_sel == "Este mês")

    dt_ini_str = dt_ini.strftime("%Y-%m-%d")
    dt_fim_str = dt_fim.strftime("%Y-%m-%d")

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ KPI: 5 min · Evolução: 1h")

# ── Empresas ativas ───────────────────────────────────────────────────────────
_todas = get_empresas_disponiveis()
empresas_ativas: list[str] = _todas if empresa_sel == "Todas" else [empresa_sel]
empresas_egestor = [e for e in empresas_ativas if e != NOME_YOU]
inclui_bling     = NOME_YOU in empresas_ativas

# ── Datas fixas para KPIs do mês atual ────────────────────────────────────────
hoje_str       = today.strftime("%Y-%m-%d")
semana_ini     = today - timedelta(days=today.weekday())
semana_ini_str = semana_ini.strftime("%Y-%m-%d")
mes_ini_str    = today.replace(day=1).strftime("%Y-%m-%d")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">💸 Realizado</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="page-sub">Despesas efetivamente pagas · data de pagamento · '
    f'<b>{_label_periodo}</b></div>',
    unsafe_allow_html=True,
)

# ── Carregar dados ────────────────────────────────────────────────────────────
# Estratégia: carrega apenas os 12 meses (cache 1h) e filtra em memória.
# Só faz chamada extra para o mês atual (cache 5 min) e períodos > 12 meses.
_doze_ini_str = (today - timedelta(days=365)).strftime("%Y-%m-%d")
_periodo_antigo = dt_ini_str < _doze_ini_str   # período selecionado fora dos 12m

with st.spinner("Carregando realizados..."):

    # — 12 meses: carrega empresas eGestor em paralelo + Bling em paralelo —
    _jobs_12m = [(load_realizados_12m, n) for n in empresas_egestor]
    if inclui_bling:
        _jobs_12m.append((load_bling_realizados_12m,))
    # Carrega plano de contas de CADA empresa separadamente
    for _emp in empresas_egestor:
        _jobs_12m.append((load_plano_contas, _emp))

    _res_12m = _parallel(_jobs_12m) if _jobs_12m else []

    # Desempacota resultados
    _idx = 0
    _doze_by_empresa: dict = {}
    for nome in empresas_egestor:
        _doze_by_empresa[nome] = _res_12m[_idx]; _idx += 1
    _bling_12m = _res_12m[_idx] if inclui_bling else []; _idx += (1 if inclui_bling else 0)

    # Plano de contas POR EMPRESA — cada uma tem sua própria hierarquia de códigos
    _plano_por_empresa: dict[str, list] = {}
    for _emp in empresas_egestor:
        _plano_por_empresa[_emp] = _res_12m[_idx]; _idx += 1

    # plano_raw para a empresa selecionada (ou primeira, para compatibilidade)
    _emp_ref = empresa_sel if empresa_sel != "Todas" and empresa_sel in _plano_por_empresa \
               else (empresas_egestor[0] if empresas_egestor else None)
    plano_raw = _plano_por_empresa.get(_emp_ref, []) if _emp_ref else []

    doze_raw: list[dict] = []
    for nome, rows in _doze_by_empresa.items():
        for r in rows:
            r["_empresa"] = nome
        doze_raw.extend(rows)
    for r in _bling_12m:
        r["_empresa"] = NOME_YOU
        doze_raw.append(r)

    # — Período selecionado: filtra dos 12m ou faz chamada para datas antigas —
    if _periodo_antigo:
        # Datas antigas: carrega empresas em paralelo
        _old_jobs = [(load_pagamentos_realizados, n, dt_ini_str, dt_fim_str) for n in empresas_egestor]
        if inclui_bling:
            _old_jobs.append((load_bling_pagamentos_realizados, dt_ini_str, dt_fim_str))
        _old_res = _parallel(_old_jobs) if _old_jobs else []
        periodo_raw: list[dict] = []
        for i, nome in enumerate(empresas_egestor):
            for r in _old_res[i]:
                r["_empresa"] = nome
                periodo_raw.append(r)
        if inclui_bling and _old_res:
            for r in _old_res[-1]:
                r["_empresa"] = NOME_YOU
                periodo_raw.append(r)
    else:
        periodo_raw = [
            r for r in doze_raw
            if dt_ini_str <= (r.get("dtPgto") or "")[:10] <= dt_fim_str
        ]

    # — Mês atual (cache 5 min): empresas em paralelo se necessário —
    if _is_mes_atual:
        _mes_jobs = [(load_pagamentos_realizados, n, mes_ini_str, hoje_str) for n in empresas_egestor]
        if inclui_bling:
            _mes_jobs.append((load_bling_pagamentos_realizados, mes_ini_str, hoje_str))
        _mes_res = _parallel(_mes_jobs) if _mes_jobs else []
        mes_raw: list[dict] = []
        for i, nome in enumerate(empresas_egestor):
            for r in _mes_res[i]:
                r["_empresa"] = nome
                mes_raw.append(r)
        if inclui_bling and _mes_res:
            for r in _mes_res[-1]:
                r["_empresa"] = NOME_YOU
                mes_raw.append(r)
    else:
        mes_raw = [
            r for r in doze_raw
            if mes_ini_str <= (r.get("dtPgto") or "")[:10] <= hoje_str
        ]


# ── Mapa hierárquico do plano de contas ───────────────────────────────────────
# Cada código recebe: {"grupo": nome_raiz, "subgrupo": nome_direto}
def _build_plano_info(plano_raw: list[dict]) -> dict[int, dict]:
    plano: dict[int, dict] = {int(p["codigo"]): p for p in plano_raw}

    def _root_nome(cod: int, depth: int = 0) -> str:
        if depth > 8 or cod not in plano:
            return "Sem Categoria"
        item = plano[cod]
        if int(item.get("codPai") or 0) == 0:
            return str(item.get("nome", "Sem Categoria"))
        return _root_nome(int(item["codPai"]), depth + 1)

    result: dict[int, dict] = {}
    for cod, item in plano.items():
        nome_direto = str(item.get("nome", "Sem Categoria"))
        cod_pai = int(item.get("codPai") or 0)
        if cod_pai == 0:
            result[cod] = {"grupo": nome_direto, "subgrupo": nome_direto}
        else:
            result[cod] = {"grupo": _root_nome(cod), "subgrupo": nome_direto}
    return result


# Constrói plano_info separado por empresa (códigos iguais = categorias diferentes!)
_plano_info_por_empresa: dict[str, dict] = {
    emp: _build_plano_info(raw)
    for emp, raw in _plano_por_empresa.items()
}
# plano_info global para a empresa de referência (gráficos de evolução 12m)
plano_info = _build_plano_info(plano_raw)


def _get_info(cod, empresa: str = "") -> dict:
    """Usa o plano da empresa específica; fallback para o global."""
    pi = _plano_info_por_empresa.get(empresa, plano_info)
    try:
        return pi.get(int(cod), {"grupo": "Sem Categoria", "subgrupo": "Sem Categoria"})
    except (TypeError, ValueError):
        return {"grupo": "Sem Categoria", "subgrupo": "Sem Categoria"}


# ── DataFrame builder ─────────────────────────────────────────────────────────
def _to_df(raw: list[dict]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["Data", "Descrição", "Fornecedor", "Valor",
                                     "Grupo", "Subgrupo", "Empresa"])
    rows = []
    for r in raw:
        # Bling traz _grupo_bling/_subgrupo_bling; eGestor usa codPlanoContas
        if "_grupo_bling" in r:
            grupo    = r["_grupo_bling"]
            subgrupo = r["_subgrupo_bling"]
        else:
            # Usa o plano de contas específico da empresa do registro
            info     = _get_info(r.get("codPlanoContas"), r.get("_empresa", ""))
            grupo    = info["grupo"]
            subgrupo = info["subgrupo"]
        rows.append({
            "Data":       (r.get("dtPgto") or r.get("data") or "")[:10],
            "Descrição":  r.get("descricao") or "",
            "Fornecedor": r.get("nomeContato") or "",
            "Valor":      float(r.get("valor") or 0),
            "Grupo":      grupo,
            "Subgrupo":   subgrupo,
            "Empresa":    r.get("_empresa", ""),
        })
    df = pd.DataFrame(rows)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    return df


df_periodo = _to_df(periodo_raw)
df_mes     = _to_df(mes_raw)
df_doze    = _to_df(doze_raw)


# ── KPIs ──────────────────────────────────────────────────────────────────────
def _sum_df(df: pd.DataFrame, d_ini: date, d_fim: date) -> float:
    if df.empty:
        return 0.0
    mask = (df["Data"] >= pd.Timestamp(d_ini)) & (df["Data"] <= pd.Timestamp(d_fim))
    return float(df.loc[mask, "Valor"].sum())


val_periodo = float(df_periodo["Valor"].sum()) if not df_periodo.empty else 0.0

if _is_mes_atual:
    val_hoje   = _sum_df(df_mes, today, today)
    val_semana = _sum_df(df_mes, semana_ini, today)
    val_mes    = float(df_mes["Valor"].sum()) if not df_mes.empty else 0.0

    col1, col2, col3, col4 = st.columns(4)
    kpi_card(col1, "📅", "Realizado Hoje",      brl(val_hoje),
             hoje_str[8:10] + "/" + hoje_str[5:7] + "/" + hoje_str[:4])
    kpi_card(col2, "📆", "Esta Semana",          brl(val_semana),
             f"Seg {semana_ini_str[8:10]}/{semana_ini_str[5:7]} → Hoje")
    kpi_card(col3, "🗓️", "Este Mês",            brl(val_mes),
             f"{mes_ini_str[8:10]}/{mes_ini_str[5:7]} → {hoje_str[8:10]}/{hoje_str[5:7]}")
    kpi_card(col4, "📊", "Lançamentos no Mês",   str(len(df_mes)),
             f"{brl(val_mes / max(today.day, 1))} / dia em média")
else:
    dias_periodo = max((dt_fim - dt_ini).days + 1, 1)
    media_dia    = val_periodo / dias_periodo
    if not df_periodo.empty:
        top_cat = df_periodo.groupby("Grupo")["Valor"].sum().idxmax()
        top_val = df_periodo.groupby("Grupo")["Valor"].sum().max()
    else:
        top_cat, top_val = "—", 0.0

    ant_ini = dt_ini - timedelta(days=dias_periodo)
    ant_fim = dt_ini - timedelta(days=1)
    ant_ini_str = ant_ini.strftime("%Y-%m-%d")
    ant_fim_str = ant_fim.strftime("%Y-%m-%d")
    # Deriva comparativo dos 12m (sem API extra); só busca se mais antigo
    if ant_ini_str >= _doze_ini_str:
        ant_raw = [
            r for r in doze_raw
            if ant_ini_str <= (r.get("dtPgto") or "")[:10] <= ant_fim_str
        ]
    else:
        ant_raw = []   # período muito antigo — omite comparativo
    val_ant = float(sum(float(r.get("valor") or 0) for r in ant_raw))

    if val_ant > 0:
        variacao_pct = (val_periodo - val_ant) / val_ant * 100
        sub_var   = f"{'▲' if variacao_pct > 0 else '▼'} {abs(variacao_pct):.1f}% vs período anterior"
        var_class = "kpi-negative" if variacao_pct > 0 else "kpi-positive"
    else:
        sub_var, var_class = "Sem comparativo anterior", ""

    val_mes_atual = float(df_mes["Valor"].sum()) if not df_mes.empty else 0.0

    col1, col2, col3, col4 = st.columns(4)
    kpi_card(col1, "💰", "Total no Período",   brl(val_periodo),   sub_var, value_class=var_class)
    kpi_card(col2, "📋", "Lançamentos",         str(len(df_periodo)), f"{brl(media_dia)} / dia em média")
    kpi_card(col3, "🏷️", "Maior Grupo",        top_cat[:28] + ("…" if len(top_cat) > 28 else ""), brl(top_val))
    kpi_card(col4, "🗓️", "Mês Atual (ref.)",   brl(val_mes_atual), f"{MESES_PT[today.month]}/{today.year}")

st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

# ── Evolução 12 meses (por Grupo) ────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Evolução 12 Meses — por Grupo</div>', unsafe_allow_html=True)

if not df_doze.empty:
    df12 = df_doze.dropna(subset=["Data"]).copy()
    df12["AnoMes"] = df12["Data"].dt.to_period("M")

    top_grupos = (
        df12.groupby("Grupo")["Valor"].sum()
        .sort_values(ascending=False)
        .head(6)
        .index.tolist()
    )
    df12["GrupoG"] = df12["Grupo"].apply(lambda g: g if g in top_grupos else "Outros")

    pivot = (
        df12.groupby(["AnoMes", "GrupoG"])["Valor"]
        .sum().unstack(fill_value=0).sort_index()
    )
    hoje_p = pd.Period(today, freq="M")
    all_p  = pd.period_range(hoje_p - 11, hoje_p, freq="M")
    pivot  = pivot.reindex(all_p, fill_value=0)
    labels = [f"{MESES_PT[p.month][:3]}/{str(p.year)[2:]}" for p in pivot.index]

    colors_12m = _palette(list(pivot.columns))
    fig12 = go.Figure()
    for g in pivot.columns:
        fig12.add_trace(go.Bar(
            name=g, x=labels, y=pivot[g].values,
            marker_color=colors_12m.get(g, "#6B7280"),
            hovertemplate=f"<b>{g}</b><br>%{{x}}: R$ %{{y:,.2f}}<extra></extra>",
        ))
    totais = pivot.sum(axis=1).values
    fig12.add_trace(go.Scatter(
        x=labels, y=totais, mode="lines+markers", name="Total",
        line=dict(color="#1A1033", width=2, dash="dot"), marker=dict(size=6),
        hovertemplate="<b>Total</b><br>%{x}: R$ %{y:,.2f}<extra></extra>",
    ))
    fig12.update_layout(barmode="stack")
    plotly_layout(fig12)
    fig12.update_layout(
        height=360,
        yaxis=dict(tickformat=",.0f", tickprefix="R$ "),
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0),
    )
    if modo == "Mês específico":
        mes_ref = pd.Period(dt_ini, freq="M")
        if mes_ref in list(pivot.index):
            hi = list(pivot.index).index(mes_ref)
            fig12.add_vline(x=hi, line_color="#7E16B8", line_width=2, line_dash="dash",
                            annotation_text=f"← {labels[hi]}",
                            annotation_font_color="#7E16B8", annotation_font_size=11)
    st.plotly_chart(fig12, use_container_width=True)
else:
    st.info("Sem dados de evolução nos últimos 12 meses.")

# ── Hierarquia: Grupo → Subgrupo ──────────────────────────────────────────────
st.markdown(
    f'<div class="section-title">🗂️ Hierarquia de Categorias — {_label_periodo}</div>',
    unsafe_allow_html=True,
)

if not df_periodo.empty:
    col_tree, col_pie = st.columns([3, 2])

    # ── Treemap (Grupo → Subgrupo) ─────────────────────────────────────────────
    with col_tree:
        grupo_sum = df_periodo.groupby("Grupo")["Valor"].sum()
        sub_sum   = df_periodo.groupby(["Grupo", "Subgrupo"])["Valor"].sum()

        ids_t, labels_t, parents_t, vals_t, texts_t = [], [], [], [], []

        # raiz invisível
        total_geral = df_periodo["Valor"].sum()
        ids_t.append("__root__"); labels_t.append("Total")
        parents_t.append("");     vals_t.append(total_geral)
        texts_t.append(brl(total_geral))

        colors_grp = _palette(sorted(grupo_sum.index.tolist()))

        for grupo, g_val in grupo_sum.sort_values(ascending=False).items():
            gid = f"g::{grupo}"
            ids_t.append(gid);        labels_t.append(grupo)
            parents_t.append("__root__"); vals_t.append(g_val)
            texts_t.append(brl(g_val))

            # subgrupos desse grupo
            subs = sub_sum.get(grupo, None)
            if subs is None:
                continue
            if isinstance(subs, float):  # único subgrupo
                subs = pd.Series({grupo: subs})
            for sub, s_val in subs.sort_values(ascending=False).items():
                if sub == grupo:
                    continue  # não duplica raiz
                sid = f"s::{grupo}::{sub}"
                ids_t.append(sid);  labels_t.append(sub)
                parents_t.append(gid); vals_t.append(s_val)
                texts_t.append(brl(s_val))

        # cores: grupo recebe cor fixa; subgrupo herda versão mais clara
        def _sub_color(label, parent_label):
            base = colors_grp.get(parent_label.replace("g::", ""), "#6B7280")
            # levemente mais claro (adiciona opacidade via rgba)
            return base

        marker_colors = []
        for lid, par in zip(ids_t, parents_t):
            if par == "":
                marker_colors.append("#1A1033")
            elif par == "__root__":
                marker_colors.append(colors_grp.get(lid.replace("g::", ""), "#7E16B8"))
            else:
                # subgrupo: cor do grupo pai
                grp_name = par.replace("g::", "")
                marker_colors.append(colors_grp.get(grp_name, "#6B7280"))

        fig_tree = go.Figure(go.Treemap(
            ids=ids_t,
            labels=labels_t,
            parents=parents_t,
            values=vals_t,
            text=texts_t,
            textinfo="label+text+percent parent",
            branchvalues="total",
            marker=dict(colors=marker_colors),
            hovertemplate="<b>%{label}</b><br>%{text}<br>%{percentParent:.1%} do grupo pai<extra></extra>",
        ))
        fig_tree.update_layout(
            height=480,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=11),
        )
        st.plotly_chart(fig_tree, use_container_width=True)

    # ── Pizza por Grupo (nível 1) ──────────────────────────────────────────────
    with col_pie:
        gs = grupo_sum.sort_values(ascending=False).reset_index()
        gs.columns = ["Grupo", "Valor"]
        gs["Pct"] = gs["Valor"] / gs["Valor"].sum() * 100

        fig_pie = go.Figure(go.Pie(
            labels=gs["Grupo"],
            values=gs["Valor"],
            hole=0.45,
            marker=dict(colors=[colors_grp.get(g, "#6B7280") for g in gs["Grupo"]]),
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f} (%{percent})<extra></extra>",
        ))
        plotly_layout(fig_pie)
        fig_pie.update_layout(
            height=480,
            showlegend=False,
            margin=dict(l=0, r=0, t=30, b=10),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

else:
    st.info("Nenhum pagamento realizado no período selecionado.")


# ── Detalhe por Grupo / Subgrupo ──────────────────────────────────────────────
st.markdown(
    f'<div class="section-title">📋 Detalhe — {_label_periodo}</div>',
    unsafe_allow_html=True,
)

if not df_periodo.empty:
    tab_hierarq, tab_grupo, tab_detalhe = st.tabs([
        "🗂️ Grupo → Subgrupo", "📊 Por Grupo", "📄 Lançamentos"
    ])

    # ── Aba: Grupo → Subgrupo ──────────────────────────────────────────────────
    with tab_hierarq:
        grupos_list = sorted(df_periodo["Grupo"].unique().tolist())
        grp_totals  = df_periodo.groupby("Grupo")["Valor"].sum().sort_values(ascending=False)
        total_all   = df_periodo["Valor"].sum()

        for grupo in grp_totals.index:
            g_val = grp_totals[grupo]
            g_pct = g_val / total_all * 100

            # Cabeçalho do grupo com expander
            with st.expander(
                f"**{grupo}** — {brl(g_val)}  ({g_pct:.1f}%)",
                expanded=False,
            ):
                df_grp = df_periodo[df_periodo["Grupo"] == grupo]
                sub_agg = (
                    df_grp.groupby("Subgrupo")
                    .agg(Total=("Valor", "sum"), Qtd=("Valor", "count"))
                    .sort_values("Total", ascending=False)
                    .reset_index()
                )
                sub_agg["% do Grupo"] = (sub_agg["Total"] / g_val * 100).map("{:.1f}%".format)
                sub_agg["Total (R$)"] = sub_agg["Total"].map(lambda v: f"R$ {v:,.2f}")

                # Exclui linha onde subgrupo == grupo (sem subgrupo real)
                sub_show = sub_agg[sub_agg["Subgrupo"] != grupo] if len(sub_agg) > 1 else sub_agg
                st.dataframe(
                    sub_show[["Subgrupo", "Total (R$)", "Qtd", "% do Grupo"]],
                    use_container_width=True, hide_index=True
                )

        st.markdown(f"**Total geral: {brl(total_all)}**")

        # Export
        buf_h = io.BytesIO()
        with pd.ExcelWriter(buf_h, engine="openpyxl") as xw:
            for grupo in grp_totals.index:
                df_grp = df_periodo[df_periodo["Grupo"] == grupo]
                sub_agg = (
                    df_grp.groupby("Subgrupo")
                    .agg(Total=("Valor", "sum"), Qtd=("Valor", "count"))
                    .sort_values("Total", ascending=False)
                    .reset_index()
                )
                sub_agg["Total (R$)"] = sub_agg["Total"].map(lambda v: f"R$ {v:,.2f}")
                sheet = grupo[:31].replace("/", "-")
                sub_agg[["Subgrupo", "Total (R$)", "Qtd"]].to_excel(xw, index=False, sheet_name=sheet)
        st.download_button(
            "⬇️ Exportar hierarquia",
            data=buf_h.getvalue(),
            file_name=f"realizado_hierarquia_{dt_ini_str}_{dt_fim_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ── Aba: Resumo por Grupo ──────────────────────────────────────────────────
    with tab_grupo:
        resumo = (
            df_periodo.groupby("Grupo")
            .agg(Total=("Valor", "sum"), Qtd=("Valor", "count"))
            .sort_values("Total", ascending=False)
            .reset_index()
        )
        resumo["% do Total"] = (resumo["Total"] / resumo["Total"].sum() * 100).map("{:.1f}%".format)
        resumo["Total (R$)"] = resumo["Total"].map(lambda v: f"R$ {v:,.2f}")
        st.dataframe(resumo[["Grupo", "Total (R$)", "Qtd", "% do Total"]],
                     use_container_width=True, hide_index=True)
        st.markdown(f"**Total: {brl(resumo['Total'].sum())}**")

        buf_g = io.BytesIO()
        with pd.ExcelWriter(buf_g, engine="openpyxl") as xw:
            resumo[["Grupo", "Total (R$)", "Qtd", "% do Total"]].to_excel(
                xw, index=False, sheet_name="Por Grupo")
        st.download_button(
            "⬇️ Exportar por grupo",
            data=buf_g.getvalue(),
            file_name=f"realizado_grupos_{dt_ini_str}_{dt_fim_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ── Aba: Lançamentos individuais ───────────────────────────────────────────
    with tab_detalhe:
        c1, c2 = st.columns(2)

        # Grupo — selectbox (único)
        grupos_filtro = ["Todos"] + sorted(df_periodo["Grupo"].unique().tolist())
        grupo_sel_f   = c1.selectbox("🔍 Grupo", grupos_filtro, key="real_grp_sel")

        df_filtrado = df_periodo.copy()
        if grupo_sel_f != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Grupo"] == grupo_sel_f]

        # Subgrupo — multiselect (múltipla seleção)
        subs_disponiveis = sorted(df_filtrado["Subgrupo"].unique().tolist())
        subs_sel = c2.multiselect(
            "🔍 Subgrupo (selecione um ou mais)",
            subs_disponiveis,
            default=[],
            key="real_sub_sel",
            placeholder="Todos os subgrupos",
        )
        if subs_sel:
            df_filtrado = df_filtrado[df_filtrado["Subgrupo"].isin(subs_sel)]

        df_filtrado = df_filtrado.sort_values("Data", ascending=False).reset_index(drop=True)

        # ── Tabela com checkbox de seleção ────────────────────────────────────
        df_filtrado["Data_fmt"]   = df_filtrado["Data"].dt.strftime("%d/%m/%Y")
        df_filtrado["Valor (R$)"] = df_filtrado["Valor"].map(lambda v: f"R$ {v:,.2f}")

        cols_show = ["Data_fmt", "Grupo", "Subgrupo", "Descrição", "Fornecedor", "Valor (R$)", "Empresa"]
        df_display = df_filtrado[cols_show].copy()
        df_display.columns = ["Data", "Grupo", "Subgrupo", "Descrição", "Fornecedor", "Valor (R$)", "Empresa"]

        # Usa st.data_editor com coluna de seleção para somar itens marcados
        df_display.insert(0, "✅", False)
        edited = st.data_editor(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={"✅": st.column_config.CheckboxColumn("✅", width="small")},
            key="real_lancamentos_editor",
        )

        # Totais
        total_filtrado = df_filtrado["Valor"].sum()
        selecionados   = edited[edited["✅"] == True]
        n_sel          = len(selecionados)

        if n_sel > 0:
            # Recupera valores numéricos dos itens selecionados
            total_sel = df_filtrado.loc[edited["✅"].values, "Valor"].sum()
            col_t1, col_t2 = st.columns(2)
            col_t1.markdown(
                f"**Subtotal ({len(df_filtrado)} lançamentos):** {brl(total_filtrado)}",
                unsafe_allow_html=True,
            )
            col_t2.markdown(
                f"<span style='background:#EDE9F8;padding:6px 14px;border-radius:8px;"
                f"font-weight:700;color:#4A1259'>✅ {n_sel} selecionado(s): "
                f"{brl(total_sel)}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"**Subtotal:** {brl(total_filtrado)} &nbsp;·&nbsp; "
                f"**{len(df_filtrado)} lançamentos** — marque linhas para somar",
                unsafe_allow_html=True,
            )

        buf_d = io.BytesIO()
        with pd.ExcelWriter(buf_d, engine="openpyxl") as xw:
            df_filtrado[cols_show].to_excel(xw, index=False, sheet_name="Lançamentos")
        st.download_button(
            "⬇️ Exportar lançamentos",
            data=buf_d.getvalue(),
            file_name=f"realizado_lancamentos_{dt_ini_str}_{dt_fim_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("Nenhum dado disponível para o período selecionado.")
