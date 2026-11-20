"""
Leitura RAPIDA de .xlsx, so de valores (o que os relatorios usam).

E o mesmo resultado do openpyxl com load_workbook(read_only=True,
data_only=True) e ws.iter_rows(values_only=True) - texto, numero (int ou
float), data (datetime), verdadeiro/falso e celula vazia (None), com as
linhas do mesmo tamanho -, so que lido direto do XML, 5 a 10 vezes mais
rapido. A TABELA_BAP (6 milhoes de celulas) era a maior parte da espera dos
relatorios, do Gerador de Meta e do Planner.

Uso igual ao do openpyxl:
    wb = abrir(caminho)              # ou load_workbook(caminho, ...)
    ws = wb["PLANNER"]               # ou wb.active / wb.worksheets[0]
    for linha in ws.iter_rows(min_row=2, values_only=True): ...
    wb.close()

Qualquer coisa fora do comum (arquivo que nao e .xlsx, aba que nao abre)
cai no openpyxl de verdade, sem mudar o resultado.

(05/11) A TABELA_BAP COM FOTOGRAFIA: quando ha RELATORIOS\\DADOS ao lado da
TABELA_BAP e a fotografia vale para ela (dados_bap.fotografia_para), as 7
abas de dados vem da fotografia (.csv.gz, o que o robo gravou na ultima
rodada, rapida ou completa) e as de cadastro vem do .xlsx, como sempre - o
mesmo resultado, so que atualizado mesmo nas rodadas que nao abrem o
Excel. BAP_SEM_FOTOGRAFIA=1 (ou BAP_XLSX_LENTO=1) no ambiente desliga.
"""
from __future__ import annotations

import re
import zipfile
from html import unescape as _unescape_html
from pathlib import PurePosixPath

_RE_ROW = re.compile(r"<(?:\w+:)?row\b([^>]*?)(?:/>|>(.*?)</(?:\w+:)?row>)",
                     re.S)
_RE_CELL = re.compile(r"<(?:\w+:)?c\b([^>]*?)(?:/>|>(.*?)</(?:\w+:)?c>)", re.S)
_RE_ATTR_R = re.compile(r'\br="([A-Z]+)(\d+)"')
_RE_ATTR_T = re.compile(r'\bt="(\w+)"')
_RE_ATTR_S = re.compile(r'\bs="(\d+)"')
_RE_ROW_R = re.compile(r'\br="([\d.]+)"')
_RE_V = re.compile(r"<(?:\w+:)?v(?:\s[^>]*)?>(.*?)</(?:\w+:)?v>", re.S)
_RE_T = re.compile(r"<(?:\w+:)?t(?:\s[^>]*)?>(.*?)</(?:\w+:)?t>|"
                   r"<(?:\w+:)?t(?:\s[^>]*)?/>", re.S)
_RE_RPH = re.compile(r"<(?:\w+:)?rPh\b.*?</(?:\w+:)?rPh>", re.S)
_RE_SI = re.compile(r"<(?:\w+:)?si\b[^>]*?(?:/>|>(.*?)</(?:\w+:)?si>)", re.S)
# o caminho rapido: uma expressao so para <row ...> e <c ...>...</c>, com
# r, s e t na ordem que o Excel e o openpyxl gravam
_RE_RAPIDO = re.compile(
    r'(<row\b)([^>]*)>'
    r'|<c\b(?: r="([A-Z]+)\d+")?(?: s="(\d+)")?(?: t="(\w+)")?([^>]*?)'
    r'(?:/>|>(.*?)</c>)', re.S)
_RE_DIM = re.compile(r'<(?:\w+:)?dimension\b[^>]*\bref="([^"]+)"')
_RE_SHEETDATA = re.compile(r"<(?:\w+:)?sheetData\b")
_ENT = re.compile(r"&(#?\w+);")


def _unescape(s: str) -> str:
    """O texto como o leitor de XML entrega: quebra de linha normalizada
    (CR LF e CR viram LF) e entidades (&amp; &#13; ...) resolvidas."""
    if "\r" in s:
        s = s.replace("\r\n", "\n").replace("\r", "\n")
    return _unescape_html(s) if "&" in s else s


_COL_CACHE: dict = {}


