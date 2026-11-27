"""T-0033 (contrato visual BC3 §12): a marca num lugar só para o que não lê CSS (PDF e Excel do site).

Os valores são os mesmos do bloco `:root` de `static/estilo.css`, com os mesmos nomes; um teste confere que são iguais.
Trocar uma cor é trocar a linha nos dois (paleta do manual da marca, aprovada pelo Alexandre em R-20261126-182227-alexandre).
"""
from __future__ import annotations

EMPRESA = "BAP AUTOPARTS"          # grafia oficial (regra 8): maiúsculas e sem espaço entre AUTO e PARTS

TOKENS = {
    "--verde-marca": "#59BA61", "--verde-escuro": "#2F7D32", "--verde-claro": "#E5F3DF", "--texto": "#1E2722",
    "--suave": "#5E6B63", "--fundo": "#F3F4F2", "--borda": "#E3E8E4", "--grade": "#ECEEEB", "--preto-bap": "#231F20",
    "--branco": "#FFFFFF", "--cartao": "#FFFFFF", "--ok-claro": "#F0F7EC", "--alerta": "#B42318", "--alerta-claro": "#FDECEA",
    "--atencao": "#B7791F", "--atencao-texto": "#8A5A00", "--atencao-claro": "#FFF4D6",
    "--erro": "#B42318", "--erro-claro": "#FDECEA",
    "--faixa-inicio": "#2F7D32", "--faixa-fim": "#1B4D1F", "--faixa-texto": "#FFFFFF",
    "--faixa-ok": "#A6E3A9", "--faixa-atencao": "#FFE08A", "--faixa-alerta": "#FFB4A9",
    "--grafico-1": "#7DB46A", "--grafico-2": "#D8B56E", "--grafico-3": "#8FA79A",
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
