"""T-0037: Farol de Fretes fictício (contrato §10.12). Nenhum dado real: "CLIENTE TESTE nn", cidades e
transportadoras inventadas. ETAPA, datas, tom e cartões saem de UMA tabela de casos, coerente com o PC
(`relatorios_nucleo.fretes`/`kpis_fretes`): entregue = ETAPA ENTREGUE ou data real; tom "alerta" = sem entrega,
com acompanhamento e prazo vencido (hoje = 24/11/2026); "ok" = com data real; o resto sem tom."""
import json
from copy import deepcopy
from datetime import date

from edicao_fixture import ETAPAS, HOJE, datas_previsao, datas_reais, farol_entregas_editavel
from farol_fixture import _base, _colunas, _kpi, _ln, _tabela7, pacote_farol

from app import tabelas

CIDADES = ["VILA DO RIO ALTO", "PORTO DO MEIO", "SERRA BONITA"]
UFS = ["PA", "MA", "PA"]
TRANSP_F = ["TRANSP. ALFA", "TRANSP. BETA", "TRANSP. GAMA"]      # nomes fictícios curtos
SEM_AC = "(sem acompanhamento)"
TIT = "Notas com frete"

# i: (ETAPA, TRANSPORTADORA, ENTREGAR ATÉ (dia de nov), ENTREGUE (dia de nov ou None), RESPONSÁVEL)
# cidade = CIDADES[i % 3]: grupo 0 (VILA DO RIO ALTO) usa ALFA/BETA; o grupo 1 usa BETA/GAMA
CASOS = {
    1: (SEM_AC, "", 9, None, ""),                                   # sem linha no acompanhamento: sem chave, sem tom
    2: ("ENTREGUE", "TRANSP. BETA", 10, 10, "MOTORISTA FICTICIO 1"),   # no prazo
    3: ("EM TRÂNSITO", "TRANSP. ALFA", 25, None, "MOTORISTA FICTICIO 2"),
    4: ("AGUARDANDO COLETA", "TRANSP. GAMA", 12, None, ""),           # prazo vencido: alerta
    5: ("EM TRÂNSITO", "TRANSP. GAMA", 26, None, "MOTORISTA FICTICIO 1"),
    6: ("ENTREGUE", "TRANSP. BETA", 14, 13, "MOTORISTA FICTICIO 2"),   # no prazo
    7: ("CANCELADA", "TRANSP. GAMA", 27, None, ""),                    # cancelada: sem data
    8: ("AGUARDANDO COLETA", "", 27, None, ""),                        # com chave e sem transportadora
    9: ("ENTREGUE", "TRANSP. ALFA", 17, 18, "MOTORISTA FICTICIO 1"),   # entregue 1 dia depois do prazo
}
N = len(CASOS)
SEM_CIDADE = {1}          # nota sem cidade (UF PA): vira "Sem cidade / PA" no Resumo
SEM_UF = {8}              # nota sem UF: vira "Sem UF" no Resumo


def _nov(d):
    return f"2026-11-{d:02d}" if d else None


def _nf(i):
    return f"7{i + 100:05d}"


def tabela_notas():
    cols = _colunas(TIT)
    linhas, tons, ufs = [], [], []
    for i, (etapa, transp, ate, entregue, resp) in CASOS.items():
        sem_ac = etapa == SEM_AC
        fim = date(2026, 11, entregue) if entregue else HOJE
        linhas.append(_ln(cols, {
            "MÊS": "NOV/26", "DATA PED.": _nov(i + 1), "DATA NF": _nov(i + 2), "NF": _nf(i), "FILIAL": "FILIAL FICTICIA",
            "CLIENTE": f"9{i:05d} - CLIENTE TESTE {i:02d}", "CIDADE": "" if i in SEM_CIDADE else CIDADES[i % 3],
            "UF": "" if i in SEM_UF else UFS[i % 3],
            "VLR NF": 8000.0 + 310 * i, "VLR FRETE": 240.0 + 9 * i, "ETAPA": etapa, "TRANSPORTADORA": transp,
            "ENTREGAR ATÉ": _nov(ate), "ENTREGUE": _nov(entregue),
            "SLA ENTREGA": None if sem_ac else (fim - date(2026, 11, i + 1)).days, "RESPONSÁVEL": resp}))
        vencida = not entregue and not sem_ac and HOJE > date(2026, 11, ate)
        tons.append("alerta" if vencida else "ok" if entregue else "")
        ufs.append("" if i in SEM_UF else UFS[i % 3])
    return linhas, tons, ufs, cols