def _col(letras: str) -> int:
    n = _COL_CACHE.get(letras)
    if n is None:
        n = 0
        for ch in letras:
            n = n * 26 + (ord(ch) - 64)
        _COL_CACHE[letras] = n
    return n


def _texto_do_si(miolo: str) -> str:
    """O texto de um <si>/<is>: o <t> simples ou os <r><t> juntos (sem o
    fonetico <rPh>) - o mesmo Text.content do openpyxl."""
    if not miolo:
        return ""
    if miolo[:3] == "<t>" and miolo.endswith("</t>") and \
            miolo.count("<", 3) == 1:
        return _unescape(miolo[3:-4])
    if "<rPh" in miolo or ":rPh" in miolo:
        miolo = _RE_RPH.sub("", miolo)
    partes = [m.group(1) or "" for m in _RE_T.finditer(miolo)]
    return _unescape("".join(partes))


def _ref_para_limites(ref: str):
    """'A1:Z300' -> (min_col, min_row, max_col, max_row) como o openpyxl."""
    m = re.match(r"^\$?([A-Z]+)?\$?(\d+)?(?::\$?([A-Z]+)?\$?(\d+)?)?$", ref)
    if not m:
        return None
    c1, r1, c2, r2 = m.groups()
    if c2 is None and r2 is None:      # uma celula so: 'A1'
        c2, r2 = c1, r1
    try:
        return (_col(c1) if c1 else None, int(r1) if r1 else None,
                _col(c2) if c2 else None, int(r2) if r2 else None)
    except ValueError:
        return None


_RE_FECHA_ROW = re.compile(r"</(?:\w+:)?row>")


def _fim_da_ultima_linha(txt: str) -> int:
    """Onde termina o ultimo </row> completo do pedaco (-1: nenhum)."""
    i = txt.rfind("row>")
    while i >= 0:
        j = txt.rfind("</", 0, i)
        if j >= 0 and _RE_FECHA_ROW.fullmatch(txt, j, i + 4):
            return i + 4
        i = txt.rfind("row>", 0, i)
    return -1


