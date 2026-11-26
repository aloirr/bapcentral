"""T-0025: Farol DDR, Campanhas BAP e Farol de Expositores como o robô manda (100% fictício)."""
from copy import deepcopy

from farol_fixture import _base, _colunas, _kpi, _ln, _tabela7, pacote_farol

DDR_CHAVE = "2026-11|PESSOA FICTICIA|{n}"
STATUS_DDR = ["ENTREGUE", "ENTREGUE PARCIAL", "NÃO ENTREGUE"]
MOTIVOS = ["Indisponibilidade de Sistema", "Sobrecarga Operacional"]


def _spec_ddr(n):
    return {"modulo": "farol", "acao": "Marcar", "chaves": [DDR_CHAVE.format(n=5 + i) for i in range(n)],
            "campos": [{"campo": "status", "rotulo": "STATUS", "coluna": "STATUS", "tipo": "lista",
                        "opcoes": STATUS_DDR},
                       {"campo": "motivo", "rotulo": "MOTIVO (parcial / não entregue)", "coluna": "MOTIVO",
                        "tipo": "lista", "opcoes": MOTIVOS}]}


def farol_ddr(n=4):
    f = _base("Farol DDR · PESSOA", [_kpi("% até hoje", "80%", "atencao"), _kpi("Sem marcação", "2", "alerta")], [])
    hoje = [_ln(_colunas("Hoje"), {"HORÁRIO": "08:00 - 09:00", "ATIVIDADE": f"Atividade fictícia {i}",
                                    "PRIORIDADE": "Alta", "PONTOS": 5, "STATUS": "", "MOTIVO": "",
                                    "FERRAMENTA BAP": "BAP Central"}) for i in range(n)]
    pend = [_ln(_colunas("Pendentes de marcação"), {"DATA": f"2026-11-{3 + i:02d}", "DIA": "TER",
                                                     "HORÁRIO": "08:00", "ATIVIDADE": f"Pendente {i}",
                                                     "PRIORIDADE": "Média", "PONTOS": 3, "STATUS": "", "MOTIVO": "",
                                                     "FERRAMENTA BAP": "Protheus"}) for i in range(n)]
    ate = [_ln(_colunas("Até hoje"), {"DATA": f"2026-11-{3 + i:02d}", "DIA": "TER", "HORÁRIO": "08:00",
                                       "ATIVIDADE": f"Feita {i}", "PRIORIDADE": "Alta", "PONTOS": 5,
                                       "STATUS": "ENTREGUE", "MOTIVO": "", "PONTOS GANHOS": 5.0,
                                       "FERRAMENTA BAP": "E-mail"}) for i in range(n)]
    f["tabelas"] = [dict(_tabela7("Hoje", hoje, [""] * n), edicao=_spec_ddr(n)),
                    dict(_tabela7("Pendentes de marcação", pend, ["atencao"] * n), edicao=_spec_ddr(n)),
                    dict(_tabela7("Até hoje", ate, ["ok"] * n, ["STATUS", "PRIORIDADE"]), edicao=_spec_ddr(n))]
    return f


CHIP_SIT = {"LIBERADO": ["#E5F3DF", "#2F7D32"], "BLOQUEADO": ["#FBDDDA", "#B3261E"]}


def farol_champions():
    f = _base("BAP CHAMPIONS", [_kpi("Líder (vendedor)", "VENDEDOR FICTICIO 01", "ok")], [])
    cols = _colunas("Vendedores")
    for c in cols:
        if c["nome"] == "SITUAÇÃO":
            c["chip"] = deepcopy(CHIP_SIT)
    base = {"POS.": 1, "VENDEDOR": "000001 - VENDEDOR FICTICIO 01", "SUPERVISOR": "SUPERVISOR FICTICIO 01",
            "FAT. BRUTO": 1000.0, "DEVOLUÇÕES": -10.0, "FAT. LÍQUIDO": 990.0, "DESAFIO": 1200.0,
            "% DESAFIO": 82.5, "SITUAÇÃO": "LIBERADO", "PTS FATUR.": 10, "TOTAL A PAGAR": 10}
    vend = {"titulo": "Vendedores", "colunas": cols, "linhas": [_ln(cols, base)], "tons": [""]}
    semanas = [{"nome": n, "tipo": "texto" if n in ("TIPO", "JOGADOR") else "int", "largura": 80, "oculta": False}
               for n in ("TIPO", "JOGADOR", "SEM. 02/11", "SEM. 09/11", "SOMA DAS SEMANAS")]
    pts = {"titulo": "Pts por semana", "colunas": semanas,
           "linhas": [["VENDEDOR", "VENDEDOR FICTICIO 01", 5, 7, 12]]}
    reg = _tabela7("Regras", [["GRUPO FICTICIO", "Regra fictícia", 10]])
    f["tabelas"] = [vend, pts, reg]
    return f


def farol_expositores():
    f = _base("Farol de Expositores", [_kpi("Expositores", "2", "neutro")], [])
    cols = _colunas("Expositores")
    n = 2
    linhas = [_ln(cols, {"STATUS": "Solicitado", "MÊS": "NOV/26", "SOLICITAÇÃO": "2026-11-10", "DIAS": None,
                         "CÓD. CLIENTE": f"9{i:05d}", "CLIENTE": f"CLIENTE FICTICIO {i}",
                         "DESCRIÇÃO DO EXPOSITOR": "EXPOSITOR FICTICIO", "CATEGORIA": "BATERIAS", "QTD": 1,
                         "CIDADE": "MANAUS", "UF": "AM", "OBSERVAÇÕES": "", "ATUALIZADO": "2026-11-10"})
              for i in range(n)]
    datas = [f"{d:02d}/11/2026" for d in range(24, 0, -1)]
    ed = {"modulo": "expositores", "acao": "Editar", "chaves": [f"EXP{i + 1:04d}" for i in range(n)],
          "novo": {"padroes": {"status": "Solicitado", "qtd": "1", "data": "hoje"}},
          "campos": [
              {"campo": "status", "rotulo": "STATUS", "coluna": "STATUS", "tipo": "lista",
               "opcoes": ["Solicitado", "Entregue"]},
              {"campo": "data", "rotulo": "DATA DA SOLICITAÇÃO", "coluna": "SOLICITAÇÃO", "tipo": "data",
               "opcoes": datas},
              {"campo": "cliente", "rotulo": "CLIENTE (código - nome)", "coluna": "CLIENTE", "tipo": "texto",
               "opcoes": [], "caixa": True, "max": 80},
              {"campo": "qtd", "rotulo": "QTD", "coluna": "QTD", "tipo": "lista",
               "opcoes": [str(k) for k in range(1, 21)]},
              {"campo": "observacoes", "rotulo": "OBSERVAÇÕES", "coluna": "OBSERVAÇÕES", "tipo": "texto",
               "opcoes": [], "caixa": True, "max": 200}]}
    exp = dict(_tabela7("Expositores", linhas, [""] * n, [{"coluna": "MÊS", "padrao": "NOV/26", "oculto": True}]),
               edicao=ed)
    uf = _tabela7("Por estado", [["AM", 2, 0, 0, 2, 0, 0, 2, 1]])
    f["tabelas"] = [exp, uf]
    return f


def pacote_t25():
    return pacote_farol(farol_pv=farol_ddr(), farol_vc=farol_ddr(), farol_pl=farol_ddr(),
                        vc_champions=farol_champions(), tm_expositores=farol_expositores())
