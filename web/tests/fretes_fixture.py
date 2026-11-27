"""T-0037: Farol de Fretes fictício (contrato §10.11). Nenhum dado real: "CLIENTE TESTE nn", cidades inventadas."""
from copy import deepcopy

from edicao_fixture import ETAPAS, TRANSP, datas_previsao, datas_reais, farol_entregas_editavel
from farol_fixture import _base, _colunas, _kpi, _ln, _tabela7, pacote_farol

from app import tabelas

CIDADES = ["VILA DO RIO ALTO", "PORTO DO MEIO", "SERRA BONITA"]
UFS = ["PA", "MA", "PA"]
N = 9
TIT = "Notas com frete"


def _kp():
    return [_kpi("Notas com frete", str(N), "neutro", "R$ 86 mil"), _kpi("% do faturado", "7,2%", "info"),
            _kpi("Frete estimado", "R$ 2,9 mil", "neutro", "3,4% do VLR NF"), _kpi("Cidades atendidas", "3"),
            _kpi("Entregues", "3", "ok", "67% no prazo"), _kpi("Sem transportadora", "1", "atencao")]


def tabela_notas():
    cols = _colunas(TIT)
    linhas, tons, ufs = [], [], []
    for i in range(1, N + 1):
        sem_ac = i == 1                           # nota sem linha no acompanhamento: sem chave
        linhas.append(_ln(cols, {
            "MÊS": "NOV/26", "DATA PED.": f"2026-11-{i + 1:02d}", "DATA NF": f"2026-11-{i + 2:02d}",
            "NF": f"7{i + 100:05d}", "FILIAL": "FILIAL FICTICIA", "CLIENTE": f"9{i:05d} - CLIENTE TESTE {i:02d}",
            "CIDADE": CIDADES[i % 3], "UF": UFS[i % 3], "VLR NF": 8000.0 + 310 * i, "VLR FRETE": 240.0 + 9 * i,
            "ETAPA": "(sem acompanhamento)" if sem_ac else ETAPAS[i % 4],
            "TRANSPORTADORA": "" if sem_ac else TRANSP[i % 3], "ENTREGAR ATÉ": f"2026-11-{i + 8:02d}",
            "ENTREGUE": f"2026-11-{i + 7:02d}" if i % 3 == 0 else None, "SLA ENTREGA": None if sem_ac else i % 6,
            "RESPONSÁVEL": "" if sem_ac else f"MOTORISTA FICTICIO {i % 3 + 1}"}))
        tons.append("alerta" if i == 4 else "ok" if i % 3 == 0 else "")
        ufs.append(UFS[i % 3])
    return linhas, tons, ufs, cols


def spec_fretes(cols, linhas):
    nomes = [c["nome"] for c in cols]
    ic = nomes.index("CIDADE")
    return {"modulo": "pos_venda", "acao": "Editar",
            "chaves": ["" if i == 0 else f"FILIAL FICTICIA|{7000 + i}|1" for i in range(len(linhas))],
            "campos": [
                {"campo": "etapa", "rotulo": "ETAPA", "coluna": "ETAPA", "tipo": "lista", "opcoes": ETAPAS},
                {"campo": "transportadora", "rotulo": "TRANSPORTADORA", "coluna": "TRANSPORTADORA", "tipo": "lista",
                 "opcoes": TRANSP, "grupos": [TRANSP[:2], TRANSP[1:]],
                 "grupo_linhas": [0 if ln[ic] == CIDADES[0] else 1 for ln in linhas]},
                {"campo": "prevista_manual", "rotulo": "DT. PREVISTA (ENTREGA)", "coluna": "ENTREGAR ATÉ",
                 "tipo": "data", "opcoes": datas_previsao()},
                {"campo": "entregue_em", "rotulo": "DT. REAL (ENTREGA)", "coluna": "ENTREGUE", "tipo": "data",
                 "opcoes": datas_reais()},
                {"campo": "responsavel", "rotulo": "RESPONSÁVEL (MOTORISTA)", "coluna": "RESPONSÁVEL",
                 "tipo": "texto", "opcoes": ["MOTORISTA FICTICIO 1", "MOTORISTA FICTICIO 2"]}]}


def _resumo(titulo, col, chaves):
    cols = _colunas(titulo, tabelas.COLUNAS_RID[("pl_fretes", titulo)])
    linhas = [_ln(cols, {"MÊS": "NOV/26", col: k, "NOTAS": 3 + j, "VLR NF": 25000.0 + 900 * j,
                         "VLR FRETE": 800.0 + 40 * j}) for j, k in enumerate(chaves)]
    kp = [_kpi("Notas", str(sum(ln[2] for ln in linhas))), _kpi("Valor", "R$ 77 mil"),
          _kpi("Frete estimado", "R$ 2,5 mil")]
    return {"titulo": titulo, "colunas": cols, "linhas": linhas, "kpis_padrao": kp}


def farol_fretes(com_edicao=True):
    linhas, tons, ufs, cols = tabela_notas()
    t = _tabela7(TIT, linhas, tons, [{"coluna": "MÊS", "padrao": "NOV/26", "oculto": True}, "UF", "FILIAL",
                                      "ETAPA", "TRANSPORTADORA"], uf_linhas=ufs, kpis_padrao=_kp())
    if com_edicao:
        t["edicao"] = spec_fretes(cols, linhas)
    f = _base("Farol de Fretes", _kp(), [])
    f["tabelas"] = [t, _resumo("Por UF", "UF", ["MA", "PA"]),
                    _resumo("Por cidade", "CIDADE", [f"{c} / PA" for c in CIDADES]),
                    _resumo("Por transportadora", "TRANSPORTADORA", TRANSP)]
    f["recortes"] = {"PA": {"kpis": _kp()[:3]}, "MA": {"kpis": _kp()[:3]}}
    return f


def pacote_fretes(**mais):
    return deepcopy(pacote_farol(pl_fretes=farol_fretes(), pl_entregas=farol_entregas_editavel(), **mais))