class _Aba:
    def __init__(self, wb, titulo, caminho):
        self.parent = wb
        self.title = titulo
        self._caminho = caminho
        self._min_column = self._min_row = 1
        self._max_column = self._max_row = None
        self._ler_dimensao()

    # ---- tamanho, como o openpyxl: o <dimension> do arquivo
    def _ler_dimensao(self):
        with self.parent._zip.open(self._caminho) as f:
            cab = f.read(4096).decode("utf-8", "replace")
        self._prefixo = bool(re.search(r"<\w+:(?:worksheet|sheetData|row)\b",
                                       cab))
        m_sd = _RE_SHEETDATA.search(cab)
        m = _RE_DIM.search(cab[:m_sd.start()] if m_sd else cab)
        if m:
            lim = _ref_para_limites(m.group(1))
            if lim:
                self._min_column, self._min_row, self._max_column, \
                    self._max_row = lim
                if self._min_column is None:
                    self._min_column = 1
                if self._min_row is None:
                    self._min_row = 1

    @property
    def max_row(self):
        return self._max_row

    @property
    def max_column(self):
        return self._max_column

    @property
    def min_row(self):
        return self._min_row

    @property
    def min_column(self):
        return self._min_column

    # ---- o XML da aba em pedacos que terminam no fim de uma linha
    def _pedacos(self):
        import codecs                                    # noqa: PLC0415
        dec = codecs.getincrementaldecoder("utf-8")()
        resto = ""
        with self.parent._zip.open(self._caminho) as f:
            while True:
                bloco = f.read(1 << 22)
                if not bloco:
                    txt = resto + dec.decode(b"", final=True)
                    if txt:
                        yield txt
                    return
                txt = resto + dec.decode(bloco)
                corte = _fim_da_ultima_linha(txt)
                if corte < 0:
                    resto = txt
                    continue
                resto = txt[corte:]
                yield txt[:corte]

    def _conversor(self):
        """O valor da celula a partir do tipo, do estilo e do <v>."""
        wb = self.parent
        ss = wb._shared
        datas = wb._date_formats
        deltas = wb._timedelta_formats
        epoch = wb.epoch
        from openpyxl.utils.datetime import from_excel   # noqa: PLC0415

        def valor(tipo, sid, miolo):
            if tipo == "inlineStr":
                if miolo:
                    i = miolo.find("<is")
                    if i < 0:
                        i = miolo.find(":is")
                    if i >= 0:
                        return _texto_do_si(miolo[i:])
                return None
            if not miolo:
                return None
            if miolo[:3] == "<v>" and miolo[-4:] == "</v>" and \
                    "<" not in miolo[3:-4]:
                bruto = miolo[3:-4]
            else:
                mv = _RE_V.search(miolo)
                bruto = mv.group(1) if mv else None
            if not bruto:
                return None
            if tipo == "n" or not tipo:
                if "." in bruto or "E" in bruto or "e" in bruto:
                    v = float(bruto)
                else:
                    v = int(bruto)
                if sid and sid in datas:
                    try:
                        return from_excel(v, epoch, timedelta=sid in deltas)
                    except (OverflowError, ValueError):
                        return "#VALUE!"
                return v
            if tipo == "s":
                return ss[int(bruto)]
            if tipo == "b":
                return bool(int(bruto))
            if tipo == "d":
                from openpyxl.utils.datetime import from_ISO8601  # noqa
                return from_ISO8601(_unescape(bruto))
            return _unescape(bruto)                 # str, e (erro)
        return valor

    # ---- as linhas cruas do XML: (numero_da_linha, [(coluna, valor)])
    def _linhas_cruas(self):
        if self._prefixo:
            yield from self._linhas_cruas_lento()
            return
        valor = self._conversor()
        col_de = _col
        conta_linha = 0
        celulas = None
        col = 0
        for txt in self._pedacos():
            for (tag_row, attrs_row, c_r, c_s, c_t, resto_attr,
                 miolo) in _RE_RAPIDO.findall(txt):
                if tag_row:
                    if celulas is not None:
                        yield conta_linha, celulas
                    m = _RE_ROW_R.search(attrs_row)
                    if m:
                        v = m.group(1)
                        conta_linha = int(float(v)) if "." in v else int(v)
                    else:
                        conta_linha += 1
                    celulas = []
                    col = 0
                    continue
                if resto_attr and "=" in resto_attr:
                    # atributo fora da ordem de costume (r, s, t)
                    if not c_r:
                        m = _RE_ATTR_R.search(resto_attr)
                        c_r = m.group(1) if m else ""
                    if not c_t:
                        m = _RE_ATTR_T.search(resto_attr)
                        c_t = m.group(1) if m else ""
                    if not c_s:
                        m = _RE_ATTR_S.search(resto_attr)
                        c_s = m.group(1) if m else ""
                col = col_de(c_r) if c_r else col + 1
                if celulas is None:               # celula fora de <row>
                    continue
                celulas.append((col, valor(c_t or "n",
                                           int(c_s) if c_s else 0, miolo)))
            if celulas is not None:
                yield conta_linha, celulas
                celulas = None

    def _linhas_cruas_lento(self):
        """Para XML com prefixo de namespace (x:row, x:c): o caminho
        completo, celula por celula."""
        valor = self._conversor()
        conta_linha = 0
        for txt in self._pedacos():
            for mr in _RE_ROW.finditer(txt):
                attrs_r, miolo = mr.group(1), mr.group(2)
                m = _RE_ROW_R.search(attrs_r)
                if m:
                    v = m.group(1)
                    conta_linha = int(float(v)) if "." in v else int(v)
                else:
                    conta_linha += 1
                celulas = []
                col = 0
                if miolo:
                    for mc in _RE_CELL.finditer(miolo):
                        ca, cm = mc.group(1), mc.group(2)
                        m = _RE_ATTR_R.search(ca)
                        col = _col(m.group(1)) if m else col + 1
                        m = _RE_ATTR_T.search(ca)
                        tipo = m.group(1) if m else "n"
                        ms = _RE_ATTR_S.search(ca)
                        celulas.append((col, valor(
                            tipo, int(ms.group(1)) if ms else 0, cm)))
                yield conta_linha, celulas

    # ---- a aba inteira, como o openpyxl entrega com iter_rows() sem
    # argumentos: guardada na memoria e no disco (_CACHE_RELATORIOS)
    def _gerar_todas(self):
        """As linhas da aba inteira, uma a uma, como o openpyxl entrega
        iter_rows(values_only=True) sem argumentos."""
        max_col = self._max_column
        vazia = (None,) * max_col if max_col is not None else ()
        max_row = self._max_row
        contador = 1
        idx = 1
        for idx, cels in self._linhas_cruas():
            if max_row is not None and idx > max_row:
                break
            for _ in range(contador, idx):
                contador += 1
                yield vazia
            if contador <= idx:
                contador += 1
                if not cels and not max_col:
                    yield ()
                    continue
                mc = max_col or cels[-1][0]
                nova = [None] * mc
                for c, v in cels:
                    if 1 <= c <= mc:
                        nova[c - 1] = v
                yield tuple(nova)
        if max_row is not None and max_row < idx:
            for _ in range(contador, max_row + 1):
                yield vazia

    def _gerar_e_guardar(self):
        """Le a aba inteira entregando linha a linha; chegou ao fim, guarda
        no cache. Quem para no meio (so o cabecalho) nao paga a aba toda."""
        linhas = []
        try:
            for r in self._gerar_todas():
                linhas.append(r)
                yield r
        except Exception:                               # noqa: BLE001
            if linhas:
                raise
            # o XML veio de um jeito que a leitura rapida nao conhece
            from openpyxl import load_workbook as _lw   # noqa: PLC0415
            wb = _lw(self.parent._arquivo, read_only=True, data_only=True)
            try:
                for r in wb[self.title].iter_rows(values_only=True):
                    linhas.append(r)
                    yield r
            finally:
                wb.close()
        self.parent._guardar(self, linhas)

    # ---- igual ao ReadOnlyWorksheet.iter_rows / _cells_by_row
    def iter_rows(self, min_row=None, max_row=None, min_col=None,
                  max_col=None, values_only=False):
        max_row = max_row or None              # 0 vale "ate o fim", como
        max_col = max_col or None              # no openpyxl
        if (max_row and self._max_row and max_row > self._max_row) or (
                max_col and self._max_column and max_col > self._max_column):
            # pediu alem do tamanho que o arquivo declara: le direto
            yield from self._iter_direto(min_row, max_row, min_col, max_col,
                                         values_only)
            return
        todas = self.parent._do_cache(self)
        if todas is None:
            if not (min_row or min_col or max_row or max_col):
                for r in self._gerar_e_guardar():
                    yield r if values_only else tuple(_Celula(v) for v in r)
                return
            todas = list(self._gerar_e_guardar())
        min_col = min_col or 1
        min_row = min_row or 1
        largura = None
        if max_col:
            largura = max_col + 1 - min_col
        fim = min(max_row, len(todas)) if max_row is not None else len(todas)
        for n in range(min_row, fim + 1):
            r = todas[n - 1]
            if min_col != 1 or max_col:
                r = r[min_col - 1:max_col] if max_col else r[min_col - 1:]
                if largura is not None and len(r) < largura:
                    r = r + (None,) * (largura - len(r))
            yield r if values_only else tuple(_Celula(v) for v in r)

    def _iter_direto(self, min_row, max_row, min_col, max_col, values_only):
        """O _cells_by_row do openpyxl, lendo o XML sem cache."""
        min_col = min_col or 1
        min_row = min_row or 1
        max_col = max_col or self._max_column
        max_row = max_row or self._max_row
        vazia = ((None,) * (max_col + 1 - min_col)
                 if max_col is not None else ())
        contador = min_row
        idx = 1
        for idx, cels in self._linhas_cruas():
            if max_row is not None and idx > max_row:
                break
            for _ in range(contador, idx):
                contador += 1
                yield vazia if values_only else tuple(
                    _Celula(None) for _ in vazia)
            if contador <= idx:
                contador += 1
                if not cels and not max_col:
                    yield ()
                    continue
                mc = max_col or cels[-1][0]
                nova = [None] * (mc + 1 - min_col)
                for c, v in cels:
                    if min_col <= c <= mc:
                        nova[c - min_col] = v
                yield tuple(nova) if values_only else tuple(
                    _Celula(v) for v in nova)
        if max_row is not None and max_row < idx:
            for _ in range(contador, max_row + 1):
                yield vazia if values_only else tuple(
                    _Celula(None) for _ in vazia)

    @property
    def values(self):
        return self.iter_rows(values_only=True)

    @property
    def rows(self):
        return self.iter_rows()

    def __iter__(self):
        return self.iter_rows()

    def cell(self, row, column):
        """ws.cell(linha, coluna).value, como o ReadOnlyWorksheet."""
        linha = next(self.iter_rows(min_row=row, max_row=row, min_col=column,
                                    max_col=column, values_only=True), ())
        return _Celula(linha[0] if linha else None)


