"""T-0033: a marca BAP AUTOPARTS no código, pelo manual aprovado
(docs/marca/manual.md, R-20261126-182227-alexandre).

- RN-GER-009: o nome nos materiais é "BAP AUTOPARTS" (manual, seção 2).
  Nenhum "BAP Auto Parts", "BAP AUTO PARTS" ou "BAP Autoparts" nos .py, .bat
  e templates de produção. Fora: docs/legado/, os testes, os caminhos de
  pasta, domínio e e-mail (bapautoparts.com.br) e a detecção dos CNPJs
  internos (RN-GER-004), que precisa reconhecer a grafia antiga no cadastro.
- Cores: os tokens do site (`:root` do estilo.css) e as constantes do PC
  (bap_visual.py) têm o hex do manual (4.2); as cores que o manual tira
  ("sai"/"saem") não aparecem no site.
"""
import ast
import importlib.util
import io
import re
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import pytest

from marca_manual import RAIZ, tokens_do_manual

# ============================================================== o nome
# a grafia certa é só "BAP AUTOPARTS"; qualquer outra com espaço depois do BAP
# ("BAP Auto Parts", "BAP AUTO PARTS", "BAP Autoparts") é a errada
_NOME = re.compile(r"BAP[ \t]+AUTO[ \t]*PARTS", re.I)
# RN-GER-004: a regra dos CNPJs internos lê o nome do cadastro do ERP
_DETECCAO_INTERNO = re.compile(r"""["']BAP AUTO PARTS["']\s+in\s+\w+""")


def _arquivos_de_producao():
    """Os .py e .bat da raiz (a pasta de produção) e o site (web/app)."""
    arqs = [p for p in RAIZ.glob("*.py") if not p.name.startswith("smoke_")]
    arqs += list(RAIZ.glob("*.bat"))
    web = RAIZ / "web" / "app"
    for ext in ("*.py", "*.html", "*.js", "*.css", "*.txt", "*.j2"):
        arqs += list(web.rglob(ext))
    return sorted(arqs)


def _grafias_erradas(texto):
    for n, linha in enumerate(texto.splitlines(), 1):
        if _DETECCAO_INTERNO.search(linha):
            continue
        for m in _NOME.finditer(linha):
            if m.group(0) == "BAP AUTOPARTS":
                continue
            antes = linha[m.start() - 1:m.start()]
            depois = linha[m.end():m.end() + 1]
            if "/" in (antes, depois) or "\\" in (antes, depois):
                continue                                  # caminho de pasta
            yield n, m.group(0)


def test_RN_GER_009_regex_pega_as_grafias_erradas_e_deixa_as_certas():
    erradas = ["BAP Auto Parts · Farol", "BAP AUTO PARTS · TRADE",
               "da BAP Autoparts.", "BAP  AUTO PARTS"]
    certas = ["BAP AUTOPARTS · Farol de Metas", "@bapautoparts.com.br",
              'or "BAP AUTO PARTS" in s', r"C:\\BAP Auto Parts\\Relatorios"]
    assert all(list(_grafias_erradas(t)) for t in erradas)
    assert not any(list(_grafias_erradas(t)) for t in certas)


def test_RN_GER_009_nome_bap_autoparts_nos_py_bat_e_templates():
    achados = []
    arqs = _arquivos_de_producao()
    assert len(arqs) > 50                         # varreu a raiz e o site
    for p in arqs:
        texto = p.read_text(encoding="utf-8", errors="replace")
        achados += [f"{p.relative_to(RAIZ)}:{n}: {g}"
                    for n, g in _grafias_erradas(texto)]
    assert not achados, "grafia fora do manual:\n" + "\n".join(achados)


