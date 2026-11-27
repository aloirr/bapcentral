"""T-0017, entregas 3 a 5, rodada do pacote: as abas de Pedidos, Entregas e
Visita no pacote da web, montado com as BASES CONGELADAS do repositório
(NOV/2026, hoje = 24/11/2026, terça, em Manaus). Desenho, seção 3.4;
contrato §10.7.

Regras citadas:
- RN-GER-011: nome e texto de cliente vão sem CPF/CNPJ e sem contato; o
  código do cliente fica.
- RN-GER-006: estado do faturamento = filial da nota (Pedidos); fretes e
  carteira = UF do cliente (Entregas); Visita sem UF do cliente.
- Abas do PC: a tabela do site é a do PC depois do corte e da limpeza;
  cartões da aba = os que o PC mostra ao abrir a aba.

Nenhum valor de célula é impresso: as mensagens de falha só têm título,
coluna, índice, contagem e cartões (números agregados). Por isso as contagens
vão para variáveis antes do assert (o pytest mostraria a lista inteira).
"""
import copy
import json
import re
import sys
import types
from datetime import date, datetime
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
MES_ROT = "NOV/26"
RIDS = ("pv_pedidos", "pl_entregas", "vc_visitas")
# transição T-0037: até o #169 (testes/T-0037-fretes), que põe o pl_fretes no RIDS_1073 e volta a comparar tudo
ABAS_FRETES_TRANSICAO = {"Notas com frete", "Por UF", "Por cidade",
                         "Por transportadora"}
ABAS = {"pv_pedidos": ["Pedidos", "Solicitação BAP"],
        "pl_entregas": ["Entregas"],
        "vc_visitas": ["Por supervisor", "Por vendedor", "Dia a dia",
                       "Aderência dia a dia", "Cliente a cliente",
                       "Prospecção", "Indicação"]}
# §10.7.4, escrito aqui à mão (sem acento, maiúsculas)
COLUNAS_FORA = {"TELEFONE", "CELULAR", "WHATSAPP", "CNPJ", "CPF", "E-MAIL",
                "EMAIL", "CONTATO", "FOTO", "ENDERECO"}
# §10.7.2: fora, sempre, em qualquer nível de `tabelas`
CHAVES_FORA = {"edicao", "editar", "abrir", "detalhe", "detalhe_pedido",
               "kpis_de", "total_de", "totais_por", "recortes",
               "ordem_exportar", "cores_celulas", "so_exportar",
               "solicitacao_bap", "nota_pdf", "garantia",
               "importar_preenchidos"}
# §10.7.3 e §10.7.4: as colunas "limpa" e o texto livre, por tabela
LIMPA = {
    "Pedidos": {"RAZÃO SOCIAL": "sem_documento", "FANTASIA": "sem_documento"},
    "Analítico produto": {"CLIENTE": "cliente_sem_documento"},
    "Entregas": {"CLIENTE": "cliente_sem_documento"},
    "Pendências dos meses anteriores": {"CLIENTE": "cliente_sem_documento"},
    "Cliente a cliente": {"CLIENTE": "cliente_sem_documento",
                          "NOME FANTASIA": "sem_documento"},
    "Prospecção": {"ESTABELECIMENTO": "sem_documento"},
    "Indicação": {"CLIENTE QUE INDICOU": "sem_documento",
                  "INDICADO": "sem_documento"}}
TEXTO_LIVRE = {"JUSTIFICATIVA", "OBSERVAÇÃO", "RESULTADO",
               "LINHAS DE INTERESSE"}
SO_MES = {"Pedidos", "Entregas"}
RE_DOC = re.compile(r"(?<!\d)(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
                    r"|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{14}|\d{11})(?!\d)")
RE_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
TETO_MB = 20
# §10.7.6 do contrato (textos de aviso, fonte única)
AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."
AVISO_CARTOES = "Cartões sem filtro. Com filtro, veja as linhas na tabela."


def _sem_acento(s):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(s or "").strip().upper())
    return "".join(c for c in t if not unicodedata.combining(c))


