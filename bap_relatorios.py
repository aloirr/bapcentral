# -*- coding: utf-8 -*-
"""
BAP RELATORIOS - a janela de cada relatorio dos assistentes.

    pythonw bap_relatorios.py pv_abertos      (abre um relatorio)
    pythonw bap_relatorios.py                 (lista todos)

O que da para fazer:
    * filtrar, buscar e escolher um RECORTE - os cartoes de cima seguem o
      que esta na tela
    * ordenar clicando no titulo da coluna
    * EXCEL / PDF - a aba aberta ou todas as abas (no PDF, cada tabela
      comeca numa pagina nova, com os numeros dela)
    * ABRIR / EDITAR NO EXCEL - a planilha de onde o dado vem
    * EDITAR NA TELA (so Entregas, Devolucoes e Fretes): duplo clique na
      linha, escolhe nas listas, SALVAR grava no ACOMPANHAMENTO_POS_VENDA
      (so as colunas da assistente) e refaz o relatorio.
"""
from __future__ import annotations

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
from collections import Counter
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import bap_visual as bv                                  # noqa: E402
import relatorios_nucleo as rn                           # noqa: E402

PASTA_EXPORT = AQUI / "RELATORIOS" / "EXPORTADOS"
# (20/10, Alexandre) os .json de roteirizacao (ROTA_PROTHEUS e
# BASE_CLIENTES_PROTHEUS) vao para a pasta da Roteirizacao
PASTA_ROTEIRIZACAO = AQUI / "RELATORIOS" / "Roteirizacao"
TODOS = "(todos)"
VAZIO = "(vazio)"


def _nome_arquivo(rel, sufixo="") -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in
                   bv.formatar(rel.get("titulo", "relatorio") + sufixo, "texto"))
    return f"{base.strip('_')}_{datetime.now():%Y%m%d_%H%M}"