def test_RN_GER_004_internos_continuam_reconhecendo_a_grafia_antiga():
    """A troca do nome não pode tirar do cadastro o CNPJ interno escrito com
    a grafia antiga (BAP AUTO PARTS LTDA): ele continua fora do resultado."""
    import bap_dados as bd
    import meta_nucleo as mn
    for nome in ("BAP AUTO PARTS LTDA", "BAP AUTOPARTS COMERCIO",
                 "FRW DISTRIBUIDORA", "PMZ DISTRIBUIDORA"):
        assert bd._interno(nome) and mn.e_cliente_interno(nome), nome
    assert not bd._interno("AUTO PECAS DO CLIENTE") \
        and not mn.e_cliente_interno("AUTO PECAS DO CLIENTE")


# ============================================================== as cores
CSS = RAIZ / "web" / "app" / "static" / "estilo.css"
# o nome do token no manual -> o nome que o site usa hoje (mesmo hex)
APELIDOS_SITE = {"--faixa-inicio": ("--faixa-inicio", "--faixa-ini"),
                 "--cartao": ("--cartao", "--branco"),
                 "--grafico-1": ("--grafico-1", "--barra-1"),
                 "--grafico-2": ("--grafico-2", "--barra-2"),
                 "--grafico-3": ("--grafico-3", "--barra-3")}
# tokens que o manual põe só no PC ou que o site não usa como :root
SO_PC = {"--cinza-cab"}
OPCIONAIS_SITE = {"--ok", "--ok-claro"}


def _root_do_site() -> dict:
    css = CSS.read_text(encoding="utf-8")
    assert ":root{" in css, "o estilo.css não tem o bloco :root dos tokens"
    bloco = css[css.index(":root{"):]
    bloco = bloco[:bloco.index("\n}")]
    return {k: v.upper() for k, v in
            re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{3,8})\s*;", bloco)}


def test_RN_GER_009_tokens_do_site_com_o_hex_do_manual():
    manual, site = tokens_do_manual(), _root_do_site()
    faltam, errados = [], []
    for nome, hexa in manual.items():
        if nome in SO_PC:
            continue
        nomes = [n for n in APELIDOS_SITE.get(nome, (nome,)) if n in site]
        if not nomes:
            if nome not in OPCIONAIS_SITE:
                faltam.append(nome)
            continue
        errados += [f"{n}: site {site[n]} manual {hexa}"
                    for n in nomes if site[n] != hexa]
    assert not faltam, f"tokens do manual fora do :root do site: {faltam}"
    assert not errados, "\n".join(errados)


def test_RN_GER_009_o_ok_do_site_e_o_verde_escuro_do_manual():
    """O site define --ok dentro dos componentes (var(--verde-escuro))."""
    css, manual = CSS.read_text(encoding="utf-8"), tokens_do_manual()
    defs = re.findall(r"--ok:\s*([^;}]+)", css)
    assert defs
    site = _root_do_site()
    for d in defs:
        d = d.strip()
        valor = site.get(d[4:-1]) if d.startswith("var(") else d.upper()
        assert valor == manual["--ok"], d


# o que o manual manda tirar do site (4.2 "Muda o quê" e a nota de fora da
# paleta): as sobras do visual antigo, os 6 verdes, os amarelos claros, o
# vermelho e o verde antigos e os cinzas do e-mail
SAEM_DO_SITE = ["#0B3A6B", "#E8590C", "#D0EBFF", "#A5D8FF", "#E7EDF5",
                "#2B8A3E", "#1E8E3E", "#4FA236", "#3C9440", "#2F5D3A",
                "#2E5C3B", "#FFF3BF", "#FFF8E1", "#FFF8E6", "#F6F7F5",
                "#F5F6F4", "#B3261E", "#FBE3E1", "#62BB47", "#D2E7D3"]