class _Celula:
    """O pouco de celula que a leitura usa: .value."""
    __slots__ = ("value",)

    def __init__(self, v):
        self.value = v


VERSAO_CACHE = 1
_MEMORIA: dict = {}             # (arquivo, assinatura, aba) -> linhas
_MEMORIA_ORDEM: list = []
LIMITE_MEMORIA = 3_000_000      # celulas guardadas no processo
TAMANHO_PARA_DISCO = 400_000    # .xlsx menor que isto nao vale o disco


def _celulas(linhas) -> int:
    return sum(len(r) for r in linhas[:50]) * max(1, len(linhas)) // max(
        1, min(50, len(linhas)))


def _guardar_na_memoria(chave, linhas):
    if chave in _MEMORIA:
        return
    _MEMORIA[chave] = linhas
    _MEMORIA_ORDEM.append((chave, _celulas(linhas)))
    total = sum(n for _, n in _MEMORIA_ORDEM)
    while total > LIMITE_MEMORIA and len(_MEMORIA_ORDEM) > 1:
        velho, n = _MEMORIA_ORDEM.pop(0)
        _MEMORIA.pop(velho, None)
        total -= n


def limpar_memoria():
    _MEMORIA.clear()
    _MEMORIA_ORDEM.clear()


class _Livro:
    def __init__(self, caminho):
        import os                                        # noqa: PLC0415
        self._arquivo = os.path.abspath(str(caminho))
        st = os.stat(self._arquivo)
        self._assinatura = f"{st.st_mtime_ns}:{st.st_size}:v{VERSAO_CACHE}"
        self._tamanho = st.st_size
        self._zip = zipfile.ZipFile(caminho)
        try:
            self._abrir()
        except Exception:
            self._zip.close()
            raise

    def _abrir(self):
        z = self._zip
        nomes = set(z.namelist())
        wbxml = z.read("xl/workbook.xml").decode("utf-8")
        rels = {}
        if "xl/_rels/workbook.xml.rels" in nomes:
            rx = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
            for m in re.finditer(r"<(?:\w+:)?Relationship\b([^>]*)/?>", rx):
                a = m.group(1)
                i = re.search(r'\bId="([^"]+)"', a)
                t = re.search(r'\bTarget="([^"]+)"', a)
                ty = re.search(r'\bType="([^"]+)"', a)
                if i and t:
                    alvo = _unescape(t.group(1))
                    if alvo.startswith("/"):
                        alvo = alvo[1:]
                    else:
                        alvo = str(PurePosixPath("xl") / alvo)
                    # normaliza ../
                    partes = []
                    for p in alvo.split("/"):
                        if p == "..":
                            if partes:
                                partes.pop()
                        elif p and p != ".":
                            partes.append(p)
                    rels[i.group(1)] = ("/".join(partes),
                                        ty.group(1) if ty else "")
        self.epoch = None
        from openpyxl.utils.datetime import (  # noqa: PLC0415
            CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900)
        m = re.search(r"<(?:\w+:)?workbookPr\b([^>]*)>", wbxml)
        d1904 = bool(m and re.search(r'\bdate1904="(1|true)"', m.group(1)))
        self.epoch = CALENDAR_MAC_1904 if d1904 else CALENDAR_WINDOWS_1900
        m = re.search(r'<(?:\w+:)?workbookView\b[^>]*\bactiveTab="(\d+)"',
                      wbxml)
        self._aba_ativa = int(m.group(1)) if m else 0
        self._abas = []
        for m in re.finditer(r"<(?:\w+:)?sheet\b([^>]*)/?>", wbxml):
            a = m.group(1)
            nome = re.search(r'\bname="([^"]*)"', a)
            rid = re.search(r'\br:id="([^"]+)"', a) or re.search(
                r'\b\w+:id="([^"]+)"', a)
            if not nome or not rid or rid.group(1) not in rels:
                continue
            caminho = rels[rid.group(1)][0]
            if caminho not in nomes or "worksheet" not in \
                    rels[rid.group(1)][1] and not caminho.startswith(
                        "xl/worksheets/"):
                # chartsheet ou aba que nao existe: o openpyxl tambem pula
                continue
            self._abas.append((_unescape(nome.group(1)), caminho))
        # textos compartilhados
        alvo_ss = next((c for c, t in rels.values()
                        if t.endswith("/sharedStrings")), None)
        if alvo_ss is None and "xl/sharedStrings.xml" in nomes:
            alvo_ss = "xl/sharedStrings.xml"
        self._shared = []
        if alvo_ss and alvo_ss in nomes:
            xml = z.read(alvo_ss).decode("utf-8")
            self._shared = [_texto_do_si(m.group(1) or "").replace(
                "x005F_", "") for m in _RE_SI.finditer(xml)]
        # estilos: quais formatos sao data (a mesma conta do openpyxl)
        self._date_formats, self._timedelta_formats = set(), set()
        alvo_st = next((c for c, t in rels.values()
                        if t.endswith("/styles")), None) or "xl/styles.xml"
        if alvo_st in nomes:
            from openpyxl.styles.stylesheet import Stylesheet  # noqa: PLC0415
            from openpyxl.xml.functions import fromstring       # noqa: PLC0415
            st = Stylesheet.from_tree(fromstring(z.read(alvo_st)))
            if st.cell_styles:
                self._date_formats = set(st.date_formats)
                self._timedelta_formats = set(st.timedelta_formats)
        self._cache = {}


    def _arquivo_cache(self, titulo):
        import os                                        # noqa: PLC0415
        pasta = os.path.join(os.path.dirname(self._arquivo),
                             "_CACHE_RELATORIOS", "xlsx")
        nome = re.sub(r"[^A-Za-z0-9_-]+", "_",
                      os.path.splitext(os.path.basename(self._arquivo))[0]
                      + "__" + titulo)
        return pasta, os.path.join(pasta, nome + ".pkl")

    def _usa_disco(self) -> bool:
        """Guarda no disco so planilha grande e so onde ja existe a pasta
        _CACHE_RELATORIOS (a RELATORIOS): nao cria pasta nova em backup."""
        import os                                        # noqa: PLC0415
        return self._tamanho >= TAMANHO_PARA_DISCO and os.path.isdir(
            os.path.join(os.path.dirname(self._arquivo), "_CACHE_RELATORIOS"))

    def _do_cache(self, aba):
        """As linhas da aba se ja foram lidas (memoria ou disco), senao
        None."""
        import pickle                                    # noqa: PLC0415
        chave = (self._arquivo, self._assinatura, aba.title)
        linhas = _MEMORIA.get(chave)
        if linhas is not None:
            return linhas
        if not self._usa_disco():
            return None
        _pasta, arq = self._arquivo_cache(aba.title)
        try:
            with open(arq, "rb") as f:
                guardado = pickle.load(f)
            if guardado.get("assinatura") == self._assinatura:
                linhas = guardado["linhas"]
                _guardar_na_memoria(chave, linhas)
                return linhas
        except Exception:                               # noqa: BLE001
            pass
        return None

    def _guardar(self, aba, linhas):
        import os                                        # noqa: PLC0415
        import pickle                                    # noqa: PLC0415
        _guardar_na_memoria((self._arquivo, self._assinatura, aba.title),
                            linhas)
        if not self._usa_disco():
            return
        pasta, arq = self._arquivo_cache(aba.title)
        try:
            os.makedirs(pasta, exist_ok=True)
            tmp = f"{arq}.{os.getpid()}.tmp"
            with open(tmp, "wb") as f:
                pickle.dump({"assinatura": self._assinatura,
                             "linhas": linhas}, f, protocol=4)
            os.replace(tmp, arq)
            self._faxina(pasta)
        except OSError:
            pass

    def _faxina(self, pasta):
        """Tira do cache o que e de planilha que nao existe mais na pasta
        (relatorio antigo apagado, PLANNER aposentado)."""
        import os                                        # noqa: PLC0415
        origem = os.path.dirname(self._arquivo)
        vivos = {re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(n)[0])
                 for n in os.listdir(origem) if n.lower().endswith(".xlsx")}
        for n in os.listdir(pasta):
            if n.endswith(".pkl") and n.split("__")[0] not in vivos:
                try:
                    os.remove(os.path.join(pasta, n))
                except OSError:
                    pass

    @property
    def sheetnames(self):
        return [n for n, _ in self._abas]

    def __getitem__(self, nome):
        for n, c in self._abas:
            if n == nome:
                if n not in self._cache:
                    self._cache[n] = _Aba(self, n, c)
                return self._cache[n]
        raise KeyError(f"Worksheet {nome} does not exist.")

    def __contains__(self, nome):
        return nome in self.sheetnames

    @property
    def worksheets(self):
        return [self[n] for n in self.sheetnames]

    @property
    def active(self):
        if not self._abas:
            return None
        i = min(max(self._aba_ativa, 0), len(self._abas) - 1)
        return self[self._abas[i][0]]

    def close(self):
        try:
            self._zip.close()
        except Exception:                               # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# =============================================================================
