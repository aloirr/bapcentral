"""Trava do escopo de bap_automation.FAROIS_WEB (T-0013, T-0017, T-0022,
T-0024): a lista PERMITIDA dos faróis que o robô leva ao site, num lugar só.

Depois do lote 2 da T-0024 no main (PR #91, 0bb251b):
- os faróis OBRIGATÓRIOS (os da T-0017, o vc_meta da T-0022 e os 5 do lote 2,
  FAROIS_LOTE2) têm de estar em FAROIS_WEB, cada um com a fonte do "baixado
  em", a tabela de recorte (ou o aviso "Sem filtro por estado") e a regra de
  UF escritas aqui, à mão;
- a lista PERMITIDA é a dos obrigatórios mais o Fretes da T-0037
  (FAROIS_T0037): um farol fora dela reprova.

Regra citada: RN-GER-006 (estado do faturamento e do estoque = filial da
nota; fretes e carteira = UF do cliente; sem a UF, o farol vai sem recortes e
com o aviso).

Formas da regra de UF (o 1º item diz qual):
- ("tabela", título, coluna, modo): cartão por estado pela tabela de recorte
  (_TABELA_RECORTE_WEB), com a coluna e a conversão de _UF_LINHAS_WEB
  ("filial" = filial da nota | "uf" = UF do cliente);
- ("kpis_uf",): o cartão do estado é o do PC com o filtro UF
  (RIDS_KPIS_POR_UF_WEB, montar_por_uf_web);
- ("meta",): os recortes do Farol de Metas (RID_META_WEB, T-0022);
- ("sem_estado",): sem recorte; o farol leva o aviso "Sem filtro por estado".

Para pôr um farol novo no site: acrescente-o aqui, com a regra, no mesmo PR.
"""
from pathlib import Path

AVISO_SEM_ESTADO = "Sem filtro por estado: os cartões mostram a BAP inteira."

# T-0024, lote 2 (PR #91, no main desde 0bb251b): obrigatórios, cada um com a sua regra
FAROIS_LOTE2 = {
    "pv_indicadores": ("sem_estado",),
    "vc_base": ("kpis_uf",),
    "vc_planner": ("sem_estado",),
    "pl_giro": ("tabela", "Todos os produtos", "FILIAL", "filial"),
    "pl_frw": ("tabela", "Estoque FRW", "FILIAL", "filial"),
}
# os faróis do main: T-0017, o vc_meta da T-0022 e o lote 2 da T-0024
REGRA_UF_OBRIGATORIOS = {
    "pl_inadimplencia": ("tabela", "Títulos", "FILIAL", "filial"),
    "pv_pedidos": ("tabela", "Pedidos", "FILIAL", "filial"),
    "pl_entregas": ("tabela", "Entregas", "UF", "uf"),
    "vc_visitas": ("sem_estado",),
    "vc_meta": ("meta",),
    **FAROIS_LOTE2,
}
FAROIS_OBRIGATORIOS = frozenset(REGRA_UF_OBRIGATORIOS)
# T-0037 (Fretes, contrato §10.12): pode estar lá (permitido, não obrigatório
# até entrar no main); fretes = UF do cliente
FAROIS_T0037 = {
    "pl_fretes": ("tabela", "Notas com frete", "UF", "uf"),
}
REGRA_UF_PERMITIDOS = {**REGRA_UF_OBRIGATORIOS, **FAROIS_T0037}
FAROIS_PERMITIDOS = frozenset(REGRA_UF_PERMITIDOS)
assert len(REGRA_UF_OBRIGATORIOS) == 5 + len(FAROIS_LOTE2)   # sem repetição
assert not FAROIS_OBRIGATORIOS & set(FAROIS_T0037)

_KPI_FICTICIO = [{"rotulo": "Itens", "valor": "1", "cor": "ok"}]


def _fonte_ok(fonte) -> bool:
    return (isinstance(fonte, tuple) and len(fonte) == 2
            and isinstance(fonte[0], Path)
            and isinstance(fonte[1], str) and bool(fonte[1].strip()))