# ------------------------------------------- exceção: as chaves do COR_PC
# Aval do design-de-marca (T-0037, UX A8): o `web/app/marca.py` traz em
# `COR_PC` a tabela de tradução "cor antiga do PC -> token do mesmo papel".
# As CHAVES são a entrada do PC (o hex que chega no pacote) e nunca vão à
# tela. A exceção vale só para elas, com 3 conferências: (1) só as chaves
# (nenhum outro lugar do marca.py nem da web traz o hex); (2) todo valor do
# COR_PC está em `marca.TOKENS`; (3) nenhum hex literal dessas chaves sai no
# HTML, no PDF ou no Excel do site (farol renderizado com as cores do PC nas
# barras).
# Chave que também é token: exceção nominal e fechada (decisão (C) do
# design-de-marca). Só `--atencao`, traduzida para `--grafico-2`, escrita
# como expressão `TOKENS["--atencao"]` (o hex fica só dentro de TOKENS).
# Manual (docs/marca/manual.md): l. 91, verde/amarelo/vermelho só para
# estado, nunca para decorar; l. 96, `--atencao` só no ponto, no ícone e na
# barra amarelos; l. 101, as barras dos gráficos usam `--grafico-1..3`;
# l. 148, cor de farol como enfeite é proibida. A barra de gráfico que o PC
# pinta de âmbar é gráfico, não estado: vira `--grafico-2`.
MARCA_WEB = RAIZ / "web" / "app" / "marca.py"
CHAVE_TOKEN_PERMITIDA = ("--atencao", "--grafico-2")    # (chave, valor)


def _no_cor_pc(src):
    """O nó Dict do `COR_PC = {...}` do marca.py (None se não existe)."""
    for no in ast.parse(src).body:
        if (isinstance(no, ast.Assign) and isinstance(no.value, ast.Dict)
                and any(isinstance(t, ast.Name) and t.id == "COR_PC"
                        for t in no.targets)):
            return no.value
    return None


def _token_da_expressao(no):
    """O nome do token se a chave é uma expressão sobre `TOKENS["--x"]` (por
    exemplo `TOKENS["--atencao"].lower()`); None se não é."""
    subs = [s for s in ast.walk(no) if isinstance(s, ast.Subscript)
            and isinstance(s.value, ast.Name) and s.value.id == "TOKENS"
            and isinstance(s.slice, ast.Constant)]
    return subs[0].slice.value if len(subs) == 1 else None


def _chaves_do_cor_pc(src, cor):
    """[(nó da chave, chave resolvida pelo valor)] na ordem do código. A
    chave literal é um hex escrito; a chave-expressão vem de TOKENS."""
    d = _no_cor_pc(src)
    if d is None:
        return []
    assert None not in d.keys, "COR_PC com **desempacotamento"
    assert len(d.keys) == len(cor), "COR_PC com chave repetida"
    return list(zip(d.keys, cor))


def _col_char(linha, col_bytes):
    """col_offset do ast é em bytes UTF-8; o índice do texto, em caracteres."""
    return len(linha.encode("utf-8")[:col_bytes].decode("utf-8"))


def _sem_as_chaves_do_cor_pc(src):
    """O texto do marca.py com as chaves LITERAIS do COR_PC apagadas (só
    elas; o resto do arquivo segue na varredura). A chave-expressão não traz
    hex: não há o que apagar."""
    d = _no_cor_pc(src)
    if d is None:
        return src
    linhas = src.splitlines()
    for k in d.keys:
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            continue
        assert k.lineno == k.end_lineno
        ln = linhas[k.lineno - 1]
        a, b = _col_char(ln, k.col_offset), _col_char(ln, k.end_col_offset)
        linhas[k.lineno - 1] = ln[:a] + " " * (b - a) + ln[b:]
    return "\n".join(linhas)