# A TABELA_BAP COM FOTOGRAFIA (05/11): as 7 abas de dados vem do .csv.gz
# =============================================================================
import logging as _logging

_log = _logging.getLogger("xlsx_rapido")


class _AbaFoto:
    """Uma aba de dados lida da fotografia - a mesma interface da _Aba (e do
    ReadOnlyWorksheet): iter_rows, values, rows, max_row, max_column, cell."""

    def __init__(self, livro, titulo, info, linhas):
        self.parent = livro
        self.title = titulo
        self._todas = linhas
        self._max_row = info["linhas"]
        self._max_column = info["colunas"]
        self.min_row = self.min_column = 1

    @property
    def max_row(self):
        return self._max_row

    @property
    def max_column(self):
        return self._max_column

    def iter_rows(self, min_row=None, max_row=None, min_col=None,
                  max_col=None, values_only=False):
        max_row = max_row or None              # 0 vale "ate o fim"
        max_col = max_col or None
        min_col = min_col or 1
        min_row = min_row or 1
        todas = self._todas
        if (max_row and max_row > self._max_row) or (
                max_col and max_col > self._max_column):
            # alem do tamanho da aba: como o _iter_direto (e o openpyxl) -
            # a linha vem com a largura pedida, mas so ate a ultima linha
            # que existe
            mc = max_col or self._max_column
            mr = max_row or self._max_row
            largura = mc + 1 - min_col
            for n in range(min_row, min(mr, len(todas)) + 1):
                r = todas[n - 1][min_col - 1:mc]
                if len(r) < largura:
                    r = r + (None,) * (largura - len(r))
                yield r if values_only else tuple(_Celula(v) for v in r)
            return
        largura = None
        if max_col:
            largura = max_col + 1 - min_col
        fim = min(max_row, len(todas)) if max_row is not None else len(todas)
        for n in range(min_row, fim + 1):
            r = todas[n - 1]
            if min_col != 1 or max_col:
                r = r[min_col - 1:max_col] if max_col else r[min_col - 1:]
                if largura is not None and len(r) < largura:
                    r = r + (None,) * (largura - len(r))
            yield r if values_only else tuple(_Celula(v) for v in r)

    @property
    def values(self):
        return self.iter_rows(values_only=True)

    @property
    def rows(self):
        return self.iter_rows()

    def __iter__(self):
        return self.iter_rows()

    def cell(self, row, column):
        if 1 <= row <= len(self._todas) and \
                1 <= column <= len(self._todas[row - 1]):
            return _Celula(self._todas[row - 1][column - 1])
        return _Celula(None)