def _moeda_mil(v):
    return f"R$ {v / 1000:.0f} mil" if v >= 10000 else f"R$ {v / 1000:.1f} mil".replace(".", ",")


def _pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "0%"


def _kp(uf=None, pct_fat="7,2%"):
    """Os 6 cartões calculados das linhas de CASOS, como o kpis_fretes do PC."""
    ls = [ln for ln, u in zip(*tabela_notas()[0:3:2]) if uf is None or u == uf]
    nomes = [c[0] for c in tabelas.COLUNAS[TIT]]
    ix = {n: nomes.index(n) for n in nomes}
    val = sum(ln[ix["VLR NF"]] for ln in ls)
    fr = sum(ln[ix["VLR FRETE"]] for ln in ls)
    entregues = [ln for ln in ls if ln[ix["ENTREGUE"]] or ln[ix["ETAPA"]] == "ENTREGUE"]
    com_data = [ln for ln in ls if ln[ix["ENTREGUE"]]]
    no_prazo = [ln for ln in com_data if ln[ix["ENTREGUE"]] <= ln[ix["ENTREGAR ATÉ"]]]
    sem_tr = sum(1 for ln in ls if ln[ix["ETAPA"]] != SEM_AC and not ln[ix["TRANSPORTADORA"]])
    return [_kpi("Notas com frete", str(len(ls)), "neutro", _moeda_mil(val)), _kpi("% do faturado", pct_fat, "info"),
            _kpi("Frete estimado", _moeda_mil(fr), "neutro", f"{100 * fr / val:.1f}% do valor".replace(".", ",")),
            _kpi("Cidades atendidas", str(len({ln[ix['CIDADE']] for ln in ls}))),
            _kpi("Entregues", str(len(entregues)), "ok",
                 f"{_pct(len(no_prazo), len(com_data))} no prazo" if com_data else ""),
            _kpi("Sem transportadora", str(sem_tr), "atencao")]


def spec_fretes(cols, linhas):
    nomes = [c["nome"] for c in cols]
    ic, inf = nomes.index("CIDADE"), nomes.index("NF")
    return {"modulo": "pos_venda", "acao": "Editar",
            "chaves": ["" if ln[nomes.index("ETAPA")] == SEM_AC else f"FILIAL FICTICIA|{ln[inf]}|1" for ln in linhas],
            "campos": [
                {"campo": "etapa", "rotulo": "ETAPA", "coluna": "ETAPA", "tipo": "lista", "opcoes": ETAPAS},
                {"campo": "transportadora", "rotulo": "TRANSPORTADORA", "coluna": "TRANSPORTADORA", "tipo": "lista",
                 "opcoes": TRANSP_F, "grupos": [TRANSP_F[:2], TRANSP_F[1:]],
                 "grupo_linhas": [0 if ln[ic] == CIDADES[0] else 1 for ln in linhas]},
                {"campo": "prevista_manual", "rotulo": "DT. PREVISTA (ENTREGA)", "coluna": "ENTREGAR ATÉ",
                 "tipo": "data", "opcoes": datas_previsao()},
                {"campo": "entregue_em", "rotulo": "DT. REAL (ENTREGA)", "coluna": "ENTREGUE", "tipo": "data",
                 "opcoes": datas_reais()},
                {"campo": "responsavel", "rotulo": "RESPONSÁVEL (MOTORISTA)", "coluna": "RESPONSÁVEL",
                 "tipo": "texto", "opcoes": ["MOTORISTA FICTICIO 1", "MOTORISTA FICTICIO 2"]}]}


