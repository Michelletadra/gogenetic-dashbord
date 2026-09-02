"""Página 6 — Sistema de Créditos de Clientes."""
import io
import streamlit as st
import pandas as pd
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
    list_movimentacoes, insert_movimentacao, delete_movimentacao,
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

def _tabs_persist(options: list, key: str) -> str:
    """Como st.tabs(), mas lembra qual aba estava selecionada entre reruns
    (st.tabs volta sempre pra primeira aba a cada rerun, o que derrubava
    o usuário de volta pro Painel no meio de um cadastro)."""
    last = st.session_state.get(key, options[0])
    if last not in options:
        last = options[0]
    sel = st.segmented_control(key, options, default=last, key=f"{key}_widget",
                                label_visibility="collapsed")
    if sel is None:
        sel = last
    st.session_state[key] = sel
    return sel

_top_l, _top_r = st.columns([5, 1])
with _top_r:
    if st.button("🔄 Atualizar dados", use_container_width=True,
                 help="Recarrega tudo do banco agora, sem esperar o cache (até 10min)."):
        _clear_and_rerun()

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

def _nf_label(numero_nf) -> str:
    return f"NF {numero_nf}" if numero_nf else "Sem NF"

def _status_dot(status: str, dias: "int | None") -> str:
    """Bolinha de status — todo crédito tem uma, não só os VÁLIDO vencendo
    (antes só VÁLIDO ganhava bolinha e o resto ficava sem nada, inconsistente
    numa lista com status misturados)."""
    if status == "VÁLIDO":
        if dias is None:
            return "🟢"
        return "🔴" if dias <= 7 else ("🟡" if dias <= 30 else "🟢")
    if status == "EXPIRADO":
        return "🟠"
    if status == "UTILIZADO":
        return "⚪"
    return "⚫"  # CANCELADO ou outro

def _render_form_consumo(cr, key_suffix=""):
    """Formulário de registrar consumo — usado tanto na aba 💳 Créditos
    (Lista/Registrar Consumo) quanto no perfil do cliente (🧑‍🤝‍🧑 Clientes),
    pra não ter duas versões divergentes da mesma coisa."""
    saldo_d = (cr["valor_original"] or 0) - (cr["valor_utilizado"] or 0)
    st.markdown(f"**Saldo disponível: {brl(saldo_d)}**")

    with st.form(f"form_consumo_dash_{cr['id']}{key_suffix}", clear_on_submit=True):
        ca, cb = st.columns(2)
        desc_serv = ca.text_input("Descrição do serviço *", placeholder="ex: Microbioma 1 alvo",
                                   key=f"desc_serv_{cr['id']}{key_suffix}")
        with cb:
            v_uso, _ = _valor_input(
                "Valor consumido (R$) *", key=f"v_uso_{cr['id']}{key_suffix}",
                help=f"Saldo disponível: {brl(saldo_d)}. Pode passar — o excedente vira saldo "
                     f"negativo, cobrado do cliente à parte.",
            )

        cc, cd = st.columns(2)
        data_serv = cc.date_input("Data do serviço", value=date.today(),
                                   key=f"data_serv_{cr['id']}{key_suffix}")
        resp      = cd.text_input("Responsável", key=f"resp_{cr['id']}{key_suffix}")
        obs_u = st.text_area("Observação", height=60, key=f"obs_u_{cr['id']}{key_suffix}")

        with st.expander("➕ Detalhes por amostra (opcional)"):
            ce, cf, cg = st.columns(3)
            cod_serv = ce.text_input("Código do serviço", placeholder="ex: S5990",
                                      key=f"cod_serv_{cr['id']}{key_suffix}")
            qtd_am   = cf.number_input("Qtd amostras", min_value=0, step=1, value=0,
                                        key=f"qtd_am_{cr['id']}{key_suffix}")
            with cg:
                vl_am, _ = _valor_input("Valor / amostra (R$)", key=f"vl_am_{cr['id']}{key_suffix}")
            if qtd_am > 0 and vl_am:
                st.caption(f"💡 {qtd_am} amostras × {brl(vl_am)} = {brl(qtd_am * vl_am)}")

        if st.form_submit_button("💸 Registrar Consumo", use_container_width=True):
            if not desc_serv.strip():
                st.error("Informe a descrição do serviço.")
            elif not v_uso or v_uso <= 0:
                st.error("❌ Informe um valor válido de consumo.")
            else:
                novo_ut = (cr["valor_utilizado"] or 0) + v_uso
                # Pode passar do saldo de propósito — o excedente vira saldo
                # negativo e é cobrado do cliente à parte, não é erro.
                novo_saldo = cr["valor_original"] - novo_ut
                novo_st = "UTILIZADO" if novo_saldo <= 0 else cr["status"]
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
                    "valor_amostra":     float(vl_am) if vl_am and vl_am > 0 else None,
                })
                if novo_saldo < 0:
                    st.session_state["_consumo_ok"] = (
                        f"✅ Consumo de {brl(v_uso)} registrado! "
                        f"Saldo ficou negativo em {brl(abs(novo_saldo))} — cobrar esse valor do cliente."
                    )
                else:
                    st.session_state["_consumo_ok"] = f"✅ Consumo de {brl(v_uso)} registrado!"
                _clear_and_rerun()

