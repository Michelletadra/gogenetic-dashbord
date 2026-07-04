"""Home — Visão geral do Grupo GoGenetic."""
import streamlit as st
from datetime import date
from utils import (GLOBAL_CSS, ASSETS, BRAND, NOMES, TODOS_NOMES, NOME_YOU,
                   CHART_COLORS, brl, soma, kpi_card, plotly_layout,
                   get_clients, load_company_data, load_bling_data,
                   sidebar_header, get_authenticator)
import bling_auth

st.set_page_config(
    page_title="Visão Mensal | GoGenetic",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── OAuth2 Bling — captura o código de retorno ─────────────────────────────────
# Roda ANTES do login: o fluxo no Bling pode derrubar a sessão e forçar novo
# login, o que faria o código nunca ser processado se isso viesse depois.
params = st.query_params
if "code" in params and params.get("state") == "bling_dashboard":
    with st.spinner("Conectando ao Bling..."):
        try:
            bling_auth.exchange_code(params["code"])
            st.query_params.clear()
            st.success("✅ GoGenetic You conectada com sucesso!")
        except Exception as e:
            st.query_params.clear()
            st.error(f"Erro ao conectar ao Bling: {e}")

# ── Autenticação ───────────────────────────────────────────────────────────────
authenticator = get_authenticator()
authenticator.login(location="main")

if st.session_state.get("authentication_status") is False:
    st.error("❌ Usuário ou senha incorretos.")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.markdown("""
    <div style='text-align:center;margin-top:40px'>
        <img src='https://raw.githubusercontent.com/Michelletadra/gogenetic-dashbord/main/assets/logo_gg.png' width='200'><br><br>
        <p style='color:#7E16B8;font-size:1.1rem;font-weight:600'>Dashboard Financeiro · Grupo GoGenetic</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
sidebar_header()
with st.sidebar:
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ Cache: 5 min")
    st.markdown("---")

    # Status Bling / GoGenetic You
    st.markdown("**🧬 GoGenetic You (Bling)**")
    _bling_erro = bling_auth.connection_error()
    if _bling_erro is None:
        st.success("✅ Conectada")
        if st.button("🔌 Desconectar", use_container_width=True):
            bling_auth.disconnect()
            st.rerun()
    else:
        st.warning("⚠️ Não conectada")
        st.caption(f"Motivo: {_bling_erro}")
        st.link_button("🔗 Conectar ao Bling", bling_auth.get_auth_url(), use_container_width=True)
    st.markdown("---")
    st.caption("Navegue pelas páginas no menu acima ↑")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<p class="page-title">🧬 Visão Mensal da Empresa</p>
<p class="page-sub">Resumo consolidado das 4 empresas · Mês atual</p>
""", unsafe_allow_html=True)

# ── Carrega dados do mês atual para todas as empresas ─────────────────────────
dt_ini = date.today().replace(day=1).strftime("%Y-%m-%d")
dt_fim = date.today().strftime("%Y-%m-%d")

_placeholder = st.empty()
with _placeholder.container():
    st.info("⏳ Carregando dados das empresas... Isso pode levar alguns segundos na primeira vez.")

from concurrent.futures import ThreadPoolExecutor

def _load(nome):
    return nome, load_company_data(nome, dt_ini, dt_fim)

with ThreadPoolExecutor(max_workers=len(NOMES)) as ex:
    raw = dict(ex.map(lambda n: _load(n), NOMES))

if bling_auth.is_connected():
    raw[NOME_YOU] = load_bling_data(dt_ini, dt_fim)

_placeholder.empty()

empresas_visiveis = NOMES + ([NOME_YOU] if bling_auth.is_connected() else [])

# ── KPIs por empresa ──────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Performance do Mês — por Empresa</div>", unsafe_allow_html=True)

for nome in empresas_visiveis:
    brand  = BRAND[nome]
    dados  = raw[nome]
    vendas = dados["vendas"]
    fat    = dados["faturamento"]
    rec    = dados["contas_receber"]
    pag    = dados["contas_pagar"]

    total_v = soma(vendas, "valorTotal")
    total_f = soma(fat,    "valor")
    total_r = soma(rec,    "valor")
    total_p = soma(pag,    "valor")

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;margin:16px 0 8px 0;">
      <div style="width:6px;height:32px;background:{brand['primary']};border-radius:3px;"></div>
      <span style="font-size:1rem;font-weight:700;color:#1A0A2E">{nome}</span>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_card(c1, "🛒", "Vendas",     brl(total_v), f"{len(vendas)} pedidos",  border=f"rgba{tuple(int(brand['primary'].lstrip('#')[i:i+2],16) for i in (0,2,4))}0.25)")
    kpi_card(c2, "🎯", "Ticket Méd", brl(total_v/len(vendas) if vendas else 0), "", border=f"rgba{tuple(int(brand['primary'].lstrip('#')[i:i+2],16) for i in (0,2,4))}0.25)")
    kpi_card(c3, "💰", "Recebido",   brl(total_f), f"{len(fat)} lançtos",     border=f"rgba{tuple(int(brand['primary'].lstrip('#')[i:i+2],16) for i in (0,2,4))}0.25)")
    kpi_card(c4, "📥", "A Receber",  brl(total_r), f"{len(rec)} títulos",     border=f"rgba{tuple(int(brand['primary'].lstrip('#')[i:i+2],16) for i in (0,2,4))}0.25)")
    kpi_card(c5, "📤", "A Pagar",    brl(total_p), f"{len(pag)} títulos",     border=f"rgba{tuple(int(brand['primary'].lstrip('#')[i:i+2],16) for i in (0,2,4))}0.25)")

# ── Totais consolidados ────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Consolidado Grupo</div>", unsafe_allow_html=True)

all_vendas = [item for n in empresas_visiveis for item in raw[n]["vendas"]]
all_fat    = [item for n in empresas_visiveis for item in raw[n]["faturamento"]]
all_rec    = [item for n in empresas_visiveis for item in raw[n]["contas_receber"]]
all_pag    = [item for n in empresas_visiveis for item in raw[n]["contas_pagar"]]

tv = soma(all_vendas, "valorTotal")
tf = soma(all_fat,    "valor")
tr = soma(all_rec,    "valor")
tp = soma(all_pag,    "valor")
ts = tr - tp

c1, c2, c3, c4, c5, c6 = st.columns(6)
kpi_card(c1, "🛒", "Vendas Grupo",    brl(tv), f"{len(all_vendas)} pedidos")
kpi_card(c2, "🎯", "Ticket Médio",    brl(tv/len(all_vendas) if all_vendas else 0))
kpi_card(c3, "💰", "Recebido",        brl(tf), f"{len(all_fat)} lançtos")
kpi_card(c4, "📥", "A Receber",       brl(tr), f"{len(all_rec)} títulos")
kpi_card(c5, "📤", "A Pagar",         brl(tp), f"{len(all_pag)} títulos")
kpi_card(c6, "📈", "Saldo Previsto",  brl(abs(ts)),
         "Receber − Pagar",
         border="rgba(36,183,140,0.4)" if ts >= 0 else "rgba(255,103,47,0.4)",
         value_class="kpi-positive" if ts >= 0 else "kpi-negative")
