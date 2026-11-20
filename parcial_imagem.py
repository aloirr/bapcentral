# -*- coding: utf-8 -*-
"""
PARCIAL EM IMAGEM - o desenho da Parcial Pedidos e da Parcial Visitas e
Positivacao (06/10), o mesmo do Claude Design:

    cabecalho (o periodo) . cartoes . faixa (pedidos em aberto / SLA)
    . a tabela POR SUPERVISOR (com TOTAL) . o TOP 3 de vendedores de cada
    indicador (o 1o em destaque, do 2o ao 5o com a barra)

Sai em PNG (para colar no WhatsApp - vai tambem para a area de
transferencia) ou em PDF (A4 em pe, a mesma imagem em alta).

Os numeros vem prontos do relatorios_nucleo.parcial_pedidos / _visitas;
aqui so se desenha (Pillow, que ja vem com o reportlab).
"""
from __future__ import annotations

import io
import math
import os
from datetime import datetime
from pathlib import Path



def _instalar(pacote: str, modulo: str) -> bool:
    """(07/10) Falta a biblioteca neste computador (No module named 'PIL'):
    instala sozinho, uma vez, com o pip do proprio Python que esta rodando
    (sem janela preta). Sem permissao na pasta do Python, tenta --user.
    False se nao der (sem internet / proxy bloqueando o pypi.org)."""
    import importlib
    import site
    import subprocess
    import sys
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        exe = exe.with_name("python.exe")
    flags = 0x08000000 if os.name == "nt" else 0       # CREATE_NO_WINDOW
    base = [str(exe), "-m", "pip", "install", pacote, "-q",
            "--disable-pip-version-check"]
    for extra in ([], ["--user"]):
        try:
            subprocess.run(base + extra, capture_output=True, timeout=300,
                           creationflags=flags, check=False)
        except Exception:                               # noqa: BLE001
            continue
        if extra:
            try:
                usuario = site.getusersitepackages()
                if usuario not in sys.path:
                    sys.path.append(usuario)
            except Exception:                           # noqa: BLE001
                pass
        importlib.invalidate_caches()
        try:
            importlib.import_module(modulo)
            return True
        except ImportError:
            continue
    return False


FALTA = ("Falta a biblioteca {0} neste computador e não consegui instalar "
         "sozinho (internet/proxy). Rode o INSTALAR_PDF.bat da pasta do BAP "
         "e tente de novo.")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                     # (07/10) instala o Pillow uma vez
    if not _instalar("pillow", "PIL"):
        raise ImportError(FALTA.format("de imagem (Pillow)")) from None
    from PIL import Image, ImageDraw, ImageFont

LARGURA = 1080                     # a largura base (px) - escala por cima
FUNDO = (243, 244, 242)
CAB = (228, 231, 227)
VERDE = (98, 187, 71)
VERDE_ESC = (47, 125, 50)
VERDE_CLARO = (238, 246, 234)
TEXTO = (30, 39, 34)
SUAVE = (105, 115, 109)
LINHA = (213, 218, 212)
CINZA_CAB = (228, 231, 229)
ZEBRA = (250, 251, 249)
BRANCO = (255, 255, 255)
OURO = (201, 162, 39)
PRATA = (154, 163, 160)
BRONZE = (176, 122, 79)
CLARO4 = (169, 219, 169)
TRILHO = (238, 240, 236)
CORES = {"ok": VERDE_ESC, "atencao": (183, 121, 31), "alerta": (179, 38, 30),
         None: TEXTO, "": TEXTO}
TOPO_CARTAO = {"ok": VERDE, "atencao": (183, 121, 31),
               "alerta": (179, 38, 30)}

# as fontes: Segoe UI no Windows; DejaVu no Linux (teste); a padrao no fim
_ARQS = {
    "normal": ("segoeui.ttf", "DejaVuSans.ttf"),
    "semi": ("seguisb.ttf", "segoeui.ttf", "DejaVuSans.ttf"),
    "bold": ("segoeuib.ttf", "DejaVuSans-Bold.ttf"),
    "black": ("seguibl.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"),
}
_PASTAS = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
           Path("/usr/share/fonts/truetype/dejavu")]
_cache = {}


def fonte(tam, peso="normal", s=1.0):
    k = (round(tam * s), peso)
    if k in _cache:
        return _cache[k]
    f = None
    for nome in _ARQS[peso]:
        for pasta in _PASTAS:
            arq = pasta / nome
            if arq.exists():
                try:
                    f = ImageFont.truetype(str(arq), k[0])
                    break
                except OSError:
                    pass
        if f:
            break
    if f is None:
        try:
            f = ImageFont.truetype(_ARQS[peso][-1], k[0])
        except OSError:
            f = ImageFont.load_default(k[0])
    _cache[k] = f
    return f


def _larg(d, txt, f):
    return d.textlength(str(txt), font=f)


def _cortar(d, txt, f, maximo):
    txt = str(txt)
    if _larg(d, txt, f) <= maximo:
        return txt
    while txt and _larg(d, txt + "…", f) > maximo:
        txt = txt[:-1]
    return txt.rstrip() + "…"


def _caber(d, txt, tam, peso, s, maximo, menor=16):
    """A maior fonte (de tam ate menor) em que o texto cabe inteiro."""
    t = tam
    while t > menor and _larg(d, txt, fonte(t, peso, s)) > maximo:
        t -= 1
    return fonte(t, peso, s)


