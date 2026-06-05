"""Página 6 — Sistema de Créditos de Clientes."""
import io
import streamlit as st
import pandas as pd
import plotly.express as px
from collections import defaultdict
from datetime import date, timedelta
from openpyxl import Workbook
from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                              numbers as xl_numbers)
from openpyxl.utils import get_column_letter

from utils import GLOBAL_CSS, brl, status_badge, sidebar_header, require_auth
from db_contratos import list_contratos as _list_contratos_all
from db_creditos import (
    list_clientes, insert_cliente, update_cliente, delete_cliente,
    list_notas, insert_nota, delete_nota,
    list_creditos, insert_credito, update_credito, delete_credito,
    list_movimentacoes, insert_movimentacao,
)

st.set_page_config(page_title="Créditos | GoGenetic", page_icon="💳", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()
require_auth()

st.markdown("""
<p class="page-title">💳 Créditos de Clientes</p>
<p class="page-sub">Gestão completa de créditos · Grupo GoGenetic</p>
""", unsafe_allow_html=True)

# ── Carrega TUDO + constrói índices dentro do cache (executado UMA vez) ───────
@st.cache_data(ttl=600, show_spinner="⏳ Carregando créditos…")
def _load_all():
    """Carrega 4 tabelas em paralelo e pré-constrói todos os índices."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_cli  = ex.submit(list_clientes)
        f_cred = ex.submit(list_creditos)
        f_nota = ex.submit(list_notas)
        f_movs = ex.submit(list_movimentacoes)
    clientes = f_cli.result()
    creditos = f_cred.result()
    notas    = f_nota.result()
    movs     = f_movs.result()

    # Índices — construídos aqui, reutilizados em todos os reruns
    cred_by_cli = defaultdict(list)
    for c in creditos:
        cred_by_cli[c["cliente_id"]].append(c)

    nota_by_cli = defaultdict(list)
    for n in notas:
        nota_by_cli[n["cliente_id"]].append(n)

    cred_map = {
        c["id"]: {"cliente_id": c["cliente_id"],
                  "cliente_nome": c.get("cliente_nome",""),
                  "valor_original": c.get("valor_original", 0)}
        for c in creditos
    }
    cred_to_cli = {cid: v["cliente_id"] for cid, v in cred_map.items()}

    # Enriquece movs com cliente_nome sem join no banco
    for m in movs:
        info = cred_map.get(m.get("credito_id"), {})
        if not m.get("cliente_nome"):
            m["cliente_nome"]   = info.get("cliente_nome", "")
        if "valor_original" not in m:
            m["valor_original"] = info.get("valor_original", 0)

    mov_by_cli = defaultdict(list)
    for m in movs:
        cli_id = cred_to_cli.get(m.get("credito_id"))
        if cli_id:
            mov_by_cli[cli_id].append(m)

    return {
        "clientes":    clientes,
        "creditos":    creditos,
        "notas":       notas,
        "movs":        movs,
        "cred_by_cli": cred_by_cli,
        "nota_by_cli": nota_by_cli,
        "mov_by_cli":  mov_by_cli,
        "cred_to_cli": cred_to_cli,
        "cred_map":    cred_map,
    }

@st.cache_data(ttl=600, show_spinner=False)
def _load_contratos():
    """Carrega contratos sob demanda (usado apenas no detalhe do cliente)."""
    contratos = _list_contratos_all()
    idx = defaultdict(list)
    for ct in contratos:
        if ct.get("cliente_id"):
            idx[ct["cliente_id"]].append(ct)
    return idx

def _clear_and_rerun():
    _load_all.clear()
    _load_contratos.clear()
    st.rerun()

_data        = _load_all()
clientes_all = _data["clientes"]
creditos_all = _data["creditos"]
notas_all    = _data["notas"]
movs_all     = _data["movs"]
_cred_by_cli = _data["cred_by_cli"]
_nota_by_cli = _data["nota_by_cli"]
_mov_by_cli  = _data["mov_by_cli"]
_cred_to_cli = _data["cred_to_cli"]
_cred_map    = _data["cred_map"]

def _get_cont_by_cli():
    return _load_contratos()

def _resumo_mem(cli_id: int) -> dict:
    """Resumo do cliente — lê direto dos índices já em cache."""
    creds  = _cred_by_cli.get(cli_id, [])
    notas_ = _nota_by_cli.get(cli_id, [])
    valid  = [c for c in creds if c["status"] == "VÁLIDO"]
    expir  = [c for c in creds if c["status"] == "EXPIRADO"]
    saldo  = lambda lst: sum((c.get("valor_original") or 0) - (c.get("valor_utilizado") or 0) for c in lst)
    return {
        "qtd_validos":     len(valid),
        "qtd_expirados":   len(expir),
        "saldo_valido":    saldo(valid),
        "saldo_expirado":  saldo(expir),
        "total_utilizado": sum(c.get("valor_utilizado") or 0 for c in creds),
        "qtd_notas":       len(notas_),
    }

# ── Tabs principais ───────────────────────────────────────────────────────────
tab_dash, tab_clientes, tab_creditos, tab_movs, tab_relatorio = st.tabs([
    "📊 Painel", "🧑‍🤝‍🧑 Clientes", "💳 Créditos", "📋 Movimentações", "📑 Relatório Mensal"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PAINEL
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    df = pd.DataFrame(creditos_all) if creditos_all else pd.DataFrame()

    if not df.empty:
        df["valor_original"]  = pd.to_numeric(df["valor_original"],  errors="coerce").fillna(0)
        df["valor_utilizado"] = pd.to_numeric(df["valor_utilizado"], errors="coerce").fillna(0)
        df["saldo"]           = df["valor_original"] - df["valor_utilizado"]
        df["data_vencimento"] = pd.to_datetime(df["data_vencimento"], errors="coerce")

        hoje        = pd.Timestamp.today().normalize()
        df_validos  = df[df["status"] == "VÁLIDO"]
        df_expirad  = df[df["status"] == "EXPIRADO"]
        df_venc30   = df_validos[df_validos["data_vencimento"] <= hoje + timedelta(days=30)]
        df_venc7    = df_validos[df_validos["data_vencimento"] <= hoje + timedelta(days=7)]
    else:
        df_validos = df_expirad = df_venc30 = df_venc7 = pd.DataFrame()
        hoje = pd.Timestamp.today().normalize()

    k1, k2, k3, k4, k5 = st.columns(5)
    def _kpi(col, icon, label, valor, sub="", cor="#1A0A2E"):
        col.markdown(f"""
        <div style='background:#fff;border-radius:12px;padding:16px 20px;
                    box-shadow:0 2px 8px rgba(126,22,184,0.08)'>
          <div style='font-size:.72rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{icon} {label}</div>
          <div style='font-size:1.3rem;font-weight:800;color:{cor}'>{valor}</div>
          <div style='font-size:.78rem;color:#6B7280'>{sub}</div>
        </div>""", unsafe_allow_html=True)

    _kpi(k1,"💚","Saldo Válido",   brl(df_validos["saldo"].sum() if not df_validos.empty else 0),
         f"{len(df_validos)} crédito(s)", "#10B981")
    _kpi(k2,"❌","Total Expirado", brl(df_expirad["saldo"].sum() if not df_expirad.empty else 0),
         f"{len(df_expirad)} crédito(s)", "#EF4444")
    _kpi(k3,"⚠️","Vencendo 30d",  brl(df_venc30["saldo"].sum() if not df_venc30.empty else 0),
         f"{len(df_venc30)} crédito(s)", "#F59E0B")
    _kpi(k4,"🚨","Vencendo 7d",   brl(df_venc7["saldo"].sum() if not df_venc7.empty else 0),
         f"{len(df_venc7)} crédito(s)", "#EF4444" if not df_venc7.empty else "#6B7280")
    _kpi(k5,"👥","Clientes",      str(len(clientes_all)), "cadastrados")

    st.markdown("<br>", unsafe_allow_html=True)

    # Alertas
    if not df_venc7.empty:
        st.markdown("#### 🚨 Vencendo nos próximos 7 dias")
        for _, row in df_venc7.iterrows():
            dias = int((row["data_vencimento"] - hoje).days)
            st.markdown(f"""
            <div style='background:#FFF5F5;border-left:4px solid #EF4444;border-radius:8px;
                        padding:10px 16px;margin-bottom:6px;display:flex;justify-content:space-between'>
              <div><b>{row.get('cliente_nome','—')}</b>
                <span style='color:#8B6BAE;font-size:.85rem;margin-left:10px'>
                  NF {row.get('numero_nf','—')} · Vence em {dias} dia{'s' if dias != 1 else ''}
                </span></div>
              <b style='color:#EF4444'>{brl(row['saldo'])}</b>
            </div>""", unsafe_allow_html=True)

    elif not df_venc30.empty:
        st.markdown("#### ⚠️ Vencendo em até 30 dias")
        for _, row in df_venc30.iterrows():
            dias = int((row["data_vencimento"] - hoje).days)
            st.markdown(f"""
            <div style='background:#FFFBEB;border-left:4px solid #F59E0B;border-radius:8px;
                        padding:10px 16px;margin-bottom:6px;display:flex;justify-content:space-between'>
              <div><b>{row.get('cliente_nome','—')}</b>
                <span style='color:#8B6BAE;font-size:.85rem;margin-left:10px'>
                  NF {row.get('numero_nf','—')} · {dias} dias
                </span></div>
              <b style='color:#F59E0B'>{brl(row['saldo'])}</b>
            </div>""", unsafe_allow_html=True)

    # Gráficos
    if not df.empty:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Top 10 Clientes — Saldo válido**")
            if not df_validos.empty:
                top = df_validos.groupby("cliente_nome")["saldo"].sum().reset_index()
                top = top.sort_values("saldo", ascending=False).head(10)
                fig = px.bar(top, x="saldo", y="cliente_nome", orientation="h",
                             color_discrete_sequence=["#7E16B8"],
                             labels={"saldo": "Saldo (R$)", "cliente_nome": ""})
                fig.update_layout(yaxis=dict(autorange="reversed"),
                                  plot_bgcolor="#fff", paper_bgcolor="#fff",
                                  margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)
        with g2:
            st.markdown("**Distribuição por Status**")
            ds = df.groupby("status")["saldo"].sum().reset_index()
            cores = {"VÁLIDO":"#10B981","EXPIRADO":"#EF4444","UTILIZADO":"#6B7280","CANCELADO":"#F59E0B"}
            fig2 = px.pie(ds, names="status", values="saldo",
                          color="status", color_discrete_map=cores, hole=0.4)
            fig2.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff",
                               margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CLIENTES
# ══════════════════════════════════════════════════════════════════════════════
with tab_clientes:
    cli_opts = {c["nome"]: c["id"] for c in clientes_all}

    col1, col2 = st.columns([3, 1])
    busca = col1.text_input("🔎 Buscar cliente")
    if col2.button("➕ Novo Cliente", use_container_width=True):
        st.session_state["_cred_novo_cli"] = True

    if st.session_state.get("_cred_novo_cli"):
        with st.form("form_novo_cli_dash", clear_on_submit=True):
            st.markdown("**Novo cliente**")
            c1, c2 = st.columns(2)
            nome  = c1.text_input("Nome *")
            email = c2.text_input("Email")
            obs   = st.text_area("Observações", height=60)
            s1, s2 = st.columns(2)
            if s1.form_submit_button("✅ Salvar", use_container_width=True):
                if nome.strip():
                    insert_cliente({"nome": nome.strip(), "email": email or None, "observacoes": obs or None})
                    st.session_state["_cred_novo_cli"] = False
                    st.success(f"✅ {nome} cadastrado!")
                    _clear_and_rerun()
                else:
                    st.error("Nome é obrigatório.")
            if s2.form_submit_button("❌ Cancelar", use_container_width=True):
                st.session_state["_cred_novo_cli"] = False
                st.rerun()

    lista = [c for c in clientes_all if not busca or busca.lower() in c["nome"].lower()]

    if not lista:
        st.info("Nenhum cliente encontrado.")
    else:
        hoje_ts = pd.Timestamp.today().normalize()

        # ── Tabela resumo (leve — sem expanders por cliente) ──────────────────
        rows_tab = []
        for cli in lista:
            res = _resumo_mem(cli["id"])
            rows_tab.append({
                "Cliente":      cli["nome"],
                "Saldo Válido": res.get("saldo_valido", 0),
                "Créditos ✅":  res.get("qtd_validos", 0),
                "Créditos ❌":  res.get("qtd_expirados", 0),
                "Utilizado":    res.get("total_utilizado", 0),
                "_id":          cli["id"],
            })
        df_clientes = pd.DataFrame(rows_tab)
        df_show_cli = df_clientes.drop(columns=["_id"]).copy()
        df_show_cli["Saldo Válido"] = df_show_cli["Saldo Válido"].apply(brl)
        df_show_cli["Utilizado"]    = df_show_cli["Utilizado"].apply(brl)
        st.dataframe(df_show_cli, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Detalhe de UM cliente (seleção) ───────────────────────────────────
        nomes_lista = [c["nome"] for c in lista]
        cli_sel_nome = st.selectbox("👤 Ver detalhe do cliente:", nomes_lista, key="cli_det_sel")
        cli = next(c for c in lista if c["nome"] == cli_sel_nome)
        res = _resumo_mem(cli["id"])

        k1c, k2c, k3c, k4c = st.columns(4)
        k1c.metric("Créditos válidos",   res.get("qtd_validos", 0))
        k2c.metric("Créditos expirados", res.get("qtd_expirados", 0))
        k3c.metric("Saldo válido",        brl(res.get("saldo_valido", 0)))
        k4c.metric("Total utilizado",     brl(res.get("total_utilizado", 0)))

        sub1, sub2, sub3, sub4 = st.tabs(["💳 Créditos", "📄 Notas Fiscais", "📋 Movimentações", "📑 Contratos"])

        creds_cli     = _cred_by_cli.get(cli["id"], [])
        notas_cli     = _nota_by_cli.get(cli["id"], [])
        movs_cli      = _mov_by_cli.get(cli["id"], [])

        with sub1:
            if not creds_cli:
                st.info("Sem créditos.")
            else:
                for cr in creds_cli:
                    saldo_cr = (cr["valor_original"] or 0) - (cr["valor_utilizado"] or 0)
                    venc = pd.to_datetime(cr["data_vencimento"], errors="coerce")
                    dias = int((venc - hoje_ts).days) if pd.notna(venc) else None
                    alerta = ""
                    if cr["status"] == "VÁLIDO" and dias is not None:
                        alerta = "🔴 " if dias <= 7 else ("🟡 " if dias <= 30 else "🟢 ")
                    nf_label = f"NF {cr.get('numero_nf','—')}"
                    with st.expander(f"{alerta}{nf_label}  ·  {brl(saldo_cr)}  ·  {cr['status']}"):
                        ca, cb, cc = st.columns(3)
                        ca.metric("Original",  brl(cr["valor_original"]))
                        cb.metric("Utilizado", brl(cr["valor_utilizado"]))
                        cc.metric("Saldo",     brl(saldo_cr))
                        if dias is not None:
                            st.caption(f"Vencimento: {venc.strftime('%d/%m/%Y')} · {dias} dias")
                        if cr["status"] == "VÁLIDO" and saldo_cr > 0:
                            with st.form(f"cons_dash_{cr['id']}", clear_on_submit=True):
                                v = st.number_input("Valor a consumir", min_value=0.01,
                                                    max_value=float(saldo_cr), step=0.01, format="%.2f",
                                                    key=f"v_cons_{cr['id']}")
                                resp = st.text_input("Responsável", key=f"resp_{cr['id']}")
                                if st.form_submit_button("💸 Registrar consumo", use_container_width=True):
                                    novo_ut = (cr["valor_utilizado"] or 0) + v
                                    novo_st = "UTILIZADO" if (cr["valor_original"] - novo_ut) <= 0 else "VÁLIDO"
                                    update_credito(cr["id"], {"valor_utilizado": novo_ut, "status": novo_st})
                                    insert_movimentacao({"credito_id": cr["id"], "tipo": "UTILIZAÇÃO",
                                                         "valor": float(v), "data": str(date.today()),
                                                         "responsavel": resp or None})
                                    st.success(f"✅ {brl(v)} consumido!")
                                    _clear_and_rerun()

        with sub2:
            if notas_cli:
                for nf in notas_cli:
                    cols = st.columns([3, 2, 2, 1])
                    cols[0].markdown(f"**NF {nf['numero_nf']}**")
                    cols[1].markdown(nf.get("data_emissao") or "—")
                    cols[2].markdown(brl(nf["valor_total"]))
                    if cols[3].button("🗑️", key=f"del_nf_dash_{nf['id']}"):
                        delete_nota(nf["id"])
                        _clear_and_rerun()
            with st.form(f"nova_nf_dash_{cli['id']}", clear_on_submit=True):
                st.caption("Nova NF")
                n1, n2 = st.columns(2)
                num_nf   = n1.text_input("Número NF")
                valor_nf = n2.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f")
                data_em  = n1.date_input("Data emissão")
                auto_cred = n2.checkbox("Criar crédito automaticamente", value=True)
                venc_nf = None
                if auto_cred:
                    venc_nf = st.date_input("Vencimento do crédito")
                if st.form_submit_button("➕ Cadastrar NF", use_container_width=True):
                    if num_nf.strip():
                        nf_id = insert_nota({"numero_nf": num_nf.strip(), "cliente_id": cli["id"],
                                              "data_emissao": str(data_em), "valor_total": float(valor_nf)})
                        if auto_cred and valor_nf > 0:
                            insert_credito({"cliente_id": cli["id"], "nota_fiscal_id": nf_id,
                                            "valor_original": float(valor_nf),
                                            "data_vencimento": str(venc_nf) if venc_nf else None})
                        st.success(f"✅ NF {num_nf} cadastrada!")
                        _clear_and_rerun()

        with sub3:
            if not movs_cli:
                st.info("Sem movimentações.")
            else:
                df_m = pd.DataFrame(movs_cli)
                for col_opt in ["descricao_servico","codigo_servico","qtd_amostras","valor_amostra"]:
                    if col_opt not in df_m.columns:
                        df_m[col_opt] = None
                cols_show = ["data","tipo","descricao_servico","codigo_servico",
                             "qtd_amostras","valor_amostra","valor","responsavel","observacao"]
                df_show = df_m[[c for c in cols_show if c in df_m.columns]].copy()
                df_show["valor"] = pd.to_numeric(df_show["valor"], errors="coerce").fillna(0).apply(brl)
                if "valor_amostra" in df_show.columns:
                    df_show["valor_amostra"] = df_show["valor_amostra"].apply(
                        lambda v: brl(v) if pd.notna(v) and v else "—")
                if "qtd_amostras" in df_show.columns:
                    df_show["qtd_amostras"] = df_show["qtd_amostras"].apply(
                        lambda v: str(int(v)) if pd.notna(v) and v else "—")
                rename = {"data":"Data","tipo":"Tipo","descricao_servico":"Serviço",
                          "codigo_servico":"Cód.","qtd_amostras":"Amostras",
                          "valor_amostra":"Vl/Amostra","valor":"Total",
                          "responsavel":"Responsável","observacao":"Obs."}
                df_show.rename(columns=rename, inplace=True)
                st.dataframe(df_show.fillna("—"), use_container_width=True, hide_index=True)

        with sub4:
            contratos_cli = _get_cont_by_cli().get(cli["id"], [])
            if not contratos_cli:
                st.info("Nenhum contrato vinculado a este cliente.")
                st.caption("Para vincular, edite um contrato na página 📑 Contratos.")
            else:
                for ct in contratos_cli:
                    venc_c = pd.to_datetime(ct.get("data_termino"), errors="coerce")
                    dias_c = int((venc_c - hoje_ts).days) if pd.notna(venc_c) else None
                    cor_c  = "#EF4444" if (dias_c is not None and dias_c < 0) else \
                             "#F59E0B" if (dias_c is not None and dias_c <= 30) else "#10B981"
                    venc_s = venc_c.strftime("%d/%m/%Y") if pd.notna(venc_c) else "—"
                    st.markdown(f"""
                    <div style='background:#fff;border-radius:8px;padding:12px 16px;
                                margin-bottom:8px;border-left:4px solid {cor_c};
                                box-shadow:0 1px 4px rgba(0,0,0,0.06)'>
                      <div style='font-weight:700'>{ct.get('contratante','—')}
                        <span style='font-size:.8rem;color:#8B6BAE;margin-left:8px'>{ct.get('empresa_gg','')}</span>
                      </div>
                      <div style='font-size:.85rem;color:#4B5563;margin-top:4px'>
                        Valor: <b>{brl(ct.get('valor_total'))}</b> &nbsp;·&nbsp;
                        Vencimento: <b>{venc_s}</b>
                        {f" · <b style='color:{cor_c}'>{dias_c}d</b>" if dias_c is not None else ""}
                      </div>
                    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CRÉDITOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_creditos:
    cli_opts = {c["nome"]: c["id"] for c in clientes_all}

    col1, col2 = st.columns(2)
    status_sel = col1.multiselect("Status", ["VÁLIDO","EXPIRADO","UTILIZADO","CANCELADO"],
                                   default=["VÁLIDO"])
    cli_f    = col2.selectbox("Cliente", ["Todos"] + list(cli_opts.keys()), key="cli_f_cred")
    cli_id_f = cli_opts.get(cli_f) if cli_f != "Todos" else None

    lista_tab, novo_tab, consumo_tab = st.tabs(["📋 Lista", "➕ Novo Crédito", "💸 Registrar Consumo"])

    with lista_tab:
        # Filter in memory
        creds_tab = creditos_all
        if status_sel:
            creds_tab = [c for c in creds_tab if c["status"] in status_sel]
        if cli_id_f:
            creds_tab = [c for c in creds_tab if c["cliente_id"] == cli_id_f]

        if not creds_tab:
            st.info("Nenhum crédito encontrado.")
        else:
            hoje3 = pd.Timestamp.today().normalize()
            total_saldo = sum((c.get("valor_original") or 0) - (c.get("valor_utilizado") or 0) for c in creds_tab)
            st.markdown(f"**{len(creds_tab)} crédito(s) — Saldo total: {brl(total_saldo)}**")

            # Tabela leve — sem expanders por linha
            rows_cr = []
            for cr in creds_tab:
                saldo = (cr.get("valor_original") or 0) - (cr.get("valor_utilizado") or 0)
                venc  = pd.to_datetime(cr.get("data_vencimento"), errors="coerce")
                dias  = int((venc - hoje3).days) if pd.notna(venc) else None
                alerta = ""
                if cr["status"] == "VÁLIDO" and dias is not None:
                    alerta = "🔴 " if dias <= 7 else ("🟡 " if dias <= 30 else "🟢 ")
                rows_cr.append({
                    "":          alerta,
                    "Cliente":   cr.get("cliente_nome","—"),
                    "NF":        cr.get("numero_nf","—"),
                    "Original":  cr.get("valor_original", 0),
                    "Utilizado": cr.get("valor_utilizado", 0),
                    "Saldo":     saldo,
                    "Vencimento": venc.strftime("%d/%m/%Y") if pd.notna(venc) else "—",
                    "Status":    cr["status"],
                    "_id":       cr["id"],
                })
            df_creds_tab = pd.DataFrame(rows_cr)
            df_creds_show = df_creds_tab.drop(columns=["_id"]).copy()
            for col_brl in ["Original","Utilizado","Saldo"]:
                df_creds_show[col_brl] = df_creds_show[col_brl].apply(brl)
            st.dataframe(df_creds_show, use_container_width=True, hide_index=True)

            # Expirar crédito individual
            with st.expander("⏰ Expirar um crédito manualmente"):
                validos_tab = [cr for cr in creds_tab if cr["status"] == "VÁLIDO"]
                if validos_tab:
                    opts_exp = {
                        f"{cr.get('cliente_nome','?')} — NF {cr.get('numero_nf','—')}": cr["id"]
                        for cr in validos_tab
                    }
                    sel_exp = st.selectbox("Crédito:", list(opts_exp.keys()), key="sel_exp")
                    if st.button("⏰ Confirmar expiração", key="btn_exp"):
                        update_credito(opts_exp[sel_exp], {"status": "EXPIRADO"})
                        _clear_and_rerun()
                else:
                    st.info("Nenhum crédito válido para expirar.")

    with novo_tab:
        if not clientes_all:
            st.warning("Cadastre um cliente primeiro.")
        else:
            with st.form("form_novo_cred_dash", clear_on_submit=True):
                cli_sel  = st.selectbox("Cliente *", list(cli_opts.keys()))
                notas_cl = _nota_by_cli.get(cli_opts.get(cli_sel), [])
                nf_opts  = {"— Sem NF —": None}
                nf_opts.update({f"NF {n['numero_nf']}": n["id"] for n in notas_cl})
                c1, c2  = st.columns(2)
                nf_sel  = c1.selectbox("NF vinculada", list(nf_opts.keys()))
                valor   = c2.number_input("Valor (R$) *", min_value=0.01, step=0.01, format="%.2f")
                venc    = c1.date_input("Vencimento *")
                obs     = c2.text_area("Observações", height=80)
                if st.form_submit_button("➕ Cadastrar", use_container_width=True):
                    insert_credito({"cliente_id": cli_opts[cli_sel], "nota_fiscal_id": nf_opts[nf_sel],
                                    "valor_original": float(valor), "data_vencimento": str(venc),
                                    "observacoes": obs or None})
                    st.success("✅ Crédito cadastrado!")
                    _clear_and_rerun()

    with consumo_tab:
        creds_validos = [c for c in creditos_all if c["status"] == "VÁLIDO"]
        if not creds_validos:
            st.info("Nenhum crédito válido disponível.")
        else:
            opts = {
                f"{c.get('cliente_nome','?')} — NF {c.get('numero_nf','—')} — Saldo: {brl((c['valor_original'] or 0)-(c['valor_utilizado'] or 0))}": c
                for c in creds_validos
            }
            with st.form("form_consumo_dash", clear_on_submit=True):
                label   = st.selectbox("Crédito *", list(opts.keys()))
                cr      = opts[label]
                saldo_d = (cr["valor_original"] or 0) - (cr["valor_utilizado"] or 0)

                st.markdown(f"**Saldo disponível: {brl(saldo_d)}**")
                st.markdown("---")

                ca, cb = st.columns(2)
                desc_serv = ca.text_input("Descrição do serviço *", placeholder="ex: Microbioma 1 alvo")
                cod_serv  = cb.text_input("Código do serviço", placeholder="ex: S5990")

                cc, cd, ce = st.columns(3)
                qtd_am    = cc.number_input("Qtd amostras", min_value=0, step=1, value=0)
                vl_am     = cd.number_input("Valor / amostra (R$)", min_value=0.0, step=0.01, format="%.2f", value=0.0)
                data_serv = ce.date_input("Data do serviço", value=date.today())

                total_calc = qtd_am * vl_am if qtd_am > 0 and vl_am > 0 else 0.0
                if total_calc > 0:
                    st.info(f"💡 Total calculado: **{brl(total_calc)}** ({qtd_am} amostras × {brl(vl_am)})")
                    v_uso_default = min(total_calc, saldo_d)
                else:
                    v_uso_default = 0.01

                cf, cg = st.columns(2)
                v_uso = cf.number_input(
                    "Valor total consumido (R$) *",
                    min_value=0.01, max_value=float(saldo_d),
                    step=0.01, format="%.2f",
                    value=float(min(v_uso_default, saldo_d)) if v_uso_default > 0 else 0.01,
                )
                resp  = cg.text_input("Responsável")
                obs_u = st.text_area("Observação", height=60)

                if st.form_submit_button("💸 Registrar Consumo", use_container_width=True):
                    if not desc_serv.strip():
                        st.error("Informe a descrição do serviço.")
                    else:
                        novo_ut = (cr["valor_utilizado"] or 0) + v_uso
                        novo_st = "UTILIZADO" if (cr["valor_original"] - novo_ut) <= 0 else "VÁLIDO"
                        update_credito(cr["id"], {"valor_utilizado": novo_ut, "status": novo_st})
                        insert_movimentacao({
                            "credito_id":        cr["id"],
                            "tipo":              "UTILIZAÇÃO",
                            "valor":             float(v_uso),
                            "data":              str(data_serv),
                            "responsavel":       resp or None,
                            "observacao":        obs_u or None,
                            "descricao_servico": desc_serv.strip(),
                            "codigo_servico":    cod_serv.strip() or None,
                            "qtd_amostras":      int(qtd_am) if qtd_am > 0 else None,
                            "valor_amostra":     float(vl_am) if vl_am > 0 else None,
                        })
                        st.success(f"✅ Consumo de {brl(v_uso)} registrado!")
                        _clear_and_rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MOVIMENTAÇÕES
# ══════════════════════════════════════════════════════════════════════════════
with tab_movs:
    import io
    cli_opts = {c["nome"]: c["id"] for c in clientes_all}

    col1, col2, col3 = st.columns(3)
    tipo_f = col1.multiselect("Tipo", ["UTILIZAÇÃO","ESTORNO","AJUSTE"],
                               default=["UTILIZAÇÃO","ESTORNO","AJUSTE"])
    cli_f2 = col2.selectbox("Cliente", ["Todos"] + list(cli_opts.keys()), key="cli_f_movs")
    busca2 = col3.text_input("🔎 Buscar responsável")

    cli_id_f2 = cli_opts.get(cli_f2) if cli_f2 != "Todos" else None

    # Filter in memory
    movs_tab = movs_all
    if cli_id_f2:
        movs_tab = [m for m in movs_tab if _cred_to_cli.get(m.get("credito_id")) == cli_id_f2]

    if not movs_tab:
        st.info("Nenhuma movimentação registrada.")
    else:
        df_m = pd.DataFrame(movs_tab)
        df_m["valor"] = pd.to_numeric(df_m["valor"], errors="coerce").fillna(0)
        df_m["data"]  = pd.to_datetime(df_m["data"], errors="coerce")
        if tipo_f:
            df_m = df_m[df_m["tipo"].isin(tipo_f)]
        if busca2:
            df_m = df_m[df_m["responsavel"].fillna("").str.contains(busca2, case=False)]

        st.markdown(f"**{len(df_m)} movimentação(ões) — Total: {brl(df_m['valor'].sum())}**")

        for col_opt in ["descricao_servico","codigo_servico","qtd_amostras","valor_amostra"]:
            if col_opt not in df_m.columns:
                df_m[col_opt] = None

        df_show = df_m[["data","tipo","cliente_nome","descricao_servico","codigo_servico",
                         "qtd_amostras","valor_amostra","valor","responsavel","observacao"]].copy()
        df_show["data"]          = df_show["data"].dt.strftime("%d/%m/%Y")
        df_show["valor"]         = df_show["valor"].apply(brl)
        df_show["valor_amostra"] = df_show["valor_amostra"].apply(
            lambda v: brl(v) if pd.notna(v) and v else "—")
        df_show["qtd_amostras"]  = df_show["qtd_amostras"].apply(
            lambda v: str(int(v)) if pd.notna(v) and v else "—")
        df_show.columns = ["Data","Tipo","Cliente","Serviço","Cód.","Amostras","Vl/Amostra","Total","Responsável","Obs."]
        st.dataframe(df_show.fillna("—"), use_container_width=True, hide_index=True)

        if st.button("📥 Exportar Excel", key="btn_export_movs"):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df_show.to_excel(writer, index=False, sheet_name="Movimentações")
            st.download_button("⬇️ Baixar movimentacoes.xlsx", data=buf.getvalue(),
                               file_name="movimentacoes.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="dl_movs")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — RELATÓRIO MENSAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_relatorio:
    from utils import MESES_PT

    hoje_r  = date.today()
    col_a, col_b, col_c = st.columns([2, 2, 4])
    ano_r = col_a.selectbox("Ano", list(range(hoje_r.year, hoje_r.year - 4, -1)), key="rel_ano")
    mes_r = col_b.selectbox("Mês", list(range(1, 13)),
                             format_func=lambda m: MESES_PT[m],
                             index=hoje_r.month - 1, key="rel_mes")

    mes_ini = date(ano_r, mes_r, 1)
    mes_fim_day = (date(ano_r, mes_r % 12 + 1, 1) - timedelta(days=1)).day if mes_r < 12 else 31
    mes_fim = date(ano_r, mes_r, mes_fim_day)
    ini_s = mes_ini.strftime("%Y-%m-%d")
    fim_s = mes_fim.strftime("%Y-%m-%d")
    mes_label = f"{MESES_PT[mes_r]} {ano_r}"

    st.markdown(f"<br>", unsafe_allow_html=True)

    # ── Dados do mês ──────────────────────────────────────────────────────────
    # Movimentações do mês
    movs_mes = [
        m for m in movs_all
        if ini_s <= (m.get("data") or "")[:10] <= fim_s
    ]

    # Créditos criados no mês (notas emitidas no mês)
    notas_mes = [
        n for n in notas_all
        if ini_s <= (n.get("data_emissao") or "")[:10] <= fim_s
    ]
    creds_novos = [
        c for c in creditos_all
        if any(n["id"] == c.get("nota_fiscal_id") for n in notas_mes)
    ]

    # Créditos vencidos no mês
    creds_vencidos = [
        c for c in creditos_all
        if ini_s <= (c.get("data_vencimento") or "")[:10] <= fim_s
        and c["status"] in ("EXPIRADO", "UTILIZADO")
    ]

    # Saldo ativo ao fim do mês
    creds_ativos = [c for c in creditos_all if c["status"] == "VÁLIDO"]
    saldo_ativo  = sum((c.get("valor_original") or 0) - (c.get("valor_utilizado") or 0)
                       for c in creds_ativos)

    total_consumido = sum(float(m.get("valor") or 0) for m in movs_mes
                          if m.get("tipo") in ("UTILIZAÇÃO", "USO"))
    total_novos     = sum(float(c.get("valor_original") or 0) for c in creds_novos)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    def _kpi_r(col, icon, label, val, sub="", cor="#1A0A2E"):
        col.markdown(f"""
        <div style='background:#fff;border-radius:12px;padding:16px 20px;
                    box-shadow:0 2px 8px rgba(126,22,184,0.08)'>
          <div style='font-size:.72rem;color:#8B6BAE;text-transform:uppercase;letter-spacing:1px'>{icon} {label}</div>
          <div style='font-size:1.25rem;font-weight:800;color:{cor}'>{val}</div>
          <div style='font-size:.78rem;color:#6B7280'>{sub}</div>
        </div>""", unsafe_allow_html=True)

    _kpi_r(k1, "💸", f"Consumido em {MESES_PT[mes_r]}", brl(total_consumido),
           f"{len(movs_mes)} serviço(s)", "#7E16B8")
    _kpi_r(k2, "➕", "Novos créditos",  brl(total_novos),
           f"{len(creds_novos)} crédito(s)", "#10B981")
    _kpi_r(k3, "⏰", "Créditos encerrados", str(len(creds_vencidos)),
           "vencidos ou utilizados no mês", "#F59E0B")
    _kpi_r(k4, "💰", "Saldo ativo total", brl(saldo_ativo),
           f"{len(creds_ativos)} crédito(s) válidos", "#10B981")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabela de consumos do mês ─────────────────────────────────────────────
    if movs_mes:
        st.markdown(f"#### 📋 Consumos de {mes_label}")

        df_rel = pd.DataFrame(movs_mes)
        df_rel["valor"] = pd.to_numeric(df_rel["valor"], errors="coerce").fillna(0)
        df_rel["data"]  = pd.to_datetime(df_rel["data"], errors="coerce")
        for col_opt in ["descricao_servico","codigo_servico","qtd_amostras","valor_amostra","responsavel","observacao"]:
            if col_opt not in df_rel.columns:
                df_rel[col_opt] = None

        df_rel_show = df_rel.sort_values("data")[
            ["data","cliente_nome","descricao_servico","codigo_servico",
             "qtd_amostras","valor_amostra","valor","responsavel","observacao"]
        ].copy()
        df_rel_show["data"]          = df_rel_show["data"].dt.strftime("%d/%m/%Y")
        df_rel_show["valor_amostra"] = df_rel_show["valor_amostra"].apply(
            lambda v: brl(v) if pd.notna(v) and v else "—")
        df_rel_show["qtd_amostras"]  = df_rel_show["qtd_amostras"].apply(
            lambda v: str(int(v)) if pd.notna(v) and v else "—")
        df_rel_show.columns = ["Data","Cliente","Serviço","Cód.","Amostras",
                                "Vl/Amostra","Total","Responsável","Obs."]
        st.dataframe(df_rel_show.fillna("—"), use_container_width=True, hide_index=True)

        # Por cliente
        st.markdown(f"#### 👥 Consumo por cliente — {mes_label}")
        por_cli = df_rel.groupby("cliente_nome")["valor"].sum().reset_index()
        por_cli = por_cli.sort_values("valor", ascending=False)
        por_cli.columns = ["Cliente", "Total consumido"]
        por_cli["Total consumido"] = por_cli["Total consumido"].apply(brl)
        st.dataframe(por_cli, use_container_width=True, hide_index=True)
    else:
        st.info(f"Nenhum consumo registrado em {mes_label}.")

    if creds_novos:
        st.markdown(f"#### ➕ Novos créditos em {mes_label}")
        df_novos = pd.DataFrame(creds_novos)[
            ["cliente_nome","numero_nf","valor_original","data_vencimento","status"]
        ].copy()
        df_novos["valor_original"]  = df_novos["valor_original"].apply(brl)
        df_novos["data_vencimento"] = pd.to_datetime(df_novos["data_vencimento"], errors="coerce")
        df_novos["data_vencimento"] = df_novos["data_vencimento"].dt.strftime("%d/%m/%Y").fillna("—")
        df_novos.columns = ["Cliente","NF","Valor","Vencimento","Status"]
        st.dataframe(df_novos, use_container_width=True, hide_index=True)

    # ── Geração do Excel ──────────────────────────────────────────────────────
    def _gerar_excel_relatorio(mes_label: str, movs: list, creds_new: list,
                                creds_enc: list, creds_atv: list) -> bytes:
        wb = Workbook()

        # Paleta
        PURPLE   = "4A1259"
        LAVENDER = "EDE9F8"
        WHITE    = "FFFFFF"
        GREY     = "F5F4FA"
        GREEN    = "D1FAE5"
        RED      = "FEE2E2"
        YELLOW   = "FEF3C7"

        hdr_font  = Font(name="Arial", bold=True, color=WHITE, size=10)
        hdr_fill  = PatternFill("solid", fgColor=PURPLE)
        hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin      = Side(style="thin", color="CCCCCC")
        border    = Border(left=thin, right=thin, top=thin, bottom=thin)
        brl_fmt   = '#,##0.00'
        int_fmt   = '#,##0'
        date_fmt  = 'DD/MM/YYYY'

        def _set_header(ws, cols, row=1):
            for c, (title, width) in enumerate(cols, 1):
                cell = ws.cell(row=row, column=c, value=title)
                cell.font    = hdr_font
                cell.fill    = hdr_fill
                cell.alignment = hdr_align
                cell.border  = border
                ws.column_dimensions[get_column_letter(c)].width = width
            ws.row_dimensions[row].height = 30

        def _style_data(ws, r, c, val, fmt=None, fill_color=None, bold=False):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font   = Font(name="Arial", size=9, bold=bold)
            cell.border = border
            cell.alignment = Alignment(vertical="center")
            if fmt:
                cell.number_format = fmt
            if fill_color:
                cell.fill = PatternFill("solid", fgColor=fill_color)
            return cell

        # ── Aba 1: Capa / Resumo ──────────────────────────────────────────────
        ws1 = wb.active
        ws1.title = "Resumo"

        # Título
        ws1.merge_cells("A1:F1")
        t = ws1["A1"]
        t.value     = f"RELATÓRIO DE CRÉDITOS — {mes_label.upper()}"
        t.font      = Font(name="Arial", bold=True, color=WHITE, size=14)
        t.fill      = PatternFill("solid", fgColor=PURPLE)
        t.alignment = Alignment(horizontal="center", vertical="center")
        ws1.row_dimensions[1].height = 40

        ws1.merge_cells("A2:F2")
        ws1["A2"].value = f"Gerado em {date.today().strftime('%d/%m/%Y')} · Grupo GoGenetic"
        ws1["A2"].font  = Font(name="Arial", size=10, color="888888")
        ws1["A2"].alignment = Alignment(horizontal="center")
        ws1.row_dimensions[2].height = 20

        # KPIs
        kpi_data = [
            ("Total consumido no mês",   total_consumido, brl_fmt, None),
            ("Novos créditos",           total_novos,     brl_fmt, GREEN),
            ("Créditos encerrados",      len(creds_enc),  int_fmt, YELLOW),
            ("Saldo ativo total",        saldo_ativo,     brl_fmt, GREEN),
            ("Créditos válidos",         len(creds_atv),  int_fmt, None),
        ]
        ws1.row_dimensions[4].height = 20
        ws1.cell(4, 1, "INDICADORES DO MÊS").font = Font(name="Arial", bold=True, size=10, color=PURPLE)

        for i, (label, val, fmt, fc) in enumerate(kpi_data, 5):
            ws1.row_dimensions[i].height = 22
            c1 = ws1.cell(i, 1, label)
            c1.font   = Font(name="Arial", size=9, bold=True)
            c1.border = border
            c1.fill   = PatternFill("solid", fgColor=LAVENDER)
            ws1.column_dimensions["A"].width = 32

            c2 = ws1.cell(i, 2, val)
            c2.font   = Font(name="Arial", size=9)
            c2.border = border
            c2.number_format = fmt
            if fc:
                c2.fill = PatternFill("solid", fgColor=fc)
            ws1.column_dimensions["B"].width = 20

        # Consumo por cliente
        row = 11
        ws1.cell(row, 1, "CONSUMO POR CLIENTE").font = Font(name="Arial", bold=True, size=10, color=PURPLE)
        row += 1

        _set_header(ws1, [("Cliente", 40), ("Total Consumido (R$)", 22)], row=row)
        row += 1

        df_pc = pd.DataFrame(movs) if movs else pd.DataFrame(columns=["cliente_nome","valor"])
        if not df_pc.empty:
            df_pc["valor"] = pd.to_numeric(df_pc["valor"], errors="coerce").fillna(0)
            por_cliente = df_pc.groupby("cliente_nome")["valor"].sum().reset_index()
            por_cliente = por_cliente.sort_values("valor", ascending=False)
            for _, rrow in por_cliente.iterrows():
                ws1.row_dimensions[row].height = 18
                _style_data(ws1, row, 1, rrow["cliente_nome"])
                _style_data(ws1, row, 2, rrow["valor"], brl_fmt)
                row += 1
            # Total
            ws1.row_dimensions[row].height = 20
            _style_data(ws1, row, 1, "TOTAL", fill_color=LAVENDER, bold=True)
            _style_data(ws1, row, 2, por_cliente["valor"].sum(), brl_fmt,
                        fill_color=LAVENDER, bold=True)

        # ── Aba 2: Consumos detalhados ────────────────────────────────────────
        ws2 = wb.create_sheet("Consumos Detalhados")

        ws2.merge_cells("A1:J1")
        t2 = ws2["A1"]
        t2.value = f"CONSUMOS DETALHADOS — {mes_label.upper()}"
        t2.font  = Font(name="Arial", bold=True, color=WHITE, size=12)
        t2.fill  = PatternFill("solid", fgColor=PURPLE)
        t2.alignment = Alignment(horizontal="center", vertical="center")
        ws2.row_dimensions[1].height = 35

        cols2 = [
            ("Data",           12), ("Cliente",         36), ("Serviço",         35),
            ("Código",         12), ("Amostras",         9), ("Vl/Amostra (R$)", 16),
            ("Total (R$)",     14), ("Responsável",     20), ("Observação",      30),
        ]
        _set_header(ws2, cols2, row=2)

        movs_sorted = sorted(movs, key=lambda m: (m.get("data") or ""))
        alt = False
        for r_idx, m in enumerate(movs_sorted, 3):
            alt = not alt
            fill_c = GREY if alt else WHITE
            ws2.row_dimensions[r_idx].height = 18
            data_val = None
            try:
                data_val = pd.to_datetime(m.get("data")).to_pydatetime() if m.get("data") else None
            except Exception:
                pass
            _style_data(ws2, r_idx, 1, data_val, date_fmt, fill_c)
            _style_data(ws2, r_idx, 2, m.get("cliente_nome",""), fill_color=fill_c)
            _style_data(ws2, r_idx, 3, m.get("descricao_servico","") or "—", fill_color=fill_c)
            _style_data(ws2, r_idx, 4, m.get("codigo_servico","") or "—", fill_color=fill_c)
            qtd = m.get("qtd_amostras")
            _style_data(ws2, r_idx, 5, int(qtd) if qtd else None, int_fmt, fill_c)
            vla = m.get("valor_amostra")
            _style_data(ws2, r_idx, 6, float(vla) if vla else None, brl_fmt, fill_c)
            _style_data(ws2, r_idx, 7, float(m.get("valor") or 0), brl_fmt, fill_c)
            _style_data(ws2, r_idx, 8, m.get("responsavel","") or "—", fill_color=fill_c)
            _style_data(ws2, r_idx, 9, m.get("observacao","") or "—", fill_color=fill_c)

        # Total
        if movs_sorted:
            tot_row = len(movs_sorted) + 3
            ws2.row_dimensions[tot_row].height = 20
            ws2.merge_cells(f"A{tot_row}:F{tot_row}")
            tc = ws2[f"A{tot_row}"]
            tc.value = "TOTAL DO MÊS"
            tc.font  = Font(name="Arial", bold=True, size=9)
            tc.fill  = PatternFill("solid", fgColor=LAVENDER)
            tc.border = border
            tv = ws2.cell(tot_row, 7)
            tv.value  = sum(float(m.get("valor") or 0) for m in movs_sorted)
            tv.number_format = brl_fmt
            tv.font   = Font(name="Arial", bold=True, size=9)
            tv.fill   = PatternFill("solid", fgColor=LAVENDER)
            tv.border = border

        # ── Aba 3: Posição dos Créditos ───────────────────────────────────────
        ws3 = wb.create_sheet("Posição dos Créditos")

        ws3.merge_cells("A1:H1")
        t3 = ws3["A1"]
        t3.value = f"POSIÇÃO DOS CRÉDITOS — {mes_label.upper()}"
        t3.font  = Font(name="Arial", bold=True, color=WHITE, size=12)
        t3.fill  = PatternFill("solid", fgColor=PURPLE)
        t3.alignment = Alignment(horizontal="center", vertical="center")
        ws3.row_dimensions[1].height = 35

        cols3 = [
            ("Cliente",         36), ("NF",       10), ("Crédito (R$)", 16),
            ("Utilizado (R$)",  16), ("Saldo (R$)", 16), ("Vencimento",  14),
            ("Status",          14),
        ]
        _set_header(ws3, cols3, row=2)

        status_fills = {
            "VÁLIDO":    GREEN,
            "EXPIRADO":  RED,
            "UTILIZADO": "F3F4F6",
            "CANCELADO": YELLOW,
        }
        creds_sorted = sorted(creditos_all,
                              key=lambda c: (c.get("status",""), c.get("cliente_nome","")))
        alt = False
        for r_idx, c in enumerate(creds_sorted, 3):
            alt = not alt
            saldo_c = (c.get("valor_original") or 0) - (c.get("valor_utilizado") or 0)
            st_fill = status_fills.get(c.get("status",""), WHITE)
            ws3.row_dimensions[r_idx].height = 18
            _style_data(ws3, r_idx, 1, c.get("cliente_nome",""), fill_color=GREY if alt else WHITE)
            _style_data(ws3, r_idx, 2, c.get("numero_nf","") or "—", fill_color=GREY if alt else WHITE)
            _style_data(ws3, r_idx, 3, float(c.get("valor_original") or 0), brl_fmt)
            _style_data(ws3, r_idx, 4, float(c.get("valor_utilizado") or 0), brl_fmt)
            _style_data(ws3, r_idx, 5, saldo_c, brl_fmt,
                        fill_color="D1FAE5" if saldo_c > 0 else "F3F4F6")
            venc = None
            try:
                venc = pd.to_datetime(c.get("data_vencimento")).to_pydatetime() if c.get("data_vencimento") else None
            except Exception:
                pass
            _style_data(ws3, r_idx, 6, venc, date_fmt)
            _style_data(ws3, r_idx, 7, c.get("status",""), fill_color=st_fill)

        # ── Aba 4: Novos créditos ──────────────────────────────────────────────
        if creds_new:
            ws4 = wb.create_sheet("Novos Créditos")
            ws4.merge_cells("A1:F1")
            t4 = ws4["A1"]
            t4.value = f"NOVOS CRÉDITOS — {mes_label.upper()}"
            t4.font  = Font(name="Arial", bold=True, color=WHITE, size=12)
            t4.fill  = PatternFill("solid", fgColor=PURPLE)
            t4.alignment = Alignment(horizontal="center", vertical="center")
            ws4.row_dimensions[1].height = 35

            cols4 = [
                ("Cliente", 36), ("NF", 10), ("Valor (R$)", 16),
                ("Emissão", 14), ("Vencimento", 14), ("Status", 14),
            ]
            _set_header(ws4, cols4, row=2)
            for r_idx, c in enumerate(creds_new, 3):
                ws4.row_dimensions[r_idx].height = 18
                em = None
                vc = None
                try:
                    nota_c = next((n for n in notas_all if n["id"] == c.get("nota_fiscal_id")), {})
                    em = pd.to_datetime(nota_c.get("data_emissao")).to_pydatetime() if nota_c.get("data_emissao") else None
                    vc = pd.to_datetime(c.get("data_vencimento")).to_pydatetime() if c.get("data_vencimento") else None
                except Exception:
                    pass
                _style_data(ws4, r_idx, 1, c.get("cliente_nome",""))
                _style_data(ws4, r_idx, 2, c.get("numero_nf","") or "—")
                _style_data(ws4, r_idx, 3, float(c.get("valor_original") or 0), brl_fmt)
                _style_data(ws4, r_idx, 4, em, date_fmt)
                _style_data(ws4, r_idx, 5, vc, date_fmt)
                _style_data(ws4, r_idx, 6, c.get("status",""),
                            fill_color=status_fills.get(c.get("status",""), WHITE))

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ── Botão de download — gera Excel SOMENTE quando clicado ────────────────
    col_btn, _ = st.columns([2, 4])
    _rel_key = f"rel_{ano_r}_{mes_r:02d}"

    if col_btn.button(f"📥 Gerar Relatório Excel — {mes_label}",
                      use_container_width=True, key="btn_gerar_rel"):
        with st.spinner("Gerando Excel…"):
            st.session_state[_rel_key] = _gerar_excel_relatorio(
                mes_label, movs_mes, creds_novos, creds_vencidos, creds_ativos
            )

    if _rel_key in st.session_state:
        col_btn.download_button(
            label=f"⬇️ Baixar {mes_label}.xlsx",
            data=st.session_state[_rel_key],
            file_name=f"relatorio_creditos_{ano_r}_{mes_r:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_dl_rel",
        )
