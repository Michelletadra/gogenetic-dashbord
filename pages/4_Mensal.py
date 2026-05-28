"""Página 4 — Detalhamento Mensal (mês a mês)."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from calendar import monthrange
from utils import (GLOBAL_CSS, BRAND, NOMES, CHART_COLORS, MESES_PT,
                   brl, soma, kpi_card, plotly_layout, sidebar_header,
                   load_metas, get_empresas_disponiveis,
                   load_data_unificado, load_vendas_ano_unificado)

st.set_page_config(page_title="Mensal | GoGenetic", page_icon="📅", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
sidebar_header()

with st.sidebar:
    _disponiveis   = get_empresas_disponiveis()
    empresa_opcoes = ["Todas"] + _disponiveis
    empresa_sel    = st.selectbox("🏢 Empresa", empresa_opcoes)
    if empresa_sel != "Todas" and empresa_sel in BRAND:
        st.image(BRAND[empresa_sel]["logo"], use_column_width=True)
    empresas_ativas = _disponiveis if empresa_sel == "Todas" else [empresa_sel]

    st.markdown("---")
    ano_atual = date.today().year
    ano = st.selectbox("📅 Ano", list(range(ano_atual, ano_atual - 4, -1)), index=0)

    # Todos os 12 meses disponíveis — padrão: mês atual (ou dezembro se ano passado)
    meses_disponiveis = {MESES_PT[m]: m for m in range(1, 13)}
    mes_padrao = date.today().month if ano == ano_atual else 12
    mes_nome = st.selectbox("📆 Mês", list(meses_disponiveis.keys()),
                             index=mes_padrao - 1)
    mes = meses_disponiveis[mes_nome]

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ Cache: 5 min")

# ── Datas do mês selecionado ───────────────────────────────────────────────────
ultimo_dia = monthrange(ano, mes)[1]
dt_ini = date(ano, mes, 1).strftime("%Y-%m-%d")
dt_fim = date(ano, mes, ultimo_dia).strftime("%Y-%m-%d")

# Mesmo mês do ano anterior (para comparação)
dt_ini_ant = date(ano - 1, mes, 1).strftime("%Y-%m-%d")
dt_fim_ant = date(ano - 1, mes, monthrange(ano - 1, mes)[1]).strftime("%Y-%m-%d")

# ── Carrega dados ──────────────────────────────────────────────────────────────
with st.spinner(f"Carregando {mes_nome} {ano}..."):
    vendas, fat, rec, pag = [], [], [], []
    vendas_ant, fat_ant   = [], []

    for nome in empresas_ativas:
        d     = load_data_unificado(nome, dt_ini, dt_fim)
        d_ant = load_data_unificado(nome, dt_ini_ant, dt_fim_ant)

        for item in d["vendas"]:         vendas.append({**item, "empresa": nome})
        for item in d["faturamento"]:    fat.append({**item, "empresa": nome})
        for item in d["contas_receber"]: rec.append({**item, "empresa": nome})
        for item in d["contas_pagar"]:   pag.append({**item, "empresa": nome})
        for item in d_ant["vendas"]:      vendas_ant.append({**item, "empresa": nome})
        for item in d_ant["faturamento"]: fat_ant.append({**item, "empresa": nome})

metas = load_metas(ano)
meta_mes = float(metas.get(mes, 0))

total_v   = soma(vendas, "valorTotal")
total_f   = soma(fat,    "valor")
total_r   = soma(rec,    "valor")
total_p   = soma(pag,    "valor")
saldo     = total_r - total_p
total_v_ant = soma(vendas_ant, "valorTotal")
total_f_ant = soma(fat_ant,    "valor")
var_v = ((total_v / total_v_ant - 1) * 100) if total_v_ant else None
var_f = ((total_f / total_f_ant - 1) * 100) if total_f_ant else None
pct_meta = (total_v / meta_mes * 100) if meta_mes else None

ticket = total_v / len(vendas) if vendas else 0

# ── Header ─────────────────────────────────────────────────────────────────────
empresa_label = empresas_ativas[0] if len(empresas_ativas) == 1 else "Grupo GoGenetic"
st.markdown(f"""
<p class="page-title">📅 {mes_nome} {ano}</p>
<p class="page-sub">{empresa_label} · detalhamento completo do mês</p>
""", unsafe_allow_html=True)

# ── KPIs ───────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)

def delta_str(var):
    if var is None: return "sem histórico"
    sinal = "▲" if var >= 0 else "▼"
    return f"{sinal} {abs(var):.1f}% vs {ano-1}"

kpi_card(c1, "🛒", "Vendas",        brl(total_v),   delta_str(var_v),
         value_class="kpi-positive" if (var_v or 0) >= 0 else "kpi-negative")
kpi_card(c2, "🎯", "Ticket Médio",  brl(ticket),    f"{len(vendas)} pedidos")
kpi_card(c3, "💰", "Faturado",      brl(total_f),   delta_str(var_f),
         value_class="kpi-positive" if (var_f or 0) >= 0 else "kpi-negative")
kpi_card(c4, "📥", "A Receber",     brl(total_r),   f"{len(rec)} títulos",  border="rgba(36,183,140,0.3)")
kpi_card(c5, "📤", "A Pagar",       brl(total_p),   f"{len(pag)} títulos",  border="rgba(255,103,47,0.3)")
kpi_card(c6, "📈", "Saldo",         brl(abs(saldo)), "Receber − Pagar",
         border="rgba(36,183,140,0.4)" if saldo >= 0 else "rgba(255,103,47,0.4)",
         value_class="kpi-positive" if saldo >= 0 else "kpi-negative")

# ── Barra de meta ──────────────────────────────────────────────────────────────
if meta_mes > 0:
    pct = min(pct_meta, 100)
    cor_barra = "#24B78C" if pct_meta >= 100 else ("#F5A623" if pct_meta >= 70 else "#FF672F")
    st.markdown(f"""
    <div style='background:#F5F0FA;border-radius:10px;padding:14px 20px;margin:16px 0 4px 0'>
      <div style='display:flex;justify-content:space-between;margin-bottom:6px'>
        <span style='font-size:.75rem;font-weight:600;color:#7E16B8;text-transform:uppercase;letter-spacing:1px'>
          🎯 Meta de Vendas — {mes_nome}
        </span>
        <span style='font-size:.85rem;font-weight:700;color:{cor_barra}'>
          {brl(total_v)} / {brl(meta_mes)} &nbsp;·&nbsp; {pct_meta:.1f}%
        </span>
      </div>
      <div style='background:#E0D4F0;border-radius:6px;height:10px;overflow:hidden'>
        <div style='background:{cor_barra};width:{pct:.1f}%;height:100%;border-radius:6px;
             transition:width .5s ease'></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_vend, tab_fin, tab_contas = st.tabs([
    f"🛒 Vendas ({len(vendas)})",
    f"💰 Financeiro",
    f"💳 Contas ({len(rec) + len(pag)})",
])

