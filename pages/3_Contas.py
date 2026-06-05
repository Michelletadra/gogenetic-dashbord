"""Página 3 — Contas a Pagar e a Receber."""
import io
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from utils import (GLOBAL_CSS, BRAND, NOMES, CHART_COLORS,
                   brl, soma, kpi_card, plotly_layout, sidebar_header,
                   load_company_data, load_vencidas,
                   get_empresas_disponiveis, load_data_unificado,
                   load_vencidas_unificado,
                   load_companies_data, load_companies_vencidas)

st.set_page_config(page_title="Contas | GoGenetic", page_icon="💳", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Helpers de semana ──────────────────────────────────────────────────────────

def semana(offset: int = 0):
    hoje    = date.today()
    segunda = hoje - timedelta(days=hoje.weekday()) + timedelta(weeks=offset)
    sexta   = segunda + timedelta(days=4)
    return segunda, sexta

def label_semana(offset: int) -> str:
    s, f = semana(offset)
    return f"{s.strftime('%d/%m')} → {f.strftime('%d/%m')}"

# ── Sidebar ────────────────────────────────────────────────────────────────────
sidebar_header()

with st.sidebar:
    _disponiveis   = get_empresas_disponiveis()
    empresa_opcoes = ["Todas"] + _disponiveis
    empresa_sel    = st.selectbox("🏢 Empresa", empresa_opcoes)
    if empresa_sel != "Todas" and empresa_sel in BRAND:
        st.image(BRAND[empresa_sel]["logo"], use_column_width=True)
    empresas_ativas = _disponiveis if empresa_sel == "Todas" else [empresa_sel]

    st.markdown("---")
    st.markdown("**📅 Período**")

    PERIODOS = {
        f"Esta semana  ({label_semana(0)})":     semana(0),
        f"Próxima semana  ({label_semana(1)})":  semana(1),
        f"Semana passada  ({label_semana(-1)})": semana(-1),
        f"Próx. 2 semanas ({label_semana(0)[0:5]} → {label_semana(1)[8:]})":
            (semana(0)[0], semana(1)[1]),
        "Este mês":         (date.today().replace(day=1), date.today()),
        "Próximo mês":      ((date.today().replace(day=1) + timedelta(days=32)).replace(day=1),
                             (date.today().replace(day=1) + timedelta(days=62)).replace(day=1) - timedelta(days=1)),
        "Últimos 30 dias":  (date.today() - timedelta(days=30), date.today()),
        "Últimos 60 dias":  (date.today() - timedelta(days=60), date.today()),
        "Personalizado":    None,
    }

    _default_idx = 0
    if "_contas_periodo" in st.session_state:
        _chave = st.session_state["_contas_periodo"]
        if _chave in list(PERIODOS.keys()):
            _default_idx = list(PERIODOS.keys()).index(_chave)
    periodo_sel = st.selectbox("Intervalo", list(PERIODOS.keys()), index=_default_idx)

    if periodo_sel == "Personalizado":
        c1, c2 = st.columns(2)
        dt_ini = c1.date_input("De",  date.today().replace(day=1))
        dt_fim = c2.date_input("Até", date.today())
    else:
        dt_ini, dt_fim = PERIODOS[periodo_sel]

    dt_ini_str = dt_ini.strftime("%Y-%m-%d")
    dt_fim_str = dt_fim.strftime("%Y-%m-%d")

    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱ Cache: 5 min")

# ── Carrega dados (empresas em paralelo) ───────────────────────────────────────
with st.spinner("Carregando contas..."):
    _dados_map = load_companies_data(empresas_ativas, dt_ini_str, dt_fim_str)
    _venc_map  = load_companies_vencidas(empresas_ativas)

    contas_rec, contas_pag = [], []
    venc_rec,   venc_pag   = [], []
    for nome in empresas_ativas:
        dados = _dados_map[nome]
        for item in dados["contas_receber"]: contas_rec.append({**item, "empresa": nome})
        for item in dados["contas_pagar"]:   contas_pag.append({**item, "empresa": nome})
        v = _venc_map[nome]
        for item in v["receber"]: venc_rec.append({**item, "empresa": nome})
        for item in v["pagar"]:   venc_pag.append({**item, "empresa": nome})

total_rec = soma(contas_rec, "valor")
total_pag = soma(contas_pag, "valor")
saldo     = total_rec - total_pag
total_vr  = soma(venc_rec, "valor")
total_vp  = soma(venc_pag, "valor")

# ── Header ─────────────────────────────────────────────────────────────────────
empresa_label = empresas_ativas[0] if len(empresas_ativas) == 1 else "Grupo GoGenetic"
st.markdown(f"""
<p class="page-title">💳 Contas a Pagar & Receber</p>
<p class="page-sub">{empresa_label} · {dt_ini.strftime('%d/%m/%Y')} → {dt_fim.strftime('%d/%m/%Y')}</p>
""", unsafe_allow_html=True)

# ── Botões rápidos de semana ───────────────────────────────────────────────────
_s0, _s1 = semana(0), semana(1)
_opcoes_rapidas = {
    f"📅 Esta semana  ({label_semana(0)})":       "Esta semana",
    f"📅 Próxima semana  ({label_semana(1)})":    "Próxima semana",
    f"📅 Próx. 2 semanas  ({_s0[0].strftime('%d/%m')} → {_s1[1].strftime('%d/%m')})": "2 semanas",
}
_key_ativa = None
for _label, _key in _opcoes_rapidas.items():
    if _key == "Esta semana" and periodo_sel.startswith("Esta semana"):
        _key_ativa = _key
    elif _key == "Próxima semana" and periodo_sel.startswith("Próxima"):
        _key_ativa = _key
    elif _key == "2 semanas" and periodo_sel.startswith("Próx. 2"):
        _key_ativa = _key

btn_cols = st.columns([2, 2, 2, 5])
with btn_cols[0]:
    if st.button(f"Esta semana\n{label_semana(0)}", use_container_width=True,
                 type="primary" if _key_ativa == "Esta semana" else "secondary"):
        st.session_state["_contas_periodo"] = list(PERIODOS.keys())[0]
        st.rerun()
with btn_cols[1]:
    if st.button(f"Próxima semana\n{label_semana(1)}", use_container_width=True,
                 type="primary" if _key_ativa == "Próxima semana" else "secondary"):
        st.session_state["_contas_periodo"] = list(PERIODOS.keys())[1]
        st.rerun()
with btn_cols[2]:
    if st.button(f"2 semanas\n{_s0[0].strftime('%d/%m')} → {_s1[1].strftime('%d/%m')}", use_container_width=True,
                 type="primary" if _key_ativa == "2 semanas" else "secondary"):
        st.session_state["_contas_periodo"] = list(PERIODOS.keys())[3]
        st.rerun()
st.markdown("")

# ── KPIs ───────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
kpi_card(c1, "📥", "A Receber",      brl(total_rec), f"{len(contas_rec)} títulos", border="rgba(36,183,140,0.3)")
kpi_card(c2, "📤", "A Pagar",        brl(total_pag), f"{len(contas_pag)} títulos", border="rgba(255,103,47,0.3)")
kpi_card(c3, "📈", "Saldo Previsto", brl(abs(saldo)), "Receber − Pagar",
         border="rgba(36,183,140,0.4)" if saldo >= 0 else "rgba(255,103,47,0.4)",
         value_class="kpi-positive" if saldo >= 0 else "kpi-negative")
kpi_card(c4, "⚠️", "Vencido a Rec.", brl(total_vr), f"{len(venc_rec)} títulos", border="rgba(245,166,35,0.4)", value_class="kpi-warn" if total_vr > 0 else "")
kpi_card(c5, "🚨", "Vencido a Pag.", brl(total_vp), f"{len(venc_pag)} títulos", border="rgba(255,103,47,0.4)", value_class="kpi-negative" if total_vp > 0 else "")

# ── Gráfico por mês ────────────────────────────────────────────────────────────
def df_mensal(items, campo_data, label):
    if not items: return pd.DataFrame()
    df = pd.DataFrame(items)
    df[campo_data] = pd.to_datetime(df[campo_data], errors="coerce")
    df["valor"]    = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=[campo_data, "valor"])
    df["mes"] = df[campo_data].dt.to_period("M").astype(str)
    g = df.groupby("mes")["valor"].sum().reset_index()
    g["tipo"] = label
    return g

