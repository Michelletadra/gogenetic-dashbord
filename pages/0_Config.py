"""Página de configuração — reconectar Bling via OAuth."""
import streamlit as st
from utils import require_auth, GLOBAL_CSS, reset_bling_client

st.set_page_config(page_title="Config · GoGenetic", page_icon="⚙️", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
require_auth()

st.markdown('<p class="page-title">⚙️ Configurações</p>', unsafe_allow_html=True)
st.markdown('<p class="page-sub">Conexões e integrações do dashboard</p>', unsafe_allow_html=True)

# ── Bling OAuth ────────────────────────────────────────────────────────────────

st.markdown("### Bling — GoGenetic You")

import bling_auth

# Verifica parâmetro de callback OAuth
params = st.query_params
code = params.get("code")

if code:
    with st.spinner("Trocando código por tokens..."):
        try:
            tokens = bling_auth.exchange_code(code)
            reset_bling_client()
            st.success("✅ Bling conectado com sucesso! Tokens salvos.")
            st.query_params.clear()
        except Exception as e:
            st.error(f"Erro ao trocar código: {e}")
else:
    token = bling_auth.get_valid_token()
    if token:
        st.success("✅ Bling conectado")
        if st.button("🔄 Reconectar Bling (forçar novo token)"):
            url = bling_auth.get_auth_url()
            st.markdown(f"[Clique aqui para autorizar no Bling]({url})", unsafe_allow_html=False)
    else:
        st.warning("⚠️ Bling não conectado")
        url = bling_auth.get_auth_url()
        st.markdown(
            f'<a href="{url}" target="_self" style="display:inline-block;padding:10px 20px;'
            f'background:#13CFE8;color:#190E33;border-radius:8px;font-weight:600;text-decoration:none;">'
            f'🔗 Conectar Bling</a>',
            unsafe_allow_html=True,
        )
        st.caption("Você será redirecionado ao Bling para autorizar o acesso. Após aprovar, voltará automaticamente para cá.")