def _quebrar(d, txt, f, maximo):
    linhas, atual = [], ""
    for palavra in str(txt).split():
        tenta = (atual + " " + palavra).strip()
        if _larg(d, tenta, f) <= maximo or not atual:
            atual = tenta
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def desenhar(p: dict, escala: float = 1.5, agora: datetime | None = None):
    """A parcial (o dict do relatorios_nucleo) numa imagem."""
    if not (p.get("faixa") or p.get("chips") or p.get("listas")):
        # (21/10, Alexandre) a IMAGEM (o print do WhatsApp) e so o RESUMO:
        # o detalhe dos clientes visitados por vendedor fica so no PDF
        return _desenhar_exec(p, escala, False)
    s = escala
    W = int(LARGURA * s)
    img = Image.new("RGB", (W, int(7000 * s)), FUNDO)
    d = ImageDraw.Draw(img)
    agora = agora or datetime.now()

    def S(v):
        return int(round(v * s))

    def F(t, peso="normal"):
        return fonte(t, peso, s)

    def texto(x, y, t, f, cor=TEXTO, anchor="la"):
        d.text((S(x), S(y)), str(t), font=f, fill=cor, anchor=anchor)

    def ret(x0, y0, x1, y1, fill=None, outline=None, w=1):
        d.rectangle([S(x0), S(y0), S(x1) - 1, S(y1) - 1], fill=fill,
                    outline=outline, width=max(1, S(w)) if outline else 0)

    def circulo(cx, cy, r, cor, num, cor_txt=BRANCO, tam=14):
        d.ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=cor)
        texto(cx, cy, num, F(tam, "bold"), cor_txt, "mm")

    PAD = 28
    LU = LARGURA - 2 * PAD               # largura util
    # ---- cabecalho
    # (07/10) so o tipo e o periodo: sem a linha de "atualizado / fonte"
    # (07/10) o NOME da parcial em destaque (o time ja sabe do que se
    # trata); o periodo embaixo, menor
    ret(0, 0, LARGURA, 116, CAB)
    ret(0, 113, LARGURA, 116, VERDE)
    texto(PAD, 16, "BAP AUTO PARTS", F(12, "bold"), VERDE_ESC)
    f_tit = _caber(d, p["tipo"].upper(), 32, "black", s, S(LU), 22)
    texto(PAD, 32, p["tipo"].upper(), f_tit)
    texto(PAD, 80, p["titulo"], F(17, "semi"), SUAVE)
    y = 136
    # ---- cartoes
    # ate 5 cartoes numa fila; mais que isso, duas filas (7 = 4 + 3)
    todos = p["cartoes"]
    corte = len(todos) if len(todos) <= 5 else (len(todos) + 1) // 2
    for k_, cs in enumerate((todos[:corte], todos[corte:])):
        if not cs:
            continue
        if k_:
            y += 96 + 10
        _fila_cartoes(d, cs, y, PAD, LU, F, texto, ret, s)
    y += 96 + 10
    # ---- faixa (pedidos em aberto agora)
    if p.get("faixa"):
        ret(PAD, y, PAD + LU, y + 40, BRANCO, LINHA)
        x = PAD + 14
        for txt, est in p["faixa"]:
            f = F(15, "bold" if est in ("titulo", "alerta") else "normal")
            cor = {"titulo": VERDE_ESC, "alerta": CORES["alerta"],
                   "ok": VERDE_ESC, "suave": SUAVE}.get(est, TEXTO)
            sobra = PAD + LU - 14 - x
            if sobra < 60:
                break
            t_ = _cortar(d, txt, f, S(sobra))
            texto(x, y + 20, t_, f, cor, "lm")
            x += _larg(d, t_, f) / s + 18
        y += 40 + 10
    # ---- por filial (Parcial Entregas): um quadrinho por filial
    if p.get("chips"):
        ch = p["chips"]
        cw = (LU - 10 * (len(ch) - 1)) / len(ch)
        for i, (nome, l1, l2) in enumerate(ch):
            x0 = PAD + i * (cw + 10)
            ret(x0, y, x0 + cw, y + 70, BRANCO, LINHA)
            texto(x0 + 12, y + 10, _cortar(d, nome, F(13, "black"),
                                           S(cw - 20)), F(13, "black"))
            for k_, partes in enumerate((l1, l2)):
                x = x0 + 12
                for txt, est in partes:
                    f = F(12, "bold" if est else "normal")
                    cor = {"alerta": CORES["alerta"], "forte": TEXTO}.get(
                        est, SUAVE)
                    texto(x, y + 32 + k_ * 17, txt, f, cor)
                    x += _larg(d, txt, f) / s + 3
        y += 70 + 10
    for lista in p.get("listas") or []:
        y = _lista(d, lista, y, PAD, LU, S, F, texto, ret, s)
    if p.get("tabela"):
        y = _tabela_sup(d, p["tabela"], y, PAD, LU, S, F, texto, ret, s)
    if p.get("nota"):
        y += 8
        for ln in _quebrar(d, p["nota"], F(13), S(LU)):
            texto(PAD, y, ln, F(13), SUAVE)
            y += 19
    if p.get("rankings"):
        y = _top5(d, img, p, y, PAD, LU, S, F, texto, ret, circulo, s)
    if p.get("tabela_vend"):           # (07/10) todos os vendedores
        y += 12
        y = _tabela_sup(d, p["tabela_vend"], y, PAD, LU, S, F, texto, ret, s)
    if p.get("fecho"):                 # (07/10) "PARABENS AOS DESTAQUES!"
        y += 10
        ret(PAD, y, PAD + LU, y + 64, VERDE_CLARO)
        ret(PAD, y, PAD + 6, y + 64, OURO)
        ret(PAD + LU - 6, y, PAD + LU, y + 64, OURO)
        texto(LARGURA / 2, y + 32, p["fecho"], F(26, "black"), VERDE_ESC,
              "mm")
        y += 64
    y += 16
    return img.crop((0, 0, W, S(y)))


def _fila_cartoes(d, cs, y, PAD, LU, F, texto, ret, s):
    """Uma fila de cartoes (rotulo, valor, detalhe, tom)."""
    gap = 10
    cw = (LU - gap * (len(cs) - 1)) / len(cs)
    for i, (rot, val, det, tom) in enumerate(cs):
        x0 = PAD + i * (cw + gap)
        larg = round((cw - 24) * s)
        ret(x0, y, x0 + cw, y + 96, BRANCO, LINHA)
        ret(x0, y, x0 + cw, y + 3, TOPO_CARTAO.get(tom, VERDE))
        texto(x0 + 14, y + 14, _cortar(d, rot, F(13, "semi"), larg),
              F(13, "semi"), SUAVE)
        f_val = _caber(d, val, 28, "bold", s, larg)
        texto(x0 + 14, y + 32, _cortar(d, val, f_val, larg), f_val)
        f_det = _caber(d, det, 12, "normal", s, larg, 10)
        texto(x0 + 14, y + 72, _cortar(d, det, f_det, larg), f_det, SUAVE)


def _tabela_sup(d, t, y, PAD, LU, S, F, texto, ret, s):
    """Uma tabela com TOTAL: a POR SUPERVISOR e a de TODOS OS VENDEDORES."""
    y += 8
    texto(PAD, y, t["titulo"], F(17, "bold"))
    y += 30
    fc, fb, fh = F(15), F(15, "bold"), F(12, "bold")
    ncol = len(t["colunas"])
    todas = t["linhas"] + [t["total"]]
    larg = []
    for j in range(ncol):
        w = max([_larg(d, t["colunas"][j], fh)] +
                [_larg(d, l[j], fb) for l in todas]) / s + 24
        larg.append(w)
    resto = LU - sum(larg[1:])
    larg[0] = max(larg[0], resto)
    if sum(larg) > LU:                      # aperta proporcional
        k_ = LU / sum(larg)
        larg = [w * k_ for w in larg]
    else:
        extra = (LU - sum(larg)) / max(1, ncol - 1)
        larg = [larg[0]] + [w + extra for w in larg[1:]]
    xs = [PAD]
    for w in larg:
        xs.append(xs[-1] + w)

    def linha_tab(vals, y0, alt, f, fundo, cores=None, topo=None):
        ret(PAD, y0, PAD + LU, y0 + alt, fundo)
        if topo:
            ret(PAD, y0, PAD + LU, y0 + 2, topo)
        for j, v in enumerate(vals):
            cor = CORES.get((cores or [None] * ncol)[j], TEXTO)
            ff = F(15, "bold") if cores and cores[j] else f
            if j == 0:
                texto(xs[j] + 9, y0 + alt / 2,
                      _cortar(d, v, ff, S(larg[j] - 14)), ff, cor, "lm")
            else:
                texto(xs[j + 1] - 9, y0 + alt / 2, v, ff, cor, "rm")
    y_tab = y
    linha_tab(t["colunas"], y, 30, fh, CINZA_CAB)
    y += 30
    for i, l in enumerate(t["linhas"]):
        linha_tab(l, y, 34, fc, BRANCO if i % 2 == 0 else ZEBRA,
                  (t.get("cores") or [None] * len(t["linhas"]))[i])
        d.line([S(PAD), S(y + 34) - 1, S(PAD + LU), S(y + 34) - 1],
               fill=TRILHO, width=1)
        y += 34
    linha_tab(t["total"], y, 36, fb, VERDE_CLARO, topo=VERDE)
    y += 36
    ret(PAD, y_tab, PAD + LU, y, None, LINHA)
    return y


