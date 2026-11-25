"""T-0017, entrega 2: cobrança no WhatsApp e abas Títulos e Por cliente no site.

Contrato: §10.6 de .coord/contratos/relatorio.md. Regras: RN-POS-001 (fila,
número e saudação), RN-POS-002 (situação pelo último registro), RN-POS-003
(diário do site volta ao PC, idempotente, confirma só depois de gravar) e
RN-POS-004 (o que vai ao site: Títulos e Por cliente sem TELEFONE nem CNPJ).

Junta os testes do modulo-posvenda (cobranca_whatsapp.pacote_web,
importar_web, historico_origem, nome_saudacao) e do modulo-robo (passo 4f do
bap_automation). Dados 100% fictícios; o site é um falso em memória.
"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

import bap_automation as ba
import cobranca_whatsapp as cw

AGORA = datetime(2026, 11, 24, 8, 7, 33, 999,
                 tzinfo=timezone(timedelta(hours=-4)))
HOJE = date(2026, 11, 24)
TOKEN = "token-ficticio-xyz"
BASE = "https://web.exemplo.test"
STATUS = ("STATUS PROTHEUS", "STATUS", "SITUAÇÃO PLANNER")


# =================================================== farol mínimo (posvenda)
CC = ["SITUAÇÃO", "CLIENTE", "NOME", "CIDADE", "UF", "VENDEDOR", "SUPERVISOR",
      "EM ATRASO", "MAIOR ATRASO", "TELEFONE"]
CT = ["SITUAÇÃO", "CLIENTE", "NF", "PARC.", "VENCIMENTO", "DIAS ATRASO",
      "SALDO"]


def farol_min():
    """Três clientes fictícios: 2 INADIMPLENTES (um com celular, um sem
    telefone) e 1 A VENCER (fora da fila)."""
    col = lambda ns: [{"nome": n} for n in ns]           # noqa: E731
    return {"tabelas": [
        {"titulo": "Por cliente", "colunas": col(CC), "linhas": [
            ["INADIMPLENTE", "000001-01", "CLIENTE UM LTDA", "MANAUS", "AM",
             "VEND A", "SUP A", 300.0, 40, "(92) 99999-1111"],
            ["INADIMPLENTE", "000002-01", "CLIENTE DOIS LTDA", "MANAUS", "AM",
             "VEND A", "SUP A", 900.0, 10, ""],
            ["A VENCER", "000003-01", "CLIENTE TRES", "MANAUS", "AM",
             "VEND A", "SUP A", 0.0, 0, ""]]},
        {"titulo": "Títulos", "colunas": col(CT), "linhas": [
            ["VENCIDO", "000001-01", "11", "1", date(2026, 10, 15), 40, 100.0],
            ["VENCIDO", "000001-01", "12", "1", date(2026, 11, 1), 23, 200.0],
            ["VENCIDO", "000002-01", "21", "", date(2026, 11, 10), 10, 900.0],
            ["A VENCER", "000001-01", "13", "1", date(2026, 12, 1), 0,
             50.0]]}]}


def reg(i, cli="000001-01", q="2026-11-24 15:02:11", ac="ENVIADO"):
    return {"seq": 1, "id": i, "quando": q, "usuario": "login.web",
            "cliente": cli, "telefone": "5592900000000", "em_atraso": 300,
            "titulos": 2, "acao": ac}


def _item(p, cod):
    return next(i for i in p["fila"] if i["cod"] == cod)


# ============================================ farol do contrato (robô, 4f)
COL_T = [("SITUAÇÃO", "texto"), ("FAIXA", "texto"), ("FILIAL", "texto"),
         ("NF", "texto"), ("PARC.", "texto"), ("EMISSÃO", "data"),
         ("VENCIMENTO", "data"), ("DIAS ATRASO", "int"), ("CLIENTE", "texto"),
         ("NOME", "texto"), ("STATUS PROTHEUS", "texto"), ("STATUS", "texto"),
         ("SITUAÇÃO PLANNER", "texto"), ("CIDADE", "texto"), ("UF", "texto"),
         ("VENDEDOR", "texto"), ("SUPERVISOR", "texto"),
         ("CONDIÇÃO", "texto"), ("VALOR", "moeda"), ("SALDO", "moeda"),
         ("TELEFONE", "texto")]
COL_C = [("SITUAÇÃO", "texto"), ("FAIXA", "texto"), ("CLIENTE", "texto"),
         ("NOME", "texto"), ("STATUS PROTHEUS", "texto"), ("STATUS", "texto"),
         ("SITUAÇÃO PLANNER", "texto"), ("CIDADE", "texto"), ("UF", "texto"),
         ("VENDEDOR", "texto"), ("SUPERVISOR", "texto"),
         ("TÍTULOS VENCIDOS", "int"), ("EM ATRASO", "moeda"),
         ("MAIOR ATRASO", "int"), ("A VENCER", "moeda"),
         ("PRÓX. VENCIMENTO", "data"), ("LIMITE", "moeda"),
         ("PEDIDO EM ABERTO", "moeda"), ("ÚLTIMA COMPRA", "data"),
         ("TELEFONE", "texto")]
CHIP = {"VENCIDO": ("#FBDDDA", "#B3261E"),
        "INADIMPLENTE": ("#FBDDDA", "#B3261E")}


def _cols(lista):
    cols = []
    for n, t in lista:
        c = {"nome": n, "tipo": t, "largura": 100,
             "oculta": n in ("STATUS PROTHEUS", "SITUAÇÃO PLANNER")}
        if n in ("SITUAÇÃO", "FAIXA"):
            c["chip"], c["larg_fixa"] = CHIP, 106
        cols.append(c)
    return cols


def _farol(tipo_errado=False):
    """O farol do PC depois do montar, com uma linha fictícia por tabela e as
    chaves de ação (callables, edicao, detalhe) que não podem ir ao site."""
    t = ["VENCIDO", "1–15 DIAS", "MANAUS", "123", "1", date(2026, 9, 1),
         date(2026, 10, 20), 35, "001234-01", "CLIENTE FICTICIO LTDA", "ATIVO",
         "ATIVO", "", "MANAUS", "AM", "VENDEDOR FICTICIO",
         "SUPERVISOR FICTICIO", "28 DIAS", 1234.5, 1234.5, "92 90000-0001"]
    c = ["INADIMPLENTE", "1–15 DIAS", "001234-01", "CLIENTE FICTICIO LTDA",
         "ATIVO", "ATIVO", "", "MANAUS", "AM", "VENDEDOR FICTICIO",
         "SUPERVISOR FICTICIO", 1, 1234.5, 35, 0.0, None, 0.0, 0.0,
         date(2026, 7, 31), "92 90000-0001"]
    cols_c = _cols(COL_C)
    if tipo_errado:
        cols_c[12]["tipo"] = "texto"
    return {
        "titulo": "Farol de Inadimplência",
        "tabelas": [
            {"titulo": "Títulos", "colunas": _cols(COL_T), "linhas": [t],
             "tons": [""], "total": None,
             "filtros": ["SITUAÇÃO", "FAIXA", "STATUS"],
             "kpis_de": lambda ls: [], "recortes": [("x", lambda l: True)],
             "edicao": {"campos": []}, "detalhe": {"nf": 3}},
            {"titulo": "Por cliente", "colunas": cols_c, "linhas": [c],
             "tons": [""], "total": ["TOTAL"] + [None] * 18 + ["x"],
             "filtros": [{"coluna": "SITUAÇÃO", "padrao": "INADIMPLENTE"},
                         "FAIXA", "STATUS"],
             "kpis_de": lambda ls: []}]}


def _farol_inteiro(**extra):
    return {"titulo": "F", "kpis": [], "painel": {"blocos": []},
            "avisos": [], **_farol(), **extra}


def _tira_colunas(farol, nomes):
    for t in farol["tabelas"]:
        ix = {i for i, c in enumerate(t["colunas"]) if c["nome"] in nomes}
        t["colunas"] = [c for i, c in enumerate(t["colunas"]) if i not in ix]
        t["linhas"] = [[v for i, v in enumerate(ln) if i not in ix]
                       for ln in t["linhas"]]
        if t.get("total"):
            t["total"] = [v for i, v in enumerate(t["total"]) if i not in ix]
    return farol


# --------------------------------------------------------- o site de mentira
class Resp:
    def __init__(self, codigo, corpo=None):
        self.status_code, self._c = codigo, corpo

    def json(self):
        if self._c is None:
            raise ValueError("sem json")
        return self._c


class SiteFalso:
    """Diário do site em memória, com o GET paginado e o confirmar."""

    def __init__(self, n=0, por_pagina=1000, epoca="ep-A"):
        self.epoca = epoca
        self.regs = [{"seq": i, "id": f"id-{i:04d}",
                      "quando": f"2026-11-2{i % 5} 10:00:00",
                      "usuario": "login.web", "cliente": "001234-01",
                      "telefone": "5592900000001", "em_atraso": 1234.5,
                      "titulos": 1, "acao": "ENVIADO", "pacote_sha": "ab"}
                     for i in range(1, n + 1)]
        self.pag = por_pagina
        self.gets, self.confirmados, self.cabs = [], [], []

    def get(self, url, params=None, headers=None, timeout=0):
        self.cabs.append(headers)
        desde = int(params["desde"])
        self.gets.append(desde)
        itens = [r for r in self.regs if r["seq"] > desde]
        pag = itens[:self.pag]
        return Resp(200, {"epoca": self.epoca, "linhas": pag,
                          "ate_seq": pag[-1]["seq"] if pag else desde,
                          "mais": len(itens) > len(pag)})

    def post(self, url, json=None, headers=None, timeout=0):
        self.cabs.append(headers)
        if json["epoca"] != self.epoca:
            return Resp(409, {"erro": "epoca"})
        self.confirmados.append(json["ate_seq"])
        return Resp(200, {"ok": True, "epoca": self.epoca,
                          "confirmado_ate": json["ate_seq"]})


class SemConfirmar(SiteFalso):
    def post(self, url, json=None, headers=None, timeout=0):
        return Resp(500)


def _sync(raiz, site, log=lambda m: None, nomes=None):
    return ba.sincronizar_cobranca_web(raiz, nomes or {}, cw, BASE, TOKEN,
                                       sessao=site, log=log)


def _log():
    msgs = []
    return msgs, msgs.append


def _csv(raiz):
    return raiz / "RELATORIOS" / "_COBRANCA_WHATSAPP" / "COBRANCA_WEB.csv"


def _n_linhas_csv(raiz):
    return len(_csv(raiz).read_text(encoding="utf-8-sig").splitlines())


# ================================================ RN-POS-001: fila e número
def test_RN_POS_001_fila_so_inadimplente_vencido_do_maior_atraso_sem_telefone_cad():
    p = cw.pacote_web(farol_min(), {}, {}, datetime(2026, 11, 24, 8, 7),
                      web_ate_seq=41, web_epoca="ep1")
    assert p["gerado_em"] == "2026-11-24T08:07:00-04:00"
    assert (p["web_epoca"], p["web_ate_seq"], p["dias_recente"],
            p["modelo"]) == ("ep1", 41, 7, cw.MODELO)
    # A VENCER fica fora; ordem pelo EM ATRASO (900 antes de 300)
    assert [i["cod"] for i in p["fila"]] == ["000002-01", "000001-01"]
    for i in p["fila"]:
        assert "telefone_cad" not in i
        assert "99999-1111" not in str(i)
    a = _item(p, "000001-01")
    assert a["whatsapp"] == "5592999991111" and a["aviso"] == ""
    assert a["ultimo"] is None
    # só os VENCIDOS, do maior dias para o menor, venc em ISO
    assert [t["dias"] for t in a["titulos"]] == [40, 23]
    assert a["titulos"][0]["venc"] == "2026-10-15"
    assert "15/10/2026" in a["mensagem"]
    sem = _item(p, "000002-01")
    assert sem["whatsapp"] == "" and sem["aviso"]


def test_RN_POS_001_fixo_sai_com_aviso_e_fantasia_na_mensagem():
    f = farol_min()
    f["tabelas"][0]["linhas"][0][-1] = "(92) 3333-4444"
    p = cw.pacote_web(f, {"000001": "FANTASIA UM"}, {}, HOJE)
    a = _item(p, "000001-01")
    assert a["whatsapp"] == "559233334444" and "fixo" in a["aviso"]
    assert "(92)" not in str(p) and a["nome_msg"] == "FANTASIA UM"


def test_RN_POS_001_saudacao_sem_cpf_nem_cnpj_no_comeco():
    assert cw.nome_saudacao("12.345.678 FULANO DE TAL") == "FULANO DE TAL"
    assert cw.nome_saudacao("123.456.789-09 FULANO") == "FULANO"
    assert cw.nome_saudacao("12.345.678/0001-90 EMPRESA X") == "EMPRESA X"
    assert cw.nome_saudacao("99 AUTO PECAS") == "99 AUTO PECAS"
    f = farol_min()
    f["tabelas"][0]["linhas"][0][2] = "12.345.678 FULANO FICTICIO"
    a = _item(cw.pacote_web(f, {}, {}, HOJE), "000001-01")
    assert a["nome_msg"] == "FULANO FICTICIO"
    assert "12.345" not in a["mensagem"] and "Fulano Ficticio" in a["mensagem"]
    a = _item(cw.pacote_web(f, {"000001": "12345678 FANTASIA UM"}, {}, HOJE),
              "000001-01")
    assert a["nome_msg"] == "FANTASIA UM" and "12345678" not in a["mensagem"]


# ================================== RN-POS-002: situação pelo último registro
def test_RN_POS_002_ultimo_em_qualquer_diario_com_origem_pc_ou_web(tmp_path):
    d = tmp_path / cw.PASTA
    d.mkdir(parents=True)
    (d / "COBRANCA_PC1.csv").write_text(
        "quando;maquina;usuario;cliente;nome;telefone;em_atraso;titulos;acao\n"
        "2026-11-21 10:15:00;PC1;u;000001-01;N;5592999991111;300.00;2;ENVIADO\n"
        "2026-11-24 09:00:00;PC1;u;000002-01;N;;900.00;1;PULADO\n",
        encoding="utf-8-sig")
    cw.importar_web(tmp_path, [reg("a", "000001-01", "2026-11-23 10:00:00")])
    u = {i["cod"]: i for i in cw.pacote_web(
        farol_min(), {}, cw.historico_origem(tmp_path), HOJE)["fila"]}
    # o registro do site (23/11) é mais novo que o do PC (21/11)
    assert u["000001-01"]["ultimo"] == {
        "quando": "2026-11-23 10:00:00", "acao": "ENVIADO", "origem": "WEB"}
    assert u["000002-01"]["ultimo"] == {
        "quando": "2026-11-24 09:00:00", "acao": "PULADO", "origem": "PC"}
    assert u["000002-01"]["whatsapp"] == ""
    h = cw.historico(tmp_path)
    assert cw.situacao(h, "000002-01", HOJE) == "PULADO HOJE"
    assert cw.situacao(h, "000001-01", HOJE) == "ENVIADO 23/11"
    # historico() (tuplas de 2) também serve: origem PC
    p2 = cw.pacote_web(farol_min(), {}, h, HOJE)
    assert {i["ultimo"]["origem"] for i in p2["fila"]} == {"PC"}


@pytest.mark.parametrize("quando,acao,esperado", [
    ("2026-11-24 08:00:00", "ENVIADO", "ENVIADO HOJE"),
    ("2026-11-18 10:00:00", "ENVIADO", "ENVIADO 18/11"),   # 6 dias: recente
    ("2026-11-17 10:00:00", "ENVIADO", ""),                # 7 dias: a cobrar
    ("2026-11-24 08:00:00", "PULADO", "PULADO HOJE"),
    ("2026-11-23 08:00:00", "PULADO", ""),                 # pulado ontem
])
def test_RN_POS_002_situacao_limites_de_7_dias(quando, acao, esperado):
    assert cw.situacao({"x": (quando, acao)}, "x", HOJE) == esperado


def test_RN_POS_002_estado_do_robo_nao_entra_no_glob_do_historico(tmp_path):
    ba.gravar_estado_cobranca(tmp_path, "ep-A", 4)
    pasta = tmp_path / "RELATORIOS" / "_COBRANCA_WHATSAPP"
    assert list(pasta.glob("COBRANCA_*.csv")) == []
    assert cw.historico_origem(tmp_path) == {}


# =============================== RN-POS-003: importar_web (o CSV do site)
def test_RN_POS_003_importar_web_idempotente_e_csv_das_assistentes_intocado(
        tmp_path):
    d = tmp_path / cw.PASTA
    d.mkdir(parents=True)
    outro = d / "COBRANCA_PC1.csv"
    outro.write_text(
        "quando;maquina;usuario;cliente;nome;telefone;em_atraso;titulos;acao\n",
        encoding="utf-8-sig")
    antes = outro.read_bytes()
    ls = [reg("a"), reg("b", "000002-01", ac="PULADO")]
    assert cw.importar_web(tmp_path, ls, {"000001-01": "CLIENTE UM"}) == 2
    assert cw.importar_web(tmp_path, ls + [reg("c")]) == 1
    assert cw.importar_web(tmp_path, ls + [reg("c"), reg("c")]) == 0
    assert outro.read_bytes() == antes
    raw = _csv(tmp_path).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\xef\xbb\xbf") == 1
    linhas = raw.decode("utf-8-sig").splitlines()
    assert linhas[0] == ("quando;maquina;usuario;cliente;nome;telefone;"
                         "em_atraso;titulos;acao;id")
    assert linhas[1].split(";")[1:] == [
        "WEB", "login.web", "000001-01", "CLIENTE UM", "5592900000000",
        "300.00", "2", "ENVIADO", "a"]
    assert len(linhas) == 4
    assert cw.historico(tmp_path)["000001-01"][1] == "ENVIADO"


def test_RN_POS_003_importar_web_erro_de_disco_levanta(tmp_path):
    (tmp_path / "RELATORIOS").write_text("arquivo no lugar da pasta")
    with pytest.raises(OSError):
        cw.importar_web(tmp_path, [reg("a")])


# ============================ RN-POS-003: a rodada do robô (GET/importar/confirmar)
def test_RN_POS_003_ida_e_volta_importa_confirma_e_monta_fila(tmp_path):
    site = SiteFalso(n=3)
    msgs, log = _log()
    est = _sync(tmp_path, site, log, {"001234-01": "CLIENTE FICTICIO LTDA"})
    assert est == {"epoca": "ep-A", "ate_seq": 3} and site.confirmados == [3]
    assert ba.ler_estado_cobranca(tmp_path) == est
    assert _n_linhas_csv(tmp_path) == 4
    # a fila nova já vê o que o site cobrou, com origem WEB
    bloco = ba.montar_cobranca_web(_farol(), tmp_path, cw, est["ate_seq"],
                                   AGORA, web_epoca=est["epoca"])
    assert (bloco["web_ate_seq"], bloco["web_epoca"]) == (3, "ep-A")
    assert bloco["gerado_em"] == "2026-11-24T08:07:33-04:00"
    item = bloco["fila"][0]
    assert item["cod"] == "001234-01" and item["ultimo"]["origem"] == "WEB"
    assert "telefone_cad" not in item
    # segunda rodada sem novidade: desde = 3, não importa de novo, mas
    # confirma de novo (idempotente; refaz a que tiver falhado)
    site.gets.clear()
    assert _sync(tmp_path, site, log)["ate_seq"] == 3
    assert site.gets == [3] and site.confirmados == [3, 3]
    assert _n_linhas_csv(tmp_path) == 4
    assert all(h["Authorization"] == f"Bearer {TOKEN}" for h in site.cabs)
    assert TOKEN not in " ".join(msgs)


def test_RN_POS_003_paginacao_enquanto_mais(tmp_path):
    site = SiteFalso(n=5, por_pagina=2)
    res = ba.baixar_cobranca_web(0, BASE, TOKEN, site, lambda m: None)
    assert [r["seq"] for r in res["linhas"]] == [1, 2, 3, 4, 5]
    assert res["ate_seq"] == 5 and site.gets == [0, 2, 4]
    assert _sync(tmp_path, SiteFalso(5, 2))["ate_seq"] == 5


def test_RN_POS_003_servidor_que_nao_anda_nao_prende_o_robo():
    class Preso(SiteFalso):
        def get(self, url, params=None, headers=None, timeout=0):
            return Resp(200, {"epoca": "e", "linhas": [], "ate_seq": 0,
                              "mais": True})
    res = ba.baixar_cobranca_web(0, BASE, TOKEN, Preso(), lambda m: None)
    assert res == {"epoca": "e", "linhas": [], "ate_seq": 0}


@pytest.mark.parametrize("codigo,trecho", [
    (404, "404"),                       # web antiga
    (401, "token da web recusado"),
    (500, "500"),
])
def test_RN_POS_003_get_que_falha_segue_sem_importar_nem_confirmar(
        tmp_path, codigo, trecho):
    class Falha(SiteFalso):
        def get(self, *a, **k):
            self.gets.append(k.get("params"))
            return Resp(codigo)
    ba.gravar_estado_cobranca(tmp_path, "ep-A", 7)
    site = Falha(3)
    msgs, log = _log()
    assert ba.baixar_cobranca_web(0, BASE, TOKEN, site, log) is None
    assert _sync(tmp_path, site, log) == {"epoca": "ep-A", "ate_seq": 7}
    assert site.confirmados == [] and not _csv(tmp_path).exists()
    assert any(trecho in m for m in msgs)
    assert TOKEN not in " ".join(msgs)


def test_RN_POS_003_erro_de_disco_nao_confirma_e_tenta_na_proxima(
        tmp_path, monkeypatch):
    site = SiteFalso(n=2)
    msgs, log = _log()

    def disco_cheio(raiz, linhas, nomes=None):
        raise PermissionError("arquivo aberto no Excel")
    monkeypatch.setattr(cw, "importar_web", disco_cheio)
    assert _sync(tmp_path, site, log)["ate_seq"] == 0
    assert site.confirmados == []
    assert ba.ler_estado_cobranca(tmp_path)["ate_seq"] == 0
    assert any("nao confirmo" in m for m in msgs)
    monkeypatch.undo()                  # próxima rodada: disco liberado
    site.gets.clear()
    assert _sync(tmp_path, site, log)["ate_seq"] == 2
    assert site.gets == [0] and site.confirmados == [2]


def test_RN_POS_003_confirmacao_que_falha_conta_no_web_ate_seq_e_e_refeita(
        tmp_path):
    est = _sync(tmp_path, SemConfirmar(n=2))
    # gravado no PC, só não confirmado: web_ate_seq já conta
    assert est == {"epoca": "ep-A", "ate_seq": 2}
    assert ba.ler_estado_cobranca(tmp_path) == est
    bloco = ba.montar_cobranca_web(_farol(), tmp_path, cw, est["ate_seq"],
                                   AGORA, web_epoca=est["epoca"])
    assert bloco["web_ate_seq"] == 2 and bloco["web_epoca"] == "ep-A"
    site = SiteFalso(n=2)
    assert _sync(tmp_path, site)["ate_seq"] == 2
    assert site.confirmados == [2]      # a confirmação foi refeita
    assert _n_linhas_csv(tmp_path) == 3  # sem duplicar


def test_RN_POS_003_estado_perdido_ou_estragado_comeca_do_zero_sem_duplicar(
        tmp_path):
    site = SiteFalso(n=3)
    _sync(tmp_path, site)
    arq = (tmp_path / "RELATORIOS" / "_COBRANCA_WHATSAPP"
           / ba.ARQ_ESTADO_COBRANCA_WEB)
    arq.unlink()
    assert ba.ler_estado_cobranca(tmp_path)["ate_seq"] == 0
    site.gets.clear()
    _sync(tmp_path, site)
    assert site.gets == [0]
    assert _n_linhas_csv(tmp_path) == 4                 # sem duplicar
    arq.write_text("{lixo", encoding="utf-8")
    assert ba.ler_estado_cobranca(tmp_path) == {"epoca": "", "ate_seq": 0}


def test_RN_POS_003_epoca_nova_descarta_e_puxa_desde_zero(tmp_path):
    _sync(tmp_path, SiteFalso(3))
    assert ba.ler_estado_cobranca(tmp_path) == {"epoca": "ep-A", "ate_seq": 3}
    site = SiteFalso(2, epoca="ep-B")      # diário do site recomeçou
    est = _sync(tmp_path, site)
    assert est == {"epoca": "ep-B", "ate_seq": 2}
    assert site.gets == [3, 0]             # a 1ª resposta foi descartada
    assert site.confirmados == [2]
    assert ba.ler_estado_cobranca(tmp_path) == est
    # os ids da época nova já estavam no CSV: não duplica
    assert _n_linhas_csv(tmp_path) == 4


def test_RN_POS_003_so_https_porta_443():
    assert ba._base_web("https://x.test/") == "https://x.test"
    assert ba._base_web("https://x.test/app/") == "https://x.test/app"
    assert ba._base_web("http://x.test") is None
    assert ba._base_web("https://x.test:8080") is None
    assert ba._base_web("") is None


# ========================= RN-POS-004: Títulos e Por cliente no pacote
def test_RN_POS_004_tabelas_so_as_colunas_do_contrato_sem_telefone_nem_acao():
    tabs = ba.tabelas_cobranca_web(_farol())
    assert [t["titulo"] for t in tabs] == ["Títulos", "Por cliente"]
    for t in tabs:
        esperado = ba._colunas_esperadas_web(t["titulo"], True)
        assert [(c["nome"], c["tipo"]) for c in t["colunas"]] == list(esperado)
        assert all(len(ln) == len(t["colunas"]) for ln in t["linhas"])
        assert len(t["tons"]) == len(t["linhas"])
        assert set(t) == {"titulo", "colunas", "linhas", "tons", "total",
                          "filtros"}
        ocultas = [c["nome"] for c in t["colunas"] if c.get("oculta")]
        assert ocultas == ["STATUS PROTHEUS", "SITUAÇÃO PLANNER"]
    assert [len(t["colunas"]) for t in tabs] == [20, 19]
    texto = json.dumps(tabs, ensure_ascii=False)
    assert "TELEFONE" not in texto and "92 90000" not in texto
    for proibida in ("CNPJ", "CPF", "E-MAIL", "EMAIL"):
        assert proibida not in texto
    for k in ("edicao", "kpis_de", "recortes", "detalhe", "editar", "abrir"):
        assert f'"{k}"' not in texto
    # data em ISO; total sem a célula do TELEFONE; filtros do PC
    assert tabs[0]["linhas"][0][5] == "2026-09-01"
    assert len(tabs[1]["total"]) == 19
    assert tabs[1]["filtros"] == [{"coluna": "SITUAÇÃO",
                                   "padrao": "INADIMPLENTE"}, "FAIXA", "STATUS"]


def test_RN_POS_004_chip_e_tons_como_o_pc_entrega():
    for t in ba.tabelas_cobranca_web(_farol()):
        com = {c["nome"]: c for c in t["colunas"] if "chip" in c}
        assert set(com) == {"SITUAÇÃO", "FAIXA"}
        assert com["FAIXA"]["chip"]["VENCIDO"] == ["#FBDDDA", "#B3261E"]
        assert com["FAIXA"]["larg_fixa"] == 106
        assert set(t["tons"]) == {""}
    json.dumps(ba.tabelas_cobranca_web(_farol()), allow_nan=False)


def test_RN_POS_004_bloco_de_status_vai_inteiro_ou_nao_vai():
    sem = ba.tabelas_cobranca_web(_tira_colunas(_farol(), STATUS))
    assert [len(t["colunas"]) for t in sem] == [17, 16]
    assert all("STATUS" not in json.dumps(t) for t in sem)
    # só uma ou duas das três: a web recusaria
    assert ba.tabelas_cobranca_web(_tira_colunas(_farol(), {"STATUS"})) is None


def test_RN_POS_004_tabela_fora_do_contrato_nao_vai():
    extra = _farol()                       # coluna a mais (não é TELEFONE)
    extra["tabelas"][0]["colunas"].append({"nome": "EXTRA", "tipo": "texto"})
    oculta = _farol()                      # oculta diferente do contrato
    oculta["tabelas"][1]["colunas"][4]["oculta"] = False
    so_uma = _farol()
    so_uma["tabelas"] = so_uma["tabelas"][:1]
    for f in (extra, oculta, so_uma, _farol(tipo_errado=True), {}):
        assert ba.tabelas_cobranca_web(f) is None


def test_RN_POS_004_tabelas_e_cobranca_juntas_so_no_inadimplencia():
    farol = _farol_inteiro()
    cob = {"gerado_em": "x", "web_ate_seq": 3, "fila": []}
    com = ba.selecionar_farol_web("pl_inadimplencia", farol, cobranca=cob)
    assert [t["titulo"] for t in com["tabelas"]] == ["Títulos", "Por cliente"]
    assert com["cobranca"]["web_ate_seq"] == 3
    sem = ba.selecionar_farol_web("pl_inadimplencia", farol)
    assert "tabelas" not in sem and "cobranca" not in sem
    outro = ba.selecionar_farol_web("pl_pedidos", farol, cobranca=cob)
    assert "tabelas" not in outro and "cobranca" not in outro
    torta = ba.selecionar_farol_web("pl_inadimplencia",
                                    {**farol, **_farol(True)}, cobranca=cob)
    assert "tabelas" not in torta and "cobranca" not in torta


def test_RN_POS_004_colunas_fora_do_contrato_farol_segue_com_aviso():
    farol = _farol_inteiro(avisos=["aviso do PC"])
    farol["tabelas"][0]["colunas"].append({"nome": "EXTRA", "tipo": "texto"})
    for ln in farol["tabelas"][0]["linhas"]:
        ln.append("x")
    val = ba.selecionar_farol_web("pl_inadimplencia", farol,
                                  cobranca={"fila": []})
    assert "tabelas" not in val and "cobranca" not in val
    assert val["kpis"] == [] and val["painel"] == {"blocos": []}
    assert val["avisos"][0] == "aviso do PC" and len(val["avisos"]) == 2


def test_RN_POS_004_pacote_inteiro_ida_e_volta_sem_telefone_cadastral(
        tmp_path):
    farol = _farol_inteiro()
    resultados = {"pl_inadimplencia": farol}
    # simulação (sincronizar=False): não toca na rede nem grava no diário
    cob = ba.preparar_cobranca_web(resultados, tmp_path, AGORA, False, BASE,
                                   TOKEN, log=lambda m: None)
    assert cob["pl_inadimplencia"]["web_ate_seq"] == 0
    assert not _csv(tmp_path).exists()
    est = _sync(tmp_path, SiteFalso(n=2))
    bloco = ba.montar_cobranca_web(farol, tmp_path, cw, est["ate_seq"], AGORA,
                                   web_epoca=est["epoca"])
    pacote = ba.montar_pacote_web(resultados, 2026, 11, AGORA,
                                  cobranca={"pl_inadimplencia": bloco})
    r = pacote["relatorios"]["pl_inadimplencia"]
    assert [t["titulo"] for t in r["tabelas"]] == ["Títulos", "Por cliente"]
    assert r["cobranca"]["web_ate_seq"] == 2
    assert r["cobranca"]["fila"][0]["ultimo"]["origem"] == "WEB"
    json.dumps(pacote, allow_nan=False)                 # serializa limpo
    assert "92 90000" not in json.dumps(pacote, ensure_ascii=False)
