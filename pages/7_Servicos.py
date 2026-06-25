"""Página 7 — Serviços em Execução (GoGenetic Pesquisa)."""
import io
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from utils import (GLOBAL_CSS, BRAND, brl, soma, kpi_card, plotly_layout,
                   sidebar_header, get_clients, tabela_marcavel)

st.set_page_config(page_title="Serviços | GoGenetic", page_icon="🔬", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Cores por situacaoOS ───────────────────────────────────────────────────────
COR_STATUS = {
    "Em execução":        "#7E16B8",
    "Aprovado":           "#10B981",
    "Faturar":            "#3B82F6",
    "Invoice":            "#F97316",
    "Em espera":          "#F59E0B",
    "Cotação":            "#8B6BAE",
    "Proposta":           "#A899C4",
    "Consumo de crédito": "#EF4444",
    "NF Emitida":         "#6B7280",
}

STATUS_ATIVOS = ["Em execução", "Aprovado", "Faturar", "Invoice", "Em espera", "Consumo de crédito"]
STATUS_TODOS  = list(COR_STATUS.keys())

# ── Sidebar ────────────────────────────────────────────────────────────────────
sidebar_header()

with st.sidebar:
    st.markdown("**🏢 Empresa**")
    st.markdown(
        "<div style='background:#2A1D4A;border-radius:10px;padding:8px 12px;"
        "color:#D4C8EE;font-size:.85rem;margin-bottom:12px'>"
        "🧬 GoGenetic Pesquisa</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("**📅 Período**")

    PERIODOS = {
        "Últimos 30 dias":  (date.today() - timedelta(days=30),  date.today()),
        "Últimos 60 dias":  (date.today() - timedelta(days=60),  date.today()),
        "Últimos 90 dias":  (date.today() - timedelta(days=90),  date.today()),
        "Últimos 6 meses":  (date.today() - timedelta(days=180), date.today()),
        "Este ano":         (date(date.today().year, 1, 1),       date.today()),
        "Desde Jan/2025":   (date(2025, 1, 1),                    date.today()),
        "Desde Jan/2024":   (date(2024, 1, 1),                    date.today()),
        "Personalizado":    None,
    }
    periodo_sel = st.selectbox("Intervalo", list(PERIODOS.keys()), index=5)  # default: Desde Jan/2025

    if periodo_sel == "Personalizado":
        c1, c2 = st.columns(2)
        dt_ini = c1.date_input("De",  date.today() - timedelta(days=90))
        dt_fim = c2.date_input("Até", date.today())
    else:
        dt_ini, dt_fim = PERIODOS[periodo_sel]

    st.markdown("---")
    status_sel = st.multiselect(
        "🔍 Situação OS",
        STATUS_TODOS,
        default=STATUS_ATIVOS,
    )

    st.markdown("---")
    busca = st.text_input("🔎 Buscar cliente / vendedor", placeholder="Digite para filtrar...")

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        load_servicos.clear()
        st.rerun()
    st.caption("⏱ Cache: 5 min")


# ── Carrega dados ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_servicos(dt_ini_str: str, dt_fim_str: str) -> list:
    try:
        client = get_clients()["GoGenetic Pesquisa"]
        return client.get_servicos(dt_ini_str, dt_fim_str)
    except Exception as exc:
        st.error(f"Erro ao carregar serviços: {exc}")
        return []


with st.spinner("Carregando serviços..."):
    dt_ini_str = dt_ini.strftime("%Y-%m-%d")
    dt_fim_str = dt_fim.strftime("%Y-%m-%d")
    todos = load_servicos(dt_ini_str, dt_fim_str)

# ── Aplica filtros ─────────────────────────────────────────────────────────────
def _sit(s): return (s.get("situacaoOS") or "").strip()

filtrados = todos
if status_sel:
    filtrados = [s for s in filtrados if _sit(s) in status_sel]
if busca:
    b = busca.lower()
    filtrados = [s for s in filtrados
                 if b in (s.get("nomeContato") or "").lower()
                 or b in (s.get("nomeVendedor") or "").lower()]

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<p class="page-title">🔬 Serviços em Execução</p>
<p class="page-sub">GoGenetic Pesquisa · {dt_ini.strftime('%d/%m/%Y')} → {dt_fim.strftime('%d/%m/%Y')}</p>
""", unsafe_allow_html=True)

# ── KPIs ───────────────────────────────────────────────────────────────────────
em_exec   = [s for s in todos if _sit(s) == "Em execução"]
aprovados = [s for s in todos if _sit(s) == "Aprovado"]
a_faturar = [s for s in todos if _sit(s) == "Faturar"]
invoice   = [s for s in todos if _sit(s) == "Invoice"]
em_espera = [s for s in todos if _sit(s) == "Em espera"]

c1, c2, c3, c4, c5 = st.columns(5)
kpi_card(c1, "⚡", "Em Execução", brl(soma(em_exec,   "valorTotal")), f"{len(em_exec)} serviços",   border="#7E16B8")
kpi_card(c2, "✅", "Aprovados",   brl(soma(aprovados, "valorTotal")), f"{len(aprovados)} serviços", border="#10B981")
kpi_card(c3, "💰", "A Faturar",   brl(soma(a_faturar, "valorTotal")), f"{len(a_faturar)} serviços", border="#3B82F6")
kpi_card(c4, "🧾", "Invoice",     brl(soma(invoice,   "valorTotal")), f"{len(invoice)} serviços",   border="#F97316")
kpi_card(c5, "⏳", "Em Espera",   brl(soma(em_espera, "valorTotal")), f"{len(em_espera)} serviços", border="#F59E0B")

# ── Gráficos ───────────────────────────────────────────────────────────────────
if filtrados:
    df = pd.DataFrame(filtrados)
    df["valorTotal"]   = pd.to_numeric(df["valorTotal"], errors="coerce").fillna(0)
    df["dtVenda"]      = pd.to_datetime(df["dtVenda"], errors="coerce")
    df["situacaoOS"]   = df["situacaoOS"].fillna("").str.strip().replace("", "—").astype(str)
    df["nomeContato"]  = df["nomeContato"].fillna("—").astype(str)
    df["nomeVendedor"] = df.get("nomeVendedor", pd.Series(dtype=str)).fillna("—").astype(str)
    if "nomeVendedor" not in df.columns:
        df["nomeVendedor"] = "—"

    # Separa ativos x em espera para os gráficos
    STATUS_ESPERA    = ["Em espera"]
    STATUS_CONCLUIDO = ["NF Emitida", "Cotação", "Proposta"]
    df_ativos = df[~df["situacaoOS"].isin(STATUS_ESPERA + STATUS_CONCLUIDO)]

    col_graf1, col_graf2 = st.columns([1, 1])

    with col_graf1:
        st.markdown("<div class='section-title'>Por Situação OS (ativos)</div>", unsafe_allow_html=True)
        df_sit = df_ativos.groupby("situacaoOS").agg(
            Valor=("valorTotal", "sum"),
            Qtd=("valorTotal", "count"),
        ).reset_index().sort_values("Valor", ascending=False)
        if not df_sit.empty:
            fig = px.bar(
                df_sit, x="situacaoOS", y="Valor",
                color="situacaoOS",
                color_discrete_map=COR_STATUS,
                labels={"situacaoOS": "", "Valor": "R$"},
                text=df_sit["Qtd"].apply(lambda x: f"{x} serv."),
            )
            fig.update_traces(textposition="outside")
            plotly_layout(fig)
            st.plotly_chart(fig, use_container_width=True)

    with col_graf2:
        st.markdown("<div class='section-title'>Top 10 Clientes — ativos (valor)</div>", unsafe_allow_html=True)
        df_cli = df_ativos.groupby("nomeContato")["valorTotal"].sum().reset_index()
        df_cli = df_cli.sort_values("valorTotal", ascending=False).head(10)
        df_cli["nomeContato"] = df_cli["nomeContato"].str.title().str[:35].fillna("—")
        if not df_cli.empty:
            fig2 = px.bar(
                df_cli, x="valorTotal", y="nomeContato",
                orientation="h",
                color_discrete_sequence=["#7E16B8"],
                labels={"valorTotal": "R$", "nomeContato": ""},
            )
            fig2.update_layout(yaxis=dict(autorange="reversed"))
            plotly_layout(fig2)
            st.plotly_chart(fig2, use_container_width=True)

    # ── Gráfico por vendedor (apenas ativos) ─────────────────────────────────
    st.markdown("<div class='section-title'>Por Vendedor — ativos</div>", unsafe_allow_html=True)
    df_vend = df_ativos.groupby(["nomeVendedor", "situacaoOS"]).agg(
        Valor=("valorTotal", "sum"),
    ).reset_index()
    if not df_vend.empty:
        fig3 = px.bar(
            df_vend, x="nomeVendedor", y="Valor",
            color="situacaoOS",
            color_discrete_map=COR_STATUS,
            barmode="stack",
            labels={"nomeVendedor": "", "Valor": "R$", "situacaoOS": "Situação"},
        )
        plotly_layout(fig3)
        st.plotly_chart(fig3, use_container_width=True)


# ── Tabela em abas ─────────────────────────────────────────────────────────────
if not filtrados:
    st.info("Nenhum serviço encontrado para os filtros selecionados.")
else:
    df_show = pd.DataFrame(filtrados)
    df_show["valorTotal"] = pd.to_numeric(df_show["valorTotal"], errors="coerce").fillna(0)
    df_show["dtVenda"]    = pd.to_datetime(df_show["dtVenda"], errors="coerce").dt.strftime("%d/%m/%Y")
    df_show["situacaoOS"] = df_show["situacaoOS"].fillna("").str.strip().replace("", "—")
    df_show["nomeContato"]  = df_show["nomeContato"].fillna("—")
    df_show["nomeVendedor"] = df_show.get("nomeVendedor", pd.Series(dtype=str)).fillna("—")

    cols_map = {
        "codigo":            "Cód.",
        "dtVenda":           "Data",
        "Dias em execução":  "Dias",
        "nomeContato":       "Cliente",
        "nomeVendedor":      "Vendedor",
        "situacaoOS":        "Situação OS",
        "valorTotal":        "Valor",
    }

    # ── Prepara base com coluna de dias e sort ────────────────────────────────
    df_base = pd.DataFrame(filtrados)
    df_base["valorTotal"]   = pd.to_numeric(df_base["valorTotal"], errors="coerce").fillna(0)
    df_base["dtVenda_sort"] = pd.to_datetime(df_base["dtVenda"], errors="coerce")
    df_base["situacaoOS"]   = df_base["situacaoOS"].fillna("").str.strip().replace("", "—")
    df_base["nomeContato"]  = df_base["nomeContato"].fillna("—")
    df_base["nomeVendedor"] = df_base.get("nomeVendedor", pd.Series(dtype=str)).fillna("—")
    df_base["Dias em execução"] = (
        pd.Timestamp.today().normalize() - df_base["dtVenda_sort"]
    ).dt.days.fillna(0).astype(int)
    df_base["dtVenda"] = df_base["dtVenda_sort"].dt.strftime("%d/%m/%Y")

    # Data de entrega
    df_base["Entrega"] = pd.to_datetime(
        df_base.get("dtEntrega", pd.Series(dtype=str)), errors="coerce"
    ).dt.strftime("%d/%m/%Y").fillna("—")

    # Código S das palavras-chave (ex: S6944)
    def _cod_s(tags):
        try:
            if not tags:
                return "—"
            items = tags if isinstance(tags, list) else str(tags).split(",")
            for t in items:
                if isinstance(t, dict):
                    nome = str(t.get("nome") or t.get("tag") or "").strip()
                else:
                    nome = str(t).strip()
                if len(nome) > 1 and nome[0].upper() == "S" and nome[1:].isdigit():
                    return nome.upper()
        except Exception:
            pass
        return "—"

    if "tags" in df_base.columns:
        df_base["Cód. S"] = df_base["tags"].apply(_cod_s)
    else:
        df_base["Cód. S"] = "—"

    def _filtro(status, asc=False):
        df_f = df_base[df_base["situacaoOS"].isin(status) if isinstance(status, list)
                       else df_base["situacaoOS"] == status]
        return df_f.sort_values("dtVenda_sort", ascending=asc)

    df_exec      = _filtro("Em execução",              asc=True)
    df_aprov     = _filtro("Aprovado",                 asc=False)
    df_faturar   = _filtro("Faturar",                  asc=False)
    df_invoice   = _filtro("Invoice",                  asc=False)
    df_credito   = _filtro("Consumo de crédito",       asc=False)
    df_espera    = _filtro("Em espera",                asc=False)
    df_concluido = _filtro(["NF Emitida", "Cotação", "Proposta"], asc=False)

    tab_exec, tab_aprov, tab_fat, tab_inv, tab_cred, tab_esp, tab_conc = st.tabs([
        f"⚡ Em Execução ({len(df_exec)})",
        f"✅ Aprovados ({len(df_aprov)})",
        f"💰 A Faturar ({len(df_faturar)})",
        f"🧾 Invoice ({len(df_invoice)})",
        f"🎯 Consumo Crédito ({len(df_credito)})",
        f"⏳ Em Espera ({len(df_espera)})",
        f"📁 Concluídos / Outros ({len(df_concluido)})",
    ])

    def tabela_servico(df_t: pd.DataFrame, key_suffix: str):
        if df_t.empty:
            st.info("Nenhum registro nesta categoria.")
            return
        existing = [c for c in cols_map if c in df_t.columns]
        df_render = df_t[existing].rename(columns=cols_map).copy()
        df_render["Valor"] = df_render["Valor"].apply(brl)

        sel_rows, _ = tabela_marcavel(
            df_render,
            key=key_suffix,
            column_config={
                "Dias":        st.column_config.NumberColumn("Dias", help="Dias desde a abertura do serviço", width="small"),
                "Situação OS": st.column_config.TextColumn("Situação OS", width="medium"),
                "Cliente":     st.column_config.TextColumn("Cliente",     width="large"),
                "Valor":       st.column_config.TextColumn("Valor",       width="small"),
            },
        )

        col_info, col_soma, col_export = st.columns([2, 2, 1])
        df_num_t = df_t.copy()

        with col_info:
            if sel_rows:
                st.caption(f"✅ {len(sel_rows)} selecionado(s) de {len(df_t)}")
            else:
                st.caption(f"Total: {len(df_t)} serviços · clique para selecionar")

        with col_soma:
            val = df_num_t.iloc[sel_rows]["valorTotal"].sum() if sel_rows else df_num_t["valorTotal"].sum()
            label = "Soma selecionados" if sel_rows else "Total filtrado"
            borda = "#7E16B8" if sel_rows else "rgba(126,22,184,0.2)"
            st.markdown(
                f"<div style='background:#F5F0FA;border:1px solid {borda};border-radius:8px;"
                f"padding:8px 16px;text-align:right'>"
                f"<span style='font-size:.72rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{label}</span><br>"
                f"<span style='font-size:1.3rem;font-weight:700;color:#1A1033'>{brl(val)}</span>"
                f"</div>", unsafe_allow_html=True,
            )

        with col_export:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                (df_render.iloc[sel_rows] if sel_rows else df_render).to_excel(
                    writer, index=False, sheet_name="Serviços")
            st.download_button(
                label="📥 Excel" + (f" ({len(sel_rows)} sel.)" if sel_rows else ""),
                data=buf.getvalue(),
                file_name=f"servicos_{key_suffix}_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"dl_{key_suffix}",
            )

    with tab_exec:
        cols_exec = {
            "codigo":            "Cód.",
            "dtVenda":           "Data",
            "Dias em execução":  "Dias",
            "Entrega":           "Entrega",
            "Cód. S":            "Cód. S",
            "nomeContato":       "Cliente",
            "nomeVendedor":      "Vendedor",
            "situacaoOS":        "Situação OS",
            "valorTotal":        "Valor",
        }
        if not df_exec.empty:
            existing = [c for c in cols_exec if c in df_exec.columns]
            df_render_exec = df_exec[existing].rename(columns=cols_exec).copy()
            df_render_exec["Valor"] = df_render_exec["Valor"].apply(brl)
            sel_rows, _ = tabela_marcavel(
                df_render_exec,
                key="execucao",
                column_config={
                    "Dias":        st.column_config.NumberColumn("Dias", width="small"),
                    "Entrega":     st.column_config.TextColumn("Entrega", width="small"),
                    "Cód. S":      st.column_config.TextColumn("Cód. S", width="small"),
                    "Situação OS": st.column_config.TextColumn("Situação OS", width="medium"),
                    "Cliente":     st.column_config.TextColumn("Cliente", width="large"),
                    "Valor":       st.column_config.TextColumn("Valor", width="small"),
                },
            )
            col_info, col_soma, col_export = st.columns([2, 2, 1])
            with col_info:
                if sel_rows:
                    st.caption(f"✅ {len(sel_rows)} selecionado(s) de {len(df_exec)}")
                else:
                    st.caption(f"Total: {len(df_exec)} serviços · clique para selecionar")
            with col_soma:
                val = df_exec.iloc[sel_rows]["valorTotal"].sum() if sel_rows else df_exec["valorTotal"].sum()
                label = "Soma selecionados" if sel_rows else "Total filtrado"
                borda = "#7E16B8" if sel_rows else "rgba(126,22,184,0.2)"
                st.markdown(
                    f"<div style='background:#F5F0FA;border:1px solid {borda};border-radius:8px;"
                    f"padding:8px 16px;text-align:right'>"
                    f"<span style='font-size:.72rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{label}</span><br>"
                    f"<span style='font-size:1.3rem;font-weight:700;color:#1A1033'>{brl(val)}</span>"
                    f"</div>", unsafe_allow_html=True,
                )
            with col_export:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    (df_render_exec.iloc[sel_rows] if sel_rows else df_render_exec).to_excel(
                        writer, index=False, sheet_name="Serviços")
                st.download_button(
                    label="📥 Excel" + (f" ({len(sel_rows)} sel.)" if sel_rows else ""),
                    data=buf.getvalue(),
                    file_name=f"servicos_execucao_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_execucao",
                )
        else:
            st.info("Nenhum registro nesta categoria.")

    with tab_aprov:
        tabela_servico(df_aprov, "aprovados")

    with tab_fat:
        tabela_servico(df_faturar, "faturar")

    with tab_inv:
        tabela_servico(df_invoice, "invoice")

    with tab_cred:
        tabela_servico(df_credito, "credito")

    with tab_esp:
        tabela_servico(df_espera, "espera")

    with tab_conc:
        cols_conc = {
            "codigo":            "Cód.",
            "dtVenda":           "Data",
            "Dias em execução":  "Dias",
            "Cód. S":            "Cód. S",
            "nomeContato":       "Cliente",
            "nomeVendedor":      "Vendedor",
            "situacaoOS":        "Situação OS",
            "valorTotal":        "Valor",
        }
        if not df_concluido.empty:
            existing = [c for c in cols_conc if c in df_concluido.columns]
            df_render_conc = df_concluido[existing].rename(columns=cols_conc).copy()
            df_render_conc["Valor"] = df_render_conc["Valor"].apply(brl)
            sel_rows, _ = tabela_marcavel(
                df_render_conc,
                key="concluidos",
                column_config={
                    "Dias":        st.column_config.NumberColumn("Dias", width="small"),
                    "Cód. S":      st.column_config.TextColumn("Cód. S", width="small"),
                    "Situação OS": st.column_config.TextColumn("Situação OS", width="medium"),
                    "Cliente":     st.column_config.TextColumn("Cliente", width="large"),
                    "Valor":       st.column_config.TextColumn("Valor", width="small"),
                },
            )
            col_info, col_soma, col_export = st.columns([2, 2, 1])
            with col_info:
                if sel_rows:
                    st.caption(f"✅ {len(sel_rows)} selecionado(s) de {len(df_concluido)}")
                else:
                    st.caption(f"Total: {len(df_concluido)} serviços · clique para selecionar")
            with col_soma:
                val = df_concluido.iloc[sel_rows]["valorTotal"].sum() if sel_rows else df_concluido["valorTotal"].sum()
                label = "Soma selecionados" if sel_rows else "Total filtrado"
                borda = "#7E16B8" if sel_rows else "rgba(126,22,184,0.2)"
                st.markdown(
                    f"<div style='background:#F5F0FA;border:1px solid {borda};border-radius:8px;"
                    f"padding:8px 16px;text-align:right'>"
                    f"<span style='font-size:.72rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{label}</span><br>"
                    f"<span style='font-size:1.3rem;font-weight:700;color:#1A1033'>{brl(val)}</span>"
                    f"</div>", unsafe_allow_html=True,
                )
            with col_export:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    (df_render_conc.iloc[sel_rows] if sel_rows else df_render_conc).to_excel(
                        writer, index=False, sheet_name="Serviços")
                st.download_button(
                    label="📥 Excel" + (f" ({len(sel_rows)} sel.)" if sel_rows else ""),
                    data=buf.getvalue(),
                    file_name=f"servicos_concluidos_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_concluidos",
                )
        else:
            st.info("Nenhum registro nesta categoria.")