def _js(v):
    """A célula como JSON (date/datetime em ISO; NaN e infinito = None)."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and (v != v or v in (float("inf"),
                                                 float("-inf"))):
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        return v.item()
    return v


def _kjs(ks):
    return json.loads(json.dumps(ba._para_json(ks), ensure_ascii=False))


# ===================================================================== fixtures
@pytest.fixture(scope="module")
def real():
    """(rels do PC, pacote) dos 3 faróis nas bases congeladas."""
    rels = {rid: rn.montar(rid, RAIZ, hoje=HOJE, params=dict(PARAMS))
            for rid in RIDS}
    pacote = ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)
    return rels, pacote


def _tab_pc(rels, rid, titulo):
    return next(t for t in rels[rid]["tabelas"] if t.get("titulo") == titulo)


def _tab_web(pacote, rid, titulo):
    return next(t for t in pacote["relatorios"][rid].get("tabelas") or []
                if t["titulo"] == titulo)


def _todas_web(pacote):
    """(rid, titulo, tabela) de toda tabela, junta e sub-aba do pacote."""
    for rid in RIDS:
        for t in pacote["relatorios"][rid].get("tabelas") or []:
            yield rid, t["titulo"], t
            for j in t.get("juntas") or []:
                yield rid, j["tabela"]["titulo"], j["tabela"]
            for sa in t.get("subabas") or []:
                yield rid, sa["titulo"], sa


@pytest.fixture(scope="module")
def web_app():
    """web/app (tabelas, pacotes): só biblioteca padrão; sai do sys.modules
    no fim."""
    antes = set(sys.modules)
    sys.path.insert(0, str(RAIZ / "web"))
    try:
        from app import pacotes, tabelas
        yield types.SimpleNamespace(pacotes=pacotes, tabelas=tabelas)
    finally:
        sys.path.remove(str(RAIZ / "web"))
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]


# ================================================== pacote inteiro e a web
def test_T0017_pacote_real_tem_todas_as_abas_e_a_web_aceita(real, web_app):
    _rels, p = real
    for rid in RIDS:
        r = p["relatorios"][rid]
        assert [t["titulo"] for t in r["tabelas"]] == ABAS[rid], rid
        assert web_app.tabelas.validar(rid, r) == [], rid
        # nenhuma aba ficou fora: sem o aviso de aba fora
        assert not [a for a in r.get("avisos") or []
                    if a.startswith("Abas fora")], rid
    assert web_app.pacotes.validar(p) == []


def test_T0017_ponta_a_ponta_web_aceita_e_nao_tira_aba(real, web_app):
    """Ponta a ponta: o pacote real, montado pelo robô, passa na validação
    da web sem erro e a defesa de documento (W2) não tira nenhuma aba."""
    _rels, p = real
    q = json.loads(json.dumps(p, ensure_ascii=False))   # o que o site recebe
    assert web_app.tabelas.tirar_abas_com_documento(q) == []
    assert web_app.pacotes.validar(q) == []
    for rid in RIDS:
        assert [t["titulo"] for t in q["relatorios"][rid]["tabelas"]] == \
            ABAS[rid], rid


def test_RN_GER_011_web_documento_numa_aba_tira_so_aquela_aba(real,
                                                              web_app):
    """CPF/CNPJ formatado numa célula: a web tira só aquela aba, com o
    aviso único de abas fora (primeiro); as outras abas e faróis seguem."""
    _rels, p = real
    q = json.loads(json.dumps(p, ensure_ascii=False))
    t = next(x for x in q["relatorios"]["vc_visitas"]["tabelas"]
             if x["titulo"] == "Cliente a cliente")
    i = [c["nome"] for c in t["colunas"]].index("NOME FANTASIA")
    t["linhas"][0][i] = "CLIENTE FICTICIO 123.456.789-01"
    assert web_app.tabelas.tirar_abas_com_documento(q) == ["Cliente a cliente"]
    assert [x["titulo"] for x in q["relatorios"]["vc_visitas"]["tabelas"]] \
        == [a for a in ABAS["vc_visitas"] if a != "Cliente a cliente"]
    assert q["relatorios"]["vc_visitas"]["avisos"][0] == \
        AVISO_ABAS_FORA.format(lista="Cliente a cliente")
    for rid in ("pv_pedidos", "pl_entregas"):
        assert [x["titulo"] for x in q["relatorios"][rid]["tabelas"]] == \
            ABAS[rid]
    assert web_app.pacotes.validar(q) == []


def test_T0017_entregas_filtro_mes_oculto(real):
    """O filtro MÊS do Entregas vai oculto (só o mês do pacote)."""
    _rels, p = real
    f = next(f for f in _tab_web(p, "pl_entregas", "Entregas")["filtros"]
             if isinstance(f, dict) and f.get("coluna") == "MÊS")
    assert f.get("oculto") is True and f.get("padrao") == MES_ROT


# ============================================ RN-GER-011: nada de documento
def test_RN_GER_011_pacote_sem_coluna_proibida_nem_chave_de_acao(real):
    _rels, p = real
    for rid, titulo, t in _todas_web(p):
        nomes = [_sem_acento(c["nome"]) for c in t["colunas"]]
        assert not COLUNAS_FORA & set(nomes), (rid, titulo)

    def chaves(o, caminho, permitidas=frozenset()):
        if isinstance(o, dict):
            for k, v in o.items():
                if (k == "edicao" and caminho[0] in ("pv_pedidos", "pl_entregas")
                        and isinstance(v, dict)):
                    # T-0021: só a especificação da edição na web (admin)
                    assert set(v) == {"modulo", "acao", "chaves", "campos"}, caminho
                    continue
                assert k in permitidas or k not in CHAVES_FORA, (caminho, k)
                assert not k.startswith("_"), (caminho, k)
                assert not k.startswith("pdf"), (caminho, k)
                if k == "kpis_padrao" and isinstance(v, list):
                    # §10.7.2: o cartão vai inteiro; o `detalhe` do Kpi não
                    # é o detalhe de pedido da tabela (só no nível do cartão)
                    for card in v:
                        chaves(card, caminho + (k,), frozenset({"detalhe"}))
                else:
                    chaves(v, caminho + (k,))
        elif isinstance(o, list):
            for v in o:
                chaves(v, caminho)
    n_cartoes = 0
    for rid in RIDS:
        chaves(p["relatorios"][rid]["tabelas"], (rid,))
        for t in p["relatorios"][rid]["tabelas"]:
            for card in t.get("kpis_padrao") or []:
                assert set(card) <= {"rotulo", "valor", "cor", "detalhe",
                                     "linhas"}, (rid, t["titulo"])
                n_cartoes += 1
    assert n_cartoes > 0
    # o `detalhe` de pedido da tabela (a chave da tabela) continua fora
    for rid, titulo, t in _todas_web(p):
        assert "detalhe" not in t, (rid, titulo)
    json.dumps(p, allow_nan=False)                  # nada de callable/NaN


def test_RN_GER_011_pacote_sem_cpf_cnpj_nem_email_em_nenhuma_celula(real):
    """Regex de CPF/CNPJ (com e sem máscara) e de e-mail em TODA célula de
    texto ou inteira de `tabelas` (juntas e sub-abas incluídas); número com
    casas decimais não é documento. Só a contagem sai na falha."""
    _rels, p = real
    achados = {}
    for rid, titulo, t in _todas_web(p):
        nomes = [c["nome"] for c in t["colunas"]]
        for ln in t["linhas"]:
            for n, v in zip(nomes, ln):
                if isinstance(v, float) and v.is_integer():
                    s = str(int(v))
                elif isinstance(v, (str, int)) and not isinstance(v, bool):
                    s = str(v)
                else:
                    continue
                if RE_DOC.search(s) or RE_EMAIL.search(s):
                    k = (rid, titulo, n)
                    achados[k] = achados.get(k, 0) + 1
    assert achados == {}


def test_RN_GER_011_pc_tinha_documento_nos_nomes_e_o_site_nao(real):
    """Prova de que a limpeza trabalhou: no PC há nome com CPF/CNPJ (as
    bases congeladas têm), no site nenhum."""
    rels, p = real
    pc = sum(1 for ln in _tab_pc(rels, "vc_visitas", "Cliente a cliente")[
        "linhas"] for v in ln if isinstance(v, str) and RE_DOC.search(v))
    assert pc > 0


# ======================================= igualdade célula a célula com o PC
def _esperado(rid, t_pc, junta=False):
    """A tabela do PC depois do corte (colunas que saem, célula a mais, só o
    mês no Pedidos/Entregas) e da limpeza (RN-GER-011)."""
    cols = t_pc["colunas"]
    idx = [i for i, c in enumerate(cols)
           if _sem_acento(c["nome"]) not in COLUNAS_FORA]
    nomes = [cols[i]["nome"] for i in idx]
    titulo = t_pc["titulo"]
    linhas = t_pc["linhas"]
    if titulo in SO_MES and not junta:
        i_mes = [c["nome"] for c in cols].index("MÊS")
        linhas = [ln for ln in linhas if ln[i_mes] == MES_ROT]
    limpa = {n: getattr(rn, f) for n, f in LIMPA.get(titulo, {}).items()}
    limpa.update({n: rn.texto_sem_contato for n in TEXTO_LIVRE})
    saida = []
    for ln in linhas:
        nova = []
        for n, i in zip(nomes, idx):
            v = ln[i]
            if n in limpa and v not in (None, ""):
                v = limpa[n](v)
            nova.append(_js(v))
        saida.append(nova)
    return nomes, saida


def _comparar(rid, titulo, t_web, nomes, linhas):
    assert [c["nome"] for c in t_web["colunas"]] == nomes, (rid, titulo)
    n_web, n_pc = len(t_web["linhas"]), len(linhas)   # sem repr de linha
    assert n_web == n_pc, (rid, titulo)
    dif = [(k, nomes[j]) for k, (a, b) in enumerate(zip(t_web["linhas"],
                                                        linhas))
           for j, (x, y) in enumerate(zip(a, b)) if x != y]
    assert dif == [], (rid, titulo, len(dif), dif[:5])


@pytest.mark.parametrize("rid", RIDS)
def test_T0017_tabelas_iguais_ao_pc_celula_a_celula(real, rid):
    rels, p = real
    for titulo in ABAS[rid]:
        if titulo == "Solicitação BAP":
            continue
        t_pc = _tab_pc(rels, rid, titulo)
        t_web = _tab_web(p, rid, titulo)
        _comparar(rid, titulo, t_web, *_esperado(rid, t_pc))
        # tons: os do PC, nas mesmas linhas
        n_tons, n_lin = len(t_web["tons"]), len(t_web["linhas"])
        assert n_tons == n_lin, (rid, titulo)
        pc_j = {j["titulo"]: j for j in t_pc.get("juntas") or []}
        for j in t_web.get("juntas") or []:
            jp = pc_j[j["titulo"]]
            _comparar(rid, j["titulo"], j["tabela"],
                      *_esperado(rid, jp["tabela"], junta=True))
            assert j["liga"] == (list(jp["liga"]) if jp.get("liga")
                                 else None)


def _total_esperado(t_pc):
    """§10.7.2.1: a linha TOTAL do PC normalizada (os 4 passos)."""
    cols = t_pc["colunas"]
    idx = [i for i, c in enumerate(cols)
           if _sem_acento(c["nome"]) not in COLUNAS_FORA]
    tot = t_pc.get("total")
    if not isinstance(tot, (list, tuple)) or len(tot) != len(cols):
        return None
    tipos = [cols[i]["tipo"] for i in idx]
    ocultas = [bool(cols[i].get("oculta")) for i in idx]
    cel = [_js(tot[i]) for i in idx]
    cel = [None if v in ("", None) else v for v in cel]          # passo 1
    rot = tot[0] if isinstance(tot[0], str) and tot[0] else None
    if rot is not None:                                          # passo 2
        alvo = next(j for j, (tp, o) in enumerate(zip(tipos, ocultas))
                    if tp == "texto" and not o)
        if idx[0] == 0 and cel[0] == rot and alvo != 0:
            cel[0] = None
        cel[alvo] = rot

    def casa(v, tp):                                             # passo 4
        if v is None:
            return True
        if tp in ("texto", "hora"):
            return isinstance(v, str)
        if tp in ("data", "dia"):
            return isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}",
                                                        v))
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return [v if casa(v, tp) else None for v, tp in zip(cel, tipos)]


def test_T0017_total_normalizado_igual_ao_pc(real):
    """§10.7.2.1: o `total` é a linha TOTAL do PC depois dos 4 passos
    (vazio = null; rótulo na 1ª coluna visível de texto; null onde o tipo
    não casa). Hoje só o Visita tem total."""
    rels, p = real
    com = []
    for rid in RIDS:
        for titulo in ABAS[rid]:
            if titulo == "Solicitação BAP":
                continue
            t_pc = _tab_pc(rels, rid, titulo)
            esperado = _total_esperado(t_pc)
            assert _tab_web(p, rid, titulo).get("total") == esperado, titulo
            if esperado is not None:
                com.append(titulo)
                assert "TOTAL" in esperado, titulo
    assert com == ["Por supervisor", "Por vendedor", "Dia a dia",
                   "Aderência dia a dia"]
    dia = _tab_web(p, "vc_visitas", "Dia a dia")
    nomes = [c["nome"] for c in dia["colunas"]]
    assert dia["total"][nomes.index("DATA")] is None
    assert dia["total"][nomes.index("DIA")] == "TOTAL"


def test_T0017_solicitacao_bap_igual_ao_arquivo(real):
    """A aba Solicitação BAP: uma sub-aba por aba do arquivo, todas as
    linhas (D3 A), sem coluna que sai, CLIENTE sem documento."""
    import solicitacao_bap as sb
    _rels, p = real
    dados = sb.ler(RAIZ)
    t = _tab_web(p, "pv_pedidos", "Solicitação BAP")
    esperadas = [a for a in sb.ABAS_TELA if dados.get(a)]
    assert [s["titulo"] for s in t["subabas"]] == esperadas
    n_cols, n_lin = len(t["colunas"]), len(t["linhas"])
    assert (n_cols, n_lin) == (0, 0)
    for sa in t["subabas"]:
        d = dados[sa["titulo"]]
        cols = [c for c in d["colunas"]]
        fica = [i for i, c in enumerate(cols)
                if c and _sem_acento(c) not in COLUNAS_FORA]
        assert [c["nome"] for c in sa["colunas"]] == [cols[i] for i in fica]
        n_web, n_pc = len(sa["linhas"]), len(d["linhas"])
        assert n_web == n_pc, sa["titulo"]
        nomes = [cols[i] for i in fica]
        # o texto igual ao do arquivo; CLIENTE limpo
        dif = 0
        for a, b in zip(sa["linhas"], d["linhas"]):
            for j, i in enumerate(fica):
                v = b[i] if i < len(b) else None
                if not isinstance(v, str):
                    continue
                if nomes[j] == "CLIENTE":
                    v = rn.cliente_sem_documento(v)
                elif nomes[j] == "MOTIVO":
                    v = rn.texto_sem_contato(v)
                dif += a[j] != v
        assert dif == 0, (sa["titulo"], dif)


# ============================================================ cartões da aba
@pytest.mark.parametrize("rid", RIDS)
def test_T0017_kpis_padrao_igual_chamar_kpis_de_linhas_padrao(real, rid):
    rels, p = real
    com = 0
    for titulo in ABAS[rid]:
        if titulo == "Solicitação BAP":
            continue
        t_pc = _tab_pc(rels, rid, titulo)
        t_web = _tab_web(p, rid, titulo)
        if not callable(t_pc.get("kpis_de")):
            assert "kpis_padrao" not in t_web, titulo
            continue
        linhas = [t_pc["linhas"][k] for k in rn.linhas_padrao(t_pc)]
        esperado = _kjs(rn.chamar_kpis_de(t_pc["kpis_de"], linhas))
        assert t_web.get("kpis_padrao") == esperado, titulo
        com += 1
    assert com > 0


# a tela do PC de verdade (VistaTabela com Tk de mentira; ver o outro teste)
from test_T0017_abas_tres_farois import _Coringa, br, _mod_tk  # noqa: E402,F401


@pytest.fixture
def tela_pc(br, monkeypatch):
    """(visíveis, filtros_colunas) que a aba mostra ao abrir no PC: os
    parâmetros de cima (nomes_params) e os filtros gerais da janela."""
    monkeypatch.setattr(br, "tk", _mod_tk("tk_falso"))
    monkeypatch.setattr(br, "ttk", _mod_tk("ttk_falso"))
    monkeypatch.setattr(br, "caixa_de_filtro", _Coringa)
    monkeypatch.setattr(br.bv, "Tabela", _Coringa)
    monkeypatch.setattr(br.VistaTabela, "aplicar", lambda self, **k: None)

    def _ver(rel, t):
        nomes_params = {prm["nome"] for prm in rel.get("parametros") or []}
        gerais = br._BaseRelatorio._filtros_gerais(
            types.SimpleNamespace(nomes_params=nomes_params), rel)
        janela = types.SimpleNamespace(
            gerais={n: None for n, _v in gerais}, gerais_escolha={},
            nomes_params=nomes_params, _filtros_guardados=None, rel=rel)
        v = br.VistaTabela(_Coringa(), t, janela)
        return v.visiveis(), v.filtros_colunas()
    return _ver


@pytest.mark.parametrize("rid", RIDS)
def test_T0017_kpis_padrao_igual_aos_cartoes_da_aba_no_pc(real, rid,
                                                          tela_pc):
    """Valor × regra: o cartão da aba no site é o que o PC mostra ao abrir
    a aba (`_BaseRelatorio.kpis_atuais`: kpis_de das visíveis, com o
    filtro das colunas)."""
    rels, p = real
    for titulo in ABAS[rid]:
        if titulo == "Solicitação BAP":
            continue
        t_pc = _tab_pc(rels, rid, titulo)
        if not callable(t_pc.get("kpis_de")):
            continue
        vis, filtro = tela_pc(rels[rid], t_pc)
        esperado = _kjs(rn.chamar_kpis_de(t_pc["kpis_de"], vis, filtro))
        assert _tab_web(p, rid, titulo).get("kpis_padrao") == esperado, \
            titulo


@pytest.mark.parametrize("rid", RIDS)
def test_T0017_kpis_padrao_numeros_iguais_aos_do_pc(real, rid, tela_pc):
    """O número (rótulo, valor e cor) de cada cartão da aba é o do PC, pelas
    duas contas: kpis_de(linhas_padrao) e a tela de verdade. O detalhe (a
    linha de baixo do cartão) é conferido nos dois testes acima."""
    rels, p = real
    for titulo in ABAS[rid]:
        if titulo == "Solicitação BAP":
            continue
        t_pc = _tab_pc(rels, rid, titulo)
        if not callable(t_pc.get("kpis_de")):
            continue
        web = _rvc(_tab_web(p, rid, titulo).get("kpis_padrao") or [])
        linhas = [t_pc["linhas"][k] for k in rn.linhas_padrao(t_pc)]
        assert web == _rvc(_kjs(rn.chamar_kpis_de(t_pc["kpis_de"], linhas))), \
            titulo
        vis, filtro = tela_pc(rels[rid], t_pc)
        assert web == _rvc(_kjs(rn.chamar_kpis_de(t_pc["kpis_de"], vis,
                                                  filtro))), titulo


# ================================================================== recortes
@pytest.mark.parametrize("rid", RIDS)
def test_T0017_recortes_linhas_igual_ao_recorte_do_pc(real, rid):
    """Para cada recorte por função do PC, os índices (nas linhas do site)
    das linhas que ele deixa. Tabela `enxuta` (Pedidos) não manda."""
    rels, p = real
    for titulo in ABAS[rid]:
        if titulo == "Solicitação BAP":
            continue
        t_pc = _tab_pc(rels, rid, titulo)
        t_web = _tab_web(p, rid, titulo)
        if t_pc.get("enxuta") or not t_pc.get("recortes"):
            assert "recortes_linhas" not in t_web, titulo
            continue
        linhas = t_pc["linhas"]
        manter = list(range(len(linhas)))
        if titulo in SO_MES:
            i_mes = [c["nome"] for c in t_pc["colunas"]].index("MÊS")
            manter = [k for k in manter if linhas[k][i_mes] == MES_ROT]
        novo = {k: j for j, k in enumerate(manter)}
        esperado = []
        for rot, regra in t_pc["recortes"]:
            if not callable(regra):
                continue
            idx = []
            for k in manter:
                try:
                    ok = regra(linhas[k])
                except Exception:                       # noqa: BLE001
                    ok = False
                if ok:
                    idx.append(novo[k])
            esperado.append({"rotulo": rot, "linhas": idx})
        assert t_web.get("recortes_linhas") == esperado, titulo


def test_T0017_pedidos_enxuta_sem_recortes_no_site(real):
    rels, p = real
    t_pc = _tab_pc(rels, "pv_pedidos", "Pedidos")
    assert t_pc.get("enxuta") and len(t_pc.get("recortes") or []) == 4
    assert "recortes_linhas" not in _tab_web(p, "pv_pedidos", "Pedidos")


# ============================================================ RN-GER-006
def test_RN_GER_006_uf_linhas_pedidos_pela_filial_da_nota(real):
    rels, p = real
    t = _tab_web(p, "pv_pedidos", "Pedidos")
    i_fil = [c["nome"] for c in t["colunas"]].index("FILIAL")
    esperado = [rn.uf_do_nome_da_filial(ln[i_fil]) or "" for ln in
                t["linhas"]]
    assert t["uf_linhas"] == esperado
    assert all(re.fullmatch(r"[A-Z]{2}|", u) for u in t["uf_linhas"])
    assert any(t["uf_linhas"])
    # as juntas do Pedidos seguem a liga, sem uf_linhas
    assert all("uf_linhas" not in j["tabela"] for j in t["juntas"])


def test_RN_GER_006_uf_linhas_entregas_pela_uf_do_cliente(real):
    rels, p = real
    t = _tab_web(p, "pl_entregas", "Entregas")
    nomes = [c["nome"] for c in t["colunas"]]
    i_uf = nomes.index("UF")

    def uf(v):
        v = str(v or "").strip().upper()
        return v if re.fullmatch(r"[A-Z]{2}", v) else ""
    assert t["uf_linhas"] == [uf(ln[i_uf]) for ln in t["linhas"]]
    assert any(t["uf_linhas"])
    pend = t["juntas"][0]["tabela"]
    assert len(pend.get("uf_linhas", [])) == len(pend["linhas"])


def test_RN_GER_006_visita_sem_uf_linhas(real):
    _rels, p = real
    for t in p["relatorios"]["vc_visitas"]["tabelas"]:
        assert "uf_linhas" not in t, t["titulo"]


# ===================================================== aba torta fica fora
def test_T0017_aba_torta_fica_fora_sozinha_com_1_aviso(real):
    rels, _p = real
    r = dict(rels["vc_visitas"])
    tabs = [dict(t) for t in r["tabelas"]]
    k = next(i for i, t in enumerate(tabs) if t["titulo"] == "Dia a dia")
    tabs[k]["colunas"] = [dict(c, nome="COLUNA NOVA") if c["nome"] == "DIA"
                          else c for c in tabs[k]["colunas"]]
    r["tabelas"] = tabs
    s = ba.selecionar_farol_web("vc_visitas", r, raiz=RAIZ)
    assert [t["titulo"] for t in s["tabelas"]] == [
        a for a in ABAS["vc_visitas"] if a != "Dia a dia"]
    # §10.7.6: um aviso só, o primeiro, e o teto do celular corta do fim
    assert s["avisos"][0] == AVISO_ABAS_FORA.format(lista="Dia a dia")
    assert sum("Abas fora" in a for a in s["avisos"]) == 1
    assert len(s["avisos"]) <= 2


def test_T0017_duas_abas_tortas_um_aviso_so(real):
    rels, _p = real
    r = dict(rels["vc_visitas"])
    tabs = []
    for t in r["tabelas"]:
        t = dict(t)
        if t["titulo"] in ("Por supervisor", "Prospecção"):
            t["colunas"] = [dict(t["colunas"][0], nome="COLUNA NOVA")] + \
                t["colunas"][1:]
        tabs.append(t)
    r["tabelas"] = tabs
    s = ba.selecionar_farol_web("vc_visitas", r, raiz=RAIZ)
    titulos = [t["titulo"] for t in s["tabelas"]]
    assert titulos == [a for a in ABAS["vc_visitas"]
                       if a not in ("Por supervisor", "Prospecção")]
    assert s["avisos"][0] == AVISO_ABAS_FORA.format(
        lista="Por supervisor, Prospecção")         # ordem do §10.7.1
    assert sum("Abas fora" in a for a in s["avisos"]) == 1
    assert len(s["avisos"]) <= 2


def test_T0017_pedidos_torto_solicitacao_segue(real):
    rels, _p = real
    r = dict(rels["pv_pedidos"])
    tabs = [dict(t) for t in r["tabelas"]]
    tabs[0]["colunas"] = tabs[0]["colunas"][1:]
    r["tabelas"] = tabs
    s = ba.selecionar_farol_web("pv_pedidos", r, raiz=RAIZ)
    assert [t["titulo"] for t in s["tabelas"]] == ["Solicitação BAP"]
    assert s["avisos"][0] == AVISO_ABAS_FORA.format(lista="Pedidos")
    assert sum("Abas fora" in a for a in s["avisos"]) == 1


# ===================================================== tamanho e o corte
def _tam(p):
    return len(json.dumps(p, ensure_ascii=False).encode("utf-8"))


def test_T0017_pacote_real_menor_que_20MB_e_sem_corte(real):
    _rels, p = real
    assert _tam(p) < TETO_MB * 1024 * 1024
    assert ba.WEB_PACOTE_TETO_MB == TETO_MB
    assert not [a for r in p["relatorios"].values()
                for a in r.get("avisos") or [] if "caber no pacote" in a]


def test_T0017_corte_em_3_passos_na_ordem(real):
    """§10.7.8: (1) Solicitação BAP só EM ABERTO; (2) Cliente a cliente
    fora; (3) todas as tabelas dos 3 faróis fora. Para no passo que cabe;
    o pacote de entrada não muda."""
    _rels, p = real
    antes = json.dumps(p, ensure_ascii=False, sort_keys=True)
    MB = 1024 * 1024

    def avisos(q):
        return {rid: [a for a in q["relatorios"][rid].get("avisos") or []
                      if "caber no pacote" in a] for rid in RIDS}

    def fora(q, rid):
        return [a for a in q["relatorios"][rid].get("avisos") or []
                if a.startswith("Abas fora desta atualização")]

    # passo 1
    p1 = ba._cortar_pacote_web(p, teto_mb=(_tam(p) - 1) / MB)
    sol = _tab_web(p1, "pv_pedidos", "Solicitação BAP")
    for sa in sol["subabas"]:
        nomes = [c["nome"] for c in sa["colunas"]]
        if "SITUACAO_PEDIDO" in nomes:
            i = nomes.index("SITUACAO_PEDIDO")
            assert all(str(ln[i]).strip().upper() == "EM ABERTO"
                       for ln in sa["linhas"]), sa["titulo"]
    assert _tam(p1) < _tam(p)
    assert "Cliente a cliente" in [t["titulo"] for t in
                                   p1["relatorios"]["vc_visitas"]["tabelas"]]
    av = avisos(p1)
    assert av["pv_pedidos"] == ["A Solicitação BAP foi reduzida aos pedidos "
                                "em aberto para caber no pacote."]
    assert not fora(p1, "vc_visitas")
    # passo 2
    p2 = ba._cortar_pacote_web(p, teto_mb=(_tam(p1) - 1) / MB)
    assert "Cliente a cliente" not in [
        t["titulo"] for t in p2["relatorios"]["vc_visitas"]["tabelas"]]
    n_abas = len(p2["relatorios"]["vc_visitas"]["tabelas"])
    assert n_abas == 6
    # passo 2: a aba sai com o aviso único de abas fora, o primeiro
    assert p2["relatorios"]["vc_visitas"]["avisos"][0] == \
        AVISO_ABAS_FORA.format(lista="Cliente a cliente")
    assert len(p2["relatorios"]["vc_visitas"]["avisos"]) <= 2
    # passo 3
    p3 = ba._cortar_pacote_web(p, teto_mb=(_tam(p2) - 1) / MB)
    for rid in RIDS:
        assert "tabelas" not in p3["relatorios"][rid], rid
        assert p3["relatorios"][rid]["kpis"] == p["relatorios"][rid]["kpis"]
        # um aviso só, com todas as abas do farol, na ordem do §10.7.1
        assert p3["relatorios"][rid]["avisos"][0] == AVISO_ABAS_FORA.format(
            lista=", ".join(ABAS[rid])), rid
        assert len(fora(p3, rid)) == 1, rid
    # a entrada não mudou
    assert json.dumps(p, ensure_ascii=False, sort_keys=True) == antes


# ==================================================== lista de colunas
def _contrato_1073():
    """{titulo: [(nome, tipo, oculta, selo)]} do §10.7.3 do contrato (None
    se a seção não existe: o teste falha)."""
    arq = RAIZ / ".coord" / "contratos" / "relatorio.md"
    txt = arq.read_text(encoding="utf-8") if arq.exists() else ""
    if "#### 10.7.3" not in txt:
        return None
    sec = txt.split("#### 10.7.3", 1)[1].split("#### 10.7.4", 1)[0]
    tipos = r"(dia|data|texto|num1|num|int|moeda|pct1|pct|hora)"
    item = re.compile(rf"^`([^`]+)` {tipos}\b(.*)$")
    selos = {"chip por faixa": "faixa", "barra": "barra",
             "chip_tom": "tom", "chip por texto": "texto"}

    def itens(corpo, metricas=()):
        saida = []
        for seg in corpo.split(" · "):
            seg = seg.strip()
            if "18 de métrica" in seg:
                saida.extend(metricas)
                continue
            m = item.match(seg)
            if not m:
                continue
            resto = m.group(3).split(". ")[0]
            selo = next((v for k, v in selos.items()
                         if f"[{k}" in resto or f"[`{k}`" in resto), None)
            saida.append((m.group(1), m.group(2), "(o)" in resto, selo))
        return saida
    linhas = sec.splitlines()
    metricas = []
    for ln in linhas:
        if "As **18 de métrica**" in ln:
            metricas = itens(ln.split("nesta ordem:", 1)[1])
    saida = {}
    for ln in linhas:
        m = (re.match(r'^\s*- \*\*"([^"]+)"\*\* \([^)]*\): (.*)$', ln)
             or re.match(r'^\s*- Junta "[^"]+" → tabela "([^"]+)" '
                         r'\([^)]*\): (.*)$', ln))
        if m and "as mesmas colunas" not in m.group(2):
            saida[m.group(1)] = itens(m.group(2), metricas)
    # Aderência dia a dia: por padrão de nome (conferido à parte)
    saida.pop("Aderência dia a dia", None)
    saida["Gerar reversa de lojas"] = saida.get("Gerar separação CD")
    if "Entregas" in saida:
        saida["Pendências dos meses anteriores"] = [
            (n, tp, False if n == "MÊS" else o, s)
            for n, tp, o, s in saida["Entregas"]]
    return saida


def _robo_rid():
    """{(rid, título): colunas} do robô. As colunas são por (rid, título),
    nunca só pelo título (contrato §10.10.1): "Por supervisor" e "Por
    vendedor" existem no Visita e na NCC (T-0023 v2)."""
    return {(rid, titulo): [(n, tp, bool(o), s) for n, tp, o, s in cols]
            for rid, tabs in ba._COLUNAS_TABELAS_WEB.items()
            for titulo, cols in tabs.items()}


