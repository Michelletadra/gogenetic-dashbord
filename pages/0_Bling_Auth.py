"""Página de callback OAuth do Bling — use esta URL como redirect_uri no Bling."""
import streamlit as st
from utils import GLOBAL_CSS, sidebar_header, require_auth
import bling_auth

st.set_page_config(page_title="Bling Auth | GoGenetic", page_icon="🔑", layout="centered")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()
require_auth()

st.markdown("## 🔑 Conexão Bling")

# Captura código de callback
params = st.query_params
code = params.get("code")

if code:
    with st.spinner("Trocando código por tokens..."):
        try:
            tokens = bling_auth.exchange_code(code)
            st.success("✅ Bling conectado com sucesso!")
            st.markdown(f"**Access token:** `{tokens.get('access_token','')[:30]}...`")
            st.markdown(f"**Expira em:** {tokens.get('expires_at','—')}")
            st.query_params.clear()
        except Exception as e:
            st.error(f"Erro ao trocar código: {e}")
else:
    # Mostra botão para iniciar autorização
    connected = bling_auth.is_connected()
    if connected:
        st.success("✅ Bling já está conectado.")
        if st.button("🔄 Reconectar (obter novo token)"):
            st.markdown(f"[Clique aqui para autorizar]({bling_auth.get_auth_url()})")
    else:
        st.warning("⚠️ Bling não conectado.")

    st.markdown("---")
    auth_url = bling_auth.get_auth_url()
    st.markdown(f"### [▶️ Clique aqui para autorizar o Bling]({auth_url})")
    st.caption("Após autorizar, você será redirecionado de volta para esta página automaticamente.")