class _BaseRelatorio:
    """A janela de um relatorio. (28/10) A mesma tela serve de programa
    proprio (Relatorio, tk.Tk) e dentro do BAP Analista (RelatorioNoQuadro,
    tk.Frame)."""

    def __init__(self, rid: str, pai=None):
        if pai is None:
            super().__init__()
        else:
            super().__init__(pai, background=bv.FUNDO)
        self.rid = rid
        _, area, titulo, _f = rn.POR_ID[rid]
        self.title(f"{titulo} · BAP")
        self.geometry("1440x880")
        self.minsize(980, 620)
        bv.aplicar_tema(self)
        self.cab = bv.Cabecalho(self, area, titulo, "")
        self.cab.pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        self.bt_salvar = self.cab.botao("Salvar", self.salvar, verde=True)
        self.bt_salvar.pack_forget()
        self.bt_editar = self.cab.botao("Abrir no Excel", self.abrir_excel)
        self.bt_xls = self.cab.botao("Excel  ▾",
                                     lambda: self._menu_exportar("xlsx"))
        self.bt_pdf = self.cab.botao("PDF  ▾",
                                     lambda: self._menu_exportar("pdf"))
        if rid == "vc_meta":           # o fechamento para o RH pagar a RV
            self.bt_rh = self.cab.botao("Exportar para o RH  ▾", self._menu_rh)
            self.cab.botao("Enviar Parcial via email", self.enviar_parcial)
        if rid == "pl_inadimplencia":  # (30/10) a carteira de cada vendedor
            self.cab.botao("Enviar por e-mail", self.enviar_inadimplencia,
                           verde=True)
            # (06/11, Alexandre) a cobranca ao CLIENTE, cliente a cliente,
            # pelo WhatsApp do computador
            self.cab.botao("Cobrar no WhatsApp", self.cobrar_whatsapp,
                           verde=True)
        # (16/10) os Indicadores Executivos estao no Painel Executivo
        if rid in ("vc_executivo", "vc_painel"):  # (06/10) o cadastro
            self.cab.botao("Metas executivas", self.metas_executivas,
                           verde=True)
            # (08/10) resumo executivo + analitico por indicador (PDF/Excel)
            self.cab.botao("Exportar para o RH",
                           lambda: DialogoRHExecutivo(self))
        if rid == "vc_visitas":        # o GridRca da Maxima, dia a dia
            self.cab.botao("Atualizar visitas", self.atualizar_visitas,
                           verde=True)
            # (06/10) a parcial do time: imagem para o WhatsApp ou PDF
            self.cab.botao("Parcial Visitas e Conversão",
                           lambda: DialogoParcial(self, "visitas"),
                           verde=True)
        if rid == "pl_entregas":       # (06/10) para o grupo do pos-venda
            self.cab.botao("Parcial Entregas",
                           lambda: DialogoParcial(self, "entregas"),
                           verde=True)
        if rid == "pv_pedidos":
            self.cab.botao("Parcial Pedidos",
                           lambda: DialogoParcial(self, "pedidos"),
                           verde=True)
        if rid == "vc_champions":      # (28/10) os parametros do jogo
            self.cab.botao("Parâmetros das campanhas",
                           lambda: DialogoChampions(self), verde=True)
            # (30/10, Alexandre) o fechamento no formato da premiacao
            self.cab.botao("Exportar campanha", self.exportar_campanha,
                           verde=True)
        if rid == "an_divergencias":   # (07/10) o que corrigir no Protheus
            self.bt_correcao = self.cab.botao("Exportar para correção  ▾",
                                              self._menu_correcao, verde=True)
        if rid == "vc_planner":
            # (07/10) os .json do Protheus sairam daqui: BAP Analista >
            # Zonas, vendedores e rota > Parametros > PROTHEUS (JSON)
            # (06/10) a rota da semana (seg a sex), um PDF por vendedor
            self.cab.botao("Enviar Rota da semana por E-mail",
                           self.enviar_rota)
        self.cab.botao("Atualizar", self.carregar)
        self.corpo = ttk.Frame(self)
        self.corpo.pack(fill="both", expand=True, padx=20, pady=(14, 4))
        self.rodape = tk.Label(self, text="", background=bv.FUNDO,
                               foreground=bv.SUAVE, font=bv.fonte(8),
                               anchor="w")
        self.rodape.pack(fill="x", padx=20, pady=(0, 6))
        self.rel = None
        self.vistas = []
        self.params = {}
        self.gerais_escolha = {}       # (10/10) os filtros gerais de cima
        self.gerais = {}
        self.nomes_params = set()
        self.pendentes = {}            # {(arquivo, aba): {chave: {campo: v}}}
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.carregar()

    # ------------------------------------------------------------ dados
    def carregar(self):
        if self.pendentes and not messagebox.askyesno(
                "Atualizar", "Há alterações não salvas. Descartar e atualizar?",
                parent=self):
            return
        self.pendentes = {}
        self._estado_salvar()
        self._guardar_filtros()
        self.rel = None
        for w in self.corpo.winfo_children():
            w.destroy()
        self.msg = tk.Label(self.corpo, text="Carregando…",
                            background=bv.FUNDO, foreground=bv.SUAVE,
                            font=bv.fonte(11))
        self.msg.pack(pady=80)
        try:                            # um so relogio do "Carregando..."
            self.after_cancel(self._id_log)
        except (AttributeError, tk.TclError, ValueError):
            pass
        self._log = []
        params = dict(self.params)

        def trabalho():
            return rn.montar(self.rid, AQUI, log=self._log.append,
                             params=params, tela=True)

        def pronto(rel):
            if isinstance(rel, dict) and "_erro" in rel:
                self.rel = False                 # para o recado de espera
                self.msg.configure(text=f"Erro ao carregar o relatório\n\n"
                                        f"{rel['_erro']}", foreground=bv.VERMELHO)
                return
            self.rel = rel
            self.desenhar()
        bv.em_segundo_plano(self, trabalho, pronto)
        self._mostrar_log()

    def _guardar_filtros(self):
        """(22/10, Alexandre) ao ATUALIZAR (salvar a autorizacao/edicao no
        pedido, trocar o mes, botao Atualizar) cada aba volta com os
        filtros, o recorte e a busca que estavam escolhidos - antes voltava
        no padrao (ex.: SITUACAO = EM ABERTO no Farol de Pedidos)."""
        guard = getattr(self, "_filtros_guardados", None)
        if guard is None:
            guard = self._filtros_guardados = {}
        vistas = getattr(self, "vistas", None) or []
        for i in range(len(vistas)):
            try:
                v = vistas.montada(i) if hasattr(vistas, "montada") \
                    else vistas[i]
                if v is None or not hasattr(v, "filtros"):
                    continue
                guard[v.t["titulo"]] = {
                    "f": {nome: var.get() for var, _m, nome in
                          v.filtros.values()
                          if nome not in getattr(v, "_ocultos", ())},
                    "recorte": v.var_recorte.get(), "busca": v.busca.get()}
            except (tk.TclError, AttributeError, KeyError):
                continue

    def _mostrar_log(self):
        try:
            if self.rel is None and self.msg.winfo_exists():
                if self._log:
                    self.msg.configure(text=f"Carregando…\n{self._log[-1]}")
                self._id_log = self.after(300, self._mostrar_log)
        except tk.TclError:
            pass

    def fechar(self):
        if self.pendentes and not messagebox.askyesno(
                "Fechar", "Há alterações não salvas. Fechar sem salvar?",
                parent=self):
            return
        self.destroy()

    def destroy(self):
        try:
            self.after_cancel(self._id_log)
        except (AttributeError, tk.TclError, ValueError):
            pass
        super().destroy()

    # ---------------------------------------------------------- desenho
    def desenhar(self):
        rel = self.rel
        for w in self.corpo.winfo_children():
            w.destroy()
        self.cab.lbl_sub.configure(text=rel.get("subtitulo", ""))
        self.bt_editar.configure(text="Editar no Excel" if rel.get("editar")
                                 else "Abrir no Excel")
        # (10/10) UMA LINHA SO em cima: os parametros (mes, ano...) e os
        # FILTROS GERAIS (filial, UF, cidade, segmento, supervisor,
        # vendedor, categoria, familia, produto, fornecedor), que valem
        # para todas as abas que tem a coluna. Embaixo de cada aba so fica
        # o que e so dela (curva, situacao, etapa, recorte, busca)
        self.nomes_params = {prm["nome"] for prm in
                             rel.get("parametros") or []}
        gerais = self._filtros_gerais(rel)
        self.gerais = {}
        self._barra_topo = None
        if rel.get("parametros") or gerais:
            self._barra_parametros(rel.get("parametros") or [], gerais)
        self.area_kpis = ttk.Frame(self.corpo)
        self.area_kpis.pack(fill="x")
        if rel.get("avisos"):
            # (10/10) as observacoes sairam da tela (mais clean): um sinal
            # discreto no fim da linha de filtros; passando o mouse, o texto
            alvo = self._barra_topo
            if alvo is None:
                alvo = tk.Frame(self.corpo, background=bv.FUNDO)
                alvo.pack(fill="x", pady=(0, 6), before=self.area_kpis)
            n_av = len(rel["avisos"])
            sinal = tk.Label(alvo, text=f"ⓘ  {n_av} observaç"
                             f"{'ão' if n_av == 1 else 'ões'}",
                             background=bv.FUNDO, foreground=bv.SUAVE,
                             font=bv.fonte(8), cursor="question_arrow")
            sinal.pack(side="right")
            bv.Dica(sinal, "\n\n".join(rel["avisos"]))
        self.abas = ttk.Notebook(self.corpo, style="Abas.TNotebook")
        self.abas.pack(fill="both", expand=True, pady=(4, 0))
        self.vistas = []
        self.aba_graficos = None
        self._n_paineis = 0
        self._kpis_aba = {}            # (26/10) aba de painel -> os cartoes
        self._painel_aba = {}          # (26/10) aba de painel -> o painel
        self._vista_da_aba = {}        # (26/10) aba -> posicao em vistas
        if rel.get("paineis"):
            # (26/10, Alexandre) Painel Executivo: so as abas pedidas, cada
            # uma um painel com os cartoes dela (Resumo gerencial,
            # Faturamento, Volume, Produtividade, Positivacao, Itens por
            # pedido, Markup, Preco e Inadimplencia)
            for pn in rel["paineis"]:
                aba = ttk.Frame(self.abas, style="TFrame")
                self.abas.add(aba, text=pn["titulo"])
                self._montar_painel(aba, pn["painel"])
                if pn.get("kpis") is not None:
                    self._kpis_aba[str(aba)] = pn["kpis"]
                self._painel_aba[str(aba)] = pn
                self._n_paineis += 1
        elif rel.get("painel_pre"):        # (12/10) a Visao executiva
            aba = ttk.Frame(self.abas, style="TFrame")
            self.abas.add(aba, text=rel["painel_pre"].get("titulo")
                          or "Visão executiva")
            self._montar_painel(aba, rel["painel_pre"]["painel"])
            self._n_paineis += 1
        if rel.get("paineis"):
            pass
        elif rel.get("painel"):            # o painel executivo (como o BI)
            aba = ttk.Frame(self.abas, style="TFrame")
            self.abas.add(aba, text=rel.get("painel_titulo")
                          or "Painel executivo")
            self.aba_graficos = aba
            self._montar_painel(aba, rel["painel"])
        elif rel.get("graficos"):
            aba = ttk.Frame(self.abas, style="TFrame")
            self.abas.add(aba, text="Resumo gerencial" if rel.get("capa")
                          else "Visão geral")
            self.aba_graficos = aba
            f = self._rolavel(aba)
            lin, colu = 0, 0
            for g in rel["graficos"]:
                largo = g.get("largo")
                if largo and colu:
                    lin, colu = lin + 1, 0
                bv.GraficoBarras(f, g["titulo"], g["rotulos"], g["series"],
                                 g.get("formato", "num"), meta=g.get("meta"),
                                 altura=270 if largo else 250,
                                 linhas=g.get("linhas", False)).grid(
                    row=lin, column=colu, columnspan=2 if largo else 1,
                    sticky="nsew", padx=8, pady=8)
                if largo:
                    lin += 1
                else:
                    colu += 1
                    if colu == 2:
                        lin, colu = lin + 1, 0
            f.columnconfigure(0, weight=1, uniform="g")
            f.columnconfigure(1, weight=1, uniform="g")
        # AS ABAS SO SAO MONTADAS QUANDO ABERTAS: antes toda troca de mes
        # redesenhava todas as tabelas (milhares de linhas) de uma vez e a
        # janela travava alguns segundos. Agora so a aba da tela.
        self.vistas = _Vistas(self)
        for t in rel.get("tabelas", []):
            f = ttk.Frame(self.abas)
            # (26/10) so_exportar: a tabela nao vira aba (vai so no Excel e
            # no PDF de todas as abas)
            if not t.get("so_exportar"):
                self.abas.add(f, text=t["titulo"])
                self._vista_da_aba[str(f)] = len(self.vistas)
            self.vistas.adicionar(f, t)
        nomes = [self.abas.tab(i, "text") for i in self.abas.tabs()]
        if getattr(self, "_aba_anterior", None) in nomes:
            self.abas.select(nomes.index(self._aba_anterior))   # mesma aba
        elif self.aba_graficos is not None and not rel.get("capa") and any(
                t.get("edicao") for t in rel.get("tabelas", [])):
            self.abas.select(1 + self._n_paineis)   # quem edita: a tabela
        self.vista_atual()             # monta a aba que esta na tela
        self.abas.bind("<<NotebookTabChanged>>", self._trocou_aba)
        self.pintar_kpis()
        edita = any(t.get("edicao") for t in rel.get("tabelas", []))
        pedido = any(t.get("detalhe") and (not t.get("edicao") or (
            t.get("edicao") or {}).get("so_colunas"))
                     for t in rel.get("tabelas", []))
        dicas = (["Duplo clique na linha para editar"] if edita else []) + \
            (["Duplo clique no pedido para ver os itens"] if pedido else [])
        self.rodape.configure(
            text="   ·   ".join([f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}"]
                                + dicas))

    def _montar_painel(self, pai, painel):
        """Os quadros do painel numa grade de 3 colunas que acompanha o
        tamanho da janela (as barras e graficos se redesenham sozinhos)."""
        # tela grande: o painel ocupa a janela toda; tela pequena: ele nao
        # amassa - fica com a altura minima e a tela rola
        ALTURA_MIN = painel.get("altura_min", 4 * 190)
        try:                     # a escala do Windows: a letra cresce
            from tkinter import font as _tkf             # noqa: PLC0415
            ALTURA_MIN = int(ALTURA_MIN * max(1.0, _tkf.Font(
                font=bv.fonte(8)).metrics("linespace") / 14.0))
        except Exception:                               # noqa: BLE001
            pass
        tela = tk.Canvas(pai, background=bv.FUNDO, highlightthickness=0)
        barra = ttk.Scrollbar(pai, orient="vertical", command=tela.yview)
        grade = tk.Frame(tela, background=bv.FUNDO)
        janela = tela.create_window(0, 0, window=grade, anchor="nw")

        def ajustar(e):
            alt = max(e.height, ALTURA_MIN)
            tela.itemconfigure(janela, width=e.width, height=alt)
            tela.configure(scrollregion=(0, 0, e.width, alt))
            if alt > e.height:
                barra.pack(side="right", fill="y", before=tela)
            else:
                barra.pack_forget()
        tela.bind("<Configure>", ajustar)
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True, pady=(6, 0))

        def rolar(e):
            try:
                if str(tela.winfo_containing(e.x_root, e.y_root)).startswith(
                        str(tela)) and barra.winfo_ismapped():
                    tela.yview_scroll(int(-e.delta / 120) or
                                      (-1 if e.delta > 0 else 1), "units")
            except (tk.TclError, KeyError):
                pass
        self.bind_all("<MouseWheel>", rolar, add="+")
        linhas = 0
        for b in painel["blocos"]:
            quadro = tk.Frame(grade, background=bv.FUNDO)
            quadro.grid(row=b["row"], column=b["col"],
                        rowspan=b.get("rowspan", 1),
                        columnspan=b.get("colspan", 1), sticky="nsew",
                        padx=5, pady=5)
            quadro.pack_propagate(False)
            linhas = max(linhas, b["row"] + b.get("rowspan", 1))
            if b["tipo"] == "hbarras":
                bv.BarrasHorizontais(quadro, b["titulo"], b["rotulos"],
                                     b["valores"], b.get("formato", "moeda"),
                                     altura=10, cores=b.get("cores"),
                                     referencia=b.get("referencia")).pack(
                                         fill="both", expand=True)
            elif b["tipo"] == "barras":
                g = b["grafico"]
                bv.GraficoBarras(quadro, g["titulo"], g["rotulos"],
                                 g["series"], g.get("formato", "num"),
                                 altura=10, meta=g.get("meta"),
                                 subrotulos=g.get("subrotulos"),
                                 rotular=g.get("rotular", False),
                                 linha=g.get("linha"),
                                 rotulo_meta=g.get("rotulo_meta", "meta"),
                                 linhas=g.get("linhas", False)).pack(
                                     fill="both", expand=True)
            elif b["tipo"] in ("pizza", "grupo"):
                bv.PizzaTabela(quadro, b["titulo"], b.get("nome_col", ""),
                               b["linhas"], b.get("total"),
                               pizza=b["tipo"] == "pizza", altura=10).pack(
                                   fill="both", expand=True)
            elif b["tipo"] == "insights":   # (06/10) o que o painel diz
                self._insights(quadro, b)
            elif b["tipo"] == "diretor":    # (29/10) o Painel do Diretor
                import painel_diretor as pdr            # noqa: PLC0415
                pdr.tela(quadro, b["dados"], abrir=abrir,
                         ao_editar=lambda: pdr.editar(
                             self.winfo_toplevel(), AQUI,
                             ao_gravar=self.carregar),
                         exportar=lambda tipo, d_=b["dados"]:
                         self._exportar_diretor(d_, tipo)).pack(
                    fill="both", expand=True)
            elif b["tipo"] == "rrm":        # (10/11) o painel no modelo RRM
                import painel_rrm as prm                # noqa: PLC0415
                vis_ = b.get("visao", "res")
                prm.tela(quadro, b["dados"], vis_,
                         exportar=lambda tipo, d_=b["dados"], v_=vis_:
                         self._exportar_rrm(d_, v_, tipo)).pack(
                    fill="both", expand=True)
            elif b["tipo"] == "cartoes":    # (06/11) o Painel em cartoes
                import painel_cartoes as pcx            # noqa: PLC0415
                pcx.tela(quadro, b["dados"], b.get("visao", "abs")).pack(
                    fill="both", expand=True)
            elif b["tipo"] == "placar":     # (12/10) a Visao executiva
                bv.PlacarFarois(quadro, b.get("titulo", ""), b["cartoes"],
                                b.get("por_linha", 4)).pack(
                                    fill="both", expand=True)
            elif b["tipo"] == "tabela":
                cartao = tk.Frame(quadro, background=bv.CARTAO,
                                  highlightthickness=1,
                                  highlightbackground=bv.CINZA_LINHA)
                cartao.pack(fill="both", expand=True)
                tk.Label(cartao, text=b["titulo"], background=bv.CARTAO,
                         foreground=bv.TEXTO, font=bv.fonte(10, "bold"),
                         anchor="w").pack(fill="x", padx=12, pady=(8, 4))
                t = bv.Tabela(cartao, b["colunas"], altura=6,
                              compacta=bool(b.get("compacta", True)),
                              grupos=b.get("grupos"), cabe="auto")
                t.pack(fill="both", expand=True, padx=1, pady=(0, 1))
                t.mostrar(b["linhas"], b.get("tons") or
                          [""] * len(b["linhas"]), b.get("total"))
        pesos = painel.get("colunas") or (10, 12, 13)
        for j_, p_ in enumerate(pesos):
            grade.columnconfigure(j_, weight=p_, uniform="c")
        for i in range(linhas):
            grade.rowconfigure(i, weight=1, uniform="l")

    def _insights(self, quadro, b):
        """O quadro O QUE A ROTA DIZ: uma frase por linha, com a bolinha da
        cor do tom (alerta, atencao, ok, info) - o texto quebra sozinho."""
        cores = {"alerta": bv.VERMELHO, "atencao": bv.AMARELO,
                 "ok": bv.VERDE, "info": bv.SUAVE}
        cartao = tk.Frame(quadro, background=bv.CARTAO, highlightthickness=1,
                          highlightbackground=bv.CINZA_LINHA)
        cartao.pack(fill="both", expand=True)
        tk.Label(cartao, text=b["titulo"], background=bv.CARTAO,
                 foreground=bv.TEXTO, font=bv.fonte(10, "bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        tk.Frame(cartao, background=bv.VERDE, height=2, width=40).pack(
            anchor="w", padx=14, pady=(0, 8))
        textos = []
        for tom, txt in b["linhas"]:
            lin = tk.Frame(cartao, background=bv.CARTAO)
            lin.pack(fill="x", padx=14, pady=4)
            tk.Label(lin, text="●", background=bv.CARTAO,
                     foreground=cores.get(tom, bv.SUAVE),
                     font=bv.fonte(9)).pack(side="left", anchor="n")
            lb = tk.Label(lin, text=txt, background=bv.CARTAO,
                          foreground=bv.TEXTO if tom in ("alerta", "atencao")
                          else bv.SUAVE, font=bv.fonte(9), justify="left",
                          anchor="w")
            lb.pack(side="left", fill="x", expand=True, padx=(6, 0))
            textos.append(lb)

        def quebrar(e):
            for lb_ in textos:
                lb_.configure(wraplength=max(120, e.width - 60))
        cartao.bind("<Configure>", quebrar)

    def _rolavel(self, pai):
        """Uma area que rola na vertical (a capa tem varios graficos)."""
        tela = tk.Canvas(pai, background=bv.FUNDO, highlightthickness=0)
        barra = ttk.Scrollbar(pai, orient="vertical", command=tela.yview)
        dentro = tk.Frame(tela, background=bv.FUNDO)
        janela = tela.create_window(0, 0, window=dentro, anchor="nw")
        dentro.bind("<Configure>", lambda e: tela.configure(
            scrollregion=tela.bbox("all")))
        tela.bind("<Configure>", lambda e: tela.itemconfigure(
            janela, width=e.width))
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        def rolar(e):
            try:
                if str(tela.winfo_containing(e.x_root, e.y_root)).startswith(
                        str(tela)):
                    tela.yview_scroll(int(-e.delta / 120) or
                                      (-1 if e.delta > 0 else 1), "units")
            except (tk.TclError, KeyError):
                pass
        self.bind_all("<MouseWheel>", rolar, add="+")
        self.bind_all("<Button-4>", lambda e: tela.yview_scroll(-1, "units"),
                      add="+")
        self.bind_all("<Button-5>", lambda e: tela.yview_scroll(1, "units"),
                      add="+")
        return dentro

    def _filtros_gerais(self, rel):
        """[(nome, valores)] dos filtros gerais: os que alguma aba tem e que
        nao sao parametro (ex.: VENDEDOR PLANNER some se VENDEDOR esta em
        cima)."""
        achados = {}
        for t in rel.get("tabelas", []):
            if t.get("solicitacao_bap") or not t.get("colunas") or \
                    t.get("so_exportar"):
                continue
            nomes = [c["nome"] for c in t["colunas"]]
            fora = set(t.get("filtros_fora") or ())
            base = t.get("linhas_filtro") or t["linhas"]
            for f in t.get("filtros", []):
                n = rn.nome_filtro(f)
                if (n not in FILTROS_GERAIS or n in fora or n not in nomes
                        or _repetido(n, self.nomes_params)):
                    continue
                i = nomes.index(n)
                multi = isinstance(f, dict) and f.get("multi")
                vals = achados.setdefault(n, set())
                for l in base:
                    v = l[i]
                    if v in (None, ""):
                        continue
                    if multi:
                        vals |= {x.strip() for x in str(v).split(";")
                                 if x.strip()}
                    else:
                        vals.add(bv.formatar(v, "texto"))
        return [(n, sorted(achados[n] - {rn.TODAS_FILIAIS}))
                for n in FILTROS_GERAIS if n in achados]

    def _escolheu_geral(self, nome, valor):
        self.gerais_escolha[nome] = valor
        for i in range(len(self.vistas)):
            v = self.vistas.montada(i)
            if v is not None and hasattr(v, "aplicar"):
                v.aplicar(primeira=True)
        self.pintar_kpis()

    def _barra_parametros(self, parametros, gerais=()):
        # (10/10) a linha vai ate a largura da janela antes de quebrar
        self.update_idletasks()
        LARGURA_FILTROS = max(globals()["LARGURA_FILTROS"],
                              self.winfo_width() - 44)
        if (self.rel or {}).get("avisos"):    # o sinal das observacoes
            LARGURA_FILTROS -= 120

        def nova_linha(pady):
            b = tk.Frame(self.corpo, background=bv.FUNDO)
            b.pack(fill="x", pady=pady)
            return b
        barra = nova_linha((0, 8))
        self._barra_topo = barra             # o sinal das observacoes vai aqui
        usado = 0
        for prm in parametros:
            if prm.get("tipo") == "flag":       # (06/10) caixa de marcar
                var_f = tk.BooleanVar(value=bool(prm.get("valor")))

                def marcou(nome=prm["nome"], var=var_f, sim=prm["valores"][0]):
                    sim_ = sim[0] if isinstance(sim, tuple) else sim
                    self.params[nome] = sim_ if var.get() else None
                    self.carregar()
                ttk.Checkbutton(barra, text=prm.get("rotulo") or
                                prm["nome"].capitalize(), variable=var_f,
                                command=marcou).pack(side="left",
                                                     padx=(0, 18))
                usado += len(prm.get("rotulo") or prm["nome"]) * 8 + 40
                continue
            vals = prm["valores"]
            pares = [v if isinstance(v, tuple) else (v, v) for v in vals]
            rotulos = [r for _, r in pares]
            de_rotulo = {r: v for v, r in pares}
            atual = next((r for v, r in pares if v == prm.get("valor")),
                         rotulos[0] if rotulos else "")
            larg = min(14 if len(rotulos) > 40 else 18,
                       max(8, max((len(r) for r in rotulos), default=8)))
            w = _largura_grupo(prm["nome"], larg, 18)
            if usado and usado + w > LARGURA_FILTROS:   # muitas caixas: quebra
                barra.pack_configure(pady=(0, 6))
                barra = nova_linha((0, 8))
                usado = 0
            usado += w
            tk.Label(barra, text=prm["nome"] if len(prm["nome"]) <= 2
                     else prm["nome"].capitalize(), background=bv.FUNDO,
                     foreground=bv.SUAVE, font=bv.fonte(9)).pack(side="left",
                                                                 padx=(0, 6))
            var = tk.StringVar(value=atual)
            # lista comprida (cliente, cidade): da para digitar e a lista
            # encolhe para o que contem o texto; Enter escolhe
            longa = len(rotulos) > 40
            cb = ttk.Combobox(barra, textvariable=var,
                              state="normal" if longa else "readonly",
                              values=rotulos, width=larg)
            bv.lista_larga(cb)
            cb.pack(side="left", padx=(0, 18))

            def mudou(e, nome=prm["nome"], var=var, de=de_rotulo):
                if var.get() not in de:
                    return
                self.params[nome] = de.get(var.get(), var.get())
                self.carregar()
            cb.bind("<<ComboboxSelected>>", mudou)
            if longa:
                def digitou(e, cb=cb, var=var, todos=rotulos):
                    if e.keysym in ("Return", "KP_Enter", "Up", "Down",
                                    "Escape"):
                        return
                    t = var.get().strip().upper()
                    cb.configure(values=[r for r in todos if t in r.upper()]
                                 if t else todos)

                def enter(e, cb=cb, var=var, de=de_rotulo, f=mudou):
                    if var.get() not in de:
                        achados = list(cb.cget("values"))
                        if not achados:
                            return
                        var.set(achados[0])
                    f(e)
                cb.bind("<KeyRelease>", digitou)
                cb.bind("<Return>", enter)
                cb.bind("<KP_Enter>", enter)
        # os FILTROS GERAIS na mesma linha (separados por um traco fino)
        for k, (nome, valores) in enumerate(gerais):
            # (15/10) caixa mais larga (cabe "000007 - RODRIGO..."); a
            # lista que abre mostra o nome inteiro (bv.lista_larga)
            larg = min(18,
                       max(8, max((len(v) for v in valores), default=8)))
            w = _largura_grupo(nome, larg, 14) + (18 if k == 0 else 0)
            if usado and usado + w > LARGURA_FILTROS:
                barra.pack_configure(pady=(0, 6))
                barra = nova_linha((0, 8))
                usado = 0
            elif k == 0 and usado:
                tk.Frame(barra, background=bv.CINZA_LINHA, width=1,
                         height=20).pack(side="left", padx=(0, 14))
            usado += w
            atual = self.gerais_escolha.get(nome, TODOS)
            var = tk.StringVar(value=atual if atual in valores else TODOS)
            self.gerais_escolha[nome] = var.get()
            self.gerais[nome] = var
            tk.Label(barra, text=nome if len(nome) <= 2 else
                     nome.capitalize(), background=bv.FUNDO,
                     foreground=bv.SUAVE, font=bv.fonte(9)).pack(
                         side="left", padx=(0, 6))
            caixa_de_filtro(barra, var, valores, larg,
                            lambda v, n=nome: self._escolheu_geral(n, v)
                            ).pack(side="left", padx=(0, 14))

    def _trocou_aba(self, _e=None):
        try:
            self._aba_anterior = self.abas.tab(self.abas.select(), "text")
        except tk.TclError:
            pass
        self.vista_atual()
        self.pintar_kpis()

    # --------------------------------------------------------- cartoes
    def vista_atual(self):
        try:
            sel = str(self.abas.select())
        except (tk.TclError, AttributeError):
            return None
        i = getattr(self, "_vista_da_aba", {}).get(sel)
        return self.vistas[i] if i is not None and 0 <= i < len(
            self.vistas) else None

    def kpis_atuais(self):
        try:                            # (26/10) a aba de painel com cartoes
            sel = str(self.abas.select())
        except (tk.TclError, AttributeError):
            sel = ""
        if sel in getattr(self, "_kpis_aba", {}):
            return self._kpis_aba[sel]
        v = self.vista_atual()
        if v is not None and v.t.get("kpis_de"):
            try:
                return rn.chamar_kpis_de(v.t["kpis_de"], v.visiveis(),
                                      v.filtros_colunas())
            except Exception:                           # noqa: BLE001
                pass
        return self.rel.get("kpis", [])

    def pintar_kpis(self):
        if not self.rel or not hasattr(self, "area_kpis"):
            return
        for w in self.area_kpis.winfo_children():
            w.destroy()
        kpis = self.kpis_atuais()
        if self.rel.get("kpis_faixa") and kpis:
            self._kpis_em_faixa(kpis)
            return
        # ate 8 cartoes numa linha so (o Farol de Metas tem 7)
        por_linha = 6 if len(kpis) <= 6 or len(kpis) > 8 else len(kpis)
        larg = max(self.area_kpis.winfo_width(), self.winfo_width() - 40, 600)
        espaco = int(larg / por_linha) - 10
        if not getattr(self.area_kpis, "_ligado", False):
            self.area_kpis._ligado = True
            self._kpi_larg = larg // 80
            self.area_kpis.bind("<Configure>", self._kpis_redimensionar)
        for i, k in enumerate(kpis):
            # (10/11) a visao por estado do cartao (tabela Por UF)
            try:
                uf_ = rn.estados_do_cartao(self.rel, k)
            except Exception:                           # noqa: BLE001
                uf_ = {}
            c = bv.cartao_kpi(self.area_kpis, k["rotulo"], k["valor"],
                              k.get("cor", "neutro"), k.get("detalhe", ""),
                              espaco=espaco, linhas=k.get("linhas"),
                              compacto=True, estados=uf_)
            c.grid(row=i // por_linha, column=i % por_linha, sticky="nsew",
                   padx=(0, 8), pady=(0, 6))
        for j in range(8):               # colunas iguais: cartao de tamanho fixo
            self.area_kpis.columnconfigure(j, weight=1 if j < por_linha
                                           else 0, uniform="k"
                                           if j < por_linha else "")

    def _kpis_em_faixa(self, kpis):
        """(09/10) Os numeros numa FAIXA fina (rotulo pequeno em cima, o
        numero e o detalhe ao lado), no lugar dos cartoes altos - sobra
        altura para as tabelas (Farol de Pedidos)."""
        faixa = tk.Frame(self.area_kpis, background=bv.CARTAO,
                         highlightthickness=1,
                         highlightbackground=bv.CINZA_LINHA)
        faixa.grid(row=0, column=0, columnspan=8, sticky="ew", pady=(0, 6))
        for j in range(8):
            self.area_kpis.columnconfigure(j, weight=1 if j == 0 else 0,
                                           uniform="")
        for i, k in enumerate(kpis):
            cx = tk.Frame(faixa, background=bv.CARTAO)
            cx.grid(row=0, column=i * 2, sticky="nsew", padx=12, pady=4)
            faixa.columnconfigure(i * 2, weight=1, uniform="kf")
            tk.Label(cx, text=k["rotulo"], background=bv.CARTAO,
                     foreground=bv.SUAVE, font=bv.fonte(8),
                     anchor="w").pack(anchor="w")
            lin = tk.Frame(cx, background=bv.CARTAO)
            lin.pack(anchor="w")
            cor = k.get("cor", "neutro")
            tk.Label(lin, text=k["valor"], background=bv.CARTAO,
                     foreground=bv.CORES.get(cor, cor if str(cor).startswith(
                         "#") else bv.TEXTO),
                     font=bv.fonte(13, "bold")).pack(side="left")
            if k.get("detalhe"):
                tk.Label(lin, text=k["detalhe"], background=bv.CARTAO,
                         foreground=bv.SUAVE, font=bv.fonte(8)).pack(
                             side="left", padx=(6, 0), pady=(4, 0))
            if i < len(kpis) - 1:
                tk.Frame(faixa, background=bv.CINZA_LINHA, width=1).grid(
                    row=0, column=i * 2 + 1, sticky="ns", pady=6)

    def _kpis_redimensionar(self, e):
        faixa = e.width // 80
        if faixa != getattr(self, "_kpi_larg", None):
            self._kpi_larg = faixa
            self.after_idle(self.pintar_kpis)

    # ---------------------------------------------------------- edicao
    def anotar(self, edicao, chave, campos: dict):
        k = (edicao["arquivo"], edicao["aba"], edicao.get("modulo", ""))
        self.pendentes.setdefault(k, {}).setdefault(chave, {}).update(campos)
        self._estado_salvar()

    def _estado_salvar(self):
        n = sum(len(v) for v in self.pendentes.values())
        if n:
            self.bt_salvar.configure(text=f"Salvar ({n})")
            self.bt_salvar.pack(side="left", padx=4, before=self.bt_editar)
        else:
            self.bt_salvar.pack_forget()

    def salvar(self):
        if not self.pendentes:
            return
        import pos_venda                                # noqa: PLC0415
        total = 0
        arquivo = ""
        try:
            for (arquivo, aba, modulo), edicoes in list(self.pendentes.items()):
                if modulo == "expositores":
                    import expositores                  # noqa: PLC0415
                    total += expositores.gravar_edicoes(AQUI, edicoes)
                elif modulo == "autorizacoes":          # (13/10)
                    import autorizacoes                 # noqa: PLC0415
                    total += autorizacoes.gravar(AQUI, edicoes)
                elif modulo == "ncc":                   # (20/10) Farol de NCC
                    import ncc_controle                 # noqa: PLC0415
                    total += ncc_controle.gravar(AQUI, edicoes)
                elif modulo == "farol":                 # Farol DDR
                    import farol_ddr                    # noqa: PLC0415
                    total += farol_ddr.gravar_marcacoes(AQUI / arquivo, aba,
                                                        edicoes)
                else:
                    total += pos_venda.gravar_edicoes(AQUI / arquivo, aba,
                                                      edicoes)
                del self.pendentes[(arquivo, aba, modulo)]
        except PermissionError:
            messagebox.showerror(
                "Salvar", f"{Path(arquivo).name} está aberto no Excel (ou "
                "sincronizando). Feche o arquivo e clique em Salvar de novo - "
                "nada se perdeu.", parent=self)
            return
        except (OSError, ValueError) as erro:
            messagebox.showerror("Salvar", str(erro), parent=self)
            return
        self._estado_salvar()
        self.rodape.configure(text=f"Salvo ({total}). Recarregando…")
        self.carregar()

    # ---------------------------------------------------------- exportar
    def _menu_rh(self):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="PDF", command=lambda: self.exportar_rh("pdf"))
        m.add_command(label="Excel", command=lambda: self.exportar_rh("xlsx"))
        bt = self.bt_rh
        m.tk_popup(bt.winfo_rootx(), bt.winfo_rooty() + bt.winfo_height())

    def exportar_rh(self, tipo):
        """Gerente, supervisores e vendedores: META, REAL, % ATING. e RV de
        faturamento total, positivacao e visita (sem NEC./DIA)."""
        def trabalho():
            ctx = rn.Contexto(AQUI, params=dict(self.params))
            rel = rn.exportar_rh(ctx)
            rel["area"] = rn.VEN
            comp = rn.rotulo_mes(rn.meta_do_periodo(ctx)["competencia"]
                                 ).replace("/", "")
            destino = PASTA_EXPORT / (f"RESULTADO_RH_{comp}_"
                                      f"{datetime.now():%Y%m%d_%H%M}.{tipo}")
            if tipo == "pdf":
                return bv.exportar_pdf(rel, destino)
            return bv.exportar_excel(rel, destino)

        def pronto(destino):
            if isinstance(destino, dict) and "_erro" in destino:
                messagebox.showerror("Exportar para o RH", str(destino["_erro"]),
                                     parent=self)
                return
            self._abrir(destino)
        bv.em_segundo_plano(self, trabalho, pronto)

    def enviar_parcial(self):
        """A parcial de cada um (formato RH) no e-mail do cadastro do
        Planner: vendedor, supervisor (com a equipe) e gerente (tudo)."""
        params = dict(self.params)

        def trabalho():
            return rn.destinatarios_parcial(rn.Contexto(AQUI, params=params))

        def pronto(pessoas):
            if isinstance(pessoas, dict) and "_erro" in pessoas:
                messagebox.showerror("Enviar Parcial", str(pessoas["_erro"]),
                                     parent=self)
                return
            if not pessoas:
                messagebox.showinfo("Enviar Parcial",
                                    "Ninguém do Planner tem resultado neste "
                                    "mês.", parent=self)
                return
            EnvioParcial(self, pessoas, params)
        bv.em_segundo_plano(self, trabalho, pronto)

    def enviar_inadimplencia(self):
        """(30/10, Alexandre) Os CLIENTES INADIMPLENTES de cada um, por
        e-mail, como a parcial do RH: vendedor (supervisor em copia),
        supervisor (gerente em copia) e gerente. PDF em anexo."""
        def trabalho():
            import email_inadimplencia as ei            # noqa: PLC0415
            return ei.destinatarios(AQUI)

        def pronto(pessoas):
            if isinstance(pessoas, dict) and "_erro" in pessoas:
                messagebox.showerror("Enviar inadimplência",
                                     str(pessoas["_erro"]), parent=self)
                return
            if not pessoas:
                messagebox.showinfo("Enviar inadimplência", "Ninguém ativo "
                                    "no Planner.", parent=self)
                return
            EnvioParcial(self, pessoas, None, modo="inadimplencia")
        bv.em_segundo_plano(self, trabalho, pronto)

    def cobrar_whatsapp(self):
        """(06/11, Alexandre: "coloque o botao de cobrar no whatsapp para a
        assistente ir enviando a cobranca cliente a cliente") a fila dos
        inadimplentes; cada mensagem abre no WhatsApp do computador e a
        assistente envia (cobranca_whatsapp.py)."""
        if not self.rel:
            return

        def trabalho():
            from datetime import date as _d             # noqa: PLC0415
            try:            # o nome da mensagem: a fantasia do cadastro
                ctx = rn.Contexto(AQUI, _d.today(), None, {})
                return {rn.texto(c.get("cod")): rn.texto(
                    c.get("fantasia")) or rn.texto(c.get("nome"))
                    for c in ctx.base.get("clientes") or []}
            except Exception:                           # noqa: BLE001
                return {}

        def pronto(nomes):
            import cobranca_whatsapp as cw              # noqa: PLC0415
            if not isinstance(nomes, dict) or "_erro" in nomes:
                nomes = {}
            try:
                cw.janela(self, self.rel, AQUI, nomes)
            except Exception as erro:                   # noqa: BLE001
                messagebox.showerror("Cobrar no WhatsApp", str(erro),
                                     parent=self)
        bv.em_segundo_plano(self, trabalho, pronto)

    def enviar_rota(self):
        """A rota da semana (segunda a sexta) de cada vendedor, por e-mail:
        vendedor (o PDF dele), supervisor e gerente (um PDF por vendedor).
        Ninguem em copia."""
        EnvioRota(self)

    def _menu_exportar(self, tipo):
        if not self.rel:
            return
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Aba atual",
                      command=lambda: self.exportar(tipo, so_aba=True))
        m.add_command(label="Todas as abas",
                      command=lambda: self.exportar(tipo, so_aba=False))
        bt = self.bt_pdf if tipo == "pdf" else self.bt_xls
        m.tk_popup(bt.winfo_rootx(), bt.winfo_rooty() + bt.winfo_height())

    def _exportar_diretor(self, dados, tipo):
        """(29/10) Painel do Diretor: PNG (WhatsApp) ou PDF A4 deitado de 1
        pagina, na pasta EXPORTADOS."""
        import painel_diretor as pdr                    # noqa: PLC0415
        PASTA_EXPORT.mkdir(parents=True, exist_ok=True)
        base = PASTA_EXPORT / (f"PAINEL_DO_DIRETOR_{dados['comp']}_"
                               f"{datetime.now():%Y%m%d_%H%M}")
        destino = base.with_suffix(".png" if tipo == "png" else ".pdf")
        try:
            pdr.imagem(dados, destino_png=destino if tipo == "png" else None,
                       destino_pdf=destino if tipo != "png" else None)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Painel do Diretor", str(erro), parent=self)
            return
        self._abrir(destino)

    def _exportar_rrm(self, dados, visao, tipo):
        """(10/11, recado 20261109-1345) o painel no modelo da RRM: PNG
        (WhatsApp) ou PDF de 1 pagina 16:9, na pasta EXPORTADOS."""
        import painel_rrm as prm                        # noqa: PLC0415
        PASTA_EXPORT.mkdir(parents=True, exist_ok=True)
        nome = {"res": "RESULTADO", "prod": "PRODUTIVIDADE",
                "du": "POR_DU"}.get(visao, visao.upper())
        base = PASTA_EXPORT / (f"PAINEL_DO_DIRETOR_{nome}_{dados['comp']}_"
                               f"{datetime.now():%Y%m%d_%H%M}")
        destino = base.with_suffix(".png" if tipo == "png" else ".pdf")
        try:
            prm.imagem(dados, visao,
                       destino_png=destino if tipo == "png" else None,
                       destino_pdf=destino if tipo != "png" else None)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Painel do Diretor", str(erro), parent=self)
            return
        self._abrir(destino)

    def _rel_do_painel(self, pn):
        """(26/10) Exportar a ABA ATUAL quando ela e um painel (Painel
        Executivo): os cartoes da aba, os graficos de barras, as tabelas
        dos quadros e o placar dos farois como tabela."""
        rel = dict(self.rel)
        rel["kpis"] = list(pn.get("kpis_export") or pn.get("kpis") or [])
        rel["titulo"] = f"{self.rel.get('titulo', '')} · {pn['titulo']}"
        graf, tabs, avisos = [], [], []
        for b in pn["painel"].get("blocos") or []:
            if b["tipo"] == "barras":
                graf.append(dict(b["grafico"], largo=b.get("colspan", 1) > 1))
            elif b["tipo"] == "tabela":
                tabs.append({"titulo": b["titulo"], "colunas": b["colunas"],
                             "linhas": b["linhas"],
                             "linhas_visiveis": b["linhas"],
                             "total": b.get("total"),
                             "tons": [""] * len(b["linhas"]),
                             "filtro_texto": ""})
            elif b["tipo"] == "insights":
                avisos += [txt for _tom, txt in b.get("linhas") or []]
            elif b["tipo"] == "placar":
                cols = [rn.col("FAROL", "texto", 150),
                        rn.col("SITUAÇÃO", "texto", 70),
                        rn.col("VALOR", "texto", 90),
                        rn.col("INDICADOR", "texto", 140),
                        rn.col("DETALHE", "texto", 260),
                        rn.col("IMPACTO R$", "moeda", 100)]
                ls = [[c_["farol"], {"ok": "BOM", "atencao": "ATENÇÃO",
                                     "alerta": "RUIM"}.get(c_["tom"], "—"),
                       c_["valor"], c_["rotulo"], c_["detalhe"],
                       c_.get("impacto")] for c_ in b["cartoes"]]
                tabs.append({"titulo": b.get("titulo") or "Faróis",
                             "colunas": cols, "linhas": ls,
                             "linhas_visiveis": ls, "total": None,
                             "tons": [""] * len(ls), "filtro_texto": ""})
        rel["graficos"], rel["tabelas"] = graf, tabs
        rel["avisos"] = avisos
        rel["tabelas_seguidas"] = True
        return rel

    def _rel_filtrado(self, so_aba=False):
        if so_aba:
            try:
                sel = str(self.abas.select())
            except (tk.TclError, AttributeError):
                sel = ""
            pn = getattr(self, "_painel_aba", {}).get(sel)
            if pn:
                return self._rel_do_painel(pn)
        rel = dict(self.rel)
        rel["kpis"] = self.kpis_atuais() if so_aba else self.rel.get("kpis", [])
        tabs = []
        atual = self.vista_atual()
        for i, t in enumerate(self.rel["tabelas"]):
            if so_aba and self.vistas.montada(i) is not atual:
                continue
            if t.get("solicitacao_bap"):
                continue                # (09/10) tem o proprio arquivo
            v = self.vistas[i]
            t2 = dict(t)
            t2["linhas_visiveis"] = v.visiveis()
            if hasattr(v, "total_de"):         # o total do que esta na tela
                t2["total"] = v.total_de(t2["linhas_visiveis"])
                t2["total_vale"] = True
            if hasattr(v.tab, "grade"):        # o calendario sai como grade
                t2["colunas"], t2["linhas_visiveis"] = v.tab.grade(
                    t2["linhas_visiveis"])
                t2["total"] = None
            if t.get("ordem_exportar"):      # (06/10) a ordem de sempre
                try:                          # (ex.: data e sequencia)
                    t2["linhas_visiveis"] = sorted(t2["linhas_visiveis"],
                                                   key=t["ordem_exportar"])
                except Exception:                       # noqa: BLE001
                    pass
            t2["filtro_texto"] = v.texto_do_filtro()
            if t.get("kpis_de"):
                try:
                    t2["kpis_visiveis"] = rn.chamar_kpis_de(
                        t["kpis_de"], t2["linhas_visiveis"],
                        v.filtros_colunas())
                except Exception:                       # noqa: BLE001
                    t2["kpis_visiveis"] = None
            tabs.append(t2)
            # (06/10) as tabelas juntas saem logo depois, so com as linhas
            # dos pedidos da tela
            antes_j = len(tabs) - 1          # (04/11) empilhadas: em cima
            for x in getattr(v, "juntas", []):
                tj = dict(x["j"]["tabela"])
                tj["linhas_visiveis"] = list(x["linhas"])
                tj["filtro_texto"] = x["j"].get("filtro_texto") or (
                    f"Dos {t['titulo'].lower()} da tela"
                    + (f" · {t2['filtro_texto']}"
                       if t2["filtro_texto"] else ""))
                if tj.get("kpis_de"):
                    try:
                        tj["kpis_visiveis"] = tj["kpis_de"](
                            tj["linhas_visiveis"])
                    except Exception:                   # noqa: BLE001
                        tj["kpis_visiveis"] = None
                if t.get("juntas_em_cima"):
                    tj["filtro_texto"] = ""
                    tabs.insert(antes_j, tj)
                    antes_j += 1
                else:
                    tabs.append(tj)
        rel["tabelas"] = tabs
        if so_aba and atual is not None:
            rel["graficos"] = []
            rel["kpis"] = []           # os numeros vao na pagina da tabela
        if self.params:
            rotulo = {}
            for prm in self.rel.get("parametros") or []:
                for v in prm["valores"]:
                    val, rot = v if isinstance(v, tuple) else (v, v)
                    rotulo[(prm["nome"], val)] = rot
            partes = [rotulo.get((k, v), v) for k, v in self.params.items()
                      if v and v != "(todos)"]
            rel["filtro_texto"] = " · ".join(str(x) for x in partes)
        return rel

    def exportar(self, tipo, so_aba=False):
        rel = self._rel_filtrado(so_aba)
        atual = self.vista_atual()
        sufixo = f"_{atual.t['titulo']}" if so_aba and atual else ""
        if so_aba and not atual:        # (26/10) a aba de painel
            try:
                pn = self._painel_aba.get(str(self.abas.select()))
            except (tk.TclError, AttributeError):
                pn = None
            sufixo = f"_{pn['titulo']}" if pn else ""
        destino = PASTA_EXPORT / (_nome_arquivo(self.rel, sufixo) + "." + tipo)
        try:
            if tipo == "pdf":
                destino = bv.exportar_pdf(rel, destino)
            else:
                destino = bv.exportar_excel(rel, destino)
        except Exception as erro:                        # noqa: BLE001
            messagebox.showerror("Exportar", str(erro), parent=self)
            return None
        if destino.suffix == ".html":
            messagebox.showinfo(
                "Exportar PDF", "Biblioteca de PDF não instalada (rode o "
                "INSTALAR_PDF.bat). Gerado em HTML: imprima com Ctrl+P.",
                parent=self)
        self._abrir(destino)
        return destino

    # ---- (07/10) Divergencias clientes Maxima x Protheus
    def _menu_correcao(self):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Excel para correção (A1_VEND atual → correto)",
                      command=self.exportar_correcao)
        # (28/10, Alexandre) o .json da base de clientes so no roteirizador
        # (saiu daqui); a analista preenche a mao e devolve
        m.add_separator()
        m.add_command(label="Clientes sem coordenada/endereço (para "
                            "preencher)", command=self.exportar_sem_coordenada)
        m.add_command(label="Importar preenchidos (coordenadas)…",
                      command=self.importar_preenchidos)
        bt = self.bt_correcao
        m.tk_popup(bt.winfo_rootx(), bt.winfo_rooty() + bt.winfo_height())

    def _chaves_correcao(self):
        """Na aba Clientes divergentes, so o que esta filtrado na tela;
        nas outras, tudo."""
        v = self.vista_atual()
        if v is None or v.t.get("titulo") != "Clientes divergentes":
            return None, ""
        return ({(str(l[0]), str(l[1])) for l in v.visiveis()},
                v.texto_do_filtro())

    def exportar_correcao(self):
        if not self.rel or not callable(self.rel.get("exportar_correcao")):
            return
        chaves, filtro = self._chaves_correcao()
        destino = PASTA_EXPORT / (f"CORRECAO_VENDEDOR_PROTHEUS_"
                                  f"{datetime.now():%Y%m%d_%H%M}.xlsx")
        try:
            destino, n1, n2 = self.rel["exportar_correcao"](destino, chaves)
        except PermissionError:
            messagebox.showerror("Exportar para correção",
                                 f"{destino.name} está aberto no Excel.",
                                 parent=self)
            return
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Exportar para correção", str(erro),
                                 parent=self)
            return
        self.rodape.configure(text=f"Gravado: {destino.name}")
        if messagebox.askyesno(
                "Exportar para correção",
                f"{destino.name}\n\n{filtro or 'Todas as divergências'}\n"
                f"CORRIGIR NO PROTHEUS: {n1} cliente(s) (A1_VEND atual → o "
                f"do Planner)\nANALISAR: {n2} cliente(s)\n\n"
                f"Gravado em:\n{destino.parent}\n\nAbrir agora?",
                parent=self):
            self._abrir(destino)

    def exportar_sem_coordenada(self):
        """(28/10) O Excel para a analista preencher: na aba Sem coordenada
        / endereco, so o que esta filtrado; nas outras, todos."""
        if not self.rel or not callable(
                self.rel.get("exportar_sem_coordenada")):
            return
        v = self.vista_atual()
        if v is not None and v.t.get("titulo") == "Sem coordenada / endereço":
            chaves = {(str(l[0]), str(l[1])) for l in v.visiveis()}
            filtro = v.texto_do_filtro()
        else:
            chaves, filtro = None, ""
        destino = PASTA_EXPORT / (f"CLIENTES_SEM_COORDENADA_ENDERECO_"
                                  f"{datetime.now():%Y%m%d_%H%M}.xlsx")
        try:
            destino, n = self.rel["exportar_sem_coordenada"](destino, chaves)
        except PermissionError:
            messagebox.showerror("Exportar para correção",
                                 f"{destino.name} está aberto no Excel.",
                                 parent=self)
            return
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Exportar para correção", str(erro),
                                 parent=self)
            return
        self.rodape.configure(text=f"Gravado: {destino.name}")
        if messagebox.askyesno(
                "Exportar para correção",
                f"{destino.name}\n\n{filtro or 'Todos os clientes da aba'}\n"
                f"{n} cliente(s) sem coordenada/endereço para a analista "
                f"preencher (colunas amarelas).\n\nDepois de preenchido: "
                f"Exportar para correção ▾ › Importar preenchidos.\n\n"
                f"Gravado em:\n{destino.parent}\n\nAbrir agora?",
                parent=self):
            self._abrir(destino)

    def importar_preenchidos(self):
        """(28/10) Le o Excel preenchido e grava as coordenadas (MANUAL) no
        COORDENADAS_CLIENTES.json."""
        if not self.rel or not callable(self.rel.get("importar_preenchidos")):
            return
        from tkinter import filedialog                  # noqa: PLC0415
        arq = filedialog.askopenfilename(
            parent=self, title="Excel preenchido (clientes sem coordenada)",
            initialdir=str(PASTA_EXPORT) if PASTA_EXPORT.exists() else None,
            filetypes=[("Excel", "*.xlsx")])
        if not arq:
            return
        try:
            res = self.rel["importar_preenchidos"](arq)
        except PermissionError:
            messagebox.showerror("Importar preenchidos", "O arquivo de "
                                 "coordenadas está em uso. Tente de novo.",
                                 parent=self)
            return
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Importar preenchidos", str(erro),
                                 parent=self)
            return
        rec = res["recusados"]
        txt = (f"Gravadas: {len(res['gravados'])} coordenada(s) (MANUAL)\n"
               f"Recusadas: {len(rec)}\n"
               f"Sem coordenada preenchida: {res['sem_coordenada']}")
        if rec:
            txt += "\n\nRecusadas:\n" + "\n".join(
                f"· {q}: {m}" for q, m in rec[:15])
            if len(rec) > 15:
                txt += f"\n… e mais {len(rec) - 15}"
        if res["gravados"]:
            txt += "\n\nO relatório vai ser atualizado."
        messagebox.showinfo("Importar preenchidos", txt, parent=self)
        self.rodape.configure(text=f"Importado: {Path(arq).name} · "
                                   f"{len(res['gravados'])} gravada(s), "
                                   f"{len(rec)} recusada(s)")
        if res["gravados"]:
            self.carregar()

    def exportar_correcao_json(self):
        if not self.rel or not callable(
                self.rel.get("exportar_correcao_json")):
            return
        chaves, filtro = self._chaves_correcao()
        try:
            linhas = self.rel["exportar_correcao_json"](chaves)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Exportar para correção", str(erro),
                                 parent=self)
            return
        if not linhas:
            messagebox.showinfo("Exportar para correção",
                                "Nenhum cliente para corrigir no Protheus "
                                "(com vendedor no Planner).", parent=self)
            return
        destino = PASTA_ROTEIRIZACAO / (f"BASE_CLIENTES_PROTHEUS_CORRECAO_"
                                  f"{datetime.now():%Y%m%d_%H%M}.json")
        try:
            import json                                 # noqa: PLC0415
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(__import__("planner_nucleo").json_protheus(linhas), encoding="utf-8")
        except OSError as erro:
            messagebox.showerror("Exportar para correção", str(erro),
                                 parent=self)
            return
        self.rodape.configure(text=f"Gravado: {destino.name}")
        if messagebox.askyesno(
                "Exportar para correção",
                f"{destino.name}\n\n{filtro or 'Todas as divergências'}\n"
                f"{len(linhas)} cliente(s) com o A1_VEND do Planner, no "
                f"layout da base de clientes do Protheus\n\nGravado em:\n"
                f"{destino.parent}\n\nAbrir a pasta?", parent=self):
            self._abrir(destino.parent)

    def _menu_protheus(self):
        """Os dois arquivos do Protheus: a roteirizacao (visitas) e a base
        de clientes (vendedor e supervisor de cada cliente)."""
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Roteirização (visitas)",
                      command=self.exportar_protheus)
        m.add_command(label="Base de clientes",
                      command=self.exportar_base_protheus)
        bt = self.bt_protheus
        m.tk_popup(bt.winfo_rootx(), bt.winfo_rooty() + bt.winfo_height())

    def exportar_base_protheus(self):
        """A base de clientes no .json do Protheus: A1_FILIAL, A1_COD,
        A1_LOJA, A1_VEND, A1_NOME, A1_NREDUZ, SUPERVISOR e STATUS (20/10:
        todos ATIVO; sem vendedor vai com o vendedor/supervisor padrao)."""
        if not self.rel or not callable(
                self.rel.get("exportar_base_protheus")):
            return
        v = self.vista_atual()
        t = v.t if v is not None and v.t.get("protheus") else None
        try:
            linhas = self.rel["exportar_base_protheus"](
                t, v.visiveis() if t else None)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Exportar Protheus", str(erro), parent=self)
            return
        if not linhas:
            messagebox.showinfo("Exportar Protheus",
                                "Nenhum cliente com vendedor para exportar.",
                                parent=self)
            return
        filtro = v.texto_do_filtro() if t else ""
        pedaco = "".join(ch if ch.isalnum() else "_" for ch in bv.formatar(
            filtro.replace("Filtro: ", ""), "texto"))
        while "__" in pedaco:
            pedaco = pedaco.replace("__", "_")
        pedaco = pedaco[:40].strip("_")
        destino = PASTA_ROTEIRIZACAO / (
            f"BASE_CLIENTES_PROTHEUS_{pedaco or 'TODOS'}"
                                  f"_{datetime.now():%Y%m%d_%H%M}.json")
        try:
            import json                                 # noqa: PLC0415
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(__import__("planner_nucleo").json_protheus(linhas), encoding="utf-8")
        except OSError as erro:
            messagebox.showerror("Exportar Protheus", str(erro), parent=self)
            return
        vend = len({x["A1_VEND"] for x in linhas})
        from types import SimpleNamespace                # noqa: PLC0415
        v_p = rn.vendedor_padrao_de(SimpleNamespace(raiz=AQUI))
        s_p = rn.vendedor_padrao_de(SimpleNamespace(raiz=AQUI),
                                    "supervisor_padrao")
        n_p = sum(1 for x in linhas if x.get("A1_VEND") == v_p)
        self.rodape.configure(text=f"Gravado: {destino.name}")
        if messagebox.askyesno(
                "Exportar Protheus",
                f"{destino.name}\n\n{filtro or 'Base inteira'}\n"
                f"{len(linhas)} cliente(s) de {vend} vendedor(es) - todos "
                f"ATIVO\n{len(linhas) - n_p} com vendedor da equipe · {n_p} "
                f"sem vendedor (vendedor padrão {v_p} / supervisor {s_p})"
                f"\n\n"
                f"Gravado em:\n{destino.parent}\n\nAbrir a pasta?",
                parent=self):
            self._abrir(destino.parent)

    def exportar_protheus(self):
        """A rota no .json do Protheus (o mesmo da aba Exportar Protheus do
        Planner). Na aba Calendario ou Por cliente, so o que esta filtrado
        na tela; nas outras, a rota inteira."""
        if not self.rel or not callable(self.rel.get("exportar_protheus")):
            return
        v = self.vista_atual()
        t = v.t if v is not None and v.t.get("protheus") else None
        try:
            linhas = self.rel["exportar_protheus"](
                t, v.visiveis() if t else None)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Exportar Protheus", str(erro), parent=self)
            return
        if not linhas:
            messagebox.showinfo("Exportar Protheus",
                                "Não há visita na tela para exportar.",
                                parent=self)
            return
        # (26/10, Alexandre) o mes inteiro ou so a partir de hoje
        nu_ = __import__("planner_nucleo")
        periodo = bv.escolher_periodo_rota(self)
        if periodo is None:
            return
        if periodo == "hoje":
            linhas = nu_.rota_a_partir_de(linhas)
            if not linhas:
                messagebox.showinfo("Exportar Protheus", "Não há visita de "
                                    "hoje em diante para exportar.",
                                    parent=self)
                return
        filtro = v.texto_do_filtro() if t else ""
        pedaco = "".join(ch if ch.isalnum() else "_" for ch in bv.formatar(
            filtro.replace("Filtro: ", ""), "texto"))
        while "__" in pedaco:
            pedaco = pedaco.replace("__", "_")
        pedaco = pedaco[:40].strip("_")
        destino = PASTA_ROTEIRIZACAO / (
            f"ROTA_PROTHEUS_{pedaco or 'TODOS'}_"
            + (nu_.sufixo_a_partir_de() if periodo == "hoje" else "")
            + f"{datetime.now():%Y%m%d_%H%M}.json")
        try:
            import json                                 # noqa: PLC0415
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(__import__("planner_nucleo").json_protheus(linhas), encoding="utf-8")
        except OSError as erro:
            messagebox.showerror("Exportar Protheus", str(erro), parent=self)
            return
        clientes = len({x["codcli"] for x in linhas})
        self.rodape.configure(text=f"Gravado: {destino.name}")
        if messagebox.askyesno(
                "Exportar Protheus",
                f"{destino.name}\n\n{filtro or 'Rota inteira'}\n"
                f"{len(linhas)} visita(s) de {clientes} cliente(s)"
                + (f" - a partir de hoje ({datetime.now():%d/%m})"
                   if periodo == "hoje" else " - o mês inteiro") + "\n"
                f"Compromisso {linhas[0]['codcompromisso']}\n\n"
                f"Gravado em:\n{destino.parent}\n\nAbrir a pasta?",
                parent=self):
            self._abrir(destino.parent)

    def exportar_excel(self, abrir=True):
        """Mantido para o teste: exporta todas as abas para Excel."""
        try:
            destino = bv.exportar_excel(
                self._rel_filtrado(), PASTA_EXPORT / (_nome_arquivo(self.rel)
                                                      + ".xlsx"))
        except OSError as erro:
            messagebox.showerror("Exportar", str(erro), parent=self)
            return None
        if abrir:
            self._abrir(destino)
        return destino

    def metas_executivas(self):
        """O cadastro das metas executivas (meta, peso e despesa mes a mes)
        abre na janela dele (processo proprio: o visual de um nao mexe no
        do outro); ao fechar, o painel refaz com o que foi gravado.
        Saiu do BAP Analista (06/10): cadastro e leitura num lugar so."""
        proc = getattr(self, "_proc_exec", None)
        if proc is not None and proc.poll() is None:
            messagebox.showinfo("Metas executivas", "O cadastro já está "
                                "aberto.", parent=self)
            return
        import subprocess                                # noqa: PLC0415
        self._proc_exec = subprocess.Popen(
            [sys.executable, str(AQUI / "bap_meta.py"), "--executivas"],
            cwd=str(AQUI))

        def esperar():
            p_ = getattr(self, "_proc_exec", None)
            if p_ is None:
                return
            if p_.poll() is None:
                self.after(1500, esperar)
                return
            self._proc_exec = None
            self.carregar()
        self.after(1500, esperar)

    def atualizar_visitas(self):
        """A janela que baixa o GridRca da Maxima; ao terminar, refaz."""
        if getattr(self, "_jan_visitas", None) is not None:
            try:
                self._jan_visitas.lift()
                return
            except tk.TclError:
                pass
        import visitas_maxima                            # noqa: PLC0415

        def pronto():
            self.carregar()
        self._jan_visitas = visitas_maxima.janela(self, AQUI, pronto)
        self._jan_visitas.bind("<Destroy>", lambda e: setattr(
            self, "_jan_visitas", None) if e.widget is self._jan_visitas
            else None)

    def abrir_excel(self):
        if not self.rel:
            return
        abrir = self.rel.get("abrir")      # so abrir (o Farol de Visita)
        if abrir:
            caminho = AQUI / abrir
            if caminho.exists():
                self._abrir(caminho)
            else:
                messagebox.showinfo("Abrir no Excel",
                                    f"{caminho.name} ainda não existe: "
                                    f"clique em Atualizar visitas.",
                                    parent=self)
            return
        editar = self.rel.get("editar")
        if editar:
            caminho = AQUI / editar
            if caminho.exists():
                self._abrir(caminho)
                return
            messagebox.showinfo("Abrir no Excel",
                                f"{caminho.name} ainda não existe.", parent=self)
            return
        self.exportar("xlsx", so_aba=False)

    def exportar_campanha(self):
        """(30/10, Alexandre) EXPORTAR CAMPANHA: o Resumo geral das
        Campanhas BAP (Campanha BAP valida + relampago) no Excel da
        premiacao (CPF, CNPJ, E-mail, Nome, Valor = pontos, Nome Acao), na
        pasta EXPORTADOS."""
        ex = (self.rel or {}).get("campanha_export") if self.rel else None
        if not ex or not ex.get("linhas"):
            messagebox.showinfo("Exportar campanha", "Nenhum ponto a pagar "
                                "no mês escolhido.", parent=self)
            return
        destino = PASTA_EXPORT / (f"CAMPANHA_{ex['comp']}_"
                                  f"{datetime.now():%Y%m%d_%H%M}.xlsx")
        try:
            rn.exportar_campanha(self.rel, destino)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Exportar campanha", str(erro), parent=self)
            return
        self._abrir(destino)

    def _abrir(self, caminho):
        try:
            bv.abrir_arquivo(caminho)
            self.rodape.configure(text=f"Aberto: {Path(caminho).name}")
        except OSError as erro:
            messagebox.showerror("Abrir", f"{caminho}\n\n{erro}", parent=self)


