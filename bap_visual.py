# -*- coding: utf-8 -*-
"""
BAP VISUAL - a cara de todos os programas BAP, num lugar so.

Cores da BAP (as do card de precos e do catalogo), com o PRETO BAP trocado
pelo CINZA CLARO: cabecalho cinza, verde BAP de destaque, fundo gelo,
cartoes brancos com numero grande.

O que tem aqui:
    aplicar_tema(janela)          fontes e estilos ttk
    Cabecalho(pai, area, titulo, subtitulo)
    cartao_kpi(pai, rotulo, valor, cor, detalhe)
    Tabela(pai, colunas)          tabela SO DE LEITURA, ordena no clique
    GraficoBarras(pai, ...)       barras simples (semana a semana, mes a mes)
    exportar_excel(rel, caminho)  o relatorio inteiro num .xlsx
    exportar_pdf(rel, caminho)    o relatorio num PDF (reportlab); sem a
                                  biblioteca, sai um .html para imprimir
    abrir_arquivo(caminho)        abre no programa do Windows (Excel, PDF)

Nada aqui grava em planilha de acompanhamento: so le e exporta.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


def _tela_nitida():
    """WINDOWS COM ESCALA (125%, 150%): sem avisar que o programa entende a
    escala, o Windows desenha a janela pequena e ESTICA como imagem - as
    letras ficam borradas e distorcidas. Avisando (o mesmo que o IDLE do
    Python faz), o Tk desenha no tamanho real: letra nitida e um pouco
    maior. Tem que ser antes da primeira janela. BAP_SEM_DPI=1 desliga."""
    if sys.platform != "win32" or os.environ.get("BAP_SEM_DPI"):
        return
    try:
        import ctypes                                   # noqa: PLC0415
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:                               # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:                                   # noqa: BLE001
        pass


_tela_nitida()


def altura_da_linha(font, folga=10, minimo=0):
    """A altura da linha da tabela pela LETRA (com a escala do Windows a
    letra cresce; uma altura fixa em pixels cortaria o texto)."""
    try:
        from tkinter import font as tkfont              # noqa: PLC0415
        return max(minimo, tkfont.Font(font=font).metrics("linespace")
                   + folga)
    except Exception:                                   # noqa: BLE001
        return minimo or 24

# ---------------------------------------------------------------- cores BAP
VERDE = "#59BA61"          # o verde da marca
VERDE_ESCURO = "#2F7D32"   # texto verde (legivel no branco)
VERDE_CLARO = "#E5F3DF"    # fundo de linha boa
CINZA_CAB = "#E4E7E3"      # o cabecalho (no lugar do preto BAP)
NOME_MARCA = "BAP AUTOPARTS"     # o nome nos materiais (uma grafia so)
CINZA_LINHA = "#E3E8E4"
FUNDO = "#F3F4F2"          # o gelo do fundo
CARTAO = "#FFFFFF"
ZEBRA_CLARA = "#F6F7F6"     # (08/10) a linha cinza bem clara da zebra
TEXTO = "#1E2722"
SUAVE = "#5E6B63"
VERMELHO = "#B42318"
VERMELHO_CLARO = "#FDECEA"
AMARELO = "#B7791F"
AMARELO_CLARO = "#FFF4D6"
AZUL = "#1F4FD1"           # o "NOVO" do card de preco
AZUL_CLARO = "#E3EAFB"
GRADE = "#ECEEEB"          # linhas de grade / divisorias (bem recessivas)
CAB_TABELA = "#EEF0ED"     # cabecalho de tabela
FAIXA_ABAS = "#E6EEE3"     # (10/10) a linha das abas: verde-acinzentado claro
FAIXA_ABAS_HOVER = "#DAE6D6"

# cor do NUMERO: so estado (bom / ruim / atencao); o resto fica em texto
CORES = {"ok": VERDE_ESCURO, "alerta": VERMELHO, "atencao": AMARELO,
         "info": TEXTO, "neutro": TEXTO}
# fundo da LINHA da tabela: tons bem leves, so para o olho achar o estado
FUNDOS = {"ok": "#F0F7EC", "alerta": "#FDECEA", "atencao": "#FFF4D6",
          "info": "#FFFFFF", "azul": "#EAF1FB", "cinza": "#F1F2F0",
          "grave": "#F6C9C4"}
FUNDO_GRAVE = "#F6C9C4"

FONTES = ("Segoe UI", "Calibri", "DejaVu Sans")
_fonte = "TkDefaultFont"


def fonte(tam=10, peso="normal"):
    return (_fonte, tam, peso) if peso != "normal" else (_fonte, tam)


# ------------------------------------------------------------- formatacao
def br(valor, casas=0) -> str:
    """1234567.8 -> 1.234.568 (ou com casas)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "" if valor is None else str(valor)
    txt = f"{v:,.{casas}f}"
    return txt.replace(",", "~").replace(".", ",").replace("~", ".")


def moeda(valor, casas=0) -> str:
    if valor in (None, ""):
        return ""
    return f"R$ {br(valor, casas)}"


def pct(valor, casas=0) -> str:
    if valor in (None, ""):
        return "—"
    return f"{br(valor, casas)}%"


def data_br(valor) -> str:
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    return "" if valor is None else str(valor)


def formatar(valor, tipo: str) -> str:
    if valor is None or valor == "":
        return ""
    if tipo == "moeda":
        return moeda(valor)
    if tipo == "moeda2":
        return moeda(valor, 2)
    if tipo == "pct":
        return pct(valor)
    if tipo == "pct1":
        return pct(valor, 1)
    if tipo in ("int", "num"):
        return br(valor, 0)
    if tipo == "num1":
        return br(valor, 1)
    if tipo == "num2":
        return br(valor, 2)
    if tipo == "data":
        return data_br(valor)
    if tipo == "dia":                    # dd/mm (a tabela ja tem o MES)
        return data_br(valor)[:5]
    return str(valor)


# ----------------------------------------------------------- abrir arquivo
def abrir_arquivo(caminho) -> None:
    caminho = str(caminho)
    if os.name == "nt":
        os.startfile(caminho)                       # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


# ===================================================================== TK
def em_segundo_plano(janela, funcao, ao_terminar, intervalo=150):
    """
    Roda funcao() numa thread e chama ao_terminar(resultado) na thread da
    janela (o Tk nao aceita ser mexido de outra thread).
    """
    import gc                                          # noqa: PLC0415
    import threading                                   # noqa: PLC0415
    caixa = []
    # O coletor de lixo NAO pode rodar na thread de trabalho: se ele soltar
    # uma variavel do Tk (de uma tela que ja fechou) fora da thread da
    # janela, o Tcl derruba o programa. Coleta aqui, desliga durante o
    # trabalho e religa (coletando de novo) na volta.
    gc.collect()
    gc.disable()

    def rodar():
        try:
            caixa.append(("ok", funcao()))
        except Exception as erro:                       # noqa: BLE001
            caixa.append(("erro", erro))

    def esperar():
        try:
            if not janela.winfo_exists():
                gc.enable()
                return
            if caixa:
                gc.enable()
                gc.collect()
                tipo, valor = caixa[0]
                ao_terminar(valor if tipo == "ok" else {"_erro": valor})
                return
            janela.after(intervalo, esperar)
        except tk.TclError:
            gc.enable()                 # a janela fechou no meio
    threading.Thread(target=rodar, daemon=True).start()
    janela.after(intervalo, esperar)


try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:                                 # pragma: no cover
    tk = ttk = None


def erro_com_print(pai, titulo: str, mensagem: str, arquivo=None) -> None:
    """(13/10) A mensagem de erro com o botao ABRIR O PRINT: quando o
    programa tirou foto da tela onde parou, o usuario ve o erro na hora.
    Sem print (ou sem o arquivo): o messagebox de sempre."""
    from tkinter import messagebox                       # noqa: PLC0415
    arq = Path(arquivo) if arquivo else None
    if arq is None or not arq.exists():
        messagebox.showerror(titulo, mensagem, parent=pai)
        return
    w = tk.Toplevel(pai)
    w.title(titulo)
    w.configure(background=FUNDO)
    w.transient(pai)
    w.resizable(False, False)
    corpo = tk.Frame(w, background=FUNDO)
    corpo.pack(fill="both", expand=True, padx=22, pady=(18, 10))
    tk.Label(corpo, text="✖", background=FUNDO, foreground=VERMELHO,
             font=fonte(20, "bold")).pack(side="left", anchor="n",
                                          padx=(0, 14))
    tk.Label(corpo, text=mensagem, background=FUNDO, foreground=TEXTO,
             font=fonte(10), justify="left", wraplength=460,
             anchor="w").pack(side="left", fill="x")
    botoes = tk.Frame(w, background=FUNDO)
    botoes.pack(fill="x", padx=22, pady=(4, 16))
    ttk.Button(botoes, text="OK", command=w.destroy).pack(side="right")
    ttk.Button(botoes, text="Abrir o print do erro", style="Verde.TButton",
               command=lambda: abrir_arquivo(arq)).pack(side="right",
                                                         padx=8)
    w.bind("<Escape>", lambda e: w.destroy())
    w.grab_set()
    w.focus_set()


def aplicar_tema(janela) -> None:
    """Estilos ttk de todos os programas BAP."""
    global _fonte
    from tkinter import font as tkfont              # noqa: PLC0415
    familias = set(tkfont.families(janela))
    _fonte = next((f for f in FONTES if f in familias), "TkDefaultFont")
    try:
        janela.configure(background=FUNDO)
    except tk.TclError:
        pass
    s = ttk.Style(janela)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", font=fonte(10), background=FUNDO, foreground=TEXTO,
                bordercolor=CINZA_LINHA, lightcolor=FUNDO, darkcolor=FUNDO,
                focuscolor=FUNDO)
    s.configure("TFrame", background=FUNDO)
    s.configure("Cartao.TFrame", background=CARTAO)
    s.configure("TLabel", background=FUNDO, foreground=TEXTO)
    s.configure("TButton", font=fonte(10), padding=(12, 5), width=-6,
                background=CARTAO,
                foreground=TEXTO, bordercolor=CINZA_LINHA, lightcolor=CARTAO,
                darkcolor=CARTAO, relief="flat", focuscolor=CARTAO)
    s.map("TButton", background=[("active", "#F4F6F3"), ("pressed", GRADE)],
          bordercolor=[("active", "#BFC6BE")])
    s.configure("Verde.TButton", background=VERDE, foreground="white",
                font=fonte(10, "bold"), bordercolor=VERDE, lightcolor=VERDE,
                darkcolor=VERDE, focuscolor=VERDE)
    s.map("Verde.TButton", background=[("active", VERDE_ESCURO)],
          bordercolor=[("active", VERDE_ESCURO)])
    # abas planas: a escolhida e branca (continua no conteudo), as outras
    # somem no fundo
    s.configure("TNotebook", background=FUNDO, borderwidth=0,
                bordercolor=CINZA_LINHA, lightcolor=CARTAO, darkcolor=CARTAO,
                tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab", padding=(14, 6), font=fonte(10),
                background=FUNDO, foreground=SUAVE, borderwidth=0,
                bordercolor=FUNDO, lightcolor=FUNDO, darkcolor=FUNDO)
    s.map("TNotebook.Tab",
          background=[("selected", CARTAO), ("active", "#EAEDE9")],
          foreground=[("selected", TEXTO)],
          bordercolor=[("selected", CINZA_LINHA)],
          lightcolor=[("selected", CARTAO)],
          expand=[("selected", (0, 0, 0, 0))])
    # (10/10) a LINHA DAS ABAS dos farois: uma faixa verde-acinzentada bem
    # clara, a aba escolhida em branco com o texto verde
    s.configure("Abas.TNotebook", background=FAIXA_ABAS, borderwidth=0,
                bordercolor=CINZA_LINHA, lightcolor=CARTAO, darkcolor=CARTAO,
                tabmargins=(4, 4, 4, 0))
    s.configure("Abas.TNotebook.Tab", padding=(11, 5), font=fonte(10),
                background=FAIXA_ABAS, foreground="#4F5B54", borderwidth=0,
                bordercolor=FAIXA_ABAS, lightcolor=FAIXA_ABAS,
                darkcolor=FAIXA_ABAS)
    s.map("Abas.TNotebook.Tab",
          background=[("selected", CARTAO), ("active", FAIXA_ABAS_HOVER)],
          foreground=[("selected", VERDE_ESCURO)],
          bordercolor=[("selected", CINZA_LINHA)],
          lightcolor=[("selected", CARTAO)],
          darkcolor=[("selected", CARTAO)],
          expand=[("selected", (0, 0, 0, 0))])
    s.configure("Treeview", rowheight=altura_da_linha(fonte(10), 10, 27),
                font=fonte(10), background=CARTAO,
                fieldbackground=CARTAO, foreground=TEXTO, borderwidth=0,
                bordercolor=CINZA_LINHA, lightcolor=CARTAO, darkcolor=CARTAO)
    s.configure("Treeview.Heading", font=fonte(9, "bold"), background=CAB_TABELA,
                foreground=SUAVE, relief="flat", padding=(6, 7), borderwidth=0,
                bordercolor=CAB_TABELA, lightcolor=CAB_TABELA,
                darkcolor=CAB_TABELA)
    s.map("Treeview.Heading", background=[("active", GRADE)])
    s.map("Treeview", background=[("selected", "#DCEFD4")],
          foreground=[("selected", TEXTO)])
    s.configure("TCombobox", padding=(6, 3), arrowsize=12,
                fieldbackground=CARTAO, background=CARTAO,
                bordercolor=CINZA_LINHA, lightcolor=CARTAO, darkcolor=CARTAO)
    s.map("TCombobox", fieldbackground=[("readonly", CARTAO)],
          selectbackground=[("readonly", CARTAO)],
          selectforeground=[("readonly", TEXTO)],
          bordercolor=[("focus", VERDE)])
    s.configure("TEntry", padding=(6, 3), fieldbackground=CARTAO,
                bordercolor=CINZA_LINHA, lightcolor=CARTAO, darkcolor=CARTAO)
    s.map("TEntry", bordercolor=[("focus", VERDE)])
    s.configure("Vertical.TScrollbar", background=FUNDO, troughcolor=CARTAO,
                bordercolor=CARTAO, arrowcolor=SUAVE, lightcolor=FUNDO,
                darkcolor=FUNDO, gripcount=0)
    s.configure("Horizontal.TScrollbar", background=FUNDO, troughcolor=CARTAO,
                bordercolor=CARTAO, arrowcolor=SUAVE, lightcolor=FUNDO,
                darkcolor=FUNDO, gripcount=0)
    # os estilos antigos dos programas, para quem ainda os usa
    s.configure("Titulo.TLabel", font=fonte(13, "bold"), foreground=VERDE_ESCURO)
    s.configure("Suave.TLabel", foreground=SUAVE)
    try:
        janela.option_add("*TCombobox*Listbox.font", fonte(10))
        janela.option_add("*TCombobox*Listbox.selectBackground", "#DCEFD4")
        janela.option_add("*TCombobox*Listbox.selectForeground", TEXTO)
        janela.option_add("*Menu.font", fonte(10))
    except tk.TclError:
        pass


class Cabecalho(tk.Frame if tk else object):
    """A faixa de cima: AREA pequena, titulo e UMA linha curta de contexto."""

    def __init__(self, pai, area: str, titulo: str, subtitulo: str = ""):
        super().__init__(pai, background=CINZA_CAB)
        # os botoes primeiro: o titulo nunca os espreme
        self.acoes = tk.Frame(self, background=CINZA_CAB)
        self.acoes.pack(side="right", padx=16)
        esq = tk.Frame(self, background=CINZA_CAB)
        esq.pack(side="left", fill="x", expand=True, padx=22, pady=(11, 10))
        tk.Label(esq, text=f"{NOME_MARCA}  ·  {area.upper()}",
                 background=CINZA_CAB, foreground=VERDE_ESCURO,
                 font=fonte(8, "bold")).pack(anchor="w")
        linha = tk.Frame(esq, background=CINZA_CAB)
        linha.pack(anchor="w", fill="x")
        self.lbl_titulo = tk.Label(linha, text=titulo, background=CINZA_CAB,
                                   foreground=TEXTO, font=fonte(17, "bold"))
        self.lbl_titulo.pack(side="left")
        self.lbl_sub = tk.Label(linha, text=subtitulo, background=CINZA_CAB,
                                foreground=SUAVE, font=fonte(10), anchor="w")
        self.lbl_sub.pack(side="left", padx=(14, 0), pady=(5, 0))

    def botao(self, texto, comando, verde=False):
        b = ttk.Button(self.acoes, text=texto, command=comando,
                       style="Verde.TButton" if verde else "TButton")
        b.pack(side="left", padx=3)
        return b


def _rotulo(txt: str) -> str:
    """'FATURAMENTO TOTAL' -> 'Faturamento total' (rotulo em caixa normal)."""
    txt = str(txt or "")
    return txt[:1] + txt[1:].lower() if txt.isupper() and len(txt) > 3 else txt


def cartao_kpi(pai, rotulo: str, valor: str, cor: str = "neutro",
               detalhe: str = "", largura: int = 190, espaco: int = 0,
               linhas=None, compacto: bool = False, estados=None):
    """O cartao: rotulo pequeno, o NUMERO e (se houver) um detalhe curto.
    linhas: [(rotulo, valor, tom)] - ating., projecao... embaixo.
    compacto (10/10, farois): metade da altura - o numero menor e o
    detalhe ao lado dele."""
    if compacto:
        if MODELO_CARTAO == "RRM":      # (10/11) o modelo da RRM
            return cartao_rrm(pai, rotulo, valor, cor, detalhe, espaco,
                              linhas, estados)
        return _cartao_compacto(pai, rotulo, valor, cor, detalhe, espaco,
                                linhas)
    c = tk.Frame(pai, background=CARTAO, highlightbackground=CINZA_LINHA,
                 highlightthickness=1, width=largura)
    tk.Label(c, text=_rotulo(rotulo), background=CARTAO, foreground=SUAVE,
             font=fonte(9), anchor="w", justify="left",
             wraplength=largura - 24).pack(fill="x", padx=14, pady=(10, 0))
    tam = 19 if len(str(valor)) <= 13 else (15 if len(str(valor)) <= 17 else 13)
    if espaco:              # o cartao estreito (tela pequena): o numero cabe
        while tam > 10 and len(str(valor)) * tam * 0.95 > espaco - 28:
            tam -= 1
    tk.Label(c, text=valor, background=CARTAO,
             foreground=CORES.get(cor, cor if cor.startswith("#") else TEXTO),
             font=fonte(tam, "bold"), anchor="w").pack(fill="x", padx=14)
    tk.Label(c, text=detalhe or " ", background=CARTAO, foreground=SUAVE,
             font=fonte(8), anchor="w", justify="left",
             wraplength=largura - 24).pack(fill="x", padx=14,
                                           pady=(0, 4 if linhas else 10))
    if linhas:
        g = tk.Frame(c, background=CARTAO)
        g.pack(fill="x", padx=14, pady=(0, 10))
        g.columnconfigure(1, weight=1)
        for i, (rot, val, tom) in enumerate(linhas):
            tk.Label(g, text=rot, background=CARTAO, foreground=SUAVE,
                     font=fonte(8), anchor="w").grid(row=i, column=0,
                                                     sticky="w")
            tk.Label(g, text=val, background=CARTAO,
                     foreground=CORES.get(tom, TEXTO) if tom else TEXTO,
                     font=fonte(8, "bold"), anchor="e").grid(
                         row=i, column=1, sticky="e")
    return c


# --------------------------------------------------------------------------
# (10/11, Alexandre) CARTAO NO MODELO DA RRM em todos os farois: faixa
# preta com o rotulo, o NUMERO em branco e o circulo de atingimento a
# direita (quando o cartao tem atingimento); embaixo, separador fino e a
# faixa de comparacao (as linhas do cartao, ate 3 colunas: rotulo pequeno
# e o valor em branco, colorido pelo tom); filete verde BAP no fim. O
# detalhe e o texto completo ficam na caixinha do mouse (cartao enxuto).
# --------------------------------------------------------------------------
MODELO_CARTAO = "RRM"
# (10/11, Alexandre: "Sugira cores diferentes para encaixar com o visual do
# farol e nao ficar tanto contraste do escuro com o claro") tres paletas:
#   GRAFITE = a da RRM (preto #151515)
#   VERDE   = faixa verde-grafite, mais suave (casa com o verde da marca)
#   CLARO   = faixa verde bem clara com texto escuro (sem o bloco escuro)
PALETAS_RRM = {
    "GRAFITE": {"faixa": "#151515", "rotulo": "#B9BDC1", "trilho": "#3A3F44",
                "numero": "#FFFFFF", "ok": "#59BA61", "atencao": "#E8A317",
                "alerta": "#F07A6A", "barra": "#2B2F33",
                "ok_b": "#3F8C2E", "atencao_b": "#C2860C",
                "alerta_b": "#C0392B", "filete": "#59BA61",
                "branco": "#FFFFFF", "borda": "#E6E8EA"},
    "VERDE": {"faixa": "#2E3D34", "rotulo": "#C3CEC6", "trilho": "#4B5D51",
              "numero": "#FFFFFF", "ok": "#7FD06A", "atencao": "#F0B840",
              "alerta": "#F59A8C", "barra": "#4A5D51",
              "ok_b": "#3F8C2E", "atencao_b": "#C2860C",
              "alerta_b": "#C0392B", "filete": "#59BA61",
              "branco": "#FFFFFF", "borda": "#DDE5DA"},
    "CLARO": {"faixa": "#E8F0E4", "rotulo": "#5E6B62", "trilho": "#CFDCCB",
              "numero": "#1E2722", "ok": "#2F7D32", "atencao": "#B7791F",
              "alerta": "#B42318", "barra": "#8FA79A",
              "ok_b": "#2F7D32", "atencao_b": "#B7791F",
              "alerta_b": "#B42318", "filete": "#59BA61",
              "branco": "#FFFFFF", "borda": "#E3E8E4"},
}
PALETA_RRM = os.environ.get("BAP_PALETA_RRM", "CLARO")   # (10/11) Alexandre: C
_PAL = PALETAS_RRM.get(PALETA_RRM, PALETAS_RRM["VERDE"])
BORDA_RRM_GRANDE = "#8F9C93"     # (11/11) borda do cartao do Painel
RRM_PRETO, RRM_ROTULO, RRM_TRILHO = _PAL["faixa"], _PAL["rotulo"], \
    _PAL["trilho"]
RRM_VERDE, RRM_AMARELO, RRM_VERMELHO = _PAL["ok"], _PAL["atencao"], \
    _PAL["alerta"]
RRM_NUMERO = _PAL["numero"]
RRM_TOM = {"ok": RRM_VERDE, "atencao": RRM_AMARELO, "alerta": RRM_VERMELHO}


def _norm(txt):
    """minusculo e sem acento (para achar 'atingimento', 'meta'...)."""
    import unicodedata                                  # noqa: PLC0415
    t = unicodedata.normalize("NFKD", str(txt or "")).encode(
        "ascii", "ignore").decode()
    return t.strip().lower()


