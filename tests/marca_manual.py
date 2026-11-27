"""Leitura dos tokens de cor do manual da marca (docs/marca/manual.md, seção 4).

Os testes da T-0033 comparam o código com o manual aprovado
(R-20261126-182227-alexandre) lendo o próprio manual: se o manual mudar, o
teste acompanha; se o código sair do manual, o teste falha.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANUAL = RAIZ / "docs" / "marca" / "manual.md"

# uma linha de tabela do manual: | `--token` | `#HEX` ...
_LINHA = re.compile(r"^\| `(--[a-z0-9-]+)` \| `(#[0-9A-Fa-f]{6})`", re.M)
# a linha dos gráficos traz três tokens e três hex na mesma célula
_GRAFICOS = re.compile(r"^\| `--grafico-1` · `--grafico-2` · `--grafico-3` \| "
                       r"`(#[0-9A-Fa-f]{6})` · `(#[0-9A-Fa-f]{6})` · "
                       r"`(#[0-9A-Fa-f]{6})`", re.M)


def tokens_do_manual() -> dict:
    """{"--token": "#HEX"} da seção 4 do manual (hex em maiúsculas)."""
    texto = MANUAL.read_text(encoding="utf-8")
    secao = texto[texto.index("## 4. Paleta em tokens"):
                  texto.index("## 5. Tipografia")]
    tokens = {}
    for nome, valor in _LINHA.findall(secao):
        assert tokens.get(nome, valor.upper()) == valor.upper(), \
            f"o manual dá dois valores para {nome}"
        tokens[nome] = valor.upper()
    graf = _GRAFICOS.search(secao)
    assert graf, "a linha dos gráficos sumiu do manual"
    for i, valor in enumerate(graf.groups(), 1):
        tokens[f"--grafico-{i}"] = valor.upper()
    return tokens
