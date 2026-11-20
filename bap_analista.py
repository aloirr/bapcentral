# -*- coding: utf-8 -*-
"""
BAP ANALISTA - o programa do ANALISTA COMERCIAL. Um so, com tudo o que e
CADASTRO e PARAMETRO:

    Zonas, vendedores e rota ...... o Planner BAP (zonas, quem atende cada
                                    zona e segmento, rota do mes, PLANNER)
    Metas e RV .................... o Gerador de Meta (meta do mes, faixas
                                    de RV, indicadores executivos)
    Oportunidades e kits .......... o Oportunidades (parametros, kits,
                                    estoque e mix)
    Segmentos e base .............. a SEGMENTACAO_BAP e a BASE_CLIENTE
    Farol DDR ..................... gerar e abrir o Farol do mes
    Relatorios do time ............ os relatorios que os assistentes veem

Os tres programas antigos continuam inteiros: aqui eles abrem DENTRO desta
janela (o pastas_bap.MODO_EMBUTIDO), cada um so quando e clicado pela
primeira vez - por isso o BAP Analista abre rapido.

Os assistentes NAO usam este programa: eles tem so os relatorios (BAP
Central). Quem cadastra meta, vendedor, zona e parametro e o Analista.

Abrir:  pythonw bap_analista.py
"""
from __future__ import annotations

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
import traceback
from datetime import date, datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import pastas_bap as pb                                   # noqa: E402

pb.MODO_EMBUTIDO = True          # ANTES de importar os tres programas

import bap_visual as bv                                   # noqa: E402

# (chave, rotulo, descricao, modulo, classe)
MODULOS = [
    ("planner", "Roteirização",
     "Zonas, vendedor por zona e segmento, rota do mês e o PLANNER.",
     "bap_planner", "App"),
    ("meta", "Metas e RV",
     "Meta do mês e faixas de RV.",
     "bap_meta", "Meta"),
    # (06/10) as Metas executivas sairam daqui: o cadastro abre no
    # Farol Indicadores Executivos (botao Metas executivas)
    ("oportunidade", "Kits promocionais",
     "Parâmetros dos kits promocionais.",
     "bap_oportunidade", "Oportunidades"),
]
CADASTROS_PAINEIS = [
    ("meta_saldo", "Saldo", ""),
    ("expositores", "Expositores (trade)", ""),
    ("transportadoras", "Entrega", ""),
    ("farol_ddr", "Farol DDR", ""),
]
# Farol de Saldo e Farol DDR ja estao no quadrado do Analista e nos
# Relatorios do time; Segmentos e base saiu do menu (04/10).
PAINEIS = [
    # (16/10, Alexandre) Resumo indicadores saiu: o Painel Executivo junta
    ("relatorios", "Relatórios do time", "O que cada assistente vê."),
    # (07/10) vendedor do cliente: Planner x A1_VEND do Protheus
    ("divergencias", "Divergências clientes", ""),
]