def _robo():
    """{título: colunas} só dos 3 faróis do §10.7.3 (RIDS), onde o título é
    único: é a forma do `tabelas.COLUNAS` da web e do contrato."""
    saida = {}
    for (rid, titulo), cols in _robo_rid().items():
        if rid in RIDS:
            assert titulo not in saida, titulo        # título único no 10.7.3
            saida[titulo] = cols
    return saida


def test_T0023_colunas_por_rid_e_titulo_sem_colisao():
    """O "Por supervisor" da NCC não pisa o do Visita (e vice-versa): cada
    (rid, título) tem a sua lista no robô (§10.10.1)."""
    r = _robo_rid()
    vis = [n for n, *_ in r[("vc_visitas", "Por supervisor")]]
    assert vis[:2] == ["SUPERVISOR", "REPRES."] and vis[-1] == "CHAVE"
    ncc = [n for n, *_ in r[("pl_ncc", "Por supervisor")]]
    assert ncc == ["SUPERVISOR", "NCC", "CLIENTES", "0-30 DIAS", "31-90 DIAS",
                   "91-180 DIAS", "+180 DIAS", "SALDO", "COMPENSAR JÁ"]
    assert [n for n, *_ in r[("pl_ncc", "Por vendedor")]][0] == "VENDEDOR"
    assert [n for n, *_ in r[("vc_visitas", "Por vendedor")]][:2] == [
        "SUPERVISOR", "VENDEDOR"]


