# -*- coding: utf-8 -*-
"""
BAP CENTRAL - a porta de entrada do time. Quatro quadrados:

    PRE-VENDA E FATURAMENTO ... Juliana    pedidos em aberto, faturados,
                                           excluidos, indicadores, Farol
    VENDAS E CRM .............. Mayara     meta e RV, indicadores
                                           executivos, Planner, base e
                                           oportunidades, Farol
    POS-VENDA E LOGISTICA ..... Estefanie  entregas, garantias, devolucoes,
                                           fretes, giro dos produtos, Farol
    ANALISTA COMERCIAL ........ Leandro    o BAP Analista (Planner + Meta +
                                           Oportunidades: os cadastros), o
                                           BAP Tools e os dados

Cada botao dos assistentes abre um RELATORIO SO DE LEITURA (bap_relatorios):
ver, filtrar, exportar para Excel/PDF e - quando o dado e de uma planilha
que a assistente cuida - abrir essa planilha no Excel. Nenhum relatorio
edita nada.

QUEM VE O QUADRADO DO ANALISTA: se existir o bap_acesso.json na pasta, so
os usuarios do Windows listados em "analistas" veem o quadrado (os outros
veem os tres dos assistentes). Sem o arquivo, todo mundo ve os quatro.
    {"analistas": ["leandro.nunes", "alexandre.guerreiro"]}

Abrir:  pythonw bap_central.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# (29/10, Alexandre: "o minimo de pasta possivel") o cache do Python fica fora
# da pasta do BAP (no %LOCALAPPDATA%\BAP_TOOLS\cache de cada maquina): sem
# __pycache__ na pasta e sem sincronizar cache pelo OneDrive.
try:
    import os as _os_c
    sys.pycache_prefix = sys.pycache_prefix or _os_c.path.join(
        _os_c.environ.get("LOCALAPPDATA") or _os_c.path.join(
            _os_c.path.dirname(_os_c.path.abspath(__file__)), "SISTEMA BAP"),
        *(("BAP_TOOLS", "cache") if _os_c.environ.get("LOCALAPPDATA")
          else ("cache",)))
except Exception:                                       # noqa: BLE001
    pass
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import bap_visual as bv                                   # noqa: E402

# (18/10) nomes da divisao das assistentes de 14/10 (rotinas_time_comercial)
PRE, VEN, POS, ANA = ("Faturamento", "CRM e Pós-venda",
                      "Logística de Entrega e Qualidade", "Analista Comercial")
TRADE = "Trade Marketing"

# (area, quem, [(botao, relatorio)])
QUADRADOS = [
    (PRE, "Juliana Almeida",
     [("Farol de Pedidos", "pv_pedidos"),
      ("Painel de indicadores", "pv_indicadores"),
      ("Farol de Estoque FRW", "pl_frw"),
      ("Farol DDR", "farol_pv")]),
    (VEN, "Mayara Santos",
     [("Farol de Metas Equipe", "vc_meta"),
      ("Farol Roteirização", "vc_planner"),
      ("Farol de Clientes", "vc_base"),
      ("Farol de Visita", "vc_visitas"),
      ("CAMPANHAS BAP", "vc_champions"),     # (28/10) Champions + relampago
      ("Farol de Giro de Produtos", "pl_giro"),
      ("Farol DDR", "farol_vc")]),
    (POS, "Estefanie Pacheco",
     [("Farol de Entregas", "pl_entregas"),
      ("Farol de Garantias", "pl_garantias"),
      ("Farol de Devoluções", "pl_devolucoes"),
      ("Farol de Estoque FRW", "pl_frw"),
      ("Farol de Inadimplência", "pl_inadimplencia"),
      ("Farol de NCC", "pl_ncc"),
      ("Farol DDR", "farol_pl")]),
    # (21/10) a Allaiza saiu: vaga de Analista de Trade Marketing Jr.
    # (responde ao Gerente Comercial) - o farol fica sem dono ate entrar
    (TRADE, "Vaga - Analista de Trade Marketing Jr.",
     [("Farol de Expositores", "tm_expositores")]),
]


# (18/10) horarios de envio dos farois de cada assistente (14/10)
ENVIOS = {
    PRE: "Envia o Farol de Pedidos: 10h · 14h · 16h · fechamento",
    VEN: "Envia o Farol de Visita: 9h · 11h · 14h · 16h · fechamento",
    POS: "Envia: Entregas 10h · Inadimplência seg 11h · Garantias ter 11h",
}


def _garantias_abertas() -> int:
    """(14/10) garantias em aberto (o Farol de Garantias novo)."""
    try:
        import garantias as gm                          # noqa: PLC0415
        return sum(1 for g in gm.ler(AQUI).values()
                   if (g.get("status") or "ABERTO").upper()
                   not in gm.FECHADOS)
    except Exception:                                   # noqa: BLE001
        return 0


def usuario() -> str:
    return (os.environ.get("USERNAME") or os.environ.get("USER") or "").lower()


def ve_analista() -> bool:
    arq = AQUI / "bap_acesso.json"
    if not arq.exists():
        return True
    try:
        lista = json.loads(arq.read_text("utf-8")).get("analistas") or []
    except (OSError, ValueError):
        return True
    return usuario() in {str(x).lower() for x in lista}


def abrir_relatorio(rid):
    subprocess.Popen([sys.executable, str(AQUI / "bap_relatorios.py"), rid],
                     cwd=str(AQUI))


def abrir_programa(script, *args):
    exe = sys.executable
    if script == "bap_janela.py":          # o BAP Tools roda no ambiente dele
        for pasta in (Path(os.environ.get("LOCALAPPDATA", "")) / "BAP_TOOLS",
                      AQUI):
            for nome in ("pythonw.exe", "python.exe"):
                cand = pasta / ".venv" / "Scripts" / nome
                if cand.is_file():
                    exe = str(cand)
                    break
    subprocess.Popen([exe, str(AQUI / script), *args], cwd=str(AQUI))


class Central(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BAP Central")
        self.geometry("1440x860")
        self.minsize(1180, 720)
        try:                        # (16/10) abre maximizado (notebook)
            self.state("zoomed")
        except tk.TclError:
            pass
        bv.aplicar_tema(self)
        cab = bv.Cabecalho(self, "Central", "BAP Central",
                           f"{date.today():%d/%m/%Y}")
        cab.pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        self.grade = tk.Frame(self, background=bv.FUNDO)
        self.grade.pack(fill="both", expand=True, padx=20, pady=18)
        quadrados = list(QUADRADOS)
        if ve_analista():
            quadrados.append((ANA, "Leandro Nunes", None))
        self.areas = [q[0] for q in quadrados]
        self.rotulos = []           # os botoes (para o teste)
        por = 3 if len(quadrados) > 4 else 2
        self.colunas_botao = 1 if por == 3 else 2
        for i, q in enumerate(quadrados):
            self._quadrado(q).grid(row=i // por, column=i % por,
                                   sticky="nsew", padx=8, pady=8)
        for c in range(por):
            self.grade.columnconfigure(c, weight=1, uniform="c")
        for r in range((len(quadrados) + por - 1) // por):
            self.grade.rowconfigure(r, weight=1, uniform="r")

    def _quadrado(self, q):
        area, quem, botoes = q
        c = tk.Frame(self.grade, background=bv.CARTAO,
                     highlightbackground=bv.CINZA_LINHA, highlightthickness=1)
        topo = tk.Frame(c, background=bv.CARTAO)
        topo.pack(fill="x", padx=22, pady=(18, 0))
        tk.Frame(topo, background=bv.VERDE, width=3, height=36).pack(
            side="left", padx=(0, 12))
        tit = tk.Frame(topo, background=bv.CARTAO)
        tit.pack(side="left", fill="x", expand=True)
        tk.Label(tit, text=area, background=bv.CARTAO, foreground=bv.TEXTO,
                 font=bv.fonte(13, "bold"), anchor="w").pack(fill="x")
        tk.Label(tit, text=quem, background=bv.CARTAO, foreground=bv.SUAVE,
                 font=bv.fonte(9), anchor="w").pack(fill="x")
        if ENVIOS.get(area):
            tk.Label(tit, text=ENVIOS[area], background=bv.CARTAO,
                     foreground=bv.VERDE_ESCURO, font=bv.fonte(8),
                     anchor="w").pack(fill="x")
        # (16/10, Alexandre) sem os avisos em cima dos botoes: a informacao
        # esta dentro dos farois
        tk.Frame(c, background=bv.CARTAO, height=14).pack(fill="x")
        caixa = tk.Frame(c, background=bv.CARTAO)
        caixa.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        if botoes is None:
            botoes = [("Abrir o BAP Analista", lambda: abrir_programa(
                "bap_analista.py"), True),
                      ("BAP Tools", lambda: abrir_programa(
                          "bap_janela.py"), False),
                      # (16/10) Painel Executivo = painel + indicadores
                      # executivos (o Resumo indicadores saiu)
                      ("Painel Executivo", lambda: abrir_relatorio(
                          "vc_painel"), False),
                      ("Farol de Saldo", lambda: abrir_relatorio(
                          "vc_saldo"), False),
                      ("Farol de Markup", lambda: abrir_relatorio(
                          "vc_markup"), False),
                      ("Farol de Preço", lambda: abrir_relatorio(
                          "vc_preco"), False),
                      ("CAMPANHAS BAP", lambda: abrir_relatorio(
                          "vc_champions"), False),
                      ("Kits promocionais", lambda: abrir_programa(
                          "bap_oportunidade.py", "--kits"), False),
                      # (07/10) pedidos + visitas p/ o grupo de vendas
                      ("Parcial BAP", self.parcial_bap, False),
                      ("Atualizar dados", self.atualizar_dados, False)]
        else:
            botoes = [(rot, (lambda r=rid: abrir_relatorio(r)), False)
                      for rot, rid in botoes]
        # muitos botoes (o quadrado do Analista): duas colunas para caber
        # (16/10) mais de 5 (Vendas e CRM): duas colunas - na tela do
        # notebook o ultimo botao cortava
        nb = 2 if len(botoes) > 5 else self.colunas_botao
        for j, (rot, cmd, destaque) in enumerate(botoes):
            self.rotulos.append(rot)
            fundo = bv.VERDE if destaque else bv.FUNDO
            b = tk.Button(caixa, text=rot, command=cmd, relief="flat",
                          cursor="hand2", anchor="w", padx=14, pady=8,
                          font=bv.fonte(10, "bold" if destaque else "normal"),
                          background=fundo,
                          foreground="white" if destaque else bv.TEXTO,
                          activebackground=bv.VERDE_ESCURO if destaque
                          else bv.VERDE_CLARO,
                          activeforeground="white" if destaque else bv.TEXTO,
                          borderwidth=0, highlightthickness=0)
            if not destaque:
                b.bind("<Enter>", lambda e, b=b: b.configure(
                    background=bv.VERDE_CLARO))
                b.bind("<Leave>", lambda e, b=b: b.configure(
                    background=bv.FUNDO))
            b.grid(row=j // nb, column=j % nb, sticky="ew", padx=6, pady=3)
        for k in range(nb):
            caixa.columnconfigure(k, weight=1, uniform="b")
        return c

    def parcial_bap(self):
        """A PARCIAL BAP (pedidos + visitas): a mesma janela das parciais
        dos farois - Acumulado, D-1 ou Hoje; imagem para o WhatsApp ou PDF."""
        try:
            import bap_relatorios as br                  # noqa: PLC0415
            br.DialogoParcial(self, "bap")
        except Exception as erro:                        # noqa: BLE001
            messagebox.showerror("Parcial BAP", str(erro), parent=self)

    def atualizar_dados(self):
        if not messagebox.askyesno(
                "BAP Central", "Atualizar os dados de todos os relatórios? "
                "Leva alguns minutos.", parent=self):
            return
        self.title("BAP Central · atualizando os dados…")

        def trabalho():
            import bap_dados as bd                       # noqa: PLC0415
            return bd.atualizar_tudo(AQUI, log=None)

        def pronto(r):
            self.title("BAP Central")
            erros = [k for k, v in r.items() if str(v).startswith("ERRO")
                     or k == "_erro"]
            if erros:
                messagebox.showerror("BAP Central",
                                     f"Erro ao atualizar: {', '.join(erros)}",
                                     parent=self)
            else:
                messagebox.showinfo("BAP Central", "Dados atualizados.",
                                    parent=self)
        bv.em_segundo_plano(self, trabalho, pronto)


def main():
    Central().mainloop()


if __name__ == "__main__":
    main()