PILULA = {"alerta": ((251, 236, 235), (179, 38, 30)),
          "atencao": ((253, 245, 230), (183, 121, 31)),
          "ok": ((238, 246, 234), (47, 125, 50)),
          "": ((238, 240, 236), (105, 115, 109))}


def _lista(d, lista, y, PAD, LU, S, F, texto, ret, s):
    """Uma lista de clientes (Parcial Entregas): colunas [(nome, alinha
    'l'/'r', estica)], celulas texto ou ('pilula'|'forte'|'cor', txt, tom).
    As colunas que esticam (cliente, cidade, pendencia) encolhem com '...'
    quando a lista nao cabe."""
    y += 12
    texto(PAD, y, lista["titulo"], F(19, "black"))
    if lista.get("sub"):
        texto(PAD + _larg(d, lista["titulo"], F(19, "black")) / s + 10,
              y + 6, lista["sub"], F(13), SUAVE)
    y += 32
    cols, linhas = lista["colunas"], lista["linhas"]
    fh, fc, fb, fp = F(11, "bold"), F(13), F(13, "bold"), F(11, "black")

    def txt_de(c):
        return c[1] if isinstance(c, tuple) else str(c)

    def fonte_de(c):
        if isinstance(c, tuple):
            return fp if c[0] == "pilula" else fb
        return fc
    larg = []
    for j, (nome, _a, _e) in enumerate(cols):
        w = max([_larg(d, nome, fh)] + [_larg(d, txt_de(l[j]), fonte_de(l[j]))
                                        + (S(16) if isinstance(l[j], tuple)
                                           and l[j][0] == "pilula" else 0)
                                        for l in linhas]) / s + 18
        larg.append(w)
    estica = [j for j, c in enumerate(cols) if c[2]]
    if sum(larg) > LU and estica:
        # aperta primeiro a coluna mais larga (um teto igual para as que
        # esticam): a curta (cidade) fica inteira enquanto der
        fixo = sum(w for j, w in enumerate(larg) if j not in estica)
        sobra = max(60 * len(estica), LU - fixo)
        teto, passo = max(larg[j] for j in estica), 2.0
        while teto > 60 and sum(min(larg[j], teto) for j in estica) > sobra:
            teto -= passo
        for j in estica:
            larg[j] = min(larg[j], teto)
    elif sum(larg) < LU:
        alvo = estica or list(range(len(cols)))
        extra = (LU - sum(larg)) / len(alvo)
        for j in alvo:
            larg[j] += extra
    if sum(larg) > LU:
        k_ = LU / sum(larg)
        larg = [w * k_ for w in larg]
    xs = [PAD]
    for w in larg:
        xs.append(xs[-1] + w)
    y0 = y
    ret(PAD, y, PAD + LU, y + 28, CINZA_CAB)
    for j, (nome, a, _e) in enumerate(cols):
        if a == "r":
            texto(xs[j + 1] - 8, y + 14, nome, fh, (46, 51, 48), "rm")
        else:
            texto(xs[j] + 8, y + 14, nome, fh, (46, 51, 48), "lm")
    y += 28
    if not linhas:
        ret(PAD, y, PAD + LU, y + 36, BRANCO)
        texto(PAD + 10, y + 18, lista.get("vazio") or "Nada pendente.",
              F(13), SUAVE, "lm")
        y += 36
    for i, l in enumerate(linhas):
        alt = 36
        ret(PAD, y, PAD + LU, y + alt, BRANCO if i % 2 == 0 else ZEBRA)
        d.line([S(PAD), S(y + alt) - 1, S(PAD + LU), S(y + alt) - 1],
               fill=TRILHO, width=1)
        for j, (nome, a, _e) in enumerate(cols):
            c = l[j]
            maxw = S(larg[j] - 16)
            if isinstance(c, tuple) and c[0] == "pilula":
                fundo, cor = PILULA.get(c[2], PILULA[""])
                t_ = _cortar(d, c[1], fp, maxw - S(16))
                w_ = _larg(d, t_, fp) / s + 16
                d.rounded_rectangle([S(xs[j] + 8), S(y + 8),
                                     S(xs[j] + 8 + w_), S(y + alt - 8)],
                                    radius=S(10), fill=fundo)
                texto(xs[j] + 16, y + alt / 2, t_, fp, cor, "lm")
                continue
            f = fonte_de(c)
            cor = CORES.get(c[2], TEXTO) if isinstance(c, tuple) and \
                c[0] == "cor" else TEXTO
            t_ = _cortar(d, txt_de(c), f, maxw)
            if a == "r":
                texto(xs[j + 1] - 8, y + alt / 2, t_, f, cor, "rm")
            else:
                texto(xs[j] + 8, y + alt / 2, t_, f, cor, "lm")
        y += alt
    ret(PAD, y0, PAD + LU, y, None, LINHA)
    if lista.get("rodape"):
        y += 6
        texto(PAD, y, lista["rodape"], F(12), SUAVE)
        y += 16
    return y + 8


def _top5(d, img, p, y, PAD, LU, S, F, texto, ret, circulo, s):
    """DESTAQUES DO PERIODO: o top 3 de vendedores de cada indicador
    (motivacional - so quem fez; quem ficou de fora nao aparece)."""
    y += 26
    ret(PAD, y + 2, PAD + 5, y + 30, OURO)
    texto(PAD + 14, y, "DESTAQUES DO PERÍODO", F(24, "black"))
    y += 44
    rk = p["rankings"]
    if len(rk) == 5:
        filas = [rk[:3], rk[3:]]
    elif len(rk) in (7, 8):                 # Parcial BAP: 4 + 3 (ou 4 + 4)
        filas = [rk[:4], rk[4:]]
    else:
        filas = [rk[i:i + 3] for i in range(0, len(rk), 3)]
    for fila in filas:
        n = len(fila)
        cw = (LU - 12 * (n - 1)) / n
        alto = 0
        for i, (tit, itens, menor) in enumerate(fila):
            x0 = PAD + i * (cw + 12)
            alto = max(alto, _card_rank(d, img, x0, y, cw, tit, itens, menor,
                                        S, F, texto, ret, circulo, s))
        y += alto + 12
    return y