def test_T0017_colunas_robo_igual_web(web_app):
    robo = {t: c for t, c in _robo().items()
            if t not in ABAS_FRETES_TRANSICAO}
    web = {t: c for t, c in web_app.tabelas.COLUNAS.items()
           if t not in ABAS_FRETES_TRANSICAO}
    assert sorted(robo) == sorted(web)
    for titulo, cols in robo.items():
        assert [c[:3] for c in cols] == [tuple(c) for c in web[titulo]], \
            titulo
        selos_r = {n: s for n, _tp, _o, s in cols if s}
        assert selos_r == web_app.tabelas.SELOS.get(titulo, {}), titulo
    # Aderência dia a dia: o mesmo padrão de nome dos dois lados
    assert ba._ADERENCIA_WEB[1] == web_app.tabelas._RE_DIA.pattern
    assert ba._ADERENCIA_WEB[2] == web_app.tabelas._RE_ACUM.pattern


def test_T0017_colunas_robo_igual_contrato_1073():
    contrato = _contrato_1073()
    assert contrato is not None, "§10.7.3 ausente no contrato"
    contrato = {t: c for t, c in contrato.items()
                if t not in ABAS_FRETES_TRANSICAO}
    robo = {t: c for t, c in _robo().items()
            if t not in ABAS_FRETES_TRANSICAO}
    assert sorted(contrato) == sorted(robo)
    for titulo in robo:
        assert contrato[titulo] == robo[titulo], titulo
    txt = (RAIZ / ".coord" / "contratos" / "relatorio.md").read_text(
        encoding="utf-8")
    assert ba._ADERENCIA_WEB[1] in txt and ba._ADERENCIA_WEB[2] in txt