class _LivroHibrido:
    """A TABELA_BAP: abas de dados da fotografia, cadastro do .xlsx."""

    def __init__(self, caminho, estado):
        import os                                        # noqa: PLC0415
        self._arquivo = os.path.abspath(str(caminho))
        self._estado = estado
        self._pasta = estado["_pasta"]
        self._xlsx = _Livro(caminho)
        self._cache = {}
        self.fotografia = {k: estado.get(k) for k in
                           ("gerada_em", "rodada", "completa_em", "carimbo")}
        self.avisos = []

    @property
    def epoch(self):
        return self._xlsx.epoch

    @property
    def sheetnames(self):
        nomes = self._xlsx.sheetnames
        return nomes + [a for a in self._estado["abas"] if a not in nomes]

    def _aba_foto(self, nome):
        import dados_bap as _db                          # noqa: PLC0415
        chave = (self._arquivo, "foto:" + str(self._estado["carimbo"]), nome)
        linhas = _MEMORIA.get(chave)
        if linhas is None:
            linhas = _db.ler_aba(self._pasta, self._estado, nome)
            _guardar_na_memoria(chave, linhas)
        return _AbaFoto(self, nome, self._estado["abas"][nome], linhas)

    def __getitem__(self, nome):
        if nome in self._cache:
            return self._cache[nome]
        if nome in self._estado["abas"]:
            try:
                ws = self._aba_foto(nome)
            except Exception as erro:                   # noqa: BLE001
                ws = self._aba_da_fotografia_nova(nome)
                if ws is None:
                    # fotografia com defeito: le do .xlsx (o de antes)
                    _log.warning("fotografia da aba %s com defeito (%s): "
                                 "lendo da TABELA_BAP", nome, erro)
                    self.avisos.append(f"{nome}: {erro}")
                    if nome not in self._xlsx.sheetnames:
                        raise
                    ws = self._xlsx[nome]
        else:
            ws = self._xlsx[nome]
        self._cache[nome] = ws
        return ws

    def _aba_da_fotografia_nova(self, nome):
        """(05/11, revisor) O robo trocou a fotografia com este livro aberto:
        a aba vem da fotografia NOVA (a que confere com o .xlsx agora), nao
        do .xlsx da rodada completa. None = nao ha fotografia nova."""
        novo = fotografia_valida(self._arquivo)
        if novo is None or nome not in novo["abas"] or \
                novo.get("carimbo") == self._estado.get("carimbo"):
            return None
        try:
            estado, pasta = self._estado, self._pasta
            self._estado, self._pasta = novo, novo["_pasta"]
            return self._aba_foto(nome)
        except Exception:                               # noqa: BLE001
            self._estado, self._pasta = estado, pasta
            return None

    def __contains__(self, nome):
        return nome in self.sheetnames

    @property
    def worksheets(self):
        return [self[n] for n in self.sheetnames]

    @property
    def active(self):
        ativa = self._xlsx.active
        return None if ativa is None else self[ativa.title]

    def close(self):
        self._xlsx.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def fotografia_valida(caminho):
    """O _estado.json da fotografia que vale para este arquivo, ou None."""
    try:
        import dados_bap as _db                          # noqa: PLC0415
    except ImportError:
        return None
    try:
        return _db.fotografia_para(caminho)
    except Exception:                                   # noqa: BLE001
        return None


