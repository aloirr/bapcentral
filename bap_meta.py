# -*- coding: utf-8 -*-
"""
GERADOR DE META BAP - a tela.

Le o PLANNER_BAP mais recente e monta a meta do mes com a mesma visao do
resumo gerencial: GERENTE, SUPERVISOR, VENDEDOR, ZONA, UF, CIDADE, BAIRRO e
CLIENTE. A conta esta toda no meta_nucleo.py; aqui e so a tela.

Tres abas, para o painel ficar espacoso:
    1. PARAMETROS      a META GERAL, o MES DA META, os percentuais, os
                       pisos e os ajustes por UF/zona
    2. PAINEL DE META  o resultado, por recorte. Clicar numa linha abre
                       embaixo a tabela para escrever a meta a mao
    3. ACOMPANHAMENTO  a meta contra o realizado da TABELA_BAP

A meta gerada MORA em RELATORIOS/ACOMPANHAMENTO_META_BAP.xlsx: uma aba
por mes ("202609") e UMA aba ANALITICO com todos os meses.
"""
from __future__ import annotations

import datetime as dt
import json
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
    from tkinter import filedialog, messagebox, ttk

    import bap_planner as bp
    import meta_nucleo as mn
    import pastas_bap as pb
except Exception:                                        # noqa: BLE001
    rastro = traceback.format_exc()
    print("O Gerador de Meta BAP nao conseguiu iniciar.\n")
    print(rastro)
    try:
        (AQUI / "erro_meta.txt").write_text(rastro, encoding="utf-8")
    except OSError:
        pass
    raise SystemExit(1)

ARQ_PARAMETROS = AQUI / "meta_config.json"
# os 8 segmentos de cliente - a mesma lista do Planner
SEGMENTOS = list(getattr(bp.nu, "SEGMENTOS", []))

# a mesma paleta do PLANNER: os dois sao o mesmo sistema
COR_FUNDO = bp.COR_FUNDO
COR_PAPEL = bp.COR_PAPEL
COR_TITULO = bp.COR_TITULO
COR_ACENTO = bp.COR_ACENTO
COR_SUAVE = bp.COR_SUAVE
COR_LINHA = bp.COR_LINHA
COR_ALERTA = bp.COR_ALERTA
COR_OK = bp.COR_OK
COR_AVISO = bp.COR_AVISO
COR_TOTAL = bp.COR_TOTAL
COR_ZEBRA = bp.COR_ZEBRA
COR_TEXTO = bp.COR_TEXTO
COR_SELECAO = bp.COR_SELECAO
LINHA_TOTAL = bp.LINHA_TOTAL

TODAS = "(todas)"
TODOS_DA_FOLHA = "(tudo)"

# na TELA os titulos das metas sao curtos - a coluna nasce do tamanho do
# titulo, e "ATING CADASTRO C/ COMPRA %" faria uma coluna mais larga que o
# numero que ela mostra. No Excel eles continuam por extenso.
# Os titulos dos tres indicadores de CONTAGEM sao abreviados: com a META
# e o REAL deles na tela junto com o faturamento, "META POSITIVACAO" nao
# cabe no cabecalho sem cortar. O que cada um quer dizer esta na legenda
# da aba, por extenso.
CURTO_AC = {"VISITA": "VIS.", "POSITIVACAO": "POS.", "FAT TOTAL": "FAT TT",
            "CAD. COMPRA": "CAD."}


