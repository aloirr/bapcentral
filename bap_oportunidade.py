# -*- coding: utf-8 -*-
"""
OPORTUNIDADES BAP - a tela.

Tres abas, duas perguntas e um lugar para mexer nas regras:

    1. OPORTUNIDADE DE CLIENTE ... a quem ir atras: limite parado, quem
       parou de comprar, quem tem titulo vencido, o que comprou por
       ultimo, telefone e endereco. A BASE_CLIENTE que alimenta tudo
       isso e refeita pela Automacao BAP no fim de cada rodada; este
       programa so LE. Para pegar a base mais nova, feche e abra.

    2. OPORTUNIDADE DE ESTOQUE ..... o que empurrar: estoque por regiao,
       preco de capital e de interior, e as duas curvas do produto -
       CURVA FILIAL e CURVA GERAL. O item que gira na rede e esta parado
       na filial e a oportunidade que salta aos olhos.

    3. PARAMETROS .................. os cortes da curva do produto e qual
       tabela de preco e capital e qual e interior.
"""
from __future__ import annotations

import datetime as dt
import math
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
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

try:
    import tkinter as tk
    from tkinter import messagebox, ttk

    import bap_planner as bp
    import familia_nucleo as fam
    import meta_nucleo as mn
    import oportunidade_nucleo as on
    import pastas_bap as pb
except Exception:                                        # noqa: BLE001
    rastro = traceback.format_exc()
    print("O Oportunidades BAP nao conseguiu iniciar.\n")
    print(rastro)
    try:
        (AQUI / "erro_oportunidade.txt").write_text(rastro, encoding="utf-8")
    except OSError:
        pass
    raise SystemExit(1)

ARQ_PARAMETROS = AQUI / "oportunidade_config.json"

COR_FUNDO = bp.COR_FUNDO
COR_PAPEL = bp.COR_PAPEL
COR_TITULO = bp.COR_TITULO
COR_SUAVE = bp.COR_SUAVE
COR_TEXTO = bp.COR_TEXTO
COR_LINHA = bp.COR_LINHA
COR_ALERTA = bp.COR_ALERTA
COR_OK = bp.COR_OK
COR_AVISO = bp.COR_AVISO
COR_ACENTO = bp.COR_ACENTO


def dinheiro(v) -> str:
    return bp.dinheiro(v)


def numero_br(v, casas=0) -> str:
    try:
        return f"{float(v):,.{casas}f}".replace(",", "~") \
            .replace(".", ",").replace("~", ".")
    except (TypeError, ValueError):
        return ""


def inteiro(v) -> int:
    try:
        return int(math.ceil(float(v or 0)))
    except (TypeError, ValueError):
        return 0


# ==========================================================================

NOMES_DAS_ABAS = ("Clientes", "Analítico da rota", "Estoque",
                  "Mix de produtos", "Cliente por família",
                  "Sugestão de kits", "Parâmetros")

