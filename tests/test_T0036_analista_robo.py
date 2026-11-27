"""T-0036: os 4 faróis do Analista Comercial no pacote web (robô × PC × web).

Contrato `.coord/contratos/relatorio.md` §10.11 (branch do desenho T-0036) e
`docs/desenho/T-0036.md` §3. Regras citadas:
- RN-GER-011: no site, cliente só pelo código; sem nome, endereço, telefone,
  e-mail ou documento; texto livre limpo ("[removido]");
- RN-GER-005: a conta 000040 (vendedor de teste) fora da pesquisa;
- RN-GER-006: faturamento pela filial da nota; pesquisa e divergências pela
  UF do cliente;
- RN-GER-002: faturado pela data da NF (o mês do Saldo).

Dados: as bases congeladas do repositório (os mesmos dos testes T-0017 e
T-0024) e, onde o teste planta dado, só valores fictícios (código 9xxxxx,
"CLIENTE FICTICIO", CNPJ/telefone/e-mail inventados). Nenhuma mensagem de
falha imprime valor das bases: só contagens e títulos.
"""
import copy
import json
import re
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn
from escopo_farois_web import UF_LINHAS_T0036
from pacote_web_util import col as _col
from pacote_web_util import tam_sem_anexos as _tam

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
MES_ROT = "NOV/26"
RIDS = ("vc_saldo", "vc_markup", "vc_preco", "an_divergencias")
MB = 1024 * 1024
AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."
AVISO_MARKUP_ATIVOS = ("A aba Todos os produtos ficou só com os produtos com "
                       "estoque ou venda, para caber no pacote. Veja o resto "
                       "no PC.")
AVISO_CORRECAO_FORA = ("O Excel de correção ficou fora desta atualização "
                       "(arquivo grande). Gere no PC.")
# §10.11.1, ordem do PC
ABAS = {
    "vc_saldo": ["Pedido a pedido", "Por vendedor", "Por supervisor",
                 "Por UF"],
    "vc_markup": ["Por pedido", "Por UF", "Por cidade", "Por supervisor",
                  "Por vendedor", "Por categoria", "Por sistema",
                  "Por família", "Por linha", "Por produto",
                  "Todos os produtos"],
    "vc_preco": ["Por categoria", "Por família", "Total BAP",
                 "Reajustes por produto", "Pesquisa de mercado"],
    "an_divergencias": ["Por vendedor", "Clientes divergentes",
                        "Sem coordenada / endereço"]}


# ============================== lista positiva do §10.11.3, escrita à mão
def _l(spec):
    """"NOME:tipo:o|..." -> [(nome, tipo, oculta)]; sem tipo = texto."""
    out = []
    for item in spec.split("|"):
        partes = item.split(":")
        nome = partes[0]
        tipo = partes[1] if len(partes) > 1 and partes[1] else "texto"
        out.append((nome, tipo, len(partes) > 2 and partes[2] == "o"))
    return out


_SALDO_AGREG = ("PEDIDOS:int|VLR TABELA:moeda|VLR VENDA:moeda|"
                "DESC. COMERCIAL:moeda|% DESC. COM.:pct1|SALDO FRETE:moeda|"
                "SALDO:moeda|META SALDO:moeda|% ATING.:pct")
_MK1 = ("PEDIDOS:int|QTD:num|R$ VENDA:moeda|CUSTO:moeda|MARGEM:moeda|"
        "MARKUP %:pct1|MKP TABELA %:pct1|% DESC.:pct1|PART. MARGEM:pct1|"
        "SEM CUSTO:int")
_MK2 = ("PRODUTOS:int|ESTOQUE:num|VOL. VENDIDO:num|R$ VENDA:moeda|"
        "CUSTO:moeda|MARGEM:moeda|MKP REAL %:pct1|% DESC.:pct1|"
        "MKP TABELA %:pct1|MKP VENDA %:pct1|PART. MARGEM:pct1|SEM CUSTO:int")
_PRECO = ("MÊS|AAAA-MM::o|{x}|LEITURA|FATURAMENTO:moeda|VAR. FAT. %:pct1|"
          "VOLUME:num|VAR. VOL. %:pct1|PREÇO MÉDIO:moeda2|"
          "PREÇO TABELA:moeda2|VAR. PREÇO %:pct1|VAR. TABELA %:pct1|"
          "VAR. FAT. R$:moeda|EFEITO PREÇO:moeda|EFEITO VOLUME:moeda|"
          "EFEITO MIX:moeda|ELASTICIDADE:num2")