def _card_rank(d, img, x0, y0, cw, tit, itens, menor, S, F, texto, ret,
               circulo, s):
    """Um cartao do top 3; devolve a altura usada."""
    alto = 38 + 72 + 2 * 39 + 14          # o 1o + o 2o e o 3o
    ret(x0, y0, x0 + cw, y0 + alto, BRANCO, LINHA)
    ret(x0, y0, x0 + cw, y0 + 4, VERDE)
    texto(x0 + 16, y0 + 16, tit.upper(), F(15, "black"), VERDE_ESC)
    y = y0 + 44
    if not itens:
        texto(x0 + 16, y + 10, "sem dados no período", F(15), SUAVE)
        return alto
    vals = [abs(v or 0) for _n, v, _t in itens]
    mx, mn = max(vals) or 1, min(vals)
    nome, _v, txt = itens[0]
    ret(x0 + 16, y, x0 + cw - 16, y + 68, VERDE_CLARO)
    ret(x0 + 16, y, x0 + 21, y + 68, OURO)
    circulo(x0 + 50, y + 34, 20, OURO, "1", tam=20)
    larg_txt = S(cw - 16 - 80 - 12)
    f_nome = _caber(d, nome, 18, "black", s, larg_txt, 13)
    texto(x0 + 80, y + 9, _cortar(d, nome, f_nome, larg_txt), f_nome)
    f_val = _caber(d, txt, 28, "black", s, larg_txt, 18)
    texto(x0 + 80, y + 31, _cortar(d, txt, f_val, larg_txt), f_val,
          VERDE_ESC)
    y += 68 + 12
    for i, (nome, v, txt) in enumerate(itens[1:], start=2):
        cor = [PRATA, BRONZE, CLARO4, CLARO4][i - 2]
        circulo(x0 + 30, y + 14, 14, cor, str(i),
                BRANCO if i < 4 else TEXTO, 14)
        f_v = F(16, "bold")
        w_v = d.textlength(txt, font=f_v) / s
        texto(x0 + cw - 16, y + 2, txt, f_v, TEXTO, "ra")
        larg_n = S(cw - 16 - 54 - w_v - 10)
        f_n = _caber(d, nome, 16, "semi", s, larg_n, 12)
        texto(x0 + 54, y + 2, _cortar(d, nome, f_n, larg_n), f_n)
        a = abs(v or 0)
        frac = (mn / a if menor and a else a / mx) if mx else 0
        ret(x0 + 54, y + 25, x0 + cw - 16, y + 31, TRILHO)
        ret(x0 + 54, y + 25, x0 + 54 + max(2, (cw - 70) * frac), y + 31,
            VERDE)
        y += 39
    return alto


# --------------------------------------------------------------- saidas
# =========================================================================
# (08/10) CARD EXECUTIVO - Parcial Pedidos, Visitas e BAP: fundo branco,
# os numeros numa faixa sem caixas, DESTAQUES logo depois (top 3 enxuto,
# separados por uma vertical) e as tabelas finas com verticais entre as
# colunas. A Parcial Entregas (faixa, chips e listas) segue no layout antigo.
# =========================================================================
X_LARG = 1080
X_BRANCO = (255, 255, 255)
X_TXT = (24, 31, 27)
X_SUAVE = (110, 118, 113)
X_FIO = (226, 230, 225)
X_FIO2 = (200, 206, 199)
X_VERDE = (98, 187, 71)
X_VESC = (40, 110, 48)
X_VCLARO = (241, 247, 238)
X_OURO, X_PRATA, X_BRONZE = (196, 154, 32), (150, 158, 155), (172, 118, 76)
X_COR = {"alerta": (179, 38, 30), "atencao": (176, 112, 20), "ok": X_TXT,
       None: X_TXT, "": X_TXT}


def _desenhar_exec(p, escala=1.5, com_detalhe=None):
    """com_detalhe: True = o detalhe dos visitados vai junto (embaixo);
    False = so o resumo (21/10: o print do WhatsApp, sem aviso); "pdf" = o
    resumo com o aviso de que o detalhe vem nas folhas seguintes; None =
    junto se couber (ate DETALHE_NA_IMAGEM linhas)."""
    s = escala
    detv = p.get("detalhe")
    if detv and com_detalhe is None:
        com_detalhe = detalhe_cabe(p)
    extra = (detv["linhas"] * 32 + len(detv["blocos"]) * 110
             + len(detv.get("grupos") or []) * 110 + 300) \
        if detv and com_detalhe is True else 0
    img = Image.new("RGB", (int(X_LARG * s), int((6000 + extra) * s)),
                    X_BRANCO)
    d = ImageDraw.Draw(img)

    def S(v):
        return int(round(v * s))

    def F(t, peso="normal"):
        return fonte(t, peso, s)

    def tx(x, y, t, f, cor=X_TXT, anchor="la"):
        d.text((S(x), S(y)), str(t), font=f, fill=cor, anchor=anchor)

    def rect(x0, y0, x1, y1, cor):
        d.rectangle([S(x0), S(y0), S(x1) - 1, S(y1) - 1], fill=cor)

    def hline(x0, x1, y, cor=X_FIO, w=1):
        d.line([S(x0), S(y), S(x1), S(y)], fill=cor, width=max(1, S(w)))

    PAD = 40
    LU = X_LARG - 2 * PAD
    # ---- cabecalho: so o nome e o periodo
    tx(PAD, 30, "BAP AUTO PARTS", F(13, "bold"), X_VESC)
    f_t = _caber(d, p["tipo"].upper(), 30, "black", s, S(LU * .68), 20)
    tx(PAD, 50, p["tipo"].upper(), f_t)
    tx(PAD + LU, 62, p["titulo"], F(17, "semi"), X_SUAVE, "ra")
    rect(PAD, 98, PAD + LU, 101, X_VERDE)
    y = 122
    # ---- os numeros numa faixa (sem caixas)
    cs = p["cartoes"]
    # (15/10) ate 5 numeros numa fila so (visitas + cadastros novos)
    filas = [cs] if len(cs) <= 5 else [cs[:math.ceil(len(cs) / 2)],
                                      cs[math.ceil(len(cs) / 2):]]
    for k, fila in enumerate(filas):
        cw = LU / len(fila)
        for i, (rot, val, det, tom) in enumerate(fila):
            x0 = PAD + i * cw
            if i:
                d.line([S(x0), S(y + 4), S(x0), S(y + 100)], fill=X_FIO,
                       width=max(1, S(1)))
            xl = x0 + (16 if i else 0)
            larg = S(cw - 28)
            f_r = _caber(d, rot.upper(), 13, "bold", s, larg, 11)
            tx(xl, y, _cortar(d, rot.upper(), f_r, larg), f_r, X_SUAVE)
            # (15/10, Alexandre) os NUMEROS maiores (36 -> 46)
            f_v = _caber(d, val, 46, "bold", s, larg, 22)
            tx(xl, y + 19, _cortar(d, val, f_v, larg), f_v, X_COR.get(tom))
            f_d = _caber(d, det, 13, "normal", s, larg, 10)
            tx(xl, y + 82, _cortar(d, det, f_d, larg), f_d, X_SUAVE)
        y += 112
        if k < len(filas) - 1:
            hline(PAD, PAD + LU, y - 4)
            y += 12
    hline(PAD, PAD + LU, y + 4, X_FIO2)
    y += 28

    def secao(t, y):
        tx(PAD, y, t, F(15, "black"), X_VESC)
        w = _larg(d, t, F(15, "black")) / s
        hline(PAD + w + 14, PAD + LU, y + 10, X_FIO)
        return y + 34

    # ---- DESTAQUES (o maior espaco do card)
    if p.get("rankings"):
        y = secao("DESTAQUES DO PERÍODO", y)
        rk = p["rankings"]
        if len(rk) <= 4:
            grupos = [rk]
        elif len(rk) == 5:
            grupos = [rk[:3], rk[3:]]
        else:
            grupos = [rk[:4], rk[4:]]
        for g in grupos:
            n = len(g)
            GAP = 60                # cada destaque no seu espaco,
            cw = (LU - GAP * (n - 1)) / n   # com a vertical no meio
            alto = 0
            for i, (tit, itens, menor) in enumerate(g):
                x0 = PAD + i * (cw + GAP)
                alto = max(alto, _x_rank(d, x0, y, cw, tit, itens, menor, S, F,
                                       tx, rect, hline, s))
            for i in range(1, n):
                xv = PAD + i * (cw + GAP) - GAP / 2
                d.line([S(xv), S(y - 2), S(xv), S(y + alto - 6)], fill=X_FIO,
                       width=max(1, S(1)))
            y += alto + 26
        y += 4
    # ---- tabelas finas
    # (22/10, Alexandre) LEGIVEL: a tabela larga (17 colunas) apertava a
    # letra e cortava os numeros. Uma tabela so, sem as colunas de
    # FORA_DA_PARCIAL (13 colunas)
    for chave, tit in (("tabela", None), ("tabela_vend", None)):
        t = p.get(chave)
        if not t:
            continue
        for sufixo, parte in _partes_da_tabela(t):
            y = secao(t["titulo"].upper() + sufixo, y)
            y = _x_tabela(d, parte, y, PAD, LU, S, F, tx, hline, rect,
                          s) + 26
    if p.get("nota"):
        # (22/10) a nota comprida quebra em linhas
        for ln in _quebrar(d, p["nota"], F(13), S(LU)):
            tx(PAD, y, ln, F(13), X_SUAVE)
            y += 19
        y += 7
    # (19/10) o detalhe dos clientes visitados por vendedor
    if detv and com_detalhe is True:
        # (20/10, Alexandre) um cabecalho por SUPERVISOR e os vendedores
        # dele embaixo
        y = secao(detv["titulo"].upper(), y)
        for g in _grupos_do_detalhe(detv):
            y = _x_cab_sup(d, g, y, PAD, LU, F, tx, rect, s, p["titulo"])
            for b in g["blocos"]:
                y = _x_detalhe(d, detv, b, y, PAD, LU, S, F, tx, hline, rect,
                               s)
            y = _x_rodape(d, g.get("rodape"), y, PAD, LU, F, tx, s)
    elif detv and com_detalhe == "pdf":
        aviso = (f"{detv['titulo']} ({detv['linhas']} clientes): nas folhas "
                 f"seguintes." if com_detalhe == "pdf" else
                 f"{detv['titulo']} ({detv['linhas']} clientes): no PDF da "
                 f"parcial e numa imagem por supervisor (pasta "
                 f"…_DETALHE, aberta ao gerar).")
        for ln in _quebrar(d, aviso, F(13), S(LU)):
            tx(PAD, y, ln, F(13), X_SUAVE)
            y += 19
        y += 8
    if p.get("fecho"):
        f_f = F(18, "black")
        w = _larg(d, p["fecho"], f_f) / s
        hline(PAD, X_LARG / 2 - w / 2 - 16, y + 12, X_FIO2)
        hline(X_LARG / 2 + w / 2 + 16, PAD + LU, y + 12, X_FIO2)
        tx(X_LARG / 2, y + 12, p["fecho"], f_f, X_VESC, "mm")
        y += 36
    y += 18
    return img.crop((0, 0, int(X_LARG * s), S(y)))