def _marca_web():
    assert MARCA_WEB.is_file(), "web/app/marca.py ausente"
    spec = importlib.util.spec_from_file_location("_marca_web_t0033",
                                                  MARCA_WEB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cor_pc():
    cor = getattr(_marca_web(), "COR_PC", None)
    assert cor, "sem marca.COR_PC na web (UX A8 da T-0037)"
    return cor


def _hex_dos_tokens(mod):
    """{hex: {nomes dos tokens}} (um hex pode ter 2 nomes: --alerta e --erro)."""
    saida = {}
    for n, v in mod.TOKENS.items():
        if isinstance(v, str):
            saida.setdefault(v.upper(), set()).add(n)
    return saida


def _varrer_web(padrao, exts):
    """[arquivo:linha: achado] do padrão em web/app, com a exceção (as
    chaves do COR_PC) e só ela."""
    achados = []
    for ext in exts:
        for p in sorted((RAIZ / "web" / "app").rglob(ext)):
            txt = p.read_text(encoding="utf-8")
            if p == MARCA_WEB:
                txt = _sem_as_chaves_do_cor_pc(txt)
            for n, linha in enumerate(txt.splitlines(), 1):
                achados += [f"{p.relative_to(RAIZ)}:{n}: #{m.group(0)}"
                            for m in padrao.finditer(linha)]
    return achados


def test_RN_GER_009_site_sem_as_cores_que_o_manual_tira():
    padrao = re.compile("|".join(h[1:] for h in SAEM_DO_SITE), re.I)
    achados = _varrer_web(padrao, ("*.py", "*.html", "*.js", "*.css"))
    assert not achados, "cor que o manual tira:\n" + "\n".join(achados)


def test_RN_GER_009_excecao_so_nas_chaves_do_cor_pc():
    """(1) As chaves do COR_PC, resolvidas pelo valor (literal ou expressão
    `TOKENS[...]`): a chave literal é um hex que não é token e não aparece
    em nenhum outro lugar do marca.py nem da web/app (nem sem o "#", nem em
    outra caixa); a chave que é token vem de `TOKENS["--x"]`, nunca do hex
    escrito à mão (o hex do token fica só dentro de TOKENS e do CSS)."""
    mod, cor = _marca_web(), _cor_pc()
    assert all(re.fullmatch(r"#[0-9a-fA-F]{6}", k) for k in cor), cor
    hex_tok = _hex_dos_tokens(mod)
    chaves = _chaves_do_cor_pc(MARCA_WEB.read_text(encoding="utf-8"), cor)
    erros, literais = [], []
    for no, k in chaves:
        literal = isinstance(no, ast.Constant)
        if k.upper() in hex_tok:
            if literal:
                erros.append(f"{k}: token escrito à mão (use TOKENS[...])")
            elif _token_da_expressao(no) not in hex_tok[k.upper()]:
                erros.append(f"{k}: a expressão não é TOKENS[...] de "
                             f"{sorted(hex_tok[k.upper()])}")
        elif not literal:
            erros.append(f"{k}: chave-expressão que não é token")
        else:
            literais.append(k)
    assert not erros, "\n".join(erros)
    if not literais:
        return
    padrao = re.compile("|".join(k[1:] for k in literais), re.I)
    achados = _varrer_web(padrao, ("*.py", "*.html", "*.js", "*.css",
                                   "*.j2", "*.txt"))
    assert not achados, "hex do COR_PC fora das chaves:\n" + "\n".join(
        achados)


def test_RN_GER_009_todo_valor_do_cor_pc_e_token():
    """(2) Todo valor do COR_PC é um valor de marca.TOKENS (o PC entra com a
    cor antiga e sai com o token do mesmo papel). Chave que também é token:
    só `--atencao` -> `--grafico-2` (exceção nominal e fechada, manual
    l. 91/96/101/148); qualquer outra chave-token reprova."""
    mod, cor = _marca_web(), _cor_pc()
    hex_tok = _hex_dos_tokens(mod)
    fora = {k: v for k, v in cor.items() if str(v).upper() not in hex_tok}
    assert not fora, f"valor do COR_PC fora do marca.TOKENS: {fora}"
    chave_ok, valor_ok = CHAVE_TOKEN_PERMITIDA
    for k, v in cor.items():
        nomes = hex_tok.get(k.upper())
        if nomes is None:
            continue
        assert chave_ok in nomes, \
            f"chave {k} é o token {sorted(nomes)}: só {chave_ok}"
        assert str(v).upper() == mod.TOKENS[valor_ok].upper(), \
            f"{chave_ok} tem de ir para {valor_ok}, não para {v}"


# (3) o farol renderizado: o pacote real do Fretes (bases congeladas, robô
# e faróis da T-0037) com as cores do PC nas barras dos meses e numa barra
# por estado (UF); a web recebe, desenha o HTML e exporta o PDF e o Excel
TOKEN_WEB = "t" * 43
ADMIN, SENHA0, SENHA1 = ("admin.teste", "senha-inicial-123",
                         "nova-senha-forte-1")
UFS_TESTE = ("AM", "PA", "RR", "AP", "MA", "AC", "RO", "PI")


def _pacote_fretes_com_cores_do_pc(cor):
    import bap_automation as ba                         # noqa: PLC0415
    import relatorios_nucleo as rn                      # noqa: PLC0415
    r = rn.montar("pl_fretes", RAIZ, hoje=date(2026, 11, 24),
                  params=ba.params_farol_web("pl_fretes", 2026, 11))
    pac = ba.montar_pacote_web({"pl_fretes": r}, 2026, 11, raiz=RAIZ)
    f = pac["relatorios"]["pl_fretes"]
    # as duas caixas: o PC manda maiúsculas (relatorios_nucleo) e minúsculas
    cores = [k.upper() if i % 2 else k for i, k in enumerate(sorted(cor))]
    barras = [b for b in f["painel"]["blocos"] if b["tipo"] == "barras"]
    assert barras, "o Resumo do Fretes sem as barras dos meses"
    for i, s in enumerate(barras[0]["grafico"]["series"]):
        s["cor"] = cores[i % len(cores)]
        s["cor_negativo"] = cores[(i + 1) % len(cores)]
    ufs = list(UFS_TESTE[:len(cores)])
    f["painel"]["blocos"].append({
        "tipo": "hbarras", "row": 99, "col": 0, "colspan": 3,
        "titulo": "Notas por estado", "rotulos": ufs,
        "valores": [float(10 + i) for i in range(len(ufs))],
        "cores": cores[:len(ufs)], "formato": "num"})
    return pac


def _limpar_app(monkeypatch):
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, m)