class Relatorio(_BaseRelatorio, tk.Tk):
    """O relatorio como programa proprio (bap_relatorios.py <id>)."""


class RelatorioNoQuadro(_BaseRelatorio, tk.Frame):
    """(28/10, Alexandre) O relatorio aberto DENTRO de outro programa (BAP
    Analista > Divergencias clientes): a mesma tela, sem janela propria."""

    def __init__(self, pai, rid: str):
        super().__init__(rid, pai=pai)

    def title(self, *_a, **_k):
        return ""

    def geometry(self, *_a, **_k):
        return ""

    def minsize(self, *_a, **_k):
        return None

    def protocol(self, *_a, **_k):
        return None


class CalendarioVisitas(tk.Canvas):
    """
    As visitas do mes num calendario (desenho do Claude Design): um cartao
    por dia, SEG a SAB, com o numero de visitas, a capacidade do vendedor
    (com um so na tela), a barrinha de ocupacao e as cidades. Feriado em
    rosa, hoje com borda verde. CLIQUE NO DIA: a janela com os clientes.
    """
    DIAS = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB")
    GAP = 6

    def __init__(self, pai, t):
        super().__init__(pai, background=bv.FUNDO, highlightthickness=0)
        self.t = t
        self.cfg = t["calendario"]
        self.ao_duplo_clique = None
        self._ultimas = []
        self._caixas = []           # [(x0, y0, x1, y1, dia)] para o clique
        self._sobre = None
        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Button-1>", self._clicou)
        self.bind("<Motion>", self._mexeu)
        self.bind("<Leave>", lambda e: self._realce(None))

    # ---- as contas
    def _semanas(self):
        import calendar as _cal                         # noqa: PLC0415
        mes = self.cfg.get("mes") or f"{datetime.now():%Y-%m}"
        ano, m = (int(x) for x in mes.split("-")[:2])
        return ano, m, [s for s in _cal.Calendar(0).monthdatescalendar(ano, m)
                        if any(d.month == m and d.weekday() < 6 for d in s)]

    @staticmethod
    def _dia_de(d):
        return d.date() if hasattr(d, "date") and callable(d.date) else d

    def _por_dia(self, linhas):
        c = self.cfg
        dia = {}
        for l in linhas:
            d = l[c["i_data"]]
            if d is None:
                continue
            d = self._dia_de(d)
            x = dia.setdefault(d, {"vis": 0, "cli": set(), "cid": {},
                                   "vend": set()})
            x["vis"] += 1
            x["cli"].add(l[c["i_cliente"]])
            x["vend"].add(l[c["i_vendedor"]])
            cid = l[c["i_cidade"]] or "?"
            x["cid"][cid] = x["cid"].get(cid, 0) + 1
        return dia

    def _feriados(self):
        fer = set()
        for f in self.cfg.get("feriados") or []:
            try:
                fer.add(datetime.strptime(str(f)[:10], "%Y-%m-%d").date())
            except ValueError:
                pass
        return fer

    def grade(self, linhas):
        """A tabela do calendario para o Excel/PDF: semana x dia."""
        ano, m, semanas = self._semanas()
        dia = self._por_dia(linhas)
        cols = [rn.col("SEMANA", "texto", 110)] + [
            rn.col(n, "texto", 120) for n in self.DIAS] + [
            rn.col("TOTAL", "int", 70)]
        saida = []
        for i, sem in enumerate(semanas, start=1):
            dentro = [d for d in sem[:6] if d.month == m]
            lin = [f"SEMANA {i} ({dentro[0]:%d} a {dentro[-1]:%d/%m})"]
            for d in sem[:6]:
                x = dia.get(d)
                lin.append("" if d.month != m else
                           f"{d:%d}: {x['vis']} vis." if x else f"{d:%d}: -")
            lin.append(sum(dia[d]["vis"] for d in sem[:6] if d in dia))
            saida.append(lin)
        return cols, saida

    # ---- o desenho
    def mostrar(self, linhas, tons=None, total=None):
        self._ultimas = list(linhas)
        self._desenhar()

    def _cartao(self, x0, y0, x1, y1, fundo, borda, larg=1, raio=6):
        r = min(raio, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r,
               x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r,
               x0, y0 + r, x0, y0]
        return self.create_polygon(pts, smooth=True, fill=fundo,
                                   outline=borda, width=larg)

    def _desenhar(self):
        self.delete("all")
        self._caixas = []
        w, h = self.winfo_width(), self.winfo_height()
        if w < 300 or h < 200:
            return
        from tkinter import font as tkfont              # noqa: PLC0415
        u = max(1.0, tkfont.Font(font=bv.fonte(8)).metrics(
            "linespace") / 14.0)
        c = self.cfg
        ano, m, semanas = self._semanas()
        dia = self._por_dia(self._ultimas)
        vendedores = {l[c["i_vendedor"]] for l in self._ultimas}
        teto = None
        if len(vendedores) == 1:
            v = next(iter(vendedores))
            teto = (c.get("tetos") or {}).get(v) or c.get("teto_padrao")
        fer = self._feriados()
        hoje = datetime.now().date()
        maior = max((x["vis"] for x in dia.values()), default=0) or 1
        G = self.GAP
        col_sem, col_tot = int(96 * u), int(74 * u)
        cab = int(26 * u)
        rod = int(34 * u)
        larg = (w - col_sem - col_tot - G * 8) / 6
        alt = (h - cab - rod - G * (len(semanas) + 2)) / max(1, len(semanas))
        f = bv.fonte
        # cabecalho
        for j, n in enumerate(self.DIAS):
            x = col_sem + G + j * (larg + G) + larg / 2
            self.create_text(x, cab / 2 + 2, text=n, font=f(8, "bold"),
                             fill=bv.SUAVE)
        self.create_text(w - col_tot / 2 - G, cab / 2 + 2, text="TOTAL",
                         font=f(8, "bold"), fill=bv.SUAVE)
        tot_dia = [0] * 6
        for i, sem in enumerate(semanas):
            y0 = cab + G + i * (alt + G)
            y1 = y0 + alt
            dentro = [d for d in sem[:6] if d.month == m]
            self.create_text(G + 4, y0 + alt / 2 - 8 * u,
                             text=f"Semana {i + 1}", anchor="w",
                             font=f(9, "bold"), fill=bv.VERDE_ESCURO)
            self.create_text(G + 4, y0 + alt / 2 + 8 * u,
                             text=f"{dentro[0]:%d} a {dentro[-1]:%d/%m}",
                             anchor="w", font=f(8), fill=bv.SUAVE)
            soma = 0
            for j, d in enumerate(sem[:6]):
                x0 = col_sem + G + j * (larg + G)
                x1 = x0 + larg
                if d.month != m:
                    self._cartao(x0, y0, x1, y1, "#EEF0ED", "#EEF0ED")
                    continue
                x = dia.get(d)
                n = x["vis"] if x else 0
                soma += n
                tot_dia[j] += n
                feriado = d in fer
                # a sexta e de prospeccao: o teto dela e menor
                teto_d = (min(teto, c.get("teto_sexta") or teto)
                          if teto and d.weekday() == 4 else teto)
                acima = bool(teto_d and n > teto_d)
                fundo = ("#FCEFEE" if feriado else bv.CARTAO if n or
                         d.weekday() < 5 else "#F7F8F6")
                borda = (bv.VERDE if d == hoje else bv.VERMELHO if acima
                         else bv.CINZA_LINHA)
                self._cartao(x0, y0, x1, y1, fundo, borda,
                             2 if d == hoje or acima else 1)
                if n:
                    self._caixas.append((x0, y0, x1, y1, d))
                # o dia (e a marca de hoje / feriado)
                self.create_text(x0 + 10, y0 + 12 * u, text=f"{d:%d}",
                                 anchor="w", font=f(9, "bold"),
                                 fill=bv.VERMELHO if feriado else bv.TEXTO)
                if feriado:
                    self.create_text(x1 - 10, y0 + 12 * u, text="Feriado",
                                     anchor="e", font=f(8), fill=bv.VERMELHO)
                elif d == hoje:
                    self.create_text(x1 - 10, y0 + 12 * u, text="Hoje",
                                     anchor="e", font=f(8, "bold"),
                                     fill=bv.VERDE_ESCURO)
                if not n:
                    continue
                # o numero grande e a capacidade
                cy = y0 + alt * 0.46
                grande = f(18 if alt >= 90 * u else 14, "bold")
                cor_n = bv.VERMELHO if acima else bv.TEXTO
                tid = self.create_text(x0 + 10, cy, text=bv.br(n), anchor="w",
                                       font=grande, fill=cor_n)
                bx = self.bbox(tid)
                if teto_d:
                    self.create_text(bx[2] + 3, cy + 3 * u, text=f"/ {teto_d}",
                                     anchor="w", font=f(10), fill=bv.SUAVE)
                cli = len(x["cli"])
                det = f"{cli} cliente{'s' if cli != 1 else ''}"
                if len(x["vend"]) > 1:
                    det += f" · {len(x['vend'])} vend."
                self.create_text(x1 - 10, cy + 3 * u, text=det, anchor="e",
                                 font=f(8), fill=bv.SUAVE)
                # as cidades (em ordem alfabetica) - so se couber
                if alt >= 78 * u:
                    cids = sorted(x["cid"].items(),
                                  key=lambda kv: str(kv[0]).upper())
                    txt = " · ".join(f"{k.title()} {v_}" for k, v_ in cids[:2])
                    if len(cids) > 2:
                        txt += f" +{len(cids) - 2}"
                    cabe = max(8, int((larg - 20) / (5.6 * u)))
                    if len(txt) > cabe:
                        txt = txt[:cabe - 1] + "…"
                    self.create_text(x0 + 10, y1 - 18 * u, text=txt,
                                     anchor="w", font=f(8), fill=bv.TEXTO)
                # a barrinha de ocupacao (do teto, ou do maior dia)
                frac = min(1.0, n / teto_d) if teto_d else n / maior
                by = y1 - 7 * u
                self.create_line(x0 + 10, by, x1 - 10, by, fill=bv.GRADE,
                                 width=max(3, int(4 * u)), capstyle="round")
                self.create_line(x0 + 10, by, x0 + 10 + (larg - 20) * frac,
                                 by, fill=bv.VERMELHO if acima else bv.VERDE,
                                 width=max(3, int(4 * u)), capstyle="round")
            # o total da semana
            tx0 = w - col_tot - G
            self._cartao(tx0, y0, w - G, y1, "#FAFBFA", bv.CINZA_LINHA)
            self.create_text((tx0 + w - G) / 2, y0 + alt / 2 - 6 * u,
                             text=bv.br(soma), font=f(14, "bold"),
                             fill=bv.TEXTO)
            self.create_text((tx0 + w - G) / 2, y0 + alt / 2 + 12 * u,
                             text="visitas", font=f(8), fill=bv.SUAVE)
        # o rodape: total por dia da semana
        yr = h - rod / 2 - 2
        self.create_text(G + 4, yr, text="TOTAL", anchor="w",
                         font=f(8, "bold"), fill=bv.SUAVE)
        for j, n in enumerate(tot_dia):
            x = col_sem + G + j * (larg + G) + larg / 2
            self.create_text(x, yr, text=bv.br(n), font=f(11, "bold"),
                             fill=bv.TEXTO)
        self.create_text(w - col_tot / 2 - G, yr, text=bv.br(sum(tot_dia)),
                         font=f(12, "bold"), fill=bv.VERDE_ESCURO)
        if self._caixas:
            self.create_text(G + 4, cab / 2 + 2, text="Clique no dia",
                             anchor="w", font=f(8), fill=bv.SUAVE)

    # ---- o clique: os clientes do dia
    def _dia_em(self, x, y):
        for x0, y0, x1, y1, d in self._caixas:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return (x0, y0, x1, y1, d)
        return None

    def _realce(self, cx):
        self.delete("realce")
        self._sobre = cx
        if cx:
            x0, y0, x1, y1, _d = cx
            rid = self._cartao(x0, y0, x1, y1, "", bv.VERDE, 2)
            self.addtag_withtag("realce", rid)
        self.configure(cursor="hand2" if cx else "")

    def _mexeu(self, e):
        cx = self._dia_em(e.x, e.y)
        if cx != self._sobre:
            self._realce(cx)

    def _clicou(self, e):
        cx = self._dia_em(e.x, e.y)
        if not cx:
            return
        d = cx[4]
        c = self.cfg
        linhas = [l for l in self._ultimas
                  if l[c["i_data"]] and self._dia_de(l[c["i_data"]]) == d]
        if linhas:
            DiaDoCalendario(self.winfo_toplevel(), d, linhas,
                            [x["nome"] for x in self.t["colunas"]])