def _x_rank(d, x0, y0, cw, tit, itens, menor, S, F, tx, rect, hline, s):
    """O top 3 do indicador, enxuto: titulo e tres linhas (posicao, nome,
    numero). Sem barra e sem fundo; o 1o so em negrito, com o numero em
    verde."""
    LIN = 36                    # (15/10) numero maior: linha mais alta
    ALTO = 24 + 3 * LIN
    # dinheiro: o "R$" vai para o titulo e sai do numero (sobra nome)
    if any(str(t).startswith("R$ ") for _n, _v, t in itens):
        itens = [(n, v, str(t)[3:]) for n, v, t in itens]
        if "R$" not in tit:
            tit = f"{tit} (R$)"
    tx(x0, y0, tit.upper(), F(13, "bold"), X_SUAVE)
    y = y0 + 26
    if not itens:
        tx(x0, y + 2, "sem dados no período", F(14), X_SUAVE)
        return ALTO
    for i, (nome, _v, txt) in enumerate(itens[:3]):
        lider = i == 0
        base = y + 22                # posicao, nome e numero na mesma base
        tx(x0, base, f"{i + 1}º", F(15, "bold"),
           [X_OURO, X_PRATA, X_BRONZE][i], "ls")
        # (15/10, Alexandre) o NUMERO maior (17 -> 23)
        f_v = F(23 if cw >= 260 else 20, "black" if lider else "bold")
        w_v = _larg(d, txt, f_v) / s
        tx(x0 + cw, base, txt, f_v, X_VESC if lider else X_TXT, "rs")
        larg_n = S(cw - 30 - w_v - 12)
        f_n = _caber(d, nome, 15, "bold" if lider else "normal", s, larg_n,
                     13)
        tx(x0 + 30, base, _cortar(d, nome, f_n, larg_n), f_n,
           X_TXT if lider else (70, 78, 73), "ls")
        y += LIN
    return ALTO


# (22/10) os titulos curtos na imagem (a nota do rodape explica)
TITULO_CURTO = {"INTERV. ALMOÇO": "ALMOÇO", "KM/CLIENTE": "KM/CLI.",
                "% FORA DE ROTA": "% FORA ROTA", "JORNADA LÍQ.": "JORN. LÍQ."}
# (22/10, Alexandre) NUMA TABELA SO (sem partir em duas): fora da imagem e
# do PDF a META (fica o % META), os DIAS ABAIXO da jornada, os DIAS ALMOCO
# > MAX. e a PROSP. - continuam no Farol de Visita
FORA_DA_PARCIAL = ("META", "DIAS < JORN. LÍQ.", "DIAS ALMOÇO > MÁX.",
                   "PROSP.")


def _partes_da_tabela(t):
    """[("", tabela)]: a tabela da parcial sem as colunas de
    FORA_DA_PARCIAL e com os titulos curtos - uma linha por pessoa."""
    cols = list(t["colunas"])
    idx = [j for j, c in enumerate(cols)
           if j == 0 or c not in FORA_DA_PARCIAL]
    if len(idx) == len(cols):
        # (23/10) o GRANDE so na Parcial Visitas (as outras nao mudam)
        return [("", dict(t, grande="INÍCIO" in cols,
                          colunas=[TITULO_CURTO.get(c, c) for c in cols]))]
    cores = t.get("cores")
    return [("", dict(
        t, grande=True,
        colunas=[TITULO_CURTO.get(cols[j], cols[j]) for j in idx],
        linhas=[[l[j] for j in idx] for l in t["linhas"]],
        total=[t["total"][j] for j in idx] if t.get("total") else None,
        cores=[[(c_[j] if c_ and j < len(c_) else None) for j in idx]
               for c_ in cores] if cores else None))]


