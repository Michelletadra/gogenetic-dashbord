"""Página 7 — Módulo de Contratos (completo)."""
import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import GLOBAL_CSS, brl, sidebar_header, require_auth
from db_contratos import (
    list_contratos, get_contrato, insert_contrato, update_contrato, delete_contrato,
    list_parcelas, insert_parcela, delete_parcela,
    list_aditivos, insert_aditivo, delete_aditivo,
    resumo_contratos, compute_status,
)
from db_creditos import list_clientes

st.set_page_config(page_title="Contratos | GoGenetic", page_icon="📑", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()
require_auth()

st.markdown("""
<p class="page-title">📑 Contratos</p>
<p class="page-sub">Gestão completa · Grupo GoGenetic</p>
""", unsafe_allow_html=True)

hoje = pd.Timestamp.today().normalize()

# ── Constantes ────────────────────────────────────────────────────────────────
TIPOS = ["Prestação laboratorial","Prestação científica","SaaS","SaaS + laboratório",
         "SaaS + microbioma","White label","Parceria estratégica","Internacional",
         "Representação comercial","Pay per use","Enterprise","P&D","Comodato",
         "Cooperação técnica","Cooperação científica","Desenvolvimento tecnológico",
         "Desenvolvimento científico","Consultoria + kits","Implantação",
         "Prestação corporativa","Prestação recorrente","Prestação contínua",
         "Prestação pontual","Prestação de serviço","Compliance corporativo",
         "Governamental","Outro"]
CATEGORIAS = ["Kits moleculares","Microbioma de solo","Metagenômica","SaaS + genética humana",
              "Plataforma + análises","Plataforma GoSolos","Enterprise","Pay per use",
              "Canal/parceria","qPCR","Microbiologia","Pesquisa agrícola","Bioinsumos",
              "Laboratorial","Diagnóstico","Metagenoma","Multinacional","Corporativo",
              "Escala industrial","Equipamentos","Consultoria técnica","Desenvolvimento",
              "Pesquisa microbiológica","Internacional","Outro"]
EMPRESAS  = ["GG SOLUÇÕES","GOSOLOS","GOGENETIC","GG PESQUISA"]
_EMPRESA_LABEL = {"GOGENETIC": "Gogenetic You"}
INDICES   = ["IPCA","IGP-M","SELIC","INPC","Fixo","Outro"]
MOEDAS    = ["BRL","USD","EUR","GBP","JPY"]
PAGAMENTOS= ["Mensal","Trimestral","Semestral","Anual","Por parcela","Por amostra","Pontual"]
PLATAFORMAS=["GoSolos","GoGenetic Lab","Externo","N/A"]

STATUS_COLORS = {
    "ATIVO":               ("#10B981","#D1FAE5"),
    "VENCENDO 30D":        ("#EF4444","#FEE2E2"),
    "VENCENDO 60D":        ("#F97316","#FEF3C7"),
    "VENCENDO 90D":        ("#F59E0B","#FFFBEB"),
    "RENOVAÇÃO AUTOMÁTICA":("#3B82F6","#DBEAFE"),
    "VENCIDO":             ("#6B7280","#F3F4F6"),
    "ENCERRADO":           ("#6B7280","#F3F4F6"),
    "RESCINDIDO":          ("#EF4444","#FEE2E2"),
    "EM NEGOCIAÇÃO":       ("#8B5CF6","#EDE9FE"),
    "SUSPENSO":            ("#F59E0B","#FEF3C7"),
}

def status_badge(s):
    cor, bg = STATUS_COLORS.get(s, ("#6B7280","#F3F4F6"))
    return f'<span style="background:{bg};color:{cor};padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600">{s}</span>'

def flag_icons(ct):
    flags = []
    if ct.get("internacional"):      flags.append("🌍")
    if ct.get("white_label"):        flags.append("🏷️")
    if ct.get("recorrente"):         flags.append("🔄")
    if ct.get("renovacao_automatica"):flags.append("♻️")
    if ct.get("tem_comissao"):       flags.append("💰")
    if ct.get("confidencialidade"):  flags.append("🔒")
    if ct.get("propriedade_intelectual"):flags.append("⚡")
    return " ".join(flags)

def dias_ate(data_termino):
    if not data_termino: return None
    try:
        v = pd.to_datetime(data_termino)
        return int((v - hoje).days)
    except: return None

# ══════════════════════════════════════════════════════════════════════════════
tabs = st.tabs(["📊 Painel","📋 Contratos","🔍 Detalhes","➕ Novo","📎 Aditivos"])
tab_painel, tab_lista, tab_detalhe, tab_novo, tab_aditivos = tabs

# ══════════════════════════════════════════════════════════════════════════════
# PAINEL
# ══════════════════════════════════════════════════════════════════════════════
with tab_painel:
    res  = resumo_contratos()
    todos = res["todos"]

    # ── KPIs linha 1 ──────────────────────────────────────────────────────────
    def _kpi(col, icon, label, valor, sub="", cor="#1A0A2E"):
        col.markdown(f"""
        <div style='background:#fff;border-radius:12px;padding:14px 18px;
                    box-shadow:0 2px 8px rgba(126,22,184,0.08)'>
          <div style='font-size:.68rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{icon} {label}</div>
          <div style='font-size:1.25rem;font-weight:800;color:{cor}'>{valor}</div>
          <div style='font-size:.75rem;color:#6B7280'>{sub}</div>
        </div>""", unsafe_allow_html=True)

    k = st.columns(6)
    _kpi(k[0],"📑","Ativos",         str(res["qtd_ativos"]),             "contratos","#7E16B8")
    _kpi(k[1],"🔴","Venc. 30d",      str(res["qtd_vencendo_30"]),        "contratos","#EF4444" if res["qtd_vencendo_30"] else "#6B7280")
    _kpi(k[2],"🟠","Venc. 60d",      str(res["qtd_vencendo_60"]),        "contratos","#F97316" if res["qtd_vencendo_60"] else "#6B7280")
    _kpi(k[3],"🟡","Venc. 90d",      str(res["qtd_vencendo_90"]),        "contratos","#F59E0B" if res["qtd_vencendo_90"] else "#6B7280")
    _kpi(k[4],"⚠️","Vencidos",       str(res["qtd_vencidos"]),           "contratos","#EF4444" if res["qtd_vencidos"] else "#6B7280")
    _kpi(k[5],"⚪","Encerrados",      str(res["qtd_encerrados"]),         "histórico","#6B7280")

    st.markdown("<br>", unsafe_allow_html=True)
    k2 = st.columns(5)
    _kpi(k2[0],"💰","Rec. Recorrente",brl(res["receita_recorrente"]),     "/ano","#10B981")
    _kpi(k2[1],"🌍","Internacionais", str(res["qtd_internacionais"]),     "contratos","#3B82F6")
    _kpi(k2[2],"🏷️","White Label",   str(res["qtd_white_label"]),        "contratos","#8B5CF6")
    _kpi(k2[3],"♻️","Renov. Auto",   str(res["qtd_renovacao_auto"]),     "contratos","#10B981")
    _kpi(k2[4],"🔄","Recorrentes",   str(res["qtd_recorrentes"]),        "contratos","#7E16B8")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Alertas ───────────────────────────────────────────────────────────────
    urgentes = [c for c in todos if c["status_real"] in ("VENCENDO 30D","VENCIDO")]
    if urgentes:
        st.markdown("#### 🚨 Atenção imediata")
        for ct in urgentes:
            dias = dias_ate(ct.get("data_termino"))
            cor  = "#EF4444"
            msg  = f"Vencido há {abs(dias)} dia{'s' if abs(dias)!=1 else ''}" if dias and dias < 0 \
                   else f"Vence em {dias} dia{'s' if dias!=1 else ''}"
            dt   = pd.to_datetime(ct.get("data_termino")).strftime("%d/%m/%Y") if ct.get("data_termino") else "—"
            st.markdown(f"""
            <div style='background:#FFF5F5;border-left:4px solid {cor};border-radius:8px;
                        padding:10px 16px;margin-bottom:6px;display:flex;justify-content:space-between'>
              <div><b>{ct['contratante']}</b>
                <span style='color:#8B6BAE;font-size:.82rem;margin-left:8px'>
                  {ct['empresa_gg']} · {ct.get('tipo_contrato','—')} · {msg} ({dt})
                </span></div>
              <span>{flag_icons(ct)}</span>
            </div>""", unsafe_allow_html=True)

    prox = [c for c in todos if c["status_real"] in ("VENCENDO 60D","VENCENDO 90D")]
    if prox:
        st.markdown("#### ⚠️ Próximos vencimentos (60–90 dias)")
        for ct in prox:
            dias = dias_ate(ct.get("data_termino"))
            cor  = "#F59E0B"
            dt   = pd.to_datetime(ct.get("data_termino")).strftime("%d/%m/%Y") if ct.get("data_termino") else "—"
            st.markdown(f"""
            <div style='background:#FFFBEB;border-left:4px solid {cor};border-radius:8px;
                        padding:10px 16px;margin-bottom:6px;display:flex;justify-content:space-between'>
              <div><b>{ct['contratante']}</b>
                <span style='color:#8B6BAE;font-size:.82rem;margin-left:8px'>
                  {ct['empresa_gg']} · {dias}d ({dt})
                </span></div>
              <span>{flag_icons(ct)}</span>
            </div>""", unsafe_allow_html=True)

    # ── Gráficos ──────────────────────────────────────────────────────────────
    ativos_df = pd.DataFrame([c for c in todos if c["status_real"] not in ("ENCERRADO","RESCINDIDO")])
    if not ativos_df.empty:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Contratos por Tipo**")
            tc = ativos_df["tipo_contrato"].value_counts().reset_index()
            tc.columns = ["Tipo","Qtd"]
            fig = px.bar(tc, x="Qtd", y="Tipo", orientation="h",
                         color_discrete_sequence=["#7E16B8"],
                         labels={"Qtd":"Contratos","Tipo":""})
            fig.update_layout(yaxis=dict(autorange="reversed"),
                              plot_bgcolor="#fff", paper_bgcolor="#fff",
                              margin=dict(l=0,r=0,t=0,b=0), height=300)
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.markdown("**Distribuição por Empresa**")
            ec = ativos_df["empresa_gg"].value_counts().reset_index()
            ec.columns = ["Empresa","Qtd"]
            fig2 = px.pie(ec, names="Empresa", values="Qtd", hole=0.4,
                          color_discrete_sequence=["#7E16B8","#10B981","#F59E0B","#3B82F6"])
            fig2.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff",
                               margin=dict(l=0,r=0,t=0,b=0), height=300)
            st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# LISTA DE CONTRATOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_lista:
    # ── Filtros ───────────────────────────────────────────────────────────────
    with st.expander("🔍 Filtros", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        f_empresa  = fc1.selectbox("Empresa", ["Todas"] + EMPRESAS, key="fl_emp")
        f_tipo     = fc2.selectbox("Tipo", ["Todos"] + TIPOS, key="fl_tipo")
        f_busca    = fc3.text_input("🔎 Buscar", key="fl_busca")
        fc5, fc6, fc7, fc8 = st.columns(4)
        f_intern   = fc5.checkbox("🌍 Internacionais", key="fl_int")
        f_wl       = fc6.checkbox("🏷️ White label", key="fl_wl")
        f_recorr   = fc7.checkbox("🔄 Recorrentes", key="fl_rec")
        f_comiss   = fc8.checkbox("💰 Com comissão", key="fl_com")

    todos_ct = list_contratos(
        empresa=f_empresa if f_empresa != "Todas" else None,
        tipo=f_tipo if f_tipo != "Todos" else None,
        busca=f_busca or None,
        internacional=True if f_intern else None,
        white_label=True if f_wl else None,
        recorrente=True if f_recorr else None,
        tem_comissao=True if f_comiss else None,
    )

    _ATIVOS_SR    = {"ATIVO","VENCENDO 30D","VENCENDO 60D","VENCENDO 90D",
                     "RENOVAÇÃO AUTOMÁTICA","EM NEGOCIAÇÃO","SUSPENSO"}
    _VENCIDOS_SR  = {"VENCIDO"}
    _ENCERR_SR    = {"ENCERRADO","RESCINDIDO"}

    ct_ativos    = [c for c in todos_ct if c["status_real"] in _ATIVOS_SR]
    ct_vencidos  = [c for c in todos_ct if c["status_real"] in _VENCIDOS_SR]
    ct_encerrados = [c for c in todos_ct if c["status_real"] in _ENCERR_SR]

    def _render_lista(contratos, tab_key):
        if not contratos:
            st.info("Nenhum contrato nesta categoria.")
            return
        st.markdown(f"**{len(contratos)} contrato(s)**")
        from collections import defaultdict
        por_empresa = defaultdict(list)
        for ct in contratos:
            por_empresa[ct.get("empresa_gg") or "—"].append(ct)
        for empresa, contratos_emp in sorted(por_empresa.items()):
            rec_emp = sum(c.get("valor_recorrente") or 0 for c in contratos_emp)
            empresa_label = _EMPRESA_LABEL.get(empresa, empresa)
            st.markdown(
                f"<div style='background:#EDE9F8;border-radius:10px;padding:8px 16px;"
                f"margin:16px 0 6px 0;font-weight:700;color:#4A1259;font-size:.95rem'>"
                f"🏢 {empresa_label} &nbsp;·&nbsp; {len(contratos_emp)} contrato(s)"
                f"{'&nbsp;·&nbsp; Rec.: ' + brl(rec_emp) + '/ano' if rec_emp else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )
            for ct in contratos_emp:
                sr   = ct["status_real"]
                cor, bg = STATUS_COLORS.get(sr, ("#6B7280","#F3F4F6"))
                dias = dias_ate(ct.get("data_termino"))
                dt   = pd.to_datetime(ct["data_termino"]).strftime("%d/%m/%Y") if ct.get("data_termino") else "—"
                vt   = brl(ct["valor_total"]) if ct.get("valor_total") else "—"
                flags = flag_icons(ct)
                with st.expander(
                    f"**{ct['contratante']}**  ·  "
                    f"{ct.get('tipo_contrato','—')}  ·  {sr}  {flags}"
                ):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.markdown(f"**Tipo:** {ct.get('tipo_contrato','—')}")
                    c1.markdown(f"**Categoria:** {ct.get('categoria','—')}")
                    c1.markdown(f"**Serviço:** {ct.get('servico_principal','—')}")
                    c2.markdown(f"**Vencimento:** {dt}")
                    c2.markdown(f"**Assinatura:** {ct.get('data_assinatura','—') or '—'}")
                    if dias is not None:
                        c2.markdown(f"**Dias restantes:** {'**'+str(dias)+'**' if dias >= 0 else f'⚠️ {abs(dias)}d vencido'}")
                    c2.markdown(f"**Status:** {sr}")
                    c3.markdown(f"**Valor total:** {vt}")
                    if ct.get("valor_recorrente"):   c3.markdown(f"**Recorrente:** {brl(ct['valor_recorrente'])}/ano")
                    if ct.get("valor_por_amostra"):  c3.markdown(f"**Por amostra:** {brl(ct['valor_por_amostra'])}")
                    if ct.get("comissao_percentual"): c3.markdown(f"**Comissão:** {ct['comissao_percentual']}%")
                    if ct.get("forma_pagamento"):     c3.markdown(f"**Pagamento:** {ct['forma_pagamento']}")
                    c4.markdown(f"**País:** {ct.get('pais','Brasil')}")
                    if ct.get("responsavel_interno"):  c4.markdown(f"**Responsável:** {ct['responsavel_interno']}")
                    if ct.get("parceiro_relacionado"): c4.markdown(f"**Parceiro:** {ct['parceiro_relacionado']}")
                    if ct.get("plataforma_vinculada"):  c4.markdown(f"**Plataforma:** {ct['plataforma_vinculada']}")
                    comp_flags = []
                    if ct.get("lgpd"):                     comp_flags.append("LGPD")
                    if ct.get("confidencialidade"):         comp_flags.append("Confidencialidade")
                    if ct.get("nao_concorrencia"):          comp_flags.append("Não concorrência")
                    if ct.get("propriedade_intelectual"):   comp_flags.append("Prop. Intelectual")
                    if ct.get("compartilhamento_dados"):    comp_flags.append("Compartilhamento dados")
                    if ct.get("internacionalizacao_dados"): comp_flags.append("Internacionalização dados")
                    if comp_flags:
                        st.markdown(f"**Compliance:** {' · '.join(comp_flags)}")
                    if ct.get("amostras_contratadas"):
                        am_ut  = ct.get("amostras_utilizadas",0) or 0
                        am_ct  = ct["amostras_contratadas"]
                        am_sal = am_ct - am_ut + (ct.get("amostras_bonus",0) or 0)
                        ac1, ac2, ac3 = st.columns(3)
                        ac1.metric("Amostras contratadas", am_ct)
                        ac2.metric("Amostras utilizadas",  am_ut)
                        ac3.metric("Saldo amostras",       am_sal)
                    if ct.get("observacoes"):  st.caption(f"📝 {ct['observacoes']}")
                    if ct.get("obs_tecnicas"): st.caption(f"🔧 {ct['obs_tecnicas']}")
                    parcelas = list_parcelas(ct["id"])
                    if parcelas:
                        with st.expander(f"📊 {len(parcelas)} parcelas", expanded=False):
                            df_p = pd.DataFrame(parcelas)[["numero","data_emissao","valor","saldo_atual","situacao","numero_nf"]]
                            df_p.columns = ["#","Emissão","Valor","Saldo","Situação","NF"]
                            df_p["Valor"] = df_p["Valor"].apply(brl)
                            df_p["Saldo"] = df_p["Saldo"].apply(brl)
                            st.dataframe(df_p.fillna("—"), use_container_width=True, hide_index=True)
                    a1, a2, a3, a4 = st.columns(4)
                    if ct["status_real"] not in ("ENCERRADO","RESCINDIDO"):
                        if a1.button("⏹️ Encerrar", key=f"enc_{tab_key}_{ct['id']}"):
                            update_contrato(ct["id"], {"status":"ENCERRADO"})
                            st.rerun()
                        if a2.button("📝 Editar", key=f"edit_{tab_key}_{ct['id']}"):
                            st.session_state["_editar_ct_id"] = ct["id"]
                            st.rerun()
                    else:
                        if a1.button("🔄 Reativar", key=f"reativ_{tab_key}_{ct['id']}"):
                            update_contrato(ct["id"], {"status":"ATIVO"})
                            st.rerun()
                    if a4.button("🗑️ Excluir", key=f"del_{tab_key}_{ct['id']}"):
                        delete_contrato(ct["id"])
                        st.rerun()

    stab_at, stab_venc, stab_enc = st.tabs([
        f"✅ Ativos ({len(ct_ativos)})",
        f"⏰ Vencidos ({len(ct_vencidos)})",
        f"🔒 Encerrados ({len(ct_encerrados)})",
    ])
    with stab_at:
        _render_lista(ct_ativos, "at")
    with stab_venc:
        _render_lista(ct_vencidos, "venc")
    with stab_enc:
        _render_lista(ct_encerrados, "enc")

    # Exportar
    if todos_ct:
        df_exp = pd.DataFrame(todos_ct)[[
            "contratante","empresa_gg","tipo_contrato","categoria","servico_principal",
            "status_real","data_assinatura","data_termino","valor_total","valor_recorrente",
            "internacional","white_label","recorrente","renovacao_automatica","observacoes"
        ]].copy()
        df_exp.columns = ["Cliente","Empresa","Tipo","Categoria","Serviço","Status",
                          "Assinatura","Vencimento","Valor Total","Rec. Anual",
                          "Internacional","White Label","Recorrente","Renov. Auto","Obs."]
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df_exp.to_excel(w, index=False, sheet_name="Contratos")
        st.download_button("📥 Exportar Excel", data=buf.getvalue(),
                           file_name="contratos.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ══════════════════════════════════════════════════════════════════════════════
# EDIÇÃO INLINE (via session_state)
# ══════════════════════════════════════════════════════════════════════════════
with tab_detalhe:
    ct_id = st.session_state.get("_editar_ct_id")
    ids   = [c["id"] for c in list_contratos()]
    opcoes = ["— Selecione —"] + [f"{c['contratante']} ({c['empresa_gg']})" for c in list_contratos()]
    sel_idx = st.selectbox("Contrato", opcoes)
    if sel_idx != "— Selecione —":
        idx = opcoes.index(sel_idx) - 1
        ct  = list_contratos()[idx]
        ct_id = ct["id"]

    if ct_id:
        ct = get_contrato(ct_id)
        if ct:
            st.markdown(f"### ✏️ Editando: **{ct['contratante']}** — {ct['empresa_gg']}")
            with st.form("form_edit_ct", clear_on_submit=False):
                st.markdown("**Dados gerais**")
                e1,e2,e3 = st.columns(3)
                novo_contratante = e1.text_input("Contratante", value=ct["contratante"])
                nova_empresa = e2.selectbox("Empresa", EMPRESAS,
                    index=EMPRESAS.index(ct["empresa_gg"]) if ct["empresa_gg"] in EMPRESAS else 0)
                novo_pais = e3.text_input("País", value=ct.get("pais","Brasil") or "Brasil")

                e4,e5 = st.columns(2)
                novo_tipo = e4.selectbox("Tipo", TIPOS,
                    index=TIPOS.index(ct["tipo_contrato"]) if ct.get("tipo_contrato") in TIPOS else 0)
                nova_cat  = e5.selectbox("Categoria", CATEGORIAS,
                    index=CATEGORIAS.index(ct["categoria"]) if ct.get("categoria") in CATEGORIAS else 0)
                novo_serv = st.text_input("Serviço principal", value=ct.get("servico_principal","") or "")

                st.markdown("**Vigência**")
                v1,v2,v3 = st.columns(3)
                novo_dt = v1.text_input("Data vencimento (AAAA-MM-DD)", value=ct.get("data_termino","") or "")
                nova_ass = v2.text_input("Data assinatura (AAAA-MM-DD)", value=ct.get("data_assinatura","") or "")
                novo_status = v3.selectbox("Status manual", list(STATUS_COLORS.keys()),
                    index=list(STATUS_COLORS.keys()).index(ct["status"]) if ct["status"] in STATUS_COLORS else 0)

                st.markdown("**Financeiro**")
                f1,f2,f3,f4 = st.columns(4)
                novo_vt  = f1.number_input("Valor total", value=float(ct.get("valor_total") or 0), step=0.01)
                novo_vr  = f2.number_input("Valor recorrente/ano", value=float(ct.get("valor_recorrente") or 0), step=0.01)
                novo_va  = f3.number_input("Valor por amostra", value=float(ct.get("valor_por_amostra") or 0), step=0.01)
                novo_cp  = f4.number_input("Comissão %", value=float(ct.get("comissao_percentual") or 0), step=0.1)

                st.markdown("**Flags**")
                fl1,fl2,fl3,fl4,fl5 = st.columns(5)
                n_intern = fl1.checkbox("Internacional",    value=bool(ct.get("internacional")))
                n_wl     = fl2.checkbox("White label",      value=bool(ct.get("white_label")))
                n_rec    = fl3.checkbox("Recorrente",       value=bool(ct.get("recorrente")))
                n_ra     = fl4.checkbox("Renovação auto",   value=bool(ct.get("renovacao_automatica")))
                n_com    = fl5.checkbox("Tem comissão",     value=bool(ct.get("tem_comissao")))

                st.markdown("**Compliance**")
                cp1,cp2,cp3,cp4,cp5,cp6 = st.columns(6)
                n_lgpd = cp1.checkbox("LGPD",          value=bool(ct.get("lgpd")))
                n_conf = cp2.checkbox("Confidencial",  value=bool(ct.get("confidencialidade")))
                n_nc   = cp3.checkbox("Não concorrência",value=bool(ct.get("nao_concorrencia")))
                n_pi   = cp4.checkbox("Prop. Intelectual",value=bool(ct.get("propriedade_intelectual")))
                n_cd   = cp5.checkbox("Compart. dados",value=bool(ct.get("compartilhamento_dados")))
                n_id   = cp6.checkbox("Internac. dados",value=bool(ct.get("internacionalizacao_dados")))

                st.markdown("**Amostras**")
                am1,am2,am3 = st.columns(3)
                n_am_ct = am1.number_input("Contratadas", value=int(ct.get("amostras_contratadas") or 0), step=1)
                n_am_ut = am2.number_input("Utilizadas",  value=int(ct.get("amostras_utilizadas")  or 0), step=1)
                n_am_bn = am3.number_input("Bônus",       value=int(ct.get("amostras_bonus")        or 0), step=1)

                n_obs    = st.text_area("Observações",    value=ct.get("observacoes","") or "", height=70)
                n_obstech= st.text_area("Obs. técnicas",  value=ct.get("obs_tecnicas","") or "", height=70)
                n_resp   = st.text_input("Responsável interno", value=ct.get("responsavel_interno","") or "")
                n_parceiro = st.text_input("Parceiro relacionado", value=ct.get("parceiro_relacionado","") or "")

                if st.form_submit_button("✅ Salvar alterações", use_container_width=True):
                    update_contrato(ct_id, {
                        "contratante": novo_contratante, "empresa_gg": nova_empresa,
                        "pais": novo_pais, "tipo_contrato": novo_tipo, "categoria": nova_cat,
                        "servico_principal": novo_serv or None,
                        "data_termino": novo_dt or None, "data_assinatura": nova_ass or None,
                        "status": novo_status,
                        "valor_total": novo_vt, "valor_recorrente": novo_vr,
                        "valor_por_amostra": novo_va, "comissao_percentual": novo_cp,
                        "internacional": 1 if n_intern else 0, "white_label": 1 if n_wl else 0,
                        "recorrente": 1 if n_rec else 0, "renovacao_automatica": 1 if n_ra else 0,
                        "tem_comissao": 1 if n_com else 0,
                        "lgpd": 1 if n_lgpd else 0, "confidencialidade": 1 if n_conf else 0,
                        "nao_concorrencia": 1 if n_nc else 0, "propriedade_intelectual": 1 if n_pi else 0,
                        "compartilhamento_dados": 1 if n_cd else 0, "internacionalizacao_dados": 1 if n_id else 0,
                        "amostras_contratadas": n_am_ct, "amostras_utilizadas": n_am_ut, "amostras_bonus": n_am_bn,
                        "observacoes": n_obs or None, "obs_tecnicas": n_obstech or None,
                        "responsavel_interno": n_resp or None, "parceiro_relacionado": n_parceiro or None,
                    })
                    st.success("✅ Contrato atualizado!")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# NOVO CONTRATO
# ══════════════════════════════════════════════════════════════════════════════
with tab_novo:
    clientes = list_clientes()
    cli_map  = {"— Sem vínculo —": None, **{c["nome"]: c["id"] for c in clientes}}

    with st.form("form_novo_ct", clear_on_submit=True):
        st.markdown("#### 📋 Dados Gerais")
        g1,g2,g3 = st.columns(3)
        n_contratante = g1.text_input("Contratante *")
        n_empresa_gg  = g2.selectbox("Empresa GoGenetic *", EMPRESAS)
        n_cli         = g3.selectbox("Vincular cliente (CRM)", list(cli_map.keys()))
        g4,g5,g6 = st.columns(3)
        n_tipo        = g4.selectbox("Tipo de contrato *", TIPOS)
        n_categoria   = g5.selectbox("Categoria", CATEGORIAS)
        n_servico     = g6.text_input("Serviço principal")
        g7,g8,g9 = st.columns(3)
        n_cnpj        = g7.text_input("CNPJ")
        n_pais        = g8.text_input("País", value="Brasil")
        n_resp        = g9.text_input("Responsável interno")
        n_parceiro    = st.text_input("Parceiro relacionado")

        st.markdown("#### 📅 Vigência")
        v1,v2,v3 = st.columns(3)
        n_ass  = v1.date_input("Data assinatura", value=None)
        n_ini  = v2.date_input("Data início", value=None)
        n_term = v3.date_input("Data término", value=None)
        v4,v5,v6 = st.columns(3)
        n_aviso   = v4.number_input("Aviso prévio (dias)", min_value=0, step=1)
        n_ra      = v5.checkbox("Renovação automática")
        n_reaj    = v6.checkbox("Reajuste automático")
        n_indice  = st.selectbox("Índice de reajuste", ["—"] + INDICES)

        st.markdown("#### 💰 Financeiro")
        f1,f2,f3 = st.columns(3)
        n_vt    = f1.number_input("Valor total (R$)", min_value=0.0, step=0.01, format="%.2f")
        n_vrec  = f2.number_input("Valor recorrente/ano (R$)", min_value=0.0, step=0.01, format="%.2f")
        n_vam   = f3.number_input("Valor por amostra (R$)", min_value=0.0, step=0.01, format="%.2f")
        f4,f5,f6 = st.columns(3)
        n_moeda = f4.selectbox("Moeda", MOEDAS)
        n_pgto  = f5.selectbox("Forma de pagamento", ["—"] + PAGAMENTOS)
        n_com_p = f6.number_input("Comissão (%)", min_value=0.0, step=0.1, format="%.1f")

        st.markdown("#### 🧪 Amostras")
        a1,a2,a3,a4 = st.columns(4)
        n_am_ct = a1.number_input("Amostras contratadas", min_value=0, step=1)
        n_am_ut = a2.number_input("Amostras utilizadas",  min_value=0, step=1)
        n_am_bn = a3.number_input("Bônus amostras",       min_value=0, step=1)
        n_vexc  = a4.number_input("Valor excedente (R$/am)", min_value=0.0, step=0.01, format="%.2f")
        n_faixas = st.text_input("Faixas comerciais (ex: 0–100: R$700; 101+: R$600)")

        st.markdown("#### 🔒 Compliance")
        cp1,cp2,cp3,cp4,cp5,cp6 = st.columns(6)
        n_lgpd = cp1.checkbox("LGPD")
        n_conf = cp2.checkbox("Confidencial")
        n_nc   = cp3.checkbox("Não concorrência")
        n_pi   = cp4.checkbox("Prop. Intelectual")
        n_cd   = cp5.checkbox("Compart. dados")
        n_id   = cp6.checkbox("Internac. dados")

        st.markdown("#### ⚙️ Operacional")
        op1,op2,op3,op4 = st.columns(4)
        n_sla    = op1.number_input("SLA (dias)", min_value=0, step=1)
        n_pe     = op2.number_input("Prazo entrega (dias)", min_value=0, step=1)
        n_ta     = op3.text_input("Tipo de análise")
        n_plat   = op4.selectbox("Plataforma", ["—"] + PLATAFORMAS)
        n_obs    = st.text_area("Observações", height=70)
        n_obstech= st.text_area("Obs. técnicas", height=70)

        st.markdown("#### 🏷️ Flags")
        fl1,fl2,fl3,fl4,fl5 = st.columns(5)
        n_int = fl1.checkbox("Internacional")
        n_wl  = fl2.checkbox("White label")
        n_rec = fl3.checkbox("Recorrente")
        n_com = fl4.checkbox("Tem comissão")

        if st.form_submit_button("➕ Cadastrar Contrato", use_container_width=True):
            if n_contratante.strip() and n_empresa_gg:
                insert_contrato({
                    "contratante":            n_contratante.strip(),
                    "empresa_gg":             n_empresa_gg,
                    "cliente_id":             cli_map.get(n_cli),
                    "tipo_contrato":          n_tipo,
                    "categoria":              n_categoria,
                    "servico_principal":      n_servico or None,
                    "cnpj":                   n_cnpj or None,
                    "pais":                   n_pais or "Brasil",
                    "responsavel_interno":    n_resp or None,
                    "parceiro_relacionado":   n_parceiro or None,
                    "data_assinatura":        str(n_ass) if n_ass else None,
                    "data_inicio":            str(n_ini) if n_ini else None,
                    "data_termino":           str(n_term) if n_term else None,
                    "aviso_previo_dias":      int(n_aviso) if n_aviso else None,
                    "renovacao_automatica":   1 if n_ra else 0,
                    "reajuste_automatico":    1 if n_reaj else 0,
                    "indice_reajuste":        n_indice if n_indice != "—" else None,
                    "status":                 "ATIVO",
                    "moeda":                  n_moeda,
                    "valor_total":            float(n_vt),
                    "valor_recorrente":       float(n_vrec),
                    "valor_por_amostra":      float(n_vam),
                    "forma_pagamento":        n_pgto if n_pgto != "—" else None,
                    "comissao_percentual":    float(n_com_p),
                    "amostras_contratadas":   int(n_am_ct),
                    "amostras_utilizadas":    int(n_am_ut),
                    "amostras_bonus":         int(n_am_bn),
                    "valor_excedente":        float(n_vexc),
                    "faixas_comerciais":      n_faixas or None,
                    "lgpd":                   1 if n_lgpd else 0,
                    "confidencialidade":      1 if n_conf else 0,
                    "nao_concorrencia":       1 if n_nc else 0,
                    "propriedade_intelectual":1 if n_pi else 0,
                    "compartilhamento_dados": 1 if n_cd else 0,
                    "internacionalizacao_dados":1 if n_id else 0,
                    "sla_prazo_dias":         int(n_sla) if n_sla else None,
                    "prazo_entrega_dias":     int(n_pe) if n_pe else None,
                    "tipo_analise":           n_ta or None,
                    "plataforma_vinculada":   n_plat if n_plat != "—" else None,
                    "obs_tecnicas":           n_obstech or None,
                    "observacoes":            n_obs or None,
                    "internacional":          1 if n_int else 0,
                    "white_label":            1 if n_wl else 0,
                    "recorrente":             1 if n_rec else 0,
                    "tem_comissao":           1 if n_com else 0,
                })
                st.success(f"✅ Contrato com **{n_contratante}** cadastrado!")
                st.rerun()
            else:
                st.error("Contratante e Empresa são obrigatórios.")

# ══════════════════════════════════════════════════════════════════════════════
# ADITIVOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_aditivos:
    todos_ct2 = list_contratos()
    opts_ad   = {f"{c['contratante']} ({c['empresa_gg']})": c["id"] for c in todos_ct2}

    sel_ad = st.selectbox("Selecione o contrato", ["— Selecione —"] + list(opts_ad.keys()))

    if sel_ad != "— Selecione —":
        cid_ad = opts_ad[sel_ad]
        ct_ad  = get_contrato(cid_ad)
        st.markdown(f"**{ct_ad['contratante']}** · {ct_ad['empresa_gg']} · {ct_ad.get('tipo_contrato','—')}")

        aditivos = list_aditivos(cid_ad)
        if aditivos:
            st.markdown(f"**{len(aditivos)} aditivo(s)**")
            for ad in aditivos:
                with st.expander(f"Aditivo #{ad['numero_aditivo']} — {ad.get('tipo','—')} — {ad.get('data','—')}"):
                    st.write(ad.get("descricao","—"))
                    if ad.get("valor_anterior") is not None:
                        ac1,ac2 = st.columns(2)
                        ac1.metric("Valor anterior", brl(ad["valor_anterior"]))
                        ac2.metric("Valor novo",     brl(ad["valor_novo"] or 0))
                    if ad.get("data_termino_novo"):
                        st.markdown(f"**Nova data de término:** {ad['data_termino_novo']}")
                    if ad.get("responsavel"):
                        st.caption(f"Responsável: {ad['responsavel']}")
                    if st.button("🗑️ Remover", key=f"del_ad_{ad['id']}"):
                        delete_aditivo(ad["id"])
                        st.rerun()
        else:
            st.info("Nenhum aditivo registrado para este contrato.")

        st.markdown("---")
        st.markdown("**Registrar novo aditivo**")
        with st.form(f"form_aditivo_{cid_ad}", clear_on_submit=True):
            prox_num = len(aditivos) + 1
            ad1,ad2,ad3 = st.columns(3)
            ad_num  = ad1.number_input("Nº aditivo", value=prox_num, min_value=1, step=1)
            ad_data = ad2.date_input("Data")
            ad_tipo = ad3.selectbox("Tipo", ["REAJUSTE","EXTENSÃO DE VIGÊNCIA","NOVO VALOR","NOVOS SERVIÇOS","OUTRO"])
            ad_desc = st.text_area("Descrição")
            adv1,adv2 = st.columns(2)
            ad_vant = adv1.number_input("Valor anterior (R$)", min_value=0.0, step=0.01, format="%.2f")
            ad_vnov = adv2.number_input("Valor novo (R$)",     min_value=0.0, step=0.01, format="%.2f")
            adt1,adt2 = st.columns(2)
            ad_tant = adt1.text_input("Data término anterior")
            ad_tnov = adt2.text_input("Nova data término")
            ad_resp = st.text_input("Responsável")

            if st.form_submit_button("📎 Registrar Aditivo", use_container_width=True):
                insert_aditivo({
                    "contrato_id":           cid_ad,
                    "numero_aditivo":        int(ad_num),
                    "data":                  str(ad_data),
                    "tipo":                  ad_tipo,
                    "descricao":             ad_desc or None,
                    "valor_anterior":        float(ad_vant) if ad_vant else None,
                    "valor_novo":            float(ad_vnov) if ad_vnov else None,
                    "data_termino_anterior": ad_tant or None,
                    "data_termino_novo":     ad_tnov or None,
                    "responsavel":           ad_resp or None,
                })
                if ad_vnov:
                    update_contrato(cid_ad, {"valor_total": float(ad_vnov)})
                if ad_tnov:
                    update_contrato(cid_ad, {"data_termino": ad_tnov})
                st.success("✅ Aditivo registrado e contrato atualizado!")
                st.rerun()