# ══════════════════════════════════════════════════════════════════════════════
with tab_vend:
    if not vendas:
        st.info("Nenhuma venda no período.")
    else:
        df_v = pd.DataFrame(vendas)
        df_v["dtVenda"]    = pd.to_datetime(df_v["dtVenda"], errors="coerce")
        df_v["valorTotal"] = pd.to_numeric(df_v["valorTotal"], errors="coerce")
        df_v = df_v.dropna(subset=["dtVenda", "valorTotal"])

        # Vendas diárias
        st.markdown("<div class='section-title'>Vendas por Dia</div>", unsafe_allow_html=True)
        if len(empresas_ativas) > 1:
            df_d = df_v.groupby(["dtVenda", "empresa"])["valorTotal"].sum().reset_index()
            fig_d = px.bar(df_d, x="dtVenda", y="valorTotal", color="empresa",
                           color_discrete_map=CHART_COLORS,
                           labels={"dtVenda": "", "valorTotal": "R$", "empresa": ""})
        else:
            df_d = df_v.groupby("dtVenda")["valorTotal"].sum().reset_index()
            cor  = BRAND.get(empresas_ativas[0], {}).get("primary", "#7E16B8")
            fig_d = px.bar(df_d, x="dtVenda", y="valorTotal",
                           labels={"dtVenda": "", "valorTotal": "R$"},
                           color_discrete_sequence=[cor])
        plotly_layout(fig_d)
        st.plotly_chart(fig_d, use_container_width=True)

        col_cli, col_vend = st.columns(2)

        # Top 10 clientes
        with col_cli:
            st.markdown("<div class='section-title'>Top 10 Clientes</div>", unsafe_allow_html=True)
            df_cli = (df_v.groupby("nomeContato")["valorTotal"]
                      .sum().reset_index()
                      .sort_values("valorTotal", ascending=False).head(10))
            df_cli["nomeContato"] = df_cli["nomeContato"].fillna("Sem cliente")
            fig_cli = px.bar(df_cli.sort_values("valorTotal"), x="valorTotal", y="nomeContato",
                             orientation="h",
                             color="valorTotal",
                             color_continuous_scale=["#CD76FF", "#7E16B8", "#370950"],
                             labels={"valorTotal": "R$", "nomeContato": ""},
                             text=df_cli.sort_values("valorTotal")["valorTotal"].apply(brl))
            fig_cli.update_traces(textposition="outside", textfont_size=9)
            fig_cli.update_layout(coloraxis_showscale=False, height=320)
            plotly_layout(fig_cli)
            st.plotly_chart(fig_cli, use_container_width=True)

        # Ranking vendedores
        with col_vend:
            st.markdown("<div class='section-title'>Vendedores</div>", unsafe_allow_html=True)
            df_vd = df_v.copy()
            df_vd["nomeVendedor"] = (df_vd.get("nomeVendedor", pd.Series(dtype=str))
                                     .fillna("Sem vendedor").replace("", "Sem vendedor"))
            df_rank = (df_vd.groupby("nomeVendedor")
                       .agg(total=("valorTotal", "sum"), qtd=("valorTotal", "count"))
                       .reset_index().sort_values("total", ascending=False))
            df_rank["ticket"] = df_rank["total"] / df_rank["qtd"]
            df_rank["pct"]    = (df_rank["total"] / df_rank["total"].sum() * 100).round(1)
            df_show = df_rank.copy()
            df_show["Total"]        = df_show["total"].apply(brl)
            df_show["Qtd"]          = df_show["qtd"]
            df_show["Ticket Médio"] = df_show["ticket"].apply(brl)
            df_show["Part. %"]      = df_show["pct"].astype(str) + "%"
            df_show = df_show.rename(columns={"nomeVendedor": "Vendedor"})
            st.dataframe(df_show[["Vendedor", "Total", "Qtd", "Ticket Médio", "Part. %"]],
                         use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
with tab_fin:
    st.markdown("<div class='section-title'>Comparação com o Mesmo Mês do Ano Anterior</div>",
                unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        # Gráfico comparativo de vendas e faturamento: este ano vs ano anterior
        categorias = ["Vendas", "Faturado"]
        vals_atual = [total_v, total_f]
        vals_ant   = [total_v_ant, total_f_ant]

        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            name=str(ano),
            x=categorias, y=vals_atual,
            marker_color="#7E16B8",
            text=[brl(v) for v in vals_atual],
            textposition="outside", textfont=dict(size=10),
        ))
        fig_comp.add_trace(go.Bar(
            name=str(ano - 1),
            x=categorias, y=vals_ant,
            marker_color="#CD76FF", opacity=0.7,
            text=[brl(v) for v in vals_ant],
            textposition="outside", textfont=dict(size=10),
        ))
        if meta_mes > 0:
            fig_comp.add_trace(go.Scatter(
                name=f"Meta {ano}",
                x=["Vendas"], y=[meta_mes],
                mode="markers",
                marker=dict(symbol="line-ew", size=20, color="#FF672F",
                            line=dict(width=3, color="#FF672F")),
            ))
        fig_comp.update_layout(
            barmode="group", bargap=0.25,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Sora, sans-serif", color="#1A0A2E", size=11),
            margin=dict(t=30, b=10, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                        font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(gridcolor="rgba(126,22,184,0.07)"),
            yaxis=dict(gridcolor="rgba(126,22,184,0.07)", tickformat=",.0f"),
            height=340,
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    with col_b:
        # Tabela resumo comparativo
        def fmt_var(v_atual, v_ant):
            if v_ant == 0: return "—"
            delta = (v_atual / v_ant - 1) * 100
            sinal = "▲" if delta >= 0 else "▼"
            cor   = "kpi-positive" if delta >= 0 else "kpi-negative"
            return f"{sinal} {abs(delta):.1f}%"

        rows = [
            {"Indicador": "Vendas",        f"{ano}": brl(total_v),   f"{ano-1}": brl(total_v_ant), "Variação": fmt_var(total_v, total_v_ant)},
            {"Indicador": "Faturado",      f"{ano}": brl(total_f),   f"{ano-1}": brl(total_f_ant), "Variação": fmt_var(total_f, total_f_ant)},
            {"Indicador": "Ticket Médio",  f"{ano}": brl(ticket),    f"{ano-1}": brl(soma(vendas_ant, "valorTotal") / len(vendas_ant) if vendas_ant else 0), "Variação": "—"},
            {"Indicador": "A Receber",     f"{ano}": brl(total_r),   f"{ano-1}": "—", "Variação": "—"},
            {"Indicador": "A Pagar",       f"{ano}": brl(total_p),   f"{ano-1}": "—", "Variação": "—"},
            {"Indicador": "Saldo",         f"{ano}": brl(abs(saldo)), f"{ano-1}": "—", "Variação": "—"},
        ]
        if meta_mes > 0:
            rows.insert(1, {
                "Indicador": "Meta",
                f"{ano}":    brl(meta_mes),
                f"{ano-1}":  "—",
                "Variação":  f"{'▲' if pct_meta >= 100 else '▼'} {pct_meta:.1f}% atingido",
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=320)

    # Participação por empresa (se múltiplas)
    if len(empresas_ativas) > 1 and vendas:
        st.markdown("<div class='section-title'>Participação por Empresa — Vendas</div>",
                    unsafe_allow_html=True)
        df_emp = pd.DataFrame(vendas)
        df_emp["valorTotal"] = pd.to_numeric(df_emp["valorTotal"], errors="coerce")
        df_emp = df_emp.groupby("empresa")["valorTotal"].sum().reset_index()
        fig_pie = px.pie(df_emp, names="empresa", values="valorTotal",
                         color="empresa", color_discrete_map=CHART_COLORS, hole=0.45)
        fig_pie.update_traces(textinfo="percent+label", textfont_size=11)
        plotly_layout(fig_pie)
        fig_pie.update_layout(showlegend=False, height=280, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_pie, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
with tab_contas:
    col_r, col_p = st.columns(2)

    with col_r:
        st.markdown("#### 📥 A Receber")
        if rec:
            df_r = pd.DataFrame(rec)
            df_r["valor"]  = pd.to_numeric(df_r["valor"], errors="coerce").fillna(0)
            df_r["dtVenc"] = pd.to_datetime(df_r["dtVenc"], errors="coerce").dt.strftime("%d/%m/%Y")
            cols_r = [c for c in ["empresa", "dtVenc", "nomeContato", "valor", "descricao"] if c in df_r.columns]
            df_r = df_r[cols_r].rename(columns={
                "empresa": "Empresa", "dtVenc": "Vencimento",
                "nomeContato": "Cliente", "valor": "Valor", "descricao": "Descrição"})
            if "Valor" in df_r.columns:
                df_r["Valor"] = pd.to_numeric(
                    df_r["Valor"], errors="coerce").apply(brl)
            st.dataframe(df_r, use_container_width=True, hide_index=True)
            st.caption(f"Total: **{brl(total_r)}** · {len(rec)} títulos")
        else:
            st.info("Nenhum título a receber no mês.")

    with col_p:
        st.markdown("#### 📤 A Pagar")
        if pag:
            df_p = pd.DataFrame(pag)
            df_p["valor"]  = pd.to_numeric(df_p["valor"], errors="coerce").fillna(0)
            df_p["dtVenc"] = pd.to_datetime(df_p["dtVenc"], errors="coerce").dt.strftime("%d/%m/%Y")
            cols_p = [c for c in ["empresa", "dtVenc", "nomeContato", "valor", "descricao"] if c in df_p.columns]
            df_p = df_p[cols_p].rename(columns={
                "empresa": "Empresa", "dtVenc": "Vencimento",
                "nomeContato": "Fornecedor", "valor": "Valor", "descricao": "Descrição"})
            if "Valor" in df_p.columns:
                df_p["Valor"] = pd.to_numeric(
                    df_p["Valor"], errors="coerce").apply(brl)
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            st.caption(f"Total: **{brl(total_p)}** · {len(pag)} títulos")
        else:
            st.info("Nenhum título a pagar no mês.")