def _pct_de(txt):
    """'83%' / '83,4 %' -> 83.4 (None se nao for porcentagem)."""
    m_ = re.search(r"(-?\d[\d.]*(?:,\d+)?)\s*%", str(txt or ""))
    if not m_:
        return None
    try:
        return float(m_.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def cor_atingimento(p):
    """verde >= 100%, amarelo 90-99%, vermelho < 90% (faixa preta)."""
    return RRM_VERDE if p >= 100 else (RRM_AMARELO if p >= 90
                                       else RRM_VERMELHO)


def _anel_rrm(pai, pct, rotulo_anel, sub, d=48):
    """o circulo: trilho grafite, arco na cor do tom, o % no centro e,
    embaixo dele, so o valor da meta. (11/11) d maior = tudo maior."""
    e = d / 48
    # (11/11) cresceu (Painel do Diretor): letra minima legivel
    m_ = {8: 16, 7: 14, 6: 11, 5: 11} if d > 48 else {}

    def L(t):
        return max(5, m_.get(t, 0), round(t * e))
    cv = tk.Canvas(pai, width=d + 4, height=d + round(18 * e),
                   background=RRM_PRETO, highlightthickness=0, borderwidth=0)
    cor = cor_atingimento(pct)
    cv.create_text((d + 4) / 2, 6 * e, text=rotulo_anel, fill=RRM_ROTULO,
                   font=fonte(L(6), "bold"))
    x0, y0, x1, y1 = 4, 14 * e, d, d + 10 * e
    cv.create_oval(x0, y0, x1, y1, outline=RRM_TRILHO, width=round(5 * e))
    ext = max(1.0, min(pct, 99.9)) / 100 * 360
    cv.create_arc(x0, y0, x1, y1, start=90, extent=-ext, style="arc",
                  outline=cor, width=round(5 * e))
    cy = (y0 + y1) / 2
    cv.create_text((x0 + x1) / 2, cy - (4 * e if sub else 0),
                   text=f"{pct:.0f}%".replace(".", ","), fill=cor,
                   font=fonte(L(8) if pct < 1000 else L(7), "bold"))
    if sub:
        cv.create_text((x0 + x1) / 2, cy + 9 * e, text=sub, fill=RRM_ROTULO,
                       font=fonte(L(5) - (2 if len(str(sub)) > 6 and d > 48
                                          else 0)))
    return cv


def _curto_rrm(val):
    """o valor da faixa: sem o '(16%)' do fim e sem 'R$ ' (cabe na coluna)."""
    v = re.sub(r"\s*\([^)]*\)\s*$", "", str(val or "")).strip()
    return v


def _meta_do_detalhe(det):
    """'... meta do mes 1.620' / 'desafio do mes R$ 1.500.000' -> o valor."""
    m_ = re.search(r"(?:meta|desafio) do m[eê]s\s+((?:R\$\s?)?[\d.,]+)",
                   str(det or ""))
    return m_.group(1) if m_ else None


def _compacto_rrm(v):
    """R$ 1.500.000 -> 1,50 mi; R$ 394.737 -> 395 mil (o numero do anel)."""
    t = str(v or "").replace("R$", "").strip()
    try:
        n = float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return t
    if n >= 1e6:
        return f"{n / 1e6:.2f} mi".replace(".", ",")
    if n >= 1e4:
        return f"{n / 1e3:.0f} mil"
    return t


def aneis_e_faixa(rotulo, detalhe, linhas):
    """(10/11) separa as linhas do cartao em: aneis [(rotulo, %, meta)]
    (MTD = atingimento ate a data; MES = projecao do mes / ating. do mes;
    taxa = 'Atingimento' com a 'Meta'/'Maximo'), a legenda do numero
    ('projecao do mes N') e o resto (a faixa de comparacao)."""
    ating_data = ating_mes = ating = proj = None
    meta_data = meta = None
    resto = []
    for rot, val, tom in linhas:
        r_ = _norm(rot)
        p_ = _pct_de(val)
        if "ating" in r_ and ("ate" in r_.split("ating", 1)[1]) and p_ is not None:
            ating_data = p_
        elif "ating" in r_ and "mes" in r_ and p_ is not None:
            ating_mes = p_
        elif "ating" in r_ and p_ is not None and ating is None:
            ating = p_
        elif r_.startswith("projecao do mes"):
            proj = (_curto_rrm(val), _pct_de(val))
        elif (r_.startswith("meta ate") or r_.startswith("desafio ate")):
            meta_data = val
        elif r_ in ("meta", "maximo", "teto", "minimo") or \
                r_.startswith("meta do mes"):
            meta = val
        else:
            resto.append((rot, val, tom))
    meta_mes = _meta_do_detalhe(detalhe) or meta
    aneis = []
    if ating_data is not None:
        aneis.append(("MTD", ating_data, _compacto_rrm(meta_data)))
    if proj and proj[1] is not None:
        aneis.append(("MÊS", proj[1], _compacto_rrm(meta_mes)))
    elif ating_mes is not None:
        aneis.append(("MÊS", ating_mes, _compacto_rrm(meta_mes)))
    if ating is not None and not aneis:
        aneis.append(("MÊS", ating, _compacto_rrm(meta)))
    elif meta and not aneis:
        resto.insert(0, ("meta", meta, ""))
    legenda = f"projeção do mês {proj[0]}" if proj else ""
    return aneis, legenda, resto


def _barras_estado(pai, estados, largura, altura=96, escala=1.0):
    """(10/11) a parte branca: uma coluna por estado (ordem do faturamento
    no ano), barra com os cantos de cima arredondados, o valor em cima e,
    dentro da barra, so o % (na cor do tom); estado sem dado em branco;
    legenda pequena no canto direito."""
    b = estados.get("barras") or []
    cv = tk.Canvas(pai, height=altura, background=_PAL["branco"],
                   highlightthickness=0, borderwidth=0)
    cv._dados = (b, estados.get("legenda") or "")
    e_ = escala
    # (11/11) o Painel do Diretor: letra minima legivel
    m_ = {7: 13, 6: 12, 5: 9} if escala > 1 else {}
    if escala > 1:               # espaco para a letra maior
        e_ = max(escala, 1.8)

    def L(t):                    # (11/11) letra pela escala do cartao
        return max(5, m_.get(t, 0), round(t * e_))

    def desenhar(_e=None):
        cv.delete("all")
        w = max(cv.winfo_width(), 80)
        n = len(b) or 1
        cw = (w - 16) / n
        # (10/11) a altura real quando o quadro estica (Painel do Diretor)
        alt_ = max(cv.winfo_height(), altura)
        base = alt_ - 30 * e_
        # (10/11) escala pelo maior em modulo (saldo negativo nao vira a
        # maior barra do positivo pequeno)
        nums = [abs(x[1]) for x in b if x[1]]
        mx = max(nums) if nums else 1
        for i, (uf, v, txt, rot, tom) in enumerate(b):
            cx = 8 + i * cw + cw / 2
            if cw < 58 * e_:     # 5-6 estados: o valor curto (98,1k)
                txt = str(txt).replace("R$ ", "").replace(" mil", "k")
            cv.create_text(cx, base + 9 * e_, text=uf, fill=TEXTO,
                           font=fonte(L(7), "bold"))
            if v is None:
                continue
            cor = _PAL.get(f"{tom}_b", SUAVE) if tom else SUAVE
            if not v or v <= 0:
                cv.create_text(cx, base - 6 * e_, text=txt, fill=TEXTO,
                               font=fonte(L(6), "bold"))
                if rot:
                    cv.create_text(cx, base - 18 * e_, text=rot, fill=cor,
                                   font=fonte(L(7), "bold"))
                continue
            bh = 16 * e_ + (base - 34 * e_) * v / mx
            bw = min(34 * e_, cw * 0.56)
            x0, x1, y0 = cx - bw / 2, cx + bw / 2, base - bh
            r = 3
            cv.create_rectangle(x0, y0 + r, x1, base, fill=_PAL["barra"],
                                width=0)
            cv.create_rectangle(x0 + r, y0, x1 - r, y0 + r,
                                fill=_PAL["barra"], width=0)
            cv.create_oval(x0, y0, x0 + 2 * r, y0 + 2 * r,
                           fill=_PAL["barra"], width=0)
            cv.create_oval(x1 - 2 * r, y0, x1, y0 + 2 * r,
                           fill=_PAL["barra"], width=0)
            cv.create_text(cx, y0 - 7 * e_, text=txt, fill=TEXTO,
                           font=fonte(L(6), "bold"))
            if rot:
                cv.create_text(cx, y0 + 9 * e_, text=rot,
                               fill=_PAL.get(tom, "#FFFFFF") if tom
                               else "#FFFFFF", font=fonte(L(7), "bold"))
        leg = estados.get("legenda") or ""
        if leg:
            cv.create_text(w - 6, alt_ - 6, text="● ", anchor="e",
                           fill=VERMELHO, font=fonte(L(5)))
            cv.create_text(w - 6 - 8 * e_, alt_ - 6, text=leg, anchor="e",
                           fill=SUAVE, font=fonte(L(5)))
    cv.bind("<Configure>", desenhar)
    return cv


def cartao_rrm(pai, rotulo, valor, cor="neutro", detalhe="", espaco=0,
               linhas=None, estados=None):
    """(10/11) o cartao no modelo da RRM (veja acima)."""
    linhas = list(linhas or [])
    aneis, legenda, resto = aneis_e_faixa(rotulo, detalhe, linhas)
    if not aneis and not legenda:
        legenda = str(detalhe or "").strip()     # o detalhe curto embaixo
    caixa = tk.Frame(pai, background=_PAL["branco"],
                     highlightbackground=_PAL["borda"], highlightthickness=1)
    c = tk.Frame(caixa, background=RRM_PRETO)
    c.pack(fill="x")
    topo = tk.Frame(c, background=RRM_PRETO)
    topo.pack(fill="x", padx=10, pady=(7, 0))
    for rot_a, p_a, sub_a in reversed(aneis):
        _anel_rrm(topo, p_a, rot_a, sub_a).pack(side="right", padx=(2, 0))
    esq = tk.Frame(topo, background=RRM_PRETO)
    esq.pack(side="left", fill="both", expand=True)
    lin_r = tk.Frame(esq, background=RRM_PRETO)
    lin_r.pack(fill="x")
    if not aneis and cor in RRM_TOM:              # sem circulo: o tom
        tk.Label(lin_r, text="●", background=RRM_PRETO,
                 foreground=RRM_TOM[cor], font=fonte(7)).pack(side="left")
    larg_txt = max(60, (espaco or 200) - 26 - len(aneis) * 54)
    tk.Label(lin_r, text=str(rotulo).upper(), background=RRM_PRETO,
             foreground=RRM_ROTULO, font=fonte(7, "bold"), anchor="w",
             justify="left", wraplength=larg_txt).pack(side="left")
    tam = 15 if len(str(valor)) <= 11 else 13
    while tam > 9 and len(str(valor)) * tam * 0.8 > larg_txt:
        tam -= 1
    tk.Label(esq, text=valor, background=RRM_PRETO, foreground=RRM_NUMERO,
             font=fonte(tam, "bold"), anchor="w").pack(fill="x",
                                                       pady=(2, 0))
    if legenda:
        tk.Label(esq, text=legenda, background=RRM_PRETO,
                 foreground=RRM_ROTULO, font=fonte(6), anchor="w",
                 justify="left", wraplength=larg_txt).pack(fill="x")
    if resto:
        tk.Frame(c, background=RRM_TRILHO, height=1).pack(
            fill="x", padx=10, pady=(4, 0))
        fx = tk.Frame(c, background=RRM_PRETO)
        fx.pack(fill="x", padx=10, pady=(2, 5))
        n = min(3, len(resto))
        for j, (rot, val, tom) in enumerate(resto[:3]):
            fx.columnconfigure(j, weight=1, uniform="rrm")
            cel = tk.Frame(fx, background=RRM_PRETO)
            cel.grid(row=0, column=j, sticky="w")
            tk.Label(cel, text=_rotulo(rot).lower(), background=RRM_PRETO,
                     foreground=RRM_ROTULO, font=fonte(6), anchor="w",
                     wraplength=max(50, ((espaco or 200) - 20) // n)).pack(
                         anchor="w")
            tk.Label(cel, text=_curto_rrm(val), background=RRM_PRETO,
                     foreground=RRM_TOM.get(tom, RRM_NUMERO),
                     font=fonte(8, "bold"), anchor="w").pack(anchor="w")
    else:
        tk.Frame(c, background=RRM_PRETO, height=6).pack(fill="x")
    tk.Frame(caixa, background=_PAL["filete"], height=3).pack(fill="x")
    if estados and estados.get("barras"):
        # (10/11) a visao por estado embaixo da faixa (parte branca)
        _barras_estado(caixa, estados, espaco or 200).pack(fill="x")
    ajuda = "\n".join(x for x in (
        str(detalhe or "").strip(),
        "\n".join(f"{r}: {v}" for r, v, _t in linhas)) if x)
    if ajuda:
        pilha = [c]
        while pilha:
            w_ = pilha.pop()
            Dica(w_, ajuda)
            pilha.extend(w_.winfo_children())
    return caixa


def cartao_rrm_spec(pai, c, espaco=250, alt_barras=120, escala=1.0):
    """(10/11, recado 20261109-1345) o cartao do Painel do Diretor no
    modelo da RRM, de um dicionario pronto (painel_rrm.calcular): rotulo,
    numero, circulos [(rotulo, %, meta)], a legenda do numero, a faixa de
    comparacao [(mes, variacao, tom, fechamento)] e as barras por estado.
    (11/11) escala > 1: letras, circulos e barras maiores (4 por linha)."""
    e = escala
    # (11/11, "ainda ficou muito pequeno… praticamente ilegivel") letra
    # minima no cartao grande: rotulo, legenda e meses 10; fechamento 13
    minimo = {7: 12, 6: 12, 9: 16, 16: 30, 14: 28} if escala > 1 else {}

    def L(t):
        return max(5, minimo.get(t, 0), round(t * e))
    # (11/11, "Coloque uma borda. pois ficou muito solto") o cartao grande
    # com borda de 2 px cinza-esverdeado
    caixa = tk.Frame(pai, background=_PAL["branco"],
                     highlightbackground=BORDA_RRM_GRANDE if escala > 1
                     else _PAL["borda"],
                     highlightcolor=BORDA_RRM_GRANDE if escala > 1
                     else _PAL["borda"],
                     highlightthickness=2 if escala > 1 else 1)
    fx_ = tk.Frame(caixa, background=RRM_PRETO)
    fx_.pack(fill="x")
    topo = tk.Frame(fx_, background=RRM_PRETO)
    topo.pack(fill="x", padx=round(10 * e), pady=(round(7 * e), 0))
    aneis = [a for a in c.get("aneis") or [] if a[1] is not None]
    for rot_a, p_a, sub_a in reversed(aneis):
        _anel_rrm(topo, p_a, rot_a, sub_a,
                  d=max(86, round(48 * e)) if e > 1 else 48).pack(
            side="right", padx=(2, 0))
    esq = tk.Frame(topo, background=RRM_PRETO)
    esq.pack(side="left", fill="both", expand=True)
    larg_txt = max(60, (espaco or 200) - 26 * e - len(aneis) * (
        max(86, 48 * e) + 6 if e > 1 else 54))
    tk.Label(esq, text=str(c["titulo"]).upper(), background=RRM_PRETO,
             foreground=RRM_ROTULO, font=fonte(L(7), "bold"), anchor="w",
             justify="left", wraplength=larg_txt).pack(fill="x")
    valor = str(c.get("valor") or "—")
    tam = L(16) if len(valor) <= 10 else L(14)
    while tam > 9 and len(valor) * tam * 0.8 > larg_txt:
        tam -= 1
    tk.Label(esq, text=valor, background=RRM_PRETO, foreground=RRM_NUMERO,
             font=fonte(tam, "bold"), anchor="w").pack(fill="x",
                                                       pady=(2, 0))
    tk.Label(esq, text=c.get("legenda") or " ", background=RRM_PRETO,
             foreground=RRM_ROTULO, font=fonte(L(6)), anchor="w").pack(
                 fill="x")
    tk.Frame(fx_, background=RRM_TRILHO, height=1).pack(
        fill="x", padx=round(10 * e), pady=(round(4 * e), 0))
    fx = tk.Frame(fx_, background=RRM_PRETO)
    fx.pack(fill="x", padx=round(10 * e), pady=(2, round(6 * e)))
    for j, (m_, t_, tm, real) in enumerate((c.get("faixa") or [])[:3]):
        fx.columnconfigure(j, weight=4 if j == 2 else 3, uniform="fx")
        cel = tk.Frame(fx, background=RRM_PRETO)
        cel.grid(row=0, column=j, sticky="w")
        l1 = tk.Frame(cel, background=RRM_PRETO)
        l1.pack(anchor="w")
        tk.Label(l1, text=m_, background=RRM_PRETO, foreground=RRM_ROTULO,
                 font=fonte(L(6)), padx=0).pack(side="left")
        if t_:
            tk.Label(l1, text=" " + t_, background=RRM_PRETO,
                     foreground=RRM_TOM.get(tm, RRM_ROTULO),
                     font=fonte(L(6), "bold"), padx=0).pack(side="left")
        tk.Label(cel, text=real, background=RRM_PRETO,
                 foreground=RRM_NUMERO if real != "—" else RRM_ROTULO,
                 font=fonte(L(9), "bold"), anchor="w").pack(anchor="w")
    tk.Frame(caixa, background=_PAL["filete"], height=3).pack(fill="x")
    if c.get("estados") and c["estados"].get("barras"):
        _barras_estado(caixa, c["estados"], espaco or 200,
                       altura=round(alt_barras * e), escala=e).pack(
                           fill="both", expand=True)
    if c.get("ajuda"):
        pilha = [caixa]
        while pilha:
            w_ = pilha.pop()
            Dica(w_, c["ajuda"])
            pilha.extend(w_.winfo_children())
    return caixa


def spec_do_kpi(k, estados=None):
    """(10/11) o cartao kpi() de um farol no formato do cartao RRM
    (cartao_rrm_spec / painel_rrm._cartao_pil): para o PDF e o Excel."""
    linhas = list(k.get("linhas") or [])
    aneis, legenda, resto = aneis_e_faixa(k.get("rotulo", ""),
                                          k.get("detalhe", ""), linhas)
    if not aneis and not legenda:
        legenda = str(k.get("detalhe") or "").strip()
    return {"titulo": k.get("rotulo", ""), "valor": str(k.get("valor", "")),
            "legenda": legenda,
            "aneis": [(r_, p_, m_) for r_, p_, m_ in aneis],
            "faixa": [(_rotulo(r_).lower(), "", "", _curto_rrm(v_))
                      for r_, v_, _t in resto[:3]],
            "estados": estados if estados and estados.get("barras")
            else None}


def imagem_cartoes_rrm(specs, por_linha=5, largura=2400):
    """(10/11) os cartoes RRM numa imagem PIL (largura em px), em linhas de
    por_linha cartoes; a parte branca so quando a linha tem barras."""
    from PIL import Image, ImageDraw                    # noqa: PLC0415
    import painel_rrm as prm                            # noqa: PLC0415
    import parcial_imagem as pi                         # noqa: PLC0415
    s_ = largura / 1920
    pal = {k_: prm._rgb(v_) for k_, v_ in _PAL.items()}

    def F(t, peso="normal"):
        return pi.fonte(t, peso, s_)

    def P(v):
        return int(round(v * s_))
    gap = P(14)
    cw = (largura - (por_linha - 1) * gap) // por_linha
    linhas = [specs[i:i + por_linha] for i in range(0, len(specs),
                                                     por_linha)]
    alts = [P(200) + (P(190) if any(c.get("estados") for c in ln) else 0)
            for ln in linhas]
    img = Image.new("RGB", (largura, sum(alts) + gap * (len(alts) - 1)),
                    (255, 255, 255))
    d = ImageDraw.Draw(img)
    y = 0
    for ln, h in zip(linhas, alts):
        for j, c in enumerate(ln):
            prm._cartao_pil(d, j * (cw + gap), y, cw, h - 1, c, pal, F, P)
        y += h + gap
    return img


def _por_linha_rrm(n_):
    return n_ if n_ <= 6 else (4 if n_ == 8 else 5 if n_ in (9, 10) else 6)


def _estados_do_rel(rel, k):
    try:
        import relatorios_nucleo as rn                  # noqa: PLC0415
        return rn.estados_do_cartao(rel, k)
    except Exception:                                   # noqa: BLE001
        return None


# o valor dentro do detalhe do cartao: R$ 1.500.000, 1.076, 85%, 6,2
_VALOR_NO_TEXTO = r"((?:R\$\s?)?-?\d[\d.]*(?:,\d+)?\s?%?)"


def _cartao_compacto(pai, rotulo, valor, cor, detalhe, espaco, linhas):
    """(10/10) rotulo, NUMERO e o detalhe embaixo, pequeno e cinza - nada
    ao lado do numero. As linhas (ating., projecao...) nao aparecem no
    cartao: ficam na caixinha ao passar o mouse."""
    c = tk.Frame(pai, background=CARTAO, highlightbackground=CINZA_LINHA,
                 highlightthickness=1)
    tk.Label(c, text=_rotulo(rotulo), background=CARTAO, foreground=SUAVE,
             font=fonte(8), anchor="w").pack(fill="x", padx=12, pady=(6, 0))
    tam = 14 if len(str(valor)) <= 13 else 12
    if espaco:
        while tam > 9 and len(str(valor)) * tam * 0.95 > espaco - 24:
            tam -= 1
    tk.Label(c, text=valor, background=CARTAO,
             foreground=CORES.get(cor, cor if cor.startswith("#") else TEXTO),
             font=fonte(tam, "bold"), anchor="w").pack(
                 fill="x", padx=12, pady=(0, 0 if detalhe else 6))
    if detalhe:
        # (10/10) a 1a letra maiuscula e o VALOR em negrito
        d = str(detalhe).strip()
        d = d[:1].upper() + d[1:]
        lin = tk.Frame(c, background=CARTAO)
        lin.pack(fill="x", padx=12, pady=(0, 6))
        for k, parte in enumerate(re.split(_VALOR_NO_TEXTO, d)):
            if not parte:
                continue
            valor_ = bool(k % 2)
            tk.Label(lin, text=parte, background=CARTAO,
                     foreground=TEXTO if valor_ else SUAVE,
                     font=fonte(8, "bold") if valor_ else fonte(8),
                     padx=0, pady=0, borderwidth=0).pack(side="left")
    if linhas:
        texto = "\n".join(f"{rot}: {val}" for rot, val, _t in linhas)
        for w in [c] + list(c.winfo_children()):
            Dica(w, texto)
    return c


class Dica:
    """Caixinha que aparece ao passar o mouse (o texto de ajuda fica aqui)."""

    def __init__(self, widget, texto: str):
        self.widget, self.texto, self.janela = widget, texto, None
        widget.bind("<Enter>", self.mostrar, add="+")
        widget.bind("<Leave>", self.esconder, add="+")
        widget.bind("<ButtonPress>", self.esconder, add="+")

    def mostrar(self, _e=None):
        if self.janela or not self.texto:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.janela = tk.Toplevel(self.widget)
        self.janela.wm_overrideredirect(True)
        self.janela.configure(background=CINZA_LINHA)
        tk.Label(self.janela, text=self.texto, background=CARTAO,
                 foreground=TEXTO, font=fonte(9), justify="left",
                 wraplength=420, padx=12, pady=9).pack(padx=1, pady=1)
        self.janela.wm_geometry(f"+{x}+{y}")

    def esconder(self, _e=None):
        if self.janela:
            try:
                self.janela.destroy()
            except tk.TclError:
                pass
            self.janela = None


def compactar_ajudas(raiz, limite: int = 80) -> int:
    """
    Troca os paragrafos de instrucao (rotulos compridos e fixos) por um
    'ⓘ' discreto: o texto continua la, na dica do mouse. Rotulo com
    variavel (que muda sozinho) fica como esta.
    """
    trocados = 0
    pilha = [raiz]
    while pilha:
        w = pilha.pop()
        try:
            pilha.extend(w.winfo_children())
        except tk.TclError:
            continue
        if getattr(w, "_bap_ajuda", False):
            continue
        try:
            classe = w.winfo_class()
        except tk.TclError:
            continue
        if classe not in ("Label", "TLabel"):
            continue
        try:
            if str(w.cget("textvariable")):
                continue
            txt = str(w.cget("text"))
        except tk.TclError:
            continue
        if len(txt.strip()) <= limite:
            continue
        w._bap_ajuda = True
        try:
            if classe == "Label":
                w.configure(text="ⓘ Ajuda", foreground=SUAVE, cursor="hand2",
                            wraplength=0, font=fonte(9))
            else:
                w.configure(text="ⓘ Ajuda", cursor="hand2", wraplength=0)
        except tk.TclError:
            continue
        Dica(w, " ".join(txt.split()))
        trocados += 1
    return trocados


class Tabela(tk.Frame if tk else object):
    """
    Tabela SO DE LEITURA. Clique no titulo da coluna ordena; a cor da linha
    vem do "tom" (ok / alerta / atencao / info).
    colunas: [{"nome", "tipo", "largura"}]
    """

    def __init__(self, pai, colunas: list, altura: int = 18, grupos=None,
                 compacta: bool = False, zebra: bool = False, letra=None,
                 cabe: bool = False):
        super().__init__(pai, background=CARTAO)
        # (04/11, Alexandre) CABE: sem barra de rolar para o lado - as
        # colunas cabem na largura (a letra desce ate 7 se precisar) e as
        # barras de rolagem so aparecem quando ha o que rolar
        # (04/11) cabe="auto": todas as abas dos farois - cabe na largura
        # ONDE DER (letra ate 7); se nem assim couber, fica como era (letra
        # pedida e barra de rolar para o lado)
        self.cabe = bool(cabe)
        self._cabe_auto = cabe == "auto"
        self._compacta0 = bool(compacta or letra)
        # (30/10) LETRA: o tamanho da letra pedido pelo relatorio (ex. 8 nas
        # Campanhas BAP, para caber tudo na tela); liga o modo compacto
        if letra:
            compacta = True
        # (08/10) ZEBRA: linhas brancas e cinza bem claro, sem cor de tom
        self.zebra = zebra
        self.colunas = colunas
        # GRUPOS: [(rotulo, quantas colunas)] - uma faixa em cima juntando
        # as colunas de cada indicador (META / REAL / % / NEC./DIA embaixo)
        self.grupos = list(grupos or [])
        # COMPACTA: letra menor, para a tabela larga caber na tela
        self.compacta = compacta
        # COMPACTA (Farol de Metas): letra 9 quando cabe (ate 30 colunas de
        # numero, as abas de territorio), 8 nas abas de pessoa (40+)
        n_num = sum(1 for c in colunas if not c.get("oculta")
                    and c.get("tipo", "texto") not in ("texto", "data", "dia"))
        self._tam = (9 if n_num <= 30 else 8) if compacta else 10
        if letra:
            self._tam = max(7, min(10, int(letra)))
        self._tam_cab = self._tam - 1 if compacta else self._tam - 1
        self._tam0 = self._tam
        estilo = "Treeview"
        if compacta:
            estilo = f"Compacta{self._tam}.Treeview"
            st = ttk.Style(self)
            st.configure(estilo, rowheight=altura_da_linha(
                fonte(self._tam), 8, self._tam * 2 + 8),
                         font=fonte(self._tam))
            st.configure(f"{estilo}.Heading",
                         font=fonte(self._tam_cab, "bold"),
                         padding=(2, 5), background="#E4E7E5",
                         foreground="#2E3330")
        ids = [f"c{i}" for i in range(len(colunas))]
        self.tv = ttk.Treeview(self, columns=ids, show="headings",
                               height=altura, selectmode="extended",
                               style=estilo)
        self._larg = []
        fator = (6.4 if self._tam >= 9 else 6.0) if compacta else 7.4
        for i, col in zip(ids, colunas):
            num = col.get("tipo", "texto") not in ("texto", "data", "dia")
            titulo = self._titulo(col)
            self.tv.heading(i, text=titulo,
                            command=lambda c=i: self.ordenar(c))
            larg = max(col.get("largura", 110), int(len(titulo) * fator) + 18)
            self._larg.append(larg)
            self.tv.column(i, width=larg, minwidth=40,
                           anchor="e" if num else "w", stretch=False)
        self._visiveis = [j for j, c in enumerate(colunas) if not c.get("oculta")]
        self.tv["displaycolumns"] = [f"c{j}" for j in self._visiveis]
        self._ultima_largura = 0
        self.tv.bind("<Configure>", self._caber, add="+")
        for tom, fundo in FUNDOS.items():
            self.tv.tag_configure(tom, background=fundo)
        self.tv.tag_configure("zebra", background=ZEBRA_CLARA)
        # (13/10) GRAVE: a linha vermelha de verdade (acima do teto sem
        # autorizacao) - nem a zebra tira
        self.tv.tag_configure("grave", background=FUNDO_GRAVE,
                              foreground="#7A1410")
        self.tv.tag_configure("total", font=fonte(self._tam, "bold"),
                              background=CAB_TABELA)
        sy = ttk.Scrollbar(self, orient="vertical", command=self.tv.yview)
        sx = ttk.Scrollbar(self, orient="horizontal", command=self.tv.xview)
        self._sx = sx
        self._sy = sy
        self.tv.configure(yscrollcommand=self._rolou_y,
                          xscrollcommand=self._rolou_x)
        # (08/10) CELULAS DESENHADAS: coluna com "chip" (a celula pintada
        # pela faixa do valor - o SLA) ou "barra" (barra de progresso - o %
        # ATENDIDO). O Treeview so pinta a linha inteira; essas celulas sao
        # quadrinhos por cima, refeitos ao rolar, ordenar e redimensionar.
        self._desenhadas = [j for j, c in enumerate(colunas)
                            if c.get("chip") or c.get("barra")
                            or c.get("chip_tom") is not None]
        self._pool = []
        self._agendado = None
        if self._desenhadas:
            self.tv.bind("<Configure>", lambda e: self._pintar_depois(),
                         add="+")
            self.tv.bind("<ButtonRelease-1>",
                         lambda e: self._pintar_depois(), add="+")
            self.tv.bind("<<TreeviewSelect>>",
                         lambda e: self._pintar_depois(), add="+")
        self.faixa = None
        if self.grupos:
            self.faixa = tk.Canvas(self, height=22, background=CARTAO,
                                   highlightthickness=0, borderwidth=0)
            self.faixa.grid(row=0, column=0, sticky="ew")
            self.tv.bind("<ButtonRelease-1>",
                         lambda e: self.after_idle(self._desenhar_grupos),
                         add="+")
        self.tv.grid(row=1, column=0, sticky="nsew")
        sy.grid(row=1, column=1, sticky="ns")
        sx.grid(row=2, column=0, sticky="ew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._linhas = []
        self._total = None
        self._ordem = {}
        self._por_item = {}
        self.ao_duplo_clique = None     # funcao(linha) - so nas editaveis
        self.tv.tag_configure("editado", background=AZUL_CLARO,
                              font=fonte(self._tam, "bold"))
        self.tv.bind("<Double-1>", self._duplo)

    def _fmt(self, v, tipo) -> str:
        """Na tabela COMPACTA o R$ sai de cada valor (cabe mais na tela)."""
        txt = formatar(v, tipo)
        if getattr(self, "_compacta0", self.compacta) and \
                tipo in ("moeda", "moeda2"):
            txt = txt.replace("R$ ", "")
        return txt

    def _titulo(self, col) -> str:
        return (col.get("curto") or col["nome"]) if self.grupos else col["nome"]

    def _rolou_x(self, a, b):
        self._sx.set(a, b)
        self._so_se_rola(self._sx, a, b)
        self._desenhar_grupos()
        self._pintar_depois()

    def _rolou_y(self, a, b):
        self._sy.set(a, b)
        self._so_se_rola(self._sy, a, b)
        self._pintar_depois()

    def _so_se_rola(self, barra, a, b):
        """(04/11) CABE: a barra some quando tudo ja aparece."""
        if not getattr(self, "cabe", False):
            return
        try:
            tudo = float(a) <= 0.0 and float(b) >= 1.0
            if tudo and barra.winfo_ismapped():
                barra.grid_remove()
            elif not tudo and not barra.winfo_ismapped():
                barra.grid()
        except (tk.TclError, ValueError):
            pass

    def _letra(self, tam):
        """(04/11) troca a letra da tabela compacta (CABE)."""
        self._tam, self._tam_cab = tam, tam - 1
        estilo = f"Compacta{tam}.Treeview"
        st = ttk.Style(self)
        st.configure(estilo, rowheight=altura_da_linha(
            fonte(tam), 8, tam * 2 + 8), font=fonte(tam))
        st.configure(f"{estilo}.Heading", font=fonte(tam - 1, "bold"),
                     padding=(2, 5), background="#E4E7E5",
                     foreground="#2E3330")
        self.tv.configure(style=estilo)
        self.tv.tag_configure("total", font=fonte(tam, "bold"))
        self.tv.tag_configure("editado", font=fonte(tam, "bold"))
        self._medir()

    def _minimo(self):
        """A menor largura em que a tabela aparece sem cortar numero."""
        soma = 0
        for j, c in enumerate(self.colunas):
            if j not in self._visiveis:
                continue
            if c.get("tipo", "texto") == "texto":
                m_ = (max(self._cab[j], min(self._cont[j], 640))
                      if c.get("inteira") else
                      max(min(self._cab[j], 90), min(self._cont[j], 96), 50))
            else:
                m_ = max(self._cab[j], self._cont[j])
            soma += max(m_, c.get("larg_fixa") or 0)
        return soma

    def _voltar_letra(self):
        """(04/11) a letra e o estilo com que a tabela nasceu."""
        if self._compacta0:
            self._letra(self._tam0)
            return
        self.compacta = False
        self._tam, self._tam_cab = self._tam0, self._tam0 - 1
        self.tv.configure(style="Treeview")
        self.tv.tag_configure("total", font=fonte(self._tam, "bold"))
        self.tv.tag_configure("editado", font=fonte(self._tam, "bold"))
        self._medir()

    def _ideal(self):
        """(04/11) a largura em que tudo aparece INTEIRO (texto ate a
        largura pedida da coluna, numero sem cortar)."""
        soma = 0
        for j, c in enumerate(self.colunas):
            if j not in self._visiveis:
                continue
            if c.get("tipo", "texto") == "texto":
                teto = 640 if c.get("inteira") else max(
                    c.get("largura", 110), self._cab[j])
                m_ = max(self._cab[j], min(self._cont[j] + 16, teto + 16))
            else:
                m_ = max(self._cab[j], self._cont[j])
            soma += max(m_, c.get("larg_fixa") or 0)
        return soma

    def _letra_que_cabe(self, disp):
        """(04/11) a letra em que a tabela cabe na largura: 1o a maior em
        que tudo aparece inteiro (ate 7); se nenhuma, a maior em que cabe
        sem cortar numero; a tabela de letra normal (10) so passa a
        compacta se precisar."""
        if self._tam != self._tam0 or self.compacta != self._compacta0:
            self._voltar_letra()
        if self._ideal() <= disp:
            return
        tentativas = ([t_ for t_ in (9, 8, 7) if t_ < self._tam0]
                      if self._compacta0 else [9, 8, 7])
        for medida in (self._ideal, self._minimo):
            if medida is self._minimo:
                self._voltar_letra()
                if medida() <= disp:
                    return
            for tam in tentativas:
                self.compacta = True
                self._letra(tam)
                if medida() <= disp:
                    return
        if self._cabe_auto:
            self._voltar_letra()        # nem com a 7: fica como era

    # ------------------------------------------------ celulas desenhadas
    def _pintar_depois(self):
        if not getattr(self, "_desenhadas", None):
            return
        if self._agendado:
            return
        self._agendado = self.after(15, self._pintar)

    @staticmethod
    def _faixa_de(v, faixas):
        """(fundo, texto) da 1a faixa (ate, fundo, texto) que cabe o v."""
        for ate, fundo, txt in faixas:
            if ate is None or v <= ate:
                return fundo, txt
        return faixas[-1][1], faixas[-1][2]

    def _pintar(self):
        self._agendado = None
        try:
            itens = self.tv.get_children()
            sel = set(self.tv.selection())
        except tk.TclError:
            return
        alvos = []
        for item in itens:
            linha = self._por_item.get(item)
            if linha is None:
                continue
            for j in self._desenhadas:
                if j not in self._visiveis:
                    continue
                try:
                    bb = self.tv.bbox(item, f"c{j}")
                except tk.TclError:
                    bb = None
                if bb:
                    alvos.append((item, j, bb, linha))
        while len(self._pool) < len(alvos):
            cv = tk.Canvas(self.tv, highlightthickness=0, borderwidth=0)
            cv.bind("<Button-1>", lambda e, c=cv: self._clicou(c, e, False))
            cv.bind("<Double-1>", lambda e, c=cv: self._clicou(c, e, True))
            cv.bind("<MouseWheel>", lambda e: self.tv.yview_scroll(
                -1 if e.delta > 0 else 1, "units"))
            cv.bind("<Button-4>", lambda e: self.tv.yview_scroll(-1, "units"))
            cv.bind("<Button-5>", lambda e: self.tv.yview_scroll(1, "units"))
            self._pool.append(cv)
        for cv in self._pool[len(alvos):]:
            cv.place_forget()
        for cv, (item, j, (x, y, w, h), linha) in zip(self._pool, alvos):
            c = self.colunas[j]
            v = linha[j] if j < len(linha) else None
            tags = self.tv.item(item, "tags")
            fundo = "#DCEFD4" if item in sel else (
                ZEBRA_CLARA if "zebra" in tags else next(
                    (FUNDOS[t] for t in tags if t in FUNDOS), CARTAO))
            cv._item = item
            cv.delete("all")
            cv.configure(background=fundo, width=w, height=h)
            cv.place(x=x, y=y, width=w, height=h)
            if v is None or v == "":
                continue
            txt = self._fmt(v, c.get("tipo", "texto"))
            f_ = fonte(self._tam + 1, "bold")
            if c.get("chip_tom") is not None:
                # (22/10) selo pela LINHA: a coluna oculta chip_tom diz o
                # tom (ok verde / atencao amarelo / alerta vermelho) - o SLA
                # do Farol de Entregas pintado pelo prazo
                t_ = linha[c["chip_tom"]] if c["chip_tom"] < len(linha) \
                    else ""
                cores = {"ok": ("#F0F7EC", "#2F7D32"),
                         "atencao": ("#FFF4D6", "#8A5A00"),
                         "alerta": ("#FDECEA", "#B42318"),
                         # (06/11) o SLA que parou de contar (fechada)
                         "cinza": ("#E3E8E4", "#5E6B63")}.get(t_)
                if not cores:
                    cv.create_text(w - 8, h / 2, text=txt, anchor="e",
                                   fill=TEXTO, font=fonte(self._tam))
                    continue
                cor_f, cor_t = cores
                lw = min(w - 8, max(34, len(txt) * self._tam + 18))
                x1 = w - 4
                cv.create_rectangle(x1 - lw, 2, x1, h - 2, outline="",
                                    fill=cor_f)
                cv.create_text(x1 - lw / 2, h / 2, text=txt, fill=cor_t,
                               font=fonte(max(7, self._tam - 1), "bold"))
            elif isinstance(c.get("chip"), dict):
                # (14/10) chip por TEXTO (ex.: ATRASADA vermelho, NO PRAZO
                # verde); valor fora do mapa: texto normal, sem selo
                # (06/11) chip_chave: a cor vem de outra coluna da linha
                # (o PRAZO "FECHADA" pela SITUACAO DO PRAZO)
                k_ = c.get("chip_chave")
                chave_ = (linha[k_] if k_ is not None and k_ < len(linha)
                          else v)
                cores = c["chip"].get(str(chave_).strip().upper())
                if not cores:
                    cv.create_text(6, h / 2, text=txt, anchor="w",
                                   fill=TEXTO, font=fonte(self._tam))
                    continue
                cor_f, cor_t = cores
                lw = min(w - 8, max(40, len(txt) * self._tam + 18))
                x0 = 4
                cv.create_rectangle(x0, 2, x0 + lw, h - 2, outline="",
                                    fill=cor_f)
                cv.create_text(x0 + lw / 2, h / 2, text=txt, fill=cor_t,
                               font=fonte(max(7, self._tam - 1), "bold"))
            elif c.get("chip"):
                cor_f, cor_t = self._faixa_de(v, c["chip"])
                if cor_f is None:       # (16/10) faixa sem cor: so o numero
                    num = c.get("tipo", "texto") not in ("texto", "data",
                                                         "dia")
                    cv.create_text(w - 8 if num else 6, h / 2, text=txt,
                                   anchor="e" if num else "w", fill=TEXTO,
                                   font=fonte(self._tam))
                    continue
                num = c.get("tipo", "texto") not in ("texto", "data", "dia")
                if num and any(fx[1] is None for fx in c["chip"]):
                    # (16/10) coluna de numero com SO PARTE pintada (EST. e
                    # COB do Giro): o selo encosta a direita, alinhado com
                    # os numeros sem cor da mesma coluna
                    from tkinter import font as _tkf     # noqa: PLC0415
                    lw = min(w - 6, _tkf.Font(font=f_).measure(txt) + 14)
                    x1 = w - 1
                    cv.create_rectangle(x1 - lw, 2, x1, h - 2, outline="",
                                        fill=cor_f)
                    cv.create_text(w - 8, h / 2, text=txt, anchor="e",
                                   fill=cor_t, font=f_)
                    continue
                lw = min(w - 8, max(40, len(txt) * self._tam + 22))
                x0 = (w - lw) / 2
                cv.create_rectangle(x0, 2, x0 + lw, h - 2, outline="",
                                    fill=cor_f)
                cv.create_text(w / 2, h / 2, text=txt, fill=cor_t, font=f_)
            else:
                b = c["barra"]
                cor_b, cor_t = self._faixa_de(v, b["faixas"])
                mx = float(b.get("max") or 100)
                tw = 56 if self._tam >= 10 else 50
                bw = max(10, w - tw - 12)
                cv.create_rectangle(6, h / 2 - 5, 6 + bw, h / 2 + 5,
                                    outline="", fill="#ECEFEB")
                fr = max(0.0, min(1.0, float(v) / mx))
                if fr > 0:
                    cv.create_rectangle(6, h / 2 - 5, 6 + max(2, bw * fr),
                                        h / 2 + 5, outline="", fill=cor_b)
                cv.create_text(w - 4, h / 2, text=txt, anchor="e",
                               fill=cor_t, font=f_)

    def _clicou(self, cv, e, duplo):
        item = getattr(cv, "_item", None)
        if not item:
            return
        try:
            self.tv.selection_set(item)
            self.tv.focus(item)
            self.tv.focus_set()
        except tk.TclError:
            return
        if duplo and self.ao_duplo_clique and item in self._por_item:
            self.ao_duplo_clique(self._por_item[item])

    def _desenhar_grupos(self):
        """A faixa dos grupos, alinhada com as colunas (e com a rolagem)."""
        cv = self.faixa
        if cv is None:
            return
        try:
            cv.delete("all")
            larg = [int(self.tv.column(f"c{j}", "width"))
                    if j in self._visiveis else 0
                    for j in range(len(self.colunas))]
            total = sum(larg) or 1
            x0 = -float(self.tv.xview()[0]) * total
        except tk.TclError:
            return
        j = 0
        for rot, n in self.grupos:
            w = sum(larg[j:j + n])
            if rot and w:
                cv.create_rectangle(x0 + 1, 2, x0 + w - 1, 22, outline="",
                                    fill="#4A4F4C")
                cv.create_text(x0 + w / 2, 12, text=rot,
                               fill="#FFFFFF",
                               font=fonte(self._tam_cab if self.compacta
                                          else 9, "bold"))
            x0 += w
            j += n

    def _medir(self):
        """Largura que cada coluna precisa: o titulo inteiro e o conteudo
        (numero e data nunca cortam; texto pode encolher e cortar)."""
        from tkinter import font as tkfont              # noqa: PLC0415
        try:
            f_cab = tkfont.Font(font=fonte(self._tam - 1 if not self.compacta
                                           else self._tam_cab, "bold"))
            f_cel = tkfont.Font(font=fonte(self._tam))
        except tk.TclError:
            return
        amostra = [l for l, _ in self._linhas[:400]]
        try:
            f_tot = tkfont.Font(font=fonte(self._tam, "bold"))
        except tk.TclError:
            f_tot = f_cel
        self._cab, self._cont = [], []
        for j, c in enumerate(self.colunas):
            tipo = c.get("tipo", "texto")
            self._cab.append(f_cab.measure(self._titulo(c))
                             + (12 if self.compacta else 22))
            vals = {self._fmt(l[j], tipo) for l in amostra if j < len(l)}
            tot_txt = (self._fmt(self._total[j], tipo)
                       if self._total and j < len(self._total) else "")
            # mede so os mais compridos: medir texto e caro (no Windows,
            # cada measure vai ao sistema) e o mais largo esta entre eles
            corte = 90 if c.get("inteira") else 40      # (16/10)
            vals = sorted({v[:corte] for v in vals}, key=len,
                          reverse=True)[:6]
            maior = max([f_cel.measure(v) for v in vals]
                        + [f_tot.measure(tot_txt[:40])], default=0)
            self._cont.append(maior + (10 if self.compacta else 18))

    def _caber(self, _e=None, forcar=False):
        """As colunas cabem na largura da tela: sobra vai para o texto; se
        faltar, o texto encolhe e o resto rola de lado."""
        disp = self.tv.winfo_width() - 4
        if disp < 200 or (not forcar and abs(disp - self._ultima_largura) < 4):
            return
        self._ultima_largura = disp
        if not getattr(self, "_cab", None):
            self._medir()
        if not getattr(self, "_cab", None):
            return
        if getattr(self, "cabe", False):
            self._letra_que_cabe(disp)
        txt = [j for j, c in enumerate(self.colunas)
               if c.get("tipo", "texto") == "texto" and j in self._visiveis]
        # o ideal: titulo e conteudo inteiros (texto ate a largura pedida)
        novas = []
        minimo = []
        for j, c in enumerate(self.colunas):
            if j not in self._visiveis:
                novas.append(0)
                minimo.append(0)
            elif j in txt and c.get("inteira"):
                # (16/10) "inteira" (codigo e descricao do Giro): o texto
                # aparece inteiro e nao encolhe - quem encolhe e o resto
                ideal = max(self._cab[j], min(self._cont[j], 640))
                novas.append(ideal)
                minimo.append(ideal)
            elif j in txt:
                ideal = max(self._cab[j], min(self._cont[j],
                                              max(c.get("largura", 110),
                                                  self._cab[j])))
                novas.append(ideal)
                minimo.append(max(min(self._cab[j], 90),
                                  min(self._cont[j], 96), 50))
            else:
                novas.append(max(self._cab[j], self._cont[j]))
                minimo.append(novas[-1])
        # (14/10) a larg_fixa entra JA na conta (antes so no fim: a sobra ia
        # para as datas e a coluna fixa do fim passava da tela)
        for j, c in enumerate(self.colunas):
            if c.get("larg_fixa") and j in self._visiveis:
                novas[j] = max(novas[j], c["larg_fixa"])
                minimo[j] = max(minimo[j], c["larg_fixa"])
        total = sum(novas)
        if total < disp and txt:
            # a sobra vai para o texto largo (a UF, "fixa", fica estreita);
            # COMPACTA: o texto fica do tamanho do que tem e a sobra se
            # reparte entre as colunas de numero (mais ar, nada espremido)
            larg_ = [j for j in txt if not self.colunas[j].get("fixa")] or txt
            if self.compacta:
                for j in txt:              # o texto: o conteudo (+ folga)
                    novas[j] = max(self._cab[j], min(self._cont[j] + 16,
                                                     novas[j]),
                                   self.colunas[j].get("larg_fixa") or 0)
                total = sum(novas)
                # (14/10) antes das datas, o texto cortado (CLIENTE) ganha
                # o que falta para aparecer inteiro, se couber
                falta = {j: self._cont[j] + 16 - novas[j] for j in txt
                         if self._cont[j] + 16 > novas[j]}
                if falta and total < disp:
                    f_ = min(1.0, (disp - total) / sum(falta.values()))
                    for j, v in falta.items():
                        novas[j] += v * f_
                    total = sum(novas)
                nums = [j for j in self._visiveis if j not in txt]
                larg_ = nums or larg_
            extra = (disp - total) / len(larg_)
            for j in larg_:
                novas[j] += extra
        elif total > disp:
            folga = sum(novas[j] - minimo[j] for j in txt)
            corta = min(total - disp, folga)
            for j in txt:
                if folga:
                    novas[j] -= corta * (novas[j] - minimo[j]) / folga
        # (08/10) "larg_fixa": a coluna fica SEMPRE com essa largura (SLA e
        # % ATENDIDO no Farol de Pedidos - o controle da assistente)
        for j, c in enumerate(self.colunas):
            if c.get("larg_fixa") and j in self._visiveis:
                novas[j] = max(novas[j], c["larg_fixa"])
        if getattr(self, "cabe", False) and not self._cabe_auto and \
                sum(novas) > disp:
            # nem com a letra 7: todas encolhem por igual (tela estreita)
            f_ = disp / sum(novas)
            novas = [w * f_ for w in novas]
        if getattr(self, "cabe", False):
            # arredonda somando (o int() de cada coluna deixava uma sobra
            # branca a direita)
            acum, feito = 0.0, 0
            for j, w in enumerate(novas):
                acum += w
                novas[j] = round(acum) - feito
                feito += novas[j]
        for j, w in enumerate(novas):
            self.tv.column(f"c{j}", width=int(w))
        self.after_idle(self._desenhar_grupos)
        self._pintar_depois()

    def _duplo(self, evento):
        item = self.tv.identify_row(evento.y)
        if not item or item not in self._por_item or not self.ao_duplo_clique:
            return "break"
        # (13/10) a coluna do duplo clique (ex.: so a AUTORIZACAO edita; o
        # resto da linha abre o pedido)
        try:
            n = int(self.tv.identify_column(evento.x)[1:]) - 1
            disp = list(self.tv["displaycolumns"])
            self.coluna_clicada = (int(str(disp[n])[1:])
                                   if 0 <= n < len(disp) else None)
        except (ValueError, IndexError, tk.TclError):
            self.coluna_clicada = None
        self.ao_duplo_clique(self._por_item[item])
        return "break"

    def mostrar(self, linhas: list, tons: list | None = None,
                total: list | None = None) -> None:
        self._linhas = list(zip(linhas, tons or [""] * len(linhas)))
        self._total = total
        self._desenhar()
        if not getattr(self, "_cab", None):      # mede uma vez, com os dados
            self._medir()
            self._caber(forcar=True)

    def _desenhar(self):
        self.tv.delete(*self.tv.get_children())
        self._por_item = {}
        for n, (linha, tom) in enumerate(self._linhas):
            vals = [self._fmt(v, c.get("tipo", "texto"))
                    for v, c in zip(linha, self.colunas)]
            if self.zebra and tom != "grave":     # (13/10) o grave fica
                tom = "zebra" if n % 2 else ""
            item = self.tv.insert("", "end", values=vals,
                                  tags=(tom,) if tom else ())
            self._por_item[item] = linha
        if self._total:
            vals = [self._fmt(v, c.get("tipo", "texto"))
                    for v, c in zip(self._total, self.colunas)]
            self.tv.insert("", "end", values=vals, tags=("total",))
        self._pintar_depois()

    def ordenar(self, cid):
        i = int(cid[1:])
        desc = not self._ordem.get(i, False)
        self._ordem = {i: desc}

        def chave(item):
            v = item[0][i] if i < len(item[0]) else None
            if v is None or v == "":
                return (1, 0)
            if isinstance(v, (int, float)):
                return (0, v)
            if isinstance(v, (date, datetime)):
                return (0, v.toordinal())
            return (0, str(v).upper())
        try:
            self._linhas.sort(key=chave, reverse=desc)
        except TypeError:
            self._linhas.sort(key=lambda x: str(x[0][i]), reverse=desc)
        self._desenhar()


def escolher_periodo_rota(pai, titulo="Exportar JSON da roteirização"):
    """(26/10, Alexandre) Ao exportar o .json da rota: o MES INTEIRO ou SO A
    PARTIR DE HOJE. Devolve "mes", "hoje" ou None (cancelou)."""
    hoje = date.today()
    escolha = {"v": None}
    j = tk.Toplevel(pai)
    j.title(titulo)
    j.configure(background=FUNDO)
    j.resizable(False, False)
    try:
        j.transient(pai.winfo_toplevel())
    except tk.TclError:
        pass
    corpo = tk.Frame(j, background=FUNDO, padx=24, pady=18)
    corpo.pack(fill="both", expand=True)
    tk.Label(corpo, text="Quais visitas vão no arquivo?", background=FUNDO,
             foreground=TEXTO, font=fonte(12, "bold"),
             anchor="w").pack(anchor="w")
    tk.Label(corpo, text=f"Hoje é {hoje:%d/%m}. Os dias que já passaram só "
             f"vão no mês inteiro.", background=FUNDO, foreground=SUAVE,
             font=fonte(9), anchor="w").pack(anchor="w", pady=(4, 14))
    botoes = tk.Frame(corpo, background=FUNDO)
    botoes.pack(fill="x")

    def fim(v):
        escolha["v"] = v
        j.destroy()
    for texto, v, cor in (("MÊS INTEIRO", "mes", VERDE),
                          (f"A PARTIR DE HOJE ({hoje:%d/%m})", "hoje",
                           VERDE_ESCURO)):
        tk.Button(botoes, text=texto, command=lambda v_=v: fim(v_),
                  background=cor, foreground="white", activebackground=cor,
                  activeforeground="white", relief="flat", padx=16, pady=8,
                  font=fonte(10, "bold"), cursor="hand2").pack(
                      side="left", padx=(0, 10))
    tk.Button(botoes, text="Cancelar", command=j.destroy, relief="flat",
              background=FUNDO, foreground=SUAVE, font=fonte(9),
              cursor="hand2").pack(side="right")
    j.bind("<Escape>", lambda e: j.destroy())
    j.update_idletasks()
    try:
        x = pai.winfo_rootx() + (pai.winfo_width() - j.winfo_width()) // 2
        y = pai.winfo_rooty() + 120
        j.geometry(f"+{max(0, x)}+{max(0, y)}")
        j.grab_set()
    except tk.TclError:
        pass
    pai.wait_window(j)
    return escolha["v"]


def lista_larga(cb, maximo=560):
    """(15/10, Alexandre) A LISTA que abre no combobox fica da largura do
    maior nome (vendedor, supervisor, produto) - a caixa continua do
    mesmo tamanho na barra. O ttk abre a lista com a largura da caixa;
    o -postoffset do estilo da caixa soma o que falta."""
    def antes():
        try:
            from tkinter import font as tkf             # noqa: PLC0415
            f_ = tkf.Font(font=fonte(10))
            maior = max((f_.measure(str(v)) for v in cb.cget("values")),
                        default=0) + 40
            extra = max(0, min(maior, maximo) - cb.winfo_width())
            extra = int(extra // 20 * 20 + (20 if extra % 20 else 0))
            nome = f"Lista{extra}.TCombobox"
            ttk.Style().configure(nome, postoffset=(0, 0, extra, 0))
            if str(cb.cget("style")) != nome:
                cb.configure(style=nome)
        except Exception:                               # noqa: BLE001
            pass
    try:
        cb.configure(postcommand=antes)
    except Exception:                                   # noqa: BLE001
        pass
    return cb


class GraficoBarras(tk.Canvas if tk else object):
    """
    Colunas finas (ate 24 px, ponta arredondada), grade de 1 px bem clara,
    legenda so com 2+ series, rotulo no topo da coluna so quando cabe.
    series: [{"nome","valores","cor"}]; formato: "pct", "moeda" ou "num".
    """

    MAX_BARRA = 24
    RAIO = 4

    def __init__(self, pai, titulo, rotulos, series, formato="num",
                 altura=250, meta=None, subrotulos=None, rotular=False,
                 linha=None, rotulo_meta="meta", linhas=False):
        # (15/10) linhas=True: as series viram LINHAS no mesmo eixo (o
        # Farol de Preco: preco x volume em indice)
        self.modo_linhas = linhas
        super().__init__(pai, background=CARTAO, height=altura,
                         highlightthickness=1, highlightbackground=CINZA_LINHA)
        self.titulo, self.rotulos, self.series = titulo, rotulos, series
        self.formato, self.meta = formato, meta
        # rotular: o numero em cima de TODA coluna (positivacao e gap...)
        self.rotular = rotular
        # linha: {"nome", "valores"} em % (a faixa de cima: % MoM...)
        self.linha = linha
        self.rotulo_meta = rotulo_meta
        # um texto pequeno embaixo de cada coluna (ex.: "4,2 SKU/NF")
        self.subrotulos = subrotulos
        self.bind("<Configure>", lambda e: self.desenhar())

    def _fmt(self, v):
        if self.formato == "pct":
            return pct(v)
        if self.formato == "moeda":
            return ("-R$ " if (v or 0) < 0 else "R$ ") + _compacto(abs(v or 0))
        if self.formato == "hora":           # segundos do dia -> 09:48
            s_ = int(round(v or 0))
            return f"{s_ // 3600:02d}:{s_ % 3600 // 60:02d}"
        if self.formato == "min":            # segundos -> 25 min (TMA/TMD)
            return f"{br((v or 0) / 60.0, 0)} min"
        if self.formato == "num1":           # (26/10) IPP: 3,7
            return br(v or 0, 1)
        return _compacto(v)

    def _coluna(self, x0, x1, y, base, cor):
        """Coluna com a ponta de cima arredondada e a base reta."""
        r = min(self.RAIO, (x1 - x0) / 2, max(base - y, 0) / 2)
        if base - y < 1:
            return
        if r < 1.5:
            self.create_rectangle(x0, y, x1, base, fill=cor, outline="")
            return
        self.create_rectangle(x0, y + r, x1, base, fill=cor, outline="")
        self.create_rectangle(x0 + r, y, x1 - r, y + r, fill=cor, outline="")
        for cx in (x0, x1 - 2 * r):
            self.create_oval(cx, y, cx + 2 * r, y + 2 * r, fill=cor, outline="")

    def desenhar(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 300), max(self.winfo_height(), 120)
        from tkinter import font as tkfont              # noqa: PLC0415
        # u: a escala da tela (Windows 125%/150%) - as distancias crescem
        # junto com a letra
        u = max(1.0, tkfont.Font(font=fonte(8)).metrics("linespace") / 14.0)
        self._u = u
        self.create_text(16, 18 * u, text=self.titulo, anchor="w",
                         font=fonte(11, "bold"), fill=TEXTO)
        topo = (54 if h >= 200 else 42) * u
        if len(self.series) > 1:                     # legenda: so com 2+
            fim_titulo = self.bbox("all")[2] + 24
            ids = []
            x = w - 16
            for s in reversed(self.series):
                tx = self.create_text(x, 18 * u, text=s["nome"], anchor="e",
                                      font=fonte(9), fill=SUAVE)
                x0 = self.bbox(tx)[0]
                ids += [tx, self.create_rectangle(
                    x0 - 14, 18 * u - 4, x0 - 6, 18 * u + 4,
                    fill=s.get("cor", VERDE), outline="")]
                x = x0 - 24
            if x < fim_titulo:                       # nao cabe: desce
                for i in ids:
                    self.move(i, 0, 20 * u)
                topo = 70 * u
        n = len(self.rotulos)
        if not n:
            self.create_text(w / 2, h / 2, text="Sem dados no período",
                             fill=SUAVE, font=fonte(10))
            return
        # A LINHA (% MoM, markup %): numa faixa propria em cima das colunas -
        # escala dela, sem misturar com o eixo das colunas
        faixa = None
        if self.linha and any(v is not None for v in self.linha["valores"]):
            faixa = (topo, topo + 46 * u)
            topo += 60 * u
        valores = [v or 0 for s in self.series for v in s["valores"]]
        maximo = max(valores + [self.meta or 0, 0])
        minimo = min(valores + [0])
        if self.modo_linhas:            # a linha nao precisa partir do zero
            ok_ = [v for s in self.series for v in s["valores"]
                   if v is not None] or [0]
            maximo, minimo = max(ok_ + [self.meta or max(ok_)]), min(ok_)
            folga_ = (maximo - minimo) * 0.08 or 1
            maximo, minimo = maximo + folga_, max(0, minimo - folga_)
        n_sub = max((str(x).count("\n") + 1 for x in self.subrotulos or []),
                    default=0)
        fundo = h - 30 * u - 13 * u * n_sub
        esq, dir_ = 60, 16
        # grade: linhas de 1 px em numeros redondos; o zero mais forte
        import math                                     # noqa: PLC0415
        passo = _passo_redondo(((maximo - minimo) or 1) / 3)
        if self.formato == "hora":           # a grade em horas cheias
            passo = 3600 * max(1, math.ceil(((maximo - minimo) or 1)
                                            / 3 / 3600))
        elif self.formato == "min":          # a grade em 5/10/15... min
            passo = 300 * max(1, math.ceil(((maximo - minimo) or 1)
                                           / 3 / 300))
        maximo = passo * math.ceil(maximo / passo - 1e-9)
        minimo = passo * math.floor(minimo / passo + 1e-9)
        if maximo == minimo:
            maximo = minimo + passo

        from tkinter import font as tkfont              # noqa: PLC0415
        f7 = tkfont.Font(font=fonte(8))
        esq = 16 + max(f7.measure(self._fmt(minimo)),
                       f7.measure(self._fmt(maximo)))
        if self.modo_linhas and any(s_.get("rotulos") for s_ in self.series):
            esq = 40                    # sem numero no eixo: so a folga

        def y_de(v):
            return fundo - (fundo - topo) * (v - minimo) / (maximo - minimo)
        base = y_de(0)
        k = minimo
        faixado = self.modo_linhas and any(s_.get("rotulos")
                                           for s_ in self.series)
        while k <= maximo + 1e-9:
            y = y_de(k)
            if faixado:              # linhas em faixas: sem grade de eixo
                k += passo
                continue
            self.create_line(esq, y, w - dir_, y,
                             fill=CINZA_LINHA if abs(k) < 1e-9 else GRADE)
            if not (self.modo_linhas and any(
                    s_.get("rotulos") for s_ in self.series)):
                self.create_text(esq - 8, y, text=self._fmt(k), anchor="e",
                                 font=fonte(8), fill=SUAVE)
            k += passo
        larg = (w - esq - dir_) / n
        ns = len(self.series)
        barra = max(3, min(self.MAX_BARRA, (larg * 0.62 - 2 * (ns - 1)) / ns))
        rotula = (ns == 1 and n <= 16) or (ns == 2 and n <= 8) or (
            self.rotular and larg / max(ns, 1) >= 16)
        if self.rotular == "nao":       # (06/10) R$ em 12 colunas: encavala
            rotula = False
        if self.meta:
            y = y_de(self.meta)
            self.create_line(esq, y, w - dir_, y, fill=SUAVE, dash=(2, 3))
            self.create_text(esq + 4, y - 7, text=self.rotulo_meta
                             if self.rotulo_meta != "meta" else
                             f"teto {self._fmt(self.meta)}"
                             if self.formato == "pct" else self.rotulo_meta,
                             anchor="w",
                             font=fonte(7), fill=SUAVE)
        grupo = barra * ns + 2 * (ns - 1)
        if faixa:
            self._desenhar_linha(faixa, esq, w - dir_, larg)
        if self.modo_linhas:
            self._fundo_linhas = fundo
            self._max_linhas = maximo
            self._desenhar_series_linha(esq, larg, y_de, n, u)
        for i, rot in enumerate(self.rotulos):
            cx = esq + larg * i + larg / 2
            for j, s in enumerate(self.series):
                if self.modo_linhas:
                    break
                v = s["valores"][i] or 0
                x0 = cx - grupo / 2 + (barra + 2) * j
                y = y_de(v)
                cor = s.get("cor", VERDE)
                if s.get("cores") and i < len(s["cores"]):
                    cor = s["cores"][i] or cor
                if v < 0 and s.get("cor_negativo", VERMELHO):
                    cor = s.get("cor_negativo", VERMELHO)
                if v >= 0:
                    self._coluna(x0, x0 + barra, y, base, cor)
                else:
                    self._coluna_baixo(x0, x0 + barra, base, y, cor)
                if rotula and (v or self.rotular is True):
                    self.create_text(x0 + barra / 2,
                                     y - 8 * u if v >= 0 else y + 8 * u,
                                     text=self._fmt(v), font=fonte(8),
                                     fill=TEXTO)
            cabe = max(3, int(larg / 6.2))
            txt = str(rot)
            f8 = tkfont.Font(font=fonte(9))
            while len(txt) > 2 and f8.measure(txt) > larg - 4:
                txt = txt[:-2] + "…"
            self.create_text(cx, fundo + 13 * u, text=txt, font=fonte(9),
                             fill=SUAVE)
            if self.subrotulos and i < len(self.subrotulos):
                sub = "\n".join(
                    x if len(x) <= cabe + 2 else x[:cabe + 1] + "…"
                    for x in str(self.subrotulos[i] or "").split("\n"))
                self.create_text(cx, fundo + 23 * u, text=sub, font=fonte(8),
                                 fill=VERDE_ESCURO, anchor="n",
                                 justify="center")

    def _desenhar_series_linha(self, esq, larg, y_de, n, u):
        """(15/10) Cada serie uma linha de 2 px com ponto de 8 px (anel
        branco); o numero em cima (1a serie) ou embaixo (2a) do ponto.
        Series com "rotulos" (o valor de verdade: R$, unidades): cada uma
        na SUA FAIXA (preco em cima, volume embaixo), na escala dela - as
        linhas nao se cruzam e os numeros nao encavalam."""
        faixas = None
        if any(s_.get("rotulos") for s_ in self.series):
            topo_ = y_de(self._max_linhas) + 16 * u
            fundo_ = getattr(self, "_fundo_linhas", topo_ + 100) - 6 * u
            ns_ = len(self.series)
            alt_ = (fundo_ - topo_) / ns_
            faixas = []
            for j, s_ in enumerate(self.series):
                ok_ = [v for v in s_["valores"] if v is not None] or [0]
                lo_, hi_ = min(ok_), max(ok_)
                if hi_ - lo_ < 1e-9:
                    lo_, hi_ = lo_ - 1, hi_ + 1
                y0_ = topo_ + alt_ * j + 14 * u
                y1_ = topo_ + alt_ * (j + 1) - 4 * u
                faixas.append((lo_, hi_, y0_, y1_))
                if j:
                    yl_ = topo_ + alt_ * j
                    self.create_line(esq, yl_, esq + larg * n, yl_,
                                     fill=GRADE, dash=(2, 3))
        for j, s in enumerate(self.series):
            cor = s.get("cor", VERDE)
            if faixas:
                lo_, hi_, y0_, y1_ = faixas[j]
                y_de = (lambda v, lo_=lo_, hi_=hi_, y0_=y0_, y1_=y1_:
                        y1_ - (y1_ - y0_) * (v - lo_) / (hi_ - lo_))
            pts = [(esq + larg * i + larg / 2, y_de(v)) if v is not None
                   else None for i, v in enumerate(s["valores"][:n])]
            for a, b in zip(pts, pts[1:]):
                if a and b:
                    self.create_line(*a, *b, fill=cor, width=2)
            rot_ = s.get("rotulos") or []
            for i_, (v, pt) in enumerate(zip(s["valores"], pts)):
                if not pt:
                    continue
                cx, cy = pt
                self.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=cor,
                                 outline=CARTAO, width=2)
                if n <= 14:
                    dy = -11 * u if (j % 2 == 0 or faixas) else 12 * u
                    # perto do eixo de baixo o numero sobe (nao encavala
                    # no rotulo do mes)
                    if cy + dy > getattr(self, "_fundo_linhas", 1e9) - 8 * u:
                        dy = -11 * u
                    self.create_text(cx, cy + dy, text=rot_[i_]
                                     if i_ < len(rot_) else self._fmt(v),
                                     font=fonte(8, "bold"), fill=cor)

    def _desenhar_linha(self, faixa, x0, x1, larg):
        """A faixa da linha: pontos ligados, o % em cima de cada ponto
        (negativo em vermelho) e o zero tracejado."""
        y0, y1 = faixa
        vals = self.linha["valores"]
        ok = [v for v in vals if v is not None]
        lo, hi = min(ok + [0.0]), max(ok + [0.0])
        if hi - lo < 1e-9:
            hi = lo + 1

        def y_de(v):
            return y1 - (y1 - y0 - 14) * (v - lo) / (hi - lo)
        self.create_rectangle(x0, y0 - 4, x1, y1 + 6, fill="#FAFBF9",
                              outline="")
        u = getattr(self, "_u", 1.0)
        self.create_text(x0 + 4, y0 + 2, text=self.linha.get("nome", ""),
                         anchor="nw", font=fonte(8), fill=SUAVE)
        if lo < 0 < hi:
            yz = y_de(0)
            self.create_line(x0, yz, x1, yz, fill=CINZA_LINHA, dash=(2, 3))
        pts = []
        for i, v in enumerate(vals):
            if v is None:
                pts.append(None)
                continue
            pts.append((x0 + larg * i + larg / 2, y_de(v)))
        for a, b in zip(pts, pts[1:]):
            if a and b:
                self.create_line(*a, *b, fill="#4A4F4C", width=2)
        for v, pt in zip(vals, pts):
            if not pt:
                continue
            cx, cy = pt
            self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=CARTAO,
                             outline="#4A4F4C", width=2)
            txt = (("+" if v > 0 else "") + pct(v)) if "MoM" in \
                self.linha.get("nome", "") else pct(v, 1)
            self.create_text(cx, cy - 10 * u, text=txt, font=fonte(8),
                             fill=VERMELHO if v < 0 else TEXTO)

    def _coluna_baixo(self, x0, x1, base, y, cor):
        """Coluna negativa: base reta no zero, ponta arredondada embaixo."""
        r = min(self.RAIO, (x1 - x0) / 2, max(y - base, 0) / 2)
        if y - base < 1:
            return
        if r < 1.5:
            self.create_rectangle(x0, base, x1, y, fill=cor, outline="")
            return
        self.create_rectangle(x0, base, x1, y - r, fill=cor, outline="")
        self.create_rectangle(x0 + r, y - r, x1 - r, y, fill=cor, outline="")
        for cx in (x0, x1 - 2 * r):
            self.create_oval(cx, y - 2 * r, cx + 2 * r, y, fill=cor, outline="")


PIZZA_CORES = ("#1F5A28", "#2F7D3A", "#59BA61", "#8FD08F", "#C4E6C2",
               "#7A8F80", "#B9C4BC", "#DDE3DC")
ATING_FUNDO = (("#FDE0DE", "#A3201A"), ("#FFF4D6", "#8A5A00"),
               ("#DDF2DF", "#1E6B2A"))


class PizzaTabela(tk.Canvas if tk else object):
    """
    O quadro do Painel Executivo (desenho do Claude Design): a PIZZA do
    projetado (rosca, participacao de cada linha na projecao) e, ao lado,
    a tabela META, REAL, PROJECAO, % PROJ. (pintado: vermelho < 80,
    amarelo < 100, verde >= 100) e MKP. Sem pizza: so a tabela.
    linhas: [nome, meta, real, projecao, % proj., mkp %, ...]; total igual.
    """

    COLS = ("DESAFIO", "REAL", "PROJEÇÃO", "% PROJ.", "SALDO", "CLIENTES",
            "POSIT.", "IPP", "VOL.", "MKP %", "MKP R$")

    def __init__(self, pai, titulo, nome_col, linhas, total=None, pizza=True,
                 altura=230):
        super().__init__(pai, background=CARTAO, height=altura,
                         highlightthickness=1, highlightbackground=CINZA_LINHA)
        self.titulo, self.nome_col = titulo, nome_col
        self.linhas, self.total, self.pizza = linhas, total, pizza
        self.bind("<Configure>", lambda e: self.desenhar())

    @staticmethod
    def _cor_pct(v):
        if not isinstance(v, (int, float)):
            return None
        return ATING_FUNDO[0] if v < 80 else ATING_FUNDO[1] if v < 100 \
            else ATING_FUNDO[2]

    def _textos(self, l):
        def n(v, casas=0):
            return "—" if v is None else br(v, casas)

        def pc(v, casas=0):
            return "—" if v is None else f"{br(v, casas)}%"
        return [n(l[1]), n(l[2]), n(l[3]), pc(l[4]), n(l[5]), n(l[6]),
                n(l[7]), n(l[8], 1), n(l[9]), pc(l[10], 1), n(l[11])]

    def _caber(self, w, h, topo, tkfont, u):
        """A maior letra que cabe (9, 8, 7) com a pizza; nao cabendo nem com
        a 7, a pizza sai e a tabela fica com a largura toda (tela pequena ou
        Windows com escala alta). Devolve (tam, d da pizza, x da tabela,
        larguras, nome)."""
        todas = list(self.linhas) + ([self.total] if self.total else [])
        txt = [self._textos(l) for l in todas]
        tentativas = [(t_, True) for t_ in (9, 8)] + [(t_, False)
                                                       for t_ in (9, 8, 7)]
        if not self.pizza:
            tentativas = [(t_, False) for t_ in (9, 8, 7)]
        for tam, com_pizza in tentativas:
            f_n = tkfont.Font(font=fonte(tam, "bold"))
            f_h = tkfont.Font(font=fonte(tam - 1, "bold"))
            f_c = tkfont.Font(font=fonte(tam))
            larg = [max([f_h.measure(c)] + [f_n.measure(t[j]) for t in txt])
                    + 12 for j, c in enumerate(self.COLS)]
            d = max(60, min(h - topo - 12, int(w * 0.13), 140 * u)) \
                if com_pizza else 0
            x_tab = (14 + d + 14) if com_pizza else 12
            nome_w = w - 10 - x_tab - sum(larg)
            maior = max((f_c.measure(str(l[0])[:14]) for l in self.linhas),
                        default=60)
            if nome_w >= min(maior, f_c.measure("M" * 9)) + 22:
                return tam, d, x_tab, larg, nome_w, txt
        return tam, d, x_tab, larg, max(60, nome_w), txt

    def desenhar(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 320), max(self.winfo_height(), 150)
        from tkinter import font as tkfont              # noqa: PLC0415
        u = max(1.0, tkfont.Font(font=fonte(8)).metrics("linespace") / 14.0)
        self.create_text(14, 18 * u, text=self.titulo, anchor="w",
                         font=fonte(11, "bold"), fill=TEXTO)
        if not self.linhas:
            self.create_text(w / 2, h / 2, text="Sem dados no período",
                             fill=SUAVE, font=fonte(9))
            return
        topo = 36 * u
        tam, d, x_tab, larg, nome_w, txt = self._caber(w, h, topo, tkfont, u)
        com_pizza = d > 0
        self.create_text(w - 12, 18 * u, anchor="e", font=fonte(8),
                         fill=SUAVE,
                         text="pizza = participação na projeção"
                         if com_pizza else "meta, real, projeção e markup")
        if com_pizza:
            cx, cy = 14 + d / 2, topo + (h - topo) / 2
            soma = sum(max(0.0, l[3] or 0) for l in self.linhas)
            r = d / 2
            if soma > 0:
                ang = 90.0
                for i, l in enumerate(self.linhas):
                    v = max(0.0, l[3] or 0)
                    if not v:
                        continue
                    ext = -360.0 * v / soma
                    if abs(ext) >= 359.9:
                        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                                         fill=PIZZA_CORES[i % 8], outline="")
                    else:
                        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                                        start=ang, extent=ext,
                                        fill=PIZZA_CORES[i % 8],
                                        outline=CARTAO, width=1)
                    ang += ext
            else:
                self.create_oval(cx - r, cy - r, cx + r, cy + r,
                                 fill=GRADE, outline="")
            ri = r * 0.62
            self.create_oval(cx - ri, cy - ri, cx + ri, cy + ri, fill=CARTAO,
                             outline="")
            tot = (self.total[3] if self.total else soma) or 0
            f_v = tkfont.Font(font=fonte(9, "bold"))
            self.create_text(cx, cy - 0.5 * f_v.metrics("linespace"),
                             text="projeção", font=fonte(7), fill=SUAVE)
            self.create_text(cx, cy + 0.45 * f_v.metrics("linespace"),
                             font=fonte(8, "bold"), fill=TEXTO,
                             text=("R$ " + _compacto(tot)) if tot else "—")
        # a tabela
        f_c = tkfont.Font(font=fonte(tam))
        f_n = tkfont.Font(font=fonte(tam, "bold"))
        todas = list(self.linhas) + ([self.total] if self.total else [])
        x_fim = w - 10
        n_l = len(todas) + 1
        lin = f_c.metrics("linespace")
        alt = max(lin + 2, min(lin + 7, (h - topo - 8) / n_l))
        y = topo + max(0, (h - topo - 8 - alt * n_l) / 2)
        cab_f = fonte(tam - 1, "bold")
        self.create_rectangle(x_tab, y, x_fim, y + alt, fill="#E4E7E5",
                              outline="")
        self.create_text(x_tab + 6, y + alt / 2, text=self.nome_col,
                         anchor="w", font=cab_f, fill="#2E3330")
        x = x_tab + nome_w
        for j, c in enumerate(self.COLS):
            x += larg[j]
            self.create_text(x - 6, y + alt / 2, text=c, anchor="e",
                             font=cab_f, fill="#2E3330")
        y += alt
        for i, l in enumerate(todas):
            eh_total = self.total is not None and i == len(todas) - 1
            if eh_total:
                self.create_rectangle(x_tab, y, x_fim, y + alt,
                                      fill="#E6F4E1", outline="")
                self.create_line(x_tab, y, x_fim, y, fill=VERDE)
            else:
                self.create_line(x_tab, y + alt, x_fim, y + alt, fill=GRADE)
            f = fonte(tam, "bold") if eh_total else fonte(tam)
            cor_t = "#1F3B22" if eh_total else TEXTO
            xn = x_tab + 6
            if com_pizza and not eh_total:
                self.create_rectangle(xn, y + alt / 2 - 4, xn + 8,
                                      y + alt / 2 + 4,
                                      fill=PIZZA_CORES[i % 8], outline="")
                xn += 13
            nome = str(l[0])
            while nome and f_c.measure(nome) > x_tab + nome_w - xn - 4:
                nome = nome[:-2] + "…" if len(nome) > 2 else ""
            self.create_text(xn, y + alt / 2, text=nome, anchor="w", font=f,
                             fill=cor_t)
            x = x_tab + nome_w
            for j, t in enumerate(txt[i]):
                x += larg[j]
                par = self._cor_pct(l[4]) if j == 3 else None
                if par:
                    tw = f_n.measure(t)
                    self.create_rectangle(x - tw - 10, y + 2, x - 2,
                                          y + alt - 2, fill=par[0],
                                          outline="")
                self.create_text(x - 6, y + alt / 2, text=t, anchor="e",
                                 font=fonte(tam, "bold") if (
                                     eh_total or par or j == 2) else f,
                                 fill=par[1] if par else
                                 VERMELHO if j == 4 and (l[5] or 0) < 0 else
                                 (SUAVE if j >= 5 and not eh_total
                                  else cor_t))
            y += alt