class DiaDoCalendario(tk.Toplevel):
    """Os clientes de um dia do calendario (os filtros da aba valem)."""
    NOMES_DIA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado",
                 "domingo")

    # o que a janela mostra -> o nome da coluna na aba Calendario
    CAMPOS = {"seq": "SEQ.", "vendedor": "VENDEDOR", "cidade": "CIDADE",
              "bairro": "BAIRRO", "cliente": "CLIENTE", "nome": "NOME",
              "fantasia": "FANTASIA", "segmento": "SEGMENTO",
              "curva": "CURVA", "limite": "COM LIMITE",
              "atraso": "INADIMPLENTE", "status": "STATUS",
              "status_pl": rn.COL_ST_PLANNER}

    def __init__(self, pai, d, linhas, nomes_col):
        super().__init__(pai)
        k = {a: nomes_col.index(b) for a, b in self.CAMPOS.items()
             if b in nomes_col}
        self.title(f"Visitas de {d:%d/%m/%Y} · BAP")
        self.configure(background=bv.FUNDO)
        self.geometry("1440x600")
        self.transient(pai.winfo_toplevel())

        def v(l, nome):
            i = k.get(nome)
            return l[i] if i is not None and i < len(l) else ""
        ordem = sorted(linhas, key=lambda l: (str(v(l, "vendedor")),
                                              v(l, "seq") or 0))
        cids = Counter(str(v(l, "cidade")).title() for l in ordem)
        vend = sorted({str(v(l, "vendedor")) for l in ordem})
        cab = bv.Cabecalho(self, "Farol Roteirização",
                           f"{self.NOMES_DIA[d.weekday()].capitalize()}, "
                           f"{d:%d/%m/%Y}",
                           f"{len(ordem)} visita(s) · " + " · ".join(
                               f"{c_} {n}" for c_, n in sorted(
                                   cids.items(),
                                   key=lambda kv: str(kv[0]).upper())[:3]))
        cab.pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        cab.botao("Excel", lambda: self._excel(d, cols, dados))
        cab.botao("Fechar", self.destroy)
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=16, pady=12)
        if len(vend) == 1:
            tk.Label(corpo, text=f"Vendedor: {vend[0]}", background=bv.FUNDO,
                     foreground=bv.SUAVE, font=bv.fonte(9), anchor="w").pack(
                         fill="x", pady=(0, 6))
        cols = [rn.col("SEQ.", "int", 45), rn.col("CLIENTE", "texto", 80),
                rn.col("NOME", "texto", 230),
                rn.col("FANTASIA", "texto", 170),
                rn.col("CIDADE", "texto", 120), rn.col("BAIRRO", "texto", 130),
                rn.col("SEGMENTO", "texto", 120), rn.col("CURVA", "texto", 55),
                rn.col("STATUS", "texto", 110),
                # (21/10) SIM/NAO: o Farol Roteirizacao nao mostra R$
                rn.col("COM LIMITE", "texto", 85),
                rn.col("INADIMPLENTE", "texto", 95)]
        if len(vend) > 1:
            cols.insert(1, rn.col("VENDEDOR", "texto", 180))
        dados = []
        tons = []
        for l in ordem:
            lin = [v(l, "seq"), v(l, "cliente"), v(l, "nome"),
                   v(l, "fantasia"), v(l, "cidade"), v(l, "bairro"),
                   v(l, "segmento"), v(l, "curva"), v(l, "status") or v(l, "status_pl"),
                   v(l, "limite"), v(l, "atraso")]
            if len(vend) > 1:
                lin.insert(1, v(l, "vendedor"))
            dados.append(lin)
            at = v(l, "atraso")
            tons.append("alerta" if at == "SIM" else "")
        tab = bv.Tabela(corpo, cols, altura=14, compacta=True)
        tab.pack(fill="both", expand=True)
        tab.mostrar(dados, tons)
        tk.Label(corpo, text="Em vermelho: cliente inadimplente (título em atraso).",
                 background=bv.FUNDO, foreground=bv.SUAVE, font=bv.fonte(8),
                 anchor="w").pack(fill="x", pady=(6, 0))

    def _excel(self, d, cols, dados):
        rel = rn.novo("vc_planner", rn.VEN, f"Visitas de {d:%d/%m/%Y}")
        rel["tabelas"].append(rn.tabela("Clientes do dia", cols, dados))
        PASTA_EXPORT.mkdir(parents=True, exist_ok=True)
        try:
            caminho = bv.exportar_excel(rel, PASTA_EXPORT / (
                f"VISITAS_{d:%Y%m%d}_{datetime.now():%H%M}.xlsx"))
            bv.abrir_arquivo(caminho)
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Excel", str(erro), parent=self)


LARGURA_FILTROS = 1250       # px de filtros numa linha antes de quebrar
# (10/10) os FILTROS GERAIS: ficam na linha de cima e valem para todas as
# abas que tem a coluna. Os outros (curva, situacao, etapa...) ficam na aba
# (15/10) produto: CATEGORIA, SISTEMA, FAMILIA e LINHA do Catalogo BAP 2026
FILTROS_GERAIS = ("FILIAL", "UF", "CIDADE", "SEGMENTO", "SUPERVISOR",
                  "VENDEDOR", "CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA",
                  "PRODUTO", "FORNECEDOR")


def _repetido(nome, params) -> bool:
    """O filtro ja esta em cima como parametro? (VENDEDOR PLANNER =
    VENDEDOR, SUPERVISOR PROTHEUS = SUPERVISOR)"""
    base = nome
    for suf in (" PLANNER", " PROTHEUS"):
        if base.endswith(suf):
            base = base[:-len(suf)]
    return nome in params or base in params


def _largura_grupo(rotulo, larg, folga) -> int:
    """(10/10) A largura de verdade de "rotulo + caixa" (a conta antiga
    exagerava e a linha quebrava antes da hora)."""
    try:
        from tkinter import font as tkf                 # noqa: PLC0415
        f_rot = tkf.Font(font=bv.fonte(9))
        f_cx = tkf.nametofont("TkDefaultFont")
        return int(f_rot.measure(rotulo.capitalize()) + 6
                   + larg * f_cx.measure("0") + 28 + folga)
    except Exception:                                   # noqa: BLE001
        return int(len(rotulo) * 7.5 + larg * 7.5 + 60)


def caixa_de_filtro(barra, var, valores, larg, ao_escolher):
    """A caixa de um filtro: (todos) + valores. Lista comprida (produto,
    cliente): da para digitar e a lista encolhe; Enter escolhe."""
    longa = len(valores) > 40
    cb = ttk.Combobox(barra, textvariable=var, values=[TODOS] + valores,
                      state="normal" if longa else "readonly", width=larg)
    bv.lista_larga(cb)
    validos = set(valores) | {TODOS}

    def escolheu(_e=None):
        if var.get() in validos:
            ao_escolher(var.get())
    cb.bind("<<ComboboxSelected>>", escolheu)
    if longa:
        def digitou(e):
            if e.keysym in ("Return", "KP_Enter", "Up", "Down", "Escape"):
                return
            t = var.get().strip().upper()
            cb.configure(values=[TODOS] + ([v for v in valores
                                            if t in v.upper()]
                                           if t else valores))

        def enter(_e=None):
            if var.get().strip() == "":
                var.set(TODOS)
            elif var.get() not in validos:
                achados = [v for v in cb.cget("values") if v != TODOS]
                if not achados:
                    return
                var.set(achados[0])
            escolheu()
        cb.bind("<KeyRelease>", digitou)
        cb.bind("<Return>", enter)
        cb.bind("<KP_Enter>", enter)
    return cb


class _Vistas:
    """As abas de tabela da janela, montadas so quando alguem olha para
    elas (abrir a aba, exportar). Funciona como lista: vistas[i] monta."""

    def __init__(self, janela):
        self.janela = janela
        self._itens = []                 # [frame, t, VistaTabela | None]

    def adicionar(self, frame, t):
        self._itens.append([frame, t, None])

    def montada(self, i):
        return self._itens[i][2] if 0 <= i < len(self._itens) else None

    def __getitem__(self, i):
        item = self._itens[i]
        if item[2] is None:
            item[2] = (AbaSolicitacaoBap(item[0], item[1], self.janela)
                       if item[1].get("solicitacao_bap")
                       else VistaTabela(item[0], item[1], self.janela))
        return item[2]

    def __len__(self):
        return len(self._itens)

    def __iter__(self):
        return (self[i] for i in range(len(self._itens)))


class AbaSolicitacaoBap:
    """(09/10) A aba SOLICITAÇÃO BAP do Farol de Pedidos: o arquivo
    RELATORIOS/SOLICITACAO_BAP.xlsx com as abas dele (cada uma numa
    sub-aba). Duplo clique num item de Lojas, CD ou FRW: troca a loja de
    coleta (ProdutosExcluir + linha nova + CSV) - solicitacao_bap.py."""

    def __init__(self, pai, t, janela):
        self.t, self.janela, self.pai = t, janela, pai
        self.juntas = []
        self.tab = None
        topo = ttk.Frame(pai)
        topo.pack(fill="x", padx=12, pady=(10, 6))
        ttk.Label(topo, text="Buscar", style="Suave.TLabel").pack(
            side="left", padx=(0, 6))
        self.busca = tk.StringVar()
        ent = ttk.Entry(topo, textvariable=self.busca, width=24)
        ent.pack(side="left")
        ent.bind("<KeyRelease>", lambda e: self._mostrar())
        ttk.Button(topo, text="Recarregar", command=self.carregar).pack(
            side="left", padx=(12, 0))
        ttk.Button(topo, text="Abrir no Excel", command=self._abrir).pack(
            side="left", padx=(8, 0))
        tk.Label(topo, text="Duplo clique num item de Lojas, CD ou FRW: "
                 "trocar a loja de coleta", background=bv.FUNDO,
                 foreground=bv.SUAVE, font=bv.fonte(9)).pack(
                     side="left", padx=(16, 0))
        self.lbl = ttk.Label(topo, text="", style="Suave.TLabel")
        self.lbl.pack(side="right")
        self.nb = ttk.Notebook(pai)
        self.nb.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._contar())
        self.tabs = {}
        self.dados = {}
        self.carregar()

    # a janela pede isto de toda aba (exportar, cartoes)
    def visiveis(self):
        return []

    def texto_do_filtro(self):
        return ""

    def _abrir(self):
        import solicitacao_bap as sb                     # noqa: PLC0415
        arq = sb.caminho(AQUI)
        if arq.exists():
            bv.abrir_arquivo(arq)

    def carregar(self):
        import solicitacao_bap as sb                     # noqa: PLC0415
        try:
            self.dados = sb.ler(AQUI)
        except Exception as e:                           # noqa: BLE001
            messagebox.showerror("Solicitação BAP", str(e), parent=self.janela)
            self.dados = {}
        atual = None
        try:
            atual = self.nb.tab(self.nb.select(), "text")
        except tk.TclError:
            pass
        for aba in self.nb.tabs():
            self.nb.forget(aba)
        self.tabs = {}
        if not self.dados:
            f = ttk.Frame(self.nb)
            self.nb.add(f, text="(sem arquivo)")
            ttk.Label(f, text="RELATORIOS\\SOLICITACAO_BAP.xlsx não encontrado."
                      ).pack(padx=20, pady=20)
            return
        for aba, d in self.dados.items():
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=f"{aba}  ·  {bv.br(len(d['linhas']))}")
            cols = [{"nome": c, "tipo": "num" if c in (
                "QUANTIDADE", "DEMANDA_PEDIDO", "JA_SOLICITADO",
                "SALDO_A_SOLICITAR", "ESTOQUE_NA_ORIGEM") else (
                    "data" if c == "DATA" and all(
                        hasattr(l[d["colunas"].index("DATA")], "year")
                        for l in d["linhas"]
                        if l[d["colunas"].index("DATA")] not in (None, ""))
                    else "texto"),
                     "largura": 90 if c not in ("ID_PRODUTO", "CHAVE",
                                                "MOTIVO", "PEDIDOS") else 170}
                    for c in d["colunas"]]
            tab = bv.Tabela(f, cols, altura=14, compacta=True, zebra=True)
            tab.pack(fill="both", expand=True)
            if aba in sb.ABAS_TROCA:
                tab.ao_duplo_clique = (lambda linha, a=aba:
                                       self.trocar(a, linha))
            self.tabs[aba] = tab
        nomes = [self.nb.tab(i, "text").split("  ·  ")[0]
                 for i in self.nb.tabs()]
        if atual and atual.split("  ·  ")[0] in nomes:
            self.nb.select(nomes.index(atual.split("  ·  ")[0]))
        self._mostrar()

    # (14/10) os FILTROS GERAIS de cima (cidade, UF, produto, vendedor)
    # tambem valem aqui; a janela chama aplicar() quando um deles muda
    def aplicar(self, primeira=False):
        self._mostrar()

    @staticmethod
    def _norm(v) -> str:
        import unicodedata                               # noqa: PLC0415
        t = unicodedata.normalize("NFKD", str(v or "").strip().upper())
        return "".join(ch for ch in t if not unicodedata.combining(ch))

    @staticmethod
    def _quando(l, i_d, i_h):
        """(data, hora) da linha para ordenar: a data vem como data do
        Excel ou como texto dd/mm/aaaa (antes ordenava pelo arquivo)."""
        from datetime import date, datetime              # noqa: PLC0415
        v = l[i_d] if i_d is not None and i_d < len(l) else None
        d = None
        if isinstance(v, datetime):
            d = v
        elif isinstance(v, date):
            d = datetime(v.year, v.month, v.day)
        elif v not in (None, ""):
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%Y%m%d"):
                try:
                    d = datetime.strptime(str(v).strip()[:10], fmt)
                    break
                except ValueError:
                    continue
        h = l[i_h] if i_h is not None and i_h < len(l) else None
        h = "" if h is None else str(h)
        return (d or datetime.min, h)

    def _vend_pedidos(self) -> dict:
        """{vendedor: {pedidos}} pela aba Pedidos do farol."""
        saida = {}
        for t in (self.janela.rel or {}).get("tabelas", []):
            if t.get("titulo") != "Pedidos" or not t.get("colunas"):
                continue
            n = [c["nome"] for c in t["colunas"]]
            if "PEDIDO" not in n or "VENDEDOR" not in n:
                continue
            ip, iv = n.index("PEDIDO"), n.index("VENDEDOR")
            for l in t.get("linhas") or []:
                ped = str(l[ip] or "").strip().lstrip("0")
                if ped:
                    saida.setdefault(str(l[iv] or ""), set()).add(ped)
        return saida

    def _mostrar(self):
        b = self.busca.get().strip().upper()
        ger = {k: v for k, v in (self.janela.gerais_escolha or {}).items()
               if v not in (None, TODOS)}
        vend_ped = self._vend_pedidos() if ger.get("VENDEDOR") else {}
        for aba, tab in self.tabs.items():
            d = self.dados[aba]
            cols = d["colunas"]

            def ix(*nomes):
                return next((cols.index(n_) for n_ in nomes if n_ in cols),
                            None)
            i_d, i_h = ix("DATA"), ix("HORA")
            i_cid, i_uf = ix("CIDADE"), ix("UF")
            i_prod, i_ped = ix("COD_PRODUTO"), ix("PEDIDOS", "PEDIDO")
            # (14/10) a mais nova em cima pela DATA + HORA de verdade
            ls = sorted(d["linhas"], key=lambda l: self._quando(l, i_d, i_h),
                        reverse=True)
            if ger.get("CIDADE") and i_cid is not None:
                alvo = self._norm(ger["CIDADE"])
                ls = [l for l in ls if self._norm(l[i_cid]) == alvo]
            if ger.get("UF") and i_uf is not None:
                ls = [l for l in ls if self._norm(l[i_uf]) ==
                      self._norm(ger["UF"])]
            if ger.get("PRODUTO") and i_prod is not None:
                alvo = self._norm(ger["PRODUTO"])
                ls = [l for l in ls if self._norm(l[i_prod]) == alvo]
            if ger.get("VENDEDOR") and i_ped is not None:
                peds = vend_ped.get(ger["VENDEDOR"], set())
                ls = [l for l in ls if {p_.strip().lstrip("0") for p_ in
                                        str(l[i_ped] or "").replace(
                                            ";", "|").split("|")} & peds]
            if b:
                ls = [l for l in ls if any(b in str(v).upper() for v in l
                                           if v is not None)]
            tab.mostrar(ls, [""] * len(ls), None)
        self._contar()

    def _contar(self):
        try:
            aba = self.nb.tab(self.nb.select(), "text").split("  ·  ")[0]
        except tk.TclError:
            return
        tab = self.tabs.get(aba)
        n = len(tab._linhas) if tab else 0
        self.lbl.configure(text=f"{bv.br(n)} linhas")

    def trocar(self, aba, linha):
        import solicitacao_bap as sb                     # noqa: PLC0415
        item = sb.item_da_linha(self.dados, aba, linha)
        if sb.texto(item.get("SITUACAO_PEDIDO")).upper() not in ("",
                                                               "EM ABERTO"):
            if not messagebox.askyesno(
                    "Trocar loja de coleta",
                    f"O pedido está {item.get('SITUACAO_PEDIDO')}. Trocar a "
                    "loja de coleta mesmo assim?", parent=self.janela):
                return
        DialogoTrocaColeta(self, item)


