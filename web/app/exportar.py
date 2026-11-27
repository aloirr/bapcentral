"""T-0026: exportar as tabelas dos faróis (Excel e PDF) e a imagem da parcial em PDF.

Sem biblioteca de fora: o Excel é um .xlsx escrito com `zipfile` (texto em `inlineStr`, que nunca vira
fórmula) e o PDF é escrito à mão (Helvetica, WinAnsi). Nenhuma regra de negócio aqui: as linhas, a ordem e
o filtro vêm de `tabelas.tabela_para_tela` (o que a pessoa vê na tela, todas as páginas) e o número bruto vem
do pacote do PC.
"""
from __future__ import annotations

import base64
import math
import re
import struct
import zipfile
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from . import marca
from .render import RE_DATA

MAX_LINHAS_PDF = 3000                      # a tabela é para olhar; o resto vai no Excel
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_NUM = ("int", "num", "num1", "num2", "moeda", "moeda2", "pct", "pct1", "valor")
_FMT = {"moeda": 2, "moeda2": 2, "pct": 3, "pct1": 4, "int": 5, "num": 6, "num1": 6, "num2": 6, "valor": 6,
        "data": 7, "dia": 7}
EXCEL_EPOCA = date(1899, 12, 30)


def _num(v):
    """Número de verdade (nem bool, nem NaN/inf: no Excel viraria `nan`/`inf` inválido e a planilha não abre)."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    try:
        return v if math.isfinite(v) else None
    except OverflowError:
        return None


def tabela_plana(tela: dict, bruta: dict, centavos: bool = False) -> dict:
    """{"titulo", "cols": [(nome, tipo)], "linhas": [[bruto...]], "textos": [[texto...]], "total": [...]|None}.
    `tela` = resultado de tabela_para_tela (com `idxs` = linhas depois de filtro, recorte e ordem);
    `bruta` = a tabela do pacote (colunas e linhas)."""
    vista = [c["i"] for c in tela["cols"]]
    cols = [(bruta["colunas"][i]["nome"], bruta["colunas"][i]["tipo"]) for i in vista]
    linhas = [[bruta["linhas"][k][i] for i in vista] for k in tela["idxs"]]
    # com pagina_tam enorme: todas as linhas; o código do cliente que a tela tirou da grade volta no arquivo
    textos = [[(c["cod"] + " - " + c["t"]) if c.get("cod") else c["t"] for c in ln["cel"]] for ln in tela["linhas"]]
    tot = bruta.get("total")
    total = [tot[i] for i in vista] if tot and len(tot) == len(bruta["colunas"]) else None
    return {"titulo": tela.get("titulo") or bruta.get("titulo", ""), "cols": cols, "linhas": linhas,
            "textos": textos, "total": total, "centavos": centavos,
            "_total_txt": [c["t"] for c in tela["total"]] if tela.get("total") else None}


# ------------------------------------------------------------------ Excel
def _ref(c: int, l: int) -> str:
    n, s = c + 1, ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return f"{s}{l}"


def _nome_aba(nome: str, usados: set) -> str:
    n = re.sub(r"[\[\]:*?/\\]", " ", nome).strip()[:31] or "Tabela"
    base, k = n, 2
    while n.lower() in usados:
        n = f"{base[:28]} {k}"
        k += 1
    usados.add(n.lower())
    return n


def _celula_xlsx(ref: str, v, tipo: str, estilo_txt: int = 0) -> str:
    if v is None or v == "":
        return ""
    if tipo in ("data", "dia") and isinstance(v, str) and RE_DATA.match(v):
        try:
            d = (date.fromisoformat(v) - EXCEL_EPOCA).days
            return f'<c r="{ref}" s="7"><v>{d}</v></c>'
        except ValueError:
            pass
    n = _num(v)
    if tipo in _NUM and n is not None:
        return f'<c r="{ref}" s="{_FMT.get(tipo, 6)}"><v>{n!r}</v></c>'
    txt = escape(_CTRL.sub("", str(v)))
    return f'<c r="{ref}" t="inlineStr" s="{estilo_txt}"><is><t xml:space="preserve">{txt}</t></is></c>'


def _folha(t: dict) -> str:
    cols, linhas = t["cols"], t["linhas"]
    larg = [min(48, max(8, len(n) + 2)) for n, _ in cols]
    for ln in linhas[:400]:
        for j, v in enumerate(ln):
            larg[j] = min(48, max(larg[j], len(str(v)) + 2 if v is not None else 0))
    xs = [f'<row r="1">' + "".join(
        f'<c r="{_ref(j, 1)}" t="inlineStr" s="1"><is><t>{escape(_CTRL.sub("", n))}</t></is></c>'
        for j, (n, _) in enumerate(cols)) + "</row>"]
    r = 2
    for ln in linhas:
        xs.append(f'<row r="{r}">' + "".join(_celula_xlsx(_ref(j, r), v, cols[j][1]) for j, v in enumerate(ln)) + "</row>")
        r += 1
    if t.get("total"):
        xs.append(f'<row r="{r}">' + "".join(
            _celula_xlsx(_ref(j, r), v, cols[j][1], 8) for j, v in enumerate(t["total"])) + "</row>")
        r += 1
    ultima = _ref(max(len(cols) - 1, 0), max(r - 1, 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>'
            + "".join(f'<col min="{j + 1}" max="{j + 1}" width="{w}" customWidth="1"/>' for j, w in enumerate(larg))
            + '</cols><sheetData>' + "".join(xs) + f'</sheetData><autoFilter ref="A1:{_ref(max(len(cols) - 1, 0), max(len(linhas) + 1, 1))}"/></worksheet>')


_ESTILOS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="4"><numFmt numFmtId="164" formatCode="&quot;R$&quot; #,##0.00"/>'
    '<numFmt numFmtId="165" formatCode="0&quot;%&quot;"/><numFmt numFmtId="166" formatCode="0.0&quot;%&quot;"/>'
    '<numFmt numFmtId="167" formatCode="dd/mm/yyyy"/></numFmts>'
    '<fonts count="3"><font><sz val="10"/><name val="Calibri"/></font>'
    '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    '<font><b/><sz val="10"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    f'<fill><patternFill patternType="solid"><fgColor rgb="{marca.argb_xlsx(marca.VERDE_ESCURO)}"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="9"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def xlsx(tabelas: list[dict]) -> bytes:
    """Uma aba do Excel por tabela (cabeçalho fixo, filtro, formato por tipo)."""
    usados: set = set()
    nomes = [_nome_aba(t["titulo"], usados) for t in tabelas]
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{k + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for k in range(len(tabelas))) + '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
        z.writestr("docProps/app.xml",       # MC-0003: o arquivo sai com o nome da empresa
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                   f'<Application>BAP Central</Application><Company>{marca.EMPRESA}</Company></Properties>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{k + 1}" r:id="rId{k + 1}"/>'
                             for k, n in enumerate(nomes)) + '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{k + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{k + 1}.xml"/>'
                             for k in range(len(tabelas)))
                   + f'<Relationship Id="rId{len(tabelas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", _ESTILOS)
        for k, t in enumerate(tabelas):
            z.writestr(f"xl/worksheets/sheet{k + 1}.xml", _folha(t))
    return buf.getvalue()


def xlsx_correcao(correcao: dict) -> bytes:
    """T-0036 (contrato §10.11.4): as 2 abas do Excel de correção (CORRIGIR NO PROTHEUS e ANALISAR), tudo texto,
    com o mesmo escritor da exportação. Sem coluna de cliente: o pacote já chegou sem ela (RN-GER-011)."""
    abas = []
    for k in ("corrigir", "analisar"):
        t = correcao.get(k) or {}
        abas.append({"titulo": t.get("titulo") or k, "cols": [(c["nome"], "texto") for c in t.get("colunas") or []],
                     "linhas": t.get("linhas") or [], "total": None})
    return xlsx(abas)


# ------------------------------------------------------------------ PDF (escrito à mão)
def _pdf(objs: list[bytes], info: int = 0) -> bytes:
    """`objs[k]` é o corpo do objeto k+1; o objeto 1 é o catálogo."""
    out = BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    pos = []
    for k, o in enumerate(objs, 1):
        pos.append(out.tell())
        out.write(f"{k} 0 obj\n".encode() + o + b"\nendobj\n")
    ini = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for p in pos:
        out.write(f"{p:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R{f' /Info {info} 0 R' if info else ''} >>\nstartxref\n{ini}\n%%EOF\n".encode())
    return out.getvalue()


def _txt_pdf(s: str) -> bytes:
    b = str(s).replace("−", "-").replace("–", "-").replace("—", "-").encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _estr(txt: str, tam: float) -> float:
    """Largura estimada em Helvetica, em pontos (média de 0,5 do corpo; maiúscula e largas contam mais)."""
    return sum(0.62 if ch.isupper() or ch in "MW@%" else 0.28 if ch in "ilI.,:;'| !" else 0.5 for ch in str(txt)) * tam


def pdf_tabela(t: dict, rodape: str) -> bytes:
    textos = t["textos"]
    """A4 deitado: título, cabeçalho repetido em cada folha, linhas (até MAX_LINHAS_PDF) e total."""
    W, H, M = 842.0, 595.0, 22.0
    cols = [n for n, _ in t["cols"]]
    tipos = [tp for _, tp in t["cols"]]
    n = max(1, len(cols))
    tam = 7.0 if n <= 12 else 6.0 if n <= 18 else 5.0
    amostra = textos[:300] + ([t["_total_txt"]] if t.get("_total_txt") else [])
    larg = [max(_estr(c, tam), *(_estr(ln[j], tam) for ln in amostra)) + 6 if amostra else _estr(c, tam) + 6
            for j, c in enumerate(cols)]
    larg = [min(w, 170.0) for w in larg]
    util = W - 2 * M
    esc = util / sum(larg) if sum(larg) > util else 1.0
    larg = [w * esc for w in larg]
    linha_h = tam + 4.5
    por_pagina = int((H - 2 * M - 40) / linha_h) - 1
    corpo = list(textos[:MAX_LINHAS_PDF])
    extra = [t["_total_txt"]] if t.get("_total_txt") else []
    paginas = [corpo[i:i + por_pagina] for i in range(0, len(corpo), por_pagina)] or [[]]
    if extra and len(paginas[-1]) >= por_pagina:
        paginas.append([])
    paginas[-1] = paginas[-1] + extra
    quando = datetime.now().strftime("%d/%m/%Y %H:%M")

    def corta(txt, w):
        s = str(txt)
        while len(s) > 1 and _estr(s, tam) > w - 4:
            s = s[:-1]
            if _estr(s + "...", tam) <= w - 4:
                return s + "..."
        return s

    conteudos = []
    for k, pag in enumerate(paginas, 1):
        c = [f"BT /F2 11 Tf {M} {H - M - 10} Td ({_txt_pdf(marca.EMPRESA + ' · ' + t['titulo']).decode('latin-1')}) Tj ET"]
        c.append(f"BT /F1 7 Tf {M} {H - M - 22} Td ({_txt_pdf(rodape).decode('latin-1')}) Tj ET")
        y = H - M - 40
        x = M
        c.append(f"{marca.rgb_pdf(marca.VERDE_ESCURO)} rg {M} {y - 2.5} {sum(larg)} {linha_h} re f 1 g")
        for j, nome in enumerate(cols):
            c.append(f"BT /F2 {tam} Tf {x + 2} {y + 1} Td ({_txt_pdf(corta(nome, larg[j])).decode('latin-1')}) Tj ET")
            x += larg[j]
        c.append("0 g")
        y -= linha_h
        for i, ln in enumerate(pag):
            ultimo_total = bool(extra) and k == len(paginas) and i == len(pag) - 1
            if i % 2:
                c.append(f"{marca.rgb_pdf(marca.LINHA_ZEBRA)} rg {M} {y - 2.5} {sum(larg)} {linha_h} re f 0 g")
            x = M
            for j, txt in enumerate(ln):
                s = corta(txt, larg[j])
                dx = larg[j] - 2 - _estr(s, tam) if tipos[j] in _NUM else 2
                c.append(f"BT /{'F2' if ultimo_total else 'F1'} {tam} Tf {x + dx:.1f} {y + 1} Td ({_txt_pdf(s).decode('latin-1')}) Tj ET")
                x += larg[j]
            y -= linha_h
        c.append(f"BT /F1 6 Tf {W - M - 120} {M - 8} Td ({_txt_pdf(f'Folha {k} de {len(paginas)} · {quando}').decode('latin-1')}) Tj ET")
        conteudos.append("\n".join(c).encode("latin-1", "replace"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"", b"",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    # objetos 1 catálogo, 2 páginas, 3 reservado, 4 recursos; 5 e 6 fontes; depois pares página + conteúdo
    kids = []
    objs[3] = b"<< /Font << /F1 5 0 R /F2 6 0 R >> >>"
    objs[2] = b"<< >>"
    for k, cont in enumerate(conteudos):
        pg = 7 + 2 * k
        kids.append(f"{pg} 0 R")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W:g} {H:g}] /Resources 4 0 R /Contents {pg + 1} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(cont) + cont + b"\nendstream")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    return _pdf(objs)


# ------------------------------------------------------------------ PDF da imagem da parcial
def png_dados(b64: str) -> bytes | None:
    """O PNG do pacote (base64), só se for PNG de verdade; senão None."""
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        return None
    return raw if raw[:8] == b"\x89PNG\r\n\x1a\n" else None


def _png_idat(raw: bytes):
    """(largura, altura, dados IDAT, cor) de um PNG RGB/RGBA 8 bits sem entrelaçamento; None se for outro."""
    pos, idat, ihdr = 8, b"", None
    while pos + 8 <= len(raw):
        n, tipo = struct.unpack(">I4s", raw[pos:pos + 8])
        corpo = raw[pos + 8:pos + 8 + n]
        if tipo == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tipo == b"IDAT":
            idat += corpo
        pos += 12 + n
    if not ihdr:
        return None
    w, h, prof, cor, _, _, entrel = ihdr
    if prof != 8 or cor != 2 or entrel != 0:
        return None
    return w, h, idat


def pdf_imagem(raw_png: bytes, titulo: str) -> bytes | None:
    """A4 em pé com a imagem da parcial ajustada à folha (o IDAT do PNG vai direto no PDF, com preditor).
    None se o PNG não for RGB 8 bits (a tela então oferece só o PNG)."""
    info = _png_idat(raw_png)
    if not info:
        return None
    w, h, idat = info
    W, H, M = 595.0, 842.0, 18.0
    esc = min((W - 2 * M) / w, (H - 2 * M) / h)
    iw, ih = w * esc, h * esc
    x, y = (W - iw) / 2, H - M - ih
    cont = f"q {iw:.2f} 0 0 {ih:.2f} {x:.2f} {y:.2f} cm /Im0 Do Q".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W:g} {H:g}] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>".encode(),
            b"<< /Length %d >>\nstream\n" % len(cont) + cont + b"\nendstream",
            (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
             f"/Filter /FlateDecode /DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns {w} >> "
             f"/Length {len(idat)} >>\nstream\n").encode() + idat + b"\nendstream",
            f"<< /Title ({_txt_pdf(titulo).decode('latin-1')}) >>".encode()]
    return _pdf(objs, info=6)


__all__ = ["tabela_plana", "xlsx", "pdf_tabela", "pdf_imagem", "png_dados"]