def rotulo_agrupa(col, ln, nb):
    """Espelho de relatorios_nucleo.rotulo_agrupa_fretes (faróis 48c6577): o rótulo das tabelas Por UF, Por cidade e
    Por transportadora sai pronto do PC. Nota sem acompanhamento (sem chave) e sem transportadora vai para
    "Sem acompanhamento"; "Sem transportadora" tem o mesmo critério do cartão."""
    v = (ln[nb.index(col)] or "").strip()
    if col == "UF":
        return v or "Sem UF"
    if col == "CIDADE":
        return (v or "Sem cidade") + " / " + ((ln[nb.index("UF")] or "").strip() or "Sem UF")
    if not v:
        return "Sem acompanhamento" if ln[nb.index("ETAPA")] == SEM_AC else "Sem transportadora"
    return v


def _resumo(titulo, col):
    """Agrega as linhas de tabela_notas por `col` (a soma bate com os cartões e com a aba Notas); ordem do PC: VLR NF."""
    base, _, _, bcols = tabela_notas()
    nb = [c["nome"] for c in bcols]
    grupos: dict = {}
    for ln in base:
        g = grupos.setdefault(rotulo_agrupa(col, ln, nb), [0, 0.0, 0.0])
        g[0] += 1
        g[1] += ln[nb.index("VLR NF")]
        g[2] += ln[nb.index("VLR FRETE")]
    cols = _colunas(titulo, tabelas.COLUNAS_RID[("pl_fretes", titulo)])
    linhas = [_ln(cols, {"MÊS": "NOV/26", col: k, "NOTAS": n, "VLR NF": v, "VLR FRETE": fr})
              for k, (n, v, fr) in sorted(grupos.items(), key=lambda kv: -kv[1][1])]
    k = _kp()
    kp = [_kpi("Notas", k[0]["valor"]), _kpi("Valor", k[0]["detalhe"]), _kpi("Frete estimado", k[2]["valor"])]
    return {"titulo": titulo, "colunas": cols, "linhas": linhas, "kpis_padrao": kp}


MESES12 = ["DEZ/25", "JAN/26", "FEV/26", "MAR/26", "ABR/26", "MAI/26", "JUN/26", "JUL/26", "AGO/26", "SET/26", "OUT/26",
           "NOV/26"]
NOTAS12 = [4, 5, 5, 6, 7, 6, 8, 7, 9, 8, 10]                     # dez/25 a out/26 (inventado); nov/26 vem das CASOS
TABELAS_RESUMO = (("Por UF", "UF"), ("Por cidade", "CIDADE"), ("Por transportadora", "TRANSPORTADORA"))