class BarrasHorizontais(tk.Canvas if tk else object):
    """
    O 'funil' do painel executivo: uma barra deitada por item, do maior
    para o menor, com o valor na ponta. Redesenha ao mudar de tamanho e
    mostra so os itens que cabem na altura.
    """

    def __init__(self, pai, titulo, rotulos, valores, formato="moeda",
                 cor=None, altura=200, cores=None, referencia=None):
        super().__init__(pai, background=CARTAO, height=altura,
                         highlightthickness=1, highlightbackground=CINZA_LINHA)
        self.titulo, self.rotulos, self.valores = titulo, rotulos, valores
        self.formato, self.cor = formato, cor or VERDE
        # cores: uma por barra (o farol de cada item); referencia: a linha
        # tracejada de um valor (ex.: 100% da meta)
        self.cores, self.referencia = cores, referencia
        self.bind("<Configure>", lambda e: self.desenhar())

    def _fmt(self, v):
        if self.formato == "moeda":
            return ("-R$ " if (v or 0) < 0 else "R$ ") + _compacto(abs(v or 0))
        if self.formato == "pct":
            return pct(v)
        if self.formato == "hora":           # segundos -> 09:48
            s_ = int(round(v or 0))
            return f"{s_ // 3600:02d}:{s_ % 3600 // 60:02d}"
        if self.formato == "num1":
            return br(v, 1)
        return _compacto(v)

    def desenhar(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 200), max(self.winfo_height(), 120)
        self.create_text(14, 16, text=self.titulo, anchor="w",
                         font=fonte(10, "bold"), fill=TEXTO)
        if not self.rotulos:
            self.create_text(w / 2, h / 2, text="Sem dados no período",
                             fill=SUAVE, font=fonte(9))
            return
        topo, passo = 36, 22
        cabem = max(1, int((h - topo - 6) / passo))
        itens = list(zip(self.rotulos, self.valores))[:cabem]
        from tkinter import font as tkfont              # noqa: PLC0415
        f8 = tkfont.Font(font=fonte(8))
        larg_rot = min(int(w * 0.38), max(f8.measure(str(r)[:22])
                                          for r, _ in itens) + 8)
        maior = max([abs(v or 0) for _, v in itens]
                    + [self.referencia or 0], default=0) or 1
        area = w - larg_rot - 14 - 86
        if self.referencia:
            xr = 14 + larg_rot + area * self.referencia / maior
            self.create_line(xr, topo - 4, xr, topo + len(itens) * passo,
                             fill=SUAVE, dash=(2, 3))
            self.create_text(xr, topo - 6, text=self._fmt(self.referencia),
                             anchor="s", font=fonte(7), fill=SUAVE)
        for i, (rot, v) in enumerate(itens):
            y = topo + i * passo + passo / 2
            txt = str(rot)
            while txt and f8.measure(txt) > larg_rot - 6:
                txt = txt[:-2] + "…" if len(txt) > 2 else ""
            self.create_text(14, y, text=txt, anchor="w", font=fonte(8),
                             fill=TEXTO)
            x0 = 14 + larg_rot
            comp = max(2, area * abs(v or 0) / maior) if v else 0
            cor = VERMELHO if (v or 0) < 0 else self.cor
            if self.cores and i < len(self.cores) and self.cores[i]:
                cor = self.cores[i]
            if comp:
                self.create_rectangle(x0, y - 7, x0 + comp, y + 7, fill=cor,
                                      outline="")
            self.create_text(x0 + comp + 6, y, text=self._fmt(v), anchor="w",
                             font=fonte(8, "bold"), fill=TEXTO)


