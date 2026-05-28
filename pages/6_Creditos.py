"""Página 6 — Sistema de Créditos de Clientes."""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

from utils import GLOBAL_CSS, brl, status_badge, sidebar_header, require_auth
from db_creditos import (
    list_clientes, insert_cliente, update_cliente, delete_cliente, resumo_cliente,
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

tab_dash, tab_clientes, tab_creditos, tab_movs = st.tabs([
    "📊 Painel", "🧑‍🤝‍🧑 Clientes", "💳 Créditos", "📋 Movimentações"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PAINEL
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    creditos_all = list_creditos()
    clientes_all = list_clientes()

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
    clientes = list_clientes()
    cli_opts = {c["nome"]: c["id"] for c in clientes}

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
                    st.rerun()
                else:
                    st.error("Nome é obrigatório.")
            if s2.form_submit_button("❌ Cancelar", use_container_width=True):
                st.session_state["_cred_novo_cli"] = False
                st.rerun()

    lista = [c for c in clientes if not busca or busca.lower() in c["nome"].lower()]

    if not lista:
        st.info("Nenhum cliente encontrado.")
    else:
        for cli in lista:
            res   = resumo_cliente(cli["id"])
            saldo = res.get("saldo_valido", 0)
            with st.expander(f"**{cli['nome']}**  ·  Saldo válido: {brl(saldo)}"):
                k1c, k2c, k3c, k4c = st.columns(4)
                k1c.metric("Créditos válidos",   res.get("qtd_validos", 0))
                k2c.metric("Créditos expirados", res.get("qtd_expirados", 0))
                k3c.metric("Saldo válido",        brl(res.get("saldo_valido", 0)))
                k4c.metric("Total utilizado",     brl(res.get("total_utilizado", 0)))

                sub1, sub2, sub3 = st.tabs(["💳 Créditos", "📄 Notas Fiscais", "📋 Movimentações"])

                with sub1:
                    creds = list_creditos(cliente_id=cli["id"])
                    if not creds:
                        st.info("Sem créditos.")
                    else:
                        for cr in creds:
                            saldo_cr = (cr["valor_original"] or 0) - (cr["valor_utilizado"] or 0)
                            venc = pd.to_datetime(cr["data_vencimento"], errors="coerce")
                            hoje2 = pd.Timestamp.today().normalize()
                            dias = int((venc - hoje2).days) if pd.notna(venc) else None
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
                                            st.rerun()

                with sub2:
                    notas = list_notas(cliente_id=cli["id"])
                    if notas:
                        for nf in notas:
                            cols = st.columns([3, 2, 2, 1])
                            cols[0].markdown(f"**NF {nf['numero_nf']}**")
                            cols[1].markdown(nf.get("data_emissao") or "—")
                            cols[2].markdown(brl(nf["valor_total"]))
                            if cols[3].button("🗑️", key=f"del_nf_dash_{nf['id']}"):
                                delete_nota(nf["id"])
                                st.rerun()
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
                                st.rerun()

                with sub3:
                    movs = list_movimentacoes(cliente_id=cli["id"])
                    if not movs:
                        st.info("Sem movimentações.")
                    else:
                        df_m = pd.DataFrame(movs)[["data","tipo","valor","responsavel","observacao"]]
                        df_m["valor"] = df_m["valor"].apply(brl)
                        df_m.columns = ["Data","Tipo","Valor","Responsável","Observação"]
                        st.dataframe(df_m.fillna("—"), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CRÉDITOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_creditos:
    clientes = list_clientes()
    cli_opts = {c["nome"]: c["id"] for c in clientes}

    col1, col2 = st.columns(2)
    status_sel = col1.multiselect("Status", ["VÁLIDO","EXPIRADO","UTILIZADO","CANCELADO"],
                                   default=["VÁLIDO"])
    cli_f    = col2.selectbox("Cliente", ["Todos"] + list(cli_opts.keys()), key="cli_f_cred")
    cli_id_f = cli_opts.get(cli_f) if cli_f != "Todos" else None

    lista_tab, novo_tab, consumo_tab = st.tabs(["📋 Lista", "➕ Novo Crédito", "💸 Registrar Consumo"])

    with lista_tab:
        creditos = list_creditos(status=status_sel or None, cliente_id=cli_id_f)
        if not creditos:
            st.info("Nenhum crédito encontrado.")
        else:
            df_c = pd.DataFrame(creditos)
            df_c["saldo"] = df_c["valor_original"].fillna(0) - df_c["valor_utilizado"].fillna(0)
            df_c["data_vencimento"] = pd.to_datetime(df_c["data_vencimento"], errors="coerce")
            hoje3 = pd.Timestamp.today().normalize()
            st.markdown(f"**{len(df_c)} crédito(s) — Saldo total: {brl(df_c['saldo'].sum())}**")
            for _, row in df_c.iterrows():
                saldo = row["saldo"]
                venc  = row["data_vencimento"]
                dias  = int((venc - hoje3).days) if pd.notna(venc) else None
                alerta = ""
                if row["status"] == "VÁLIDO" and dias is not None:
                    alerta = "🔴 " if dias <= 7 else ("🟡 " if dias <= 30 else "🟢 ")
                with st.expander(f"{alerta}{row.get('cliente_nome','—')}  ·  NF {row.get('numero_nf','—')}  ·  {brl(saldo)}  ·  {row['status']}"):
                    ca, cb, cc = st.columns(3)
                    ca.metric("Original",  brl(row["valor_original"]))
                    cb.metric("Utilizado", brl(row["valor_utilizado"]))
                    cc.metric("Saldo",     brl(saldo))
                    if dias is not None:
                        st.caption(f"Vencimento: {venc.strftime('%d/%m/%Y')} · {dias} dias")
                    st.markdown(f"**Status:** {status_badge(row['status'])}", unsafe_allow_html=True)
                    if row["status"] == "VÁLIDO":
                        if st.button("⏰ Expirar", key=f"exp_{row['id']}"):
                            update_credito(row["id"], {"status": "EXPIRADO"})
                            st.rerun()

    with novo_tab:
        if not clientes:
            st.warning("Cadastre um cliente primeiro.")
        else:
            with st.form("form_novo_cred_dash", clear_on_submit=True):
                cli_sel  = st.selectbox("Cliente *", list(cli_opts.keys()))
                notas_cl = list_notas(cliente_id=cli_opts.get(cli_sel))
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
                    st.rerun()

    with consumo_tab:
        creds_validos = list_creditos(status=["VÁLIDO"])
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
                c1, c2  = st.columns(2)
                v_uso   = c1.number_input("Valor consumido *", min_value=0.01,
                                           max_value=float(saldo_d), step=0.01, format="%.2f")
                resp    = c2.text_input("Responsável")
                obs_u   = st.text_area("Observação")
                if st.form_submit_button("💸 Registrar Consumo", use_container_width=True):
                    novo_ut = (cr["valor_utilizado"] or 0) + v_uso
                    novo_st = "UTILIZADO" if (cr["valor_original"] - novo_ut) <= 0 else "VÁLIDO"
                    update_credito(cr["id"], {"valor_utilizado": novo_ut, "status": novo_st})
                    insert_movimentacao({"credito_id": cr["id"], "tipo": "UTILIZAÇÃO",
                                         "valor": float(v_uso), "data": str(date.today()),
                                         "responsavel": resp or None, "observacao": obs_u or None})
                    st.success(f"✅ Consumo de {brl(v_uso)} registrado!")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MOVIMENTAÇÕES
# ══════════════════════════════════════════════════════════════════════════════
with tab_movs:
    import io
    clientes = list_clientes()
    cli_opts = {c["nome"]: c["id"] for c in clientes}

    col1, col2, col3 = st.columns(3)
    tipo_f = col1.multiselect("Tipo", ["UTILIZAÇÃO","ESTORNO","AJUSTE"],
                               default=["UTILIZAÇÃO","ESTORNO","AJUSTE"])
    cli_f2 = col2.selectbox("Cliente", ["Todos"] + list(cli_opts.keys()), key="cli_f_movs")
    busca2 = col3.text_input("🔎 Buscar responsável")

    cli_id_f2 = cli_opts.get(cli_f2) if cli_f2 != "Todos" else None
    movs = list_movimentacoes(cliente_id=cli_id_f2)

    if not movs:
        st.info("Nenhuma movimentação registrada.")
    else:
        df_m = pd.DataFrame(movs)
        df_m["valor"] = pd.to_numeric(df_m["valor"], errors="coerce").fillna(0)
        df_m["data"]  = pd.to_datetime(df_m["data"], errors="coerce")
        if tipo_f:
            df_m = df_m[df_m["tipo"].isin(tipo_f)]
        if busca2:
            df_m = df_m[df_m["responsavel"].fillna("").str.contains(busca2, case=False)]

        st.markdown(f"**{len(df_m)} movimentação(ões) — Total: {brl(df_m['valor'].sum())}**")
        df_show = df_m[["data","tipo","cliente_nome","valor","responsavel","observacao"]].copy()
        df_show["data"]  = df_show["data"].dt.strftime("%d/%m/%Y")
        df_show["valor"] = df_show["valor"].apply(brl)
        df_show.columns  = ["Data","Tipo","Cliente","Valor","Responsável","Observação"]
        st.dataframe(df_show.fillna("—"), use_container_width=True, hide_index=True)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_show.to_excel(writer, index=False, sheet_name="Movimentações")
        st.download_button("📥 Exportar Excel", data=buf.getvalue(),
                           file_name="movimentacoes.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