@pytest.fixture
def web_fretes(tmp_path, monkeypatch):
    for m in ("fastapi", "httpx", "jinja2"):
        pytest.importorskip(m)
    cor = _cor_pc()
    pac = _pacote_fretes_com_cores_do_pc(cor)
    _limpar_app(monkeypatch)
    monkeypatch.syspath_prepend(str(RAIZ / "web"))
    for k, val in (("SESSION_SECRET", "segredo-de-teste-0123456789abcdef"),
                   ("BAP_WEB_DADOS", str(tmp_path / "dados")),
                   ("BAP_WEB_TOKEN", TOKEN_WEB), ("BAP_ADMIN_USUARIO", ADMIN),
                   ("BAP_ADMIN_SENHA_INICIAL", SENHA0),
                   ("BAP_WEB_PACOTE_MAX_MB", "25"), ("TZ", "America/Manaus")):
        monkeypatch.setenv(k, val)
    time.tzset()
    from fastapi.testclient import TestClient           # noqa: PLC0415

    from app.main import criar_app                      # noqa: PLC0415
    cli = TestClient(criar_app(), base_url="https://testserver")
    cli.__enter__()

    def tok(url):
        return re.search(r'name="csrf" value="([^"]+)"',
                         cli.get(url).text).group(1)
    assert cli.post("/login", data={"usuario": ADMIN, "senha": SENHA0,
                                    "csrf": tok("/login")},
                    follow_redirects=False).status_code == 303
    assert cli.post("/senha", data={"atual": SENHA0, "nova": SENHA1,
                                    "confirma": SENHA1, "csrf": tok("/senha")},
                    follow_redirects=False).status_code == 303
    r = cli.post("/api/pacote", json=pac,
                 headers={"Authorization": f"Bearer {TOKEN_WEB}"})
    assert r.status_code == 200, r.text[:300]
    yield cli, cor
    cli.__exit__(None, None, None)
    _limpar_app(monkeypatch)
    monkeypatch.undo()
    time.tzset()