class Analista(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BAP Analista")
        self.geometry("1500x940")
        self.minsize(1200, 760)
        bv.aplicar_tema(self)
        try:
            pb.arrumar(AQUI)
        except OSError:
            pass
        cab = bv.Cabecalho(self, "Analista Comercial", "BAP Analista")
        cab.pack(fill="x")
        tk.Frame(self, background=bv.VERDE, height=2).pack(fill="x")
        corpo = tk.Frame(self, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True)
        # (07/10) a largura do menu acompanha a fonte (Windows em 125%/150%
        # cortava "Zonas, vendedores e rota")
        import tkinter.font as tkf                        # noqa: PLC0415
        _f = tkf.Font(font=bv.fonte(10, "bold"))
        largura = max([240] + [_f.measure(x[1]) + 60 for x in
                               MODULOS + CADASTROS_PAINEIS + PAINEIS])
        self.menu = tk.Frame(corpo, background=bv.CARTAO, width=largura,
                             highlightbackground=bv.CINZA_LINHA,
                             highlightthickness=1)
        self.menu.pack(side="left", fill="y")
        self.menu.pack_propagate(False)
        self.area = tk.Frame(corpo, background=bv.FUNDO)
        self.area.pack(side="left", fill="both", expand=True)
        self.quadros, self.botoes, self.atual = {}, {}, None
        tk.Label(self.menu, text="CADASTROS", background=bv.CARTAO,
                 foreground=bv.SUAVE, font=bv.fonte(8, "bold"),
                 anchor="w").pack(fill="x", padx=20, pady=(20, 6))
        for chave, rotulo, desc, _m, _c in MODULOS:
            self._item(chave, rotulo, desc)
        for chave, rotulo, desc in CADASTROS_PAINEIS:
            self._item(chave, rotulo, desc)
        tk.Label(self.menu, text="APOIO", background=bv.CARTAO,
                 foreground=bv.SUAVE, font=bv.fonte(8, "bold"),
                 anchor="w").pack(fill="x", padx=20, pady=(20, 6))
        for chave, rotulo, desc in PAINEIS:
            self._item(chave, rotulo, desc)
        self.status = tk.Label(self.menu, text="", background=bv.CARTAO,
                               foreground=bv.SUAVE, font=bv.fonte(8),
                               justify="left", wraplength=220, anchor="w")
        self.status.pack(side="bottom", fill="x", padx=16, pady=14)
        # (16/10) abre nos Relatorios do time (o Resumo saiu); o Planner
        # monta ao clicar
        self.mostrar("relatorios")

    def _item(self, chave, rotulo, desc):
        f = tk.Frame(self.menu, background=bv.CARTAO, cursor="hand2")
        f.pack(fill="x", padx=8, pady=1)
        barra = tk.Frame(f, background=bv.CARTAO, width=4)
        barra.pack(side="left", fill="y")
        txt = tk.Frame(f, background=bv.CARTAO)
        txt.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        l1 = tk.Label(txt, text=rotulo, background=bv.CARTAO,
                      foreground=bv.TEXTO, font=bv.fonte(10), anchor="w")
        l1.pack(fill="x")
        l2 = tk.Label(txt, background=bv.CARTAO)    # sem descricao: o nome basta
        for w in (f, txt, l1, l2, barra):
            w.bind("<Button-1>", lambda e, c=chave: self.mostrar(c))
        self.botoes[chave] = (f, barra, txt, l1, l2)

    def _pintar(self, chave):
        for c, (f, barra, txt, l1, l2) in self.botoes.items():
            fundo = bv.VERDE_CLARO if c == chave else bv.CARTAO
            for w in (f, txt, l1, l2):
                w.configure(background=fundo)
            l1.configure(font=bv.fonte(10, "bold" if c == chave else "normal"))
            barra.configure(background=bv.VERDE if c == chave else fundo)

    # ------------------------------------------------------------ trocar
    def mostrar(self, chave):
        if self.atual == chave:
            return
        if self.atual in self.quadros:
            self.quadros[self.atual].pack_forget()
        self._pintar(chave)
        self.atual = chave
        if chave not in self.quadros:
            quadro = tk.Frame(self.area, background=bv.FUNDO)
            self.quadros[chave] = quadro
            quadro.pack(fill="both", expand=True)
            self.update_idletasks()
            try:
                self._montar(chave, quadro)
            except Exception as erro:                    # noqa: BLE001
                traceback.print_exc()
                tk.Label(quadro, text=f"Não consegui abrir esta parte:\n\n"
                                      f"{erro}", background=bv.FUNDO,
                         foreground=bv.VERMELHO, font=bv.fonte(11),
                         justify="left").pack(padx=30, pady=30, anchor="w")
        else:
            self.quadros[chave].pack(fill="both", expand=True)

    def _montar(self, chave, quadro):
        modulo = next((m for m in MODULOS if m[0] == chave), None)
        if modulo:
            carregando = tk.Label(quadro, text="Abrindo…", background=bv.FUNDO,
                                  foreground=bv.SUAVE, font=bv.fonte(12))
            carregando.pack(pady=60)
            self.update_idletasks()
            mod = __import__(modulo[3])
            pb.PAI_EMBUTIDO = quadro
            carregando.destroy()
            getattr(mod, modulo[4])()
            self._compactar(quadro)
            return
        getattr(self, f"_painel_{chave}")(quadro)

    def _compactar(self, quadro):
        """Os paragrafos de ajuda dos cadastros viram um 'ⓘ' com dica."""
        bv.compactar_ajudas(quadro)
        if not getattr(self, "_ligado", False):
            self._ligado = True
            # abas montadas depois (na primeira vez que abrem) tambem
            # so o quadro da aba que abriu (varrer todos os modulos a cada
            # troca de aba pesava na tela inteira)
            self.bind_all("<<NotebookTabChanged>>", lambda e: self.after(
                50, lambda w=e.widget: self._compactar_aba(w)), add="+")

    def _compactar_aba(self, w):
        try:
            aba = w.nametowidget(w.select()) if hasattr(w, "select") else w
        except (tk.TclError, KeyError, AttributeError):
            aba = w
        try:
            bv.compactar_ajudas(aba)
        except tk.TclError:
            pass

    # ------------------------------------------------------- os paineis
    def _titulo(self, pai, titulo, sub=""):
        tk.Label(pai, text=titulo, background=bv.FUNDO, foreground=bv.TEXTO,
                 font=bv.fonte(16, "bold"), anchor="w").pack(fill="x", padx=30,
                                                            pady=(24, 0))
        tk.Label(pai, text=sub, background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(10), anchor="w").pack(fill="x", padx=30,
                                                      pady=(2, 16))

    def _botoes(self, pai, itens):
        caixa = tk.Frame(pai, background=bv.FUNDO)
        caixa.pack(fill="x", padx=24)
        for i, (rot, desc, cmd) in enumerate(itens):
            c = tk.Frame(caixa, background=bv.CARTAO, cursor="hand2",
                         highlightbackground=bv.CINZA_LINHA, highlightthickness=1)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
            a = tk.Label(c, text=rot, background=bv.CARTAO, foreground=bv.TEXTO,
                         font=bv.fonte(11, "bold"), anchor="w")
            a.pack(fill="x", padx=16, pady=(14, 0))
            b = tk.Label(c, text=desc, background=bv.CARTAO, foreground=bv.SUAVE,
                         font=bv.fonte(9), anchor="w")
            b.pack(fill="x", padx=16, pady=(2, 14))
            for w in (c, a, b):
                w.bind("<Enter>", lambda e, ws=(c, a, b): [
                    x.configure(background=bv.VERDE_CLARO) for x in ws])
                w.bind("<Leave>", lambda e, ws=(c, a, b): [
                    x.configure(background=bv.CARTAO) for x in ws])
            for w in (c, a, b):
                w.bind("<Button-1>", lambda e, f=cmd: f())
        for j in range(3):
            caixa.columnconfigure(j, weight=1, uniform="b")
        return caixa

    def _abrir(self, caminho: Path):
        if not caminho.exists():
            messagebox.showinfo("BAP Analista", f"{caminho.name} não existe "
                                f"ainda nesta pasta.", parent=self)
            return
        bv.abrir_arquivo(caminho)

    def _painel_segmentos(self, q):
        self._titulo(q, "Segmentos e base de clientes")
        self._botoes(q, [
            ("Regras e ajustes", "SEGMENTACAO_BAP.xlsx",
             lambda: self._abrir(AQUI / "SEGMENTACAO_BAP.xlsx")),
            ("Base de clientes", "BASE_CLIENTE.xlsx",
             lambda: self._abrir(AQUI / pb.RELATORIOS / "BASE_CLIENTE.xlsx")),
            ("Base e oportunidades", "Relatório",
             lambda: abrir_relatorio("vc_base")),
        ])
        try:
            import bap_dados as bd                       # noqa: PLC0415
            base = bd.carregar(AQUI, "base")
            from collections import Counter               # noqa: PLC0415
            cont = Counter(c["segmento"] for c in base["clientes"])
            cartoes = tk.Frame(q, background=bv.FUNDO)
            cartoes.pack(fill="x", padx=30, pady=16)
            itens = [("Na base", bv.br(len(base["clientes"])), "neutro"),
                     ("Excluídos", bv.br(base.get("excluidos")), "atencao")] + \
                [(k.title(), bv.br(v), "ok") for k, v in cont.most_common()]
            for i, (r_, v, c) in enumerate(itens):
                bv.cartao_kpi(cartoes, r_, v, c, largura=170).grid(
                    row=i // 5, column=i % 5, sticky="nsew", padx=(0, 10),
                    pady=(0, 10))
            for j in range(5):
                cartoes.columnconfigure(j, weight=1, uniform="s")
        except Exception as erro:                        # noqa: BLE001
            tk.Label(q, text=f"Contagem indisponível: {erro}", background=bv.FUNDO,
                     foreground=bv.SUAVE).pack(anchor="w", padx=30)

    def _painel_farol(self, q):
        import farol_ddr                                 # noqa: PLC0415
        hoje = date.today()
        arq = AQUI / pb.RELATORIOS / f"{farol_ddr.PREFIXO}{hoje:%Y-%m}.xlsx"
        self._titulo(q, "Farol DDR",
                     f"{farol_ddr.MESES[hoje.month]}/{hoje.year} · "
                     f"{'gerado' if arq.exists() else 'não gerado'}")

        def gerar():
            try:
                destino = farol_ddr.gerar_farol(hoje.year, hoje.month,
                                                AQUI / pb.RELATORIOS)
            except FileExistsError as erro:
                messagebox.showinfo("Farol DDR", str(erro), parent=self)
                return
            messagebox.showinfo("Farol DDR", f"Gerado: {destino.name}",
                                parent=self)
            bv.abrir_arquivo(destino)

        def proximo():
            a, m = (hoje.year + 1, 1) if hoje.month == 12 else \
                (hoje.year, hoje.month + 1)
            try:
                destino = farol_ddr.gerar_farol(a, m, AQUI / pb.RELATORIOS)
            except FileExistsError as erro:
                messagebox.showinfo("Farol DDR", str(erro), parent=self)
                return
            messagebox.showinfo("Farol DDR", f"Gerado: {destino.name}",
                                parent=self)
        self._botoes(q, [
            ("Abrir o Farol do mês", arq.name, lambda: self._abrir(arq)),
            ("Gerar o Farol do mês", "Não sobrescreve marcações", gerar),
            ("Gerar o do próximo mês", "Usa a rotina mais recente", proximo),
        ])

    def _painel_relatorios(self, q):
        import relatorios_nucleo as rn                   # noqa: PLC0415
        self._titulo(q, "Relatórios do time")
        area = None
        for rid, ar, titulo, _f in rn.CATALOGO:
            if ar != area:
                area = ar
                tk.Label(q, text=ar.upper(), background=bv.FUNDO,
                         foreground=bv.VERDE_ESCURO, font=bv.fonte(9, "bold"),
                         anchor="w").pack(fill="x", padx=30, pady=(12, 2))
                linha = tk.Frame(q, background=bv.FUNDO)
                linha.pack(fill="x", padx=26)
            tk.Button(linha, text=titulo, relief="flat", background=bv.CARTAO,
                      activebackground=bv.VERDE_CLARO, foreground=bv.TEXTO,
                      font=bv.fonte(10), padx=14, pady=6, cursor="hand2",
                      highlightthickness=1, highlightbackground=bv.CINZA_LINHA,
                      command=lambda r=rid: abrir_relatorio(r)).pack(
                          side="left", padx=4, pady=2)
        tk.Frame(q, background=bv.FUNDO, height=18).pack()

        def refazer():
            self.status.configure(text="Atualizando…")

            def trabalho():
                import bap_dados as bd                   # noqa: PLC0415
                return bd.atualizar_tudo(AQUI, log=None)

            def pronto(r):
                erros = [k for k, v in r.items() if str(v).startswith("ERRO")
                         or k == "_erro"]
                self.status.configure(
                    text="Dados atualizados" if not erros else
                    "Erro em: " + ", ".join(erros))
            bv.em_segundo_plano(self, trabalho, pronto)
        tk.Button(q, text="Atualizar dados",
                  relief="flat", background=bv.VERDE, foreground="white",
                  activebackground=bv.VERDE_ESCURO, font=bv.fonte(10, "bold"),
                  padx=16, pady=8, cursor="hand2", command=refazer).pack(
                      anchor="w", padx=30, pady=6)


    # ---------------------------------------------------- meta de saldo
    def _painel_meta_saldo(self, q):
        import relatorios_nucleo as rn                   # noqa: PLC0415
        import saldo_meta as sm                          # noqa: PLC0415
        hoje = date.today()
        comps = []
        a_, m_ = hoje.year, hoje.month
        for k in range(-2, 4):
            mm, aa = m_ + k, a_
            while mm < 1:
                mm, aa = mm + 12, aa - 1
            while mm > 12:
                mm, aa = mm - 12, aa + 1
            comps.append(f"{aa}-{mm:02d}")
        self._titulo(q, "Meta de saldo",
                     "Por UF · dividida pelo peso de venda dos 3 meses "
                     "anteriores")
        topo = tk.Frame(q, background=bv.FUNDO)
        topo.pack(fill="x", padx=30)
        tk.Label(topo, text="Mês", background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=0, column=0, sticky="w")
        rot = {rn.rotulo_mes(c): c for c in comps}
        self.ms_comp = tk.StringVar(value=rn.rotulo_mes(f"{a_}-{m_:02d}"))
        cb = ttk.Combobox(topo, textvariable=self.ms_comp, state="readonly",
                          width=10, values=list(rot))
        cb.grid(row=1, column=0, sticky="w", padx=(0, 20))
        self.ms_ufs = {}
        for j, uf in enumerate(sm.UFS, 1):
            tk.Label(topo, text=uf, background=bv.FUNDO, foreground=bv.SUAVE,
                     font=bv.fonte(9)).grid(row=0, column=j, sticky="w")
            v = tk.StringVar()
            ttk.Entry(topo, textvariable=v, width=12, justify="right").grid(
                row=1, column=j, sticky="w", padx=(0, 10))
            self.ms_ufs[uf] = v
        ttk.Button(topo, text="Salvar e dividir", style="Verde.TButton",
                   command=lambda: self._ms_salvar(rot)).grid(
                       row=1, column=len(sm.UFS) + 1, padx=(10, 0))
        self.ms_info = tk.Label(q, text="", background=bv.FUNDO,
                                foreground=bv.SUAVE, font=bv.fonte(9),
                                anchor="w")
        self.ms_info.pack(fill="x", padx=30, pady=(8, 4))
        corpo = tk.Frame(q, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        corpo.columnconfigure(0, weight=3, uniform="m")
        corpo.columnconfigure(1, weight=2, uniform="m")
        corpo.rowconfigure(0, weight=1)
        self.ms_vend = bv.Tabela(corpo, [
            {"nome": "UF", "largura": 50}, {"nome": "SUPERVISOR", "largura": 180},
            {"nome": "VENDEDOR", "largura": 220},
            {"nome": "VENDA 3 MESES", "tipo": "moeda", "largura": 110},
            {"nome": "PESO NA UF", "tipo": "pct1", "largura": 90},
            {"nome": "META DE SALDO", "tipo": "moeda", "largura": 110}],
            altura=18)
        self.ms_vend.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.ms_sup = bv.Tabela(corpo, [
            {"nome": "UF", "largura": 50}, {"nome": "SUPERVISOR", "largura": 200},
            {"nome": "META DE SALDO", "tipo": "moeda", "largura": 120}],
            altura=18)
        self.ms_sup.grid(row=0, column=1, sticky="nsew")
        cb.bind("<<ComboboxSelected>>", lambda e: self._ms_mostrar(rot))
        self._ms_mostrar(rot)

    def _ms_mostrar(self, rot):
        import saldo_meta as sm                          # noqa: PLC0415
        comp = rot.get(self.ms_comp.get())
        m = sm.meta_do_mes(comp, AQUI) if comp else {}
        for uf, v in self.ms_ufs.items():
            val = (m.get("ufs") or {}).get(uf)
            v.set(bv.br(val, 2) if val else "")
        self._ms_tabelas(m)

    def _ms_tabelas(self, m):
        div = m.get("divisao", [])
        self.ms_vend.mostrar([[d["uf"], d["supervisor"], d["vendedor"],
                               d["venda3m"], d["peso"], d["meta"]]
                              for d in div],
                             total=["TOTAL", "", "", sum(d["venda3m"]
                                                         for d in div), None,
                                    sum(d["meta"] for d in div)] if div
                             else None)
        sup = {}
        for d in div:
            k = (d["uf"], d["supervisor"])
            sup[k] = sup.get(k, 0.0) + d["meta"]
        self.ms_sup.mostrar([[k[0], k[1], v] for k, v in sorted(sup.items())])
        self.ms_info.configure(
            text=f"Gravada em {m['gerado_em']}" if m.get("gerado_em") else
            "Sem meta cadastrada para este mês")

    def _ms_salvar(self, rot):
        import relatorios_nucleo as rn                   # noqa: PLC0415
        import saldo_meta as sm                          # noqa: PLC0415
        comp = rot.get(self.ms_comp.get())
        ufs = {}
        try:
            for uf, v in self.ms_ufs.items():
                t = v.get().strip().replace("R$", "").replace(" ", "")
                if t:
                    ufs[uf] = float(t.replace(".", "").replace(",", "."))
        except ValueError:
            messagebox.showinfo("Meta de saldo", "Valor inválido.", parent=self)
            return
        self.ms_info.configure(text="Dividindo…")

        def trabalho():
            return sm.gravar_meta(rn.Contexto(AQUI), comp, ufs, AQUI)

        def pronto(m):
            if isinstance(m, dict) and "_erro" in m:
                messagebox.showerror("Meta de saldo", str(m["_erro"]),
                                     parent=self)
                return
            self._ms_tabelas(m)
        bv.em_segundo_plano(self, trabalho, pronto)

    # ---------------------------------------------------- expositores
    def _painel_expositores(self, q):
        import expositores as ex                         # noqa: PLC0415
        self.ex_itens = ex.carregar_cadastro(AQUI)
        self.ex_atual = None
        self._titulo(q, "Expositores (trade)", "Quantidade por filial")
        corpo = tk.Frame(q, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        corpo.columnconfigure(0, weight=5, uniform="e")
        corpo.columnconfigure(1, weight=3, uniform="e")
        corpo.rowconfigure(0, weight=1)
        self.ex_tab = bv.Tabela(corpo, [
            {"nome": "NOME", "largura": 260},
            {"nome": "CATEGORIA FOCO", "largura": 130},
            {"nome": "FILIAL", "largura": 120},
            {"nome": "QTD", "tipo": "int", "largura": 60}], altura=20)
        self.ex_tab.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.ex_tab.tv.bind("<<TreeviewSelect>>", self._ex_escolheu, add="+")
        f = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                     highlightbackground=bv.CINZA_LINHA)
        f.grid(row=0, column=1, sticky="new")
        f.columnconfigure(1, weight=1)
        try:
            import bap_dados as bd                       # noqa: PLC0415
            tab = bd.do_cache(AQUI, "tabela") or {}
            filiais = sorted(set((tab.get("filiais") or {}).values()))
        except Exception:                                # noqa: BLE001
            filiais = []
        filiais = filiais or ["BELÉM", "BOA VISTA", "MACAPÁ", "MANAUS",
                              "MATOGROSSO", "SANTARÉM", "SÃO LUIS"]
        self.ex_vars = {}
        for n, (campo, rot, tipo, ops) in enumerate((
                ("nome", "Nome *", "texto", None),
                ("categoria", "Categoria foco", "lista",
                 ex.categorias_foco(AQUI)),
                ("qtd", "Qtd", "numero", None),
                ("filial", "Filial (cidade)", "lista", filiais))):
            tk.Label(f, text=rot, background=bv.CARTAO, foreground=bv.SUAVE,
                     font=bv.fonte(9)).grid(row=n, column=0, sticky="w",
                                           padx=(16, 10),
                                           pady=(14 if n == 0 else 5, 5))
            v = tk.StringVar()
            if tipo == "lista":
                w = ttk.Combobox(f, textvariable=v, state="readonly",
                                 values=ops)
            elif tipo == "numero":
                w = ttk.Spinbox(f, from_=0, to=999, increment=1, width=8,
                                textvariable=v)
            else:
                w = ttk.Entry(f, textvariable=v)
            w.grid(row=n, column=1, sticky="ew" if tipo != "numero" else "w",
                   padx=(0, 16), pady=(14 if n == 0 else 5, 5))
            self.ex_vars[campo] = v
        bt = tk.Frame(f, background=bv.CARTAO)
        bt.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16,
                pady=(10, 14))
        ttk.Button(bt, text="Salvar", style="Verde.TButton",
                   command=self._ex_salvar).pack(side="right")
        ttk.Button(bt, text="Novo", command=self._ex_novo).pack(
            side="right", padx=6)
        ttk.Button(bt, text="Excluir", command=self._ex_excluir).pack(
            side="left")
        ttk.Button(q, text="Abrir o Farol de Expositores",
                   command=lambda: abrir_relatorio("tm_expositores")).pack(
                       anchor="w", padx=30, pady=(0, 16))
        self._ex_pintar()
        self._ex_novo()

    def _ex_pintar(self):
        self.ex_tab.mostrar([[i["nome"], i.get("categoria", ""),
                              i.get("filial", ""), int(i.get("qtd") or 0)]
                             for i in self.ex_itens],
                            total=["TOTAL", "", "", sum(
                                int(i.get("qtd") or 0) for i in self.ex_itens)]
                            if self.ex_itens else None)

    def _ex_escolheu(self, _e=None):
        sel = self.ex_tab.tv.selection()
        linha = self.ex_tab._por_item.get(sel[0]) if sel else None
        if not linha:
            return
        self.ex_atual = (linha[0], linha[2])
        for campo, v in zip(("nome", "categoria", "filial", "qtd"),
                            (linha[0], linha[1], linha[2], linha[3])):
            self.ex_vars[campo].set(v)

    def _ex_novo(self):
        self.ex_atual = None
        for v in self.ex_vars.values():
            v.set("")
        self.ex_vars["qtd"].set("1")

    def _ex_salvar(self):
        import expositores as ex                         # noqa: PLC0415
        nome = self.ex_vars["nome"].get().strip().upper()
        if not nome:
            messagebox.showinfo("Expositores", "Informe o nome.", parent=self)
            return
        try:
            qtd = int(float(self.ex_vars["qtd"].get().replace(",", ".") or 0))
        except ValueError:
            messagebox.showinfo("Expositores", "Quantidade inválida.",
                                parent=self)
            return
        filial = self.ex_vars["filial"].get()
        novo = {"nome": nome, "categoria": self.ex_vars["categoria"].get(),
                "qtd": qtd, "filial": filial}
        itens = [i for i in self.ex_itens
                 if (i["nome"], i.get("filial", "")) not in
                 (self.ex_atual, (nome, filial))]
        itens.append(novo)
        try:
            ex.salvar_cadastro(itens, AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Expositores", str(erro), parent=self)
            return
        self.ex_itens = itens
        self.ex_atual = (nome, filial)
        self._ex_pintar()
        self.status.configure(text=f"{nome} salvo")

    def _ex_excluir(self):
        import expositores as ex                         # noqa: PLC0415
        if not self.ex_atual or not messagebox.askyesno(
                "Expositores", f"Excluir {self.ex_atual[0]} "
                f"({self.ex_atual[1]})?", parent=self):
            return
        itens = [i for i in self.ex_itens
                 if (i["nome"], i.get("filial", "")) != self.ex_atual]
        try:
            ex.salvar_cadastro(itens, AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Expositores", str(erro), parent=self)
            return
        self.ex_itens = itens
        self._ex_pintar()
        self._ex_novo()

    # ------------------------------------------------- transportadoras
    def _painel_transportadoras(self, q):
        import transportadoras as tr                     # noqa: PLC0415
        self.tr_dados = tr.carregar(AQUI)
        self.tr_atual = None                 # nome original da que se edita
        self.tr_cidades = set()              # "UF|CIDADE" marcadas
        self._titulo(q, "Entrega")
        # (10/10) ENTREGA: a aba das TRANSPORTADORAS e a dos PARAMETROS
        # (SLA de entrega por filial e por cidade)
        nb = ttk.Notebook(q, style="Abas.TNotebook")
        nb.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        q_ = tk.Frame(nb, background=bv.FUNDO)
        nb.add(q_, text="Transportadoras")
        q_p = tk.Frame(nb, background=bv.FUNDO)
        nb.add(q_p, text="Parâmetros")
        self._painel_sla(q_p)
        q = q_
        topo = tk.Frame(q, background=bv.FUNDO)
        topo.pack(fill="x", padx=16, pady=(14, 10))
        tk.Label(topo, text="% do frete padrão", background=bv.FUNDO,
                 foreground=bv.SUAVE, font=bv.fonte(9)).pack(side="left")
        self.tr_pct_padrao = tk.StringVar(
            value=bv.br(self.tr_dados.get("pct_padrao"), 1))
        sp = ttk.Spinbox(topo, from_=0, to=50, increment=0.5, width=6,
                         textvariable=self.tr_pct_padrao,
                         command=self._tr_salvar_padrao)
        sp.pack(side="left", padx=6)
        for ev in ("<FocusOut>", "<Return>"):
            sp.bind(ev, lambda e: self._tr_salvar_padrao())
        tk.Label(topo, text="vale para quem não tem % próprio",
                 background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).pack(side="left")
        corpo = tk.Frame(q, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        # (30/10, Alexandre: "estica mais a parte da cidade") lista e
        # formulario meio a meio
        corpo.columnconfigure(0, weight=1, uniform="t")
        corpo.columnconfigure(1, weight=1, uniform="t")
        corpo.rowconfigure(0, weight=1)
        # ---- a lista
        cols = [{"nome": "NOME", "largura": 200}, {"nome": "CONTATO",
                                                   "largura": 150},
                {"nome": "CNPJ", "largura": 130},
                {"nome": "% FRETE", "tipo": "texto", "largura": 70},
                # (23/10, Alexandre) o FRETE MINIMO e ate que nota ele vale
                {"nome": "FRETE MÍNIMO", "largura": 230},
                {"nome": "ONDE ATUA", "largura": 220}]
        self.tr_tab = bv.Tabela(corpo, cols, altura=20)
        self.tr_tab.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.tr_tab.tv.bind("<<TreeviewSelect>>", self._tr_escolheu, add="+")
        # ---- o formulario
        f = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                     highlightbackground=bv.CINZA_LINHA)
        f.grid(row=0, column=1, sticky="nsew")
        f.columnconfigure(1, weight=1)
        self.tr_vars = {}
        for n, (campo, rot) in enumerate((("nome", "Nome *"),
                                          ("contato", "Contato"),
                                          ("cnpj", "CNPJ"),
                                          ("pct", "% do frete"),
                                          ("fmin", "Frete mínimo (R$)"),
                                          ("fate", "Aciona o mínimo em NF "
                                                   "até (R$)"))):
            tk.Label(f, text=rot, background=bv.CARTAO, foreground=bv.SUAVE,
                     font=bv.fonte(9)).grid(row=n, column=0, sticky="w",
                                           padx=(16, 10), pady=(12 if n == 0
                                                                else 4, 4))
            v = tk.StringVar()
            if campo == "pct":
                ttk.Spinbox(f, from_=0, to=50, increment=0.5, width=8,
                            textvariable=v).grid(row=n, column=1, sticky="w",
                                                 padx=(0, 16))
            elif campo == "fmin":
                ttk.Entry(f, textvariable=v, width=12).grid(
                    row=n, column=1, sticky="w", padx=(0, 16), pady=4)
            elif campo == "fate":
                # (30/10, Alexandre) AUTOMATICO: frete minimo / % do frete
                # (a nota em que o % da o minimo; abaixo dela vale o minimo)
                ttk.Entry(f, textvariable=v, width=12, state="readonly").grid(
                    row=n, column=1, sticky="w", padx=(0, 16), pady=4)
            else:
                ttk.Entry(f, textvariable=v).grid(row=n, column=1, sticky="ew",
                                                  padx=(0, 16),
                                                  pady=(12 if n == 0 else 4, 4))
            self.tr_vars[campo] = v
        for k_ in ("pct", "fmin"):
            self.tr_vars[k_].trace_add("write",
                                       lambda *_a: self._tr_aciona_auto())
        tk.Label(f, text="UFs", background=bv.CARTAO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=6, column=0, sticky="nw",
                                       padx=(16, 10), pady=(10, 4))
        ufs = tk.Frame(f, background=bv.CARTAO)
        ufs.grid(row=6, column=1, sticky="w", pady=(10, 4))
        self.tr_ufs = {}
        for uf in tr.UFS:
            v = tk.BooleanVar()
            tk.Checkbutton(ufs, text=uf, variable=v, background=bv.CARTAO,
                           activebackground=bv.CARTAO, font=bv.fonte(10),
                           command=self._tr_listar_cidades).pack(side="left",
                                                                 padx=(0, 6))
            self.tr_ufs[uf] = v
        # (30/10) as CIDADES na largura inteira do formulario (o rotulo
        # em cima) e esticando para baixo
        tk.Label(f, text="Cidades", background=bv.CARTAO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=7, column=0, sticky="nw",
                                       padx=(16, 10), pady=(4, 0))
        cx = tk.Frame(f, background=bv.CARTAO)
        cx.grid(row=8, column=0, columnspan=2, sticky="nsew", padx=16,
                pady=4)
        f.rowconfigure(8, weight=1)
        self.tr_busca = tk.StringVar()
        linha_b = tk.Frame(cx, background=bv.CARTAO)
        linha_b.pack(fill="x")
        tk.Label(linha_b, text="Buscar", background=bv.CARTAO,
                 foreground=bv.SUAVE, font=bv.fonte(9)).pack(side="left",
                                                             padx=(0, 6))
        ent = ttk.Entry(linha_b, textvariable=self.tr_busca)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<KeyRelease>", lambda e: self._tr_listar_cidades())
        # (30/10, Alexandre) coluna % FRETE editavel: o % daquela cidade
        # nesta transportadora (clique na coluna; vazio = o % de cima)
        self.tr_pct_cid = {}
        self.tr_lista = ttk.Treeview(cx, columns=("m", "uf", "c", "p"),
                                     show="headings", height=14,
                                     selectmode="none")
        for c, t, w in (("m", "", 30), ("uf", "UF", 40), ("c", "CIDADE", 220),
                        ("p", "% FRETE", 80)):
            self.tr_lista.heading(c, text=t)
            self.tr_lista.column(c, width=w, stretch=(c == "c"),
                                 anchor="center" if c != "c" else "w")
        self.tr_lista.pack(fill="both", expand=True, pady=(6, 0))
        self.tr_lista.bind("<Button-1>", self._tr_marcar)
        self.tr_info = tk.Label(cx, text="", background=bv.CARTAO,
                                foreground=bv.SUAVE, font=bv.fonte(8),
                                anchor="w")
        self.tr_info.pack(fill="x", pady=(4, 0))
        bt = tk.Frame(f, background=bv.CARTAO)
        bt.grid(row=9, column=0, columnspan=2, sticky="ew", padx=16,
                pady=(8, 14))
        ttk.Button(bt, text="Salvar", style="Verde.TButton",
                   command=self._tr_salvar).pack(side="right")
        ttk.Button(bt, text="Nova", command=self._tr_nova).pack(side="right",
                                                                padx=6)
        ttk.Button(bt, text="Excluir", command=self._tr_excluir).pack(
            side="left")
        self._tr_pintar_lista()
        self._tr_nova()

    # ------------------------------------------------------- Farol DDR
    # (11/10) a ROTINA, a EQUIPE e os FERIADOS do Farol DDR: parametro e do
    # analista (as assistentes so marcam o status no farol). Vale a partir
    # do proximo mes; no Excel do farol as tres abas ficam protegidas.
    DDR_ABAS = {
        "Rotina": (2, [  # (indice na tupla, rotulo, largura, opcoes)
            (1, "COLABORADOR", 150, "equipe"), (2, "HORÁRIO", 95, None),
            (3, "ATIVIDADE", 420, None), (4, "PRIORIDADE", 80,
                                          ("Alta", "Média", "Baixa")),
            (5, "QUANDO", 120, "quando"), (6, "FERRAMENTA BAP", 230, None),
            (7, "ENTREGÁVEL", 200, None)]),
        "Equipe": (0, [(0, "NOME", 240, None), (1, "CARGO", 220, None),
                       (2, "PAPEL", 220, None),
                       (3, "NO FAROL", 80, ("SIM", "NÃO"))]),
        "Feriados": (0, [(0, "DATA (AAAA-MM-DD)", 140, None),
                         (1, "FERIADO", 360, None)]),
    }

    def _painel_farol_ddr(self, q):
        import farol_ddr as fd                           # noqa: PLC0415
        eq, rot, fer = fd.base_do_analista(AQUI / "RELATORIOS")
        self.ddr = {"Equipe": [list(x) for x in eq],
                    "Rotina": [list(x) for x in rot],
                    "Feriados": [list(x) for x in fer]}
        self.ddr_ui = {}
        self._titulo(q, "Farol DDR", "Rotina, equipe e feriados - valem a "
                     "partir do próximo mês do farol")
        nb = ttk.Notebook(q, style="Abas.TNotebook")
        nb.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        for nome, (_ord, campos) in self.DDR_ABAS.items():
            aba = tk.Frame(nb, background=bv.FUNDO)
            nb.add(aba, text=nome)
            corpo = tk.Frame(aba, background=bv.FUNDO)
            corpo.pack(fill="both", expand=True, padx=16, pady=14)
            corpo.columnconfigure(0, weight=7, uniform="d")
            corpo.columnconfigure(1, weight=3, uniform="d")
            corpo.rowconfigure(0, weight=1)
            tab = bv.Tabela(corpo, [{"nome": rot_, "largura": lg}
                                    for _i, rot_, lg, _o in campos],
                            altura=20, compacta=True, zebra=True)
            tab.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
            tab.tv.bind("<<TreeviewSelect>>",
                        lambda e, n=nome: self._ddr_escolheu(n), add="+")
            f = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                         highlightbackground=bv.CINZA_LINHA)
            f.grid(row=0, column=1, sticky="nsew")
            f.columnconfigure(1, weight=1)
            vars_ = {}
            for n, (i_, rot_, _lg, ops) in enumerate(campos):
                tk.Label(f, text=rot_.capitalize(), background=bv.CARTAO,
                         foreground=bv.SUAVE, font=bv.fonte(9)).grid(
                             row=n, column=0, sticky="w", padx=(16, 10),
                             pady=(14 if n == 0 else 4, 4))
                v = tk.StringVar()
                if ops:
                    w = ttk.Combobox(f, textvariable=v,
                                     state="readonly" if isinstance(
                                         ops, tuple) else "normal")
                    if isinstance(ops, tuple):
                        w.configure(values=ops)
                else:
                    w = ttk.Entry(f, textvariable=v)
                w.grid(row=n, column=1, sticky="ew", padx=(0, 16),
                       pady=(14 if n == 0 else 4, 4))
                vars_[i_] = (v, w, ops)
            f.rowconfigure(len(campos), weight=1)
            bt = tk.Frame(f, background=bv.CARTAO)
            bt.grid(row=len(campos) + 1, column=0, columnspan=2, sticky="ew",
                    padx=16, pady=(16, 14))
            ttk.Button(bt, text="Salvar", style="Verde.TButton",
                       command=lambda n=nome: self._ddr_salvar(n)).pack(
                           side="right")
            ttk.Button(bt, text="Nova",
                       command=lambda n=nome: self._ddr_nova(n)).pack(
                           side="right", padx=6)
            ttk.Button(bt, text="Excluir",
                       command=lambda n=nome: self._ddr_excluir(n)).pack(
                           side="left")
            tk.Label(aba, text="Vale a partir do próximo mês do Farol DDR. "
                     "No Excel do farol estas abas ficam só para consulta.",
                     background=bv.FUNDO, foreground=bv.SUAVE,
                     font=bv.fonte(9), anchor="w").pack(fill="x", padx=16,
                                                        pady=(0, 10))
            self.ddr_ui[nome] = {"tab": tab, "vars": vars_, "atual": None}
        self._ddr_pintar()

    def _ddr_opcoes(self):
        import farol_ddr as fd                           # noqa: PLC0415
        nomes = [e[0] for e in self.ddr["Equipe"]]
        for ui in self.ddr_ui.values():
            for _i, (v, w, ops) in ui["vars"].items():
                if ops == "equipe":
                    w.configure(values=nomes)
                elif ops == "quando":
                    w.configure(values=["DIÁRIA", "SEG", "TER", "QUA", "QUI",
                                        "SEX", "SEG,QUA", "TER,QUI",
                                        "SEG,QUA,SEX"]
                                + [q_ for q_ in fd.QUANDO_VALIDOS
                                   if "(" not in q_ and q_ != "DIÁRIA"])

    def _ddr_pintar(self):
        for nome, ui in self.ddr_ui.items():
            campos = self.DDR_ABAS[nome][1]
            ls = [[(x[i_] if i_ < len(x) else "") for i_, *_r in campos]
                  for x in self.ddr[nome]]
            ui["tab"].mostrar(ls, [""] * len(ls))
            ui["linhas"] = ls
        self._ddr_opcoes()

    def _ddr_escolheu(self, nome):
        ui = self.ddr_ui[nome]
        try:
            sel = ui["tab"].tv.selection()
            linha = ui["tab"]._por_item.get(sel[0]) if sel else None  # noqa: SLF001
        except (tk.TclError, AttributeError, IndexError):
            linha = None
        if linha is None:
            return
        try:
            j = next(k for k, l_ in enumerate(ui["linhas"]) if l_ is linha)
        except StopIteration:
            return
        ui["atual"] = j
        for i_, (v, _w, _o) in ui["vars"].items():
            x = self.ddr[nome][j]
            v.set(str(x[i_]) if i_ < len(x) and x[i_] is not None else "")

    def _ddr_nova(self, nome):
        ui = self.ddr_ui[nome]
        ui["atual"] = None
        for v, _w, _o in ui["vars"].values():
            v.set("")

    def _ddr_gravar(self):
        import farol_ddr as fd                           # noqa: PLC0415
        try:
            fd.salvar_config(self.ddr["Equipe"], self.ddr["Rotina"],
                             self.ddr["Feriados"], AQUI)
        except OSError as erro:
            messagebox.showerror("Farol DDR", str(erro), parent=self)
            return False
        self._ddr_pintar()
        return True

    def _ddr_salvar(self, nome):
        ui = self.ddr_ui[nome]
        tam = {"Rotina": 9, "Equipe": 4, "Feriados": 2}[nome]
        j = ui["atual"]
        x = list(self.ddr[nome][j]) if j is not None else (
            ["Administrativo BAP"] + [""] * 8 if nome == "Rotina"
            else [""] * tam)
        x += [""] * (tam - len(x))
        antigo = x[0] if nome == "Equipe" else None
        for i_, (v, _w, _o) in ui["vars"].items():
            x[i_] = v.get().strip()
        chave = x[self.DDR_ABAS[nome][0]]
        if not chave or (nome == "Rotina" and not x[3]):
            messagebox.showinfo("Farol DDR", "Preencha os campos principais.",
                                parent=self)
            return
        if nome == "Feriados":
            try:
                datetime.strptime(x[0][:10], "%Y-%m-%d")
            except ValueError:
                messagebox.showinfo("Farol DDR", "Data no formato "
                                    "AAAA-MM-DD (ex.: 2026-12-24).",
                                    parent=self)
                return
        if nome == "Rotina":
            x[4] = x[4] or "Média"
            x[5] = x[5] or "DIÁRIA"
        if j is None:
            self.ddr[nome].append(x)
            ui["atual"] = len(self.ddr[nome]) - 1
        else:
            self.ddr[nome][j] = x
        if antigo and antigo != x[0]:      # trocou o nome: a rotina segue
            for r_ in self.ddr["Rotina"]:
                if r_[1] == antigo:
                    r_[1] = x[0]
        if nome == "Feriados":
            self.ddr[nome].sort(key=lambda f_: str(f_[0]))
        if self._ddr_gravar():
            self.status.configure(text=f"Farol DDR · {nome} salvo - vale no "
                                       f"próximo mês")

    def _ddr_excluir(self, nome):
        ui = self.ddr_ui[nome]
        j = ui["atual"]
        if j is None:
            return
        if not messagebox.askyesno("Farol DDR", "Excluir a linha escolhida?",
                                   parent=self):
            return
        del self.ddr[nome][j]
        ui["atual"] = None
        self._ddr_nova(nome)
        self._ddr_gravar()

    # ------------------------------------------- entrega › parametros (SLA)
    def _painel_sla(self, q):
        """SLA ENTREGA LOCAL e SLA ENTREGA FRETE por filial e, se quiser, o
        SLA de uma cidade (vale a cidade; sem ela, a filial)."""
        import transportadoras as tr                     # noqa: PLC0415
        self.sla = tr.ler_sla(AQUI)
        tk.Label(q, text="Dias úteis para entregar. Vale o SLA da cidade "
                 "cadastrada; sem ela, o da filial onde a cidade está "
                 "(local ou frete).", background=bv.FUNDO,
                 foreground=bv.SUAVE, font=bv.fonte(9), anchor="w").pack(
                     fill="x", padx=16, pady=(14, 10))
        # (30/10) o Salvar vem antes (embaixo, sempre visivel): com a janela
        # baixa ele nao some nem fica cortado
        rod = tk.Frame(q, background=bv.FUNDO)
        rod.pack(side="bottom", fill="x", padx=16, pady=(0, 16))
        ttk.Button(rod, text="Salvar parâmetros", style="Verde.TButton",
                   command=self._sla_salvar).pack(side="right")
        corpo = tk.Frame(q, background=bv.FUNDO)
        corpo.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        corpo.columnconfigure(0, weight=1, uniform="s")
        corpo.columnconfigure(1, weight=1, uniform="s")
        corpo.rowconfigure(0, weight=1)
        # ---- por filial
        f = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                     highlightbackground=bv.CINZA_LINHA)
        f.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        tk.Label(f, text="SLA por filial", background=bv.CARTAO,
                 foreground=bv.TEXTO, font=bv.fonte(11, "bold"),
                 anchor="w").grid(row=0, column=0, columnspan=3, sticky="w",
                                  padx=16, pady=(14, 10))
        for j, t_ in enumerate(("FILIAL", "SLA ENTREGA LOCAL",
                                "SLA ENTREGA FRETE")):
            tk.Label(f, text=t_, background=bv.CARTAO, foreground=bv.SUAVE,
                     font=bv.fonte(8, "bold")).grid(
                         row=1, column=j, sticky="w" if j == 0 else "",
                         padx=(16 if j == 0 else 8, 8), pady=(0, 6))
        self.sla_vars = {}
        for i, fil in enumerate(tr.FILIAIS):
            atual = self.sla["filiais"].get(tr._norm(fil)) or {}   # noqa: SLF001
            tk.Label(f, text=fil, background=bv.CARTAO, foreground=bv.TEXTO,
                     font=bv.fonte(10), anchor="w").grid(
                         row=2 + i, column=0, sticky="ew", padx=(16, 8),
                         pady=3)
            vs = []
            for j, (k, pad) in enumerate((("local", tr.SLA_LOCAL_PADRAO),
                                          ("frete", tr.SLA_FRETE_PADRAO))):
                v = tk.StringVar(value=str(atual.get(k, pad)))
                ttk.Spinbox(f, from_=0, to=60, increment=1, width=6,
                            textvariable=v).grid(row=2 + i, column=1 + j,
                                                 padx=8, pady=3)
                vs.append(v)
            self.sla_vars[fil] = vs
        f.columnconfigure(0, weight=1)
        # ---- por cidade
        c = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                     highlightbackground=bv.CINZA_LINHA)
        c.grid(row=0, column=1, sticky="nsew")
        tk.Label(c, text="SLA por cidade (opcional)", background=bv.CARTAO,
                 foreground=bv.TEXTO, font=bv.fonte(11, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(14, 10))
        # (30/10, Alexandre: "ajuste o layout do botao Adicionar") a linha
        # UF / Cidade / SLA em grade (a CIDADE estica ou encolhe) e o
        # ADICIONAR na barra de baixo, ao lado do Remover cidade - a barra
        # vem antes da tabela, entao nunca sai do quadro nem e cortada
        bt = tk.Frame(c, background=bv.CARTAO)
        bt.pack(side="bottom", fill="x", padx=16, pady=(0, 14))
        ttk.Button(bt, text="Adicionar cidade", style="Verde.TButton",
                   command=self._sla_add_cidade).pack(side="left")
        ttk.Button(bt, text="Remover cidade",
                   command=self._sla_remover_cidade).pack(side="left",
                                                           padx=(8, 0))
        lin = tk.Frame(c, background=bv.CARTAO)
        lin.pack(fill="x", padx=16)
        self.sla_uf = tk.StringVar(value=tr.UFS[0])
        self.sla_cid = tk.StringVar()
        self.sla_n = tk.StringVar(value=str(tr.SLA_FRETE_PADRAO))
        tk.Label(lin, text="UF", background=bv.CARTAO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=0, column=0, sticky="w")
        cb_uf = ttk.Combobox(lin, textvariable=self.sla_uf, values=tr.UFS,
                             state="readonly", width=5)
        cb_uf.grid(row=0, column=1, padx=(6, 12))
        tk.Label(lin, text="Cidade", background=bv.CARTAO,
                 foreground=bv.SUAVE, font=bv.fonte(9)).grid(
                     row=0, column=2, sticky="w")
        self.sla_cb_cid = ttk.Combobox(lin, textvariable=self.sla_cid,
                                       width=8)
        self.sla_cb_cid.grid(row=0, column=3, sticky="ew", padx=(6, 12))
        tk.Label(lin, text="SLA", background=bv.CARTAO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=0, column=4, sticky="w")
        ttk.Spinbox(lin, from_=0, to=60, increment=1, width=4,
                    textvariable=self.sla_n).grid(row=0, column=5,
                                                  padx=(6, 0))
        lin.columnconfigure(3, weight=1)

        def cidades_da_uf(_e=None):
            todas = tr.cidades_da_uf(self.sla_uf.get())
            t_ = self.sla_cid.get().strip().upper()
            self.sla_cb_cid.configure(values=[x for x in todas
                                              if t_ in x.upper()] if t_
                                      else todas)
        cb_uf.bind("<<ComboboxSelected>>", lambda e: (self.sla_cid.set(""),
                                                      cidades_da_uf()))
        self.sla_cb_cid.bind("<KeyRelease>", cidades_da_uf)
        cidades_da_uf()
        cols = [{"nome": "UF", "largura": 50}, {"nome": "CIDADE",
                                                "largura": 220},
                {"nome": "SLA (DIAS ÚTEIS)", "tipo": "int", "largura": 110},
                {"nome": "FILIAL", "largura": 120}]
        self.sla_tab = bv.Tabela(c, cols, altura=12)
        self.sla_tab.pack(fill="both", expand=True, padx=16, pady=(10, 8))
        self._sla_pintar()

    def _sla_pintar(self):
        import transportadoras as tr                     # noqa: PLC0415
        ls = []
        for k, n in sorted(self.sla["cidades"].items()):
            uf, cid = (k.split("|") + [""])[:2]
            ls.append([uf, cid, n, tr.FILIAL_DA_UF.get(uf, "")])
        self.sla_tab.mostrar(ls, [""] * len(ls))

    def _sla_add_cidade(self):
        import transportadoras as tr                     # noqa: PLC0415
        cid = self.sla_cid.get().strip()
        if not cid:
            return
        try:
            n = int(float(self.sla_n.get().replace(",", ".")))
        except ValueError:
            messagebox.showinfo("Entrega", "SLA inválido.", parent=self)
            return
        self.sla["cidades"][tr.chave_cidade(self.sla_uf.get(), cid)] = n
        self.sla_cid.set("")
        self._sla_pintar()
        self.status.configure(text="Cidade incluída - clique em Salvar "
                                   "parâmetros")

    def _sla_remover_cidade(self):
        try:
            sel = [self.sla_tab._por_item[i]            # noqa: SLF001
                   for i in self.sla_tab.tv.selection()]
        except (AttributeError, KeyError, tk.TclError):
            sel = []
        import transportadoras as tr                     # noqa: PLC0415
        for l in sel:
            self.sla["cidades"].pop(tr.chave_cidade(l[0], l[1]), None)
        self._sla_pintar()

    def _sla_salvar(self):
        import transportadoras as tr                     # noqa: PLC0415
        fil = {}
        for nome, (v_l, v_f) in self.sla_vars.items():
            try:
                fil[tr._norm(nome)] = {                  # noqa: SLF001
                    "local": int(float(v_l.get().replace(",", "."))),
                    "frete": int(float(v_f.get().replace(",", ".")))}
            except ValueError:
                messagebox.showinfo("Entrega", f"SLA inválido em {nome}.",
                                    parent=self)
                return
        self.sla["filiais"] = fil
        try:
            tr.salvar_sla(self.sla, AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Entrega", str(erro), parent=self)
            return
        try:                    # a lista de transportadoras segue valendo
            self.tr_dados = tr.carregar(AQUI)
        except Exception:                                # noqa: BLE001
            pass
        self.status.configure(text="SLA de entrega salvo - vale nos faróis "
                                   "na próxima atualização")

    def _tr_onde(self, t):
        import transportadoras as tr                     # noqa: PLC0415
        if not t["ufs"] and not t["cidades"]:
            return "todas as UFs"
        partes = []
        for uf in tr.UFS:
            n = sum(1 for c in t["cidades"] if c.startswith(uf + "|"))
            if n:
                partes.append(f"{uf}: {n} cidade{'s' if n > 1 else ''}")
            elif uf in t["ufs"]:
                partes.append(uf)
        return " · ".join(partes)

    def _tr_pintar_lista(self):
        import transportadoras as tr                     # noqa: PLC0415
        ts = self.tr_dados["transportadoras"]
        self.tr_tab.mostrar([[t["nome"], t["contato"], t["cnpj"],
                              (bv.br(t["pct_frete"], 1) + "%")
                              if t.get("pct_frete") not in (None, "")
                              else "padrão",
                              tr.texto_minimo(t, self._tr_pct_padrao_num()),
                              self._tr_onde(t)] for t in ts])

    def _tr_escolheu(self, _e=None):
        sel = self.tr_tab.tv.selection()
        if not sel:
            return
        linha = self.tr_tab._por_item.get(sel[0])
        t = next((x for x in self.tr_dados["transportadoras"]
                  if linha and x["nome"] == linha[0]), None)
        if not t:
            return
        self.tr_atual = t["nome"]
        self.tr_vars["nome"].set(t["nome"])
        self.tr_vars["contato"].set(t["contato"])
        self.tr_vars["cnpj"].set(t["cnpj"])
        self.tr_vars["pct"].set("" if t.get("pct_frete") in (None, "")
                                else bv.br(t["pct_frete"], 1))
        self.tr_vars["fmin"].set("" if t.get("frete_minimo") in (None, "")
                                 else bv.br(t["frete_minimo"], 2))
        self._tr_aciona_auto()
        ufs_c = {c.split("|")[0] for c in t["cidades"]}
        for uf, v in self.tr_ufs.items():
            v.set(uf in t["ufs"] or uf in ufs_c)
        self.tr_cidades = set(t["cidades"])
        self.tr_pct_cid = dict(t.get("pct_cidades") or {})
        self.tr_busca.set("")
        self._tr_listar_cidades()

    def _tr_pct_padrao_num(self):
        try:
            return self._tr_numero(self.tr_pct_padrao.get())
        except (ValueError, AttributeError):
            return None

    def _tr_aciona_auto(self):
        """(30/10, Alexandre) o "Aciona o minimo em NF ate" sai sozinho:
        frete minimo / % do frete (sem %: o padrao)."""
        import transportadoras as tr                     # noqa: PLC0415
        try:
            fmin = self._tr_reais(self.tr_vars["fmin"].get())
            pct = self._tr_numero(self.tr_vars["pct"].get())
        except (ValueError, KeyError):
            fmin = pct = None
        if pct is None:
            pct = self._tr_pct_padrao_num()
        ate = tr.minimo_ate_auto(fmin, pct if pct is not None
                                 else tr.PCT_PADRAO)
        if "fate" in self.tr_vars:
            self.tr_vars["fate"].set("" if ate is None else bv.br(ate, 2))
        self._tr_repintar_pct()

    def _tr_nova(self):
        self.tr_atual = None
        for v in self.tr_vars.values():
            v.set("")
        for v in self.tr_ufs.values():
            v.set(False)
        self.tr_cidades = set()
        self.tr_pct_cid = {}
        self._tr_listar_cidades()
        try:
            self.tr_tab.tv.selection_remove(self.tr_tab.tv.selection())
        except tk.TclError:
            pass

    def _tr_listar_cidades(self):
        import transportadoras as tr                     # noqa: PLC0415
        lst = self.tr_lista
        lst.delete(*lst.get_children())
        busca = self.tr_busca.get().strip().upper()
        ufs = [uf for uf, v in self.tr_ufs.items() if v.get()]
        # desmarcou a UF: as cidades dela saem
        self.tr_cidades = {c for c in self.tr_cidades
                           if c.split("|")[0] in ufs}
        for uf in ufs:
            for cid in tr.cidades_da_uf(uf):
                if busca and busca not in cid:
                    continue
                k = f"{uf}|{cid}"
                lst.insert("", "end", iid=k, values=(
                    "✓" if k in self.tr_cidades else "", uf, cid,
                    self._tr_pct_txt(k)))
        self.tr_pct_cid = {k: v for k, v in self.tr_pct_cid.items()
                           if k.split("|")[0] in ufs}
        self._tr_info_cidades(bool(ufs))

    def _tr_pct_base(self):
        """(30/10, Alexandre: "frete das cidades tem que ser o frete
        padrao") o % que a cidade usa quando nao tem o dela: o % do frete da
        transportadora; sem ele, o % do frete padrao."""
        import transportadoras as tr                     # noqa: PLC0415
        try:
            p_ = self._tr_numero(self.tr_vars["pct"].get())
        except (ValueError, KeyError, AttributeError):
            p_ = None
        if p_ is None:
            p_ = self._tr_pct_padrao_num()
        return tr.PCT_PADRAO if p_ is None else p_

    def _tr_pct_txt(self, k):
        v = self.tr_pct_cid.get(k)
        return bv.br(self._tr_pct_base() if v is None else v, 1) + "%"

    def _tr_repintar_pct(self):
        """O % de cada cidade da lista (o padrao muda junto com o % de
        cima)."""
        lst = getattr(self, "tr_lista", None)
        if lst is None:
            return
        for k in lst.get_children():
            lst.set(k, "p", self._tr_pct_txt(k))

    def _tr_info_cidades(self, tem_uf=True):
        n, n_p = len(self.tr_cidades), len(self.tr_pct_cid)
        if not tem_uf:
            txt = "Nenhuma UF marcada: atua em todas"
        else:
            txt = (f"{n} cidade(s) marcada(s)" if n else
                   "Nenhuma cidade marcada: atua na UF inteira")
            txt += (f" · % próprio em {n_p}" if n_p else "") + \
                " · % FRETE = o da transportadora; clique para mudar"
        self.tr_info.configure(text=txt)

    def _tr_editar_pct(self, k):
        """(30/10) a caixinha do % da cidade em cima da celula: Enter grava,
        Esc desiste; vazio = volta ao % da transportadora. Pôr % marca a
        cidade."""
        lst = self.tr_lista
        caixa = lst.bbox(k, "p")
        if not caixa:
            return
        x, y, w, h = caixa
        v = tk.StringVar(value=self._tr_pct_txt(k).replace("%", ""))
        e = ttk.Entry(lst, textvariable=v, width=6, justify="center")
        e.place(x=x, y=y, width=w, height=h)
        e.focus_set()
        e.select_range(0, "end")

        def gravar(_ev=None):
            if not e.winfo_exists():
                return
            try:
                n = self._tr_numero(v.get())
                if n is not None and not 0 < n <= 50:
                    raise ValueError
            except ValueError:
                e.destroy()
                messagebox.showinfo("Transportadoras", "% do frete da cidade "
                                    "inválido (ex.: 4,5).", parent=self)
                return
            e.destroy()
            # igual ao padrao (ou vazio) = a cidade usa o padrao
            if n is None or abs(n - self._tr_pct_base()) < 1e-9:
                self.tr_pct_cid.pop(k, None)
            else:
                self.tr_pct_cid[k] = n
                self.tr_cidades.add(k)
                lst.set(k, "m", "✓")
            lst.set(k, "p", self._tr_pct_txt(k))
            self._tr_info_cidades()
        e.bind("<Return>", gravar)
        e.bind("<KP_Enter>", gravar)
        e.bind("<FocusOut>", gravar)
        e.bind("<Escape>", lambda _ev: e.destroy())

    def _tr_marcar(self, e):
        k = self.tr_lista.identify_row(e.y)
        if not k:
            return "break"
        if self.tr_lista.identify_column(e.x) == "#4":     # % FRETE
            self._tr_editar_pct(k)
            return "break"
        if k in self.tr_cidades:
            self.tr_cidades.discard(k)
            self.tr_pct_cid.pop(k, None)     # desmarcou: o % dela sai
            self.tr_lista.set(k, "p", self._tr_pct_txt(k))
        else:
            self.tr_cidades.add(k)
        self.tr_lista.set(k, "m", "✓" if k in self.tr_cidades else "")
        self._tr_info_cidades()
        return "break"

    def _tr_numero(self, txt):
        txt = str(txt or "").strip().replace("%", "").replace(",", ".")
        if not txt:
            return None
        return float(txt)

    @staticmethod
    def _tr_reais(txt):
        """(23/10) R$ escrito do jeito brasileiro: "120", "120,50",
        "2.400" ou "R$ 2.400,00"."""
        import re                                       # noqa: PLC0415
        t = str(txt or "").upper().replace("R$", "").replace(" ", "")
        if not t:
            return None
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
        v = float(t)
        if v < 0:
            raise ValueError
        return v

    def _tr_salvar(self):
        import transportadoras as tr                     # noqa: PLC0415
        nome = self.tr_vars["nome"].get().strip().upper()
        if not nome:
            messagebox.showinfo("Transportadoras", "Informe o nome.",
                                parent=self)
            return
        try:
            pct = self._tr_numero(self.tr_vars["pct"].get())
            padrao = self._tr_numero(self.tr_pct_padrao.get())
        except ValueError:
            messagebox.showinfo("Transportadoras", "% do frete inválido.",
                                parent=self)
            return
        try:
            fmin = self._tr_reais(self.tr_vars["fmin"].get())
        except ValueError:
            messagebox.showinfo("Transportadoras", "Frete mínimo inválido "
                                "(use R$, ex.: 120 ou 150,00).", parent=self)
            return
        # (30/10) o "aciona o minimo" e automatico: minimo / %
        fate = tr.minimo_ate_auto(
            fmin, pct if pct is not None else
            (padrao if padrao is not None else tr.PCT_PADRAO))
        t = tr.novo(nome, self.tr_vars["contato"].get().strip(),
                    self.tr_vars["cnpj"].get().strip(), pct,
                    [uf for uf, v in self.tr_ufs.items() if v.get()],
                    sorted(self.tr_cidades), fmin, fate,
                    {k: v for k, v in self.tr_pct_cid.items()
                     if k in self.tr_cidades
                     and abs(v - self._tr_pct_base()) > 1e-9})
        ts = [x for x in self.tr_dados["transportadoras"]
              if x["nome"] not in (self.tr_atual, nome)]
        ts.append(t)
        dados = dict(self.tr_dados, transportadoras=ts,
                     pct_padrao=tr.PCT_PADRAO if padrao is None else padrao)
        try:
            tr.salvar(dados, AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Transportadoras", str(erro), parent=self)
            return
        self.tr_dados = dados
        self.tr_atual = nome
        self.tr_vars["nome"].set(nome)
        self._tr_pintar_lista()
        self.status.configure(text=f"{nome} salva")

    def _tr_salvar_padrao(self):
        import transportadoras as tr                     # noqa: PLC0415
        try:
            padrao = self._tr_numero(self.tr_pct_padrao.get())
        except ValueError:
            return
        if padrao is None or padrao == self.tr_dados.get("pct_padrao"):
            return
        dados = dict(self.tr_dados, pct_padrao=padrao)
        try:
            tr.salvar(dados, AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Transportadoras", str(erro), parent=self)
            return
        self.tr_dados = dados
        self.status.configure(text=f"% do frete padrão: {bv.br(padrao, 1)}%")
        self._tr_repintar_pct()

    def _tr_excluir(self):
        import transportadoras as tr                     # noqa: PLC0415
        if not self.tr_atual:
            return
        if not messagebox.askyesno("Transportadoras",
                                   f"Excluir {self.tr_atual} da lista?",
                                   parent=self):
            return
        dados = dict(self.tr_dados, transportadoras=[
            x for x in self.tr_dados["transportadoras"]
            if x["nome"] != self.tr_atual])
        try:
            tr.salvar(dados, AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Transportadoras", str(erro), parent=self)
            return
        self.tr_dados = dados
        self._tr_pintar_lista()
        self._tr_nova()

    # ------------------------------------------------ resumo indicadores
    def _painel_resumo(self, q):
        """A visao geral do mes, com os cartoes de cada area; o relatorio
        inteiro (abas por area, mes a mes, semana, dia) abre ao lado."""
        self._titulo(q, "Resumo indicadores", "Carregando…")
        sub = q.winfo_children()[-1]
        cartoes = tk.Frame(q, background=bv.FUNDO)
        cartoes.pack(fill="x", padx=30)
        botoes = tk.Frame(q, background=bv.FUNDO)
        botoes.pack(fill="x", padx=30, pady=16)
        ttk.Button(botoes, text="Abrir o Resumo indicadores",
                   style="Verde.TButton",
                   command=lambda: abrir_relatorio("an_resumo")).pack(
                       side="left")
        quadro = tk.Frame(q, background=bv.FUNDO)
        quadro.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        def trabalho():
            import relatorios_nucleo as rn               # noqa: PLC0415
            return rn.montar("an_resumo", AQUI)

        def pronto(rel):
            if not isinstance(rel, dict) or "_erro" in rel:
                sub.configure(text=f"Erro: {rel.get('_erro')}",
                              foreground=bv.VERMELHO)
                return
            t = rel["tabelas"][0]
            sub.configure(text=t["titulo"])
            for i, k in enumerate(rel["kpis"]):
                bv.cartao_kpi(cartoes, k["rotulo"], k["valor"], k["cor"],
                              k.get("detalhe", "")).grid(
                    row=i // 4, column=i % 4, sticky="nsew", padx=(0, 10),
                    pady=(0, 10))
            for j in range(4):
                cartoes.columnconfigure(j, weight=1, uniform="s")
            tab = bv.Tabela(quadro, t["colunas"], altura=18)
            tab.pack(fill="both", expand=True)
            tab.mostrar(t["linhas"], t["tons"], None)
        bv.em_segundo_plano(self, trabalho, pronto)

    # ------------------------------------------- (07/10) divergencias
    def _painel_divergencias(self, q):
        """(28/10, Alexandre) Divergencias clientes Planner x Protheus: o
        RELATORIO ja aberto aqui dentro (sem o botao Abrir o relatorio e sem
        o .json da base de clientes - esse fica so na Roteirizacao). O
        Exportar para correcao do relatorio tem o Excel do A1_VEND, o Excel
        dos clientes sem coordenada/endereco e o Importar preenchidos."""
        import bap_relatorios as br                     # noqa: PLC0415
        br.RelatorioNoQuadro(q, "an_divergencias").pack(fill="both",
                                                        expand=True)

    # --------------------------------------------------------- saldo
    def _painel_saldo(self, q):
        self._titulo(q, "Farol de Saldo", "Carregando…")
        sub = q.winfo_children()[-1]
        cartoes = tk.Frame(q, background=bv.FUNDO)
        cartoes.pack(fill="x", padx=30)
        botoes = tk.Frame(q, background=bv.FUNDO)
        botoes.pack(fill="x", padx=30, pady=16)
        ttk.Button(botoes, text="Acompanhar pedido a pedido",
                   style="Verde.TButton",
                   command=lambda: abrir_relatorio("vc_saldo")).pack(
                       side="left")

        def trabalho():
            import relatorios_nucleo as rn               # noqa: PLC0415
            return rn.montar("vc_saldo", AQUI)

        def pronto(rel):
            if not isinstance(rel, dict) or "_erro" in rel:
                sub.configure(text=f"Erro: {rel.get('_erro')}",
                              foreground=bv.VERMELHO)
                return
            sub.configure(text=f"{rel['subtitulo']} · mês atual")
            for i, k in enumerate(rel["kpis"]):
                bv.cartao_kpi(cartoes, k["rotulo"], k["valor"], k["cor"],
                              k.get("detalhe", "")).grid(
                    row=i // 3, column=i % 3, sticky="nsew", padx=(0, 10),
                    pady=(0, 10))
            for j in range(3):
                cartoes.columnconfigure(j, weight=1, uniform="s")
        bv.em_segundo_plano(self, trabalho, pronto)

def abrir_relatorio(rid):
    subprocess.Popen([sys.executable, str(AQUI / "bap_relatorios.py"), rid],
                     cwd=str(AQUI))


def main():
    Analista().mainloop()


if __name__ == "__main__":
    main()