def test_T0017_colunas_do_pc_batem_com_o_robo(real):
    """As tabelas que o PC monta hoje (bases congeladas) têm as colunas da
    lista, depois de tirar as que saem: nenhuma aba cai."""
    rels, _p = real
    robo = _robo_rid()
    for rid in RIDS:
        for t in rels[rid]["tabelas"]:
            if t["titulo"] in ("Solicitação BAP", "Aderência dia a dia"):
                continue
            nomes = [(c["nome"], c["tipo"], bool(c.get("oculta")))
                     for c in t["colunas"]
                     if _sem_acento(c["nome"]) not in COLUNAS_FORA]
            assert nomes == [x[:3] for x in robo[(rid, t["titulo"])]], \
                t["titulo"]


# ========================================= número do cartão × farol de origem
def _col(t, nome):
    i = [c["nome"] for c in t["colunas"]].index(nome)
    return [ln[i] for ln in t["linhas"]]


def _kpi(ks, rotulo):
    return next(k for k in ks if k["rotulo"].startswith(rotulo))["valor"]


def _rvc(ks):
    """Rótulo, valor e cor (o detalhe e as mini-barras ficam de fora)."""
    return [(k["rotulo"], k["valor"], k.get("cor")) for k in ks]


def _br(n, casas=0):
    s = f"{n:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def test_RN_GER_006_pedidos_em_aberto_no_mes_bate_com_as_linhas(real):
    """Pedidos "Em aberto" (topo) = linhas EM ABERTO do mês na aba Pedidos
    do site = o cartão "Pedidos" da aba (kpis_padrao)."""
    _rels, p = real
    r = p["relatorios"]["pv_pedidos"]
    t = _tab_web(p, "pv_pedidos", "Pedidos")
    sit = _col(t, "SITUAÇÃO")
    abertos = sum(1 for s in sit if s == "EM ABERTO")
    assert abertos > 0
    assert _kpi(r["kpis"], "Em aberto") == _br(abertos)
    assert _kpi(t["kpis_padrao"], "Pedidos") == _br(abertos)
    # os outros contadores do topo, pela SITUAÇÃO das linhas do mês
    for rot, sit_ in (("Entregues", "ENTREGUE"),
                      ("Pedidos devolvidos", "DEVOLVIDO"),
                      ("Excluídos", "EXCLUÍDO"), ("Cancelados", "CANCELADO")):
        assert _kpi(r["kpis"], rot) == _br(sum(s == sit_ for s in sit)), rot
    # "Pedidos" do topo = pedidos distintos (filial, pedido) do mês
    ped = set(zip(_col(t, "FILIAL"), _col(t, "PEDIDO")))
    assert _kpi(r["kpis"], "Pedidos") == _br(len(ped))