def test_RN_GER_009_hex_do_cor_pc_nao_sai_no_html_pdf_nem_excel(web_fretes):
    """(3) As formas de cada hex do COR_PC: o texto (HTML e XML do Excel, sem
    o "#" e em qualquer caixa), o ARGB do Excel e o operando `rg` do PDF."""
    cli, cor = web_fretes
    mod = _marca_web()
    saidas = {}
    for aba in ("resumo", "notas", "uf", "cidade", "transportadora"):
        r = cli.get(f"/farol/pl_fretes?aba={aba}")
        assert r.status_code == 200, aba
        saidas[f"html:{aba}"] = r.text
    h = saidas["html:resumo"]
    # o farol desenhou as barras, e a cor do PC entrou como o token
    assert "Notas por estado" in h
    assert any(v.lower() in h.lower() for v in cor.values())
    for aba in ("notas", "uf", "cidade", "transportadora"):
        for fmt in ("xlsx", "pdf"):
            r = cli.get(f"/farol/pl_fretes/exportar?aba={aba}&formato={fmt}")
            assert r.status_code == 200, (aba, fmt)
            if fmt == "pdf":
                assert r.content[:5] == b"%PDF-"
                saidas[f"pdf:{aba}"] = r.content.decode("latin-1")
            else:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                saidas[f"xlsx:{aba}"] = "".join(
                    z.read(n).decode("utf-8", "replace")
                    for n in z.namelist())
    # a chave que é token (só a `--atencao`, conferida no (2)) fica fora da
    # busca: o ponto e o ícone amarelos do site usam esse hex (manual l. 96)
    hex_tok = _hex_dos_tokens(mod)
    achados = []
    for k in [k for k in cor if k.upper() not in hex_tok]:
        texto, argb, rg = (re.compile(k[1:], re.I), mod.argb_xlsx(k),
                           mod.rgb_pdf(k))
        achados += [f"{k} em {nome}" for nome, s in saidas.items()
                    if texto.search(s) or argb in s
                    or (nome.startswith("pdf") and rg in s)]
    assert not achados, "\n".join(achados)


# a constante do PC (bap_visual.py) -> o token do manual (4.2: "Os nomes
# valem igual ... nas constantes do PC, que passam a usar o mesmo hex")
CONSTANTES_PC = {"VERDE": "--verde-marca", "VERDE_ESCURO": "--verde-escuro",
                 "VERDE_CLARO": "--verde-claro", "PRETO_BAP": "--preto-bap",
                 "VERMELHO": "--alerta", "VERMELHO_CLARO": "--alerta-claro",
                 "AMARELO": "--atencao", "AMARELO_CLARO": "--atencao-claro",
                 "TEXTO": "--texto", "SUAVE": "--suave", "FUNDO": "--fundo",
                 "CARTAO": "--cartao", "GRADE": "--grade",
                 "CINZA_CAB": "--cinza-cab", "CINZA_LINHA": "--borda"}


@pytest.mark.parametrize("constante, token", sorted(CONSTANTES_PC.items()))
def test_RN_GER_009_constantes_do_pc_com_o_hex_do_manual(constante, token):
    import bap_visual as bv
    assert getattr(bv, constante).upper() == tokens_do_manual()[token]


def test_RN_GER_009_fundos_do_tom_no_pc_iguais_ao_manual():
    """FUNDOS do bap_visual: o fundo da linha por tom (manual 4.2)."""
    import bap_visual as bv
    manual = tokens_do_manual()
    assert bv.FUNDOS["ok"].upper() == manual["--ok-claro"]
    assert bv.FUNDOS["alerta"].upper() == manual["--alerta-claro"]
    assert bv.FUNDOS["atencao"].upper() == manual["--atencao-claro"]