def numero(texto, padrao=0.0) -> float:
    """Aceita 1.234,56 e 1234.56 - o usuario digita do jeito dele."""
    s = str(texto or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return padrao
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return padrao


def inteiro(v) -> int:
    """Para cima e sem casa: 89,4 visitas viram 90."""
    try:
        return int(math.ceil(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def dinheiro(v) -> str:
    return bp.dinheiro(v)


def numero_br(v, casas=1) -> str:
    try:
        return f"{float(v):,.{casas}f}".replace(",", "~") \
            .replace(".", ",").replace("~", ".")
    except (TypeError, ValueError):
        return "0"


def _texto_da_celula(v) -> str:
    """O que a celula mostra, para saber se a coluna esta vazia na folha."""
    return "" if v is None else str(v).strip()


def _rv_pct(valor) -> str:
    """
    O percentual de uma faixa de RV como ele aparece no campo.

    O TETO (999999) aparece VAZIO: ler "ate vazio" como "dai para cima"
    e mais honesto do que mostrar um numero que ninguem vai atingir. E
    as casas sobrando somem - 80,000 escrito e 80.
    """
    if valor is None:
        return ""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return ""
    if v >= mn.TETO_DA_FAIXA:
        return ""
    texto = numero_br(v, 3)
    return texto.rstrip("0").rstrip(",") if "," in texto else texto


# ==========================================================================
class Meta(pb.base_da_janela()):
    # nao ha mais modo a escolher: e uma mecanica so
    MODOS = ["M3M atual x M3M anterior"]

    # as colunas do painel, iguais em todos os recortes
    # A META VEM PRIMEIRO E JUNTA - e para isso que o painel serve. O
    # que explica de onde ela veio fica depois, a direita.
    COLUNAS = [
        ("codigo", "CODIGO", 100, "w", False),
        ("nome", "NOME", 230, "w", True),
        ("base_visita", "BASE VISITA", 92, "center", False),
        # COMERCIAL = a do gerente desdobrada (soma em todo recorte);
        # RH = a regra de cada nivel, a que paga a RV
        ("meta", "DESAFIO FAT. TT R$", 136, "e", False),
        ("meta_rh", "META FAT. TT R$", 146, "e", False),
        ("meta_pecas", "META PECAS R$", 124, "e", False),
        ("meta_lubrificante", "META LUBRIF. R$", 124, "e", False),
        ("meta_bateria", "META BATERIA R$", 124, "e", False),
        ("meta_pneu", "META PNEU R$", 118, "e", False),
        ("meta_visita", "META VISITA", 96, "center", False),
        ("meta_positivacao", "META POSIT.", 96, "center", False),
        ("meta_cadastro", "META CADASTRO", 108, "center", False),
        # dai para a direita, de onde a meta saiu
        ("base_carteira", "BASE TOTAL", 88, "center", False),
        ("positivacao_base", "BASE POSIT.", 92, "center", False),
        ("visitas", "VISITAS ROTA", 92, "center", False),
        ("visitas_deposito", "VIS. DEPOSITO", 96, "center", False),
        ("fat_m3m", "FAT M3M R$", 116, "e", False),
        ("fat_m3m_anterior", "M3M ANTERIOR R$", 128, "e", False),
        ("meta_dos_clientes", "SOMA DOS CLI. R$", 132, "e", False),
        ("faixa", "DE ONDE VEIO A META", 240, "w", False),
    ]

    def __init__(self):
        super().__init__()
        self.title("Gerador de Meta BAP")
        self.geometry("1480x960")
        self.minsize(1100, 700)
        self.configure(bg=COR_FUNDO)
        bp.App._estilo(self)

        try:
            pb.arrumar(AQUI)
        except OSError:
            pass

        self.par = mn.carregar_parametros(ARQ_PARAMETROS)
        self.mapa_categoria = dict(self.par.get("categoria_por_fornecedor")
                                   or {})
        self.categorias_produto = {}
        self.csv_categorias = None
        self.dados = None            # o PLANNER lido
        self.resultado = None        # a meta calculada
        self.realizado = None        # o que a TABELA_BAP diz que foi faturado
        self.arq_visitas = None      # o CSV de visita do mes apurado
        self.comp_visitas = ""       # de que mes ele e
        self.visitas_feitas = {}
        self.datas_cadastro = {}
        self.acomp = None            # a meta contra o realizado
        self.planner = None
        self.visoes_ac = {}
        # OS DOIS FILTROS DE PESSOA, valendo para o programa inteiro:
        # a mesma variavel esta ligada ao checkbox de todas as abas
        self.var_so_ativos = tk.BooleanVar(value=False)
        self.var_so_conta = tk.BooleanVar(value=False)
        # O FILTRO DE SEGMENTO, tambem do programa inteiro (painel,
        # acompanhamento e folha). E so de LEITURA: a meta que vale e
        # grava continua sendo a de todos os segmentos.
        self.var_segmento = tk.StringVar(value=mn.TODOS_OS_SEGMENTOS)
        self._cache_tela = {}
        self._silencio = False
        self.visoes = {}
        # quem esta FORA da meta do supervisor no mes que esta na tela da
        # aba 5, enquanto ele mexe - so vira decisao quando ele grava
        self.fora_tela = {n: set() for n in mn.NIVEIS_DO_CORTE}
        self.comp_conta = ""

        raiz = ttk.Frame(self, style="Fundo.TFrame", padding=(14, 12))
        raiz.pack(fill="both", expand=True)
        self._cabecalho(raiz)
        self.abas = ttk.Notebook(raiz)
        self.abas.pack(fill="both", expand=True, pady=(10, 0))
        self.aba_par = ttk.Frame(self.abas, padding=16)
        self.aba_painel = ttk.Frame(self.abas, padding=16)
        self.aba_acomp = ttk.Frame(self.abas, padding=16)
        self.aba_exec = ttk.Frame(self.abas, padding=16)
        self.aba_conta = ttk.Frame(self.abas, padding=16)
        self.aba_folha = ttk.Frame(self.abas, padding=16)
        for aba, nome in zip((self.aba_par, self.aba_painel, self.aba_acomp,
                              self.aba_exec, self.aba_conta, self.aba_folha),
                             ("1. Parâmetros", "2. Painel de meta",
                              "Acompanhamento", "Metas executivas",
                              "3. Quem conta na meta", "Imprimir / exportar")):
            self.abas.add(aba, text=nome)

        self._montar_parametros()
        self._montar_painel()
        self._montar_acompanhamento()
        self._montar_executivo()
        self._montar_quem_conta()
        self._montar_folha()
        self._mostrar_so_as_abas()
        self._ver_tudo = False
        self._aplicar_modo()
        self.rodape = ttk.Label(raiz, text="", style="Sub.TLabel")
        self.rodape.pack(anchor="w", pady=(8, 0))
        self.after(80, self._abertura)

    # AS ABAS QUE APARECEM. O acompanhamento, os indicadores executivos e o
    # imprimir/exportar sao LEITURA e moram nos farois (Metas Equipe,
    # Indicadores Executivos, Exportar para o RH) - aqui ficariam em dobro.
    # As metas executivas (meta, peso e despesa do mes) sao CADASTRO: ficam
    # pelo botao Metas executivas do Farol Indicadores Executivos.
    ABAS_VISIVEIS = ("par", "painel")
    TITULO = "Gerador de Meta BAP"

    def _gravar_par(self):
        """O Gerador e as Metas executivas gravam o mesmo meta_config.json:
        cada tela so manda na parte dela, para uma nao desfazer a outra."""
        try:
            disco = json.loads(Path(ARQ_PARAMETROS).read_text("utf-8"))
        except (OSError, ValueError):
            disco = {}
        if "exec" in self.ABAS_VISIVEIS and "par" not in self.ABAS_VISIVEIS:
            disco["executivo"] = self.par.get("executivo") or {}
            mn.gravar_parametros(disco, ARQ_PARAMETROS)
            return
        if "executivo" in disco:
            self.par["executivo"] = disco["executivo"]
        mn.gravar_parametros(self.par, ARQ_PARAMETROS)

    def _selecionar(self, chave):
        """Vai para a aba so se ela aparece nesta tela."""
        if chave in self.ABAS_VISIVEIS:
            self.abas.select({"par": self.aba_par, "painel": self.aba_painel,
                              "acomp": self.aba_acomp, "exec": self.aba_exec,
                              "conta": self.aba_conta,
                              "folha": self.aba_folha}[chave])

    def _mostrar_so_as_abas(self):
        todas = {"par": self.aba_par, "painel": self.aba_painel,
                 "acomp": self.aba_acomp, "exec": self.aba_exec,
                 "conta": self.aba_conta, "folha": self.aba_folha}
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

    # --------------------------------------------------------- aba 1
    # A TELA E ENXUTA DE PROPOSITO: a meta de faturamento do mes vem do
    # Excel da diretoria e ponto. Tudo o que e regra de calculo so entra
    # onde o arquivo nao cobre, entao mora num bloco recolhido - quem
    # abre a aba no dia a dia so precisa do mes, do arquivo e do GERAR.
    def _montar_parametros(self):
        f = self.aba_par
        ttk.Label(f, text="Parametros da meta",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(f, style="Sub.TLabel", wraplength=1360,
                  text="A meta de faturamento do mes vem do Excel da "
                       "diretoria. O programa so reparte essa meta entre os "
                       "clientes, na proporcao do FAT M3M de cada um, e "
                       "soma para cima - ele nao inventa meta."
                  ).pack(anchor="w", pady=(2, 12))

        # ---- A META DO MES, em destaque ---------------------------------
        moldura = tk.Frame(f, background="#EEF6EA", highlightthickness=1,
                           highlightbackground=COR_LINHA)
        moldura.pack(fill="x", pady=(0, 14))
        topo = tk.Frame(moldura, background="#EEF6EA")
        topo.pack(fill="x")
        tk.Label(topo, text="MES DA META:", background="#EEF6EA",
                 foreground=COR_TITULO, font=(self.FONTE, 10, "bold"),
                 padx=14, pady=12).pack(side="left")
        self.var_competencia = tk.StringVar()
        self.cb_competencia = ttk.Combobox(
            topo, textvariable=self.var_competencia, width=11,
            justify="center", values=mn.meses_por_perto())
        self.cb_competencia.pack(side="left", pady=10)
        self.cb_competencia.bind("<<ComboboxSelected>>",
                                 lambda _: self._mes_mudou())
        self.cb_competencia.bind("<FocusOut>", lambda _: self._mes_mudou())
        ttk.Button(topo, text="IMPORTAR A META DO EXCEL", style="Big.TButton",
                   command=self.importar_metas).pack(side="left", padx=14)
        ttk.Button(topo, text="Baixar o modelo",
                   command=self.modelo_por_filial).pack(side="left")
        ttk.Button(topo, text="Esquecer as metas importadas",
                   command=self.limpar_metas).pack(side="left", padx=8)
        # a linha grande: quanto e a meta DESTE mes e de onde ela veio
        self.lbl_meta_mes = tk.Label(
            moldura, text="", background="#EEF6EA", foreground=COR_TITULO,
            font=(self.FONTE, 12), justify="left", anchor="w", padx=16,
            pady=(4))
        self.lbl_meta_mes.pack(fill="x")
        # MES SEM META NO ARQUIVO: digita a META GERAL e gera para todos
        self.quadro_geral = tk.Frame(moldura, background="#EEF6EA")
        tk.Label(self.quadro_geral, text="META GERAL DO MÊS:",
                 background="#EEF6EA", foreground=COR_TITULO,
                 font=(self.FONTE, 10, "bold"), padx=14).pack(side="left")
        self.var_geral_mes = tk.StringVar()
        self.ent_geral_mes = ttk.Entry(self.quadro_geral,
                                       textvariable=self.var_geral_mes,
                                       width=16, justify="right",
                                       font=(self.FONTE, 11))
        self.ent_geral_mes.pack(side="left", pady=(2, 8))
        self.ent_geral_mes.bind("<Return>", lambda _: self.gerar_pela_geral())
        ttk.Button(self.quadro_geral, text="GERAR", style="Big.TButton",
                   command=self.gerar_pela_geral).pack(side="left", padx=10,
                                                       pady=(2, 8))
        self.lbl_metas = ttk.Label(moldura, text="", style="Sub.TLabel",
                                   wraplength=1340, background="#EEF6EA")
        self.lbl_metas.pack(anchor="w", padx=16, pady=(2, 10))
        # continua existindo por tras: e a rede quando NAO ha arquivo para
        # o mes - ai a UF e o gerente rateiam este valor. Nao tem campo na
        # tela de proposito; quem manda e o Excel.
        self.var_meta = tk.StringVar()
        self.var_modo = tk.StringVar(value=self.MODOS[0])

        # ---- as metas que nao vem do arquivo ----------------------------
        corpo = ttk.Frame(f)
        corpo.pack(fill="x")
        quadro = ttk.LabelFrame(corpo, text=" As outras metas do mes ",
                                padding=12)
        quadro.pack(side="left", fill="both", expand=True, padx=(0, 18))
        self.var_visita = tk.StringVar()
        self.var_pos = tk.StringVar()
        self.var_cad = tk.StringVar()
        for i, (rotulo, var, ajuda) in enumerate((
                ("META VISITA (% das visitas do PLANNER)", self.var_visita,
                 "(21/10) NAO E MAIS USADO: a meta de visita e 12 clientes "
                 "por dia util desde a admissao (vendedor do interior 6, e "
                 "12 no dia da cidade base) - Mecanica da rota, item 25. "
                 "Este % so vale se meta_visita_por_du for 0"),
                ("POSITIVACAO (% dos clientes da rota)", self.var_pos,
                 "os clientes marcados para visita, TIRANDO os que so tem "
                 "visita no primeiro sabado (os excedentes)"),
                ("CADASTRO COM COMPRA (por vendedor, no mes)", self.var_cad,
                 "quantos clientes NOVOS cada vendedor tem de cadastrar E "
                 "fazer comprar dentro do mes. Supervisor e gerente sao a "
                 "soma da equipe"))):
            ttk.Label(quadro, text=rotulo).grid(row=i * 2, column=0,
                                                sticky="w", pady=(6, 0))
            ttk.Entry(quadro, textvariable=var, width=10,
                      justify="right").grid(row=i * 2, column=1, padx=8,
                                            sticky="w")
            ttk.Label(quadro, text=ajuda, style="Sub.TLabel",
                      wraplength=440).grid(row=i * 2 + 1, column=0,
                                           columnspan=2, sticky="w")
        quadro.columnconfigure(0, weight=1)

        # ---- a META DO VENDEDOR pelos MESES DE CASA (06/10) -------------
        quadro_c = ttk.LabelFrame(corpo, text=" Meta do vendedor (meses de "
                                              "casa) ", padding=12)
        quadro_c.pack(side="left", fill="both", expand=True, padx=(0, 18))
        self.var_casa = []
        for i in range(4):
            ttk.Label(quadro_c, text=f"{i + 1}º mês de casa (R$)").grid(
                row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar()
            self.var_casa.append(v)
            ttk.Entry(quadro_c, textvariable=v, width=12,
                      justify="right").grid(row=i, column=1, padx=8)
        self.var_piso_vet = tk.StringVar()
        self.var_teto_rh = tk.StringVar()
        for i, (rot, var) in enumerate((
                ("Depois: desafio mínimo comercial (R$)", self.var_piso_vet),
                ("Depois: teto da meta (R$)", self.var_teto_rh)), 4):
            ttk.Label(quadro_c, text=rot).grid(row=i, column=0, sticky="w",
                                               pady=3)
            ttk.Entry(quadro_c, textvariable=var, width=12,
                      justify="right").grid(row=i, column=1, padx=8)
        ttk.Label(quadro_c, style="Sub.TLabel", wraplength=380,
                  text="O mês de casa vem do cadastro do vendedor/supervisor "
                       "no Planner do mês. A soma dos vendedores nunca passa "
                       "da meta do gerente."
                  ).grid(row=6, column=0, columnspan=2, sticky="w",
                         pady=(6, 0))
        # ---- E-MAILS EM COPIA da parcial do GERENTE (06/10) ---------------
        ttk.Label(quadro_c, text="E-mails em cópia (parcial do gerente)",
                  font=("Segoe UI", 9, "bold")).grid(
                      row=7, column=0, columnspan=2, sticky="w", pady=(12, 2))
        self.var_cc = []
        for i in range(5):
            v = tk.StringVar()
            self.var_cc.append(v)
            ttk.Entry(quadro_c, textvariable=v, width=38).grid(
                row=8 + i, column=0, columnspan=2, sticky="we", pady=1)
        ttk.Label(quadro_c, style="Sub.TLabel", wraplength=380,
                  text="Recebem o PDF só quando a parcial vai para o gerente."
                  ).grid(row=13, column=0, columnspan=2, sticky="w",
                         pady=(2, 0))
        quadro_c.columnconfigure(0, weight=1)

        # ---- o PLANNER que esta sendo usado -----------------------------
        quadro_pl = ttk.LabelFrame(corpo, text=" O PLANNER que gera a meta ",
                                   padding=12)
        quadro_pl.pack(side="left", fill="both", expand=True)
        ttk.Label(quadro_pl, style="Sub.TLabel", wraplength=460,
                  text="Dele saem a carteira, a hierarquia, as visitas do "
                       "mes e o FAT M3M de cada cliente. O programa pega "
                       "sozinho o mais recente da pasta RELATORIOS."
                  ).pack(anchor="w")
        ttk.Button(quadro_pl, text="Escolher outro PLANNER...",
                   command=self.escolher_planner).pack(anchor="w",
                                                       pady=(10, 0))
        self.lbl_par_msg = ttk.Label(quadro_pl, text="", style="Sub.TLabel",
                                     wraplength=460)
        self.lbl_par_msg.pack(anchor="w", pady=(10, 0))

        # ---- o bloco recolhido: as regras de excecao --------------------
        self.linha_regras = ttk.Frame(f)
        self.linha_regras.pack(fill="x", pady=(14, 0))
        self.bt_regras = ttk.Button(
            self.linha_regras, text="+  REGRAS DE EXCECAO   (so valem para a "
                                    "filial ou cidade que NAO veio no "
                                    "arquivo de meta)",
            command=self.virar_regras)
        self.bt_regras.pack(anchor="w")
        self.quadro_regras = ttk.Frame(f)
        self._regras_abertas = False
        self._montar_regras(self.quadro_regras)

        # ---- a RV, numa janela so dela ----------------------------------
        # A TABELA DO RH NAO CABE AQUI, e nem precisa: ela se mexe uma vez
        # por ano, enquanto o resto desta aba se mexe todo mes. Numa janela
        # propria os tres indicadores ficam lado a lado e ainda sobra
        # espaco para o simulador.
        linha_rv = ttk.Frame(f)
        linha_rv.pack(fill="x", pady=(8, 0))
        ttk.Button(linha_rv, text="REMUNERACAO VARIAVEL...   (quanto cada "
                                  "indicador paga, por faixa de atingimento)",
                   command=self.abrir_rv).pack(anchor="w")
        self.jan_rv = None
        self.var_rv = {}

        # ---- botoes -----------------------------------------------------
        rodape = ttk.Frame(f)
        rodape.pack(fill="x", pady=(14, 0))
        ttk.Button(rodape, text="GERAR A META", style="Big.TButton",
                   command=self.gerar).pack(side="left")
        ttk.Button(rodape, text="Salvar parametros",
                   command=self.salvar_parametros).pack(side="left", padx=8)
        ttk.Button(rodape, text="Voltar ao padrao",
                   command=self.voltar_ao_padrao).pack(side="left")

    def virar_regras(self):
        """Abre e fecha o bloco das regras de excecao."""
        self._regras_abertas = not self._regras_abertas
        if self._regras_abertas:
            self.quadro_regras.pack(fill="both", expand=True, pady=(8, 0),
                                    before=self.linha_regras)
            self.bt_regras.configure(text="-  REGRAS DE EXCECAO   (esconder)")
        else:
            self.quadro_regras.pack_forget()
            self.bt_regras.configure(
                text="+  REGRAS DE EXCECAO   (so valem para a filial ou "
                     "cidade que NAO veio no arquivo de meta)")

    def _montar_regras(self, f):
        """
        O que fazer com quem o arquivo de meta nao cobriu: a meta pelo
        crescimento, os pisos e os percentuais por categoria.
        """
        ttk.Label(f, style="Sub.TLabel", wraplength=1360,
                  text="Filial ou cidade que vem no arquivo NAO passa por "
                       "aqui - a meta dela e a do arquivo, repartida pelo "
                       "M3M. Estas regras so pegam o que ficou de fora."
                  ).pack(anchor="w", pady=(0, 8))
        corpo = ttk.Frame(f)
        corpo.pack(fill="both", expand=True)
        esq = ttk.Frame(corpo)
        esq.pack(side="left", fill="both", expand=True, padx=(0, 18))
        dir_ = ttk.Frame(corpo)
        dir_.pack(side="left", fill="both", expand=True)

        quadro_c = ttk.LabelFrame(esq, text=" A meta pelo crescimento "
                                            "(M3M atual x M3M anterior) ",
                                  padding=12)
        quadro_c.pack(fill="x")
        for j, titulo in enumerate(("Se cresceu", "sobre o", "acrescentar %")):
            ttk.Label(quadro_c, text=titulo, style="Sub.TLabel").grid(
                row=1, column=j + 1 if j else 1, sticky="w", padx=(0, 6))
        self.var_faixa = []
        for i, rotulo in enumerate(("10% ou mais", "de 5% a 10%",
                                    "menos de 5% (ou caindo)")):
            ttk.Label(quadro_c, text=rotulo).grid(row=i + 2, column=0,
                                                  sticky="w", pady=4)
            base = tk.StringVar()
            acr = tk.StringVar()
            ttk.Combobox(quadro_c, textvariable=base, width=14,
                         state="readonly",
                         values=["M3M atual", "M3M anterior"]).grid(
                             row=i + 2, column=1, padx=6)
            ttk.Entry(quadro_c, textvariable=acr, width=8,
                      justify="right").grid(row=i + 2, column=2, padx=6)
            self.var_faixa.append((base, acr))
        quadro_c.columnconfigure(0, weight=1)

        quadro_p = ttk.LabelFrame(esq, text=" Meta minima (o piso de cada "
                                            "nivel) ", padding=12)
        quadro_p.pack(fill="x", pady=(12, 0))
        self.var_piso = {}
        for i, (chave, rotulo) in enumerate((
                ("piso_cliente", "Por CLIENTE (R$)"),
                ("piso_zona", "Por ZONA (R$)"))):
            ttk.Label(quadro_p, text=rotulo).grid(row=i, column=0, sticky="w",
                                                  pady=4)
            v = tk.StringVar()
            self.var_piso[chave] = v
            ttk.Entry(quadro_p, textvariable=v, width=14,
                      justify="right").grid(row=i, column=1, padx=8)
        quadro_p.columnconfigure(0, weight=1)
        self.var_piso_so_fat = tk.StringVar(value="SIM")
        ttk.Label(quadro_p, text="O piso do cliente vale so para quem ja "
                                 "comprou?").grid(row=3, column=0, sticky="w",
                                                  pady=(8, 0))
        ttk.Combobox(quadro_p, textvariable=self.var_piso_so_fat, width=8,
                     state="readonly", values=["SIM", "NAO"]).grid(
                         row=3, column=1, padx=8, pady=(8, 0))
        self.lbl_piso = ttk.Label(quadro_p, text="", style="Sub.TLabel",
                                  wraplength=440)
        self.lbl_piso.grid(row=4, column=0, columnspan=2, sticky="w",
                           pady=(6, 0))

        quadro2 = ttk.LabelFrame(dir_, text=" Meta por categoria (% da meta de "
                                            "faturamento da linha) ",
                                 padding=12)
        quadro2.pack(fill="x", pady=(0, 12))
        self.var_cat = {}
        for i, (chave, rotulo, _) in enumerate(mn.CATEGORIAS):
            ttk.Label(quadro2, text=rotulo).grid(row=i, column=0, sticky="w",
                                                 pady=5)
            v = tk.StringVar()
            self.var_cat[chave] = v
            ttk.Entry(quadro2, textvariable=v, width=10,
                      justify="right").grid(row=i, column=1, padx=8)
        quadro2.columnconfigure(0, weight=1)
        self.lbl_soma = ttk.Label(quadro2, text="", style="Sub.TLabel",
                                  wraplength=440)
        self.lbl_soma.grid(row=len(mn.CATEGORIAS), column=0, columnspan=2,
                           sticky="w", pady=(8, 0))

        quadro3 = ttk.LabelFrame(dir_, text=" Percentuais diferentes por UF "
                                            "ou por ZONA ", padding=12)
        quadro3.pack(fill="both", expand=True)
        ttk.Label(quadro3, text="Mexeu no ESTADO, muda tudo daquele estado. "
                                "Mexeu na ZONA, muda tudo daquela zona - e a "
                                "zona manda mais que o estado.",
                  style="Sub.TLabel", wraplength=460).pack(anchor="w",
                                                            pady=(0, 8))
        linha = ttk.Frame(quadro3)
        linha.pack(fill="x")
        ttk.Label(linha, text="Aplicar em:").pack(side="left")
        self.var_nivel = tk.StringVar(value="UF")
        cb = ttk.Combobox(linha, textvariable=self.var_nivel, width=8,
                          values=["UF", "ZONA"], state="readonly")
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _: self._encher_alvos())
        self.var_alvo = tk.StringVar()
        self.cb_alvo = ttk.Combobox(linha, textvariable=self.var_alvo,
                                    width=34, state="readonly")
        self.cb_alvo.pack(side="left", padx=6)
        self.cb_alvo.bind("<<ComboboxSelected>>", lambda _: self._ler_excecao())

        grade = ttk.Frame(quadro3)
        grade.pack(fill="x", pady=(10, 0))
        self.var_cat_exc = {}
        for i, (chave, rotulo, _) in enumerate(mn.CATEGORIAS):
            ttk.Label(grade, text=rotulo).grid(row=i, column=0, sticky="w",
                                               pady=4)
            v = tk.StringVar()
            self.var_cat_exc[chave] = v
            ttk.Entry(grade, textvariable=v, width=10,
                      justify="right").grid(row=i, column=1, padx=8)
        grade.columnconfigure(0, weight=1)

        botoes = ttk.Frame(quadro3)
        botoes.pack(fill="x", pady=(10, 0))
        ttk.Button(botoes, text="APLICAR NESTE",
                   command=self.aplicar_excecao).pack(side="left")
        ttk.Button(botoes, text="Voltar ao geral",
                   command=self.tirar_excecao).pack(side="left", padx=6)

        ttk.Label(quadro3, text="Ja tem percentual proprio:",
                  style="Sub.TLabel").pack(anchor="w", pady=(12, 2))
        self.lst_excecoes = tk.Listbox(quadro3, height=6, relief="flat",
                                       borderwidth=0, highlightthickness=1,
                                       highlightbackground=COR_LINHA,
                                       font=(self.FONTE, 9),
                                       background=COR_PAPEL)
        self.lst_excecoes.pack(fill="both", expand=True)

    # ------------------------------------------------- aba 1: a RV
    # AS FAIXAS DO RH, EDITAVEIS. Elas nao entram no calculo da meta: a
    # RV e consequencia do atingimento, nao causa dele. Ficam aqui porque
    # e aqui que moram as regras, e aparecem no acompanhamento (aba 3) e
    # no IMPRIMIR/EXPORTAR (aba 6) como qualquer outro indicador.
    LINHAS_EXTRA_RV = 2         # linhas em branco para o usuario acrescentar

    def abrir_rv(self):
        """A janela das faixas de RV - uma so, nunca duas."""
        if self.jan_rv is not None and self.jan_rv.winfo_exists():
            self.jan_rv.lift()
            self.jan_rv.focus_force()
            return
        self.jan_rv = tk.Toplevel(self)
        self.jan_rv.title("Remuneracao variavel - as faixas de cada "
                          "indicador")
        self.jan_rv.configure(background=COR_FUNDO)
        self.jan_rv.geometry("1180x640")
        self.jan_rv.transient(self)
        quadro = ttk.Frame(self.jan_rv, style="Fundo.TFrame", padding=16)
        quadro.pack(fill="both", expand=True)
        self._montar_rv(quadro)
        self._desenhar_rv()
        self.jan_rv.protocol("WM_DELETE_WINDOW", self.fechar_rv)

    def fechar_rv(self):
        """
        Fecha guardando o que esta escrito.

        Quem digitou uma faixa e fechou a janela espera que ela esteja la
        - perder o que foi digitado por nao ter clicado no botao certo
        seria uma armadilha. O que ainda falta e o Salvar parametros, e a
        mensagem da aba 1 diz isso.
        """
        if self.var_rv:
            self.par.setdefault("rv", mn.rv_padrao())
            self.par["rv"][self._nivel_da_rv()] = self._faixas_da_tela()
            self.lbl_par_msg.configure(
                text="Faixas de RV guardadas. Clique em Salvar parametros "
                     "para elas valerem da proxima vez que abrir o "
                     "programa, e em Apurar (aba 3) para recalcular a RV "
                     "de cada pessoa.", foreground=COR_OK)
        self.var_rv = {}
        if self.jan_rv is not None and self.jan_rv.winfo_exists():
            self.jan_rv.destroy()
        self.jan_rv = None

    def _montar_rv(self, f):
        ttk.Label(f, style="Sub.TLabel", wraplength=1360,
                  text="Uma tabela por nivel. Cada indicador tem as suas "
                       "faixas: o atingimento cai na PRIMEIRA faixa que "
                       "servir e leva o valor dela. Deixe o ATE da ultima "
                       "faixa VAZIO - assim ela vale para qualquer "
                       "atingimento acima do DE, e ninguem fica sem valor "
                       "por bater 150%. Para TIRAR uma faixa, apague as tres "
                       "celulas dela; para ACRESCENTAR, use as linhas em "
                       "branco do fim."
                  ).pack(anchor="w", pady=(0, 8))
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Tabela de:").pack(side="left")
        self.var_rv_nivel = tk.StringVar(value=mn.NIVEIS_DA_RV[0][1])
        self.cb_rv_nivel = ttk.Combobox(
            topo, textvariable=self.var_rv_nivel, width=14, state="readonly",
            values=[rotulo for _, rotulo in mn.NIVEIS_DA_RV])
        self.cb_rv_nivel.pack(side="left", padx=6)
        self.cb_rv_nivel.bind("<<ComboboxSelected>>",
                              lambda _: self._desenhar_rv())
        ttk.Button(topo, text="GUARDAR ESTA TABELA", style="Big.TButton",
                   command=self.guardar_rv).pack(side="left", padx=(14, 0))
        ttk.Button(topo, text="Voltar esta ao padrao",
                   command=self.rv_ao_padrao).pack(side="left", padx=6)
        ttk.Button(topo, text="FECHAR",
                   command=self.fechar_rv).pack(side="right")
        self.lbl_rv_msg = ttk.Label(f, text="", style="Sub.TLabel",
                                    wraplength=1360)
        self.lbl_rv_msg.pack(anchor="w", pady=(6, 0))

        self.quadro_rv_grade = ttk.Frame(f)
        self.quadro_rv_grade.pack(fill="x", pady=(8, 0))
        self.var_rv = {}        # kpi -> [(de, ate, valor), ...] da tela

        # ---- o simulador: quanto UMA pessoa levaria -----------------
        sim = ttk.LabelFrame(f, text=" Quanto paga, neste nivel, um "
                                     "atingimento assim ", padding=12)
        sim.pack(fill="x", pady=(12, 0))
        self.var_rv_sim = {}
        for i, (chave, rotulo, _campo) in enumerate(mn.KPIS_DA_RV):
            ttk.Label(sim, text=f"ATING {rotulo} %").grid(
                row=0, column=i * 2, sticky="e", padx=(0 if not i else 16, 6))
            v = tk.StringVar(value="100")
            self.var_rv_sim[chave] = v
            e = ttk.Entry(sim, textvariable=v, width=8, justify="right")
            e.grid(row=0, column=i * 2 + 1, sticky="w")
            e.bind("<KeyRelease>", lambda _: self._simular_rv())
        ttk.Button(sim, text="CALCULAR",
                   command=self._simular_rv).grid(row=0, column=6, padx=16)
        self.lbl_rv_sim = ttk.Label(sim, text="", style="Sub.TLabel",
                                    wraplength=1320)
        self.lbl_rv_sim.grid(row=1, column=0, columnspan=7, sticky="w",
                             pady=(10, 0))

    def _nivel_da_rv(self) -> str:
        """A chave do nivel escolhido no combo ('vendedor', ...)."""
        rotulo = self.var_rv_nivel.get()
        for chave, texto in mn.NIVEIS_DA_RV:
            if texto == rotulo:
                return chave
        return mn.NIVEIS_DA_RV[0][0]

    def _desenhar_rv(self):
        """Refaz a grade com as faixas do nivel escolhido."""
        for filho in self.quadro_rv_grade.winfo_children():
            filho.destroy()
        self.var_rv = {}
        nivel = self._nivel_da_rv()
        vazio = True
        for chave, rotulo, _campo in mn.KPIS_DA_RV:
            faixas = mn.faixas_da_rv(self.par, nivel, chave)
            vazio = vazio and not faixas
            quadro = ttk.LabelFrame(self.quadro_rv_grade,
                                    text=f" {rotulo} ", padding=10)
            quadro.pack(side="left", fill="both", expand=True,
                        padx=(0, 12))
            for j, titulo in enumerate(("DE %", "ATE %", "PAGA R$")):
                ttk.Label(quadro, text=titulo, style="Sub.TLabel").grid(
                    row=0, column=j, sticky="w", padx=(0, 6))
            linhas = []
            for i in range(len(faixas) + self.LINHAS_EXTRA_RV):
                faixa = faixas[i] if i < len(faixas) else {}
                trio = []
                for j, (campo, texto) in enumerate(
                        (("de", _rv_pct(faixa.get("de"))),
                         ("ate", _rv_pct(faixa.get("ate"))),
                         ("valor", dinheiro(faixa["valor"])
                          if faixa else ""))):
                    v = tk.StringVar(value=texto)
                    ttk.Entry(quadro, textvariable=v,
                              width=11 if campo == "valor" else 8,
                              justify="right").grid(row=i + 1, column=j,
                                                    padx=(0, 6), pady=2)
                    trio.append(v)
                linhas.append(tuple(trio))
            self.var_rv[chave] = linhas
        if vazio:
            self.lbl_rv_msg.configure(
                text=f"{self.var_rv_nivel.get()} ainda NAO tem tabela de RV. "
                     f"Enquanto estiver assim, as colunas de RV ficam VAZIAS "
                     f"para ele no acompanhamento - vazio diz 'ainda nao ha "
                     f"regra', e R$ 0,00 diria 'nao bateu nada'. Escreva as "
                     f"faixas aqui e clique em GUARDAR ESTA TABELA.",
                foreground=COR_ALERTA)
        else:
            self.lbl_rv_msg.configure(
                text=f"Faixas de {self.var_rv_nivel.get()}. Mexeu? Clique em "
                     f"GUARDAR ESTA TABELA e depois em Salvar parametros, "
                     f"para valer nas proximas vezes que abrir o programa.",
                foreground=COR_SUAVE)
        self._simular_rv()

    def _faixas_da_tela(self) -> dict:
        """
        O que esta escrito na grade, virado em faixas.

        Linha com as tres celulas em branco e linha que nao existe. As
        faixas saem ordenadas pelo DE, para a leitura de cima para baixo
        continuar valendo mesmo que ele digite fora de ordem.
        """
        saida = {}
        for chave, linhas in self.var_rv.items():
            faixas = []
            for de, ate, valor in linhas:
                txt_de, txt_ate = de.get().strip(), ate.get().strip()
                txt_valor = valor.get().strip()
                if not (txt_de or txt_ate or txt_valor):
                    continue
                faixas.append({
                    "de": numero(txt_de, 0.0),
                    # ATE vazio = faixa sem fim, o teto de sempre
                    "ate": (numero(txt_ate) if txt_ate else mn.TETO_DA_FAIXA),
                    "valor": numero(txt_valor, 0.0)})
            saida[chave] = sorted(faixas, key=lambda f: f["de"])
        return saida

    def guardar_rv(self):
        """Guarda a grade no parametro, sem gravar o arquivo ainda."""
        nivel = self._nivel_da_rv()
        self.par.setdefault("rv", mn.rv_padrao())
        self.par["rv"][nivel] = self._faixas_da_tela()
        quantas = sum(len(v) for v in self.par["rv"][nivel].values())
        self._desenhar_rv()
        self.lbl_rv_msg.configure(
            text=f"{quantas} faixas guardadas para "
                 f"{self.var_rv_nivel.get()}. Clique em Salvar parametros "
                 f"(no fim da aba) para elas sobreviverem ao fechar o "
                 f"programa, e em Apurar (aba 3) para a RV de cada pessoa "
                 f"ser recalculada.", foreground=COR_OK)

    def rv_ao_padrao(self):
        nivel = self._nivel_da_rv()
        if not messagebox.askyesno(
                "Gerador de Meta BAP",
                f"Voltar as faixas de {self.var_rv_nivel.get()} ao padrao "
                f"do RH?\n\nAs outras tabelas nao mudam."):
            return
        self.par.setdefault("rv", mn.rv_padrao())
        self.par["rv"][nivel] = (mn.rv_padrao().get(nivel)
                                 or {k: [] for k, _, _ in mn.KPIS_DA_RV})
        self._desenhar_rv()
        self.lbl_rv_msg.configure(
            text=f"Faixas de {self.var_rv_nivel.get()} de volta ao padrao.",
            foreground=COR_SUAVE)

    def _simular_rv(self):
        """Quanto a grade da tela pagaria para o atingimento digitado."""
        if not getattr(self, "var_rv", None):
            return
        faixas = self._faixas_da_tela()
        if not any(faixas.values()):
            self.lbl_rv_sim.configure(
                text="Sem faixas escritas, nao ha o que pagar.",
                foreground=COR_SUAVE)
            return
        partes, total = [], 0.0
        for chave, rotulo, _campo in mn.KPIS_DA_RV:
            ating = numero(self.var_rv_sim[chave].get(), 0.0)
            valor = mn.valor_da_rv(faixas.get(chave) or [], ating)
            total += valor
            partes.append(f"{rotulo} a {numero_br(ating, 1)}% paga "
                          f"R$ {dinheiro(valor)}")
        self.lbl_rv_sim.configure(
            text="   |   ".join(partes) + f"      TOTAL: R$ {dinheiro(total)}",
            foreground=COR_TITULO)

    # --------------------------------------------------------- aba 2
    def _montar_painel(self):
        f = self.aba_painel
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Painel de meta",
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="GRAVAR A META DO MES", style="Big.TButton",
                   command=lambda: self.guardar(avisar=True)).pack(
                       side="right")
        ttk.Button(topo, text="RECALCULAR",
                   command=self.recalcular).pack(side="right", padx=8)
        self.bt_ver_tudo = ttk.Button(topo, text="VER TUDO",
                                      command=self.virar_ver_tudo)
        self.bt_ver_tudo.pack(side="right", padx=8)
        # (06/10) sem filtro de segmento: o painel e so para GERAR a meta
        self.lbl_painel = ttk.Label(f, text="", style="Sub.TLabel",
                                    wraplength=1200)
        self.lbl_painel.pack(anchor="w", pady=(4, 10))

        self.recortes = ttk.Notebook(f)
        self.recortes.pack(fill="both", expand=True)
        for recorte in mn.RECORTES:
            quadro_aba = ttk.Frame(self.recortes, padding=10)
            self.recortes.add(quadro_aba, text=mn.TITULO_DO_RECORTE[recorte])
            quadro, tabela = bp.tabela(quadro_aba, self.COLUNAS, rodape=True)
            quadro.pack(fill="both", expand=True)
            tabela.tag_configure("ajustada", background=COR_AVISO)
            tabela.tag_configure("piso", background="#EEF6EA")
            tabela.bind("<<TreeviewSelect>>",
                        lambda e, r=recorte: self._abrir_edicao(r))
            # DUAS BATIDAS NA LINHA: a meta dela se escreve ali mesmo
            tabela.bind("<Double-1>",
                        lambda e, r=recorte: self._editar_no_painel(r, e))
            self.visoes[recorte] = tabela
        # A META POR CATEGORIA BAP (linha leve, pesada, moto, pneu...)
        quadro_aba = ttk.Frame(self.recortes, padding=10)
        self.recortes.add(quadro_aba, text="CATEGORIA")
        quadro, self.tab_categoria = bp.tabela(
            quadro_aba, [("familia", "CATEGORIA", 220, "w", True)]
            + self.COLUNAS_FAM[1:], rodape=True)
        quadro.pack(fill="both", expand=True)
        ttk.Label(quadro_aba, style="Sub.TLabel", text=(
            "Desafio da categoria no cliente = desafio comercial do cliente × peso "
            "da categoria no que ele comprou nos 3 meses antes (sem compra: o "
            "mix do segmento dele). Soma = desafio comercial.")).pack(
                anchor="w", pady=(6, 0))
        # A META POR FAMILIA DA PECA (a comercial aberta pelo mix do M3M)
        quadro_aba = ttk.Frame(self.recortes, padding=10)
        self.recortes.add(quadro_aba, text="FAMILIA")
        quadro, self.tab_familia = bp.tabela(quadro_aba, self.COLUNAS_FAM,
                                             rodape=True)
        quadro.pack(fill="both", expand=True)
        ttk.Label(quadro_aba, style="Sub.TLabel", text=(
            "Desafio da família no cliente = desafio comercial do cliente × peso da "
            "família no que ele comprou nos 3 meses antes (sem compra: o mix "
            "do segmento dele). Soma = desafio comercial.")).pack(anchor="w",
                                                            pady=(6, 0))

        self._montar_edicao(f)

        bp.legenda_de_cores(f, [
            (COR_AVISO, "meta escrita a mão"),
            ("#EEF6EA", "meta no piso"),
        ]).pack(anchor="w", pady=(8, 0))
        # (05/10) sem o paragrafo de ajuda: duplo clique edita a meta


    COLUNAS_FAM = [
        ("familia", "FAMILIA", 220, "w", True),
        ("meta", "DESAFIO FAT. TT R$", 150, "e", False),
        ("perc", "% DO DESAFIO", 100, "center", False),
        ("m3m", "FAT M3M R$", 140, "e", False),
        ("clientes_m3m", "CLIENTES COM COMPRA NO M3M", 200, "center", False),
    ]

    # ---- a tabela editavel que abre embaixo -----------------------------
    # quem se abre em quem, quando alguem clica numa linha do painel
    FILHO = {"gerente": "supervisor", "supervisor": "vendedor",
             "vendedor": "zona", "zona": "cliente", "segmento": "cliente",
             "uf": "cidade", "cidade": "bairro", "bairro": "cliente",
             "cliente": ""}

    COLUNAS_EDICAO = [
        ("nivel", "NIVEL", 96, "w", False),
        ("codigo", "CODIGO", 100, "w", False),
        ("nome", "NOME", 240, "w", True),
        ("clientes", "CLI.", 56, "center", False),
        ("fat_m3m", "FAT M3M R$", 120, "e", False),
        ("meta_com", "DESAFIO COMERCIAL R$", 150, "e", False),
        ("meta_calculada", "META CALCULADA R$", 160, "e", False),
        ("meta", "META QUE VALE R$", 156, "e", False),
        ("origem", "DE ONDE VEIO A META", 240, "w", False),
    ]

    def _montar_edicao(self, pai):
        self.quadro_edicao = ttk.LabelFrame(
            pai, text=" Editar a meta desta linha ", padding=10)
        # so aparece quando alguem clica numa linha do painel
        self.lbl_edicao = ttk.Label(self.quadro_edicao, text="",
                                    style="Cod.TLabel", wraplength=1200)
        self.lbl_edicao.pack(anchor="w")
        tk.Frame(self.quadro_edicao, height=6).pack()
        quadro, self.tab_edicao = bp.tabela(self.quadro_edicao,
                                            self.COLUNAS_EDICAO, altura=7)
        quadro.pack(fill="x")
        self.tab_edicao.tag_configure("ajustada", background=COR_AVISO)
        self.tab_edicao.tag_configure("pai", background="#EEF6EA")
        self.tab_edicao.bind("<Double-1>", self._clique_na_celula)
        self.tab_edicao.bind("<Return>", lambda _: self._editar_celula(
            self.tab_edicao.focus(), self._coluna_da_meta()))

        botoes = ttk.Frame(self.quadro_edicao)
        botoes.pack(fill="x", pady=(8, 0))
        ttk.Button(botoes, text="VOLTAR ESTA LINHA AO CALCULADO",
                   command=self._desfazer_linha).pack(side="left")
        ttk.Button(botoes, text="Voltar TODAS ao calculado",
                   command=self._desfazer_tudo).pack(side="left", padx=8)
        ttk.Button(botoes, text="Fechar",
                   command=self._fechar_edicao).pack(side="right")
        self._edicao = []          # as linhas que estao na tabela de baixo
        self._celula = None        # a caixinha de digitacao, quando aberta

    # --------------------------------------------------------- aba 3
    # AS SETE METAS na ordem combinada, cada uma com META / REAL / ATING%
    # coladinhos. A ordem vem do nucleo, para a tela e o Excel nunca
    # discordarem um do outro.
    COLUNAS_AC = (
        [("codigo", "CODIGO", 88, "w", False),
         ("nome", "NOME", 200, "w", True),
         # O SUPERVISOR DO VENDEDOR, ao lado do nome dele: a folha do
         # vendedor passa a dizer de quem ele e, sem ter de ir ate a aba
         # do supervisor para descobrir. Nos recortes que nao sao de
         # pessoa a coluna fica vazia.
         ("supervisor", "SUPERVISOR", 170, "w", False),
         ("clientes", "QTD CLI.", 68, "center", False)]
        # VISITA, POSITIVACAO e CAD. COMPRA sao CONTAGEM: cabem em
        # coluna estreita, porque o numero e "38", nao "363.909,63". E o
        # que permite a meta e o realizado dos tres caberem na tela junto
        # com o faturamento, sem barra de rolagem lateral.
        + [c for rotulo, meta, real, ating, gap, nec
           in mn.METAS_DO_ACOMPANHAMENTO
           for larg, larg_at, larg_gap in
           [((80, 92, 96) if rotulo in mn.METAS_DE_CONTAGEM
             else (110, 110, 116))]
           for c in ((meta, f"META {CURTO_AC.get(rotulo, rotulo)}", larg,
                      "e", False),
                     (real, f"REAL {CURTO_AC.get(rotulo, rotulo)}", larg,
                      "e", False),
                     (ating, f"ATING {CURTO_AC.get(rotulo, rotulo)} %",
                      larg_at, "center", False),
                     (gap, f"GAP MES {CURTO_AC.get(rotulo, rotulo)}",
                      larg_gap, "e", False),
                     (nec, f"NEC./DIA {CURTO_AC.get(rotulo, rotulo)}",
                      larg_gap, "e", False))]
        + [("faturamento_carteira", "FAT. CARTEIRA R$", 118, "e", False),
           ("base_visita", "BASE VISITA", 92, "center", False),
           ("base_carteira", "BASE TOTAL", 88, "center", False),
           ("dias_restantes", "DIAS QUE FALTAM", 118, "center", False),
           ("devolvido", "DEVOLVIDO R$", 118, "e", False),
           ("notas", "NOTAS", 66, "center", False)]
        # A RV fecha a tabela: e consequencia do atingimento, entao vem
        # depois dele. Fica fora do EXEC_ACOMP de proposito - quem quer
        # ver quanto cada um esta ganhando marca no VER TUDO ou no
        # IMPRIMIR/EXPORTAR, como qualquer outro indicador.
        + [(f"rv_{chave}", f"RV {CURTO_AC.get(rotulo, rotulo)} R$", 112,
            "e", False)
           for chave, rotulo, _campo in mn.KPIS_DA_RV]
        + [("rv_total", "RV TOTAL R$", 112, "e", False)]
    )

    # MODO EXECUTIVO: as colunas que cabem numa tela e respondem a
    # pergunta do gerente - bateu ou nao bateu. O VER TUDO abre o resto,
    # para quem precisa investigar de onde o numero saiu.
    # a ordem tambem e a da folha impressa: o dinheiro primeiro, que e a
    # primeira pergunta, e os indicadores de atividade depois
    EXEC_PAINEL = ["codigo", "nome", "meta", "meta_rh", "base_visita",
                   "meta_visita",
                   "meta_positivacao", "meta_cadastro", "fat_m3m", "faixa"]
    # O EXECUTIVO mostrava so o ATINGIMENTO de visita, positivacao e
    # cadastro - um percentual solto, sem o numero de onde ele saiu. Com
    # META e REAL ao lado da pergunta e respondida de uma vez: "62 de 88
    # visitas, 70%".
    EXEC_ACOMP = ["codigo", "nome", "supervisor", "clientes", "meta",
                  "realizado",
                  "faturamento_carteira", "atingimento", "falta", "nec_fat",
                  "meta_visita_int", "visitas_realizadas",
                  "atingimento_visita",
                  "meta_positivacao_int", "positivados",
                  "atingimento_positivacao",
                  "meta_cadastro_int", "cadastros_com_compra",
                  "atingimento_cadastro"]

    def virar_ver_tudo(self):
        """Troca entre o modo EXECUTIVO (cabe na tela) e a visao inteira."""
        self._ver_tudo = not getattr(self, "_ver_tudo", False)
        self._aplicar_modo()

    def _aplicar_modo(self):
        """
        Esconde ou mostra colunas sem refazer a tabela: o displaycolumns
        so muda o que aparece, os valores continuam la. O rodape (a linha
        TOTAL) segue junto, senao as duas desalinham.
        """
        tudo = getattr(self, "_ver_tudo", False)
        for tabelas, colunas, exec_ in (
                (self.visoes, self.COLUNAS, self.EXEC_PAINEL),
                (self.visoes_ac, self.COLUNAS_AC, self.EXEC_ACOMP)):
            # no modo executivo a ORDEM tambem e a do conjunto - o
            # dinheiro na frente, igual a folha impressa
            existem = {c[0] for c in colunas}
            chaves = ([c[0] for c in colunas] if tudo
                      else [c for c in exec_ if c in existem])
            for t in tabelas.values():
                try:
                    t.configure(displaycolumns=chaves)
                    for chave in chaves:
                        t.column(chave, stretch=(chave == "nome") or not tudo)
                    rodape = getattr(t, "_rodape", None)
                    if rodape is not None:
                        rodape.configure(displaycolumns=chaves)
                        if getattr(rodape, "_alinhar_agora", None):
                            rodape.after_idle(rodape._alinhar_agora)
                except tk.TclError:
                    pass
        texto = "VER SO O EXECUTIVO" if tudo else "VER TUDO"
        for nome in ("bt_ver_tudo", "bt_ver_tudo_ac"):
            bt = getattr(self, nome, None)
            if bt is not None:
                bt.configure(text=texto)

    def _montar_acompanhamento(self):
        f = self.aba_acomp
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Acompanhamento da meta",
                  style="Titulo.TLabel").pack(side="left")
        # EXPORTAR PARA O RH mora na aba 6 IMPRIMIR / EXPORTAR, junto
        # com todo o resto que gera arquivo. Aqui seria o segundo botao
        # a fazer a mesma coisa, e dois botoes iguais em telas
        # diferentes viram duvida sobre qual e o certo.
        ttk.Button(topo, text="APURAR AGORA", style="Big.TButton",
                   command=self.apurar).pack(side="right")
        self.bt_ver_tudo_ac = ttk.Button(topo, text="VER TUDO",
                                         command=self.virar_ver_tudo)
        self.bt_ver_tudo_ac.pack(side="right")

        linha = ttk.Frame(f)
        linha.pack(fill="x", pady=(8, 0))
        ttk.Label(linha, text="Mes (AAAA-MM):").pack(side="left")
        self.var_comp = tk.StringVar()
        self.cb_comp = ttk.Combobox(linha, textvariable=self.var_comp,
                                    width=12, justify="center")
        self.cb_comp.pack(side="left", padx=6)
        ttk.Button(linha, text="Meses ja gravados",
                   command=self._encher_meses).pack(side="left")
        # OS DOIS PARAGRAFOS DE EXPLICACAO SAIRAM DAQUI. O que eles diziam
        # esta na tabela (META e REAL de cada indicador, FAT. CARTEIRA ao
        # lado do REAL) e na legenda do rodape. O cabecalho ficou para o
        # que muda: o mes, os filtros e o aviso quando ha algo errado.
        self._barra_de_filtro(linha)
        self.lbl_acomp = ttk.Label(f, text="", style="Sub.TLabel",
                                   wraplength=1250)
        self.lbl_acomp.pack(anchor="w", pady=(6, 8))

        self.recortes_ac = ttk.Notebook(f)
        self.recortes_ac.pack(fill="both", expand=True)
        for recorte in mn.RECORTES:
            quadro_aba = ttk.Frame(self.recortes_ac, padding=10)
            self.recortes_ac.add(quadro_aba,
                                 text=mn.TITULO_DO_RECORTE[recorte])
            quadro, t = bp.tabela(quadro_aba, self.COLUNAS_AC, rodape=True)
            quadro.pack(fill="both", expand=True)
            t.tag_configure("bateu", background="#E4F3E9")
            t.tag_configure("longe", background=COR_AVISO)
            t.tag_configure("fora", background="#F1F1F4")
            self.visoes_ac[recorte] = t
        self._montar_familia_ac()

        # ---- a classificacao dos produtos -------------------------------
        quadro = ttk.LabelFrame(f, text=" Classificacao dos produtos (para o "
                                        "realizado por categoria) ", padding=10)
        quadro.pack(fill="x", pady=(10, 0))
        self.lbl_csv = ttk.Label(quadro, text="", style="Sub.TLabel",
                                 wraplength=1250)
        self.lbl_csv.pack(anchor="w", pady=(0, 6))
        ttk.Label(quadro, text="Sem o CATEGORIAS_PRODUTO.csv, sobra o "
                               "FORNECEDOR da TABELA_BAP - e ele so conhece "
                               "lubrificante. Ai da para dizer aqui embaixo a "
                               "categoria de cada fornecedor, e tudo o que "
                               "sobrar entra como PECAS.",
                  style="Sub.TLabel", wraplength=1250).pack(anchor="w")
        corpo = ttk.Frame(quadro)
        corpo.pack(fill="x", pady=(8, 0))
        self.lst_forn = tk.Listbox(corpo, height=5, relief="flat",
                                   borderwidth=0, highlightthickness=1,
                                   highlightbackground=COR_LINHA,
                                   font=(self.FONTE, 9), background=COR_PAPEL,
                                   exportselection=False)
        self.lst_forn.pack(side="left", fill="x", expand=True)
        self.lst_forn.bind("<<ListboxSelect>>", lambda _: self._ler_fornecedor())
        lado = ttk.Frame(corpo)
        lado.pack(side="left", padx=12)
        self.var_forn_cat = tk.StringVar(value=mn.CATEGORIA_PADRAO)
        ttk.Combobox(lado, textvariable=self.var_forn_cat, width=16,
                     state="readonly",
                     values=[c for c, _, _ in mn.CATEGORIAS]).pack()
        ttk.Button(lado, text="Aplicar neste fornecedor",
                   command=self.aplicar_fornecedor).pack(pady=(6, 0))

        bp.legenda_de_cores(f, [
            ("#E4F3E9", "bateu a meta (100% ou mais)"),
            (COR_AVISO, "abaixo de 70% da meta"),
            ("#F1F1F4", "faturou e nao esta no PLANNER - sem meta"),
        ]).pack(anchor="w", pady=(8, 0))
        ttk.Label(f, style="Sub.TLabel", anchor="w", justify="left",
                  text="Nos titulos: VIS. = VISITA   |   POS. = "
                       "POSITIVACAO   |   CAD. = CADASTRO COM COMPRA   |   "
                       "FAT TT = FATURAMENTO TOTAL. Cada indicador tem META, "
                       "REAL e ATING %; o GAP DO MES e o NEC./DIA aparecem "
                       "no VER TUDO."
                  ).pack(anchor="w", pady=(2, 0))

    # --------------------------------------------------------- aba 5
    # QUEM CONTA NA META DO SUPERVISOR, MES A MES
    #
    # A cadeira vaga, o vendedor que entrou este mes, a zona que ninguem
    # cobre: a carteira continua com meta e o REALIZADO deles continua
    # somando para o supervisor - se vendeu, vendeu. O que fica de fora e
    # a META daquele mes (faturamento, visita e positivacao).
    COLUNAS_CONTA = {
        "vendedor": [("conta", "CONTA?", 78, "center", False),
                     ("codigo", "CODIGO", 86, "w", False),
                     ("nome", "VENDEDOR", 180, "w", True),
                     ("dono", "SUPERVISOR", 150, "w", False),
                     ("clientes", "QTD CLI.", 74, "center", False),
                     ("meta", "META FAT. R$", 128, "e", False)],
        "zona": [("conta", "CONTA?", 78, "center", False),
                 ("codigo", "CODIGO", 86, "w", False),
                 ("nome", "ZONA", 180, "w", True),
                 ("dono", "VENDEDOR", 150, "w", False),
                 ("clientes", "QTD CLI.", 74, "center", False),
                 ("meta", "META FAT. R$", 128, "e", False)],
    }
    TITULO_CONTA = {"vendedor": "Vendedores", "zona": "Zonas"}

    def _montar_quem_conta(self):
        f = self.aba_conta
        ttk.Label(f, text="Quem conta na meta do supervisor",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            f, wraplength=1360, style="Sub.TLabel",
            text="Escolha o MES e diga quem entra na meta do supervisor "
                 "naquele mes. Quem fica em NAO continua com a meta dele "
                 "(a carteira e dos clientes) e o REALIZADO dele continua "
                 "somando para o supervisor - se vendeu, vendeu. O que nao "
                 "sobe para o supervisor e a META daquele mes: faturamento, "
                 "visita e positivacao. O resto do painel - UF, gerente, "
                 "cidade, total - nao muda."
        ).pack(anchor="w", pady=(2, 10))

        topo = tk.Frame(f, background="#EEF6EA", highlightthickness=1,
                        highlightbackground=COR_LINHA)
        topo.pack(fill="x", pady=(0, 12))
        tk.Label(topo, text="MES:", background="#EEF6EA",
                 foreground=COR_TITULO, font=(self.FONTE, 9, "bold"),
                 padx=14, pady=10).pack(side="left")
        self.var_comp_conta = tk.StringVar()
        cb = ttk.Combobox(topo, textvariable=self.var_comp_conta, width=11,
                          justify="center", values=mn.meses_por_perto())
        cb.pack(side="left", pady=10)
        cb.bind("<<ComboboxSelected>>", lambda _: self._mes_do_conta_mudou())
        cb.bind("<FocusOut>", lambda _: self._mes_do_conta_mudou())
        self.cb_comp_conta = cb
        ttk.Button(topo, text="GRAVAR A DECISAO DESTE MES",
                   style="Big.TButton",
                   command=self.gravar_quem_conta).pack(side="right", padx=12,
                                                        pady=8)
        ttk.Button(topo, text="Copiar do mes anterior",
                   command=self.copiar_quem_conta).pack(side="right")
        ttk.Button(topo, text="Todos contam",
                   command=lambda: self._todos_no_conta(True)).pack(
            side="right", padx=6)
        self.lbl_conta_msg = tk.Label(topo, text="", background="#EEF6EA",
                                      foreground=COR_SUAVE,
                                      font=(self.FONTE, 9), justify="left",
                                      wraplength=620, anchor="w", padx=12)
        self.lbl_conta_msg.pack(side="left", padx=(6, 0))

        corpo = ttk.Frame(f)
        corpo.pack(fill="both", expand=True)
        self.tab_conta = {}
        for i, nivel in enumerate(mn.NIVEIS_DO_CORTE):
            lado = ttk.LabelFrame(corpo, text=f" {self.TITULO_CONTA[nivel]} ",
                                  padding=10)
            lado.pack(side="left", fill="both", expand=True,
                      padx=(0, 12) if i == 0 else 0)
            ttk.Label(lado, style="Sub.TLabel", wraplength=560,
                      text="Clique duas vezes na linha (ou use o botao "
                           "abaixo) para virar de SIM para NAO."
                      ).pack(anchor="w", pady=(0, 6))
            quadro, t = bp.tabela(lado, self.COLUNAS_CONTA[nivel],
                                  selecao="extended", horizontal=False)
            quadro.pack(fill="both", expand=True)
            t.tag_configure("fora", background=COR_AVISO,
                            foreground=COR_TITULO)
            t.bind("<Double-1>", lambda _e, n=nivel: self._virar_conta(n))
            t.bind("<space>", lambda _e, n=nivel: self._virar_conta(n))
            self.tab_conta[nivel] = t
            barra = ttk.Frame(lado)
            barra.pack(fill="x", pady=(6, 0))
            ttk.Button(barra, text="VIRAR SIM / NAO",
                       command=lambda n=nivel: self._virar_conta(n)).pack(
                side="left")
            ttk.Button(barra, text="Todos desta lista contam",
                       command=lambda n=nivel: self._todos_no_conta(
                           True, n)).pack(side="left", padx=6)

        bp.legenda_de_cores(f, [
            (COR_AVISO, "NAO conta na meta do supervisor neste mes - a meta "
                        "dele continua existindo, mas nao sobe para a equipe"),
        ]).pack(anchor="w", pady=(8, 0))

    def _mes_do_conta(self) -> str:
        """O mes da aba 5 - o dela, e nao o da meta, que pode ser outro."""
        return (mn.normalizar_competencia(self.var_comp_conta.get())
                or mn.normalizar_competencia(self.var_competencia.get())
                or (self.dados or {}).get("competencia", ""))

    def _mes_do_conta_mudou(self):
        comp = self._mes_do_conta()
        if comp:
            self.var_comp_conta.set(comp)
        if comp != self.comp_conta:
            self._carregar_quem_conta(comp)

    def _linhas_do_conta(self, nivel: str) -> list:
        """
        A lista de vendedores (ou zonas) para marcar. Sai da meta gerada,
        quando ja ha uma; sem ela, sai do proprio PLANNER - para dar para
        decidir o mes ANTES de gerar.
        """
        clientes = (self.dados or {}).get("clientes") or []
        dono = {}
        contagem = {}
        for c in clientes:
            chave = c.get("cod_vendedor" if nivel == "vendedor" else "cod_zona")
            if not chave:
                continue
            dono.setdefault(chave, c.get("supervisor" if nivel == "vendedor"
                                         else "vendedor", ""))
            contagem[chave] = contagem.get(chave, 0) + 1
        linhas = []
        if self.resultado:
            for l in self.resultado["recortes"][nivel]:
                if not l["chave"]:
                    continue
                linhas.append({"chave": l["chave"],
                               "codigo": l.get("codigo") or l["chave"],
                               "nome": l.get("nome") or l["rotulo"],
                               "dono": dono.get(l["chave"], ""),
                               "clientes": l["clientes"], "meta": l["meta"]})
        else:
            nomes = {}
            for c in clientes:
                chave = c.get("cod_vendedor" if nivel == "vendedor"
                              else "cod_zona")
                if chave:
                    nomes.setdefault(chave, c.get("vendedor" if nivel ==
                                                  "vendedor" else "zona", ""))
            for chave, nome in nomes.items():
                linhas.append({"chave": chave, "codigo": chave, "nome": nome,
                               "dono": dono.get(chave, ""),
                               "clientes": contagem.get(chave, 0),
                               "meta": 0.0})
        return sorted(linhas, key=lambda x: (-x["meta"], x["nome"]))

    def _carregar_quem_conta(self, comp=""):
        """Traz para a tela a decisao gravada do mes - ou a sugestao."""
        comp = comp or self._mes_do_conta()
        self.comp_conta = comp
        self.var_comp_conta.set(comp)
        fonte = mn.fora_do_mes(self.par, comp,
                               (self.dados or {}).get("clientes") or [])
        self.fora_tela = {n: set(fonte.get(n) or ())
                          for n in mn.NIVEIS_DO_CORTE}
        self._desenhar_quem_conta()

    def _desenhar_quem_conta(self):
        comp = self.comp_conta
        for nivel in mn.NIVEIS_DO_CORTE:
            t = self.tab_conta[nivel]
            marcada = t.selection()
            t.delete(*t.get_children())
            for linha in self._linhas_do_conta(nivel):
                fora = linha["chave"] in self.fora_tela[nivel]
                t.insert("", "end", iid=linha["chave"],
                         tags=("fora",) if fora else (),
                         values=("NAO" if fora else "SIM", linha["codigo"],
                                 linha["nome"], linha["dono"] or "-",
                                 linha["clientes"], dinheiro(linha["meta"])))
            for m in marcada:
                if t.exists(m):
                    t.selection_set(m)
        fora_v = len(self.fora_tela["vendedor"])
        fora_z = len(self.fora_tela["zona"])
        if mn.mes_configurado(self.par, comp):
            texto = f"{comp}: decisao GRAVADA."
            cor = COR_OK
        else:
            texto = (f"{comp}: ainda NAO gravado - o que esta na tela e a "
                     f"sugestao (o ultimo mes decidido; na primeira vez, o "
                     f"que vinha do PLANNER). Grave para congelar.")
            cor = COR_ALERTA
        texto += (f"   Fora da meta: {fora_v} vendedor(es) e {fora_z} zona(s)."
                  if (fora_v or fora_z) else "   Todos contam neste mes.")
        self.lbl_conta_msg.configure(text=texto, foreground=cor)

    def _virar_conta(self, nivel: str):
        t = self.tab_conta[nivel]
        sel = t.selection()
        if not sel:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Marque na lista quem voce quer virar.")
            return "break"
        for chave in sel:
            if chave in self.fora_tela[nivel]:
                self.fora_tela[nivel].discard(chave)
            else:
                self.fora_tela[nivel].add(chave)
        self._desenhar_quem_conta()
        return "break"

    def _todos_no_conta(self, contam: bool, nivel=""):
        for n in ([nivel] if nivel else list(mn.NIVEIS_DO_CORTE)):
            if contam:
                self.fora_tela[n] = set()
            else:
                self.fora_tela[n] = {l["chave"]
                                     for l in self._linhas_do_conta(n)}
        self._desenhar_quem_conta()

    def copiar_quem_conta(self):
        """Traz para este mes a decisao do ultimo mes ja decidido."""
        comp = self._mes_do_conta()
        guardados = sorted(k for k in (self.par.get("fora_da_meta") or {})
                           if k < comp)
        if not guardados:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Nao ha nenhum mes decidido antes deste.")
            return
        de = guardados[-1]
        fonte = mn.fora_da_meta(self.par, de)
        self.fora_tela = {n: set(fonte.get(n) or ())
                          for n in mn.NIVEIS_DO_CORTE}
        self._desenhar_quem_conta()
        self.aviso(f"Copiado de {de}. Clique em GRAVAR A DECISAO DESTE MES "
                   f"para valer em {comp}.", COR_ALERTA)

    def gravar_quem_conta(self):
        comp = self._mes_do_conta()
        if not comp:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Escolha o mes (AAAA-MM) antes de gravar.")
            return
        mn.guardar_fora_da_meta(self.par, comp,
                                self.fora_tela["vendedor"],
                                self.fora_tela["zona"])
        self._gravar_par()
        self._desenhar_quem_conta()
        recado = (f"Gravado: em {comp}, "
                  f"{len(self.fora_tela['vendedor'])} vendedor(es) e "
                  f"{len(self.fora_tela['zona'])} zona(s) ficam fora da meta "
                  f"do supervisor. So muda se voce mudar de novo.")
        # se a meta na tela e desse mes, refaz agora para o painel ja
        # mostrar o efeito
        if self.dados and self.resultado and \
                self.resultado.get("competencia") == comp:
            self.resultado = mn.calcular(self.dados, self.par)
            self._fechar_edicao()
            self._desenhar()
            recado += "   O painel de meta foi refeito."
        elif self.dados:
            recado += "   Clique em GERAR A META para o painel acompanhar."
        self.aviso(recado, COR_OK)

    # --------------------------------------------------------- aba 6
    # IMPRIMIR / EXPORTAR
    #
    # A tela do acompanhamento tem oito metas em META/REAL/ATING - 30 e
    # tantas colunas. Isso nunca vai caber num A4 e nem deve: a folha do
    # gerente e outra coisa. Aqui se escolhe O QUE, QUAIS RECORTES e
    # QUAIS COLUNAS, e sai uma pagina por recorte, em A4 deitado, ja com
    # as colunas executivas marcadas.
    RECORTES_DA_FOLHA = ["gerente", "supervisor", "vendedor", "zona", "uf",
                         "cidade", "bairro", "cliente"]
    # NEC./DIA de gente vai com uma casa (0,4 por dia nao e zero); o GAP
    # de gente e inteiro
    NEC_DE_CONTAGEM = {nec for rotulo, _, _, _, _, nec
                       in mn.METAS_DO_ACOMPANHAMENTO
                       if rotulo in mn.METAS_DE_CONTAGEM}
    GAP_DE_CONTAGEM = {gap for rotulo, _, _, _, gap, _
                       in mn.METAS_DO_ACOMPANHAMENTO
                       if rotulo in mn.METAS_DE_CONTAGEM}
    # os que valem a pena imprimir de fabrica: os que cabem numa folha
    FOLHA_PADRAO = ["gerente", "supervisor", "vendedor", "uf"]
    GRANDES = {"cliente", "bairro"}

    def _montar_folha(self):
        f = self.aba_folha
        ttk.Label(f, text="Imprimir / exportar",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(f, style="Sub.TLabel", wraplength=1360,
                  text="Uma pagina por recorte, em A4 DEITADO, com as "
                       "colunas executivas ja marcadas. ABRIR PARA IMPRIMIR "
                       "abre a folha no seu navegador: Ctrl+P, destino "
                       "'Salvar como PDF', layout Paisagem."
                  ).pack(anchor="w", pady=(2, 12))

        moldura_f = tk.Frame(f, background="#EEF6EA", highlightthickness=1,
                             highlightbackground=COR_LINHA)
        moldura_f.pack(fill="x", pady=(0, 12))
        topo = tk.Frame(moldura_f, background="#EEF6EA")
        topo.pack(fill="x")
        tk.Label(topo, text="O QUE IMPRIMIR:", background="#EEF6EA",
                 foreground=COR_TITULO, font=(self.FONTE, 9, "bold"),
                 padx=14, pady=10).pack(side="left")
        self.var_folha_o_que = tk.StringVar(value="ACOMPANHAMENTO")
        cb = ttk.Combobox(topo, textvariable=self.var_folha_o_que, width=18,
                          state="readonly",
                          values=["ACOMPANHAMENTO", "PAINEL DE META"])
        self._barra_de_filtro(topo)
        cb.pack(side="left", pady=8)
        cb.bind("<<ComboboxSelected>>",
                lambda _: (self._encher_colunas_folha(),
                           self._nivel_da_folha()))
        ttk.Button(topo, text="ABRIR PARA IMPRIMIR", style="Big.TButton",
                   command=self.imprimir_folha).pack(side="right", padx=12,
                                                     pady=8)
        ttk.Button(topo, text="EXPORTAR EXCEL",
                   command=self.exportar_folha).pack(side="right")
        ttk.Button(topo, text="EXPORTAR PARA O RH",
                   command=self.exportar_acompanhamento).pack(side="right",
                                                              padx=8)

        # ---- o recorte: imprimir so o pedaco de alguem -----------------
        filtro = tk.Frame(topo, background="#EEF6EA")
        filtro.pack(side="left", padx=(18, 0))
        tk.Label(filtro, text="SO DE:", background="#EEF6EA",
                 foreground=COR_TITULO,
                 font=(self.FONTE, 9, "bold")).pack(side="left")
        self.var_folha_nivel = tk.StringVar(value=TODOS_DA_FOLHA)
        cb_n = ttk.Combobox(filtro, textvariable=self.var_folha_nivel,
                            width=13, state="readonly",
                            values=[TODOS_DA_FOLHA] +
                                   [mn.TITULO_DO_RECORTE[n]
                                    for n in mn.NIVEIS_DA_FOLHA])
        cb_n.pack(side="left", padx=6)
        cb_n.bind("<<ComboboxSelected>>", lambda _: self._nivel_da_folha())
        self.var_folha_alvo = tk.StringVar(value=TODOS_DA_FOLHA)
        self.cb_folha_alvo = ttk.Combobox(
            filtro, textvariable=self.var_folha_alvo, width=32,
            state="disabled", values=[TODOS_DA_FOLHA])
        self.cb_folha_alvo.pack(side="left")
        self.cb_folha_alvo.bind("<<ComboboxSelected>>",
                                lambda _: self._contar_folha())

        self.lbl_folha = tk.Label(moldura_f, text="", background="#EEF6EA",
                                  foreground=COR_SUAVE,
                                  font=(self.FONTE, 9), anchor="w",
                                  justify="left", wraplength=1820, padx=14)
        self.lbl_folha.pack(fill="x", pady=(0, 8))

        corpo = ttk.Frame(f)
        corpo.pack(fill="both", expand=True)

        q_rec = ttk.LabelFrame(corpo, text=" Quais recortes (um por pagina) ",
                               padding=12)
        q_rec.pack(side="left", fill="both", padx=(0, 16))
        self.var_folha_rec = {}
        for recorte in self.RECORTES_DA_FOLHA:
            v = tk.BooleanVar(value=recorte in self.FOLHA_PADRAO)
            self.var_folha_rec[recorte] = v
            texto = mn.TITULO_DO_RECORTE[recorte]
            if recorte in self.GRANDES:
                texto += "   (nao cabe em uma pagina)"
            ttk.Checkbutton(q_rec, text=texto, variable=v,
                            command=self._contar_folha).pack(anchor="w",
                                                             pady=2)
        ttk.Button(q_rec, text="Todos", command=lambda: self._todos_folha(True)
                   ).pack(side="left", pady=(10, 0))
        ttk.Button(q_rec, text="Nenhum",
                   command=lambda: self._todos_folha(False)).pack(
            side="left", padx=6, pady=(10, 0))

        # ---- as colunas: quais E EM QUE ORDEM -------------------------
        # Duas listas em vez de caixinhas: a da direita e a folha, de cima
        # para baixo, e e ela que manda na ordem das colunas. So marcar
        # nao bastava - o lugar da coluna na folha e meio caminho da
        # leitura.
        q_col = ttk.LabelFrame(corpo, text=" Quais colunas, e em que ordem ",
                               padding=12)
        q_col.pack(side="left", fill="both", expand=True)
        ttk.Label(q_col, style="Sub.TLabel", wraplength=1100,
                  text="A lista da direita E A FOLHA: a primeira linha e a "
                       "primeira coluna. Ja vem com o conjunto executivo na "
                       "ordem que se le - o dinheiro na frente, os "
                       "indicadores de atividade depois. Clique duas vezes "
                       "para passar de um lado para o outro."
                  ).pack(anchor="w", pady=(0, 8))
        corpo_col = ttk.Frame(q_col)
        corpo_col.pack(fill="both", expand=True)

        esq_col = ttk.Frame(corpo_col)
        esq_col.pack(side="left", fill="both", expand=True)
        ttk.Label(esq_col, text="Disponiveis",
                  style="Cod.TLabel").pack(anchor="w")
        self.lst_disp = tk.Listbox(
            esq_col, selectmode="extended", exportselection=False,
            activestyle="none", font=(self.FONTE, 9), relief="flat",
            borderwidth=0, highlightthickness=1,
            highlightbackground=COR_LINHA, highlightcolor=COR_ACENTO,
            background=COR_PAPEL, foreground=COR_TEXTO,
            selectbackground=COR_ACENTO, selectforeground="white")
        self.lst_disp.pack(fill="both", expand=True, pady=(4, 0))
        self.lst_disp.bind("<Double-1>", lambda _: self.por_na_folha())

        meio = ttk.Frame(corpo_col)
        meio.pack(side="left", fill="y", padx=10)
        ttk.Label(meio, text=" ").pack()
        ttk.Button(meio, text="ADICIONAR  >",
                   command=self.por_na_folha).pack(pady=(24, 4), fill="x")
        ttk.Button(meio, text="<  TIRAR",
                   command=self.tirar_da_folha).pack(pady=4, fill="x")
        ttk.Separator(meio).pack(fill="x", pady=10)
        ttk.Button(meio, text="SUBIR",
                   command=lambda: self.mover_na_folha(-1)).pack(pady=4,
                                                                 fill="x")
        ttk.Button(meio, text="DESCER",
                   command=lambda: self.mover_na_folha(1)).pack(pady=4,
                                                                fill="x")
        ttk.Separator(meio).pack(fill="x", pady=10)
        ttk.Button(meio, text="Voltar ao executivo",
                   command=self.folha_executiva).pack(pady=4, fill="x")

        dir_col = ttk.Frame(corpo_col)
        dir_col.pack(side="left", fill="both", expand=True)
        ttk.Label(dir_col, text="Na folha, nesta ordem",
                  style="Cod.TLabel").pack(anchor="w")
        self.lst_folha = tk.Listbox(
            dir_col, selectmode="extended", exportselection=False,
            activestyle="none", font=(self.FONTE, 9), relief="flat",
            borderwidth=0, highlightthickness=1,
            highlightbackground=COR_LINHA, highlightcolor=COR_ACENTO,
            background=COR_PAPEL, foreground=COR_TEXTO,
            selectbackground=COR_ACENTO, selectforeground="white")
        self.lst_folha.pack(fill="both", expand=True, pady=(4, 0))
        self.lst_folha.bind("<Double-1>", lambda _: self.tirar_da_folha())

        self.var_folha_col = {}
        self.ordem_da_folha = {}
        self._encher_colunas_folha()

    def _nivel_escolhido(self) -> str:
        """O recorte do filtro, com o nome interno (vendedor, zona...)."""
        escolhido = self.var_folha_nivel.get()
        for nivel in mn.NIVEIS_DA_FOLHA:
            if mn.TITULO_DO_RECORTE[nivel] == escolhido:
                return nivel
        return ""

    def _fonte_da_folha(self):
        """De onde saem as linhas: o acompanhamento ou o painel de meta."""
        if self.var_folha_o_que.get() == "PAINEL DE META":
            return self._resultado_tela()
        return self._acomp_tela()

    def _nivel_da_folha(self):
        """Trocou o nivel do filtro: a caixinha do alvo se refaz."""
        nivel = self._nivel_escolhido()
        fonte = self._fonte_da_folha()
        if not nivel:
            self.cb_folha_alvo.configure(values=[TODOS_DA_FOLHA],
                                         state="disabled")
            self.var_folha_alvo.set(TODOS_DA_FOLHA)
            self._contar_folha()
            return
        if not fonte:
            self.cb_folha_alvo.configure(values=[TODOS_DA_FOLHA],
                                         state="disabled")
            self.var_folha_alvo.set(TODOS_DA_FOLHA)
            self.lbl_folha.configure(
                text="Gere a meta (aba 1) ou apure o acompanhamento (aba 3) "
                     "para a lista aparecer aqui.", foreground=COR_ALERTA)
            return
        self._alvos_folha = mn.alvos_para_a_folha(fonte, nivel)
        rotulos = [TODOS_DA_FOLHA] + [r for _, r in self._alvos_folha]
        self.cb_folha_alvo.configure(values=rotulos, state="readonly")
        if self.var_folha_alvo.get() not in rotulos:
            self.var_folha_alvo.set(TODOS_DA_FOLHA)
        self._contar_folha()

    def _alvo_da_folha(self):
        """(nivel, chave) do filtro que esta valendo - ou ('', '')."""
        nivel = self._nivel_escolhido()
        rotulo = self.var_folha_alvo.get()
        if not nivel or rotulo in (TODOS_DA_FOLHA, ""):
            return "", ""
        for chave, nome in getattr(self, "_alvos_folha", []):
            if nome == rotulo:
                return nivel, chave
        return "", ""

    def _colunas_da_fonte(self):
        """As colunas disponiveis e as que vem marcadas, conforme a fonte."""
        if self.var_folha_o_que.get() == "PAINEL DE META":
            return self.COLUNAS, self.EXEC_PAINEL
        return self.COLUNAS_AC, self.EXEC_ACOMP

    def _tipo_da_coluna(self, chave: str) -> str:
        if chave in ("codigo", "nome", "rotulo", "faixa", "supervisor"):
            return "texto"
        if chave in self.NEC_DE_CONTAGEM:
            return "decimal"
        if chave in self.GAP_DE_CONTAGEM or chave == "dias_restantes":
            return "inteiro"
        if chave.startswith("atingimento") or chave.startswith("ating_") \
                or chave.endswith("_pct") or chave == "conversao_cadastro":
            return "pct"
        if chave in ("meta_visita", "meta_positivacao", "meta_cadastro",
                     "meta_visita_int", "meta_positivacao_int",
                     "meta_cadastro_int", "visitas_realizadas", "positivados",
                     "cadastros_com_compra", "cadastros_no_mes", "clientes",
                     "notas", "base_visita", "base_carteira",
                     "positivacao_base", "visitas", "visitas_deposito",
                     "excedentes"):
            return "inteiro"
        return "dinheiro"

    def _rotulos_da_fonte(self) -> dict:
        colunas, _ = self._colunas_da_fonte()
        return {chave: rotulo for chave, rotulo, _, _, _ in colunas}

    def _encher_colunas_folha(self):
        """
        Refaz as duas listas para a fonte escolhida. A ordem de quem ja
        estava na folha e guardada por fonte (acompanhamento e painel tem
        colunas diferentes), e volta gravada do meta_config.json.
        """
        colunas, executivas = self._colunas_da_fonte()
        fonte = self.var_folha_o_que.get()
        guardada = (self.par.get("folha_colunas") or {}).get(fonte)
        vistas = (self.par.get("folha_colunas_vistas") or {}).get(fonte) or []
        validas = [c for c, _, _, _, _ in colunas]
        escolhida = self.ordem_da_folha.get(fonte)
        if escolhida is None:
            escolhida = [c for c in (guardada or executivas) if c in validas]
            # COLUNA QUE NASCEU DEPOIS da ordem ter sido gravada entra
            # sozinha, no lugar dela. Sem isto, toda coluna nova ficava
            # escondida ate alguem clicar em "Voltar ao executivo" - e
            # perder a ordem que ele montou. So vale para coluna que ele
            # NUNCA viu: a que ele tirou da folha de proposito ja esta na
            # lista de vistas e continua fora.
            # ORDEM GRAVADA POR UMA VERSAO ANTERIOR nao tem lista de
            # vistas nenhuma. Ai o programa poe as executivas que
            # faltarem, UMA VEZ, e grava a lista - na pior das hipoteses
            # ele tira de novo a que nao quer, e dessa vez fica.
            if guardada:
                for chave in executivas:
                    if chave in escolhida or chave in vistas:
                        continue
                    antes = [c for c in executivas[:executivas.index(chave)]
                             if c in escolhida]
                    escolhida.insert(
                        escolhida.index(antes[-1]) + 1 if antes else 0, chave)
        self.ordem_da_folha[fonte] = [c for c in escolhida if c in validas]
        self._desenhar_colunas_folha()

    def _desenhar_colunas_folha(self):
        colunas, _ = self._colunas_da_fonte()
        fonte = self.var_folha_o_que.get()
        na_folha = self.ordem_da_folha.get(fonte) or []
        rotulos = self._rotulos_da_fonte()
        self.lst_disp.delete(0, "end")
        self._disp_chaves = [c for c, _, _, _, _ in colunas
                             if c not in na_folha]
        for chave in self._disp_chaves:
            self.lst_disp.insert("end", rotulos.get(chave, chave))
        self.lst_folha.delete(0, "end")
        for i, chave in enumerate(na_folha, start=1):
            self.lst_folha.insert("end", f"{i:2d}. {rotulos.get(chave, chave)}")
        # o var_folha_col continua existindo: e por ele que o resto do
        # programa (e o teste) pergunta se a coluna esta na folha
        self.var_folha_col = {c: tk.BooleanVar(value=c in na_folha)
                              for c, _, _, _, _ in colunas}
        self._contar_folha()

    def por_na_folha(self):
        """Passa o que esta marcado na esquerda para o fim da folha."""
        fonte = self.var_folha_o_que.get()
        escolhidos = [self._disp_chaves[i]
                      for i in self.lst_disp.curselection()]
        if not escolhidos:
            return
        self.ordem_da_folha.setdefault(fonte, []).extend(escolhidos)
        self._desenhar_colunas_folha()

    def tirar_da_folha(self):
        fonte = self.var_folha_o_que.get()
        na_folha = self.ordem_da_folha.get(fonte) or []
        fora = {na_folha[i] for i in self.lst_folha.curselection()
                if i < len(na_folha)}
        if not fora:
            return
        self.ordem_da_folha[fonte] = [c for c in na_folha if c not in fora]
        self._desenhar_colunas_folha()

    def mover_na_folha(self, passo: int):
        """Sobe ou desce na folha o que estiver marcado."""
        fonte = self.var_folha_o_que.get()
        na_folha = list(self.ordem_da_folha.get(fonte) or [])
        alvos = sorted(i for i in self.lst_folha.curselection()
                       if i < len(na_folha))
        if not alvos:
            return
        if passo > 0:
            alvos = list(reversed(alvos))
        novos = []
        for i in alvos:
            j = i + passo
            if j < 0 or j >= len(na_folha) or j in novos:
                novos.append(i)
                continue
            na_folha[i], na_folha[j] = na_folha[j], na_folha[i]
            novos.append(j)
        self.ordem_da_folha[fonte] = na_folha
        self._desenhar_colunas_folha()
        for j in novos:
            self.lst_folha.selection_set(j)

    def folha_executiva(self):
        """Devolve a folha ao conjunto executivo, na ordem de fabrica."""
        _, executivas = self._colunas_da_fonte()
        self.ordem_da_folha[self.var_folha_o_que.get()] = list(executivas)
        self._desenhar_colunas_folha()

    def _guardar_ordem_da_folha(self):
        self.par.setdefault("folha_colunas", {}).update(
            {k: list(v) for k, v in self.ordem_da_folha.items()})
        # AS COLUNAS QUE EXISTIAM QUANDO ELE GRAVOU. E o que permite, na
        # proxima versao do programa, saber se uma coluna esta fora da
        # folha porque ele a tirou ou porque ela ainda nao existia.
        vistas = self.par.setdefault("folha_colunas_vistas", {})
        for fonte, (colunas, _exec) in (
                ("ACOMPANHAMENTO", (self.COLUNAS_AC, self.EXEC_ACOMP)),
                ("PAINEL DE META", (self.COLUNAS, self.EXEC_PAINEL))):
            if fonte in self.ordem_da_folha:
                vistas[fonte] = [c for c, _, _, _, _ in colunas]
        self._gravar_par()

    def _todos_folha(self, ligado: bool):
        for v in self.var_folha_rec.values():
            v.set(ligado)
        self._contar_folha()

    def _contar_folha(self):
        recs = [r for r, v in self.var_folha_rec.items() if v.get()]
        cols = [c for c, v in self.var_folha_col.items() if v.get()]
        recado = f"{len(recs)} pagina(s), {len(cols)} coluna(s)."
        cor = COR_SUAVE
        nivel, chave = self._alvo_da_folha()
        if nivel:
            recado += (f"   SO DE {mn.TITULO_DO_RECORTE[nivel]} "
                       f"{self.var_folha_alvo.get()}: a linha que for "
                       f"INTEIRA dele vai com a meta do painel; a que tiver "
                       f"cliente de outra equipe - a cidade partida, o "
                       f"gerente todo - e refeita so com a parte dele.")
        if len(cols) > 14:
            recado += "  Com mais de 14 colunas a letra fica pequena."
            cor = COR_ALERTA
        grandes = [mn.TITULO_DO_RECORTE[r] for r in recs if r in self.GRANDES]
        if grandes:
            recado += (f"  {', '.join(grandes)} tem linha demais para uma "
                       f"pagina - vai sair em varias.")
            cor = COR_ALERTA
        self.lbl_folha.configure(text=recado, foreground=cor)

    def _blocos_da_folha(self):
        """O que vai para a folha: um bloco por recorte marcado."""
        painel = self.var_folha_o_que.get() == "PAINEL DE META"
        fonte = self._fonte_da_folha()
        if not fonte:
            messagebox.showinfo(
                "Gerador de Meta BAP",
                "Gere a meta primeiro (aba 1)." if painel else
                "Apure o acompanhamento primeiro (aba 3).")
            return None, ""
        # A ORDEM E A DA LISTA DA DIREITA, de cima para baixo
        rotulos = self._rotulos_da_fonte()
        escolhidas = [(rotulos.get(chave, chave), chave,
                       self._tipo_da_coluna(chave))
                      for chave in (self.ordem_da_folha.get(
                          self.var_folha_o_que.get()) or [])
                      if chave in rotulos]
        if not escolhidas:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Marque pelo menos uma coluna.")
            return None, ""
        nivel, chave = self._alvo_da_folha()
        if nivel:
            fonte = mn.filtrar_para_a_folha(fonte, nivel, chave,
                                            acompanhamento=not painel)
            if not fonte.get("clientes"):
                messagebox.showinfo(
                    "Gerador de Meta BAP",
                    f"{self.var_folha_alvo.get()} nao tem cliente nenhum "
                    f"neste mes.")
                return None, ""
        blocos = []
        for recorte in self.RECORTES_DA_FOLHA:
            if not self.var_folha_rec[recorte].get():
                continue
            linhas = self._filtrar_pessoas(fonte["recortes"][recorte],
                                           recorte)
            if not painel:
                # o executivo le por ATINGIMENTO, nao por tamanho: quem
                # esta em cima e quem esta embaixo e a primeira pergunta
                linhas = sorted(linhas,
                                key=lambda l: -(l.get("atingimento") or 0))
            linhas = [mn._arredondar_metas(l) for l in linhas]
            for l in linhas:
                l["nome"] = l.get("nome") or l.get("rotulo") or ""
            # o TOTAL da folha e o do que foi impresso
            bruto = (fonte.get("totais") or {}).get(recorte) or {}
            if len(linhas) != len(fonte["recortes"][recorte]):
                bruto = (mn._total_acompanhamento(linhas) if not painel
                         else mn.total_do_recorte(linhas))
            total = mn._arredondar_metas(bruto)
            total["nome"] = f"TOTAL DE {mn.TITULO_DO_RECORTE[recorte]}"
            total["codigo"] = "TOTAL"
            # COLUNA DE TEXTO VAZIA NA PAGINA INTEIRA NAO E IMPRESSA.
            # SUPERVISOR so tem conteudo na pagina do vendedor; deixa-la
            # em branco nas outras so rouba largura de quem tem numero.
            # Coluna de numero continua sempre saindo: zero e informacao,
            # vazio nao e.
            colunas = [(rotulo, chave, tipo) for rotulo, chave, tipo
                       in escolhidas
                       if tipo != "texto"
                       or any(_texto_da_celula(l.get(chave)) for l in linhas)]
            blocos.append({"titulo": mn.TITULO_DO_RECORTE[recorte],
                           "colunas": colunas, "linhas": linhas,
                           "total": total})
        if not blocos:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Marque pelo menos um recorte.")
            return None, ""
        comp = (fonte.get("competencia") or "")
        return blocos, comp

    def _nome_da_folha(self, comp: str, painel: bool) -> str:
        """O nome do arquivo leva o filtro, para uma folha nao tapar a
        outra: FOLHA_ACOMPANHAMENTO_BAP_202609_VENDEDOR_000015."""
        nome = mn.nome_da_folha(comp, "META" if painel else "ACOMPANHAMENTO")
        nivel, chave = self._alvo_da_folha()
        if nivel:
            limpo = "".join(c if c.isalnum() else "_"
                            for c in f"{nivel}_{chave}").upper()
            nome += "_" + limpo.strip("_")[:40]
        return nome

    def imprimir_folha(self):
        blocos, comp = self._blocos_da_folha()
        if not blocos:
            return
        painel = self.var_folha_o_que.get() == "PAINEL DE META"
        nivel, _ = self._alvo_da_folha()
        titulo = ("META " if painel else "ACOMPANHAMENTO ") + \
                 (mn.rotulo_do_mes(comp) if comp else "")
        if nivel:
            titulo += f"  |  {self.var_folha_alvo.get()}"
        sub = (f"BAP  |  {mn.rotulo_do_mes(comp) if comp else ''}  |  "
               f"gerado em {dt.date.today().strftime('%d/%m/%Y')}"
               + (f"  |  {self.planner.name}" if self.planner else ""))
        # SEM PE DE PAGINA: a folha e para ler o numero, nao para ler
        # definicao. O que cada coluna quer dizer esta no LEIAME e na aba
        # COMO_LER do Excel; repetir isso embaixo de cada tabela so
        # roubava espaco e atrapalhava a leitura.
        rodape = ""
        destino = (AQUI / pb.RELATORIOS /
                   (self._nome_da_folha(comp, painel) + ".html"))
        try:
            mn.gravar_html_para_imprimir(blocos, destino, titulo, sub, rodape)
        except OSError as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            return
        self._guardar_ordem_da_folha()
        bp.App._abrir(destino)
        self.aviso(f"Folha aberta no navegador: {destino.name}  "
                   f"(Ctrl+P, destino 'Salvar como PDF', layout Paisagem)",
                   COR_OK)

    def exportar_folha(self):
        blocos, comp = self._blocos_da_folha()
        if not blocos:
            return
        painel = self.var_folha_o_que.get() == "PAINEL DE META"
        destino = (AQUI / pb.RELATORIOS /
                   (self._nome_da_folha(comp, painel) + ".xlsx"))
        try:
            mn.gravar_excel_escolhido(blocos, destino)
        except OSError as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            return
        self._guardar_ordem_da_folha()
        messagebox.showinfo("Gerador de Meta BAP",
                            f"Gravado em {pb.RELATORIOS}:\n\n{destino.name}")
        self.aviso(f"Gravado: {destino.name}", COR_OK)

    def _encher_meses(self):
        """
        A caixinha do mes oferece o que JA ESTA gravado no
        ACOMPANHAMENTO_META_BAP.xlsx, mais os meses por perto.
        """
        try:
            gravados = mn.meses_no_arquivo(AQUI)
        except OSError:
            gravados = []
        bonitos = [f"{m[:4]}-{m[4:]}" for m in gravados]
        for m in mn.meses_por_perto():
            if m not in bonitos:
                bonitos.append(m)
        self.cb_comp.configure(values=bonitos)
        if gravados:
            self.aviso(f"O {mn.ARQUIVO_ACOMPANHAMENTO} tem "
                       f"{len(gravados)} mes(es): "
                       f"{', '.join(bonitos[:len(gravados)])}.", COR_SUAVE)
        return bonitos

    # ---- a classificacao dos produtos -----------------------------------
    def _encher_fornecedores(self):
        self.lst_forn.delete(0, "end")
        self._fornecedores = sorted(self.mapa_categoria or {})
        for nome in self._fornecedores:
            self.lst_forn.insert(
                "end", f"{nome}   ->   {self.mapa_categoria[nome].upper()}")
        if not self._fornecedores:
            self.lst_forn.insert("end", "(a lista aparece depois de apurar)")

    def _ler_fornecedor(self):
        marcada = self.lst_forn.curselection()
        if marcada and getattr(self, "_fornecedores", None):
            nome = self._fornecedores[marcada[0]]
            self.var_forn_cat.set(self.mapa_categoria.get(
                nome, mn.CATEGORIA_PADRAO))

    def aplicar_fornecedor(self):
        marcada = self.lst_forn.curselection()
        if not marcada or not getattr(self, "_fornecedores", None):
            messagebox.showinfo("Gerador de Meta BAP",
                                "Escolha um fornecedor na lista.")
            return
        nome = self._fornecedores[marcada[0]]
        self.mapa_categoria[nome] = self.var_forn_cat.get()
        self.par.setdefault("categoria_por_fornecedor", {})[nome] = \
            self.var_forn_cat.get()
        self._gravar_par()
        self._encher_fornecedores()
        self.aviso(f"{nome} passou a contar como "
                   f"{self.var_forn_cat.get().upper()}. Clique em APURAR "
                   f"AGORA para refazer.", COR_OK)

    # ---- apurar ----------------------------------------------------------
    def apurar(self):
        if not self.resultado:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Gere a meta primeiro (aba 1).")
            self._selecionar("par")
            return
        tabela = AQUI / pb.RELATORIOS / "TABELA_BAP.xlsx"
        if not tabela.exists():
            messagebox.showwarning(
                "Gerador de Meta BAP",
                f"Nao achei a TABELA_BAP em {pb.RELATORIOS}.\n\nE dela que "
                f"sai o faturamento do mes (aba ftPedidos). Rode a Automacao "
                f"BAP para traze-la.")
            return
        competencia = (mn.normalizar_competencia(self.var_comp.get())
                       or self.resultado.get("competencia", ""))
        self.var_comp.set(competencia)
        self.aviso("Lendo a TABELA_BAP...", COR_SUAVE)
        self.update_idletasks()
        try:
            self.csv_categorias = mn.achar_csv_de_categorias(AQUI)
            self.categorias_produto = mn.ler_categorias_de_produto(
                self.csv_categorias) if self.csv_categorias else {}
            self.mapa_categoria = mn.mapa_de_categorias(
                tabela, self.par.get("categoria_por_fornecedor"))
            self.realizado = mn.ler_realizado(
                tabela, competencia, self.mapa_categoria,
                self.categorias_produto,
                segmento_do_cliente=mn.segmentos_da_base(
                    AQUI / pb.RELATORIOS / "BASE_CLIENTE.xlsx"))
        except (OSError, ValueError) as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        # AS VISITAS FEITAS vem de RELATORIOS\\Visitas\\AAAAMM.csv - um
        # arquivo por mes, com o nome sendo o proprio mes. E o unico lugar
        # que sabe quem o vendedor visitou (a TABELA_BAP tem nota, nao
        # check-in). O arquivo lido e SEMPRE o da competencia apurada:
        # trocar o mes na tela troca o arquivo. Sem ele, a meta de visita
        # fica sem realizado - e o programa diz isso, em vez de zero.
        self.arq_visitas = mn.achar_visitas_do_mes(AQUI, competencia)
        self.comp_visitas = competencia
        self.visitas_feitas = (mn.ler_visitas_realizadas(self.arq_visitas)
                               if self.arq_visitas else {})
        # A DATA DE CADASTRO vem da BASE_CLIENTE (o PLANNER nao a
        # carrega): e ela que diz quem e cliente NOVO no mes.
        self.datas_cadastro = mn.datas_de_cadastro(
            AQUI / pb.RELATORIOS / "BASE_CLIENTE.xlsx")
        # (15/10, Alexandre) CADASTRO NOVO CONTA COMO VISITA (e na RV de
        # visita): os clientes cadastrados no mes por vendedor (dClientesBap)
        self.cad_visita = mn.cadastros_por_vendedor(tabela, competencia)
        # OS DIAS QUE FALTAM (o denominador do NEC./DIA) tiram os
        # feriados que estao no Planner - feriado nao e dia de venda.
        self.acomp = mn.acompanhar(self.resultado, self.realizado,
                                   self.visitas_feitas,
                                   self.datas_cadastro,
                                   feriados=self._feriados(),
                                   par=self.par,
                                   cad_visita=self.cad_visita)
        if self.categorias_produto:
            self.lbl_csv.configure(
                text=f"CATEGORIAS_PRODUTO.csv encontrado "
                     f"({self.csv_categorias.name}): "
                     f"{len(self.categorias_produto)} produtos classificados "
                     f"em PECAS, BATERIA, LUBRIFICANTE e PNEU. E dele que sai "
                     f"o realizado por categoria."
                     + (f"  {self.realizado['sem_categoria']} item(ns) de nota "
                        f"nao estavam no arquivo e entraram como PECAS."
                        if self.realizado["sem_categoria"] else ""),
                foreground=COR_OK)
        else:
            self.lbl_csv.configure(
                text="CATEGORIAS_PRODUTO.csv NAO esta na pasta. Sem ele nao "
                     "da para separar bateria e pneu: exporte o 'Estoque "
                     "Total' do sistema (colunas Forn., Cod. Prod., Produto e "
                     "Categoria) e salve como CATEGORIAS_PRODUTO.csv aqui na "
                     "pasta.", foreground=COR_ALERTA)
        self._encher_fornecedores()
        self._desenhar_acompanhamento()
        self._nivel_da_folha()
        self._selecionar("acomp")
        self.aviso(f"Acompanhamento de {competencia} apurado.", COR_OK)

    def _desenhar_acompanhamento(self):
        ac = self._acomp_tela()
        if not ac:
            return
        self._silencio = True
        try:
            for recorte in mn.RECORTES:
                t = self.visoes_ac[recorte]
                t.delete(*t.get_children())
                visiveis = self._filtrar_pessoas(ac["recortes"][recorte],
                                                 recorte)
                for linha in visiveis:
                    if linha.get("fora_do_planner"):
                        tags = ("fora",)
                    elif linha["meta"] and linha["atingimento"] >= 100:
                        tags = ("bateu",)
                    elif linha["meta"] and linha["atingimento"] < 70:
                        tags = ("longe",)
                    else:
                        tags = ()
                    t.insert("", "end", iid=linha["chave"], tags=tags,
                             values=self._valores_ac(
                                 mn._arredondar_metas(linha),
                                 recorte=recorte))
                total = (mn._total_acompanhamento(visiveis)
                         if len(visiveis) != len(ac["recortes"][recorte])
                         else ac["totais"][recorte])
                bp.escrever_total(
                    t, self._valores_ac(mn._arredondar_metas(total),
                                        total=True, recorte=recorte))
        finally:
            self._silencio = False
        # O RESUMO EM TEXTO SAIU: meta, realizado, atingimento e GAP estao
        # na linha TOTAL da tabela, em coluna, que e onde se le melhor.
        # Aqui fica so o que a tabela NAO mostra - e so quando ha o que
        # dizer. Sem aviso, a linha some e a tela sobe.
        self._desenhar_familia_ac()
        avisos = [x for x in (self._recado_das_visitas().strip(),
                              self._recado_do_fora_do_planner()) if x]
        if avisos:
            self.lbl_acomp.configure(text="   ".join(avisos))
            self.lbl_acomp.pack(anchor="w", pady=(6, 8))
        else:
            self.lbl_acomp.pack_forget()

    # ======================================================== os filtros
    # DOIS INTERRUPTORES, os mesmos em todas as abas: eles nao escondem
    # "algumas linhas de algumas telas", eles dizem QUEM entra na conta.
    # A linha TOTAL e sempre a soma do que esta na tela, entao ela
    # acompanha - e e justamente ai que eles servem: com a cadeira vaga
    # de fora, o TOTAL do recorte VENDEDOR para de somar meta de quem nao
    # vai vender.
    #
    # Valem para as linhas de PESSOA (vendedor). Gerente, supervisor,
    # zona, cidade, bairro e cliente nao sao vendedor - ali nao ha o que
    # filtrar, e as linhas ficam como estao.
    # ---- a vista por FAMILIA DA PECA -----------------------------------
    # Fica ao lado de GERENTE / SUPERVISOR / VENDEDOR porque e a mesma
    # pergunta vista por outro angulo: nao "quem vendeu", mas "o que foi
    # vendido". Nao tem meta - as quatro categorias (PECAS, BATERIA,
    # LUBRIFICANTE, PNEU) continuam sendo as que tem meta e atingimento.
    # A soma da coluna REALIZADO bate com o FAT TOTAL da pessoa
    # escolhida, porque sai da MESMA leitura da ftPedidos.
    COLUNAS_FAM_AC = [
        ("familia", "FAMILIA", 170, "w", False),
        ("faturado", "FATURADO R$", 140, "e", False),
        ("devolvido", "DEVOLVIDO R$", 140, "e", False),
        ("realizado", "REALIZADO R$", 140, "e", False),
        ("perc", "% DO TOTAL", 110, "center", False),
        ("qtd_clientes", "CLIENTES", 96, "center", False),
        ("qtd_notas", "NOTAS", 84, "center", False),
        ("qtd_skus", "SKUS", 84, "center", False),
        ("ticket", "TICKET MEDIO R$", 150, "e", False),
    ]
    COLUNAS_GRU_AC = [
        ("grupo", "GRUPO", 300, "w", True),
        ("realizado", "REALIZADO R$", 140, "e", False),
        ("qtd_skus", "SKUS", 84, "center", False),
        ("qtd_clientes", "CLIENTES", 96, "center", False),
    ]
    ROTULO_NIVEL_FAM = {"bap": "BAP INTEIRA", "gerente": "GERENTE",
                        "supervisor": "SUPERVISOR", "vendedor": "VENDEDOR"}

    def _montar_familia_ac(self):
        quadro_aba = ttk.Frame(self.recortes_ac, padding=10)
        self.recortes_ac.add(quadro_aba, text="FAMILIA DA PECA")

        barra = ttk.Frame(quadro_aba)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Ver por:").pack(side="left")
        self.var_nivel_fam = tk.StringVar(
            value=self.ROTULO_NIVEL_FAM[mn.NIVEL_BAP])
        cb = ttk.Combobox(barra, textvariable=self.var_nivel_fam, width=14,
                          state="readonly",
                          values=[self.ROTULO_NIVEL_FAM[n]
                                  for n in mn.NIVEIS_DA_FAMILIA])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _: self._nivel_fam_mudou())
        self.lbl_quem_fam = ttk.Label(barra, text="   Quem:")
        self.var_quem_fam = tk.StringVar(value="")
        self.cb_quem_fam = ttk.Combobox(barra, textvariable=self.var_quem_fam,
                                        width=34, state="readonly", values=[])
        self.cb_quem_fam.bind("<<ComboboxSelected>>",
                              lambda _: self._desenhar_familia_ac())
        ttk.Label(barra, text="   Clique numa familia para ver os grupos "
                              "dela.", style="Sub.TLabel").pack(side="right")

        quadro, self.tab_fam_ac = bp.tabela(quadro_aba, self.COLUNAS_FAM_AC,
                                            altura=13, rodape=True,
                                            horizontal=False)
        quadro.pack(fill="x")
        self.tab_fam_ac.bind("<<TreeviewSelect>>",
                             lambda _: self._desenhar_grupos_ac())
        self.lbl_fam_ac = ttk.Label(quadro_aba, text="", style="Sub.TLabel",
                                    wraplength=1350)
        self.lbl_fam_ac.pack(anchor="w", pady=(6, 0))

        ttk.Label(quadro_aba, text="Grupos da familia escolhida",
                  style="Sub.TLabel").pack(anchor="w", pady=(10, 2))
        quadro2, self.tab_gru_ac = bp.tabela(quadro_aba, self.COLUNAS_GRU_AC,
                                             altura=7, horizontal=False)
        quadro2.pack(fill="x")

    def _nivel_da_familia(self) -> str:
        escolhido = self.var_nivel_fam.get()
        for chave, rotulo in self.ROTULO_NIVEL_FAM.items():
            if rotulo == escolhido:
                return chave
        return mn.NIVEL_BAP

    def _rotulo_da_pessoa(self, nivel: str, chave: str) -> str:
        """O codigo com o nome, quando o painel souber o nome."""
        for linha in (self._acomp_tela() or {}).get("recortes", {}).get(nivel, ()):
            if linha.get("chave") == chave:
                return linha.get("rotulo") or chave
        return chave

    def _nivel_fam_mudou(self):
        """Trocou o nivel: a lista de pessoas muda junto."""
        nivel = self._nivel_da_familia()
        if nivel == mn.NIVEL_BAP or not self.acomp:
            self.lbl_quem_fam.pack_forget()
            self.cb_quem_fam.pack_forget()
        else:
            pessoas = mn.pessoas_da_familia(self._realizado_tela() or {},
                                            self._resultado_tela() or {}, nivel)
            # no VENDEDOR a chave e o codigo; na tela vai o codigo com o
            # nome, que e como o resto do app mostra
            self._quem_fam = {self._rotulo_da_pessoa(nivel, x): x
                              for x in pessoas}
            mostrar = list(self._quem_fam)
            self.cb_quem_fam.configure(values=mostrar)
            if self.var_quem_fam.get() not in mostrar:
                self.var_quem_fam.set(mostrar[0] if mostrar else "")
            self.lbl_quem_fam.pack(side="left")
            self.cb_quem_fam.pack(side="left", padx=6)
        self._desenhar_familia_ac()

    def _linhas_da_familia(self) -> list:
        if not (self.acomp and self.realizado):
            return []
        nivel = self._nivel_da_familia()
        chave = "" if nivel == mn.NIVEL_BAP else getattr(
            self, "_quem_fam", {}).get(self.var_quem_fam.get(),
                                       self.var_quem_fam.get())
        return mn.visao_por_familia(self._realizado_tela(),
                                    self._resultado_tela() or {}, nivel, chave)

    def _valores_fam_ac(self, linha, colunas=None, total=False):
        saida = []
        for chave, _, _, _, _ in (colunas or self.COLUNAS_FAM_AC):
            v = linha.get(chave)
            if chave in ("faturado", "devolvido", "realizado", "ticket"):
                saida.append(dinheiro(v) if v or total else "")
            elif chave == "perc":
                saida.append(numero_br(v, 1) + "%" if v else "")
            elif v is None:
                saida.append("")
            elif chave in ("qtd_clientes", "qtd_notas", "qtd_skus"):
                # contagem nao tem casa decimal: "31", nunca "31,0"
                saida.append(f"{int(round(v)):,}".replace(",", "."))
            elif isinstance(v, (int, float)):
                saida.append(numero_br(v))
            else:
                saida.append(v)
        return saida

    def _desenhar_familia_ac(self):
        if not hasattr(self, "tab_fam_ac"):
            return
        linhas = self._linhas_da_familia()
        t = self.tab_fam_ac
        t.delete(*t.get_children())
        for i, l in enumerate(linhas):
            t.insert("", "end", iid=l["familia"],
                     tags=("zebra",) if i % 2 else (),
                     values=self._valores_fam_ac(l))
        if linhas:
            bp.escrever_total(t, self._valores_fam_ac(
                mn.total_da_familia(linhas), total=True))
            t.selection_set(linhas[0]["familia"])
        self._desenhar_grupos_ac()
        nivel = self._nivel_da_familia()
        quem = ("a BAP inteira" if nivel == mn.NIVEL_BAP
                else self.var_quem_fam.get() or "(ninguem)")
        total = mn.total_da_familia(linhas)["realizado"] if linhas else 0.0
        sem = (self.realizado or {}).get("sem_descricao", 0)
        self.lbl_fam_ac.configure(
            text=f"{len(linhas)} familia(s) em {quem}   |   realizado "
                 f"{dinheiro(total)} - o mesmo FAT TOTAL do acompanhamento, "
                 f"so que aberto pela peca   |   a familia sai da DESCRICAO "
                 f"do produto, e nao tem meta: quem tem meta sao as quatro "
                 f"categorias (PECAS, BATERIA, LUBRIFICANTE, PNEU)"
                 + (f"   |   ATENCAO: {sem} item(ns) de nota sem descricao "
                    f"de produto cairam em OUTROS" if sem else ""))

    def _desenhar_grupos_ac(self):
        if not hasattr(self, "tab_gru_ac"):
            return
        t = self.tab_gru_ac
        t.delete(*t.get_children())
        escolhida = (self.tab_fam_ac.selection() or (None,))[0]
        if not escolhida or escolhida == bp.LINHA_TOTAL:
            return
        for i, g in enumerate(mn.grupos_da_familia(self._linhas_da_familia(),
                                                   escolhida)):
            t.insert("", "end", iid=g["grupo"],
                     tags=("zebra",) if i % 2 else (),
                     values=self._valores_fam_ac(g, self.COLUNAS_GRU_AC))

    def _barra_de_filtro(self, pai):
        """Os dois checkbox, ligados nas MESMAS variaveis em toda aba."""
        quadro = ttk.Frame(pai)
        quadro.pack(side="left", padx=(18, 0))
        # (05/10) "apenas ativos" e "apenas quem conta" sairam: o Planner
        # do mes ja diz quem esta na equipe
        ttk.Label(quadro, text="Segmento:").pack(side="left", padx=(0, 4))
        cb = ttk.Combobox(quadro, textvariable=self.var_segmento,
                          state="readonly", width=26,
                          values=[mn.TODOS_OS_SEGMENTOS] + list(SEGMENTOS))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _: self._filtro_mudou())
        return quadro

    # ---- o que a TELA mostra: tudo, ou so um segmento --------------------
    def _segmento_da_tela(self) -> str:
        seg = self.var_segmento.get() if hasattr(self, "var_segmento") else ""
        return "" if seg in ("", mn.TODOS_OS_SEGMENTOS) else seg

    def _resultado_tela(self):
        seg = self._segmento_da_tela()
        if not seg or not self.resultado:
            return self.resultado
        chave = ("res", id(self.resultado), seg)
        if chave not in self._cache_tela:
            self._cache_tela[chave] = mn.resultado_do_segmento(self.resultado, seg)
        return self._cache_tela[chave]

    def _realizado_tela(self):
        seg = self._segmento_da_tela()
        if not seg or not self.realizado:
            return self.realizado
        chave = ("real", id(self.realizado), seg)
        if chave not in self._cache_tela:
            self._cache_tela[chave] = mn.realizado_do_segmento(self.realizado, seg)
        return self._cache_tela[chave]

    def _acomp_tela(self):
        seg = self._segmento_da_tela()
        if not seg or not self.acomp:
            return self.acomp
        chave = ("ac", id(self.acomp), seg)
        if chave not in self._cache_tela:
            self._cache_tela[chave] = mn.acompanhar(
                self._resultado_tela(), self._realizado_tela(),
                self.visitas_feitas, self.datas_cadastro,
                feriados=self._feriados(), par=self.par,
                cad_visita=getattr(self, "cad_visita", None))
        return self._cache_tela[chave]

    def _filtro_mudou(self):
        """Redesenha tudo o que depende dos filtros, nas seis abas."""
        if self.resultado:
            self._desenhar()
        if self.acomp:
            self._desenhar_acompanhamento()
        self._nivel_da_folha()

    def _filtrar_pessoas(self, linhas, recorte):
        """
        Tira da lista os vendedores que os filtros mandam esconder.

        So mexe no recorte VENDEDOR: e o unico em que a linha E uma
        pessoa. Nos outros devolve a lista inteira - esconder metade de
        um supervisor nao faria sentido nenhum.
        """
        if recorte != "vendedor":
            return list(linhas)
        fora = []
        for l in linhas:
            # QUEM VENDEU E NAO ESTA NO PLANNER NUNCA SOME. E dinheiro
            # faturado sem meta; escondendo a linha, o TOTAL da tela
            # deixaria de bater com a ftPedidos e ninguem entenderia por
            # que. Ele nao e um vendedor inativo - e um codigo que o
            # cadastro nao conhece, e isso precisa aparecer.
            if l.get("fora_do_planner"):
                fora.append(l)
                continue
            if self.var_so_ativos.get() and not l.get("vendedor_ativo", True):
                continue
            if self.var_so_conta.get() and not l.get("conta_na_meta", True):
                continue
            fora.append(l)
        return fora

    def _recado_do_fora_do_planner(self) -> str:
        """Quem faturou sem estar no PLANNER - o unico numero que a tabela
        nao conta sozinha."""
        ac = self.acomp or {}
        if not ac.get("fora_do_planner"):
            return ""
        texto = (f"{ac['fora_do_planner']} cliente(s) faturaram e nao estao "
                 f"no PLANNER (o bairro deles ainda nao foi posto em nenhuma "
                 f"zona): o faturamento sobe pela equipe do vendedor da nota, "
                 f"com meta zero.")
        if ac.get("sem_dono"):
            texto += (f" Destes, {ac['sem_dono']} nem pela nota deu para "
                      f"saber de quem sao.")
        return texto

    def _feriados(self) -> list:
        """Os feriados do planner_config.json, se ele estiver na pasta."""
        try:
            with open(AQUI / "planner_config.json", encoding="utf-8") as arq:
                return list((json.load(arq) or {}).get("feriados") or [])
        except (OSError, ValueError):
            return []

    def _recado_das_visitas(self) -> str:
        """Diz de onde saiu a visita feita - ou por que ela nao saiu."""
        comp = self.comp_visitas or self.var_comp.get()
        esperado = mn.nome_do_arquivo_de_visita(comp) if comp else "AAAAMM.csv"
        if not self.arq_visitas:
            tem = mn.meses_com_visita(AQUI)
            return (f"   A META DE VISITA ficou sem realizado: nao achei o "
                    f"{esperado} em {pb.VISITAS_TELA}. E dele que sai quantas "
                    f"visitas cada vendedor fez no mes."
                    + (f"   Nessa pasta ha visita de: "
                       f"{', '.join(tem[-8:])}." if tem else ""))
        if not self.visitas_feitas:
            return (f"   O {self.arq_visitas.name} foi encontrado mas nao deu "
                    f"para ler: confira se ele tem a coluna "
                    f"{' ou '.join(mn.COLUNAS_DE_VISITA)} e uma coluna com o "
                    f"nome do vendedor (NOME ou NOMERCA).")
        vendedores = (self.acomp["recortes"]["vendedor"] if self.acomp
                      else [])
        sem_casar = [l["nome"] or l["rotulo"] for l in vendedores
                     if l.get("chave") and not l.get("visita_casou")]
        por_curto = [l["nome"] or l["rotulo"] for l in vendedores
                     if l.get("visita_por_apelido")]
        # o arquivo do jeito antigo nao tem mes: vale avisar que ele serve
        # para um mes so, senao o numero vira do mes errado sem ninguem ver
        antigo = mn._so_letras(self.arq_visitas.stem) != mn.marca_do_mes(comp)
        recado = (f"   Visitas feitas de {mn.rotulo_do_mes(comp)}: "
                  f"{self.arq_visitas.name}, "
                  f"{len(self.visitas_feitas.get('_nomes', {}))} vendedor(es) "
                  f"no arquivo.")
        if antigo:
            recado += (f"   ATENCAO: esse e o arquivo unico do jeito antigo, "
                       f"que nao diz de que mes ele e. Separe por mes em "
                       f"{pb.VISITAS_TELA}\\{esperado} para o acompanhamento "
                       f"fechar mes a mes.")
        if por_curto:
            recado += (f"   {len(por_curto)} casou(aram) pelo PRIMEIRO NOME "
                       f"e ULTIMO SOBRENOME, porque o arquivo escreve o nome "
                       f"inteiro e o cadastro, o curto: "
                       f"{', '.join(por_curto[:4])}"
                       + ("..." if len(por_curto) > 4 else "") + ".")
        if sem_casar:
            recado += (f"   {len(sem_casar)} vendedor(es) do PLANNER nao "
                       f"foram achados nele pelo nome e ficaram com visita "
                       f"zero: {', '.join(sem_casar[:4])}"
                       + ("..." if len(sem_casar) > 4 else "") + ".")
        return recado

    def _valores_ac(self, linha, total=False, recorte=""):
        """
        Cada celula do acompanhamento. O que e VAZIO (None) fica vazio
        mesmo - e o caso da visita de zona, cidade, bairro e cliente:
        eles nao visitam ninguem, entao nao ha meta nem realizado, e um
        zero ali mentiria dizendo que a meta existe e nao foi cumprida.
        """
        contagem = {"meta_visita_int", "visitas_realizadas",
                    "meta_positivacao_int", "positivados", "clientes",
                    "notas", "base_visita", "base_carteira",
                    "meta_cadastro_int", "cadastros_com_compra",
                    "cadastros_no_mes"}
        percentual = {a for _, _, _, a in mn.TRIO_DAS_METAS}
        # NEC./DIA de visita, positivacao e cadastro e "gente por dia":
        # 0,4 por dia nao pode virar 0 - e justamente o que falta
        uma_casa = {nec for rotulo, _, _, _, _, nec
                    in mn.METAS_DO_ACOMPANHAMENTO
                    if rotulo in mn.METAS_DE_CONTAGEM}
        contagem = contagem | {gap for rotulo, _, _, _, gap, _
                               in mn.METAS_DO_ACOMPANHAMENTO
                               if rotulo in mn.METAS_DE_CONTAGEM}
        contagem = contagem | {"dias_restantes"}
        saida = []
        for chave, _, _, _, _ in self.COLUNAS_AC:
            v = linha.get(chave)
            if chave == "codigo":
                saida.append("TOTAL" if total else (v or ""))
            elif chave == "nome":
                saida.append(f"TOTAL DE {mn.TITULO_DO_RECORTE[recorte]}"
                             if total else (v or linha.get("rotulo") or ""))
            elif v is None:
                saida.append("")
            elif chave == "supervisor":
                saida.append("" if total else str(v))
            elif chave in percentual or chave in uma_casa:
                saida.append(numero_br(v, 1))
            elif chave in contagem:
                saida.append(numero_br(inteiro(v), 0))
            else:
                saida.append(dinheiro(v))
        return saida

    def exportar_acompanhamento(self):
        if not self.acomp:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Apure o acompanhamento primeiro.")
            return
        destino = (AQUI / pb.RELATORIOS /
                   mn.nome_do_acompanhamento(self.acomp["competencia"]))
        try:
            mn.gravar_excel_acompanhamento(self.acomp, self.par, destino)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            return
        self.aviso(f"{destino.name} gravado em {destino.parent.name}.", COR_OK)
        messagebox.showinfo(
            "Gerador de Meta BAP",
            f"{destino.name}\n\nO arquivo do RH, de UM mes so "
            f"({self.acomp['competencia']}): a META e o REALIZADO em uma aba "
            f"por recorte, o ANALITICO cliente a cliente e a aba PARAMETROS "
            f"dizendo de onde cada numero saiu.\n\nEle nao substitui o "
            f"{mn.ARQUIVO_ACOMPANHAMENTO}, que fica na pasta com TODOS os "
            f"meses.\n\nGravado em:\n{destino.parent}")

    # ---------------------------------------------------------- abertura
    def _abertura(self):
        try:
            self._encher_parametros()
            self._contar_metas()
            try:
                # o PLANNER do MES DA META (cada mes tem o seu); sem ele,
                # o mais recente
                achado = pb.planner_do_mes(
                    AQUI, mn.normalizar_competencia(
                        self.var_competencia.get())) \
                    or pb.planner_mais_recente(AQUI)
            except OSError:
                achado = None
            if achado is None:
                self.aviso("Nenhum PLANNER_BAP encontrado na pasta. Gere um no "
                           "Planner BAP, ou escolha o arquivo na aba 1.",
                           COR_ALERTA)
                self.lbl_par_msg.configure(
                    text="Sem PLANNER nao ha meta: e dele que saem a carteira, a "
                         "hierarquia, as visitas do mes e o FAT M3M de cada "
                         "cliente.", foreground=COR_ALERTA)
                return
            self.carregar_planner(achado)
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

    def carregar_planner(self, caminho):
        try:
            self.dados = mn.ler_planner(caminho)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return
        self.planner = Path(caminho)
        # a EQUIPE do mes da meta: o Planner daquele mes manda em quem
        # responde a quem (o PLANNER traz a do dia em que foi gerado)
        comp = (mn.normalizar_competencia(self.var_competencia.get())
                or self.dados.get("competencia", ""))
        cfg_mes = pb.config_do_mes(AQUI, comp) if comp else None
        if cfg_mes is not None and cfg_mes.exists():
            mn.aplicar_equipe_do_mes(self.dados, cfg_mes)
        self._equipe_de = comp
        self.lbl_topo.configure(text="")
        if self.dados.get("sem_m3m_anterior"):
            self.aviso("ATENCAO: este PLANNER veio SEM o M3M ANTERIOR (todos "
                       "em 0,00). Sem ele ninguem tem com o que comparar e "
                       "todos caem na faixa de quem esta caindo. Gere a "
                       "BASE_CLIENTE de novo no Planner BAP (botao GERAR A "
                       "BASE) e refaca o PLANNER.", COR_ALERTA)
        else:
            self.aviso("")
        if not mn.normalizar_competencia(self.var_competencia.get()):
            self.var_competencia.set(self.dados.get("competencia", ""))
        self._mes_mudou()
        self._encher_alvos()
        self._carregar_quem_conta()
        if numero(self.var_meta.get()) > 0 or \
                mn.meta_geral_do_mes(self.par, comp) > 0 or \
                mn.metas_do_mes(self.par.get("metas_importadas") or {}, comp):
            # ABRIR NAO GRAVA: a meta aparece na tela, mas o
            # ACOMPANHAMENTO_META_BAP so e regravado quando o Analista
            # clica em GERAR / GRAVAR A META DO MES. Regravar a cada
            # abertura levava mais de 1 minuto (o arquivo e grande).
            self.gerar(gravar=False)
        self._mes_nas_abas()
        if not getattr(self, "_recalculando", False) and \
                self._planner_mudou(comp):
            self.aviso(f"O Planner de {mn.rotulo_do_mes(comp)} mudou: clique "
                       f"em RECALCULAR para trazer a equipe e as zonas.",
                       COR_ALERTA)

    def escolher_planner(self):
        caminho = filedialog.askopenfilename(
            title="Escolher o PLANNER que vai gerar a meta",
            initialdir=str(AQUI / pb.RELATORIOS),
            filetypes=[("Excel", "*.xlsx *.xlsm")])
        if caminho:
            self.carregar_planner(Path(caminho))

    # -------------------------------------------------------- parametros
    def _modo_mudou(self):
        """Mantido pelo nome antigo: hoje so refaz a linha da meta do mes."""
        self._mostrar_meta_do_mes()

    def _mostrar_meta_do_mes(self):
        """
        A linha grande da aba 1: quanto e a meta DESTE mes e de onde ela
        veio. E a pergunta que se faz ao abrir o programa.
        """
        if not hasattr(self, "lbl_meta_mes"):
            return
        comp = mn.normalizar_competencia(self.var_competencia.get())
        if not comp:
            self.lbl_meta_mes.configure(
                text="Escolha o mes da meta (AAAA-MM).",
                foreground=COR_ALERTA)
            return
        do_mes = mn.metas_do_mes(self.par.get("metas_importadas") or {}, comp)
        total = sum(v for linha in do_mes.values()
                    for v in (linha or {}).values())
        if hasattr(self, "quadro_geral"):
            if do_mes and total > 0:
                self.quadro_geral.pack_forget()
            else:
                geral = mn.meta_geral_do_mes(self.par, comp)
                self.var_geral_mes.set(dinheiro(geral) if geral else "")
                if not self.quadro_geral.winfo_ismapped():
                    self.quadro_geral.pack(fill="x", after=self.lbl_meta_mes)
                if geral:
                    self.lbl_meta_mes.configure(
                        text=f"{mn.rotulo_do_mes(comp)}:   "
                             f"{dinheiro(geral)}   (meta geral do mês)",
                        foreground=COR_TITULO)
                    return
        if do_mes and total > 0:
            self.lbl_meta_mes.configure(
                text=f"{mn.rotulo_do_mes(comp)}:   {dinheiro(total)}   "
                     f"em {len(do_mes)} linha(s) do arquivo",
                foreground=COR_TITULO)
        else:
            self.lbl_meta_mes.configure(
                text=f"{mn.rotulo_do_mes(comp)}:   SEM META NO ARQUIVO - "
                     f"digite a meta geral do mês e clique em GERAR.",
                foreground=COR_ALERTA)

    def _mes_mudou(self):
        """
        O mes escolhido aqui manda em tudo: e a aba (AAAA-MM virando
        '202609') do ACOMPANHAMENTO_META_BAP, o mes do ANALITICO e o mes
        que o acompanhamento vai buscar na TABELA_BAP.
        """
        bom = mn.normalizar_competencia(self.var_competencia.get())
        if not bom and self.dados:
            bom = self.dados.get("competencia", "")
        if bom and self.dados is not None and \
                not getattr(self, "_trocando_planner", False):
            # outro mes, outro PLANNER (e outra equipe)
            alvo = (pb.planner_do_mes(AQUI, bom)
                    or pb.planner_mais_recente(AQUI) or self.planner)
            if alvo and (Path(alvo) != self.planner
                         or bom != getattr(self, "_equipe_de", None)):
                self.var_competencia.set(bom)
                self._trocando_planner = True
                try:
                    self.carregar_planner(alvo)
                finally:
                    self._trocando_planner = False
                return
        if bom:
            self.var_competencia.set(bom)
            self.var_comp.set(bom)
            # a aba 5 segue o mes da meta enquanto ninguem a mexeu para
            # outro mes de proposito
            if not self.comp_conta or self.comp_conta != bom:
                atual = mn.normalizar_competencia(self.var_comp_conta.get())
                if not atual or atual == self.comp_conta:
                    self._carregar_quem_conta(bom)
        self.lbl_par_msg.configure(
            text=(f"A meta vai ser gravada na aba {mn.marca_do_mes(bom)} do "
                  f"{mn.ARQUIVO_ACOMPANHAMENTO}." if bom else
                  "Escolha o mes da meta (AAAA-MM). Sem ele vale o mes das "
                  "visitas do PLANNER."), foreground=COR_SUAVE)
        self._mostrar_meta_do_mes()
        self._mes_nas_abas()

    def _encher_parametros(self):
        self.par["modo"] = "crescimento"
        self.var_modo.set(self.MODOS[0])
        self._modo_mudou()
        faixas = self.par.get("faixas") or mn.FAIXAS_PADRAO
        for (base, acr), faixa in zip(self.var_faixa, faixas):
            base.set("M3M anterior" if faixa.get("base") == "anterior"
                     else "M3M atual")
            acr.set(numero_br(faixa.get("acrescimo"), 0))
        for chave, var in self.var_piso.items():
            var.set(dinheiro(self.par.get(chave) or 0))
        tabela_casa = list(self.par.get("meta_mes_de_casa")
                           or mn.PARAMETROS_PADRAO["meta_mes_de_casa"])
        for i, var in enumerate(self.var_casa):
            var.set(dinheiro(tabela_casa[i] if i < len(tabela_casa) else 0))
        self.var_piso_vet.set(dinheiro(self.par.get("piso_vendedor") or 0))
        self.var_teto_rh.set(dinheiro(self.par.get("teto_rh_vendedor") or 0))
        ccs = list(self.par.get("emails_copia_gerente") or [])
        for i, var in enumerate(self.var_cc):
            var.set(ccs[i] if i < len(ccs) else "")
        self.var_piso_so_fat.set(
            "SIM" if self.par.get("piso_so_com_faturamento", True) else "NAO")
        self.var_meta.set(dinheiro(self.par.get("meta_geral") or 0))
        self.var_competencia.set(
            mn.normalizar_competencia(self.par.get("competencia")))
        self.var_visita.set(numero_br(self.par.get("pct_visita"), 1))
        self.var_pos.set(numero_br(self.par.get("pct_positivacao"), 1))
        self.var_cad.set(numero_br(self.par.get("meta_cadastro"), 0))
        for chave, _, padrao in mn.CATEGORIAS:
            self.var_cat[chave].set(
                numero_br((self.par.get("categorias") or {}).get(chave, padrao), 1))
        self._mostrar_soma()
        self._mostrar_piso()
        self._encher_excecoes()
        self._mostrar_meta_do_mes()
        self.par.setdefault("rv", mn.rv_padrao())
        if self.jan_rv is not None and self.jan_rv.winfo_exists():
            self._desenhar_rv()

    def _mostrar_piso(self):
        if self.var_piso_so_fat.get() == "SIM":
            self.lbl_piso.configure(
                text="SIM: o piso segura a meta do cliente PEQUENO, que e "
                     "para o que ele serve. Quem nunca comprou entra pela "
                     "POSITIVACAO, nao pelo faturamento.",
                foreground=COR_SUAVE)
        else:
            self.lbl_piso.configure(
                text="NAO: TODO cliente da rota ganha o piso, tenha ou nao "
                     "historico. Confira o total: numa carteira com muitos "
                     "clientes que nunca compraram, isso cria uma meta "
                     "grande so de piso.", foreground=COR_ALERTA)

    def _mostrar_soma(self):
        soma = sum(numero(v.get()) for v in self.var_cat.values())
        if abs(soma - 100.0) < 0.01:
            self.lbl_soma.configure(
                text="Os quatro somam 100%: a meta de faturamento fica "
                     "repartida exatamente entre as categorias.",
                foreground=COR_SUAVE)
        else:
            self.lbl_soma.configure(
                text=f"Os quatro somam {numero_br(soma, 1)}%, e nao 100%. "
                     f"Isso NAO e erro do programa: cada categoria e uma meta "
                     f"propria, medida sobre a mesma meta de faturamento. So "
                     f"confira se e isso mesmo que voce quer.",
                foreground=COR_ALERTA if soma > 150 else COR_SUAVE)

    def _ler_dos_campos(self):
        self.par["modo"] = "crescimento"     # e a unica mecanica
        faixas = []
        for (base, acr), padrao in zip(self.var_faixa, mn.FAIXAS_PADRAO):
            faixas.append({**padrao,
                           "base": ("anterior" if base.get() == "M3M anterior"
                                    else "atual"),
                           "acrescimo": numero(acr.get(),
                                               padrao["acrescimo"])})
        self.par["faixas"] = faixas
        for chave, var in self.var_piso.items():
            self.par[chave] = numero(var.get())
        self.par["meta_mes_de_casa"] = [numero(v.get()) for v in self.var_casa]
        self.par["piso_vendedor"] = numero(self.var_piso_vet.get())
        self.par["teto_rh_vendedor"] = numero(self.var_teto_rh.get())
        self.par["emails_copia_gerente"] = [
            v.get().strip().lower() for v in self.var_cc
            if "@" in v.get() and "." in v.get().split("@")[-1]][:5]
        self.par["piso_so_com_faturamento"] = self.var_piso_so_fat.get() == "SIM"
        self.par["meta_geral"] = numero(self.var_meta.get())
        self.par["competencia"] = mn.normalizar_competencia(
            self.var_competencia.get())
        self.par["pct_visita"] = numero(self.var_visita.get(), 90.0)
        self.par["pct_positivacao"] = numero(self.var_pos.get(), 50.0)
        self.par["meta_cadastro"] = numero(self.var_cad.get(), 12.0)
        self.par["categorias"] = {c: numero(self.var_cat[c].get(), p)
                                  for c, _, p in mn.CATEGORIAS}
        # A GRADE DA RV ABERTA ENTRA JUNTO: quem mexeu nas faixas e clicou
        # direto em Salvar parametros nao pode perder o que digitou so por
        # nao ter passado pelo GUARDAR ESTA TABELA.
        if getattr(self, "var_rv", None):
            self.par.setdefault("rv", mn.rv_padrao())
            self.par["rv"][self._nivel_da_rv()] = self._faixas_da_tela()
        self._mostrar_soma()
        self._mostrar_piso()

    def salvar_parametros(self):
        self._ler_dos_campos()
        self._gravar_par()
        self.lbl_par_msg.configure(
            text=f"Parametros salvos em {ARQ_PARAMETROS.name}. Clique em "
                 f"GERAR A META para o painel refletir a mudanca.",
            foreground=COR_OK)

    def voltar_ao_padrao(self):
        if not messagebox.askyesno(
                "Gerador de Meta BAP",
                "Voltar TODOS os parametros ao padrao?\n\nOs percentuais por "
                "UF e por zona e as metas escritas a mao tambem se perdem."):
            return
        self.par = mn.parametros_novos()
        self._encher_parametros()
        self.lbl_par_msg.configure(text="Parametros de fabrica.",
                                   foreground=COR_SUAVE)

    # ------------------------------------------------- excecao UF / zona
    def _encher_alvos(self):
        nivel = self.var_nivel.get()
        if not self.dados:
            self.cb_alvo.configure(values=[])
            return
        if nivel == "UF":
            valores = sorted({c["uf"] for c in self.dados["clientes"] if c["uf"]})
        else:
            vistos = {}
            for c in self.dados["clientes"]:
                if c["cod_zona"]:
                    vistos.setdefault(c["cod_zona"],
                                      f"{c['cod_zona']} - {c['zona']}")
            valores = [vistos[k] for k in sorted(vistos)]
        self.cb_alvo.configure(values=valores)
        if valores and self.var_alvo.get() not in valores:
            self.var_alvo.set(valores[0])
        self._ler_excecao()

    def _alvo_atual(self) -> str:
        alvo = self.var_alvo.get().strip()
        return alvo.split(" - ")[0] if self.var_nivel.get() == "ZONA" else alvo

    def _mapa_da_excecao(self) -> dict:
        return self.par.setdefault(
            "por_uf" if self.var_nivel.get() == "UF" else "por_zona", {})

    def _ler_excecao(self):
        atual = self._mapa_da_excecao().get(self._alvo_atual()) or {}
        for chave, _, padrao in mn.CATEGORIAS:
            self.var_cat_exc[chave].set(numero_br(
                atual.get(chave, (self.par.get("categorias") or {}).get(chave,
                                                                       padrao)),
                1))

    def aplicar_excecao(self):
        alvo = self._alvo_atual()
        if not alvo:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Escolha a UF ou a zona primeiro.")
            return
        self._mapa_da_excecao()[alvo] = {
            c: numero(self.var_cat_exc[c].get(), p) for c, _, p in mn.CATEGORIAS}
        self._encher_excecoes()
        self.lbl_par_msg.configure(
            text=f"{self.var_nivel.get()} {alvo}: percentuais proprios "
                 f"aplicados. Clique em GERAR A META.", foreground=COR_OK)

    def tirar_excecao(self):
        alvo = self._alvo_atual()
        self._mapa_da_excecao().pop(alvo, None)
        self._encher_excecoes()
        self._ler_excecao()
        self.lbl_par_msg.configure(
            text=f"{self.var_nivel.get()} {alvo}: voltou a usar os "
                 f"percentuais gerais.", foreground=COR_SUAVE)

    def _encher_excecoes(self):
        self.lst_excecoes.delete(0, "end")
        for nivel, mapa in (("UF", self.par.get("por_uf") or {}),
                            ("ZONA", self.par.get("por_zona") or {})):
            for alvo, pcts in sorted(mapa.items()):
                texto = "  ".join(f"{r}={numero_br(pcts.get(c, 0), 0)}%"
                                  for c, r, _ in mn.CATEGORIAS)
                self.lst_excecoes.insert("end", f"{nivel} {alvo}:  {texto}")
        if not self.lst_excecoes.size():
            self.lst_excecoes.insert("end", "(nenhum - todos usam o geral)")

    # ------------------------------------------------------------ gerar
    def gerar(self, gravar=True):
        if not self.dados:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Nao ha PLANNER carregado.")
            return
        self._ler_dos_campos()
        sem_meta_geral = self.par["meta_geral"] <= 0
        self.resultado = mn.calcular(self.dados, self.par)
        self._gravar_par()
        self.var_competencia.set(self.resultado["competencia"])
        self.var_comp.set(self.resultado["competencia"])
        self._fechar_edicao()
        self._desenhar()
        self._nivel_da_folha()
        self._selecionar("painel")
        r = self.resultado
        if r.get("meta_importada"):
            # com meta importada, a META GERAL digitada nao manda mais -
            # quem manda e o arquivo, cidade por cidade
            recado = (f"Meta gerada pela META IMPORTADA: "
                      f"{len(r['cidades_importadas'])} de "
                      f"{r['cidades_no_arquivo']} cidade(s) do arquivo "
                      f"existem no PLANNER, "
                      f"{r['clientes_importados']} cliente(s) receberam a "
                      f"fatia deles. Total importado "
                      f"{dinheiro(r['meta_importada_total'])}.")
            sobrando = r["cidades_no_arquivo"] - len(r["cidades_importadas"])
            if sobrando > 0:
                recado += (f"   {sobrando} cidade(s) do arquivo nao tem "
                           f"cliente no PLANNER e ficaram sem efeito.")
            if r["cidades_sem_m3m"]:
                recado += (f"   {len(r['cidades_sem_m3m'])} cidade(s) nao tem "
                           f"M3M nenhum e nao deu para repartir a meta delas "
                           f"({', '.join(r['cidades_sem_m3m'][:4])}) - "
                           f"esses clientes ficaram pelo crescimento.")
            self.aviso(recado, COR_ALERTA if (sobrando or r["cidades_sem_m3m"])
                       else COR_OK)
        elif r.get("modo") == "geral":
            self.aviso(f"Meta de {mn.rotulo_do_mes(r['competencia'])} gerada "
                       f"pela meta geral do mês.", COR_OK)
        elif sem_meta_geral:
            self.aviso("Meta gerada. A META GERAL DO MES esta em branco: a UF "
                       "e o GERENTE ficaram com a soma que saiu dos clientes. "
                       "Preencha na aba 1 para eles ratearem o valor que voce "
                       "quer.", COR_ALERTA)
        else:
            self.aviso("Meta gerada.", COR_OK)
        if gravar:
            self.guardar()

    def _desenhar(self):
        r = self._resultado_tela()
        if not r:
            return
        self._silencio = True
        try:
            for recorte in mn.RECORTES:
                t = self.visoes[recorte]
                t.delete(*t.get_children())
                visiveis = self._filtrar_pessoas(r["recortes"][recorte],
                                                 recorte)
                for i, linha in enumerate(visiveis):
                    if linha.get("ajustada"):
                        tags = ("ajustada",)
                    elif linha.get("no_piso"):
                        tags = ("piso",)
                    else:
                        tags = ("zebra",) if i % 2 else ()
                    t.insert("", "end", iid=linha["chave"], tags=tags,
                             values=self._valores(linha))
                # o TOTAL e o que ESTA na tela: com filtro, ele encolhe
                total = (mn.total_do_recorte(visiveis)
                         if len(visiveis) != len(r["recortes"][recorte])
                         else r["totais"][recorte])
                bp.escrever_total(
                    t, self._valores(total, total=True, recorte=recorte))
        finally:
            self._silencio = False
        for tf, fams in ((self.tab_familia, r.get("familias") or []),
                         (self.tab_categoria, r.get("categorias_bap") or [])):
            tf.delete(*tf.get_children())
            tot_f = sum(x["meta"] for x in fams)
            for i, x in enumerate(fams):
                tf.insert("", "end", tags=("zebra",) if i % 2 else (),
                          values=[x["familia"], dinheiro(x["meta"]),
                                  f"{numero_br(x['meta'] / tot_f * 100 if tot_f else 0, 1)}%",
                                  dinheiro(x["m3m"]), x["clientes_m3m"]])
            bp.escrever_total(tf, ["TOTAL", dinheiro(tot_f),
                                   "100%" if fams else "",
                                   dinheiro(sum(x["m3m"] for x in fams)), ""])
        t = r["total"]
        dep = t["excedentes"]
        de_onde = (f"soma dos clientes {dinheiro(t['meta'])}   |   "
                   f"{r['no_piso']} linha(s) no piso   |   META GERAL "
                   f"{dinheiro(self.par['meta_geral'])} (a UF e o gerente)")
        alerta = ("   ATENCAO: o M3M ANTERIOR veio ZERADO neste PLANNER - "
                  "refaca a BASE_CLIENTE e o PLANNER."
                  if self.dados.get("sem_m3m_anterior") else "")
        _ = (de_onde, dep)
        self.lbl_painel.configure(text=alerta.strip(),
                                  foreground=COR_ALERTA)
        self._mes_nas_abas()

    def _valores(self, linha, total=False, recorte=""):
        saida = []
        for chave, _, _, _, _ in self.COLUNAS:
            v = linha.get(chave)
            if chave == "codigo":
                saida.append("TOTAL" if total else (v or ""))
            elif chave == "nome":
                saida.append(f"TOTAL DE {mn.TITULO_DO_RECORTE[recorte]}"
                             if total else (v or linha.get("rotulo") or ""))
            elif chave == "faixa":
                saida.append("" if total else (v or ""))
            elif chave in ("meta_visita", "meta_positivacao",
                           "meta_cadastro"):
                # visita, cliente e cadastro sao coisa de contar: numero
                # inteiro, arredondado para cima e sem casa decimal.
                # None = a linha nao TEM essa meta, e vazio nao e zero.
                saida.append("" if v is None else numero_br(inteiro(v), 0))
            elif chave in ("fat_m3m", "fat_m3m_anterior", "meta",
                           "meta_dos_clientes") or chave.startswith("meta_"):
                saida.append(dinheiro(v))
            else:
                saida.append(v)
        return saida

    # ------------------------------------------------------ ajuste a mao
    def _sublinhas(self, recorte, chave):
        """As linhas do nivel de baixo que formam a linha clicada."""
        filho = self.FILHO.get(recorte) or ""
        if not filho or not self.resultado:
            return filho, []
        membros = [c for c in self.resultado["clientes"]
                   if mn.chave_da_linha(recorte, c) == chave]
        chaves = {mn.chave_da_linha(filho, c) for c in membros}
        filhas = [l for l in self.resultado["recortes"][filho]
                  if l["chave"] in chaves]
        return filho, sorted(filhas, key=lambda x: -x["meta"])

    def _item_de_edicao(self, recorte, linha, pai=False):
        return {
            "recorte": recorte,
            "chave": linha["chave"],
            "nivel": mn.TITULO_DO_RECORTE[recorte] + (" *" if pai else ""),
            "rotulo": linha["rotulo"],
            "codigo": linha.get("codigo", ""),
            "nome": linha.get("nome") or linha["rotulo"],
            "clientes": linha["clientes"],
            "fat_m3m": linha["fat_m3m"],
            "meta_com": linha["meta"],
            "meta_calculada": linha.get("meta_calculada_rh",
                                        linha.get("meta_calculada",
                                                  linha["meta"])),
            "meta": linha.get("meta_rh", linha["meta"]),
            "origem": linha.get("faixa_rh") or linha.get("faixa") or "",
            "ajustada": bool(linha.get("ajustada")),
            "pai": pai,
        }

    def _abrir_edicao(self, recorte):
        """Clicou numa linha do painel: a tabela editavel abre embaixo."""
        if self._silencio or not self.resultado:
            return
        if self._segmento_da_tela():
            self.aviso("Com o filtro de SEGMENTO ligado o painel e so para "
                       "leitura - volte o Segmento para (todos) para editar "
                       "a meta.", COR_ALERTA)
            return
        marcada = self.visoes[recorte].focus()
        if not marcada:
            return
        linha = next((l for l in self.resultado["recortes"][recorte]
                      if l["chave"] == marcada), None)
        if linha is None:
            return
        self._fechar_celula()
        filho, filhas = self._sublinhas(recorte, marcada)
        self._edicao = [self._item_de_edicao(recorte, linha, pai=True)]
        LIMITE = 300
        for f in filhas[:LIMITE]:
            self._edicao.append(self._item_de_edicao(filho, f))
        texto = (f"{mn.TITULO_DO_RECORTE[recorte]}: {linha['rotulo']}"
                 f"   |   meta {dinheiro(linha['meta'])}"
                 f"   |   {linha['clientes']} cliente(s)")
        if filhas:
            texto += (f"   |   aberta em {len(filhas)} "
                      f"{mn.TITULO_DO_RECORTE[filho].lower()}(s)")
            if len(filhas) > LIMITE:
                texto += f" - mostrando os {LIMITE} maiores"
        self.lbl_edicao.configure(text=texto)
        self._desenhar_edicao()
        if not self.quadro_edicao.winfo_ismapped():
            self.quadro_edicao.pack(fill="x", pady=(10, 0))

    # ------------------------------------------------ o mes nas abas
    def _mes_nas_abas(self):
        comp = mn.normalizar_competencia(self.var_competencia.get())
        rot = f"  ·  {mn.rotulo_do_mes(comp)}" if comp else ""
        for aba, nome in ((self.aba_par, "1. Parâmetros"),
                          (self.aba_painel, "2. Painel de meta")):
            try:
                self.abas.tab(aba, text=nome + rot)
            except tk.TclError:
                pass

    # ------------------------------------------- meta geral do mes
    def gerar_pela_geral(self):
        """Mes sem meta no arquivo: a META GERAL digitada se reparte por
        todos os clientes (pelo M3M) e sobe para vendedor, supervisor e
        gerente."""
        comp = mn.normalizar_competencia(self.var_competencia.get())
        if not comp:
            self.aviso("Escolha o mês da meta.", COR_ALERTA)
            return
        valor = numero(self.var_geral_mes.get(), 0.0)
        mn.gravar_meta_geral_do_mes(self.par, comp, valor)
        self._mostrar_meta_do_mes()
        if self.dados:
            self.gerar(gravar=False)

    # ------------------------------------------------- RECALCULAR
    def _planner_mudou(self, comp) -> bool:
        """A equipe/zonas do mes no Planner mudaram depois do PLANNER?"""
        cfg = pb.config_do_mes(AQUI, comp) if comp else None
        if cfg is None or not cfg.exists():
            return False
        do_mes = pb.planner_do_mes(AQUI, comp)
        if do_mes is None:
            return True
        try:
            return cfg.stat().st_mtime > do_mes.stat().st_mtime
        except OSError:
            return False

    def recalcular(self):
        """Refaz o PLANNER do mes com a equipe e as zonas do Planner
        daquele mes (quem saiu, sai; quem entrou, entra) e gera a meta de
        novo. Sem configuracao do mes no Planner, so recalcula."""
        comp = mn.normalizar_competencia(self.var_competencia.get())
        if not comp or not pb.config_do_mes(AQUI, comp).exists():
            self.gerar(gravar=False)
            return
        if getattr(self, "_recalculando", False):
            return
        self._recalculando = True
        self.aviso(f"Atualizando equipe e zonas de {mn.rotulo_do_mes(comp)}"
                   f" pelo Planner…", COR_SUAVE)
        self.configure(cursor="watch")
        import threading                                # noqa: PLC0415
        import planner_nucleo as pn                     # noqa: PLC0415
        saida = {}

        def trabalho():
            try:
                saida["ok"] = pn.gerar_planner_do_mes(AQUI, comp)
            except Exception as erro:                   # noqa: BLE001
                saida["erro"] = erro

        th = threading.Thread(target=trabalho, daemon=True)
        th.start()

        def esperar():
            if th.is_alive():
                self.after(200, esperar)
                return
            self._recalculando = False
            self.configure(cursor="")
            if "erro" in saida:
                self.aviso(f"Não consegui refazer o PLANNER de "
                           f"{mn.rotulo_do_mes(comp)}: {saida['erro']}",
                           COR_ALERTA)
                return
            self.carregar_planner(saida["ok"])
            self.gerar(gravar=False)
            self.aviso(f"{mn.rotulo_do_mes(comp)}: equipe e zonas do Planner "
                       f"atualizadas. Clique em GRAVAR A META DO MÊS para "
                       f"valer.", COR_OK)
        self.after(200, esperar)

    # as metas que se escrevem a mao direto no painel (duas batidas)
    EDITAVEIS = {"meta": "DESAFIO FAT. TT", "meta_rh": "META FAT. TT",
                 "meta_visita": "META VISITA",
                 "meta_positivacao": "META POSITIVACAO",
                 "meta_cadastro": "META CADASTRO"}

    @staticmethod
    def _coluna_clicada(t, evento) -> str:
        """A chave da coluna onde o clique caiu (respeita o VER TUDO)."""
        try:
            n = int(str(t.identify_column(evento.x)).lstrip("#")) - 1
        except (ValueError, TypeError):
            return ""
        visiveis = t["displaycolumns"]
        if not visiveis or tuple(visiveis) in (("#all",), ("",)) or \
                visiveis == "#all":
            visiveis = t["columns"]
        visiveis = list(visiveis)
        return visiveis[n] if 0 <= n < len(visiveis) else ""

    def _editar_no_painel(self, recorte, evento):
        """Duas batidas numa linha do painel: a caixinha abre em cima da
        meta clicada - faturamento, visita, positivacao ou cadastro (fora
        dessas colunas, a de faturamento)."""
        t = self.visoes[recorte]
        iid = t.identify_row(evento.y)
        if not iid or self._silencio or not self.resultado:
            return "break"
        if self._segmento_da_tela():
            self.aviso("Com o filtro de SEGMENTO ligado o painel e so para "
                       "leitura - volte o Segmento para (todos) para editar "
                       "a meta.", COR_ALERTA)
            return "break"
        if recorte == "segmento":
            self.aviso("A meta do SEGMENTO e a soma dos clientes dele: "
                       "escreva a meta no cliente, na zona ou no vendedor.",
                       COR_SUAVE)
            return "break"
        linha = next((l for l in self.resultado["recortes"][recorte]
                      if l["chave"] == iid), None)
        if linha is None:
            return "break"
        campo = self._coluna_clicada(t, evento)
        if campo in ("meta_pecas", "meta_lubrificante", "meta_bateria",
                     "meta_pneu"):
            self.aviso("As metas por categoria seguem a de faturamento, "
                       "pelos percentuais da aba 1.", COR_SUAVE)
            return "break"
        if campo not in self.EDITAVEIS:
            campo = "meta_rh"
        if campo == "meta" and recorte != "gerente":
            self.aviso("O DESAFIO FAT. TT (comercial) é o do gerente "
                       "desdobrado: escreva o do gerente, ou a META FAT. TT "
                       "desta linha.", COR_SUAVE)
            return "break"
        if campo in mn.AJUSTE_SO_EM_PESSOA and \
                recorte not in mn.AJUSTE_SO_EM_PESSOA[campo]:
            self.aviso("A meta de CADASTRO e de pessoa: escreva no "
                       "vendedor, no supervisor ou no gerente.", COR_SUAVE)
            return "break"
        if iid not in t.selection():         # (o 1o clique ja marcou)
            t.selection_set(iid)
        t.focus(iid)
        self._abrir_edicao(recorte)          # a de baixo segue a linha
        t.see(iid)
        t.update_idletasks()
        caixa = t.bbox(iid, campo)
        if not caixa:
            if campo in ("meta", "meta_rh"):  # coluna escondida: embaixo
                self._editar_celula(f"{recorte}|{iid}", self._coluna_da_meta())
            return "break"
        self._fechar_celula()
        x, y, largura, altura = caixa
        atual = linha.get(campo) or 0.0
        rotulo_campo = self.EDITAVEIS[campo]
        # as duas de faturamento gravam no mesmo lugar (a RH; no gerente
        # as duas sao a mesma)
        campo = "meta" if campo == "meta_rh" else campo
        var = tk.StringVar(value=dinheiro(atual) if campo == "meta"
                           else numero_br(inteiro(atual), 0))
        campo_tela = tk.Entry(t, textvariable=var, justify="right",
                              font=(self.FONTE, 9, "bold"), relief="solid",
                              borderwidth=1, highlightthickness=1,
                              highlightcolor=COR_TITULO)
        campo_tela.place(x=x, y=y, width=max(largura, 90), height=altura)
        campo_tela.focus_set()
        campo_tela.select_range(0, "end")
        self._celula = campo_tela
        item = {"recorte": recorte, "chave": iid}

        def gravar(_=None):
            texto = var.get().strip()
            self._fechar_celula()
            if not texto:
                mn.tirar_ajuste(self.par, recorte, iid, campo)
            else:
                mn.marcar_ajuste(self.par, recorte, iid,
                                 numero(texto, atual), campo)
            self._refazer(item)
            self.aviso(f"{rotulo_campo} de {linha['rotulo']}: "
                       + ("volta ao calculado." if not texto else
                          "escrita a mao.") + " Clique em GRAVAR A META DO "
                       "MES para valer.", COR_OK)

        campo_tela.bind("<Return>", gravar)
        campo_tela.bind("<KP_Enter>", gravar)
        campo_tela.bind("<Escape>", lambda _: self._fechar_celula())
        campo_tela.bind("<FocusOut>", lambda _: self._fechar_celula())
        return "break"

    def _desenhar_edicao(self):
        t = self.tab_edicao
        t.delete(*t.get_children())
        for i, item in enumerate(self._edicao):
            if item["ajustada"]:
                tags = ("ajustada",)
            elif item["pai"]:
                tags = ("pai",)
            else:
                tags = ("zebra",) if i % 2 else ()
            t.insert("", "end", iid=f"{item['recorte']}|{item['chave']}",
                     tags=tags, values=[
                         item["nivel"], item["codigo"], item["nome"],
                         item["clientes"],
                         dinheiro(item["fat_m3m"]),
                         dinheiro(item["meta_com"]),
                         dinheiro(item["meta_calculada"]),
                         dinheiro(item["meta"]), item["origem"]])

    def _fechar_edicao(self):
        self._fechar_celula()
        self._edicao = []
        if self.quadro_edicao.winfo_ismapped():
            self.quadro_edicao.pack_forget()

    def _achar_item(self, iid):
        for item in self._edicao:
            if f"{item['recorte']}|{item['chave']}" == iid:
                return item
        return None

    # ---- a caixinha de digitacao em cima da celula ----------------------
    def _fechar_celula(self):
        if self._celula is not None:
            try:
                self._celula.destroy()
            except tk.TclError:
                pass
            self._celula = None

    def _coluna_da_meta(self) -> str:
        return f"#{[c[0] for c in self.COLUNAS_EDICAO].index('meta') + 1}"

    def _clique_na_celula(self, evento):
        t = self.tab_edicao
        self._editar_celula(t.identify_row(evento.y),
                            t.identify_column(evento.x))
        return "break"

    def _editar_celula(self, iid, coluna):
        """Duas batidas na coluna META QUE VALE: abre a caixinha ali."""
        t = self.tab_edicao
        item = self._achar_item(iid) if iid else None
        if item is None:
            return
        if item["recorte"] == "segmento":
            self.aviso("A meta do SEGMENTO e a soma dos clientes dele: "
                       "escreva a meta no cliente, na zona ou no vendedor.",
                       COR_SUAVE)
            return
        if coluna != self._coluna_da_meta():
            t.selection_set(iid)
            t.focus(iid)
            self.aviso("Para escrever a meta a mao, clique duas vezes na "
                       "coluna META QUE VALE.", COR_SUAVE)
            return
        caixa = t.bbox(iid, "meta")
        if not caixa:
            return
        self._fechar_celula()
        x, y, largura, altura = caixa
        var = tk.StringVar(value=dinheiro(item["meta"]))
        campo = tk.Entry(t, textvariable=var, justify="right",
                         font=(self.FONTE, 9), relief="solid", borderwidth=1)
        campo.place(x=x, y=y, width=largura, height=altura)
        campo.focus_set()
        campo.select_range(0, "end")
        self._celula = campo

        def gravar(_=None):
            valor = numero(var.get(), item["meta"])
            self._fechar_celula()
            mn.marcar_ajuste(self.par, item["recorte"], item["chave"], valor)
            self._refazer(item)

        campo.bind("<Return>", gravar)
        campo.bind("<KP_Enter>", gravar)
        campo.bind("<Escape>", lambda _: self._fechar_celula())
        campo.bind("<FocusOut>", lambda _: self._fechar_celula())

    def _desfazer_linha(self):
        item = self._achar_item(self.tab_edicao.focus())
        if item is None:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Marque a linha que deve voltar ao valor "
                                "calculado.")
            return
        for campo in mn.CAMPOS_COM_AJUSTE:
            mn.tirar_ajuste(self.par, item["recorte"], item["chave"], campo)
        self._refazer(item)

    def _desfazer_tudo(self):
        if not (self.par.get("ajustes") or {}) and not any(
                (self.par.get("ajustes_ind") or {}).values()):
            self.aviso("Nao ha meta escrita a mao.", COR_SUAVE)
            return
        if not messagebox.askyesno("Gerador de Meta BAP",
                                   "Apagar TODAS as metas escritas a mao?"):
            return
        self.par["ajustes"] = {}
        self.par["ajustes_ind"] = {}
        self._refazer(None)

    def _refazer(self, item):
        """Recalcula tudo e deixa a tabela de baixo aberta onde estava."""
        recorte = item["recorte"] if item else None
        chave = item["chave"] if item else None
        pai = next((i for i in self._edicao if i["pai"]), None)
        self.gerar(gravar=False)
        if pai:
            aba = mn.RECORTES.index(pai["recorte"])
            self.recortes.select(aba)
            tabela = self.visoes[pai["recorte"]]
            if tabela.exists(pai["chave"]):
                self._silencio = True
                try:
                    tabela.selection_set(pai["chave"])
                    tabela.focus(pai["chave"])
                    tabela.see(pai["chave"])
                finally:
                    self._silencio = False
            self._abrir_edicao(pai["recorte"])
            if recorte and chave and \
                    self.tab_edicao.exists(f"{recorte}|{chave}"):
                self.tab_edicao.selection_set(f"{recorte}|{chave}")
                self.tab_edicao.focus(f"{recorte}|{chave}")
        self.aviso("Meta refeita com o valor escrito a mao.", COR_OK)

    # --------------------------------------------------------- exportar
    def guardar(self, avisar=False):
        """
        A meta MORA no ACOMPANHAMENTO_META_BAP.xlsx, dentro da pasta
        RELATORIOS: uma aba por mes ("202609") e UMA aba ANALITICO com
        todos os meses, com a coluna MES para filtrar. Os outros meses que
        ja estao la nao sao tocados.
        """
        if not self.resultado:
            messagebox.showinfo("Gerador de Meta BAP",
                                "Gere a meta primeiro (aba 1).")
            return None
        competencia = self.resultado["competencia"]
        try:
            destino = mn.guardar_meta_do_mes(self.resultado, self.par, AQUI,
                                             competencia)
        except (OSError, ValueError, PermissionError) as erro:
            self.aviso(f"Nao deu para gravar o "
                       f"{mn.ARQUIVO_ACOMPANHAMENTO}: {erro}", COR_ALERTA)
            if avisar:
                messagebox.showerror(
                    "Gerador de Meta BAP",
                    f"Nao deu para gravar o {mn.ARQUIVO_ACOMPANHAMENTO}.\n\n"
                    f"Se ele estiver aberto no Excel, feche e tente de "
                    f"novo.\n\n{erro}")
            return None
        self._encher_meses()
        self.aviso(f"Meta de {competencia} gravada na aba "
                   f"{mn.marca_do_mes(competencia)} do {destino.name}.",
                   COR_OK)
        return destino

    def exportar(self):
        """Compatibilidade: o botao antigo agora grava no arquivo do mes."""
        return self.guardar(avisar=True)

    # ---------------------------------------------------- metas do Excel
    def _contar_metas(self):
        """A etiqueta que diz o que esta importado."""
        imp = self.par.get("metas_importadas")
        if not imp:
            self.lbl_metas.configure(
                text="Nenhum arquivo de meta importado ainda.",
                foreground=COR_SUAVE)
            self._mostrar_meta_do_mes()
            return
        meses = imp.get("meses") or []
        faixa = (f"{meses[0]} a {meses[-1]}" if len(meses) > 1
                 else (meses[0] if meses else "?"))
        avisos = imp.get("avisos") or []
        por_polo = imp.get("por_polo")
        quem = "filial(is)" if por_polo else "cidade(s)"
        self.lbl_metas.configure(
            text=f"{imp.get('linhas', 0)} linha(s) de meta, "
                 f"{len(imp.get('cidades') or {})} {quem}, {faixa}"
                 + ("   (MODELO por FILIAL x CATEGORIA, um mes por coluna)"
                    if por_polo else "   (lista ANO/MES/CIDADE)")
                 + (f"   {len(avisos)} linha(s) do arquivo ficaram de fora: "
                    f"{avisos[0]}" if avisos else ""),
            foreground=COR_ALERTA if avisos else COR_SUAVE)
        self._mostrar_meta_do_mes()

    def importar_metas(self):
        caminho = filedialog.askopenfilename(
            title="Escolha o Excel com as metas",
            initialdir=str(AQUI / pb.RELATORIOS),
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not caminho:
            return
        try:
            imp = mn.ler_metas(caminho)
        except (OSError, ValueError, FileNotFoundError, KeyError) as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            self.aviso(str(erro), COR_ALERTA)
            return

        clientes = (self.dados or {}).get("clientes") or []
        if imp.get("por_polo"):
            # A META VEIO POR FILIAL: quem diz que cidade pertence a que
            # filial e a aba Filiais da TABELA_BAP. Sem ela o programa
            # ainda liga a cidade ao polo mais proximo da mesma UF, mas
            # avisa - porque ai o vinculo e deduzido, nao lido.
            tabela = AQUI / pb.RELATORIOS / "TABELA_BAP.xlsx"
            polos = mn.ler_polos_da_tabela(tabela)
            imp["polo_da_cidade"] = polos.get("polo_da_cidade") or {}
            imp["cidades_do_polo"] = polos.get("cidades_do_polo") or {}
            imp.setdefault("filiais", {}).update(polos.get("filiais") or {})
            if not imp["polo_da_cidade"]:
                imp["_sem_tabela"] = True

        self.par["metas_importadas"] = imp
        self._gravar_par()
        self._contar_metas()

        recado = (f"{imp['linhas']} linha(s) lidas, "
                  f"{len(imp.get('cidades') or {})} "
                  f"{'filial(is)' if imp.get('por_polo') else 'cidade(s)'}, "
                  f"meses {', '.join(imp.get('meses') or [])[:140]}.")
        alerta = False
        if imp.get("por_polo"):
            ligacao = mn.ligar_cidades_aos_polos(imp, clientes)
            fora = [n for k, n in (imp.get("polos") or {}).items()
                    if k not in set(ligacao["polo_da_cidade"].values())]
            sem_polo = ligacao.get("sem_polo") or []
            recado += (f"   {len(ligacao['polo_da_cidade'])} cidade(s) da "
                       f"base ligadas as filiais.")
            if imp.get("_sem_tabela"):
                recado += ("   ATENCAO: nao achei a TABELA_BAP para ler a "
                           "aba Filiais - liguei a cidade ao polo mais "
                           "proximo da mesma UF, o que e deducao, nao "
                           "cadastro.")
                alerta = True
            if fora:
                recado += (f"   {len(fora)} filial(is) do arquivo nao "
                           f"pegaram cliente nenhum: {', '.join(fora[:6])}.")
                alerta = True
            if sem_polo:
                recado += (f"   {len(sem_polo)} cidade(s) da base ficaram "
                           f"sem filial e seguem pelo crescimento.")
        else:
            conhecidas = {mn.chave_de_cidade(c.get("cidade"))
                          for c in clientes}
            fora = [n for k, n in (imp.get("cidades") or {}).items()
                    if conhecidas and k not in conhecidas]
            if fora:
                recado += (f"   ATENCAO: {len(fora)} cidade(s) do arquivo "
                           f"nao existem no PLANNER e vao ficar sem efeito: "
                           f"{', '.join(fora[:6])}.")
                alerta = True
        self.aviso(recado + "   Clique em GERAR A META para aplicar.",
                   COR_ALERTA if alerta else COR_OK)

    def modelo_por_filial(self):
        """O modelo largo: FILIAL x CATEGORIA, um mes por coluna."""
        destino = AQUI / pb.RELATORIOS / mn.ARQUIVO_MODELO_META
        ano = mn.normalizar_competencia(self.var_competencia.get())
        try:
            mn.modelo_de_meta_por_filial(
                destino, int(ano[:4]) if ano else None,
                caminho_tabela=AQUI / pb.RELATORIOS / "TABELA_BAP.xlsx")
        except (OSError, PermissionError, ValueError) as erro:
            messagebox.showerror("Gerador de Meta BAP",
                                 f"Nao deu para gravar o modelo.\n\n{erro}")
            return
        self.aviso(f"Modelo gravado em {pb.RELATORIOS}\\{destino.name} - "
                   f"uma linha por FILIAL x CATEGORIA e doze colunas de mes. "
                   f"Preencha as celulas dos meses e importe de volta. A aba "
                   f"COMO PREENCHER explica cada coluna.", COR_OK)
        return destino

    def modelo_de_metas(self):
        cidades = sorted({(c.get("cidade") or "").strip().upper()
                          for c in ((self.dados or {}).get("clientes") or [])
                          if (c.get("cidade") or "").strip()})
        destino = AQUI / pb.RELATORIOS / "MODELO_METAS_BAP.xlsx"
        try:
            mn.modelo_de_metas(destino, cidades)
        except (OSError, PermissionError) as erro:
            messagebox.showerror("Gerador de Meta BAP",
                                 f"Nao deu para gravar o modelo.\n\n{erro}")
            return
        self.aviso(f"Modelo gravado em {pb.RELATORIOS}\\{destino.name} - "
                   f"{len(cidades) or 1} cidade(s) x 12 meses x 4 categorias. "
                   f"Preencha a coluna META e importe de volta.", COR_OK)
        return destino

    def limpar_metas(self):
        if not self.par.get("metas_importadas"):
            return
        if not messagebox.askyesno(
                "Gerador de Meta BAP",
                "Esquecer as metas importadas?\n\nA meta volta a sair do "
                "crescimento (M3M atual x M3M anterior), com o piso."):
            return
        self.par.pop("metas_importadas", None)
        self._gravar_par()
        self._contar_metas()
        self.aviso("Metas importadas esquecidas. Clique em GERAR A META "
                   "para recalcular.", COR_OK)

    # ================================================================
    # ABA 4 - INDICADORES EXECUTIVOS
    # ================================================================
    def _montar_executivo(self):
        f = self.aba_exec
        ttk.Label(f, text="Indicadores executivos",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(f, text="Cinco indicadores, um PESO para cada, e mes a mes "
                          "META, REAL, % AT. META (o atingimento da meta) e "
                          "% AT. PESO (quanto do peso ele entregou). A ESCADA "
                          "DO PESO: abaixo de 80% da meta nao pontua; em 80% "
                          "vale metade do peso; dali para cima cada 1% soma "
                          "2,5 pontos, ate o teto de 120%. Ou seja, 100% da "
                          "meta entrega 100% do peso e 108% ja bate o teto. "
                          "Na ponta de cada bloco, em VERDE, o FECHAMENTO DO "
                          "TRIMESTRE: a meta e o real dos tres meses SOMADOS "
                          "- nao a media dos tres percentuais. Passe o mouse "
                          "nele para ver a soma.",
                  style="Sub.TLabel", wraplength=1340).pack(anchor="w",
                                                            pady=(2, 10))

        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 10))
        ttk.Label(barra, text="Ano:").pack(side="left")
        self.var_ano_exec = tk.StringVar(
            value=str((self.par.get("executivo") or {}).get("ano")
                      or dt.date.today().year))
        anos = [str(a) for a in range(dt.date.today().year - 3,
                                      dt.date.today().year + 3)]
        cb = ttk.Combobox(barra, textvariable=self.var_ano_exec, width=8,
                          state="readonly", values=anos)
        cb.pack(side="left", padx=(6, 16))
        cb.bind("<<ComboboxSelected>>", lambda _: self._trocar_ano_exec())
        ttk.Button(barra, text="APURAR O REAL", style="Big.TButton",
                   command=self.apurar_executivo).pack(side="left")
        ttk.Button(barra, text="Salvar", command=self.salvar_executivo).pack(
            side="left", padx=8)
        ttk.Button(barra, text="EXPORTAR PARA EXCEL",
                   command=self.exportar_executivo).pack(side="left")
        ttk.Label(barra, text="  A DESPESA e digitada: ela nao existe na "
                              "TABELA_BAP. E ela conta AO CONTRARIO - gastar "
                              "menos que a meta e bom, entao ali o "
                              "atingimento e meta / real.",
                  style="Sub.TLabel", wraplength=560).pack(side="left",
                                                           padx=(16, 0))

        # ---- o pos-venda do mes, embaixo, FORA DO PESO ----------------
        # Vem do ACOMPANHAMENTO_POS_VENDA. Fica de proposito fora dos cinco
        # indicadores com peso: aqueles sao a nota da diretoria, e mudar o
        # peso deles e decisao de quem cobra a nota - nao deste programa.
        self.quadro_pos = ttk.LabelFrame(
            f, text=" Pós-venda do mês — do ACOMPANHAMENTO_POS_VENDA "
                    "(informativo, fora do peso) ", padding=(12, 8))
        self.quadro_pos.pack(side="bottom", fill="x", pady=(10, 0))
        self._montar_pos_venda(self.quadro_pos)

        quadro = ttk.Frame(f)
        quadro.pack(fill="both", expand=True)
        self.tela_exec = tk.Canvas(quadro, highlightthickness=0,
                                   background=COR_PAPEL)
        rol_y = ttk.Scrollbar(quadro, orient="vertical",
                              command=self.tela_exec.yview)
        rol_x = ttk.Scrollbar(f, orient="horizontal",
                              command=self.tela_exec.xview)
        self.grade_exec = ttk.Frame(self.tela_exec)
        self.grade_exec.bind(
            "<Configure>",
            lambda _: self.tela_exec.configure(
                scrollregion=self.tela_exec.bbox("all")))
        self.tela_exec.create_window((0, 0), window=self.grade_exec,
                                     anchor="nw")
        self.tela_exec.configure(yscrollcommand=rol_y.set,
                                 xscrollcommand=rol_x.set)
        self.tela_exec.pack(side="left", fill="both", expand=True)
        rol_y.pack(side="right", fill="y")
        rol_x.pack(fill="x", pady=(4, 0))

        self.lbl_exec = ttk.Label(f, text="", style="Sub.TLabel",
                                  wraplength=1340)
        self.lbl_exec.pack(anchor="w", pady=(8, 0))
        self.real_exec = {}
        self._desenhar_executivo()

    def _config_exec(self) -> dict:
        """A configuracao do painel, sempre completa."""
        exe = self.par.setdefault("executivo", {})
        if not exe.get("indicadores"):
            exe["indicadores"] = mn.indicadores_padrao()
        ano = int(mn._numero(self.var_ano_exec.get()
                             if hasattr(self, "var_ano_exec")
                             else exe.get("ano")) or dt.date.today().year)
        exe["ano"] = ano
        exe["meses"] = mn.meses_do_ano(ano)
        exe.setdefault("metas", {})
        exe.setdefault("reais", {})
        return exe

    def _trocar_ano_exec(self):
        self._ler_executivo_da_tela()
        self.real_exec = {}
        self._desenhar_executivo()

    # ---- as cores do painel executivo -----------------------------------
    # A tela e uma grade de campos, nao uma tabela: sem cor nos titulos o
    # olho nao acha onde um mes acaba e o outro comeca. Entao o mes vem
    # numa tarja azul escura, os quatro titulos dele numa faixa azul
    # clara, e o FECHAMENTO DO TRIMESTRE em verde - para ninguem
    # confundir a coluna que fecha o trimestre com mais um mes.
    EXEC_MES_FUNDO = "#2F7D32"
    EXEC_MES_TEXTO = "#FFFFFF"
    EXEC_CAB_FUNDO = "#E5F3DF"
    EXEC_CAB_TEXTO = "#2F7D32"
    EXEC_TRI_FUNDO = "#1E7A46"
    EXEC_TRI_CAB = "#DDF0E2"
    EXEC_TRI_TEXTO = "#14522F"
    EXEC_LINHA_PAR = "#F7F8F6"
    EXEC_TOTAL_FUNDO = "#E4E7E3"

    def _tarja_exec(self, texto, linha, coluna, vao=1, fundo=None, cor=None,
               fonte=("Segoe UI", 9, "bold"), pad=(0, 0)):
        """Uma etiqueta PINTADA na grade - ttk.Label nao aceita fundo."""
        etiqueta = tk.Label(self.grade_exec, text=texto, font=fonte,
                            background=fundo or self.EXEC_MES_FUNDO,
                            foreground=cor or self.EXEC_MES_TEXTO,
                            padx=6, pady=3)
        etiqueta.grid(row=linha, column=coluna, columnspan=vao, sticky="we",
                      padx=1, pady=pad)
        return etiqueta

    def _quadro_exec(self, texto, linha, coluna, largura=10, fundo=None,
                     cor=None, negrito=False, dica=""):
        """Um numero de leitura, com fundo - para a zebra e os totais."""
        etiqueta = tk.Label(self.grade_exec, text=texto, width=largura,
                            anchor="e", padx=4,
                            font=("Segoe UI", 9, "bold") if negrito
                            else ("Segoe UI", 9),
                            background=fundo or COR_PAPEL,
                            foreground=cor or COR_TEXTO)
        etiqueta.grid(row=linha, column=coluna, sticky="we", padx=1)
        if dica:
            self._dica(etiqueta, dica)
        return etiqueta

    def _dica(self, widget, texto):
        """A tarjinha que aparece quando o mouse para em cima."""
        def entrar(_=None):
            self.lbl_exec.configure(text=texto, foreground=COR_TITULO)
        widget.bind("<Enter>", entrar)

    # ---- o bloco de pos-venda (entrega, devolucao, garantia) ------------
    POS_VENDA_TILES = [
        ("prazo", "ENTREGAS NO PRAZO"), ("atrasadas", "ATRASADAS AGORA"),
        ("canhoto", "ENTREGUES SEM CANHOTO"), ("dev", "DEVOLUÇÕES NO MÊS"),
        ("sem_motivo", "DEVOLUÇÕES SEM MOTIVO"),
        ("garantias", "GARANTIAS EM ABERTO"),
    ]

    def _montar_pos_venda(self, f):
        linha = ttk.Frame(f)
        linha.pack(fill="x")
        self.tiles_pos = {}
        for chave, rotulo in self.POS_VENDA_TILES:
            caixa = tk.Frame(linha, background="#F7F8F6",
                             highlightbackground=COR_LINHA,
                             highlightthickness=1)
            caixa.pack(side="left", fill="both", expand=True, padx=(0, 8))
            tk.Label(caixa, text=rotulo, background="#F7F8F6",
                     foreground=COR_SUAVE, font=(self.FONTE, 8, "bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(6, 0))
            valor = tk.Label(caixa, text="—", background="#F7F8F6",
                             foreground=COR_TITULO, font=(self.FONTE, 15),
                             anchor="w")
            valor.pack(fill="x", padx=10)
            nota = tk.Label(caixa, text="", background="#F7F8F6",
                            foreground=COR_SUAVE, font=(self.FONTE, 8),
                            anchor="w")
            nota.pack(fill="x", padx=10, pady=(0, 6))
            self.tiles_pos[chave] = (valor, nota)
        rodape = ttk.Frame(f)
        rodape.pack(fill="x", pady=(8, 0))
        self.lbl_pos_motivos = ttk.Label(rodape, text="", style="Sub.TLabel",
                                         wraplength=1000)
        self.lbl_pos_motivos.pack(side="left", fill="x", expand=True)
        ttk.Button(rodape, text="Abrir o acompanhamento",
                   command=self.abrir_pos_venda).pack(side="right")
        ttk.Button(rodape, text="Atualizar",
                   command=self._desenhar_pos_venda).pack(side="right", padx=8)
        self._desenhar_pos_venda()

    def _arquivo_pos_venda(self):
        return AQUI / pb.RELATORIOS / "ACOMPANHAMENTO_POS_VENDA.xlsx"

    def _desenhar_pos_venda(self):
        caminho = self._arquivo_pos_venda()
        if not caminho.exists():
            for valor, nota in self.tiles_pos.values():
                valor.configure(text="—", foreground=COR_SUAVE)
                nota.configure(text="")
            self.lbl_pos_motivos.configure(
                text="O ACOMPANHAMENTO_POS_VENDA ainda não existe nesta pasta "
                     "— ele nasce na próxima rodada do BAP Tools.",
                foreground=COR_SUAVE)
            return
        try:
            import pos_venda                             # noqa: PLC0415
            ind = pos_venda.ler_acompanhamento(caminho)["indicadores"]
        except Exception as erro:                       # noqa: BLE001
            self.lbl_pos_motivos.configure(
                text=f"Não consegui ler o acompanhamento: {erro}",
                foreground=COR_ALERTA)
            return
        pct = ind["entregas_no_prazo_pct"]
        valores = {
            "prazo": ("—" if pct is None else f"{numero_br(pct, 0)}%",
                      "das que já foram entregues",
                      COR_OK if pct is None or pct >= 90 else COR_ALERTA),
            "atrasadas": (str(ind["entregas_atrasadas"]),
                          "passaram da data prevista",
                          COR_ALERTA if ind["entregas_atrasadas"] else COR_OK),
            "canhoto": (str(ind["entregas_sem_canhoto"]), "canhoto a cobrar",
                        COR_ALERTA if ind["entregas_sem_canhoto"] else COR_OK),
            "dev": (str(ind["devolucoes_mes_qtd"]),
                    f"R$ {dinheiro(ind['devolucoes_mes_valor'])}",
                    COR_TITULO),
            "sem_motivo": (str(ind["devolucoes_sem_motivo"]),
                           "sem motivo, não dá para corrigir a causa",
                           COR_ALERTA if ind["devolucoes_sem_motivo"] else COR_OK),
            "garantias": (str(ind["garantias_abertas"]),
                          f"{ind['garantias_no_fornecedor_30']} há mais de 30 "
                          f"dias no fornecedor",
                          COR_ALERTA if ind["garantias_no_fornecedor_30"]
                          else COR_TITULO),
        }
        for chave, (texto, nota_txt, cor) in valores.items():
            valor, nota = self.tiles_pos[chave]
            valor.configure(text=texto, foreground=cor)
            nota.configure(text=nota_txt)
        motivos = ind["devolucoes_por_motivo"]
        self.lbl_pos_motivos.configure(
            text=("Devoluções do mês por motivo:  " + "   |   ".join(
                f"{m.title()}: {q} (R$ {dinheiro(v)})"
                for m, (q, v) in list(motivos.items())[:5])) if motivos
            else "Nenhuma devolução no mês ainda.",
            foreground=COR_TITULO if motivos else COR_SUAVE)

    def abrir_pos_venda(self):
        caminho = self._arquivo_pos_venda()
        if not caminho.exists():
            messagebox.showinfo("Gerador de Meta BAP",
                                "O ACOMPANHAMENTO_POS_VENDA ainda não existe "
                                "— ele nasce na próxima rodada do BAP Tools.")
            return
        bp.App._abrir(caminho)

    def _desenhar_executivo(self):
        """
        O painel em TRIMESTRES, um bloco embaixo do outro: JAN-FEV-MAR,
        depois ABR-MAI-JUN, e assim por diante. Doze meses lado a lado
        obrigavam a arrastar a tela o tempo todo; em blocos de tres tudo
        cabe na largura.

        Cada bloco fecha com a coluna FECHAMENTO DO TRIMESTRE, em verde:
        a meta e o real dos tres meses SOMADOS, e o atingimento em cima
        dessa soma - nao a media dos tres percentuais.
        """
        exe = self._config_exec()
        meses = exe["meses"]
        for w in self.grade_exec.winfo_children():
            w.destroy()
        self.var_exec = {}
        painel = mn.montar_executivo(self.par, self.real_exec)
        # titulos curtos de proposito: com "% ATING. META" por extenso a
        # coluna nascia mais larga que o numero e a tela voltava a rolar.
        # O texto de cima da aba diz o que cada um e.
        cab = ("META", "REAL", "% AT. META", "% AT. PESO")
        campos_por_chave = {}
        linha_atual = 0
        self.fech_exec = {}

        for t in range(4):
            do_tri = meses[t * 3:(t + 1) * 3]
            if not do_tri:
                continue
            fech = mn.acumulado_do_executivo(painel, do_tri)
            self.fech_exec[t + 1] = fech
            # o FECHAMENTO fica na ponta, com DUAS colunas so: o que
            # interessa dele e o atingimento. A meta e o real somados do
            # trimestre saem na aba FECHAMENTO TRIMESTRE do Excel - por
            # mais duas colunas aqui a tela voltava a rolar para o lado.
            base_tri = 2 + 3 * 4          # onde comeca o bloco do fechamento
            titulo = (f"{t + 1}o TRIMESTRE   -   "
                      + "   ".join(mn.rotulo_do_mes(m) for m in do_tri))
            ttk.Label(self.grade_exec, text=titulo,
                      style="Secao.TLabel").grid(
                          row=linha_atual, column=0, columnspan=base_tri + 2,
                          sticky="w", pady=(16 if t else 0, 4))
            linha_atual += 1

            self._tarja_exec("INDICADOR", linha_atual, 0, fundo=self.EXEC_MES_FUNDO)
            self._tarja_exec("% PESO", linha_atual, 1, fundo=self.EXEC_MES_FUNDO)
            ttk.Label(self.grade_exec, text="").grid(row=linha_atual + 1,
                                                     column=0)
            for j, mes in enumerate(do_tri):
                base = 2 + j * 4
                self._tarja_exec(mn.rotulo_do_mes(mes), linha_atual, base, vao=4)
                for k, tit in enumerate(cab):
                    self._tarja_exec(tit, linha_atual + 1, base + k,
                                fundo=self.EXEC_CAB_FUNDO,
                                cor=self.EXEC_CAB_TEXTO,
                                fonte=("Segoe UI", 8, "bold"))
            self._tarja_exec(f"FECHAMENTO DO {t + 1}o TRIMESTRE", linha_atual,
                             base_tri, vao=2, fundo=self.EXEC_TRI_FUNDO)
            for k, tit in enumerate(cab[2:]):
                self._tarja_exec(tit, linha_atual + 1, base_tri + k,
                                 fundo=self.EXEC_TRI_CAB,
                                 cor=self.EXEC_TRI_TEXTO,
                                 fonte=("Segoe UI", 8, "bold"))
            linha_atual += 2

            for n, linha in enumerate(painel["linhas"]):
                chave = linha["chave"]
                fundo = self.EXEC_LINHA_PAR if n % 2 else COR_PAPEL
                campos = campos_por_chave.setdefault(
                    chave, {"peso": None, "meta": {}, "real": {}})
                tk.Label(self.grade_exec,
                         text=linha["rotulo"] + (" (inverso)"
                                                 if linha["invertido"]
                                                 else ""),
                         anchor="w", padx=6, background=fundo,
                         foreground=COR_TEXTO,
                         font=("Segoe UI", 9)).grid(
                             row=linha_atual, column=0, sticky="we", pady=1)
                # O PESO e um campo so, no primeiro trimestre; nos outros
                # ele aparece como etiqueta - dois campos para o mesmo
                # numero era pedir para eles discordarem.
                if campos["peso"] is None:
                    campos["peso"] = tk.StringVar(
                        value=numero_br(linha["peso"], 1))
                    ttk.Entry(self.grade_exec, textvariable=campos["peso"],
                              width=6, justify="right").grid(
                                  row=linha_atual, column=1, padx=(0, 4))
                else:
                    self._quadro_exec(numero_br(linha["peso"], 1),
                                      linha_atual, 1, largura=6, fundo=fundo)
                for j, mes in enumerate(do_tri):
                    base = 2 + j * 4
                    cel = linha["meses"][mes]
                    vm = tk.StringVar(value=(numero_br(cel["meta"], 2)
                                             if cel["meta"] else ""))
                    campos["meta"][mes] = vm
                    ttk.Entry(self.grade_exec, textvariable=vm, width=11,
                              justify="right").grid(row=linha_atual,
                                                    column=base, padx=1)
                    if linha["automatico"]:
                        self._quadro_exec(numero_br(cel["real"], 2)
                                     if cel["real"] else "-",
                                     linha_atual, base + 1, largura=11,
                                     fundo=fundo)
                    else:
                        vr = tk.StringVar(value=(numero_br(cel["real"], 2)
                                                 if cel["real"] else ""))
                        campos["real"][mes] = vr
                        ttk.Entry(self.grade_exec, textvariable=vr, width=11,
                                  justify="right").grid(row=linha_atual,
                                                        column=base + 1,
                                                        padx=1)
                    for k, campo in ((2, "ating"), (3, "ating_peso")):
                        self._quadro_exec(self._pct(cel[campo]), linha_atual,
                                     base + k, fundo=fundo,
                                     cor=self._cor_do_ating(cel[campo], campo))
                # ---- o fechamento do trimestre, na ponta ----------------
                # a meta e o real dos tres meses SOMADOS, e o atingimento
                # em cima dessa soma - nao a media dos tres percentuais.
                # O total somado vai na dica de quem passa o mouse.
                f_cel = fech["linhas"].get(chave) or {}
                for k, campo in ((0, "ating"), (1, "ating_peso")):
                    self._quadro_exec(
                        self._pct(f_cel.get(campo)), linha_atual,
                        base_tri + k, largura=12,
                        fundo=self.EXEC_TRI_CAB, cor=self.EXEC_TRI_TEXTO,
                        negrito=True,
                        dica=(f"{linha['rotulo']} no {t + 1}o trimestre:  "
                              f"meta {numero_br(f_cel.get('meta'), 2)}   "
                              f"real {numero_br(f_cel.get('real'), 2)}"
                              if f_cel.get("meta") else
                              "sem meta lancada nos tres meses"))
                linha_atual += 1

            t_linha = painel["total"]
            tk.Label(self.grade_exec, text="TOTAL DO MES", anchor="w", padx=6,
                     background=self.EXEC_TOTAL_FUNDO, foreground=COR_TITULO,
                     font=("Segoe UI", 9, "bold")).grid(
                         row=linha_atual, column=0, sticky="we", pady=(3, 0))
            self._quadro_exec(numero_br(t_linha["peso"], 1), linha_atual, 1,
                              largura=6, fundo=self.EXEC_TOTAL_FUNDO,
                              cor=COR_TITULO, negrito=True)
            for j, mes in enumerate(do_tri):
                base = 2 + j * 4
                cel = t_linha["meses"][mes]
                for k in (0, 1):
                    self._quadro_exec("", linha_atual, base + k, largura=11,
                                      fundo=self.EXEC_TOTAL_FUNDO)
                for k, campo in ((2, "ating"), (3, "ating_peso")):
                    self._quadro_exec(self._pct(cel[campo]), linha_atual, base + k,
                                 fundo=self.EXEC_TOTAL_FUNDO,
                                 cor=self._cor_do_ating(cel[campo], campo)
                                 or COR_TITULO, negrito=True)
            # o numero que o trimestre inteiro entrega
            for k, campo in ((0, "ating"), (1, "ating_peso")):
                self._quadro_exec(self._pct(fech["total"].get(campo)),
                                  linha_atual, base_tri + k, largura=12,
                                  fundo=self.EXEC_TRI_FUNDO, cor="#FFFFFF",
                                  negrito=True)
            linha_atual += 1

        self.var_exec = campos_por_chave
        self.painel_exec = painel
        if not self.lbl_exec.cget("text"):
            self.lbl_exec.configure(
                text="Digite as METAS e clique em APURAR O REAL para o "
                     "programa buscar o realizado na TABELA_BAP.",
                foreground=COR_SUAVE)

    def _cor_do_ating(self, valor, campo="ating"):
        """
        Verde bateu, vermelho nao pontuou, preto no meio do caminho. So
        no % ATING. META: no % ATING PESO o numero ja e o resultado, e
        pintar os dois deixava a tela parecendo um semaforo quebrado.
        """
        if campo != "ating" or valor is None:
            return None
        if valor >= 100.0:
            return COR_OK
        if valor < mn.PISO_DO_PESO:
            return COR_ALERTA
        return None

    @staticmethod
    def _pct(v):
        """12.5 -> '12,50%'. Sem valor, um tracinho."""
        if v is None:
            return "-"
        return f"{v:,.2f}%".replace(",", "@").replace(".", ",").replace("@", ".")

    def _ler_executivo_da_tela(self):
        """O que esta digitado vira configuracao."""
        exe = self._config_exec()
        indicadores = exe["indicadores"]
        for ind in indicadores:
            campos = (getattr(self, "var_exec", {}) or {}).get(ind["chave"])
            if not campos:
                continue
            ind["peso"] = numero(campos["peso"].get())
            for mes, var in campos["meta"].items():
                exe["metas"].setdefault(ind["chave"], {})[mes] = numero(
                    var.get())
            for mes, var in campos["real"].items():
                # CAMPO VAZIO GUARDA VAZIO, nao zero: e a diferenca entre
                # "ainda nao apurei este mes" e "deu zero". Na DESPESA,
                # que conta ao contrario, zero valeria o teto do peso -
                # e o mes que nem aconteceu pontuaria sozinho.
                texto = var.get().strip()
                exe["reais"].setdefault(ind["chave"], {})[mes] = (
                    numero(texto) if texto else None)

    def salvar_executivo(self):
        self._ler_executivo_da_tela()
        self._gravar_par()
        self._desenhar_executivo()
        self.lbl_exec.configure(text=f"Pesos, metas e despesas salvos em "
                                     f"{ARQ_PARAMETROS.name}.",
                                foreground=COR_OK)

    def apurar_executivo(self):
        self._ler_executivo_da_tela()
        tabela = AQUI / pb.RELATORIOS / "TABELA_BAP.xlsx"
        if not tabela.exists():
            messagebox.showwarning(
                "Gerador de Meta BAP",
                f"Nao achei a TABELA_BAP em {pb.RELATORIOS}.\n\nE dela que "
                f"sai o faturamento, a positivacao e o cadastro com compra.")
            return
        exe = self._config_exec()
        self.lbl_exec.configure(text="Lendo a TABELA_BAP...",
                                foreground=COR_SUAVE)
        self.update_idletasks()
        try:
            csv_cat = mn.achar_csv_de_categorias(AQUI)
            categorias = (mn.ler_categorias_de_produto(csv_cat)
                          if csv_cat else {})
            self.real_exec = mn.apurar_executivo(tabela, exe["meses"],
                                                 categorias)
        except (OSError, ValueError) as erro:
            messagebox.showerror("Gerador de Meta BAP", str(erro))
            self.lbl_exec.configure(text=str(erro), foreground=COR_ALERTA)
            return
        self._gravar_par()
        self._desenhar_executivo()
        com_dado = sum(1 for m in exe["meses"]
                       if self.real_exec.get(m, {}).get("faturamento"))
        self.lbl_exec.configure(
            text=f"Realizado apurado em {com_dado} mes(es) de "
                 f"{exe['ano']}." + ("" if csv_cat else
                                     "  SEM o CATEGORIAS_PRODUTO.csv na "
                                     "pasta, o FATURAMENTO DE PECAS sai "
                                     "pelo palpite do fornecedor."),
            foreground=COR_OK)

    def exportar_executivo(self):
        self._ler_executivo_da_tela()
        painel = mn.montar_executivo(self.par, self.real_exec)
        destino = AQUI / pb.RELATORIOS / mn.nome_do_executivo()
        try:
            mn.gravar_excel_executivo(painel, destino)
        except (OSError, PermissionError) as erro:
            messagebox.showerror("Gerador de Meta BAP",
                                 f"Nao deu para gravar o Excel.\n\n{erro}")
            return
        self._gravar_par()
        self.lbl_exec.configure(text=f"Painel gravado em {destino.name}.",
                                foreground=COR_OK)
        return destino





class MetasExecutivas(Meta):
    """O cadastro das metas executivas (meta, peso e despesa mes a mes).
    Abre pelo botao Metas executivas do Farol Indicadores Executivos
    (bap_meta.py --executivas) - saiu do BAP Analista em 06/10."""
    ABAS_VISIVEIS = ("exec",)
    TITULO = "Metas executivas"


def main():
    if "--executivas" in sys.argv[1:]:   # o botao do Farol Indicadores
        app = MetasExecutivas()          # Executivos (06/10)
        try:                             # as ajudas viram um (i), como
            import bap_visual as bv      # no BAP Analista  # noqa: PLC0415
            app.after(300, lambda: bv.compactar_ajudas(app))
        except Exception:                # noqa: BLE001
            pass
        app.mainloop()
        return
    Meta.ABA_INICIAL = pb.aba_pedida()
    app = Meta()
    app.mainloop()


if __name__ == "__main__":
    main()