class DialogoTrocaColeta(tk.Toplevel):
    """(09/10) Trocar a loja de coleta de um item da SOLICITACAO_BAP: a de
    agora vai para a ProdutosExcluir e a escolhida ganha a linha nova e o
    CSV (reversa de loja ou separacao de CD)."""

    def __init__(self, aba, item):
        super().__init__(aba.janela)
        self.aba, self.item = aba, item
        self.title("Trocar loja de coleta · BAP")
        self.configure(background=bv.FUNDO)
        self.transient(aba.janela.winfo_toplevel())
        self.geometry("760x560")
        bv.Cabecalho(self, "Solicitação BAP", "Trocar loja de coleta",
                     f"{item.get('COD_PRODUTO')} · {bv.br(item.get('QUANTIDADE') or 0)} un."
                     f" · {item.get('CIDADE')}").pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=18, pady=10)
        info = (f"Coletar em {item.get('COLETAR_EM')} (destino "
                f"{item.get('FILIAL_DESTINO')})  ·  pedidos "
                f"{item.get('PEDIDOS')}  ·  {item.get('aba')} de "
                f"{item.get('DATA')} {item.get('HORA')}")
        tk.Label(corpo, text=info, background=bv.FUNDO, foreground=bv.TEXTO,
                 font=bv.fonte(9, "bold"), anchor="w", justify="left",
                 wraplength=720).pack(fill="x")
        tk.Label(corpo, text=f"A loja {item.get('COLETAR_EM')} vai para a "
                 "ProdutosExcluir deste produto. Escolha onde coletar:",
                 background=bv.FUNDO, foreground=bv.SUAVE, font=bv.fonte(9),
                 anchor="w").pack(fill="x", pady=(6, 4))
        cols = [{"nome": "FILIAL", "tipo": "texto", "largura": 70},
                {"nome": "TIPO", "tipo": "texto", "largura": 150},
                {"nome": "ESTOQUE", "tipo": "num", "largura": 80},
                {"nome": "JÁ SOLICITADO", "tipo": "num", "largura": 100},
                {"nome": "DISPONÍVEL", "tipo": "num", "largura": 90},
                {"nome": "ATENDE", "tipo": "texto", "largura": 80},
                {"nome": "DESTINO", "tipo": "texto", "largura": 70}]
        self.tab = bv.Tabela(corpo, cols, altura=10, compacta=True,
                             zebra=True)
        self.tab.pack(fill="both", expand=True)
        self.tab.ao_duplo_clique = lambda l: self.gerar()
        self.msg = tk.Label(corpo, text="Procurando lojas com estoque…",
                            background=bv.FUNDO, foreground=bv.SUAVE,
                            font=bv.fonte(9), anchor="w", justify="left",
                            wraplength=720)
        self.msg.pack(fill="x", pady=(8, 0))
        bts = tk.Frame(self, background=bv.FUNDO)
        bts.pack(fill="x", padx=18, pady=(0, 14))
        self.bt = ttk.Button(bts, text="Gerar nova solicitação",
                             style="Verde.TButton", command=self.gerar)
        self.bt.pack(side="right")
        self.bt.configure(state="disabled")
        ttk.Button(bts, text="Cancelar", command=self.destroy).pack(
            side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        self.cands = []
        self.grab_set()

        def trabalho():
            import solicitacao_bap as sb                 # noqa: PLC0415
            return sb.candidatos(AQUI, item, aba.dados)
        bv.em_segundo_plano(self, trabalho, self._chegou)

    def _chegou(self, res):
        if isinstance(res, dict) and "_erro" in res:
            self.msg.configure(text=f"Não consegui ler o estoque: {res['_erro']}",
                               foreground=bv.VERMELHO)
            return
        self.cands = res or []
        linhas = [[c["filial"], c["tipo"], c["estoque"], c["comprometido"],
                   c["disponivel"], "SIM" if c["cabe"] else "PARCIAL",
                   c["destino"]] for c in self.cands]
        self.tab.mostrar(linhas, ["" if c["cabe"] else "atencao"
                                  for c in self.cands], None)
        if not self.cands:
            self.msg.configure(text="Nenhuma outra loja da cidade tem esse "
                               "produto em estoque.", foreground=bv.VERMELHO)
            return
        primeiro = self.tab.tv.get_children()[0]
        self.tab.tv.selection_set(primeiro)
        self.bt.configure(state="normal")
        self.msg.configure(text="Sugestão: a primeira da lista (a ordem do BAP "
                           "Tools: CD, loja preferencial, maior disponível). "
                           "Pode escolher outra.", foreground=bv.SUAVE)

    def gerar(self):
        sel = self.tab.tv.selection()
        linha = self.tab._por_item.get(sel[0]) if sel else None
        if not linha or str(self.bt.cget("state")) == "disabled":
            return
        c = next(x for x in self.cands if x["filial"] == linha[0])
        it = self.item
        tipo_csv = ("separação de CD" if c["tipo"] == "CD"
                    else "reversa de loja")
        if not messagebox.askyesno(
                "Trocar loja de coleta",
                f"{it.get('COD_PRODUTO')} · {bv.br(it.get('QUANTIDADE') or 0)} un."
                f"\n\n1. A loja {it.get('COLETAR_EM')} vai para a "
                f"ProdutosExcluir deste produto.\n2. Linha nova coletando na "
                f"{c['filial']} ({c['tipo']}), STATUS ABRIR SOLICITAÇÃO."
                f"\n3. CSV novo de {tipo_csv} em Arquivos para Importar."
                + ("" if c["cabe"] else f"\n\nAtenção: a {c['filial']} tem "
                   f"só {bv.br(c['disponivel'])} disponível(is).")
                + "\n\nConfirma?", parent=self):
            return
        self.bt.configure(state="disabled")
        self.msg.configure(text="Gravando…", foreground=bv.SUAVE)

        def trabalho():
            import solicitacao_bap as sb                 # noqa: PLC0415
            return sb.trocar_coleta(AQUI, it, c)

        def pronto(res):
            if isinstance(res, dict) and "_erro" in res:
                try:
                    self.bt.configure(state="normal")
                    self.msg.configure(text=f"Não gravou: {res['_erro']}",
                                       foreground=bv.VERMELHO)
                except tk.TclError:
                    pass
                return
            messagebox.showinfo(
                "Trocar loja de coleta",
                f"Pronto.\n\nProdutosExcluir: {res['excluido'][1]} na "
                f"{res['excluido'][0]}.\nLinha nova em {res['aba']} "
                f"(pedidos {', '.join(res['pedidos'])}).\nCSV: "
                f"{', '.join(res['csv']) or '—'}", parent=self.aba.janela)
            self.destroy()
            self.aba.carregar()
        bv.em_segundo_plano(self, trabalho, pronto)


class VistaTabela:
    """Uma aba: filtros (so de tela) + recorte + busca + a tabela."""

    def __init__(self, pai, t, janela):
        self.t = t
        self.janela = janela
        nomes = [c["nome"] for c in t["colunas"]]
        barra = ttk.Frame(pai)
        barra.pack(fill="x", padx=12, pady=(12, 8))
        self.filtros = {}
        self._ocultos = set()          # (22/10) os que seguem o de cima
        # (22/10) o que estava escolhido antes de atualizar (ver
        # Relatorio._guardar_filtros)
        antes = (getattr(janela, "_filtros_guardados", None) or {}).get(
            t["titulo"]) or {}
        # muitos filtros: quebram em mais de uma linha (antes os do fim
        # sumiam para fora da tela). A conta e pela largura estimada.
        usado, linhas_f = 0, 1
        fora = set(t.get("filtros_fora") or ())
        # (10/10) os FILTROS GERAIS (linha de cima) que valem nesta aba: a
        # coluna existe aqui. O padrao da aba (FILIAL = TODAS na visao por
        # familia) vale enquanto o de cima esta em (todos)
        decl = {rn.nome_filtro(f): f for f in t.get("filtros", [])}
        self.gerais = {}
        for nome_g in janela.gerais:
            if nome_g in nomes:
                f = decl.get(nome_g)
                self.gerais[nome_g] = (
                    nomes.index(nome_g),
                    isinstance(f, dict) and bool(f.get("multi")),
                    f.get("padrao") if isinstance(f, dict) else None)
        for f in t.get("filtros", []):
            nome = rn.nome_filtro(f)
            if nome not in nomes or nome in fora:
                continue
            if nome in janela.gerais:
                continue                 # esta na linha de cima
            if _repetido(nome, janela.nomes_params):
                # (10/10) o MES da aba (padrao = o mes de cima) continua
                # VALENDO, so nao aparece; o resto que repete o de cima sai
                if isinstance(f, dict) and ("padrao" in f or f.get("oculto")):
                    f = dict(f, oculto=True)
                else:
                    continue
            i = nomes.index(nome)
            multi = isinstance(f, dict) and f.get("multi")
            base_f = t.get("linhas_filtro") or t["linhas"]
            if multi:
                valores = sorted({x.strip() for l in base_f
                                  for x in str(l[i] or "").split(";")
                                  if x.strip()})
            elif t["colunas"][i].get("tipo") in ("data", "dia"):
                valores = [bv.data_br(d) for d in sorted(
                    {l[i] for l in base_f if l[i] not in (None, "")},
                    reverse=True)]
            else:
                valores = sorted({bv.formatar(l[i], "texto")
                                  for l in base_f if l[i] not in (None, "")})
            padrao = f.get("padrao") if isinstance(f, dict) else None
            if isinstance(f, dict) and f.get("oculto"):
                # (08/10) filtro que segue o de cima (o MES da capa): vale,
                # mas nao aparece - era redundante na tela
                # o padrao vale mesmo sem linha naquele mes (antes caia em
                # "todos" e a aba mostrava os 12 meses)
                self.filtros[i] = (tk.StringVar(
                    value=padrao if padrao not in (None, "") else TODOS),
                    multi, nome)
                self._ocultos.add(nome)
                continue
            rot = nome if len(nome) <= 3 else (
                nome.title() if nome.startswith("STATUS ")
                else nome.capitalize())
            larg = min(20, max(8, max((len(v) for v in valores), default=8)))
            w = int(len(rot) * 7.5 + larg * 7.5 + 58)
            if usado and usado + w > LARGURA_FILTROS:
                barra = ttk.Frame(pai)
                barra.pack(fill="x", padx=12, pady=(0, 8))
                usado, linhas_f = 0, linhas_f + 1
            usado += w
            ttk.Label(barra, text=rot, style="Suave.TLabel").pack(
                side="left", padx=(0, 6))
            var = tk.StringVar(value=padrao if padrao in valores else TODOS)
            ja = (antes.get("f") or {}).get(nome)
            if ja is not None and (ja == TODOS or ja in valores or multi):
                var.set(ja)              # (22/10) o que estava escolhido
            caixa_de_filtro(barra, var, valores, larg,
                            lambda _v: self.aplicar()).pack(
                                side="left", padx=(0, 16))
            self.filtros[i] = (var, multi, nome)
        # (08/10) enxuta: sem RECORTE e sem BUSCAR (Farol de Pedidos)
        enxuta = bool(t.get("enxuta"))
        self.recortes = [] if enxuta else (t.get("recortes") or [])
        self.var_recorte = tk.StringVar(value=TODOS)
        if antes.get("recorte") in [r[0] for r in self.recortes]:
            self.var_recorte.set(antes["recorte"])
        # (10/10) recorte e busca na MESMA linha dos filtros da aba, se
        # couberem (os gerais subiram: sobra espaco)
        cabe = (usado + (300 if self.recortes else 0) + 260
                <= LARGURA_FILTROS)
        if not enxuta and (linhas_f > 1 or not cabe):
            barra = ttk.Frame(pai)        # recorte e busca na linha de baixo
            barra.pack(fill="x", padx=12, pady=(0, 8))
        if self.recortes:
            ttk.Label(barra, text="Recorte", style="Suave.TLabel").pack(
                side="left", padx=(0, 6))
            cb = ttk.Combobox(barra, textvariable=self.var_recorte,
                              state="readonly", width=30,
                              values=[TODOS] + [r[0] for r in self.recortes])
            cb.pack(side="left", padx=(0, 16))
            cb.bind("<<ComboboxSelected>>", lambda e: self.aplicar())
        self.busca = tk.StringVar(value=antes.get("busca") or "")
        if not enxuta:
            ttk.Label(barra, text="Buscar", style="Suave.TLabel").pack(
                side="left", padx=(0, 6))
            ent = ttk.Entry(barra, textvariable=self.busca, width=22)
            ent.pack(side="left")
            ent.bind("<KeyRelease>", lambda e: self.aplicar())
        if (t.get("edicao") or {}).get("novo"):
            ttk.Button(barra, text="Novo", style="Verde.TButton",
                       command=self.novo).pack(side="left", padx=(16, 0))
        if t.get("garantia") and (janela.rel or {}).get("garantia"):
            ttk.Button(barra, text="Nova garantia", style="Verde.TButton",
                       command=lambda: self.abrir_garantia(None)).pack(
                           side="left", padx=(16, 0))
        self.tem_detalhe = bool(t.get("detalhe")) and callable(
            (janela.rel or {}).get("detalhe_pedido"))
        if self.tem_detalhe:
            ttk.Button(barra, text="Ver pedido", command=self.ver_selecionado
                       ).pack(side="left", padx=(16, 0))
        self.lbl = ttk.Label(barra, text="", style="Suave.TLabel")
        self.lbl.pack(side="right")
        # (06/10) TABELAS JUNTAS: embaixo da tabela, numa divisoria que se
        # arrasta, as tabelas ligadas a ela (ex.: Pedidos > Analitico
        # produto, Gerar separacao CD e Gerar reversa de lojas) - cada uma
        # mostra so o que e das linhas que estao na tela
        alvo = pai
        self.juntas = []
        empilha = bool(t.get("juntas_em_cima"))
        # (04/11, Alexandre) "Todas abas terem esse formato, onde for
        # possivel": sem rolar de lado onde cabe; Equipe/Acomp. RH sempre
        cabe = True if t.get("sem_rolar_lado") else "auto"
        if t.get("juntas") and empilha:
            # (04/11, Alexandre) "Ficou muito achatado": as tabelinhas de
            # cima com a altura certa (gerente 2 linhas, supervisores 4), sem
            # divisoria; a de vendedores fica com o resto da tela
            for k, j in enumerate(t["juntas"]):
                cartao = tk.Frame(pai, background=bv.CARTAO,
                                  highlightthickness=1,
                                  highlightbackground=bv.CINZA_LINHA)
                cartao.pack(fill="x", pady=(0 if k == 0 else 8, 0))
                lb = tk.Label(cartao, text=j.get("titulo")
                              or j["tabela"]["titulo"])   # o nome vai na faixa
                tab_j = bv.Tabela(cartao, [dict(c_) for c_ in
                                           j["tabela"]["colunas"]],
                                  altura=j.get("altura") or 4, compacta=True,
                                  grupos=j["tabela"].get("grupos"),
                                  zebra=bool(t.get("zebra")), cabe=cabe)
                tab_j.pack(fill="x", padx=1, pady=(0, 1))
                self.juntas.append({"j": j, "tab": tab_j, "rotulo": lb,
                                    "linhas": []})
            alvo = tk.Frame(pai, background=bv.CARTAO,
                            highlightthickness=1,
                            highlightbackground=bv.CINZA_LINHA)
            alvo.pack(fill="both", expand=True, pady=(8, 0))
        elif t.get("juntas"):
            pw = ttk.PanedWindow(pai, orient="vertical")
            pw.pack(fill="both", expand=True)
            cima, baixo = ttk.Frame(pw), ttk.Frame(pw)
            if empilha:
                # (04/11, Alexandre) TABELINHAS uma embaixo da outra: as
                # juntas (gerente, supervisores) em cima, a principal
                # (vendedores) embaixo
                pw.add(baixo, weight=1)
                pw.add(cima, weight=3)
            else:
                pw.add(cima, weight=3)
                pw.add(baixo, weight=2)
            alvo = cima
            # LADO A LADO, como no Overview (BI): um quadro por tabela, com
            # o titulo e a contagem; so as colunas que cabem ("mostrar")
            grade = tk.Frame(baixo, background=bv.FUNDO)
            grade.pack(fill="both", expand=True, pady=(8, 0))
            for k, j in enumerate(t["juntas"]):
                if not empilha:
                    grade.columnconfigure(k, weight=j.get("peso", 1),
                                          uniform="j")
                cartao = tk.Frame(grade, background=bv.CARTAO,
                                  highlightthickness=1,
                                  highlightbackground=bv.CINZA_LINHA)
                if empilha:
                    cartao.grid(row=k, column=0, sticky="nsew",
                                pady=(0 if k == 0 else 6, 0))
                    grade.rowconfigure(k, weight=j.get("altura", 1) + 3)
                else:
                    cartao.grid(row=0, column=k, sticky="nsew",
                                padx=(0 if k == 0 else 4, 0))
                lb = tk.Label(cartao, text=j.get("titulo")
                              or j["tabela"]["titulo"],
                              background=bv.CARTAO, foreground=bv.TEXTO,
                              font=bv.fonte(10, "bold"), anchor="w")
                if not empilha:      # (04/11) empilhadas: o nome vai na
                    lb.pack(fill="x", padx=10, pady=(6, 4))   # faixa de cima
                mostrar = j.get("mostrar")
                larg_j = j.get("larguras") or {}
                cols = [dict(c_, oculta=c_.get("oculta") or (
                    bool(mostrar) and c_["nome"] not in mostrar),
                    largura=larg_j.get(c_["nome"], c_.get("largura")))
                    for c_ in j["tabela"]["colunas"]]
                tab_j = bv.Tabela(cartao, cols,
                                  altura=(j.get("altura") or 7)
                                  if empilha else 8, compacta=True,
                                  grupos=j["tabela"].get("grupos")
                                  if empilha else None,
                                  zebra=bool(t.get("zebra")), cabe="auto")
                tab_j.pack(fill="both", expand=True, padx=1, pady=(0, 1))
                if j.get("editavel") and t.get("edicao"):
                    # (10/10) as pendencias editam como a tabela de cima
                    tab_j.ao_duplo_clique = self.editar
                self.juntas.append({"j": j, "tab": tab_j, "rotulo": lb,
                                    "linhas": []})
            if empilha:
                grade.columnconfigure(0, weight=1)
            else:
                grade.rowconfigure(0, weight=1)

            def dividir(e=None, pw=pw):
                # a divisoria abre em 55% (pedidos) / 45% (os 3 quadros)
                alt = pw.winfo_height()
                if alt > 200 and not getattr(pw, "_dividido", False):
                    pw._dividido = True
                    if empilha:     # o tamanho das tabelinhas de cima
                        px = sum(14 + 60 + 26 * (j.get("altura") or 1)
                                 for j in t["juntas"])
                        pw.sashpos(0, int(min(px, alt * 0.6)))
                        return
                    pw.sashpos(0, int(alt * float(t.get("divisao") or 0.55)))
            pw.bind("<Configure>", dividir, add="+")
        if t.get("calendario"):
            self.tab = CalendarioVisitas(alvo, t)
        else:
            self.tab = bv.Tabela(alvo, t["colunas"], grupos=t.get("grupos"),
                                 compacta=bool(t.get("compacta")),
                                 zebra=bool(t.get("zebra")),
                                 letra=t.get("letra"), cabe=cabe)
        self.tab.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        if t.get("edicao") and (t["edicao"].get("so_colunas")
                                and self.tem_detalhe):
            # (13/10) duplo clique na AUTORIZACAO edita; no resto, o pedido
            def _duplo(linha, so=tuple(t["edicao"]["so_colunas"])):
                if getattr(self.tab, "coluna_clicada", None) in so:
                    self.editar(linha)
                else:
                    self.ver_pedido(linha)
            self.tab.ao_duplo_clique = _duplo
        elif t.get("garantia") and (janela.rel or {}).get("garantia"):
            self.tab.ao_duplo_clique = self.abrir_garantia   # (14/10)
        elif t.get("edicao"):
            self.tab.ao_duplo_clique = self.editar
        elif self.tem_detalhe:
            self.tab.ao_duplo_clique = self.ver_pedido
        if self.juntas and hasattr(self.tab, "tv"):
            # (09/10) um clique no pedido: as tabelas de baixo so com ele
            self.tab.tv.bind("<<TreeviewSelect>>", self._encher_juntas,
                             add="+")
            self.tab.tv.bind("<Escape>", self._limpar_selecao, add="+")
        self.editadas = set()
        self.aplicar(primeira=True)

    def visiveis(self):
        return [l for l, _ in self._filtradas()]

    def _geral_ativo(self):
        """{coluna: (valor, multi)} dos filtros gerais que valem aqui."""
        saida = {}
        for nome, (i, multi, padrao) in self.gerais.items():
            v = self.janela.gerais_escolha.get(nome, TODOS)
            if v == TODOS:
                v = padrao
            if v not in (None, TODOS):
                saida[i] = (v, multi, nome)
        return saida

    def _gerais_sem_coluna(self):
        return [n for n, v in self.janela.gerais_escolha.items()
                if v != TODOS and n in self.janela.gerais
                and n not in self.gerais]

    def texto_do_filtro(self):
        partes = [f"{nome}: {v}" for v, _m, nome in
                  self._geral_ativo().values() if v != rn.TODAS_FILIAIS]
        partes += [f"{nome}: {var.get()}" for var, _m, nome in
                   self.filtros.values() if var.get() != TODOS]
        if self.var_recorte.get() != TODOS:
            partes.append(f"Recorte: {self.var_recorte.get()}")
        if self.busca.get().strip():
            partes.append(f"Busca: {self.busca.get().strip()}")
        return ("Filtro: " + " · ".join(partes)) if partes else ""

    def filtros_colunas(self):
        """{indice da coluna: valor} dos filtros de coluna ligados."""
        filtros = {i: v for i, (v, m, _n) in self._geral_ativo().items()}
        for i, (var, multi, _n) in self.filtros.items():
            if var.get() != TODOS:
                filtros[i] = var.get()
        return filtros

    def _filtradas(self):
        busca = self.busca.get().strip().upper()
        rec = next((r for r in self.recortes
                    if r[0] == self.var_recorte.get()), None)
        saida = []
        # TOP N (Top 30 clientes): o filtro corre na carteira inteira e o
        # top se refaz dentro dele
        base = self.t.get("linhas_filtro") or self.t["linhas"]
        tons_b = (self.t.get("tons_filtro") if self.t.get("linhas_filtro")
                  else self.t.get("tons")) or [""] * len(base)
        filtros = {i: (v, m) for i, (v, m, _n) in self._geral_ativo().items()}
        for i, (var, multi, _n) in self.filtros.items():
            if var.get() != TODOS:
                filtros[i] = (var.get(), multi)
        for l, tom in zip(base, tons_b):
            ok = True
            for i, (v, multi) in filtros.items():
                if multi:
                    if v not in [x.strip() for x in str(l[i] or "").split(";")]:
                        ok = False
                        break
                elif (bv.data_br(l[i]) if self.t["colunas"][i].get("tipo")
                      in ("data", "dia") else bv.formatar(l[i], "texto")) != v:
                    ok = False
                    break
            if not ok:
                continue
            if rec and callable(rec[1]) and not rec[1](l):
                continue
            if busca and not any(busca in str(x).upper() for x in l
                                 if x is not None and not isinstance(x, dict)):
                continue
            if id(l) in self.editadas:
                tom = "editado"
            saida.append((l, tom))
        if rec and isinstance(rec[1], dict) and rec[1].get("top"):
            c = rec[1]["coluna"]
            if rec[1].get("so_positivo"):     # (10/10) top de quem comprou
                saida = [x for x in saida if (x[0][c] or 0) > 0]
            saida.sort(key=lambda x: -(x[0][c] or 0))
            saida = saida[:rec[1]["top"]]
        if self.t.get("top_n"):
            saida = saida[:self.t["top_n"]]
            if self.t.get("ordem_top"):         # o top: da maior meta
                i_m, i_f = self.t["ordem_top"]
                saida.sort(key=lambda x: (-(x[0][i_m] or 0),
                                          -(x[0][i_f] or 0)))
        return saida

    def total_de(self, linhas):
        """O TOTAL do que esta na tela: o da tabela, sem filtro; com
        filtro, so quando a tabela traz o total pronto daquele grupo
        (totais_por) e a tela mostra o grupo inteiro."""
        if callable(self.t.get("total_de")):
            try:
                return self.t["total_de"](linhas)
            except Exception:                           # noqa: BLE001
                return None
        if len(linhas) == len(self.t["linhas"]):
            return self.t.get("total")
        tp = self.t.get("totais_por")
        if not tp or not linhas:
            return None
        c = tp["coluna"]
        vals = {l[c] for l in linhas}
        if len(vals) != 1:
            return None
        v = vals.pop()
        if sum(1 for l in self.t["linhas"] if l[c] == v) != len(linhas):
            return None
        return tp["valores"].get(v)

    def _ligadas(self, x, linhas):
        """As linhas da tabela junta que sao das linhas da tela."""
        if x["j"].get("liga") is None:      # (10/10) solta: todas as linhas
            tj = x["j"]["tabela"]
            ts = [("editado" if id(l) in self.editadas else tom) for l, tom in
                  zip(tj["linhas"], tj.get("tons") or [""] * len(tj["linhas"]))]
            return list(tj["linhas"]), ts
        col_j, col_m, sep = x["j"]["liga"]
        nomes = [c["nome"] for c in self.t["colunas"]]
        tj = x["j"]["tabela"]
        nj = [c["nome"] for c in tj["colunas"]]
        if col_m not in nomes or col_j not in nj:
            return [], []
        im, ij = nomes.index(col_m), nj.index(col_j)
        chaves = {str(l[im] or "").strip().lstrip("0") for l in linhas}
        tons = tj.get("tons") or [""] * len(tj["linhas"])
        ls, ts = [], []
        for l, tom in zip(tj["linhas"], tons):
            vals = str(l[ij] or "").split(sep) if sep else [str(l[ij] or "")]
            if any(v.strip().lstrip("0") in chaves for v in vals if v.strip()):
                ls.append(l)
                ts.append(tom)
        return ls, ts

    def aplicar(self, primeira=False):
        f = self._filtradas()
        filtrou = len(f) != len(self.t["linhas"])
        self.tab.mostrar([l for l, _ in f], [t for _, t in f],
                         self.total_de([l for l, _ in f]))
        for x in self.juntas:
            ls, ts = self._ligadas(x, [l for l, _ in f])
            x["linhas"] = ls              # o que vai no Excel/PDF: a tela
        self._encher_juntas()
        if self.t.get("top_n"):
            filtrou = False             # o top se refaz no filtro
        txt = (f"{bv.br(len(f))} de {bv.br(len(self.t['linhas']))}"
               if filtrou else f"{bv.br(len(f))} linhas")
        sem = self._gerais_sem_coluna()
        if sem:                       # o filtro de cima nao vale nesta aba
            txt = (f"{', '.join(n.capitalize() for n in sem)} não se "
                   f"aplica a esta aba   ·   {txt}")
        self.lbl.configure(text=txt)
        if not primeira and self.janela.vista_atual() is self:
            self.janela.pintar_kpis()

    def _encher_juntas(self, _e=None):
        """(09/10) As tabelas de baixo (separacao CD, reversa, analitico):
        com um pedido SELECIONADO (um clique), so as linhas dele; sem
        selecao, as de todos os pedidos da tela."""
        if not self.juntas:
            return
        try:
            sel = [self.tab._por_item[i] for i in self.tab.tv.selection()
                   if i in self.tab._por_item]
        except (tk.TclError, AttributeError):
            sel = []
        ped = ""
        if sel and self.juntas[0]["j"].get("liga") is not None:
            nomes = [c["nome"] for c in self.t["colunas"]]
            col_m = self.juntas[0]["j"]["liga"][1]
            if col_m in nomes:
                ped = " · ".join(sorted({str(l[nomes.index(col_m)] or "")
                                         for l in sel}))[:40]
        for x in self.juntas:
            if x["j"].get("liga") is None:
                ls, ts = self._ligadas(x, [])
            elif sel:
                ls, ts = self._ligadas(x, sel)
            else:
                ls = x.get("linhas") or []
                tj = x["j"]["tabela"]
                tom = dict(zip(map(id, tj["linhas"]),
                               tj.get("tons") or [""] * len(tj["linhas"])))
                ts = [tom.get(id(l), "") for l in ls]
            x["tab"].mostrar(ls, ts, x["j"]["tabela"].get("total")
                             if x["j"].get("com_total") else None)
            tit = x["j"].get("titulo") or x["j"]["tabela"]["titulo"]
            x["rotulo"].configure(
                text=f"{tit}  ·  {bv.br(len(ls))}"
                + (f"  ·  pedido {ped}" if ped else ""))

    def _limpar_selecao(self, _e=None):
        try:
            self.tab.tv.selection_remove(*self.tab.tv.selection())
        except tk.TclError:
            pass

    # ---- o detalhe do pedido -------------------------------------------
    def ver_selecionado(self):
        sel = self.tab.tv.selection()
        linha = self.tab._por_item.get(sel[0]) if sel else None
        if linha is None:
            messagebox.showinfo("Ver pedido", "Selecione uma linha.",
                                parent=self.janela)
            return
        self.ver_pedido(linha)

    def linhas_na_tela(self):
        """(22/10) as linhas na ORDEM em que estao na tela (filtro e
        ordenacao por coluna) - para o anterior/proximo do pedido."""
        try:
            por = self.tab._por_item
            ls = [por[i] for i in self.tab.tv.get_children() if i in por]
            if ls:
                return ls
        except (AttributeError, tk.TclError):
            pass
        return self.visiveis()

    def ver_pedido(self, linha):
        try:
            d = self.janela.rel["detalhe_pedido"](self.t, linha)
        except Exception as e:                           # noqa: BLE001
            messagebox.showerror("Ver pedido", str(e), parent=self.janela)
            return
        if not d:
            messagebox.showinfo("Ver pedido",
                                "Pedido não encontrado na TABELA_BAP.",
                                parent=self.janela)
            return
        # (22/10, Alexandre) setas para ir ao pedido anterior/proximo da
        # lista que esta na tela (com os filtros escolhidos)
        ls = self.linhas_na_tela()
        idx = next((k for k, l_ in enumerate(ls) if l_ is linha), None)
        nav = {"titulo": self.t["titulo"], "linhas": ls, "i": idx,
               "fn": self.janela.rel["detalhe_pedido"], "t": self.t} \
            if idx is not None and len(ls) > 1 else None
        # (14/10) a autorizacao de venda so se GRAVA no Farol de Pedidos;
        # nos outros farois (Saldo, Markup...) a janela do pedido so le
        DetalhePedido(self.janela, d, editar_aut=(
            (self.janela.rel or {}).get("id") in AUTORIZA_EM), nav=nav)

    # ---- a edicao: so por lista, nunca digitando ----------------------
    def editar(self, linha):
        ed = self.t["edicao"]
        chave = linha[ed["chave"]] if len(linha) > ed["chave"] else ""
        if not chave:
            messagebox.showinfo(
                "Editar", "Nota concluída (anterior ao controle de 01/10/2026).",
                parent=self.janela)
            return
        Edicao(self.janela, self, linha, chave, ed)

    def abrir_garantia(self, linha):
        """(14/10) A janela da garantia: detalhe do cliente + edicao."""
        g = self.janela.rel["garantia"]
        ticket = None
        if linha is not None:
            ticket = linha[self.t["garantia"]["i_ticket"]]
        DialogoGarantia(self.janela, g, ticket)

    def novo(self):
        """Uma linha nova (so nas tabelas que deixam acrescentar)."""
        ed = self.t["edicao"]
        self._n_novo = getattr(self, "_n_novo", 0) + 1
        linha = [None] * len(self.t["colunas"]) + [f"NOVO-{self._n_novo}"]
        Edicao(self.janela, self, linha, linha[-1], ed)

    def aplicar_edicao(self, linha, chave, valores: dict):
        ed = self.t["edicao"]
        if str(chave).startswith("NOVO") and not any(
                l is linha for l in self.t["linhas"]):
            if not any(v for v in valores.values()):
                return
            self.t["linhas"].insert(0, linha)
            self.t.setdefault("tons", []).insert(0, "")
        mudou = {}
        for c in ed["campos"]:
            if c["campo"] not in valores:
                continue
            v = valores[c["campo"]]
            idx = c.get("col")
            atual = linha[idx] if idx is not None else None
            if c.get("numero"):         # (16/10) VLR FRETE (REAL)
                import pos_venda                        # noqa: PLC0415
                try:
                    n = pos_venda.valor_digitado(v)
                    if n is not None and n < 0:
                        raise ValueError(v)
                except ValueError:
                    messagebox.showerror(
                        "Editar", f"{bv._rotulo(c['rotulo'])}: \"{v}\" não "
                        "é um valor. Escreva só o número (ex.: 278,40) ou "
                        "deixe vazio.", parent=self.janela)
                    return
                a_ = atual if isinstance(atual, (int, float)) else None
                if (n is None and a_ is None) or (
                        n is not None and a_ is not None
                        and abs(n - a_) < 0.005):
                    continue
                mudou[c["campo"]] = "" if n is None else n
                if idx is not None:
                    linha[idx] = n
                continue
            atual_txt = bv.formatar(atual, "data" if c.get("data") else "texto")
            if v == atual_txt:
                continue
            mudou[c["campo"]] = v
            if idx is not None:
                tipo = self.t["colunas"][idx].get("tipo", "texto") \
                    if idx < len(self.t["colunas"]) else "texto"
                if c.get("data"):
                    from bap_dados import data_de        # noqa: PLC0415
                    linha[idx] = data_de(v) if v else None
                elif tipo in ("int", "num", "num2", "moeda", "moeda2"):
                    try:
                        n = float(str(v).replace(",", "."))
                        linha[idx] = int(n) if tipo == "int" else n
                    except ValueError:
                        linha[idx] = 0
                else:
                    linha[idx] = v
        if mudou:
            if ed.get("ao_mudar"):
                ed["ao_mudar"](linha)          # ex.: refaz o VLR FRETE
            self.janela.anotar(ed, chave, mudou)
            self.editadas.add(id(linha))
            self.aplicar()


def _nome_bonito(nome):
    import email_parcial as ep                          # noqa: PLC0415
    return ep.nome_bonito(nome)


class EnvioParcial(tk.Toplevel):
    """Quem recebe a parcial: marcado = vai. Sem e-mail no Planner, nao da
    para marcar (cadastre em Planner › cadastro e alteracao de vendedor)."""

    def __init__(self, janela, pessoas, params, modo="parcial"):
        super().__init__(janela)
        self.janela, self.params = janela, params
        # (30/10) modo "inadimplencia": a mesma janela para o e-mail dos
        # clientes inadimplentes (Farol de Inadimplencia)
        self.modo = modo
        inad = modo == "inadimplencia"
        self.nome_envio = "Enviar inadimplência" if inad else \
            "Enviar Parcial"
        self.title("Enviar inadimplência por e-mail" if inad
                   else "Enviar Parcial via email")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        bv.Cabecalho(self, "Farol de Inadimplência" if inad else
                     "Farol de Metas",
                     "Enviar por e-mail" if inad else
                     "Enviar Parcial via email",
                     "os clientes inadimplentes de cada um" if inad else
                     "a parcial de cada um, no formato do RH").pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=20, pady=12)
        self.marcas = []
        for n, p in enumerate(pessoas):
            var = tk.BooleanVar(value=bool(p["email"]))
            cb = ttk.Checkbutton(corpo, variable=var)
            cb.grid(row=n, column=0, sticky="w")
            if not p["email"]:
                cb.state(["disabled"])
            for j, (txt, larg) in enumerate(((p["cargo"].title(), 11),
                                             (_nome_bonito(p["nome"]), 36),
                                             (p["email"] or "sem e-mail no "
                                              "Planner", 38),
                                             (f"cc {p['cc']}" if p.get("cc")
                                              else "", 38)), start=1):
                tk.Label(corpo, text=txt, width=larg, anchor="w",
                         background=bv.FUNDO, font=bv.fonte(9),
                         foreground=bv.SUAVE if j == 4 else
                         bv.TEXTO if p["email"] or j < 3
                         else bv.VERMELHO).grid(row=n, column=j, sticky="w",
                                                pady=1)
            self.marcas.append((var, p))
        tk.Label(self, text=("Vendedor recebe os clientes dele (supervisor "
                             "em cópia); supervisor, os da equipe (gerente "
                             "em cópia); gerente, todos. Quem não tem "
                             "cliente inadimplente não recebe. PDF em anexo."
                             if inad else
                             "Vendedor recebe os números dele (supervisor em "
                             "cópia); supervisor, os da equipe (gerente em "
                             "cópia); gerente, o time inteiro. PDF em "
                             "anexo."),
                 background=bv.FUNDO, foreground=bv.SUAVE, font=bv.fonte(8),
                 anchor="w").pack(fill="x", padx=20)
        botoes = tk.Frame(self, background=bv.FUNDO)
        botoes.pack(fill="x", padx=20, pady=(8, 16))
        ttk.Button(botoes, text="Enviar agora", style="Verde.TButton",
                   command=lambda: self.ir(False)).pack(side="right")
        ttk.Button(botoes, text="Abrir no Outlook para revisar",
                   command=lambda: self.ir(True)).pack(side="right", padx=8)
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(
            side="right")
        self.grab_set()

    def ir(self, revisar):
        escolhidos = [p for var, p in self.marcas if var.get() and p["email"]]
        if not escolhidos:
            messagebox.showinfo(self.nome_envio, "Marque quem recebe.",
                                parent=self)
            return
        inad = self.modo == "inadimplencia"
        if not revisar and not messagebox.askyesno(
                self.nome_envio,
                f"Enviar {'os inadimplentes' if inad else 'a parcial'} por "
                f"e-mail para até {len(escolhidos)} "
                f"pessoa(s)?\n\n" + "\n".join(
                    f"{_nome_bonito(p['nome'])} <{p['email']}>"
                    for p in escolhidos[:20])
                + ("\n..." if len(escolhidos) > 20 else ""), parent=self):
            return
        janela, params = self.janela, self.params
        self.destroy()
        nome_envio = self.nome_envio
        janela.rodape.configure(text="Montando os PDFs…")

        def trabalho():
            import email_parcial as ep                  # noqa: PLC0415
            if inad:
                import email_inadimplencia as ei        # noqa: PLC0415
                itens = ei.preparar(AQUI, escolhidos)
                if not itens:
                    return {"_erro": "Nenhum dos marcados tem cliente "
                                     "inadimplente."}
            else:
                itens = ep.preparar(AQUI, params, escolhidos)
            return ep.enviar(itens, revisar=revisar)

        def pronto(res):
            if isinstance(res, dict) and "_erro" in res:
                messagebox.showerror(nome_envio, str(res["_erro"]),
                                     parent=janela)
                return
            partes = list(res.get("avisos") or [])
            if res["enviados"]:
                partes.append(f"{len(res['enviados'])} e-mail(s) enviado(s) "
                              f"pelo Outlook.")
            if res["abertos"]:
                if res.get("metodo") == "WEB":
                    partes.append(
                        f"{len(res['abertos'])} e-mail(s) aberto(s) no "
                        f"Outlook na Web (uma aba por pessoa), com os números "
                        f"no texto: confira e clique em Enviar. O PDF de cada "
                        f"um está na pasta abaixo, se quiser anexar.\n\nPara "
                        f"o programa enviar sozinho, com o PDF: abra o "
                        f"Outlook clássico uma vez e adicione a sua conta "
                        f"(Arquivo › Adicionar conta).")
                else:
                    onde = ("no Outlook" if res.get("metodo") == "Outlook"
                            else "no seu programa de e-mail")
                    partes.append(f"{len(res['abertos'])} e-mail(s) aberto(s)"
                                  f" {onde}, já com o PDF: confira e clique "
                                  f"em Enviar.")
            if res["eml"]:
                partes.append(
                    f"{len(res['eml'])} e-mail(s) ficaram prontos na pasta, "
                    f"um arquivo .eml por pessoa (dois cliques abre o e-mail "
                    f"com o PDF; é só Enviar).\n\nPara o programa enviar "
                    f"sozinho: abra o Outlook clássico uma vez e adicione a "
                    f"sua conta (Arquivo › Adicionar conta).")
            if res["erros"]:
                partes.append("Problemas:\n" + "\n".join(res["erros"][:8]))
            janela.rodape.configure(text=("Inadimplência: " if inad else
                                          "Parcial: ")
                                    + " ".join(partes)[:160])
            messagebox.showinfo(nome_envio, "\n\n".join(partes)
                                + f"\n\nPDFs em:\n{res['pasta']}",
                                parent=janela)
            if res["eml"] or res.get("metodo") == "WEB":
                janela._abrir(res["pasta"])
        bv.em_segundo_plano(janela, trabalho, pronto)