LISTA_1093 = {
    ("vc_saldo", "Pedido a pedido"): _l(
        "MÊS::o|DATA NF:dia|FILIAL|PEDIDO|CÓD.|VENDEDOR|COND. PAGTO|"
        "VLR TABELA:moeda|VLR VENDA:moeda|% DESC. COM.:pct1|"
        "SALDO DO PEDIDO:moeda|SALDO FRETE:moeda|NO SALDO:moeda|NF|"
        "SUPERVISOR|DESC. COMERCIAL:moeda|UF|CHAVE::o"),
    ("vc_saldo", "Por vendedor"): _l("MÊS::o|VENDEDOR|SUPERVISOR|"
                                     + _SALDO_AGREG),
    ("vc_saldo", "Por supervisor"): _l("MÊS::o|SUPERVISOR|" + _SALDO_AGREG),
    ("vc_saldo", "Por UF"): _l("MÊS::o|UF|" + _SALDO_AGREG),
    ("vc_markup", "Por pedido"): _l(
        "SITUAÇÃO|DATA PED.:dia|DATA NF:dia|FILIAL|PEDIDO|NF|CÓD.|"
        "STATUS PROTHEUS::o|STATUS|SITUAÇÃO PLANNER::o|UF|CIDADE|"
        "SUPERVISOR|VENDEDOR|QTD:num|R$ VENDA:moeda|CUSTO:moeda|"
        "SUCATA:moeda|MARGEM:moeda|MARKUP %:pct1|MKP TABELA %:pct1|"
        "% DESC.:pct1|SEM CUSTO:int|VENDA SEM CUSTO:moeda:o|SO BATERIA::o|"
        "CÓD. AUTORIZAÇÃO|AUTORIZADO POR"),
    **{("vc_markup", t): _l(f"{c}|" + _MK1) for t, c in (
        ("Por UF", "UF"), ("Por cidade", "CIDADE"),
        ("Por supervisor", "SUPERVISOR"), ("Por vendedor", "VENDEDOR"))},
    **{("vc_markup", t): _l(f"{c}|" + _MK2) for t, c in (
        ("Por categoria", "CATEGORIA"), ("Por sistema", "SISTEMA"),
        ("Por família", "FAMÍLIA"), ("Por linha", "LINHA"))},
    ("vc_markup", "Por produto"): _l(
        "PRODUTO|DESCRIÇÃO|CATEGORIA::o|SISTEMA::o|FAMÍLIA::o|LINHA::o|"
        "SITUAÇÃO|ESTOQUE:num|CUSTO UNIT.:moeda2|PRC. TABELA MÉD.:moeda2|"
        "MKP TABELA %:pct1|PRC. VENDA MÉD.:moeda2|MKP VENDA %:pct1|"
        "VOL. VENDIDO:num|R$ VENDA:moeda|CUSTO:moeda|MARGEM:moeda|"
        "MKP REAL %:pct1|% DESC.:pct1|PART. MARGEM:pct1"),
    ("vc_markup", "Todos os produtos"): _l(
        "PRODUTO|DESCRIÇÃO|CATEGORIA|SISTEMA|FAMÍLIA|LINHA|FORNECEDOR|"
        "CUSTO:moeda2|ORIGEM CUSTO::o|PRC. TABELA MÉD.:moeda2|% DESC.:pct1|"
        "PRC. VENDA MÉD.:moeda2|MKP VENDA %:pct1|"
        "PREÇO INTERIOR MÉDIO:moeda2:o|MKP TABELA %:pct1:o|"
        "MKP INTERIOR %:pct1:o|EST.:num|SITUAÇÃO|QTD VEND.:num|"
        "R$ VENDA:moeda|MKP REAL %:pct1|ÚLT. VENDA:data"),
    **{("vc_preco", t): _l(_PRECO.format(x=c)) for t, c in (
        ("Por categoria", "CATEGORIA"), ("Por família", "FAMÍLIA"),
        ("Total BAP", "TOTAL"))},
    ("vc_preco", "Reajustes por produto"): _l(
        "MÊS|AAAA-MM::o|FILIAL|CÓD. PRODUTO|PRODUTO|CATEGORIA::o|FAMÍLIA|"
        "LEITURA|TABELA ANTES:moeda2:o|TABELA AGORA:moeda2:o|"
        "VAR. TABELA %:pct1|PRATICADO ANTES:moeda2:o|"
        "PREÇO PRATICADO:moeda2|VAR. PREÇO %:pct1|QTD ANTES:num:o|QTD:num|"
        "VAR. QTD %:pct1|FAT. ANTES:moeda:o|FATURAMENTO:moeda|"
        "VAR. FAT. %:pct1|SISTEMA::o|LINHA::o"),
    ("vc_preco", "Pesquisa de mercado"): _l(
        "MÊS::o|DATA:data|VENDEDOR|SUPERVISOR::o|CIDADE|UF|SEGMENTO::o|"
        "LINHA DIA FOCO|PAPEL|CÓD. BAP|PRODUTO|CONCORRENTE|"
        "CÓD. CONCORRENTE::o|LEITURA|COMPRA BAP:moeda2|COMPRA CONC.:moeda2|"
        "DIF. COMPRA %:pct1|VENDA BAP:moeda2|VENDA CONC.:moeda2|"
        "DIF. VENDA %:pct1|MKP CLIENTE BAP %:pct1|MKP CLIENTE CONC. %:pct1|"
        "PRC. TABELA BAP:moeda2|COMPRA x TABELA %:pct1|ESTOQUE BAP:num|"
        "ESTOQUE CONC.:num|SHARE ESTOQUE %:pct1|VOL. BAP:num|VOL. CONC.:num|"
        "SHARE VOLUME %:pct1|OBSERVAÇÃO|CATEGORIA::o|FAMÍLIA::o"),
    ("an_divergencias", "Por vendedor"): _l(
        "VENDEDOR|SUPERVISOR|CARTEIRA PLANNER:int|BASE PROTHEUS:int|"
        "IGUAIS:int|SÓ NO PLANNER:int|SÓ NO PROTHEUS:int|"
        "· FORA DA BASE:int|· PLANNER SEM VENDEDOR:int|BATE?"),
    ("an_divergencias", "Clientes divergentes"): _l(
        "COD|LOJA|CIDADE|UF|SEGMENTO|ZONA|VENDEDOR PLANNER|"
        "VENDEDOR PROTHEUS (A1_VEND)|STATUS PROTHEUS::o|SITUAÇÃO|"
        "O QUE FAZER"),
    ("an_divergencias", "Sem coordenada / endereço"): _l(
        "CÓD.|LOJA|O QUE FALTA|NA ROTA DO MÊS|UF|CIDADE|VENDEDOR PLANNER|"
        "SUPERVISOR PLANNER|SEGMENTO|CURVA|SITUAÇÃO|PONTO"),
}
# o número de colunas que o §10.11.3 escreve ao lado de cada aba
N_1093 = {("vc_saldo", "Pedido a pedido"): 18, ("vc_saldo", "Por vendedor"): 12,
          ("vc_saldo", "Por supervisor"): 11, ("vc_saldo", "Por UF"): 11,
          ("vc_markup", "Por pedido"): 27, ("vc_markup", "Por produto"): 20,
          ("vc_markup", "Todos os produtos"): 22,
          ("vc_preco", "Reajustes por produto"): 22,
          ("vc_preco", "Pesquisa de mercado"): 33,
          ("an_divergencias", "Por vendedor"): 10,
          ("an_divergencias", "Clientes divergentes"): 11,
          ("an_divergencias", "Sem coordenada / endereço"): 12}