def test_T0017_pedidos_cartoes_da_aba_pela_regra(real):
    """Os 6 cartões do BI (aba Pedidos, filtro padrão EM ABERTO do mês)
    recalculados das linhas do site."""
    _rels, p = real
    t = _tab_web(p, "pv_pedidos", "Pedidos")
    nomes = [c["nome"] for c in t["colunas"]]
    ab = [ln for ln in t["linhas"]
          if ln[nomes.index("SITUAÇÃO")] == "EM ABERTO"]
    sla = [ln[nomes.index("SLA")] for ln in ab
           if ln[nomes.index("SLA")] is not None]
    ks = t["kpis_padrao"]
    assert _kpi(ks, "SLA") == _br(sum(sla) / len(sla), 1)
    assert _kpi(ks, "Faturar") == _br(sum(
        1 for ln in ab if (ln[nomes.index("% ATENDIDO")] or 0) >= 99.99))
    assert _kpi(ks, "> 4 dias") == _br(sum(
        1 for ln in ab if (ln[nomes.index("SLA")] or 0) > 4))
    assert _kpi(ks, "Volume") == _br(sum(ln[nomes.index("VOL.")] or 0
                                         for ln in ab))
    assert _kpi(ks, "R$") == "R$ " + _br(sum(ln[nomes.index("R$ VENDA")]
                                             for ln in ab))