class PlacarFarois(tk.Frame if tk else object):
    """(12/10) O placar da Visao executiva: um cartao por farol - o nome,
    BOM/ATENCAO/RUIM, o numero, o detalhe e o IMPACTO no faturamento (verde
    soma, vermelho tira). Passando o mouse: como e calculado."""

    TONS = {"ok": (VERDE, "BOM"), "atencao": (AMARELO, "ATENÇÃO"),
            "alerta": (VERMELHO, "RUIM")}

    def __init__(self, pai, titulo, cartoes, por_linha=4):
        super().__init__(pai, background=FUNDO)
        tk.Label(self, text=titulo, background=FUNDO, foreground=TEXTO,
                 font=fonte(10, "bold"), anchor="w").grid(
            row=0, column=0, columnspan=por_linha, sticky="w", padx=2,
            pady=(0, 4))
        n_lin = (len(cartoes) + por_linha - 1) // por_linha
        for i, c in enumerate(cartoes):
            self._cartao(c).grid(row=1 + i // por_linha, column=i % por_linha,
                                 sticky="nsew", padx=3, pady=3)
        for j in range(por_linha):
            self.columnconfigure(j, weight=1, uniform="pf")
        for i in range(n_lin):
            self.rowconfigure(1 + i, weight=1, uniform="pl")

    def _cartao(self, c):
        if MODELO_CARTAO == "RRM":
            return self._cartao_rrm(c)
        cor, txt_tom = self.TONS.get(c.get("tom"), (CINZA_LINHA, ""))
        f = tk.Frame(self, background=CARTAO, highlightthickness=1,
                     highlightbackground=CINZA_LINHA)
        tk.Frame(f, background=cor, width=4).pack(side="left", fill="y")
        d = tk.Frame(f, background=CARTAO)
        d.pack(side="left", fill="both", expand=True, padx=(9, 8), pady=6)
        top = tk.Frame(d, background=CARTAO)
        top.pack(fill="x")
        tk.Label(top, text=c.get("farol", ""), background=CARTAO,
                 foreground=SUAVE, font=fonte(8, "bold"), anchor="w").pack(
            side="left")
        if txt_tom:
            tk.Label(top, text=txt_tom, background=CARTAO, foreground=cor,
                     font=fonte(7, "bold")).pack(side="right")
        lin = tk.Frame(d, background=CARTAO)
        lin.pack(fill="x", pady=(1, 0))
        tk.Label(lin, text=str(c.get("valor", "—")), background=CARTAO,
                 foreground=TEXTO, font=fonte(14, "bold")).pack(side="left")
        tk.Label(lin, text=c.get("rotulo", ""), background=CARTAO,
                 foreground=SUAVE, font=fonte(8)).pack(
            side="left", padx=(6, 0), pady=(5, 0))
        det = tk.Label(d, text=c.get("detalhe", ""), background=CARTAO,
                       foreground=SUAVE, font=fonte(8), anchor="w",
                       justify="left")
        det.pack(fill="x")
        imp = c.get("impacto")
        if imp is not None and abs(imp) >= 0.5:
            sinal = "+" if imp > 0 else "−"
            txt = f"{sinal}R$ {_compacto(abs(imp))}"
            tk.Label(d, text=f"{txt}  ·  {c.get('sentido', '')}",
                     background=CARTAO,
                     foreground=VERDE_ESCURO if imp > 0 else VERMELHO,
                     font=fonte(9, "bold"), anchor="w").pack(fill="x",
                                                             pady=(2, 0))
        else:
            tk.Label(d, text="sem impacto em R$", background=CARTAO,
                     foreground=CINZA_LINHA, font=fonte(8), anchor="w").pack(
                fill="x", pady=(2, 0))
        ajuda = "\n\n".join(x for x in (c.get("frase"), c.get("dica")) if x)
        if ajuda:
            for w in [f, d, top, lin, det] + list(d.winfo_children()):
                Dica(w, ajuda)
        d.bind("<Configure>", lambda e, w_=det: w_.configure(
            wraplength=max(80, e.width - 4)))
        return f


    def _cartao_rrm(self, c):
        """(10/11, recado 20261109-1345) o placar no modelo da RRM: faixa
        com o farol, BOM/ATENCAO/RUIM, o numero e o indicador; filete
        verde; embaixo, o impacto em R$."""
        tom = c.get("tom")
        _cor, txt_tom = self.TONS.get(tom, (CINZA_LINHA, ""))
        caixa = tk.Frame(self, background=_PAL["branco"],
                         highlightbackground=_PAL["borda"],
                         highlightthickness=1)
        fx = tk.Frame(caixa, background=RRM_PRETO)
        fx.pack(fill="x")
        top = tk.Frame(fx, background=RRM_PRETO)
        top.pack(fill="x", padx=10, pady=(7, 0))
        tk.Label(top, text=str(c.get("farol", "")).upper(),
                 background=RRM_PRETO, foreground=RRM_ROTULO,
                 font=fonte(7, "bold"), anchor="w").pack(side="left")
        if txt_tom:
            tk.Label(top, text=txt_tom, background=RRM_PRETO,
                     foreground=RRM_TOM.get(tom, RRM_ROTULO),
                     font=fonte(7, "bold")).pack(side="right")
        lin = tk.Frame(fx, background=RRM_PRETO)
        lin.pack(fill="x", padx=10)
        tk.Label(lin, text=str(c.get("valor", "—")), background=RRM_PRETO,
                 foreground=RRM_NUMERO, font=fonte(15, "bold")).pack(
                     side="left")
        tk.Label(lin, text=c.get("rotulo", ""), background=RRM_PRETO,
                 foreground=RRM_ROTULO, font=fonte(7)).pack(
                     side="left", padx=(6, 0), pady=(6, 0))
        det = tk.Label(fx, text=c.get("detalhe", ""), background=RRM_PRETO,
                       foreground=RRM_ROTULO, font=fonte(7), anchor="w",
                       justify="left")
        det.pack(fill="x", padx=10, pady=(0, 6))
        tk.Frame(caixa, background=_PAL["filete"], height=3).pack(fill="x")
        imp = c.get("impacto")
        if imp is not None and abs(imp) >= 0.5:
            sinal = "+" if imp > 0 else "−"
            txt = f"{sinal}R$ {_compacto(abs(imp))}  ·  {c.get('sentido', '')}"
            cor_i = _PAL["ok_b"] if imp > 0 else _PAL["alerta_b"]
            fonte_i = fonte(9, "bold")
        else:
            txt, cor_i, fonte_i = "sem impacto em R$", SUAVE, fonte(8)
        tk.Label(caixa, text=txt, background=_PAL["branco"],
                 foreground=cor_i, font=fonte_i, anchor="w").pack(
                     fill="x", padx=10, pady=(5, 6))
        ajuda = "\n\n".join(x for x in (c.get("frase"), c.get("dica")) if x)
        if ajuda:
            pilha = [caixa]
            while pilha:
                w_ = pilha.pop()
                Dica(w_, ajuda)
                pilha.extend(w_.winfo_children())
        fx.bind("<Configure>", lambda e, w_=det: w_.configure(
            wraplength=max(80, e.width - 20)))
        return caixa