# colunas de cliente que nunca vão nestes 4 (§10.11.2), sem acento
NOMES_FORA = ("CLIENTE", "RAZAO", "FANTASIA", "ENDERECO", "BAIRRO", "Nº",
              "TELEFONE", "CELULAR", "WHATSAPP", "E-MAIL", "EMAIL", "CNPJ",
              "CPF", "CONTATO")
# métricas com a palavra CLIENTE que não são dado do cliente (markup do PDV)
METRICAS_CLIENTE = {"MKP CLIENTE BAP %", "MKP CLIENTE CONC. %"}
RE_DOC = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}")
RE_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
RE_FONE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}-\d{4}")


def _sem_acento(s):
    import unicodedata                                  # noqa: PLC0415
    return "".join(c for c in unicodedata.normalize("NFD", str(s))
                   if unicodedata.category(c) != "Mn").upper()


def _montar(rids=RIDS):
    return {rid: rn.montar(rid, RAIZ, hoje=HOJE, params=dict(PARAMS))
            for rid in rids}


class _Sigilo(tuple):
    """Par (rels, pacote) com repr sem dado: a falha do pytest não imprime
    nome de cliente nem de vendedor das bases (regra 6)."""
    def __repr__(self):
        return "<bases congeladas: repr oculto>"


@pytest.fixture(scope="module")
def real():
    """(rels do PC, relatorios do pacote) dos 4 faróis, bases congeladas."""
    rels = _montar()
    pac = ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)["relatorios"]
    return _Sigilo((rels, pac))


def _tab(farol, titulo):
    return next((t for t in farol.get("tabelas") or []
                 if t.get("titulo") == titulo), None)


