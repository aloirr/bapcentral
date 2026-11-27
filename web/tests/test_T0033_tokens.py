"""T-0033 · contrato visual BC3 §12 e manual da marca (aprovado em R-20261126-182227-alexandre):
os tokens do `:root` do `estilo.css` e o `marca.py` têm os mesmos valores, e os valores são os aprovados."""
import re
from pathlib import Path

from app import marca

CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css"


def _root() -> dict:
    css = CSS.read_text(encoding="utf-8")
    bloco = css[css.index(":root{"):]
    bloco = bloco[:bloco.index("\n}")]
    return {k: v.upper() for k, v in re.findall(r"(--[a-z0-9-]+):(#[0-9A-Fa-f]{3,8});", bloco)}


def test_T0033_tokens_do_root_iguais_ao_marca_py():
    css = _root()
    for nome, valor in marca.TOKENS.items():
        assert css.get(nome) == valor.upper(), f"{nome}: css={css.get(nome)} marca.py={valor}"


def test_T0033_valores_aprovados_no_manual_da_marca():
    t = marca.TOKENS
    assert t["--verde-marca"] == "#59BA61" and t["--verde-escuro"] == "#2F7D32"
    assert (t["--faixa-ini"], t["--faixa-fim"], t["--faixa-texto"]) == ("#2F7D32", "#1B4D1F", "#FFFFFF")
    assert (t["--alerta"], t["--alerta-claro"]) == ("#B42318", "#FDECEA")
    assert (t["--erro"], t["--erro-claro"]) == ("#B42318", "#FDECEA")
    assert t["--atencao-texto"] == "#8A5A00" and t["--atencao"] == "#B7791F"
    assert (t["--suave"], t["--fundo"], t["--borda"], t["--grade"]) == ("#5E6B63", "#F3F4F2", "#E3E8E4", "#ECEEEB")
    assert t["--preto-bap"] == "#231F20"


def test_T0033_nenhuma_cor_fora_do_root_e_fonte_inter():
    css = CSS.read_text(encoding="utf-8")
    fora = css[css.index("\n}") + 2:]
    assert not re.findall(r"#[0-9A-Fa-f]{3,8}\b", fora), "cor solta fora do :root"
    assert "--fonte:Inter,\"Segoe UI\",Arial,sans-serif" in css


def test_T0033_texto_de_atencao_usa_o_tom_escuro_e_o_amarelo_so_em_ponto_e_barra():
    css = CSS.read_text(encoding="utf-8")
    assert not re.search(r"[^-]color:var\(--atencao\)", css), "o amarelo #B7791F não é texto (3,64:1)"
    assert ".t-atencao{color:var(--atencao-texto)}" in css