df_fl = pd.concat([df_mensal(contas_rec, "dtVenc", "A Receber"),
                   df_mensal(contas_pag, "dtVenc", "A Pagar")])

if not df_fl.empty:
    st.markdown("<div class='section-title'>Fluxo por Mês de Vencimento</div>", unsafe_allow_html=True)
    fig = px.bar(df_fl, x="mes", y="valor", color="tipo", barmode="group",
                 color_discrete_map={"A Receber": "#24B78C", "A Pagar": "#FF672F"},
                 labels={"mes": "", "valor": "R$", "tipo": ""})
    plotly_layout(fig)
    st.plotly_chart(fig, use_container_width=True)

# ── Tabelas interativas ────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Detalhamento — selecione linhas para somar</div>",
            unsafe_allow_html=True)
st.caption("💡 Clique nas linhas para selecioná-las. O total e o botão de exportação aparecem abaixo.")

tab_rec, tab_pag, tab_venc = st.tabs([
    f"📥 A Receber ({len(contas_rec)})",
    f"📤 A Pagar ({len(contas_pag)})",
    f"⚠️ Vencidos ({len(venc_rec) + len(venc_pag)})",
])


def prep_df(items: list, cols_map: dict) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
    existing = [c for c in cols_map if c in df.columns]
    df = df[existing].rename(columns=cols_map)
    if "Valor" in df.columns:
        df["Valor"] = df["Valor"].apply(brl)
    if "Vencimento" in df.columns:
        df["Vencimento"] = pd.to_datetime(df["Vencimento"], errors="coerce").dt.strftime("%d/%m/%Y")
    if "Data Pgto" in df.columns:
        df["Data Pgto"] = pd.to_datetime(df["Data Pgto"], errors="coerce").dt.strftime("%d/%m/%Y")
    return df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados")
    return buf.getvalue()