def blocos_resumo_web(r):
    """Espelho de bap_automation.blocos_resumo_fretes_web (robô, T-0037 91e6f8a), campo a campo: o gráfico de 12 meses
    como `barras`; as tabelas do mês padrão como `tabela` (sem MÊS, com TOTAL); e as 2 frases como `insights`."""
    import relatorios_nucleo as rn
    blocos, linha = [], 0
    for g in r.get("graficos") or []:
        if g.get("rotulos"):
            blocos.append({"tipo": "barras", "row": linha, "col": 0, "colspan": 3, "grafico": g})
            linha += 1
            break
    por_titulo = {t["titulo"]: t for t in r["tabelas"]}
    agreg = {}
    for titulo, rot in TABELAS_RESUMO:
        t = por_titulo[titulo]
        nomes = [c["nome"] for c in t["colunas"]]
        mes = next(f["padrao"] for f in t["filtros"] if f["coluna"] == "MÊS")
        im, ir = nomes.index("MÊS"), nomes.index(rot)
        ls = [[l[ir], l[nomes.index("NOTAS")], l[nomes.index("VLR NF")] or 0,
               l[nomes.index("VLR FRETE")] or 0] for l in t["linhas"] if l[im] == mes]
        ls.sort(key=lambda x: -x[2])
        tot = ["TOTAL", sum(x[1] or 0 for x in ls), round(sum(x[2] for x in ls), 2), round(sum(x[3] for x in ls), 2)]
        agreg[titulo] = [list(x) for x in ls]
        ls = [[x[0], x[1], round(x[2], 2), round(x[3], 2)] for x in ls]
        cols = [{"nome": rot, "tipo": "texto", "largura": 140, "oculta": False},
                {"nome": "NOTAS", "tipo": "int", "largura": 70, "oculta": False},
                {"nome": "VLR NF", "tipo": "moeda", "largura": 100, "oculta": False},
                {"nome": "VLR FRETE", "tipo": "moeda", "largura": 100, "oculta": False}]
        blocos.append({"tipo": "tabela", "titulo": f"{titulo} ({mes})", "colunas": cols, "linhas": ls, "total": tot,
                       "row": linha, "col": 0})
        linha += 1
    frases = []
    ufs = agreg["Por UF"]
    ufs_ok = [x for x in ufs if x[0] != "Sem UF"]
    if len(ufs) > 1 and ufs_ok:
        v_ = sum(x[2] for x in ufs)
        topo = max(ufs_ok, key=lambda x: x[2])
        frases.append(("info", f"{topo[0]} concentra {rn.p(rn.pct_de(topo[2], v_))} do valor das notas com frete."))
    trs = agreg["Por transportadora"]
    tr = [x for x in trs if x[0] not in ("Sem transportadora", "Sem acompanhamento")]
    if tr:
        v_ = sum(x[2] for x in trs)
        t0 = max(tr, key=lambda x: x[2])
        frases.append(("info", f"{t0[0]} leva {rn.p(rn.pct_de(t0[2], v_))} do valor."))
    if frases:
        blocos.append({"tipo": "insights", "titulo": "Resumo gerencial", "linhas": frases, "row": linha, "col": 0})
    return blocos, frases


def tabelas_resumo():
    return [_resumo(t, rot) for t, rot in TABELAS_RESUMO]


def blocos_resumo():
    """A entrada do robô (`r`: gráfico de 12 meses + as 3 tabelas de resumo com o filtro MÊS) passa pela mesma função
    pura do robô; o JSON vai pelo pacote como o robô o grava."""
    n = len(tabela_notas()[0])
    graf = {"titulo": "Mês a mês: notas com frete", "rotulos": MESES12, "formato": "num",
            "series": [{"nome": "notas", "cor": "#1F4FD1", "valores": NOTAS12 + [n]}]}
    tabs = []
    for t in tabelas_resumo():
        t = deepcopy(t)
        t["filtros"] = [{"coluna": "MÊS", "padrao": "NOV/26"}]
        tabs.append(t)
    blocos, frases = blocos_resumo_web({"graficos": [graf], "tabelas": tabs})
    return json.loads(json.dumps(blocos)), json.loads(json.dumps(frases))


def farol_fretes(com_edicao=True, com_resumo=True):
    linhas, tons, ufs, cols = tabela_notas()
    t = _tabela7(TIT, linhas, tons, [{"coluna": "MÊS", "padrao": "NOV/26", "oculto": True}, "UF", "FILIAL",
                                      "ETAPA", "TRANSPORTADORA"], uf_linhas=ufs, kpis_padrao=_kp())
    if com_edicao:
        t["edicao"] = spec_fretes(cols, linhas)
    f = _base("Farol de Fretes", _kp(), blocos_resumo()[0] if com_resumo else [])
    if com_resumo:                                                # o PC manda as frases também em insights_painel
        f["insights_painel"] = blocos_resumo()[1]
    f["tabelas"] = [t] + tabelas_resumo()
    f["recortes"] = {"PA": {"kpis": _kp("PA", "7,1%")}, "MA": {"kpis": _kp("MA", "7,4%")}}
    return f


def pacote_fretes(**mais):
    return deepcopy(pacote_farol(pl_fretes=farol_fretes(), pl_entregas=farol_entregas_editavel(), **mais))