def _nome_curto(d, nome, f, maximo):
    """(23/10) o nome que cabe: inteiro; senao PRIMEIRO + inicial do
    ultimo ("FRANCISCO C."); senao cortado com reticencias."""
    nome = str(nome or "")
    if _larg(d, nome, f) <= maximo:
        return nome
    ps = nome.split()
    if len(ps) >= 2:
        curto = f"{ps[0]} {ps[-1][0]}."
        if _larg(d, curto, f) <= maximo:
            return curto
    return _cortar(d, nome, f, maximo)


def _x_tabela(d, t, y, PAD, LU, S, F, tx, hline, rect, s):
    """Tabela com LINHAS VERTICAIS entre as colunas (sem o fio entre as
    linhas): cabecalho, linhas e o TOTAL."""
    # (15/10, Alexandre) os NUMEROS maiores (15 -> 19); o nome fica 16.
    # Tabela larga (R$ em 3 colunas): o numero desce de tamanho ate caber,
    # em vez de apertar as colunas (um numero nao encosta no outro)
    fh = F(12, "bold")
    cols = t["colunas"]
    n = len(cols)
    todas = t["linhas"] + [t["total"]]

    # (22/10) tabela larga (14 colunas): o titulo comprido quebra em 2
    # linhas e o numero desce ate 13 - nada encosta no vizinho
    def cab_de(c):
        ps = str(c).split(" ")
        # (23/10) GRANDE: todo titulo de 2 palavras quebra (a coluna fica
        # da largura do numero, nao do titulo)
        if len(ps) < 2 or (_larg(d, c, fh) / s <= 70
                           and not t.get("grande")) or (
                               len(ps) == 2 and ps[0] == "%"):
            return [c]
        melhor = None
        for k in range(1, len(ps)):
            a_, b_ = " ".join(ps[:k]), " ".join(ps[k:])
            if a_ == "%" and len(ps) > 2:
                continue                 # (23/10) o "%" nao fica sozinho
            w_ = max(_larg(d, a_, fh), _larg(d, b_, fh))
            if melhor is None or w_ < melhor[0]:
                melhor = (w_, [a_, b_])
        return melhor[1]
    # (23/10, Alexandre) GRANDE (Parcial Visitas, print do WhatsApp): o
    # NUMERO o maior que couber (ate 26), colunas sem folga sobrando, o
    # nome curto (PRIMEIRO + inicial) e a linha mais alta
    grande = bool(t.get("grande"))
    tams = tuple(range(26, 11, -1)) if grande else \
        (19, 18, 17, 16, 15, 14, 13, 12, 11)
    for tam in tams:
        # (22/10) 16 colunas: o titulo e o nome tambem diminuem e o nome
        # do vendedor e cortado (…) antes de apertar os numeros
        if grande:
            fh = F(13 if tam >= 20 else 12, "bold")
        else:
            fh = F(12 if tam >= 15 else (11 if tam >= 13 else 10), "bold")
        cabs = [[c] if j == 0 else cab_de(c) for j, c in enumerate(cols)]
        fc, fb = F(tam), F(tam, "bold")
        t_nome = min(20, tam) if grande else min(16, tam)
        fn, fnb = F(t_nome), F(t_nome, "bold")
        if grande:
            pad = 14 if tam >= 20 else 12
        else:
            pad = 26 if tam >= 18 else (18 if tam >= 15 else 12)
        larg = [max([_larg(d, x_, fh) for x_ in cabs[j]]
                    + [_larg(d, l[j], fnb if j == 0 else fb) for l in todas])
                / s + pad for j in range(n)]
        if grande:
            larg[0] = min(larg[0], 175)
        elif tam <= 16:
            larg[0] = min(larg[0], 230 if tam >= 15 else 190)
        if sum(larg) <= LU:
            break
    alt_l = max(35, int(tam * 1.75)) if grande else 35   # altura da linha
    base_l = int(alt_l * 0.71)
    larg[0] = max(larg[0], LU - sum(larg[1:]))
    if sum(larg) > LU:
        k = LU / sum(larg)
        larg = [w * k for w in larg]
    xs = [PAD]
    for w in larg:
        xs.append(xs[-1] + w)
    y_top = y
    n_cab = max(len(c_) for c_ in cabs)
    for j, c in enumerate(cabs):
        for k, x_ in enumerate(c):
            yk = y + (n_cab - len(c) + k) * 17
            if j == 0:
                tx(xs[0], yk, x_, fh, X_SUAVE)
            else:
                tx(xs[j + 1] - (6 if grande else 8), yk, x_, fh, X_SUAVE,
                   "ra")
    y += 26 + (n_cab - 1) * 17
    dx = 6 if grande else 8              # o numero encostado a direita
    cores = t.get("cores") or [[None] * n] * len(t["linhas"])
    for l, cr in zip(t["linhas"], cores):
        for j, v in enumerate(l):
            cor = X_COR.get(cr[j]) if cr and cr[j] else X_TXT
            f = fb if cr and cr[j] else fc
            if j == 0:
                f = fnb if cr and cr[j] else fn
                # nome e numero na MESMA linha de base
                nome = (_nome_curto(d, v, f, S(larg[0] - 10)) if grande
                        else _cortar(d, v, f, S(larg[0] - 14)))
                tx(xs[0], y + base_l, nome, f, cor, "ls")
            else:
                tx(xs[j + 1] - dx, y + base_l, v, f, cor, "rs")
        y += alt_l
    y += 4
    for j, v in enumerate(t["total"]):
        if j == 0:
            tx(xs[0], y + base_l + 2, v, fnb, X_TXT, "ls")
        else:
            tx(xs[j + 1] - dx, y + base_l + 2, v, fb, X_TXT, "rs")
    y_fim = y + alt_l + 3
    # as verticais: entre as colunas, da altura da tabela toda
    for x in xs[1:-1]:
        d.line([S(x), S(y_top - 2), S(x), S(y_fim)], fill=X_FIO,
               width=max(1, S(1)))
    return y_fim


# =========================================================================
# (19/10, Alexandre) DETALHE DOS CLIENTES VISITADOS (Parcial Visitas): um
# bloco por vendedor - cliente, segmento, limite, prazo, se comprou no mes
# (e, no acumulado, a ultima visita). Na imagem vai junto quando cabe (D-1 e
# Hoje); senao, uma imagem por vendedor numa pasta ao lado. No PDF, sempre.
# =========================================================================
DETALHE_NA_IMAGEM = 160
X_COMPROU = {"ok_forte": (40, 110, 48), "atencao": (176, 112, 20),
             "alerta": (179, 38, 30)}


def detalhe_cabe(p) -> bool:
    det = p.get("detalhe")
    return bool(det) and det.get("linhas", 0) <= DETALHE_NA_IMAGEM


def _x_rodape(d, txt, y, PAD, LU, F, tx, s):
    if not txt:
        return y
    for ln in _quebrar(d, txt, F(12), int(round(LU * s))):
        tx(PAD, y, ln, F(12), X_SUAVE)
        y += 17
    return y + 10


