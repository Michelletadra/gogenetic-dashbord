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
    st.link_button("🔗 Conectar Bling", url)
    st.caption(f"URL de autorização: {url}")
    st.caption("Clique no botão acima. Após aprovar no Bling, você será redirecionado de volta para cá.")