def _textos(obj):
    """Todas as strings de um objeto JSON (chaves e valores)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _textos(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _textos(v)


# ================================================ RN-GER-011: código do cliente
@pytest.mark.parametrize("texto, codigo", [
    ("900123-01 - CLIENTE FICTICIO LTDA", "900123-01"),        # com loja
    ("900123 - CLIENTE FICTICIO LTDA", "900123"),              # sem loja
    ("900123-01", "900123-01"),                                 # só o código
    ("  900123-01 - CLIENTE FICTICIO", "900123-01"),           # espaço antes
    ("900123-01 - CLIENTE FICTICIO 12.345.678/0001-90", "900123-01"),  # CNPJ no fim
    ("900123-01 - CLIENTE FICTICIO 123.456.789-09", "900123-01"),      # CPF no fim
    ("CLIENTE FICTICIO LTDA", ""),                              # sem código
    ("", ""),
    (None, ""),
])
def test_RN_GER_011_codigo_do_cliente_sem_nome(texto,
                                                codigo):
    saida = rn.codigo_do_cliente(texto)
    assert saida == codigo
    assert "FICTICIO" not in saida and not RE_DOC.search(saida)


@pytest.mark.parametrize("texto", ["12345678000190 - CLIENTE FICTICIO",
                                   "12345678909 CLIENTE FICTICIO"])
def test_RN_GER_011_codigo_do_cliente_documento_no_comeco_nao_vira_codigo(
        texto):
    """RN-GER-011: sem CPF/CNPJ "no começo, no meio ou no fim". O código do
    PC tem 6 dígitos (§10.11.2: `^\\d{6}(-\\d{2})? - `)."""
    assert rn.codigo_do_cliente(texto) == ""


def test_RN_GER_011_cliente_por_codigo_web_troca_a_coluna_e_nao_muda_a_entrada():
    t = {"titulo": "Pedido a pedido",
         "colunas": [{"nome": "PEDIDO", "tipo": "texto"},
                     {"nome": "CLIENTE", "tipo": "texto", "largura": 200},
                     {"nome": "VLR VENDA", "tipo": "moeda"}],
         "linhas": [["P1", "900001-01 - CLIENTE FICTICIO UM", 10.0],
                    ["P2", "CLIENTE FICTICIO SEM CODIGO", 5.0]],
         "total": ["TOTAL", "", 15.0]}
    antes = json.dumps(t, sort_keys=True)
    s = ba._cliente_por_codigo_web(t, "CLIENTE")
    assert json.dumps(t, sort_keys=True) == antes            # pura
    assert [c["nome"] for c in s["colunas"]] == ["PEDIDO", "CÓD.", "VLR VENDA"]
    assert s["colunas"][1] == {"nome": "CÓD.", "tipo": "texto", "largura": 200}
    assert s["linhas"] == [["P1", "900001-01", 10.0], ["P2", "", 5.0]]
    assert s["total"] == ["TOTAL", "", 15.0]
    assert "FICTICIO" not in json.dumps(s, ensure_ascii=False)
    # sem a coluna: a própria tabela
    assert ba._cliente_por_codigo_web(t, "OUTRA") is t


def test_RN_GER_011_analista_sem_coluna_de_nome_endereco_telefone(real):
    """Em nenhuma aba dos 4 faróis vai coluna de nome, endereço, telefone,
    e-mail ou documento do cliente (§10.11.2). O cliente fica pelo código."""
    _rels, pac = real
    achados = []
    for rid in RIDS:
        for t in pac[rid].get("tabelas") or []:
            for c in t["colunas"]:
                n = _sem_acento(c["nome"])
                if c["nome"] not in METRICAS_CLIENTE and any(x in n.split() or n == x or n.startswith(x + " ")
                       for x in NOMES_FORA):
                    achados.append((rid, t["titulo"], c["nome"]))
    assert achados == []
    # anexo de correção sem CLIENTE
    for parte in pac["an_divergencias"]["correcao"].values():
        assert "CLIENTE" not in [c["nome"] for c in parte["colunas"]]


def _nomes_de_cliente(rels):
    """Os nomes de cliente que o PC mostra (só para conferir; nunca
    impressos). Saem do 'código - nome', do CLIENTE só nome, da razão social
    e do nome fantasia."""
    nomes = set()
    fontes = (("vc_saldo", "Pedido a pedido", "CLIENTE", True),
              ("vc_markup", "Por pedido", "CLIENTE", True),
              ("vc_preco", "Pesquisa de mercado", "CLIENTE", False),
              ("an_divergencias", "Clientes divergentes", "CLIENTE", False),
              ("an_divergencias", "Sem coordenada / endereço",
               "RAZÃO SOCIAL", False),
              ("an_divergencias", "Sem coordenada / endereço",
               "NOME FANTASIA", False))
    for rid, titulo, col, com_codigo in fontes:
        t = _tab(rels[rid], titulo)
        for v in _col(t, col):
            v = str(v or "").strip()
            if com_codigo:
                v = re.sub(r"^\s*\d+(-\d+)?\s+-\s+", "", v)
            if len(v) >= 10:            # nome curto/genérico não prova nada
                nomes.add(v.upper())
    return nomes


def test_RN_GER_011_analista_sem_nome_de_cliente_no_pacote(real):
    """Nenhum nome de cliente do PC (10+ caracteres) aparece em célula,
    cartão, painel ou anexo dos 4 faróis. A mensagem só dá a contagem."""
    rels, pac = real
    nomes = _nomes_de_cliente(rels)
    assert len(nomes) > 100                     # o PC tem cliente com nome
    textos = {s.upper() for rid in RIDS for s in _textos(pac[rid])}
    vazou = sum(1 for s in textos if s in nomes)
    assert vazou == 0, f"{vazou} célula(s) com nome de cliente"
    # dentro de frase (insights, avisos): busca por pedaço nas strings longas
    frases = [s for s in textos if len(s) > 40]
    em_frase = sum(1 for nm in nomes for s in frases if nm in s)
    assert em_frase == 0, f"{em_frase} frase(s) com nome de cliente"


def test_RN_GER_011_cliente_ficticio_plantado_sai_so_pelo_codigo():
    """Planta um cliente fictício (com CNPJ inventado) no Pedido a pedido do
    Saldo e no Por pedido do Markup: no pacote, só o código."""
    rels = _montar(("vc_saldo", "vc_markup"))
    for rid, titulo in (("vc_saldo", "Pedido a pedido"),
                        ("vc_markup", "Por pedido")):
        t = _tab(rels[rid], titulo)
        i = [c["nome"] for c in t["colunas"]].index("CLIENTE")
        for k, ln in enumerate(t["linhas"]):
            ln[i] = f"9{k:05d}-01 - CLIENTE FICTICIO {k} 12.345.678/0001-90"
    pac = ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)["relatorios"]
    for rid, titulo in (("vc_saldo", "Pedido a pedido"),
                        ("vc_markup", "Por pedido")):
        t = _tab(pac[rid], titulo)
        assert t is not None, (rid, titulo)
        cods = _col(t, "CÓD.")
        assert cods == [f"9{k:05d}-01" for k in range(len(cods))]
        txt = json.dumps(pac[rid], ensure_ascii=False)
        assert "FICTICIO" not in txt and "12.345.678/0001-90" not in txt


def test_RN_GER_011_pesquisa_texto_livre_limpo_e_sem_cliente():
    """Telefone, e-mail e CNPJ fictícios no texto livre da Pesquisa de
    mercado viram "[removido]"; a coluna CLIENTE sai."""
    rels = _montar(("vc_preco",))
    t = _tab(rels["vc_preco"], "Pesquisa de mercado")
    nomes = [c["nome"] for c in t["colunas"]]
    sujo = ("ligar (92) 99876-5432 ou ficticio@exemplo.com.br, "
            "CNPJ 12.345.678/0001-90")
    for col in ("OBSERVAÇÃO", "PRODUTO", "CONCORRENTE", "CÓD. CONCORRENTE"):
        t["linhas"][0][nomes.index(col)] = f"{col} {sujo}"
    t["linhas"][0][nomes.index("CLIENTE")] = "CLIENTE FICTICIO DA PESQUISA"
    pac = ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)["relatorios"]
    w = _tab(pac["vc_preco"], "Pesquisa de mercado")
    assert w is not None
    assert "CLIENTE" not in [c["nome"] for c in w["colunas"]]
    k = next(j for j, v in enumerate(_col(w, "OBSERVAÇÃO"))
             if str(v).startswith("OBSERVAÇÃO "))
    for col in ("OBSERVAÇÃO", "PRODUTO", "CONCORRENTE", "CÓD. CONCORRENTE"):
        v = _col(w, col)[k]
        assert v.startswith(col) and "[removido]" in v, col
        assert not (RE_DOC.search(v) or RE_EMAIL.search(v)
                    or RE_FONE.search(v)), col
    txt = json.dumps(pac["vc_preco"], ensure_ascii=False)
    assert "CLIENTE FICTICIO DA PESQUISA" not in txt
    assert "ficticio@exemplo" not in txt and "99876-5432" not in txt


def test_RN_GER_005_pesquisa_sem_000040(real):
    """O vendedor de teste 000040 não aparece na Pesquisa de mercado do site
    (o nome dele vem do Por vendedor das Divergências; não é impresso)."""
    rels, pac = real
    div = _tab(rels["an_divergencias"], "Por vendedor")
    v40 = [re.sub(r"^000040\s*-\s*", "", str(v)).strip()
           for v in _col(div, "VENDEDOR") if str(v).startswith("000040")]
    pesq = _tab(pac["vc_preco"], "Pesquisa de mercado")
    vends = {str(v).strip() for v in _col(pesq, "VENDEDOR")}
    # só contagens na falha (regra 6: nenhum nome de vendedor impresso)
    n_cod = sum(1 for v in vends if v.startswith("000040"))
    assert n_cod == 0, "código 000040 na pesquisa"
    n_nome = len(set(v40) & vends)
    assert n_nome == 0, "vendedor 000040 na pesquisa"


# ============================================ RN-GER-006: estado das linhas
def test_RN_GER_006_uf_linhas_pela_filial_e_pela_uf_do_cliente(real):
    """Saldo, Markup e Reajustes: estado = filial da nota; Por UF do Saldo,
    Pesquisa e Divergências: a coluna UF (UF do cliente)."""
    _rels, pac = real
    for (rid, titulo), (coluna, modo) in UF_LINHAS_T0036.items():
        t = _tab(pac[rid], titulo)
        if modo == "filial":
            assert t["uf_linhas"] == [rn.uf_do_nome_da_filial(f) for f in
                                      _col(t, coluna)], (rid, titulo)
            assert {u for u in t["uf_linhas"] if u} <= set(
                rn.FILIAL_UF.values())
        else:
            assert t["uf_linhas"] == [str(u or "").strip().upper()
                                      for u in _col(t, coluna)], (rid, titulo)
    # Preço e Divergências sem cartões por estado (§10.11.1)
    for rid in ("vc_preco", "an_divergencias"):
        assert not pac[rid].get("recortes"), rid


# ======================================================= lista positiva
def test_RN_GER_011_colunas_positivas_lista_do_robo_igual_ao_contrato():
    robo = {(rid, titulo): [(n, tp, bool(o)) for n, tp, o, _s in cols]
            for rid, tabs in ba._COLUNAS_TABELAS_WEB.items() if rid in RIDS
            for titulo, cols in tabs.items()}
    assert sorted(robo) == sorted(LISTA_1093)
    for k, cols in LISTA_1093.items():
        assert robo[k] == cols, k
        if k in N_1093:
            assert len(cols) == N_1093[k], k
    for rid in RIDS:
        assert list(ba._ABAS_TABELAS_WEB[rid]) == ABAS[rid], rid


def test_RN_GER_011_colunas_positivas_pacote_real_com_todas_as_abas(real):
    """Nas bases congeladas nenhuma aba cai: os 4 faróis vão com as abas na
    ordem do PC e as colunas exatas do §10.11.3."""
    _rels, pac = real
    for rid in RIDS:
        tabs = pac[rid].get("tabelas") or []
        assert [t["titulo"] for t in tabs] == ABAS[rid], rid
        for t in tabs:
            got = [(c["nome"], c["tipo"], bool(c.get("oculta")))
                   for c in t["colunas"]]
            assert got == LISTA_1093[(rid, t["titulo"])], (rid, t["titulo"])
            assert all(len(ln) == len(got) for ln in t["linhas"])


def test_RN_GER_011_colunas_positivas_coluna_a_mais_no_pc_tira_a_aba():
    """Coluna nova no PC (fora do §10.11.3): o robô tira a aba, com o aviso
    único de abas fora; as outras abas e os cartões seguem."""
    rels = _montar(("vc_saldo",))
    t = _tab(rels["vc_saldo"], "Por UF")
    t["colunas"].append({"nome": "COLUNA NOVA", "tipo": "texto"})
    for ln in t["linhas"]:
        ln.append("x")
    f = ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)["relatorios"]["vc_saldo"]
    assert [x["titulo"] for x in f["tabelas"]] == ABAS["vc_saldo"][:3]
    assert AVISO_ABAS_FORA.format(lista="Por UF") in f["avisos"]
    assert [k["valor"] for k in f["kpis"]] == [
        k["valor"] for k in rels["vc_saldo"]["kpis"]]


def test_RN_GER_011_colunas_positivas_web_aceita_o_pacote_real_do_robo(
        real, web_app):
    """O pacote real do robô passa na validação da web (§10.11.2)."""
    _rels, pac = real
    tb = web_app.tabelas
    for rid in RIDS:
        assert tb.validar(rid, copy.deepcopy(pac[rid])) == [], rid


# ============================================================ cortes
def test_T0036_markup_cortes_quatro_passos_em_ordem(real):
    """§10.11.5: acima do teto, o Markup corta (1) Todos os produtos só com
    estoque ou venda, (2) Todos os produtos sai, (3) Por produto sai, (4) as
    tabelas saem; cada passo com o seu aviso; cartões intactos."""
    _rels, pac = real
    f = pac["vc_markup"]
    antes = json.dumps(f, ensure_ascii=False, sort_keys=True)
    todos = _tab(f, "Todos os produtos")
    nomes = [c["nome"] for c in todos["colunas"]]
    ie, iq = nomes.index("EST."), nomes.index("QTD VEND.")

    def ativo(ln):
        return any(isinstance(ln[i], (int, float)) and not isinstance(
            ln[i], bool) and ln[i] > 0 for i in (ie, iq))
    ficam = [k for k, ln in enumerate(todos["linhas"]) if ativo(ln)]
    assert 0 < len(ficam) < len(todos["linhas"])       # o passo 1 corta algo

    # passo 1
    p1 = ba._cortar_farol_web("vc_markup", f, teto_mb=(_tam(f) - 1) / MB)
    t1 = _tab(p1, "Todos os produtos")
    assert t1["linhas"] == [todos["linhas"][k] for k in ficam]
    assert t1["tons"] == [todos["tons"][k] for k in ficam]
    assert [x["titulo"] for x in p1["tabelas"]] == ABAS["vc_markup"]
    assert AVISO_MARKUP_ATIVOS in p1["avisos"]
    assert not any(str(a).startswith("Abas fora") for a in p1["avisos"])
    # passo 2
    p2 = ba._cortar_farol_web("vc_markup", f, teto_mb=(_tam(p1) - 1) / MB)
    assert [x["titulo"] for x in p2["tabelas"]] == ABAS["vc_markup"][:-1]
    assert AVISO_ABAS_FORA.format(lista="Todos os produtos") in p2["avisos"]
    # passo 3
    p3 = ba._cortar_farol_web("vc_markup", f, teto_mb=(_tam(p2) - 1) / MB)
    assert [x["titulo"] for x in p3["tabelas"]] == ABAS["vc_markup"][:-2]
    assert AVISO_ABAS_FORA.format(
        lista="Por produto, Todos os produtos") in p3["avisos"]
    # passo 4
    p4 = ba._cortar_farol_web("vc_markup", f, teto_mb=(_tam(p3) - 1) / MB)
    assert "tabelas" not in p4
    assert AVISO_ABAS_FORA.format(lista=", ".join(ABAS["vc_markup"])) \
        in p4["avisos"]
    assert sum(1 for a in p4["avisos"] if str(a).startswith("Abas fora")) == 1
    for p in (p1, p2, p3, p4):
        assert p["kpis"] == f["kpis"]
    # a entrada não mudou
    assert json.dumps(f, ensure_ascii=False, sort_keys=True) == antes


@pytest.mark.parametrize("rid", ["vc_saldo", "vc_preco", "an_divergencias"])
def test_T0036_outros_tres_so_perdem_as_tabelas(real, rid):
    _rels, pac = real
    f = pac[rid]
    p = ba._cortar_farol_web(rid, f, teto_mb=(_tam(f) - 1) / MB)
    assert "tabelas" not in p
    assert AVISO_ABAS_FORA.format(lista=", ".join(ABAS[rid])) in p["avisos"]
    assert p["kpis"] == f["kpis"]


def test_T0036_correcao_acima_do_teto_sai_so_o_anexo(real):
    _rels, pac = real
    f = copy.deepcopy(pac["an_divergencias"])
    cheio = f["correcao"]["analisar"]["linhas"]
    while len(json.dumps(f["correcao"], ensure_ascii=False).encode()) \
            <= ba.MAX_CORRECAO_BYTES:
        cheio.extend(copy.deepcopy(cheio))
    p = ba._cortar_farol_web("an_divergencias", f)
    assert "correcao" not in p and AVISO_CORRECAO_FORA in p["avisos"]
    assert [t["titulo"] for t in p["tabelas"]] == ABAS["an_divergencias"]


# ============================================ Excel de correção (PC e web)
def _divs_ficticias():
    return [
        {"filial": "0101002", "cod": "900001", "loja": "01",
         "nome": "CLIENTE FICTICIO UM", "cidade": "CIDADE FICTICIA",
         "uf": "AM", "vend_protheus": "000901", "vend_planner": "000902",
         "status_protheus": "ATIVO", "situacao": rn.SIT_CORRIGIR[0],
         "acao": "trocar"},
        {"filial": "0101005", "cod": "900002", "loja": "02",
         "nome": "CLIENTE FICTICIO DOIS", "cidade": "CIDADE FICTICIA 2",
         "uf": "PA", "vend_protheus": "", "vend_planner": None,
         "status_protheus": "ATIVO", "situacao": "FICTICIA PARA ANALISAR",
         "acao": "ver no cadastro"},
        {"filial": "0101007", "cod": "900003", "loja": "01",
         "nome": "CLIENTE FICTICIO TRES", "cidade": "CIDADE FICTICIA 3",
         "uf": "PA", "vend_protheus": "000903", "vend_planner": "000999",
         "status_protheus": "BLOQUEADO", "situacao": rn.SIT_CORRIGIR[-1],
         "acao": "trocar"}]


def _antigo(divs, pes, sup):
    """O gravar_correcao de antes da T-0036 (origin/main a81c2e4), linha a
    linha: o oráculo do "igual ao de antes"."""
    c, a = [], []
    for d in divs:
        if d["situacao"] in rn.SIT_CORRIGIR:
            v = d["vend_planner"]
            c.append([d["filial"], d["cod"], d["loja"], d["nome"],
                      d["cidade"], d["uf"], d["vend_protheus"], v,
                      (pes.get(v) or {}).get("nome", ""), sup(v),
                      d["status_protheus"]])
        else:
            a.append([d["filial"], d["cod"], d["loja"], d["nome"],
                      d["cidade"], d["uf"], d["vend_planner"] or "",
                      d["vend_protheus"], d["situacao"], d["acao"]])
    return c, a


def _ler_xlsx(arq):
    from openpyxl import load_workbook                  # noqa: PLC0415
    wb = load_workbook(arq)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = [["" if v is None else v for v in r]
                         for r in ws.iter_rows(values_only=True)]
    return out


def test_RN_GER_011_gravar_correcao_igual_ao_de_antes(tmp_path, monkeypatch):
    divs = _divs_ficticias()
    pes = {"000902": {"nome": "VENDEDOR FICTICIO 02"},
           "000999": {"nome": "VENDEDOR FICTICIO 99"}}

    def sup(v):
        return f"SUPERVISOR FICTICIO {v}" if v else ""
    monkeypatch.setattr(rn, "_para_corrigir", lambda ctx, chaves=None: [
        d for d in divs if chaves is None or (d["cod"], d["loja"]) in chaves])
    monkeypatch.setattr(rn, "_vendedores_do_planner", lambda ctx: pes)
    monkeypatch.setattr(rn, "_sup_nome", lambda ctx, v: sup(v))
    destino, n1, n2 = rn.gravar_correcao(None, tmp_path / "c.xlsx")
    c, a = _antigo(divs, pes, sup)
    assert (n1, n2) == (len(c), len(a)) == (2, 1)
    xl = _ler_xlsx(destino)
    assert list(xl) == ["CORRIGIR NO PROTHEUS", "ANALISAR"]
    assert xl["CORRIGIR NO PROTHEUS"][0] == [
        "A1_FILIAL", "A1_COD", "A1_LOJA", "CLIENTE", "CIDADE", "UF",
        "A1_VEND ATUAL", "A1_VEND CORRETO", "VENDEDOR CORRETO", "SUPERVISOR",
        "STATUS PROTHEUS"]
    assert xl["ANALISAR"][0] == [
        "A1_FILIAL", "A1_COD", "A1_LOJA", "CLIENTE", "CIDADE", "UF",
        "VENDEDOR NO PLANNER", "A1_VEND ATUAL", "SITUAÇÃO", "O QUE FAZER"]
    assert xl["CORRIGIR NO PROTHEUS"][1:] == c
    assert xl["ANALISAR"][1:] == a
    # com chaves: só o que estava na tela
    _d, m1, m2 = rn.gravar_correcao(None, tmp_path / "c2.xlsx",
                                    {("900002", "02")})
    assert (m1, m2) == (0, 1)
    # correcao_linhas = as mesmas linhas sem o CLIENTE (RN-GER-011)
    lin = rn.correcao_linhas(None)
    assert lin == {"corrigir": [r[:3] + r[4:] for r in c],
                   "analisar": [r[:3] + r[4:] for r in a]}
    assert "FICTICIO UM" not in json.dumps(lin, ensure_ascii=False)
    # e o anexo do robô: 10 e 9 colunas de texto, sem CLIENTE
    cor = ba._correcao_divergencias_web(
        {"correcao_linhas": lambda: rn.correcao_linhas(None)})
    assert [len(cor[k]["colunas"]) for k in ("corrigir", "analisar")] == [10, 9]
    assert cor["analisar"]["linhas"][0][3] == "CIDADE FICTICIA 2"
    assert all(isinstance(v, str) for k in cor for ln in cor[k]["linhas"]
               for v in ln)


def test_RN_GER_011_correcao_real_igual_ao_excel_do_pc_sem_cliente(real,
                                                                    tmp_path):
    """Bases congeladas: o anexo do site = o Excel do PC sem a coluna
    CLIENTE, linha a linha (o Excel fica no tmp; nada é impresso)."""
    rels, pac = real
    destino, n1, n2 = rels["an_divergencias"]["exportar_correcao"](
        tmp_path / "correcao.xlsx")
    xl = _ler_xlsx(destino)
    cor = pac["an_divergencias"]["correcao"]
    assert (len(cor["corrigir"]["linhas"]), len(cor["analisar"]["linhas"])) \
        == (n1, n2)
    for aba, chave in (("CORRIGIR NO PROTHEUS", "corrigir"),
                       ("ANALISAR", "analisar")):
        sem_cliente = [[str(v) for v in r[:3] + r[4:]] for r in xl[aba][1:]]
        site = cor[chave]["linhas"]
        # igualdade linha a linha, com só contagens na falha (regra 6: sem
        # nome de vendedor ou supervisor das bases na mensagem)
        n_xl, n_site = len(sem_cliente), len(site)
        assert n_xl == n_site, aba
        n_dif = sum(1 for a, b in zip(sem_cliente, site) if a != b)
        assert n_dif == 0, f"{aba}: linhas diferentes do Excel do PC"
    # valor x regra: n1 = linhas de "Clientes divergentes" com SITUAÇÃO em
    # rn.SIT_CORRIGIR = cartão "Vendedor diferente"; n2 = as outras linhas =
    # "Sem vendedor no Planner" + "Fora da base do Planner" + "Código
    # duplicado". Vale no PC e no site (o mesmo número do farol de origem).
    assert n1 > 0 and n2 > 0
    for farol in (rels["an_divergencias"], pac["an_divergencias"]):
        sit = _col(_tab(farol, "Clientes divergentes"), "SITUAÇÃO")
        assert n1 == sum(1 for x in sit if x in rn.SIT_CORRIGIR)
        assert n2 == sum(1 for x in sit if x not in rn.SIT_CORRIGIR)
        k = {x["rotulo"]: int(str(x["valor"]).replace(".", ""))
             for x in farol["kpis"]}
        assert n1 == k["Vendedor diferente"]
        assert n2 == (k["Sem vendedor no Planner"]
                      + k["Fora da base do Planner"] + k["Código duplicado"])


# ======================================== número do Diretor (Desconto comercial)
@pytest.fixture(scope="module")
def com_diretor(real):
    """O pacote com o vc_saldo e o vc_painel do mesmo mês (o histórico do
    Diretor vai para a cópia temporária do conftest)."""
    rels, _pac = real
    rp = {"vc_saldo": rels["vc_saldo"],
          "vc_painel": rn.montar("vc_painel", RAIZ, hoje=HOJE,
                                 params=dict(PARAMS))}
    return _Sigilo((rels, ba.montar_pacote_web(rp, 2026, 11,
                                               raiz=RAIZ)["relatorios"]))


def _rrm_desc(pac):
    for b in pac["vc_painel"]["abas"]["resultado"]["painel"]["blocos"]:
        for c in (b.get("dados") or {}).get("res", []):
            if c.get("chave") == "desc":
                return c
    return None


def _pct(txt):
    return float(str(txt).replace("%", "").replace(".", "").replace(",", "."))


def _desc_do_mes(t, filtro=None):
    """Regra: desconto comercial = Σ DESC. COMERCIAL ÷ Σ VLR TABELA × 100,
    nos pedidos com NF no mês (RN-GER-002), estado = filial da nota
    (RN-GER-006)."""
    ix = {c["nome"]: i for i, c in enumerate(t["colunas"])}
    ls = [ln for k, ln in enumerate(t["linhas"]) if ln[ix["MÊS"]] == MES_ROT
          and (filtro is None or t["uf_linhas"][k] == filtro)]
    dc = sum(ln[ix["DESC. COMERCIAL"]] for ln in ls)
    tb = sum(ln[ix["VLR TABELA"]] for ln in ls)
    return dc / tb * 100 if tb else None, dc


def test_RN_GER_006_numero_do_diretor_desconto_comercial_bate_com_o_saldo(
        com_diretor):
    """Valor × regra: o cartão "Desconto comercial" do vc_saldo, a coluna
    % DESC. COM. do Por UF, o cartão de cada estado (recortes) e as barras
    por estado do RRM do Diretor saem da mesma fórmula, no mesmo pacote."""
    _rels, pac = com_diretor
    s = pac["vc_saldo"]
    ped = _tab(s, "Pedido a pedido")
    total, dc = _desc_do_mes(ped)
    k = next(x for x in s["kpis"] if x["rotulo"] == "Desconto comercial")
    assert k["valor"] == rn.p(total)                    # "15%"
    assert k["detalhe"] == rn.moeda(dc)
    por_uf = _tab(s, "Por UF")
    ix = {c["nome"]: i for i, c in enumerate(por_uf["colunas"])}
    uf_pct = {ln[ix["UF"]]: ln[ix["% DESC. COM."]] for ln in por_uf["linhas"]
              if ln[ix["MÊS"]] == MES_ROT}
    assert set(uf_pct) == set(s["recortes"]) == {"AM", "MA", "PA"}
    rrm = _rrm_desc(pac)
    assert rrm is not None and rrm["titulo"] == "Desconto comercial"
    barras = {b[0]: b for b in rrm["estados"]["barras"] if b[1] is not None}
    for uf, v in uf_pct.items():
        regra, _ = _desc_do_mes(ped, uf)
        assert v == pytest.approx(regra), uf             # Por UF = regra
        kuf = next(x for x in s["recortes"][uf]["kpis"]
                   if x["rotulo"] == "Desconto comercial")
        assert kuf["valor"] == rn.p(regra), uf           # cartão do estado
        assert barras[uf][1] == pytest.approx(v), uf     # barra do Diretor
        assert _pct(barras[uf][2]) == round(v, 1), uf
    assert set(barras) == set(uf_pct)


@pytest.mark.xfail(strict=True, reason="DEFEITO ANTIGO fora da T-0036 "
                   "(T-0048, tarefa à parte, com simulação; modulo-farois, "
                   "painel_diretor.py): o Diretor lê o texto arredondado do "
                   "cartão do Saldo ('15%') e mostra '15,0%' com 1 casa; a "
                   "regra dá 15,1% (a barra do estado já usa o número cheio)")
def test_RN_GER_006_numero_do_diretor_desconto_comercial_total_com_uma_casa(
        com_diretor):
    _rels, pac = com_diretor
    total, _dc = _desc_do_mes(_tab(pac["vc_saldo"], "Pedido a pedido"))
    assert _pct(_rrm_desc(pac)["valor"]) == round(total, 1)
