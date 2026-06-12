"""Página de configuração — reconectar Bling via OAuth."""
import streamlit as st
import bling_auth

st.set_page_config(page_title="Config · GoGenetic", page_icon="⚙️", layout="wide")

# Processa callback OAuth ANTES de exigir login
code = st.query_params.get("code")
if code:
    with st.spinner("Conectando ao Bling..."):
        try:
            bling_auth.exchange_code(code)
            st.query_params.clear()
            st.success("✅ Bling conectado com sucesso! Tokens salvos.")
            st.info("Faça login para continuar.")
        except Exception as e:
            st.error(f"Erro ao trocar código: {e}")
    st.stop()

from utils import require_auth, GLOBAL_CSS
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
require_auth()

st.markdown('<p class="page-title">⚙️ Configurações</p>', unsafe_allow_html=True)
st.markdown('<p class="page-sub">Conexões e integrações do dashboard</p>', unsafe_allow_html=True)

st.markdown("### Bling — GoGenetic You")

token = bling_auth.get_valid_token()
if token:
    st.success("✅ Bling conectado")
    if st.button("🔄 Reconectar Bling"):
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
    st.caption("Você será redirecionado ao Bling para autorizar. Após aprovar, volte e faça login.")