@st.dialog("💸 Registrar consumo")
def _abrir_dialog_consumo(cr):
    """Aberto sob demanda (não a cada linha da lista) — antes o formulário
    inteiro de cada crédito era montado em popover pra TODAS as linhas em
    todo carregamento de página, o que deixava a Lista lenta com muitos
    créditos (100+). Com st.dialog só constrói quando alguém clica."""
    alerta_exp = " ⚠️ EXPIRADO" if cr["status"] == "EXPIRADO" else ""
    st.caption(f"{cr.get('cliente_nome','?')} — {_nf_label(cr.get('numero_nf'))}{alerta_exp}")
    _render_form_consumo(cr, key_suffix=f"_dlg_{cr['id']}")

@st.dialog("🗑️ Excluir crédito")
def _abrir_dialog_excluir(cr):
    st.caption(f"Excluir crédito de {cr.get('cliente_nome','?')} — {brl(cr.get('valor_original'))}")
    movs_do_credito = [m for m in movs_all if m.get("credito_id") == cr["id"]]
    if movs_do_credito:
        st.warning(
            f"⚠️ Tem {len(movs_do_credito)} movimentação(ões) registrada(s) — "
            f"excluir apaga esse histórico junto."
        )
    confirma_del = st.checkbox("Confirmo a exclusão", key=f"del_confirm_dlg_{cr['id']}")
    if st.button("🗑️ Excluir definitivamente", key=f"del_btn_dlg_{cr['id']}",
                 disabled=not confirma_del, use_container_width=True):
        delete_credito(cr["id"])
        st.session_state["_edit_cred_ok"] = f"🗑️ Crédito de {cr.get('cliente_nome','?')} excluído."
        _clear_and_rerun()

def _attach_nf_control(cr, key_suffix=""):
    """Campo rápido pra anexar (ou trocar) a NF de um crédito, sem precisar
    abrir outra aba. Digitou um número novo -> cria a NF e já vincula."""
    with st.form(f"form_nf_{cr['id']}{key_suffix}", clear_on_submit=True):
        nf1, nf2 = st.columns([3, 1])
        nf_num = nf1.text_input(
            "Número da NF", value=cr.get("numero_nf") or "",
            key=f"nf_num_{cr['id']}{key_suffix}", placeholder="ex: 6640",
        )
        salvar_nf = nf2.form_submit_button("💾 Salvar NF", use_container_width=True)
        if salvar_nf:
            nf_num = nf_num.strip()
            if not nf_num:
                st.error("❌ Digite o número da NF antes de salvar.")
            else:
                nf_id = insert_nota({
                    "numero_nf":    nf_num,
                    "cliente_id":   cr["cliente_id"],
                    "data_emissao": str(date.today()),
                    "valor_total":  float(cr.get("valor_original") or 0),
                })
                update_credito(cr["id"], {"nota_fiscal_id": nf_id})
                st.session_state["_edit_cred_ok"] = f"✅ NF {nf_num} vinculada ao crédito!"
                _clear_and_rerun()

def _parse_valor(texto: str):
    """Converte texto digitado em R$ pra float — aceita '2500', '2500.00',
    '2500,00' e '2.500,00' (o campo numérico nativo do navegador só aceita
    ponto e rejeita vírgula, o que fazia o valor digitado sumir/dar errado)."""
    if not texto:
        return None
    t = texto.strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        val = float(t)
    except ValueError:
        return None
    return val if val >= 0 else None