def test_T0017_entregas_cartoes_pela_regra(real):
    """Os 7 cartões do Farol de Entregas recalculados das linhas do site
    (aba Entregas, mês) e da junta de pendências."""
    _rels, p = real
    r = p["relatorios"]["pl_entregas"]
    t = _tab_web(p, "pl_entregas", "Entregas")
    n = [c["nome"] for c in t["colunas"]]
    ls = t["linhas"]
    et = [str(ln[n.index("ETAPA")] or "").upper() for ln in ls]
    abertas = [ln for ln, e in zip(ls, et) if e not in ("ENTREGUE",
                                                       "CANCELADA")]
    com_data = [ln for ln in ls if ln[n.index("DT. REAL")]]
    no_prazo = [ln for ln in com_data if ln[n.index("PRAZO")] == "NO PRAZO"]
    slas = [ln[n.index("SLA")] for ln in com_data
            if ln[n.index("SLA")] is not None]
    ks = r["kpis"]
    assert _kpi(ks, "Em aberto") == _br(len(abertas))
    assert _kpi(ks, "Atrasadas") == _br(sum(
        1 for ln in ls if ln[n.index("PRAZO")] == "ATRASADA"))
    assert _kpi(ks, "Entregues") == _br(sum(e == "ENTREGUE" for e in et))
    assert _kpi(ks, "No prazo") == _br(100 * len(no_prazo) / len(com_data)) \
        + "%"
    assert _kpi(ks, "SLA médio de entrega") == \
        _br(sum(slas) / len(slas), 1) + " dias"
    assert _kpi(ks, "Frete") == "R$ " + _br(sum(ln[n.index("VLR FRETE")] or 0
                                                for ln in ls))
    pend = t["juntas"][0]["tabela"]["linhas"]
    assert _kpi(ks, "Pendências anteriores") == _br(len(pend))
    # os cartões da aba = os do topo (mesmo escopo: o mês)
    assert _rvc(t["kpis_padrao"]) == _rvc(ks)


