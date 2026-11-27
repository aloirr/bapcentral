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
import re
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


def test_RN_GER_009_site_sem_as_cores_que_o_manual_tira():
    achados = []
    web = RAIZ / "web" / "app"
    padrao = re.compile("|".join(h[1:] for h in SAEM_DO_SITE), re.I)
    for ext in ("*.py", "*.html", "*.js", "*.css"):
        for p in sorted(web.rglob(ext)):
            for n, linha in enumerate(
                    p.read_text(encoding="utf-8").splitlines(), 1):
                for m in padrao.finditer(linha):
                    achados.append(f"{p.relative_to(RAIZ)}:{n}: #{m.group(0)}")
    assert not achados, "cor que o manual tira:\n" + "\n".join(achados)


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