class Oportunidades(pb.base_da_janela()):

    # a mesma lista da antiga aba CLIENTE do Gerador de Meta
    # A MESMA ORDEM do Excel da base: onde o cliente fica, quem ele e,
    # como falar com ele, quanto pode comprar e o que levou da ultima vez.
    # quantos filtros cabem numa fileira sem estourar a janela
    FLAGS_POR_FILEIRA = 5

    # os dois jeitos de puxar a oportunidade pela peca
    MODO_FAM_NAO = "QUEM NAO COMPRA"
    MODO_FAM_SIM = "QUEM COMPRA"

    COLUNAS_CLI = [
        ("uf", "UF", 40, "center", False),
        ("cidade", "CIDADE", 140, "w", False),
        ("cod_cliente", "COD.", 96, "w", False),
        ("cliente", "RAZAO SOCIAL", 250, "w", True),
        ("fantasia", "NOME FANTASIA", 190, "w", False),
        ("segmento", "SEGMENTO", 170, "w", False),
        ("endereco", "ENDERECO", 220, "w", False),
        # BAIRRO antes do NUMERO: e assim que se le um endereco em voz
        # alta, e e assim que ele sai na folha impressa
        ("bairro", "BAIRRO", 150, "w", False),
        ("numero", "NUMERO", 66, "center", False),
        # DDD, TELEFONE, FONE e CONTATO eram quatro colunas dizendo quase
        # a mesma coisa. Viraram uma: o numero pronto para discar mais o
        # contato, quando ele acrescenta algo (ver _contato_completo)
        ("contato_completo", "CONTATO", 210, "w", False),
        ("limite_disponivel", "LIM. DISP. R$", 130, "e", False),
        ("ult_produto", "ULT. PRODUTO", 118, "w", False),
        ("ult_produto_nome", "ULT. COMPRA", 260, "w", False),
        ("ult_quantidade", "QTD", 60, "center", False),
        ("status_cliente", "STATUS", 110, "w", False),
        ("curva", "CURVA", 60, "center", False),
        ("dias_sem_compra", "DIAS SEM COMPRA", 120, "center", False),
        ("valor_em_atraso", "EM ATRASO R$", 118, "e", False),
        ("meta", "META R$", 118, "e", False),
        ("realizado", "REALIZADO R$", 118, "e", False),
        ("falta", "FALTA R$", 116, "e", False),
        ("cod_vendedor", "COD VD", 66, "center", False),
        ("vendedor", "VENDEDOR", 180, "w", False),
        # a ZONA fecha a lista: serve para conferir e filtrar, nao e o que
        # o vendedor le na rua
        ("cod_zona", "COD ZONA", 84, "w", False),
        ("zona", "ZONA", 190, "w", False),
        # A DATA DE CADASTRO fecha a lista: e ela que separa o cliente
        # NOVO que ainda nao comprou do cadastro antigo que nunca girou
        ("data_cadastro_txt", "DATA CADASTRO", 116, "center", False),
    ]

    COLUNAS_EST = [
        ("regiao", "REGIAO", 130, "w", False),
        ("produto", "PRODUTO", 150, "w", False),
        ("descricao", "DESCRICAO", 300, "w", True),
        ("familia", "FAMILIA", 130, "w", False),
        ("grupo", "GRUPO", 200, "w", False),
        ("linha", "LINHA", 90, "center", False),
        ("curva_filial", "CURVA FILIAL", 100, "center", False),
        ("curva_geral", "CURVA GERAL", 100, "center", False),
        ("estoque", "ESTOQUE", 88, "center", False),
        ("disponivel", "DISPONIVEL", 96, "center", False),
        ("custo", "CUSTO (CD) R$", 120, "e", False),
        ("markup_capital", "% MARKUP CAPITAL", 138, "center", False),
        ("markup_interior", "% MARKUP INTERIOR", 142, "center", False),
        ("preco_capital", "PRECO CAPITAL R$", 130, "e", False),
        ("preco_interior", "PRECO INTERIOR R$", 132, "e", False),
        ("valor_estoque", "ESTOQUE EM R$", 128, "e", False),
        ("dias_sem_venda_filial", "DIAS S/ VENDA (FILIAL)", 150, "center",
         False),
        ("dias_sem_venda_geral", "DIAS S/ VENDA (GERAL)", 146, "center",
         False),
        ("qtd_vendida_filial", "VENDIDO NA FILIAL", 130, "center", False),
        ("qtd_vendida_geral", "VENDIDO NA REDE", 126, "center", False),
        ("filial", "COD FILIAL", 100, "w", False),
    ]

    # ---- a sugestao de kits --------------------------------------------
    # A MESMA escada do Excel: TABELA -> VENDA (so os 15% do gerente) ->
    # ACAO (com o desconto todo). O que a verba paga e a diferenca entre
    # os dois ultimos, e o ROI e o que entra menos o que ela pagou.
    # Os titulos sao curtos DE PROPOSITO: a regra e caber tudo numa tela
    # so, sem rolagem lateral. O nome comprido do kit virou CODIGO
    # (K-filial-mes-dia-sequencia); a categoria e a familia, que diziam a
    # mesma coisa que o nome, ja estao nas colunas ao lado.
    # AS COLUNAS DO KIT NA TELA sao as MESMAS do Excel e as MESMAS no
    # resumo e no detalhe - o que muda e so o que a linha e (um KIT
    # inteiro em cima, um PRODUTO embaixo). Tudo o que e dinheiro ja sai
    # multiplicado pela QTD; percentual nao multiplica nada.
    # As larguras somam ~1440 DE PROPOSITO: o RESUMO e a folha que o
    # diretor le, e ela tem de caber numa tela de 1480 sem rolagem
    # lateral. O detalhamento, com o nome do produto, rola - e ali tudo
    # bem, porque quem desce ate o item ja sabe o que esta procurando.
    # O MKP KIT saiu: ele e o MESMO numero do MKP TT %, porque markup em
    # percentual nao muda quando se multiplica pela quantidade. Duas
    # colunas iguais lado a lado so fazem o leitor procurar a diferenca.
    COLUNAS_KIT_VALOR_TELA = [
        ("quantidade", "QTD", 52, "center", False),
        ("custo_total", "P. PEDIDO", 100, "e", False),
        ("valor_tabela", "VLR TAB. C/ 15%", 120, "e", False),
        ("custo_por_kit", "DESC. R$", 88, "e", False),
        ("desconto", "DESC. %", 70, "center", False),
        ("valor_acao", "VLR KIT", 92, "e", False),
        ("kits_liberados_txt", "QTD KITS", 78, "center", False),
        ("valor_kit_total", "VLR TOTAL", 104, "e", False),
        ("custo_liberado", "INVEST. R$", 122, "e", False),
        ("roi_previsto", "MKP TT R$", 94, "e", False),
        ("markup_tt_pct", "MKP TT %", 78, "center", False),
        ("roi_pct", "ROI %", 68, "center", False),
    ]

    COLUNAS_RES = ([
        ("kit", "KIT", 112, "w", False),
        ("regiao", "FILIAL", 66, "w", True),
        ("rotulo", "CATEGORIA", 72, "w", False),
    ] + COLUNAS_KIT_VALOR_TELA)

    # No DETALHE entra o VLR UNIT.: quanto UMA unidade daquele item custa
    # dentro do kit. Ele fica LOGO ANTES do VLR KIT porque e dali que o
    # VLR KIT sai, e a linha passa a se ler em sequencia:
    #
    #   P. PEDIDO -> VLR TAB. C/ 15% -> DESC. R$ -> DESC. % -> VLR UNIT.
    #   -> VLR KIT (= VLR UNIT. x QTD) -> QTD KITS -> VLR TOTAL
    #
    # A QTD KITS ali e o numero, nao o texto "SEM LIMITE".
    COLUNAS_DET = ([
        ("kit", "KIT", 112, "w", False),
        ("regiao", "FILIAL", 66, "w", False),
        ("produto", "COD. PRODUTO", 92, "w", False),
        ("descricao", "DESCRICAO", 180, "w", True),
    ] + [x for c, t_, l, a, cr in COLUNAS_KIT_VALOR_TELA
         for x in ((("preco_final", "VLR UNIT.", 92, "e", False),)
                   if c == "valor_acao" else ())
         + ((c if c != "kits_liberados_txt" else "kits_liberados",
             t_, l, a, cr),)])

    def __init__(self):
        super().__init__()
        self.title("Oportunidades BAP")
        self.geometry("1480x960")
        self.minsize(1100, 700)
        self.configure(bg=COR_FUNDO)
        bp.App._estilo(self)

        try:
            pb.arrumar(AQUI)
        except OSError:
            pass

        self.par = on.carregar_parametros(ARQ_PARAMETROS)
        self.oportunidade = None      # a base de cliente
        self.competencia = ""         # o mes da base carregada
        self.resumo_base = None       # o painel da base de clientes
        self.estoque = None           # a base de estoque
        self.mix = None               # o mix disponivel x positivado
        self.compras = None           # o que cada cliente comprou, por familia
        # a janela do historico e UMA so para as abas 1 e 5: as duas leem
        # a mesma passada pela ftPedidos, entao nao faz sentido cada uma
        # ter o seu periodo
        self.var_fam_dias = tk.StringVar(value=str(
            on.DIAS_DO_HISTORICO_PADRAO))
        self.kits = None              # os kits sugeridos
        self.visitas = None           # a agenda lida do PLANNER
        self.categorias = {}          # produto -> categoria do kit
        self._silencio = False

        raiz = ttk.Frame(self, style="Fundo.TFrame", padding=(14, 12))
        raiz.pack(fill="both", expand=True)
        self._cabecalho(raiz)
        self.abas = ttk.Notebook(raiz)
        self.abas.pack(fill="both", expand=True, pady=(10, 0))
        self.aba_cli = ttk.Frame(self.abas, padding=14)
        self.aba_rota = ttk.Frame(self.abas, padding=14)
        self.aba_est = ttk.Frame(self.abas, padding=14)
        self.aba_mix = ttk.Frame(self.abas, padding=14)
        self.aba_fam = ttk.Frame(self.abas, padding=14)
        self.aba_kit = ttk.Frame(self.abas, padding=14)
        self.aba_par = ttk.Frame(self.abas, padding=16)
        for aba, nome in zip((self.aba_cli, self.aba_rota, self.aba_est,
                              self.aba_mix, self.aba_fam, self.aba_kit,
                              self.aba_par), NOMES_DAS_ABAS):
            self.abas.add(aba, text=nome)

        self._montar_cliente()
        self._montar_rota()
        self._montar_estoque()
        self._montar_mix()
        self._montar_familia()
        self._montar_kits()
        self._montar_parametros()
        self._mostrar_so_as_abas()
        self.rodape = ttk.Label(raiz, text="", style="Sub.TLabel")
        self.rodape.pack(anchor="w", pady=(8, 0))
        self.after(80, self._abertura)

    # AS ABAS QUE APARECEM. Clientes, rota, estoque, mix e familia ja estao
    # nos farois (Clientes, Roteirizacao, Giro, Estoque FRW). Aqui ficam os
    # KITS PROMOCIONAIS: no BAP Analista so os parametros (cadastro); no
    # quadrado do Analista da Central, a sugestao de kits (gerar os kits).
    # As outras abas continuam montadas por baixo: os kits usam o que elas
    # carregam (estoque, mix, agenda).
    ABAS_VISIVEIS = ("par",)
    TITULO = "Kits promocionais"

    def _mostrar_so_as_abas(self):
        todas = {"cli": self.aba_cli, "rota": self.aba_rota,
                 "est": self.aba_est, "mix": self.aba_mix,
                 "fam": self.aba_fam, "kit": self.aba_kit,
                 "par": self.aba_par}
        if self.ABAS_VISIVEIS is None:
            return
        for chave, aba in todas.items():
            if chave not in self.ABAS_VISIVEIS:
                self.abas.hide(aba)
        self.abas.select(todas[self.ABAS_VISIVEIS[0]])

    # ---------------------------------------------------------------- topo
    def _cabecalho(self, pai):
        barra = tk.Frame(pai, background=bp.COR_CABECALHO)
        barra.pack(fill="x")
        tk.Frame(pai, background="#62BB47", height=3).pack(fill="x")
        tk.Label(barra, text=self.TITULO, background=bp.COR_CABECALHO,
                 foreground=bp.COR_TEXTO, font=(self.FONTE, 15, "bold"),
                 padx=16, pady=12).pack(side="left")
        self.lbl_topo = tk.Label(barra, text="", background=bp.COR_CABECALHO,
                                 foreground=bp.COR_SUAVE, font=(self.FONTE, 9),
                                 padx=10)
        self.lbl_topo.pack(side="left")

    def aviso(self, texto, cor=COR_SUAVE):
        self.rodape.configure(text=texto, foreground=cor)
        self.rodape.update_idletasks()

    # ================================================================== 1
    def _montar_cliente(self):
        f = self.aba_cli
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Oportunidade de cliente",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="EXPORTAR BASE DE CLIENTE",
                   style="Big.TButton",
                   command=self.exportar_cliente).pack(side="right")
        ttk.Button(topo, text="GERAR PDF DA LISTA",
                   style="Big.TButton",
                   command=self.imprimir_cliente).pack(side="right", padx=8)
        ttk.Button(topo, text="RECARREGAR", style="Big.TButton",
                   command=self.carregar_cliente).pack(side="right")

        ttk.Label(f, text="A quem ir atras: limite parado, quem deixou de "
                          "comprar, titulo vencido, o ultimo item que levou "
                          "e onde ele fica. A BASE_CLIENTE e refeita pela "
                          "Automacao BAP no fim de cada rodada - para pegar "
                          "a mais nova, feche e abra este programa.",
                  style="Sub.TLabel", wraplength=1350).pack(anchor="w",
                                                            pady=(4, 10))

        # DUAS SUB-ABAS: o painel da base inteira (o mesmo da RRM) e a
        # lista de clientes que o vendedor leva para a rua. Cada uma cabe
        # numa tela so, para printar.
        self.abas_cli = ttk.Notebook(f)
        self.abas_cli.pack(fill="both", expand=True)
        q_resumo = ttk.Frame(self.abas_cli, padding=10)
        q_lista = ttk.Frame(self.abas_cli, padding=10)
        self.abas_cli.add(q_resumo, text="RESUMO GERENCIAL | BASE DE CLIENTES")
        self.abas_cli.add(q_lista, text="LISTA DE CLIENTES")

        barra = ttk.Frame(q_lista)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Ver por:").pack(side="left")
        self.var_recorte = tk.StringVar(value="ZONA")
        cb = ttk.Combobox(barra, textvariable=self.var_recorte, width=12,
                          state="readonly",
                          values=[mn.TITULO_DO_RECORTE[r]
                                  for r in mn.RECORTES_FILTRO])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _: self._encher_alvos())
        self.var_alvo = tk.StringVar(value=mn.TODOS)
        self.cb_alvo = ttk.Combobox(barra, textvariable=self.var_alvo,
                                    width=42, state="readonly",
                                    values=[mn.TODOS])
        self.cb_alvo.pack(side="left", padx=6)
        self.cb_alvo.bind("<<ComboboxSelected>>",
                          lambda _: self._desenhar_cliente())
        ttk.Button(barra, text="Limpar filtros",
                   command=self._limpar_cliente).pack(side="left", padx=6)

        # OS FILTROS EM DUAS FILEIRAS: numa so, os rotulos compridos
        # empurravam os ultimos para fora da janela em tela menor. A
        # quebra e automatica - acrescentar um filtro novo na lista
        # FLAGS nao exige mexer aqui.
        flags = ttk.Frame(q_lista)
        flags.pack(fill="x", pady=(0, 8))
        self.var_flag = {}
        fileira = None
        for i, (chave, rotulo) in enumerate(mn.FLAGS):
            if i % self.FLAGS_POR_FILEIRA == 0:
                fileira = ttk.Frame(flags)
                fileira.pack(fill="x", pady=(0, 2))
                ttk.Label(fileira,
                          text="So quem:" if i == 0 else "          ",
                          style="Sub.TLabel").pack(side="left", padx=(0, 6))
            v = tk.BooleanVar(value=False)
            self.var_flag[chave] = v
            ttk.Checkbutton(fileira, text=rotulo, variable=v,
                            command=self._desenhar_cliente).pack(
                                side="left", padx=(0, 12))

        # PUXAR A OPORTUNIDADE PELA PECA. As caixas de cima olham o
        # CLIENTE (limite, atraso, dias sem compra); esta fileira olha o
        # que ele COMPRA. Sao perguntas diferentes e se somam: "cliente
        # com limite, adimplente, que nunca levou FREIO" e uma lista
        # curta e boa de levar para a rua.
        #
        # Ela le a nota item a item (ftPedidos), que e uma leitura cara -
        # por isso so acontece quando se escolhe uma familia de verdade.
        fam_bar = ttk.Frame(q_lista)
        fam_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(fam_bar, text="Pela peca:",
                  style="Sub.TLabel").pack(side="left", padx=(0, 6))
        self.var_modo_fam_cli = tk.StringVar(value=self.MODO_FAM_NAO)
        cbm = ttk.Combobox(fam_bar, textvariable=self.var_modo_fam_cli,
                           width=16, state="readonly",
                           values=[self.MODO_FAM_NAO, self.MODO_FAM_SIM])
        cbm.pack(side="left", padx=(0, 6))
        cbm.bind("<<ComboboxSelected>>", lambda _: self._desenhar_cliente())
        ttk.Label(fam_bar, text="a familia:").pack(side="left")
        self.var_fam_cli = tk.StringVar(value=mn.TODOS)
        self.cb_fam_cli = ttk.Combobox(fam_bar, textvariable=self.var_fam_cli,
                                       width=20, state="readonly",
                                       values=[mn.TODOS]
                                       + fam.ORDEM_FAMILIA)
        self.cb_fam_cli.pack(side="left", padx=6)
        self.cb_fam_cli.bind("<<ComboboxSelected>>",
                             lambda _: self._familia_do_cliente_mudou())
        ttk.Label(fam_bar, text="   ou o grupo:").pack(side="left")
        self.var_gru_cli = tk.StringVar(value=mn.TODOS)
        self.cb_gru_cli = ttk.Combobox(fam_bar, textvariable=self.var_gru_cli,
                                       width=32, state="readonly",
                                       values=[mn.TODOS])
        self.cb_gru_cli.pack(side="left", padx=6)
        self.cb_gru_cli.bind("<<ComboboxSelected>>",
                             lambda _: self._carregar_compras_e_desenhar())
        ttk.Label(fam_bar, text="   olhando os ultimos:").pack(side="left")
        cbd = ttk.Combobox(fam_bar, textvariable=self.var_fam_dias, width=6,
                           state="readonly",
                           values=[str(d) for d in on.DIAS_DO_HISTORICO])
        cbd.pack(side="left", padx=6)
        cbd.bind("<<ComboboxSelected>>", lambda _: self._periodo_fam_mudou())
        ttk.Label(fam_bar, text="dias",
                  style="Sub.TLabel").pack(side="left")

        quadro, self.tab_cli = bp.tabela(q_lista, self.COLUNAS_CLI,
                                         rodape=True)
        quadro.pack(fill="both", expand=True)
        self.tab_cli.tag_configure("bateu", background="#E4F3E9")
        self.tab_cli.tag_configure("semlimite", background="#F6E7E7")
        self.lbl_cli = ttk.Label(q_lista, text="", style="Sub.TLabel",
                                 wraplength=1350)
        self.lbl_cli.pack(anchor="w", pady=(6, 0))
        self._montar_resumo_base(q_resumo)

    # ---- o RESUMO GERENCIAL da base de clientes -------------------------
    # As cores dos cartoes sao as do painel que vai para a RRM, para a
    # tela e o slide serem a mesma coisa.
    CARTOES_DA_BASE = [
        ("clientes", "TOTAL CLIENTES", "#12797E", False),
        ("com_limite", "COM LIMITE", "#4E9A3E", False),
        ("inadimplentes", "INADIMPLENTES", "#C62828", False),
        ("limite_sem_compra", "LIMITE SEM COMPRA", "#E07B18", False),
        ("limite_parado", "LIMITE PARADO R$", "#2F7D32", True),
    ]
    COR_CURVA = "#6B3FA0"

    COLUNAS_BASE_TELA = [
        ("rotulo", "RECORTE", 190, "w", True),
        ("codigo", "CODIGO", 92, "w", False),
        ("clientes", "TOTAL CLI.", 88, "center", True),
        ("curva_S", "S", 46, "center", True),
        ("curva_A", "A", 46, "center", True),
        ("curva_B", "B", 46, "center", True),
        ("curva_C", "C", 50, "center", True),
        ("curva_Z", "Z", 62, "center", True),
        ("com_limite", "COM LIMITE", 92, "center", True),
        ("inadimplentes", "INADIMPL.", 84, "center", True),
        ("pct_inadimplentes", "% INAD.", 74, "center", True),
        ("em_atraso", "EM ATRASO R$", 112, "e", True),
        ("limite_sem_compra", "LIMITE S/ COMPRA", 128, "center", True),
        ("limite_parado", "LIMITE PARADO R$", 130, "e", True),
        ("positivados", "POSIT.", 66, "center", True),
        ("pct_positivados", "% POSIT.", 78, "center", True),
        ("sem_compra_90", "SEM COMPRA 90+", 116, "center", True),
    ]

    def _cartao(self, pai, titulo, cor):
        """Um cartao do painel: rotulo pequeno e o numero (a cor do numero
        e a mesma do painel da RRM)."""
        quadro = tk.Frame(pai, background="#FFFFFF",
                          highlightbackground=COR_LINHA, highlightthickness=1)
        tk.Label(quadro, text=titulo.capitalize().replace(" r$", " (R$)"),
                 background="#FFFFFF",
                 foreground=COR_SUAVE, font=(self.FONTE, 9),
                 anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        valor = tk.Label(quadro, text="-", background="#FFFFFF",
                         foreground=cor, font=(self.FONTE, 19, "bold"),
                         anchor="w")
        valor.pack(fill="x", padx=14, pady=(0, 10))
        return quadro, valor

    def _montar_resumo_base(self, f):
        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 10))
        ttk.Label(barra, text="Detalhar por:").pack(side="left")
        self.var_base_rec = tk.StringVar(value="UF")
        cb = ttk.Combobox(barra, textvariable=self.var_base_rec, width=14,
                          state="readonly",
                          values=[mn.TITULO_DO_RECORTE.get(r, r.upper())
                                  for r in mn.RECORTES_DA_BASE])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _: self._desenhar_resumo_base())
        ttk.Button(barra, text="EXPORTAR RESUMO", style="Big.TButton",
                   command=self.exportar_resumo_base).pack(side="right")
        ttk.Label(barra, text="Base inteira (não segue os filtros da lista)",
                  style="Sub.TLabel").pack(side="left", padx=(12, 0))

        # ---- os cartoes ---------------------------------------------------
        cartoes = tk.Frame(f, background=COR_FUNDO)
        cartoes.pack(fill="x", pady=(0, 10))
        self.lbl_cartao = {}
        for i, (chave, titulo, cor, _dinheiro) in enumerate(
                self.CARTOES_DA_BASE):
            quadro, valor = self._cartao(cartoes, titulo, cor)
            quadro.grid(row=0, column=i, sticky="we", padx=(0, 10))
            cartoes.columnconfigure(i, weight=1)
            self.lbl_cartao[chave] = valor

        # ---- a distribuicao por curva ------------------------------------
        faixa = tk.Frame(f, background=COR_FUNDO)
        faixa.pack(fill="x", pady=(0, 10))
        tk.Label(faixa, text="Distribuição por curva", background=COR_FUNDO,
                 foreground=COR_TEXTO, font=(self.FONTE, 10, "bold"),
                 pady=2).pack(anchor="w")
        linha_c = tk.Frame(faixa, background=COR_FUNDO)
        linha_c.pack(anchor="w", pady=(2, 0))
        self.lbl_curva_base = {}
        for i, letra in enumerate(mn.CURVAS_DA_BASE):
            tk.Label(linha_c, text=f"Curva {letra}", background="#FFFFFF",
                     foreground=COR_SUAVE, font=(self.FONTE, 8),
                     width=12, pady=3).grid(row=0, column=i, padx=(0, 6))
            v = tk.Label(linha_c, text="-", background="#FFFFFF",
                         foreground=COR_TEXTO, font=(self.FONTE, 12, "bold"),
                         width=12, pady=3)
            v.grid(row=1, column=i, padx=(0, 6))
            self.lbl_curva_base[letra] = v

        # ---- o detalhamento ----------------------------------------------
        self.lbl_base_titulo = tk.Label(
            f, text="Detalhamento por UF", background=COR_FUNDO,
            foreground=COR_TEXTO, font=(self.FONTE, 10, "bold"), pady=2,
            anchor="w")
        self.lbl_base_titulo.pack(fill="x")
        # a tabela acompanha a quantidade de linhas, em vez de esticar
        # sempre: com duas linhas de supervisor, um painel vazio entre a
        # ultima linha e o TOTAL nao ajuda ninguem a printar
        quadro, self.tab_base = bp.tabela(f, self.COLUNAS_BASE_TELA,
                                          altura=6, rodape=True,
                                          horizontal=False)
        quadro.pack(fill="x", pady=(2, 0))
        self.lbl_base = ttk.Label(f, text="", style="Sub.TLabel",
                                  wraplength=1400)
        self.lbl_base.pack(anchor="w", pady=(6, 0))

    def _recorte_da_base(self) -> str:
        escolhido = self.var_base_rec.get()
        for r in mn.RECORTES_DA_BASE:
            if mn.TITULO_DO_RECORTE.get(r, r.upper()) == escolhido:
                return r
        return "uf"

    def _valores_base(self, linha):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_BASE_TELA:
            v = linha.get(chave)
            if chave in ("limite_parado", "em_atraso"):
                saida.append(dinheiro(v) if v else "")
            elif chave.startswith("pct_"):
                saida.append(f"{numero_br(v, 1)}%")
            elif chave in ("rotulo", "codigo"):
                saida.append(v or "")
            else:
                saida.append(numero_br(v))
        return saida

    def _desenhar_resumo_base(self):
        if not self.oportunidade:
            return
        recorte = self._recorte_da_base()
        self.resumo_base = mn.resumo_da_base(self.oportunidade, recorte)
        t = self.resumo_base["total"]
        for chave, _, _, e_dinheiro in self.CARTOES_DA_BASE:
            self.lbl_cartao[chave].configure(
                text=dinheiro(t.get(chave)) if e_dinheiro
                else numero_br(t.get(chave)))
        for letra in mn.CURVAS_DA_BASE:
            self.lbl_curva_base[letra].configure(
                text=numero_br(t.get(f"curva_{letra}")))
        titulo = self.resumo_base["titulo"]
        self.lbl_base_titulo.configure(text=f"Detalhamento por {titulo}")
        self.tab_base.heading("rotulo", text=titulo)
        linhas = self.resumo_base["linhas"]
        t_tab = self.tab_base
        # CODIGO so existe em ZONA, VENDEDOR, SUPERVISOR e GERENTE. Em UF,
        # CIDADE e BAIRRO a coluna sairia vazia linha a linha: ela some e
        # devolve a largura para as outras.
        chaves = [c[0] for c in self.COLUNAS_BASE_TELA]
        if not any(l.get("codigo") for l in linhas):
            chaves = [c for c in chaves if c != "codigo"]
        t_tab.configure(displaycolumns=chaves)
        pe = getattr(t_tab, "_rodape", None)
        if pe is not None:
            pe.configure(displaycolumns=chaves)
        self._silencio = True
        try:
            t_tab.delete(*t_tab.get_children())
            for i, l in enumerate(linhas):
                t_tab.insert("", "end", iid=f"{l['rotulo']}|{i}",
                             tags=("zebra",) if i % 2 else (),
                             values=self._valores_base(l))
            bp.escrever_total(t_tab, self._valores_base(
                {**t, "rotulo": "TOTAL", "codigo": ""}))
            t_tab.configure(height=max(4, min(len(linhas),
                                              self.TETO_DE_LINHAS)))
        finally:
            self._silencio = False
        self.lbl_base.configure(
            text=f"{len(linhas)} linhas · competência "
                 f"{self.competencia or '-'}",
            foreground=COR_SUAVE)

    def exportar_resumo_base(self):
        if not self.oportunidade:
            messagebox.showinfo("Oportunidades BAP",
                                "Carregue a base de cliente primeiro.")
            return
        destino = (AQUI / pb.RELATORIOS /
                   mn.nome_do_resumo_da_base())
        try:
            mn.gravar_excel_resumo_da_base(self.oportunidade, destino,
                                           self.competencia or "")
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado.", COR_OK)
        messagebox.showinfo(
            "Oportunidades BAP",
            f"{destino.name}\n\nUma aba por recorte - UF, CIDADE, ZONA, "
            f"BAIRRO, SUPERVISOR, VENDEDOR e GERENTE - mais a COMO_LER.\n\n"
            f"Gravado em:\n{destino.parent}")

    def _recorte(self) -> str:
        titulo = self.var_recorte.get()
        for r in mn.RECORTES_FILTRO:
            if mn.TITULO_DO_RECORTE[r] == titulo:
                return r
        return "zona"

    def _encher_alvos(self):
        alvos = mn.alvos_do_recorte(self.oportunidade or [], self._recorte())
        self.cb_alvo.configure(values=alvos)
        self.var_alvo.set(mn.TODOS)
        self._desenhar_cliente()
        self._desenhar_resumo_base()

    def _limpar_cliente_peca(self):
        """A fileira da peca volta ao neutro junto com o resto."""
        self.var_fam_cli.set(mn.TODOS)
        self.var_gru_cli.set(mn.TODOS)
        self.var_modo_fam_cli.set(self.MODO_FAM_NAO)
        self.cb_gru_cli.configure(values=[mn.TODOS])

    def _limpar_cliente(self):
        for v in self.var_flag.values():
            v.set(False)
        self.var_alvo.set(mn.TODOS)
        self._limpar_cliente_peca()
        self._desenhar_cliente()

    def _lista_cliente(self) -> list:
        alvo = self.var_alvo.get()
        if alvo != mn.TODOS and " - " in alvo:
            alvo = alvo.split(" - ", 1)[1]
        linhas = mn.filtrar_oportunidade(
            self.oportunidade or [], self._recorte(), alvo,
            {k: v.get() for k, v in self.var_flag.items()})
        return self._filtrar_pela_peca(linhas)

    def _familia_do_cliente_mudou(self):
        """Escolhida a familia, o GRUPO passa a listar so os dela."""
        familia = self.var_fam_cli.get()
        grupos = [g for g in fam.ORDEM_GRUPO
                  if familia == mn.TODOS
                  or fam.FAMILIA_DO_GRUPO.get(g) == familia]
        self.cb_gru_cli.configure(values=[mn.TODOS] + grupos)
        if self.var_gru_cli.get() not in grupos:
            self.var_gru_cli.set(mn.TODOS)
        self._carregar_compras_e_desenhar()

    def _periodo_fam_mudou(self):
        """Trocou a janela: a leitura anterior nao serve mais."""
        self.compras = None
        self._carregar_compras_e_desenhar()

    def _carregar_compras_e_desenhar(self):
        """
        Le a nota item a item SO QUANDO PRECISA. Sem familia nem grupo
        escolhido, a aba 1 nao usa esse dado e nao vale gastar os
        segundos de leitura.
        """
        if self._quer_peca() and not self._compras_prontas():
            return                        # nao deu para ler: avisa e sai
        self._desenhar_cliente()

    def _quer_peca(self) -> bool:
        return (self.var_fam_cli.get() != mn.TODOS
                or self.var_gru_cli.get() != mn.TODOS)

    def _compras_prontas(self) -> bool:
        """Garante a leitura da ftPedidos, na janela escolhida."""
        dias = int(on._numero(self.var_fam_dias.get())
                   or on.DIAS_DO_HISTORICO_PADRAO)
        if self.compras and self.compras.get("dias") == dias:
            return True
        tabela = on.achar_tabela(AQUI)
        if tabela is None:
            messagebox.showwarning(
                "Oportunidades BAP",
                f"Para filtrar pela peca eu preciso da "
                f"{on.ARQUIVO_TABELA} em {pb.RELATORIOS} - e dela que sai "
                f"o que cada cliente comprou, item a item.")
            self.var_fam_cli.set(mn.TODOS)
            self.var_gru_cli.set(mn.TODOS)
            return False
        self.aviso(f"Lendo a venda item a item dos ultimos {dias} dias "
                   f"para saber quem compra o que...", COR_SUAVE)
        self.update_idletasks()
        try:
            self.compras = on.compras_por_familia(tabela, dias=dias)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.var_fam_cli.set(mn.TODOS)
            self.var_gru_cli.set(mn.TODOS)
            return False
        self.aviso(f"{self.compras['linhas']} item(ns) de nota lido(s) em "
                   f"{len(self.compras['clientes'])} cliente(s).", COR_OK)
        return True

    def _filtrar_pela_peca(self, linhas: list) -> list:
        """
        Deixa so quem compra (ou so quem NAO compra) a familia ou o
        grupo escolhido, no periodo escolhido.
        """
        if not self._quer_peca() or not self.compras:
            return linhas
        grupo = "" if self.var_gru_cli.get() == mn.TODOS \
            else self.var_gru_cli.get()
        familia = "" if self.var_fam_cli.get() == mn.TODOS \
            else self.var_fam_cli.get()
        onde = "grupos" if grupo else "familias"
        alvo = grupo or familia
        dados = self.compras.get("clientes") or {}
        quer_quem_compra = (self.var_modo_fam_cli.get() == self.MODO_FAM_SIM)
        saida = []
        for l in linhas:
            reg = dados.get(mn._texto(l.get("cod_cliente"))) or {}
            comprou = bool((reg.get(onde) or {}).get(alvo))
            if comprou == quer_quem_compra:
                saida.append(l)
        return saida

    def _recado_da_peca(self) -> str:
        """O que a fileira da peca esta fazendo, em uma linha."""
        if not self._quer_peca():
            return ""
        alvo = (self.var_gru_cli.get() if self.var_gru_cli.get() != mn.TODOS
                else self.var_fam_cli.get())
        dias = (self.compras or {}).get("dias", "?")
        return (f"{self.var_modo_fam_cli.get()} {alvo} "
                f"nos ultimos {dias} dias")

    def _na_ordem_da_tela(self, t, linhas: list, campo: str = "chave") -> list:
        """
        As linhas NA ORDEM EM QUE ESTAO NA TELA.

        Clicar no titulo de uma coluna reordena a tabela. O PDF e o
        Excel tem de sair do mesmo jeito que a pessoa deixou - senao ela
        organiza por CIDADE, manda imprimir, e a folha volta embaralhada.
        Quem nao estiver na tela (nao deveria acontecer) vai para o fim,
        em vez de sumir.
        """
        try:
            visiveis = [i for i in t.get_children("") if i != bp.LINHA_TOTAL]
        except tk.TclError:
            return linhas
        if not visiveis:
            return linhas
        ordem = {iid: i for i, iid in enumerate(visiveis)}
        fim = len(ordem)
        return sorted(linhas,
                      key=lambda l: ordem.get(str(l.get(campo, "")), fim))

    def _desenhar_cliente(self):
        if self.oportunidade is None:
            return
        linhas = self._lista_cliente()
        t = self.tab_cli
        self._silencio = True
        try:
            t.delete(*t.get_children())
            for i, l in enumerate(linhas):
                if l.get("limite_disponivel", 0.0) <= 0:
                    tags = ("semlimite",)
                elif l.get("meta") and l.get("atingimento", 0) >= 100:
                    tags = ("bateu",)
                else:
                    tags = ("zebra",) if i % 2 else ()
                t.insert("", "end", iid=l["chave"], tags=tags,
                         values=self._valores_cli(l))
            bp.escrever_total(t, self._valores_cli(
                mn._total_acompanhamento(linhas), total=True))
        finally:
            self._silencio = False
        limite = sum(l.get("limite_disponivel", 0.0) for l in linhas
                     if l.get("limite_disponivel", 0.0) > 0)
        atraso = sum(l.get("valor_em_atraso", 0.0) for l in linhas)
        self.lbl_cli.configure(
            text=f"{len(linhas)} cliente(s) de {len(self.oportunidade)}   |   "
                 f"limite disponivel somado {dinheiro(limite)}   |   em "
                 f"atraso {dinheiro(atraso)}   |   falta "
                 f"{dinheiro(sum(l.get('falta') or 0 for l in linhas))} para "
                 f"a meta deles.   Linha rosa = sem limite disponivel; "
                 f"verde = ja bateu a meta."
                 + (f"   |   PECA: {self._recado_da_peca()}"
                    if self._recado_da_peca() else ""))

    def _valores_cli(self, linha, total=False):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_CLI:
            v = linha.get(chave)
            if chave == "uf":
                saida.append("TOTAL" if total else v)
            elif chave == "cliente":
                saida.append("TOTAL DA LISTA" if total else v)
            elif chave in ("limite_disponivel", "valor_em_atraso", "meta",
                           "realizado", "falta"):
                saida.append(dinheiro(v))
            elif chave == "ult_quantidade":
                saida.append(numero_br(v) if v else "")
            elif chave == "data_cadastro_txt":
                d = linha.get("data_cadastro")
                saida.append(f"{d:%d/%m/%Y}" if d else "")
            elif total:
                saida.append("")
            else:
                saida.append(v)
        return saida

    # ---- carregar e atualizar a base de cliente -------------------------
    def carregar_cliente(self):
        """
        Monta a base de cliente: PLANNER (quem e de quem) + BASE_CLIENTE
        (limite, atraso, dias sem compra, telefone) + TABELA_BAP (o
        ultimo item e o faturamento do mes).
        """
        planner = pb.planner_mais_recente(AQUI)
        if planner is None:
            self.aviso("Nenhum PLANNER_BAP na pasta. Gere um no Planner BAP "
                       "para a base de oportunidade saber de quem e cada "
                       "cliente.", COR_ALERTA)
            return
        tabela = on.achar_tabela(AQUI)
        self.aviso("Montando a base de oportunidade...", COR_SUAVE)
        self.update_idletasks()
        # O CAMINHO RAPIDO: a base pronta do bap_dados (o BAP Tools a deixa
        # montada no fim de cada rodada). So refaz se a TABELA, a BASE, o
        # PLANNER ou a meta mudaram - e ai le a TABELA_BAP uma vez so.
        try:
            import bap_dados                             # noqa: PLC0415
            pronto = bap_dados.carregar(AQUI, "oportunidade")
            self.oportunidade = pronto["linhas"]
            self.competencia = pronto["competencia"]
            self.lbl_topo.configure(
                text=f"{pronto['planner']}   |   {len(self.oportunidade)} "
                     f"clientes   |   competencia {self.competencia}")
            self._encher_alvos()
            self.aviso(f"Base de oportunidade pronta: "
                       f"{len(self.oportunidade)} cliente(s).", COR_OK)
            return
        except Exception:                                # noqa: BLE001
            pass                    # cai no caminho antigo, logo abaixo
        try:
            dados = mn.ler_planner(planner)
            par_meta = mn.carregar_parametros(AQUI / "meta_config.json")
            resultado = mn.calcular(dados, par_meta)
            competencia = resultado["competencia"]
            realizado = {"clientes": {}, "competencia": competencia,
                         "sem_categoria": 0, "com_csv": False,
                         "notas": 0, "linhas": 0}
            csv_cat = mn.achar_csv_de_categorias(AQUI)
            nomes = mn.nomes_de_produto(csv_cat) if csv_cat else {}
            ultimo = {}
            if tabela:
                mapa = mn.mapa_de_categorias(tabela, {})
                realizado = mn.ler_realizado(
                    tabela, competencia, mapa,
                    mn.ler_categorias_de_produto(csv_cat) if csv_cat else {})
                ultimo = mn.ultimo_item_comprado(tabela, nomes)
            acomp = mn.acompanhar(resultado, realizado)
            cadastro = mn.ler_cadastro_do_cliente(
                mn._achar_base_cliente(AQUI))
            self.oportunidade = mn.montar_oportunidade(acomp, cadastro,
                                                       ultimo)
            self.competencia = competencia
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        self.lbl_topo.configure(
            text=f"{Path(planner).name}   |   {len(self.oportunidade)} "
                 f"clientes   |   competencia {competencia}")
        self._encher_alvos()
        self.aviso(f"Base de oportunidade pronta: "
                   f"{len(self.oportunidade)} cliente(s).", COR_OK)

    # O BOTAO "ATUALIZAR BASE DE CLIENTE" SAIU, e com ele o atualizar_base()
    # e o _esperar_base(). Este programa passou a so LER a BASE_CLIENTE.
    #
    # Quem a refaz e a Automacao BAP, no fim de cada rodada - para pegar a
    # base nova, fecha e abre. Tinha ficado estranho: a mesma base era
    # gerada em dois lugares, e a daqui rodava numa thread so para a
    # janela nao congelar durante os ~30 s. Um caminho so e menos coisa
    # para dar errado.

    # AS COLUNAS DA FOLHA IMPRESSA sao um recorte da tela: as que o
    # vendedor le na rua. A ORDEM delas nao e escrita aqui - ela e a da
    # COLUNAS_CLI, para a folha nunca mais poder discordar da tabela.
    # O tipo diz so como formatar (dinheiro com R$, data dd/mm/aaaa).
    # A chave e a coluna DA TELA; o valor diz com que nome, de que campo
    # e em que formato ela sai na folha. A coluna da tela guarda a data
    # ja escrita (data_cadastro_txt) e a folha usa a data de verdade,
    # porque e o _celula_impressa que formata la.
    NA_FOLHA = {
        "uf": ("UF", "uf", "texto"),
        "cidade": ("CIDADE", "cidade", "texto"),
        "cod_cliente": ("COD.", "cod_cliente", "texto"),
        "cliente": ("RAZAO SOCIAL", "cliente", "texto"),
        "fantasia": ("NOME FANTASIA", "fantasia", "texto"),
        "segmento": ("SEGMENTO", "segmento", "texto"),
        "endereco": ("ENDERECO", "endereco", "texto"),
        "bairro": ("BAIRRO", "bairro", "texto"),
        "numero": ("NUMERO", "numero", "texto"),
        "contato_completo": ("CONTATO", "contato_completo", "texto"),
        "limite_disponivel": ("LIM. DISP. R$", "limite_disponivel",
                              "dinheiro"),
        "curva": ("CURVA", "curva", "texto"),
        "data_cadastro_txt": ("CADASTRO", "data_cadastro", "data"),
    }

    def _colunas_da_folha(self) -> list:
        """
        As colunas da folha, na MESMA ordem em que estao na tela.

        A ordem NAO e escrita aqui: ela e lida da COLUNAS_CLI, para a
        folha impressa nunca mais poder discordar da tabela.
        """
        return [self.NA_FOLHA[chave]
                for chave, _, _, _, _ in self.COLUNAS_CLI
                if chave in self.NA_FOLHA]

    def _ordem_da_tela_txt(self) -> str:
        """Por qual coluna a tabela esta ordenada, para sair no cabecalho."""
        estado = getattr(self.tab_cli, "_ordem", None) or {}
        coluna = estado.get("coluna")
        if not coluna:
            return ""
        titulo = (getattr(self.tab_cli, "_titulos", {}) or {}).get(coluna,
                                                                  coluna)
        return f"{titulo} ({'maior primeiro' if estado.get('invertido') else 'menor primeiro'})"

    def exportar_cliente(self):
        if not self.oportunidade:
            messagebox.showinfo("Oportunidades BAP",
                                "A base ainda nao foi montada.")
            return
        linhas = self._na_ordem_da_tela(self.tab_cli, self._lista_cliente())
        alvo = self.var_alvo.get()
        marcadas = [r for c, r in mn.FLAGS if self.var_flag[c].get()]
        peca = self._recado_da_peca()
        titulo = (f"{mn.TITULO_DO_RECORTE[self._recorte()]}: {alvo}"
                  + (f"   |   {', '.join(marcadas)}" if marcadas else "")
                  + (f"   |   {peca}" if peca else ""))
        destino = (AQUI / pb.RELATORIOS /
                   mn.nome_da_base_de_oportunidade(
                       getattr(self, "competencia", "")))
        try:
            mn.gravar_excel_oportunidade(linhas, destino, titulo)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado com {len(linhas)} cliente(s).",
                   COR_OK)
        messagebox.showinfo(
            "Oportunidades BAP",
            f"{destino.name}\n\n{len(linhas)} cliente(s), com o filtro da "
            f"tela:\n{titulo}\n\nGravado em:\n{destino.parent}")

    def imprimir_cliente(self):
        """
        A lista filtrada numa folha A4 DEITADA, so com as colunas que o
        vendedor le na rua.

        Abre no NAVEGADOR, e nao gera o .pdf direto: assim nao e preciso
        instalar biblioteca nenhuma nos notebooks, e o Ctrl+P do proprio
        navegador salva em PDF com o papel ja no tamanho certo. A lista e
        cortada em paginas de verdade - cabecalho repetido em cada uma -
        em vez de virar uma pagina so com letra ilegivel.
        """
        if not self.oportunidade:
            messagebox.showinfo("Oportunidades BAP",
                                "A base ainda nao foi montada.")
            return
        # A ORDEM DA TELA MANDA: se a pessoa clicou em CIDADE e ordenou,
        # a folha sai ordenada por cidade. Antes o PDF saia na ordem
        # interna da base e nao conferia com o que estava na tela.
        linhas = self._na_ordem_da_tela(self.tab_cli, self._lista_cliente())
        if not linhas:
            messagebox.showinfo(
                "Oportunidades BAP",
                "Nenhum cliente neste filtro - nao ha o que imprimir.")
            return
        alvo = self.var_alvo.get()
        marcadas = [r for c, r in mn.FLAGS if self.var_flag[c].get()]
        peca = self._recado_da_peca()
        subtitulo = (f"{mn.TITULO_DO_RECORTE[self._recorte()]}: {alvo}"
                     + (f"   |   {', '.join(marcadas)}" if marcadas else "")
                     + (f"   |   {peca}" if peca else "")
                     + f"   |   {len(linhas)} cliente(s)"
                     + (f"   |   ordenado por {self._ordem_da_tela_txt()}"
                        if self._ordem_da_tela_txt() else "")
                     + (f"   |   competencia {self.competencia}"
                        if getattr(self, "competencia", "") else ""))
        destino = (AQUI / pb.RELATORIOS /
                   mn.nome_da_folha_de_clientes(
                       getattr(self, "competencia", "")))
        try:
            mn.gravar_folha_de_clientes(linhas, destino, subtitulo,
                                        colunas=self._colunas_da_folha())
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        self.aviso(f"{destino.name}: {len(linhas)} cliente(s). Abrindo no "
                   f"navegador - use Ctrl+P e 'Salvar como PDF'.", COR_OK)
        bp.App._abrir(destino)

    # ================================================================== 2
    # ================================================================== 2
    def _montar_rota(self):
        """
        A MESMA consulta do Planner, aqui do lado. A agenda vem do
        PLANNER_BAP ja gerado - a rota que esta valendo na rua - e o resto
        da linha e a base de oportunidade da aba 1. Aqui so se CONSULTA e
        EXPORTA: mudar zona, vendedor, semana ou dia continua sendo no
        Planner, para os dois programas nao gravarem no mesmo cadastro ao
        mesmo tempo.
        """
        f = self.aba_rota
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Analitico de rota",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="EXPORTAR ROTA", style="Big.TButton",
                   command=self.exportar_rota).pack(side="right")
        ttk.Button(topo, text="RECARREGAR", style="Big.TButton",
                   command=self.carregar_rota).pack(side="right", padx=8)

        ttk.Label(f, text="Quando voce passa em cada cliente, com tudo o "
                          "que a aba 1 sabe sobre ele. A agenda vem do "
                          "PLANNER_BAP que ja foi gerado - a rota que o "
                          "vendedor tem na mao. Para MUDAR zona, vendedor, "
                          "semana ou dia, use o Planner BAP.",
                  style="Sub.TLabel", wraplength=1350).pack(anchor="w",
                                                            pady=(4, 10))

        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Ver por:").pack(side="left")
        self.var_rec_rota = tk.StringVar(value="zona")
        cb = ttk.Combobox(barra, textvariable=self.var_rec_rota, width=13,
                          state="readonly", values=mn.RECORTES_FILTRO)
        cb.pack(side="left", padx=(6, 10))
        cb.bind("<<ComboboxSelected>>", lambda _: self._recorte_rota_mudou())
        self.var_alvo_rota = tk.StringVar(value=mn.TODOS)
        self.cb_alvo_rota = ttk.Combobox(barra, textvariable=self.var_alvo_rota,
                                         width=34, state="readonly",
                                         values=[mn.TODOS])
        self.cb_alvo_rota.pack(side="left")
        self.cb_alvo_rota.bind("<<ComboboxSelected>>",
                               lambda _: self._desenhar_rota())

        ttk.Label(barra, text="   Visao:").pack(side="left")
        self.var_visao_rota = tk.StringVar(value=on.VISAO_CLIENTE)
        cbv = ttk.Combobox(barra, textvariable=self.var_visao_rota, width=24,
                           state="readonly", values=on.VISOES_DA_ROTA)
        cbv.pack(side="left", padx=6)
        cbv.bind("<<ComboboxSelected>>", lambda _: self._visao_rota_mudou())

        self.linha_agenda_rota = ttk.Frame(f)
        ttk.Label(self.linha_agenda_rota, text="Semana:").pack(side="left")
        self.var_semana_rota = tk.StringVar(value=mn.TODOS)
        self.cb_semana_rota = ttk.Combobox(
            self.linha_agenda_rota, textvariable=self.var_semana_rota,
            width=12, state="readonly", values=[mn.TODOS])
        self.cb_semana_rota.pack(side="left", padx=(6, 14))
        self.cb_semana_rota.bind("<<ComboboxSelected>>",
                                 lambda _: self._desenhar_rota())
        ttk.Label(self.linha_agenda_rota, text="Dia do mes:").pack(side="left")
        self.var_dia_rota = tk.StringVar(value=mn.TODOS)
        self.cb_dia_rota = ttk.Combobox(
            self.linha_agenda_rota, textvariable=self.var_dia_rota, width=12,
            state="readonly", values=[mn.TODOS])
        self.cb_dia_rota.pack(side="left", padx=6)
        self.cb_dia_rota.bind("<<ComboboxSelected>>",
                              lambda _: self._desenhar_rota())
        ttk.Button(self.linha_agenda_rota, text="Limpar dia e semana",
                   command=self._limpar_agenda_rota).pack(side="left", padx=10)
        ttk.Label(self.linha_agenda_rota, style="Sub.TLabel",
                  text="Nesta visao o cliente aparece uma vez por visita. "
                       "Na visao CLIENTE ele aparece uma vez so, com os "
                       "dias dele nas ultimas colunas.").pack(side="left",
                                                              padx=10)

        self.lbl_rota = ttk.Label(f, text="", style="Sub.TLabel")
        self.lbl_rota.pack(anchor="w", pady=(0, 6))
        self.quadro_rota = ttk.Frame(f)
        self.quadro_rota.pack(fill="both", expand=True)
        self.tab_rota = None
        self._montar_tabela_rota()

    def _colunas_da_rota_na_tela(self) -> list:
        """
        As colunas do Excel viram colunas de tabela, na mesma ordem.

        Guardado por visao: sao 40 colunas, e remontar a lista a cada uma
        das milhares de linhas desenhadas custava mais que desenhar.
        """
        guardado = getattr(self, "_cols_rota", None)
        if guardado and guardado[0] == self.var_visao_rota.get():
            return guardado[1]
        largura = {"CLIENTE": 250, "ZONA": 190, "ENDERECO": 220,
                   "ULT. COMPRA": 250, "VENDEDOR": 180, "SUPERVISOR": 170,
                   "GERENTE": 160, "BAIRRO": 150, "CIDADE": 140}
        direita = {"#,##0.00", "#,##0.0"}
        saida = []
        for titulo, chave, larg, formato in on.colunas_da_rota(
                self.var_visao_rota.get()):
            saida.append((chave, titulo, largura.get(titulo, max(70, larg * 7)),
                          "e" if formato in direita else "w",
                          titulo == "CLIENTE"))
        self._cols_rota = (self.var_visao_rota.get(), saida)
        return saida

    def _montar_tabela_rota(self):
        if self.tab_rota is not None:
            for filho in self.quadro_rota.winfo_children():
                filho.destroy()
        quadro, self.tab_rota = bp.tabela(self.quadro_rota,
                                          self._colunas_da_rota_na_tela(),
                                          rodape=True)
        quadro.pack(fill="both", expand=True)

    def _visao_rota_mudou(self):
        if self.var_visao_rota.get() == on.VISAO_VISITA:
            self.linha_agenda_rota.pack(fill="x", pady=(0, 8),
                                        before=self.lbl_rota)
        else:
            self.linha_agenda_rota.pack_forget()
        self._montar_tabela_rota()
        self._desenhar_rota()

    def _limpar_agenda_rota(self):
        self.var_semana_rota.set(mn.TODOS)
        self.var_dia_rota.set(mn.TODOS)
        self._desenhar_rota()

    def _recorte_rota_mudou(self):
        alvos = mn.alvos_do_recorte(self.oportunidade or [],
                                    self.var_rec_rota.get())
        self.cb_alvo_rota.configure(values=alvos)
        self.var_alvo_rota.set(mn.TODOS)
        self._desenhar_rota()

    def carregar_rota(self):
        """Le a agenda do PLANNER_BAP mais recente da pasta."""
        if self.oportunidade is None:
            self.carregar_cliente()
            if self.oportunidade is None:
                return
        planner = pb.planner_mais_recente(AQUI)
        if planner is None:
            self.aviso("Nenhum PLANNER_BAP na pasta: gere a rota no Planner "
                       "BAP e volte aqui.", COR_ALERTA)
            return
        self.aviso("Lendo a rota do PLANNER...", COR_SUAVE)
        self.update_idletasks()
        try:
            self.visitas = on.ler_visitas_do_planner(planner)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        semanas, dias = on.semanas_e_dias(self.visitas)
        self.cb_semana_rota.configure(values=[mn.TODOS] + semanas)
        self.cb_dia_rota.configure(values=[mn.TODOS] + dias)
        self._recorte_rota_mudou()
        self.aviso(f"{len(self.visitas)} visita(s) na rota de "
                   f"{Path(planner).name}.", COR_OK)

    def _lista_rota(self) -> list:
        if not getattr(self, "visitas", None):
            return []
        # a caixinha mostra "000034 - ANDERSON"; o filtro quer so o nome
        alvo = self.var_alvo_rota.get()
        if alvo != mn.TODOS and " - " in alvo:
            alvo = alvo.split(" - ", 1)[1]
        base = mn.filtrar_oportunidade(
            self.oportunidade or [], self.var_rec_rota.get(), alvo)
        return on.montar_rota(base, self.visitas, self.var_visao_rota.get(),
                              self.var_semana_rota.get(),
                              self.var_dia_rota.get())

    def _desenhar_rota(self):
        if not getattr(self, "visitas", None):
            return
        linhas = self._lista_rota()
        t = self.tab_rota
        self._silencio = True
        try:
            t.delete(*t.get_children())
            colunas = self._colunas_da_rota_na_tela()
            for i, l in enumerate(linhas):
                t.insert("", "end", tags=("zebra",) if i % 2 else (),
                         values=self._valores_rota(l, colunas=colunas))
            bp.escrever_total(t, self._valores_rota(
                {"uf": "TOTAL", "cliente": f"{len(linhas)} linha(s)"},
                total=True, colunas=colunas))
        finally:
            self._silencio = False
        visitas = sum(l.get("visitas") or 0 for l in linhas) \
            if self.var_visao_rota.get() == on.VISAO_CLIENTE else len(linhas)
        self.lbl_rota.configure(
            text=f"{len(linhas)} linha(s)   |   {visitas} visita(s)   |   "
                 f"visao {self.var_visao_rota.get()}")

    def _valores_rota(self, linha, total=False, colunas=None):
        saida = []
        for chave, titulo, _, _, _ in (colunas
                                       or self._colunas_da_rota_na_tela()):
            v = linha.get(chave)
            if total and chave not in ("uf", "cliente"):
                saida.append("")
            elif "R$" in titulo:
                saida.append(dinheiro(v))
            elif isinstance(v, (dt.date, dt.datetime)):
                saida.append(v.strftime("%d/%m/%Y"))
            else:
                saida.append(v if v is not None else "")
        return saida

    def exportar_rota(self, avisar=True):
        if not getattr(self, "visitas", None):
            if avisar:
                messagebox.showinfo("Oportunidades BAP",
                                    "Carregue a rota primeiro.")
            return
        linhas = self._lista_rota()
        destino = AQUI / pb.RELATORIOS / on.nome_do_arquivo_de_rota()
        alvo = self.var_alvo_rota.get()
        filtro = (f"{self.var_rec_rota.get().upper()}: {alvo}"
                  if alvo and alvo != mn.TODOS else "")
        try:
            on.gravar_excel_rota(linhas, destino,
                                 self.var_visao_rota.get(), filtro)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado com {len(linhas)} linha(s).",
                   COR_OK)
        if avisar:
            messagebox.showinfo("Oportunidades BAP",
                                f"{destino.name}\n\n{len(linhas)} linha(s).")

    # ================================================================== 3
    def _montar_estoque(self):
        f = self.aba_est
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Oportunidade de estoque",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="EXPORTAR ESTOQUE", style="Big.TButton",
                   command=self.exportar_estoque).pack(side="right")
        ttk.Button(topo, text="APURAR AGORA",
                   command=self.carregar_estoque).pack(side="right", padx=8)

        ttk.Label(f, text="O que empurrar: o estoque de cada filial com o "
                          "preco de capital e de interior, e as DUAS curvas "
                          "do produto. CURVA FILIAL diz se o item gira ALI; "
                          "CURVA GERAL, se ele gira na BAP inteira. Item que "
                          "gira na rede e esta parado na filial e a "
                          "oportunidade de verdade - ha para quem vender.",
                  style="Sub.TLabel", wraplength=1350).pack(anchor="w",
                                                            pady=(4, 10))

        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Regiao:").pack(side="left")
        self.var_regiao = tk.StringVar(value=mn.TODOS)
        self.cb_regiao = ttk.Combobox(barra, textvariable=self.var_regiao,
                                      width=24, state="readonly",
                                      values=[mn.TODOS])
        self.cb_regiao.pack(side="left", padx=6)
        self.cb_regiao.bind("<<ComboboxSelected>>",
                            lambda _: self._desenhar_estoque())
        for rotulo, var_nome in (("Curva FILIAL:", "var_cf"),
                                 ("Curva GERAL:", "var_cg")):
            ttk.Label(barra, text=f"   {rotulo}").pack(side="left")
            v = tk.StringVar(value=mn.TODOS)
            setattr(self, var_nome, v)
            cb = ttk.Combobox(barra, textvariable=v, width=8,
                              state="readonly", values=[mn.TODOS])
            cb.pack(side="left", padx=6)
            cb.bind("<<ComboboxSelected>>",
                    lambda _: self._desenhar_estoque())
            setattr(self, "cb_" + var_nome[4:], cb)
        self.var_so_op = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="SO AS OPORTUNIDADES (gira na rede e "
                                    "esta parado aqui)",
                        variable=self.var_so_op,
                        command=self._desenhar_estoque).pack(side="left",
                                                             padx=14)
        ttk.Button(barra, text="Limpar filtros",
                   command=self._limpar_estoque).pack(side="left")

        # a segunda fileira: a peca em si. FAMILIA e a caixa grande
        # (FREIO, SUSPENSAO), GRUPO e o item dentro dela e LINHA e para
        # que veiculo. Escolher a familia ja enxuga a lista do grupo.
        barra2 = ttk.Frame(f)
        barra2.pack(fill="x", pady=(0, 8))
        ttk.Label(barra2, text="Familia:").pack(side="left")
        self.var_fam_est = tk.StringVar(value=mn.TODOS)
        self.cb_fam_est = ttk.Combobox(barra2, textvariable=self.var_fam_est,
                                       width=20, state="readonly",
                                       values=[mn.TODOS])
        self.cb_fam_est.pack(side="left", padx=6)
        self.cb_fam_est.bind("<<ComboboxSelected>>",
                             lambda _: self._familia_do_estoque_mudou())
        ttk.Label(barra2, text="   Grupo:").pack(side="left")
        self.var_gru_est = tk.StringVar(value=mn.TODOS)
        self.cb_gru_est = ttk.Combobox(barra2, textvariable=self.var_gru_est,
                                       width=34, state="readonly",
                                       values=[mn.TODOS])
        self.cb_gru_est.pack(side="left", padx=6)
        self.cb_gru_est.bind("<<ComboboxSelected>>",
                             lambda _: self._desenhar_estoque())
        ttk.Label(barra2, text="   Linha:").pack(side="left")
        self.var_lin_est = tk.StringVar(value=mn.TODOS)
        self.cb_lin_est = ttk.Combobox(barra2, textvariable=self.var_lin_est,
                                       width=14, state="readonly",
                                       values=[mn.TODOS])
        self.cb_lin_est.pack(side="left", padx=6)
        self.cb_lin_est.bind("<<ComboboxSelected>>",
                             lambda _: self._desenhar_estoque())

        quadro, self.tab_est = bp.tabela(f, self.COLUNAS_EST, rodape=True)
        quadro.pack(fill="both", expand=True)
        self.tab_est.tag_configure("oportunidade", background="#FFF4D6")
        self.tab_est.tag_configure("parado", background="#F6E7E7")
        self.lbl_est = ttk.Label(f, text="", style="Sub.TLabel",
                                 wraplength=1350)
        self.lbl_est.pack(anchor="w", pady=(6, 0))
        bp.legenda_de_cores(f, [
            ("#FFF4D6", "OPORTUNIDADE: curva A ou B na rede e C, D ou Z "
                        "nesta filial - gira la fora e esta parado aqui"),
            ("#F6E7E7", "parado nos dois: curva Z na filial e na rede"),
        ]).pack(anchor="w", pady=(8, 0))

    def carregar_estoque(self):
        tabela = on.achar_tabela(AQUI)
        if tabela is None:
            messagebox.showwarning(
                "Oportunidades BAP",
                f"Nao achei a {on.ARQUIVO_TABELA} na pasta "
                f"{pb.RELATORIOS}.")
            return
        self.aviso("Lendo o estoque, os precos e a ultima venda de cada "
                   "item...", COR_SUAVE)
        self.update_idletasks()
        try:
            self.estoque = on.montar_estoque(tabela, self.par, raiz=AQUI)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        regioes = sorted({l["regiao"] for l in self.estoque["linhas"]})
        self.cb_regiao.configure(values=[mn.TODOS] + regioes)
        letras = [f["letra"] for f in self.par.get("curvas")
                  or on.CURVAS_PADRAO] + [on.LETRA_PARADO]
        self.cb_cf.configure(values=[mn.TODOS] + letras)
        self.cb_cg.configure(values=[mn.TODOS] + letras)
        presentes = {l.get("familia") or "" for l in self.estoque["linhas"]}
        self.cb_fam_est.configure(
            values=[mn.TODOS] + [x for x in fam.ORDEM_FAMILIA
                                 if x in presentes])
        linhas_v = {l.get("linha") or "" for l in self.estoque["linhas"]}
        self.cb_lin_est.configure(
            values=[mn.TODOS] + [x for x in fam.ORDEM_LINHA if x in linhas_v])
        self._encher_grupos_do_estoque()
        self._desenhar_estoque()
        recado = (f"{len(self.estoque['linhas'])} item(ns) com estoque, "
                  f"{self.estoque['oportunidades']} oportunidade(s). "
                  f"Estoque lido de {self.estoque.get('fonte_estoque') or '?'}")
        quando = self.estoque.get("extraido_em")
        if quando:
            recado += f", extraido em {quando}"
        aviso = self.estoque.get("aviso_estoque")
        self.aviso(recado + "." + (f"  ATENCAO: {aviso}" if aviso else ""),
                   COR_ALERTA if aviso else COR_OK)
        # agora que se sabe quais filiais tem estoque, a lista da aba 5
        # pode ser desenhada de verdade
        self._desenhar_filiais()

    def _limpar_estoque(self):
        self.var_regiao.set(mn.TODOS)
        self.var_cf.set(mn.TODOS)
        self.var_cg.set(mn.TODOS)
        self.var_so_op.set(False)
        self.var_fam_est.set(mn.TODOS)
        self.var_lin_est.set(mn.TODOS)
        self._encher_grupos_do_estoque()
        self._desenhar_estoque()

    def _familia_do_estoque_mudou(self):
        """Escolhida a familia, o GRUPO passa a mostrar so os dela."""
        self._encher_grupos_do_estoque()
        self._desenhar_estoque()

    def _encher_grupos_do_estoque(self):
        """A lista de grupos, limitada a familia escolhida."""
        linhas = list((self.estoque or {}).get("linhas") or [])
        familia = self.var_fam_est.get()
        if familia != mn.TODOS:
            linhas = [l for l in linhas if l.get("familia") == familia]
        grupos = sorted({l.get("grupo") or "" for l in linhas} - {""},
                        key=lambda g: (fam.ORDEM_GRUPO.index(g)
                                       if g in fam.ORDEM_GRUPO else 999, g))
        self.cb_gru_est.configure(values=[mn.TODOS] + grupos)
        if self.var_gru_est.get() not in grupos:
            self.var_gru_est.set(mn.TODOS)

    def _lista_estoque(self) -> list:
        linhas = list((self.estoque or {}).get("linhas") or [])
        if self.var_regiao.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l["regiao"] == self.var_regiao.get()]
        if self.var_cf.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l["curva_filial"] == self.var_cf.get()]
        if self.var_cg.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l["curva_geral"] == self.var_cg.get()]
        if self.var_so_op.get():
            linhas = [l for l in linhas if l["oportunidade"]]
        if self.var_fam_est.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l.get("familia") == self.var_fam_est.get()]
        if self.var_gru_est.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l.get("grupo") == self.var_gru_est.get()]
        if self.var_lin_est.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l.get("linha") == self.var_lin_est.get()]
        return linhas

    def _desenhar_estoque(self):
        if self.estoque is None:
            return
        linhas = self._lista_estoque()
        t = self.tab_est
        self._silencio = True
        try:
            t.delete(*t.get_children())
            for i, l in enumerate(linhas):
                if l["oportunidade"]:
                    tags = ("oportunidade",)
                elif (l["curva_filial"] == on.LETRA_PARADO
                      and l["curva_geral"] == on.LETRA_PARADO):
                    tags = ("parado",)
                else:
                    tags = ("zebra",) if i % 2 else ()
                l["_iid"] = f"{l['filial']}|{l['produto']}"
                t.insert("", "end", iid=l["_iid"],
                         tags=tags, values=self._valores_est(l))
            bp.escrever_total(t, self._valores_est(
                self._total_estoque(linhas), total=True))
        finally:
            self._silencio = False
        parado = [l for l in linhas if l["oportunidade"]]
        self.lbl_est.configure(
            text=f"{len(linhas)} item(ns) de "
                 f"{len(self.estoque['linhas'])}   |   estoque somado "
                 f"{dinheiro(sum(l['valor_estoque'] for l in linhas))}   |   "
                 f"{len(parado)} oportunidade(s), "
                 f"{dinheiro(sum(l['valor_estoque'] for l in parado))} "
                 f"parados que giram na rede.   A curva olha de "
                 f"{self.estoque['hoje'].strftime('%d/%m/%Y')} para tras."
                 f"   Estoque: {self.estoque.get('fonte_estoque') or '?'}"
                 + (f" de {self.estoque['extraido_em']}"
                    if self.estoque.get("extraido_em") else ""))

    def _total_estoque(self, linhas) -> dict:
        soma = {"regiao": "TOTAL", "produto": "",
                "descricao": f"TOTAL DA LISTA ({len(linhas)} itens)"}
        for campo in ("estoque", "disponivel", "valor_estoque",
                      "qtd_vendida_filial", "qtd_vendida_geral"):
            soma[campo] = sum(l.get(campo) or 0 for l in linhas)
        return soma

    def _valores_est(self, linha, total=False):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_EST:
            v = linha.get(chave)
            if chave in ("preco_capital", "preco_interior", "valor_estoque",
                         "custo"):
                saida.append(dinheiro(v) if v or total else "")
            elif chave in ("markup_capital", "markup_interior"):
                # sem custo nao da markup - e melhor vazio que zero
                saida.append(numero_br(v, 1) if v is not None else "")
            elif chave in ("estoque", "disponivel", "qtd_vendida_filial",
                           "qtd_vendida_geral"):
                saida.append(numero_br(v))
            elif v is None:
                saida.append("nunca" if not total else "")
            else:
                saida.append(v)
        return saida

    def exportar_estoque(self):
        if not self.estoque:
            messagebox.showinfo("Oportunidades BAP",
                                "Clique em APURAR AGORA primeiro.")
            return
        linhas = self._na_ordem_da_tela(self.tab_est, self._lista_estoque(),
                                        campo="_iid")
        destino = (AQUI / pb.RELATORIOS /
                   on.nome_do_arquivo_de_estoque(self.estoque["hoje"]))
        try:
            on.gravar_excel_estoque(
                linhas, self.par, destino, self.estoque["hoje"],
                fonte=self.estoque.get("fonte_estoque", ""),
                extraido_em=self.estoque.get("extraido_em", ""))
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado com {len(linhas)} item(ns).",
                   COR_OK)
        messagebox.showinfo(
            "Oportunidades BAP",
            f"{destino.name}\n\n{len(linhas)} item(ns), com o filtro da "
            f"tela. A aba PARAMETROS diz de onde cada curva saiu.\n\n"
            f"Gravado em:\n{destino.parent}")

    # ============================================================== 4 (mix)
    # MIX DISPONIVEL x MIX POSITIVADO
    #   disponivel = SKUs diferentes com estoque
    #   positivado = quantos DESSES sairam na janela
    #   % MIX      = positivado / disponivel
    # Conta SKU, nunca unidade: um item vendido 300 vezes conta 1.
    # As colunas sao as mesmas em todo nivel; o que muda e o titulo da
    # primeira. TODAS ESTICAM: a tabela reparte a largura que sobra, e ao
    # maximizar nao fica buraco branco na direita nem barra de rolagem.
    COLUNAS_MIX_TELA = [
        ("nome", "CIDADE", 130, "w", True),
        ("rotulo", "CATEGORIA", 150, "w", True),
        ("skus_disponiveis", "SKUS DISP.", 90, "center", True),
        ("skus_positivados", "SKUS POSIT.", 92, "center", True),
        ("pct_mix", "% MIX", 68, "center", True),
        ("skus_sem_giro", "SEM GIRO", 80, "center", True),
        ("curva_A", "CURVA A", 66, "center", True),
        ("curva_B", "CURVA B", 66, "center", True),
        ("curva_C", "CURVA C", 66, "center", True),
        ("curva_D", "CURVA D", 66, "center", True),
        ("curva_Z", "CURVA Z", 66, "center", True),
        ("media_sku_mes", "MEDIA SKU/MES", 108, "center", True),
        ("volume_medio_mes", "VOL. MEDIO/MES", 112, "center", True),
        ("estoque", "ESTOQUE (UN)", 100, "center", True),
        ("valor_estoque", "ESTOQUE EM R$", 118, "e", True),
        ("valor_parado", "R$ PARADO", 112, "e", True),
    ]

    # quantas linhas a tabela mostra antes de comecar a rolar. Vinte e
    # seis cabem numa tela de 1080 com a barra de cima e o rodape.
    TETO_DE_LINHAS = 26

    def _montar_mix(self):
        f = self.aba_mix
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Mix de produtos: disponivel x positivado",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="EXPORTAR MIX", style="Big.TButton",
                   command=self.exportar_mix).pack(side="right")
        ttk.Button(topo, text="APURAR AGORA",
                   command=self.carregar_mix).pack(side="right", padx=8)

        ttk.Label(f, text="Do que esta na prateleira, quanto voce consegue "
                          "vender. SKUS DISP. = quantos SKUs DIFERENTES tem "
                          "estoque; SKUS POSIT. = quantos desses sairam "
                          "dentro da janela; % MIX = um dividido pelo outro. "
                          "Conta SKU, nunca unidade.",
                  style="Sub.TLabel", wraplength=1400).pack(anchor="w",
                                                            pady=(2, 8))

        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Label(barra, text="Ver por:").pack(side="left")
        self.var_mix_nivel = tk.StringVar(value="CIDADE")
        cb = ttk.Combobox(barra, textvariable=self.var_mix_nivel, width=12,
                          state="readonly",
                          values=[r for _, r in on.NIVEIS_DO_MIX])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _: self._nivel_do_mix_mudou())

        self.var_mix_cat = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="quebrar por CATEGORIA",
                        variable=self.var_mix_cat,
                        command=self._desenhar_mix).pack(side="left", padx=12)

        ttk.Label(barra, text="  Vendeu nos ultimos:").pack(side="left")
        self.var_mix_janela = tk.StringVar(value=str(on.JANELA_DO_MIX_PADRAO))
        cbj = ttk.Combobox(barra, textvariable=self.var_mix_janela, width=6,
                           state="readonly",
                           values=[str(d) for d in on.JANELAS_DO_MIX])
        cbj.pack(side="left", padx=6)
        cbj.bind("<<ComboboxSelected>>", lambda _: self.carregar_mix())
        ttk.Label(barra, text="dias", style="Sub.TLabel").pack(side="left")

        self.lbl_mix_filtro = ttk.Label(barra, text="   Cidade:")
        self.lbl_mix_filtro.pack(side="left")
        self.var_mix_cidade = tk.StringVar(value=mn.TODOS)
        self.cb_mix_cidade = ttk.Combobox(barra,
                                          textvariable=self.var_mix_cidade,
                                          width=20, state="readonly",
                                          values=[mn.TODOS])
        self.cb_mix_cidade.pack(side="left", padx=6)
        self.cb_mix_cidade.bind("<<ComboboxSelected>>",
                                lambda _: self._desenhar_mix())

        # ESTOQUE FISICO x DISPONIVEL: o disponivel ja desconta a reserva
        # e o que esta em pedido. Muda o denominador, entao muda o % MIX.
        self.var_mix_disp = tk.BooleanVar(value=False)
        self.cb_mix_disp = ttk.Checkbutton(
            barra, text="usar o DISPONIVEL (desconta reserva e pedido)",
            variable=self.var_mix_disp, command=self.carregar_mix)
        self.cb_mix_disp.pack(side="left", padx=12)

        # A PECA: recortar a prateleira por FAMILIA/GRUPO/LINHA muda o
        # denominador do % MIX - a pergunta passa a ser "do freio que eu
        # tenho, quanto consigo vender".
        barra2 = ttk.Frame(f)
        barra2.pack(fill="x", pady=(0, 6))
        ttk.Label(barra2, text="Familia:").pack(side="left")
        self.var_fam_mix = tk.StringVar(value=mn.TODOS)
        self.cb_fam_mix = ttk.Combobox(barra2, textvariable=self.var_fam_mix,
                                       width=20, state="readonly",
                                       values=[mn.TODOS])
        self.cb_fam_mix.pack(side="left", padx=6)
        self.cb_fam_mix.bind("<<ComboboxSelected>>",
                             lambda _: self._familia_do_mix_mudou())
        ttk.Label(barra2, text="   Grupo:").pack(side="left")
        self.var_gru_mix = tk.StringVar(value=mn.TODOS)
        self.cb_gru_mix = ttk.Combobox(barra2, textvariable=self.var_gru_mix,
                                       width=34, state="readonly",
                                       values=[mn.TODOS])
        self.cb_gru_mix.pack(side="left", padx=6)
        self.cb_gru_mix.bind("<<ComboboxSelected>>",
                             lambda _: self.carregar_mix())
        ttk.Label(barra2, text="   Linha:").pack(side="left")
        self.var_lin_mix = tk.StringVar(value=mn.TODOS)
        self.cb_lin_mix = ttk.Combobox(barra2, textvariable=self.var_lin_mix,
                                       width=14, state="readonly",
                                       values=[mn.TODOS])
        self.cb_lin_mix.pack(side="left", padx=6)
        self.cb_lin_mix.bind("<<ComboboxSelected>>",
                             lambda _: self.carregar_mix())
        ttk.Button(barra2, text="Limpar",
                   command=self._limpar_mix).pack(side="left", padx=10)

        # ---- o placar da BAP inteira -------------------------------------
        placar = ttk.Frame(f)
        placar.pack(fill="x", pady=(0, 6))
        self.lbl_mix_placar = ttk.Label(placar, text="Clique em APURAR AGORA.",
                                        style="Cod.TLabel", wraplength=1400)
        self.lbl_mix_placar.pack(anchor="w")

        # A TABELA ACOMPANHA A QUANTIDADE DE LINHAS ate um teto, em vez
        # de esticar sempre: com sete cidades na tela um painel de 600px
        # vazio entre a ultima linha e o TOTAL nao ajuda ninguem a printar.
        quadro, self.tab_mix = bp.tabela(f, self.COLUNAS_MIX_TELA,
                                         altura=8, rodape=True,
                                         horizontal=False)
        quadro.pack(fill="x")
        self.lbl_mix = ttk.Label(f, text="", style="Sub.TLabel",
                                 wraplength=1400)
        self.lbl_mix.pack(anchor="w", pady=(6, 0))

    def _nivel_do_mix(self) -> str:
        escolhido = self.var_mix_nivel.get()
        for chave, rotulo in on.NIVEIS_DO_MIX:
            if rotulo == escolhido:
                return chave
        return "cidade"

    def _nivel_do_mix_mudou(self):
        """Trocou o nivel: o titulo da primeira coluna e o filtro mudam."""
        nivel = self._nivel_do_mix()
        rotulo = dict(on.NIVEIS_DO_MIX).get(nivel, "CIDADE")
        self.tab_mix.heading("nome", text=rotulo)
        self.lbl_mix_filtro.configure(text=f"   So um(a) {rotulo}:")
        nomes = sorted({l["nome"] for l in on.linhas_do_mix(self.mix, nivel)})
        self.cb_mix_cidade.configure(values=[mn.TODOS] + nomes)
        if self.var_mix_cidade.get() not in [mn.TODOS] + nomes:
            self.var_mix_cidade.set(mn.TODOS)
        # no nivel BAP a lista tem uma linha so: filtrar nao faz sentido
        if nivel == "bap":
            self.lbl_mix_filtro.pack_forget()
            self.cb_mix_cidade.pack_forget()
        else:
            self.lbl_mix_filtro.pack(side="left", before=self.cb_mix_disp)
            self.cb_mix_cidade.pack(side="left", padx=6,
                                    before=self.cb_mix_disp)
        self._desenhar_mix()

    def carregar_mix(self):
        if self.estoque is None:
            self.carregar_estoque()
            if self.estoque is None:
                return
        if not self.categorias:
            csv_cat = mn.achar_csv_de_categorias(AQUI)
            self.categorias = (on.ler_categoria_dos_produtos(csv_cat)
                               if csv_cat else {})
        # o nome do vendedor vem da base de cliente (o PLANNER), se ela
        # ja estiver carregada. Sem ela, fica so o codigo Protheus.
        nomes = {}
        for c in (self.oportunidade or []):
            cod = (c.get("cod_vendedor") or "").strip()
            if cod and c.get("vendedor"):
                nomes.setdefault(cod, c["vendedor"])
                nomes.setdefault(cod.zfill(6), c["vendedor"])
        self._encher_pecas_do_mix()
        so = lambda v: "" if v.get() == mn.TODOS else v.get()   # noqa: E731
        self.mix = on.montar_mix(
            self.estoque, self.categorias,
            janela=on._numero(self.var_mix_janela.get())
            or on.JANELA_DO_MIX_PADRAO,
            usar_disponivel=self.var_mix_disp.get(),
            nomes_de_vendedor=nomes,
            familia=so(self.var_fam_mix), grupo=so(self.var_gru_mix),
            linha_bap=so(self.var_lin_mix))
        self._nivel_do_mix_mudou()
        self.aviso(f"Mix apurado: {self.mix['geral']['skus_positivados']} de "
                   f"{self.mix['geral']['skus_disponiveis']} SKUs "
                   f"positivados na BAP.", COR_OK)

    def _limpar_mix(self):
        self.var_fam_mix.set(mn.TODOS)
        self.var_gru_mix.set(mn.TODOS)
        self.var_lin_mix.set(mn.TODOS)
        self.carregar_mix()

    def _familia_do_mix_mudou(self):
        self.var_gru_mix.set(mn.TODOS)
        self.carregar_mix()

    def _encher_pecas_do_mix(self):
        """As listas de FAMILIA, GRUPO e LINHA, so com o que ha em estoque."""
        todas = list((self.estoque or {}).get("linhas") or [])
        presentes = {l.get("familia") or "" for l in todas}
        self.cb_fam_mix.configure(
            values=[mn.TODOS] + [x for x in fam.ORDEM_FAMILIA
                                 if x in presentes])
        linhas_v = {l.get("linha") or "" for l in todas}
        self.cb_lin_mix.configure(
            values=[mn.TODOS] + [x for x in fam.ORDEM_LINHA if x in linhas_v])
        if self.var_fam_mix.get() != mn.TODOS:
            todas = [l for l in todas
                     if l.get("familia") == self.var_fam_mix.get()]
        grupos = sorted({l.get("grupo") or "" for l in todas} - {""},
                        key=lambda g: (fam.ORDEM_GRUPO.index(g)
                                       if g in fam.ORDEM_GRUPO else 999, g))
        self.cb_gru_mix.configure(values=[mn.TODOS] + grupos)
        if self.var_gru_mix.get() not in grupos:
            self.var_gru_mix.set(mn.TODOS)

    def _lista_mix(self) -> list:
        linhas = on.linhas_do_mix(self.mix, self._nivel_do_mix(),
                                  self.var_mix_cat.get())
        if self.var_mix_cidade.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l["nome"] == self.var_mix_cidade.get()]
        return linhas

    def _total_mix(self, linhas) -> dict:
        """
        O rodape NAO soma SKU: o mesmo produto aparece em varias cidades e
        somar contaria ele de novo. O que vale de total e a BAP inteira,
        que ja vem contada uma vez so - o dinheiro, sim, e a soma da tela.
        """
        g = (self.mix or {}).get("geral") or {}
        total = {"nome": "TOTAL BAP",
                 "rotulo": "SKU contado uma vez so"}
        for campo in ("skus_disponiveis", "skus_positivados", "pct_mix",
                      "skus_sem_giro", "media_sku_mes", "volume_medio_mes"):
            total[campo] = g.get(campo, 0)
        for letra in on.ORDEM_DAS_CURVAS:
            total[f"curva_{letra}"] = g.get(f"curva_{letra}", 0)
        for campo in ("estoque", "valor_estoque", "valor_parado"):
            total[campo] = sum(l.get(campo) or 0 for l in linhas)
        return total

    def _valores_mix(self, linha, total=False):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_MIX_TELA:
            v = linha.get(chave)
            if chave in ("valor_estoque", "valor_parado"):
                saida.append(dinheiro(v) if v or total else "")
            elif chave == "pct_mix":
                saida.append(f"{numero_br(v, 1)}%")
            elif chave == "media_sku_mes":
                saida.append(numero_br(v, 1))
            elif chave in ("skus_disponiveis", "skus_positivados",
                           "skus_sem_giro", "estoque", "volume_medio_mes") \
                    or chave.startswith("curva_"):
                saida.append(numero_br(v))
            else:
                saida.append(v if v is not None else "")
        return saida

    def _desenhar_mix(self):
        if self.mix is None:
            return
        linhas = self._lista_mix()
        t = self.tab_mix
        # sem a quebra, a coluna CATEGORIA so repetiria "(todas as
        # categorias)" linha a linha: ela sai da tela e devolve a largura
        # para as outras
        chaves = [c[0] for c in self.COLUNAS_MIX_TELA]
        if not self.var_mix_cat.get():
            chaves = [c for c in chaves if c != "rotulo"]
        t.configure(displaycolumns=chaves)
        pe = getattr(t, "_rodape", None)
        if pe is not None:
            pe.configure(displaycolumns=chaves)
        self._silencio = True
        try:
            t.delete(*t.get_children())
            for i, l in enumerate(linhas):
                t.insert("", "end",
                         iid=f"{l['nome']}|{l['categoria']}|{i}",
                         tags=("zebra",) if i % 2 else (),
                         values=self._valores_mix(l))
            bp.escrever_total(t, self._valores_mix(self._total_mix(linhas),
                                                   total=True))
            t.configure(height=max(4, min(len(linhas), self.TETO_DE_LINHAS)))
        finally:
            self._silencio = False
        g = self.mix["geral"]
        self.lbl_mix_placar.configure(
            text=f"A BAP INTEIRA:   MIX DISPONIVEL "
                 f"{numero_br(g['skus_disponiveis'])} SKUs   |   MIX "
                 f"POSITIVADO {numero_br(g['skus_positivados'])} SKUs   |   "
                 f"% MIX {numero_br(g['pct_mix'], 1)}%   |   SEM GIRO "
                 f"{numero_br(g['skus_sem_giro'])} SKUs, "
                 f"{dinheiro(g['valor_parado'])} parados   |   MEDIA "
                 f"{numero_br(g['media_sku_mes'], 1)} SKUs/mes   |   janela "
                 f"de {self.mix['janela']} dias",
            foreground=COR_TITULO)
        sem_cat = not self.mix.get("com_categoria") and self.var_mix_cat.get()
        nivel = self._nivel_do_mix()
        recado = (f"{len(linhas)} linha(s) na tela   |   denominador: "
                  f"{'DISPONIVEL (sem reserva e sem pedido)' if self.mix['usar_disponivel'] else 'estoque fisico da prateleira'}"
                  f"   |   a janela olha de "
                  f"{self.estoque['hoje'].strftime('%d/%m/%Y')} para tras   |"
                  f"   MEDIA SKU/MES e VOL. MEDIO/MES sao dos ultimos "
                  f"{self.mix.get('meses_da_media', 12)} meses.")
        if nivel == "vendedor":
            recado += ("   O estoque do vendedor e o da FILIAL ONDE ELE MAIS "
                       "VENDE - dois da mesma filial mostram o mesmo estoque, "
                       "de proposito. O POSITIVADO e o que ELE vendeu.")
        elif nivel == "bap":
            recado += ("   No BAP vale a venda da REDE; nos outros niveis, a "
                       "venda DALI - por isso o geral nao e a soma das "
                       "cidades.")
        if sem_cat:
            recado += ("   ATENCAO: sem o CATEGORIAS_PRODUTO.csv na pasta "
                       "tudo cai em '(sem categoria)'.")
        self.lbl_mix.configure(text=recado,
                               foreground=COR_ALERTA if sem_cat else COR_SUAVE)

    def exportar_mix(self):
        if not self.mix:
            messagebox.showinfo("Oportunidades BAP",
                                "Clique em APURAR AGORA primeiro.")
            return
        destino = (AQUI / pb.RELATORIOS /
                   on.nome_do_arquivo_de_mix(self.estoque["hoje"]))
        try:
            on.gravar_excel_mix(self.mix, destino, self.estoque["hoje"])
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado.", COR_OK)
        messagebox.showinfo(
            "Oportunidades BAP",
            f"{destino.name}\n\nUma aba por recorte - BAP, UF, CIDADE e "
            f"VENDEDOR, com e sem a quebra por categoria - mais a "
            f"COMO_LER.\n\nGravado em:\n{destino.parent}")

    # ================================================================== 3
    # ---- a aba CLIENTE POR FAMILIA -------------------------------------
    # A pergunta que o vendedor faz na rua e "esse cliente compra freio?".
    # Ela nao esta na BASE_CLIENTE, que e por cliente, nem no estoque,
    # que e por produto: so o ITEM DA NOTA responde. Esta aba le a
    # ftPedidos item a item, classifica cada item pela familia e cruza
    # com a lista de clientes da aba 1.
    # As larguras somam ~1400 DE PROPOSITO: a tabela tem de caber numa
    # tela de 1480 sem barra de rolagem lateral. Os titulos sao curtos
    # pelo mesmo motivo - o rodape explica o que cada um quer dizer.
    COLUNAS_FAM = [
        ("uf", "UF", 38, "center", False),
        ("cidade", "CIDADE", 110, "w", False),
        ("cod_cliente", "COD.", 76, "w", False),
        ("cliente", "RAZAO SOCIAL", 195, "w", True),
        ("segmento", "SEGMENTO", 150, "w", False),
        ("cod_vendedor", "COD VD", 62, "center", False),
        ("vendedor", "VENDEDOR", 135, "w", False),
        ("zona", "ZONA", 105, "w", False),
        ("comprou_txt", "COMPROU", 70, "center", False),
        ("valor_familia", "R$ NA FAMILIA", 112, "e", False),
        ("skus_familia", "SKUS", 52, "center", False),
        ("dias_familia", "DIAS S/ FAM.", 96, "center", False),
        ("valor_total", "R$ TOTAL", 118, "e", False),
        ("perc_familia", "% FAM.", 80, "center", False),
        ("limite_disponivel", "LIM. DISP. R$", 104, "e", False),
        ("curva", "CURVA", 48, "center", False),
    ]

    def _montar_familia(self):
        f = self.aba_fam
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Cliente por familia de peca",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="EXPORTAR LISTA", style="Big.TButton",
                   command=self.exportar_familia).pack(side="right")
        ttk.Button(topo, text="APURAR AGORA",
                   command=self.carregar_familia).pack(side="right", padx=8)

        ttk.Label(f, text="Quem compra cada familia de peca, e quem nao "
                          "compra. A familia sai da DESCRICAO do item da "
                          "nota, entao aqui se le a venda item a item - "
                          "nao o total do cliente. Cliente que compra da "
                          "BAP mas nunca levou aquela familia e a "
                          "oportunidade limpa: o cadastro e o limite ja "
                          "existem, so falta oferecer.",
                  style="Sub.TLabel", wraplength=1400).pack(anchor="w",
                                                            pady=(4, 10))

        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Label(barra, text="Familia:").pack(side="left")
        self.var_fam = tk.StringVar(value=mn.TODOS)
        self.cb_fam = ttk.Combobox(barra, textvariable=self.var_fam, width=20,
                                   state="readonly",
                                   values=[mn.TODOS] + fam.ORDEM_FAMILIA)
        self.cb_fam.pack(side="left", padx=6)
        self.cb_fam.bind("<<ComboboxSelected>>",
                         lambda _: self._familia_mudou())
        ttk.Label(barra, text="   Grupo:").pack(side="left")
        self.var_gru = tk.StringVar(value=mn.TODOS)
        self.cb_gru = ttk.Combobox(barra, textvariable=self.var_gru, width=32,
                                   state="readonly", values=[mn.TODOS])
        self.cb_gru.pack(side="left", padx=6)
        self.cb_gru.bind("<<ComboboxSelected>>",
                         lambda _: self._desenhar_familia())
        # a MESMA variavel da aba 1: as duas leem a mesma passada pela
        # ftPedidos, entao o periodo tem de ser um so (ela nasce no
        # __init__, antes das abas)
        ttk.Label(barra, text="   Olhando os ultimos:").pack(side="left")
        cbd = ttk.Combobox(barra, textvariable=self.var_fam_dias, width=6,
                           state="readonly",
                           values=[str(d) for d in on.DIAS_DO_HISTORICO])
        cbd.pack(side="left", padx=6)
        cbd.bind("<<ComboboxSelected>>", lambda _: self.carregar_familia())
        ttk.Label(barra, text="dias", style="Sub.TLabel").pack(side="left")

        barra2 = ttk.Frame(f)
        barra2.pack(fill="x", pady=(0, 8))
        self.var_fam_nao = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra2, text="SO QUEM NAO COMPRA ESTA FAMILIA",
                        variable=self.var_fam_nao,
                        command=self._desenhar_familia).pack(side="left")
        self.var_fam_ativo = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra2, text="so quem comprou alguma coisa no "
                                     "periodo",
                        variable=self.var_fam_ativo,
                        command=self._desenhar_familia).pack(side="left",
                                                             padx=14)
        ttk.Label(barra2, text="   Segmento:").pack(side="left")
        self.var_fam_seg = tk.StringVar(value=mn.TODOS)
        self.cb_fam_seg = ttk.Combobox(
            barra2, textvariable=self.var_fam_seg, width=24,
            state="readonly",
            values=[mn.TODOS] + list(getattr(bp.nu, "SEGMENTOS", [])))
        self.cb_fam_seg.pack(side="left", padx=6)
        self.cb_fam_seg.bind("<<ComboboxSelected>>",
                             lambda _: self._desenhar_familia())
        ttk.Label(barra2, text="   Vendedor:").pack(side="left")
        self.var_fam_vend = tk.StringVar(value=mn.TODOS)
        self.cb_fam_vend = ttk.Combobox(barra2,
                                        textvariable=self.var_fam_vend,
                                        width=26, state="readonly",
                                        values=[mn.TODOS])
        self.cb_fam_vend.pack(side="left", padx=6)
        self.cb_fam_vend.bind("<<ComboboxSelected>>",
                              lambda _: self._desenhar_familia())
        ttk.Button(barra2, text="Limpar filtros",
                   command=self._limpar_familia).pack(side="left", padx=10)

        # o placar: quanto cada familia faturou no periodo
        self.lbl_fam_placar = ttk.Label(f, text="Clique em APURAR AGORA.",
                                        style="Cod.TLabel", wraplength=1400)
        self.lbl_fam_placar.pack(anchor="w", pady=(0, 6))

        quadro, self.tab_fam = bp.tabela(f, self.COLUNAS_FAM, rodape=True)
        quadro.pack(fill="both", expand=True)
        self.tab_fam.tag_configure("oportunidade", background="#FFF4D6")
        self.lbl_fam = ttk.Label(f, text="", style="Sub.TLabel",
                                 wraplength=1400)
        self.lbl_fam.pack(anchor="w", pady=(6, 0))
        bp.legenda_de_cores(f, [
            ("#FFF4D6", "OPORTUNIDADE: comprou da BAP no periodo, mas nunca "
                        "levou esta familia"),
        ]).pack(anchor="w", pady=(8, 0))

    def carregar_familia(self):
        if self.oportunidade is None:
            self.carregar_cliente()
            if self.oportunidade is None:
                return
        tabela = on.achar_tabela(AQUI)
        if tabela is None:
            messagebox.showwarning(
                "Oportunidades BAP",
                f"Nao achei a {on.ARQUIVO_TABELA} na pasta {pb.RELATORIOS}.")
            return
        dias = int(on._numero(self.var_fam_dias.get())
                   or on.DIAS_DO_HISTORICO_PADRAO)
        self.aviso(f"Lendo a venda item a item dos ultimos {dias} dias...",
                   COR_SUAVE)
        self.update_idletasks()
        try:
            self.compras = on.compras_por_familia(tabela, dias=dias)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        vends = sorted({f"{c.get('cod_vendedor') or ''} - "
                        f"{c.get('vendedor') or ''}".strip(" -")
                        for c in self.oportunidade} - {""})
        self.cb_fam_vend.configure(values=[mn.TODOS] + vends)
        self._familia_mudou()
        self.aviso(f"{self.compras['linhas']} item(ns) de nota lido(s) em "
                   f"{len(self.compras['clientes'])} cliente(s).", COR_OK)

    def _familia_mudou(self):
        """Trocou a familia: o GRUPO passa a listar so os dela."""
        familia = self.var_fam.get()
        grupos = [g for g in fam.ORDEM_GRUPO
                  if familia == mn.TODOS
                  or fam.FAMILIA_DO_GRUPO.get(g) == familia]
        self.cb_gru.configure(values=[mn.TODOS] + grupos)
        if self.var_gru.get() not in grupos:
            self.var_gru.set(mn.TODOS)
        self._desenhar_familia()

    def _limpar_familia(self):
        self.var_fam.set(mn.TODOS)
        self.var_gru.set(mn.TODOS)
        self.var_fam_nao.set(False)
        self.var_fam_ativo.set(False)
        self.var_fam_vend.set(mn.TODOS)
        self.var_fam_seg.set(mn.TODOS)
        self._familia_mudou()

    def _lista_familia(self) -> list:
        if not self.compras:
            return []
        familia = ("" if self.var_fam.get() == mn.TODOS
                   else self.var_fam.get())
        grupo = "" if self.var_gru.get() == mn.TODOS else self.var_gru.get()
        linhas = on.montar_familia_do_cliente(self.oportunidade or [],
                                              self.compras, familia, grupo)
        if self.var_fam_nao.get():
            linhas = [l for l in linhas if not l["comprou"]]
        if self.var_fam_ativo.get():
            linhas = [l for l in linhas if (l.get("valor_total") or 0) > 0]
        if self.var_fam_seg.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l.get("segmento") == self.var_fam_seg.get()]
        if self.var_fam_vend.get() != mn.TODOS:
            alvo = self.var_fam_vend.get()
            linhas = [l for l in linhas
                      if f"{l.get('cod_vendedor') or ''} - "
                         f"{l.get('vendedor') or ''}".strip(" -") == alvo]
        return linhas

    def _valores_fam(self, linha, total=False):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_FAM:
            v = linha.get(chave)
            if chave in ("valor_familia", "valor_total", "limite_disponivel"):
                saida.append(dinheiro(v) if v or total else "")
            elif chave == "perc_familia":
                saida.append(numero_br(v, 1) + "%" if v else "")
            elif chave == "skus_familia":
                saida.append(numero_br(v) if v else "")
            elif chave == "dias_familia":
                saida.append("nunca" if v is None and not total
                             else (numero_br(v) if v is not None else ""))
            else:
                saida.append("" if v is None else v)
        return saida

    def _total_fam(self, linhas) -> dict:
        valor = sum(l.get("valor_familia") or 0.0 for l in linhas)
        total = sum(l.get("valor_total") or 0.0 for l in linhas)
        return {"uf": "TOTAL", "cliente": f"{len(linhas)} cliente(s)",
                "comprou_txt": f"{sum(1 for l in linhas if l['comprou'])} SIM",
                "valor_familia": valor, "valor_total": total,
                "perc_familia": (valor / total * 100) if total else 0.0,
                "limite_disponivel": sum(l.get("limite_disponivel") or 0.0
                                         for l in linhas),
                "skus_familia": None, "dias_familia": None}

    def _desenhar_familia(self):
        if not self.compras:
            return
        linhas = self._lista_familia()
        self._familia_na_tela = linhas
        t = self.tab_fam
        self._silencio = True
        try:
            t.delete(*t.get_children())
            for i, l in enumerate(linhas):
                tags = ("oportunidade",) if l["oportunidade"] else (
                    ("zebra",) if i % 2 else ())
                # o iid leva o indice junto: o mesmo COD aparece duas vezes
                # quando o cliente tem mais de uma loja
                l["_iid"] = f"{i}|{l['cod_cliente']}"
                t.insert("", "end", iid=l["_iid"],
                         tags=tags, values=self._valores_fam(l))
            bp.escrever_total(t, self._valores_fam(self._total_fam(linhas),
                                                   total=True))
        finally:
            self._silencio = False
        # o placar por familia, que e a leitura de cima
        resumo = sorted(on.resumo_das_familias(self.compras),
                        key=lambda r: -r["valor"])
        pedacos = [f"{r['familia']} {r['perc']:.1f}%" for r in resumo[:8]]
        self.lbl_fam_placar.configure(
            text=f"Ultimos {self.compras['dias']} dias, por familia:   " +
                 "   ".join(pedacos))
        compraram = sum(1 for l in linhas if l["comprou"])
        oport = sum(1 for l in linhas if l["oportunidade"])
        alvo = (self.var_gru.get() if self.var_gru.get() != mn.TODOS
                else self.var_fam.get())
        self.lbl_fam.configure(
            text=f"{len(linhas)} cliente(s)   |   {compraram} compraram "
                 f"{alvo}   |   {len(linhas) - compraram} nao compraram"
                 f"   |   {oport} sao oportunidade (compram da BAP mas nao "
                 f"esta familia)   |   faturado no recorte "
                 f"{dinheiro(sum(l['valor_familia'] for l in linhas))}")

    def exportar_familia(self):
        if not self.compras:
            messagebox.showinfo("Oportunidades BAP",
                                "Clique em APURAR AGORA primeiro.")
            return
        linhas = self._na_ordem_da_tela(
            self.tab_fam, getattr(self, "_familia_na_tela", None)
            or self._lista_familia(), campo="_iid")
        alvo = (self.var_gru.get() if self.var_gru.get() != mn.TODOS
                else ("" if self.var_fam.get() == mn.TODOS
                      else self.var_fam.get()))
        destino = (AQUI / pb.RELATORIOS /
                   on.nome_do_arquivo_de_familia(alvo, self.compras["hoje"]))
        try:
            on.gravar_excel_familia(linhas, destino, self.compras,
                                    alvo or "(todas as familias)")
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"Lista gravada em {destino.name} "
                   f"({len(linhas)} cliente(s)).", COR_OK)

    def _montar_kits(self):
        f = self.aba_kit
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Sugestao de kits",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="EXPORTAR PARA APROVACAO",
                   style="Big.TButton",
                   command=self.exportar_kits).pack(side="right")
        ttk.Button(topo, text="GERAR PDF DOS KITS", style="Big.TButton",
                   command=self.imprimir_kits).pack(side="right", padx=8)
        ttk.Button(topo, text="MONTAR OS KITS",
                   command=self.carregar_kits).pack(side="right", padx=8)
        ttk.Button(topo, text="POR QUE NAO SAIU KIT?",
                   command=self.mostrar_faltas).pack(side="right")

        ttk.Label(f, text="Uma cesta fechada por FILIAL e por CATEGORIA, "
                          "montada so com o que esta na prateleira daquela "
                          "filial. O diretor comercial aprova UMA vez a cesta "
                          "e o desconto, e o vendedor sai vendendo a mesma "
                          "cesta a semana inteira. As regras estao na aba 4.",
                  style="Sub.TLabel", wraplength=1350).pack(anchor="w",
                                                            pady=(4, 10))

        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Regiao:").pack(side="left")
        self.var_kit_regiao = tk.StringVar(value=mn.TODOS)
        self.cb_kit_regiao = ttk.Combobox(
            barra, textvariable=self.var_kit_regiao, width=24,
            state="readonly", values=[mn.TODOS])
        self.cb_kit_regiao.pack(side="left", padx=6)
        self.cb_kit_regiao.bind("<<ComboboxSelected>>",
                                lambda _: self._desenhar_kits())
        ttk.Label(barra, text="   Categoria:").pack(side="left")
        self.var_kit_cat = tk.StringVar(value=mn.TODOS)
        self.cb_kit_cat = ttk.Combobox(barra, textvariable=self.var_kit_cat,
                                       width=18, state="readonly",
                                       values=[mn.TODOS])
        self.cb_kit_cat.pack(side="left", padx=6)
        self.cb_kit_cat.bind("<<ComboboxSelected>>",
                             lambda _: self._desenhar_kits())
        ttk.Button(barra, text="Limpar filtros",
                   command=self._limpar_kits).pack(side="left", padx=6)

        # as duas visoes: o RESUMO e por onde se aprova, o DETALHAMENTO e
        # o que vai dentro da cesta
        self.abas_kit = ttk.Notebook(f)
        self.abas_kit.pack(fill="both", expand=True)
        q_res = ttk.Frame(self.abas_kit, padding=10)
        q_det = ttk.Frame(self.abas_kit, padding=10)
        self.abas_kit.add(q_res, text="RESUMO GERENCIAL")
        self.abas_kit.add(q_det, text="DETALHAMENTO")

        quadro, self.tab_res = bp.tabela(q_res, self.COLUNAS_RES,
                                         rodape=True)
        quadro.pack(fill="both", expand=True)
        self.tab_res.tag_configure("incompleto", background=COR_AVISO)
        self.tab_res.bind("<<TreeviewSelect>>",
                          lambda _: self._kit_escolhido())

        quadro, self.tab_det = bp.tabela(q_det, self.COLUNAS_DET,
                                         rodape=True)
        quadro.pack(fill="both", expand=True)
        self.tab_det.tag_configure("herdou", background="#EEF6EA")

        # Embaixo da tabela fica SO a mecanica do ROI, em negrito, e a
        # legenda das cores. Os numeros de diagnostico (quantos produtos
        # ficaram de fora e por que) sairam daqui para o botao
        # POR QUE NAO SAIU KIT? - la eles cabem inteiros.
        self.lbl_kit = ttk.Label(f, text="", style="Secao.TLabel",
                                 wraplength=1350)
        self.lbl_kit.pack(anchor="w", pady=(6, 0))
        bp.legenda_de_cores(f, [
            (COR_AVISO, "kit INCOMPLETO: nao deu para fechar a quantidade "
                        "pedida - faltou produto com estoque naquela "
                        "filial"),
            ("#EEF6EA", "a linha herdou a vaga de uma curva que nao tinha "
                        "produto naquela filial"),
        ]).pack(anchor="w", pady=(8, 0))

    def carregar_kits(self):
        if self.estoque is None:
            self.carregar_estoque()
            if self.estoque is None:
                return
        csv_cat = mn.achar_csv_de_categorias(AQUI)
        self.categorias = (on.ler_categoria_dos_produtos(csv_cat)
                           if csv_cat else {})
        if not self.categorias:
            messagebox.showwarning(
                "Oportunidades BAP",
                "Sem o CATEGORIAS_PRODUTO.csv na pasta nao da para montar "
                "kit: e ele que diz se o produto e peca, oleo, bateria ou "
                "pneu.\n\nExporte o 'Estoque Total' do sistema e salve como "
                "CATEGORIAS_PRODUTO.csv aqui na pasta.")
            return
        self._ler_kit_dos_campos()
        self.kits = on.montar_kits(self.estoque, self.categorias,
                                   self.par.get("kit") or {})
        regioes = sorted({r["regiao"] for r in self.kits["resumo"]})
        self.cb_kit_regiao.configure(values=[mn.TODOS] + regioes)
        cats = sorted({r["rotulo"] for r in self.kits["resumo"]})
        self.cb_kit_cat.configure(values=[mn.TODOS] + cats)
        self._desenhar_kits()
        if "kit" in (self.ABAS_VISIVEIS or ("kit",)):
            self.abas.select(self.aba_kit)          # a aba dos kits
        self.aviso(f"{len(self.kits['resumo'])} kit(s) montado(s), "
                   f"{len(self.kits['detalhe'])} linha(s).", COR_OK)

    def _limpar_kits(self):
        self.var_kit_regiao.set(mn.TODOS)
        self.var_kit_cat.set(mn.TODOS)
        self._desenhar_kits()

    def _resumo_filtrado(self) -> list:
        linhas = list((self.kits or {}).get("resumo") or [])
        if self.var_kit_regiao.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l["regiao"] == self.var_kit_regiao.get()]
        if self.var_kit_cat.get() != mn.TODOS:
            linhas = [l for l in linhas
                      if l["rotulo"] == self.var_kit_cat.get()]
        return linhas

    def _detalhe_filtrado(self, so_kit="") -> list:
        nomes = {l["kit"] for l in self._resumo_filtrado()}
        linhas = [l for l in ((self.kits or {}).get("detalhe") or [])
                  if l["kit"] in nomes]
        if so_kit:
            linhas = [l for l in linhas if l["kit"] == so_kit]
        return linhas

    def _kit_escolhido(self):
        """Clicou num kit do resumo: o detalhamento abre so naquele."""
        if self._silencio or not self.kits:
            return
        marcado = self.tab_res.focus()
        self._desenhar_detalhe(marcado if marcado != "TOTAL" else "")
        if marcado:
            self.abas_kit.select(1)

    def _desenhar_kits(self):
        if not self.kits:
            return
        linhas = self._resumo_filtrado()
        t = self.tab_res
        self._silencio = True
        try:
            t.delete(*t.get_children())
            for i, l in enumerate(linhas):
                tags = ("incompleto",) if not l["completo"] else (
                    ("zebra",) if i % 2 else ())
                t.insert("", "end", iid=l["kit"], tags=tags,
                         values=self._valores_res(l))
            bp.escrever_total(t, self._valores_res(self._total_res(linhas),
                                                   total=True))
        finally:
            self._silencio = False
        self._desenhar_detalhe()
        self.lbl_kit.configure(text=self.MECANICA_DO_ROI)

    def _desenhar_detalhe(self, so_kit=""):
        linhas = self._detalhe_filtrado(so_kit)
        t = self.tab_det
        self._silencio = True
        try:
            t.delete(*t.get_children())
            for i, l in enumerate(linhas):
                tags = ("herdou",) if l["herdou"] else (
                    ("zebra",) if i % 2 else ())
                t.insert("", "end", iid=f"{l['kit']}|{l['produto']}",
                         tags=tags, values=self._valores_det(l))
            bp.escrever_total(t, self._valores_det(self._total_det(linhas),
                                                   total=True))
        finally:
            self._silencio = False

    # A unica frase que fica embaixo da tabela, em negrito: de onde sai o
    # numero que o diretor olha primeiro.
    MECANICA_DO_ROI = (
        "QTD = quantas unidades do item vao em UM kit - lubrificante vai "
        "em CAIXA FECHADA, entao um oleo de caixa 24 entra com 24   |   "
        "VLR UNIT. = quanto UMA unidade custa no kit   |   "
        "P. PEDIDO, VLR TAB. C/ 15% e DESC. R$ ja vem multiplicados pela "
        "QTD   |   VLR TOTAL = QTD KITS x VLR KIT   |   "
        "INVEST. R$ = o que a verba paga: QTD KITS x DESC. R$"
        "   |   MKP TT R$ = VLR TOTAL menos o P. PEDIDO da quantidade "
        "toda   |   ROI % = MKP TT R$ / INVEST. R$   |   "
        "o P. PEDIDO da bateria ja inclui a SUCATA que vai junto para a "
        "fabrica, e dai para a frente ela segue a regra das outras."
    )

    def _porque_faltou(self) -> str:
        """
        A pergunta que vem depois de todo kit que nao sai e sempre a
        mesma - por que nao saiu? Aqui ela ja vem respondida, com o
        numero na frente, em vez de virar meia hora de investigacao.
        """
        if not self.kits:
            return ""
        recado = ""
        barrados = self.kits.get("barrados_estoque") or 0
        minimo = self.kits.get("estoque_minimo") or 0
        if barrados:
            recado += (f"   {barrados} produto(s) ficaram de fora por nao "
                       f"chegar ao ESTOQUE MINIMO de {minimo:.0f} (aba 4).")
        if self.kits.get("barrados_preco"):
            recado += (f"   {self.kits['barrados_preco']} nao tem preco na "
                       f"tabela escolhida.")
        if self.kits.get("sem_categoria"):
            recado += (f"   {self.kits['sem_categoria']} nao tem categoria "
                       f"no CATEGORIAS_PRODUTO.csv.")
        if self.kits.get("barrados_markup"):
            recado += (f"   {self.kits['barrados_markup']} ficaram de fora "
                       f"pela TRAVA DO MARKUP: nem no preco de tabela "
                       f"alcancam o markup minimo da curva.")
        if self.kits.get("sem_caixa_cheia"):
            recado += (f"   {self.kits['sem_caixa_cheia']} lubrificante(s) "
                       f"nao tem estoque para uma CAIXA inteira.")
        # CATEGORIA COM VERBA E SEM KIT: e a que some da tela levando a
        # verba junto, sem dizer nada. Agora ela diz.
        for falta in (self.kits.get("faltas") or []):
            if falta.get("verba_parada"):
                rotulo = dict(on.CATEGORIAS_KIT).get(falta["categoria"],
                                                     falta["categoria"])
                recado += (f"   ATENCAO: {rotulo} esta marcada com "
                           f"{dinheiro(falta['verba_parada'])} de verba e "
                           f"nao gerou kit nenhum - {falta['motivo']}.")
        return recado

    def _resumo_da_rodada(self) -> str:
        """Os numeros que saiam embaixo da tabela e agora vivem aqui."""
        linhas = self.kits.get("resumo") or []
        motivos = self._porque_faltou().strip()
        if not linhas:
            # nenhum kit saiu: o que interessa e exatamente o porque
            return ("Nenhum kit saiu nesta rodada."
                    + (f"\n\n{motivos}" if motivos else ""))
        investido = sum(l["valor_investido"] for l in linhas)
        kits = sum(l["kits_liberados"] or 0 for l in linhas)
        incompletos = [l for l in linhas if not l["completo"]]
        # ONDE A VERBA FICOU. A pergunta "pedi 15 mil, por que saiu 10?"
        # tem tres respostas possiveis, e as tres aparecem aqui:
        #   1. categoria com verba e sem produto nenhum (verba parada)
        #   2. o resto que nao fecha mais um kit inteiro
        #   3. o que foi de fato investido
        chegou = sum(l["verba_da_filial"] for l in linhas)
        parada = self.kits.get("verba_parada") or 0.0
        sobra = max(0.0, chegou - investido)
        conta = [f"verba posta nas categorias que geraram kit "
                 f"{dinheiro(chegou)}"]
        if parada:
            conta.append(f"{dinheiro(parada)} de categoria sem produto "
                         f"nenhum (ver abaixo)")
        conta.append(f"investido {dinheiro(investido)}")
        if sobra > 0.005:
            conta.append(f"{dinheiro(sobra)} nao fecharam mais um kit "
                         f"inteiro")
        return (
            f"{len(linhas)} kit(s)   |   {kits} kit(s) liberado(s) para "
            f"venda\n"
            + "   |   ".join(conta)
            + f"\nROI previsto "
              f"{dinheiro(sum(l.get('roi_previsto') or 0 for l in linhas))}"
            f"   |   desconto do gerente por curva: "
            + ", ".join(f"{c} {v:.0f}%" for c, v
                        in (self.kits.get("desc_gerente") or {}).items())
            + (f"   |   {len(incompletos)} kit(s) nao fecharam a quantidade "
               f"pedida." if incompletos else "")
            + (f"\n\n{motivos}" if motivos else ""))

    def mostrar_faltas(self):
        """A lista do que nao virou kit, e o motivo de cada um."""
        faltas = (self.kits or {}).get("faltas") or []
        if not self.kits:
            messagebox.showinfo("Oportunidades BAP",
                                "Clique em MONTAR OS KITS primeiro.")
            return
        cabeca = self._resumo_da_rodada()
        if not faltas:
            messagebox.showinfo(
                "Oportunidades BAP",
                (cabeca + "\n\n" if cabeca else "")
                + "Toda combinacao de filial e categoria que tem produto no "
                  "estoque gerou kit.")
            return
        cabeca = (cabeca + "\n\n") if cabeca else ""
        titulos = dict(on.CATEGORIAS_KIT)
        linhas = [f"{f['regiao']}  /  "
                  f"{titulos.get(f['categoria'], f['categoria'])}\n"
                  f"      {f['motivo']}" for f in faltas[:24]]
        resto = (f"\n\n... e mais {len(faltas) - 24} combinacao(oes)."
                 if len(faltas) > 24 else "")
        messagebox.showinfo(
            "Oportunidades BAP",
            cabeca
            + f"{len(faltas)} combinacao(oes) de filial e categoria tem "
              f"produto no estoque mas NAO geraram kit:\n\n"
            + "\n".join(linhas) + resto
            + f"\n\nO ESTOQUE MINIMO esta em "
              f"{self.kits.get('estoque_minimo', 0):.0f}: quanto maior, "
              f"menos produto sobra para montar cesta.")

    DINHEIRO_RES = ("valor_tabela", "valor_unit", "valor_total",
                    "valor_acao", "custo_total", "custo_por_kit",
                    "custo_liberado", "valor_total_tabela", "roi_previsto",
                    "valor_kit_total", "verba_do_kit", "custo_total_tt")
    PERCENTO_RES = ("markup_normal", "markup_acao", "desconto",
                    "markup_tt_pct", "roi_pct")
    DINHEIRO_DET = DINHEIRO_RES + ("preco_tabela", "preco_final",
                                   "desc_unit", "custo_unit", "sucata",
                                   "valor_unit")
    PERCENTO_DET = PERCENTO_RES
    # as colunas que contam peca, e nao dinheiro
    CONTAGEM_KIT = ("quantidade", "qtd_total", "kits_liberados",
                    "sobra_da_caixa")

    def _total_res(self, linhas) -> dict:
        soma = {"kit": f"TOTAL ({len(linhas)} kits)", "regiao": "",
                "rotulo": "", "familia": "",
                "quantidade": sum(l.get("quantidade") or 0 for l in linhas),
                "qtd_total": sum(l.get("qtd_total") or 0 for l in linhas),
                "kits_liberados_txt": sum(l.get("kits_liberados") or 0
                                          for l in linhas)}
        for campo in self.DINHEIRO_RES + ("valor_venda",):
            soma[campo] = sum(l.get(campo) or 0 for l in linhas)
        # os percentuais do total saem das colunas POR KIT, que ficam
        # ali do lado somadas - da para conferir dividindo duas celulas
        on._totais_do_conjunto(soma)
        # As tres colunas POR KIT sao valor de UM kit: somar 21 delas nao
        # da numero nenhum. O que fecha em baixo e o que ja e TOTAL.
        return soma

    def _total_det(self, linhas) -> dict:
        # VLR UNIT. nao entra no total: somar preco de uma unidade de
        # bateria com o de um litro de oleo nao quer dizer nada
        soma = {"kit": "TOTAL", "regiao": "", "rotulo_cat": "",
                "familia": "", "descricao": f"{len(linhas)} linha(s)",
                "preco_final": None}
        for campo in self.CONTAGEM_KIT + self.DINHEIRO_DET:
            soma[campo] = sum(l.get(campo) or 0 for l in linhas)
        # a QTD KIT ORCADA nao se soma linha a linha: as cinco linhas de
        # um kit de oito repetem o mesmo 8
        soma["kits_liberados"] = on._kits_do_conjunto(linhas)
        soma["kits_liberados_txt"] = soma["kits_liberados"]
        on._totais_do_conjunto(soma)
        return soma

    def _valores_res(self, linha, total=False):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_RES:
            v = linha.get(chave)
            if chave in self.DINHEIRO_RES:
                saida.append("" if v is None else dinheiro(v))
            elif chave in self.PERCENTO_RES:
                saida.append("" if v is None
                             else (numero_br(v, 2) if v else "0,00"))
            elif chave == "kits_liberados_txt":
                # sem verba consumida a conta nao tem teto: a alcada do
                # gerente ja cobriu o desconto inteiro
                saida.append(v if isinstance(v, str) else numero_br(v or 0))
            elif chave in self.CONTAGEM_KIT or chave in ("itens",
                                                         "unidades"):
                saida.append(f"{int(round(v)):,}".replace(",", ".")
                             if v else ("" if v is None else "0"))
            else:
                saida.append(v)
        return saida

    def _valores_det(self, linha, total=False):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_DET:
            v = linha.get(chave)
            if chave in self.DINHEIRO_DET:
                saida.append("" if v is None else dinheiro(v))
            elif chave in self.PERCENTO_DET:
                saida.append("" if v is None
                             else (numero_br(v, 2) if v
                                   else ("" if total else "0,00")))
            elif chave in self.CONTAGEM_KIT:
                saida.append(f"{int(round(v)):,}".replace(",", ".")
                             if v else "")
            else:
                saida.append(v if v is not None else "")
        return saida

    def exportar_kits(self):
        if not self.kits or not self.kits["resumo"]:
            messagebox.showinfo("Oportunidades BAP",
                                "Clique em MONTAR OS KITS primeiro.")
            return
        filtrado = {**self.kits,
                    "resumo": self._resumo_filtrado(),
                    "detalhe": self._detalhe_filtrado()}
        destino = (AQUI / pb.RELATORIOS /
                   on.nome_do_arquivo_de_kits(self.kits["hoje"]))
        try:
            on.gravar_excel_kits(filtrado, self.par,
                                 self.par.get("kit") or {}, destino)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado com "
                   f"{len(filtrado['resumo'])} kit(s).", COR_OK)
        messagebox.showinfo(
            "Oportunidades BAP",
            f"{destino.name}\n\n{len(filtrado['resumo'])} kit(s) para o "
            f"diretor comercial aprovar.\n\nRESUMO GERENCIAL na frente - e "
            f"por ele que se aprova; DETALHAMENTO atras, com o que vai na "
            f"cesta; e a aba PARAMETROS dizendo com que regra tudo foi "
            f"montado.\n\nGravado em:\n{destino.parent}")

    def imprimir_kits(self):
        """
        A folha de aprovacao: RESUMO na primeira pagina - e por ele que
        o diretor assina - e depois uma pagina por kit com os produtos.

        Abre no NAVEGADOR em vez de gerar o .pdf direto, para nao
        precisar de biblioteca nenhuma nos notebooks: o Ctrl+P do
        proprio navegador salva em PDF ja no A4 deitado.
        """
        if not self.kits or not self.kits["resumo"]:
            messagebox.showinfo("Oportunidades BAP",
                                "Clique em MONTAR OS KITS primeiro.")
            return
        resumo = self._resumo_filtrado()
        if not resumo:
            messagebox.showinfo("Oportunidades BAP",
                                "Nenhum kit neste filtro - nao ha o que "
                                "imprimir.")
            return
        destino = (AQUI / pb.RELATORIOS /
                   on.nome_da_folha_de_kits(self.kits["hoje"]))
        verba = sum(r.get("custo_liberado") or 0.0 for r in resumo)
        subtitulo = (f"{len(resumo)} kit(s)   |   investimento "
                     f"{dinheiro(verba)}   |   "
                     f"gerado em {self.kits['hoje']:%d/%m/%Y}")
        try:
            on.gravar_folha_de_kits(self.kits, destino, resumo,
                                    self._detalhe_filtrado(), subtitulo)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Oportunidades BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        self.aviso(f"{destino.name}: {len(resumo)} kit(s). Abrindo no "
                   f"navegador - use Ctrl+P e 'Salvar como PDF'.", COR_OK)
        bp.App._abrir(destino)

    # ================================================================== 4
    def _rolagem(self, pai):
        """
        Um quadro que ROLA. A aba de parametros nao cabe numa tela de
        notebook, e uma tela que nao cabe e sem barra e uma tela que
        esconde campo - foi exatamente isso que aconteceu com a cota das
        curvas. Aqui ela rola com a roda do mouse e com a barra.
        """
        fora = ttk.Frame(pai)
        fora.pack(fill="both", expand=True)
        tela = tk.Canvas(fora, background=COR_FUNDO, highlightthickness=0)
        barra = ttk.Scrollbar(fora, orient="vertical", command=tela.yview)
        dentro = ttk.Frame(tela)
        janela = tela.create_window((0, 0), window=dentro, anchor="nw")
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        def ajustar(_=None):
            tela.configure(scrollregion=tela.bbox("all"))
            tela.itemconfigure(janela, width=tela.winfo_width())

        dentro.bind("<Configure>", ajustar)
        tela.bind("<Configure>", ajustar)

        def roda(evento):
            passo = -1 if getattr(evento, "delta", 0) > 0 or \
                evento.num == 4 else 1
            tela.yview_scroll(passo, "units")

        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            tela.bind_all(evento, roda, add="+")
        return dentro

    def _montar_parametros(self):
        f = self._rolagem(self.aba_par)
        ttk.Label(f, text="Parametros",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(f, text="A CURVA DO PRODUTO nao e a curva do cliente: ela "
                          "diz com que frequencia o item gira, olhando "
                          "SEMPRE de HOJE para tras. O corte de cada letra e "
                          "em DIAS desde a ultima venda, e vale nas duas "
                          "curvas - a da filial e a geral.",
                  style="Sub.TLabel", wraplength=1300).pack(anchor="w",
                                                            pady=(2, 12))

        # DUAS COLUNAS: empilhado, isto nao cabia na tela
        corpo = ttk.Frame(f)
        corpo.pack(fill="both", expand=True)
        esq = ttk.Frame(corpo)
        esq.pack(side="left", fill="both", expand=True, padx=(0, 14))
        dir_ = ttk.Frame(corpo)
        dir_.pack(side="left", fill="both", expand=True)

        # ---- esquerda: a curva e o preco --------------------------------
        quadro = ttk.LabelFrame(esq, text=" A curva do produto ", padding=12)
        quadro.pack(fill="x")
        for j, titulo in enumerate(("CURVA", "ATE QUANTOS DIAS",
                                    "O QUE ISSO QUER DIZER")):
            ttk.Label(quadro, text=titulo, style="Sub.TLabel").grid(
                row=0, column=j, sticky="w", padx=(0, 10), pady=(0, 6))
        self.var_curva = []
        for i, faixa in enumerate(self.par.get("curvas") or on.CURVAS_PADRAO):
            ttk.Label(quadro, text=f"CURVA {faixa['letra']}",
                      style="Cod.TLabel").grid(row=i + 1, column=0,
                                               sticky="w", pady=4,
                                               padx=(0, 12))
            v = tk.StringVar(value=str(int(on._numero(faixa.get("dias")))))
            self.var_curva.append((faixa["letra"], v))
            ttk.Entry(quadro, textvariable=v, width=8,
                      justify="right").grid(row=i + 1, column=1, sticky="w",
                                            padx=(0, 10))
            ttk.Label(quadro, text=faixa.get("texto", ""),
                      style="Sub.TLabel", wraplength=300).grid(
                          row=i + 1, column=2, sticky="w")
        n = len(self.var_curva) + 1
        ttk.Label(quadro, text=f"CURVA {on.LETRA_PARADO}",
                  style="Cod.TLabel").grid(row=n, column=0, sticky="w",
                                           pady=4, padx=(0, 12))
        ttk.Label(quadro, text="o que sobrar", style="Sub.TLabel").grid(
            row=n, column=1, sticky="w")
        ttk.Label(quadro, text=on.TEXTO_PARADO, style="Sub.TLabel",
                  wraplength=300).grid(row=n, column=2, sticky="w")
        self.lbl_curva = ttk.Label(quadro, text="", style="Sub.TLabel",
                                   wraplength=440)
        self.lbl_curva.grid(row=n + 1, column=0, columnspan=3, sticky="w",
                            pady=(10, 0))
        quadro.columnconfigure(2, weight=1)

        quadro2 = ttk.LabelFrame(esq, text=" A tabela de preco ", padding=12)
        quadro2.pack(fill="x", pady=(12, 0))
        ttk.Label(quadro2, text="Na TABELA_BAP as tabelas se chamam AM1, "
                                "AM2, PA1, PA2... O NUMERO NO FIM diz se e "
                                "capital ou interior. Diga aqui qual e qual - "
                                "isso e regra de negocio, nao da para "
                                "adivinhar.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=0, column=0, columnspan=2, sticky="w",
                      pady=(0, 10))
        self.var_sufixo = {}
        for i, (chave, rotulo) in enumerate(
                (("sufixo_capital", "Tabela de CAPITAL termina em:"),
                 ("sufixo_interior", "Tabela de INTERIOR termina em:"))):
            ttk.Label(quadro2, text=rotulo).grid(row=i + 1, column=0,
                                                 sticky="w", pady=4)
            v = tk.StringVar(value=str(self.par.get(chave) or ""))
            self.var_sufixo[chave] = v
            ttk.Entry(quadro2, textvariable=v, width=8,
                      justify="center").grid(row=i + 1, column=1, sticky="w",
                                             padx=8)
        self.var_so_estoque = tk.StringVar(
            value="SIM" if self.par.get("so_com_estoque", True) else "NAO")
        ttk.Label(quadro2, text="Mostrar so o que TEM estoque?").grid(
            row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(quadro2, textvariable=self.var_so_estoque, width=8,
                     state="readonly", values=["SIM", "NAO"]).grid(
                         row=3, column=1, sticky="w", padx=8, pady=(8, 0))
        quadro2.columnconfigure(0, weight=1)

        # ---- quem entra na acao ------------------------------------------
        quadro_fil = ttk.LabelFrame(
            esq, text=" Filiais que entram na acao ", padding=12)
        quadro_fil.pack(fill="x", pady=(12, 0))
        ttk.Label(quadro_fil,
                  text="Marque as filiais que vao receber kit nesta acao. "
                       "Filial desmarcada nao monta kit de categoria "
                       "nenhuma. Com NENHUMA marcada, vale a rede inteira - "
                       "quem nunca abriu este campo nao fica sem kit.",
                  style="Sub.TLabel", wraplength=440).pack(anchor="w",
                                                           pady=(0, 8))
        botoes_fil = ttk.Frame(quadro_fil)
        botoes_fil.pack(fill="x", pady=(0, 6))
        ttk.Button(botoes_fil, text="MARCAR TODAS",
                   command=lambda: self._marcar_filiais(True)).pack(
                       side="left")
        ttk.Button(botoes_fil, text="DESMARCAR TODAS",
                   command=lambda: self._marcar_filiais(False)).pack(
                       side="left", padx=8)
        self.quadro_filiais = ttk.Frame(quadro_fil)
        self.quadro_filiais.pack(fill="x")
        self.var_filial = {}
        self._desenhar_filiais()

        # ---- direita: o kit ---------------------------------------------
        kit = self.par.get("kit") or on.kit_padrao()
        quadro3 = ttk.LabelFrame(dir_, text=" A montagem do kit ", padding=12)
        quadro3.pack(fill="x")
        self.var_kit = {}
        for i, (chave, rotulo, ajuda) in enumerate((
                ("itens_no_kit", "Quantos PRODUTOS (SKUs) no kit:",
                 "o kit fecha quando chega nesta conta"),
                ("estoque_minimo", "Estoque minimo por produto:",
                 "so entra no kit o que tem pelo menos isso na filial"))):
            ttk.Label(quadro3, text=rotulo).grid(row=i * 2, column=0,
                                                 sticky="w", pady=(5, 0))
            v = tk.StringVar(value=str(kit.get(chave) or ""))
            self.var_kit[chave] = v
            ttk.Entry(quadro3, textvariable=v, width=13,
                      justify="right").grid(row=i * 2, column=1, padx=8,
                                            sticky="w")
            ttk.Label(quadro3, text=ajuda, style="Sub.TLabel",
                      wraplength=430).grid(row=i * 2 + 1, column=0,
                                           columnspan=2, sticky="w")
        ttk.Label(quadro3, text="Considerar a curva:").grid(row=4, column=0,
                                                            sticky="w",
                                                            pady=(8, 0))
        self.var_usar_curva = tk.StringVar(
            value="POR FILIAL" if kit.get("usar_curva") != "geral"
            else "GERAL DA BAP")
        ttk.Combobox(quadro3, textvariable=self.var_usar_curva, width=14,
                     state="readonly",
                     values=["POR FILIAL", "GERAL DA BAP"]).grid(
                         row=4, column=1, padx=8, sticky="w", pady=(8, 0))
        ttk.Label(quadro3, text="POR FILIAL monta com o giro daquela loja; "
                                "GERAL, com o giro da rede",
                  style="Sub.TLabel", wraplength=430).grid(
                      row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(quadro3, text="Preco de tabela do kit:").grid(
            row=6, column=0, sticky="w", pady=(8, 0))
        self.var_preco_base = tk.StringVar(
            value=str(kit.get("preco_base") or "capital").upper())
        ttk.Combobox(quadro3, textvariable=self.var_preco_base, width=14,
                     state="readonly", values=["CAPITAL", "INTERIOR"]).grid(
                         row=6, column=1, padx=8, sticky="w", pady=(8, 0))
        quadro3.columnconfigure(0, weight=1)

        quadro4 = ttk.LabelFrame(dir_, text=" Quanto de cada curva entra no "
                                            "kit, e com que desconto ",
                                 padding=12)
        quadro4.pack(fill="x", pady=(12, 0))
        ttk.Label(quadro4, text="Se faltar produto numa curva, a vaga passa "
                                "para a proxima: bater a quantidade do kit "
                                "vale mais que respeitar a divisao.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=0, column=0, columnspan=6, sticky="w",
                      pady=(0, 8))
        for j, titulo in enumerate(("CURVA", "QTD DE SKUS", "QTD DO ITEM",
                                    "% DESC. GERENTE", "% DESCONTO",
                                    "% MARKUP MIN")):
            ttk.Label(quadro4, text=titulo, style="Sub.TLabel").grid(
                row=1, column=j, sticky="w", padx=(0, 10))
        self.var_cota = {}
        cotas = kit.get("cotas") or {}
        for i, curva in enumerate(on.ORDEM_DAS_CURVAS):
            regra = cotas.get(curva) or {}
            ttk.Label(quadro4, text=f"CURVA {curva}",
                      style="Cod.TLabel").grid(row=i + 2, column=0,
                                               sticky="w", pady=3,
                                               padx=(0, 12))
            campos = {}
            for j, campo in enumerate(("skus", "qtd", "desc_gerente",
                                       "desconto", "markup_min")):
                v = tk.StringVar(value=str(regra.get(campo) or 0))
                campos[campo] = v
                ttk.Entry(quadro4, textvariable=v, width=11,
                          justify="right").grid(row=i + 2, column=j + 1,
                                                padx=(0, 10), sticky="w")
            self.var_cota[curva] = campos
        ttk.Label(quadro4, text="% DESC. GERENTE sai do preco de tabela "
                                "ANTES de montar o kit - ele nao aparece em "
                                "coluna nenhuma: o VLR. UNIT. TABELA ja vem "
                                "sem ele. O % DESCONTO e o da ACAO, em cima "
                                "desse preco, e e ele inteiro que a verba "
                                "paga.\n"
                                "% MARKUP MIN e a TRAVA: nenhum item sai do "
                                "kit abaixo desse markup. Desconto que "
                                "derrubaria o markup encolhe ate o piso, e "
                                "quem nem no preco de partida alcanca o piso "
                                "fica de fora.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=len(on.ORDEM_DAS_CURVAS) + 2, column=0,
                      columnspan=6, sticky="w", pady=(8, 0))
        # a folga vai para uma coluna VAZIA no fim: se ela fosse a do
        # % MARKUP MIN, a caixinha escorregava para longe do titulo
        quadro4.columnconfigure(6, weight=1)

        quadro5 = ttk.LabelFrame(dir_, text=" Valor de investimento por "
                                            "categoria ", padding=12)
        quadro5.pack(fill="x", pady=(12, 0))
        ttk.Label(quadro5, text="E daqui que sai QUANTOS KITS podem ir para "
                                "a rua: a verba da categoria dividida pelo "
                                "valor do kit.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=0, column=0, columnspan=2, sticky="w",
                      pady=(0, 8))
        self.var_verba = {}
        self.var_gerar = {}
        self.var_verba_geral = {}
        verbas = kit.get("investimento") or {}
        geral = {**on.kit_padrao()["verba_geral"],
                 **(kit.get("verba_geral") or {})}
        ligadas = {**on.kit_padrao()["gerar"], **(kit.get("gerar") or {})}
        for j, titulo in enumerate(("GERAR?", "CATEGORIA", "VERBA (R$)",
                                    "A VERBA E")):
            ttk.Label(quadro5, text=titulo, style="Sub.TLabel").grid(
                row=1, column=j, sticky="w", padx=(0, 8))
        for i, (chave, rotulo) in enumerate(on.CATEGORIAS_KIT):
            marcado = tk.BooleanVar(value=bool(ligadas.get(chave, True)))
            self.var_gerar[chave] = marcado
            ttk.Checkbutton(quadro5, variable=marcado).grid(
                row=i + 2, column=0, sticky="w", pady=3)
            ttk.Label(quadro5, text=rotulo).grid(row=i + 2, column=1,
                                                 sticky="w", pady=3)
            v = tk.StringVar(value=str(verbas.get(chave) or 0))
            self.var_verba[chave] = v
            ttk.Entry(quadro5, textvariable=v, width=13,
                      justify="right").grid(row=i + 2, column=2, padx=8,
                                            sticky="w")
            g = tk.StringVar(value="GERAL" if geral.get(chave, True)
                             else "POR FILIAL")
            self.var_verba_geral[chave] = g
            ttk.Combobox(quadro5, textvariable=g, width=11, state="readonly",
                         values=["GERAL", "POR FILIAL"]).grid(
                             row=i + 2, column=3, sticky="w")
        ttk.Label(quadro5, text="GERAL = o valor e da rede inteira e se "
                                "divide entre os kits da categoria. POR "
                                "FILIAL = o valor vale para CADA filial. "
                                "Categoria desmarcada nao gera kit.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=len(on.CATEGORIAS_KIT) + 2, column=0, columnspan=4,
                      sticky="w", pady=(8, 0))
        quadro5.columnconfigure(1, weight=1)

        quadro6 = ttk.LabelFrame(esq, text=" Kit de peca por familia ",
                                 padding=12)
        quadro6.pack(fill="x", pady=(12, 0))
        self.var_por_familia = tk.StringVar(
            value="SIM" if kit.get("por_familia") else "NAO")
        ttk.Label(quadro6, text="Quebrar as PECAS por familia?").grid(
            row=0, column=0, sticky="w")
        ttk.Combobox(quadro6, textvariable=self.var_por_familia, width=8,
                     state="readonly", values=["NAO", "SIM"]).grid(
                         row=0, column=1, padx=8, sticky="w")
        ttk.Label(quadro6, text="Em SIM, cada familia de peca vira um kit "
                                "proprio - AMORTECEDOR, FILTRO, JOGO "
                                "PASTILHA, TERMINAL... A familia sai da "
                                "descricao do produto. Vale so para as tres "
                                "categorias de PECA; bateria, pneu e "
                                "lubrificante seguem com um kit cada.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        quadro6.columnconfigure(0, weight=1)

        quadro7 = ttk.LabelFrame(esq, text=" A caixa do lubrificante ",
                                 padding=12)
        quadro7.pack(fill="x", pady=(12, 0))
        # A CAIXA NAO E MAIS OPCIONAL. Oleo nao se compra quebrado, e
        # ponto - o que ficou configuravel e o TAMANHO da caixa de cada
        # familia, na tabela aqui embaixo. O antigo SIM/NAO saiu: com ele
        # em NAO o pedido saia com 29 litros de um oleo de caixa 24.
        ttk.Label(quadro7, text="Oleo nao se compra quebrado. A QTD A "
                                "COMPRAR de cada item - que e a QTD do kit "
                                "vezes a QTD DE KITS ORCADA - sobe sempre "
                                "ate fechar a caixa, mesmo que passe um "
                                "pouco da verba. O que sobra fica de "
                                "estoque na filial. Aqui se diz o tamanho "
                                "da caixa de cada familia.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
        for j, titulo in enumerate(("GRUPO", "UN/CAIXA", "RECONHECE PELA "
                                    "DESCRICAO (separe por virgula)")):
            ttk.Label(quadro7, text=titulo, style="Sub.TLabel").grid(
                row=2, column=j, sticky="w", padx=(0, 8))
        self.var_caixa = []
        for i, regra in enumerate(kit.get("caixas") or on.caixas_padrao()):
            nome = tk.StringVar(value=str(regra.get("nome") or ""))
            unid = tk.StringVar(value=str(int(on._numero(
                regra.get("unidades")) or 1)))
            palavras = tk.StringVar(
                value=", ".join(regra.get("palavras") or []))
            ttk.Entry(quadro7, textvariable=nome, width=26).grid(
                row=i + 3, column=0, sticky="w", pady=3)
            ttk.Entry(quadro7, textvariable=unid, width=8,
                      justify="right").grid(row=i + 3, column=1, padx=8,
                                            sticky="w")
            ttk.Entry(quadro7, textvariable=palavras, width=34).grid(
                row=i + 3, column=2, sticky="we", pady=3)
            self.var_caixa.append({"nome": nome, "unidades": unid,
                                   "palavras": palavras})
        ttk.Label(quadro7, text="A regra vale DE CIMA PARA BAIXO: a primeira "
                                "que casar com a descricao manda - por isso o "
                                "fluido de freio vem antes do oleo. Balde, "
                                "tambor e galao nunca entram em caixa: saem "
                                "avulsos.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=len(self.var_caixa) + 3, column=0, columnspan=3,
                      sticky="w", pady=(8, 0))
        quadro7.columnconfigure(2, weight=1)

        # ---- a sucata da bateria -----------------------------------------
        quadro8 = ttk.LabelFrame(dir_, text=" A sucata da bateria ",
                                 padding=12)
        quadro8.pack(fill="x", pady=(12, 0))
        ttk.Label(quadro8,
                  text="Para comprar bateria da fabrica e preciso entregar a "
                       "sucata junto. Entao o custo de verdade e o P. PEDIDO "
                       "do CD MAIS o valor da sucata - e e sobre esse custo "
                       "que o MKP TABELA e o MKP KIT sao calculados. Sem "
                       "isso a bateria aparece com markup inflado e o combo "
                       "fica desequilibrado contra as outras categorias.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(quadro8, text="A amperagem sai da descricao do produto "
                               "(\"60 AMPERES\", \"( 60AMP )\"). A faixa e o "
                               "TETO em amperes: a primeira que couber manda. "
                               "Sem amperagem na descricao, a sucata fica "
                               "zero - melhor nao inventar custo.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        for j, titulo in enumerate(("ATE (A)", "COMUM R$", "ATE (A)",
                                    "START STOP R$")):
            ttk.Label(quadro8, text=titulo, style="Sub.TLabel").grid(
                row=2, column=j, sticky="w", padx=(0, 10))
        self.var_sucata = []
        self.var_sucata_ss = []
        _comum = kit.get("sucata") or on.sucata_padrao()
        _ss = kit.get("sucata_ss") or on.sucata_ss_padrao()
        for i in range(max(len(_comum), len(_ss))):
            if i < len(_comum):
                a = tk.StringVar(value=str(int(on._numero(
                    _comum[i].get("ate")))))
                v = tk.StringVar(value=str(on._numero(_comum[i].get("valor"))))
                self.var_sucata.append({"ate": a, "valor": v})
                ttk.Entry(quadro8, textvariable=a, width=9,
                          justify="right").grid(row=i + 3, column=0,
                                                padx=(0, 10), pady=2,
                                                sticky="w")
                ttk.Entry(quadro8, textvariable=v, width=10,
                          justify="right").grid(row=i + 3, column=1,
                                                padx=(0, 18), pady=2,
                                                sticky="w")
            if i < len(_ss):
                a2 = tk.StringVar(value=str(int(on._numero(
                    _ss[i].get("ate")))))
                v2 = tk.StringVar(value=str(on._numero(_ss[i].get("valor"))))
                self.var_sucata_ss.append({"ate": a2, "valor": v2})
                ttk.Entry(quadro8, textvariable=a2, width=9,
                          justify="right").grid(row=i + 3, column=2,
                                                padx=(0, 10), pady=2,
                                                sticky="w")
                ttk.Entry(quadro8, textvariable=v2, width=10,
                          justify="right").grid(row=i + 3, column=3,
                                                padx=(0, 10), pady=2,
                                                sticky="w")
        ttk.Label(quadro8, text="START STOP e reconhecida pelas palavras EFB, "
                                "AGM e START STOP na descricao. A ultima "
                                "faixa de cada lado (9999) e o teto: vale "
                                "para tudo que passar das anteriores.",
                  style="Sub.TLabel", wraplength=440).grid(
                      row=max(len(self.var_sucata),
                              len(self.var_sucata_ss)) + 3,
                      column=0, columnspan=4, sticky="w", pady=(8, 0))
        quadro8.columnconfigure(4, weight=1)

        botoes = ttk.Frame(f)
        botoes.pack(fill="x", pady=(16, 0))
        ttk.Button(botoes, text="SALVAR E APURAR DE NOVO",
                   style="Big.TButton",
                   command=self.salvar_parametros).pack(side="left")
        ttk.Button(botoes, text="Voltar ao padrao",
                   command=self.voltar_ao_padrao).pack(side="left", padx=8)
        self.lbl_par = ttk.Label(f, text="", style="Sub.TLabel",
                                 wraplength=1300)
        self.lbl_par.pack(anchor="w", pady=(10, 0))
        self._mostrar_curvas()

    def _mostrar_curvas(self):
        linhas = [f"{letra}: {faixa}"
                  for letra, faixa, _ in on.texto_das_curvas(self.par)]
        self.lbl_curva.configure(text="Como esta agora:   "
                                      + "   |   ".join(linhas))

    def _filiais_conhecidas(self) -> dict:
        """
        {codigo: nome} das filiais que podem entrar na acao. Vem do
        estoque quando ele ja foi lido; senao, do que ficou gravado no
        oportunidade_config.json na ultima vez - assim a lista continua
        na tela quando o programa abre, antes de ler qualquer Excel.
        """
        kit = self.par.get("kit") or {}
        nomes = dict(kit.get("filiais_nomes") or {})
        for codigo in (kit.get("filiais") or {}):
            nomes.setdefault(str(codigo), str(codigo))
        if self.estoque:
            for l in self.estoque.get("linhas") or []:
                nomes[str(l["filial"])] = l["regiao"] or str(l["filial"])
        return dict(sorted(nomes.items(), key=lambda x: (x[1], x[0])))

    def _desenhar_filiais(self):
        """A lista de filiais da aba 5, em tres colunas."""
        quadro = getattr(self, "quadro_filiais", None)
        if quadro is None:
            return
        escolhidas = {str(c) for c, v in
                      ((self.par.get("kit") or {}).get("filiais")
                       or {}).items() if v}
        # o que ja estava marcado NA TELA manda sobre o que esta gravado:
        # redesenhar a lista nao pode desfazer o clique de ninguem
        for codigo, var in getattr(self, "var_filial", {}).items():
            escolhidas = (escolhidas | {codigo}) if var.get() else (
                escolhidas - {codigo})
        for w in quadro.winfo_children():
            w.destroy()
        conhecidas = self._filiais_conhecidas()
        self.var_filial = {}
        if not conhecidas:
            ttk.Label(quadro, text="A lista aparece depois de ATUALIZAR "
                                   "ESTOQUE na aba 3 - e de la que sai "
                                   "quais filiais tem produto.",
                      style="Sub.TLabel", wraplength=440).grid(
                          row=0, column=0, sticky="w")
            return
        # O % DA VERBA DE CADA FILIAL, ao lado do nome. Ele nasce
        # calculado pelo faturamento dos ultimos 12 meses, com piso de
        # 10%, e pode ser trocado na mao - o que estiver escrito aqui
        # manda sobre o calculo.
        pesos = self._pesos_sugeridos()
        guardados = {str(c): on._numero(v) for c, v in
                     ((self.par.get("kit") or {}).get("peso_filial")
                      or {}).items()}
        self.var_peso_filial = {}
        for i, (codigo, nome) in enumerate(conhecidas.items()):
            linha, col = i // 2, (i % 2) * 3
            v = tk.BooleanVar(value=codigo in escolhidas)
            self.var_filial[codigo] = v
            ttk.Checkbutton(quadro, variable=v, text=f"{nome} ({codigo})"
                            ).grid(row=linha, column=col, sticky="w",
                                   padx=(0, 6), pady=2)
            pv = tk.StringVar(value=f"{guardados.get(codigo) or pesos.get(codigo, 0.0):.2f}")
            self.var_peso_filial[codigo] = pv
            ttk.Entry(quadro, textvariable=pv, width=7,
                      justify="center").grid(row=linha, column=col + 1,
                                             sticky="w", pady=2)
            ttk.Label(quadro, text="% da verba",
                      style="Sub.TLabel").grid(row=linha, column=col + 2,
                                               sticky="w", padx=(2, 16))
        self.lbl_peso = ttk.Label(quadro, text="", style="Sub.TLabel",
                                  wraplength=440)
        self.lbl_peso.grid(row=(len(conhecidas) + 1) // 2, column=0,
                           columnspan=6, sticky="w", pady=(8, 0))
        self._conferir_pesos()
        for c in (0, 3):
            quadro.columnconfigure(c, weight=1)

    def _pesos_sugeridos(self) -> dict:
        """
        O peso de cada filial pelo FATURAMENTO dos ultimos 12 meses.

        So da para calcular depois que o estoque foi apurado - e de la
        que vem o faturamento. Sem ele, todas ficam iguais.
        """
        fat = (self.estoque or {}).get("faturamento_filial") or {}
        conhecidas = self._filiais_conhecidas()
        piso = on._numero((self.par.get("kit") or {}).get("piso_da_filial"))
        return on.pesos_das_filiais(fat, conhecidas or None,
                                    piso or on.PISO_DA_FILIAL)

    def _conferir_pesos(self):
        """Avisa quando os percentuais nao somam 100."""
        if not hasattr(self, "lbl_peso"):
            return
        soma = sum(on._numero(v.get())
                   for c, v in self.var_peso_filial.items()
                   if self.var_filial.get(c) and self.var_filial[c].get())
        fat = (self.estoque or {}).get("faturamento_filial") or {}
        de_onde = ("calculado pelo faturamento dos ultimos 12 meses, com "
                   "piso de 10%" if fat else
                   "ainda nao calculado: apure o estoque na aba 3 e volte "
                   "aqui")
        self.lbl_peso.configure(
            text=f"A VERBA GERAL da categoria se divide entre as filiais "
                 f"por estes percentuais ({de_onde}). "
                 f"Soma das marcadas: {numero_br(soma, 2)}%."
                 + ("" if abs(soma - 100.0) < 0.05 else
                    "  Nao precisa fechar em 100: o que vale e o peso de "
                    "cada uma contra a soma."),
            foreground=COR_SUAVE if abs(soma - 100.0) < 0.05 else COR_AVISO)

    def _marcar_filiais(self, ligado: bool):
        for v in getattr(self, "var_filial", {}).values():
            v.set(ligado)

    def salvar_parametros(self, avisar=True):
        curvas = []
        anterior = 0
        for (letra, var), padrao in zip(self.var_curva,
                                        self.par.get("curvas")
                                        or on.CURVAS_PADRAO):
            dias = int(on._numero(var.get()) or padrao["dias"])
            if dias <= anterior:
                self.lbl_par.configure(
                    text=f"A curva {letra} tem de ter um corte MAIOR que o "
                         f"da curva de cima ({anterior} dias) - nada foi "
                         f"salvo.", foreground=COR_ALERTA)
                if not avisar:
                    return
                messagebox.showwarning(
                    "Oportunidades BAP",
                    f"A curva {letra} tem de ter um corte MAIOR que o da "
                    f"curva de cima ({anterior} dias).\n\nAs faixas sao uma "
                    f"escada: cada letra pega o que sobrou da anterior.")
                return
            anterior = dias
            curvas.append({**padrao, "letra": letra, "dias": dias})
        self.par["curvas"] = curvas
        for chave, var in self.var_sufixo.items():
            self.par[chave] = var.get().strip()
        self.par["so_com_estoque"] = self.var_so_estoque.get() == "SIM"
        self._ler_kit_dos_campos()
        on.gravar_parametros(self.par, ARQ_PARAMETROS)
        self._mostrar_curvas()
        self.lbl_par.configure(
            text=f"Parametros salvos em {ARQ_PARAMETROS.name}.",
            foreground=COR_OK)
        if self.estoque is not None:
            self.carregar_estoque()
            if self.kits is not None:
                self.carregar_kits()
            elif "est" in (self.ABAS_VISIVEIS or ("est",)):
                self.abas.select(self.aba_est)      # a aba do estoque

    def _ler_kit_dos_campos(self):
        """As regras do kit, do jeito que estao na tela."""
        kit = {**on.kit_padrao(), **(self.par.get("kit") or {})}
        for chave, var in getattr(self, "var_kit", {}).items():
            kit[chave] = on._numero(var.get())
        if hasattr(self, "var_usar_curva"):
            kit["usar_curva"] = ("geral"
                                 if self.var_usar_curva.get().startswith("GERAL")
                                 else "filial")
        if hasattr(self, "var_preco_base"):
            kit["preco_base"] = self.var_preco_base.get().lower()
        cotas = {}
        for curva, campos in getattr(self, "var_cota", {}).items():
            cotas[curva] = {
                "skus": int(on._numero(campos["skus"].get())),
                "qtd": int(on._numero(campos["qtd"].get())),
                "desc_gerente": on._numero(campos["desc_gerente"].get()),
                "desconto": on._numero(campos["desconto"].get()),
                "markup_min": on._numero(campos["markup_min"].get()),
            }
        if cotas:
            kit["cotas"] = cotas
        verbas = {c: on._numero(v.get())
                  for c, v in getattr(self, "var_verba", {}).items()}
        if verbas:
            kit["investimento"] = verbas
        pesos = {c: on._numero(v.get())
                 for c, v in getattr(self, "var_peso_filial", {}).items()}
        if pesos:
            kit["peso_filial"] = pesos
        ligadas = {c: bool(v.get())
                   for c, v in getattr(self, "var_gerar", {}).items()}
        if ligadas:
            kit["gerar"] = ligadas
        geral = {c: v.get().startswith("GERAL")
                 for c, v in getattr(self, "var_verba_geral", {}).items()}
        if geral:
            kit["verba_geral"] = geral
        if hasattr(self, "var_filial"):
            kit["filiais"] = {c: bool(v.get())
                              for c, v in self.var_filial.items()}
            # os nomes viajam junto so para a lista poder ser redesenhada
            # antes de o estoque ser lido - o motor de calculo ignora
            kit["filiais_nomes"] = self._filiais_conhecidas()
        if hasattr(self, "var_por_familia"):
            kit["por_familia"] = self.var_por_familia.get() == "SIM"
        if hasattr(self, "var_caixa_lub"):
            # a caixa fechada agora e regra, nao escolha - a chave fica
            # no arquivo so para nao quebrar config antigo
            kit["caixa_lubrificante"] = True
        caixas = []
        for campos in getattr(self, "var_caixa", []):
            palavras = [p.strip() for p in campos["palavras"].get().split(",")
                        if p.strip()]
            nome = campos["nome"].get().strip()
            unidades = int(on._numero(campos["unidades"].get()) or 1)
            if nome or palavras:
                caixas.append({"nome": nome, "unidades": max(1, unidades),
                               "palavras": palavras})
        for _chave, _campos in (("sucata", getattr(self, "var_sucata", [])),
                                ("sucata_ss",
                                 getattr(self, "var_sucata_ss", []))):
            _faixas = []
            for _c in _campos:
                _ate = int(on._numero(_c["ate"].get()) or 0)
                if _ate > 0:
                    _faixas.append({"ate": _ate,
                                    "valor": on._numero(_c["valor"].get())})
            if _faixas:
                kit[_chave] = sorted(_faixas, key=lambda x: x["ate"])
        if caixas:
            kit["caixas"] = caixas
        self.par["kit"] = kit
        return kit

    def voltar_ao_padrao(self):
        if not messagebox.askyesno("Oportunidades BAP",
                                   "Voltar os parametros ao padrao?"):
            return
        self.par = on.parametros_novos()
        for (letra, var), faixa in zip(self.var_curva, self.par["curvas"]):
            var.set(str(int(faixa["dias"])))
        for chave, var in self.var_sufixo.items():
            var.set(str(self.par.get(chave) or ""))
        self.var_so_estoque.set("SIM" if self.par["so_com_estoque"] else "NAO")
        kit = self.par["kit"]
        for chave, var in self.var_kit.items():
            var.set(str(kit.get(chave) or ""))
        self.var_usar_curva.set("POR FILIAL")
        self.var_preco_base.set("CAPITAL")
        for curva, campos in self.var_cota.items():
            regra = kit["cotas"].get(curva) or {}
            for campo, var in campos.items():
                var.set(str(regra.get(campo) or 0))
        for chave, var in self.var_verba.items():
            var.set(str(kit["investimento"].get(chave) or 0))
        on.gravar_parametros(self.par, ARQ_PARAMETROS)
        self._mostrar_curvas()
        self.lbl_par.configure(text="Parametros de fabrica.",
                               foreground=COR_SUAVE)

    # ---------------------------------------------------------- abertura
    def _abertura(self):
        try:
            self.carregar_cliente()
            # a rota vem junto: sem ela a aba 2 abre vazia e parece quebrada
            if self.oportunidade:
                try:
                    self.carregar_rota()
                except Exception:        # noqa: BLE001 - abrir nunca pode falhar
                    pass
        finally:
            # o --aba do BAP Central: so depois de tudo carregado,
            # senao a propria abertura troca de aba por cima
            self._ir_para_aba_inicial()

    # aba em que o programa abre (o BAP Central passa --aba N)
    ABA_INICIAL = None

    def _ir_para_aba_inicial(self):
        n = type(self).ABA_INICIAL
        if n is None:
            return
        try:
            self.abas.select(n)
        except tk.TclError:
            pass


class KitsPromocionais(Oportunidades):
    """A tela de GERAR os kits (sugestao, PDF, exportar para aprovacao) -
    o botao Kits promocionais do quadrado do Analista na Central."""
    ABAS_VISIVEIS = ("kit",)


def main():
    import sys                                          # noqa: PLC0415
    Oportunidades.ABA_INICIAL = pb.aba_pedida()
    KitsPromocionais.ABA_INICIAL = None
    classe = KitsPromocionais if "--kits" in sys.argv else Oportunidades
    app = classe()
    if "--kits" in sys.argv:
        # sozinho (fora do BAP Analista): os paragrafos viram "i Ajuda"
        try:
            import bap_visual as bv                     # noqa: PLC0415
            app.after(400, lambda: bv.compactar_ajudas(app))
        except Exception:                               # noqa: BLE001
            pass
    app.mainloop()


if __name__ == "__main__":
    main()

