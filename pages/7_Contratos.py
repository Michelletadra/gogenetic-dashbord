"""Página 7 — Módulo de Contratos."""
import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import GLOBAL_CSS, brl, sidebar_header, require_auth
from db_contratos import (
    list_contratos, get_contrato, insert_contrato, update_contrato, delete_contrato,
    list_parcelas, insert_parcela, delete_parcela, resumo_contratos,
)
from db_creditos import list_clientes

st.set_page_config(page_title="Contratos | GoGenetic", page_icon="📑", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()
require_auth()

st.markdown("""
<p class="page-title">📑 Contratos</p>
<p class="page-sub">Gestão completa de contratos · Grupo GoGenetic</p>
""", unsafe_allow_html=True)

hoje = pd.Timestamp.today().normalize()

EMPRESAS  = ["GG SOLUÇÕES", "GOSOLOS", "GOGENETIC", "GG PESQUISA"]
SITUACOES = ["EM VIGÊNCIA", "ENCERRADO", "SUSPENSO", "EM NEGOCIAÇÃO"]

def dias_badge(dias):
    if dias is None:   return ""
    if dias < 0:       return "🔴 VENCIDO"
    if dias <= 30:     return f"🔴 {dias}d"
    if dias <= 60:     return f"🟠 {dias}d"
    if dias <= 90:     return f"🟡 {dias}d"
    return f"🟢 {dias}d"

tab_painel, tab_ativos, tab_historico, tab_novo = st.tabs([
    "📊 Painel", "📋 Contratos Ativos", "📁 Histórico", "➕ Novo Contrato"
])

# ══════════════════════════════════════════════════════════════════════════════
# PAINEL
# ══════════════════════════════════════════════════════════════════════════════
with tab_painel:
    res   = resumo_contratos()
    ativos = list_contratos(status="ATIVO")

    df_a = pd.DataFrame(ativos) if ativos else pd.DataFrame()
    if not df_a.empty:
        df_a["data_vencimento"] = pd.to_datetime(df_a["data_vencimento"], errors="coerce")
        df_a["dias_restantes"]  = df_a["data_vencimento"].apply(
            lambda v: int((v - hoje).days) if pd.notna(v) else None
        )
        v30 = df_a[df_a["dias_restantes"].notna() & (df_a["dias_restantes"] <= 30)]
        v60 = df_a[df_a["dias_restantes"].notna() & (df_a["dias_restantes"] <= 60)]
        v90 = df_a[df_a["dias_restantes"].notna() & (df_a["dias_restantes"] <= 90)]
        vencidos = df_a[df_a["dias_restantes"].notna() & (df_a["dias_restantes"] < 0)]
    else:
        v30 = v60 = v90 = vencidos = pd.DataFrame()

    # KPIs
    k1, k2, k3, k4, k5 = st.columns(5)
    def _kpi(col, icon, label, valor, sub="", cor="#1A0A2E"):
        col.markdown(f"""
        <div style='background:#fff;border-radius:12px;padding:16px 20px;
                    box-shadow:0 2px 8px rgba(126,22,184,0.08)'>
          <div style='font-size:.72rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{icon} {label}</div>
          <div style='font-size:1.3rem;font-weight:800;color:{cor}'>{valor}</div>
          <div style='font-size:.78rem;color:#6B7280'>{sub}</div>
        </div>""", unsafe_allow_html=True)

    _kpi(k1,"📑","Contratos Ativos",   str(res["qtd_ativos"]),      "em vigência",      "#7E16B8")
    _kpi(k2,"💰","Valor Total Ativo",  brl(res["valor_total_ativo"]),"contratos ativos", "#1A0A2E")
    _kpi(k3,"💚","Saldo Restante",     brl(res["saldo_total_ativo"]),"a executar",       "#10B981")
    _kpi(k4,"🔴","Vencendo 30d",       str(len(v30)),               "contratos",        "#EF4444" if len(v30) else "#6B7280")
    _kpi(k5,"⚪","Encerrados",         str(res["qtd_encerrados"]),  "histórico",        "#6B7280")

    st.markdown("<br>", unsafe_allow_html=True)

    # Alertas de vencimento
    if not vencidos.empty:
        st.markdown("#### 🔴 Contratos Vencidos")
        for _, row in vencidos.iterrows():
            dias = int(row["dias_restantes"])
            st.markdown(f"""
            <div style='background:#FFF5F5;border-left:4px solid #EF4444;border-radius:8px;
                        padding:10px 16px;margin-bottom:6px;display:flex;justify-content:space-between'>
              <div><b>{row['contratante']}</b>
                <span style='color:#8B6BAE;font-size:.85rem;margin-left:10px'>{row['empresa']} ·
                Venceu há {abs(dias)} dia{'s' if abs(dias)!=1 else ''}</span></div>
              <b style='color:#EF4444'>{brl(row['saldo'])}</b>
            </div>""", unsafe_allow_html=True)

    if not v30.empty:
        st.markdown("#### 🟠 Vencendo em até 30 dias")
        for _, row in v30[v30["dias_restantes"] >= 0].iterrows():
            dias = int(row["dias_restantes"])
            venc = row["data_vencimento"].strftime("%d/%m/%Y") if pd.notna(row["data_vencimento"]) else "—"
            st.markdown(f"""
            <div style='background:#FFF5F5;border-left:4px solid #F59E0B;border-radius:8px;
                        padding:10px 16px;margin-bottom:6px;display:flex;justify-content:space-between'>
              <div><b>{row['contratante']}</b>
                <span style='color:#8B6BAE;font-size:.85rem;margin-left:10px'>{row['empresa']} ·
                Vence em {dias} dia{'s' if dias!=1 else ''} ({venc})</span></div>
              <b style='color:#F59E0B'>{brl(row['saldo'])}</b>
            </div>""", unsafe_allow_html=True)

    # Gráficos
    if not df_a.empty:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Saldo por Contrato Ativo**")
            fig = px.bar(df_a.sort_values("saldo", ascending=False),
                         x="contratante", y="saldo",
                         color="empresa",
                         color_discrete_sequence=["#7E16B8","#10B981","#F59E0B","#3B82F6"],
                         labels={"saldo":"Saldo (R$)","contratante":"","empresa":"Empresa"})
            fig.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff",
                              margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.markdown("**Valor Total por Empresa**")
            emp = df_a.groupby("empresa")["valor_total"].sum().reset_index()
            fig2 = px.pie(emp, names="empresa", values="valor_total", hole=0.4,
                          color_discrete_sequence=["#7E16B8","#10B981","#F59E0B","#3B82F6"])
            fig2.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff",
                               margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# CONTRATOS ATIVOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_ativos:
    col1, col2 = st.columns(2)
    empresa_f = col1.selectbox("Empresa", ["Todas"] + EMPRESAS, key="emp_f_ativos")
    busca_f   = col2.text_input("🔎 Buscar contratante")

    ativos = list_contratos(status="ATIVO",
                            empresa=empresa_f if empresa_f != "Todas" else None)
    if busca_f:
        ativos = [c for c in ativos if busca_f.lower() in c["contratante"].lower()]

    if not ativos:
        st.info("Nenhum contrato ativo encontrado.")
    else:
        st.markdown(f"**{len(ativos)} contrato(s) ativo(s)**")
        for ct in ativos:
            venc = pd.to_datetime(ct["data_vencimento"], errors="coerce")
            dias = int((venc - hoje).days) if pd.notna(venc) else None
            badge = dias_badge(dias)
            prog = (ct["valor_consumido"] / ct["valor_total"] * 100) if ct["valor_total"] else 0

            with st.expander(f"**{ct['contratante']}**  ·  {ct['empresa']}  ·  {brl(ct['saldo'])} saldo  ·  {badge}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Valor Total",   brl(ct["valor_total"]))
                c2.metric("Consumido",     brl(ct["valor_consumido"]))
                c3.metric("Saldo",         brl(ct["saldo"]))
                c4.metric("Parcela",       brl(ct["valor_parcela"]))

                info1, info2 = st.columns(2)
                with info1:
                    venc_str = venc.strftime("%d/%m/%Y") if pd.notna(venc) else "—"
                    ass_str  = pd.to_datetime(ct["data_assinatura"], errors="coerce")
                    ass_str  = ass_str.strftime("%d/%m/%Y") if pd.notna(ass_str) else "—"
                    st.markdown(f"**Assinatura:** {ass_str} &nbsp;·&nbsp; **Validade:** {venc_str}")
                    if ct.get("kit_info"):       st.markdown(f"**Kits:** {ct['kit_info']}")
                    if ct.get("amostras_info"):  st.markdown(f"**Amostras:** {ct['amostras_info']}")
                    if ct.get("servico"):        st.markdown(f"**Serviço:** {ct['servico']}")
                    if ct.get("info_pagamento"): st.markdown(f"**Pagamento:** {ct['info_pagamento']}")
                    if ct.get("observacoes"):    st.caption(f"📝 {ct['observacoes']}")

                with info2:
                    st.markdown(f"**Execução: {prog:.0f}%**")
                    st.progress(min(prog / 100, 1.0))

                # Parcelas
                parcelas = list_parcelas(ct["id"])
                if parcelas:
                    st.markdown("**Parcelas**")
                    df_p = pd.DataFrame(parcelas)[["numero","data_emissao","valor","saldo_atual","situacao","numero_nf"]]
                    df_p.columns = ["#","Emissão","Valor","Saldo","Situação","NF"]
                    df_p["Valor"] = df_p["Valor"].apply(brl)
                    df_p["Saldo"] = df_p["Saldo"].apply(brl)
                    df_p = df_p.fillna("—")
                    st.dataframe(df_p, use_container_width=True, hide_index=True)

                # Ações
                a1, a2, a3 = st.columns(3)
                if a1.button("⏹️ Encerrar", key=f"enc_{ct['id']}"):
                    update_contrato(ct["id"], {"status": "ENCERRADO", "situacao": "ENCERRADO"})
                    st.success("Contrato encerrado.")
                    st.rerun()
                if a2.button("✏️ Editar obs.", key=f"edit_{ct['id']}"):
                    st.session_state[f"_edit_ct_{ct['id']}"] = True

                if st.session_state.get(f"_edit_ct_{ct['id']}"):
                    with st.form(f"form_edit_{ct['id']}", clear_on_submit=True):
                        nova_obs  = st.text_area("Observações", value=ct.get("observacoes","") or "")
                        novo_venc = st.date_input("Data vencimento",
                            value=venc.date() if pd.notna(venc) else date.today())
                        nova_sit  = st.selectbox("Situação", SITUACOES,
                            index=SITUACOES.index(ct["situacao"]) if ct.get("situacao") in SITUACOES else 0)
                        s1, s2 = st.columns(2)
                        if s1.form_submit_button("✅ Salvar"):
                            update_contrato(ct["id"], {
                                "observacoes": nova_obs or None,
                                "data_vencimento": str(novo_venc),
                                "situacao": nova_sit,
                            })
                            st.session_state[f"_edit_ct_{ct['id']}"] = False
                            st.rerun()
                        if s2.form_submit_button("❌ Cancelar"):
                            st.session_state[f"_edit_ct_{ct['id']}"] = False
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════
with tab_historico:
    col1, col2 = st.columns(2)
    empresa_h = col1.selectbox("Empresa", ["Todas"] + EMPRESAS, key="emp_f_hist")
    busca_h   = col2.text_input("🔎 Buscar contratante", key="busca_hist")

    encerrados = list_contratos(status="ENCERRADO",
                                empresa=empresa_h if empresa_h != "Todas" else None)
    if busca_h:
        encerrados = [c for c in encerrados if busca_h.lower() in c["contratante"].lower()]

    if not encerrados:
        st.info("Nenhum contrato encerrado.")
    else:
        st.markdown(f"**{len(encerrados)} contrato(s) no histórico**")
        for ct in encerrados:
            venc = pd.to_datetime(ct["data_vencimento"], errors="coerce")
            venc_str = venc.strftime("%d/%m/%Y") if pd.notna(venc) else "—"
            with st.expander(f"**{ct['contratante']}**  ·  {ct['empresa']}  ·  {brl(ct['valor_total'])}  ·  {venc_str}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Valor Total",  brl(ct["valor_total"]))
                c2.metric("Consumido",    brl(ct["valor_consumido"]))
                c3.metric("Parcelas",     ct["total_parcelas"])
                if ct.get("observacoes"): st.caption(f"📝 {ct['observacoes']}")

                parcelas = list_parcelas(ct["id"])
                if parcelas:
                    df_p = pd.DataFrame(parcelas)[["numero","data_emissao","valor","situacao","numero_nf"]]
                    df_p.columns = ["#","Emissão","Valor","Situação","NF"]
                    df_p["Valor"] = df_p["Valor"].apply(brl)
                    st.dataframe(df_p.fillna("—"), use_container_width=True, hide_index=True)

                if st.button("🔄 Reativar", key=f"reativ_{ct['id']}"):
                    update_contrato(ct["id"], {"status": "ATIVO", "situacao": "EM VIGÊNCIA"})
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# NOVO CONTRATO
# ══════════════════════════════════════════════════════════════════════════════
with tab_novo:
    clientes = list_clientes()
    cli_opts = {"— Sem vínculo —": None}
    cli_opts.update({c["nome"]: c["id"] for c in clientes})

    with st.form("form_novo_contrato", clear_on_submit=True):
        st.markdown("**Dados do contrato**")
        c1, c2 = st.columns(2)
        empresa     = c1.selectbox("Empresa *", EMPRESAS)
        contratante = c2.text_input("Contratante *")
        cli_sel     = c1.selectbox("Vincular a cliente", list(cli_opts.keys()))

        c3, c4 = st.columns(2)
        data_ass  = c3.date_input("Data assinatura")
        data_venc = c4.date_input("Data vencimento")

        c5, c6, c7 = st.columns(3)
        valor_total   = c5.number_input("Valor total (R$)", min_value=0.0, step=0.01, format="%.2f")
        valor_parcela = c6.number_input("Valor parcela (R$)", min_value=0.0, step=0.01, format="%.2f")
        total_parc    = c7.number_input("Nº parcelas", min_value=0, step=1)

        c8, c9 = st.columns(2)
        servico    = c8.text_input("Serviço")
        kit_info   = c9.text_input("Kit info")
        amostras   = c8.text_input("Amostras")
        info_pgto  = c9.text_input("Info pagamento")
        obs        = st.text_area("Observações", height=80)

        if st.form_submit_button("➕ Cadastrar Contrato", use_container_width=True):
            if contratante.strip() and empresa:
                insert_contrato({
                    "empresa":         empresa,
                    "contratante":     contratante.strip(),
                    "cliente_id":      cli_opts[cli_sel],
                    "data_assinatura": str(data_ass),
                    "data_vencimento": str(data_venc),
                    "valor_total":     float(valor_total),
                    "valor_parcela":   float(valor_parcela),
                    "total_parcelas":  int(total_parc),
                    "status":          "ATIVO",
                    "situacao":        "EM VIGÊNCIA",
                    "servico":         servico or None,
                    "kit_info":        kit_info or None,
                    "amostras_info":   amostras or None,
                    "info_pagamento":  info_pgto or None,
                    "observacoes":     obs or None,
                })
                st.success(f"✅ Contrato com {contratante} cadastrado!")
                st.rerun()
            else:
                st.error("Empresa e Contratante são obrigatórios.")