def abrir(caminho):
    """O livro, para ler so valores. Nao abriu do jeito rapido: openpyxl.
    (BAP_XLSX_LENTO=1 no ambiente desliga a leitura rapida - para teste.)
    A TABELA_BAP com fotografia valida vem do _LivroHibrido."""
    import os                                            # noqa: PLC0415
    if os.environ.get("BAP_XLSX_LENTO"):
        from openpyxl import load_workbook as _lw       # noqa: PLC0415
        return _lw(caminho, read_only=True, data_only=True)
    est = fotografia_valida(caminho)
    if est is not None:
        try:
            return _LivroHibrido(caminho, est)
        except Exception as erro:                       # noqa: BLE001
            _log.warning("fotografia nao abriu (%s): lendo a TABELA_BAP",
                         erro)
    try:
        return _Livro(caminho)
    except Exception:                                   # noqa: BLE001
        from openpyxl import load_workbook as _lw       # noqa: PLC0415
        return _lw(caminho, read_only=True, data_only=True)


def load_workbook(caminho, read_only=False, data_only=False, **kw):
    """Troca direta do openpyxl.load_workbook para LEITURA de valores.
    Para qualquer outro uso (gravar, ler formula) vai no openpyxl."""
    if read_only and data_only and not kw:
        return abrir(caminho)
    from openpyxl import load_workbook as _lw           # noqa: PLC0415
    return _lw(caminho, read_only=read_only, data_only=data_only, **kw)