def _passo_redondo(v: float) -> float:
    """O passo 'bonito' da grade: 1, 2, 2,5 ou 5 vezes 10^n."""
    import math                                         # noqa: PLC0415
    if v <= 0:
        return 1
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * mag:
            return m * mag
    return 10 * mag


def _compacto(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if abs(v) >= 1_000_000:
        return br(v / 1_000_000, 1) + " mi"
    if abs(v) >= 10_000:
        return br(v / 1000, 0) + " mil"
    return br(v, 0)


# ============================================================== EXPORTAR
def _valor_excel(v, tipo):
    if tipo in ("pct", "pct1") and isinstance(v, (int, float)):
        return v / 100.0
    return v


def _cabecalho_rv(ws, n_col, larguras, titulo, periodo) -> int:
    """A faixa da BAP (imagem dos slides), o titulo e o PERIODO no topo de
    uma aba do Excel do RH. Devolve a linha livre de baixo."""
    from openpyxl.styles import Font, PatternFill      # noqa: PLC0415
    img = RECURSOS / "cabecalho_bap.png"
    total_px = sum(larguras) * 7.0 + 5 * n_col
    lin = 1
    if img.exists():
        try:
            from openpyxl.drawing.image import Image as XlImg  # noqa
            pic = XlImg(str(img))
            fator = total_px / pic.width
            pic.width, pic.height = int(pic.width * fator), \
                int(pic.height * fator)
            ws.add_image(pic, "A1")
            n_lin = max(2, int(pic.height / 20) + 1)
            for i in range(1, n_lin + 1):
                ws.row_dimensions[i].height = 15
            lin = n_lin + 1
        except Exception:                               # noqa: BLE001
            lin = 1
    if lin == 1:                                       # sem a imagem
        preto = PatternFill("solid", fgColor="111111")
        for j in range(1, n_col + 1):
            ws.cell(1, j).fill = preto
        ws.cell(1, n_col, "bap").font = Font(bold=True, size=20,
                                             color="FFFFFF")
        ws.row_dimensions[1].height = 34
        lin = 2
    lin += 1
    ws.cell(lin, 1, titulo).font = Font(bold=True, size=20, color=TEXTO[1:])
    ws.row_dimensions[lin].height = 28
    lin += 1
    ws.cell(lin, 1, f"PERÍODO: {periodo}").font = Font(
        bold=True, size=12, color=VERDE_ESCURO[1:])
    return lin + 1


def _aba_mecanica_rv(wb, rel) -> dict:
    """(04/11, Alexandre) A aba MECANICA do Excel do RH: indicadores e
    valor maximo por publico, as TABELAS DE FAIXAS em celulas (com nome:
    RV_VENDEDOR_FAT_DE / _ATE / _VAL ...) e as regras de apuracao.
    Devolve {(nivel, kpi): (nome_de, nome_ate, nome_val)}."""
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa
    from openpyxl.workbook.defined_name import DefinedName    # noqa
    mec = rel["mecanica"]
    ws = wb.create_sheet("MECÂNICA")
    ws.sheet_view.showGridLines = False
    larg = [30, 28, 22, 18, 4, 16, 16, 16, 4, 16, 16, 16, 16]
    for j, w in enumerate(larg, 1):
        ws.column_dimensions[chr(64 + j)].width = w
    lin = _cabecalho_rv(ws, len(larg), larg,
                        "REMUNERAÇÃO VARIÁVEL · MECÂNICA",
                        mec.get("periodo") or rel.get("periodo") or "")
    cab_f = PatternFill("solid", fgColor=CINZA_CAB[1:])
    sec = Font(bold=True, size=12, color=VERDE_ESCURO[1:])
    rot = mec.get("rotulos") or {}
    faixas = mec.get("faixas") or {}
    publicos = (("vendedor", "VENDEDOR"), ("supervisor", "SUPERVISOR"),
                ("gerente", "GERENTE"))
    # 1) quem recebe e quanto vale cada indicador (a ultima faixa)
    lin += 1
    ws.cell(lin, 1, "1. INDICADORES QUE PAGAM RV E VALOR MÁXIMO").font = sec
    lin += 1
    for j, t in enumerate(("PÚBLICO", "INDICADOR", "META USADA",
                           "VALOR MÁXIMO R$"), 1):
        c = ws.cell(lin, j, t)
        c.fill = cab_f
        c.font = Font(bold=True, size=9)
    lin += 1
    meta_usada = {"fat": "meta RH", "positivacao": "meta de positivação",
                  "visita": "meta de visita (RH)"}
    for nivel, nome in publicos:
        kp = faixas.get(nivel) or {}
        if not any(kp.values()):
            ws.cell(lin, 1, nome)
            ws.cell(lin, 2, "sem tabela de RV")
            lin += 1
            continue
        tot = 0.0
        for k in ("fat", "positivacao", "visita"):
            fs = kp.get(k) or []
            mx = fs[-1][2] if fs else 0.0
            tot += mx
            ws.cell(lin, 1, nome)
            ws.cell(lin, 2, rot.get(k, k))
            ws.cell(lin, 3, meta_usada.get(k, ""))
            ws.cell(lin, 4, mx).number_format = '"R$" #,##0.00'
            lin += 1
        ws.cell(lin, 2, "TOTAL MÁXIMO").font = Font(bold=True)
        c = ws.cell(lin, 4, tot)
        c.number_format = '"R$" #,##0.00'
        c.font = Font(bold=True)
        lin += 1
    # 2) as faixas, em celulas (as formulas leem daqui)
    lin += 1
    ws.cell(lin, 1, "2. TABELAS DE FAIXAS (% ATING. → VALOR PAGO)").font = sec
    lin += 1
    ws.cell(lin, 1, "A RV do indicador é o VALOR da faixa em que o % ATING. "
            "cai (DE ≤ % ≤ ATÉ). Acima da última faixa vale a última. As "
            "fórmulas da aba REMUNERAÇÃO VARIÁVEL leem estas células: mudar "
            "aqui muda a RV.").font = Font(size=9, color=SUAVE[1:])
    lin += 2
    nomes = {}
    for nivel, nome in publicos:
        kp = faixas.get(nivel) or {}
        if not any(kp.values()):
            continue
        ws.cell(lin, 1, nome).font = Font(bold=True, size=11)
        lin += 1
        topo = lin
        alto = 0
        for b, k in enumerate(("fat", "positivacao", "visita")):
            fs = kp.get(k) or []
            col0 = (1, 6, 10)[b]
            ws.cell(topo, col0, rot.get(k, k)).font = Font(
                bold=True, color=VERDE_ESCURO[1:])
            for jj, t in enumerate(("DE (%)", "ATÉ (%)", "VALOR R$")):
                c = ws.cell(topo + 1, col0 + jj, t)
                c.fill = cab_f
                c.font = Font(bold=True, size=9)
                c.alignment = Alignment(horizontal="center")
            for i, (de, ate, val) in enumerate(fs):
                r_ = topo + 2 + i
                ws.cell(r_, col0, de).number_format = "0.000"
                ws.cell(r_, col0 + 1, ate).number_format = "0.000"
                ws.cell(r_, col0 + 2, val).number_format = '"R$" #,##0.00'
            if fs:
                r1, r2 = topo + 2, topo + 1 + len(fs)
                trio = []
                for jj, suf in enumerate(("DE", "ATE", "VAL")):
                    letra = chr(64 + col0 + jj)
                    nm = f"RV_{nivel.upper()}_{k.upper()}_{suf}"
                    ref = f"'MECÂNICA'!${letra}${r1}:${letra}${r2}"
                    wb.defined_names[nm] = DefinedName(nm, attr_text=ref)
                    trio.append(nm)
                nomes[(nivel, k)] = tuple(trio)
            alto = max(alto, len(fs) + 2)
        lin = topo + alto + 1
    # 3) as regras de apuracao
    lin += 1
    ws.cell(lin, 1, "3. REGRAS DE APURAÇÃO").font = sec
    lin += 1
    for tema, txt in mec.get("regras") or []:
        c = ws.cell(lin, 1, tema)
        c.font = Font(bold=True, size=9,
                      color=(AMARELO[1:] if "[" in tema else TEXTO[1:]))
        c.alignment = Alignment(vertical="top", wrap_text=True)
        t = ws.cell(lin, 2, txt)
        t.font = Font(size=9)
        t.alignment = Alignment(vertical="top", wrap_text=True)
        ws.merge_cells(start_row=lin, start_column=2, end_row=lin,
                       end_column=13)
        ws.row_dimensions[lin].height = 15 * max(1, len(txt) // 150 + 1)
        lin += 1
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return nomes


def _exportar_excel_rv(rel: dict, caminho) -> Path:
    """(03/11, Alexandre) O fechamento do RH (Exportar para o RH do Farol de
    Metas) numa aba so: o cabecalho da BAP (a faixa dos PowerPoints, em
    SISTEMA BAP\\recursos\\cabecalho_bap.png), REMUNERACAO VARIAVEL e o
    PERIODO, e embaixo Gerente, Supervisores e Vendedores com as mesmas
    colunas. COMPLEMENTO e para o RH preencher (amarelo); TOTAL A PAGAR =
    RV TOTAL + COMPLEMENTO (formula), com os totais por formula."""
    from openpyxl import Workbook                     # noqa: PLC0415
    from openpyxl.styles import (Alignment, Border, Font,  # noqa: PLC0415
                                 PatternFill, Side)
    from openpyxl.utils import get_column_letter      # noqa: PLC0415
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "REMUNERAÇÃO VARIÁVEL"
    ws.sheet_view.showGridLines = False
    tabelas = rel.get("tabelas", [])
    # a grade comum: NOME, SUPERVISOR e os numeros (a tabela sem a coluna
    # SUPERVISOR deixa a coluna B em branco, para tudo ficar alinhado)
    base = next((t for t in tabelas if any(c["nome"] == "SUPERVISOR"
                                           for c in t["colunas"])),
                tabelas[-1] if tabelas else None)
    if base is None:
        wb.save(caminho)
        return caminho
    grade = [c for c in base["colunas"] if c["nome"] not in ("NOME",
                                                              "SUPERVISOR")]
    n_col = 2 + len(grade)
    ult = get_column_letter(n_col)
    # (04/11, Alexandre) colunas justas: tudo cabe na tela sem arrastar
    def larg_(c):
        n_ = c["nome"]
        if n_ == "TOTAL A PAGAR":
            return 13
        if n_ in ("RV TOTAL", "COMPLEMENTO"):
            return 12
        if n_.endswith(" RV"):
            return 11
        if n_.endswith("% ATING."):
            return 8
        return 12 if c.get("tipo") == "moeda" else 7
    larguras = [34, 20] + [larg_(c) for c in grade]
    for j, w in enumerate(larguras, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    fino = Side(style="thin", color=CINZA_CAB[1:])
    cab_f = PatternFill("solid", fgColor=CINZA_CAB[1:])
    grupo_f = PatternFill("solid", fgColor=VERDE_CLARO[1:])
    amarelo = PatternFill("solid", fgColor="FFF4C2")
    # (05/11, Alexandre) "a coluna meta e os nomes com um cinza mais claro"
    # (mais claro que o cinza do cabecalho)
    cinza_claro = PatternFill("solid", fgColor="F3F4F2")
    preto = PatternFill("solid", fgColor="111111")
    # 1) o CABECALHO DA BAP (a faixa preta com o logo, como nos slides)
    lin = _cabecalho_rv(ws, n_col, larguras, "REMUNERAÇÃO VARIÁVEL",
                        rel.get("periodo") or "")
    # (04/11, Alexandre) sem a linha cinza de "resultado ate / posicao"
    # (04/11) a aba MECANICA: as faixas em celulas, com nome (as formulas
    # da RV leem daqui) e as regras
    nomes_faixa = _aba_mecanica_rv(wb, rel) if rel.get("mecanica") else {}
    com_regra = bool(rel.get("mecanica"))
    j_regra = n_col + 1
    if com_regra:
        ws.column_dimensions[get_column_letter(j_regra)].width = 30
    ws.sheet_view.zoomScale = 85
    pref_kpi = {"FAT.": "fat", "POSIT.": "positivacao", "VISITA": "visita"}

    def formula_rv(nome_c, nivel, lin_):
        """(04/11) % ATING. e RV de cada indicador por formula (lendo as
        faixas da aba MECANICA); None = escreve o valor."""
        if not com_regra:
            return None
        for pre, k in pref_kpi.items():
            if not nome_c.startswith(pre + " "):
                continue
            l_m = get_column_letter(destino[f"{pre} META"])
            l_r = get_column_letter(destino[f"{pre} REAL"])
            l_p = get_column_letter(destino[f"{pre} % ATING."])
            if nome_c.endswith("% ATING."):
                return f"=IF(N({l_m}{lin_})>0,N({l_r}{lin_})/N({l_m}{lin_}),0)"
            if nome_c.endswith(" RV"):
                trio = nomes_faixa.get((nivel, k))
                if not trio:
                    return ""
                de, ate, val = trio
                x = f"ROUND({l_p}{lin_}*100,3)"   # como o sistema (04/11)
                return (f"=SUMPRODUCT(({x}>={de})*({x}<={ate})*{val})"
                        f"+IF({x}>MAX({ate}),INDEX({val},ROWS({val})),0)")
            return None
        if nome_c == "RV TOTAL":
            if not any(nomes_faixa.get((nivel, k)) for k in pref_kpi.values()):
                return ""
            return "=" + "+".join(
                f"N({get_column_letter(destino[p + ' RV'])}{lin_})"
                for p in pref_kpi)
        return None
    lin += 2
    celulas_total = []

    def fmt(cel, tipo, nome=""):
        if tipo in ("moeda", "moeda2") and nome.endswith((" META",
                                                            " REAL")):
            cel.number_format = '"R$" #,##0'      # meta e real sem centavos
        elif tipo in ("moeda", "moeda2"):
            cel.number_format = '"R$" #,##0.00'
        elif tipo in ("pct", "pct1"):
            cel.number_format = "0%"
        elif tipo in ("int", "num"):
            cel.number_format = "#,##0"
    for t in tabelas:
        cols = t["colunas"]
        idx = {c["nome"]: j for j, c in enumerate(cols)}
        destino = {"NOME": 1, "SUPERVISOR": 2}
        destino.update({c["nome"]: 3 + k for k, c in enumerate(grade)})
        # o titulo da secao
        ws.cell(lin, 1, t["titulo"].upper()).font = Font(
            bold=True, size=12, color=VERDE_ESCURO[1:])
        lin += 1
        # a linha dos indicadores (mesclada) e a dos nomes curtos
        grupos = base.get("grupos") or []
        j = 1
        for rot, n in grupos:
            if rot:
                cel = ws.cell(lin, j, rot)
                cel.fill = grupo_f
                cel.font = Font(bold=True, size=9, color=VERDE_ESCURO[1:])
                cel.alignment = Alignment(horizontal="center")
                if n > 1:
                    ws.merge_cells(start_row=lin, start_column=j,
                                   end_row=lin, end_column=j + n - 1)
            j += n
        lin += 1
        for nome_c, jj in destino.items():
            c = next((x for x in base["colunas"] if x["nome"] == nome_c),
                     None)
            rot = (c.get("curto") or c["nome"]) if c else nome_c
            if nome_c == "SUPERVISOR" and nome_c not in idx:
                rot = ""
            cel = ws.cell(lin, jj, rot)
            ws.row_dimensions[lin].height = 24
            cel.fill = cab_f
            cel.font = Font(bold=True, size=9)
            cel.alignment = Alignment(horizontal="center" if jj > 2
                                      else "left", vertical="center",
                                      wrap_text=True)
            cel.border = Border(bottom=fino)
        if com_regra:
            # (05/11, Alexandre) "tire esse campo regra aplicada e troque
            # por OBS.:"
            cel = ws.cell(lin, j_regra, "OBS.:")
            cel.fill = cab_f
            cel.font = Font(bold=True, size=9)
            cel.border = Border(bottom=fino)
        lin += 1
        primeira = lin
        nivel = t.get("nivel_rv") or ""
        regras_l = t.get("regras_excel") or []
        cores_l = t.get("cores_celulas") or []
        for i, l in enumerate(t["linhas"]):
            pinta = cores_l[i] if i < len(cores_l) else {}
            for nome_c, j_src in idx.items():
                jj = destino.get(nome_c)
                if jj is None:
                    continue
                c = cols[j_src]
                tipo = c.get("tipo", "texto")
                v = l[j_src] if j_src < len(l) else None
                cel = ws.cell(lin, jj)
                if c.get("editavel_excel"):
                    cel.value = v
                    cel.fill = amarelo
                elif c.get("formula_excel") == "rv+compl":
                    l_rv = get_column_letter(destino["RV TOTAL"])
                    l_cp = get_column_letter(destino["COMPLEMENTO"])
                    cel.value = f"=N({l_rv}{lin})+N({l_cp}{lin})"
                    cel.font = Font(bold=True)
                else:
                    f_ = formula_rv(c["nome"], nivel, lin)
                    if f_ is not None:
                        cel.value = f_ or None
                    else:
                        cel.value = _valor_excel(v, tipo)
                    if j_src in pinta:
                        cel.font = Font(bold=True, color=pinta[j_src][1:])
                fmt(cel, tipo, c["nome"])
                cel.border = Border(bottom=fino)
                if nome_c in ("NOME", "SUPERVISOR") or \
                        nome_c.endswith(" META"):
                    cel.fill = cinza_claro
            if com_regra and i < len(regras_l):
                cel = ws.cell(lin, j_regra, regras_l[i])
                cel.font = Font(size=8, color=SUAVE[1:])
                cel.alignment = Alignment(wrap_text=True, vertical="center")
                cel.border = Border(bottom=fino)
            lin += 1
        # TOTAL por formula (o % e o real / meta do total)
        if len(t["linhas"]) > 1:
            ws.cell(lin, 1, "TOTAL").font = Font(bold=True)
            for j in range(1, n_col + 1):
                ws.cell(lin, j).fill = cab_f
            for k, c in enumerate(grade):
                jj = 3 + k
                col_l = get_column_letter(jj)
                cel = ws.cell(lin, jj)
                if c["nome"] == "MESES DE CASA":    # (04/11) nao se soma
                    continue
                if c.get("tipo") in ("pct", "pct1"):
                    l_m = get_column_letter(jj - 2)
                    l_r = get_column_letter(jj - 1)
                    cel.value = (f'=IFERROR({l_r}{lin}/{l_m}{lin},"")')
                else:
                    cel.value = f"=SUM({col_l}{primeira}:{col_l}{lin - 1})"
                cel.font = Font(bold=True)
                fmt(cel, c.get("tipo"), c["nome"])
            celulas_total.append(
                f"{get_column_letter(destino['TOTAL A PAGAR'])}{lin}")
            lin += 1
        elif t["linhas"]:
            celulas_total.append(
                f"{get_column_letter(destino['TOTAL A PAGAR'])}{lin - 1}")
        lin += 1
    # 3) o total geral a pagar e as assinaturas
    if celulas_total:
        j_p = 2 + len(grade)
        ws.cell(lin, j_p - 1, "TOTAL GERAL A PAGAR").font = Font(
            bold=True, color=VERDE_ESCURO[1:])
        ws.cell(lin, j_p - 1).alignment = Alignment(horizontal="right")
        cel = ws.cell(lin, j_p, "=" + "+".join(f"N({c})"
                                               for c in celulas_total))
        cel.font = Font(bold=True, size=12, color=VERDE_ESCURO[1:])
        cel.number_format = '"R$" #,##0.00'
        lin += 1
    if rel.get("assinaturas"):
        lin += 3
        n_a = len(rel["assinaturas"])
        for i, a_ in enumerate(rel["assinaturas"]):
            j = 1 if i == 0 else 2 + round(i * (n_col - 3) / max(n_a - 1, 1))
            ws.cell(lin, j, "_" * 28).font = Font(color=SUAVE[1:])
            ws.cell(lin + 1, j, a_).font = Font(color=SUAVE[1:])
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = (f"A1:{get_column_letter(j_regra) if com_regra else ult}"
                     f"{lin + 2}")
    wb.save(caminho)
    return caminho


def exportar_excel(rel: dict, caminho) -> Path:
    """O relatorio (como esta na tela, com o filtro) num .xlsx."""
    if rel.get("excel_rv"):          # (03/11) o fechamento do RH, aba unica
        return _exportar_excel_rv(rel, caminho)
    from openpyxl import Workbook                     # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    from openpyxl.utils import get_column_letter      # noqa: PLC0415
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "RESUMO"
    cab = PatternFill("solid", fgColor=CINZA_CAB[1:])
    verde = Font(color=VERDE_ESCURO[1:], bold=True, size=9)
    ws["A1"] = f"{NOME_MARCA} · {rel.get('area', '').upper()}"
    ws["A1"].font = verde
    ws["A2"] = rel.get("titulo", "")
    ws["A2"].font = Font(bold=True, size=16)
    ws["A3"] = rel.get("subtitulo", "")
    ws["A3"].font = Font(color=SUAVE[1:], size=10)
    lin = 5
    for k in rel.get("kpis", []):
        ws.cell(lin, 1, k["rotulo"]).font = Font(bold=True, color=SUAVE[1:])
        ws.cell(lin, 2, k["valor"]).font = Font(bold=True, size=12)
        ws.cell(lin, 3, k.get("detalhe", ""))
        lin += 1
    for aviso in rel.get("avisos", []):
        lin += 1
        ws.cell(lin, 1, aviso).font = Font(italic=True, color=SUAVE[1:])
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 60
    for g in rel.get("graficos", []):
        lin += 2
        ws.cell(lin, 1, g["titulo"]).font = Font(bold=True)
        lin += 1
        ws.cell(lin, 1, "Período").fill = cab
        for j, s in enumerate(g["series"]):
            ws.cell(lin, 2 + j, s["nome"]).fill = cab
        for i, r in enumerate(g["rotulos"]):
            lin += 1
            ws.cell(lin, 1, str(r))
            for j, s in enumerate(g["series"]):
                ws.cell(lin, 2 + j, s["valores"][i])
    usados = {"RESUMO"}
    for t in rel.get("tabelas", []):
        nome = "".join(ch for ch in t["titulo"] if ch not in "[]*?/\\:")[:28]
        base, n = nome or "TABELA", 2
        while nome in usados:
            nome = f"{base[:25]} {n}"
            n += 1
        usados.add(nome)
        wt = wb.create_sheet(nome)
        cols = t["colunas"]
        grupos = t.get("grupos")
        # TABELA AGRUPADA: uma linha em cima com o indicador (celulas
        # mescladas) e embaixo os nomes curtos - igual a tela e o PDF
        topo = 2 if grupos else 1
        if grupos:
            grupo_f = PatternFill("solid", fgColor=VERDE_CLARO[1:])
            j = 1
            for rot, n in grupos:
                if rot:
                    cel = wt.cell(1, j, rot)
                    cel.fill = grupo_f
                    cel.font = Font(bold=True, color=VERDE_ESCURO[1:])
                    cel.alignment = Alignment(horizontal="center")
                    if n > 1:
                        wt.merge_cells(start_row=1, start_column=j,
                                       end_row=1, end_column=j + n - 1)
                j += n
        for j, c in enumerate(cols, 1):
            cel = wt.cell(topo, j, (c.get("curto") or c["nome"]) if grupos
                          else c["nome"])
            cel.fill = cab
            cel.font = Font(bold=True)
            cel.alignment = Alignment(wrap_text=True, vertical="center")
            wt.column_dimensions[get_column_letter(j)].width = max(
                10, min(48, c.get("largura", 110) / 7))
        linhas = t.get("linhas_visiveis", t["linhas"])
        cores_l = {id(l): c_ for l, c_ in zip(t["linhas"],
                                               t.get("cores_celulas") or [])}
        tons_l = {id(l): tn for l, tn in zip(t["linhas"], t.get("tons") or [])}
        vermelho = Font(color=VERMELHO[1:])
        for i, linha in enumerate(linhas, topo + 1):
            pinta = cores_l.get(id(linha), {})
            for j, (v, c) in enumerate(zip(linha, cols), 1):
                tipo = c.get("tipo", "texto")
                cel = wt.cell(i, j, _valor_excel(v, tipo))
                if (j - 1) in pinta:
                    cel.font = Font(bold=True, color=pinta[j - 1][1:])
                elif tons_l.get(id(linha)) == "devolucao":
                    cel.font = vermelho
                if tipo in ("moeda", "moeda2"):
                    cel.number_format = '"R$" #,##0.00'
                elif tipo in ("pct", "pct1"):
                    cel.number_format = "0.0%"
                elif tipo in ("data", "dia"):
                    cel.number_format = "dd/mm/yyyy"
                elif tipo in ("int", "num"):
                    cel.number_format = "#,##0"
                elif tipo == "num2":
                    cel.number_format = "#,##0.00"
        tot = t.get("total")
        vis = t.get("linhas_visiveis")
        if tot and (vis is None or len(vis) == len(t["linhas"])
                    or t.get("total_vale")):
            i = len(linhas) + topo + 1
            for j, (v, c) in enumerate(zip(tot, cols), 1):
                cel = wt.cell(i, j, _valor_excel(v, c.get("tipo", "texto")))
                cel.font = Font(bold=True)
                cel.fill = cab
                tipo = c.get("tipo", "texto")
                if tipo in ("moeda", "moeda2"):
                    cel.number_format = '"R$" #,##0.00'
                elif tipo in ("pct", "pct1"):
                    cel.number_format = "0.0%"
                elif tipo in ("int", "num"):
                    cel.number_format = "#,##0"
                elif tipo == "num2":
                    cel.number_format = "#,##0.00"
        if t.get("nota_pdf"):        # (08/10) a nota vai junto no Excel
            i_n = len(linhas) + topo + (3 if tot else 2)
            wt.cell(i_n, 1, t["nota_pdf"]).font = Font(italic=True,
                                                       color=SUAVE[1:])
        wt.freeze_panes = f"A{topo + 1}"
        if linhas:
            wt.auto_filter.ref = (f"A{topo}:{get_column_letter(len(cols))}"
                                  f"{len(linhas) + topo}")
    # (10/11) os cartoes no modelo da RRM (imagem) no RESUMO, ao lado
    if MODELO_CARTAO == "RRM" and rel.get("kpis"):
        try:
            import io                                   # noqa: PLC0415
            from openpyxl.drawing.image import Image as XLImg  # noqa: PLC0415
            ks = rel["kpis"]
            im = imagem_cartoes_rrm(
                [spec_do_kpi(k, _estados_do_rel(rel, k)) for k in ks],
                _por_linha_rrm(len(ks)), 1400)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            buf.seek(0)
            xi = XLImg(buf)
            xi.anchor = "E5"
            ws.add_image(xi)
        except Exception:                               # noqa: BLE001
            pass
    wb.save(caminho)
    return caminho


def pdf_disponivel() -> bool:
    try:
        import reportlab                              # noqa: F401,PLC0415
        return True
    except ImportError:
        return False


def exportar_pdf(rel: dict, caminho, max_linhas: int = 1500) -> Path:
    """
    O relatorio num PDF A4 deitado. A 1a pagina tem os cartoes e os
    graficos; CADA TABELA comeca numa pagina nova, com o cabecalho e os
    numeros dela - para a assistente imprimir e mandar so a que interessa.
    Sem o reportlab instalado, grava um .html com o mesmo conteudo.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not pdf_disponivel():
        return _exportar_html(rel, caminho.with_suffix(".html"), max_linhas)
    if rel.get("estilo") == "bap":
        return _exportar_pdf_bap(rel, caminho, max_linhas)
    from reportlab.lib import colors                   # noqa: PLC0415
    from reportlab.lib.pagesizes import A4, landscape  # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle    # noqa: PLC0415
    from reportlab.lib.units import mm                 # noqa: PLC0415
    from reportlab.platypus import (KeepTogether, PageBreak,  # noqa: PLC0415
                                    Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    def cor(h):
        return colors.HexColor(h)
    est_tit = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17,
                             leading=21, textColor=cor(TEXTO))
    est_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5,
                             leading=11, textColor=cor(SUAVE))
    est_aviso = ParagraphStyle("av", parent=est_sub, textColor=cor(AMARELO))
    est_sec = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13,
                             leading=16, spaceAfter=2, textColor=cor(TEXTO))
    est_graf = ParagraphStyle("g", fontName="Helvetica-Bold", fontSize=9.5,
                              leading=12, textColor=cor(TEXTO))
    est_cel = ParagraphStyle("c", fontName="Helvetica", fontSize=7, leading=8.5,
                             textColor=cor(TEXTO))
    est_cel_p = ParagraphStyle("cp", fontName="Helvetica", fontSize=6,
                               leading=7.2, textColor=cor(TEXTO))
    est_kpi = ParagraphStyle("k", fontName="Helvetica", fontSize=7, leading=9)
    pag = landscape(A4)
    doc = SimpleDocTemplate(str(caminho), pagesize=pag,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=17 * mm, bottomMargin=13 * mm,
                            title=rel.get("titulo", "Relatório BAP"),
                            author=NOME_MARCA)
    largura = pag[0] - 28 * mm

    def cartoes(kpis, compacto=False):
        """Os numeros em blocos cinza-claro, separados por espaco branco.
        compacto: numero menor e menos respiro (o layout enxuto).
        (10/11) MODELO_CARTAO RRM: os cartoes iguais aos da tela (faixa,
        circulos, comparacao e barras por estado), como imagem."""
        if MODELO_CARTAO == "RRM" and kpis:
            try:
                import io                               # noqa: PLC0415
                from reportlab.platypus import Image as RLImg  # noqa: PLC0415
                im = imagem_cartoes_rrm(
                    [spec_do_kpi(k, _estados_do_rel(rel, k)) for k in kpis],
                    _por_linha_rrm(len(kpis)), 2400)
                buf = io.BytesIO()
                im.save(buf, "PNG")
                buf.seek(0)
                alt = largura * im.height / im.width
                return [RLImg(buf, width=largura, height=alt), Spacer(1, 6)]
            except Exception:                           # noqa: BLE001
                pass
        saida = []
        por = 8 if compacto and len(kpis) <= 8 else 6   # enxuto: 1 linha so
        t_rot, t_val, t_det, lead = ((6.5, 11, 6, 12.5) if compacto
                                     else (7, 13, 6.5, 15))
        for i in range(0, len(kpis), por):
            fatia = kpis[i:i + por]
            cel = []
            for k in fatia:
                det = (f"<br/><font size={t_det} color='{SUAVE}'>"
                       f"{k['detalhe']}</font>") if k.get("detalhe") else ""
                cel.append(Paragraph(
                    f"<font size={t_rot} color='{SUAVE}'>"
                    f"{_rotulo(k['rotulo'])}</font><br/>"
                    f"<font size={t_val} "
                    f"color='{CORES.get(k.get('cor'), TEXTO)}'>"
                    f"<b>{k['valor']}</b></font>{det}",
                    ParagraphStyle("kk", parent=est_kpi, leading=lead)))
            t = Table([cel], colWidths=[largura / por] * len(fatia),
                      hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), cor("#F4F5F3")),
                ("LINEAFTER", (0, 0), (-2, -1), 4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4 if compacto else 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if compacto else 7)]))
            saida += [t, Spacer(1, 5)]
        return saida

    sub = " · ".join(x for x in (rel.get("subtitulo", ""),
                                 rel.get("filtro_texto", "")) if x)
    tabelas = rel.get("tabelas", [])
    graficos = rel.get("graficos", [])
    # LAYOUT ENXUTO: so uma tabela "compacta", sem cartoes nem graficos do
    # relatorio (exportar a aba atual) -> um cabecalho so, o da tabela
    unica = (len(tabelas) == 1 and not graficos and not rel.get("kpis")
             and (tabelas[0].get("pdf") or {}).get("compacto"))
    hist = [] if unica else [Paragraph(rel.get("titulo", ""), est_tit)]
    if sub and not unica:
        hist.append(Paragraph(sub, est_sub))
    if not unica:
        hist.append(Spacer(1, 4 if rel.get("uma_pagina") else 8))
    # (03/11) uma_pagina: o fechamento do RH (gerente, supervisores e
    # vendedores) numa folha so - cartoes enxutos e menos respiro
    uma = bool(rel.get("uma_pagina"))
    if uma:
        est_sec = ParagraphStyle("h1", parent=est_sec, fontSize=11,
                                 leading=13, spaceAfter=0)
    hist += cartoes(rel.get("kpis", []), compacto=uma)
    for aviso in [] if unica else rel.get("avisos", []):
        hist.append(Paragraph(aviso, est_aviso))
    meia = (largura - 8 * mm) / 2
    pares = []
    for g in graficos:
        if g.get("largo") or len(graficos) == 1:
            if pares:
                hist.append(_par_pdf(pares, meia, est_graf, cor, mm))
                pares = []
            hist.append(Spacer(1, 10))
            hist.append(KeepTogether([Paragraph(g["titulo"], est_graf),
                                      Spacer(1, 4),
                                      _grafico_pdf(g, largura, 46 * mm, cor)]))
        else:
            pares.append(g)
            if len(pares) == 2:
                hist.append(_par_pdf(pares, meia, est_graf, cor, mm))
                pares = []
    if pares:
        hist.append(_par_pdf(pares, meia, est_graf, cor, mm))
    seguidas = rel.get("tabelas_seguidas")     # todas na mesma pagina
    for n, t in enumerate(tabelas):
        if seguidas:
            hist.append(Spacer(1, 5 if uma else 12))
        elif n or graficos or rel.get("kpis"):
            hist.append(PageBreak())
        linhas = t.get("linhas_visiveis", t["linhas"])
        sobra = ""
        if len(linhas) > max_linhas:
            sobra = f"{max_linhas} de {len(linhas)} linhas"
            linhas = linhas[:max_linhas]
        opc = t.get("pdf") or {}
        compacto = bool(opc.get("compacto"))
        mostra = [j for j, c in enumerate(t["colunas"])
                  if not c.get("oculta") and not c.get("pdf_oculta")]
        # coluna com o MESMO valor em todas as linhas sai da tabela e vai
        # para a linha de cima (Filial BELEM · Curva A ...)
        fixos, sairam = [], set()
        todas = t.get("linhas_visiveis", t["linhas"])    # antes do corte
        for nome_c in (opc.get("colapsa") or ()) if todas else ():
            j = next((j for j in mostra
                      if t["colunas"][j]["nome"] == nome_c), None)
            if j is None:
                continue
            vals = {l[j] if j < len(l) else None for l in todas}
            if len(vals) == 1:
                tipo_c = t["colunas"][j].get("tipo", "texto")
                mostra.remove(j)
                sairam.add(nome_c)
                v_ = formatar(next(iter(vals)), tipo_c)
                # (08/10) o nome do PDF quando tem (VENDEDOR PLANNER -> Vendedor)
                nome_c = t["colunas"][j].get("pdf_nome") or nome_c
                rot_ = nome_c if nome_c == "UF" else nome_c.capitalize()
                # "Semana 2" (nao "Semana Semana 2"); "UF PA"
                fixos.append(v_ if v_.upper().startswith(nome_c.upper())
                             else f"{rot_} {v_}")
        filtro_t = t.get("filtro_texto", "")
        if sairam and filtro_t:        # o filtro que ja virou "fixo" sai
            resto = [x for x in filtro_t.replace("Filtro: ", "", 1)
                     .split(" · ") if x.split(":")[0] not in sairam]
            filtro_t = ("Filtro: " + " · ".join(resto)) if resto else ""
        if compacto:
            if unica:
                hist.append(Paragraph(
                    f"<font color='{VERDE_ESCURO}'><b>"
                    f"{rel.get('titulo', '').upper()}</b></font>",
                    ParagraphStyle("kick", parent=est_sub, fontSize=7,
                                   leading=9)))
                hist.append(Spacer(1, 1))
            hist.append(Paragraph(t["titulo"], ParagraphStyle(
                "hc", parent=est_sec, fontSize=15, leading=18)))
            cont = opc.get("contagem")
            meta_t = " · ".join(x for x in (
                "" if (seguidas or unica) else rel.get("titulo", ""),
                *fixos, filtro_t,
                rel.get("subtitulo", "") if unica else "",
                f"{br(len(todas))} {cont}" if cont else "", sobra) if x)
        else:
            hist.append(Paragraph(t["titulo"], est_sec))
            meta_t = " · ".join(x for x in (
                "" if seguidas else rel.get("titulo", ""),
                *fixos, filtro_t, sobra) if x)
        if meta_t:
            hist.append(Paragraph(meta_t, est_sub))
        if unica:                       # o aviso vem depois do titulo
            for aviso in rel.get("avisos", []):
                hist.append(Paragraph(aviso, est_aviso))
        hist.append(Spacer(1, 6))
        if t.get("kpis_visiveis"):
            hist += cartoes(t["kpis_visiveis"], compacto)
            hist.append(Spacer(1, 2))
        cols = [t["colunas"][j] for j in mostra]
        linhas = [[l[j] if j < len(l) else None for j in mostra]
                  for l in linhas]
        grupos = t.get("grupos")       # [(rotulo, quantas colunas)]
        if opc.get("grupos"):          # so no PDF: [(rotulo, [nomes])]
            grupo_de = {n_: rot_g for rot_g, ns_ in opc["grupos"]
                        for n_ in ns_}
            grupos = []
            for c in cols:
                g_ = grupo_de.get(c["nome"], "")
                if grupos and grupos[-1][0] == g_:
                    grupos[-1] = (g_, grupos[-1][1] + 1)
                else:
                    grupos.append((g_, 1))
        elif grupos and len(mostra) != len(t["colunas"]):
            vis, j0, novos = set(mostra), 0, []
            for rot_g, n_g in grupos:  # o grupo conta so as que aparecem
                n_v = sum(1 for j in range(j0, j0 + n_g) if j in vis)
                if n_v:
                    novos.append((rot_g, n_v))
                j0 += n_g
            grupos = novos
        est = est_cel_p if len(cols) > (16 if grupos else 14) else est_cel
        if opc.get("corpo"):           # letra do corpo pedida
            tam = float(opc["corpo"])
            est = ParagraphStyle("cx", parent=est_cel, fontSize=tam,
                                 leading=tam + 1.3)
        dados = [[(c.get("pdf_nome") or c.get("curto") or c["nome"])
                  if grupos else c["nome"] for c in cols]]
        for linha in linhas:
            dados.append([formatar(v, c.get("tipo", "texto"))
                          for v, c in zip(linha, cols)])
        vis = t.get("linhas_visiveis")
        tem_total = bool(t.get("total")) and (
            vis is None or len(vis) == len(t["linhas"])
            or t.get("total_vale"))
        if tem_total:
            tot_v = [t["total"][j] if j < len(t["total"]) else None
                     for j in mostra]
            dados.append([formatar(v, c.get("tipo", "texto"))
                          for v, c in zip(tot_v, cols)])
        if tem_total and compacto and "TOTAL" not in dados[-1]:
            dados[-1][0] = "TOTAL"     # a coluna do TOTAL subiu para o titulo
        if opc.get("sem_rs"):          # o R$ vai no titulo, nao em cada valor
            dados = [dados[0]] + [[str(v).replace("R$ ", "") for v in l]
                                  for l in dados[1:]]
        tipos_c = [c.get("tipo", "texto") for c in cols]
        if opc.get("nome_curto"):      # PAULO AUGUSTO M. NOVO FILHO -> PAULO FILHO
            liga = {"DA", "DE", "DO", "DAS", "DOS", "E"}
            for j, c in enumerate(cols):
                if c["nome"] not in opc["nome_curto"]:
                    continue
                for lin in dados[1:]:
                    ps_ = [w for w in str(lin[j]).split() if w not in liga]
                    if len(ps_) > 2 and not str(lin[j]).startswith("("):
                        lin[j] = f"{ps_[0]} {ps_[-1]}"
        if opc.get("data_curta"):      # 24/07/2026 -> 24/07/26
            for lin in dados[1:]:
                for j, tp in enumerate(tipos_c):
                    v = str(lin[j])
                    if tp == "data" and len(v) == 10 and v[2] == "/":
                        lin[j] = v[:6] + v[8:]
        if opc.get("traco_zero"):      # zero vira um traco cinza
            import re as _re                            # noqa: PLC0415
            for lin in dados[1:]:
                for j, tp in enumerate(tipos_c):
                    if tp not in ("texto", "data", "dia") and _re.fullmatch(
                            r"-?(R\$ )?0(,0+)?%?", str(lin[j]).strip()):
                        lin[j] = "—"
        tam_c = opc.get("cab")
        while True:
            # no enxuto, se nem o minimo couber, a letra diminui (ate 5)
            # em vez de quebrar numero e titulo no meio
            apertou = []
            larg = _larguras_pdf(
                dados, cols, largura, est.fontSize, cab_inteiro=compacto,
                tam_cab=tam_c if compacto else None,
                inteiras={j for j, c in enumerate(cols)
                          if c["nome"] in (opc.get("inteiras") or ())},
                corta_texto=(bool(opc.get("sem_quebra"))
                             or bool(opc.get("quebra"))) and compacto,
                aperto=apertou,
                quebra={j for j, c in enumerate(cols)
                         if c["nome"] in (opc.get("quebra") or ())})
            if not (compacto and apertou and est.fontSize > 5.05):
                break
            novo_t = round(est.fontSize - 0.3, 2)
            est = ParagraphStyle("cx", parent=est_cel, fontSize=novo_t,
                                 leading=novo_t + 1.3)
            tam_c = round((tam_c or novo_t) - 0.3, 2)
        if all(c.get("pdf_larg") for c in cols):
            # TODAS com largura FIXA: as colunas ficam exatamente uma
            # embaixo da outra em todas as tabelas do PDF
            larg = [float(c["pdf_larg"]) for c in cols]
        elif all(c.get("pdf_larg") for c in cols
                 if c.get("tipo", "texto") != "texto"):
            # largura FIXA para os numeros (as colunas ficam uma embaixo da
            # outra em todas as tabelas); o texto divide o que sobra
            fixo = sum(c["pdf_larg"] for c in cols
                       if c.get("tipo", "texto") != "texto")
            txt = [c for c in cols if c.get("tipo", "texto") == "texto"]
            peso = sum(c.get("largura", 110) for c in txt) or 1
            sobra = max(largura - fixo, 60)
            larg = [c["pdf_larg"] if c.get("tipo", "texto") != "texto"
                    else sobra * c.get("largura", 110) / peso for c in cols]
        if opc.get("sem_quebra") or (compacto and opc.get("quebra")):
            # o texto que nao cabe e cortado (...); so as colunas de
            # "quebra" (endereco, ultimo produto) descem para outra linha
            from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa
            pad_ = float(opc.get("pad", 3))
            for j, c in enumerate(cols):
                if c.get("tipo", "texto") != "texto" or \
                        c["nome"] in (opc.get("quebra") or ()):
                    continue
                cabe = larg[j] - 2 * pad_ - 1
                # no enxuto so a coluna em destaque sai em negrito
                fonte = ("Helvetica" if compacto and c["nome"] not in
                         (opc.get("destaque") or ()) else "Helvetica-Bold")
                for lin in dados[1:]:
                    v = str(lin[j])
                    if stringWidth(v, fonte, est.fontSize) > cabe:
                        while v and stringWidth(v + "…", fonte,
                                                est.fontSize) > cabe:
                            v = v[:-1]
                        lin[j] = v.rstrip() + "…"
        cores = None
        if t.get("cores_celulas"):      # [{indice da coluna: cor}] por linha
            vis_l = t.get("linhas_visiveis", t["linhas"])
            por_linha = {id(l): c_ for l, c_ in zip(t["linhas"],
                                                     t["cores_celulas"])}
            cores = [{}] + [{mostra.index(j): c_ for j, c_ in
                             por_linha.get(id(l), {}).items() if j in mostra}
                            for l in vis_l[:len(dados) - 1]]
            if tem_total:
                cores.append({mostra.index(j): c_ for j, c_ in
                              (t.get("cores_total") or {}).items()
                              if j in mostra})
        destaque = {j for j, c in enumerate(cols)
                    if c["nome"] in (opc.get("destaque") or ())}
        tab_pdf = _tabela_pdf(dados, larg, cor, est, largura,
                              [c.get("tipo", "texto") for c in cols],
                              total=tem_total, grupos=grupos, cores=cores,
                              verticais=opc.get("verticais", False),
                              tam_cab=tam_c, pad=opc.get("pad", 3),
                              zebra=opc.get("zebra", False),
                              negrito=destaque,
                              traco_suave=opc.get("traco_zero", False))
        if seguidas and len(dados) < 40:     # a tabela nao se parte
            titulo_t = hist.pop()
            while not isinstance(titulo_t, Paragraph):
                titulo_t = hist.pop()
            hist.append(KeepTogether([titulo_t, Spacer(1, 2 if uma else 6),
                                      tab_pdf]))
        else:
            hist.append(tab_pdf)
        if t.get("nota_pdf"):          # a explicacao de baixo da tabela
            hist.append(Spacer(1, 4))
            hist.append(Paragraph(t["nota_pdf"], ParagraphStyle(
                "np", parent=est_sub, textColor=cor(VERMELHO))))
    if rel.get("assinaturas"):
        hist.append(Spacer(1, 2 if uma else 34))
        n_a = len(rel["assinaturas"])
        cel = [Paragraph(f"<font color='{SUAVE}'>____________________________"
                         f"<br/>{a}</font>", ParagraphStyle(
                             "as", parent=est_sub, alignment=1))
               for a in rel["assinaturas"]]
        hist.append(KeepTogether([Table([cel], colWidths=[largura / n_a] * n_a,
                                        hAlign="LEFT")]))

    area = CABECALHO_PDF        # o mesmo em todos os PDFs exportados
    gerado = f"{datetime.now():%d/%m/%Y %H:%M}"

    def moldura(canvas, d):
        canvas.saveState()
        canvas.setFillColor(cor(VERDE))
        canvas.rect(0, pag[1] - 2 * mm, pag[0], 2 * mm, stroke=0, fill=1)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(cor(VERDE_ESCURO))
        canvas.drawString(14 * mm, pag[1] - 9 * mm, f"{NOME_MARCA}  ·  {area}")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(cor(SUAVE))
        canvas.drawRightString(pag[0] - 14 * mm, pag[1] - 9 * mm, gerado)
        canvas.setStrokeColor(cor(GRADE))
        canvas.setLineWidth(0.5)
        canvas.line(14 * mm, 9 * mm, pag[0] - 14 * mm, 9 * mm)
        canvas.drawString(14 * mm, 5.5 * mm, rel.get("titulo", ""))
        canvas.drawRightString(pag[0] - 14 * mm, 5.5 * mm, f"{d.page}")
        canvas.restoreState()
    doc.build(hist, onFirstPage=moldura, onLaterPages=moldura)
    return caminho


def _par_pdf(graficos, meia, est_graf, cor, mm):
    """Dois graficos lado a lado (uma linha da capa)."""
    from reportlab.platypus import (Paragraph, Spacer, Table,  # noqa: PLC0415
                                    TableStyle)
    cel = [[Paragraph(g["titulo"], est_graf), Spacer(1, 4),
            _grafico_pdf(g, meia, 44 * mm, cor)] for g in graficos]
    if len(cel) == 1:
        cel.append("")
    t = Table([cel], colWidths=[meia + 8 * mm, meia], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    return t


def _grafico_pdf(g, largura, altura, cor):
    """Colunas finas, grade clara, legenda so com 2+ series."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart  # noqa
    from reportlab.graphics.shapes import Drawing, Rect, String       # noqa
    d = Drawing(largura, altura)
    series = g["series"]
    ns, n = len(series), max(len(g["rotulos"]), 1)
    bc = VerticalBarChart()
    bc.x, bc.y = 40, 16
    bc.width, bc.height = largura - 50, altura - (34 if ns > 1 else 26)
    bc.data = [[float(v or 0) for v in s["valores"]] for s in series]
    bc.categoryAxis.categoryNames = [str(r)[:12] for r in g["rotulos"]]
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.valueAxis.labels.fontName = "Helvetica"
    bc.barLabels.fontName = "Helvetica"
    bc.categoryAxis.labels.fillColor = cor(SUAVE)
    bc.categoryAxis.strokeColor = cor(CINZA_LINHA)
    bc.categoryAxis.strokeWidth = 0.5
    bc.categoryAxis.visibleTicks = 0
    bc.categoryAxis.labelAxisMode = "low"      # rotulos embaixo, mesmo com negativo
    bc.valueAxis.labels.fontSize = 6.5
    bc.valueAxis.labels.fillColor = cor(SUAVE)
    bc.valueAxis.visibleAxis = 0
    bc.valueAxis.visibleTicks = 0
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = cor(GRADE)
    bc.valueAxis.gridStrokeWidth = 0.5
    bc.valueAxis.maximumTicks = 5
    bc.valueAxis.valueMin = min(0, min((min(x) for x in bc.data if x),
                                       default=0))
    fmt = {"pct": lambda v: f"{br(v)}%"}.get(g.get("formato"),
                                              lambda v: _compacto(v))
    bc.valueAxis.labelTextFormat = fmt
    # coluna fina: no maximo ~9 mm, o resto da faixa e respiro
    faixa = bc.width / n
    barra = min(25.0, faixa * 0.6 / ns)
    bc.barWidth = barra
    bc.barSpacing = 1.5
    bc.groupSpacing = max(faixa - barra * ns - 1.5 * (ns - 1), 2)
    if (ns == 1 and n <= 16) or (ns == 2 and n <= 8):
        bc.barLabelFormat = lambda v: fmt(v) if v else ""
        bc.barLabels.fontSize = 6
        bc.barLabels.fillColor = cor(TEXTO)
        bc.barLabels.nudge = 5
    for i, s in enumerate(series):
        bc.bars[i].fillColor = cor(s.get("cor", VERDE))
        bc.bars[i].strokeColor = None
        bc.bars[i].strokeWidth = 0
        for j, v in enumerate(bc.data[i]):
            if v < 0:
                bc.bars[(i, j)].fillColor = cor(s.get("cor_negativo", VERMELHO))
                bc.bars[(i, j)].strokeColor = None
    if g.get("linhas"):
        # (15/10) as series em LINHA no mesmo eixo (Farol de Preco)
        from reportlab.graphics.charts.linecharts import \
            HorizontalLineChart                         # noqa: PLC0415
        from reportlab.graphics.widgets.markers import \
            makeMarker                                  # noqa: PLC0415
        lc = HorizontalLineChart()
        lc.x, lc.y, lc.width, lc.height = bc.x, bc.y, bc.width, bc.height
        lc.data = bc.data
        lc.categoryAxis.categoryNames = bc.categoryAxis.categoryNames
        lc.categoryAxis.labels.fontSize = 6.5
        lc.categoryAxis.labels.fillColor = cor(SUAVE)
        lc.categoryAxis.strokeColor = cor(CINZA_LINHA)
        lc.categoryAxis.visibleTicks = 0
        lc.valueAxis.labels.fontSize = 6.5
        lc.valueAxis.labels.fillColor = cor(SUAVE)
        lc.valueAxis.visibleAxis = 0
        lc.valueAxis.visibleTicks = 0
        lc.valueAxis.visibleGrid = 1
        lc.valueAxis.gridStrokeColor = cor(GRADE)
        lc.valueAxis.gridStrokeWidth = 0.5
        lc.valueAxis.labelTextFormat = fmt
        for i, s in enumerate(series):
            lc.lines[i].strokeColor = cor(s.get("cor", VERDE))
            lc.lines[i].strokeWidth = 1.5
            lc.lines[i].symbol = makeMarker("FilledCircle", size=3)
            lc.lines[i].symbol.fillColor = cor(s.get("cor", VERDE))
        bc = lc
    d.add(bc)
    if ns > 1:                                  # legenda a direita, no alto
        x = largura - 4
        for s in reversed(series):
            tw = len(s["nome"]) * 3.4
            d.add(String(x, altura - 7, s["nome"], fontName="Helvetica",
                         fontSize=6.5, fillColor=cor(SUAVE), textAnchor="end"))
            d.add(Rect(x - tw - 9, altura - 7.5, 6, 6, strokeColor=None,
                       fillColor=cor(s.get("cor", VERDE))))
            x -= tw + 22
    return d


def _larguras_pdf(dados, cols, largura, corpo, cab_inteiro=False,
                  tam_cab=None, inteiras=(), corta_texto=False,
                  aperto=None, quebra=()):
    """
    Largura de cada coluna medida pelo conteudo (fonte de verdade do
    PDF): numero nunca quebra; se nao couber, quem cede e o texto, que
    quebra em mais linhas. O titulo quebra por palavra (cab_inteiro: o
    titulo inteiro numa linha so; tam_cab: a letra do titulo, quando e
    outra; inteiras: indices das colunas de texto que nunca encolhem;
    corta_texto: o texto longo pode ser cortado com "…" em vez de quebrar,
    entao a coluna de texto encolhe ate ~7 letras; aperto: uma lista
    que recebe True quando nem o minimo de cada coluna coube).
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: PLC0415
    tipos = [c.get("tipo", "texto") for c in cols]
    pad = 7.0                                 # 3 + 3 de respiro + folga
    precisa, minimo = [], []
    for j, tp in enumerate(tipos):
        partes = ([str(dados[0][j])] if cab_inteiro
                  else str(dados[0][j]).split())
        cab = max((stringWidth(w, "Helvetica-Bold", tam_cab or corpo)
                   for w in partes), default=10)
        vals = [stringWidth(str(l[j]), "Helvetica", corpo)
                for l in dados[1:] if j < len(l)]
        maior = max(vals, default=10)
        if tp == "texto":
            pal = max((stringWidth(w, "Helvetica", corpo) for l in dados[1:]
                       if j < len(l) for w in str(l[j]).split()), default=10)
            if j in inteiras:          # o codigo do produto: nunca corta
                minimo.append(max(cab, maior) + pad)
            elif j in quebra:          # quebra em linhas (endereco...), mas
                maior = min(maior, corpo * 24)     # com largura para ~2
                minimo.append(max(cab, pal, min(maior, corpo * 16)) + pad)
            elif quebra:               # a tabela tem colunas que quebram:
                maior = min(maior, corpo * 15)     # as outras ficam numa
                minimo.append(max(cab, maior) + pad)  # linha (ate ~15)
            elif corta_texto:
                minimo.append(max(cab, min(maior, corpo * 7)) + pad)
                maior = min(maior, corpo * 22)
            else:
                minimo.append(max(cab, pal) + pad)
                maior = min(maior, corpo * 22)
        else:
            minimo.append(max(cab, maior) + pad)
        precisa.append(max(cab, maior) + pad)
    total = sum(precisa)
    if total <= largura:                      # sobra: vai para o texto
        txt = [j for j, tp in enumerate(tipos) if tp == "texto"] or \
            list(range(len(tipos)))
        for j in txt:
            precisa[j] += (largura - total) / len(txt)
        return precisa
    falta = total - largura
    folga = sum(precisa[j] - minimo[j] for j in range(len(tipos)))
    if folga >= falta:                        # encolhe ate o minimo de cada
        return [p_ - (p_ - m) * falta / folga
                for p_, m in zip(precisa, minimo)]
    if aperto is not None:
        aperto.append(True)
    return [x * largura / total for x in precisa]


def _tabela_pdf(dados, larguras, cor, est, largura_total, tipos=None,
                total=False, grupos=None, cores=None, verticais=False,
                tam_cab=None, pad=3, zebra=False, negrito=(),
                traco_suave=False):
    """cores: [{coluna: cor do texto}] por linha (0 = cabecalho).
    verticais: linhas verticais entre as colunas no lugar das horizontais.
    tam_cab: tamanho da letra do cabecalho. zebra: uma linha sim, outra
    nao, cinza bem claro. negrito: indices das colunas em negrito (a que
    ordena a tabela). traco_suave: o "—" (zero) em cinza."""
    from reportlab.lib.styles import ParagraphStyle    # noqa: PLC0415
    from reportlab.lib import colors                   # noqa: PLC0415
    from reportlab.platypus import Paragraph, Table, TableStyle  # noqa: PLC0415
    tipos = tipos or ["texto"] * len(dados[0])
    direita = ParagraphStyle("d", parent=est, alignment=2)
    cab = ParagraphStyle("hb", parent=est, fontName="Helvetica-Bold",
                         textColor=cor(SUAVE))
    if tam_cab:
        cab = ParagraphStyle("hbp", parent=cab, fontSize=tam_cab,
                             leading=tam_cab + 1.4)
    cab_d = ParagraphStyle("hd", parent=cab, alignment=2)
    tot = ParagraphStyle("tb", parent=est, fontName="Helvetica-Bold")
    tot_d = ParagraphStyle("td", parent=tot, alignment=2)
    corpo = []
    ult = len(dados) - 1
    for n, linha in enumerate(dados):
        lin = []
        for v, tp in zip(linha, tipos):
            num = tp not in ("texto", "data", "dia")
            if n == 0:
                e = cab_d if num else cab
            elif total and n == ult:
                e = tot_d if num else tot
            else:
                e = direita if num else est
            c_ = (cores[n].get(len(lin)) if cores and n < len(cores)
                  else None)
            txt = f"<font color='{c_}'><b>{v}</b></font>" if c_ and v != "" \
                else str(v)
            if n and traco_suave and txt == "—":
                txt = f"<font color='{CINZA_LINHA}'>—</font>"
            elif n and len(lin) in negrito and not c_:
                txt = f"<b>{txt}</b>"
            lin.append(Paragraph(txt, e))
        corpo.append(lin)
    extra = []
    if grupos:                 # uma linha de cima juntando as colunas
        g_est = ParagraphStyle("gr", parent=cab, alignment=1,
                               textColor=cor(VERDE_ESCURO),
                               fontSize=(tam_cab or est.fontSize) + 0.5,
                               leading=(tam_cab or est.fontSize) + 2)
        linha_g, j = [], 0
        for rot, n_ in grupos:
            linha_g += [Paragraph(rot, g_est)] + [""] * (n_ - 1)
            if n_ > 1:
                extra.append(("SPAN", (j, 0), (j + n_ - 1, 0)))
            if rot:
                extra.append(("LINEBELOW", (j, 0), (j + n_ - 1, 0), 0.75,
                              cor(VERDE)))
            j += n_
        corpo.insert(0, linha_g)
        ult += 1
    t = Table(corpo, colWidths=larguras, repeatRows=2 if grupos else 1,
              hAlign="LEFT")
    h = 1 if grupos else 0
    linhas_grade = ([("LINEAFTER", (0, h), (-2, -1), 0.4, cor(CINZA_LINHA))]
                    if verticais else
                    [("LINEBELOW", (0, 1), (-1, -1), 0.25, cor(GRADE))])
    estilo = extra + linhas_grade + [
              ("BACKGROUND", (0, h), (-1, h), cor(CAB_TABELA)),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
              ("LEFTPADDING", (0, 0), (-1, -1), pad),
              ("RIGHTPADDING", (0, 0), (-1, -1), pad),
              ("TOPPADDING", (0, h), (-1, h), 4),
              ("BOTTOMPADDING", (0, h), (-1, h), 4)]
    if zebra and ult > h + 1:
        estilo.append(("ROWBACKGROUNDS", (0, h + 1),
                       (-1, ult - (1 if total else 0)),
                       [colors.white, cor("#F5F7F4")]))
    if total:
        estilo += [("LINEABOVE", (0, ult), (-1, ult), 0.75, cor(SUAVE)),
                   ("BACKGROUND", (0, ult), (-1, ult), cor("#F7F8F6"))]
    t.setStyle(TableStyle(estilo))
    return t


def _exportar_html(rel, caminho, max_linhas):
    import html                                         # noqa: PLC0415
    e = html.escape
    p = [f"<html><head><meta charset='utf-8'><title>{e(rel.get('titulo', ''))}"
         f"</title><style>body{{font-family:Segoe UI,Arial;background:{FUNDO};"
         f"color:{TEXTO};margin:24px}}.k{{display:inline-block;background:#fff;"
         f"border:1px solid {CINZA_LINHA};padding:10px 16px;margin:4px;"
         f"min-width:150px}}.k b{{font-size:22px;display:block}}table{{border-"
         f"collapse:collapse;background:#fff;font-size:11px;margin:8px 0}}"
         f"th{{background:{CINZA_CAB};text-align:left}}th,td{{padding:3px 6px;"
         f"border-bottom:1px solid {CINZA_LINHA}}}</style></head><body>",
         f"<div style='color:{VERDE_ESCURO};font-weight:bold;font-size:11px'>"
         f"{NOME_MARCA} · {e(CABECALHO_PDF)}</div>",
         f"<h1>{e(rel.get('titulo', ''))}</h1><p>{e(rel.get('subtitulo', ''))}</p>"]
    for k in rel.get("kpis", []):
        p.append(f"<div class='k'>{e(k['rotulo'].upper())}<b>{e(k['valor'])}"
                 f"</b>{e(k.get('detalhe', ''))}</div>")
    for t in rel.get("tabelas", []):
        linhas = t.get("linhas_visiveis", t["linhas"])[:max_linhas]
        p.append(f"<h3>{e(t['titulo'])}</h3><table><tr>"
                 + "".join(f"<th>{e(c['nome'])}</th>" for c in t["colunas"])
                 + "</tr>")
        for linha in linhas:
            p.append("<tr>" + "".join(
                f"<td>{e(formatar(v, c.get('tipo', 'texto')))}</td>"
                for v, c in zip(linha, t["colunas"])) + "</tr>")
        p.append("</table>")
    p.append("</body></html>")
    Path(caminho).write_text("\n".join(p), encoding="utf-8")
    return Path(caminho)


# =========================================================================
# O PDF NA CARA DO CATALOGO BAP (parcial de meta e Farol de Metas)
# =========================================================================
# Faixa preta em cima com o logo, faixa verde-clara com o titulo, cartoes
# pretos com o numero em verde, tabelas com cabecalho escuro, o comeco da
# linha em verde-claro e o atingimento pintado (vermelho < 80%, amarelo
# < 100%, verde >= 100%). Fontes: Poppins (a do catalogo, pasta recursos\)
# na marca - faixa, titulos e cartoes; Calibri (a do Windows/Office, numeros
# de mesma largura, nitida em letra pequena) nas tabelas. Sem elas,
# Helvetica.
PRETO_BAP = "#231F20"
GRAFITE_BAP = "#3A3536"
VERDE_BAP = "#59BA61"
VERDE_FAIXA = "#F2FAED"
VERDE_LINHA = "#ECF6E7"
VERDE_CAB = "#E6F4E1"       # o TOTAL das tabelas
CINZA_GRUPO = "#4A4F4C"     # a faixa dos indicadores (FATURAMENTO...)
CINZA_COLUNA = "#E4E7E5"    # o nome das colunas
CINZA_TEXTO = "#2E3330"
VERDE_INICIO = "#F4FAF1"    # o comeco da linha
VERDE_TEXTO = "#1F3B22"
VERDE_NUMERO = "#2F9E44"
ATING_CORES = (("#FDE0DE", "#A3201A"), ("#FFF4D6", "#8A5A00"),
               ("#DDF2DF", "#1E6B2A"))
RECURSOS = Path(__file__).resolve().parent / "SISTEMA BAP" / "recursos"
# O CABECALHO DE TODOS OS PDFs EXPORTADOS (no lugar da area: Vendas e CRM,
# Pre-venda e faturamento...)
CABECALHO_PDF = "APURAÇÃO DE RESULTADO E PROCESSOS"


def _fonte_tabela() -> dict:
    """A letra das tabelas: Calibri (Windows), Carlito (a mesma medida, no
    Linux) ou Helvetica. {"tr": normal, "tb": negrito}."""
    from reportlab.pdfbase import pdfmetrics               # noqa: PLC0415
    from reportlab.pdfbase.ttfonts import TTFont           # noqa: PLC0415
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    opcoes = [("Calibri", win / "calibri.ttf", win / "calibrib.ttf"),
              ("Carlito", RECURSOS / "Carlito-Regular.ttf",
               RECURSOS / "Carlito-Bold.ttf"),
              ("Carlito", Path("/usr/share/fonts/truetype/crosextra/"
                               "Carlito-Regular.ttf"),
               Path("/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"))]
    for nome, r, b in opcoes:
        try:
            if not (r.exists() and b.exists()):
                continue
            ja = pdfmetrics.getRegisteredFontNames()
            if nome not in ja:
                pdfmetrics.registerFont(TTFont(nome, str(r)))
            if nome + "-Bold" not in ja:
                pdfmetrics.registerFont(TTFont(nome + "-Bold", str(b)))
            return {"tr": nome, "tb": nome + "-Bold"}
        except Exception:                                  # noqa: BLE001
            continue
    return {"tr": "Helvetica", "tb": "Helvetica-Bold"}


def _fontes_bap() -> dict:
    """Registra a Poppins (pasta recursos ou do sistema) e a letra das
    tabelas; devolve os nomes."""
    from reportlab.pdfbase import pdfmetrics               # noqa: PLC0415
    from reportlab.pdfbase.ttfonts import TTFont           # noqa: PLC0415
    nomes = {"r": "Helvetica", "m": "Helvetica-Bold", "b": "Helvetica-Bold"}
    lugares = [RECURSOS, Path("/usr/share/fonts/truetype/google-fonts"),
               Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    achou = {}
    for chave, arq in (("r", "Poppins-Regular.ttf"), ("m", "Poppins-Medium.ttf"),
                       ("b", "Poppins-Bold.ttf")):
        for pasta in lugares:
            f = pasta / arq
            if f.exists():
                achou[chave] = f
                break
    if len(achou) == 3:
        try:
            for chave, f in achou.items():
                nome = {"r": "Poppins", "m": "Poppins-Medium",
                        "b": "Poppins-Bold"}[chave]
                if nome not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(nome, str(f)))
                nomes[chave] = nome
        except Exception:                                  # noqa: BLE001
            nomes = {"r": "Helvetica", "m": "Helvetica-Bold",
                     "b": "Helvetica-Bold"}
    nomes.update(_fonte_tabela())
    return nomes


def _cor_do_ating(v):
    if not isinstance(v, (int, float)):
        return None
    return ATING_CORES[0] if v < 80 else ATING_CORES[1] if v < 100 \
        else ATING_CORES[2]


def _exportar_pdf_bap(rel: dict, caminho, max_linhas: int = 1500) -> Path:
    from reportlab.lib import colors                   # noqa: PLC0415
    from reportlab.lib.pagesizes import A4, landscape  # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle    # noqa: PLC0415
    from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: PLC0415
    from reportlab.platypus import (KeepTogether,  # noqa: PLC0415
                                    PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)
    F = _fontes_bap()
    cor = colors.HexColor
    pag = landscape(A4)
    ML = 17.0       # a margem que se ve (o quadro do reportlab tem +6)
    largura = pag[0] - 2 * ML
    doc = SimpleDocTemplate(str(caminho), pagesize=pag, leftMargin=ML - 6,
                            rightMargin=ML - 6, topMargin=50,
                            bottomMargin=34,
                            title=rel.get("titulo", "Relatório BAP"),
                            author=NOME_MARCA)
    logo = RECURSOS / "logo_bap.png"
    faixa = rel.get("faixa") or rel.get("titulo", "").upper()
    area = CABECALHO_PDF        # o mesmo em todos os PDFs exportados

    def moldura(cv, d):
        cv.saveState()
        cv.setFillColor(cor(PRETO_BAP))
        cv.rect(0, pag[1] - 38, pag[0], 38, stroke=0, fill=1)
        x = ML
        if logo.exists():
            try:
                cv.drawImage(str(logo), x, pag[1] - 34, height=30, width=22,
                             preserveAspectRatio=True, mask="auto",
                             anchor="w")
                x += 32
            except Exception:                           # noqa: BLE001
                pass
        cv.setStrokeColor(cor(VERDE_BAP))
        cv.setLineWidth(0.6)
        cv.line(x, pag[1] - 27, x, pag[1] - 11)
        cv.saveState()
        t = cv.beginText(x + 10, pag[1] - 22)
        t.setFont(F["m"], 7.5)
        t.setCharSpace(1.2)
        t.setFillColor(cor(VERDE_BAP))
        t.textLine(faixa)
        cv.drawText(t)
        cv.restoreState()
        cv.saveState()
        t = cv.beginText(0, pag[1] - 22)
        t.setFont(F["r"], 6.5)
        t.setCharSpace(1.4)
        w = stringWidth(area, F["r"], 6.5) + 1.4 * len(area)
        t.setTextOrigin(pag[0] - ML - w, pag[1] - 22)
        t.setFillColor(colors.white)
        t.textLine(area)
        cv.drawText(t)
        cv.restoreState()
        # rodape: linha verde e faixa preta
        cv.setFillColor(cor(VERDE_BAP))
        cv.rect(0, 22, pag[0], 2, stroke=0, fill=1)
        cv.setFillColor(cor(PRETO_BAP))
        cv.rect(0, 0, pag[0], 22, stroke=0, fill=1)
        cv.setFont(F["b"], 6.5)
        cv.setFillColor(colors.white)
        cv.drawString(ML, 8.5, "www.bapautoparts.com.br")
        cv.drawRightString(pag[0] - ML, 8.5, "@bapautoparts")
        cv.setFillColor(cor(VERDE_BAP))
        cv.drawCentredString(pag[0] / 2, 8.5, f"{d.page:02d}")
        cv.setFont(F["r"], 5.5)
        cv.setFillColor(cor("#BDB9BA"))
        cv.drawRightString(pag[0] / 2 - 18, 8.5,
                           f"gerado em {datetime.now():%d/%m/%Y %H:%M}")
        cv.restoreState()

    est = {
        "eyebrow": ParagraphStyle("eb", fontName=F["m"], fontSize=7,
                                  leading=9, textColor=cor("#2F7D32")),
        "titulo": ParagraphStyle("tt", fontName=F["b"], fontSize=19,
                                 leading=23, textColor=cor(PRETO_BAP)),
        "sub": ParagraphStyle("sb", fontName=F["r"], fontSize=7.5,
                              leading=10, textColor=cor("#6B6768")),
        "sec": ParagraphStyle("sc", fontName=F["b"], fontSize=9, leading=11,
                              textColor=cor(PRETO_BAP)),
        "aviso": ParagraphStyle("av", fontName=F["r"], fontSize=6.5,
                                leading=8.5, textColor=cor("#8A5A00")),
        "nota": ParagraphStyle("nt", fontName=F["r"], fontSize=6.5,
                               leading=8.5, textColor=cor("#A3201A")),
        "nota_suave": ParagraphStyle("ns", fontName=F["r"], fontSize=6.5,
                                     leading=8.5, textColor=cor("#6B6768")),
        "assina": ParagraphStyle("as", fontName=F["r"], fontSize=7,
                                 leading=9, textColor=cor("#6B6768"),
                                 alignment=1),
    }

    def legenda():
        leg = [["", "abaixo de 80%", "", "de 80% a 99%", "", "100% ou mais"]]
        lt = Table(leg, colWidths=[10, 60, 10, 60, 10, 60], hAlign="LEFT")
        lt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), cor(ATING_CORES[0][0])),
            ("BACKGROUND", (2, 0), (2, 0), cor(ATING_CORES[1][0])),
            ("BACKGROUND", (4, 0), (4, 0), cor(ATING_CORES[2][0])),
            ("FONT", (0, 0), (-1, -1), F["r"], 6),
            ("TEXTCOLOR", (0, 0), (-1, -1), cor("#6B6768")),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        return [Spacer(1, 10), Paragraph("ATINGIMENTO", est["eyebrow"]),
                Spacer(1, 2), lt]

    def assinaturas():
        n_a = len(rel["assinaturas"])
        w = largura / n_a
        # a linha de cada assinatura com folga entre elas
        tb_ = Table([[Table([[Paragraph(a_, est["assina"])]],
                            colWidths=[w - 48], style=TableStyle([
                                ("LINEABOVE", (0, 0), (-1, 0), 0.6,
                                 cor(PRETO_BAP)),
                                ("TOPPADDING", (0, 0), (-1, -1), 4)]))
                      for a_ in rel["assinaturas"]]],
                    colWidths=[w] * n_a)
        return [Spacer(1, 42), tb_]
    fecho_feito = False
    hist = []
    # ---- a faixa do titulo
    cab = [[Paragraph(rel.get("eyebrow") or area, est["eyebrow"])],
           [Paragraph(rel.get("titulo_curto") or rel.get("titulo", ""),
                      est["titulo"])],
           [Paragraph(" · ".join(x for x in (rel.get("subtitulo", ""),
                                             rel.get("filtro_texto", ""))
                                 if x), est["sub"])]]
    tb = Table(cab, colWidths=[largura], hAlign="LEFT")
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cor(VERDE_FAIXA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, -1),
                                             (-1, -1), 9),
        ("TOPPADDING", (0, 1), (-1, -1), 1), ("BOTTOMPADDING", (0, 0),
                                              (-1, -2), 1)]))
    hist += [tb, Spacer(1, 8)]
    # ---- os cartoes pretos
    kpis = rel.get("kpis") or []
    # (10/11) MODELO_CARTAO RRM: os cartoes iguais aos da tela (imagem)
    if kpis and MODELO_CARTAO == "RRM":
        try:
            import io                                   # noqa: PLC0415
            from reportlab.platypus import Image as RLImg  # noqa: PLC0415
            im = imagem_cartoes_rrm(
                [spec_do_kpi(k, _estados_do_rel(rel, k)) for k in kpis],
                _por_linha_rrm(len(kpis)), 2400)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            buf.seek(0)
            hist += [RLImg(buf, width=largura,
                           height=largura * im.height / im.width),
                     Spacer(1, 6)]
            kpis = []
        except Exception:                               # noqa: BLE001
            pass
    if kpis:
        por = min(len(kpis), 8)
        gap = 5.0
        lw = (largura - gap * (por - 1)) / por
        for i in range(0, len(kpis), por):
            cel = []
            for k in kpis[i:i + por]:
                cor_v = {"alerta": "#C0392B", "atencao": "#B7791F"}.get(
                    k.get("cor"), VERDE_NUMERO)
                mini = []
                if k.get("linhas"):
                    cores_l = {"alerta": ATING_CORES[0][1],
                               "atencao": ATING_CORES[1][1],
                               "ok": ATING_CORES[2][1]}
                    tl = Table([[r_, v_] for r_, v_, _t in k["linhas"]],
                               colWidths=[(lw - 16) * 0.45,
                                          (lw - 16) * 0.55])
                    est_l = [("FONT", (0, 0), (0, -1), F["tr"], 6.4),
                             ("FONT", (1, 0), (1, -1), F["tb"], 6.6),
                             ("TEXTCOLOR", (0, 0), (0, -1), cor("#6B6768")),
                             ("TEXTCOLOR", (1, 0), (1, -1), cor(PRETO_BAP)),
                             ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                             ("LINEABOVE", (0, 0), (-1, 0), 0.4,
                              cor("#E3EFDF")),
                             ("LINEBELOW", (0, 0), (-1, -2), 0.3,
                              cor("#F0F4EE")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 1.6),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]
                    for n_, (_r, _v, t_) in enumerate(k["linhas"]):
                        if t_ in cores_l:
                            est_l.append(("TEXTCOLOR", (1, n_), (1, n_),
                                          cor(cores_l[t_])))
                    tl.setStyle(TableStyle(est_l))
                    mini = [[Spacer(1, 3)], [tl]]
                cel.append(Table(
                    [[Paragraph(f"<font color='#6B6768'>{k['rotulo']}</font>",
                                ParagraphStyle("kr", fontName=F["r"],
                                               fontSize=6.3, leading=8))],
                     [Paragraph(f"<font color='{cor_v}'>{k['valor']}</font>",
                                ParagraphStyle("kv", fontName=F["b"],
                                               fontSize=12.5, leading=15))],
                     [Paragraph(f"<font color='#8A8687'>"
                                f"{k.get('detalhe') or '&nbsp;'}</font>",
                                ParagraphStyle("kd", fontName=F["r"],
                                               fontSize=5.8, leading=7.5))]]
                    + mini,
                    colWidths=[lw], style=TableStyle([
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.7, cor("#D7EBD1")),
                        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, 0), 6),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
                        ("TOPPADDING", (0, 1), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -2), 0)])))
                cel.append("")
            cel = cel[:-1]
            larg = []
            for j in range(len(cel)):
                larg.append(lw if j % 2 == 0 else gap)
            t = Table([cel], colWidths=larg, hAlign="LEFT")
            t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            hist += [t, Spacer(1, 6)]
    for aviso in rel.get("avisos", []):
        hist.append(Paragraph(aviso, est["aviso"]))
    graficos = rel.get("graficos", [])
    if graficos:
        meia = (largura - 20) / 2
        pares = [graficos[i:i + 2] for i in range(0, len(graficos), 2)]
        for par in pares:
            hist.append(_par_pdf(par, meia, est["sec"], cor, 2.83))
    # ---- as tabelas
    tem_ating = False
    for t in rel.get("tabelas", []):
        linhas = t.get("linhas_visiveis", t["linhas"])[:max_linhas]
        titulo = Table([["", Paragraph(t["titulo"].upper(), est["sec"])]],
                       colWidths=[3, largura - 3], hAlign="LEFT")
        titulo.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), cor(VERDE_BAP)),
            ("LEFTPADDING", (1, 0), (1, 0), 6),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        tab, ating = _tabela_bap(t, linhas, F, cor, largura, stringWidth,
                                 colors)
        tem_ating = tem_ating or ating
        bloco = [Spacer(1, 10), titulo, Spacer(1, 4), tab]
        if t.get("nota_pdf"):
            bloco += [Spacer(1, 3), Paragraph(
                t["nota_pdf"], est["nota_suave" if t.get("nota_tom") ==
                                    "suave" else "nota"])]
        # NAO QUEBRAR TABELA ENTRE PAGINAS: a que cabe numa pagina (ate ~36
        # linhas) vai inteira para a pagina seguinte; so a maior (ex.: as
        # notas do mes) continua na outra, com o cabecalho repetido.
        # pdf_pagina: a tabela numa pagina SO DELA (os TOP 30)
        propria = t.get("pdf_pagina") and len(linhas) <= 36
        if (propria or t.get("pdf_quebra_antes")) and hist and \
                not isinstance(hist[-1], PageBreak):
            hist.append(PageBreak())
        if len(linhas) <= 36:
            hist.append(KeepTogether(bloco[1:] if (
                propria or t.get("pdf_quebra_antes")) else bloco))
        else:
            hist += bloco
        if propria:
            hist.append(PageBreak())
        # (08/10) fecho_na_1a: legenda e assinaturas logo depois da 1a
        # tabela (o resumo que o RH assina); o resto vem nas paginas seguintes
        if rel.get("fecho_na_1a") and not fecho_feito:
            fecho_feito = True
            hist += (legenda() if tem_ating else []) + (
                assinaturas() if rel.get("assinaturas") else [])
    if hist and isinstance(hist[-1], PageBreak):
        hist.pop()                  # sem pagina em branco no fim
    if not fecho_feito:
        if tem_ating:
            hist += legenda()
        if rel.get("assinaturas"):
            hist.append(Spacer(1, 30))
            n_a = len(rel["assinaturas"])
            hist.append(Table([[f"____________________________\n{a}"
                                for a in rel["assinaturas"]]],
                              colWidths=[largura / n_a] * n_a))
    doc.build(hist, onFirstPage=moldura, onLaterPages=moldura)
    return caminho


def _tabela_bap(t, linhas, F, cor, largura, stringWidth, colors):
    """Uma tabela do relatorio no estilo BAP. Devolve (Table, tem %)."""
    from reportlab.platypus import Table, TableStyle   # noqa: PLC0415
    mostra = [j for j, c in enumerate(t["colunas"])
              if not c.get("oculta") and not c.get("pdf_oculta")]
    cols = [t["colunas"][j] for j in mostra]
    grupos = t.get("grupos")
    if grupos and len(mostra) != len(t["colunas"]):
        vis, j0, novos = set(mostra), 0, []
        for rot_g, n_g in grupos:
            n_v = sum(1 for j in range(j0, j0 + n_g) if j in vis)
            if n_v:
                novos.append((rot_g, n_v))
            j0 += n_g
        grupos = novos
    tipos = [c.get("tipo", "texto") for c in cols]
    # o comeco da linha (verde): o 1o grupo (nome, ou UF/CIDADE/BAIRRO)
    k_ini = grupos[0][1] if grupos and not grupos[0][0] else 1
    TAM, TAM_CAB = 6.2, 5.6
    TR, TB = F["tr"], F["tb"]
    sem_rs = (t.get("pdf") or {}).get("sem_rs", True)

    def fmt(v, tp):
        if tp == "pct" and isinstance(v, (int, float)) and v >= 999.5:
            return ">999%"
        txt = formatar(v, tp)
        return txt.replace("R$ ", "") if sem_rs and tp.startswith("moeda") \
            else txt
    corpo = [[fmt(l[j] if j < len(l) else None, c.get("tipo", "texto"))
              for j, c in zip(mostra, cols)] for l in linhas]
    vis_t = t.get("linhas_visiveis")
    tem_total = bool(t.get("total")) and (vis_t is None or len(vis_t) == len(
        t["linhas"]) or t.get("total_vale"))
    total = ([fmt(t["total"][j] if j < len(t["total"]) else None,
                  c.get("tipo", "texto")) for j, c in zip(mostra, cols)]
             if tem_total else None)
    # larguras: as fixas do Farol; senao, pelo conteudo
    if all(c.get("pdf_larg") for c in cols):
        larg = [float(c["pdf_larg"]) for c in cols]
    else:
        larg = []
        for j, c in enumerate(cols):
            vals = [r[j] for r in corpo[:300]] + ([total[j]] if total else [])
            w = max([stringWidth(str(v), TB, TAM) for v in vals]
                    + [stringWidth(w_, TB, TAM_CAB)
                       for w_ in str(c.get("curto") or c["nome"]).split()])
            larg.append(w + 8)
        txt = [j for j, tp in enumerate(tipos) if tp == "texto"]
        sobra = largura - sum(larg)
        if txt and sobra > 0:
            for j in txt:
                larg[j] += sobra / len(txt)
        elif sobra < 0 and txt:
            corte = -sobra
            for j in txt:
                larg[j] = max(40, larg[j] - corte / len(txt))
    # texto que nao cabe: cortado com "..."
    for j, tp in enumerate(tipos):
        if tp != "texto":
            continue
        cabe = larg[j] - 5
        for r in corpo + ([total] if total else []):
            v = str(r[j])
            if stringWidth(v, TB, TAM) > cabe:
                while v and stringWidth(v + "…", TB, TAM) > cabe:
                    v = v[:-1]
                r[j] = v.rstrip() + "…"
    # o cabecalho: o nome curto, em duas linhas quando nao cabe
    cab = []
    for j, c in enumerate(cols):
        rot = str((c.get("curto") or c["nome"]) if grupos else c["nome"])
        if stringWidth(rot, TB, TAM_CAB) > larg[j] - 4 and " " in rot:
            a, _, b = rot.partition(" ")
            rot = f"{a}\n{b}"
        cab.append(rot)
    dados, est = [], []
    h = 0
    if grupos:
        linha_g, j0 = [], 0
        for rot, n in grupos:
            linha_g += [rot] + [""] * (n - 1)
            if n > 1:
                est.append(("SPAN", (j0, 0), (j0 + n - 1, 0)))
            if rot:
                est += [("BACKGROUND", (j0, 0), (j0 + n - 1, 0),
                         cor(CINZA_GRUPO)),
                        ("LINEAFTER", (j0 + n - 1, 0), (j0 + n - 1, -1), 1.2,
                         colors.white)]
            j0 += n
        dados.append(linha_g)
        h = 1
        est += [("FONT", (0, 0), (-1, 0), TB, 6.0),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "CENTER")]
    dados.append(cab)
    dados += corpo
    if total:
        dados.append(total)
    ult = len(dados) - 1
    num = [j for j, tp in enumerate(tipos) if tp not in ("texto", "data",
                                                          "dia")]
    est += [
        ("FONT", (0, h), (-1, h), TB, TAM_CAB),
        ("BACKGROUND", (0, h), (-1, h), cor(CINZA_COLUNA)),
        ("TEXTCOLOR", (0, h), (-1, h), cor(CINZA_TEXTO)),
        ("LINEAFTER", (0, h), (-2, h), 0.6, colors.white),
        ("VALIGN", (0, h), (-1, h), "MIDDLE"),
        ("FONT", (0, h + 1), (-1, -1), TR, TAM),
        ("TEXTCOLOR", (0, h + 1), (-1, -1), cor(PRETO_BAP)),
        ("FONT", (0, h + 1), (k_ini - 1, -1), TB, TAM),
        ("BACKGROUND", (0, h + 1), (k_ini - 1, -1), cor(VERDE_INICIO)),
        ("TEXTCOLOR", (0, h + 1), (k_ini - 1, -1), cor(VERDE_TEXTO)),
        ("LINEBELOW", (0, h + 1), (-1, -1), 0.35, cor("#E8EDE6")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
        ("LEADING", (0, 0), (-1, -1), TAM + 1.0),
    ]
    for j in num:
        est.append(("ALIGN", (j, h), (j, -1), "RIGHT"))
    for n in range(h + 1, ult + 1 if not total else ult):
        if (n - h) % 2 == 0:
            est += [("BACKGROUND", (k_ini, n), (-1, n), cor("#FAFBF9")),
                    ("BACKGROUND", (0, n), (k_ini - 1, n), cor(VERDE_LINHA))]
    if total:
        est += [("BACKGROUND", (0, ult), (-1, ult), cor(VERDE_CAB)),
                ("TEXTCOLOR", (0, ult), (-1, ult), cor(VERDE_TEXTO)),
                ("LINEABOVE", (0, ult), (-1, ult), 1.0, cor(VERDE_BAP)),
                ("FONT", (0, ult), (-1, ult), TB, TAM)]
    # o atingimento pintado
    ating = [j for j, c in enumerate(cols) if c.get("ating")]
    for j in ating:
        jo = mostra[j]
        fontes = list(linhas) + ([t["total"]] if total else [])
        for n, l in enumerate(fontes, start=h + 1):
            v = l[jo] if jo < len(l) else None
            par = _cor_do_ating(v)
            if par:
                est += [("BACKGROUND", (j, n), (j, n), cor(par[0])),
                        ("TEXTCOLOR", (j, n), (j, n), cor(par[1])),
                        ("FONT", (j, n), (j, n), TB, TAM)]
    # cor de texto por celula (ex.: a devolucao em vermelho)
    if t.get("cores_celulas"):
        por_linha = {id(l): c_ for l, c_ in zip(t["linhas"],
                                                 t["cores_celulas"])}
        for n, l in enumerate(linhas, start=h + 1):
            for jo, c_ in (por_linha.get(id(l)) or {}).items():
                if jo in mostra:
                    est += [("TEXTCOLOR", (mostra.index(jo), n),
                             (mostra.index(jo), n), cor(c_)),
                            ("FONT", (mostra.index(jo), n),
                             (mostra.index(jo), n), TB, TAM)]
    tab = Table(dados, colWidths=larg, repeatRows=h + 1, hAlign="LEFT")
    tab.setStyle(TableStyle(est))
    return tab, bool(ating)