def _grupos_do_detalhe(det) -> list:
    """Os grupos por supervisor (o detalhe antigo, sem grupos: um so)."""
    return det.get("grupos") or [{"supervisor": "", "blocos": det["blocos"],
                                  "resumo": "", "rodape": det.get("rodape"),
                                  "linhas": det.get("linhas", 0)}]


def _x_cab_sup(d, g, y, PAD, LU, F, tx, rect, s, data=""):
    """(20/10) O cabecalho do SUPERVISOR: o nome em destaque, o resumo da
    equipe e a data a direita."""
    if not g.get("supervisor"):
        return y
    y += 6
    rect(PAD, y, PAD + LU, y + 58, X_VCLARO)
    rect(PAD, y, PAD + 5, y + 58, X_VERDE)
    f_s = _caber(d, f"SUPERVISOR {g['supervisor']}", 19, "black", s,
                 int(round(LU * .62 * s)), 14)
    tx(PAD + 16, y + 27, f"SUPERVISOR {g['supervisor']}", f_s, X_VESC, "ls")
    if g.get("resumo"):
        tx(PAD + 16, y + 48, g["resumo"], F(12), X_SUAVE, "ls")
    if data:
        tx(PAD + LU - 12, y + 27, data, F(13, "semi"), X_SUAVE, "rs")
    return y + 58 + 14


def _x_detalhe(d, det, b, y, PAD, LU, S, F, tx, hline, rect, s):
    """Um vendedor: o nome, o resumo e a tabela fina (o supervisor ja esta
    no cabecalho do grupo)."""
    f_v = F(16, "black")
    tx(PAD, y + 18, b["vendedor"], f_v, X_TXT, "ls")
    tx(PAD + LU, y + 18, b["resumo"], F(12, "semi"), X_VESC, "rs")
    y += 30
    cols = det["colunas"]
    n = len(cols)
    linhas = b["linhas"]
    fh, fc, fb = F(11, "bold"), F(13), F(13, "bold")
    # larguras FIXAS (iguais em todos os vendedores); o CLIENTE fica com o
    # resto
    fixa = {1: 145, 2: 90, 3: 128, 4: 136, 5: 122, 6: 96}
    larg = [0.0] + [fixa.get(j, 110) for j in range(1, n)]
    larg[0] = LU - sum(larg[1:])
    xs = [PAD]
    for w in larg:
        xs.append(xs[-1] + w)
    rect(PAD, y, PAD + LU, y + 24, (246, 248, 245))
    for j, c in enumerate(cols):
        if j in (0, 1, 3, 4):
            tx(xs[j] + 8, y + 12, c, fh, X_SUAVE, "lm")
        else:
            tx(xs[j + 1] - 8, y + 12, c, fh, X_SUAVE, "rm")
    y += 24
    for i, (l, cr) in enumerate(zip(linhas, b.get("cores") or
                                     [[None] * n] * len(linhas))):
        if i % 2:
            rect(PAD, y, PAD + LU, y + 30, (250, 251, 249))
        for j, v in enumerate(l):
            tom = cr[j] if cr else None
            f = fb if tom else fc
            cor = X_COMPROU.get(tom, X_TXT)
            maxw = S(larg[j] - 16)
            t_ = _cortar(d, str(v), f, maxw)
            if j in (0, 1, 3, 4):
                tx(xs[j] + 8, y + 15, t_, f, cor, "lm")
            else:
                tx(xs[j + 1] - 8, y + 15, t_, f, cor, "rm")
        y += 30
    hline(PAD, PAD + LU, y, X_FIO2)
    for x in xs[1:-1]:
        d.line([S(x), S(y - 30 * len(linhas) - 24), S(x), S(y)],
               fill=X_FIO, width=max(1, S(1)))
    return y + 22


# (20/10) o tanto de linhas de uma imagem de supervisor; mais que isso, o
# supervisor sai em partes (o cabecalho dele em cada uma)
LINHAS_POR_IMAGEM_SUP = 120


def partes_do_grupo(g) -> list:
    """Os vendedores do supervisor em partes de ate LINHAS_POR_IMAGEM_SUP
    linhas (um vendedor nao se quebra)."""
    partes, atual, n = [], [], 0
    for b in g["blocos"]:
        k = len(b["linhas"])
        if atual and n + k > LINHAS_POR_IMAGEM_SUP:
            partes.append(atual)
            atual, n = [], 0
        atual.append(b)
        n += k
    if atual or not partes:
        partes.append(atual)
    return partes


def desenhar_supervisor(p, g, escala=1.5, blocos=None, parte=""):
    """(20/10, Alexandre) Um SUPERVISOR numa imagem: o cabecalho dele (nome
    em destaque, resumo da equipe e a data) e os vendedores dele, um bloco
    depois do outro. blocos: so uma parte dos vendedores (parte "1/2")."""
    s = escala
    det = p["detalhe"]
    blocos = g["blocos"] if blocos is None else blocos
    n_lin = sum(len(b["linhas"]) for b in blocos)
    img = Image.new("RGB", (int(X_LARG * s),
                            int((360 + n_lin * 32 + len(blocos) * 90) * s)),
                    X_BRANCO)
    d = ImageDraw.Draw(img)

    def S(v):
        return int(round(v * s))

    def F(t, peso="normal"):
        return fonte(t, peso, s)

    def tx(x, y, t, f, cor=X_TXT, anchor="la"):
        d.text((S(x), S(y)), str(t), font=f, fill=cor, anchor=anchor)

    def rect(x0, y0, x1, y1, cor):
        d.rectangle([S(x0), S(y0), S(x1) - 1, S(y1) - 1], fill=cor)

    def hline(x0, x1, y, cor=X_FIO, w=1):
        d.line([S(x0), S(y), S(x1), S(y)], fill=cor, width=max(1, S(w)))
    PAD = 40
    LU = X_LARG - 2 * PAD
    tx(PAD, 30, "BAP AUTO PARTS · " + det["titulo"].upper(), F(13, "bold"),
       X_VESC)
    tit = (f"SUPERVISOR {g['supervisor']}" if g.get("supervisor")
           else det["titulo"].upper())
    if parte:
        tit += f"  ({parte})"
    f_t = _caber(d, tit, 26, "black", s, S(LU * .66), 16)
    tx(PAD, 50, tit, f_t)
    tx(PAD + LU, 62, p["titulo"], F(16, "semi"), X_SUAVE, "ra")
    rect(PAD, 98, PAD + LU, 101, X_VERDE)
    y = 112
    if g.get("resumo"):
        tx(PAD, y, g["resumo"], F(13, "semi"), X_VESC)
        y += 26
    for b in blocos:
        y = _x_detalhe(d, det, b, y, PAD, LU, S, F, tx, hline, rect, s)
    y = _x_rodape(d, g.get("rodape"), y, PAD, LU, F, tx, s)
    return img.crop((0, 0, int(X_LARG * s), S(y + 8)))


def imagens_por_supervisor(p, escala=1.5) -> list:
    """[(nome do arquivo, imagem)] - uma por supervisor (ou parte)."""
    saida = []
    for i, g in enumerate(_grupos_do_detalhe(p["detalhe"]), start=1):
        partes = partes_do_grupo(g)
        for k, blocos in enumerate(partes, start=1):
            parte = f"parte {k}/{len(partes)}" if len(partes) > 1 else ""
            nome = (f"{i:02d}_SUPERVISOR_{_nome_seguro(g['supervisor'])}"
                    + (f"_PARTE_{k}" if parte else "") + ".png")
            saida.append((nome, desenhar_supervisor(p, g, escala, blocos,
                                                    parte)))
    return saida


