"""T-0017, entregas 3 a 5: Farol de Pedidos (pv_pedidos), de Entregas
(pl_entregas) e de Visita (vc_visitas) no pacote da web (forma "farol",
contrato 10.1 de .coord/contratos/relatorio.md).

Regras citadas:
- RN-GER-006: estado do faturamento = filial da nota (Pedidos); fretes,
  Planner e carteira = UF do cliente (Entregas pela coluna UF; Visita não
  tem a UF do cliente e vai sem recortes, com aviso);
- RN-GER-007: hoje fora do DU (o Farol de Visita não cobra o arquivo de
  hoje) e data de hoje no fuso America/Manaus.

Junta os testes do robô (bap_automation) e do modulo-farois
(relatorios_nucleo), sem casos repetidos. O teste antigo que só conferia o
texto da chamada no fonte foi trocado por um de comportamento: pasta de
visitas fictícia em tmp_path, sem o arquivo de hoje.

Dados 100% fictícios (sem cliente, CNPJ, telefone ou nome de pessoa real).
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import bap_automation as ba
import relatorios_nucleo as rn

HOJE = date(2026, 11, 24)                 # terça-feira, NOV/2026
AVISO_SEM_ESTADO = "Sem filtro por estado: os cartões mostram a BAP inteira."
COLS_FRETE = ["UF", "REGIÃO", "NOTAS", "VALOR NF", "FRETE R$", "% S/ NOTA",
              "FRETE/NOTA"]


# ------------------------------------------------------------------ fixture
def _kpis_de(linhas):
    """Cartão fictício: contagem de linhas."""
    return [{"rotulo": "Pedidos", "valor": str(len(linhas)), "cor": "ok"}]


def _tabela(titulo, linhas, mes=None, extra_filtros=()):
    """linhas: (MÊS, FILIAL[, UF do cliente])."""
    colunas = [{"nome": n, "tipo": "texto"}
               for n in ("MÊS", "FILIAL", "VENDEDOR", "UF")]
    corpo = [[m, f, "Vendedor 01", (u[0] if u else "XX")]
             for m, f, *u in linhas]
    filtros = list(extra_filtros)
    if mes:
        filtros.insert(0, {"coluna": "MÊS", "padrao": mes})
    return {"titulo": titulo, "colunas": colunas, "linhas": corpo,
            "filtros": filtros, "kpis_de": _kpis_de,
            "edicao": {"campos": ["x"]}}


def _farol(titulo, tabela, blocos=None, **extra):
    r = {"titulo": titulo, "kpis": [{"rotulo": "Pedidos", "valor": "3"}],
         "tabelas": [tabela], "painel": {"blocos": blocos or []},
         "insights_painel": [["info", "Sem nome de cliente."]], "avisos": [],
         "editar": lambda *a: None, "abrir": "RELATORIOS/x.xlsx",
         "detalhe_pedido": lambda *a: None}
    r.update(extra)
    return r


def _bloco_frete(colunas):
    return {"tipo": "tabela", "titulo": "Frete por estado · NOV/26",
            "colunas": [{"nome": c, "tipo": "texto"} for c in colunas],
            "linhas": [["AM", "NORTE", 3, 100.0, 5.0, 5.0, 1.6]],
            "total": ["TOTAL", "", 3, 100.0, 5.0, 5.0, 1.6],
            "editar": "x", "row": 0, "col": 1, "colspan": 2}


def _valores(recortes):
    return {u: v["kpis"][0]["valor"] for u, v in recortes.items()}


# --------------------------------------------------------- os quatro faróis
def test_RN_GER_006_FAROIS_WEB_tem_os_quatro_farois_com_fonte_e_tabela():
    assert set(ba.FAROIS_WEB) == {"pl_inadimplencia", "pv_pedidos",
                                  "pl_entregas", "vc_visitas"}
    for rid in ba.FAROIS_WEB:
        assert rid in ba._FONTE_BAIXADO_WEB
        assert rid in ba._TABELA_RECORTE_WEB


def test_RN_GER_006_pacote_com_tres_farois_um_com_erro_nao_derruba():
    def montado(titulo, tab):
        return _farol(titulo, _tabela(tab, [("NOV/26", "MANAUS")],
                                      mes="NOV/26"))
    res = {"pv_pedidos": montado("Farol de Pedidos", "Pedidos"),
           "pl_entregas": {"erro_montagem": "KeyError"},
           "vc_visitas": montado("Farol de Visita", "Por vendedor")}
    p = ba.montar_pacote_web(res, 2026, 11, raiz=Path("/nao/existe"))
    assert set(p["relatorios"]) == {"pv_pedidos", "vc_visitas"}
    for v in p["relatorios"].values():
        assert v["forma"] == "farol" and v["baixado_em"] is None
    json.dumps(p, allow_nan=False)


# ------------------------------------------------------------------ Pedidos
def test_RN_GER_006_pedidos_estado_pela_filial_da_nota_so_do_mes_do_farol():
    """Os cartões por estado partem do mesmo escopo do total (filtro MÊS);
    o padrão SITUAÇÃO = EM ABERTO é só visão da tela e não corta; a soma dos
    estados fecha o total do mês."""
    t = _tabela("Pedidos", [("NOV/26", "MANAUS"), ("NOV/26", "MANAUS"),
                            ("NOV/26", "BELÉM"), ("OUT/26", "BELÉM"),
                            ("OUT/26", "SÃO LUIS")], mes="NOV/26",
                extra_filtros=[{"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}])
    rec = ba.recortes_farol_por_uf(_farol("Farol de Pedidos", t), "Pedidos")
    assert _valores(rec) == {"AM": "2", "PA": "1"}
    assert sum(int(v) for v in _valores(rec).values()) == 3


def test_RN_GER_006_pedidos_sem_tabela_sem_acao_com_faixa_e_vendedor():
    t = _tabela("Pedidos", [("NOV/26", "MANAUS")], mes="NOV/26")
    r = _farol("Farol de Pedidos", t, kpis_faixa=True, blocos=[
        {"tipo": "hbarras", "titulo": "Pedidos em aberto por vendedor (R$)",
         "rotulos": ["Vendedor 01"], "valores": [10.0], "formato": "moeda"},
        {"tipo": "tabela", "titulo": "outra", "colunas": [], "linhas": []}])
    s = ba.selecionar_farol_web("pv_pedidos", r)
    assert s["forma"] == "farol" and s["kpis_faixa"] is True
    texto = json.dumps(s, ensure_ascii=False)
    for proibido in ("tabelas", "juntas", "editar", "abrir", "edicao",
                     "detalhe_pedido", "kpis_de", "AUTORIZA"):
        assert proibido not in texto
    # nome de vendedor VAI (D1); bloco tabela não é do Farol de Pedidos
    assert [b["tipo"] for b in s["painel"]["blocos"]] == ["hbarras"]
    assert "Vendedor 01" in texto
    assert set(s["recortes"]) == {"AM"}


def test_RN_GER_006_pedidos_bloco_frete_nao_entra():
    t = _tabela("Pedidos", [("NOV/26", "MANAUS")], mes="NOV/26")
    r = _farol("Farol de Pedidos", t, blocos=[_bloco_frete(COLS_FRETE)])
    assert ba.selecionar_farol_web("pv_pedidos", r)["painel"]["blocos"] == []


# ----------------------------------------------------------------- Entregas
def test_RN_GER_006_entregas_estado_pela_UF_do_cliente_nao_pela_filial():
    """Frete = UF do cliente: a nota da filial MANAUS entregue no MA conta
    MA; linha de outro mês fica fora; soma dos estados = total do mês."""
    t = _tabela("Entregas", [("NOV/26", "MANAUS", "MA"),
                             ("NOV/26", "MANAUS", "MA"),
                             ("NOV/26", "BELÉM", "AM"),
                             ("OUT/26", "BELÉM", "PA")], mes="NOV/26")
    s = ba.selecionar_farol_web("pl_entregas", _farol("Farol de Entregas", t))
    assert _valores(s["recortes"]) == {"MA": "2", "AM": "1"}
    assert sum(int(v) for v in _valores(s["recortes"]).values()) == 3
    assert "kpis_faixa" not in s
    assert AVISO_SEM_ESTADO not in s["avisos"]


def test_RN_GER_006_entregas_leva_frete_por_estado_sem_edicao():
    t = _tabela("Entregas", [("NOV/26", "MANAUS", "AM"),
                             ("NOV/26", "MANAUS", "MA")], mes="NOV/26")
    r = _farol("Farol de Entregas", t, blocos=[_bloco_frete(COLS_FRETE)])
    s = ba.selecionar_farol_web("pl_entregas", r)
    blocos = s["painel"]["blocos"]
    assert [b["tipo"] for b in blocos] == ["tabela"]
    assert blocos[0]["linhas"] == [["AM", "NORTE", 3, 100.0, 5.0, 5.0, 1.6]]
    assert blocos[0]["total"] == ["TOTAL", "", 3, 100.0, 5.0, 5.0, 1.6]
    assert "editar" not in blocos[0]            # a edição NÃO vai
    assert set(s["recortes"]) == {"AM", "MA"}


def _entrega(uf, dnf, etapa, valor):
    """Entrega fictícia do ACOMPANHAMENTO_POS_VENDA (sem pessoa real)."""
    return {"filial": "0101002", "nf": f"{dnf:%m%d}{uf}{int(valor)}",
            "data_nf": dnf, "situacao": "NO PRAZO", "etapa": etapa, "uf": uf,
            "cidade": "CIDADE FICTICIA", "cliente": "CLIENTE FICTICIO 01",
            "valor": valor, "transportadora": "", "responsavel": "",
            "cidade_filial": "MANAUS", "chave": ""}


def test_RN_GER_006_entregas_pendencias_anteriores_por_estado(tmp_path):
    """Comportamento: o Farol de Entregas (relatorios_nucleo.entregas) com
    entregas fictícias; o kpis_de da tabela Entregas, chamado com as linhas
    de NOV/26 de um estado (UF do cliente), dá as pendências de meses
    anteriores SÓ daquele estado; a soma dos estados = o cartão da BAP."""
    ctx = rn.Contexto(tmp_path, hoje=HOJE, params={"ANO": "2026", "MÊS": "11"})
    ctx._b["posvenda"] = {"existe": True, "devolucoes": [], "entregas": [
        _entrega("AM", date(2026, 11, 5), "ENTREGUE", 10.0),
        _entrega("PA", date(2026, 11, 6), "ENTREGUE", 20.0),
        _entrega("AM", date(2026, 10, 5), "EM ROTA", 1.0),     # pendentes
        _entrega("AM", date(2026, 10, 6), "EM ROTA", 2.0),
        _entrega("PA", date(2026, 10, 7), "EM ROTA", 4.0),
        _entrega("PA", date(2026, 10, 8), "ENTREGUE", 8.0)]}   # concluída
    ctx._b["tabela"] = {"itens": []}
    r = rn.entregas(ctx)

    def pend(kpis):
        k = next(k for k in kpis if k["rotulo"] == "Pendências anteriores")
        return k["valor"], k["detalhe"]
    assert pend(r["kpis"]) == ("3", "R$ 7 · meses anteriores")
    t = next(t for t in r["tabelas"] if t["titulo"] == "Entregas")
    n = [c["nome"] for c in t["colunas"]]
    iu, im = n.index("UF"), n.index("MÊS")
    por_uf = {uf: pend(t["kpis_de"]([l for l in t["linhas"]
                                     if l[iu] == uf and l[im] == "NOV/26"]))
              for uf in ("AM", "PA")}
    assert por_uf == {"AM": ("2", "R$ 3 · meses anteriores"),
                      "PA": ("1", "R$ 4 · meses anteriores")}
    assert sum(int(v) for v, _ in por_uf.values()) == 3


def test_RN_GER_006_entregas_pendencias_anteriores_so_na_BAP_no_site():
    """O site tira 'Pendências anteriores' do recorte por estado
    (_KPIS_SO_BAP_WEB) e o mantém nos cartões da BAP."""
    def kpis_de(linhas):
        return [{"rotulo": "Entregues", "valor": str(len(linhas))},
                {"rotulo": "Pendências anteriores", "valor": "9"}]
    t = _tabela("Entregas", [("NOV/26", "MANAUS", "AM"),
                             ("NOV/26", "MANAUS", "PA")], mes="NOV/26")
    t["kpis_de"] = kpis_de
    r = _farol("Farol de Entregas", t)
    r["kpis"] = kpis_de(t["linhas"])
    s = ba.selecionar_farol_web("pl_entregas", r)
    assert [k["rotulo"] for k in s["kpis"]] == ["Entregues",
                                                 "Pendências anteriores"]
    for uf in ("AM", "PA"):
        assert [k["rotulo"] for k in s["recortes"][uf]["kpis"]] == [
            "Entregues"]


def test_RN_GER_006_entregas_tabela_com_cliente_fica_so_no_pc():
    t = _tabela("Entregas", [("NOV/26", "MANAUS")], mes="NOV/26")
    cols = ["UF", "CLIENTE"] + COLS_FRETE[2:]
    s = ba.selecionar_farol_web(
        "pl_entregas", _farol("Farol de Entregas", t,
                              blocos=[_bloco_frete(cols)]))
    assert s["painel"]["blocos"] == []
    assert any("so no PC" in a for a in s["avisos"])


# ------------------------------------------------------------------- Visita
def test_RN_GER_006_visita_sem_UF_do_cliente_vai_sem_recortes_e_com_aviso():
    """Visita (Planner/carteira): estado = UF do cliente; 'Por vendedor' só
    tem a filial do vendedor, então NÃO se recorta por ela. Prospecção fica
    no PC."""
    t = _tabela("Por vendedor", [("", "MANAUS"), ("", "BELÉM"),
                                 ("", "BELÉM")])
    r = _farol("Farol de Visita", t, blocos=[
        {"tipo": "barras", "grafico": {"titulo": "Visitas dia a dia",
                                       "rotulos": ["1"], "series": []}}],
        avisos=["O dia de hoje é parcial: muda até o vendedor sincronizar.",
                "Prospecção do app BAP Ajuda: a foto fica em RELATORIOS"])
    s = ba.selecionar_farol_web("vc_visitas", r)
    assert s["recortes"] == {}
    assert AVISO_SEM_ESTADO in s["avisos"]
    assert "abrir" not in json.dumps(s)
    assert ("O dia de hoje é parcial: muda até o vendedor sincronizar."
            in s["avisos"])
    assert not any("rospec" in a for a in s["avisos"])


def test_RN_GER_006_inadimplencia_segue_pela_filial_sem_aviso_novo():
    """Entrega 1 intacta: Inadimplência recorta pela filial, sem filtro MÊS,
    e não ganha o aviso 'Sem filtro por estado' (nem sem recorte)."""
    t = _tabela("Títulos", [("", "MANAUS"), ("", "MANAUS"), ("", "BELÉM")])
    s = ba.selecionar_farol_web("pl_inadimplencia", _farol("Farol", t))
    assert _valores(s["recortes"]) == {"AM": "2", "PA": "1"}
    t2 = _tabela("Títulos", [("", "FILIAL DESCONHECIDA")])
    s2 = ba.selecionar_farol_web("pl_inadimplencia", _farol("Farol", t2))
    assert s2["recortes"] == {} and s2["avisos"] == []


def test_RN_GER_006_visita_cartao_por_estado_sem_dado_sai(monkeypatch):
    monkeypatch.setattr(rn, "estados_do_cartao", lambda r, k: {
        "barras": [["AM", 10.0, "10", "", ""], ["RR", None, "", "", ""]],
        "legenda": "x"})
    r = _farol("Farol de Visita", _tabela("Por vendedor", [("", "MANAUS")]))
    s = ba.selecionar_farol_web("vc_visitas", r)
    assert [b[0] for b in s["kpis"][0]["estados"]["barras"]] == ["AM"]
    assert s["kpis"][0]["estados"]["legenda"] == "x"


def test_RN_GER_006_visita_avisos_curtos_sem_arquivo_de_rota_nem_formula():
    """Celular: no máximo 2 linhas, sem nome de arquivo de rota nem fórmula;
    'Sem o arquivo' vem primeiro."""
    av = ["O dia de hoje é parcial: muda até o vendedor sincronizar.",
          "Sem o arquivo de 2 dia(s) útil(eis): 20/11, 23/11",
          "Aderência = programados do Planner do dia (ROTA_PROTHEUS 2026)",
          "Prospecção: 1 resposta(s) da conta de teste"]
    r = _farol("Farol de Visita", _tabela("Por vendedor", [("", "MANAUS")]),
               avisos=av)
    s = ba.selecionar_farol_web("vc_visitas", r)
    assert len(s["avisos"]) <= 2
    assert s["avisos"][0].startswith("Sem o arquivo")
    assert not any("ROTA_PROTHEUS" in a or "Aderência =" in a
                   for a in s["avisos"])


# -------------------------------------------------- RN-GER-007: datas/hoje
def test_RN_GER_007_hoje_manaus_e_a_data_no_fuso_de_manaus():
    antes = datetime.now(ZoneInfo("America/Manaus")).date()
    h = rn.hoje_manaus()
    depois = datetime.now(ZoneInfo("America/Manaus")).date()
    assert h in (antes, depois)
    assert rn.Contexto(Path("/nao/existe")).hoje in (h, depois)
    assert rn.Contexto(Path("/nao/existe"), hoje=HOJE).hoje == HOJE


def _pasta_visitas(raiz, falta=()):
    """GridRca fictício de 02/11 a ONTEM (23/11), dias úteis; hoje (24/11)
    sem arquivo, como na vida real antes do vendedor sincronizar."""
    pasta = raiz / "RELATORIOS" / "Visitas" / "diario"
    pasta.mkdir(parents=True)
    cab = "CodigoGeral;Nome;TotalVisitados;Agendados;TotalVisitas\n"
    d = date(2026, 11, 2)
    while d < HOJE:
        if d.weekday() < 5 and d not in falta:
            (pasta / f"{d:%Y%m%d}.csv").write_text(
                cab + "901;VENDEDOR FICTICIO 01;5;6;5\n", encoding="utf-8")
        d += timedelta(days=1)


def _farol_visita(raiz, monkeypatch):
    # sem Planner na pasta fictícia: o vendedor fictício vira ativo
    monkeypatch.setattr(rn, "com_cadastro_como_visita",
                        lambda ctx, regs, *a, **k: [
                            dict(l, ativo=True, cargo="VENDEDOR")
                            for l in regs])
    return rn.montar("vc_visitas", raiz, hoje=HOJE,
                     params={"ANO": "2026", "MÊS": "11"})


def test_RN_GER_007_visita_nao_cobra_o_arquivo_de_hoje(tmp_path, monkeypatch):
    """Hoje fica fora do DU: sem o arquivo de 24/11 (hoje), o aviso 'Sem o
    arquivo' não aparece (antes da T-0017 aparecia '1 dia(s): 24/11')."""
    _pasta_visitas(tmp_path)
    r = _farol_visita(tmp_path, monkeypatch)
    assert not any("Sem o arquivo" in a for a in r["avisos"])
    assert not any("24/11" in a for a in r["avisos"])


