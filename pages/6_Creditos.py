"""Página 6 — Créditos de Clientes."""
import json
from pathlib import Path
from datetime import date, datetime

import openpyxl
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import GLOBAL_CSS, brl, kpi_card, plotly_layout, sidebar_header

st.set_page_config(page_title="Créditos | GoGenetic", page_icon="💳", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

DATA_FILE   = Path(__file__).parent.parent / "data" / "creditos.xlsx"
MANUAL_FILE = Path(__file__).parent.parent / "data" / "creditos_manual.json"
SITUACOES   = ["VÁLIDO", "EXPIRADO", "CANCELADO"]
EMPRESAS_C  = ["GG", "GGS", "GS", "GGY"]

# ── Persistência ───────────────────────────────────────────────────────────────
def load_manual_cred() -> dict:
    if MANUAL_FILE.exists():
        return json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
    return {"novos": [], "consumos": {}}

def save_manual_cred(data: dict):
    MANUAL_FILE.parent.mkdir(exist_ok=True)
    MANUAL_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

# ── Sidebar ────────────────────────────────────────────────────────────────────
sidebar_header()
with st.sidebar:
    st.markdown("**📁 Arquivo de Créditos**")
    uploaded = st.file_uploader("Substituir planilha", type=["xlsx"])
    if uploaded:
        DATA_FILE.parent.mkdir(exist_ok=True)
        DATA_FILE.write_bytes(uploaded.read())
        st.success("✅ Arquivo atualizado!")
        st.cache_data.clear()
        st.rerun()
    if DATA_FILE.exists():
        st.caption(f"Atualizado: {date.fromtimestamp(DATA_FILE.stat().st_mtime).strftime('%d/%m/%Y')}")

    st.markdown("---")
    st.markdown("**🔍 Filtros**")
    filtro_sit = st.multiselect("Situação", ["VÁLIDO", "EXPIRADO"], default=["VÁLIDO"])
    filtro_emp = st.multiselect("Empresa",  EMPRESAS_C, default=[])
    busca      = st.text_input("🔎 Buscar cliente", "")
    st.markdown("---")
    if st.button("🔄 Recarregar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if not DATA_FILE.exists():
    st.warning("⚠️ Nenhum arquivo encontrado. Use o menu lateral para enviar a planilha.")
    st.stop()

# ── Carrega Excel ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_creditos(caminho: str):
    wb = openpyxl.load_workbook(caminho, data_only=True)

    def parse_painel(ws):
        rows = list(ws.iter_rows(values_only=True))
        header_idx = next(
            (i for i, r in enumerate(rows)
             if any(str(v).strip().upper() == "CLIENTES" for v in r if v)), None)
        if header_idx is None:
            return []
        result = []
        for row in rows[header_idx + 1:]:
            cliente = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            if not cliente or cliente.upper() == "CLIENTES":
                continue
            def g(i): return row[i] if len(row) > i else None
            result.append({
                "Cliente":    cliente,
                "Email":      str(g(2) or "").strip(),
                "Empresa":    str(g(3) or "").strip().upper(),
                "OR":         str(g(4) or "").strip(),
                "NF":         str(g(5) or "").strip(),
                "Pagamento":  g(6),
                "Vencimento": g(7),
                "Valor":      float(g(8))  if isinstance(g(8),  (int, float)) else 0.0,
                "Consumo":    float(g(9))  if isinstance(g(9),  (int, float)) else 0.0,
                "Saldo":      float(g(10)) if isinstance(g(10), (int, float)) else 0.0,
                "Situação":   str(g(11) or "").strip().upper() or "—",
            })
        return result

    ativos      = parse_painel(wb["PAINEL"])
    finalizados = parse_painel(wb["FINALIZADO"])

    # Detalhes por aba NF
    detalhes = {}
    skip = {"PAINEL", "FINALIZADO", "MODELO", "MODELO (2)"}
    for nome_aba in wb.sheetnames:
        if nome_aba in skip:
            continue
        try:
            ws2   = wb[nome_aba]
            rows2 = list(ws2.iter_rows(values_only=True))

            # Nome do cliente (primeiras linhas)
            cliente_nome = ""
            for r in rows2[:4]:
                for v in r:
                    s = str(v).strip() if v else ""
                    if s and s.upper() not in ("OBSERVAÇÕES", ""):
                        cliente_nome = s
                        break
                if cliente_nome:
                    break

            # Observações
            obs = ""
            for r in rows2:
                flags = [str(v).strip().upper() for v in r if v]
                if "OBSERVAÇÕES" in flags:
                    idx = next(i for i, v in enumerate(r) if v and str(v).strip().upper() == "OBSERVAÇÕES")
                    if idx + 1 < len(r) and r[idx + 1]:
                        obs = str(r[idx + 1]).strip()
                    break

            # Localiza cabeçalho DATA | DESCRIÇÃO
            header_idx = next(
                (i for i, r in enumerate(rows2)
                 if any(str(v).strip().upper() == "DATA" for v in r if v)
                 and any(str(v).strip().upper() == "DESCRIÇÃO" for v in r if v)), None)

            credito = consumo = saldo = 0.0
            pagamentos, consumos = [], []

            if header_idx is not None:
                hr = rows2[header_idx]
                for j, v in enumerate(hr):
                    if str(v or "").strip().upper() == "CRÉDITO" and j + 1 < len(hr):
                        credito = float(hr[j + 1]) if isinstance(hr[j + 1], (int, float)) else 0.0

                for r in rows2[header_idx + 1:]:
                    for j, v in enumerate(r):
                        s = str(v or "").strip().upper()
                        if s == "CONSUMO" and j + 1 < len(r):
                            consumo = float(r[j + 1]) if isinstance(r[j + 1], (int, float)) else 0.0
                        if s == "SALDO" and j + 1 < len(r):
                            saldo = float(r[j + 1]) if isinstance(r[j + 1], (int, float)) else 0.0

                    data_v = r[1] if len(r) > 1 else None
                    desc_v = str(r[2] or "").strip() if len(r) > 2 else ""
                    if not isinstance(data_v, (datetime, date)) or not data_v:
                        continue
                    serv_v = str(r[3] or "").strip() if len(r) > 3 else ""
                    amos_v = r[4] if len(r) > 4 else None
                    vua_v  = r[5] if len(r) > 5 else None
                    vto_v  = r[6] if len(r) > 6 else None
                    sal_v  = r[7] if len(r) > 7 else None

                    if any(kw in desc_v.upper() for kw in ("PARCELA", "NF ", "CRÉDITO RESTANTE")):
                        pagamentos.append({
                            "Data":      data_v,
                            "Descrição": desc_v,
                            "Valor":     float(sal_v) if isinstance(sal_v, (int, float)) else 0.0,
                        })
                    elif desc_v:
                        consumos.append({
                            "Data":         data_v,
                            "Descrição":    desc_v,
                            "Serviço":      serv_v,
                            "Amostras":     int(amos_v) if isinstance(amos_v, (int, float)) else 0,
                            "Vlr Unitário": float(vua_v) if isinstance(vua_v, (int, float)) else 0.0,
                            "Vlr Total":    float(vto_v) if isinstance(vto_v, (int, float)) else 0.0,
                            "Saldo":        float(sal_v) if isinstance(sal_v, (int, float)) else None,
                        })

            detalhes[nome_aba] = {
                "cliente":    cliente_nome,
                "obs":        obs,
                "credito":    credito,
                "consumo":    consumo,
                "saldo":      saldo,
                "pagamentos": pagamentos,
                "consumos":   consumos,
            }
        except Exception:
            pass

    return ativos, finalizados, detalhes


with st.spinner("Carregando créditos..."):
    ativos_xls, finalizados_xls, detalhes_xls = load_creditos(str(DATA_FILE))

manual_cred = load_manual_cred()
novos_cred  = manual_cred.get("novos", [])
todos_ativos = ativos_xls + novos_cred
df_all  = pd.DataFrame(todos_ativos)  if todos_ativos  else pd.DataFrame()
df_fin  = pd.DataFrame(finalizados_xls) if finalizados_xls else pd.DataFrame()

# Filtros
df_view = df_all.copy()
if not df_view.empty:
    if filtro_sit: df_view = df_view[df_view["Situação"].isin(filtro_sit)]
    if filtro_emp: df_view = df_view[df_view["Empresa"].isin(filtro_emp)]
    if busca:      df_view = df_view[df_view["Cliente"].str.contains(busca, case=False, na=False)]

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<p class="page-title">💳 Créditos de Clientes</p>
<p class="page-sub">Saldo, consumo e histórico por cliente</p>
""", unsafe_allow_html=True)

# ── KPIs ───────────────────────────────────────────────────────────────────────
df_validos = df_all[df_all["Situação"] == "VÁLIDO"] if not df_all.empty else pd.DataFrame()
df_expir   = df_all[df_all["Situação"] == "EXPIRADO"] if not df_all.empty else pd.DataFrame()

c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "✅", "Créditos Válidos",    str(len(df_validos)),
         f"{len(df_expir)} expirados", border="rgba(36,183,140,0.3)")
kpi_card(c2, "💰", "Saldo Disponível",    brl(df_validos["Saldo"].sum() if not df_validos.empty else 0),
         "a consumir", value_class="kpi-positive")
kpi_card(c3, "📊", "Consumido (válidos)", brl(df_validos["Consumo"].sum() if not df_validos.empty else 0))
kpi_card(c4, "⚠️", "Saldo Expirado",     brl(df_expir["Saldo"].sum() if not df_expir.empty else 0),
         "não utilizado", border="rgba(245,166,35,0.4)",
         value_class="kpi-warn" if not df_expir.empty and df_expir["Saldo"].sum() > 0 else "")

# ══════════════════════════════════════════════════════════════════════════════
tab_painel, tab_detalhe, tab_novo, tab_fin_tab = st.tabs([
    f"📋 Painel  ({len(df_view)})",
    "🔍 Detalhamento por Cliente",
    "➕ Novo Crédito",
    f"🗂️ Finalizados  ({len(df_fin)})",
])

# ══════════════════════════════════════════════════════════════════════════════
with tab_painel:
    if df_view.empty:
        st.info("Nenhum crédito encontrado com os filtros selecionados.")
    else:
        # Gráfico top 10 saldos
        df_top = df_view[df_view["Saldo"] > 0].sort_values("Saldo", ascending=False).head(10)
        if not df_top.empty:
            st.markdown("<div class='section-title'>Top 10 Maiores Saldos</div>",
                        unsafe_allow_html=True)
            fig = px.bar(
                df_top.sort_values("Saldo"),
                x="Saldo", y="Cliente", orientation="h",
                color="Situação",
                color_discrete_map={"VÁLIDO": "#24B78C", "EXPIRADO": "#FF672F"},
                text=df_top.sort_values("Saldo")["Saldo"].apply(brl),
                labels={"Saldo": "R$", "Cliente": ""},
            )
            fig.update_traces(textposition="outside", textfont_size=9)
            plotly_layout(fig)
            fig.update_layout(height=340, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        # Tabela
        st.markdown("<div class='section-title'>Lista de Créditos</div>", unsafe_allow_html=True)
        df_show = df_view.copy()
        df_show["Pagamento"]  = pd.to_datetime(df_show["Pagamento"],  errors="coerce").dt.strftime("%d/%m/%Y")
        df_show["Vencimento"] = pd.to_datetime(df_show["Vencimento"], errors="coerce").dt.strftime("%d/%m/%Y")
        df_show["Valor"]   = df_show["Valor"].apply(brl)
        df_show["Consumo"] = df_show["Consumo"].apply(brl)
        df_show["Saldo"]   = df_show["Saldo"].apply(brl)
        st.dataframe(
            df_show[["Cliente","Empresa","NF","OR","Pagamento","Vencimento",
                     "Valor","Consumo","Saldo","Situação"]],
            use_container_width=True, hide_index=True,
        )
        st.caption(f"{len(df_view)} créditos · "
                   f"Saldo total: **{brl(df_view['Saldo'].sum())}** · "
                   f"Valor total: **{brl(df_view['Valor'].sum())}**")

# ══════════════════════════════════════════════════════════════════════════════
with tab_detalhe:
    # Monta opções com NOME DO CLIENTE — quando há duplicatas, adiciona NF
    opcoes_label = {}   # "label exibido" → {"aba": ..., "sit": ...}
    contagem = {}
    for aba, det in detalhes_xls.items():
        nome = det["cliente"].strip() if det["cliente"].strip() else aba
        contagem[nome] = contagem.get(nome, 0) + 1

    for aba, det in detalhes_xls.items():
        nome  = det["cliente"].strip() if det["cliente"].strip() else aba
        nf    = aba.strip()
        label = f"{nome}  —  {nf}" if contagem[nome] > 1 else nome
        opcoes_label[label] = {"aba": aba, "sit": "—"}

    if not opcoes_label:
        st.info("Nenhum detalhe encontrado.")
    else:
        cliente_sel = st.selectbox(
            "👤 Selecione o cliente",
            list(opcoes_label.keys()),
            key="sel_cliente_det",
        )
        aba_sel = opcoes_label[cliente_sel]["aba"]
        det     = detalhes_xls[aba_sel]

        # ── Cabeçalho do cliente ───────────────────────────────────────────────
        st.markdown(f"""
        <div style='background:#F5F0FA;border-radius:10px;padding:16px 20px;margin:12px 0'>
          <div style='font-size:1rem;font-weight:700;color:#1A0A2E;margin-bottom:8px'>
            {det['cliente'] or aba_sel}
          </div>
          <div style='display:flex;gap:32px;flex-wrap:wrap'>
            <div><span style='font-size:.72rem;color:#9E86B8'>CRÉDITO TOTAL</span><br>
              <span style='font-size:1.1rem;font-weight:700;color:#7E16B8'>{brl(det['credito'])}</span></div>
            <div><span style='font-size:.72rem;color:#9E86B8'>CONSUMIDO</span><br>
              <span style='font-size:1.1rem;font-weight:700;color:#EF4444'>{brl(det['consumo'])}</span></div>
            <div><span style='font-size:.72rem;color:#9E86B8'>SALDO</span><br>
              <span style='font-size:1.1rem;font-weight:700;color:#10B981'>{brl(det['saldo'])}</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Barra de progresso
        if det["credito"] > 0:
            pct = min(det["consumo"] / det["credito"] * 100, 100)
            cor = "#10B981" if pct >= 80 else ("#F59E0B" if pct >= 40 else "#7E16B8")
            st.markdown(
                f"<div style='background:#E0D4F0;border-radius:6px;height:10px;margin-bottom:16px'>"
                f"<div style='background:{cor};width:{pct:.1f}%;height:100%;border-radius:6px'></div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if det["obs"]:
            with st.expander("📝 Observações / Tabela de preços"):
                st.markdown(det["obs"].replace("\n", "  \n"))

        # ── Pagamentos e Consumo lado a lado ──────────────────────────────────
        col_pag, col_con = st.columns([1, 2])

        with col_pag:
            st.markdown("<div class='section-title'>Pagamentos / Parcelas</div>",
                        unsafe_allow_html=True)
            if det["pagamentos"]:
                df_pag = pd.DataFrame(det["pagamentos"])
                df_pag["Data"]  = pd.to_datetime(df_pag["Data"], errors="coerce").dt.strftime("%d/%m/%Y")
                df_pag["Valor"] = df_pag["Valor"].apply(brl)
                st.dataframe(df_pag, use_container_width=True, hide_index=True)
            else:
                st.info("Sem parcelas registradas.")

        with col_con:
            st.markdown("<div class='section-title'>Histórico de Consumo</div>",
                        unsafe_allow_html=True)
            consumos_todos = list(det["consumos"])
            consumos_man   = manual_cred.get("consumos", {}).get(aba_sel, [])
            if consumos_man:
                consumos_todos = consumos_todos + consumos_man

            if consumos_todos:
                df_con = pd.DataFrame(consumos_todos)
                df_con["Data"]         = pd.to_datetime(df_con["Data"], errors="coerce").dt.strftime("%d/%m/%Y")
                df_con["Vlr Unitário"] = df_con["Vlr Unitário"].apply(brl)
                df_con["Vlr Total"]    = df_con["Vlr Total"].apply(brl)
                df_con["Saldo"]        = df_con["Saldo"].apply(
                    lambda v: brl(float(v)) if pd.notna(v) and str(v) not in ("", "nan", "None") else "—")
                st.dataframe(
                    df_con[["Data","Descrição","Serviço","Amostras","Vlr Unitário","Vlr Total","Saldo"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("Sem consumos registrados.")

        # ── Registrar consumo ──────────────────────────────────────────────────
        st.markdown("<div class='section-title'>➕ Registrar Novo Consumo</div>",
                    unsafe_allow_html=True)
        with st.form(f"consumo_{aba_sel}", clear_on_submit=True):
            r1c1, r1c2, r1c3 = st.columns([1, 2, 1])
            data_c  = r1c1.date_input("Data", value=date.today())
            desc_c  = r1c2.text_input("Descrição do serviço *")
            serv_c  = r1c3.text_input("Nº Serviço")
            r2c1, r2c2, r2c3 = st.columns(3)
            amos_c  = r2c1.number_input("Amostras", min_value=1, value=1)
            vunit_c = r2c2.number_input("Valor unitário (R$)", min_value=0.0, step=10.0, format="%.2f")
            vtot_c  = amos_c * vunit_c
            r2c3.markdown(f"<br><b>Total: {brl(vtot_c)}</b>", unsafe_allow_html=True)

            if st.form_submit_button("✅ Registrar", type="primary", use_container_width=True):
                if desc_c.strip():
                    man2 = load_manual_cred()
                    man2.setdefault("consumos", {}).setdefault(aba_sel, [])
                    man2["consumos"][aba_sel].append({
                        "Data": str(data_c), "Descrição": desc_c.strip(),
                        "Serviço": serv_c.strip(), "Amostras": int(amos_c),
                        "Vlr Unitário": float(vunit_c), "Vlr Total": float(vtot_c), "Saldo": None,
                    })
                    save_manual_cred(man2)
                    st.success("✅ Consumo registrado!")
                    st.rerun()
                else:
                    st.error("Informe a descrição do serviço.")

# ══════════════════════════════════════════════════════════════════════════════
with tab_novo:
    st.markdown("<div class='section-title'>Cadastrar Novo Crédito</div>", unsafe_allow_html=True)

    with st.form("novo_credito", clear_on_submit=False):
        c1f, c2f = st.columns(2)
        cliente_n = c1f.text_input("Cliente *")
        email_n   = c2f.text_input("E-mail")
        c3f, c4f, c5f = st.columns(3)
        empresa_n = c3f.selectbox("Empresa", EMPRESAS_C)
        nf_n      = c4f.text_input("NF")
        or_n      = c5f.text_input("OR")
        c6f, c7f, c8f = st.columns(3)
        valor_n   = c6f.number_input("Valor do crédito (R$) *", min_value=0.0, step=100.0, format="%.2f")
        dt_pag_n  = c7f.date_input("Data de pagamento", value=date.today())
        dt_venc_n = c8f.date_input("Vencimento", value=date.today().replace(year=date.today().year + 2))
        obs_n     = st.text_area("Observações / Tabela de preços", height=80)

        if st.form_submit_button("✅ Cadastrar", type="primary", use_container_width=True):
            if not cliente_n.strip():
                st.error("Cliente é obrigatório.")
            elif valor_n <= 0:
                st.error("Valor deve ser maior que zero.")
            else:
                man2 = load_manual_cred()
                man2.setdefault("novos", []).append({
                    "Cliente": cliente_n.strip(), "Email": email_n.strip(),
                    "Empresa": empresa_n, "OR": or_n.strip(), "NF": nf_n.strip(),
                    "Pagamento": str(dt_pag_n), "Vencimento": str(dt_venc_n),
                    "Valor": float(valor_n), "Consumo": 0.0, "Saldo": float(valor_n),
                    "Situação": "VÁLIDO", "obs": obs_n.strip(), "_manual": True,
                })
                save_manual_cred(man2)
                st.cache_data.clear()
                st.success(f"✅ Crédito de {brl(valor_n)} cadastrado para {cliente_n.strip()}!")
                st.rerun()

    # Créditos manuais cadastrados
    if novos_cred:
        st.markdown("<div class='section-title'>Cadastrados Manualmente</div>", unsafe_allow_html=True)
        for i, c in enumerate(novos_cred):
            with st.expander(f"💳  {c['Cliente']}  ·  {brl(c['Saldo'])}  ·  {c['Situação']}"):
                col_i, col_s, col_d = st.columns([3, 1, 1])
                col_i.markdown(f"**NF:** {c.get('NF','—')}  |  **OR:** {c.get('OR','—')}  |  "
                                f"**Empresa:** {c.get('Empresa','—')}  |  "
                                f"**Vencimento:** {c.get('Vencimento','—')}")
                nova_sit = col_s.selectbox(
                    "Situação", SITUACOES,
                    index=SITUACOES.index(c["Situação"]) if c["Situação"] in SITUACOES else 0,
                    key=f"sit_{i}",
                )
                if col_s.button("💾", key=f"sv_{i}"):
                    man2 = load_manual_cred()
                    man2["novos"][i]["Situação"] = nova_sit
                    if nova_sit != "VÁLIDO":
                        man2["novos"][i]["Saldo"] = 0.0
                    save_manual_cred(man2)
                    st.rerun()
                if col_d.button("🗑️ Excluir", key=f"del_{i}"):
                    man2 = load_manual_cred()
                    man2["novos"].pop(i)
                    save_manual_cred(man2)
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
with tab_fin_tab:
    if df_fin.empty:
        st.info("Nenhum crédito finalizado.")
    else:
        busca_fin = st.text_input("🔎 Buscar cliente", key="busca_fin")
        df_fv = df_fin.copy()
        if busca_fin:
            df_fv = df_fv[df_fv["Cliente"].str.contains(busca_fin, case=False, na=False)]

        df_fv["Pagamento"]  = pd.to_datetime(df_fv["Pagamento"],  errors="coerce").dt.strftime("%d/%m/%Y")
        df_fv["Vencimento"] = pd.to_datetime(df_fv["Vencimento"], errors="coerce").dt.strftime("%d/%m/%Y")
        df_fv["Valor"]      = df_fv["Valor"].apply(brl)
        df_fv["Consumo"]    = df_fv["Consumo"].apply(brl)
        df_fv["Saldo"]      = df_fv["Saldo"].apply(brl)
        st.dataframe(
            df_fv[["Cliente","Empresa","NF","Pagamento","Vencimento","Valor","Consumo","Saldo","Situação"]],
            use_container_width=True, hide_index=True,
        )
        st.caption(f"{len(df_fv)} créditos · valor histórico total: **{brl(df_fin['Valor'].sum())}**")