def desenhar_detalhe(p, bloco, escala=1.5):
    """Um vendedor numa imagem so (o formato de 19/10; ficou para quem
    ainda chama): o cabecalho da parcial, o bloco dele e o rodape."""
    s = escala
    det = p["detalhe"]
    img = Image.new("RGB", (int(X_LARG * s),
                            int((420 + len(bloco["linhas"]) * 32) * s)),
                    X_BRANCO)
    d = ImageDraw.Draw(img)

    def S(v):
        return int(round(v * s))

    def F(t, peso="normal"):
        return fonte(t, peso, s)

    def tx(x, y, t, f, cor=X_TXT, anchor="la"):
        d.text((S(x), S(y)), str(t), font=f, fill=cor, anchor=anchor)

    def rect(x0, y0, x1, y1, cor):
        d.rectangle([S(x0), S(y0), S(x1) - 1, S(y1) - 1], fill=cor)

    def hline(x0, x1, y, cor=X_FIO, w=1):
        d.line([S(x0), S(y), S(x1), S(y)], fill=cor, width=max(1, S(w)))
    PAD = 40
    LU = X_LARG - 2 * PAD
    tx(PAD, 30, "BAP AUTO PARTS", F(13, "bold"), X_VESC)
    tit = det["titulo"].upper()
    f_t = _caber(d, tit, 26, "black", s, S(LU * .66), 18)
    tx(PAD, 50, tit, f_t)
    tx(PAD + LU, 62, p["titulo"], F(16, "semi"), X_SUAVE, "ra")
    rect(PAD, 98, PAD + LU, 101, X_VERDE)
    y = _x_detalhe(d, det, bloco, 120, PAD, LU, S, F, tx, hline, rect, s)
    y = _x_rodape(d, det.get("rodape"), y, PAD, LU, F, tx, s)
    return img.crop((0, 0, int(X_LARG * s), S(y + 8)))


def _nome_seguro(t) -> str:
    import re                                           # noqa: PLC0415
    import unicodedata                                  # noqa: PLC0415
    t = unicodedata.normalize("NFKD", str(t))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", "_", t.upper()).strip("_")[:40] or "X"


def nome_arquivo(p: dict, ext: str, agora: datetime | None = None) -> str:
    agora = agora or datetime.now()
    tipo = ("PARCIAL_BAP" if p["tipo"] == "Parcial BAP" else
            "PARCIAL_PEDIDOS" if "Pedidos" in p["tipo"] else
            "PARCIAL_ENTREGAS" if "Entregas" in p["tipo"] else
            "PARCIAL_VISITAS")
    q = {"acum": "ACUMULADO", "d1": "D-1", "hoje": "HOJE"}.get(p["quando"],
                                                                "")
    return f"{tipo}_{q}_{agora:%Y%m%d_%H%M}.{ext}"


def gravar_png(p: dict, pasta, agora=None) -> Path:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    img = desenhar(p, 1.5, agora)
    destino = pasta / nome_arquivo(p, "png", agora)
    img.save(destino, "PNG", optimize=True)
    # (21/10, Alexandre) o print e so o resumo: sem o detalhe dos visitados
    # e sem a pasta _DETALHE (o detalhe por vendedor vai so no PDF)
    p["_extras"] = []
    return destino


def gravar_pdf(p: dict, pasta, agora=None) -> Path:
    """A4 em pe; a imagem em alta (2x) na largura da folha - se passar da
    altura, continua na folha seguinte."""
    try:
        import reportlab                                   # noqa: F401
    except ImportError:                 # (07/10) instala uma vez
        if not _instalar("reportlab", "reportlab"):
            raise ImportError(FALTA.format("de PDF (reportlab)")) from None
    from reportlab.lib.pagesizes import A4                # noqa: PLC0415
    from reportlab.lib.utils import ImageReader            # noqa: PLC0415
    from reportlab.pdfgen import canvas                    # noqa: PLC0415
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    det = p.get("detalhe")
    if det and (p.get("faixa") or p.get("chips") or p.get("listas")):
        det = None
    # (19/10) com o detalhe dos visitados: o resumo e depois um bloco por
    # vendedor (cada um inteiro na folha quando cabe)
    imgs = [_desenhar_exec(p, 2.0, "pdf") if det else
            desenhar(p, 2.0, agora)]
    if det:
        imgs += [im for _n, im in imagens_por_supervisor(p, 2.0)]
    destino = pasta / nome_arquivo(p, "pdf", agora)
    larg_p, alt_p = A4
    m = 18
    c = canvas.Canvas(str(destino), pagesize=A4)
    c.setTitle(f"{p['tipo']} · {p['titulo']}")
    livre = alt_p - 2 * m              # o que sobra na folha atual
    usada = False

    def por(parte, esc):
        nonlocal livre, usada
        h = parte.height * esc
        buf = io.BytesIO()
        parte.save(buf, "PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), m, m + livre - h, width=larg_p - 2 * m,
                    height=h)
        livre -= h + 8
        usada = True

    def nova_folha():
        nonlocal livre, usada
        if usada:
            c.showPage()
        livre, usada = alt_p - 2 * m, False
    for k, img in enumerate(imgs):
        esc = (larg_p - 2 * m) / img.width
        h = img.height * esc
        if k == 1 or (usada and h > livre):
            nova_folha()        # o detalhe comeca numa folha nova
        fatia = int((alt_p - 2 * m) / esc)
        topo = 0
        while topo < img.height:
            parte = img.crop((0, topo, img.width,
                              min(img.height, topo + fatia)))
            if usada and parte.height * esc > livre:
                nova_folha()
            por(parte, esc)
            topo += fatia
    c.save()
    return destino


def copiar_imagem(caminho) -> bool:
    """Poe o PNG na area de transferencia do Windows (Ctrl+V no WhatsApp).
    Sem Windows (ou sem permissao), devolve False e nada acontece."""
    if os.name != "nt":
        return False
    img = Image.open(caminho).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "BMP")
    dib = buf.getvalue()[14:]              # o BMP sem o cabecalho do arquivo
    try:
        import win32clipboard                             # noqa: PLC0415
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:                                    # noqa: BLE001
        pass
    try:                                     # sem o pywin32: pelo ctypes
        import ctypes                                     # noqa: PLC0415
        from ctypes import wintypes                       # noqa: PLC0415
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalLock.restype = wintypes.LPVOID
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        h = k32.GlobalAlloc(0x0042, len(dib))           # GHND
        ptr = k32.GlobalLock(h)
        ctypes.memmove(ptr, dib, len(dib))
        k32.GlobalUnlock(h)
        if not u32.OpenClipboard(None):
            return False
        try:
            u32.EmptyClipboard()
            u32.SetClipboardData(8, h)                  # CF_DIB
        finally:
            u32.CloseClipboard()
        return True
    except Exception:                                    # noqa: BLE001
        return False
