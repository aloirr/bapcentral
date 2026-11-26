"""T-0021: a especificação de edição (`edicao`) como o robô manda, sobre a fixture fictícia dos faróis."""
from copy import deepcopy
from datetime import date, timedelta

from farol_fixture import farol_entregas_com_abas, farol_pedidos_com_abas, pacote_farol

HOJE = date(2026, 11, 24)
ETAPAS = ["AGUARDANDO COLETA", "EM TRÂNSITO", "ENTREGUE", "CANCELADA"]
TRANSP = ["TRANSPORTADORA FICTICIA 1", "TRANSPORTADORA FICTICIA 2", "TRANSPORTADORA FICTICIA 3"]


def _br(d):
    return f"{d:%d/%m/%Y}"


def datas_reais():
    return [_br(HOJE - timedelta(days=i)) for i in range(30)]


def datas_previsao():
    return [_br(HOJE + timedelta(days=i)) for i in range(46)] + [_br(HOJE - timedelta(days=i)) for i in range(1, 16)]


def spec_autorizacao(t):
    nomes = [c["nome"] for c in t["colunas"]]
    ich = nomes.index("CHAVE")
    return {"modulo": "autorizacoes", "acao": "Autorização",
            "chaves": [str(ln[ich] or "") for ln in t["linhas"]],
            "campos": [{"campo": "codigo", "rotulo": "CÓD. AUTORIZAÇÃO", "coluna": "CÓD. AUTORIZAÇÃO",
                        "tipo": "texto", "opcoes": [], "caixa": True},
                       {"campo": "por", "rotulo": "AUTORIZADO POR", "coluna": "AUTORIZADO POR",
                        "tipo": "lista", "opcoes": ["ALEXANDRE", "PRICE"]}]}


def spec_entregas(t, prefixo="NF"):
    nomes = [c["nome"] for c in t["colunas"]]
    n = len(t["linhas"])
    ic = nomes.index("CIDADE")
    grupos = [TRANSP[:2], TRANSP[1:]]
    return {"modulo": "pos_venda", "acao": "Editar",
            "chaves": ["" if i == 0 else f"FILIAL FICTICIA|{9000 + i}|1" if prefixo == "NF" else
                       f"FILIAL FICTICIA|{8000 + i}|1" for i in range(n)],
            "campos": [
                {"campo": "etapa", "rotulo": "ETAPA", "coluna": "ETAPA", "tipo": "lista", "opcoes": ETAPAS},
                {"campo": "transportadora", "rotulo": "TRANSPORTADORA", "coluna": "TRANSPORTADORA", "tipo": "lista",
                 "opcoes": TRANSP, "grupos": grupos,
                 "grupo_linhas": [0 if ln[ic] == "MANAUS" else 1 for ln in t["linhas"]]},
                {"campo": "prevista_manual", "rotulo": "DT. PREVISTA (ENTREGA)", "coluna": "DT. PREVISTA",
                 "tipo": "data", "opcoes": datas_previsao()},
                {"campo": "entregue_em", "rotulo": "DT. REAL (ENTREGA)", "coluna": "DT. REAL", "tipo": "data",
                 "opcoes": datas_reais()},
                {"campo": "responsavel", "rotulo": "RESPONSÁVEL (MOTORISTA)", "coluna": "RESPONSÁVEL",
                 "tipo": "texto", "opcoes": ["MOTORISTA FICTICIO 1", "MOTORISTA FICTICIO 2"]},
                {"campo": "frete_real", "rotulo": "VLR FRETE (REAL)", "coluna": "VLR REAL FRETE", "tipo": "numero",
                 "opcoes": [], "linhas": list(range(n)), "sugestoes_linhas": ["250,00"] * n}]}


def farol_pedidos_editavel():
    f = farol_pedidos_com_abas()
    t = f["tabelas"][0]
    t["edicao"] = spec_autorizacao(t)
    return f


def farol_entregas_editavel():
    f = farol_entregas_com_abas()
    t = f["tabelas"][0]
    t["edicao"] = spec_entregas(t)
    jt = t["juntas"][0]["tabela"]
    jt["edicao"] = spec_entregas(jt, "PEND")
    return f


def pacote_editavel(gerado_em="2026-11-24T08:30:00-04:00"):
    p = pacote_farol(pv_pedidos=farol_pedidos_editavel(), pl_entregas=farol_entregas_editavel())
    p["gerado_em"] = gerado_em
    return deepcopy(p)