def test_RN_GER_007_visita_segue_cobrando_dia_passado_sem_arquivo(
        tmp_path, monkeypatch):
    """Dia útil fechado sem arquivo (20/11) continua no aviso; hoje não."""
    _pasta_visitas(tmp_path, falta={date(2026, 11, 20)})
    r = _farol_visita(tmp_path, monkeypatch)
    aviso = [a for a in r["avisos"] if a.startswith("Sem o arquivo")]
    assert aviso == ["Sem o arquivo de 1 dia(s) útil(eis): 20/11"]


def test_RN_GER_007_baixado_em_de_cada_farol_pelo_arquivo_de_origem(tmp_path):
    """Carimbo 'baixado em' no fuso de Manaus (UTC-4), pela base de origem
    de cada farol; sem a base, None."""
    mov = tmp_path / ba.BKP_BAPTOOLS
    mov.mkdir(parents=True)
    (mov / "Relatorio_Movimentos_BAP_Protheus_2026-11-18.xlsx").write_text("a")
    (mov / "Relatorio_Movimentos_BAP_Protheus_2026-11-19.xlsx").write_text("b")
    vis = tmp_path / ba.SUBPASTA_RELATORIOS / "Visitas"
    vis.mkdir(parents=True)
    (vis / "VISITAS_POR_CLIENTE.xlsx").write_text("c")
    ts = datetime(2026, 11, 20, 8, 30,
                  tzinfo=timezone(timedelta(hours=-4))).timestamp()
    os.utime(vis / "VISITAS_POR_CLIENTE.xlsx", (ts, ts))
    q = ba._baixado_em_da_base("vc_visitas", tmp_path)
    assert q is not None and q.utcoffset().total_seconds() == -4 * 3600
    assert q.replace(tzinfo=None) == datetime(2026, 11, 20, 8, 30)
    for rid in ("pv_pedidos", "pl_entregas"):
        assert ba._baixado_em_da_base(rid, tmp_path) is not None
    assert ba._baixado_em_da_base("vc_visitas", tmp_path / "vazio") is None
