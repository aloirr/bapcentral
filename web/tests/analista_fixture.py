"""T-0036: pacote fictício dos 4 faróis do Analista Comercial (contrato §10.9). Tudo inventado: sem nome, CNPJ,
telefone ou e-mail real; o cliente aparece só pelo código fictício (RN-GER-011)."""
from copy import deepcopy

from app import tabelas

MESES = ("2026-10", "2026-11")
_UF = ("AM", "PA", "MA")
_FILIAL = ("MANAUS", "BELEM", "SAO LUIS")


def _valor(nome, tipo, i):
    if nome in ("UF",):
        return _UF[i % 3]
    if nome == "FILIAL":
        return _FILIAL[i % 3]
    if nome in ("CÓD.", "COD", "A1_COD"):
        return f"9{i:05d}-01"
    if nome == "PONTO":
        return "SEM COORDENADA"
    if nome in ("MÊS", "AAAA-MM"):
        return MESES[i % 2]
    if tipo in ("dia", "data"):
        return f"2026-11-{i % 20 + 1:02d}"
    if tipo == "hora":
        return "08:00"
    if tipo == "int":
        return i + 1
    if tipo in ("num", "num1", "num2", "valor", "moeda", "moeda2"):
        return round(100.5 * (i + 1), 2)
    if tipo in ("pct", "pct1"):
        return round(10.0 + i, 1)
    if "VENDEDOR" in nome:
        return f"VENDEDOR FICTICIO {i % 3 + 1:02d}"
    if "SUPERVISOR" in nome:
        return f"SUPERVISOR FICTICIO {i % 2 + 1:02d}"
    if nome in ("CIDADE",):
        return f"CIDADE FICTICIA {i % 3 + 1:02d}"
    return f"{nome[:12]} {i + 1}"


def tabela(rid, titulo, n=6, **extra):
    esp = tabelas.COLUNAS_RID[(rid, titulo)]
    cols = [{"nome": nm, "tipo": tp, "largura": 90, "oculta": o} for nm, tp, o in esp]
    linhas = [[_valor(nm, tp, i) for nm, tp, _ in esp] for i in range(n)]
    t = {"titulo": titulo, "colunas": cols, "linhas": linhas}
    nomes = [c["nome"] for c in cols]
    if "UF" in nomes:
        k = nomes.index("UF")
        t["uf_linhas"] = [ln[k] for ln in linhas]
    t.update(extra)
    return t


KPIS = {
    "vc_saldo": ["Faturado", "Desconto comercial", "Saldo", "Saldo do frete"],
    "vc_markup": ["Venda", "Custo", "Margem", "Markup", "Abaixo do mínimo", "Sem custo", "Em aberto"],
    "vc_preco": ["Faturamento NOV", "Efeito preço", "Efeito volume", "Efeito mix", "Reajustes", "Queda após reajuste"],
    "an_divergencias": ["Clientes na base (Planner)", "Batem", "Vendedor diferente", "Sem vendedor no Planner",
                        "Fora da base do Planner", "Código duplicado", "Sem coordenada / endereço"],
}
TITULOS = {"vc_saldo": "Farol de Saldo", "vc_markup": "Farol de Markup", "vc_preco": "Farol de Preço",
           "an_divergencias": "Divergências clientes Planner x Protheus"}


def farol(rid, n=6):
    f = {"forma": "farol", "titulo": TITULOS[rid],
         "kpis": [{"rotulo": r, "valor": f"{(i + 1) * 12},5", "cor": ("ok", "atencao", "neutro")[i % 3],
                   "detalhe": "dado fictício"} for i, r in enumerate(KPIS[rid])],
         "painel": {"blocos": [{"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
                                "linhas": [["info", "Frase fictícia do farol."]]}]},
         "insights_painel": [["info", "Frase fictícia do farol."]], "avisos": [],
         "baixado_em": "2026-11-24T08:10:00-04:00",
         "tabelas": [tabela(rid, t, n) for _, t in tabelas.ABAS[rid]]}
    if rid == "vc_saldo":                      # recorte por estado (o robô confere o kpis_de; §10.9.1)
        f["recortes"] = {uf: {"kpis": f["kpis"]} for uf in _UF}
    return f


def correcao():
    cor = [[f"01", f"9{i:05d}", "01", f"CIDADE FICTICIA {i}", "AM", "V001", "V002", f"VENDEDOR FICTICIO {i}",
            "SUPERVISOR FICTICIO 01", "ATIVO"] for i in range(3)]
    ana = [["01", f"9{i:05d}", "01", f"CIDADE FICTICIA {i}", "AM", "VENDEDOR FICTICIO 01", "V001",
            "SEM VENDEDOR NO PLANNER", "Analisar no Planner"] for i in range(2)]
    return {"corrigir": {"titulo": "CORRIGIR NO PROTHEUS", "linhas": cor, "colunas": [
                {"nome": n, "tipo": "texto"} for n in
                ("A1_FILIAL", "A1_COD", "A1_LOJA", "CIDADE", "UF", "A1_VEND ATUAL", "A1_VEND CORRETO",
                 "VENDEDOR CORRETO", "SUPERVISOR", "STATUS PROTHEUS")]},
            "analisar": {"titulo": "ANALISAR", "linhas": ana, "colunas": [
                {"nome": n, "tipo": "texto"} for n in
                ("A1_FILIAL", "A1_COD", "A1_LOJA", "CIDADE", "UF", "VENDEDOR NO PLANNER", "A1_VEND ATUAL",
                 "SITUAÇÃO", "O QUE FAZER")]}}


RIDS_NOVOS = ("vc_saldo", "vc_markup", "vc_preco", "an_divergencias")


def pacote_analista(com_correcao=True, n=6):
    rels = {rid: farol(rid, n) for rid in RIDS_NOVOS}
    if com_correcao:
        rels["an_divergencias"]["correcao"] = correcao()
    return deepcopy({"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
                     "relatorios": rels})