class DialogoChampions(tk.Toplevel):
    """(28/10, Alexandre) BAP CHAMPIONS: os parametros do jogo cadastrados
    e alterados aqui (champions_config.json): pontos, aceleradores, trava,
    SLA, os Aux. Tecnicos (e o supervisor que cada um apoia), os jogos da
    semana e quem fica fora do jogo."""

    def __init__(self, janela):
        import bap_champions as bc                       # noqa: PLC0415
        super().__init__(janela)
        self.janela, self.bc = janela, bc
        self.cfg = bc.ler(AQUI)
        info = (janela.rel or {}).get("_champions") or {}
        self.vend = [(c, n) for c, n in info.get("vendedores") or []]
        self.sups = [(c, n) for c, n in info.get("supervisores") or []]
        self.semanas = list(info.get("semanas") or [])
        if self.semanas:            # e as 4 semanas seguintes (cadastrar
            ult = self.semanas[-1]  # antes de virar o mes)
            from datetime import timedelta               # noqa: PLC0415
            self.semanas += [ult + timedelta(days=7 * i) for i in range(1, 5)]
        self.title("Parâmetros das campanhas · BAP")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        self.geometry("980x640")
        bv.Cabecalho(self, "Campanhas BAP", "Parâmetros das campanhas",
                     "valem para todos os meses").pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        nb = ttk.Notebook(self, style="Abas.TNotebook")
        nb.pack(fill="both", expand=True, padx=16, pady=10)
        self._aba_pontos(nb)
        self._aba_aux(nb)
        self._aba_jogos(nb)
        self._aba_fora(nb)
        self._aba_relampago(nb)
        self._aba_equipe_mes(nb)
        botoes = tk.Frame(self, background=bv.FUNDO)
        botoes.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(botoes, text="Salvar", style="Verde.TButton",
                   command=self.salvar).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(
            side="right", padx=8)
        self.msg = tk.Label(botoes, text="", background=bv.FUNDO,
                            foreground=bv.SUAVE, font=bv.fonte(9))
        self.msg.pack(side="left")

    # ---------------------------------------------------------- utilidades
    def _rot(self, cod, lista):
        nome = dict(lista).get(cod)
        return f"{cod} - {nome}" if nome else (cod or "")

    @staticmethod
    def _cod(rotulo):
        return str(rotulo or "").split(" - ")[0].strip()

    def _quadro(self, nb, titulo):
        f = tk.Frame(nb, background=bv.FUNDO)
        nb.add(f, text=titulo)
        return f

    # --------------------------------------------------------------- pontos
    def _aba_pontos(self, nb):
        bc = self.bc
        f = self._quadro(nb, "Pontos e regras")
        c = self.cfg
        self.campos = []          # (rotulo, getter, setter)
        linhas = [
            ("FATURAMENTO (a cada R$ 1.000 vendidos)", None, None),
            ("Vendedor", ("pontos_por_mil", bc.VENDEDOR), "pts"),
            ("Supervisor (equipe)", ("pontos_por_mil", bc.SUPERVISOR), "pts"),
            ("Aux. Técnico (equipe apoiada)", ("pontos_por_mil", bc.AUX),
             "pts"),
            ("CONFRONTO DA SEMANA", None, None),
            ("Vitória (vendedor e supervisor)", ("bonus_confronto",), "pts"),
            ("ACELERADORES · VENDEDOR", None, None),
            ("Peça vendida (por unidade)",
             ("acel_vendedor", "sku_pecas"), "pts"),
            ("Cliente novo com pedido", ("acel_vendedor", "cliente_novo"),
             "pts"),
            ("ACELERADORES · SUPERVISOR", None, None),
            ("SKU novo vendido", ("acel_supervisor", "sku_novo"), "pts"),
            ("Cliente positivado", ("acel_supervisor", "positivado"), "pts"),
            ("ACELERADORES · AUX. TÉCNICO (mês fechado)", None, None),
            ("SLA de entrega", ("acel_aux", "sla_entrega"), "pts"),
            ("SLA de faturamento", ("acel_aux", "sla_faturamento"), "pts"),
            ("REGRAS", None, None),
            ("Trava: % do desafio comercial que libera os pontos", ("trava_pct",), "%"),
            ("SLA de entrega: % mínimo no prazo",
             ("sla_entrega_meta_pct",), "%"),
            ("SLA de faturamento: % mínimo no prazo",
             ("sla_faturamento_meta_pct",), "%"),
            ("SLA de faturamento: prazo (dias úteis)",
             ("sla_faturamento_dias",), "dias"),
            ("Categoria das peças (pontos por unidade)", ("categoria_pecas",), "texto")]
        grade = tk.Frame(f, background=bv.FUNDO)
        grade.pack(fill="both", expand=True, padx=12, pady=8)
        col = 0
        lin = 0
        for i, (rot, chave, un) in enumerate(linhas):
            if i == 12:                     # segunda coluna
                col, lin = 3, 0
            if chave is None:
                tk.Label(grade, text=rot, background=bv.FUNDO,
                         foreground=bv.VERDE_ESCURO, font=bv.fonte(9, "bold"),
                         anchor="w").grid(row=lin, column=col, columnspan=3,
                                          sticky="w", pady=(10, 2))
                lin += 1
                continue
            v = c
            for k in chave:
                v = v.get(k) if isinstance(v, dict) else None
            var = tk.StringVar(value="" if v is None else (
                str(v) if un == "texto" else
                (f"{float(v):g}" if isinstance(v, (int, float)) else str(v))))
            tk.Label(grade, text=rot, background=bv.FUNDO, foreground=bv.TEXTO,
                     font=bv.fonte(9), anchor="w").grid(
                row=lin, column=col, sticky="w", padx=(0, 8), pady=2)
            ttk.Entry(grade, textvariable=var,
                      width=14 if un == "texto" else 8).grid(
                row=lin, column=col + 1, sticky="w", pady=2)
            if un != "texto":
                tk.Label(grade, text=un, background=bv.FUNDO,
                         foreground=bv.SUAVE, font=bv.fonte(8)).grid(
                    row=lin, column=col + 2, sticky="w", padx=(4, 24))
            self.campos.append((rot, chave, un, var))
            lin += 1

    # ---------------------------------------------------------- aux tecnico
    def _aba_aux(self, nb):
        f = self._quadro(nb, "Aux. Técnico")
        tk.Label(f, text="Os assistentes do backoffice e o supervisor que "
                 "cada um apoia: os pontos saem do faturamento, da meta e "
                 "dos SLAs da equipe desse supervisor.", background=bv.FUNDO,
                 foreground=bv.SUAVE, font=bv.fonte(9), anchor="w",
                 wraplength=840, justify="left").pack(fill="x", padx=12,
                                                      pady=(10, 4))
        self.tv_aux = ttk.Treeview(f, columns=("nome", "sup"),
                                   show="headings", height=8)
        self.tv_aux.heading("nome", text="AUX. TÉCNICO")
        self.tv_aux.heading("sup", text="APOIA (SUPERVISOR)")
        self.tv_aux.column("nome", width=300)
        self.tv_aux.column("sup", width=420)
        self.tv_aux.pack(fill="x", padx=12)
        for a in self.cfg.get("aux") or []:
            self.tv_aux.insert("", "end", values=(
                a.get("nome", ""), self._rot(a.get("supervisor", ""),
                                             self.sups)))
        ed = tk.Frame(f, background=bv.FUNDO)
        ed.pack(fill="x", padx=12, pady=8)
        self.var_aux_nome = tk.StringVar()
        self.var_aux_sup = tk.StringVar()
        tk.Label(ed, text="Nome", background=bv.FUNDO).pack(side="left")
        ttk.Entry(ed, textvariable=self.var_aux_nome, width=28).pack(
            side="left", padx=(4, 12))
        tk.Label(ed, text="Apoia", background=bv.FUNDO).pack(side="left")
        ttk.Combobox(ed, textvariable=self.var_aux_sup, state="readonly",
                     width=40, values=["(nenhum)"] + [
                         f"{c} - {n}" for c, n in self.sups]).pack(
            side="left", padx=(4, 12))
        ttk.Button(ed, text="Adicionar / alterar",
                   command=self._aux_gravar).pack(side="left")
        ttk.Button(ed, text="Remover", command=lambda: [
            self.tv_aux.delete(i) for i in self.tv_aux.selection()]).pack(
            side="left", padx=6)

        def escolheu(_e=None):
            sel = self.tv_aux.selection()
            if sel:
                n, s = self.tv_aux.item(sel[0], "values")
                self.var_aux_nome.set(n)
                self.var_aux_sup.set(s or "(nenhum)")
        self.tv_aux.bind("<<TreeviewSelect>>", escolheu)

    def _aux_gravar(self):
        nome = self.var_aux_nome.get().strip()
        if not nome:
            return
        sup = self.var_aux_sup.get()
        sup = "" if sup in ("", "(nenhum)") else sup
        for i in self.tv_aux.get_children():
            if self.tv_aux.item(i, "values")[0].strip().upper() == \
                    nome.upper() or i in self.tv_aux.selection():
                self.tv_aux.item(i, values=(nome, sup))
                return
        self.tv_aux.insert("", "end", values=(nome, sup))

    # ------------------------------------------------------------- jogos
    def _aba_jogos(self, nb):
        bc = self.bc
        f = self._quadro(nb, "Confrontos da semana")
        tk.Label(f, text="Os jogos de cada semana (segunda a domingo). Vence "
                 f"quem fizer mais pontos na semana: +"
                 f"{float(self.cfg.get('bonus_confronto') or 0):g} pontos.",
                 background=bv.FUNDO, foreground=bv.SUAVE, font=bv.fonte(9),
                 anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        self.tv_j = ttk.Treeview(f, columns=("sem", "tipo", "a", "b"),
                                 show="headings", height=10)
        for k, t, w in (("sem", "SEMANA (SEGUNDA)", 130), ("tipo", "TIPO", 110),
                        ("a", "JOGADOR A", 290), ("b", "JOGADOR B", 290)):
            self.tv_j.heading(k, text=t)
            self.tv_j.column(k, width=w)
        self.tv_j.pack(fill="x", padx=12)
        todos = self.vend + self.sups
        for j in self.cfg.get("jogos") or []:
            try:
                from datetime import date                # noqa: PLC0415
                s = date.fromisoformat(str(j.get("semana"))[:10])
                st = f"{s:%d/%m/%Y}"
            except ValueError:
                st = str(j.get("semana"))
            self.tv_j.insert("", "end", values=(
                st, j.get("tipo", bc.VENDEDOR), self._rot(j.get("a"), todos),
                self._rot(j.get("b"), todos)))
        ed = tk.Frame(f, background=bv.FUNDO)
        ed.pack(fill="x", padx=12, pady=8)
        self.var_j_sem = tk.StringVar(value=f"{self.semanas[0]:%d/%m/%Y}"
                                      if self.semanas else "")
        self.var_j_tipo = tk.StringVar(value=bc.VENDEDOR)
        self.var_j_a, self.var_j_b = tk.StringVar(), tk.StringVar()
        ttk.Combobox(ed, textvariable=self.var_j_sem, width=11, values=[
            f"{s:%d/%m/%Y}" for s in self.semanas]).pack(side="left")
        cb_t = ttk.Combobox(ed, textvariable=self.var_j_tipo, width=11,
                            state="readonly",
                            values=[bc.VENDEDOR, bc.SUPERVISOR])
        cb_t.pack(side="left", padx=6)
        self.cb_a = ttk.Combobox(ed, textvariable=self.var_j_a, width=30,
                                 state="readonly")
        self.cb_a.pack(side="left")
        tk.Label(ed, text="x", background=bv.FUNDO).pack(side="left", padx=4)
        self.cb_b = ttk.Combobox(ed, textvariable=self.var_j_b, width=30,
                                 state="readonly")
        self.cb_b.pack(side="left")

        def opcoes(_e=None):
            lst = self.sups if self.var_j_tipo.get() == bc.SUPERVISOR \
                else self.vend
            vals = [f"{c} - {n}" for c, n in lst]
            self.cb_a.configure(values=vals)
            self.cb_b.configure(values=vals)
        cb_t.bind("<<ComboboxSelected>>", opcoes)
        opcoes()
        ed2 = tk.Frame(f, background=bv.FUNDO)
        ed2.pack(fill="x", padx=12)
        ttk.Button(ed2, text="Adicionar jogo",
                   command=self._jogo_add).pack(side="left")
        ttk.Button(ed2, text="Remover selecionado(s)", command=lambda: [
            self.tv_j.delete(i) for i in self.tv_j.selection()]).pack(
            side="left", padx=6)

    def _jogo_add(self):
        from datetime import datetime as _dt             # noqa: PLC0415
        try:
            s = _dt.strptime(self.var_j_sem.get().strip(), "%d/%m/%Y").date()
        except ValueError:
            self.msg.configure(text="Semana: use dd/mm/aaaa (a segunda-"
                                    "feira).", foreground=bv.VERMELHO)
            return
        if s.weekday() != 0:
            self.msg.configure(text=f"{s:%d/%m} não é segunda-feira.",
                               foreground=bv.VERMELHO)
            return
        a, b = self.var_j_a.get(), self.var_j_b.get()
        if not a or not b or a == b:
            self.msg.configure(text="Escolha dois jogadores diferentes.",
                               foreground=bv.VERMELHO)
            return
        self.tv_j.insert("", "end", values=(f"{s:%d/%m/%Y}",
                                            self.var_j_tipo.get(), a, b))
        self.msg.configure(text="Jogo adicionado (falta Salvar).",
                           foreground=bv.SUAVE)

    # ---------------------------------------------------------- fora
    # ------------------------------------------------- equipe do mes
    COLS_EQ = ("mes", "regiao", "supervisor", "cod", "vendedor", "meta")

    def _aba_equipe_mes(self, nb):
        """(28/10) Equipe e metas de um mes cadastradas a mao (ex.: julho):
        o mes que tem lista aqui usa ela no lugar do Planner/Gerador."""
        f = self._quadro(nb, "Equipe do mês")
        tk.Label(f, text="Para meses de antes do Planner (ou com outra "
                 "equipe): a lista do mês substitui a equipe e a meta do "
                 "Planner/Gerador de Meta. Meta do supervisor = soma da "
                 "equipe.", background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(9), anchor="w", wraplength=920,
                 justify="left").pack(fill="x", padx=12, pady=(10, 4))
        rot = {"mes": "MÊS", "regiao": "REGIÃO", "supervisor": "SUPERVISOR",
               "cod": "CÓD.", "vendedor": "VENDEDOR", "meta": "META (R$)"}
        larg = {"mes": 80, "regiao": 80, "supervisor": 230, "cod": 70,
                "vendedor": 280, "meta": 110}
        self.tv_eq = ttk.Treeview(f, columns=self.COLS_EQ, show="headings",
                                  height=9)
        for k in self.COLS_EQ:
            self.tv_eq.heading(k, text=rot[k])
            self.tv_eq.column(k, width=larg[k])
        self.tv_eq.pack(fill="x", padx=12)
        for comp, ls in sorted((self.cfg.get("equipes_mes") or {}).items()):
            for x in ls or []:
                self.tv_eq.insert("", "end", values=(
                    f"{comp[5:7]}/{comp[:4]}", x.get("regiao", ""),
                    x.get("supervisor", ""), x.get("cod", ""),
                    x.get("vendedor", ""),
                    f"{self.bc.moeda(x.get('meta'), 0.0):.2f}"))
        ed = tk.Frame(f, background=bv.FUNDO)
        ed.pack(fill="x", padx=12, pady=8)
        self.vars_eq = {k: tk.StringVar() for k in self.COLS_EQ}
        for i, (k, w) in enumerate((("mes", 9), ("regiao", 9),
                                    ("supervisor", 26), ("cod", 8),
                                    ("vendedor", 24), ("meta", 12))):
            tk.Label(ed, text=rot[k] + (" (mm/aaaa)" if k == "mes" else ""),
                     background=bv.FUNDO).grid(row=0, column=i, sticky="w",
                                               padx=(0, 6))
            ttk.Entry(ed, textvariable=self.vars_eq[k], width=w).grid(
                row=1, column=i, sticky="w", padx=(0, 6))
        bt = tk.Frame(f, background=bv.FUNDO)
        bt.pack(fill="x", padx=12)
        ttk.Button(bt, text="Adicionar / alterar",
                   command=self._eq_gravar).pack(side="left")
        ttk.Button(bt, text="Remover selecionado(s)", command=lambda: [
            self.tv_eq.delete(i) for i in self.tv_eq.selection()]).pack(
            side="left", padx=6)

        def escolheu(_e=None):
            sel = self.tv_eq.selection()
            if sel:
                for k, v in zip(self.COLS_EQ, self.tv_eq.item(sel[0],
                                                              "values")):
                    self.vars_eq[k].set(v)
        self.tv_eq.bind("<<TreeviewSelect>>", escolheu)

    def _eq_ler(self, vals):
        """(comp AAAA-MM, linha) de uma linha da tabela; erro = ValueError."""
        x = dict(zip(self.COLS_EQ, [str(v).strip() for v in vals]))
        try:
            m, a = x["mes"].replace("-", "/").split("/")
            comp = f"{int(a):04d}-{int(m):02d}"
        except ValueError:
            raise ValueError(f"Mês inválido \"{x['mes']}\" (use mm/aaaa)."
                             ) from None
        if not x["vendedor"]:
            raise ValueError("Vendedor sem nome.")
        meta = self.bc.moeda(x["meta"], None)
        if meta is None or meta < 0:
            raise ValueError(f"{x['vendedor']}: meta inválida "
                             f"\"{x['meta']}\".")
        cod = x["cod"].strip("#")
        return comp, {"regiao": x["regiao"], "supervisor": x["supervisor"],
                      "cod": cod.zfill(6) if cod.isdigit() else cod,
                      "vendedor": x["vendedor"].upper(), "meta": meta}

    def _eq_gravar(self):
        vals = tuple(self.vars_eq[k].get() for k in self.COLS_EQ)
        try:
            comp, x = self._eq_ler(vals)
        except ValueError as erro:
            self.msg.configure(text=str(erro), foreground=bv.VERMELHO)
            return
        nova = (f"{comp[5:7]}/{comp[:4]}", x["regiao"], x["supervisor"],
                x["cod"], x["vendedor"], f"{x['meta']:.2f}")
        # mesmo mes e mesmo vendedor (codigo ou nome; ou a linha escolhida
        # na tabela): altera; senao, linha nova
        sel = set(self.tv_eq.selection())
        for i in self.tv_eq.get_children():
            v = self.tv_eq.item(i, "values")
            if v[0] == nova[0] and (
                    i in sel or (x["cod"] and v[3] == x["cod"])
                    or str(v[4]).upper() == x["vendedor"]):
                self.tv_eq.item(i, values=nova)
                break
        else:
            self.tv_eq.insert("", "end", values=nova)
        self.msg.configure(text="Equipe do mês atualizada (falta Salvar).",
                           foreground=bv.SUAVE)

    # ------------------------------------------------ campanha relampago
    def _aba_relampago(self, nb):
        """(28/10) A Campanha relampago: nome, dias e os numeros."""
        bc = self.bc
        f = self._quadro(nb, "Campanha relâmpago")
        tk.Label(f, text="Nos dias da campanha: a cada R$ X em PEDIDOS do "
                 "dia o vendedor e o supervisor (pela equipe) ganham pontos; "
                 "se a BAP vender a meta do dia, ganham o bônus do desafio "
                 "(só quem vendeu no dia). Pontos troca pontos: ficam fora do "
                 "placar do BAP Champions.", background=bv.FUNDO,
                 foreground=bv.SUAVE, font=bv.fonte(9), anchor="w",
                 wraplength=920, justify="left").pack(fill="x", padx=12,
                                                      pady=(10, 4))
        cols = ("nome", "dias") + tuple(bc.CAMPOS_RELAMPAGO)
        self.tv_rel = ttk.Treeview(f, columns=cols, show="headings",
                                   height=5)
        larg = {"nome": 170, "dias": 200}
        for k in cols:
            self.tv_rel.heading(k, text={"nome": "CAMPANHA",
                                         "dias": "DIAS"}.get(
                k, k.upper().replace("_", " ")))
            self.tv_rel.column(k, width=larg.get(k, 90))
        self.tv_rel.pack(fill="x", padx=12)
        for c in self.cfg.get("relampago") or []:
            self.tv_rel.insert("", "end", values=self._rel_valores(c))
        ed = tk.Frame(f, background=bv.FUNDO)
        ed.pack(fill="x", padx=12, pady=8)
        self.vars_rel = {"nome": tk.StringVar(), "dias": tk.StringVar()}
        tk.Label(ed, text="Campanha", background=bv.FUNDO).grid(
            row=0, column=0, sticky="w")
        ttk.Entry(ed, textvariable=self.vars_rel["nome"], width=26).grid(
            row=0, column=1, sticky="w", padx=(4, 16))
        tk.Label(ed, text="Dias (dd/mm/aaaa, vírgula)",
                 background=bv.FUNDO).grid(row=1, column=0, sticky="w")
        ttk.Entry(ed, textvariable=self.vars_rel["dias"], width=60).grid(
            row=1, column=1, columnspan=3, sticky="w", padx=(4, 16), pady=2)
        for i, (k, rot) in enumerate(bc.CAMPOS_RELAMPAGO.items()):
            self.vars_rel[k] = tk.StringVar()
            tk.Label(ed, text=rot, background=bv.FUNDO).grid(
                row=2 + i // 2, column=(i % 2) * 2, sticky="w", pady=2)
            ttk.Entry(ed, textvariable=self.vars_rel[k], width=12).grid(
                row=2 + i // 2, column=(i % 2) * 2 + 1, sticky="w",
                padx=(4, 16))
        bt = tk.Frame(f, background=bv.FUNDO)
        bt.pack(fill="x", padx=12)
        ttk.Button(bt, text="Adicionar / alterar",
                   command=self._rel_gravar).pack(side="left")
        ttk.Button(bt, text="Remover selecionada", command=lambda: [
            self.tv_rel.delete(i) for i in self.tv_rel.selection()]).pack(
            side="left", padx=6)

        def escolheu(_e=None):
            sel = self.tv_rel.selection()
            if sel:
                vals = self.tv_rel.item(sel[0], "values")
                for k, v in zip(cols, vals):
                    self.vars_rel[k].set(v)
        self.tv_rel.bind("<<TreeviewSelect>>", escolheu)

    def _rel_valores(self, c):
        from datetime import date as _d                  # noqa: PLC0415
        dias = []
        for d in c.get("dias") or []:
            try:
                dias.append(f"{_d.fromisoformat(str(d)[:10]):%d/%m/%Y}")
            except ValueError:
                dias.append(str(d))
        return (c.get("nome", ""), ", ".join(dias)) + tuple(
            f"{self.bc.numero(c.get(k)):g}" for k in self.bc.CAMPOS_RELAMPAGO)

    def _rel_ler(self, vals):
        """A campanha (dict) dos valores da linha; erro = ValueError."""
        from datetime import datetime as _dt             # noqa: PLC0415
        bc = self.bc
        cols = ("nome", "dias") + tuple(bc.CAMPOS_RELAMPAGO)
        x = dict(zip(cols, vals))
        nome = str(x["nome"]).strip()
        if not nome:
            raise ValueError("Campanha relâmpago sem nome.")
        dias = []
        for t in str(x["dias"]).replace(";", ",").split(","):
            t = t.strip()
            if not t:
                continue
            try:
                dias.append(_dt.strptime(t, "%d/%m/%Y").date().isoformat())
            except ValueError:
                raise ValueError(f"{nome}: dia inválido \"{t}\" (use "
                                 f"dd/mm/aaaa).") from None
        c = {"nome": nome, "dias": dias}
        for k, rot in bc.CAMPOS_RELAMPAGO.items():
            v = bc.numero(x[k], None)
            if v is None or v < 0:
                raise ValueError(f"{nome} › {rot}: número inválido.")
            c[k] = v
        return c

    def _rel_gravar(self):
        cols = ("nome", "dias") + tuple(self.bc.CAMPOS_RELAMPAGO)
        vals = tuple(self.vars_rel[k].get().strip() for k in cols)
        try:
            c = self._rel_ler(vals)
        except ValueError as erro:
            self.msg.configure(text=str(erro), foreground=bv.VERMELHO)
            return
        vals = self._rel_valores(c)
        for i in self.tv_rel.get_children():
            if self.tv_rel.item(i, "values")[0].strip().upper() == \
                    c["nome"].upper() or i in self.tv_rel.selection():
                self.tv_rel.item(i, values=vals)
                break
        else:
            self.tv_rel.insert("", "end", values=vals)
        self.msg.configure(text="Campanha atualizada (falta Salvar).",
                           foreground=bv.SUAVE)

    def _aba_fora(self, nb):
        f = self._quadro(nb, "Fora do jogo")
        tk.Label(f, text="Marque quem NÃO joga (ex.: a conta de teste).",
                 background=bv.FUNDO, foreground=bv.SUAVE, font=bv.fonte(9),
                 anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        fora = {str(x) for x in self.cfg.get("fora_do_jogo") or []}
        self.vars_fora = {}
        caixa = tk.Frame(f, background=bv.FUNDO)
        caixa.pack(fill="both", padx=12)
        for i, (c, n) in enumerate(self.vend + self.sups):
            var = tk.BooleanVar(value=c in fora)
            self.vars_fora[c] = var
            ttk.Checkbutton(caixa, text=f"{c} - {n}", variable=var).grid(
                row=i % 12, column=i // 12, sticky="w", padx=(0, 30), pady=1)
        self._fora_outros = [x for x in fora if x not in self.vars_fora]

    # ------------------------------------------------------------ salvar
    def salvar(self):
        bc = self.bc
        cfg = dict(self.cfg)
        for rot, chave, un, var in self.campos:
            txt = var.get().strip()
            if un == "texto":
                val = txt
            else:
                val = bc.numero(txt, None)
                if val is None or val < 0:
                    self.msg.configure(text=f"{rot}: número inválido.",
                                       foreground=bv.VERMELHO)
                    return
                if un == "dias":
                    val = int(val)
            if len(chave) == 1:
                cfg[chave[0]] = val
            else:
                cfg[chave[0]] = {**cfg.get(chave[0], {}), chave[1]: val}
        cfg["aux"] = [{"nome": n, "supervisor": self._cod(s)}
                      for n, s in (self.tv_aux.item(i, "values")
                                   for i in self.tv_aux.get_children())]
        from datetime import datetime as _dt             # noqa: PLC0415
        jogos = []
        for i in self.tv_j.get_children():
            st, tipo, a, b = self.tv_j.item(i, "values")
            try:
                s = _dt.strptime(st, "%d/%m/%Y").date().isoformat()
            except ValueError:
                s = st
            jogos.append({"semana": s, "tipo": tipo, "a": self._cod(a),
                          "b": self._cod(b)})
        cfg["jogos"] = jogos
        try:
            eqs = {}
            for i in self.tv_eq.get_children():
                comp, x = self._eq_ler(self.tv_eq.item(i, "values"))
                eqs.setdefault(comp, []).append(x)
            cfg["equipes_mes"] = eqs
            cfg["relampago"] = [self._rel_ler(self.tv_rel.item(i, "values"))
                                for i in self.tv_rel.get_children()]
        except ValueError as erro:
            messagebox.showerror("Campanhas BAP", str(erro), parent=self)
            return
        cfg["fora_do_jogo"] = sorted(
            [c for c, v in self.vars_fora.items() if v.get()]
            + self._fora_outros)
        import os                                        # noqa: PLC0415
        try:
            bc.gravar(AQUI, cfg, por=os.environ.get("USERNAME") or "")
        except ValueError as erro:
            messagebox.showerror("BAP CHAMPIONS", str(erro), parent=self)
            return
        except OSError as erro:
            messagebox.showerror("BAP CHAMPIONS", f"Não gravou: {erro}",
                                 parent=self)
            return
        self.destroy()
        self.janela.carregar()


class DialogoParcial(tk.Toplevel):
    """(06/10) PARCIAL PEDIDOS / PARCIAL VISITAS E POSITIVACAO: escolhe o
    periodo (Acumulado, D-1 ou Hoje) e o formato (imagem para o WhatsApp -
    vai para a area de transferencia - ou PDF) e gera. Sai sempre da
    equipe inteira (os filtros da tela nao valem)."""

    TITULOS = {"pedidos": ("Farol de Pedidos", "Parcial Pedidos"),
               "visitas": ("Farol de Visita", "Parcial Visitas e Conversão"),
               "entregas": ("Farol de Entregas", "Parcial Entregas"),
               "bap": ("Analista Comercial", "Parcial BAP")}
    SUBTITULOS = {"entregas": "por cliente · entregas e pedidos pendentes",
                  "bap": "pedidos e visitas · por supervisor e destaques"}

    def __init__(self, janela, tipo):
        super().__init__(janela)
        self.janela, self.tipo = janela, tipo
        farol, titulo = self.TITULOS[tipo]
        self.title(f"{titulo} · BAP")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        self.resizable(False, False)
        ctx = rn.Contexto(AQUI)
        bv.Cabecalho(self, farol, titulo, self.SUBTITULOS.get(
            tipo, "tabela por supervisor e destaques do período")).pack(
                fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", padx=20, pady=14)
        self.var_q = tk.StringVar(value="hoje" if tipo == "entregas"
                                  else "acum")
        self.var_f = tk.StringVar(value="png")
        opcoes_q = []
        for q, rot in rn.QUANDO_PARCIAL:
            de, ate, _r = rn.periodo_parcial(ctx, q)
            sub = (f"{de:%d} a {ate:%d/%m}" if q == "acum" else
                   f"{rn.DIAS_CURTOS[de.weekday()]} {de:%d/%m}")
            opcoes_q.append((q, rot, sub))
        self._grupo(corpo, "PERÍODO", self.var_q, opcoes_q)
        self._grupo(corpo, "GERAR", self.var_f, [
            ("png", "Imagem para WhatsApp", "copiada: é só colar (Ctrl+V)"),
            ("pdf", "Arquivo PDF", "A4 em pé, abre ao gerar")])
        self.msg = tk.Label(corpo, text="", background=bv.FUNDO,
                            foreground=bv.SUAVE, font=bv.fonte(9),
                            anchor="w", justify="left")
        self.msg.pack(fill="x", pady=(10, 0))
        botoes = tk.Frame(self, background=bv.FUNDO)
        botoes.pack(fill="x", padx=20, pady=(4, 16))
        self.bt = ttk.Button(botoes, text="Gerar", style="Verde.TButton",
                             command=self.gerar)
        self.bt.pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(
            side="right", padx=8)
        self.bind("<Return>", lambda _e: self.gerar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _grupo(self, pai, rotulo, var, opcoes):
        """Os botoes de escolha (um so marcado), como no Claude Design."""
        tk.Label(pai, text=rotulo, background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(8, "bold"), anchor="w").pack(
                     fill="x", pady=(8, 4))
        linha = tk.Frame(pai, background=bv.FUNDO)
        linha.pack(fill="x")
        caixas = {}

        def pintar():
            for k, (cx, ls) in caixas.items():
                marc = var.get() == k
                cx.configure(background=bv.VERDE_CLARO if marc else
                             bv.CARTAO, highlightbackground=bv.VERDE if marc
                             else bv.CINZA_LINHA)
                for i, l_ in enumerate(ls):
                    l_.configure(background=bv.VERDE_CLARO if marc else
                                 bv.CARTAO, font=bv.fonte(
                                     10 if i == 0 else 8,
                                     "bold" if marc and i == 0 else
                                     "normal"))
        for k, rot, sub in opcoes:
            cx = tk.Frame(linha, background=bv.CARTAO, cursor="hand2",
                          highlightthickness=1,
                          highlightbackground=bv.CINZA_LINHA)
            cx.pack(side="left", fill="x", expand=True, padx=(0, 8))
            l1 = tk.Label(cx, text=rot, background=bv.CARTAO,
                          foreground=bv.TEXTO, font=bv.fonte(10))
            l1.pack(padx=16, pady=(8, 0))
            l2 = tk.Label(cx, text=sub, background=bv.CARTAO,
                          foreground=bv.SUAVE, font=bv.fonte(8))
            l2.pack(padx=16, pady=(0, 8))
            caixas[k] = (cx, (l1, l2))
            for w in (cx, l1, l2):
                w.bind("<Button-1>", lambda _e, k=k: (var.set(k), pintar()))
        pintar()

    def gerar(self):
        if str(self.bt.cget("state")) == "disabled":
            return
        self.bt.configure(state="disabled")
        self.msg.configure(text="Gerando…", foreground=bv.SUAVE)
        q, fmt, tipo = self.var_q.get(), self.var_f.get(), self.tipo

        def trabalho():
            import parcial_imagem as pi                 # noqa: PLC0415
            ctx = rn.Contexto(AQUI)
            p_ = {"pedidos": rn.parcial_pedidos, "visitas": rn.parcial_visitas,
                  "entregas": rn.parcial_entregas,
                  "bap": rn.parcial_bap}[tipo](ctx, q)
            if fmt == "pdf":
                return pi.gravar_pdf(p_, PASTA_EXPORT), False
            arq = pi.gravar_png(p_, PASTA_EXPORT)
            # (19/10) o detalhe dos visitados que nao coube na imagem: uma
            # imagem por vendedor numa pasta ao lado
            return arq, p_.get("_pasta_extras")

        def pronto(res):
            try:
                self.bt.configure(state="normal")
            except tk.TclError:
                return
            if isinstance(res, dict) and "_erro" in res:
                self.msg.configure(text=f"Não consegui gerar: {res['_erro']}",
                                   foreground=bv.VERMELHO)
                return
            arq, extras = res
            if fmt == "pdf":
                bv.abrir_arquivo(arq)
                self.msg.configure(text=f"PDF gerado: {arq.name}",
                                   foreground=bv.VERDE_ESCURO)
                return
            import parcial_imagem as pi                 # noqa: PLC0415
            copiou = False
            try:
                copiou = pi.copiar_imagem(arq)
            except Exception:                            # noqa: BLE001
                copiou = False
            if extras:
                try:
                    bv.abrir_arquivo(extras)
                except Exception:                        # noqa: BLE001
                    pass
            mais = (f"\nDetalhe dos visitados: uma imagem por vendedor na "
                    f"pasta {extras.name}" if extras else "")
            if copiou:
                self.msg.configure(
                    text=f"Imagem copiada: abra o WhatsApp e cole (Ctrl+V)."
                         f"\nArquivo: {arq.name}{mais}",
                    foreground=bv.VERDE_ESCURO)
            else:
                bv.abrir_arquivo(arq)
                self.msg.configure(text=f"Imagem gerada: {arq.name}{mais}",
                                   foreground=bv.VERDE_ESCURO)
        bv.em_segundo_plano(self, trabalho, pronto)


class DialogoRHExecutivo(tk.Toplevel):
    """(08/10) EXPORTAR PARA O RH (Farol Indicadores Executivos): escolhe o
    trimestre e o formato. 1a pagina: o resumo executivo; depois o
    analitico de cada indicador (PDF: uma pagina por indicador; Excel: uma
    aba por indicador)."""

    _grupo = DialogoParcial._grupo

    def __init__(self, janela):
        super().__init__(janela)
        self.janela = janela
        self.title("Exportar para o RH · BAP")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        self.resizable(False, False)
        bv.Cabecalho(self, "Indicadores Executivos", "Exportar para o RH",
                     "resumo executivo e analítico por indicador").pack(
                         fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", padx=20, pady=14)
        prm = next((p_ for p_ in (janela.rel or {}).get("parametros") or []
                    if p_["nome"] == "TRIMESTRE"), None) or (
                        (janela.rel or {}).get("exec_tri"))
        tris = [v for v, _r in prm["valores"]] if prm else [1, 2, 3, 4]
        atual = prm.get("valor") if prm else tris[-1]
        self.var_t = tk.StringVar(value=str(atual))
        self.var_f = tk.StringVar(value="pdf")
        self._grupo(corpo, "TRIMESTRE", self.var_t, [
            (str(n), f"{rn.TRIMESTRES[n - 1]} tri",
             " · ".join(rn.MESES[m][:3].upper()
                        for m in range(3 * n - 2, 3 * n + 1)))
            for n in tris])
        self._grupo(corpo, "FORMATO", self.var_f, [
            ("pdf", "PDF", "resumo na 1ª página, um indicador por página"),
            ("xlsx", "Excel", "resumo e uma aba por indicador")])
        self.msg = tk.Label(corpo, text="", background=bv.FUNDO,
                            foreground=bv.SUAVE, font=bv.fonte(9),
                            anchor="w", justify="left")
        self.msg.pack(fill="x", pady=(10, 0))
        botoes = tk.Frame(self, background=bv.FUNDO)
        botoes.pack(fill="x", padx=20, pady=(4, 16))
        self.bt = ttk.Button(botoes, text="Exportar", style="Verde.TButton",
                             command=self.gerar)
        self.bt.pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(
            side="right", padx=8)
        self.bind("<Return>", lambda _e: self.gerar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def gerar(self):
        if str(self.bt.cget("state")) == "disabled":
            return
        self.bt.configure(state="disabled")
        self.msg.configure(text="Gerando…", foreground=bv.SUAVE)
        n, fmt = int(self.var_t.get()), self.var_f.get()

        def trabalho():
            ctx = rn.Contexto(AQUI, params={"TRIMESTRE": n})
            rel = rn.exportar_rh_executivo(ctx)
            destino = PASTA_EXPORT / (
                f"INDICADORES_EXECUTIVOS_RH_{n}TRI{ctx.executivo['ano']}_"
                f"{datetime.now():%Y%m%d_%H%M}.{fmt}")
            if fmt == "pdf":
                return bv.exportar_pdf(rel, destino, max_linhas=100000)
            return bv.exportar_excel(rel, destino)

        def pronto(res):
            try:
                self.bt.configure(state="normal")
            except tk.TclError:
                return
            if isinstance(res, dict) and "_erro" in res:
                self.msg.configure(text=f"Não consegui gerar: {res['_erro']}",
                                   foreground=bv.VERMELHO)
                return
            bv.abrir_arquivo(res)
            self.msg.configure(text=f"Gerado: {Path(res).name}",
                               foreground=bv.VERDE_ESCURO)
        bv.em_segundo_plano(self, trabalho, pronto)


class EnvioRota(tk.Toplevel):
    """ENVIAR ROTA DA SEMANA POR E-MAIL: escolhe a semana, marca quem
    recebe (sem e-mail no Planner, nao da para marcar) e envia - do mesmo
    jeito da parcial (Outlook, e-mail padrao, Outlook na Web ou .eml)."""

    def __init__(self, janela):
        super().__init__(janela)
        import email_rota as er                         # noqa: PLC0415
        from datetime import date, timedelta            # noqa: PLC0415
        self.janela, self.er = janela, er
        self.title("Enviar Rota da semana por E-mail")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        bv.Cabecalho(self, "Farol Roteirização",
                     "Enviar Rota da semana por E-mail",
                     "segunda a sexta · um PDF por vendedor · Ver PDF ou "
                     "enviar").pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        topo = tk.Frame(self, background=bv.FUNDO)
        topo.pack(fill="x", padx=20, pady=(12, 0))
        tk.Label(topo, text="Semana", background=bv.FUNDO,
                 font=bv.fonte(9)).pack(side="left")
        seg = er.semana_de(date.today())
        self.semanas = {}
        for i, rot in ((-1, "Semana passada"), (0, "Semana atual"),
                       (1, "Próxima semana")):
            d = seg + timedelta(days=7 * i)
            self.semanas[f"{rot} · {er.rotulo_semana(d)}"] = d
        self.var_sem = tk.StringVar(value=list(self.semanas)[1])
        cb = ttk.Combobox(topo, textvariable=self.var_sem, width=40,
                          state="readonly", values=list(self.semanas))
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.carregar())
        self.corpo = tk.Frame(self, background=bv.FUNDO)
        self.corpo.pack(fill="both", expand=True, padx=20, pady=12)
        tk.Label(self, text="Vendedor recebe a rota dele; supervisor, um PDF "
                 "por vendedor da equipe; gerente, um PDF por vendedor do "
                 "time. Ninguém vai em cópia.", background=bv.FUNDO,
                 foreground=bv.SUAVE, font=bv.fonte(8), anchor="w"
                 ).pack(fill="x", padx=20)
        botoes = tk.Frame(self, background=bv.FUNDO)
        botoes.pack(fill="x", padx=20, pady=(8, 16))
        ttk.Button(botoes, text="Enviar agora", style="Verde.TButton",
                   command=lambda: self.ir(False)).pack(side="right")
        ttk.Button(botoes, text="Abrir no Outlook para revisar",
                   command=lambda: self.ir(True)).pack(side="right", padx=8)
        # (06/10) ver o PDF da rota aqui no Farol, sem mandar nada
        ttk.Button(botoes, text="Ver PDF", command=self.ver_pdf).pack(
            side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(
            side="left")
        self.marcas, self.rota = [], None
        self.carregar()
        self.grab_set()

    def segunda(self):
        return self.semanas[self.var_sem.get()]

    def carregar(self):
        for w in self.corpo.winfo_children():
            w.destroy()
        self.marcas, self.rota = [], None
        tk.Label(self.corpo, text="Montando a rota da semana…",
                 background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=0, column=0, sticky="w")
        seg, er = self.segunda(), self.er

        def trabalho():
            rota = er.rota_da_semana(AQUI, seg)
            return rota, er.destinatarios_rota(AQUI, seg, rota)

        def pronto(res):
            if not self.winfo_exists() or seg != self.segunda():
                return
            for w in self.corpo.winfo_children():
                w.destroy()
            if isinstance(res, dict) and "_erro" in res:
                tk.Label(self.corpo, text=str(res["_erro"]),
                         background=bv.FUNDO, foreground=bv.VERMELHO,
                         font=bv.fonte(9)).grid(row=0, column=0, sticky="w")
                return
            self.rota, pessoas = res
            if not pessoas:
                tk.Label(self.corpo, text="Ninguém tem rota nesta semana.",
                         background=bv.FUNDO, font=bv.fonte(9)).grid(
                             row=0, column=0, sticky="w")
            for n, p in enumerate(pessoas):
                # sem e-mail: nao vai no envio, mas da para marcar e VER o PDF
                var = tk.BooleanVar(value=bool(p["email"]))
                cb = ttk.Checkbutton(self.corpo, variable=var)
                cb.grid(row=n, column=0, sticky="w")
                info = (f"{p['visitas']} visita(s)" if p["cargo"] == "VENDEDOR"
                        else f"{len(p['vendedores'])} PDF(s) · "
                             f"{p['visitas']} visita(s)")
                for j, (txt, larg) in enumerate((
                        (p["cargo"].title(), 11),
                        (_nome_bonito(p["nome"]), 36),
                        (p["email"] or "sem e-mail no Planner", 38),
                        (info, 26)), start=1):
                    tk.Label(self.corpo, text=txt, width=larg, anchor="w",
                             background=bv.FUNDO, font=bv.fonte(9),
                             foreground=bv.SUAVE if j == 4 else
                             bv.TEXTO if p["email"] or j < 3
                             else bv.VERMELHO).grid(row=n, column=j,
                                                    sticky="w", pady=1)
                self.marcas.append((var, p))
            for a in self.rota.get("avisos") or []:
                tk.Label(self.corpo, text=a, background=bv.FUNDO,
                         foreground=bv.AMARELO, font=bv.fonte(8)).grid(
                             row=len(pessoas) + 1, column=0, columnspan=5,
                             sticky="w")
        bv.em_segundo_plano(self, trabalho, pronto)

    def ver_pdf(self):
        """O PDF da rota (o mesmo do e-mail) dos marcados, sem enviar: um
        PDF por vendedor; um so abre direto, varios abrem a pasta."""
        marcados = [p for var, p in self.marcas if var.get()]
        if not marcados or self.rota is None:
            messagebox.showinfo("Rota da semana", "Marque de quem é a rota.",
                                parent=self)
            return
        seg, rota, er, janela = self.segunda(), self.rota, self.er, self.janela
        cods = list(dict.fromkeys(v for p in marcados
                                  for v in p["vendedores"]))
        janela.rodape.configure(text="Montando o PDF da rota…")

        def trabalho():
            return er.gerar_pdfs(AQUI, cods, seg, rota)

        def pronto(res):
            if isinstance(res, dict) and "_erro" in res:
                messagebox.showerror("Rota da semana", str(res["_erro"]),
                                     parent=self if self.winfo_exists()
                                     else janela)
                return
            if not res:
                return
            janela.rodape.configure(text=f"Rota da semana: {len(res)} PDF(s) "
                                         f"em {res[0].parent}")
            janela._abrir(res[0] if len(res) == 1 else res[0].parent)
        bv.em_segundo_plano(self, trabalho, pronto)

    def ir(self, revisar):
        escolhidos = [p for var, p in self.marcas if var.get() and p["email"]]
        if not escolhidos or self.rota is None:
            messagebox.showinfo("Enviar Rota", "Marque quem recebe (quem "
                                "não tem e-mail no Planner não recebe).",
                                parent=self)
            return
        seg, rota, er = self.segunda(), self.rota, self.er
        if not revisar and not messagebox.askyesno(
                "Enviar Rota",
                f"Enviar a rota da semana {er.rotulo_semana(seg)} para "
                f"{len(escolhidos)} pessoa(s)?\n\n" + "\n".join(
                    f"{_nome_bonito(p['nome'])} <{p['email']}>"
                    for p in escolhidos[:20])
                + ("\n..." if len(escolhidos) > 20 else ""), parent=self):
            return
        janela = self.janela
        self.destroy()
        janela.rodape.configure(text="Montando a rota da semana…")

        def trabalho():
            import email_parcial as ep                  # noqa: PLC0415
            itens = er.preparar(AQUI, escolhidos, seg, rota)
            return ep.enviar(itens, revisar=revisar)

        def pronto(res):
            if isinstance(res, dict) and "_erro" in res:
                messagebox.showerror("Enviar Rota", str(res["_erro"]),
                                     parent=janela)
                return
            partes = list(res.get("avisos") or [])
            if res["enviados"]:
                partes.append(f"{len(res['enviados'])} e-mail(s) enviado(s) "
                              f"pelo Outlook.")
            if res["abertos"]:
                partes.append(
                    f"{len(res['abertos'])} e-mail(s) aberto(s) para conferir"
                    f" e clicar em Enviar"
                    + (" (no Outlook na Web, sem anexo: os PDFs estão na "
                       "pasta abaixo)." if res.get("metodo") == "WEB"
                       else ", já com os PDFs."))
            if res["eml"]:
                partes.append(f"{len(res['eml'])} e-mail(s) prontos na pasta "
                              f"(.eml: dois cliques abre o e-mail com os PDFs;"
                              f" é só Enviar).")
            if res["erros"]:
                partes.append("Problemas:\n" + "\n".join(res["erros"][:8]))
            janela.rodape.configure(text="Rota da semana: "
                                    + " ".join(partes)[:160])
            messagebox.showinfo("Enviar Rota", "\n\n".join(partes)
                                + f"\n\nPDFs em:\n{res['pasta']}",
                                parent=janela)
            if res["eml"] or res.get("metodo") == "WEB":
                janela._abrir(res["pasta"])
        bv.em_segundo_plano(janela, trabalho, pronto)


class Edicao(tk.Toplevel):
    """A janelinha de edicao de uma linha: uma lista por campo."""

    def __init__(self, janela, vista, linha, chave, ed):
        super().__init__(janela)
        self.vista, self.linha, self.chave, self.ed = vista, linha, chave, ed
        self.title("Novo" if str(chave).startswith("NOVO") else "Editar")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        self.resizable(False, False)
        cols = vista.t["colunas"]
        resumo = " · ".join(bv.formatar(linha[i], cols[i].get("tipo", "texto"))
                            for i in range(min(len(cols), 8))
                            if linha[i] not in (None, ""))
        resumo = resumo if len(resumo) <= 90 else resumo[:89] + "…"
        bv.Cabecalho(self, "Editar", vista.t["titulo"]).pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        tk.Label(self, text=resumo, background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(9), anchor="w").pack(fill="x", padx=20,
                                                    pady=(12, 0))
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", padx=20, pady=14)
        self.vars = {}
        novo_ = str(chave).startswith("NOVO")
        self.livres = {c["campo"] for c in ed["campos"] if c.get("livre")}
        self.caixa = {c["campo"] for c in ed["campos"] if c.get("mantem_caixa")}
        campos_ = [c for c in ed["campos"]
                   if not c.get("so_se") or c["so_se"](linha)]
        for n, c in enumerate(campos_):
            idx = c.get("col")
            atual = linha[idx] if idx is not None and idx < len(linha) else ""
            atual = (bv.formatar(atual, "num2") if c.get("numero")
                     else bv.formatar(atual, "data" if c.get("data")
                                      else "texto"))
            opcoes = list(c["opcoes_de"](linha) if c.get("opcoes_de")
                          else c["opcoes"])
            if atual and atual not in opcoes:
                opcoes = [atual] + opcoes
            tk.Label(corpo, text=bv._rotulo(c["rotulo"]), background=bv.FUNDO,
                     foreground=bv.SUAVE, font=bv.fonte(9),
                     anchor="w").grid(row=n, column=0, sticky="w", pady=4,
                                      padx=(0, 12))
            if novo_ and not atual and c["campo"] in (ed.get("padroes_novo")
                                                     or {}):
                atual = ed["padroes_novo"][c["campo"]]
            if c.get("livre"):          # texto escrito (a lista so sugere)
                var = tk.StringVar(value=atual)
                cb = ttk.Combobox(corpo, textvariable=var, width=52,
                                  values=opcoes[:300])
                cb.grid(row=n, column=1, sticky="w", pady=4)
                if len(opcoes) > 12:     # filtra a lista pelo que se digita
                    cb.bind("<KeyRelease>", lambda e, cb=cb, ops=opcoes:
                            cb.configure(values=[
                                o for o in ops
                                if cb.get().strip().upper() in o.upper()][:300]))
            else:
                var = tk.StringVar(value=atual or VAZIO)
                ttk.Combobox(corpo, textvariable=var, state="readonly",
                             width=40, values=[VAZIO] + opcoes).grid(
                                 row=n, column=1, sticky="w", pady=4)
            self.vars[c["campo"]] = var
        botoes = tk.Frame(self, background=bv.FUNDO)
        botoes.pack(fill="x", padx=20, pady=(0, 16))
        ttk.Button(botoes, text="Aplicar", style="Verde.TButton",
                   command=self.ok).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(
            side="right", padx=8)
        if getattr(vista, "tem_detalhe", False) and not novo_:
            ttk.Button(botoes, text="Ver pedido",
                       command=lambda: vista.ver_pedido(linha)).pack(
                           side="left")
        self.grab_set()

    def ok(self):
        # (16/10) campo de valor (VLR FRETE REAL): confere antes de fechar
        for c in self.ed["campos"]:
            if c.get("numero") and c["campo"] in self.vars:
                import pos_venda                        # noqa: PLC0415
                txt = self.vars[c["campo"]].get().strip()
                try:
                    n = pos_venda.valor_digitado(txt)
                    if n is not None and n < 0:
                        raise ValueError(txt)
                except ValueError:
                    messagebox.showerror(
                        "Editar", f"{bv._rotulo(c['rotulo'])}: \"{txt}\" "
                        "não é um valor. Escreva só o número (ex.: 278,40) "
                        "ou deixe vazio.", parent=self)
                    return
        valores = {k: ("" if v.get() == VAZIO else
                       (v.get().strip() if k in self.caixa
                        else v.get().strip().upper())
                       if k in self.livres else v.get())
                   for k, v in self.vars.items()}
        self.vista.aplicar_edicao(self.linha, self.chave, valores)
        self.destroy()


class DialogoGarantia(tk.Toplevel):
    """(14/10) A GARANTIA aberta no Farol de Garantias: em cima o cliente
    (endereco, bairro, cidade, vendedor, supervisor), embaixo o que a
    assistente edita. Salvar grava no diario (garantias.py) e recarrega o
    farol. ticket None = garantia nova."""

    CAMPOS = (("ticket", "Ticket", "entry"),      # (06/11) editavel
              ("dt_solicitacao", "Dt. solicitação", "data"),
              ("status", "Status", "status"),
              ("resultado", "Resultado análise", "resultado"),
              ("cod_produto", "Cód. produto", "produto"),
              ("descricao", "Descrição produto", "entry"),
              ("qtd", "Quantidade", "entry"),
              ("contato_nome", "Contato · nome", "entry"),
              ("contato_fone", "Contato · telefone", "entry"),
              ("dt_retorno", "Dt. último retorno", "data"),
              # (06/11) o prazo: em branco = solicitação + 15 dias úteis
              ("dt_prazo", "Dt. fechamento (prazo)", "data"))
    TEXTOS = (("reclamacao", "Reclamação do cliente"),
              ("pendencias", "Pendências (o que falta)"),
              ("retorno_cliente", "Retorno do cliente"),
              ("observacao", "Observação"))

    def __init__(self, janela, g, ticket):
        import garantias as gm                           # noqa: PLC0415
        super().__init__(janela)
        self.janela, self.g = janela, g
        self.novo = not ticket
        self.ticket = ticket or gm.novo_ticket(AQUI)
        d = g["dados"](self.ticket)
        self.title(f"Garantia {self.ticket}")
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        larg = min(1180, self.winfo_screenwidth() - 60)
        alt = min(880, self.winfo_screenheight() - 80)
        self.geometry(f"{larg}x{alt}+40+10")
        st = d["situacao"]
        # (06/11) a DT. FECHAMENTO (o prazo) no lugar da prevista
        sub = (" · ".join(x for x in (
            f"solicitada {st['inicio']:%d/%m/%Y}" if st["inicio"] else "",
            f"fechamento até {st['prevista']:%d/%m/%Y}" if st["prevista"]
            else "",
            f"SLA {st['sla']} dias" if st["sla"] is not None else "",
            "ATRASADA" if st["atrasada"] else (
                ("FECHADA no prazo" if st.get("no_prazo")
                 else "FECHADA com atraso") if st.get("fechada") else ""))
            if x) if not self.novo else "nova garantia")
        cab = bv.Cabecalho(self, "Garantia", f"Ticket {self.ticket}", sub)
        self.cab = cab
        cab.pack(fill="x")
        cab.botao("Salvar", self.salvar)
        cab.botao("Fechar", self.destroy)
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=16, pady=(8, 10))
        # ---- o CADASTRO do cliente (14/10, Alexandre: editavel, para a
        # garantia ficar completa). Vem da base; o que mudar aqui fica SO na
        # garantia (a base de clientes vem do Protheus e nao muda)
        info = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                        highlightbackground=bv.CINZA_LINHA)
        info.pack(fill="x", pady=(0, 10))
        self.base = dict(d.get("base") or {})
        self.base["_cod"] = (d["g"].get("cod_cliente") or "").strip()
        self.lbl_cli = tk.Label(info, text=self._titulo_cliente(),
                                background=bv.CARTAO, foreground=bv.TEXTO,
                                font=bv.fonte(9, "bold"), anchor="w")
        self.lbl_cli.grid(row=0, column=0, columnspan=4, sticky="w",
                          padx=12, pady=(8, 2))
        self.vars_cli = {}
        self.vars = {}
        opcoes = g.get("opcoes") or {}
        # (14/10) o COD. CLIENTE e o nome ficam AQUI, no cadastro: digitou o
        # codigo, o resto vem da base
        cli_ = dict(g.get("campos_cliente") or ())
        ordem = [("cod_cliente", "Cód. cliente"), ("cliente", "Cliente"),
                 ("cli_fantasia", cli_.get("cli_fantasia", "Fantasia")),
                 ("cli_telefone", cli_.get("cli_telefone", "Telefone")),
                 ("cli_endereco", cli_.get("cli_endereco", "Endereço")),
                 ("cli_bairro", cli_.get("cli_bairro", "Bairro")),
                 ("cli_cidade", cli_.get("cli_cidade", "Cidade")),
                 ("cli_uf", cli_.get("cli_uf", "UF")),
                 ("cli_vendedor", cli_.get("cli_vendedor", "Vendedor")),
                 ("cli_supervisor", cli_.get("cli_supervisor", "Supervisor"))]
        ordem += [(k, r_) for k, r_ in cli_.items()
                  if k not in dict(ordem)]
        for n, (campo, rot) in enumerate(ordem):
            lin, colu = divmod(n, 4)
            tk.Label(info, text=rot, background=bv.CARTAO,
                     foreground=bv.SUAVE, font=bv.fonte(8), anchor="w").grid(
                row=lin * 2 + 1, column=colu, sticky="w", padx=12)
            if campo in ("cod_cliente", "cliente"):
                v = tk.StringVar(value=(d["g"].get(campo) or "").strip())
                self.vars[campo] = v
                w = ttk.Entry(info, textvariable=v)
                w.grid(row=lin * 2 + 2, column=colu, sticky="ew", padx=12,
                       pady=(0, 8))
                if campo == "cod_cliente":
                    w.bind("<FocusOut>", lambda e: self._trocou_cliente())
                    w.bind("<Return>", lambda e: self._trocou_cliente())
                continue
            v = tk.StringVar(value=(d["g"].get(campo) or "").strip()
                             or self.base.get(campo, ""))
            self.vars_cli[campo] = v
            if opcoes.get(campo):
                w = ttk.Combobox(info, textvariable=v,
                                 values=opcoes[campo])
            else:
                w = ttk.Entry(info, textvariable=v)
            w.grid(row=lin * 2 + 2, column=colu, sticky="ew", padx=12,
                   pady=(0, 8))
        for j in range(4):
            info.columnconfigure(j, weight=1, uniform="c")
        # ---- os campos
        grade = tk.Frame(corpo, background=bv.FUNDO)
        grade.pack(fill="x")
        gd = d["g"]
        for n, (campo, rot, tipo) in enumerate(self.CAMPOS):
            lin, colu = divmod(n, 4)
            tk.Label(grade, text=rot, background=bv.FUNDO,
                     foreground=bv.SUAVE, font=bv.fonte(8), anchor="w").grid(
                row=lin * 2, column=colu, sticky="w", padx=(0, 14))
            padrao = {"status": "ABERTO", "resultado": "PENDENTE",
                      "ticket": self.ticket}.get(campo, "")
            if self.novo and campo == "dt_solicitacao":
                from datetime import date as _hoje       # noqa: PLC0415
                padrao = f"{_hoje.today():%d/%m/%Y}"
            if campo == "dt_prazo":     # (06/11) mostra o prazo padrao
                padrao = self._prazo_padrao(gd.get("dt_solicitacao")
                                            or (self.vars.get(
                                                "dt_solicitacao")
                                                and self.vars[
                                                    "dt_solicitacao"].get()))
            v = tk.StringVar(value=gd.get(campo) or padrao)
            self.vars[campo] = v
            if tipo in ("status", "resultado"):
                w = ttk.Combobox(grade, textvariable=v, state="readonly",
                                 values=list(g["status"] if tipo == "status"
                                             else g["resultados"]))
            else:
                w = ttk.Entry(grade, textvariable=v)
            w.grid(row=lin * 2 + 1, column=colu, sticky="ew",
                   padx=(0, 14), pady=(0, 8))
            if tipo == "produto":
                w.bind("<FocusOut>", lambda e: self._descricao())
                w.bind("<Return>", lambda e: self._descricao())
        for j in range(4):
            grade.columnconfigure(j, weight=1, uniform="g")
        textos = tk.Frame(corpo, background=bv.FUNDO)
        textos.pack(fill="both", expand=True)
        self.textos = {}
        for n, (campo, rot) in enumerate(self.TEXTOS):
            lin, colu = divmod(n, 2)
            fr = tk.Frame(textos, background=bv.FUNDO)
            fr.grid(row=lin, column=colu, sticky="nsew", padx=(0, 14),
                    pady=(0, 8))
            tk.Label(fr, text=rot, background=bv.FUNDO, foreground=bv.SUAVE,
                     font=bv.fonte(8), anchor="w").pack(anchor="w")
            tx = tk.Text(fr, height=5, wrap="word", font=bv.fonte(9),
                         relief="solid", borderwidth=1)
            tx.insert("1.0", gd.get(campo) or "")
            tx.pack(fill="both", expand=True)
            self.textos[campo] = tx
        for j in range(2):
            textos.columnconfigure(j, weight=1, uniform="t")
            textos.rowconfigure(j, weight=1)
        self.lbl = tk.Label(corpo, text=(
            f"Última alteração: {gd.get('_alterada')}"
            + (f" ({gd.get('_por')})" if gd.get("_por") else "")
            if gd.get("_alterada") else ""),
                            background=bv.FUNDO, foreground=bv.SUAVE,
                            font=bv.fonte(8))
        self.lbl.pack(anchor="w")
        self.bind("<Escape>", lambda e: self.destroy())

    def _titulo_cliente(self):
        cod = (self.vars["cod_cliente"].get().strip()
               if "cod_cliente" in (getattr(self, "vars", None) or {})
               else (self.base.get("_cod") or ""))
        nome = self.base.get("_nome") or ""
        if cod and nome:
            return f"Cadastro do cliente · {cod} - {nome}"
        if cod:
            return f"Cadastro do cliente · {cod} (fora da base)"
        return "Cadastro do cliente · sem código: preencha à mão"

    def _trocou_cliente(self):
        """Cod. cliente novo: o cadastro vem da base nos campos que ainda
        estavam como a base antiga (ou vazios); o que a assistente ja
        corrigiu fica."""
        cod = self.vars["cod_cliente"].get().strip()
        if cod == self.base.get("_cod", None):
            return
        novo = dict(self.g["cliente_base"](cod) or {})
        novo["_cod"] = cod
        for k, v in self.vars_cli.items():
            atual = v.get().strip()
            if not atual or atual == (self.base.get(k) or "").strip():
                v.set(novo.get(k, ""))
        if novo.get("_nome") and not self.vars["cliente"].get().strip():
            self.vars["cliente"].set(novo["_nome"])
        self.base = novo
        self.lbl_cli.configure(text=self._titulo_cliente())

    def _descricao(self):
        cod = self.vars["cod_produto"].get().strip()
        if cod and not self.vars["descricao"].get().strip():
            self.vars["descricao"].set(self.g["produto"](cod) or "")

    @staticmethod
    def _prazo_padrao(dt_sol) -> str:
        """(06/11) a DT. FECHAMENTO padrao: solicitacao + 15 dias uteis."""
        import garantias as gm                           # noqa: PLC0415
        try:
            fer = rn.bd.feriados(AQUI)
        except Exception:                               # noqa: BLE001
            fer = set()
        d = gm.prazo_padrao(gm.data(dt_sol), fer)
        return f"{d:%d/%m/%Y}" if d else ""

    def salvar(self):
        import garantias as gm                           # noqa: PLC0415
        self._descricao()
        campos = {k: v.get().strip() for k, v in self.vars.items()}
        # (06/11, Alexandre: "Acrescente para poder editar o ticket") o
        # numero novo: na garantia nova so troca o numero; na que ja existe
        # grava a troca no diario (a historia continua no numero novo)
        novo_t = campos.pop("ticket", self.ticket) or ""
        trocou = False
        if novo_t != self.ticket:
            erro_t = gm.renomear(AQUI, None if self.novo else self.ticket,
                                 novo_t)
            if erro_t:
                messagebox.showerror("Garantia", f"Ticket: {erro_t}.",
                                     parent=self)
                return
            trocou = not self.novo
            self.ticket = novo_t
            self.title(f"Garantia {novo_t}")
            try:
                self.cab.lbl_titulo.configure(text=f"Ticket {novo_t}")
            except (AttributeError, tk.TclError):
                pass
        # (06/11) a DT. FECHAMENTO igual a padrao fica em branco: assim ela
        # acompanha a solicitacao se a data da solicitacao mudar
        if campos.get("dt_prazo") and not gm.data(campos["dt_prazo"]):
            messagebox.showerror("Garantia", "Dt. fechamento: use "
                                 "dd/mm/aaaa.", parent=self)
            return
        if campos.get("dt_prazo") == self._prazo_padrao(
                campos.get("dt_solicitacao")):
            campos["dt_prazo"] = ""
        campos.update({k: tx.get("1.0", "end").strip()
                       for k, tx in self.textos.items()})
        # o cadastro: grava so o que difere da base (ou o que ja era da
        # garantia) - assim a base, quando melhorar, continua valendo
        self._trocou_cliente()
        for k, v in self.vars_cli.items():
            val = v.get().strip()
            if val != (self.base.get(k) or "").strip() or (
                    self.g["dados"](self.ticket)["g"].get(k) or "").strip():
                campos[k] = val
        if campos.get("dt_solicitacao") and not gm.data(
                campos["dt_solicitacao"]):
            messagebox.showerror("Garantia", "Dt. solicitação: use "
                                 "dd/mm/aaaa.", parent=self)
            return
        if self.novo:
            campos["origem"] = "FAROL DE GARANTIAS"
        try:
            n = gm.gravar(AQUI, self.ticket, campos)
        except OSError as erro:
            messagebox.showerror("Garantia", str(erro), parent=self)
            return
        n += 1 if trocou else 0
        self.novo = False
        self.lbl.configure(text=f"Salvo · {n} campo(s) alterado(s)",
                           foreground=bv.VERDE_ESCURO)
        try:
            self.janela.carregar()
        except Exception:                                # noqa: BLE001
            pass


# (14/10) onde a autorizacao de venda se GRAVA (governanca): so o Farol de
# Pedidos. Nos outros, a janela do pedido mostra so a leitura.
AUTORIZA_EM = ("pv_pedidos",)


class DetalhePedido(tk.Toplevel):
    """O pedido aberto: cabecalho, numeros e os itens.
    (09/10) ENXUTO: os campos em 5 colunas com letra menor, os numeros numa
    faixa so (sem cartoes grandes) e a tabela dos itens compacta, ocupando
    o resto da janela - todas as colunas dos itens cabem na tela."""

    def __init__(self, janela, d, editar_aut=False, nav=None, geometria=None):
        super().__init__(janela)
        self.d = d
        self.janela_farol = janela
        self.editar_aut = editar_aut
        self.nav = nav
        self.title(d["titulo"])
        self.configure(background=bv.FUNDO)
        self.transient(janela.winfo_toplevel())
        larg = min(1400, self.winfo_screenwidth() - 60)
        alt = min(780, self.winfo_screenheight() - 90)
        self.geometry(geometria or f"{larg}x{alt}+30+20")
        sub = d.get("subtitulo", "")
        if nav:
            sub = (f"{sub}   ·   {nav['i'] + 1} de {len(nav['linhas'])}"
                   if sub else f"{nav['i'] + 1} de {len(nav['linhas'])}")
        cab = bv.Cabecalho(self, "Pedido", d["titulo"], sub)
        cab.pack(fill="x")
        if nav:
            # (22/10, Alexandre) anterior / proximo da lista da tela
            b_ant = cab.botao("◀  Anterior", lambda: self.ir(-1))
            b_prox = cab.botao("Próximo  ▶", lambda: self.ir(1))
            for b_, pode in ((b_ant, nav["i"] > 0),
                             (b_prox, nav["i"] < len(nav["linhas"]) - 1)):
                if not pode and b_ is not None:
                    try:
                        b_.state(["disabled"])
                    except (AttributeError, tk.TclError):
                        pass
            self.bind("<Prior>", lambda e: self.ir(-1))
            self.bind("<Next>", lambda e: self.ir(1))
            self.bind("<Left>", lambda e: self._seta(e, -1))
            self.bind("<Right>", lambda e: self._seta(e, 1))
        cab.botao("Excel", self.excel)
        cab.botao("Fechar", self.destroy)
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=16, pady=(8, 10))
        info = tk.Frame(corpo, background=bv.FUNDO)
        info.pack(fill="x")
        n_col = 5
        for n, (rot, val) in enumerate(d["campos"]):
            lin, colu = divmod(n, n_col)
            tk.Label(info, text=rot, background=bv.FUNDO, foreground=bv.SUAVE,
                     font=bv.fonte(8), anchor="w").grid(
                row=lin * 2, column=colu, sticky="w", padx=(0, 16))
            tk.Label(info, text=val or "—", background=bv.FUNDO,
                     foreground=bv.TEXTO, font=bv.fonte(9, "bold"),
                     anchor="w", wraplength=max(200, larg // n_col - 30),
                     justify="left").grid(row=lin * 2 + 1, column=colu,
                                          sticky="w", padx=(0, 16),
                                          pady=(0, 5))
        for j in range(n_col):
            info.columnconfigure(j, weight=1, uniform="i")
        # os numeros numa faixa: rotulo pequeno, valor e o detalhe ao lado
        faixa = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                         highlightbackground=bv.CINZA_LINHA)
        faixa.pack(fill="x", pady=(4, 8))
        cores = {"alerta": bv.VERMELHO, "atencao": bv.AMARELO,
                 "ok": bv.VERDE_ESCURO}
        for i, k in enumerate(d["kpis"]):
            cx = tk.Frame(faixa, background=bv.CARTAO)
            cx.grid(row=0, column=i * 2, sticky="nsew", padx=12, pady=6)
            faixa.columnconfigure(i * 2, weight=1, uniform="k")
            tk.Label(cx, text=k["rotulo"], background=bv.CARTAO,
                     foreground=bv.SUAVE, font=bv.fonte(8),
                     anchor="w").pack(anchor="w")
            lin_v = tk.Frame(cx, background=bv.CARTAO)
            lin_v.pack(anchor="w")
            tk.Label(lin_v, text=k["valor"], background=bv.CARTAO,
                     foreground=cores.get(k.get("cor"), bv.TEXTO),
                     font=bv.fonte(13, "bold")).pack(side="left")
            if k.get("detalhe"):
                tk.Label(lin_v, text=k["detalhe"], background=bv.CARTAO,
                         foreground=bv.SUAVE, font=bv.fonte(8)).pack(
                             side="left", padx=(6, 0), pady=(4, 0))
            if i < len(d["kpis"]) - 1:
                tk.Frame(faixa, background=bv.CINZA_LINHA, width=1).grid(
                    row=0, column=i * 2 + 1, sticky="ns", pady=8)
        if d.get("autorizacao"):        # (13/10) a autorizacao de venda
            if self.editar_aut:
                self._autorizacao(corpo, d["autorizacao"])
            else:
                self._autorizacao_leitura(corpo, d["autorizacao"])
        tab = bv.Tabela(corpo, d["colunas"], altura=16, compacta=True,
                        zebra=True)
        tab.pack(fill="both", expand=True)
        tab.mostrar(d["linhas"], d["tons"], d["total"])
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_set()

    def _seta(self, e, passo):
        """As setas do teclado so andam fora dos campos de texto."""
        if isinstance(e.widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return
        self.ir(passo)

    def ir(self, passo):
        """(22/10, Alexandre) abre o pedido anterior/proximo da lista que
        estava na tela, no mesmo lugar e tamanho da janela."""
        nav = self.nav
        if not nav:
            return
        j = nav["i"] + passo
        if j < 0 or j >= len(nav["linhas"]):
            return
        fn, t = nav["fn"], nav["t"]
        rel = getattr(self.janela_farol, "rel", None)
        if isinstance(rel, dict) and callable(rel.get("detalhe_pedido")):
            # o farol foi atualizado (salvou a autorizacao): os dados novos
            t2 = next((x for x in rel.get("tabelas", [])
                       if x.get("titulo") == nav["titulo"]), None)
            if t2 is not None:
                fn, t = rel["detalhe_pedido"], t2
        try:
            d = fn(t, nav["linhas"][j])
        except Exception as erro:                       # noqa: BLE001
            messagebox.showerror("Ver pedido", str(erro), parent=self)
            return
        if not d:
            messagebox.showinfo("Ver pedido",
                                "Pedido não encontrado na TABELA_BAP.",
                                parent=self)
            return
        geo = self.geometry()
        janela = self.janela_farol
        editar = self.editar_aut
        self.destroy()
        DetalhePedido(janela, d, editar_aut=editar,
                      nav=dict(nav, i=j, fn=fn, t=t), geometria=geo)

    def _autorizacao(self, pai, a):
        """O CODIGO DE AUTORIZACAO e QUEM AUTORIZOU (Alexandre ou Price),
        escritos aqui no pedido. Acima de 15% sem autorizacao: vermelho."""
        cor = bv.VERMELHO if a.get("grave") else (
            bv.AMARELO if a.get("precisa") and not a.get("por")
            else bv.VERDE_ESCURO)
        fundo = bv.FUNDOS["grave"] if a.get("grave") else bv.CARTAO
        caixa = tk.Frame(pai, background=fundo, highlightthickness=1,
                         highlightbackground=bv.CINZA_LINHA)
        caixa.pack(fill="x", pady=(0, 8))
        tk.Label(caixa, text="Autorização de venda", background=fundo,
                 foreground=bv.TEXTO, font=bv.fonte(9, "bold")).pack(
                     side="left", padx=(12, 14), pady=8)
        tk.Label(caixa, text="Código", background=fundo, foreground=bv.SUAVE,
                 font=bv.fonte(8)).pack(side="left")
        self.v_cod = tk.StringVar(value=a.get("codigo") or "")
        ttk.Entry(caixa, textvariable=self.v_cod, width=26).pack(
            side="left", padx=(6, 14))
        tk.Label(caixa, text="Autorizado por", background=fundo,
                 foreground=bv.SUAVE, font=bv.fonte(8)).pack(side="left")
        self.v_por = tk.StringVar(value=a.get("por") or VAZIO)
        ttk.Combobox(caixa, textvariable=self.v_por, state="readonly",
                     width=14, values=[VAZIO] + list(rn.QUEM_AUTORIZA)).pack(
                         side="left", padx=(6, 14))
        ttk.Button(caixa, text="Salvar autorização", style="Verde.TButton",
                   command=lambda: self._salvar_aut(a)).pack(side="left")
        self.lbl_aut = tk.Label(caixa, text=a.get("aviso", ""),
                                background=fundo, foreground=cor,
                                font=bv.fonte(8, "bold"))
        self.lbl_aut.pack(side="left", padx=14)
        self.caixa_aut = caixa

    def _autorizacao_leitura(self, pai, a):
        """(14/10) So leitura: o codigo e quem autorizou, sem campo nem
        botao (a autorizacao e gravada so no Farol de Pedidos)."""
        cor = bv.VERMELHO if a.get("grave") else (
            bv.AMARELO if a.get("precisa") and not a.get("por")
            else bv.VERDE_ESCURO)
        fundo = bv.FUNDOS["grave"] if a.get("grave") else bv.CARTAO
        caixa = tk.Frame(pai, background=fundo, highlightthickness=1,
                         highlightbackground=bv.CINZA_LINHA)
        caixa.pack(fill="x", pady=(0, 8))
        tk.Label(caixa, text="Autorização de venda", background=fundo,
                 foreground=bv.TEXTO, font=bv.fonte(9, "bold")).pack(
                     side="left", padx=(12, 14), pady=8)
        for rot, val in (("Código", a.get("codigo") or "—"),
                         ("Autorizado por", a.get("por") or "—")):
            tk.Label(caixa, text=rot, background=fundo, foreground=bv.SUAVE,
                     font=bv.fonte(8)).pack(side="left")
            tk.Label(caixa, text=val, background=fundo, foreground=bv.TEXTO,
                     font=bv.fonte(9, "bold")).pack(side="left",
                                                    padx=(6, 18))
        if a.get("aviso"):
            tk.Label(caixa, text=a["aviso"], background=fundo, foreground=cor,
                     font=bv.fonte(8, "bold")).pack(side="left", padx=(0, 14))
        tk.Label(caixa, text="Preenchimento no Farol de Pedidos",
                 background=fundo, foreground=bv.SUAVE,
                 font=bv.fonte(8)).pack(side="right", padx=12)

    def _salvar_aut(self, a):
        import autorizacoes                             # noqa: PLC0415
        por = self.v_por.get()
        por = "" if por == VAZIO else por
        try:
            autorizacoes.gravar(AQUI, {a["chave"]: {
                "codigo": self.v_cod.get().strip(), "por": por}})
        except (OSError, ValueError) as erro:
            messagebox.showerror("Autorização", str(erro), parent=self)
            return
        vermelho = a.get("precisa") and not por
        fundo = bv.FUNDOS["grave"] if vermelho else bv.CARTAO
        for w_ in [self.caixa_aut] + list(self.caixa_aut.winfo_children()):
            if isinstance(w_, (tk.Frame, tk.Label)):
                w_.configure(background=fundo)
        self.lbl_aut.configure(
            text=f"Salvo · {por or 'sem autorização'}",
            foreground=bv.VERMELHO if vermelho else bv.VERDE_ESCURO)
        try:                            # a lista de tras ja sai do vermelho
            self.master.carregar()
        except Exception:                               # noqa: BLE001
            pass

    def excel(self):
        d = self.d
        rel = {"id": "pedido", "area": "Pedido", "titulo": d["titulo"],
               "subtitulo": d.get("subtitulo", ""), "fonte": "TABELA_BAP",
               "kpis": d["kpis"], "graficos": [], "avisos": [],
               "tabelas": [{"titulo": "Itens", "colunas": d["colunas"],
                            "linhas": d["linhas"], "tons": d["tons"],
                            "total": d["total"]},
                           {"titulo": "Pedido",
                            "colunas": [{"nome": "CAMPO", "tipo": "texto"},
                                        {"nome": "VALOR", "tipo": "texto"}],
                            "linhas": [list(c) for c in d["campos"]],
                            "tons": [""] * len(d["campos"]), "total": None}]}
        nome = "".join(ch if ch.isalnum() else "_" for ch in d["titulo"])
        destino = PASTA_EXPORT / f"{nome}_{datetime.now():%Y%m%d_%H%M}.xlsx"
        try:
            destino = bv.exportar_excel(rel, destino)
        except PermissionError:
            messagebox.showerror("Excel", "Feche o arquivo no Excel e tente de "
                                 "novo.", parent=self)
            return
        except Exception as e:                           # noqa: BLE001
            messagebox.showerror("Excel", str(e), parent=self)
            return
        bv.abrir_arquivo(destino)


class Cardapio(tk.Tk):
    """Sem argumento: a lista de todos os relatorios (para teste)."""

    def __init__(self):
        super().__init__()
        self.title("Relatórios BAP")
        self.geometry("520x680")
        bv.aplicar_tema(self)
        bv.Cabecalho(self, "Relatórios", "Todos os relatórios").pack(fill="x")
        f = ttk.Frame(self)
        f.pack(fill="both", expand=True, padx=18, pady=12)
        area = None
        for rid, ar, titulo, _ in rn.CATALOGO:
            if ar != area:
                area = ar
                ttk.Label(f, text=ar.upper(), style="Titulo.TLabel").pack(
                    anchor="w", pady=(10, 2))
            ttk.Button(f, text=titulo, command=lambda r=rid: abrir(r)).pack(
                fill="x", pady=1)


def abrir(rid):
    import subprocess                                    # noqa: PLC0415
    subprocess.Popen([sys.executable, str(AQUI / "bap_relatorios.py"), rid],
                     cwd=str(AQUI))


def main():
    rid = sys.argv[1] if len(sys.argv) > 1 else ""
    if rid in rn.POR_ID:
        Relatorio(rid).mainloop()
    else:
        Cardapio().mainloop()


if __name__ == "__main__":
    main()
