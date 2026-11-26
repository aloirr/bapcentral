"""T-0033 (contrato visual BC3 §12): a marca num lugar só para o que não lê CSS (PDF e Excel do site).

Os valores são os mesmos do bloco `:root` de `static/estilo.css`, com os mesmos nomes; um teste confere que são iguais.
Trocar uma cor é trocar a linha nos dois (a paleta nova vem do design-de-marca, com o "aprovo" do Alexandre).
"""
from __future__ import annotations

EMPRESA = "BAP AUTOPARTS"          # grafia oficial (regra 8): maiúsculas e sem espaço entre AUTO e PARTS

TOKENS = {
    "--verde": "#62BB47", "--verde-escuro": "#2F7D32", "--verde-claro": "#E5F3DF", "--texto": "#1E2722",
    "--suave": "#69736D", "--fundo": "#F6F7F5", "--grade": "#E3E8E4", "--branco": "#FFFFFF",
    "--vermelho": "#B3261E", "--vermelho-claro": "#FBE3E1", "--amarelo": "#B7791F", "--amarelo-claro": "#FFF4D6",
    "--erro": "#B42318", "--erro-claro": "#FDECEA",
}
VERDE_ESCURO = TOKENS["--verde-escuro"]       # cabeçalho das tabelas no PDF e no Excel
TEXTO = TOKENS["--texto"]
LINHA_ZEBRA = TOKENS["--fundo"]               # linha alternada da tabela no PDF


def rgb_pdf(hex_: str) -> str:
    """'#2F7D32' -> '0.184 0.490 0.196' (operando `rg` do PDF)."""
    h = hex_.lstrip("#")
    return " ".join(f"{int(h[i:i + 2], 16) / 255:.3f}" for i in (0, 2, 4))


def argb_xlsx(hex_: str) -> str:
    """'#2F7D32' -> 'FF2F7D32' (atributo `rgb` do Excel)."""
    return "FF" + hex_.lstrip("#").upper()