def tabela_interativa(items: list, cols_map: dict, valor_campo: str = "valor",
                      nome_arquivo: str = "contas"):
    if not items:
        st.info("Nenhum registro no período.")
        return

    df_num  = pd.DataFrame(items)
    df_num[valor_campo] = pd.to_numeric(df_num[valor_campo], errors="coerce").fillna(0)
    df_show = prep_df(items, cols_map)

    event = st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
    )

    sel_rows = event.selection.rows if event.selection else []

    col_info, col_soma, col_export = st.columns([2, 2, 1])

    with col_info:
        if sel_rows:
            st.caption(f"✅ {len(sel_rows)} linha(s) selecionada(s) de {len(items)}")
        else:
            st.caption(f"Total: {len(items)} registros · clique para selecionar")

    with col_soma:
        if sel_rows:
            soma_sel = df_num.iloc[sel_rows][valor_campo].sum()
            st.markdown(
                f"<div style='background:#F5F0FA;border:1px solid #7E16B8;border-radius:8px;"
                f"padding:8px 16px;text-align:right'>"
                f"<span style='font-size:.72rem;color:#7E16B8;text-transform:uppercase;letter-spacing:1px'>Soma selecionadas</span><br>"
                f"<span style='font-size:1.3rem;font-weight:700;color:#1A0A2E'>{brl(soma_sel)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            soma_total = df_num[valor_campo].sum()
            st.markdown(
                f"<div style='background:#F5F0FA;border:1px solid rgba(126,22,184,0.2);border-radius:8px;"
                f"padding:8px 16px;text-align:right'>"
                f"<span style='font-size:.72rem;color:#9E86B8;text-transform:uppercase;letter-spacing:1px'>Total do período</span><br>"
                f"<span style='font-size:1.3rem;font-weight:700;color:#1A0A2E'>{brl(soma_total)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with col_export:
        df_export = df_show.iloc[sel_rows] if sel_rows else df_show
        label_btn = f"📥 Excel ({len(sel_rows)} sel.)" if sel_rows else "📥 Excel"
        st.download_button(
            label=label_btn,
            data=to_excel_bytes(df_export),
            file_name=f"{nome_arquivo}_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


with tab_rec:
    tabela_interativa(
        contas_rec,
        {"empresa": "Empresa", "dtVenc": "Vencimento", "nomeContato": "Cliente",
         "valor": "Valor", "descricao": "Descrição"},
        nome_arquivo="a_receber",
    )

with tab_pag:
    tabela_interativa(
        contas_pag,
        {"empresa": "Empresa", "dtVenc": "Vencimento", "nomeContato": "Fornecedor",
         "valor": "Valor", "descricao": "Descrição"},
        nome_arquivo="a_pagar",
    )

with tab_venc:
    st.markdown("#### 📥 A Receber em Atraso")
    if venc_rec:
        df_vr = pd.DataFrame(venc_rec)
        df_vr["valor"]  = pd.to_numeric(df_vr["valor"], errors="coerce").fillna(0)
        df_vr["dtVenc"] = pd.to_datetime(df_vr["dtVenc"], errors="coerce")
        df_vr["Atraso"] = df_vr["dtVenc"].apply(
            lambda d: f"{(pd.Timestamp.today()-d).days} dias" if pd.notna(d) else "")
        df_vr = df_vr.sort_values("dtVenc")
        tabela_interativa(
            df_vr.to_dict("records"),
            {"empresa": "Empresa", "dtVenc": "Vencimento", "nomeContato": "Cliente",
             "valor": "Valor", "Atraso": "Atraso"},
            nome_arquivo="vencidos_receber",
        )
    else:
        st.success("Nenhum recebimento em atraso! ✅")

    st.markdown("#### 📤 A Pagar em Atraso")
    if venc_pag:
        df_vp = pd.DataFrame(venc_pag)
        df_vp["valor"]  = pd.to_numeric(df_vp["valor"], errors="coerce").fillna(0)
        df_vp["dtVenc"] = pd.to_datetime(df_vp["dtVenc"], errors="coerce")
        df_vp["Atraso"] = df_vp["dtVenc"].apply(
            lambda d: f"{(pd.Timestamp.today()-d).days} dias" if pd.notna(d) else "")
        df_vp = df_vp.sort_values("dtVenc")
        tabela_interativa(
            df_vp.to_dict("records"),
            {"empresa": "Empresa", "dtVenc": "Vencimento", "nomeContato": "Fornecedor",
             "valor": "Valor", "Atraso": "Atraso"},
            nome_arquivo="vencidos_pagar",
        )
    else:
        st.success("Nenhum pagamento em atraso! ✅")