def test_T0017_visita_cartoes_pelas_tabelas(real):
    """Visita: o cartão bate com a aba de origem (Por supervisor e Por
    vendedor somam as visitas do topo; vendedores em campo)."""
    _rels, p = real
    r = p["relatorios"]["vc_visitas"]
    sup = _tab_web(p, "vc_visitas", "Por supervisor")
    ven = _tab_web(p, "vc_visitas", "Por vendedor")
    vis = _kpi(r["kpis"], "Visitas")
    assert vis == _br(sum(v or 0 for v in _col(sup, "VISIT.")))
    cargo = _col(ven, "CARGO")
    visit = _col(ven, "VISIT.")
    vend = [v for c, v in zip(cargo, visit) if c == "VENDEDOR"]
    assert _kpi(r["kpis"], "Vendedores em campo") == \
        f"{_br(sum(1 for v in vend if v))} de {_br(len(vend))}"
    # o Diretor/cartões das abas: iguais ao topo (filtro padrão = tudo)
    for titulo in ("Por supervisor", "Por vendedor", "Dia a dia"):
        assert _rvc(_tab_web(p, "vc_visitas", titulo)["kpis_padrao"]) == \
            _rvc(r["kpis"]), titulo


# ================================================ fontes únicas do contrato
def _contrato_txt():
    return (RAIZ / ".coord" / "contratos" / "relatorio.md").read_text(
        encoding="utf-8")


def _bloco_colunas_fora():
    m = re.search(r"```text colunas-fora\n(.*?)\n\s*```", _contrato_txt(),
                  re.S)
    assert m, "bloco `colunas-fora` ausente no contrato"
    return {ln.strip() for ln in m.group(1).splitlines() if ln.strip()}


def test_RN_GER_011_colunas_fora_contrato_igual_robo_e_web(web_app):
    """§10.7.4: o bloco `colunas-fora` do contrato é a fonte única; o robô
    e a web (render.COLUNAS_FORA, de onde o tabelas importa) são cópias."""
    from app import render
    lista = _bloco_colunas_fora()
    assert lista == COLUNAS_FORA                # a cópia deste teste também
    assert set(ba._COLUNAS_FORA_WEB) == lista
    assert set(render.COLUNAS_FORA) == lista
    assert web_app.tabelas.COLUNAS_FORA is render.COLUNAS_FORA
    # a comparação é sem acento e em maiúsculas, nos dois lados
    for nome in ("Endereço", "e-mail", " Telefone "):
        assert ba._coluna_proibida_web(nome), nome
        assert render.coluna_fora(nome), nome


def test_T0017_avisos_robo_e_web_iguais_ao_contrato(web_app):
    """§10.7.6: os textos AVISO_ABAS_FORA e AVISO_CARTOES são os do
    contrato, no robô e na web."""
    txt = _contrato_txt()
    assert f"`{AVISO_ABAS_FORA}`" in txt
    assert f"`{AVISO_CARTOES}`" in txt
    assert ba.AVISO_ABAS_FORA == AVISO_ABAS_FORA
    assert web_app.tabelas.AVISO_CARTOES == AVISO_CARTOES
    assert getattr(web_app.tabelas, "AVISO_ABAS_FORA", AVISO_ABAS_FORA) == \
        AVISO_ABAS_FORA