def _problemas_regra(ba, rid, regra) -> list:
    """O que falta no robô para a regra de UF do farol (lista vazia = ok)."""
    tab_rec = getattr(ba, "_TABELA_RECORTE_WEB", {})
    uf_linhas = getattr(ba, "_UF_LINHAS_WEB", {})
    kpis_uf = tuple(getattr(ba, "RIDS_KPIS_POR_UF_WEB", ()))
    forma, saida = regra[0], []
    if forma == "tabela":
        _f, titulo, coluna, modo = regra
        if tab_rec.get(rid) != titulo:
            saida.append(f"{rid}: tabela de recorte {tab_rec.get(rid)!r}, "
                         f"esperado {titulo!r}")
        if uf_linhas.get((rid, titulo)) != (coluna, modo):
            saida.append(f"{rid}: regra de UF {uf_linhas.get((rid, titulo))!r}"
                         f", esperado {(coluna, modo)!r}")
    elif forma == "kpis_uf":
        if rid not in kpis_uf:
            saida.append(f"{rid}: fora de RIDS_KPIS_POR_UF_WEB")
        if rid in tab_rec:
            saida.append(f"{rid}: kpis_uf não leva tabela de recorte")
        rec = ba.selecionar_farol_web(
            rid, {"titulo": "Farol fictício", "kpis": _KPI_FICTICIO},
            por_uf={"AM": {"kpis": [dict(k, valor="2")
                                    for k in _KPI_FICTICIO]}})
        if rec.get("recortes") != {"AM": {"kpis": [dict(_KPI_FICTICIO[0],
                                                        valor="2")]}}:
            saida.append(f"{rid}: o cartão do estado não é o do PC com UF")
    elif forma == "meta":
        if rid != getattr(ba, "RID_META_WEB", None):
            saida.append(f"{rid}: não é o RID_META_WEB")
    elif forma == "sem_estado":
        if rid in tab_rec or rid in kpis_uf:
            saida.append(f"{rid}: sem_estado não leva recorte")
        sel = ba.selecionar_farol_web(
            rid, {"titulo": "Farol fictício", "kpis": _KPI_FICTICIO})
        if sel.get("recortes"):
            saida.append(f"{rid}: sem_estado com recortes")
        if AVISO_SEM_ESTADO not in (sel.get("avisos") or []):
            saida.append(f"{rid}: sem o aviso {AVISO_SEM_ESTADO!r}")
    else:
        saida.append(f"{rid}: forma de regra desconhecida {forma!r}")
    return saida


def problemas_escopo(ba) -> list:
    """Função pura sobre o módulo do robô: a lista do que fere a trava do
    escopo (vazia = ok). Recebe o módulo (ou um objeto com os mesmos nomes)."""
    farois = tuple(getattr(ba, "FAROIS_WEB", ()))
    fontes = getattr(ba, "_FONTE_BAIXADO_WEB", {})
    tab_rec = getattr(ba, "_TABELA_RECORTE_WEB", {})
    saida = []
    if len(set(farois)) != len(farois):
        saida.append(f"FAROIS_WEB com repetição: {farois!r}")
    for rid in sorted(FAROIS_OBRIGATORIOS - set(farois)):
        saida.append(f"{rid}: obrigatório e fora de FAROIS_WEB")
    for rid in sorted(set(farois) - FAROIS_PERMITIDOS):
        saida.append(f"{rid}: fora da lista PERMITIDA")
    for rid in sorted(set(farois) & FAROIS_PERMITIDOS):
        if not _fonte_ok(fontes.get(rid)):
            saida.append(f"{rid}: sem a fonte do 'baixado em'")
        saida.extend(_problemas_regra(ba, rid, REGRA_UF_PERMITIDOS[rid]))
    # nenhuma tabela de recorte sobra para farol que não a declarou
    esperadas = {rid: REGRA_UF_PERMITIDOS[rid][1] for rid in farois
                 if REGRA_UF_PERMITIDOS.get(rid, ("",))[0] == "tabela"}
    for rid in sorted(set(tab_rec) - set(esperadas)):
        saida.append(f"{rid}: tabela de recorte sem regra declarada")
    return saida