def _valor_input(label: str, key: str, valor_atual: float = None, help: str = None) -> tuple:
    """Campo de texto pra valores em R$ — mostra o valor interpretado embaixo
    pra confirmar antes de salvar. Retorna (valor_float_ou_None, texto_digitado)."""
    default = f"{valor_atual:.2f}".replace(".", ",") if valor_atual is not None else ""
    texto = st.text_input(label, value=default, key=key,
                           placeholder="ex: 2500,00", help=help)
    val = _parse_valor(texto)
    if texto and val is None:
        st.caption("⚠️ Não entendi esse valor — use só números, vírgula e ponto.")
    elif val is not None:
        st.caption(f"= {brl(val)}")
    return val, texto

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
main_tab = _tabs_persist(
    ["📊 Painel", "🧑‍🤝‍🧑 Clientes", "💳 Créditos", "📋 Movimentações", "📑 Relatório Mensal"],
    key="cred_main_tab",
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PAINEL
# ══════════════════════════════════════════════════════════════════════════════
if main_tab == "📊 Painel":
    df = pd.DataFrame(creditos_all) if creditos_all else pd.DataFrame()

    if not df.empty:
        df["valor_original"]  = pd.to_numeric(df["valor_original"],  errors="coerce").fillna(0)
        df["valor_utilizado"] = pd.to_numeric(df["valor_utilizado"], errors="coerce").fillna(0)
        df["saldo"]           = df["valor_original"] - df["valor_utilizado"]
        df["data_vencimento"] = pd.to_datetime(df["data_vencimento"], errors="coerce")

        hoje        = pd.Timestamp.today().normalize()
        df_validos  = df[df["status"] == "VÁLIDO"]
        df_expirad  = df[df["status"] == "EXPIRADO"]
        df_venc30   = df_validos[(df_validos["data_vencimento"] >= hoje) & (df_validos["data_vencimento"] <= hoje + timedelta(days=30))]
        df_venc7    = df_validos[(df_validos["data_vencimento"] >= hoje) & (df_validos["data_vencimento"] <= hoje + timedelta(days=7))]
    else:
        df_validos = df_expirad = df_venc30 = df_venc7 = pd.DataFrame()
        hoje = pd.Timestamp.today().normalize()

    k1, k2, k3, k4 = st.columns(4)
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
    _kpi(k2,"⚠️","Vencendo 30d",  brl(df_venc30["saldo"].sum() if not df_venc30.empty else 0),
         f"{len(df_venc30)} crédito(s)", "#F59E0B")
    _kpi(k3,"🚨","Vencendo 7d",   brl(df_venc7["saldo"].sum() if not df_venc7.empty else 0),
         f"{len(df_venc7)} crédito(s)", "#EF4444" if not df_venc7.empty else "#6B7280")
    _kpi(k4,"👥","Clientes",      str(len(clientes_all)), "cadastrados")

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
                  {_nf_label(row.get('numero_nf'))} · Vence em {dias} dia{'s' if dias != 1 else ''}
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
                  {_nf_label(row.get('numero_nf'))} · {dias} dias
                </span></div>
              <b style='color:#F59E0B'>{brl(row['saldo'])}</b>
            </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CLIENTES
# ══════════════════════════════════════════════════════════════════════════════
if main_tab == "🧑‍🤝‍🧑 Clientes":
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

        cli_sub_tab = _tabs_persist(
            ["💳 Créditos", "📄 Notas Fiscais", "📋 Movimentações", "📑 Contratos"],
            key="cred_cli_subtab",
        )

        creds_cli     = _cred_by_cli.get(cli["id"], [])
        notas_cli     = _nota_by_cli.get(cli["id"], [])
        movs_cli      = _mov_by_cli.get(cli["id"], [])

        if cli_sub_tab == "💳 Créditos":
            if st.session_state.get("_consumo_cli_ok"):
                st.success(st.session_state.pop("_consumo_cli_ok"))
            if st.session_state.get("_edit_cred_ok"):
                st.success(st.session_state.pop("_edit_cred_ok"))
            if not creds_cli:
                st.info("Sem créditos.")
            else:
                for cr in creds_cli:
                    saldo_cr = (cr["valor_original"] or 0) - (cr["valor_utilizado"] or 0)
                    venc = pd.to_datetime(cr["data_vencimento"], errors="coerce")
                    dias = int((venc - hoje_ts).days) if pd.notna(venc) else None
                    alerta = _status_dot(cr["status"], dias) + " "
                    nf_label = _nf_label(cr.get('numero_nf'))
                    with st.expander(f"{alerta}{nf_label}  ·  {brl(saldo_cr)}  ·  {cr['status']}"):
                        ca, cb, cc = st.columns(3)
                        ca.metric("Original",  brl(cr["valor_original"]))
                        cb.metric("Utilizado", brl(cr["valor_utilizado"]))
                        cc.metric("Saldo",     brl(saldo_cr))
                        if dias is not None:
                            st.caption(f"Vencimento: {venc.strftime('%d/%m/%Y')} · {dias} dias")

                        st.markdown("**Número da NF**")
                        _attach_nf_control(cr, key_suffix="_cli")

                        if cr["status"] != "CANCELADO" and saldo_cr > 0:
                            st.markdown("**Registrar consumo**")
                            _render_form_consumo(cr, key_suffix="_cli")

                        st.markdown("---")
                        movs_do_credito = [m for m in movs_all if m.get("credito_id") == cr["id"]]
                        if movs_do_credito:
                            st.caption(f"⚠️ Tem {len(movs_do_credito)} movimentação(ões) — excluir apaga junto.")
                        confirma_del_cli = st.checkbox("Confirmo a exclusão", key=f"del_confirm_cli_{cr['id']}")
                        if st.button("🗑️ Excluir crédito", key=f"del_btn_cli_{cr['id']}",
                                     disabled=not confirma_del_cli):
                            delete_credito(cr["id"])
                            st.session_state["_edit_cred_ok"] = f"🗑️ Crédito excluído."
                            _clear_and_rerun()

        if cli_sub_tab == "📄 Notas Fiscais":
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
                with n2:
                    valor_nf, _ = _valor_input("Valor (R$)", key=f"valor_nf_{cli['id']}")
                data_em  = n1.date_input("Data emissão")
                auto_cred = n2.checkbox("Criar crédito automaticamente", value=True)
                venc_nf = None
                if auto_cred:
                    venc_nf = st.date_input("Vencimento do crédito",
                                             value=date.today() + timedelta(days=30))
                if st.form_submit_button("➕ Cadastrar NF", use_container_width=True):
                    if not num_nf.strip():
                        st.error("❌ Informe o número da NF.")
                    elif valor_nf is None:
                        st.error("❌ Informe um valor válido para a NF.")
                    else:
                        nf_id = insert_nota({"numero_nf": num_nf.strip(), "cliente_id": cli["id"],
                                              "data_emissao": str(data_em), "valor_total": float(valor_nf)})
                        if auto_cred and valor_nf > 0:
                            insert_credito({"cliente_id": cli["id"], "nota_fiscal_id": nf_id,
                                            "valor_original": float(valor_nf),
                                            "data_vencimento": str(venc_nf) if venc_nf else None})
                        st.success(f"✅ NF {num_nf} cadastrada!")
                        _clear_and_rerun()

        if cli_sub_tab == "📋 Movimentações":
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

        if cli_sub_tab == "📑 Contratos":
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
if main_tab == "💳 Créditos":
    cli_opts = {c["nome"]: c["id"] for c in clientes_all}

    col1, col2, col3 = st.columns([2, 2, 2])
    status_sel = col1.multiselect("Status", ["VÁLIDO","EXPIRADO","UTILIZADO","CANCELADO"],
                                   default=["VÁLIDO"])
    cli_f    = col2.selectbox("Cliente", ["Todos"] + list(cli_opts.keys()), key="cli_f_cred")
    cli_id_f = cli_opts.get(cli_f) if cli_f != "Todos" else None
    busca_nf = col3.text_input("🔎 Buscar por NF ou cliente", key="busca_nf_cred",
                                placeholder="ex: 1234 ou nome do cliente")

    cred_action = _tabs_persist(
        ["📋 Lista", "➕ Novo Crédito", "💸 Registrar Consumo"],
        key="cred_creditos_subtab",
    )

    if cred_action == "📋 Lista":
        if st.session_state.get("_edit_cred_ok"):
            st.success(st.session_state.pop("_edit_cred_ok"))

        # Filter in memory. Busca por NF/cliente tem prioridade sobre o filtro
        # de Status — já aconteceu 2x de um crédito EXPIRADO/UTILIZADO existir
        # mas não aparecer porque o filtro de Status tinha ficado em "VÁLIDO",
        # dando a impressão de que a busca "não achou" quando na real achava,
        # só estava escondido pelo outro filtro.
        creds_tab = creditos_all
        if busca_nf:
            termo = busca_nf.strip().lower()
            creds_tab = [c for c in creds_tab
                         if termo in str(c.get("numero_nf") or "").lower()
                         or termo in str(c.get("cliente_nome") or "").lower()]
        elif status_sel:
            creds_tab = [c for c in creds_tab if c["status"] in status_sel]
        if cli_id_f:
            creds_tab = [c for c in creds_tab if c["cliente_id"] == cli_id_f]
        if busca_nf and status_sel and len(status_sel) < 4:
            st.caption("🔎 Busca ativa — mostrando qualquer status (ignorando o filtro de Status acima).")

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
                alerta = _status_dot(cr["status"], dias)
                rows_cr.append({
                    "":          alerta,
                    "Cliente":   cr.get("cliente_nome","—"),
                    "NF":        cr.get("numero_nf") or "—",
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

            import io as _io
            buf_lista = _io.BytesIO()
            with pd.ExcelWriter(buf_lista, engine="openpyxl") as writer:
                df_creds_show.drop(columns=[""]).to_excel(writer, index=False, sheet_name="Creditos")
            status_lbl = "+".join(status_sel) if status_sel else "Todos"
            st.download_button(
                f"📥 Exportar Excel ({len(creds_tab)} crédito{'s' if len(creds_tab) != 1 else ''} — {status_lbl})",
                data=buf_lista.getvalue(),
                file_name=f"creditos_{status_lbl.lower()}_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_lista_creditos",
            )
            st.markdown("---")

            # Uma linha por crédito, com 💸 (baixar/registrar consumo) e 🗑️
            # (excluir) direto ali — sem precisar abrir outra aba e escolher de
            # novo o mesmo crédito num dropdown.
            _col_w = [0.3, 2.2, 0.9, 1.1, 1.1, 1.1, 1.0, 1.0, 0.55, 0.55]
            hcols = st.columns(_col_w)
            for h, label in zip(hcols, ["", "Cliente", "NF", "Original", "Utilizado",
                                         "Saldo", "Vencimento", "Status", "", ""]):
                if label:
                    h.markdown(f"**{label}**")

            for cr in creds_tab:
                saldo = (cr.get("valor_original") or 0) - (cr.get("valor_utilizado") or 0)
                venc  = pd.to_datetime(cr.get("data_vencimento"), errors="coerce")
                dias  = int((venc - hoje3).days) if pd.notna(venc) else None
                alerta = _status_dot(cr["status"], dias)
                venc_str = venc.strftime("%d/%m/%Y") if pd.notna(venc) else "—"

                rc = st.columns(_col_w)
                rc[0].markdown(alerta)
                rc[1].markdown(cr.get("cliente_nome", "—"))
                rc[2].markdown(_nf_label(cr.get("numero_nf")))
                rc[3].markdown(brl(cr.get("valor_original")))
                rc[4].markdown(brl(cr.get("valor_utilizado")))
                rc[5].markdown(brl(saldo))
                rc[6].markdown(venc_str)
                rc[7].markdown(cr["status"])

                pode_consumir = cr["status"] != "CANCELADO" and saldo > 0
                with rc[8]:
                    if pode_consumir:
                        if st.button("💸", key=f"btn_consumo_{cr['id']}", help="Registrar consumo"):
                            _abrir_dialog_consumo(cr)

                with rc[9]:
                    if st.button("🗑️", key=f"btn_del_{cr['id']}", help="Excluir crédito"):
                        _abrir_dialog_excluir(cr)

            st.markdown("---")

            # Editar detalhes de um crédito (valor, vencimento, status, NF, contrato, obs)
            # — excluir agora é direto na linha da tabela (🗑️ acima).
            with st.expander("✏️ Editar detalhes de um crédito"):
                opts_edit = {
                    f"{cr.get('cliente_nome','?')} — {_nf_label(cr.get('numero_nf'))} — "
                    f"{brl(cr.get('valor_original'))} (#{cr['id']})": cr
                    for cr in creds_tab
                }
                sel_edit_label = st.selectbox("Crédito:", list(opts_edit.keys()), key="sel_edit_cred")
                cr_edit = opts_edit[sel_edit_label]

                # Mesmas opções de NF/contrato do cadastro (➕ Novo Crédito), só que
                # já pré-selecionadas com o que o crédito tem hoje.
                notas_cl_edit = _nota_by_cli.get(cr_edit.get("cliente_id"), [])
                nf_opts_edit  = {"— Sem NF —": None}
                nf_opts_edit.update({f"NF {n['numero_nf']}": n["id"] for n in notas_cl_edit})
                nf_labels_edit = list(nf_opts_edit.keys())
                nf_atual_idx = next(
                    (i for i, v in enumerate(nf_opts_edit.values()) if v == cr_edit.get("nota_fiscal_id")), 0
                )

                contratos_cl_edit = _get_cont_by_cli().get(cr_edit.get("cliente_id"), [])
                ct_opts_edit = {"— Sem contrato —": None}
                ct_opts_edit.update({
                    f"{ct.get('contratante','?')} ({ct.get('empresa_gg','—')}) · {ct.get('tipo_contrato','—')}": ct.get("id")
                    for ct in contratos_cl_edit
                })
                ct_labels_edit = list(ct_opts_edit.keys())
                ct_atual_idx = next(
                    (i for i, v in enumerate(ct_opts_edit.values()) if v == cr_edit.get("contrato_id")), 0
                )

                with st.form(f"form_edit_cred_{cr_edit['id']}"):
                    ce1, ce2 = st.columns(2)
                    with ce1:
                        novo_valor, _ = _valor_input(
                            "Valor original (R$)", key=f"edit_valor_{cr_edit['id']}",
                            valor_atual=float(cr_edit.get("valor_original") or 0),
                        )
                    venc_atual = pd.to_datetime(cr_edit.get("data_vencimento"), errors="coerce")
                    novo_venc = ce2.date_input(
                        "Vencimento", key=f"edit_venc_{cr_edit['id']}",
                        value=venc_atual.date() if pd.notna(venc_atual) else date.today() + timedelta(days=30),
                    )
                    status_opts = ["VÁLIDO", "EXPIRADO", "UTILIZADO", "CANCELADO"]
                    novo_status = st.selectbox(
                        "Status", status_opts, key=f"edit_status_{cr_edit['id']}",
                        index=status_opts.index(cr_edit.get("status")) if cr_edit.get("status") in status_opts else 0,
                    )
                    novo_nf_label = st.selectbox(
                        "NF vinculada", nf_labels_edit, index=nf_atual_idx, key=f"edit_nf_{cr_edit['id']}",
                    )
                    novo_ct_label = st.selectbox(
                        "Contrato vinculado", ct_labels_edit, index=ct_atual_idx, key=f"edit_ct_{cr_edit['id']}",
                    )
                    nova_obs = st.text_area(
                        "Observações", key=f"edit_obs_{cr_edit['id']}",
                        value=cr_edit.get("observacoes") or "", height=80,
                    )
                    if st.form_submit_button("💾 Salvar alterações", use_container_width=True):
                        if novo_valor is None:
                            st.error("❌ Informe um valor válido antes de salvar.")
                        else:
                            update_credito(cr_edit["id"], {
                                "valor_original":  float(novo_valor),
                                "data_vencimento": str(novo_venc),
                                "status":          novo_status,
                                "nota_fiscal_id":  nf_opts_edit[novo_nf_label],
                                "contrato_id":     ct_opts_edit[novo_ct_label],
                                "observacoes":     nova_obs or None,
                            })
                            st.session_state["_edit_cred_ok"] = (
                                f"✅ Crédito de {cr_edit.get('cliente_nome','?')} atualizado!"
                            )
                            _clear_and_rerun()

                st.markdown("---")
                movs_do_credito = [m for m in movs_all if m.get("credito_id") == cr_edit["id"]]
                if movs_do_credito:
                    st.warning(
                        f"⚠️ Este crédito tem {len(movs_do_credito)} movimentação(ões) registrada(s). "
                        f"Excluir apaga esse histórico de uso junto — normalmente é mais seguro "
                        f"editar o valor/status acima do que excluir. Se ainda assim quiser apagar, "
                        f"apague antes as movimentações (aba Movimentações) ou confirme abaixo."
                    )
                confirma_excluir = st.checkbox(
                    "Confirmo que quero excluir este crédito permanentemente",
                    key=f"confirma_del_cred_{cr_edit['id']}",
                )
                if st.button("🗑️ Excluir crédito", key=f"btn_del_cred_{cr_edit['id']}",
                             disabled=not confirma_excluir):
                    delete_credito(cr_edit["id"])
                    st.session_state["_edit_cred_ok"] = (
                        f"🗑️ Crédito de {cr_edit.get('cliente_nome','?')} excluído."
                    )
                    _clear_and_rerun()

            # Expirar crédito individual
            with st.expander("⏰ Expirar um crédito manualmente"):
                validos_tab = [cr for cr in creds_tab if cr["status"] == "VÁLIDO"]
                if validos_tab:
                    opts_exp = {
                        f"{cr.get('cliente_nome','?')} — {_nf_label(cr.get('numero_nf'))} (#{cr['id']})": cr["id"]
                        for cr in validos_tab
                    }
                    sel_exp = st.selectbox("Crédito:", list(opts_exp.keys()), key="sel_exp")
                    if st.button("⏰ Confirmar expiração", key="btn_exp"):
                        update_credito(opts_exp[sel_exp], {"status": "EXPIRADO"})
                        _clear_and_rerun()
                else:
                    st.info("Nenhum crédito válido para expirar.")

    if cred_action == "➕ Novo Crédito":
        # Confirmação do último cadastro — fica visível até a próxima ação
        # (antes sumia junto com o rerun, e por não notar que já tinha
        # funcionado, cadastros repetidos sem querer criavam créditos duplicados).
        if st.session_state.get("_novo_cred_ok"):
            st.success(st.session_state.pop("_novo_cred_ok"))

        cli_opts_nc = {c["nome"]: c["id"] for c in clientes_all}
        clic1, clic2 = st.columns(2)
        cli_sel = clic1.selectbox(
            "Cliente já cadastrado (clique e digite pra buscar)",
            ["— Nenhum —"] + list(cli_opts_nc.keys()), key="cli_sel_novo_cred",
        )
        cli_novo = clic2.text_input(
            "Ou nome de um cliente novo", placeholder="ex: Empresa XYZ Ltda",
            help="Se o cliente ainda não está cadastrado, digite o nome aqui — ele é "
                 "criado automaticamente junto com o crédito.",
        )
        cli_id_sel = cli_opts_nc.get(cli_sel) if cli_sel != "— Nenhum —" else None
        notas_cl   = _nota_by_cli.get(cli_id_sel, []) if cli_id_sel else []
        nf_opts    = {"— Sem NF —": None}
        nf_opts.update({f"NF {n['numero_nf']}": n["id"] for n in notas_cl})

        with st.form("form_novo_cred_dash", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                valor, _ = _valor_input("Valor (R$) *", key="valor_novo_cred",
                                         help="Digite o valor real do crédito antes de cadastrar.")
            venc   = c2.date_input("Vencimento *", value=date.today() + timedelta(days=30),
                                    help="Data até quando o crédito vale. Ajuste conforme o combinado com o cliente.")
            nfc1, nfc2 = st.columns(2)
            nf_sel  = nfc1.selectbox("NF já cadastrada (opcional)", list(nf_opts.keys()))
            nf_nova = nfc2.text_input(
                "Ou número de uma NF nova", placeholder="ex: 6640",
                help="Se a NF ainda não existe no sistema, digite o número aqui — ela é "
                     "criada e já vinculada a este crédito, sem precisar ir na aba Notas Fiscais antes.",
            )

            with st.expander("➕ Mais detalhes (opcional)"):
                obs = st.text_area("Observações", height=80)
                contratos_flat = [
                    ct for lst in _get_cont_by_cli().values() for ct in lst
                    if ct.get("status_real") not in ("ENCERRADO", "RESCINDIDO")
                ]
                ct_opts = {"— Sem contrato —": None}
                ct_opts.update({
                    f"{ct.get('contratante','?')} ({ct.get('empresa_gg','—')}) · {ct.get('tipo_contrato','—')}": ct.get("id")
                    for ct in contratos_flat
                })
                ct_sel = st.selectbox("Contrato vinculado", list(ct_opts.keys()))

            if st.form_submit_button("➕ Cadastrar crédito", use_container_width=True):
                if cli_sel == "— Nenhum —" and not cli_novo.strip():
                    st.error("❌ Escolha um cliente já cadastrado ou digite o nome de um novo.")
                elif cli_sel != "— Nenhum —" and cli_novo.strip():
                    st.error("❌ Escolha um cliente já cadastrado OU digite um novo — não os dois.")
                elif valor is None:
                    st.error("❌ Informe um valor válido antes de cadastrar.")
                elif valor < 1:
                    st.error(f"❌ Valor muito baixo ({brl(valor)}). "
                             f"Confirme se digitou o valor certo antes de cadastrar.")
                elif nf_nova.strip() and nf_sel != "— Sem NF —":
                    st.error("❌ Escolha uma NF já cadastrada OU digite uma nova — não os dois.")
                else:
                    cli_id_final = cli_id_sel
                    cli_nome_final = cli_sel
                    if cli_novo.strip():
                        cli_id_final = insert_cliente({"nome": cli_novo.strip()})
                        cli_nome_final = cli_novo.strip()

                    nota_fiscal_id_sel = nf_opts[nf_sel]
                    if nf_nova.strip():
                        nota_fiscal_id_sel = insert_nota({
                            "numero_nf":    nf_nova.strip(),
                            "cliente_id":   cli_id_final,
                            "data_emissao": str(date.today()),
                            "valor_total":  float(valor),
                        })
                    payload = {
                        "cliente_id":      cli_id_final,
                        "nota_fiscal_id":  nota_fiscal_id_sel,
                        "valor_original":  float(valor),
                        "data_vencimento": str(venc),
                        "observacoes":     obs or None,
                        "contrato_id":     ct_opts[ct_sel],
                    }
                    try:
                        insert_credito(payload)
                        st.session_state["_novo_cred_ok"] = f"✅ Crédito de {brl(valor)} cadastrado para {cli_nome_final}!"
                        _clear_and_rerun()
                    except Exception as e:
                        if "contrato_id" in str(e):
                            # Coluna contrato_id ainda não existe na tabela do Supabase —
                            # cadastra o crédito mesmo assim, só sem o vínculo com o contrato.
                            try:
                                payload.pop("contrato_id")
                                insert_credito(payload)
                                msg = f"✅ Crédito de {brl(valor)} cadastrado para {cli_nome_final}!"
                                if ct_opts[ct_sel] is not None:
                                    msg += (" ⚠️ O vínculo com o contrato não foi salvo — falta "
                                             "uma coluna no banco (peça pra rodar a migração "
                                             "pendente do Supabase).")
                                st.session_state["_novo_cred_ok"] = msg
                                _clear_and_rerun()
                            except Exception as e2:
                                st.error(f"❌ Não foi possível cadastrar o crédito: {e2}")
                        else:
                            st.error(f"❌ Não foi possível cadastrar o crédito: {e}")

    if cred_action == "💸 Registrar Consumo":
        if st.session_state.get("_consumo_ok"):
            st.success(st.session_state.pop("_consumo_ok"))

        # Aceita qualquer crédito com saldo, mesmo EXPIRADO — só CANCELADO fica
        # de fora. Ver mesma regra no bloco de busca da aba Lista.
        creds_validos = [
            c for c in creditos_all
            if c["status"] != "CANCELADO"
            and ((c.get("valor_original") or 0) - (c.get("valor_utilizado") or 0)) > 0
        ]
        if not creds_validos:
            st.info("Nenhum crédito com saldo disponível.")
        else:
            # Filtro por cliente primeiro, pra não ter que procurar num dropdown
            # gigante com todo mundo junto.
            cli_opts_consumo = {c["nome"]: c["id"] for c in clientes_all}
            cli_f_consumo = st.selectbox("Cliente", ["Todos"] + list(cli_opts_consumo.keys()),
                                          key="cli_f_consumo")
            cli_id_f_consumo = cli_opts_consumo.get(cli_f_consumo) if cli_f_consumo != "Todos" else None
            creds_filtrados = [c for c in creds_validos
                                if not cli_id_f_consumo or c["cliente_id"] == cli_id_f_consumo]
            if busca_nf:
                termo_c = busca_nf.strip().lower()
                creds_filtrados = [c for c in creds_filtrados
                                    if termo_c in str(c.get("numero_nf") or "").lower()
                                    or termo_c in str(c.get("cliente_nome") or "").lower()]

            if not creds_filtrados:
                st.info("Nenhum crédito válido para esse cliente.")
            else:
                # Rótulo inclui o id pra nunca colidir entre créditos "iguais"
                # (mesmo cliente, mesma NF, mesmo saldo) — já vi isso acontecer.
                opts = {
                    f"{c.get('cliente_nome','?')} — {_nf_label(c.get('numero_nf'))} — "
                    f"Saldo: {brl((c['valor_original'] or 0)-(c['valor_utilizado'] or 0))}"
                    f"{' ⚠️ EXPIRADO' if c['status'] == 'EXPIRADO' else ''} (#{c['id']})": c
                    for c in creds_filtrados
                }
                # Fora do form: selecionar outro crédito atualiza o saldo na hora,
                # em vez de só mudar depois de enviar (o que já causou confusão de
                # "saldo não bate" — a tela ficava mostrando o crédito anterior).
                label = st.selectbox("Crédito *", list(opts.keys()), key="consumo_cred_sel")
                cr    = opts[label]
                _render_form_consumo(cr)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MOVIMENTAÇÕES
# ══════════════════════════════════════════════════════════════════════════════
if main_tab == "📋 Movimentações":
    import io
    if st.session_state.get("_del_mov_ok"):
        st.success(st.session_state.pop("_del_mov_ok"))

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

        with st.expander("🗑️ Apagar uma movimentação errada"):
            movs_no_filtro = df_m.to_dict("records")
            opts_del = {
                f"{(m.get('data').strftime('%d/%m/%Y') if pd.notna(m.get('data')) else '—')} — "
                f"{m.get('cliente_nome','?')} — {m.get('descricao_servico') or m.get('tipo','')} — "
                f"{brl(m.get('valor'))} (#{m['id']})": m
                for m in movs_no_filtro
            }
            sel_del_label = st.selectbox("Movimentação:", list(opts_del.keys()), key="sel_del_mov")
            mov_del = opts_del[sel_del_label]
            st.caption("Isso também devolve o valor pro saldo do crédito (desfaz o consumo).")
            if st.button("🗑️ Confirmar exclusão", key="btn_del_mov"):
                cred = next((c for c in creditos_all if c["id"] == mov_del.get("credito_id")), None)
                if cred and mov_del.get("tipo") in ("UTILIZAÇÃO", "USO"):
                    novo_ut = max(0, (cred.get("valor_utilizado") or 0) - (mov_del.get("valor") or 0))
                    novo_st = "VÁLIDO" if novo_ut < (cred.get("valor_original") or 0) else cred.get("status")
                    update_credito(cred["id"], {"valor_utilizado": novo_ut, "status": novo_st})
                delete_movimentacao(mov_del["id"])
                st.session_state["_del_mov_ok"] = "✅ Movimentação apagada e saldo do crédito corrigido."
                _clear_and_rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — RELATÓRIO MENSAL
# ══════════════════════════════════════════════════════════════════════════════
if main_tab == "📑 Relatório Mensal":
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
