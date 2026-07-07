"""Página 10 — GoGenetic You: Bling, Guru e Asaas num só lugar."""
import io
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from utils import (GLOBAL_CSS, BRAND, brl, kpi_card, plotly_layout,
                    sidebar_header, tabela_marcavel, get_bling_client, load_bling_data)
import bling_auth

st.set_page_config(page_title="GoGenetic You | GoGenetic", page_icon="🧬", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()

BRANDY = BRAND["GoGenetic You"]


def _secret(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        try:
            val = st.secrets.get(key, "")
        except Exception:
            pass
    return val


with st.sidebar:
    st.markdown("---")
    st.markdown("**📅 Período**")
    PERIODOS = {
        "Últimos 30 dias": (date.today() - timedelta(days=30), date.today()),
        "Últimos 60 dias": (date.today() - timedelta(days=60), date.today()),
        "Últimos 90 dias": (date.today() - timedelta(days=90), date.today()),
        "Este ano":        (date(date.today().year, 1, 1), date.today()),
        "Personalizado":   None,
    }
    periodo_sel = st.selectbox("Intervalo", list(PERIODOS.keys()), index=1)
    if periodo_sel == "Personalizado":
        c1, c2 = st.columns(2)
        dt_ini = c1.date_input("De", date.today() - timedelta(days=60))
        dt_fim = c2.date_input("Até", date.today())
    else:
        dt_ini, dt_fim = PERIODOS[periodo_sel]

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

dt_ini_s, dt_fim_s = dt_ini.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")

st.markdown(f"""
<p class="page-title">🧬 GoGenetic You</p>
<p class="page-sub">Bling · Guru · Asaas · {dt_ini.strftime('%d/%m/%Y')} → {dt_fim.strftime('%d/%m/%Y')}</p>
""", unsafe_allow_html=True)

tab_bling, tab_guru, tab_asaas = st.tabs(["🔗 Bling", "🛒 Guru", "💳 Asaas"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA BLING
# ══════════════════════════════════════════════════════════════════════════════
with tab_bling:
    erro = bling_auth.connection_error()
    if erro:
        st.warning("⚠️ Bling não conectado.")
        st.caption(f"Motivo: {erro}")
        st.link_button("🔗 Conectar ao Bling", bling_auth.get_auth_url())
    else:
        with st.spinner("Carregando dados do Bling..."):
            dados = load_bling_data(dt_ini_s, dt_fim_s)
        vendas, fat, rec, pag = dados["vendas"], dados["faturamento"], dados["contas_receber"], dados["contas_pagar"]

        total_v = sum(float(v.get("valorTotal") or 0) for v in vendas)
        total_f = sum(float(v.get("valor") or 0) for v in fat)
        total_r = sum(float(v.get("valor") or 0) for v in rec)
        total_p = sum(float(v.get("valor") or 0) for v in pag)

        c1, c2, c3, c4 = st.columns(4)
        kpi_card(c1, "🛒", "Vendas",    brl(total_v), f"{len(vendas)} pedidos", border=f"{BRANDY['primary']}40")
        kpi_card(c2, "💰", "Recebido",  brl(total_f), f"{len(fat)} lançtos",   border=f"{BRANDY['primary']}40")
        kpi_card(c3, "📥", "A Receber", brl(total_r), f"{len(rec)} títulos",   border=f"{BRANDY['primary']}40")
        kpi_card(c4, "📤", "A Pagar",   brl(total_p), f"{len(pag)} títulos",   border=f"{BRANDY['primary']}40")

        st.markdown("<br>", unsafe_allow_html=True)
        if vendas:
            df_v = pd.DataFrame(vendas)
            df_v["valorTotal"] = pd.to_numeric(df_v["valorTotal"], errors="coerce").fillna(0)
            df_show = df_v[["dtVenda", "nomeContato", "nomeVendedor", "valorTotal"]].copy()
            df_show["valorTotal"] = df_show["valorTotal"].apply(brl)
            df_show.columns = ["Data", "Cliente", "Vendedor", "Valor"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma venda no período.")

# ══════════════════════════════════════════════════════════════════════════════
# ABA GURU
# ══════════════════════════════════════════════════════════════════════════════
COR_STATUS_GURU = {
    "approved": "#10B981", "canceled": "#EF4444", "expired": "#F59E0B",
    "pending": "#8B6BAE", "refunded": "#6B7280", "chargeback": "#EF4444",
}


@st.cache_data(ttl=600, show_spinner=False)
def _load_guru(dt_ini_s: str, dt_fim_s: str) -> list:
    from guru_api import GuruClient
    token = _secret("GURU_API_TOKEN")
    if not token:
        return []
    client = GuruClient(token)
    txs = client.get_transacoes(dt_ini_s, dt_fim_s)
    return [GuruClient.normaliza_transacao(t) for t in txs]


@st.cache_data(ttl=600, show_spinner=False)
def _load_asaas_recente() -> list:
    """Pagamentos do Asaas dos últimos 45 dias + próximos 30 — janela usada só
    pra cruzar com pedidos novos do Guru, independente do período escolhido
    na sidebar."""
    from asaas_api import AsaasClient
    key = _secret("ASAAS_API_KEY")
    if not key:
        return []
    client = AsaasClient(key)
    cust_map = client.get_customers_map()
    dt_ini = (date.today() - timedelta(days=45)).strftime("%Y-%m-%d")
    dt_fim = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    raw = client.get_recebidos((date.today() - timedelta(days=45)).strftime("%Y-%m-%d"),
                                date.today().strftime("%Y-%m-%d"))
    raw += client.get_contas_receber(dt_ini, dt_fim)
    return [AsaasClient.normaliza_pagamento(p, cust_map) for p in raw]


def _normaliza_nome(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().strip()


def _status_pagamento_asaas(nome: str, valor: float, pagamentos: list) -> str:
    """Procura um pagamento no Asaas do mesmo cliente com valor parecido
    (tolerância de 5%, mínimo R$1 — Guru e Asaas podem divergir por taxas)."""
    nome_n = _normaliza_nome(nome)
    if not nome_n:
        return "nao_encontrado"
    tolerancia = max(1.0, valor * 0.05)
    candidatos = [p for p in pagamentos if _normaliza_nome(p["nomeContato"]) == nome_n
                  and abs(p["valor"] - valor) <= tolerancia]
    if not candidatos:
        return "nao_encontrado"
    if any(p["situacao"] in ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH") for p in candidatos):
        return "pago"
    return "pendente"


BADGE_ASAAS = {
    "pago":          "✅ Pago no Asaas",
    "pendente":      "⏳ Aguardando pagamento no Asaas",
    "nao_encontrado":"❓ Pagamento não encontrado no Asaas ainda",
}


with tab_guru:
    if not _secret("GURU_API_TOKEN"):
        st.warning("⚠️ Token do Guru não configurado (GURU_API_TOKEN).")
    else:
        with st.spinner("Carregando dados do Guru..."):
            txs = _load_guru(dt_ini_s, dt_fim_s)

        import db_guru_seen
        seen_ids = db_guru_seen.get_seen_ids()
        novos = [t for t in txs if str(t["codigo"]) not in seen_ids]
        if novos:
            pagamentos_asaas = _load_asaas_recente()
            cor = BRANDY["primary"]
            st.markdown(
                f'<div style="background:{cor}15;border:2px solid {cor};'
                f'border-radius:12px;padding:16px 20px;margin-bottom:20px">',
                unsafe_allow_html=True,
            )
            st.markdown(f"#### 🆕 {len(novos)} pedido(s) novo(s) desde a última vez")
            for t in sorted(novos, key=lambda x: x["dtVenda"], reverse=True):
                status = _status_pagamento_asaas(t["nomeContato"], float(t["valorTotal"] or 0), pagamentos_asaas)
                st.markdown(
                    f"**{t['nomeContato']}** · {t['produto']} · {brl(t['valorTotal'])} · "
                    f"{t['dtVenda']} · {BADGE_ASAAS[status]}"
                )
            st.markdown("</div>", unsafe_allow_html=True)
            db_guru_seen.mark_seen([t["codigo"] for t in novos])

        if not txs:
            st.info("Nenhuma transação no período.")
        else:
            df = pd.DataFrame(txs)
            df["valorTotal"] = pd.to_numeric(df["valorTotal"], errors="coerce").fillna(0)

            aprovadas = df[df["status"] == "approved"]
            canceladas = df[df["status"].isin(["canceled", "refunded", "chargeback"])]
            taxa_aprov = (len(aprovadas) / len(df) * 100) if len(df) else 0

            c1, c2, c3, c4 = st.columns(4)
            kpi_card(c1, "✅", "Vendas Aprovadas", brl(aprovadas["valorTotal"].sum()),
                      f"{len(aprovadas)} vendas", border=f"{BRANDY['primary']}40")
            kpi_card(c2, "🎯", "Ticket Médio", brl(aprovadas["valorTotal"].mean() if len(aprovadas) else 0),
                      "", border=f"{BRANDY['primary']}40")
            kpi_card(c3, "📊", "Taxa de Aprovação", f"{taxa_aprov:.1f}%",
                      f"{len(df)} transações totais", border=f"{BRANDY['primary']}40")
            kpi_card(c4, "❌", "Canceladas/Reembolsadas", brl(canceladas["valorTotal"].sum()),
                      f"{len(canceladas)} transações", border="#EF444440")

            st.markdown("<br>", unsafe_allow_html=True)
            g1, g2 = st.columns(2)
            with g1:
                st.markdown("**Por status**")
                df_st = df.groupby("status")["valorTotal"].sum().reset_index()
                fig = px.pie(df_st, names="status", values="valorTotal",
                             color="status", color_discrete_map=COR_STATUS_GURU, hole=0.4)
                plotly_layout(fig)
                st.plotly_chart(fig, use_container_width=True)
            with g2:
                st.markdown("**Top produtos (aprovadas)**")
                if not aprovadas.empty:
                    df_p = aprovadas.groupby("produto")["valorTotal"].sum().reset_index()
                    df_p = df_p.sort_values("valorTotal", ascending=False).head(10)
                    fig2 = px.bar(df_p, x="valorTotal", y="produto", orientation="h",
                                  color_discrete_sequence=[BRANDY["primary"]],
                                  labels={"valorTotal": "R$", "produto": ""})
                    fig2.update_layout(yaxis=dict(autorange="reversed"))
                    plotly_layout(fig2)
                    st.plotly_chart(fig2, use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)
            status_sel = st.multiselect("Status", sorted(df["status"].unique()),
                                          default=list(df["status"].unique()), key="guru_status")
            df_tab = df[df["status"].isin(status_sel)] if status_sel else df
            df_tab_show = df_tab[["dtVenda", "produto", "nomeContato", "valorTotal", "status", "metodo"]].copy()
            df_tab_show["valorTotal"] = df_tab_show["valorTotal"].apply(brl)
            df_tab_show.columns = ["Data", "Produto", "Cliente", "Valor", "Status", "Método"]
            df_tab_show = df_tab_show.sort_values("Data", ascending=False)
            st.dataframe(df_tab_show, use_container_width=True, hide_index=True)

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df_tab_show.to_excel(writer, index=False, sheet_name="Guru")
            st.download_button("📥 Exportar Excel", data=buf.getvalue(),
                                file_name=f"guru_{date.today().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="dl_guru")

# ══════════════════════════════════════════════════════════════════════════════
# ABA ASAAS
# ══════════════════════════════════════════════════════════════════════════════
COR_STATUS_ASAAS = {
    "RECEIVED": "#10B981", "CONFIRMED": "#10B981", "RECEIVED_IN_CASH": "#10B981",
    "PENDING": "#F59E0B", "OVERDUE": "#EF4444", "REFUNDED": "#6B7280",
}


@st.cache_data(ttl=600, show_spinner=False)
def _load_asaas(dt_ini_s: str, dt_fim_s: str):
    from asaas_api import AsaasClient
    key = _secret("ASAAS_API_KEY")
    if not key:
        return [], [], [], {}
    client = AsaasClient(key)
    cust_map = client.get_customers_map()
    receber = client.get_contas_receber(dt_ini_s, dt_fim_s)
    recebidos = client.get_recebidos(dt_ini_s, dt_fim_s)
    vencidas = client.get_vencidas()
    return receber, recebidos, vencidas, cust_map


with tab_asaas:
    if not _secret("ASAAS_API_KEY"):
        st.warning("⚠️ Chave do Asaas não configurada (ASAAS_API_KEY).")
    else:
        from asaas_api import AsaasClient

        with st.spinner("Carregando dados do Asaas..."):
            receber_raw, recebidos_raw, vencidas_raw, cust_map = _load_asaas(dt_ini_s, dt_fim_s)

        receber   = [AsaasClient.normaliza_pagamento(p, cust_map) for p in receber_raw]
        recebidos = [AsaasClient.normaliza_pagamento(p, cust_map) for p in recebidos_raw]
        vencidas  = [AsaasClient.normaliza_pagamento(p, cust_map) for p in vencidas_raw]

        total_receber   = sum(r["valor"] for r in receber)
        total_recebido  = sum(r["valor"] for r in recebidos)
        total_vencidas  = sum(r["valor"] for r in vencidas)

        c1, c2, c3 = st.columns(3)
        kpi_card(c1, "💰", "Recebido no Período", brl(total_recebido),
                  f"{len(recebidos)} cobranças", border=f"{BRANDY['primary']}40")
        kpi_card(c2, "📥", "A Receber (vencimento no período)", brl(total_receber),
                  f"{len(receber)} cobranças", border=f"{BRANDY['primary']}40")
        kpi_card(c3, "🚨", "Vencidas", brl(total_vencidas),
                  f"{len(vencidas)} cobranças", border="#EF444440" if vencidas else "#EAE6F4")

        st.markdown("<br>", unsafe_allow_html=True)

        if recebidos:
            st.markdown("**Fluxo de caixa — recebido por dia**")
            df_rec = pd.DataFrame(recebidos)
            df_rec["dtPgto"] = pd.to_datetime(df_rec["dtPgto"], errors="coerce")
            df_dia = df_rec.groupby(df_rec["dtPgto"].dt.date)["valor"].sum().reset_index()
            df_dia.columns = ["Data", "Valor"]
            fig = px.bar(df_dia, x="Data", y="Valor", color_discrete_sequence=[BRANDY["primary"]])
            plotly_layout(fig)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Contas a receber**")
        if not receber:
            st.info("Nenhuma cobrança com vencimento no período.")
        else:
            df_show = pd.DataFrame(receber)[["dtVenc", "nomeContato", "descricao", "valor", "situacao", "metodo"]].copy()
            df_show["valor"] = df_show["valor"].apply(brl)
            df_show.columns = ["Vencimento", "Cliente", "Descrição", "Valor", "Situação", "Método"]
            df_show = df_show.sort_values("Vencimento")
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df_show.to_excel(writer, index=False, sheet_name="Asaas")
            st.download_button("📥 Exportar Excel", data=buf.getvalue(),
                                file_name=f"asaas_{date.today().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="dl_asaas")

        if vencidas:
            st.markdown("**🚨 Cobranças vencidas**")
            df_v = pd.DataFrame(vencidas)[["dtVenc", "nomeContato", "descricao", "valor"]].copy()
            df_v["valor"] = df_v["valor"].apply(brl)
            df_v.columns = ["Vencimento", "Cliente", "Descrição", "Valor"]
            st.dataframe(df_v, use_container_width=True, hide_index=True)
