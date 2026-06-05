"""Página 1 — Faturamento Mensal vs Meta + Comparação Histórica."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date
from utils import (GLOBAL_CSS, ASSETS, BRAND, NOMES, NOME_YOU, CHART_COLORS,
                   brl, soma, kpi_card, plotly_layout, sidebar_header,
                   get_clients, load_vendas_ano, load_metas, save_metas,
                   MESES_PT, get_empresas_disponiveis, load_vendas_ano_unificado,
                   load_companies_vendas_ano, _parallel)

st.set_page_config(page_title="Faturamento | GoGenetic", page_icon="📊", layout="wide")
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
    ano_atual_real = date.today().year
    anos_disponiveis = list(range(ano_atual_real, ano_atual_real - 4, -1))  # ex: 2026,2025,2024,2023
    ano = st.selectbox("📅 Ano principal", anos_disponiveis, index=0)

    st.markdown("---")
    st.markdown("**🎯 Metas Mensais**")
    metas_salvas = load_metas(ano)
    metas_input = {}
    for m in range(1, 13):
        metas_input[m] = st.number_input(
            MESES_PT[m],
            value=float(metas_salvas.get(m, 0)),
            step=1000.0,
            format="%.0f",
            key=f"meta_{ano}_{m}",
        )
    if st.button("💾 Salvar metas", use_container_width=True):
        save_metas(ano, metas_input)
        st.success("Metas salvas!")

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ Cache: 1h para dados anuais")

# ── Carrega dados do ano principal (empresas em paralelo) ──────────────────────
with st.spinner(f"Carregando faturamento de {ano}..."):
    _ano_data = load_companies_vendas_ano(empresas_ativas, ano)
    vendas_raw = []
    for nome, items in _ano_data.items():
        for item in items:
            vendas_raw.append({**item, "empresa": nome})

# ── Agrupa por mês ─────────────────────────────────────────────────────────────
df = pd.DataFrame(vendas_raw) if vendas_raw else pd.DataFrame(columns=["dtVenda","valorTotal","empresa"])
if not df.empty:
    df["dtVenda"]    = pd.to_datetime(df["dtVenda"], errors="coerce")
    df["valorTotal"] = pd.to_numeric(df["valorTotal"], errors="coerce")
    df["mes"]        = df["dtVenda"].dt.month

fat_mes = {m: 0.0 for m in range(1, 13)}
if not df.empty:
    for m, v in df.groupby("mes")["valorTotal"].sum().items():
        fat_mes[int(m)] = float(v)

meta_mes   = {m: float(metas_input.get(m, 0)) for m in range(1, 13)}
total_fat  = sum(fat_mes.values())
total_meta = sum(meta_mes.values())
pct_geral  = (total_fat / total_meta * 100) if total_meta else 0

# Mês de corte: só conta até o mês atual se for o ano corrente; se for futuro conta zero
if ano == ano_atual_real:
    mes_corte = date.today().month
elif ano < ano_atual_real:
    mes_corte = 12
else:
    mes_corte = 0  # ano futuro — nenhum mês concluído ainda

fat_acum  = sum(fat_mes[m] for m in range(1, mes_corte + 1))
meta_acum = sum(meta_mes[m] for m in range(1, mes_corte + 1))
pct_acum  = (fat_acum / meta_acum * 100) if meta_acum else 0
melhor_m  = max(fat_mes, key=fat_mes.get)

# ── Header ─────────────────────────────────────────────────────────────────────
empresa_label = empresa_sel if empresa_sel != "Todas" else "Grupo GoGenetic"
st.markdown(f"""
<p class="page-title">📊 Faturamento {ano}</p>
<p class="page-sub">Realizado vs Meta mensal · {empresa_label}</p>
""", unsafe_allow_html=True)

# ── KPIs ───────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
kpi_card(c1, "💰", f"Recebido {ano}",  brl(total_fat), f"meta anual: {brl(total_meta)}")
kpi_card(c2, "🎯", "% Meta Anual",    f"{pct_geral:.1f}%", "",
         value_class="kpi-positive" if pct_geral >= 100 else ("kpi-warn" if pct_geral >= 70 else "kpi-negative"))
kpi_card(c3, "📅", "Acumulado",       brl(fat_acum), f"meta: {brl(meta_acum)}" if mes_corte > 0 else "—")
kpi_card(c4, "📈", "% Meta Acumulada", f"{pct_acum:.1f}%" if mes_corte > 0 else "—",
         MESES_PT.get(mes_corte, ""),
         value_class="kpi-positive" if pct_acum >= 100 else ("kpi-warn" if pct_acum >= 70 else "kpi-negative"))
kpi_card(c5, "🏆", "Melhor Mês",      brl(fat_mes[melhor_m]), MESES_PT[melhor_m] if fat_mes[melhor_m] > 0 else "—")

st.markdown(f"<div class='section-title'>Faturamento vs Meta — {ano}</div>", unsafe_allow_html=True)

# ── Gráfico principal + tabela ─────────────────────────────────────────────────
meses_label = [MESES_PT[m] for m in range(1, 13)]
fat_vals    = [fat_mes[m] for m in range(1, 13)]
meta_vals   = [meta_mes[m] for m in range(1, 13)]

col_chart, col_table = st.columns([3, 1])

with col_chart:
    fig = go.Figure()

    colors_fat = ["#24B78C" if fat_mes[m] > 0 else "rgba(36,183,140,0.18)" for m in range(1, 13)]

    fig.add_trace(go.Bar(
        name="Faturamento",
        x=meses_label, y=fat_vals,
        marker_color=colors_fat,
        text=[f"{v/1e6:.2f} Mi" if v >= 1e6 else (f"{v/1e3:.0f} Mil" if v > 0 else "") for v in fat_vals],
        textposition="outside",
        textfont=dict(size=10, color="#1A0A2E"),
    ))
    fig.add_trace(go.Bar(
        name="Meta",
        x=meses_label, y=meta_vals,
        marker_color="#370950", opacity=0.85,
        text=[f"{v/1e6:.2f} Mi" if v >= 1e6 else (f"{v/1e3:.0f} Mil" if v > 0 else "") for v in meta_vals],
        textposition="outside",
        textfont=dict(size=10, color="#370950"),
    ))
    fig.update_layout(
        barmode="group", bargap=0.15, bargroupgap=0.05,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Sora, sans-serif", color="#1A0A2E", size=11),
        margin=dict(t=20, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="rgba(126,22,184,0.07)", linecolor="rgba(126,22,184,0.15)"),
        yaxis=dict(gridcolor="rgba(126,22,184,0.07)", linecolor="rgba(126,22,184,0.15)", tickformat=",.0f"),
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_table:
    rows = []
    for m in range(1, 13):
        fv = fat_mes[m]; mv = meta_mes[m]
        pct = (fv / mv * 100) if mv else 0
        rows.append({
            "Mês":         MESES_PT[m],
            "Faturamento": brl(fv) if fv else "—",
            "Meta":        brl(mv) if mv else "—",
            "%":           f"{pct:.0f}%" if fv else "—",
        })
    rows.append({
        "Mês": "Total",
        "Faturamento": brl(total_fat),
        "Meta":        brl(total_meta),
        "%":           f"{pct_geral:.0f}%",
    })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=460)

# ── Participação por empresa ───────────────────────────────────────────────────
if len(empresas_ativas) > 1 and not df.empty:
    st.markdown("<div class='section-title'>Participação por Empresa</div>", unsafe_allow_html=True)
    col_pie, col_emp = st.columns([1, 2])
    df_emp = df.groupby("empresa")["valorTotal"].sum().reset_index()
    with col_pie:
        fig_pie = px.pie(df_emp, names="empresa", values="valorTotal",
                         color="empresa", color_discrete_map=CHART_COLORS, hole=0.45)
        fig_pie.update_traces(textinfo="percent+label", textfont_size=11)
        plotly_layout(fig_pie)
        fig_pie.update_layout(showlegend=False, margin=dict(t=10,b=10,l=10,r=10))
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_emp:
        df_es = df_emp.copy().sort_values("valorTotal", ascending=False)
        df_es["Part. %"]     = (df_es["valorTotal"] / df_es["valorTotal"].sum() * 100).round(2).astype(str) + "%"
        df_es["Faturamento"] = df_es["valorTotal"].apply(brl)
        st.dataframe(df_es.rename(columns={"empresa":"Empresa"})[["Empresa","Faturamento","Part. %"]],
                     use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# ── Comparação Histórica ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(f"<div class='section-title'>Comparação Histórica por Mês</div>", unsafe_allow_html=True)

# Anos para comparar: ano principal + até 3 anos anteriores com dados
anos_comp = [a for a in range(ano, ano - 4, -1)]

with st.spinner("Carregando histórico de anos anteriores..."):
    # Carrega todos os anos × empresas em paralelo
    _anos_missing = [a for a in anos_comp if a != ano]
    _hist_jobs = [(load_companies_vendas_ano, empresas_ativas, a) for a in _anos_missing]
    _hist_results = _parallel(_hist_jobs) if _hist_jobs else []
    _hist_by_ano = dict(zip(_anos_missing, _hist_results))

    fat_hist: dict = {}
    for a in anos_comp:
        fat_hist[a] = {m: 0.0 for m in range(1, 13)}
        if a == ano:
            fat_hist[a] = fat_mes.copy()
        else:
            for nome, items in _hist_by_ano[a].items():
                for item in items:
                    try:
                        m = int(pd.to_datetime(item.get("dtVenda","")).month)
                        fat_hist[a][m] += float(item.get("valorTotal") or 0)
                    except Exception:
                        pass

# Remove anos sem nenhum dado
anos_com_dados = [a for a in anos_comp if sum(fat_hist[a].values()) > 0]

if len(anos_com_dados) < 1:
    st.info("Sem dados históricos suficientes para comparação.")
else:
    # Paleta de cores para os anos
    paleta_anos = {
        ano:     "#24B78C",   # verde — ano principal
        ano-1:   "#7E16B8",   # roxo
        ano-2:   "#FF672F",   # laranja
        ano-3:   "#0E62AA",   # azul
    }

    # ── Gráfico de barras agrupadas por mês ────────────────────────────────────
    fig_hist = go.Figure()
    for a in anos_com_dados:
        vals = [fat_hist[a][m] for m in range(1, 13)]
        fig_hist.add_trace(go.Bar(
            name=str(a),
            x=meses_label,
            y=vals,
            marker_color=paleta_anos.get(a, "#999"),
            opacity=1.0 if a == ano else 0.75,
            text=[f"{v/1e6:.2f}Mi" if v >= 1e6 else (f"{v/1e3:.0f}K" if v > 0 else "") for v in vals],
            textposition="outside",
            textfont=dict(size=9),
        ))

    # Linha de meta do ano principal
    if any(meta_mes.values()):
        fig_hist.add_trace(go.Scatter(
            name=f"Meta {ano}",
            x=meses_label,
            y=[meta_mes[m] for m in range(1, 13)],
            mode="lines+markers",
            line=dict(color="#370950", width=2, dash="dash"),
            marker=dict(size=6),
        ))

    fig_hist.update_layout(
        barmode="group", bargap=0.12, bargroupgap=0.04,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Sora, sans-serif", color="#1A0A2E", size=11),
        margin=dict(t=20, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="rgba(126,22,184,0.07)", linecolor="rgba(126,22,184,0.15)"),
        yaxis=dict(gridcolor="rgba(126,22,184,0.07)", linecolor="rgba(126,22,184,0.15)", tickformat=",.0f"),
        height=420,
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # ── Tabela comparativa ─────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>Tabela Comparativa por Mês</div>", unsafe_allow_html=True)

    rows_hist = []
    for m in range(1, 13):
        row = {"Mês": MESES_PT[m]}
        for a in anos_com_dados:
            v = fat_hist[a][m]
            row[str(a)] = brl(v) if v > 0 else "—"
        # Variação % entre ano principal e ano anterior (se existir)
        if len(anos_com_dados) >= 2:
            v_atual   = fat_hist[anos_com_dados[0]][m]
            v_anterior= fat_hist[anos_com_dados[1]][m]
            if v_anterior > 0 and v_atual > 0:
                delta = (v_atual / v_anterior - 1) * 100
                sinal = "▲" if delta >= 0 else "▼"
                row[f"Var. {anos_com_dados[0]}x{anos_com_dados[1]}"] = f"{sinal} {abs(delta):.1f}%"
            else:
                row[f"Var. {anos_com_dados[0]}x{anos_com_dados[1]}"] = "—"
        rows_hist.append(row)

    # Linha de totais
    row_tot = {"Mês": "Total"}
    for a in anos_com_dados:
        row_tot[str(a)] = brl(sum(fat_hist[a].values()))
    if len(anos_com_dados) >= 2:
        t0 = sum(fat_hist[anos_com_dados[0]].values())
        t1 = sum(fat_hist[anos_com_dados[1]].values())
        if t1 > 0 and t0 > 0:
            delta_t = (t0 / t1 - 1) * 100
            sinal = "▲" if delta_t >= 0 else "▼"
            row_tot[f"Var. {anos_com_dados[0]}x{anos_com_dados[1]}"] = f"{sinal} {abs(delta_t):.1f}%"
        else:
            row_tot[f"Var. {anos_com_dados[0]}x{anos_com_dados[1]}"] = "—"
    rows_hist.append(row_tot)

    st.dataframe(pd.DataFrame(rows_hist), use_container_width=True, hide_index=True)

    # ── Linha de evolução anual (totais por ano) ───────────────────────────────
    if len(anos_com_dados) >= 2:
        st.markdown("<div class='section-title'>Evolução Anual — Total por Ano</div>", unsafe_allow_html=True)
        df_anual = pd.DataFrame([
            {"Ano": str(a), "Total": sum(fat_hist[a].values())}
            for a in sorted(anos_com_dados)
        ])
        fig_anual = px.bar(
            df_anual, x="Ano", y="Total",
            color="Ano",
            color_discrete_map={str(a): paleta_anos.get(a, "#999") for a in anos_com_dados},
            text=df_anual["Total"].apply(brl),
            labels={"Ano": "", "Total": "R$"},
        )
        fig_anual.update_traces(textposition="outside", textfont_size=12)
        fig_anual.update_layout(showlegend=False, coloraxis_showscale=False)
        plotly_layout(fig_anual)
        fig_anual.update_layout(height=320)
        st.plotly_chart(fig_anual, use_container_width=True)
