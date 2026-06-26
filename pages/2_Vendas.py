"""Página 2 — Vendas & Vendedores."""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from utils import (GLOBAL_CSS, ASSETS, BRAND, NOMES, CHART_COLORS,
                   brl, soma, kpi_card, plotly_layout, sidebar_header,
                   load_company_data, load_vendas_ano,
                   get_empresas_disponiveis, load_data_unificado,
                   load_vendas_ano_unificado,
                   load_companies_data, load_companies_vendas_ano)

st.set_page_config(page_title="Vendas | GoGenetic", page_icon="🛒", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
sidebar_header()

with st.sidebar:
    _disponiveis = get_empresas_disponiveis()
    empresa_opcoes = ["Todas"] + _disponiveis
    empresa_sel = st.selectbox("🏢 Empresa", empresa_opcoes)
    if empresa_sel != "Todas" and empresa_sel in BRAND:
        st.image(BRAND[empresa_sel]["logo"], use_column_width=True)
    empresas_ativas = _disponiveis if empresa_sel == "Todas" else [empresa_sel]

    st.markdown("---")
    _period_map = {
        "Este mês":        (date.today().replace(day=1), date.today()),
        "Últimos 30 dias": (date.today() - timedelta(days=30), date.today()),
        "Últimos 60 dias": (date.today() - timedelta(days=60), date.today()),
        "Últimos 90 dias": (date.today() - timedelta(days=90), date.today()),
        "Este ano":        (date(date.today().year, 1, 1), date.today()),
        "Personalizado":   None,
    }
    periodo_sel = st.selectbox("📅 Período", list(_period_map.keys()))
    if periodo_sel == "Personalizado":
        c1, c2 = st.columns(2)
        _dt_ini = c1.date_input("De",  date.today().replace(day=1))
        _dt_fim = c2.date_input("Até", date.today())
    else:
        _dt_ini, _dt_fim = _period_map[periodo_sel]
    dt_ini = _dt_ini.strftime("%Y-%m-%d")
    dt_fim = _dt_fim.strftime("%Y-%m-%d")

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ Cache: 5 min")

# ── Carrega dados (empresas em paralelo) ───────────────────────────────────────
with st.spinner("Carregando vendas..."):
    ano_atual   = date.today().year
    _period_map = load_companies_data(empresas_ativas, dt_ini, dt_fim)
    _ano_map    = load_companies_vendas_ano(empresas_ativas, ano_atual)

    vendas, vendas_12m = [], []
    for nome in empresas_ativas:
        for item in _period_map[nome]["vendas"]:
            vendas.append({**item, "empresa": nome})
        for item in _ano_map[nome]:
            vendas_12m.append({**item, "empresa": nome})

total_vendas = soma(vendas, "valorTotal")
ticket_medio = total_vendas / len(vendas) if vendas else 0

# ── Header ─────────────────────────────────────────────────────────────────────
empresa_label = empresas_ativas[0] if len(empresas_ativas) == 1 else "Grupo GoGenetic"
st.markdown(f"""
<p class="page-title">🛒 Vendas & Vendedores</p>
<p class="page-sub">{empresa_label} · {dt_ini} → {dt_fim}</p>
""", unsafe_allow_html=True)

# ── KPIs ───────────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
kpi_card(c1, "🛒", "Total Vendas",  brl(total_vendas), f"{len(vendas)} pedidos")
kpi_card(c2, "🎯", "Ticket Médio",  brl(ticket_medio), "por pedido")
kpi_card(c3, "🏢", "Empresas",      str(len(empresas_ativas)), "ativas no período")

# ── Gráficos de vendas ─────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Vendas por Dia</div>", unsafe_allow_html=True)

if vendas:
    df_v = pd.DataFrame(vendas)
    df_v["dtVenda"]    = pd.to_datetime(df_v["dtVenda"], errors="coerce")
    df_v["valorTotal"] = pd.to_numeric(df_v["valorTotal"], errors="coerce")
    df_v = df_v.dropna(subset=["dtVenda", "valorTotal"])

    col_bar, col_pie = st.columns([3, 2])
    with col_bar:
        if len(empresas_ativas) > 1:
            df_d = df_v.groupby(["dtVenda","empresa"])["valorTotal"].sum().reset_index()
            fig  = px.bar(df_d, x="dtVenda", y="valorTotal", color="empresa",
                          color_discrete_map=CHART_COLORS,
                          labels={"dtVenda":"","valorTotal":"R$","empresa":""})
        else:
            df_d = df_v.groupby("dtVenda")["valorTotal"].sum().reset_index()
            cor  = BRAND.get(empresas_ativas[0],{}).get("primary","#7E16B8")
            fig  = px.bar(df_d, x="dtVenda", y="valorTotal",
                          labels={"dtVenda":"","valorTotal":"R$"},
                          color_discrete_sequence=[cor])
        plotly_layout(fig, "Vendas diárias")
        st.plotly_chart(fig, use_container_width=True)

    with col_pie:
        if len(empresas_ativas) > 1:
            df_emp = df_v.groupby("empresa")["valorTotal"].sum().reset_index()
            fig2 = px.pie(df_emp, names="empresa", values="valorTotal",
                          color="empresa", color_discrete_map=CHART_COLORS, hole=0.45)
            fig2.update_traces(textinfo="percent+label", textfont_size=11)
            plotly_layout(fig2, "Participação por empresa")
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            # Top clientes
            df_cli = df_v.groupby("nomeContato")["valorTotal"].sum().reset_index().sort_values("valorTotal", ascending=False).head(5)
            cor = BRAND.get(empresas_ativas[0],{}).get("primary","#7E16B8")
            fig3 = px.bar(df_cli, x="valorTotal", y="nomeContato", orientation="h",
                          color_discrete_sequence=[cor],
                          labels={"valorTotal":"R$","nomeContato":""})
            plotly_layout(fig3, "Top 5 clientes")
            st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Nenhuma venda no período.")

# ── Evolução 12 meses ──────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Evolução Mensal — Ano Atual</div>", unsafe_allow_html=True)

if vendas_12m:
    df_12 = pd.DataFrame(vendas_12m)
    df_12["dtVenda"]    = pd.to_datetime(df_12["dtVenda"], errors="coerce")
    df_12["valorTotal"] = pd.to_numeric(df_12["valorTotal"], errors="coerce")
    df_12 = df_12.dropna(subset=["dtVenda","valorTotal"])
    df_12["mes"] = df_12["dtVenda"].dt.to_period("M").astype(str)

    if len(empresas_ativas) > 1:
        df_12g = df_12.groupby(["mes","empresa"])["valorTotal"].sum().reset_index()
        fig12  = px.line(df_12g, x="mes", y="valorTotal", color="empresa",
                         color_discrete_map=CHART_COLORS, markers=True,
                         labels={"mes":"","valorTotal":"R$","empresa":""})
    else:
        df_12g = df_12.groupby("mes")["valorTotal"].sum().reset_index()
        cor    = BRAND.get(empresas_ativas[0],{}).get("primary","#7E16B8")
        fig12  = px.area(df_12g, x="mes", y="valorTotal",
                         labels={"mes":"","valorTotal":"R$"},
                         color_discrete_sequence=[cor])
    plotly_layout(fig12)
    st.plotly_chart(fig12, use_container_width=True)

# ── Top 10 Clientes ────────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Top 10 Clientes por Valor</div>", unsafe_allow_html=True)

if vendas:
    df_cli = pd.DataFrame(vendas)
    df_cli["valorTotal"] = pd.to_numeric(df_cli["valorTotal"], errors="coerce")
    df_cli["nomeContato"] = df_cli["nomeContato"].fillna("Sem cliente")
    df_top = (df_cli.groupby("nomeContato")
              .agg(total=("valorTotal","sum"), qtd=("codigo","count"))
              .reset_index().sort_values("total", ascending=False).head(10))
    df_top["ticket"] = df_top["total"] / df_top["qtd"]
    df_top["pct"]    = (df_top["total"] / df_top["total"].sum() * 100).round(1)

    col_tl, col_tr = st.columns([3, 2])
    with col_tl:
        fig_top = px.bar(df_top.sort_values("total"), x="total", y="nomeContato",
                         orientation="h",
                         color="total",
                         color_continuous_scale=["#CD76FF","#7E16B8","#370950"],
                         labels={"total":"R$","nomeContato":""},
                         text=df_top.sort_values("total")["total"].apply(brl))
        fig_top.update_traces(textposition="outside", textfont_size=10)
        fig_top.update_layout(coloraxis_showscale=False)
        plotly_layout(fig_top, "Top 10 clientes")
        st.plotly_chart(fig_top, use_container_width=True)

    with col_tr:
        df_show = df_top.copy()
        df_show["Total"]        = df_show["total"].apply(brl)
        df_show["Qtd"]          = df_show["qtd"]
        df_show["Ticket Médio"] = df_show["ticket"].apply(brl)
        df_show["Part. %"]      = df_show["pct"].astype(str) + "%"
        df_show = df_show.rename(columns={"nomeContato":"Cliente"})
        st.dataframe(df_show[["Cliente","Total","Qtd","Ticket Médio","Part. %"]],
                     use_container_width=True, hide_index=True)

# ── Vendedores ─────────────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Desempenho por Vendedor</div>", unsafe_allow_html=True)

if vendas:
    df_vd = pd.DataFrame(vendas)
    df_vd["valorTotal"]    = pd.to_numeric(df_vd["valorTotal"], errors="coerce")
    df_vd["nomeVendedor"]  = df_vd.get("nomeVendedor", pd.Series(dtype=str)).fillna("Sem vendedor").replace("","Sem vendedor")

    df_rank = (df_vd.groupby("nomeVendedor")
               .agg(total=("valorTotal","sum"), qtd=("codigo","count"))
               .reset_index().sort_values("total", ascending=False))
    df_rank["ticket"] = df_rank["total"] / df_rank["qtd"]
    df_rank["pct"]    = (df_rank["total"] / df_rank["total"].sum() * 100).round(1)

    col_vl, col_vr = st.columns([3, 2])
    with col_vl:
        fig_v = px.bar(df_rank.sort_values("total"), x="total", y="nomeVendedor",
                       orientation="h",
                       color="total",
                       color_continuous_scale=["#CD76FF","#7E16B8","#370950"],
                       labels={"total":"R$","nomeVendedor":""},
                       text=df_rank.sort_values("total")["total"].apply(brl))
        fig_v.update_traces(textposition="outside", textfont_size=10)
        fig_v.update_layout(coloraxis_showscale=False)
        plotly_layout(fig_v, "Ranking de vendedores")
        st.plotly_chart(fig_v, use_container_width=True)

    with col_vr:
        df_rv = df_rank.copy()
        df_rv["Total"]        = df_rv["total"].apply(brl)
        df_rv["Qtd Vendas"]   = df_rv["qtd"]
        df_rv["Ticket Médio"] = df_rv["ticket"].apply(brl)
        df_rv["Part. %"]      = df_rv["pct"].astype(str) + "%"
        df_rv = df_rv.rename(columns={"nomeVendedor":"Vendedor"})
        st.dataframe(df_rv[["Vendedor","Total","Qtd Vendas","Ticket Médio","Part. %"]],
                     use_container_width=True, hide_index=True)

# ── Tabela detalhe ─────────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Detalhe das Vendas</div>", unsafe_allow_html=True)
if vendas:
    df_det = pd.DataFrame(vendas)

    # debug temporário — remover depois
    if "tags" in df_det.columns:
        st.caption(f"DEBUG tags sample: {df_det['tags'].dropna().head(3).tolist()}")
    else:
        st.caption("DEBUG: coluna 'tags' não existe no DataFrame")

    def _cod_s(tags):
        try:
            if not tags:
                return "—"
            items = tags if isinstance(tags, list) else str(tags).split(",")
            for t in items:
                nome = str(t.get("nome") or t.get("tag") or "") if isinstance(t, dict) else str(t)
                nome = nome.strip()
                if len(nome) > 1 and nome[0].upper() == "S" and nome[1:].isdigit():
                    return nome.upper()
        except Exception:
            pass
        return "—"

    if "tags" in df_det.columns:
        df_det["Cód. S"] = df_det["tags"].apply(_cod_s)
    else:
        df_det["Cód. S"] = "—"

    cols = [c for c in ["empresa","dtVenda","nomeVendedor","nomeContato","Cód. S","valorTotal"] if c in df_det.columns]
    df_det = df_det[cols].rename(columns={
        "empresa":"Empresa","dtVenda":"Data","nomeVendedor":"Vendedor",
        "nomeContato":"Cliente","valorTotal":"Valor"})
    if "Valor" in df_det.columns:
        df_det["Valor"] = df_det["Valor"].apply(brl)
    st.dataframe(df_det, use_container_width=True, hide_index=True)
else:
    st.info("Nenhuma venda no período.")
