"""Separação de impostos nas contas a pagar — regra determinística, só leitura.

Um título é imposto quando a conta dele no PLANO DE CONTAS do eGestor fica no
grupo "Impostos" (ou "Tributos"/"Tributário"), na mesma hierarquia usada pela
página Realizado. Não se adivinha pelo texto da descrição nem pelo fornecedor.
Títulos sem conta (ex.: GoGenetic You, Bling) ficam como não-imposto.
"""
from __future__ import annotations

import unicodedata
from typing import Iterable, Optional

PALAVRAS_GRUPO_IMPOSTO = ("IMPOSTO", "TRIBUT")


def _norm(txt) -> str:
    s = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def plano_info(plano_raw: Iterable[dict]) -> dict:
    """{codigo: {"grupo": nome da raiz, "subgrupo": nome da conta}} — mesma
    lógica de pages/9_Realizado.py (_build_plano_info)."""
    plano = {}
    for p in plano_raw or []:
        try:
            plano[int(p["codigo"])] = p
        except (KeyError, TypeError, ValueError):
            continue

    def _raiz(cod: int, depth: int = 0) -> str:
        if depth > 8 or cod not in plano:
            return "Sem Categoria"
        it = plano[cod]
        pai = int(it.get("codPai") or 0)
        return str(it.get("nome") or "Sem Categoria") if pai == 0 else _raiz(pai, depth + 1)

    return {cod: {"grupo": _raiz(cod), "subgrupo": str(it.get("nome") or "Sem Categoria")}
            for cod, it in plano.items()}


def grupo_e_imposto(nome_grupo) -> bool:
    g = _norm(nome_grupo)
    return any(k in g for k in PALAVRAS_GRUPO_IMPOSTO)


def classificar(item: dict, info: dict) -> Optional[dict]:
    """Devolve {"grupo", "subgrupo"} da conta do título, ou None se sem conta."""
    try:
        return info.get(int(item.get("codPlanoContas")))
    except (TypeError, ValueError):
        return None


def separar(itens: Iterable[dict], info_por_empresa: dict) -> tuple[list, list]:
    """(demais, impostos). Cada item de imposto ganha "tipo_imposto" (subgrupo).
    `info_por_empresa`: {empresa: plano_info(...)} — códigos iguais em empresas
    diferentes são contas diferentes, por isso o plano é por empresa."""
    demais, impostos = [], []
    for it in itens:
        c = classificar(it, info_por_empresa.get(it.get("empresa"), {}))
        if c and grupo_e_imposto(c["grupo"]):
            impostos.append({**it, "tipo_imposto": c["subgrupo"]})
        else:
            demais.append(it)
    return demais, impostos
