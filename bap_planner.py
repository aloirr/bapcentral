# -*- coding: utf-8 -*-
"""
Planner BAP - monte a rota do jeito que voce quiser.

    python bap_planner.py

O programa abre VAZIO. Dois caminhos para comecar:
    a) IMPORTAR ARQUIVO DO PLANNER (aba 1) - traz zonas, equipe, areas e
       clientes de um PLANNER que ja saiu daqui; ou
    b) montar do zero: importa a base de clientes (aba 3), cadastra as
       zonas (aba 3) e a equipe (aba 2).

AS SEIS ABAS
  1. RESUMO GERENCIAL   os numeros por zona, vendedor, supervisor e cidade.
                        Exporta e importa o PLANNER.
  2. CADASTRO DE VENDEDOR E SUPERVISOR
                        gerente, supervisor e vendedor. Para o vendedor,
                        a lista das zonas que sao dele.
  3. CADASTRO E ALTERACAO DE ZONA
                        importa a base de clientes e monta cada zona
                        escolhendo UF, cidade e bairro.
  4. ANALITICO ROTA     so consulta: os clientes de uma zona.
  5. EXPORTAR FORMATO PROTHEUS
                        a MESMA rota no .json de doze campos que o Protheus
                        le, com filtro por zona, vendedor, supervisor,
                        cidade ou UF.
  6. PARAMETROS         curva, churn, visitas por dia, sabado.

CODIGO DA ZONA
  Voce escolhe. O padrao sugerido e Z-<UF>-<NN> (Z-AM-01, Z-PA-03...).
  E por ele que a zona se liga ao vendedor e aos relatorios.

TUDO o que voce configurar fica no planner_config.json, ao lado deste
arquivo, e a pasta de trabalho e sempre a pasta onde este arquivo esta.

NOTAS DE DESEMPENHO (por que a tela nao trava)
  1. Os clientes sao varridos UMA vez, ao carregar a base, e viram um
     indice por area. Dai para frente a tela mexe em areas, nao nos
     milhares de clientes.
  2. Toda funcao que reconstroi uma Treeview levanta a trava _silencio,
     porque delete() e selection_set() disparam <<TreeviewSelect>>.
  3. A busca e adiada em 250 ms.
  4. Ler a base e gravar o Excel rodam fora da thread da tela.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import queue
import re
import shutil
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
import threading
import traceback
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))


def _morrer(explicacao, rastro, com_janela):
    texto = (f"O Planner BAP nao conseguiu iniciar.\n"
             f"Pasta:  {AQUI}\n"
             f"Python: {sys.executable}\n\n{explicacao}\n\n{rastro}")
    try:
        (AQUI / "erro_planner.txt").write_text(texto, encoding="utf-8")
    except OSError:
        pass
    print(texto)
    if com_janela:
        try:
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showerror("Planner BAP", texto[:1500])
            _r.destroy()
        except Exception:                          # noqa: BLE001
            pass
    sys.exit(1)


try:
    import tkinter as tk
    from tkinter import filedialog, font as tkfont, messagebox, ttk
except Exception:                                  # noqa: BLE001
    _morrer("Este Python foi instalado SEM o tkinter, que e a biblioteca da "
            "janela.\n\nReinstale o Python em python.org e, no instalador, "
            "deixe marcado 'tcl/tk and IDLE'.",
            traceback.format_exc(), com_janela=False)

try:
    import planner_nucleo as nu          # noqa: E402
    import pastas_bap as pb               # noqa: E402
    import base_cliente as bcli                  # noqa: E402
except Exception:                                  # noqa: BLE001
    _rastro = traceback.format_exc()
    if "openpyxl" in _rastro:
        _explicacao = ("Falta a biblioteca openpyxl, que le e grava Excel.\n\n"
                       "Abra o Prompt de Comando e rode:\n\n"
                       f'    "{sys.executable}" -m pip install openpyxl')
    elif any(m in _rastro for m in ("planner_nucleo", "zonas_padrao",
                                    "base_cliente")):
        _explicacao = ("Falta um arquivo do proprio programa. Os quatro tem "
                       "de estar na mesma pasta:\n"
                       "    bap_planner.py\n    planner_nucleo.py\n"
                       "    pastas_bap.py\n    zonas_padrao.py\n"
                       "    base_cliente.py")
    else:
        _explicacao = ("Erro ao carregar as bibliotecas. Rode o "
                       "VERIFICAR_REQUISITOS.bat e mande o "
                       "DIAGNOSTICO_BAP.txt.")
    _morrer(_explicacao, _rastro, com_janela=True)

ARQ_CONFIG = AQUI / "planner_config.json"
ARQ_PASTAS = AQUI / "planner_pastas.json"

# a pasta antiga se chamava roteiro_*: o nome mudou para planner_*, e a
# configuracao de quem ja usava e aproveitada em vez de recomecar do zero
for _velho, _novo in (("roteiro_config.json", ARQ_CONFIG),
                      ("roteiro_pastas.json", ARQ_PASTAS)):
    _de = AQUI / _velho
    if _de.exists() and not _novo.exists():
        try:
            _de.rename(_novo)
        except OSError:
            pass

# ---- paleta ---------------------------------------------------------------
# Cinza levemente azulado no fundo, branco no conteudo, um azul so como
# acento. Sem relevo, sem borda grossa: o que separa as coisas e o espaco.
COR_FUNDO = "#F3F4F2"        # o fundo da janela
COR_PAPEL = "#FFFFFF"        # o fundo dos paineis e das tabelas
COR_TITULO = "#2F7D32"       # texto de titulo
COR_TEXTO = "#1E2722"        # texto normal
COR_SUAVE = "#69736D"        # texto secundario
COR_ACENTO = "#4FA236"       # o verde BAP do programa
COR_ACENTO_ESC = "#3F8C2E"   # o mesmo verde, apertado
COR_LINHA = "#D5DAD4"        # divisorias
COR_ALERTA = "#B3261E"
COR_OK = "#1E7A46"
COR_ZEBRA = "#F7F8F6"
COR_AVISO = "#FFF4D6"        # zona sem vendedor
COR_ESTOURO = "#FCE8E8"      # nao cabe no mes
COR_SELECAO = "#DDEFD5"      # linha selecionada
COR_TOTAL = "#E4E7E3"
COR_CABECALHO = "#E4E7E3"    # o cabecalho cinza claro (no lugar do preto BAP)
COR_INATIVO = "#ECECEC"      # pessoa INATIVA: a cadeira esta vaga
COR_ESCONDIDA = "#F0F0F0"    # linha fora do filtro do gerencial

SEM_VENDEDOR = "(sem vendedor)"
TODAS = "(todas)"

# a linha TOTAL tem um iid proprio: e por ele que a ordenacao sabe que ela
# nao entra na fila e fica sempre no fim
LINHA_TOTAL = "__total__"
ROTULO_TOTAL = "TOTAL"

AVISO_RECALCULAR = ("PARA QUALQUER ALTERACAO TER VALIDADE, VA EM PARAMETROS "
                    "E CLIQUE EM RECALCULAR PLANNER.")
# (20/11) aviso ao gravar a ROTA com a regra nova do dtfinal.
AVISO_REMESSA_ANTERIOR = ("Antes de importar esta rota, peça à Máxima a "
                          "exclusão das remessas anteriores (uma vez só, no "
                          "primeiro envio com a regra nova).")
NOMES_DAS_ABAS = ("1. Resumo gerencial", "2. Vendedores e supervisores",
                  "3. Zonas", "4. Rota por cidade", "5. Analítico da rota",
                  "6. Base cliente", "7. Exportar Protheus", "8. Parâmetros")
# O PLANNER MES A MES: ao abrir, ele pergunta o mes (os testes desligam)
PERGUNTAR_MES = True

FAIXA_EM_DIA = "Alterações passam a valer depois de Recalcular Planner."
FAIXA_PENDENTE = "Há alterações pendentes: clique em Recalcular Planner."

# O DESENHO DA PASTA esta no pastas_bap.py. Aqui so os padroes de quem
# le e escreve: os Excel do dia a dia moram na RELATORIOS.
PASTAS_PADRAO = {
    "tabela_bap": f"{pb.RELATORIOS}/TABELA_BAP.xlsx",
    "base_cliente": f"{pb.RELATORIOS}/BASE_CLIENTE.xlsx",
    # (20/10, Alexandre) tudo o que o Planner exporta vai para
    # RELATORIOS\Roteirizacao
    "saida": pb.ROTEIRIZACAO,
}


def resolver(valor) -> Path:
    p = Path(str(valor or ".").strip())
    return p if p.is_absolute() else (AQUI / p)


def guardar(valor) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    p = Path(texto)
    if not p.is_absolute():
        return texto
    try:
        return str(p.resolve().relative_to(AQUI)) or "."
    except (ValueError, OSError):
        return str(p)


def dinheiro(v) -> str:
    try:
        return f"{float(v):,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    except (TypeError, ValueError):
        return "0,00"


# ==========================================================================
class Editor:
    """Combobox que aparece em cima da celula da Treeview."""

    def __init__(self):
        self.combo = None

    def abrir(self, arvore, item, coluna, valores, atual, ao_escolher):
        self.fechar()
        caixa = arvore.bbox(item, coluna)
        if not caixa:
            return
        x, y, largura, altura = caixa
        self.combo = ttk.Combobox(arvore, values=valores, state="readonly")
        self.combo.set(atual)
        self.combo.place(x=x, y=y, width=max(largura, 300),
                         height=max(altura, 22))
        self.combo.focus_set()
        self.combo.event_generate("<Down>")

        def confirmar(_=None):
            if self.combo is None:
                return
            escolha = self.combo.get()
            self.fechar()
            if escolha:
                ao_escolher(escolha)

        self.combo.bind("<<ComboboxSelected>>", confirmar)
        self.combo.bind("<Return>", confirmar)
        self.combo.bind("<Escape>", lambda _: self.fechar())

    def fechar(self):
        if self.combo is not None:
            combo, self.combo = self.combo, None
            combo.destroy()


def valor_de_ordem(texto):
    """
    Chave de ordenacao de uma celula. Numero (inclusive 1.234,56, 12,3%,
    -25 e vazio) ordena como numero; o resto ordena como texto sem acento.
    """
    s = str(texto or "").strip()
    if not s:
        return (0, float("-inf"), "")
    limpo = s.replace("R$", "").replace("%", "").replace(" ", "")
    if limpo and all(c in "0123456789.,-+" for c in limpo):
        n = limpo.replace(".", "").replace(",", ".") if "," in limpo else limpo
        try:
            return (0, float(n), "")
        except ValueError:
            pass
    return (1, 0.0, nu.norm(s))


def ordenavel(t, chaves):
    """
    Clicar no titulo ordena a tabela por aquela coluna; clicar de novo
    inverte. A seta no titulo mostra por onde esta ordenado.
    """
    estado = {"coluna": None, "invertido": False}
    titulos = {c: t.heading(c)["text"] for c in chaves}

    def ordenar(coluna):
        estado["invertido"] = (not estado["invertido"]
                               if estado["coluna"] == coluna else False)
        estado["coluna"] = coluna
        # a linha TOTAL nao entra na fila: ela mora no rodape
        linhas = [(valor_de_ordem(t.set(i, coluna)), i)
                  for i in t.get_children("") if i != LINHA_TOTAL]
        linhas.sort(key=lambda x: x[0], reverse=estado["invertido"])
        for posicao, (_, iid) in enumerate(linhas):
            t.move(iid, "", posicao)
            # zebra e so listra: refaz pela posicao nova, sem encostar
            # nas marcacoes que querem dizer alguma coisa (amarelo,
            # vermelho, inadimplente)
            tags = tuple(t.item(iid, "tags") or ())
            if set(tags) <= {"zebra"}:
                t.item(iid, tags=("zebra",) if posicao % 2 else ())
        if t.exists(LINHA_TOTAL):
            t.move(LINHA_TOTAL, "", "end")
        for c in chaves:
            seta = ""
            if c == coluna:
                seta = "  v" if estado["invertido"] else "  ^"
            t.heading(c, text=titulos[c] + seta)

    for c in chaves:
        t.heading(c, command=lambda cc=c: ordenar(cc))
    t._ordenar = ordenar
    t._ordem = estado
    t._titulos = titulos


def reaplicar_ordem(t):
    """Depois de redesenhar, refaz a ordenacao que estava na tela."""
    estado = getattr(t, "_ordem", None)
    if estado and estado.get("coluna"):
        invertido = estado["invertido"]
        estado["invertido"] = not invertido      # ordenar() inverte de novo
        t._ordenar(estado["coluna"])


def legenda_de_cores(pai, itens, titulo="O que as cores querem dizer"):
    """
    A tirinha que explica a cor das linhas. Cada item e (cor, texto): sai
    um quadradinho pintado com a explicacao ao lado. A mesma cor quer
    dizer coisas diferentes em cada aba, entao cada aba tem a sua.
    """
    faixa = ttk.Frame(pai)
    ttk.Label(faixa, text=titulo + ":", font=("Segoe UI", 8, "bold"),
              foreground=COR_TITULO).pack(side="left", padx=(0, 10))
    for cor, texto_ in itens:
        item = ttk.Frame(faixa)
        item.pack(side="left", padx=(0, 18))
        tk.Frame(item, background=cor, width=15, height=15,
                 highlightthickness=1,
                 highlightbackground="#C9CFC8").pack(side="left", pady=1)
        # wraplength: a legenda nao pode empurrar o painel da direita
        # para fora da tela. Texto comprido quebra em duas linhas.
        ttk.Label(item, text=texto_, font=("Segoe UI", 8),
                  foreground=COR_SUAVE, wraplength=300,
                  justify="left").pack(side="left", padx=(6, 0))
    return faixa


def geo_ponto(c) -> str:
    """De onde vem o ponto do cliente no mapa: endereco, bairro ou cidade."""
    try:
        return nu.geo.ponto_do_cliente(c)[2]
    except Exception:                                   # noqa: BLE001
        return ""


def tabela(pai, colunas, altura=None, selecao="browse", horizontal=True,
           rodape=False):
    """
    A tabela do programa. Com rodape=True nasce grudada nela uma segunda
    tabela de UMA linha so, colada embaixo: e a linha TOTAL. Ela fica
    presa ali - nao rola junto, nao entra na ordenacao e nao some quando
    a lista e grande. As duas dividem as mesmas colunas e a mesma rolagem
    horizontal, entao ficam sempre alinhadas.
    """
    quadro = ttk.Frame(pai)
    chaves = [c[0] for c in colunas]
    t = ttk.Treeview(quadro, columns=chaves, show="headings",
                     selectmode=selecao, **({"height": altura} if altura else {}))
    for chave, titulo, largura, ancora, cresce in colunas:
        t.heading(chave, text=titulo)
        t.column(chave, width=largura, anchor=ancora, stretch=cresce)
    ordenavel(t, chaves)
    sv = ttk.Scrollbar(quadro, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sv.set)
    t.grid(row=0, column=0, sticky="nsew")
    sv.grid(row=0, column=1, sticky="ns")

    pe = None
    if rodape:
        # O rodape e uma tabela de uma linha so. Ele NAO calcula largura
        # nenhuma: toda coluna dele nasce com stretch=False e copia, a cada
        # instante, a largura da coluna de cima. Duas coisas garantem isso:
        #   1. os eventos (redimensionar, arrastar o titulo, trocar de aba)
        #      pedem a copia depois que o Tk terminou de distribuir as
        #      colunas (after_idle);
        #   2. um vigia de 200 em 200 ms confere e corrige. Foi ele que
        #      resolveu o MAXIMIZAR no Windows: la a janela cresce numa
        #      ordem de eventos em que o after_idle rodava cedo demais e o
        #      rodape ficava com a largura antiga.
        pe = ttk.Treeview(quadro, columns=chaves, show="", selectmode="none",
                          height=1, xscrollcommand=lambda *a: None)
        for chave, _, largura, ancora, _cresce in colunas:
            pe.column(chave, width=largura, anchor=ancora, stretch=False)
        pe.grid(row=1, column=0, sticky="we")
        pe.tag_configure("total", background=COR_TOTAL, foreground=COR_TITULO,
                         font=("Segoe UI", 9, "bold"))

        def _larguras(_=None):
            try:
                mexeu = False
                for c in chaves:
                    largura = t.column(c, "width")
                    if pe.column(c, "width") != largura:
                        pe.column(c, width=largura)
                        mexeu = True
                inicio = t.xview()[0]
                if mexeu or abs(pe.xview()[0] - inicio) > 1e-6:
                    pe.xview_moveto(inicio)
            except tk.TclError:
                pass                      # a tabela ja foi destruida

        def _sincronizar(_=None):
            # o Tk so redistribui as colunas depois do evento: espera a
            # fila esvaziar antes de copiar as larguras
            try:
                pe.after_idle(_larguras)
            except tk.TclError:
                pass

        def _vigiar():
            if not pe.winfo_exists():
                return
            _larguras()
            pe.after(200, _vigiar)

        t.bind("<ButtonRelease-1>", _sincronizar, add="+")
        t.bind("<Configure>", _sincronizar, add="+")
        t.bind("<Map>", _sincronizar, add="+")
        pe.bind("<Configure>", _sincronizar, add="+")
        pe.after(200, _vigiar)
        pe._sincronizar = _sincronizar
        pe._alinhar_agora = _larguras
        t._rodape = pe

    if horizontal:
        def _rolar(*a):
            t.xview(*a)
            if pe is not None:
                pe.xview_moveto(t.xview()[0])
        sh = ttk.Scrollbar(quadro, orient="horizontal", command=_rolar)

        def _mostrar(a, b):
            sh.set(a, b)
            if pe is not None:
                pe.xview_moveto(float(a))
        t.configure(xscrollcommand=_mostrar)
        sh.grid(row=2, column=0, sticky="we")
    quadro.rowconfigure(0, weight=1)
    quadro.columnconfigure(0, weight=1)
    t.tag_configure("zebra", background=COR_ZEBRA)
    t.tag_configure("aviso", background=COR_AVISO)
    t.tag_configure("inativo", background=COR_INATIVO, foreground=COR_SUAVE)
    t.tag_configure("estourou", background=COR_ESTOURO)
    # a zona virtual do estado - onde o cliente de bairro sem dono espera
    t.tag_configure("semzona", background="#FBE3E3", foreground=COR_ALERTA)
    t.tag_configure("total", background=COR_TOTAL, foreground=COR_TITULO,
                    font=("Segoe UI", 9, "bold"))
    return quadro, t


def escrever_total(t, valores):
    """Poe (ou troca) a linha TOTAL presa no rodape da tabela."""
    pe = getattr(t, "_rodape", None)
    if pe is None:
        return
    pe.delete(*pe.get_children())
    if valores:
        pe.insert("", "end", iid=LINHA_TOTAL, tags=("total",), values=valores)
    pe._sincronizar()


def lista_multipla(pai, titulo, altura=14, largura=26):
    """Listbox de selecao multipla com 'marcar todos' e contador."""
    quadro = ttk.Frame(pai)
    topo = ttk.Frame(quadro)
    topo.pack(fill="x")
    ttk.Label(topo, text=titulo, font=("Segoe UI", 9, "bold")).pack(side="left")
    corpo = ttk.Frame(quadro)
    corpo.pack(fill="both", expand=True, pady=(2, 0))
    lb = tk.Listbox(corpo, selectmode="extended", exportselection=False,
                    height=altura, width=largura, font=("Segoe UI", 9),
                    activestyle="none", relief="flat", borderwidth=0,
                    highlightthickness=1, highlightbackground=COR_LINHA,
                    highlightcolor=COR_ACENTO, background=COR_PAPEL,
                    foreground=COR_TEXTO, selectbackground=COR_ACENTO,
                    selectforeground="white")
    sv = ttk.Scrollbar(corpo, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=sv.set)
    lb.pack(side="left", fill="both", expand=True)
    sv.pack(side="left", fill="y")
    rodape = ttk.Frame(quadro)
    rodape.pack(fill="x", pady=(2, 0))
    contador = ttk.Label(rodape, text="", style="Sub.TLabel")
    contador.pack(side="right")
    botoes = ttk.Frame(rodape)
    botoes.pack(side="left")
    return quadro, lb, botoes, contador


# ==========================================================================
def _sem_email(cfg) -> str:
    """O cadastro sem os e-mails (para saber se so o e-mail mudou)."""
    return json.dumps(
        [{k: v for k, v in p.items() if k not in ("email", "meses_de_casa")}
         for p in cfg.get("pessoas") or []]
        + [cfg.get("zonas"), cfg.get("atendimento")], sort_keys=True,
        ensure_ascii=False, default=str)


class App(pb.base_da_janela()):
    def __init__(self):
        super().__init__()
        self.title("Planner BAP")
        self.geometry("1450x900")
        self.minsize(1150, 720)
        self.configure(bg=COR_FUNDO)

        # a pasta se arruma sozinha ao abrir: RELATORIOS com os Excel do dia
        # a dia e BACKUP_RELATORIOS com as copias. Nada e apagado, e quando
        # ja esta tudo no lugar isto nao faz nada.
        self._arrumacao = []
        try:
            self._arrumacao = pb.arrumar(AQUI)
        except OSError:
            pass

        self.cfg = nu.carregar_config(self._preparar_meses())
        self.pastas = self._ler_pastas()
        self._gravar_pastas()
        self.clientes: list[dict] = []
        self.areas: list[dict] = []          # indice por UF/cidade/bairro
        self.contagem_zona = Counter()
        self.resumo = None
        self.lbl_calendario = None           # so existe depois da aba 6
        self._faixas = []                    # as faixas de aviso das abas
        self._rota_an = None                 # a agenda do mes, no analitico
        self._pendente = False               # mudou algo e nao recalculou
        self.editor = Editor()
        self._editando = None                # pessoa em edicao
        self._zona_editando = None           # zona em edicao
        self._rota_sem = {}                  # (a SEMANA DA ROTA saiu)
        self._sel_sem = None
        self._historico = ""

        # O FILTRO DO RESUMO GERENCIAL, um por recorte. "texto" e o que
        # esta escrito na caixa; "escondidas" sao as linhas que voce tirou
        # a mao. Fica gravado no config: fechar o programa nao desfaz.
        self._ler_filtros_do_cfg()

        self._silencio = False
        self._tarefa_busca = None
        self._ger_sujo = True
        self._ocupado = False
        self._fila = queue.Queue()

        self._estilo()
        self._montar()
        self.after(120, self._bombear_fila)
        self.after(200, self._abertura)

    def _ler_filtros_do_cfg(self):
        guardado = self.cfg.get("filtro_resumo") or {}
        self._filtro_texto = {chave: str(((guardado.get(chave) or {})
                                          .get("texto") or ""))
                              for chave, _, _ in self.VISOES}
        self._escondidas = {chave: set((guardado.get(chave) or {})
                                       .get("escondidas") or ())
                            for chave, _, _ in self.VISOES}
        # "campos" sao os filtros de uma visao pela outra (as cidades do
        # PA, as zonas do Denylson): {recorte: {campo: valor}}
        self._filtro_campo = {
            chave: {c: str(v) for c, v in
                    ((guardado.get(chave) or {}).get("campos") or {}).items()}
            for chave, _, _ in self.VISOES}

    # ------------------------------------------------------ o mes do planner
    # Cada mes tem a configuracao dele em PLANNER_MESES (equipe, zonas, quem
    # responde a quem). O planner_config.json da pasta e a copia do mes
    # mais adiante - e ele que o BAP Tools e os farois leem.
    @staticmethod
    def _preparar_meses() -> Path:
        """Na primeira vez, o planner_config.json vira o arquivo do mes
        dele. Na virada do mes, a copia da pasta passa a ser a do mes novo.
        Devolve o arquivo do mes que abre (o vigente)."""
        meses = pb.meses_do_planner(AQUI)
        mes = ""
        if ARQ_CONFIG.exists():
            try:
                mes = nu.carregar_config(ARQ_CONFIG).get("mes") or ""
            except (OSError, ValueError):
                mes = ""
            if mes and mes not in meses:
                try:
                    destino = pb.config_do_mes(AQUI, mes)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ARQ_CONFIG, destino)
                    meses = pb.meses_do_planner(AQUI)
                except OSError:
                    pass
        if not meses:
            return ARQ_CONFIG
        vigente = pb.mes_vigente(AQUI)
        arq = pb.config_do_mes(AQUI, vigente)
        if mes != vigente:                 # virou o mes: a da pasta segue
            try:
                shutil.copy2(arq, ARQ_CONFIG)
            except OSError:
                pass
        return arq

    def _rotulo_mes(self) -> str:
        return nu.rotulo_do_mes(self.cfg.get("mes", ""))

    def _atualizar_botoes_mes(self):
        mes = self.cfg.get("mes", "")
        if getattr(self, "bt_mes", None) is not None and mes:
            self.bt_mes.configure(text=f"Mês: {self._rotulo_mes()}  ▾")
            self.bt_duplicar.configure(
                text=f"Duplicar para {nu.rotulo_do_mes(nu.mes_seguinte(mes))}")

    def perguntar_mes(self):
        """A janelinha do comeco: qual mes do Planner abrir."""
        if getattr(self, "_janela_mes", None) is not None:
            try:
                self._janela_mes.lift()
                return
            except tk.TclError:
                pass
        hoje = dt.date.today()
        atual = self.cfg.get("mes") or f"{hoje.year:04d}-{hoje.month:02d}"
        existentes = pb.meses_do_planner(AQUI)
        opcoes = sorted(set(existentes) | {nu.mes_seguinte(atual, n)
                                           for n in range(-3, 2)})
        win = tk.Toplevel(self)
        self._janela_mes = win
        win.title("Planner BAP")
        win.configure(background=COR_PAPEL)
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        corpo = tk.Frame(win, background=COR_PAPEL, padx=26, pady=20)
        corpo.pack(fill="both", expand=True)
        tk.Label(corpo, text="Qual mês do Planner?", background=COR_PAPEL,
                 foreground=COR_TITULO, font=(self.FONTE, 13, "bold")
                 ).pack(anchor="w")
        rotulos = [nu.rotulo_do_mes(m) + ("" if m in existentes else
                                          "   (novo)") for m in opcoes]
        var = tk.StringVar(value=rotulos[opcoes.index(atual)]
                           if atual in opcoes else rotulos[-1])
        cb = ttk.Combobox(corpo, textvariable=var, values=rotulos, width=22,
                          state="readonly", font=(self.FONTE, 11))
        cb.pack(anchor="w", pady=(10, 14))
        botoes = tk.Frame(corpo, background=COR_PAPEL)
        botoes.pack(fill="x")

        def fechar():
            self._janela_mes = None
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()

        def abrir():
            mes = opcoes[rotulos.index(var.get())]
            fechar()
            if mes != self.cfg.get("mes"):
                self.abrir_mes(mes)

        ttk.Button(botoes, text="Abrir", style="Big.TButton",
                   command=abrir).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=fechar).pack(
            side="right", padx=8)
        win.protocol("WM_DELETE_WINDOW", fechar)
        win.bind("<Return>", lambda _: abrir())
        win.update_idletasks()
        try:
            top = self.winfo_toplevel()
            x = top.winfo_rootx() + (top.winfo_width() - win.winfo_width()) // 2
            y = top.winfo_rooty() + 140
            win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
            win.grab_set()
        except tk.TclError:
            pass

    def abrir_mes(self, mes: str) -> bool:
        """Troca o Planner para outro mes. O mes sem arquivo nasce como
        copia do que esta aberto (pergunta antes)."""
        arq = pb.config_do_mes(AQUI, mes)
        if not arq.exists():
            if not messagebox.askyesno(
                    "Planner BAP",
                    f"{nu.rotulo_do_mes(mes)} ainda não tem Planner.\n\n"
                    f"Criar copiando o de {self._rotulo_mes()} (zonas, "
                    f"equipe e parâmetros)?"):
                return False
            nu.gravar_config(nu.duplicar_config(self.cfg, mes), arq)
            if mes == pb.mes_vigente(AQUI):
                nu.gravar_config(nu.carregar_config(arq), ARQ_CONFIG)
        self.cfg = nu.carregar_config(arq)
        self._ler_filtros_do_cfg()
        self._editando = None
        self._zona_editando = None
        self._pendente = False
        if getattr(self, "var_mes", None) is not None:
            self.var_ano.set(self.cfg["mes"][:4])
            self.var_mes.set(nu.MESES_PT[int(self.cfg["mes"][5:7])])
        if self.clientes:
            nu.aplicar_parametros(self.cfg, self.clientes)
            self._indexar()
            nu.sincronizar_areas(self.cfg, self.clientes)
        try:
            self.limpar_pessoa()
        except (AttributeError, tk.TclError):
            pass
        self._atualizar_botoes_mes()
        self._pintar_faixas()
        self.atualizar_tudo()
        self.log(f"Planner de {self._rotulo_mes()} aberto.")
        self.aviso(f"Planner de {self._rotulo_mes()}.", COR_OK)
        return True

    def duplicar_para_o_seguinte(self):
        """Copia o Planner aberto (zonas, equipe, parametros) para o mes
        seguinte. Nunca grava por cima sem perguntar."""
        destino = nu.mes_seguinte(self.cfg["mes"])
        rot = nu.rotulo_do_mes(destino)
        arq = pb.config_do_mes(AQUI, destino)
        if arq.exists():
            if not messagebox.askyesno(
                    "Planner BAP",
                    f"{rot} já tem Planner.\n\nSubstituir pelo de "
                    f"{self._rotulo_mes()}? (o de {rot} vai para o backup)"):
                return
            pb.guardar_anterior(arq, AQUI, copiar=True)
        elif not messagebox.askyesno(
                "Planner BAP",
                f"Duplicar o Planner de {self._rotulo_mes()} para {rot}?\n\n"
                f"Vão juntos: zonas, equipe, quem responde a quem e os "
                f"parâmetros."):
            return
        nu.gravar_config(nu.duplicar_config(self.cfg, destino), arq)
        if destino == pb.mes_vigente(AQUI):
            nu.gravar_config(nu.carregar_config(arq), ARQ_CONFIG)
        self.log(f"Planner de {self._rotulo_mes()} duplicado para {rot}.")
        if messagebox.askyesno("Planner BAP", f"Planner de {rot} criado.\n\n"
                                              f"Abrir {rot} agora?"):
            self.abrir_mes(destino)

    # ---------------------------------------------------------------- infra
    def _estilo(self):
        """
        O visual do programa. Tudo plano: nada de relevo, nada de borda
        grossa. O que separa as coisas e o espaco em branco e uma linha
        fina; a cor forte fica so no que se clica.
        """
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        familia = "Segoe UI"
        for candidata in ("Segoe UI", "Calibri", "DejaVu Sans", "Arial"):
            try:
                if candidata in tkfont.families(self):
                    familia = candidata
                    break
            except Exception:                          # noqa: BLE001
                break
        self.FONTE = familia

        # o conteudo mora dentro das abas, que sao brancas: o branco e o
        # fundo padrao, e o cinza fica so na moldura da janela
        s.configure(".", background=COR_PAPEL, foreground=COR_TEXTO,
                    font=(familia, 9), borderwidth=0, relief="flat",
                    focuscolor=COR_ACENTO)
        s.configure("TFrame", background=COR_PAPEL)
        s.configure("TLabel", background=COR_PAPEL, foreground=COR_TEXTO)
        s.configure("Papel.TFrame", background=COR_PAPEL)
        s.configure("Papel.TLabel", background=COR_PAPEL, foreground=COR_TEXTO)
        s.configure("Fundo.TFrame", background=COR_FUNDO)

        # ---- abas --------------------------------------------------------
        s.configure("TNotebook", background=COR_FUNDO, borderwidth=0,
                    tabmargins=(2, 6, 2, 0))
        s.configure("TNotebook.Tab", padding=(16, 8), borderwidth=0,
                    background=COR_FUNDO, foreground=COR_SUAVE,
                    font=(familia, 9))
        s.map("TNotebook.Tab",
              background=[("selected", COR_PAPEL), ("active", "#E9ECE8")],
              foreground=[("selected", COR_TEXTO), ("active", COR_TEXTO)],
              expand=[("selected", (0, 0, 0, 0))])

        # ---- tabelas -----------------------------------------------------
        try:                    # a altura pela letra (escala do Windows)
            from tkinter import font as _tkf             # noqa: PLC0415
            _lin = _tkf.Font(font=(familia, 9)).metrics("linespace")
        except Exception:                               # noqa: BLE001
            _lin = 16
        s.configure("Treeview", rowheight=max(26, _lin + 10),
                    font=(familia, 9),
                    background=COR_PAPEL, fieldbackground=COR_PAPEL,
                    foreground=COR_TEXTO, borderwidth=0, relief="flat")
        # as caixas da SEMANA DA ROTA sao quatro (ou cinco) numa coluna
        # so: com a linha de 26px elas nao caberiam na mesma altura das
        # listas de UF, CIDADE e BAIRRO
        s.configure("Semana.Treeview", rowheight=max(21, _lin + 5),
                    font=(familia, 9),
                    background=COR_PAPEL, fieldbackground=COR_PAPEL,
                    foreground=COR_TEXTO, borderwidth=0, relief="flat")
        s.map("Semana.Treeview",
              background=[("selected", COR_SELECAO)],
              foreground=[("selected", COR_TITULO)])
        s.layout("Semana.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Treeview.Heading", font=(familia, 8, "bold"),
                    background="#EEF0ED", foreground=COR_SUAVE,
                    padding=(6, 7), relief="flat", borderwidth=0)
        s.map("Treeview.Heading",
              background=[("active", "#DFE3DE")],
              relief=[("active", "flat"), ("pressed", "flat")])
        s.map("Treeview",
              background=[("selected", COR_SELECAO)],
              foreground=[("selected", COR_TITULO)])
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        # ---- botoes ------------------------------------------------------
        s.configure("TButton", font=(familia, 9), padding=(12, 7),
                    background="#E9ECE8", foreground=COR_TITULO,
                    borderwidth=0, relief="flat")
        s.map("TButton",
              background=[("pressed", "#D5DAD4"), ("active", "#DFE3DE"),
                          ("disabled", "#F0F1EF")],
              foreground=[("disabled", "#A7B0AA")])
        s.configure("Big.TButton", font=(familia, 9, "bold"), padding=(18, 9),
                    background=COR_ACENTO, foreground="white")
        s.map("Big.TButton",
              background=[("pressed", "#2B6B22"), ("active", COR_ACENTO_ESC),
                          ("disabled", "#B9D9AE")])

        # ---- campos ------------------------------------------------------
        for classe in ("TEntry", "TCombobox"):
            s.configure(classe, fieldbackground=COR_PAPEL,
                        background=COR_PAPEL, foreground=COR_TEXTO,
                        bordercolor=COR_LINHA, lightcolor=COR_LINHA,
                        darkcolor=COR_LINHA, borderwidth=1, relief="flat",
                        arrowcolor=COR_ACENTO, padding=5)
            s.map(classe,
                  bordercolor=[("focus", COR_ACENTO), ("hover", "#C9CFC8")],
                  lightcolor=[("focus", COR_ACENTO)],
                  darkcolor=[("focus", COR_ACENTO)])
        self.option_add("*TCombobox*Listbox.background", COR_PAPEL)
        self.option_add("*TCombobox*Listbox.foreground", COR_TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", COR_ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", "white")
        self.option_add("*TCombobox*Listbox.font", (familia, 9))

        # ---- moldura de secao -------------------------------------------
        s.configure("TLabelframe", background=COR_PAPEL, borderwidth=1,
                    relief="solid", bordercolor=COR_LINHA,
                    lightcolor=COR_PAPEL, darkcolor=COR_PAPEL)
        s.configure("TLabelframe.Label", background=COR_PAPEL,
                    foreground=COR_ACENTO, font=(familia, 8, "bold"))

        # ---- barras de rolagem ------------------------------------------
        s.configure("TScrollbar", background="#DADFD9", troughcolor=COR_FUNDO,
                    bordercolor=COR_FUNDO, arrowcolor=COR_SUAVE,
                    borderwidth=0, relief="flat")
        s.map("TScrollbar", background=[("active", "#C5CBC4")])

        # ---- textos ------------------------------------------------------
        s.configure("Titulo.TLabel", font=(familia, 15), foreground=COR_TITULO,
                    background=COR_PAPEL)
        s.configure("Secao.TLabel", font=(familia, 11, "bold"),
                    foreground=COR_TITULO, background=COR_PAPEL)
        s.configure("Sub.TLabel", font=(familia, 9), foreground=COR_SUAVE,
                    background=COR_PAPEL)
        s.configure("Cod.TLabel", font=(familia, 11, "bold"),
                    foreground=COR_TITULO, background=COR_PAPEL)
        s.configure("Aviso.TLabel", font=(familia, 9), foreground=COR_ALERTA,
                    background=COR_PAPEL)
        s.configure("TSeparator", background=COR_LINHA)

    def _faixa_recalcular(self, pai):
        """
        A faixa de aviso que aparece no alto de todas as abas. Ela acende
        em vermelho assim que alguma coisa muda e so apaga quando o
        RECALCULAR PLANNER roda.
        """
        faixa = tk.Frame(pai, background="#F7F8F6", highlightthickness=1,
                         highlightbackground=COR_LINHA)
        faixa.pack(fill="x", pady=(0, 10))
        etiqueta = tk.Label(faixa, text=FAIXA_EM_DIA, background="#F7F8F6",
                            foreground=COR_SUAVE, font=(self.FONTE, 9),
                            anchor="w")
        etiqueta._bap_ajuda = True        # texto curto e vivo: nao vira dica
        etiqueta.pack(side="left", fill="x", expand=True, padx=12, pady=6)
        botao = ttk.Button(faixa, text="Recalcular Planner",
                           command=lambda: self.recalcular_planner(
                               agenda=True))
        botao.pack(side="right", padx=8, pady=4)
        self._faixas.append((faixa, etiqueta))
        return faixa

    def _pintar_faixas(self):
        """Vermelho quando ha mudanca esperando; amarelo quando esta em dia."""
        pendente = getattr(self, "_pendente", False)
        fundo = "#FCE8E8" if pendente else "#F7F8F6"
        borda = "#E3A9A9" if pendente else COR_LINHA
        cor = COR_ALERTA if pendente else COR_SUAVE
        texto = FAIXA_PENDENTE if pendente else FAIXA_EM_DIA
        for faixa, etiqueta in getattr(self, "_faixas", []):
            try:
                faixa.configure(background=fundo, highlightbackground=borda)
                etiqueta.configure(background=fundo, foreground=cor, text=texto)
            except tk.TclError:
                pass

    def marcar_pendente(self):
        self._pendente = True
        self._pintar_faixas()

    def _ler_pastas(self) -> dict:
        """
        A BASE_CLIENTE TEM UM LUGAR SO: RELATORIOS\\BASE_CLIENTE.xlsx, ao
        lado deste programa. Nao se escolhe mais outro arquivo.

        E o arquivo que a Automacao BAP reescreve no fim de cada rodada,
        entao apontar para outro lugar so servia para o Planner trabalhar
        com uma base velha sem ninguem perceber. Um planner_pastas.json
        de antes, com outro caminho gravado, e ignorado na leitura - o
        que fica escolhivel e so a pasta de SAIDA.
        """
        padrao = dict(PASTAS_PADRAO)
        if ARQ_PASTAS.exists():
            try:
                with open(ARQ_PASTAS, encoding="utf-8") as f:
                    guardado = json.load(f)
            except (OSError, json.JSONDecodeError):
                guardado = {}
            valor = str(guardado.get("saida") or "").strip()
            # (20/10) a saida antiga (a RELATORIOS) vira a Roteirizacao
            if valor and valor.replace("\\", "/").strip("/").upper() != \
                    pb.RELATORIOS.upper():
                padrao["saida"] = guardar(valor)
        saida = resolver(padrao["saida"])
        if saida.resolve() in (AQUI.resolve(),
                               (AQUI / pb.RELATORIOS).resolve()):
            padrao["saida"] = pb.ROTEIRIZACAO
        return padrao

    def caminho(self, chave) -> Path:
        p_ = resolver(self.pastas.get(chave) or PASTAS_PADRAO[chave])
        if chave == "saida":            # (20/10) a Roteirizacao nasce aqui
            try:
                p_.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        return p_

    def _gravar_pastas(self):
        with open(ARQ_PASTAS, "w", encoding="utf-8") as f:
            json.dump(self.pastas, f, ensure_ascii=False, indent=2)

    def salvar(self):
        mes = self.cfg.get("mes") or ""
        if mes:
            nu.gravar_config(self.cfg, pb.config_do_mes(AQUI, mes))
        # a da pasta e sempre a do mes vigente (o de hoje)
        if not mes or mes == pb.mes_vigente(AQUI):
            nu.gravar_config(self.cfg, ARQ_CONFIG)

    def aviso(self, texto, cor="#333333"):
        self.rodape.configure(text=texto, foreground=cor)
        self.rodape.update_idletasks()

    def log(self, texto):
        self._historico += texto + "\n"
        if getattr(self, "txt_log", None) is not None:
            try:
                self.txt_log.insert("end", texto + "\n")
                self.txt_log.see("end")
            except tk.TclError:
                self.txt_log = None

    def _tarefa(self, funcao, ao_terminar, mensagem):
        if self._ocupado:
            self.aviso("Ja tem uma tarefa rodando, aguarde.", COR_ALERTA)
            return
        self._ocupado = True
        self.configure(cursor="watch")
        self.aviso(mensagem)

        def correr():
            try:
                self._fila.put((ao_terminar, funcao(), None))
            except Exception as erro:                  # noqa: BLE001
                self._fila.put((ao_terminar, None,
                                (erro, traceback.format_exc())))
        threading.Thread(target=correr, daemon=True).start()

    def _bombear_fila(self):
        try:
            while True:
                ao_terminar, resultado, erro = self._fila.get_nowait()
                self._ocupado = False
                self.configure(cursor="")
                ao_terminar(resultado, erro)
        except queue.Empty:
            pass
        self.after(120, self._bombear_fila)

    # --------------------------------------------------------------- layout
    def _montar(self):
        # ---- cabecalho: faixa azul com o nome e o resumo do estado -------
        # (07/10) sem altura fixa: com o Windows em 125%/150% os 54 px
        # cortavam o botao do mes e o titulo - a faixa cresce com a fonte
        topo = tk.Frame(self, background=COR_CABECALHO)
        topo.pack(fill="x")
        tk.Frame(self, background="#62BB47", height=3).pack(fill="x")
        dentro = tk.Frame(topo, background=COR_CABECALHO)
        dentro.pack(fill="both", expand=True, padx=20)
        tk.Label(dentro, text="Planner BAP", background=COR_CABECALHO,
                 foreground=COR_TEXTO, font=(self.FONTE, 14, "bold")).pack(
                     side="left", pady=12)
        self.lbl_topo = tk.Label(dentro, text="", background=COR_CABECALHO,
                                 foreground=COR_SUAVE, font=(self.FONTE, 9))
        self.lbl_topo.pack(side="left", padx=18, pady=14)
        self.bt_duplicar = ttk.Button(dentro, text="Duplicar",
                                      command=self.duplicar_para_o_seguinte)
        self.bt_duplicar.pack(side="right", pady=10)
        self.bt_mes = ttk.Button(dentro, text="Mês", style="Big.TButton",
                                 command=self.perguntar_mes)
        self.bt_mes.pack(side="right", padx=8, pady=10)
        self._atualizar_botoes_mes()

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=14, pady=(8, 4))
        self.aba_resumo = ttk.Frame(self.abas, padding=14, style="Papel.TFrame")
        self.aba_pessoas = ttk.Frame(self.abas, padding=16, style="Papel.TFrame")
        self.aba_zonas = ttk.Frame(self.abas, padding=14, style="Papel.TFrame")
        self.aba_rota = ttk.Frame(self.abas, padding=14, style="Papel.TFrame")
        self.aba_analitico = ttk.Frame(self.abas, padding=14, style="Papel.TFrame")
        self.aba_base = ttk.Frame(self.abas, padding=14, style="Papel.TFrame")
        self.aba_protheus = ttk.Frame(self.abas, padding=14,
                                      style="Papel.TFrame")
        self.aba_parametros = ttk.Frame(self.abas, padding=(16, 10, 16, 10),
                                        style="Papel.TFrame")
        for aba, nome in zip((self.aba_resumo, self.aba_pessoas, self.aba_zonas,
                              self.aba_rota, self.aba_analitico,
                              self.aba_base, self.aba_protheus,
                              self.aba_parametros), NOMES_DAS_ABAS):
            self.abas.add(aba, text=nome)

        rodape = tk.Frame(self, background=COR_FUNDO, height=34)
        rodape.pack(fill="x", side="bottom")
        rodape.pack_propagate(False)
        self.rodape = tk.Label(rodape, text="", background=COR_FUNDO,
                               foreground=COR_SUAVE, font=(self.FONTE, 9),
                               anchor="w")
        self.rodape.pack(fill="both", expand=True, padx=20, pady=(6, 8))

        self._montar_resumo()
        self._montar_pessoas()
        self._montar_zonas()
        self._montar_rota_cidade()
        self._montar_analitico()
        self._montar_base_cliente()
        self._montar_protheus()
        self._montar_parametros()
        # no BAP Analista os dois .json do Protheus (roteirizacao e base de
        # clientes) saem do Farol Roteirizacao: a aba 6 nao aparece la
        if pb.MODO_EMBUTIDO:
            self.abas.hide(self.aba_protheus)
            self.abas.tab(self.aba_parametros, text="7. Parâmetros")
        self.abas.bind("<<NotebookTabChanged>>", self._trocou_aba)

    def _trocou_aba(self, _=None):
        try:
            aba = self.abas.nametowidget(self.abas.select())
        except (tk.TclError, KeyError):
            return
        self.editor.fechar()
        if aba is self.aba_resumo and self._ger_sujo:
            self.atualizar_resumo()
        elif aba is self.aba_pessoas:
            self.desenhar_pessoas()
        elif aba is self.aba_zonas:
            self.desenhar_zonas()
        elif aba is self.aba_rota:
            self.recarregar_rota_cidade()
        elif aba is self.aba_analitico:
            self.recarregar_zonas_analitico()
        elif aba is self.aba_base:
            self.recarregar_base_cliente()
        elif aba is self.aba_protheus:
            self.recarregar_protheus()

    def _abertura(self):
        """Abre vazio; so carrega o que ja estiver configurado."""
        try:
            self.log(f"Pasta de trabalho: {AQUI}")
            if self._arrumacao:
                self.log(f"Pasta arrumada: {len(self._arrumacao)} arquivo(s) "
                         f"foram para o lugar novo.")
                for _linha in self._arrumacao[:12]:
                    self.log("   " + _linha)
                if len(self._arrumacao) > 12:
                    self.log(f"   ... e mais {len(self._arrumacao) - 12}.")
            if not ARQ_CONFIG.exists():
                # primeira vez nesta pasta: deixa o arquivo criado ja com os
                # parametros de fabrica, para o usuario poder edita-lo/ve-lo
                self.salvar()
                self.log(f"Configuracao nova criada em {ARQ_CONFIG.name}.")
            base = self.caminho("base_cliente")
            if self.cfg.get("zonas") or self.cfg.get("pessoas"):
                self.log(f"Configuracao encontrada: {len(self.cfg['zonas'])} zona(s), "
                         f"{len(self.cfg['pessoas'])} pessoa(s).")
            else:
                self.log("Nenhuma zona nem equipe cadastrada ainda.")

            _, etiqueta = self._idade_da_base()
            self.log(etiqueta)
            if base.exists():
                self.carregar_base(base)
            else:
                self.log(f"Nao achei a base de clientes em {base}.\n"
                         f"Ela e feita pela Automacao BAP no fim de cada rodada. "
                         f"Rode a Automacao, ou use 'IMPORTAR ARQUIVO DO PLANNER' "
                         f"na aba 1 para trabalhar com um PLANNER ja pronto.")
                self.atualizar_tudo()
        finally:
            # o --aba do BAP Central: so depois de tudo carregado,
            # senao a propria abertura troca de aba por cima
            self._ir_para_aba_inicial()
            if PERGUNTAR_MES:
                self.after(300, self.perguntar_mes)

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

    def _idade_da_base(self):
        """
        So DIZ como esta a BASE_CLIENTE - nao refaz mais nada.

        Quem a refaz e a Automacao BAP, no fim de cada rodada. Este
        programa le o arquivo que esta em RELATORIOS e avisa quando ele
        esta atrasado ou fora de formato, em vez de sair gerando por
        conta propria (o que, com dois geradores, ja deu base diferente
        em maquina diferente).

        Devolve (False, etiqueta) - o primeiro valor ficou para nao
        quebrar quem chama, e hoje e sempre False.
        """
        base = self.caminho("base_cliente")
        tabela = self.caminho("tabela_bap")
        if not base.exists():
            return False, (f"Nao existe BASE_CLIENTE em {pb.RELATORIOS}. "
                           f"Rode a Automacao BAP para gerar.")
        quando = dt.datetime.fromtimestamp(base.stat().st_mtime)
        # A DATA NAO PEGA TUDO: a base pode estar "em dia" com a TABELA_BAP
        # e mesmo assim ter sido feita por uma VERSAO ANTIGA do programa,
        # sem as colunas de hoje. Ai o numero nao vem errado - vem VAZIO,
        # e atravessa calado ate a tela da meta. Entao aqui se olha
        # tambem O CABECALHO dela.
        try:
            faltam = bcli.colunas_faltando(base)
        except Exception:                                     # noqa: BLE001
            faltam = []
        if faltam:
            return False, (f"ATENCAO: a BASE_CLIENTE e de uma versao ANTIGA "
                           f"do programa - faltam as colunas "
                           f"{', '.join(faltam[:4])}"
                           + (f" e mais {len(faltam) - 4}" if len(faltam) > 4
                              else "")
                           + ". Rode a Automacao BAP para refazer.")
        if tabela.exists() and tabela.stat().st_mtime > base.stat().st_mtime:
            return False, (f"ATENCAO: a TABELA_BAP esta mais nova que a "
                           f"BASE_CLIENTE ({quando:%d/%m/%Y %H:%M}). Rode a "
                           f"Automacao BAP para a base pegar o movimento de "
                           f"hoje.")
        return False, f"BASE_CLIENTE de {quando:%d/%m/%Y %H:%M}."

    # =================================================================== 1
    # as visoes do gerencial: a mesma tabela, trocando o recorte
    VISOES = [
        ("gerente", "GERENTE", "GERENTE"),
        ("uf", "UF", "UF"),
        ("cidade", "CIDADE", "CIDADE"),
        ("supervisor", "SUPERVISOR", "SUPERVISOR"),
        ("vendedor", "VENDEDOR", "VENDEDOR"),
        ("zona", "ZONA", "ZONA"),
        ("segmento", "SEGMENTO", "SEGMENTO"),
    ]

    # o que cada sigla da tabela quer dizer - aparece no rodape da aba
    LEGENDA = [
        ("CODIGO", "codigo fixo da zona (Z-UF-NN)"),
        ("VENDEDOR", "quem atende, com o codigo Protheus na frente"),
        ("SUPERVISOR", "o chefe do vendedor, pelo vinculo da aba 2"),
        ("QTD VDE", "quantos vendedores ATIVOS diferentes atendem a linha. "
                    "Quem esta INATIVO na aba 2 (cadeira vaga) nao entra"),
        ("QTD ZONAS", "quantas zonas diferentes a linha tem"),
        ("ZONAS C/ VDE", "as zonas que tem alguem ATIVO na cadeira"),
        ("ZONAS S/ VDE", "a vaga em aberto: zona sem vendedor nenhum ou com "
                         "vendedor marcado INATIVO na aba 2"),
        ("QTD CLI/VDE", "clientes divididos pelos vendedores ATIVOS da linha"),
        ("QTD CLI/SUP", "clientes divididos pelos supervisores da linha"),
        ("CLI/DIA", "quantas visitas o vendedor faz num DIA UTIL, do jeito "
                    "que a rota monta. Com 'excedentes no sabado' o dia util "
                    "para no teto e o resto vai para o sabado"),
        ("QTD CLI.", "clientes (codigo + loja: matriz com 2 lojas conta 2)"),
        ("BASE VISITA", "os clientes que ele visita NA SEMANA: os dias uteis "
                        "mais o ultimo sabado. E sobre esta base que a meta "
                        "e feita"),
        ("BASE TOTAL", "a carteira inteira dele, somando os excedentes que "
                       "caem no sabado-deposito. Sem o deposito ligado, as "
                       "duas bases sao iguais"),
        ("QTD CID.", "quantas cidades diferentes"),
        ("FAT. M6M R$", "media mensal dos ultimos 6 meses, liquida de "
                        "devolucao"),
        ("FAT/CLIENTE COMP. R$",
         "a media M6M dividida so pelos COMPRANTES. E o ticket real"),
        ("FAT. ACUM. R$", "faturamento desde o inicio da operacao"),
        ("COMPRANTES", "clientes que compraram nos ultimos 90 dias"),
        ("S A B C Z", "curva pela media mensal (cortes na aba 6). "
                      "Z = nunca faturou nada na janela"),
        ("C/ LIM.", "clientes com limite de credito cadastrado"),
        ("INAD. N", "inadimplentes (valor em atraso maior que zero)"),
        ("INAD. R$", "soma do valor em atraso"),
        ("INAD. %", "inadimplentes / clientes da linha"),
        ("(SEM ZONA)", "a linha com o que ainda nao tem zona nenhuma"),
        ("TOTAL", "a BAP inteira, presa no rodape. Nao rola e nao entra na "
                  "ordenacao. Vendedor, zona e supervisor contam uma vez so"),
    ]

    # as colunas que todo recorte tem, do QTD CLI. em diante.
    # OS TITULOS SAO CURTOS DE PROPOSITO: a regra desta aba e caber tudo
    # numa tela so, sem barra de rolagem lateral. O que cada sigla quer
    # dizer esta na legenda do rodape, que continua por extenso.
    COLUNAS_NUMEROS = [
        ("clientes", "QTD CLI.", 66, "center", False),
        # AS DUAS BASES DE CLIENTE:
        #   BASE VISITA  quem o vendedor visita na semana (dias uteis mais o
        #                ultimo sabado) - e sobre ela que a meta e feita
        #   BASE TOTAL   a carteira inteira, com os excedentes que caem no
        #                sabado-deposito. Sem deposito, as duas sao iguais.
        ("base_visita", "B. VISITA", 76, "center", False),
        ("base_carteira", "B. TOTAL", 74, "center", False),
        ("cidades", "QTD CID.", 66, "center", False),
        ("fat_mes", "FAT. M6M", 100, "e", False),
        ("fat_compr", "FAT/CLI. COMP.", 112, "e", False),
        ("fat_acum", "FAT. ACUM.", 110, "e", False),
        ("compr", "COMPR.", 70, "center", False),
        ("s", "S", 32, "center", False), ("a", "A", 32, "center", False),
        ("b", "B", 32, "center", False), ("c", "C", 34, "center", False),
        ("z", "Z", 44, "center", False),
        ("limite", "C/ LIM.", 62, "center", False),
        ("inad_qtd", "INAD. N", 62, "center", False),
        ("inad_valor", "INAD. R$", 94, "e", False),
        ("inad_pct", "INAD. %", 64, "center", False),
    ]

    # ZONAS C/ VDE e ZONAS S/ VDE entram em todo recorte que tem zona.
    # S/ VDE junta as duas caras da vaga em aberto: a zona sem ninguem
    # cadastrado e a zona com vendedor INATIVO.
    COLUNAS_DE_ZONA = [("zonas_com_vde", "ZONAS C/ VDE", 102, "center", False),
                       ("zonas_sem_vde", "ZONAS S/ VDE", 102, "center", False)]

    def _colunas_da_visao(self, chave, titulo):
        """
        Cada recorte tem o seu comeco; do QTD CLI. em diante e tudo igual.
        CLI/DIA so faz sentido em VENDEDOR e ZONA, que sao os unicos que
        tem uma agenda de rota propria.
        """
        if chave == "zona":
            cabeca = [("codigo", "CODIGO", 70, "w", False),
                      ("nome", "ZONA", 150, "w", True),
                      ("uf", "UF", 32, "center", False),
                      ("vendedor", "VENDEDOR", 134, "w", False),
                      ("supervisor", "SUPERVISOR", 120, "w", False),
                      ("cli_dia", "CLI/DIA", 58, "center", False)]
        elif chave == "vendedor":
            cabeca = [("nome", titulo, 190, "w", True),
                      ("qtd_zonas", "QTD ZONAS", 88, "center", False)] \
                + self.COLUNAS_DE_ZONA \
                + [("cli_dia", "CLI/DIA", 58, "center", False)]
        elif chave == "supervisor":
            cabeca = [("nome", titulo, 190, "w", True),
                      ("qtd_vde", "QTD VDE", 72, "center", False),
                      ("qtd_zonas", "QTD ZONAS", 88, "center", False)] \
                + self.COLUNAS_DE_ZONA \
                + [("cli_vde", "QTD CLI/VDE", 92, "center", False)]
        elif chave == "gerente":
            cabeca = [("nome", titulo, 190, "w", True),
                      ("qtd_vde", "QTD VDE", 72, "center", False),
                      ("qtd_zonas", "QTD ZONAS", 88, "center", False)] \
                + self.COLUNAS_DE_ZONA \
                + [("cli_sup", "QTD CLI/SUP", 92, "center", False)]
        else:                                   # UF e CIDADE
            cabeca = [("nome", titulo, 190, "w", True),
                      ("qtd_vde", "QTD VDE", 72, "center", False),
                      ("qtd_zonas", "QTD ZONAS", 88, "center", False)] \
                + self.COLUNAS_DE_ZONA
        return cabeca + self.COLUNAS_NUMEROS

    def _montar_resumo(self):
        f = self.aba_resumo
        self._faixa_recalcular(f)
        topo = ttk.Frame(f)
        topo.pack(fill="x", pady=(0, 6))
        self.lbl_du = ttk.Label(topo, text="", style="Cod.TLabel")
        self.lbl_du.pack(side="left")
        # o mes, os feriados, IMPORTAR e EXPORTAR o PLANNER ficam na aba 6

        ttk.Label(f, text="Clique numa linha de GERENTE, UF, CIDADE, SUPERVISOR "
                          "ou VENDEDOR para ver embaixo as zonas dela. Clique "
                          "no titulo de qualquer coluna para ordenar (de novo "
                          "para inverter). A linha TOTAL fica presa no rodape "
                          "de cada recorte; as legendas estao no fim da aba.",
                  style="Sub.TLabel", wraplength=1250).pack(anchor="w",
                                                            pady=(0, 6))

        # ---- o filtro de linhas, um por recorte --------------------------
        # Serve para tirar da tela o que nao vai para a foto: cada aba tem
        # o seu proprio filtro e a sua propria lista de escondidas, e as
        # duas coisas ficam gravadas - fechar o programa nao desfaz.
        # A LINHA TOTAL PASSA A FECHAR COM O QUE SOBROU NA TELA.
        barra_f = ttk.Frame(f)
        barra_f.pack(fill="x", pady=(0, 6))
        # O FILTRO DE SEGMENTO vale para TODAS as abas de recorte de uma
        # vez: escolheu MOTOPECAS, gerente, UF, vendedor, zona... passam a
        # contar so os clientes de motopecas. Fica gravado no config.
        ttk.Label(barra_f, text="Segmento:").pack(side="left")
        self.var_segmento_res = tk.StringVar(
            value=self.cfg.get("filtro_segmento") or self.TODOS_NO_FILTRO)
        self.cb_segmento_res = ttk.Combobox(
            barra_f, textvariable=self.var_segmento_res, state="readonly",
            width=26, values=[self.TODOS_NO_FILTRO] + list(nu.SEGMENTOS))
        self.cb_segmento_res.pack(side="left", padx=(4, 16))
        self.cb_segmento_res.bind("<<ComboboxSelected>>",
                                  lambda _: self._segmento_res_mudou())
        ttk.Label(barra_f, text="Mostrar so quem tem:").pack(side="left")
        self.var_filtro_res = tk.StringVar()
        ent = ttk.Entry(barra_f, textvariable=self.var_filtro_res, width=26)
        ent.pack(side="left", padx=6)
        ent.bind("<KeyRelease>", lambda _: self._filtro_res_digitado())
        ttk.Button(barra_f, text="ESCONDER A LINHA MARCADA",
                   command=self.esconder_linha_resumo).pack(side="left",
                                                            padx=(8, 0))
        ttk.Button(barra_f, text="MOSTRAR TUDO",
                   command=self.mostrar_tudo_resumo).pack(side="left", padx=6)
        self.lbl_filtro_res = ttk.Label(barra_f, text="", style="Sub.TLabel")
        self.lbl_filtro_res.pack(side="left", padx=10)

        # ---- os filtros de uma visao pela outra --------------------------
        # "as cidades do PA", "as zonas do Denylson", "os vendedores da
        # Lais". A caixa de texto acima procura no nome da propria linha;
        # estes olham o que esta DENTRO dela. Cada recorte mostra so os
        # que fazem sentido nele, e um filtro estreita a lista do outro.
        self._montar_filtros_da_visao(f)

        # ---- uma tabela so, com as seis abas de recorte -------------------
        self.abas_visao = ttk.Notebook(f)
        self.abas_visao.pack(fill="both", expand=True)
        self.visoes = {}
        for chave, rotulo, titulo in self.VISOES:
            colunas = self._colunas_da_visao(chave, titulo)
            quadro, t = tabela(self.abas_visao, colunas, altura=10,
                               rodape=True)
            self.abas_visao.add(quadro, text=f"  {rotulo}  ")
            self.visoes[chave] = t
            t.tag_configure("semvend", background=COR_AVISO)
            if chave != "zona":
                # clicar numa linha abre, embaixo, as zonas que ela tem
                t.bind("<<TreeviewSelect>>",
                       lambda _, c=chave: self._linha_do_resumo_clicada(c))
        self.abas_visao.bind("<<NotebookTabChanged>>",
                             lambda _: self._recorte_trocado(), add="+")

        quadro_total = ttk.Frame(self.abas_visao, padding=14)
        self.abas_visao.add(quadro_total, text="  BAP TOTAL  ")
        self.txt_total = tk.Text(quadro_total, height=10, relief="flat",
                                 font=("Consolas", 10), background=COR_PAPEL,
                                 foreground=COR_TEXTO, borderwidth=0,
                                 highlightthickness=0, padx=10, pady=6,
                                 wrap="none")
        self.txt_total.pack(fill="both", expand=True)

        # ---- o detalhe da linha clicada: as zonas dela --------------------
        # Fica escondido ate alguem clicar num vendedor, supervisor,
        # gerente, UF ou cidade. Entra entre a tabela e a legenda.
        self._detalhe = None                 # (recorte, iid) do que esta aberto
        self.quadro_detalhe = ttk.LabelFrame(f, text=" Zonas da linha marcada ",
                                             padding=(10, 6, 10, 8))
        cab_d = ttk.Frame(self.quadro_detalhe)
        cab_d.pack(fill="x")
        self.lbl_detalhe = ttk.Label(cab_d, text="", style="Cod.TLabel")
        self.lbl_detalhe.pack(side="left")
        ttk.Button(cab_d, text="Fechar", command=self._fechar_detalhe).pack(
            side="right")
        colunas_d = [("codigo", "CODIGO", 78, "w", False),
                     ("nome", "ZONA", 190, "w", True),
                     ("uf", "UF", 38, "center", False),
                     ("vendedor", "VENDEDOR DA ZONA", 190, "w", False),
                     ("vinculo", "VINCULO", 150, "w", False),
                     ("clientes", "QTD CLI.", 66, "center", False),
                     ("cidades", "QTD CID.", 66, "center", False),
                     ("cli_dia", "CLI/DIA", 66, "center", False),
                     ("fat_mes", "FAT. M6M R$", 108, "e", False),
                     ("compr", "COMPRANTES", 92, "center", False),
                     ("inad_qtd", "INAD. N", 62, "center", False),
                     ("inad_valor", "INAD. R$", 94, "e", False)]
        quadro_d, self.tab_detalhe = tabela(self.quadro_detalhe, colunas_d,
                                            altura=5, horizontal=False)
        quadro_d.pack(fill="both", expand=True, pady=(4, 0))
        self.tab_detalhe.tag_configure("semvend", background=COR_AVISO)
        self.lbl_detalhe_pe = ttk.Label(self.quadro_detalhe, text="",
                                        style="Sub.TLabel", wraplength=1250)
        self.lbl_detalhe_pe.pack(anchor="w", pady=(6, 0))

        # ---- legenda das colunas -----------------------------------------
        # A legenda come uns 300px de altura. Como a regra desta aba e
        # caber tudo na tela, ela nasce FECHADA e abre no botao - com ela
        # fechada a tabela ganha o espaco e mostra o dobro de linhas. O
        # estado fica gravado: quem gosta dela aberta a deixa aberta.
        linha_leg = ttk.Frame(f)
        linha_leg.pack(fill="x", pady=(8, 0))
        self.linha_legenda = linha_leg
        self.var_legenda = tk.BooleanVar(
            value=bool(self.cfg.get("mostrar_legenda", False)))
        self.btn_legenda = ttk.Button(linha_leg, text="",
                                      command=self.virar_legenda)
        self.btn_legenda.pack(side="left")

        rodape = ttk.LabelFrame(f, text=" O que quer dizer cada coluna ",
                                padding=(10, 4, 10, 6))
        self.rodape_legenda = rodape
        corpo = ttk.Frame(rodape)
        corpo.pack(fill="x")
        por_coluna = (len(self.LEGENDA) + 2) // 3
        for n in range(3):
            pedaco = self.LEGENDA[n * por_coluna:(n + 1) * por_coluna]
            for linha, (sigla, texto_) in enumerate(pedaco):
                ttk.Label(corpo, text=sigla, font=("Segoe UI", 8, "bold"),
                          foreground=COR_TITULO).grid(row=linha, column=n * 2,
                                                      sticky="nw", padx=(0, 6),
                                                      pady=0)
                ttk.Label(corpo, text=texto_, font=("Segoe UI", 8),
                          foreground="#555555", wraplength=300,
                          justify="left").grid(row=linha, column=n * 2 + 1,
                                               sticky="nw", padx=(0, 20), pady=0)
            corpo.columnconfigure(n * 2 + 1, weight=1)
        legenda_de_cores(rodape, [
            (COR_AVISO, "zona SEM VENDEDOR - nao entra na rota"),
            (COR_ESTOURO, "a carteira NAO CABE no mes (CLI/DIA passa do teto)"),
            (COR_INATIVO, "cadeira VAGA: o vendedor da zona esta INATIVO"),
            (COR_SELECAO, "linha marcada agora"),
            (COR_TOTAL, "linha TOTAL - a BAP inteira"),
        ]).pack(anchor="w", pady=(10, 0))
        self._mostrar_legenda()

    def virar_legenda(self):
        self.var_legenda.set(not self.var_legenda.get())
        self.cfg["mostrar_legenda"] = self.var_legenda.get()
        self.salvar()
        self._mostrar_legenda()

    def _mostrar_legenda(self):
        if self.var_legenda.get():
            self.rodape_legenda.pack(fill="x", pady=(6, 0))
            self.btn_legenda.configure(text="ESCONDER A LEGENDA DAS COLUNAS")
        else:
            self.rodape_legenda.pack_forget()
            self.btn_legenda.configure(text="O QUE QUER DIZER CADA COLUNA")

    def trocar_mes(self):
        """Mudar o mes aqui e abrir o Planner daquele mes (cada mes tem o
        seu); se ele nao existir, nasce como copia do aberto."""
        mes = nu.MESES_PT.index(self.var_mes.get())
        novo = f"{self.var_ano.get()}-{mes:02d}"
        if novo == self.cfg["mes"]:
            return
        if not self.abrir_mes(novo):
            self.var_ano.set(self.cfg["mes"][:4])
            self.var_mes.set(nu.MESES_PT[int(self.cfg["mes"][5:7])])

    def editar_feriados(self):
        atual = ", ".join(self.cfg.get("feriados") or [])
        novo = self._perguntar_texto(
            "Feriados",
            "Datas no formato AAAA-MM-DD, separadas por virgula. "
            "Sao os dias que saem do calculo de dias uteis.\n"
            "Ex.: 2026-09-07, 2026-10-12", atual)
        if novo is None:
            return
        datas = []
        for parte in novo.replace(";", ",").split(","):
            d = nu.data_de(parte.strip())
            if d:
                datas.append(d.isoformat())
        self.cfg["feriados"] = sorted(set(datas))
        self.salvar()
        self.marcar_pendente()
        self._mostrar_calendario()
        # o mes mudou: o numero de caixas da SEMANA DA ROTA vai junto
        self._desenhar_semanas()
        self.atualizar_resumo(True)

    def _mostrar_calendario(self):
        """A etiqueta de dias uteis/feriados, na aba 6 e na aba 1."""
        feriados = self.cfg.get("feriados") or []
        du = nu.dias_uteis(self.cfg["mes"], feriados)
        do_mes = [f for f in feriados if f[:7] == self.cfg["mes"]]
        texto_ = f"{du} dias uteis   |   {len(do_mes)} feriado(s) neste mes"
        if do_mes:
            texto_ += ":  " + ", ".join(f[8:] + "/" + f[5:7] for f in do_mes)
        if len(feriados) > len(do_mes):
            texto_ += f"   ({len(feriados)} cadastrados no total)"
        if getattr(self, "lbl_calendario", None):
            self.lbl_calendario.configure(text=texto_)

    @staticmethod
    def _numeros_da_linha(r):
        """A parte que e igual em todos os seis recortes."""
        return (r["clientes"],
                r.get("base_visita", r["clientes"]),
                r.get("base_carteira", r["clientes"]),
                r["cidades"],
                dinheiro(r["faturamento_mensal"]),
                dinheiro(r["faturamento_por_comprante"]),
                dinheiro(r["receita_acumulada"]), r["comprantes"],
                r["curva_S"], r["curva_A"], r["curva_B"], r["curva_C"],
                r["curva_Z"], r["com_limite"], r["inadimplentes"],
                dinheiro(r["valor_atraso"]), f"{r['pct_inadimplencia']:.1f}%")

    def _cabeca_da_linha(self, chave, r):
        """O comeco da linha, que muda de recorte para recorte."""
        if chave == "zona":
            return (r["codigo"], r["zona_nome"], r["uf"],
                    r.get("atendimento_rotulo")
                    or f"{r['vendedor']} {r['vendedor_nome']}".strip()
                    or SEM_VENDEDOR,
                    r["supervisor"], r["clientes_dia"])
        nome = self._rotulo_da_visao(chave, r)
        zonas = (r.get("zonas_com_vde", 0), r.get("zonas_sem_vde", 0))
        if chave == "vendedor":
            return (nome, r["qtd_zonas"]) + zonas + (r["clientes_dia"],)
        if chave == "supervisor":
            return (nome, r["qtd_vendedores"], r["qtd_zonas"]) + zonas \
                + (r["clientes_por_vendedor"],)
        if chave == "gerente":
            return (nome, r["qtd_vendedores"], r["qtd_zonas"]) + zonas \
                + (r["clientes_por_supervisor"],)
        return (nome, r["qtd_vendedores"], r["qtd_zonas"]) + zonas

    def _cabeca_da_total(self, chave, t, cli_dia=None):
        """
        O comeco da linha TOTAL. E a BAP inteira: o numero de vendedores,
        de zonas e de supervisores conta cada um UMA vez, mesmo que ele
        apareca em varias linhas do recorte (um vendedor com tres zonas
        soma 1 em QTD VDE e 3 em QTD ZONAS). O CLI/DIA e a soma da coluna
        - sao as visitas que a BAP inteira faz num dia util.
        """
        if cli_dia is None:
            cli_dia = t["clientes_dia"]
        zonas = (t.get("zonas_com_vde", 0), t.get("zonas_sem_vde", 0))
        if chave == "zona":
            return (ROTULO_TOTAL, f"{t['qtd_zonas']} zona(s) com cliente", "",
                    f"{t['qtd_vendedores']} vendedor(es) ativo(s)",
                    f"{t['qtd_supervisores']} supervisor(es)", cli_dia)
        if chave == "vendedor":
            return (ROTULO_TOTAL, t["qtd_zonas"]) + zonas + (cli_dia,)
        if chave == "supervisor":
            return (ROTULO_TOTAL, t["qtd_vendedores"], t["qtd_zonas"]) \
                + zonas + (t["clientes_por_vendedor"],)
        if chave == "gerente":
            return (ROTULO_TOTAL, t["qtd_vendedores"], t["qtd_zonas"]) \
                + zonas + (t["clientes_por_supervisor"],)
        return (ROTULO_TOTAL, t["qtd_vendedores"], t["qtd_zonas"]) + zonas

    def _rotulo_da_visao(self, chave, r):
        if chave == "vendedor":
            return (f"{r['vendedor']} - {r['vendedor_nome']}"
                    if r["vendedor"] not in ("", "(sem vendedor)")
                    else "(SEM VENDEDOR)")
        if chave == "cidade":
            return f"{r['uf']} - {r['cidade_nome']}"
        return r.get(chave) or f"(sem {chave})"

    def atualizar_resumo(self, forcar=False):
        if not self.clientes:
            self.lbl_du.configure(text="Sem base carregada")
            for t in self.visoes.values():
                t.delete(*t.get_children())
                escrever_total(t, None)
            self._fechar_detalhe()
            self.txt_total.delete("1.0", "end")
            self.txt_total.insert("1.0", self._historico)
            return
        if not forcar and not self._ger_sujo:
            return
        self.resumo = nu.indicadores(self.cfg, self.clientes,
                                     self._segmentos_do_filtro())
        self._ger_sujo = False
        self._redesenhar_resumo()

    def _redesenhar_resumo(self):
        """
        So redesenha, com os numeros que ja estao em self.resumo. E o que
        o filtro chama: mexer no filtro nao pode refazer a rota do mes
        inteira a cada tecla.
        """
        if not self.clientes or not self.resumo:
            return
        du = self.resumo["du"]
        mes = int(self.cfg["mes"][5:7])
        self.lbl_du.configure(
            text=f"{nu.MESES_PT[mes]}/{self.cfg['mes'][:4]}   |   {du} dias "
                 f"uteis   |   {len(self.cfg.get('feriados') or [])} feriado(s)")
        self.lbl_topo.configure(
            text=f"{len(self.clientes)} clientes  |  {len(self.areas)} areas  |  "
                 f"{len(self.cfg['zonas'])} zonas")

        self._silencio = True
        try:
            for chave, _, _ in self.VISOES:
                arvore = self.visoes[chave]
                arvore.delete(*arvore.get_children())
                dia = 0.0            # soma do CLI/DIA do que foi desenhado
                mostradas = []       # as linhas que sobraram depois do filtro
                if chave == "zona":
                    linhas = sorted(self.resumo["zona"],
                                    key=lambda x: (-x["clientes"], x["codigo"]))
                    i = 0
                    for r in linhas:
                        if r["clientes"] == 0 and not r["vendedor"]:
                            continue
                        if not self._passa_no_filtro(chave, r["zona"],
                                                     r["zona_nome"]):
                            continue
                        if not self._passa_nos_campos(chave, r):
                            continue
                        if not r["vendedor"]:
                            tags = ("semvend",)
                        elif not r.get("vendedor_ativo", True):
                            # cadeira VAGA: a rota sai, mas nao ha vendedor
                            tags = ("inativo",)
                        elif not r.get("cabe", True):
                            tags = ("estourou",)
                        else:
                            tags = ("zebra",) if i % 2 else ()
                        i += 1
                        dia += r["clientes_dia"]
                        mostradas.append(r)
                        arvore.insert(
                            "", "end", iid=r["zona"], tags=tags,
                            values=self._cabeca_da_linha(chave, r)
                            + self._numeros_da_linha(r))
                else:
                    i = 0
                    for r in self.resumo[chave]:
                        iid = self._iid_da_linha(chave, r)
                        if not self._passa_no_filtro(
                                chave, iid, self._rotulo_da_visao(chave, r)):
                            continue
                        if not self._passa_nos_campos(chave, r):
                            continue
                        dia += r["clientes_dia"]
                        # vermelho = a carteira da linha nao cabe no mes
                        # com o teto de visitas por dia configurado
                        tags = (("estourou",) if not r.get("cabe", True)
                                else ("zebra",) if i % 2 else ())
                        i += 1
                        mostradas.append(r)
                        # o iid e a chave da linha (codigo do vendedor, nome
                        # do supervisor, UF|CIDADE...): e por ele que o
                        # clique acha de novo a linha no resumo
                        arvore.insert(
                            "", "end", iid=iid, tags=tags,
                            values=self._cabeca_da_linha(chave, r)
                            + self._numeros_da_linha(r))
                # A linha TOTAL fecha toda tabela e fica presa no rodape.
                # COM FILTRO LIGADO ELA FECHA COM O QUE SOBROU NA TELA -
                # senao o rodape contaria o que nao esta mais ali.
                total = (self.resumo["total"] if not self._tem_filtro(chave)
                         else nu.total_das_linhas(
                             mostradas,
                             self.cfg["parametros"].get("meses_faturamento", 6)))
                escrever_total(
                    arvore,
                    self._cabeca_da_total(chave, total, round(dia, 1))
                    + self._numeros_da_linha(total))
                reaplicar_ordem(arvore)
        finally:
            self._silencio = False

        self._escrever_bap_total(du)
        self._redesenhar_detalhe()
        self._recorte_trocado()
        self.aviso("Indicadores atualizados.", COR_OK)

    # ---- o filtro de SEGMENTO (vale para todas as abas) ------------------
    def _segmentos_do_filtro(self) -> list:
        seg = (self.cfg.get("filtro_segmento") or "").strip()
        return [seg] if seg and seg != self.TODOS_NO_FILTRO else []

    def _segmento_res_mudou(self):
        if self._silencio:
            return
        valor = self.var_segmento_res.get()
        self.cfg["filtro_segmento"] = ("" if valor == self.TODOS_NO_FILTRO
                                       else valor)
        self.salvar()
        self.atualizar_resumo(True)
        self.aviso(("Segmento: " + valor) if self._segmentos_do_filtro()
                   else "Todos os segmentos.", COR_OK)

    # ---- os filtros de uma visao pela outra -----------------------------
    # QUAL FILTRO APARECE EM CADA ABA. So entra o que existe dentro da
    # linha: nao da para filtrar a aba UF por UF (a linha JA e a UF), nem
    # a de gerente por supervisor - para isso ha a aba do supervisor.
    TODOS_NO_FILTRO = "(todos)"
    FILTROS_DA_VISAO = {
        "uf": ("supervisor",),
        "cidade": ("uf",),
        "vendedor": ("supervisor",),
        "zona": ("uf", "cidade", "supervisor", "vendedor"),
        "segmento": ("uf", "supervisor"),
    }
    ROTULO_DO_FILTRO = {"uf": "UF", "cidade": "Cidade",
                        "supervisor": "Supervisor", "vendedor": "Vendedor"}
    LARGURA_DO_FILTRO = {"uf": 7, "cidade": 18, "supervisor": 22,
                         "vendedor": 24}

    def _montar_filtros_da_visao(self, pai):
        barra = ttk.Frame(pai)
        barra.pack(fill="x", pady=(0, 6))
        self.lbl_filtros_da_visao = ttk.Label(barra, text="Filtrar por:")
        self.lbl_filtros_da_visao.pack(side="left")
        self.var_filtro_campo = {}
        self.quadro_filtro_campo = {}
        for campo in ("uf", "cidade", "supervisor", "vendedor"):
            quadro = ttk.Frame(barra)
            ttk.Label(quadro, text=self.ROTULO_DO_FILTRO[campo],
                      style="Sub.TLabel").pack(side="left", padx=(10, 4))
            var = tk.StringVar(value=self.TODOS_NO_FILTRO)
            cb = ttk.Combobox(quadro, textvariable=var, state="readonly",
                              width=self.LARGURA_DO_FILTRO[campo])
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>",
                    lambda _e, c=campo: self._filtro_campo_mudou(c))
            self.var_filtro_campo[campo] = var
            self.quadro_filtro_campo[campo] = (quadro, cb)
        self.bt_limpar_campos = ttk.Button(
            barra, text="Limpar os filtros", command=self.limpar_filtros_campo)
        self.bt_limpar_campos.pack(side="left", padx=(14, 0))
        self.lbl_filtro_campo = ttk.Label(barra, text="", style="Sub.TLabel")
        self.lbl_filtro_campo.pack(side="left", padx=10)

    def _escolhas_da_visao(self, visao) -> dict:
        """O que esta escolhido nos filtros daquela aba, sem os '(todos)'."""
        guardado = self._filtro_campo.get(visao) or {}
        return {c: v for c, v in guardado.items()
                if v and v != self.TODOS_NO_FILTRO
                and c in self.FILTROS_DA_VISAO.get(visao, ())}

    def _valores_da_linha(self, visao, campo, r) -> set:
        """
        O que a linha tem daquele campo - sempre um conjunto.

        Uma UF tem varios supervisores e uma zona tem varias cidades: por
        isso conjunto, e nao um valor so. A linha passa no filtro quando o
        que foi escolhido esta dentro desse conjunto.
        """
        # os conjuntos com "_" na frente ja viajam em toda linha do
        # gerencial (e deles que sai o TOTAL da tela): _cidades vem como
        # "UF|CIDADE", _supervisores com o nome e _vendedores_cadeira com
        # o codigo, incluindo a cadeira VAGA.
        if campo == "uf":
            if r.get("uf"):
                return {r["uf"]}
            return {c.split("|")[0] for c in (r.get("_cidades") or ())}
        if campo == "cidade":
            if visao == "cidade":
                return {r.get("cidade_nome") or ""}
            return {c.partition("|")[2] for c in (r.get("_cidades") or ())}
        if campo == "supervisor":
            if r.get("supervisor"):
                return {r["supervisor"]}
            return set(r.get("_supervisores") or ())
        if campo == "vendedor":
            if visao in ("zona", "vendedor"):
                return {self._nome_do_vendedor(r.get("vendedor"))}
            return {self._nome_do_vendedor(c)
                    for c in (r.get("_vendedores_cadeira") or ())}
        return set()

    def _nome_do_vendedor(self, cod) -> str:
        """'000034 - ANDERSON LIMA SILVA', do jeito que a tela ja mostra."""
        cod = (cod or "").strip()
        if not cod or cod == "(sem vendedor)":
            return SEM_VENDEDOR
        nome = next((p.get("nome", "") for p in self.cfg["pessoas"]
                     if p["cod_protheus"] == cod), "")
        return f"{cod} - {nome}".strip(" -")

    def _passa_nos_campos(self, visao, r) -> bool:
        escolhas = self._escolhas_da_visao(visao)
        return all(valor in self._valores_da_linha(visao, campo, r)
                   for campo, valor in escolhas.items())

    def _opcoes_do_campo(self, visao, campo) -> list:
        """
        O que cabe naquela caixa, JA ESTREITADO pelos outros filtros: com
        PA escolhido na UF, a caixa de cidade so oferece cidade do PA.
        """
        escolhas = {c: v for c, v in self._escolhas_da_visao(visao).items()
                    if c != campo}
        valores = set()
        for r in (self.resumo or {}).get(visao, ()):
            if not all(v in self._valores_da_linha(visao, c, r)
                       for c, v in escolhas.items()):
                continue
            valores |= {v for v in self._valores_da_linha(visao, campo, r) if v}
        return [self.TODOS_NO_FILTRO] + sorted(valores)

    def _desenhar_filtros_da_visao(self):
        """Mostra so as caixas da aba aberta e enche cada uma."""
        visao = self._recorte_atual()
        campos = self.FILTROS_DA_VISAO.get(visao, ())
        for campo, (quadro, cb) in self.quadro_filtro_campo.items():
            if campo not in campos:
                quadro.pack_forget()
                continue
            quadro.pack(side="left", before=self.bt_limpar_campos)
            opcoes = self._opcoes_do_campo(visao, campo)
            cb.configure(values=opcoes)
            atual = (self._filtro_campo.get(visao) or {}).get(campo)
            # valor que sumiu da base (vendedor que saiu, cidade sem
            # cliente) nao pode ficar preso filtrando tudo para fora
            if atual not in opcoes:
                atual = self.TODOS_NO_FILTRO
                self._filtro_campo.setdefault(visao, {})[campo] = atual
            self.var_filtro_campo[campo].set(atual)
        self.bt_limpar_campos.configure(
            state="normal" if campos else "disabled")
        escolhas = self._escolhas_da_visao(visao)
        if not campos:
            texto = ""
        elif escolhas:
            texto = "  |  ".join(f"{self.ROTULO_DO_FILTRO[c]}: {v}"
                                 for c, v in escolhas.items())
        else:
            texto = ""
        self.lbl_filtro_campo.configure(
            text=texto, foreground=COR_ALERTA if escolhas else COR_SUAVE)

    def _filtro_campo_mudou(self, campo):
        if self._silencio:
            return
        visao = self._recorte_atual()
        if campo not in self.FILTROS_DA_VISAO.get(visao, ()):
            return
        self._filtro_campo.setdefault(visao, {})[campo] = \
            self.var_filtro_campo[campo].get()
        self._gravar_filtro()
        self._redesenhar_resumo()

    def limpar_filtros_campo(self):
        """Devolve as caixas da aba aberta para (todos)."""
        visao = self._recorte_atual()
        self._filtro_campo[visao] = {}
        self._gravar_filtro()
        self._redesenhar_resumo()

    # ---- o filtro de linhas do resumo -----------------------------------
    def _recorte_atual(self) -> str:
        """Qual das seis abas de recorte esta aberta agora."""
        try:
            i = self.abas_visao.index(self.abas_visao.select())
        except (tk.TclError, AttributeError):
            return self.VISOES[0][0]
        return self.VISOES[i][0] if i < len(self.VISOES) else ""

    def _tem_filtro(self, chave) -> bool:
        return bool(self._filtro_texto.get(chave)
                    or self._escondidas.get(chave)
                    or self._escolhas_da_visao(chave))

    def _passa_no_filtro(self, chave, iid, rotulo="") -> bool:
        """
        A linha entra na tela? Nao entra se voce a escondeu a mao, e nao
        entra se ha texto na caixa e nem o nome nem a chave dela casam.
        """
        if iid in self._escondidas.get(chave, ()):
            return False
        procura = (self._filtro_texto.get(chave) or "").strip()
        if not procura:
            return True
        alvo = nu.norm(f"{rotulo} {iid}")
        return all(p in alvo for p in nu.norm(procura).split())

    def _gravar_filtro(self):
        self.cfg["filtro_resumo"] = {
            chave: {"texto": self._filtro_texto.get(chave, ""),
                    "escondidas": sorted(self._escondidas.get(chave, ())),
                    "campos": self._escolhas_da_visao(chave)}
            for chave, _, _ in self.VISOES
            if self._tem_filtro(chave)}
        self.salvar()

    def _recorte_trocado(self):
        """Trocou de aba: a caixa mostra o filtro DAQUELE recorte."""
        chave = self._recorte_atual()
        if not chave:
            return
        self._silencio = True
        try:
            self.var_filtro_res.set(self._filtro_texto.get(chave, ""))
        finally:
            self._silencio = False
        self._desenhar_filtros_da_visao()
        escondidas = len(self._escondidas.get(chave, ()))
        rotulo = dict((c, r) for c, r, _ in self.VISOES).get(chave, chave)
        self.lbl_filtro_res.configure(
            text=(f"filtro da aba {rotulo}"
                  + (f"   |   {escondidas} linha(s) escondida(s) a mao"
                     if escondidas else "")
                  + ("   |   o TOTAL esta fechando com o que ficou na tela"
                     if self._tem_filtro(chave) else "")),
            foreground=COR_ALERTA if self._tem_filtro(chave) else COR_SUAVE)

    def _filtro_res_digitado(self):
        if self._silencio:
            return
        chave = self._recorte_atual()
        if not chave:
            return
        self._filtro_texto[chave] = self.var_filtro_res.get()
        self._gravar_filtro()
        self._redesenhar_resumo()

    def esconder_linha_resumo(self):
        """Tira da tela a linha marcada - so daquela aba."""
        chave = self._recorte_atual()
        arvore = self.visoes.get(chave)
        if arvore is None:
            return
        marcadas = [i for i in arvore.selection() if i != LINHA_TOTAL]
        if not marcadas:
            messagebox.showinfo("Planner BAP",
                                "Clique primeiro na linha que voce quer tirar "
                                "da tela.\n\nEla nao e apagada de nada: sai da "
                                "foto desta aba e volta com MOSTRAR TUDO.")
            return
        self._escondidas.setdefault(chave, set()).update(marcadas)
        self._gravar_filtro()
        self._redesenhar_resumo()

    def mostrar_tudo_resumo(self):
        """Limpa o filtro da aba aberta: texto e linhas escondidas."""
        chave = self._recorte_atual()
        if not chave:
            return
        self._filtro_texto[chave] = ""
        self._escondidas[chave] = set()
        self._filtro_campo[chave] = {}
        self._silencio = True
        try:
            self.var_filtro_res.set("")
        finally:
            self._silencio = False
        self._gravar_filtro()
        self._redesenhar_resumo()

    # ---- o detalhe: as zonas da linha clicada ---------------------------
    @staticmethod
    def _iid_da_linha(chave, r):
        """A chave de cada linha do recorte, igual a que indicadores() usa."""
        return str(r.get(chave) or f"(sem {chave})")

    def _filtro_da_linha(self, chave, iid):
        """
        A mesma regra de agrupamento de indicadores(), como um filtro de
        cliente: devolve a funcao que diz se o cliente pertence a linha.
        """
        cfg = self.cfg
        zonas = {z["id"]: z for z in cfg["zonas"]}
        chefia = {}

        def chefes(cod):
            if cod not in chefia:
                chefia[cod] = (nu.nome_supervisor(cfg, cod) or "(sem supervisor)",
                               nu.nome_gerente(cfg, cod) or "(sem gerente)")
            return chefia[cod]

        if chave == "vendedor":
            alvo = "" if iid == "(sem vendedor)" else iid
            return lambda c: nu.vendedor_do_cliente(cfg, c, zonas) == alvo
        if chave == "supervisor":
            return lambda c: chefes(nu.vendedor_do_cliente(cfg, c, zonas))[0] == iid
        if chave == "gerente":
            return lambda c: chefes(nu.vendedor_do_cliente(cfg, c, zonas))[1] == iid
        if chave == "uf":
            return lambda c: (c["UF"] or "(sem UF)") == iid
        if chave == "cidade":
            return lambda c: f"{c['UF']}|{c['CIDADE']}" == iid
        if chave == "segmento":
            return lambda c: nu.segmento_do_cliente(c) == iid
        return lambda c: False

    def _linha_do_resumo_clicada(self, chave):
        if self._silencio:
            return
        sel = self.visoes[chave].selection()
        if not sel or sel[0] == LINHA_TOTAL:
            return
        self._mostrar_detalhe(chave, sel[0])

    def _mostrar_detalhe(self, chave, iid):
        """Enche e mostra o quadro com as zonas da linha (chave, iid)."""
        if not self.clientes or self.resumo is None:
            return
        r = next((x for x in self.resumo.get(chave, [])
                  if self._iid_da_linha(chave, x) == iid), None)
        if r is None:
            self._fechar_detalhe()
            return
        rotulo = self._rotulo_da_visao(chave, r)
        da_linha = self._filtro_da_linha(chave, iid)
        segs = self._segmentos_do_filtro()
        filtro = (da_linha if not segs else
                  (lambda c: da_linha(c) and nu.segmento_do_cliente(c) in segs))
        linhas = nu.recorte_por_zona(self.cfg, self.clientes, filtro)
        da_zona = {x["zona"]: x for x in self.resumo["zona"]}
        cod_vend = ("" if iid == "(sem vendedor)" else iid) \
            if chave == "vendedor" else None

        self._silencio = True
        try:
            self.tab_detalhe.delete(*self.tab_detalhe.get_children())
            titulares = 0
            for i, z in enumerate(linhas):
                inteira = da_zona.get(z["zona"], {})
                dono = (f"{z['vendedor']} {z['vendedor_nome']}".strip()
                        or SEM_VENDEDOR)
                if z["zona"] == nu.SEM_ZONA:
                    vinculo = "cliente sem zona"
                elif chave == "vendedor":
                    if cod_vend in nu.vendedores_da_zona(
                            next((x for x in self.cfg["zonas"]
                                  if x["id"] == z["zona"]), {})):
                        vinculo = "titular"
                        titulares += 1
                    else:
                        vinculo = f"por excecao ({z['clientes']} cli.)"
                elif chave in ("supervisor", "gerente"):
                    # a zona e "da linha" quando o vendedor titular dela
                    # responde a esse supervisor/gerente
                    if not z["vendedor"]:
                        vinculo = "sem vendedor"
                    else:
                        chefe = (nu.nome_supervisor(self.cfg, z["vendedor"])
                                 or "(sem supervisor)") if chave == "supervisor" \
                            else (nu.nome_gerente(self.cfg, z["vendedor"])
                                  or "(sem gerente)")
                        if chefe == iid:
                            vinculo = "titular"
                            titulares += 1
                        else:
                            vinculo = f"por excecao ({z['clientes']} cli.)"
                else:
                    vinculo = ""
                tags = ("semvend",) if not z["vendedor"] else (
                    ("zebra",) if i % 2 else ())
                self.tab_detalhe.insert(
                    "", "end", iid=z["zona"], tags=tags,
                    values=(z["codigo"], z["zona_nome"], z["uf"], dono, vinculo,
                            z["clientes"], z["cidades"],
                            inteira.get("clientes_dia", ""),
                            dinheiro(z["faturamento_mensal"]), z["comprantes"],
                            z["inadimplentes"], dinheiro(z["valor_atraso"])))
            reaplicar_ordem(self.tab_detalhe)
        finally:
            self._silencio = False

        nome_recorte = dict((c, t) for c, _, t in self.VISOES)[chave]
        total = sum(z["clientes"] for z in linhas)
        self.quadro_detalhe.configure(
            text=f" Zonas de {nome_recorte}: {rotulo} ")
        self.lbl_detalhe.configure(
            text=f"{rotulo}   |   {len(linhas)} zona(s)   |   {total} cliente(s)")
        if chave in ("vendedor", "supervisor", "gerente"):
            excecao = sum(1 for z in linhas if z["zona"] != nu.SEM_ZONA
                          and z["vendedor"]) - titulares
            quem = {"vendedor": "e dele", "supervisor": "e de um vendedor dele",
                    "gerente": "e de um vendedor da equipe dele"}[chave]
            pe = (f"titular = a zona {quem} na aba 2.  por excecao = so ha "
                  f"ali clientes trocados a mao no analitico.  "
                  f"{titulares} zona(s) titular, {excecao} por excecao.  "
                  f"CLI/DIA e o da zona inteira, com todos os vendedores.")
        else:
            pe = ("QTD CLI., FAT. e INAD. contam so os clientes desta linha "
                  "dentro de cada zona; CLI/DIA e o da zona inteira.")
        self.lbl_detalhe_pe.configure(text=pe)
        self._detalhe = (chave, iid)
        if not self.quadro_detalhe.winfo_ismapped():
            # com o quadro aberto a tabela de cima encolhe, para a legenda
            # do fim da aba nao sair da tela
            for t in self.visoes.values():
                t.configure(height=6)
            self.quadro_detalhe.pack(fill="x", pady=(10, 0),
                                     before=self.linha_legenda)

    def _fechar_detalhe(self):
        self._detalhe = None
        if self.quadro_detalhe.winfo_ismapped():
            self.quadro_detalhe.pack_forget()
            for t in self.visoes.values():
                t.configure(height=10)

    def _redesenhar_detalhe(self):
        """Depois de recalcular: refaz o detalhe aberto, se a linha ainda existe."""
        if not self._detalhe:
            return
        chave, iid = self._detalhe
        arvore = self.visoes.get(chave)
        if arvore is None or not arvore.exists(iid):
            self._fechar_detalhe()
            return
        self._silencio = True
        try:
            arvore.selection_set(iid)
        finally:
            self._silencio = False
        self._mostrar_detalhe(chave, iid)

    def _escrever_bap_total(self, du):
        t = self.resumo["total"]
        sem_vend = [r for r in self.resumo["zona"]
                    if r["clientes"] and not r["vendedor"]]
        estourou = [r for r in self.resumo["zona"]
                    if r["vendedor"] and not r.get("cabe", True)]
        vend_estourou = [r for r in self.resumo["vendedor"]
                         if r["vendedor"] and not r.get("cabe", True)]
        sem_zona = sum(1 for c in self.clientes
                       if not nu.zona_do_cliente(self.cfg, c))
        zonas_cfg = {z["id"]: z for z in self.cfg["zonas"]}
        seg_sem_vend = sum(
            1 for c in self.clientes
            if nu.zona_do_cliente(self.cfg, c) in zonas_cfg
            and nu.vendedores_da_zona(zonas_cfg[nu.zona_do_cliente(self.cfg, c)])
            and not nu.vendedor_do_cliente(self.cfg, c, zonas_cfg))
        linhas = [
            f"Mes ........................... "
            f"{nu.MESES_PT[int(self.cfg['mes'][5:7])]}/{self.cfg['mes'][:4]}"
            f"   ({du} dias uteis)",
            f"Clientes ...................... {t['clientes']:>12}",
            f"Cidades ....................... {t['cidades']:>12}",
            f"Bairros ....................... {t['bairros']:>12}",
            f"Vendedores com carteira ....... {t['qtd_vendedores']:>12}",
            f"Zonas com cliente ............. {t['qtd_zonas']:>12}",
            f"Cliente de segmento s/ vendedor {seg_sem_vend:>12}"
            + ("   (a zona tem vendedor, mas nenhum atende o segmento dele - "
               "aba 2)" if seg_sem_vend else ""),
            f"Clientes/dia (dia util) ....... {t['clientes_dia']:>12}",
            (f"Clientes/dia no sabado ........ {t['clientes_dia_sabado']:>12}"
             if t.get("clientes_dia_sabado") else ""),
            "",
            f"FAT. M6M (media mensal) ....... "
            f"R$ {dinheiro(t['faturamento_mensal']):>16}",
            f"FAT/CLIENTE COMPRANTE ......... "
            f"R$ {dinheiro(t['faturamento_por_comprante']):>16}",
            f"FAT. ACUMULADO ................ "
            f"R$ {dinheiro(t['receita_acumulada']):>16}",
            f"COMPRANTES (ate 90 dias) ...... {t['comprantes']:>12}   "
            f"({t['pct_comprantes']:.1f}% da base)",
            f"Ja compraram alguma vez ....... {t['compradores_historico']:>12}",
            "",
            f"Curva  S {t['curva_S']:>5}   A {t['curva_A']:>5}   "
            f"B {t['curva_B']:>5}   C {t['curva_C']:>5}   Z {t['curva_Z']:>6}",
            f"Status ATIVO {t['status_ATIVO']:>4}  CHURN30 {t['status_CHURN 30']:>4}  "
            f"CHURN60 {t['status_CHURN 60']:>4}  CHURN90 {t['status_CHURN 90']:>4}  "
            f"CHURN90+ {t['status_CHURN 90+']:>4}  NUNCA {t['status_NUNCA COMPROU']:>5}",
            "",
            f"Com limite .................... {t['com_limite']:>12}   "
            f"(R$ {dinheiro(t['limite_disponivel'])} disponivel)",
            f"Inadimplentes ................. {t['inadimplentes']:>12}   "
            f"R$ {dinheiro(t['valor_atraso'])}   "
            f"{t['pct_inadimplencia']:.1f}% da carteira",
            "",
            f"Zonas cadastradas ............. {len(self.cfg['zonas']):>12}",
            f"Zonas SEM vendedor ............ {len(sem_vend):>12}"
            + (f"   -> {', '.join(r['codigo'] for r in sem_vend)}"
               if sem_vend else ""),
            f"Clientes SEM zona ............. {sem_zona:>12}"
            + ("   -> cadastre a zona na aba 3" if sem_zona else ""),
        ]
        if vend_estourou:
            linhas += ["", "ATENCAO - A CARTEIRA NAO CABE NO MES",
                       "O teto de visitas por dia esta na aba 6. PARAMETROS.",
                       "A rota sai completa assim mesmo, com os dias acima do "
                       "teto - ninguem fica de fora."]
            for r in sorted(vend_estourou, key=lambda x: x["folga_dias"]):
                linhas.append(
                    f"   {r['vendedor']} {r['vendedor_nome'][:24]:<24} "
                    f"{r['clientes']:>5} cli x {r['visitas_mes'] // max(1, r['clientes'])} "
                    f"visita(s) = {r['visitas_mes']:>5} visitas   |   "
                    f"teto {r['capacidade_dia']}/dia -> precisa de "
                    f"{r['dias_necessarios']} dias, a agenda tem "
                    f"{r['dias_agenda']}   |   a rota ficou com "
                    f"{r['clientes_dia']}/dia")
        if estourou:
            linhas += ["", "As zonas apertadas:"]
            for r in estourou:
                linhas.append(f"   {r['codigo']}  {r['zona_nome'][:34]:<35} "
                              f"precisa de {r['dias_necessarios']} dias, "
                              f"a agenda tem {r['dias_agenda']}")
        self.txt_total.delete("1.0", "end")
        self.txt_total.insert("1.0", "\n".join(
            l for i, l in enumerate(linhas)
            if l or (i and linhas[i - 1])))

    # ---- exportar / importar o PLANNER ----------------------------------
    def exportar_modelo_agenda(self):
        """O AGENDA_CIDADES_<mes>.xlsx: uma aba por vendedor ativo do mes,
        com a lista das cidades da carteira em cada dia (ate 2 por dia).
        Vai para os supervisores; volta na hora de RECALCULAR/EXPORTAR."""
        if not self.clientes:
            messagebox.showinfo("Planner BAP",
                                "Nao ha base de clientes carregada.")
            return
        import agenda_cidades as ac                      # noqa: PLC0415
        destino = self.caminho("saida") / ac.nome_do_modelo(self.cfg["mes"])
        try:
            ac.modelo(self.cfg, self.clientes, destino)
        except PermissionError:
            messagebox.showerror("Planner BAP",
                                 f"{destino.name} esta aberto no Excel. "
                                 f"Feche e tente de novo.")
            return
        except Exception as erro:                        # noqa: BLE001
            messagebox.showerror("Planner BAP", str(erro))
            self.log(traceback.format_exc())
            return
        self.log(f"MODELO DE AGENDA DE CIDADE: {destino}")
        self.aviso(f"{destino.name} gravado.", COR_OK)
        if messagebox.askyesno("Planner BAP",
                               f"{destino.name}\n\nUma aba por vendedor "
                               f"ativo de {self.cfg['mes']}. Envie aos "
                               f"supervisores para escolherem as cidades de "
                               f"cada dia.\n\nGravado em:\n{destino.parent}"
                               f"\n\nAbrir agora?"):
            self._abrir(destino)

    def perguntar_agenda(self):
        """'IMPORTAR AGENDA?' antes de recalcular/exportar: SIM abre o Excel
        dos supervisores e cada vendedor preenchido vai para o calendario
        da aba ROTA POR CIDADE; quem ficou em branco segue o algoritmo."""
        if not self.clientes:
            return False
        if not messagebox.askyesno(
                "Planner BAP",
                "IMPORTAR AGENDA DE CIDADES DOS SUPERVISORES?\n\n"
                "SIM: escolha o Excel preenchido (pode ser mais de um).\n"
                "NAO: a rota sai com as regras normais."):
            return False
        return self.importar_agenda()

    def importar_agenda_e_recalcular(self):
        """O botao IMPORTAR AGENDA DE CIDADE: escolhe o Excel, grava o
        calendario e ja recalcula a rota (sem perguntar de novo)."""
        if not self.clientes:
            messagebox.showinfo("Planner BAP",
                                "Nao ha base de clientes carregada.")
            return
        if self.importar_agenda():
            self.recalcular_planner(agenda=False)

    def importar_agenda(self):
        """Escolhe o(s) Excel dos supervisores e grava o calendario de quem
        foi preenchido. True se entrou alguma coisa."""
        arqs = filedialog.askopenfilenames(
            title="Agenda de cidades dos supervisores",
            initialdir=str(self.caminho("saida")),
            filetypes=[("Excel", "*.xlsx")])
        if not arqs:
            return False
        import agenda_cidades as ac                      # noqa: PLC0415
        calendario, avisos, resumo = {}, [], {}
        for a in arqs:
            try:
                cal, av, rs = ac.ler(self.cfg, self.clientes, a)
            except Exception as erro:                    # noqa: BLE001
                avisos.append(f"{Path(a).name}: nao consegui ler ({erro})")
                continue
            calendario.update(cal)
            avisos += av
            resumo.update(rs)
        if not calendario:
            messagebox.showwarning(
                "Planner BAP",
                "Nenhum dia preenchido nos arquivos escolhidos - a rota sai "
                "com as regras normais."
                + ("\n\n" + "\n".join(avisos[:12]) if avisos else ""))
            return False
        ac.aplicar(self.cfg, calendario)
        self.salvar()
        try:
            self.recarregar_rota_cidade()
        except Exception:                                # noqa: BLE001
            pass
        quem = "\n".join(f"   {cod} {nome}: {n} dia(s)"
                         for cod, (nome, n) in sorted(resumo.items()))
        self.log(f"AGENDA DE CIDADES importada: {len(calendario)} "
                 f"vendedor(es)\n{quem}"
                 + ("\n  " + "\n  ".join(avisos) if avisos else ""))
        messagebox.showinfo(
            "Planner BAP",
            f"AGENDA IMPORTADA: {len(calendario)} vendedor(es).\n\n{quem}"
            f"\n\nQuem nao foi preenchido segue o algoritmo normal. Cidade "
            f"da carteira sem dia entra no dia mais perto com vaga; o que "
            f"passar do teto vai para o 1o sabado."
            + (f"\n\nNAO ENTROU ({len(avisos)}):\n" + "\n".join(avisos[:12])
               + ("\n..." if len(avisos) > 12 else "") if avisos else ""))
        return True

    def exportar_planner(self, perguntar=False):
        if perguntar:
            self.perguntar_agenda()
        if not self.clientes:
            messagebox.showinfo("Planner BAP",
                                "Nao ha base de clientes carregada.")
            return
        if not any(z.get("vendedor") for z in self.cfg["zonas"]):
            messagebox.showwarning("Planner BAP",
                                   "Nenhuma zona tem vendedor. Cadastre na "
                                   "aba 2 quais zonas sao de cada vendedor.")
            return
        destino = self.caminho("saida") / nu.nome_do_planner(
            mes=self.cfg["mes"])
        cfg = json.loads(json.dumps(self.cfg))
        clientes = self.clientes

        def pronto(resultado, erro):
            if erro:
                messagebox.showerror("Planner BAP", str(erro[0]))
                self.log(erro[1])
                self.aviso("Falhou ao exportar.", COR_ALERTA)
                return
            linhas, resumo = resultado
            zonas = len({r["COD_ZONA"] for r in linhas})
            self.log(f"PLANNER exportado: {destino} ({len(linhas)} visitas, "
                     f"{zonas} zonas)")
            # so o PLANNER do momento fica na RELATORIOS; os anteriores vao
            # para o BACKUP_RELATORIOS\BKP_RELATORIOS_PLANNER
            gerado = destino
            try:
                saiu = pb.aposentar_planners(AQUI, manter=destino.name)
                if saiu:
                    self.log(f"{saiu} PLANNER anterior(es) foram para "
                             f"{pb.BKP_PLANNER}.")
                if not destino.exists():     # mes que ja passou: backup
                    gerado = pb.planner_do_mes(AQUI, cfg["mes"]) or destino
            except OSError:
                pass
            self.aviso(f"{destino.name}: {len(linhas)} visitas.", COR_OK)
            if messagebox.askyesno(
                    "Planner BAP",
                    f"{destino.name}\n\n{len(linhas)} visitas | {zonas} zonas | "
                    f"{resumo['du']} dias uteis\n\nGravado em:\n"
                    f"{gerado.parent}\n\nAbrir agora?"):
                self._abrir(gerado)

        self._tarefa(lambda: nu.gravar_planner(cfg, clientes, destino), pronto,
                     f"Gerando {destino.name}...")

    def importar_planner(self):
        caminho = filedialog.askopenfilename(
            title="Importar arquivo do PLANNER",
            initialdir=str(self.caminho("saida")),
            filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not caminho:
            return
        if (self.cfg.get("zonas") or self.clientes) and not messagebox.askyesno(
                "Planner BAP",
                "Importar o PLANNER SUBSTITUI as zonas, a equipe, a lotacao "
                "das areas e a base de clientes que estao carregadas agora.\n\n"
                "Continuar?"):
            return

        def pronto(d, erro):
            if erro:
                messagebox.showerror("Planner BAP", str(erro[0]))
                self.log(erro[1])
                self.aviso("Falhou ao importar o PLANNER.", COR_ALERTA)
                return
            self.cfg["zonas"] = d["zonas"]
            self.cfg["pessoas"] = d["pessoas"]
            self.cfg["areas"] = d["areas"]
            self.cfg["excecoes"] = d.get("excecoes") or {}
            nu.normalizar_pessoas(self.cfg)
            self.clientes = d["clientes"]
            nu.aplicar_parametros(self.cfg, self.clientes)
            self.salvar()
            self._indexar()
            self.log(f"\nPLANNER importado: {Path(d['arquivo']).name}\n"
                     f"  {len(d['zonas'])} zonas | {len(d['pessoas'])} pessoas | "
                     f"{len(d['areas'])} areas | {len(d['clientes'])} clientes"
                     + (f" | {len(self.cfg['excecoes'])} cliente(s) fora da "
                        f"zona do bairro" if self.cfg["excecoes"] else ""))
            self.atualizar_tudo()
            self._pendente = False
            self._pintar_faixas()
            self.aviso(f"PLANNER importado: {len(d['clientes'])} clientes.", COR_OK)
            messagebox.showinfo(
                "Planner BAP",
                f"Importado de {Path(d['arquivo']).name}:\n\n"
                f"{len(d['zonas'])} zonas\n{len(d['pessoas'])} pessoas\n"
                f"{len(d['areas'])} areas (UF/cidade/bairro)\n"
                f"{len(d['clientes'])} clientes"
                + (f"\n{len(self.cfg['excecoes'])} cliente(s) fora da zona "
                   f"do bairro" if self.cfg["excecoes"] else ""))

        self._tarefa(lambda: nu.importar_planner(caminho), pronto,
                     "Importando o PLANNER...")

    # =================================================================== 2
    def _montar_pessoas(self):
        f = self.aba_pessoas
        self._faixa_recalcular(f)
        corpo_p = ttk.Frame(f)
        corpo_p.pack(fill="both", expand=True)
        f = corpo_p
        # o PAINEL DA DIREITA reserva a largura dele primeiro; a tabela
        # fica com o que sobra (ela tem rolagem lateral)
        dir_ = ttk.Frame(f, width=480)
        dir_.pack(side="right", fill="y", padx=(16, 0))
        dir_.pack_propagate(False)
        esq = ttk.Frame(f)
        esq.pack(side="left", fill="both", expand=True)
        ttk.Label(esq, text="Equipe cadastrada", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(esq, text="Para ALTERAR: clique na linha (ou marque e use "
                            "ALTERAR O SELECIONADO), mude o que precisa no "
                            "painel da direita e clique em SALVAR A "
                            "ALTERACAO. VENDEDOR e SUPERVISOR recebem zonas "
                            "na lista da direita.",
                  style="Sub.TLabel", wraplength=680).pack(anchor="w", pady=(0, 8))
        colunas = [("cargo", "CARGO", 88, "w", False),
                   ("situacao", "SITUACAO", 84, "center", False),
                   ("protheus", "PROTHEUS", 86, "w", False),
                   ("maxima", "MAXIMA", 72, "w", False),
                   ("nome", "NOME COMPLETO", 210, "w", True),
                   ("uf", "UF", 40, "center", False),
                   ("cidade", "CIDADE BASE", 100, "w", False),
                   ("interior", "INTERIOR", 64, "center", False),
                   ("chefe", "RESPONDE A", 150, "w", False),
                   ("zonas", "ZONAS", 190, "w", False),
                   ("segmentos", "SEGMENTOS", 90, "w", False)]
        quadro, self.tab_pessoas = tabela(esq, colunas)
        quadro.pack(fill="both", expand=True)
        self.tab_pessoas.bind("<<TreeviewSelect>>", self._pessoa_clicada)

        bp = ttk.Frame(esq)
        bp.pack(fill="x", pady=(6, 0))
        # ALTERAR nao tem botao: clicar na pessoa ja abre a ficha ao lado,
        # com o SALVAR A ALTERACAO embaixo
        ttk.Button(bp, text="Novo cadastro",
                   command=self.limpar_pessoa).pack(side="left")
        ttk.Button(bp, text="Excluir o selecionado",
                   command=self.excluir_pessoa).pack(side="left", padx=6)
        ttk.Button(bp, text="Replicar equipe do mês anterior",
                   command=self.replicar_equipe).pack(side="left")
        # (07/10) a equipe do mes num Excel (para mandar ao RH)
        ttk.Button(bp, text="Exportar equipe do mês",
                   command=self.exportar_equipe).pack(side="left", padx=6)
        ttk.Button(bp, text="Importar vendedores da base",
                   command=self.importar_vendedores).pack(side="right")
        self.lbl_pessoa_resumo = ttk.Label(esq, text="", style="Sub.TLabel",
                                           wraplength=680)
        self.lbl_pessoa_resumo.pack(anchor="w", pady=(6, 0))
        legenda_de_cores(esq, [
            (COR_AVISO, "codigo PROVISORIO (o programa inventou um numero a "
                        "partir de 901) - troque pelo Protheus de verdade"),
            (COR_INATIVO, "INATIVO: a cadeira esta VAGA - tem rota e meta, "
                          "mas nao conta como vendedor no gerencial"),
            (COR_SELECAO, "pessoa que voce esta editando agora"),
        ]).pack(anchor="w", pady=(8, 0))

        ttk.Label(dir_, text="Cadastro", style="Titulo.TLabel").pack(anchor="w")
        self.lbl_pessoa_sel = ttk.Label(dir_, text="Novo cadastro",
                                        style="Cod.TLabel", wraplength=460)
        self.lbl_pessoa_sel.pack(anchor="w", pady=(2, 8))

        # A FICHA em duas colunas (rotulo + campo, rotulo + campo): cabe
        # tudo sem espremer e sobra altura para a lista de zonas
        ficha = ttk.LabelFrame(dir_, text=" Dados da pessoa ", padding=(12, 8))
        ficha.pack(fill="x")

        def rotulo(txt, lin, col):
            r = ttk.Label(ficha, text=txt)
            r.grid(row=lin, column=col, sticky="w", pady=3,
                   padx=(0 if col == 0 else 12, 6))
            return r

        def caixa(var, lin, col, valores=None, span=1, combo=True):
            if combo:
                w = ttk.Combobox(ficha, textvariable=var, width=10,
                                 values=valores or [], state="readonly")
            else:
                w = ttk.Entry(ficha, textvariable=var, width=10)
            w.grid(row=lin, column=col, columnspan=span, sticky="we", pady=3)
            return w

        self.var_cargo = tk.StringVar(value="VENDEDOR")
        self.var_ativo = tk.StringVar(value="ATIVO")
        self.var_protheus, self.var_maxima = tk.StringVar(), tk.StringVar()
        self.var_nome_p = tk.StringVar()
        self.var_uf_base, self.var_cidade_base = tk.StringVar(), tk.StringVar()
        self.var_chefe = tk.StringVar()
        self.var_interior = tk.StringVar(value="NAO")
        self.var_email = tk.StringVar()
        self.var_casa = tk.StringVar()
        self.var_admissao = tk.StringVar()

        rotulo("Cargo", 0, 0)
        cb_cargo = caixa(self.var_cargo, 0, 1, nu.CARGOS)
        cb_cargo.bind("<<ComboboxSelected>>", lambda _: self._cargo_mudou())
        # ATIVO x INATIVO: a cadeira VAGA (vaga em aberto) e INATIVA
        rotulo("Situacao", 0, 2)
        self.cb_ativo = caixa(self.var_ativo, 0, 3, ["ATIVO", "INATIVO"])

        rotulo("Cod. Protheus", 1, 0)
        caixa(self.var_protheus, 1, 1, combo=False)
        rotulo("Cod. Maxima", 1, 2)
        caixa(self.var_maxima, 1, 3, combo=False)

        rotulo("Nome", 2, 0)
        caixa(self.var_nome_p, 2, 1, span=3, combo=False)

        rotulo("UF base", 3, 0)
        cb_uf = caixa(self.var_uf_base, 3, 1, nu.UF_BASE)
        cb_uf.bind("<<ComboboxSelected>>", lambda _: self._uf_base_mudou())
        rotulo("Cidade base", 3, 2)
        self.cb_cidade_base = caixa(self.var_cidade_base, 3, 3)

        self.lbl_chefe = rotulo("Supervisor", 4, 0)
        self.cb_chefe = caixa(self.var_chefe, 4, 1, span=3)

        # VENDEDOR DO INTERIOR: muda a forma de montar a rota dele - por
        # CIDADE, um dia uma cidade so, ate o teto de visitas por dia
        self.lbl_interior = rotulo("Interior", 5, 0)
        self.cb_interior = caixa(self.var_interior, 5, 1, ["NAO", "SIM"])
        # UMA ajuda so para a ficha toda (vira um 'i' com dica no app)
        self.lbl_interior_ajuda = ttk.Label(
            ficha, style="Sub.TLabel", wraplength=200,
            text="INTERIOR = SIM: a rota dele e montada POR CIDADE (um dia, "
                 "uma cidade, ate o teto de visitas por dia da aba 6). "
                 "INATIVO = a cadeira esta VAGA: rota e meta continuam, mas "
                 "ele nao conta como vendedor no resumo gerencial (fica fora "
                 "do QTD VDE e a zona vai para ZONAS S/ VDE). Contabilizar "
                 "para a meta do supervisor e no Gerador de Meta, aba QUEM "
                 "CONTA NA META, mes a mes.")
        self.lbl_interior_ajuda.grid(row=5, column=2, columnspan=2,
                                     sticky="w", padx=(12, 0))
        # E-MAIL: para onde o Farol de Metas manda a parcial da pessoa
        rotulo("E-mail", 6, 0)
        caixa(self.var_email, 6, 1, span=3, combo=False)
        # (22/10, Alexandre) a caixa MES DE CASA saiu da ficha: fica so a
        # DATA DE ADMISSAO. O mes de casa continua sendo calculado dela (meta
        # e relatorios); self.var_casa ficou escondida so para guardar o
        # valor antigo de quem nao tem admissao.
        # (18/10) DATA DE ADMISSAO: o mes de casa e a proporcao do primeiro
        # mes saem dela
        rotulo("Admissão", 7, 0)
        caixa(self.var_admissao, 7, 1, combo=False)
        self.lbl_admissao = ttk.Label(
            ficha, style="Sub.TLabel", wraplength=260,
            text="DD/MM/AAAA · o mês de casa e a proporção do 1º mês saem "
                 "daqui (automático)")
        self.var_admissao.trace_add("write",
                                    lambda *_: self._casa_pela_admissao())
        self.lbl_admissao.grid(row=7, column=2, columnspan=2, sticky="w",
                               padx=(12, 0))
        ficha.columnconfigure(1, weight=1)
        ficha.columnconfigure(3, weight=1)

        # O BOTAO DE GRAVAR VEM ANTES DA LISTA DE ZONAS no empacotamento:
        # com side="bottom" ele reserva o lugar dele primeiro, e a lista
        # fica com o que sobra. Antes era o contrario, e em tela de 1050
        # de altura o botao acabava cortado - parecia que so dava para
        # incluir e excluir, nunca alterar.
        self.lbl_pessoa_msg = ttk.Label(dir_, text="", style="Sub.TLabel",
                                        wraplength=460)
        self.lbl_pessoa_msg.pack(side="bottom", anchor="w", pady=(6, 0))
        self.bt_salvar_pessoa = ttk.Button(
            dir_, text="SALVAR O CADASTRO", style="Big.TButton",
            command=self.salvar_pessoa)
        self.bt_salvar_pessoa.pack(side="bottom", fill="x", pady=(10, 2))

        # ---- as zonas do vendedor ---------------------------------------
        self.quadro_zonas_p = ttk.LabelFrame(dir_, padding=(10, 6, 10, 10))
        self.quadro_zonas_p.pack(fill="both", expand=True, pady=(10, 0))
        self.lbl_quadro_zonas = self._titulo_de_quadro(
            self.quadro_zonas_p, "Zonas deste vendedor",
            "Marque as zonas que serao dele. Segure Ctrl para "
                       "marcar varias. No SUPERVISOR, as zonas da equipe ja "
                       "vem marcadas; marque as demais. Os clientes delas que "
                       "nao sao de um vendedor dele somam no RESULTADO dele "
                       "(a meta nao muda). A zona AMARELA ainda nao tem "
                       "vendedor nenhum.")
        corpo = ttk.Frame(self.quadro_zonas_p)
        corpo.pack(fill="both", expand=True)
        self.lb_zonas_p = tk.Listbox(corpo, selectmode="extended", height=12,
                                     exportselection=False, activestyle="none",
                                     font=("Segoe UI", 9), relief="flat",
                                     borderwidth=0, highlightthickness=1,
                                     highlightbackground=COR_LINHA,
                                     highlightcolor=COR_ACENTO,
                                     background=COR_PAPEL, foreground=COR_TEXTO,
                                     selectbackground=COR_ACENTO,
                                     selectforeground="white")
        # no supervisor as zonas da equipe sao fixas: nao desmarcam
        self.lb_zonas_p.bind("<<ListboxSelect>>",
                             lambda _: self._manter_zonas_da_equipe())
        sv = ttk.Scrollbar(corpo, orient="vertical", command=self.lb_zonas_p.yview)
        self.lb_zonas_p.configure(yscrollcommand=sv.set)
        self.lb_zonas_p.pack(side="left", fill="both", expand=True)
        sv.pack(side="left", fill="y")

        # ---- os SEGMENTOS que ele atende nas zonas marcadas -------------
        # Dois vendedores podem dividir a mesma zona, cada um com os seus
        # segmentos - o mesmo segmento nunca fica com dois na mesma zona.
        # Nenhum marcado = TODOS os segmentos que ninguem mais pegou ali.
        self.quadro_segs_p = ttk.LabelFrame(dir_, padding=(8, 4, 8, 8))
        self.lbl_segs_p = self._titulo_de_quadro(
            self.quadro_segs_p, "Segmentos que ele atende nessas zonas",
            "Nenhum marcado = TODOS os segmentos que ninguem mais atende "
            "na zona. O mesmo segmento nao pode ter dois vendedores na "
            "mesma zona.")
        self.quadro_segs_p.pack(side="bottom", fill="x", pady=(8, 0),
                                after=self.bt_salvar_pessoa)
        grade = ttk.Frame(self.quadro_segs_p)
        grade.pack(fill="x")
        self.var_segs_p = {}
        self.chk_segs_p = []
        for i, seg in enumerate(nu.SEGMENTOS):
            var = tk.BooleanVar(value=False)
            chk = ttk.Checkbutton(grade, text=seg, variable=var)
            chk.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 10))
            self.var_segs_p[seg] = var
            self.chk_segs_p.append(chk)

        self._modo_do_cadastro(False)
        self._cargo_mudou()

    def _cargo_mudou(self):
        cargo = self.var_cargo.get()
        if cargo == "VENDEDOR":
            alvo, rotulo = "SUPERVISOR", "Supervisor"
        elif cargo == "SUPERVISOR":
            alvo, rotulo = "GERENTE", "Gerente"
        else:
            alvo, rotulo = None, "Responde a"
        self.lbl_chefe.configure(text=rotulo)
        if alvo is None:
            self.cb_chefe.configure(values=["(ninguem)"], state="disabled")
            self.var_chefe.set("(ninguem)")
        else:
            opcoes = ["(nenhum)"] + [nu.rotulo_pessoa(p) for p in
                                     sorted(nu.pessoas_do_cargo(self.cfg, alvo),
                                            key=lambda x: x["nome"])]
            self.cb_chefe.configure(values=opcoes, state="readonly")
            if self.var_chefe.get() not in opcoes:
                self.var_chefe.set("(nenhum)")
        # so vendedor tem zona - e so ele tem rota, entao so nele faz
        # sentido a marca de VENDEDOR DO INTERIOR
        vendedor = cargo == "VENDEDOR"
        com_zona = cargo in ("VENDEDOR", "SUPERVISOR")
        self.cb_interior.configure(state="readonly" if vendedor else "disabled")
        if not vendedor:
            self.var_interior.set("NAO")
        self.lbl_quadro_zonas.configure(
            text=" Zonas do supervisor " if cargo == "SUPERVISOR"
            else " Zonas deste vendedor ")
        self.lb_zonas_p.configure(state="normal" if com_zona else "disabled")
        if not com_zona:
            self.lb_zonas_p.selection_clear(0, "end")
        for chk in getattr(self, "chk_segs_p", []):
            chk.configure(state="normal" if vendedor else "disabled")
        # SEGMENTO so existe no vendedor: nos outros o quadro some e a
        # lista de zonas ganha a altura
        if hasattr(self, "quadro_segs_p"):
            if vendedor:
                self.quadro_segs_p.pack(side="bottom", fill="x", pady=(8, 0),
                                        after=self.bt_salvar_pessoa)
            else:
                self.quadro_segs_p.pack_forget()
        self._carregar_zonas_da_pessoa()

    def _uf_base_mudou(self):
        # (17/10) a lista e a das cidades da BASE DE CLIENTES daquela UF
        cidades = nu.cidades_da_uf(self.var_uf_base.get(), self.clientes)
        self.cb_cidade_base.configure(values=cidades)
        if self.var_cidade_base.get() not in cidades:
            self.var_cidade_base.set(cidades[0] if cidades else "")

    @staticmethod
    def _titulo_de_quadro(quadro, titulo, ajuda):
        """Titulo da moldura com a ajuda NA MESMA LINHA (no app ela vira
        um 'i' com dica) - nao gasta uma linha do quadro."""
        cab = tk.Frame(quadro, background=COR_PAPEL)
        rot = ttk.Label(cab, text=f" {titulo} ", style="TLabelframe.Label")
        rot.pack(side="left")
        tk.Label(cab, text=ajuda, background=COR_PAPEL, foreground=COR_SUAVE,
                 font=("Segoe UI", 8), wraplength=300, justify="left"
                 ).pack(side="left", padx=(4, 4))
        quadro.configure(labelwidget=cab)
        return rot

    def _manter_zonas_da_equipe(self):
        for i in getattr(self, "_idx_equipe", ()):
            self.lb_zonas_p.selection_set(i)

    def _carregar_zonas_da_pessoa(self):
        """Enche a lista de zonas e marca as que ja sao desta pessoa."""
        self._zonas_lista = sorted(self.cfg["zonas"],
                                   key=lambda z: z.get("codigo") or "ZZZ")
        self.lb_zonas_p.configure(state="normal")
        self.lb_zonas_p.delete(0, "end")
        cod_agora = getattr(self, "_editando", None)
        nomes = {p["cod_protheus"]: p["nome"] for p in self.cfg["pessoas"]}
        # as zonas dos vendedores do supervisor: por padrao sao dele
        self._zonas_equipe = (nu.zonas_da_equipe(self.cfg, cod_agora)
                              if self.var_cargo.get() == "SUPERVISOR" else set())
        self._idx_equipe = [i for i, z in enumerate(self._zonas_lista)
                            if z["id"] in self._zonas_equipe]
        for i, z in enumerate(self._zonas_lista):
            qtd = self.contagem_zona.get(z["id"], 0)
            # quem mais esta na zona, com os segmentos de cada um
            outros = [f"{nomes.get(a['vendedor'], a['vendedor']).split(' ')[0]}"
                      f" {nu.rotulo_segmentos(a['segmentos'])}"
                      for a in nu.atendimento_da_zona(z)
                      if a["vendedor"] != cod_agora]
            # (08/10) no supervisor: a zona que ja e de outro supervisor
            # aparece com o nome dele (nao pode ser marcada aqui)
            dono = (nu.supervisor_da_zona(self.cfg, z["id"], cod_agora)
                    if self.var_cargo.get() == "SUPERVISOR"
                    and z["id"] not in self._zonas_equipe else {})
            self.lb_zonas_p.insert("end", f"{z.get('codigo','')}  "
                                          + ("· EQUIPE ·  " if z["id"] in
                                             self._zonas_equipe else "")
                                          + (f"· SUP. {nu.texto(dono.get('nome')).split(' ')[0]}"
                                             f" {nu.texto(dono.get('nome')).split(' ')[-1]} ·  "
                                             if dono else "")
                                          + f"{z['nome']}"
                                          f"   ({qtd} cli.)"
                                   + (f"   [{'; '.join(outros)}]" if outros else ""))
            # A ZONA SEM VENDEDOR FICA AMARELA, igual na aba 3: ela nao
            # entra na rota enquanto ninguem a pegar.
            if not nu.vendedores_da_zona(z):
                self.lb_zonas_p.itemconfigure(i, background=COR_AVISO)
        cod = cod_agora
        segs_dele = set()
        if cod and self.var_cargo.get() == "VENDEDOR":
            for i, z in enumerate(self._zonas_lista):
                segs = nu.segmentos_na_zona(z, cod)
                if segs is not None:
                    self.lb_zonas_p.selection_set(i)
                    segs_dele |= set(segs)
        for seg, var in getattr(self, "var_segs_p", {}).items():
            var.set(seg in segs_dele)
        if self.var_cargo.get() == "SUPERVISOR":
            p = nu.pessoa_por_codigo(self.cfg, cod) if cod else None
            dele = set((p or {}).get("zonas_supervisor") or []) \
                | self._zonas_equipe
            for i, z in enumerate(self._zonas_lista):
                if z["id"] in dele:
                    self.lb_zonas_p.selection_set(i)
        elif self.var_cargo.get() != "VENDEDOR":
            self.lb_zonas_p.selection_clear(0, "end")
            self.lb_zonas_p.configure(state="disabled")
        marcadas = self.lb_zonas_p.curselection()
        if marcadas:                 # a lista abre ja nas zonas dele
            self.lb_zonas_p.see(marcadas[-1])
            self.lb_zonas_p.see(marcadas[0])

    def exportar_equipe(self):
        """(07/10) EQUIPE_BAP_<mes>.xlsx: a equipe cadastrada do mes (a mesma
        lista da tela) com codigo do supervisor, e-mail, meses de casa e
        clientes na carteira - para mandar ao RH."""
        from openpyxl import Workbook                    # noqa: PLC0415
        from openpyxl.styles import Font, PatternFill    # noqa: PLC0415
        mes = self.cfg.get("mes", "")
        cab = ["MÊS", "CARGO", "SITUAÇÃO", "CÓD. PROTHEUS", "CÓD. MÁXIMA",
               "NOME", "UF", "CIDADE BASE", "INTERIOR", "CÓD. SUPERVISOR",
               "SUPERVISOR (RESPONDE A)", "E-MAIL", "MÊS DE CASA", "ZONAS",
               "SEGMENTOS", "CLIENTES NA CARTEIRA", "ADMISSÃO"]
        wb = Workbook()
        ws = wb.active
        ws.title = "EQUIPE"
        ws.append(cab)
        for j in range(1, len(cab) + 1):
            c = ws.cell(1, j)
            c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
            c.fill = PatternFill("solid", fgColor="2F7D32")
        n = 0
        for iid in self.tab_pessoas.get_children():
            v = list(self.tab_pessoas.item(iid, "values"))
            p = nu.pessoa_por_codigo(self.cfg, iid) or {}
            chefe = nu.chefe_de(self.cfg, iid)
            cli = (len(nu.clientes_do_vendedor(self.cfg, self.clientes, iid))
                   if self.clientes and p.get("cargo") == "VENDEDOR" else "")
            ws.append([mes, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                       nu.texto(chefe.get("cod_protheus")), v[8],
                       nu.texto(p.get("email")),
                       nu.mes_de_casa_no_mes(p, mes) or "", v[9], v[10], cli,
                       (f"{nu.data_admissao(p):%d/%m/%Y}"
                        if nu.data_admissao(p) else "")])
            n += 1
        for j, w in enumerate((9, 12, 10, 13, 12, 38, 5, 16, 9, 15, 34, 30,
                               11, 26, 30, 12, 12), start=1):
            ws.column_dimensions[ws.cell(1, j).column_letter].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial", size=10)
                c.number_format = "@" if c.column in (4, 5, 10) else "General"
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        destino = self.caminho("saida") / f"EQUIPE_BAP_{mes}.xlsx"
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            wb.save(destino)
        except PermissionError:
            messagebox.showerror("Planner BAP", f"{destino.name} está aberto "
                                 f"no Excel. Feche e tente de novo.")
            return
        self.log(f"Equipe do mês exportada: {destino} ({n} pessoas)")
        self.aviso(f"{destino.name} gravado.", COR_OK)
        if messagebox.askyesno("Planner BAP", f"{destino.name}\n\n{n} "
                               f"pessoa(s) da equipe de {mes}.\n\nGravado "
                               f"em:\n{destino.parent}\n\nAbrir agora?"):
            self._abrir(destino)

    def desenhar_pessoas(self):
        marcada = self.tab_pessoas.selection()
        ordem = {"GERENTE": 0, "SUPERVISOR": 1, "VENDEDOR": 2}
        zonas_de = defaultdict(list)
        segs_de = defaultdict(set)
        todos_de = set()
        cod_da_zona = {z["id"]: z.get("codigo", "") for z in self.cfg["zonas"]}
        for p in self.cfg["pessoas"]:
            if p.get("cargo") == "SUPERVISOR":
                zonas_de[p["cod_protheus"]] += sorted({
                    cod_da_zona.get(z, z) for z in
                    set(p.get("zonas_supervisor") or [])
                    | nu.zonas_da_equipe(self.cfg, p["cod_protheus"])})
        for z in self.cfg["zonas"]:
            for a in nu.atendimento_da_zona(z):
                zonas_de[a["vendedor"]].append(z.get("codigo", ""))
                if a["segmentos"]:
                    segs_de[a["vendedor"]] |= set(a["segmentos"])
                else:
                    todos_de.add(a["vendedor"])
        self._silencio = True
        try:
            self.tab_pessoas.delete(*self.tab_pessoas.get_children())
            for i, p in enumerate(sorted(self.cfg["pessoas"],
                                         key=lambda x: (ordem.get(x["cargo"], 9),
                                                        x["nome"]))):
                chefe = nu.chefe_de(self.cfg, p["cod_protheus"]).get("nome", "")
                provisorio = p.get("provisorio") or not p["cod_protheus"].isdigit()
                inativo = p.get("ativo") is False
                # o CINZA do inativo manda mais que o amarelo do codigo
                # provisorio: a cadeira vaga e a informacao mais forte
                tags = (("inativo",) if inativo else ("aviso",) if provisorio
                        else ("zebra",) if i % 2 else ())
                self.tab_pessoas.insert(
                    "", "end", iid=p["cod_protheus"], tags=tags,
                    values=(p["cargo"], "INATIVO" if inativo else "ATIVO",
                            p["cod_protheus"], p["cod_maxima"],
                            p["nome"], p["uf_base"], p["cidade_base"],
                            (("SIM" if p.get("interior") else "-")
                             if p["cargo"] == "VENDEDOR" else "-"),
                            chefe or "-",
                            ", ".join(sorted(zonas_de.get(p["cod_protheus"], []))) or "-",
                            ("TODOS" if p["cod_protheus"] in todos_de
                             and not segs_de.get(p["cod_protheus"])
                             else ", ".join(s for s in nu.SEGMENTOS
                                            if s in segs_de.get(p["cod_protheus"], ()))
                             or ("-" if p["cargo"] != "VENDEDOR"
                                 or not zonas_de.get(p["cod_protheus"]) else "TODOS"))))
            for m in marcada:
                if self.tab_pessoas.exists(m):
                    self.tab_pessoas.selection_set(m)
        finally:
            self._silencio = False
        self._carregar_zonas_da_pessoa()
        ativos = [p for p in self.cfg["pessoas"] if p.get("ativo") is not False]
        contagem = Counter(p["cargo"] for p in ativos)
        inativos = [p for p in self.cfg["pessoas"] if p.get("ativo") is False]
        provisorios = [p for p in self.cfg["pessoas"]
                       if p.get("provisorio") or not p["cod_protheus"].isdigit()]
        texto = (f"{contagem.get('GERENTE',0)} gerente(s), "
                 f"{contagem.get('SUPERVISOR',0)} supervisor(es), "
                 f"{contagem.get('VENDEDOR',0)} vendedor(es) ATIVO(s)"
                 + (f" - e {len(inativos)} INATIVO(s), que sao cadeira vaga "
                    f"e nao contam no resumo gerencial." if inativos else "."))
        if provisorios:
            texto += (f"   {len(provisorios)} com codigo PROVISORIO (amarelo): "
                      + ", ".join(p["cod_protheus"] for p in provisorios)
                      + " - troque pelo codigo Protheus de verdade.")
        self.lbl_pessoa_resumo.configure(
            text=texto, foreground=(COR_ALERTA if provisorios else COR_OK))

    def _pessoa_clicada(self, _=None):
        if self._silencio:
            return
        sel = self.tab_pessoas.selection()
        if not sel:
            return
        p = nu.pessoa_por_codigo(self.cfg, sel[0])
        if not p:
            return
        self._editando = p["cod_protheus"]
        self.lbl_pessoa_sel.configure(text=f"Editando: {p['nome']}")
        self._modo_do_cadastro(True)
        self.var_cargo.set(p["cargo"])
        self.var_protheus.set(p["cod_protheus"])
        self.var_maxima.set(p["cod_maxima"])
        self.var_nome_p.set(p["nome"])
        self.var_email.set(p.get("email", ""))
        self.var_casa.set(str(p.get("meses_de_casa") or ""))
        _adm = nu.data_admissao(p)
        self.var_admissao.set(f"{_adm:%d/%m/%Y}" if _adm else "")
        _mes = self.cfg.get("mes") or ""
        if _adm and nu.casa_pela_admissao(_mes):
            _n = nu.mes_de_casa_no_mes(p, _mes)
            self.var_casa.set(str(_n or ""))
        self.var_uf_base.set(p["uf_base"])
        self._uf_base_mudou()
        self.var_cidade_base.set(p["cidade_base"])
        self.var_interior.set("SIM" if p.get("interior") else "NAO")
        # conta_supervisor nao e mais editado aqui (foi para o Gerador de
        # Meta, por mes); o valor antigo e guardado como estava
        self._conta_sup = p.get("conta_supervisor", True) is not False
        self.var_ativo.set("INATIVO" if p.get("ativo") is False else "ATIVO")
        chefe = nu.chefe_de(self.cfg, p["cod_protheus"])
        self._cargo_mudou()
        self.var_chefe.set(nu.rotulo_pessoa(chefe) if chefe else "(nenhum)")
        self.lbl_pessoa_msg.configure(text="")

    def alterar_pessoa(self):
        """
        Traz para o painel da direita quem esta marcado na tabela. Clicar
        na linha ja faz isso; o botao existe porque nem todo mundo
        descobre o clique - e ele deixa claro que ALTERAR e uma das
        opcoes, nao so incluir e excluir.
        """
        sel = self.tab_pessoas.selection()
        if not sel:
            messagebox.showinfo("Planner BAP",
                                "Marque na tabela quem voce quer alterar.")
            return
        self._pessoa_clicada()
        self.tab_pessoas.see(sel[0])
        try:
            self.bt_salvar_pessoa.focus_set()
        except Exception:
            pass

    def _modo_do_cadastro(self, editando: bool):
        """O botao diz o que ele vai fazer - incluir ou alterar."""
        self.bt_salvar_pessoa.configure(
            text="SALVAR A ALTERACAO" if editando else "INCLUIR O CADASTRO")

    def limpar_pessoa(self):
        self._editando = None
        self._silencio = True
        try:
            self.tab_pessoas.selection_remove(*self.tab_pessoas.selection())
        finally:
            self._silencio = False
        self.lbl_pessoa_sel.configure(text="Novo cadastro")
        self._modo_do_cadastro(False)
        self.var_cargo.set("VENDEDOR")
        for v in (self.var_protheus, self.var_maxima, self.var_nome_p,
                  self.var_uf_base, self.var_cidade_base, self.var_email,
                  self.var_casa, self.var_admissao):
            v.set("")
        self.cb_cidade_base.configure(values=[])
        self.var_interior.set("NAO")
        self._conta_sup = True
        self.var_ativo.set("ATIVO")
        self.var_chefe.set("(nenhum)")
        self._cargo_mudou()
        self.lbl_pessoa_msg.configure(text="")

    def _casa_pela_admissao(self):
        """(20/10) Admissao preenchida: o MES DE CASA do mes do Planner sai
        dela. (22/10) Sem a caixa na tela: so guarda o numero na variavel
        escondida (o salvar faz a mesma conta)."""
        adm = nu.data_admissao({"data_admissao":
                                self.var_admissao.get().strip()})
        mes_ = self.cfg.get("mes") or ""
        if adm is not None and nu.casa_pela_admissao(mes_):
            n_ = nu.mes_de_casa_no_mes({"data_admissao": adm.isoformat()},
                                       mes_)
            self.var_casa.set(str(n_) if n_ else "")

    def salvar_pessoa(self):
        nome = self.var_nome_p.get().strip()
        cod = self.var_protheus.get().strip()
        if not nome:
            messagebox.showwarning("Planner BAP", "O nome e obrigatorio.")
            return
        if not cod:
            messagebox.showwarning("Planner BAP",
                                   "O codigo Protheus e obrigatorio - e ele "
                                   "que liga a pessoa a zona e ao PLANNER.")
            return
        email = self.var_email.get().strip().lower()
        if email and not nu.email_valido(email):
            messagebox.showwarning("Planner BAP",
                                   f"O e-mail '{email}' nao parece valido.")
            return
        # (22/10) sem a caixa na tela: o mes de casa vem da admissao (abaixo)
        # ou fica o que ja estava gravado
        casa_txt = self.var_casa.get().strip()
        casa = int(casa_txt) if casa_txt.isdigit() else 0
        adm_txt = self.var_admissao.get().strip()
        adm = nu.data_admissao({"data_admissao": adm_txt}) if adm_txt else None
        if adm_txt and adm is None:
            messagebox.showwarning("Planner BAP",
                                   "Data de admissão: escreva DD/MM/AAAA "
                                   "(ex.: 01/04/2026) ou deixe vazio.")
            return
        mes_ = self.cfg.get("mes") or ""
        if adm is not None and nu.casa_pela_admissao(mes_):
            casa = nu.mes_de_casa_no_mes({"data_admissao": adm.isoformat()},
                                         mes_)
        antigo = getattr(self, "_editando", None)
        antes = _sem_email(self.cfg)     # mudou SO o e-mail? nao recalcula
        if cod != antigo and nu.pessoa_por_codigo(self.cfg, cod):
            messagebox.showwarning("Planner BAP",
                                   f"O codigo Protheus {cod} ja esta em uso.")
            return
        # zonas e SEGMENTOS do vendedor: o mesmo segmento nao pode ter dois
        # vendedores na mesma zona - confere antes de gravar qualquer coisa
        zonas_sup = []
        if self.var_cargo.get() == "VENDEDOR":
            marcadas = {self._zonas_lista[i]["id"]
                        for i in self.lb_zonas_p.curselection()}
            segmentos = [sg for sg, var in self.var_segs_p.items() if var.get()]
        else:
            marcadas, segmentos = set(), []
            if self.var_cargo.get() == "SUPERVISOR":
                # as zonas que o SUPERVISOR atende: nao mexem na rota nem
                # na carteira dos vendedores - so somam no resultado dele
                # (as da equipe ja sao dele por padrao: grava so as demais)
                zonas_sup = sorted(
                    self._zonas_lista[i]["id"]
                    for i in self.lb_zonas_p.curselection()
                    if self._zonas_lista[i]["id"] not in
                    getattr(self, "_zonas_equipe", set()))
        if zonas_sup:
            # (08/10) a zona tem UM supervisor so: se ja e de outro (pela
            # equipe dele ou cadastrada na ficha dele), nao grava
            dup = nu.conflitos_de_zona_supervisor(self.cfg, antigo or cod,
                                                  zonas_sup)
            if dup:
                messagebox.showwarning(
                    "Planner BAP",
                    "Nao da para gravar: cada zona tem um supervisor so.\n\n"
                    + "\n".join(dup[:12]) + ("\n..." if len(dup) > 12 else "")
                    + "\n\nDesmarque essas zonas (ou tire-as do outro "
                    "supervisor antes).")
                return
        conflitos = nu.conflitos_de_atendimento(
            self.cfg, cod, marcadas, segmentos, ignorar={antigo} if antigo else ())
        if conflitos:
            messagebox.showwarning(
                "Planner BAP",
                "Nao da para gravar: o mesmo segmento nao pode ter dois "
                "vendedores na mesma zona.\n\n" + "\n".join(conflitos[:12])
                + ("\n..." if len(conflitos) > 12 else "")
                + "\n\nTire o segmento de um dos dois (ou desmarque a zona).")
            return
        escolha = self.var_chefe.get()
        chefe = "" if escolha in ("(nenhum)", "(ninguem)", "") \
            else escolha.split(" - ")[0]
        if chefe == cod:
            chefe = ""
        registro = {
            "cod_protheus": cod, "cod_maxima": self.var_maxima.get().strip(),
            "nome": nome, "cargo": self.var_cargo.get(),
            "email": email,
            **({"meses_de_casa": casa} if casa else {}),
            **({"data_admissao": adm.isoformat()} if adm else {}),
            "uf_base": self.var_uf_base.get(),
            "cidade_base": self.var_cidade_base.get(),
            "responde_a": chefe,
            "ativo": self.var_ativo.get() != "INATIVO",
            "provisorio": False,
            # so vendedor tem rota, entao so nele a marca do interior vale
            "interior": (self.var_cargo.get() == "VENDEDOR"
                         and self.var_interior.get() == "SIM"),
            # so continua gravado para o Gerador de Meta usar como
            # semente do PRIMEIRO mes; quem decide e a aba QUEM CONTA NA
            # META, mes a mes
            "conta_supervisor": (self.var_cargo.get() != "VENDEDOR"
                                 or getattr(self, "_conta_sup", True)),
        }
        if zonas_sup:
            registro["zonas_supervisor"] = zonas_sup
        if antigo:
            for i, p in enumerate(self.cfg["pessoas"]):
                if p["cod_protheus"] == antigo:
                    self.cfg["pessoas"][i] = registro
                    break
            if cod != antigo:
                for p in self.cfg["pessoas"]:
                    if p["responde_a"] == antigo:
                        p["responde_a"] = cod
                nu.trocar_codigo_no_atendimento(self.cfg, antigo, cod)
            acao = "atualizado"
        else:
            self.cfg["pessoas"].append(registro)
            acao = "cadastrado"
        self._editando = cod

        # as zonas marcadas passam a ser dele, com os segmentos marcados;
        # das desmarcadas ele sai (os outros vendedores da zona ficam)
        nu.definir_atendimento(self.cfg, cod, marcadas, segmentos)

        self.salvar()
        # o e-mail vale em todos os meses (e no Farol de Metas) na hora
        try:
            nu.propagar_email(AQUI, cod, email,
                              codigos_antigos=[antigo] if antigo else ())
        except OSError as erro:
            self.log(f"Nao gravei o e-mail nos outros meses: {erro}")
        if _sem_email(self.cfg) == antes:
            # so o e-mail: nao mexe em rota, meta nem resumo - vale na hora,
            # sem Recalcular Planner
            self.desenhar_pessoas()
            msg = (f"{nome}: e-mail ({email or 'sem e-mail'}) gravado. "
                   f"Vale na hora - não precisa Recalcular Planner.")
            # depois da selecao (que limpa a mensagem ao redesenhar)
            self.after(120, lambda: self.lbl_pessoa_msg.configure(
                text=msg, foreground=COR_OK))
            self.aviso(f"E-mail de {nome} gravado.", COR_OK)
            return
        self._ger_sujo = True
        self.marcar_pendente()
        self.desenhar_pessoas()
        self.lbl_pessoa_sel.configure(text=f"Editando: {nome}")
        self._modo_do_cadastro(True)
        zonas_txt = (f" com {len(marcadas)} zona(s) - segmentos: "
                     f"{nu.rotulo_segmentos(segmentos)}." if marcadas
                     else " (sem zona por enquanto)."
                     if registro["cargo"] == "VENDEDOR"
                     else f" - zonas da equipe + {len(zonas_sup)} cadastrada(s)."
                     if zonas_sup else " - zonas da equipe.")
        self.lbl_pessoa_msg.configure(
            text=f"{registro['cargo'].capitalize()} {nome} {acao}{zonas_txt}",
            foreground=COR_OK)
        self.aviso(f"{nome} {acao}.", COR_OK)

    def replicar_equipe(self):
        """
        A EQUIPE DO MES ANTERIOR NESTE MES: as pessoas (cargo, codigos,
        supervisor, situacao, interior, e-mail...) e quem atende cada zona
        (vendedor e segmentos), nas zonas que existem nos dois meses. As
        zonas, areas, excecoes e parametros deste mes ficam como estao.
        Antes, a configuracao deste mes vai para o backup.
        """
        mes = self.cfg.get("mes") or ""
        if not mes:
            return
        a, m = int(mes[:4]), int(mes[5:7])
        ant = f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"
        arq = pb.config_do_mes(AQUI, ant)
        if not arq.exists():
            messagebox.showinfo("Planner BAP",
                                f"Nao ha configuracao de {ant[5:]}/{ant[:4]} "
                                f"em {pb.PLANNER_MESES} para replicar.")
            return
        velho = nu.carregar_config(arq)
        atual = {p["cod_protheus"]: p for p in self.cfg["pessoas"]}
        antes = {p["cod_protheus"]: p for p in velho["pessoas"]}
        entram = [antes[c]["nome"] for c in antes if c not in atual]
        saem = [atual[c]["nome"] for c in atual if c not in antes]
        mudam = [antes[c]["nome"] for c in antes
                 if c in atual and antes[c] != atual[c]]

        def lista(xs):
            return (", ".join(x.title() for x in xs[:6])
                    + (f" e mais {len(xs) - 6}" if len(xs) > 6 else "")) \
                if xs else "ninguem"
        if not messagebox.askyesno(
                "Replicar equipe do mês anterior",
                f"Trazer a equipe de {ant[5:]}/{ant[:4]} para "
                f"{mes[5:]}/{mes[:4]}?\n\n"
                f"Entram: {lista(entram)}\nSaem: {lista(saem)}\n"
                f"Mudam (cargo, supervisor, e-mail...): {lista(mudam)}\n"
                f"Mês de casa: +1 para quem tem (quem tem data de admissão: "
                f"calculado por ela).\n\n"
                f"Quem atende cada zona volta como em {ant[5:]}/{ant[:4]}. "
                f"Zonas, areas e parametros deste mes nao mudam.\n"
                f"A configuracao atual vai para o backup antes."):
            return
        # backup da configuracao deste mes, antes de mexer
        try:
            bkp = AQUI / pb.BKP_PLANNER / (
                f"planner_config_{mes}_antes_de_replicar_"
                f"{dt.datetime.now():%Y%m%d_%H%M%S}.json")
            nu.gravar_config(self.cfg, bkp)
        except OSError as erro:
            messagebox.showerror("Planner BAP",
                                 f"Nao consegui fazer o backup: {erro}")
            return
        import copy                                      # noqa: PLC0415
        self.cfg["pessoas"] = copy.deepcopy(velho["pessoas"])
        # um mes a mais de casa para quem tinha o mes de casa preenchido
        for p in self.cfg["pessoas"]:
            if nu.data_admissao(p) is not None and nu.casa_pela_admissao(mes):
                # (18/10) com a data de admissao, o mes de casa e a conta
                n_ = nu.mes_de_casa_no_mes(p, mes)
                if n_:
                    p["meses_de_casa"] = n_
                else:
                    p.pop("meses_de_casa", None)
            elif p.get("meses_de_casa"):
                p["meses_de_casa"] = int(p["meses_de_casa"]) + 1
        zonas_velhas = {z["id"]: z for z in velho.get("zonas") or []}
        for z in self.cfg.get("zonas") or []:
            zv = zonas_velhas.get(z["id"])
            if zv is not None:
                for k in ("vendedor", "atendimento"):
                    if k in zv:
                        z[k] = copy.deepcopy(zv[k])
                    else:
                        z.pop(k, None)
        # zona so deste mes com quem saiu da equipe: fica sem vendedor
        for cod in set(atual) - set(antes):
            nu.tirar_vendedor_das_zonas(self.cfg, cod)
        nu.normalizar_atendimento(self.cfg)
        self.salvar()
        self._ger_sujo = True
        self.marcar_pendente()
        self.limpar_pessoa()
        self.desenhar_pessoas()
        self.aviso(f"Equipe de {ant[5:]}/{ant[:4]} replicada. Clique em "
                   f"Recalcular Planner para refazer a rota.", COR_OK)

    def excluir_pessoa(self):
        sel = self.tab_pessoas.selection()
        if not sel:
            messagebox.showinfo("Planner BAP", "Selecione quem excluir.")
            return
        cod = sel[0]
        p = nu.pessoa_por_codigo(self.cfg, cod)
        zonas = [z.get("codigo", "") for z in nu.zonas_do_vendedor(self.cfg, cod)]
        liderados = [x["nome"] for x in self.cfg["pessoas"]
                     if x["responde_a"] == cod]
        aviso = ""
        if zonas:
            aviso += f"\n\nEsta em {len(zonas)} zona(s): " + ", ".join(zonas) \
                     + " - elas ficam sem vendedor."
        if liderados:
            aviso += f"\n\n{len(liderados)} pessoa(s) respondem a ele - ficam " \
                     f"sem chefe."
        if not messagebox.askyesno("Planner BAP",
                                   f"Excluir {p.get('nome','')}?{aviso}"):
            return
        self.cfg["pessoas"] = [x for x in self.cfg["pessoas"]
                               if x["cod_protheus"] != cod]
        for x in self.cfg["pessoas"]:
            if x["responde_a"] == cod:
                x["responde_a"] = ""
        nu.tirar_vendedor_das_zonas(self.cfg, cod)
        self.salvar()
        self._ger_sujo = True
        self.limpar_pessoa()
        self.desenhar_pessoas()

    def importar_vendedores(self):
        if not self.clientes:
            messagebox.showinfo("Planner BAP",
                                "Importe a base de clientes primeiro (aba 3).")
            return
        existentes = {p["cod_protheus"] for p in self.cfg["pessoas"]}
        novos = sorted({c["COD_ULTIMO_VENDEDOR"].zfill(6)
                        for c in self.clientes
                        if c["COD_ULTIMO_VENDEDOR"]} - existentes)
        if not novos:
            messagebox.showinfo("Planner BAP", "Nenhum codigo novo na base.")
            return
        if not messagebox.askyesno(
                "Planner BAP",
                f"{len(novos)} codigo(s) aparecem faturando na base e nao "
                f"estao no cadastro:\n\n{', '.join(novos)}\n\n"
                f"Incluir como VENDEDOR? O nome fica em branco para preencher."):
            return
        for cod in novos:
            self.cfg["pessoas"].append({
                "cod_protheus": cod, "cod_maxima": "", "nome": f"({cod})",
                "cargo": "VENDEDOR", "uf_base": "", "cidade_base": "",
                "responde_a": "", "ativo": True, "provisorio": False})
        self.salvar()
        self.desenhar_pessoas()

    # =================================================================== 3
    AUTOMATICO = "(automatico)"

    def _agenda_editando(self) -> dict:
        """A agenda da zona que esta sendo editada. Zona nova ainda nao tem."""
        if not self._zona_editando:
            return {}
        z = next((x for x in self.cfg["zonas"]
                  if x["id"] == self._zona_editando), None)
        if z is None:
            return {}
        if not isinstance(z.get("agenda"), dict):
            z["agenda"] = {}
        return z["agenda"]

    def _cidades_da_zona(self) -> set:
        """As cidades que tem ao menos um bairro na zona sendo editada."""
        if not self._zona_editando:
            return set()
        minhas = set()
        for a in self.areas:
            if self.cfg["areas"].get(a["chave"]) == self._zona_editando:
                minhas.add((a["uf"], a["cidade"]))
        return minhas

    # ---- A CAIXA SEMANA DA ROTA ---------------------------------------
    # A quarta lista da aba, do lado do BAIRRO. Ela diz, semana a semana,
    # quais cidades o vendedor roda e EM QUE ORDEM - e o calendario
    # comercial dele escrito no programa. O que a caixa guarda esta
    # explicado por extenso em A ROTA SEMANAL DA ZONA, no nucleo.
    def _zona_atual(self):
        """A zona que esta sendo editada, ou None (zona ainda nao salva)."""
        if not self._zona_editando:
            return None
        return next((x for x in self.cfg["zonas"]
                     if x["id"] == self._zona_editando), None)

    def _clientes_por_cidade(self) -> dict:
        """{'UF|CIDADE': quantos clientes} contando so os bairros da zona."""
        dono = self.cfg["areas"]
        conta = defaultdict(int)
        for a in getattr(self, "areas", []):
            if dono.get(a["chave"]) == self._zona_editando:
                conta[nu.chave_da_cidade(a["uf"], a["cidade"])] += a["clientes"]
        return conta

    def _semanas_na_tela(self) -> list:
        """
        Quantas caixas aparecer: as semanas que o MES tem.

        Mes de cinco semanas mostra cinco caixas. Semana que ficou
        guardada na zona e nao existe no mes continua aparecendo - some-la
        da tela seria esconder trabalho que ele ja fez, e o PLANNER ainda
        vai usa-la (na semana mais proxima, avisando no log).
        """
        try:
            do_mes = nu.semanas_do_mes(self.cfg["mes"],
                                       self.cfg.get("feriados") or [])
        except Exception:                              # noqa: BLE001
            do_mes = [1, 2, 3, 4]
        mostrar = set(do_mes) | set(getattr(self, "_rota_sem", {}) or {})
        return sorted(n for n in mostrar if 1 <= n <= nu.SEMANAS_DA_ROTA)

    LINHAS_DA_SEMANA = 6        # o teto de linhas visiveis numa caixa

    def _montar_semanas(self, pai):
        painel = ttk.Frame(pai, width=412)
        painel.pack(side="left", fill="both")
        painel.pack_propagate(False)
        self._rota_sem = {}
        self._sel_sem = None

        topo = ttk.Frame(painel)
        topo.pack(fill="x")
        ttk.Label(topo, text="SEMANA DA ROTA",
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        self.lbl_sem_resumo = ttk.Label(topo, text="", style="Sub.TLabel")
        self.lbl_sem_resumo.pack(side="right")

        ttk.Label(painel, text="Por as cidades marcadas na semana:",
                  style="Sub.TLabel").pack(anchor="w", pady=(4, 0))
        mandar = ttk.Frame(painel)
        mandar.pack(fill="x", pady=(2, 6))
        self.bt_semana = {}
        for n in range(1, nu.SEMANAS_DA_ROTA + 1):
            self.bt_semana[n] = ttk.Button(
                mandar, text=f"S{n}", width=4,
                command=lambda n=n: self.por_na_semana(n))

        # OS BOTOES FICAM PRESOS EMBAIXO, montados antes das caixas: assim
        # as caixas crescem no espaco que sobra e nunca empurram o SUBIR
        # para fora da tela.
        barra = ttk.Frame(painel)
        barra.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(barra, text="\u25b2 SUBIR", width=9,
                   command=self.subir_na_semana).pack(side="left")
        ttk.Button(barra, text="\u25bc DESCER", width=10,
                   command=self.descer_na_semana).pack(side="left", padx=4)
        ttk.Button(barra, text="TIRAR DA SEMANA",
                   command=self.tirar_da_semana).pack(side="left")
        linha_dia = ttk.Frame(painel)
        linha_dia.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Label(linha_dia, text="Dia fixo:", style="Sub.TLabel").pack(
            side="left")
        self.var_dia_sem = tk.StringVar(value=self.AUTOMATICO)
        cb = ttk.Combobox(linha_dia, textvariable=self.var_dia_sem, width=12,
                          state="readonly",
                          values=[self.AUTOMATICO] + list(nu.DIAS_DA_SEMANA_PT))
        cb.pack(side="left", padx=5)
        cb.bind("<<ComboboxSelected>>", lambda _: self.mudar_dia_fixo())
        self.lbl_dia_sem = ttk.Label(linha_dia, text="", style="Sub.TLabel",
                                     foreground=COR_ACENTO)
        self.lbl_dia_sem.pack(side="left")

        # AS CAIXAS ROLAM: num mes de cinco semanas as cinco nao cabem na
        # mesma altura das listas de UF, CIDADE e BAIRRO. Rolando, cada
        # uma continua mostrando quatro cidades sem apertar.
        tela = tk.Canvas(painel, highlightthickness=0, background=COR_PAPEL)
        rol = ttk.Scrollbar(painel, orient="vertical", command=tela.yview)
        self.quadro_semanas = ttk.Frame(tela)
        self.quadro_semanas.bind(
            "<Configure>",
            lambda _: tela.configure(scrollregion=tela.bbox("all")))
        self._janela_semanas = tela.create_window((0, 0),
                                                  window=self.quadro_semanas,
                                                  anchor="nw")
        tela.bind("<Configure>",
                  lambda e: tela.itemconfigure(self._janela_semanas,
                                               width=e.width))
        tela.configure(yscrollcommand=rol.set)
        tela.pack(side="left", fill="both", expand=True)
        rol.pack(side="right", fill="y")
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            tela.bind(evento, self._roda_nas_semanas)
        self.tela_semanas = tela
        self.tab_semana = {}
        self._desenhar_semanas()

    def _roda_nas_semanas(self, evento):
        """A roda do mouse rolando as caixas da semana."""
        passo = 0
        if getattr(evento, "num", 0) == 4 or getattr(evento, "delta", 0) > 0:
            passo = -1
        elif getattr(evento, "num", 0) == 5 or getattr(evento, "delta", 0) < 0:
            passo = 1
        if passo:
            self.tela_semanas.yview_scroll(passo, "units")

    def _desenhar_semanas(self):
        """Refaz as caixas - o numero delas muda com o mes."""
        if not hasattr(self, "quadro_semanas"):
            return
        for filho in self.quadro_semanas.winfo_children():
            filho.destroy()
        self.tab_semana = {}
        semanas = self._semanas_na_tela() or [1, 2, 3, 4]
        for b in self.bt_semana.values():
            b.pack_forget()
        for n in semanas:
            self.bt_semana[n].pack(side="left", padx=(0, 4))
        conta = self._clientes_por_cidade()
        # QUANTOS CLIENTES EM CADA PASSAGEM: cidade que esta em quatro
        # semanas nao leva a carteira inteira quatro vezes - ela se
        # reparte entre elas, e e o pedaco que tem de aparecer, senao a
        # soma da caixa mente.
        vezes = Counter(it["cidade"] for itens in (self._rota_sem or {}).values()
                        for it in itens)
        gastos = Counter()
        pedaco = {}
        for sem in sorted(self._rota_sem or {}):
            for i, it in enumerate(self._rota_sem[sem]):
                total, v = conta.get(it["cidade"], 0), max(1, vezes[it["cidade"]])
                k = gastos[it["cidade"]]
                gastos[it["cidade"]] += 1
                pedaco[(sem, i)] = (k + 1) * total // v - k * total // v
        for n in semanas:
            itens = (self._rota_sem or {}).get(n) or []
            cli = sum(pedaco.get((n, i), 0) for i in range(len(itens)))
            quadro = ttk.LabelFrame(
                self.quadro_semanas,
                text=f" SEMANA {n}    {len(itens)} cidade(s) - {cli} cli. ",
                padding=(6, 2, 6, 4))
            quadro.pack(fill="x", pady=(0, 5))
            # A CAIXA CRESCE COM O QUE TEM DENTRO: semana de uma cidade
            # nao fica com tres linhas vazias, e semana cheia so ganha
            # barra de rolagem propria quando passa do teto.
            altura = max(1, min(len(itens) or 1, self.LINHAS_DA_SEMANA))
            t = ttk.Treeview(quadro, columns=("n", "cidade", "dia"), show="",
                             height=altura, selectmode="browse",
                             style="Semana.Treeview")
            t.column("n", width=24, anchor="center", stretch=False)
            t.column("cidade", width=252, anchor="w")
            t.column("dia", width=42, anchor="center", stretch=False)
            t.pack(side="left", fill="both", expand=True)
            if len(itens) > altura:
                sv = ttk.Scrollbar(quadro, orient="vertical", command=t.yview)
                t.configure(yscrollcommand=sv.set)
                sv.pack(side="left", fill="y")
            t.tag_configure("zebra", background=COR_ZEBRA)
            for i, it in enumerate(itens):
                nome = it["cidade"].split("|")[-1]
                dia = ("-" if it.get("dia") is None
                       else nu.DIAS_DA_SEMANA_PT[int(it["dia"])][:3].upper())
                t.insert("", "end", iid=str(i),
                         values=(i + 1, f"{nome}  ({pedaco.get((n, i), 0)})",
                                 dia),
                         tags=("zebra",) if i % 2 else ())
            t.bind("<<TreeviewSelect>>", lambda _e, n=n: self._semana_clicada(n))
            self.tab_semana[n] = t
        # devolve a selecao que havia antes de redesenhar
        if self._sel_sem:
            sem, i = self._sel_sem
            t = self.tab_semana.get(sem)
            if t is not None and str(i) in t.get_children():
                t.selection_set(str(i))
            else:
                self._sel_sem = None
        self._resumo_das_semanas()

    def _resumo_das_semanas(self):
        """A etiqueta do alto da caixa e a do dia fixo."""
        if not hasattr(self, "lbl_sem_resumo"):
            return
        if not self._zona_editando:
            self.lbl_sem_resumo.configure(
                text="salve a zona primeiro", foreground=COR_ALERTA)
        else:
            rota = self._rota_sem or {}
            cidades = sum(len(v) for v in rota.values())
            cheias = len([s for s, v in rota.items() if v])
            self.lbl_sem_resumo.configure(
                text=(f"{cheias} semana(s) montada(s) - {cidades} cidade(s)"
                      if cidades else "nenhuma cidade nas semanas ainda"),
                foreground=COR_SUAVE)
        if not self._sel_sem:
            self.var_dia_sem.set(self.AUTOMATICO)
            self.lbl_dia_sem.configure(
                text="escolha uma cidade na caixa ao lado")

    def _semana_clicada(self, n):
        """Guarda qual cidade de qual semana esta escolhida agora."""
        t = self.tab_semana.get(n)
        if t is None:
            return
        sel = t.selection()
        if not sel:
            return
        for outra, outro_t in self.tab_semana.items():
            if outra != n and outro_t.selection():
                outro_t.selection_remove(*outro_t.selection())
        i = int(sel[0])
        self._sel_sem = (n, i)
        itens = (self._rota_sem or {}).get(n) or []
        if i >= len(itens):
            return
        it = itens[i]
        self.var_dia_sem.set(self.AUTOMATICO if it.get("dia") is None
                             else nu.DIAS_DA_SEMANA_PT[int(it["dia"])])
        self.lbl_dia_sem.configure(
            text=f"em {it['cidade'].split('|')[-1]} (S{n})")

    def _item_escolhido(self):
        """(semana, indice, item) do que esta escolhido nas caixas."""
        if not self._sel_sem:
            return None, None, None
        sem, i = self._sel_sem
        itens = (self._rota_sem or {}).get(sem) or []
        if i >= len(itens):
            return None, None, None
        return sem, i, itens[i]

    def _guardar_rota(self, recado=""):
        """
        Grava a rota na zona e no disco, na hora.

        E de proposito que nao espera pelo SALVAR ZONA: montar a semana e
        arrastar cidade de caixa em caixa, e perder isso por ter fechado o
        programa antes de clicar no botao certo seria uma armadilha.
        """
        z = self._zona_atual()
        if z is None:
            return
        self._rota_sem = {s: v for s, v in (self._rota_sem or {}).items() if v}
        nu.gravar_rota_semanal(z, self._rota_sem)
        self.salvar()
        self._ger_sujo = True
        self.marcar_pendente()
        self._desenhar_semanas()
        self._uf_mudou()              # refaz a lista para a etiqueta [S1] mudar
        if recado:
            self.log(recado)

    def por_na_semana(self, n):
        """Manda as cidades marcadas na lista do meio para a semana n."""
        if not self._zona_editando:
            messagebox.showinfo(
                "Planner BAP",
                "Salve a zona primeiro. A rota da semana fica guardada na "
                "zona, entao ela tem de existir antes.")
            return
        cidades = self._escolhidos(self.lb_cidade,
                                   getattr(self, "_cidades", []))
        if not cidades:
            messagebox.showinfo("Planner BAP",
                                "Marque ao menos uma cidade na lista do meio.")
            return
        # SO VALE PARA CIDADE QUE E DESTA ZONA. A lista do meio mostra as
        # cidades da UF inteira, entao da para marcar uma que nao tem
        # bairro nenhum aqui - e ela ficaria guardada sem nunca valer,
        # porque a rota daquela cidade e montada na zona dela.
        minhas = self._cidades_da_zona()
        dentro = [(uf, cid) for uf, cid in cidades if (uf, cid) in minhas]
        fora = [cid for uf, cid in cidades if (uf, cid) not in minhas]
        if not dentro:
            messagebox.showwarning(
                "Planner BAP",
                "Nenhuma das cidades marcadas tem bairro nesta zona.\n\n"
                "A rota da semana e guardada na zona, entao ela so vale "
                "para as cidades que pertencem a ela. Marque os bairros da "
                "cidade nesta zona antes.")
            return
        itens = self._rota_sem.setdefault(n, [])
        ja = {it["cidade"] for it in itens}
        novas = []
        for uf, cid in dentro:
            chave = nu.chave_da_cidade(uf, cid)
            # a mesma cidade DUAS VEZES NA MESMA SEMANA nao quer dizer
            # nada - os dias dela ja sao os mesmos. Em semanas diferentes,
            # sim: e a cidade-base, que ele roda toda semana.
            if chave in ja:
                continue
            itens.append({"cidade": chave, "dia": None})
            novas.append(cid)
        if fora:
            self.log(f"  {len(fora)} cidade(s) marcadas nao sao desta zona e "
                     f"ficaram de fora: {', '.join(sorted(fora)[:6])}")
        if not novas:
            self.aviso(f"Essas cidades ja estao na semana {n}.")
            return
        self._sel_sem = (n, len(itens) - 1)
        self._guardar_rota(f"Semana {n} da zona {self.var_cod_zona.get()}: "
                           f"+{len(novas)} cidade(s) - "
                           f"{', '.join(novas[:6])}")

    def subir_na_semana(self):
        self._mover_na_semana(-1)

    def descer_na_semana(self):
        self._mover_na_semana(+1)

    def _mover_na_semana(self, passo):
        """Troca a cidade de lugar: e a ordem da visita dentro da semana."""
        sem, i, _ = self._item_escolhido()
        if sem is None:
            self.aviso("Escolha uma cidade dentro de uma das semanas.")
            return
        itens = self._rota_sem[sem]
        j = i + passo
        if not 0 <= j < len(itens):
            return
        itens[i], itens[j] = itens[j], itens[i]
        self._sel_sem = (sem, j)
        self._guardar_rota()

    def tirar_da_semana(self):
        """A cidade sai da caixa e volta para o automatico."""
        sem, i, it = self._item_escolhido()
        if sem is None:
            self.aviso("Escolha uma cidade dentro de uma das semanas.")
            return
        self._rota_sem[sem].pop(i)
        self._sel_sem = None
        self._guardar_rota(f"{it['cidade'].split('|')[-1]} saiu da semana "
                           f"{sem} - volta para o dia automatico.")

    def mudar_dia_fixo(self):
        """O dia certo daquela cidade naquela semana, quando precisa."""
        sem, i, _ = self._item_escolhido()
        if sem is None:
            self.var_dia_sem.set(self.AUTOMATICO)
            self.aviso("Escolha uma cidade dentro de uma das semanas.")
            return
        escolhido = self.var_dia_sem.get()
        self._rota_sem[sem][i]["dia"] = (
            None if escolhido == self.AUTOMATICO
            else list(nu.DIAS_DA_SEMANA_PT).index(escolhido))
        self._guardar_rota()

    def _rotulo_das_semanas(self, chave) -> str:
        """
        Onde a cidade esta, para aparecer ao lado do nome na lista:

            'S1 S2-QUA S4'   - semana 1, semana 2 na quarta, semana 4
        """
        partes = []
        for sem in sorted(self._rota_sem or {}):
            for it in self._rota_sem[sem]:
                if it["cidade"] != chave:
                    continue
                if it.get("dia") is None:
                    partes.append(f"S{sem}")
                else:
                    curto = nu.DIAS_DA_SEMANA_PT[int(it["dia"])][:3].upper()
                    partes.append(f"S{sem}-{curto}")
        return " ".join(partes)

    def _montar_zonas(self):
        f = self.aba_zonas
        self._faixa_recalcular(f)
        # OS BOTOES DE IMPORTAR E DE GERAR A BASE SAIRAM.
        # A BASE_CLIENTE tem um lugar so - RELATORIOS\\BASE_CLIENTE.xlsx, ao
        # lado deste programa - e quem a refaz e a Automacao BAP, no fim de
        # cada rodada. Poder apontar para outro arquivo so servia para
        # trabalhar com base velha sem perceber.
        topo = ttk.Frame(f)
        topo.pack(fill="x", pady=(0, 8))
        self.lbl_base = ttk.Label(
            topo, style="Sub.TLabel", foreground=COR_ALERTA,
            text=f"Nenhuma base carregada - ela vem de "
                 f"{pb.RELATORIOS}\\BASE_CLIENTE.xlsx, feita pela Automacao "
                 f"BAP")
        self.lbl_base.pack(side="left")

        corpo = ttk.Frame(f)
        corpo.pack(fill="both", expand=True)

        esq = ttk.Frame(corpo, width=330)
        esq.pack(side="left", fill="y", padx=(0, 14))
        esq.pack_propagate(False)
        ttk.Label(esq, text="Zonas cadastradas", style="Titulo.TLabel").pack(anchor="w")
        colunas = [("codigo", "CODIGO", 78, "w", False),
                   ("nome", "NOME", 150, "w", True),
                   ("cli", "QTD CLI.", 66, "center", False)]
        quadro, self.lista_zonas = tabela(esq, colunas, horizontal=False)
        quadro.pack(fill="both", expand=True, pady=(6, 6))
        self.lista_zonas.bind("<<TreeviewSelect>>", self._zona_clicada)
        bz = ttk.Frame(esq)
        bz.pack(fill="x")
        ttk.Button(bz, text="Nova zona", command=self.nova_zona).pack(side="left")
        ttk.Button(bz, text="Excluir zona",
                   command=self.excluir_zona).pack(side="left", padx=6)
        self.lbl_zonas_resumo = ttk.Label(esq, text="", style="Sub.TLabel",
                                          wraplength=310)
        self.lbl_zonas_resumo.pack(anchor="w", pady=(8, 0))

        dir_ = ttk.Frame(corpo)
        dir_.pack(side="left", fill="both", expand=True)
        cab = ttk.Frame(dir_)
        cab.pack(fill="x")
        ttk.Label(cab, text="Codigo da zona:").grid(row=0, column=0, sticky="w")
        self.var_cod_zona = tk.StringVar()
        ttk.Entry(cab, textvariable=self.var_cod_zona, width=16,
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=1,
                                                      sticky="w", padx=(6, 20))
        ttk.Label(cab, text="Nome da zona:").grid(row=0, column=2, sticky="w")
        self.var_nome_zona = tk.StringVar()
        ttk.Entry(cab, textvariable=self.var_nome_zona, width=46).grid(
            row=0, column=3, sticky="we", padx=6)
        # (18/10) ZONA SO NO SABADO DO EXCEDENTE: o vendedor fica com os
        # clientes (ativos, na carteira dele), mas eles nao entram nos dias
        # de rota - vao todos para o 1o sabado (ex.: Roraima do Thiago)
        self.var_zona_so_exc = tk.BooleanVar(value=False)
        ttk.Checkbutton(cab, text="Só no sábado do excedente",
                        variable=self.var_zona_so_exc).grid(
            row=0, column=4, sticky="w", padx=(10, 0))
        cab.columnconfigure(3, weight=1)
        listas = ttk.Frame(dir_)
        listas.pack(fill="both", expand=True, pady=(10, 0))

        # O QUE ESTA SEM ZONA: clicar na zona vermelha (Z-UF-100) lista
        # aqui as cidades e os bairros que ainda nao tem dono
        self.quadro_sem_zona = ttk.Frame(listas, width=330)
        self.quadro_sem_zona.pack_propagate(False)
        cab_sz = ttk.Frame(self.quadro_sem_zona)
        cab_sz.pack(fill="x")
        self.lbl_sem_zona = ttk.Label(cab_sz, text="SEM ZONA",
                                      foreground=COR_ALERTA,
                                      font=("Segoe UI", 9, "bold"))
        self.lbl_sem_zona.pack(side="left", pady=(0, 6))
        ttk.Button(cab_sz, text="Fechar", width=7,
                   command=self._fechar_sem_zona).pack(side="right")
        q_sz, self.tab_sem_zona = tabela(
            self.quadro_sem_zona,
            [("cidade", "CIDADE", 120, "w", True),
             ("bairro", "BAIRRO", 130, "w", True),
             ("cli", "CLI.", 44, "center", False)], horizontal=False)
        q_sz.pack(fill="both", expand=True, pady=(4, 0))
        self.tab_sem_zona.bind("<Double-1>", lambda _: self._ir_ao_sem_zona())

        q1, self.lb_uf, b1, self.lbl_c_uf = lista_multipla(listas, "UF", 16, 12)
        q1.pack(side="left", fill="both", padx=(0, 8))
        ttk.Button(b1, text="Todas", width=7,
                   command=lambda: self._marcar_todos(self.lb_uf, self._uf_mudou)).pack(side="left")
        ttk.Button(b1, text="Nenhuma", width=9,
                   command=lambda: self._marcar_nenhum(self.lb_uf, self._uf_mudou)).pack(side="left", padx=3)
        self.lb_uf.bind("<<ListboxSelect>>", lambda _: self._uf_mudou())

        q2, self.lb_cidade, b2, self.lbl_c_cid = lista_multipla(listas, "CIDADE", 16, 26)
        q2.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Button(b2, text="Todas", width=7,
                   command=lambda: self._marcar_todos(self.lb_cidade, self._cidade_mudou)).pack(side="left")
        ttk.Button(b2, text="Nenhuma", width=9,
                   command=lambda: self._marcar_nenhum(self.lb_cidade, self._cidade_mudou)).pack(side="left", padx=3)
        self.lb_cidade.bind("<<ListboxSelect>>", lambda _: self._cidade_mudou())

        q3, self.lb_bairro, b3, self.lbl_c_bai = lista_multipla(listas, "BAIRRO", 16, 28)
        q3.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Button(b3, text="Todos", width=7,
                   command=lambda: self._marcar_todos(self.lb_bairro, self._bairro_mudou)).pack(side="left")
        ttk.Button(b3, text="Nenhum", width=9,
                   command=lambda: self._marcar_nenhum(self.lb_bairro, self._bairro_mudou)).pack(side="left", padx=3)
        self.lb_bairro.bind("<<ListboxSelect>>", lambda _: self._bairro_mudou())

        # (05/10) a caixa SEMANA DA ROTA saiu da aba de zonas: a zona volta
        # a ser so UF, cidade e bairro. A rota por semana/dia vai para a
        # aba ROTA POR CIDADE.

        rodape = ttk.Frame(dir_)
        rodape.pack(fill="x", pady=(10, 0))
        self.lbl_zona_msg = ttk.Label(rodape, text="", style="Sub.TLabel",
                                      wraplength=880)
        self.lbl_zona_msg.pack(anchor="w", pady=(0, 6))
        ttk.Button(rodape, text="SALVAR ZONA", style="Big.TButton",
                   command=self.salvar_zona).pack(side="left")
        ttk.Button(rodape, text="Limpar (nova zona)",
                   command=self.nova_zona).pack(side="left", padx=8)
        ttk.Button(rodape, text="SUGERIR ZONA PARA OS BAIRROS EM VERMELHO",
                   command=self.sugerir_zonas).pack(side="right")
        legenda_de_cores(f, [
            (COR_AVISO, "sem vendedor"),
            (COR_SELECAO, "editando"),
            ("#FBE3E3", "sem zona (clique para ver)"),
        ], "Zonas").pack(anchor="w", pady=(10, 0))

    # ---- o que ainda esta sem zona -------------------------------------
    def _mostrar_sem_zona(self, uf):
        """Clicou na zona vermelha: as cidades e bairros sem dono da UF."""
        dono = self.cfg["areas"]
        t = self.tab_sem_zona
        t.delete(*t.get_children())
        linhas = sorted((a for a in self.areas
                         if a["uf"] == uf and not dono.get(a["chave"])),
                        key=lambda a: (a["cidade"], a["bairro"]))
        self._sem_zona_linhas = {}
        for i, a in enumerate(linhas):
            t.insert("", "end", iid=a["chave"],
                     tags=("zebra",) if i % 2 else (),
                     values=(a["cidade"], a["bairro"] or "-", a["clientes"]))
            self._sem_zona_linhas[a["chave"]] = a
        cidades = len({a["cidade"] for a in linhas})
        self.lbl_sem_zona.configure(
            text=f"{uf} SEM ZONA\n{cidades} cidade(s) · {len(linhas)} "
                 f"bairro(s) · {sum(a['clientes'] for a in linhas)} cli.")
        if not self.quadro_sem_zona.winfo_ismapped():
            self.quadro_sem_zona.pack(side="right", fill="y", padx=(10, 0))

    def _fechar_sem_zona(self):
        if self.quadro_sem_zona.winfo_ismapped():
            self.quadro_sem_zona.pack_forget()

    def _ir_ao_sem_zona(self):
        """Duas batidas num bairro sem zona: as listas abrem nele (UF e
        cidade marcadas), para colocar na zona que esta sendo editada."""
        sel = self.tab_sem_zona.selection()
        a = (getattr(self, "_sem_zona_linhas", {}) or {}).get(
            sel[0] if sel else "")
        if not a:
            return
        if a["uf"] in self._ufs:
            i = self._ufs.index(a["uf"])
            if i not in self.lb_uf.curselection():
                self.lb_uf.selection_set(i)
                self._uf_mudou()
            self.lb_uf.see(i)
        cidades = list(getattr(self, "_cidades", []))
        if (a["uf"], a["cidade"]) in cidades:
            i = cidades.index((a["uf"], a["cidade"]))
            if i not in self.lb_cidade.curselection():
                self.lb_cidade.selection_set(i)
                self._cidade_mudou()
            self.lb_cidade.see(i)

    # ---- as tres listas encadeadas --------------------------------------
    def _marcar_todos(self, lb, depois):
        lb.selection_set(0, "end")
        depois()

    def _marcar_nenhum(self, lb, depois):
        lb.selection_clear(0, "end")
        depois()

    def _escolhidos(self, lb, fonte):
        return [fonte[i] for i in lb.curselection()] if fonte else []

    def _sem_zona_ainda(self):
        """
        Onde ainda falta zona, contado por UF e por CIDADE.

        E a mesma pergunta do bairro em vermelho, so que um nivel acima:
        sem isso, para achar o bairro orfao era preciso abrir UF por UF e
        cidade por cidade ate topar com o vermelho.
        """
        dono = self.cfg["areas"]
        por_uf, por_cidade = defaultdict(int), defaultdict(int)
        for a in self.areas:
            if not dono.get(a["chave"]):
                por_uf[a["uf"]] += 1
                por_cidade[(a["uf"], a["cidade"])] += 1
        return por_uf, por_cidade

    def _pintar_sem_zona(self):
        """Pinta de vermelho a UF e a cidade que ainda tem bairro sem zona."""
        por_uf, por_cidade = self._sem_zona_ainda()
        for i, uf in enumerate(getattr(self, "_ufs", [])):
            self.lb_uf.itemconfigure(
                i, foreground=COR_ALERTA if por_uf.get(uf) else COR_TEXTO)
        for i, par in enumerate(getattr(self, "_cidades", [])):
            self.lb_cidade.itemconfigure(
                i, foreground=COR_ALERTA if por_cidade.get(par) else COR_TEXTO)

    def _encher_ufs(self):
        self._ufs = sorted({a["uf"] for a in self.areas if a["uf"]})
        self.lb_uf.delete(0, "end")
        for uf in self._ufs:
            self.lb_uf.insert("end", uf)
        self._uf_mudou()

    def _uf_mudou(self):
        ufs = set(self._escolhidos(self.lb_uf, getattr(self, "_ufs", [])))
        antes = set(self._escolhidos(self.lb_cidade, getattr(self, "_cidades", [])))
        self._cidades = sorted({(a["uf"], a["cidade"]) for a in self.areas
                                if a["uf"] in ufs})
        _, por_cidade = self._sem_zona_ainda()
        self.lb_cidade.delete(0, "end")
        for uf, cid in self._cidades:
            faltam = por_cidade.get((uf, cid), 0)
            # as semanas da cidade aparecem ao lado do nome:
            # "MA  IMPERATRIZ   [S1 S2-SEX S3-SEG S4]"
            marca = self._rotulo_das_semanas(nu.chave_da_cidade(uf, cid))
            self.lb_cidade.insert(
                "end", f"{uf}  {cid}"
                       + (f"   [{marca}]" if marca else "")
                       + (f"   ({faltam} sem zona)" if faltam else ""))
        for i, par in enumerate(self._cidades):
            if par in antes:
                self.lb_cidade.selection_set(i)
        self.lbl_c_uf.configure(text=f"{len(ufs)}/{len(self._ufs)}")
        self._pintar_sem_zona()
        self._cidade_mudou()

    def _cidade_mudou(self):
        cidades = set(self._escolhidos(self.lb_cidade, getattr(self, "_cidades", [])))
        antes = set(self._escolhidos(self.lb_bairro, getattr(self, "_bairros", [])))
        self._bairros = sorted({(a["uf"], a["cidade"], a["bairro"])
                                for a in self.areas
                                if (a["uf"], a["cidade"]) in cidades})
        self.lb_bairro.delete(0, "end")
        dono = self.cfg["areas"]
        for i, (uf, cid, bai) in enumerate(self._bairros):
            chave = nu.chave_de_area(uf, cid, bai)
            z = dono.get(chave)
            marca = ""
            if z and z != self._zona_editando:
                marca = f"   [{self._codigo_zona(z)}]"
            self.lb_bairro.insert("end", f"{cid}  /  {bai}{marca}")
            # BAIRRO SEM ZONA fica em VERMELHO: e o que falta cadastrar
            if not z:
                self.lb_bairro.itemconfigure(i, foreground=COR_ALERTA)
        for i, trio in enumerate(self._bairros):
            if trio in antes:
                self.lb_bairro.selection_set(i)
        self.lbl_c_cid.configure(text=f"{len(cidades)}/{len(self._cidades)}")
        self._resumo_das_semanas()
        self._pintar_sem_zona()
        self._bairro_mudou()

    def _bairro_mudou(self):
        marcados = self._escolhidos(self.lb_bairro, getattr(self, "_bairros", []))
        self.lbl_c_bai.configure(text=f"{len(marcados)}/{len(self._bairros)}")
        clientes = 0
        por_area = {a["chave"]: a["clientes"] for a in self.areas}
        for uf, cid, bai in marcados:
            clientes += por_area.get(nu.chave_de_area(uf, cid, bai), 0)
        roubados = [t for t in marcados
                    if self.cfg["areas"].get(nu.chave_de_area(*t))
                    not in (None, "", self._zona_editando)]
        texto = f"{len(marcados)} bairro(s) marcado(s), {clientes} cliente(s)."
        if roubados:
            texto += (f"   {len(roubados)} deles pertencem hoje a outra zona e "
                      f"vao MUDAR de dono (marcados com [codigo] na lista).")
        self.lbl_zona_msg.configure(
            text=texto, foreground=(COR_ALERTA if roubados else "#555555"))

    # ---- lista de zonas -------------------------------------------------
    def _codigo_zona(self, zid):
        for z in self.cfg["zonas"]:
            if z["id"] == zid:
                return z.get("codigo", "")
        return zid

    def _nome_zona(self, zid):
        for z in self.cfg["zonas"]:
            if z["id"] == zid:
                return z["nome"]
        return zid

    def sugerir_zonas(self):
        """
        Olha os bairros em VERMELHO e propoe, para cada um, a zona de um
        bairro que ja tem dono: primeiro o do mesmo nome (CIDADE NOVA 1 e
        CIDADE NOVA I sao o mesmo lugar), depois o vizinho mais perto pela
        coordenada. Mostra a lista antes de aplicar - nada muda sozinho.
        """
        sugestao = nu.sugerir_zonas(self.cfg, self.clientes)
        if not sugestao:
            messagebox.showinfo(
                "Planner BAP",
                "Nao consegui propor zona para nenhum bairro em vermelho.\n\n"
                "Ou nao ha bairro sem zona, ou nenhum deles tem um bairro do "
                "mesmo nome nem um vizinho com coordenada na mesma cidade.\n\n"
                "Nesse caso e no dedo mesmo: marque o bairro e a zona e "
                "clique em SALVAR ZONA.")
            return
        por_area = {a["chave"]: a["clientes"] for a in self.areas}
        cod = {z["id"]: z.get("codigo", z["id"]) for z in self.cfg["zonas"]}
        linhas = sorted(sugestao.items(),
                        key=lambda kv: -por_area.get(kv[0], 0))
        quantos = sum(por_area.get(k, 0) for k in sugestao)
        amostra = "\n".join(
            f"  {k.replace('|', ' / ')}  ->  {cod.get(z, z)}   ({por_que})"
            for k, (z, por_que) in linhas[:14])
        if len(linhas) > 14:
            amostra += f"\n  ... e mais {len(linhas) - 14} bairro(s)."
        if not messagebox.askyesno(
                "Planner BAP",
                f"Achei zona para {len(sugestao)} bairro(s), "
                f"{quantos} cliente(s):\n\n{amostra}\n\n"
                f"Aplicar? Nada e apagado - so entram os bairros que hoje "
                f"nao tem zona nenhuma, e voce pode mudar qualquer um "
                f"depois."):
            return
        n = nu.aplicar_sugestoes(self.cfg, sugestao)
        self.salvar()
        self._recontar_zonas()
        self._ger_sujo = True
        self.marcar_pendente()
        self.desenhar_zonas()
        self._uf_mudou()
        self.aviso(f"{n} bairro(s) entraram em zona pela sugestao. Va em "
                   f"PARAMETROS e clique em RECALCULAR PLANNER para valer.",
                   COR_OK)

    def desenhar_zonas(self):
        self._silencio = True
        try:
            marcada = self.lista_zonas.selection()
            self.lista_zonas.delete(*self.lista_zonas.get_children())
            for i, z in enumerate(sorted(self.cfg["zonas"],
                                         key=lambda x: x.get("codigo") or "ZZZ")):
                qtd = self.contagem_zona.get(z["id"], 0)
                tags = ("aviso",) if not z.get("vendedor") else (
                    ("zebra",) if i % 2 else ())
                self.lista_zonas.insert("", "end", iid=z["id"], tags=tags,
                                        values=(z.get("codigo", ""), z["nome"],
                                                qtd))
            # as ZONAS VIRTUAIS do estado, montadas na hora: e onde o
            # cliente de bairro sem dono fica estacionado. Nao estao no
            # cadastro - nao da para dar vendedor nem excluir.
            for z in nu.zonas_virtuais(self.cfg, self.clientes):
                self.lista_zonas.insert("", "end", iid=z["id"],
                                        tags=("semzona",),
                                        values=(z["codigo"], z["nome"],
                                                z["clientes"]))
            for m in marcada:
                if self.lista_zonas.exists(m):
                    self.lista_zonas.selection_set(m)
        finally:
            self._silencio = False
        sem_zona = sum(a["clientes"] for a in self.areas
                       if not self.cfg["areas"].get(a["chave"]))
        bairros_fora = sum(1 for a in self.areas
                           if not self.cfg["areas"].get(a["chave"]))
        self.lbl_zonas_resumo.configure(
            text=(f"{len(self.cfg['zonas'])} zonas"
                  + (f"  ·  {bairros_fora} bairros sem zona ({sem_zona} cli.)"
                     if sem_zona else "  ·  todos com zona")),
            foreground=(COR_ALERTA if sem_zona else COR_OK))
        self.lbl_base.configure(
            text=(f"{len(self.clientes)} clientes | {len(self.areas)} areas "
                  f"(UF/cidade/bairro)" if self.clientes
                  else "Nenhuma base carregada - rode a Automacao BAP"),
            foreground=("#555555" if self.clientes else COR_ALERTA))

    def _zona_clicada(self, _=None):
        if self._silencio:
            return
        sel = self.lista_zonas.selection()
        if not sel:
            return
        z = next((x for x in self.cfg["zonas"] if x["id"] == sel[0]), None)
        if not z:
            virtual = next((v for v in nu.zonas_virtuais(self.cfg,
                                                         self.clientes)
                            if v["id"] == sel[0]), None)
            if virtual:
                self._mostrar_sem_zona(virtual["uf"])
            return
        self._zona_editando = z["id"]
        # a rota semanal vem ANTES de encher as listas: e dela que sai a
        # etiqueta [S1 S2-QUA] ao lado do nome da cidade
        self._rota_sem = {}           # (a SEMANA DA ROTA saiu da zona)
        self._sel_sem = None
        self.var_cod_zona.set(z.get("codigo", ""))
        self.var_nome_zona.set(z["nome"])
        self.var_zona_so_exc.set(bool(z.get("so_excedente")))
        # marca as areas da zona
        minhas = {c for c, v in self.cfg["areas"].items() if v == z["id"]}
        trios = []
        for a in self.areas:
            if a["chave"] in minhas:
                trios.append((a["uf"], a["cidade"], a["bairro"]))
        ufs = {t[0] for t in trios}
        # ZERA as tres listas antes de marcar: se sobrar marcacao da zona
        # anterior, SALVAR ZONA levaria embora bairro que nao e desta zona.
        self._silencio = True
        try:
            self.lb_cidade.selection_clear(0, "end")
            self.lb_bairro.selection_clear(0, "end")
            self.lb_uf.selection_clear(0, "end")
            for i, uf in enumerate(getattr(self, "_ufs", [])):
                if uf in ufs:
                    self.lb_uf.selection_set(i)
        finally:
            self._silencio = False
        self._uf_mudou()
        cidades = {(t[0], t[1]) for t in trios}
        for i, par in enumerate(self._cidades):
            if par in cidades:
                self.lb_cidade.selection_set(i)
        self._cidade_mudou()
        marcar = set(trios)
        for i, trio in enumerate(self._bairros):
            if trio in marcar:
                self.lb_bairro.selection_set(i)
        self._bairro_mudou()
        # rola cada lista ate a primeira marcacao: com 54 cidades e 168
        # bairros, o que esta marcado costuma ficar fora da tela
        for lb in (self.lb_uf, self.lb_cidade, self.lb_bairro):
            escolhidos = lb.curselection()
            if escolhidos:
                lb.see(escolhidos[0])
        self._desenhar_semanas()
        self.aviso(f"Editando a zona {z.get('codigo','')} - {z['nome']}")

    def nova_zona(self):
        self._zona_editando = None
        self._rota_sem = {}
        self._sel_sem = None
        self._silencio = True
        try:
            self.lista_zonas.selection_remove(*self.lista_zonas.selection())
        finally:
            self._silencio = False
        usados = {z.get("codigo") for z in self.cfg["zonas"]}
        self.var_cod_zona.set(nu.codigo_livre(usados, ""))
        self.var_nome_zona.set("")
        self.var_zona_so_exc.set(False)
        self.lb_bairro.selection_clear(0, "end")
        self.lb_cidade.selection_clear(0, "end")
        self.lb_uf.selection_clear(0, "end")
        self._uf_mudou()
        self._desenhar_semanas()
        self.lbl_zona_msg.configure(text="Nova zona: preencha o codigo e o "
                                         "nome, marque UF/cidade/bairro e "
                                         "clique em SALVAR ZONA.",
                                    foreground="#555555")

    def salvar_zona(self):
        cod = self.var_cod_zona.get().strip().upper()
        nome = self.var_nome_zona.get().strip()
        if not cod:
            messagebox.showwarning("Planner BAP",
                                   "O codigo da zona e obrigatorio.")
            return
        if not nome:
            messagebox.showwarning("Planner BAP",
                                   "O nome da zona e obrigatorio.")
            return
        marcados = self._escolhidos(self.lb_bairro, getattr(self, "_bairros", []))
        if not marcados:
            messagebox.showwarning("Planner BAP",
                                   "Marque ao menos um bairro para a zona.")
            return
        outro = next((z for z in self.cfg["zonas"]
                      if z.get("codigo") == cod and z["id"] != self._zona_editando),
                     None)
        if outro:
            messagebox.showwarning("Planner BAP",
                                   f"O codigo {cod} ja e da zona '{outro['nome']}'.")
            return

        ufs = sorted({t[0] for t in marcados})
        if self._zona_editando:
            z = next(x for x in self.cfg["zonas"] if x["id"] == self._zona_editando)
            z["codigo"], z["nome"] = cod, nome
            z["uf"] = ufs[0] if len(ufs) == 1 else "/".join(ufs[:3])
            acao = "atualizada"
            z["so_excedente"] = bool(self.var_zona_so_exc.get())
        else:
            # a zona nao guarda a regra de sabado: quem manda e a aba 6
            z = {"id": cod, "codigo": cod, "nome": nome,
                 "uf": ufs[0] if len(ufs) == 1 else "/".join(ufs[:3]),
                 "vendedor": "", "visitas_por_dia": 0, "frequencia": 0,
                 "so_excedente": bool(self.var_zona_so_exc.get())}
            self.cfg["zonas"].append(z)
            self._zona_editando = z["id"]
            acao = "criada"

        # tira desta zona o que nao esta mais marcado e poe o que esta
        novas = {nu.chave_de_area(*t) for t in marcados}
        for chave, dono in list(self.cfg["areas"].items()):
            if dono == z["id"] and chave not in novas:
                self.cfg["areas"].pop(chave)
        roubadas = sum(1 for c in novas
                       if self.cfg["areas"].get(c) not in (None, "", z["id"]))
        nu.aplicar_area(self.cfg, novas, z["id"])

        self.salvar()
        self._recontar_zonas()
        self._ger_sujo = True
        self.marcar_pendente()
        self.desenhar_zonas()
        self._desenhar_semanas()
        # refaz a lista de CIDADE tambem: o "(n sem zona)" e o vermelho
        # dela mudam junto com o que acabou de ser salvo
        self._uf_mudou()
        clientes = sum(self.contagem_zona.get(z["id"], 0) for _ in (1,))
        self.lbl_zona_msg.configure(
            text=f"Zona {cod} - {nome} {acao}: {len(novas)} bairro(s), "
                 f"{clientes} cliente(s)."
                 + (f" {roubadas} area(s) vieram de outra zona." if roubadas else "")
                 + "  Agora de a zona a um vendedor na aba 2.",
            foreground=COR_OK)
        self.aviso(f"Zona {cod} {acao}.", COR_OK)

    def excluir_zona(self):
        sel = self.lista_zonas.selection()
        if not sel:
            messagebox.showinfo("Planner BAP", "Selecione uma zona.")
            return
        z = next(x for x in self.cfg["zonas"] if x["id"] == sel[0])
        areas = [c for c, v in self.cfg["areas"].items() if v == z["id"]]
        if not messagebox.askyesno(
                "Planner BAP",
                f"Excluir a zona {z.get('codigo','')} - {z['nome']}?\n\n"
                f"{len(areas)} area(s) ficam sem zona."):
            return
        self.cfg["zonas"] = [x for x in self.cfg["zonas"] if x["id"] != z["id"]]
        for c in areas:
            self.cfg["areas"].pop(c, None)
        self.salvar()
        self._recontar_zonas()
        self._ger_sujo = True
        self.marcar_pendente()
        self.nova_zona()
        self.desenhar_zonas()

    # IMPORTAR BASE / GERAR DA TABELA_BAP sairam daqui junto com os botoes.
    # O Planner passou a so LER a BASE_CLIENTE que esta em RELATORIOS.

    def carregar_base(self, caminho):
        def pronto(clientes, erro):
            if erro:
                self.log(f"ERRO ao ler a base: {erro[0]}")
                messagebox.showerror("Planner BAP", str(erro[0]))
                self.aviso("Nao consegui ler a base.", COR_ALERTA)
                return
            self.clientes = clientes
            nu.aplicar_parametros(self.cfg, self.clientes)
            convertidas = nu.migrar_areas_antigas(self.cfg, self.clientes)
            if convertidas:
                self.salvar()
                self.log(f"  {convertidas} cidade(s) da versao anterior foram "
                         f"convertidas para bairro, mantendo a zona delas.")
            self._indexar()
            sem = nu.sincronizar_areas(self.cfg, self.clientes)
            ufs = sorted({c["UF"] for c in self.clientes if c["UF"]})
            self.log(f"\nBase lida: {len(self.clientes)} clientes | "
                     f"{len(ufs)} UFs ({', '.join(ufs)}) | "
                     f"{len(self.areas)} areas (UF/cidade/bairro)")
            if sem:
                self.log(f"  {sem} area(s) ainda sem zona - cadastre na aba 3.")
            self.atualizar_tudo()
            self.aviso(f"Base carregada: {len(self.clientes)} clientes.", COR_OK)

        self._tarefa(lambda: nu.ler_base_cliente(caminho), pronto,
                     f"Lendo {Path(caminho).name}...")

    def _indexar(self):
        info = {}
        for c in self.clientes:
            reg = info.get(c["AREA"])
            if reg is None:
                info[c["AREA"]] = reg = {
                    "chave": c["AREA"], "uf": c["UF"], "cidade": c["CIDADE"],
                    "bairro": c["BAIRRO"], "clientes": 0,
                }
            reg["clientes"] += 1
        self.areas = sorted(info.values(),
                            key=lambda a: (a["uf"], a["cidade"], a["bairro"]))
        self._recontar_zonas()

    def _recontar_zonas(self):
        c = Counter()
        for a in self.areas:
            zid = self.cfg["areas"].get(a["chave"])
            if zid:
                c[zid] += a["clientes"]
        self.contagem_zona = c

    def atualizar_tudo(self):
        """Redesenha as seis abas com o estado atual."""
        self._ger_sujo = True
        self._rota_an = None            # a agenda do analitico e refeita
        self._encher_ufs()
        self.desenhar_zonas()
        self.desenhar_pessoas()
        self._mostrar_calendario()
        self.atualizar_resumo(True)
        # analitico, exportar e rota por cidade sao refeitos quando a aba
        # abre (_trocou_aba); so a que esta na tela e refeita agora
        try:
            aba = self.abas.nametowidget(self.abas.select())
        except (tk.TclError, KeyError):
            aba = None
        if aba is self.aba_analitico:
            self.recarregar_zonas_analitico()
        elif aba is self.aba_protheus:
            self.recarregar_protheus()
        elif aba is self.aba_rota:
            self.recarregar_rota_cidade()
        elif aba is self.aba_base:
            self.recarregar_base_cliente()

    # =================================================================== 6
    # BASE CLIENTE (06/10): todo cliente e ATIVO; aqui se INATIVA. O cliente
    # inativo sai da rota do vendedor (o Planner e refeito sem ele). (20/10)
    # No .json da base de clientes ele vai ATIVO com o vendedor e o
    # supervisor PADRAO (o vendedor nao ve).
    TODOS_BC = "(todos)"
    COLUNAS_BC = [
        ("cod", "COD", 66, "w", False), ("loja", "LOJA", 44, "center", False),
        ("cliente", "CLIENTE", 230, "w", True),
        ("fantasia", "NOME FANTASIA", 160, "w", False),
        ("uf", "UF", 36, "center", False), ("cidade", "CIDADE", 130, "w", False),
        ("bairro", "BAIRRO", 130, "w", False),
        ("vendedor", "VENDEDOR", 170, "w", False),
        # (07/10) o supervisor com o CODIGO, como vai no .json da base
        ("supervisor", "SUPERVISOR", 170, "w", False),
        ("curva", "CURVA", 52, "center", False),
        ("situacao", "SITUAÇÃO", 110, "w", False),
        ("dias", "DIAS S/ COMPRA", 96, "center", False),
        ("limite", "LIMITE DISP. R$", 106, "e", False),
        ("visitas", "VISITAS NO MÊS", 96, "center", False),
        ("ponto", "PONTO NO MAPA", 104, "center", False),
        ("status", "STATUS", 74, "center", False),
    ]

    def _montar_base_cliente(self):
        f = self.aba_base
        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 10))
        self.var_bc_busca = tk.StringVar()
        self.var_bc_vend = tk.StringVar(value=self.TODOS_BC)
        self.var_bc_sit = tk.StringVar(value=self.TODOS_BC)
        self.var_bc_st = tk.StringVar(value=self.TODOS_BC)
        ttk.Label(barra, text="Buscar").pack(side="left")
        e = ttk.Entry(barra, textvariable=self.var_bc_busca, width=28)
        e.pack(side="left", padx=(6, 14))
        e.bind("<KeyRelease>", lambda _e: self._bc_depois())
        for rot, var, larg, attr in (("Vendedor", self.var_bc_vend, 34,
                                      "cb_bc_vend"),
                                     ("Situação", self.var_bc_sit, 16,
                                      "cb_bc_sit"),
                                     ("Status", self.var_bc_st, 10,
                                      "cb_bc_st")):
            ttk.Label(barra, text=rot).pack(side="left")
            cb = ttk.Combobox(barra, textvariable=var, width=larg,
                              state="readonly")
            cb.pack(side="left", padx=(6, 14))
            cb.bind("<<ComboboxSelected>>", lambda _e: self.desenhar_base_cliente())
            setattr(self, attr, cb)
        self.cb_bc_sit.configure(values=[self.TODOS_BC] + nu.STATUS)
        self.cb_bc_st.configure(values=[self.TODOS_BC, "ATIVO", "INATIVO"])
        self.lbl_bc = ttk.Label(barra, text="", style="Sub.TLabel")
        self.lbl_bc.pack(side="right")

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(rod, text="INATIVAR SELECIONADOS", style="Big.TButton",
                   command=lambda: self._bc_marcar(True)).pack(side="right")
        ttk.Button(rod, text="Reativar selecionados",
                   command=lambda: self._bc_marcar(False)).pack(
                       side="right", padx=8)
        # (06/10) LATITUDE/LONGITUDE pelo endereco (OpenStreetMap)
        self.bt_geo = ttk.Button(rod, text="Atualizar coordenadas",
                                 command=self._bc_coordenadas)
        self.bt_geo.pack(side="left")
        self.lbl_geo = ttk.Label(rod, text="", style="Sub.TLabel")
        self.lbl_geo.pack(side="left", padx=10)
        self._geo_parar = None
        ttk.Label(rod, text="Inativar tira o cliente da rota e refaz o "
                            "Planner.", style="Sub.TLabel").pack(
                                side="right", padx=12)
        q, self.tab_bc = tabela(f, self.COLUNAS_BC, selecao="extended")
        q.pack(fill="both", expand=True)
        self.tab_bc.tag_configure("inativo", background=COR_INATIVO,
                                  foreground=COR_SUAVE)
        self._bc_job = None

    def _bc_depois(self):
        if self._bc_job:
            self.after_cancel(self._bc_job)
        self._bc_job = self.after(250, self.desenhar_base_cliente)

    def recarregar_base_cliente(self):
        zonas = {z["id"]: z for z in self.cfg["zonas"]}
        vends = sorted({nu.vendedor_do_cliente(self.cfg, c, zonas) or ""
                        for c in self.clientes or []})
        rot = [self.TODOS_BC] + [
            f"{v} {nu.pessoa_por_codigo(self.cfg, v).get('nome', '')}".strip()
            if v else SEM_VENDEDOR for v in vends]
        self.cb_bc_vend.configure(values=rot)
        if self.var_bc_vend.get() not in rot:
            self.var_bc_vend.set(self.TODOS_BC)
        self.desenhar_base_cliente()

    def desenhar_base_cliente(self):
        t = self.tab_bc
        t.delete(*t.get_children())
        if not self.clientes:
            self.lbl_bc.configure(text="Sem base carregada.")
            return
        zonas = {z["id"]: z for z in self.cfg["zonas"]}
        agenda = self._agenda_do_mes()
        busca = nu.norm(self.var_bc_busca.get())
        vend_f, sit_f, st_f = (self.var_bc_vend.get(), self.var_bc_sit.get(),
                               self.var_bc_st.get())
        n = inat = 0
        for c in self.clientes:
            cod_v = nu.vendedor_do_cliente(self.cfg, c, zonas) or ""
            rot_v = (f"{cod_v} {nu.pessoa_por_codigo(self.cfg, cod_v).get('nome', '')}"
                     .strip() if cod_v else SEM_VENDEDOR)
            sup = nu.chefe_de(self.cfg, cod_v) if cod_v else {}
            rot_s = (f"{nu.texto(sup.get('cod_protheus'))} "
                     f"{nu.texto(sup.get('nome'))}".strip()
                     if sup and sup.get("cargo") == "SUPERVISOR" else "")
            inativo = nu.cliente_inativo(self.cfg, c)
            status = nu.status_para_protheus(inativo)
            if vend_f != self.TODOS_BC and rot_v != vend_f:
                continue
            if sit_f != self.TODOS_BC and c["STATUS_CLIENTE"] != sit_f:
                continue
            if st_f != self.TODOS_BC and status != st_f:
                continue
            if busca and busca not in nu.norm(
                    f"{c['COD_CLIENTE']} {c['NOME_CLIENTE']} "
                    f"{c.get('NOME_FANTASIA', '')} {c['CIDADE']} {c['BAIRRO']}"):
                continue
            n += 1
            inat += inativo
            dias = c.get("DIAS_SEM_COMPRA")
            t.insert("", "end", iid=c["CHAVE_CLIENTE"],
                     tags=("inativo",) if inativo else (
                         ("zebra",) if n % 2 else ()),
                     values=(c["COD_CLIENTE"], c["LOJA"], c["NOME_CLIENTE"],
                             c.get("NOME_FANTASIA", ""), c["UF"], c["CIDADE"],
                             c["BAIRRO"], rot_v, rot_s, c["CURVA_RECEITA"],
                             c["STATUS_CLIENTE"],
                             "" if dias is None else int(dias),
                             dinheiro(c["LIMITE_DISPONIVEL"]),
                             len(agenda.get(c["CHAVE_CLIENTE"], [])),
                             {"endereco": "endereço", "bairro": "bairro",
                              "cidade": "cidade"}.get(
                                 geo_ponto(c), "—"), status))
        total_inat = len(nu.clientes_inativos(self.cfg))
        self.lbl_bc.configure(text=f"{n} cliente(s) na tela  ·  {inat} inativo(s)"
                                   f" na tela  ·  {total_inat} inativo(s) no "
                                   f"Planner")

    def _bc_coordenadas(self):
        """LATITUDE e LONGITUDE pelo ENDERECO (OpenStreetMap, 1 consulta por
        segundo), so de quem e novo ou mudou de endereco. Roda em segundo
        plano; o botao vira Parar. No fim, o Planner e refeito."""
        if self._geo_parar is not None:          # esta rodando: parar
            self._geo_parar.set()
            self.bt_geo.configure(text="Parando…")
            return
        try:
            import geocodificar as gc                   # noqa: PLC0415
        except ImportError:
            messagebox.showerror("Planner BAP", "Falta o geocodificar.py "
                                 "na pasta.", parent=self)
            return
        base = self.caminho("base_cliente")
        arq = gc.caminho(base)
        falta = len(gc.pendentes(self.clientes or [], gc.ler(arq)))
        if not falta:
            self.lbl_geo.configure(text="Coordenadas em dia.")
            gc.completar(self.clientes or [], arq)
            return
        if not messagebox.askyesno(
                "Planner BAP",
                f"Localizar {falta} cliente(s) pelo endereço "
                f"(OpenStreetMap, 1 por segundo: ~{max(1, falta // 50)} min)?"
                f"\n\nRoda em segundo plano; dá para parar e continuar "
                f"depois. No fim o Planner é refeito com a rota pelo "
                f"caminho mais curto.", parent=self):
            return
        parar = threading.Event()
        self._geo_parar = parar
        self.bt_geo.configure(text="Parar")
        estado = {"txt": f"Localizando 0 de {falta}…", "fim": None}

        def log(t):
            estado["txt"] = t
        clientes = list(self.clientes or [])

        def correr():
            try:
                estado["fim"] = gc.atualizar(base, clientes=clientes, log=log,
                                             parar=parar.is_set)
            except Exception as e:                      # noqa: BLE001
                estado["fim"] = {"erro": str(e), "consultados": 0,
                                 "achados": 0, "faltam": falta}
        threading.Thread(target=correr, daemon=True).start()

        def vigiar():
            if estado["fim"] is None:
                self.lbl_geo.configure(text=estado["txt"])
                self.after(1000, vigiar)
                return
            r = estado["fim"]
            self._geo_parar = None
            self.bt_geo.configure(text="Atualizar coordenadas")
            gc.completar(self.clientes or [], arq)
            nu.esquecer_rota()
            self._rota_an = None
            msg = (f"{r['achados']} de {r['consultados']} localizado(s)"
                   + (f" · faltam {r['faltam']}" if r["faltam"] else "")
                   + (f" · erro: {r['erro']}" if r.get("erro") else ""))
            self.lbl_geo.configure(text=msg)
            self.log(f"COORDENADAS: {msg}")
            if r["consultados"]:
                self.recalcular_planner()
                self.desenhar_base_cliente()
        self.after(1000, vigiar)

    def _bc_marcar(self, inativo):
        chaves = list(self.tab_bc.selection())
        if not chaves:
            messagebox.showinfo("Planner BAP", "Selecione os clientes na lista "
                                "(Ctrl ou Shift para vários).", parent=self)
            return
        muda = [ch for ch in chaves
                if nu.cliente_inativo(self.cfg, ch) != inativo]
        if not muda:
            messagebox.showinfo("Planner BAP", "Os selecionados já estão "
                                + ("inativos." if inativo else "ativos."),
                                parent=self)
            return
        if not messagebox.askyesno(
                "Planner BAP",
                (f"INATIVAR {len(muda)} cliente(s)?\n\nEles saem da rota do "
                 f"vendedor, o Planner é refeito sem eles e no .json da "
                 f"base de clientes vão com o vendedor e o supervisor "
                 f"padrão (o vendedor deixa de ver)."
                 if inativo else
                 f"Reativar {len(muda)} cliente(s)?\n\nEles voltam para a "
                 f"rota e o Planner é refeito."), parent=self):
            return
        nu.inativar_clientes(self.cfg, muda, inativo)
        self.log(("INATIVADOS: " if inativo else "REATIVADOS: ")
                 + ", ".join(muda))
        self._rota_an = None
        self.salvar()
        self.recalcular_planner()       # o Planner refeito sem (ou com) eles
        self.desenhar_base_cliente()
        self.aviso(f"{len(muda)} cliente(s) "
                   + ("inativado(s): fora da rota." if inativo
                      else "reativado(s): de volta à rota."), COR_OK)

    # =================================================================== 4
    # ROTA POR CIDADE: o calendario do vendedor, montado arrastando cidades
    CORES_CIDADE = ["#2F7D32", "#1F77B4", "#E67E22", "#C0392B", "#16A085",
                    "#9B59B6", "#7F8C8D", "#D35400", "#8E44AD", "#B7950B",
                    "#2C3E50", "#27AE60", "#2980B9", "#E74C3C", "#F39C12",
                    "#1ABC9C"]
    DIAS_CAL = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB")

    @staticmethod
    def _clarear(cor, f=0.86):
        r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % tuple(int(x + (255 - x) * f)
                                       for x in (r, g, b))

    def _montar_rota_cidade(self):
        f = self.aba_rota
        self._faixa_recalcular(f)
        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 10))
        ttk.Label(barra, text="Vendedor").pack(side="left")
        self.var_rc_vend = tk.StringVar()
        self.cb_rc_vend = ttk.Combobox(barra, textvariable=self.var_rc_vend,
                                       width=42, state="readonly")
        self.cb_rc_vend.pack(side="left", padx=(8, 16))
        self.cb_rc_vend.bind("<<ComboboxSelected>>",
                             lambda _: self._rc_vendedor_mudou())
        self.lbl_rc_info = ttk.Label(barra, text="", style="Sub.TLabel")
        self.lbl_rc_info.pack(side="left")
        self.lbl_rc_aviso = ttk.Label(barra, text="", foreground="#B7791F",
                                      font=("Segoe UI", 10, "bold"))
        self.lbl_rc_aviso.pack(side="right")

        rod = ttk.Frame(f)
        rod.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(rod, text="Limpar o vendedor",
                   command=self._rc_limpar).pack(side="left")
        self.mb_rc_copiar = ttk.Menubutton(rod, text="Copiar semana")
        self.mb_rc_copiar.pack(side="left", padx=8)
        self.menu_rc_copiar = tk.Menu(self.mb_rc_copiar, tearoff=False)
        self.mb_rc_copiar["menu"] = self.menu_rc_copiar
        ttk.Button(rod, text="GRAVAR E RECALCULAR", style="Big.TButton",
                   command=self._rc_gravar).pack(side="right")
        ttk.Label(rod, text="dia sem cidade = automático  ·  clique na "
                            "cidade para tirá-la da rota do mês",
                  style="Sub.TLabel"
                  ).pack(side="right", padx=14)

        corpo = ttk.Frame(f)
        corpo.pack(fill="both", expand=True)
        esq = ttk.Frame(corpo, width=330)
        esq.pack(side="left", fill="y", padx=(0, 14))
        esq.pack_propagate(False)
        ttk.Label(esq, text="CIDADES DELE  ·  arraste para o dia",
                  foreground=COR_ACENTO, font=("Segoe UI", 8, "bold")).pack(
                      anchor="w", pady=(0, 4))
        q, self.tab_rc_cid = tabela(
            esq, [("cidade", "CIDADE", 156, "w", True),
                  ("cli", "CLI.", 42, "center", False),
                  ("dias", "DIAS", 84, "center", False)], horizontal=False)
        q.pack(fill="both", expand=True)
        self.tab_rc_cid.tag_configure("semdia", background="#FFF8E6",
                                      foreground="#8A5A00")
        self.tab_rc_cid.tag_configure("fora", background="#F1F2F0",
                                      foreground="#A0A8A2")
        self.tab_rc_cid.bind("<ButtonPress-1>", self._rc_pegar_da_lista,
                             add="+")
        self.tab_rc_cid.bind("<B1-Motion>", self._rc_arrastando, add="+")
        self.tab_rc_cid.bind("<ButtonRelease-1>", self._rc_soltar, add="+")

        self.quadro_cal = tk.Frame(corpo, background=COR_LINHA)
        self.quadro_cal.pack(side="left", fill="both", expand=True)
        self._rc_cod = ""
        self._rc_cores = {}
        self._rc_arrasto = None
        self._rc_fantasma = None

    # ---- dados
    def _rc_vendedores(self):
        """Os vendedores que tem carteira (os que podem ter rota)."""
        com = {nu.vendedor_do_cliente(self.cfg, c,
                                      {z["id"]: z for z in self.cfg["zonas"]})
               for c in self.clientes} if self.clientes else set()
        return sorted((p for p in nu.vendedores(self.cfg)
                       if p["cod_protheus"] in com),
                      key=lambda p: p["nome"])

    def recarregar_rota_cidade(self):
        vends = self._rc_vendedores()
        rotulos = [nu.rotulo_pessoa(p) for p in vends]
        self._rc_por_rotulo = {nu.rotulo_pessoa(p): p["cod_protheus"]
                               for p in vends}
        self.cb_rc_vend.configure(values=rotulos)
        if self.var_rc_vend.get() not in rotulos:
            self.var_rc_vend.set(rotulos[0] if rotulos else "")
        self._rc_vendedor_mudou()

    def _rc_vendedor_mudou(self):
        self._rc_cod = (getattr(self, "_rc_por_rotulo", {}) or {}).get(
            self.var_rc_vend.get(), "")
        self._rc_cidades = (nu.cidades_do_vendedor(self.cfg, self.clientes,
                                                   self._rc_cod)
                            if self._rc_cod else [])
        self._rc_cores = {c["chave"]: self.CORES_CIDADE[i % len(
            self.CORES_CIDADE)] for i, c in enumerate(self._rc_cidades)}
        self._rc_desenhar()

    def _rc_cal(self) -> dict:
        # (17/10) com a REGRA DA CIDADE BASE: nos primeiros dias uteis so a
        # regiao da base (a cidade de fora sai, a base entra)
        return dict(nu.calendario_efetivo(self.cfg, self._rc_cod))

    def _rc_pode(self, ch, iso) -> bool:
        """A cidade pode ir para o dia? Se nao, avisa (regra da base)."""
        if nu.cidade_aceita_no_dia(self.cfg, self._rc_cod, ch, iso):
            return True
        v = nu.pessoa_por_codigo(self.cfg, self._rc_cod) or {}
        par = self.cfg["parametros"]
        messagebox.showinfo(
            "Planner BAP",
            f"Os {int(par.get('dias_cidade_base', 10) or 0)} primeiros dias "
            f"úteis do mês são da cidade base "
            f"({v.get('cidade_base', '') or 'sem cidade base'}) e das "
            f"cidades até {int(par.get('raio_base_km', 50) or 0)} km dela."
            f"\n\n{ch.split('|')[-1]} não entra nesses dias. Para abrir "
            f"exceção, use IMPORTAR AGENDA DE CIDADE (aba Parâmetros).",
            parent=self)
        return False

    def _rc_rota_dele(self) -> dict:
        """{data ISO: [linhas da rota]} do vendedor - a rota como ela sai
        hoje (cidades do calendario + o automatico dos dias sem cidade)."""
        por = defaultdict(list)
        if not self._rc_cod or not self.clientes:
            return por
        try:
            rota = nu.rota_do_mes(self.cfg, self.clientes)
        except Exception:                               # noqa: BLE001
            return por
        for r in rota:
            if nu.texto(r.get("COD_VENDEDOR")) != self._rc_cod:
                continue
            d = r.get("DATA")
            if isinstance(d, dt.datetime):
                d = d.date()
            if d:
                por[d.isoformat()].append(r)
        return por

    def _rc_mudar(self, cal):
        nu.gravar_rota_cidade(self.cfg, self._rc_cod, cal)
        self.marcar_pendente()
        self._rc_desenhar()

    # ---- desenho
    def _rc_desenhar(self):
        cal = self._rc_cal() if self._rc_cod else {}
        dias_de = Counter(ch for chs in cal.values() for ch in chs)
        self._rc_rota = self._rc_rota_dele()
        # (07/10) AUTO = o dia em que a cidade entrou SEM estar no
        # calendario: dia em branco OU encaixada por proximidade num dia
        # de outra cidade (antes so contava o dia em branco e a cidade
        # encaixada aparecia como "sem dia")
        auto_de = Counter(ch for iso, rs in self._rc_rota.items()
                          for ch in {nu.chave_da_cidade(r.get("UF"),
                                                        r.get("CIDADE"))
                                     for r in rs}
                          if ch not in (cal.get(iso) or []))
        fora = nu.cidades_fora_da_rota(self.cfg, self._rc_cod) \
            if self._rc_cod else set()
        t = self.tab_rc_cid
        t.delete(*t.get_children())
        for i, c in enumerate(self._rc_cidades):
            n = dias_de.get(c["chave"], 0)
            a = auto_de.get(c["chave"], 0)
            if c["chave"] in fora:          # tirada da rota: no fim, cinza
                continue
            t.insert("", "end", iid=c["chave"],
                     tags=("semdia",) if not n else (
                         ("zebra",) if i % 2 else ()),
                     values=(c["cidade"] or "(SEM CIDADE)", c["clientes"],
                             (f"{n}+{a} auto" if a else
                              f"{n} dia" + ("s" if n != 1 else ""))
                             if n else (f"auto · {a}" if a
                                        else "sem dia")))
        for c in self._rc_cidades:
            if c["chave"] in fora:
                t.insert("", "end", iid=c["chave"], tags=("fora",),
                         values=(c["cidade"] or "(SEM CIDADE)", c["clientes"],
                                 "fora"))
        # sem dia de verdade: nem no calendario nem na rota (encaixada por
        # proximidade ja tem dia)
        sem = sum(1 for c in self._rc_cidades
                  if not dias_de.get(c["chave"]) and not auto_de.get(
                      c["chave"]) and c["chave"] not in fora)
        self.lbl_rc_aviso.configure(
            text=f"⚠ {sem} cidade(s) sem dia" if sem and cal else "")
        previa = (nu.previa_rota_cidade(self.cfg, self.clientes, self._rc_cod)
                  if cal else {})
        zonas_dele = {id(z): z for _, z in nu.clientes_do_vendedor(
            self.cfg, self.clientes, self._rc_cod)}.values() \
            if self._rc_cod else []
        teto = nu._teto_do_vendedor(self.cfg, list(zonas_dele)) \
            if self._rc_cod else 0
        du = nu.dias_uteis(self.cfg["mes"], self.cfg.get("feriados") or [])
        cap_mes = sum(nu.teto_do_dia(teto, d[0], self.cfg["parametros"])
                      for d in nu.dias_do_mes(self.cfg["mes"],
                                              self.cfg.get("feriados") or [],
                                              False))
        sexta = nu.teto_do_dia(teto, dt.date(2026, 10, 2),
                               self.cfg["parametros"])
        self.lbl_rc_info.configure(
            text=f"{sum(c['clientes'] for c in self._rc_cidades)} clientes   "
                 f"{du} dias úteis   {teto} visitas/dia (sexta {sexta})   "
                 f"{cap_mes} capacidade no mês" if self._rc_cod else "")
        self._rc_teto = teto
        self._rc_restritos, _nb, self._rc_liberadas = \
            nu.regra_da_base_do_vendedor(self.cfg, self._rc_cod) \
            if self._rc_cod else (frozenset(), None, set())
        self._rc_desenhar_calendario(cal, previa, teto)
        self._rc_menu_copiar()

    def _rc_desenhar_calendario(self, cal, previa, teto):
        import calendar as _cal                         # noqa: PLC0415
        q = self.quadro_cal
        for w in q.winfo_children():
            w.destroy()
        ano, mes = (int(x) for x in self.cfg["mes"].split("-")[:2])
        fer = {nu.data_de(x) for x in self.cfg.get("feriados") or []}
        rota = {d[0] for d in nu.dias_do_mes(self.cfg["mes"],
                                             self.cfg.get("feriados") or [],
                                             True)}
        sab_ultimo = max((d for d in rota if d.weekday() == 5), default=None)
        nome = {c["chave"]: c["cidade"] or "(SEM CIDADE)"
                for c in self._rc_cidades}
        tk.Label(q, text="", background="#FAFBFA").grid(row=0, column=0,
                                                       sticky="nsew")
        for j, dn in enumerate(self.DIAS_CAL, start=1):
            tk.Label(q, text=dn, background="#FAFBFA", foreground=COR_SUAVE,
                     font=("Segoe UI", 8, "bold"), pady=4).grid(
                         row=0, column=j, sticky="nsew", padx=(1, 0),
                         pady=(0, 1))
        semanas = [s for s in _cal.Calendar(0).monthdatescalendar(ano, mes)
                   if any(d.month == mes and d.weekday() < 6 for d in s)]
        for i, sem in enumerate(semanas, start=1):
            dentro = [d for d in sem if d.month == mes and d.weekday() < 6]
            tk.Label(q, text=f"SEMANA {i}\n{dentro[0]:%d} a {dentro[-1]:%d/%m}",
                     background="#FAFBFA", foreground=COR_ACENTO,
                     font=("Segoe UI", 8, "bold"), justify="left",
                     anchor="w", padx=8).grid(row=i, column=0, sticky="nsew",
                                              pady=(0, 1))
            for j, d in enumerate(sem[:6], start=1):
                self._rc_celula(q, i, j, d, mes, fer, rota, sab_ultimo, cal,
                                previa, teto, nome)
        q.columnconfigure(0, weight=0, minsize=90)
        for j in range(1, 7):
            q.columnconfigure(j, weight=1, uniform="dia")
        for i in range(1, len(semanas) + 1):
            q.rowconfigure(i, weight=1, uniform="sem")

    def _rc_celula(self, q, i, j, d, mes, fer, rota, sab_ultimo, cal, previa,
                   teto, nome):
        iso = d.isoformat()
        if d.month != mes:
            cel = tk.Frame(q, background="#EEF0ED")
            cel.grid(row=i, column=j, sticky="nsew", padx=(1, 0), pady=(0, 1))
            return
        feriado = d in fer
        fundo = "#FCEFEE" if feriado else COR_PAPEL
        cel = tk.Frame(q, background=fundo)
        cel.grid(row=i, column=j, sticky="nsew", padx=(1, 0), pady=(0, 1))
        cel._rc_iso = iso if (d in rota) else None
        chs = cal.get(iso, [])
        teto = nu.teto_do_dia(teto, d, self.cfg["parametros"])
        da_rota = (getattr(self, "_rc_rota", {}) or {}).get(iso, [])
        # a carga do dia e a da ROTA (com o que entrou por proximidade);
        # sem rota calculada, a previa das cidades do calendario
        total = len(da_rota) if da_rota else sum(
            sum(previa.get((iso, ch), [0, 0])) for ch in chs)
        rot = f"{d.day:02d}"
        if d in (getattr(self, "_rc_restritos", None) or ()) and \
                iso not in (getattr(self, "_rc_liberadas", None) or ()):
            rot += "  base"             # (17/10) dia da cidade base
        if feriado:
            rot += "  FERIADO"
        elif d == sab_ultimo:
            rot += "  último sábado"
        cor_dia = COR_ALERTA if (feriado or (teto and total > teto)) \
            else "#A0A8A2"
        if teto and total > teto:
            rot += f"  ({total}/{teto})"
        elif total and d in rota:
            rot += f"   {total}/{teto}" if teto else f"   {total} vis."
        lb_dia = tk.Label(cel, text=rot, background=fundo, foreground=cor_dia,
                          font=("Segoe UI", 7), anchor="w")
        lb_dia.pack(fill="x", padx=4)
        if d in rota:                   # CLIQUE NO DIA: clientes e cidade
            for w in (cel, lb_dia):
                w.configure(cursor="hand2")
                w.bind("<ButtonRelease-1>",
                       lambda e, o=iso: self._rc_abrir_dia(o), add="+")
        if not chs and da_rota:         # dia sem cidade: o AUTOMATICO
            por_cid = Counter(nu.chave_da_cidade(r.get("UF"), r.get("CIDADE"))
                              for r in da_rota)
            alfa = sorted(por_cid.items(), key=lambda kv: nu.norm(
                nome.get(kv[0], kv[0].split("|")[-1])))
            for ch, n in alfa[:4]:
                cor = self._rc_cores.get(ch, COR_SUAVE)
                lb = tk.Label(cel, text=f"{nome.get(ch, ch.split('|')[-1])}"
                                        f" · {n} cli  (auto)",
                              background=COR_PAPEL, foreground=cor,
                              font=("Segoe UI", 8, "italic"), anchor="w",
                              cursor="hand2", highlightthickness=1,
                              highlightbackground=self._clarear(cor, .6))
                lb.pack(fill="x", padx=4, pady=(0, 3))
                # CLIQUE NA CIDADE: sai da rota do mes
                lb.bind("<ButtonRelease-1>",
                        lambda e, c=ch: self._rc_tirar_da_rota(c))
            if len(por_cid) > 4:
                tk.Label(cel, text=f"+{len(por_cid) - 4} cidade(s)",
                         background=fundo, foreground=COR_SUAVE,
                         font=("Segoe UI", 7)).pack(anchor="w", padx=4)
        # (07/10) dia COM cidade: o que entrou por PROXIMIDADE aparece
        # embaixo, em italico (auto)
        extras = Counter(nu.chave_da_cidade(r.get("UF"), r.get("CIDADE"))
                         for r in da_rota) if chs else Counter()
        for ch in chs:
            extras.pop(ch, None)
        for ch in sorted(chs, key=lambda c: nu.norm(
                nome.get(c, c.split("|")[-1]))):
            cor = self._rc_cores.get(ch, COR_SUAVE)
            novos, rep = previa.get((iso, ch), [0, 0])
            chip = tk.Frame(cel, background=cor)
            chip.pack(fill="x", padx=4, pady=(0, 3))
            corpo = tk.Frame(chip, background=self._clarear(cor))
            corpo.pack(fill="x", padx=(3, 0))
            t1 = tk.Label(corpo, text=nome.get(ch, ch.split("|")[-1]),
                          background=self._clarear(cor), foreground=COR_TEXTO,
                          font=("Segoe UI", 8), anchor="w", cursor="hand2")
            t1.pack(fill="x", padx=4)
            t2 = tk.Label(corpo, text=f"{novos} cli" + (f" · +{rep} repetidos"
                                                        if rep else ""),
                          background=self._clarear(cor), foreground=COR_SUAVE,
                          font=("Segoe UI", 7), anchor="w", cursor="hand2")
            t2.pack(fill="x", padx=4)
            for w in (chip, corpo, t1, t2):
                w.bind("<ButtonPress-1>",
                       lambda e, c=ch, o=iso: self._rc_pegar_chip(e, c, o))
                w.bind("<B1-Motion>", self._rc_arrastando)
                w.bind("<ButtonRelease-1>", self._rc_soltar)
        alfa = sorted(extras.items(), key=lambda kv: nu.norm(
            nome.get(kv[0], kv[0].split("|")[-1])))
        for ch, n in alfa[:3]:
            cor = self._rc_cores.get(ch, COR_SUAVE)
            lb = tk.Label(cel, text=f"+ {nome.get(ch, ch.split('|')[-1])}"
                                    f" · {n} cli  (auto)",
                          background=fundo, foreground=cor,
                          font=("Segoe UI", 7, "italic"), anchor="w",
                          cursor="hand2")
            lb.pack(fill="x", padx=4)
            lb.bind("<ButtonRelease-1>",
                    lambda e, c=ch: self._rc_tirar_da_rota(c))
        if len(alfa) > 3:
            tk.Label(cel, text=f"+{len(alfa) - 3} cidade(s)",
                     background=fundo, foreground=COR_SUAVE,
                     font=("Segoe UI", 7)).pack(anchor="w", padx=4)

    # ---- o dia: os clientes e a cidade
    def _rc_abrir_dia(self, iso):
        if getattr(self, "_rc_arrasto", None) or getattr(
                self, "_rc_fantasma", None) or not self._rc_cod:
            return
        DiaDaRota(self, iso)

    # ---- arrastar e soltar
    def _rc_pegar_da_lista(self, e):
        iid = self.tab_rc_cid.identify_row(e.y)
        self._rc_arrasto = {"cidade": iid, "origem": None,
                            "x": e.x_root, "y": e.y_root} if iid else None

    def _rc_pegar_chip(self, e, cidade, origem):
        self._rc_arrasto = {"cidade": cidade, "origem": origem,
                            "x": e.x_root, "y": e.y_root}

    def _rc_arrastando(self, e):
        a = self._rc_arrasto
        if not a:
            return
        if self._rc_fantasma is None:
            if abs(e.x_root - a["x"]) + abs(e.y_root - a["y"]) < 6:
                return
            g = tk.Toplevel(self)
            g.wm_overrideredirect(True)
            try:
                g.attributes("-topmost", True)
            except tk.TclError:
                pass
            nome = next((c["cidade"] for c in self._rc_cidades
                         if c["chave"] == a["cidade"]), a["cidade"])
            tk.Label(g, text=f"⠿ {nome}", background=COR_PAPEL,
                     foreground=COR_TEXTO, font=("Segoe UI", 9),
                     padx=8, pady=4, highlightthickness=1,
                     highlightbackground=COR_ACENTO).pack()
            self._rc_fantasma = g
        self._rc_fantasma.geometry(f"+{e.x_root + 12}+{e.y_root + 8}")

    def _rc_soltar(self, e):
        a, self._rc_arrasto = self._rc_arrasto, None
        g, self._rc_fantasma = self._rc_fantasma, None
        if g is not None:
            g.destroy()
        if not a:
            return
        cal = self._rc_cal()
        if g is None:                       # foi so um clique
            if a["origem"]:                 # na cidade do dia: sai da rota
                self._rc_tirar_da_rota(a["cidade"])
            elif a["cidade"] in nu.cidades_fora_da_rota(self.cfg,
                                                        self._rc_cod):
                self._rc_voltar_para_rota(a["cidade"])  # na lista: volta
            return
        alvo = self._rc_dia_em(e.x_root, e.y_root)
        if not alvo:
            return
        fora = nu.cidades_fora_da_rota(self.cfg, self._rc_cod)
        if a["cidade"] in fora:             # arrastou a tirada: volta
            nu.gravar_cidades_fora(self.cfg, self._rc_cod,
                                   fora - {a["cidade"]})
        if a["origem"] and a["origem"] != alvo:
            cal[a["origem"]] = [c for c in cal.get(a["origem"], [])
                                if c != a["cidade"]]
        if not self._rc_pode(a["cidade"], alvo):
            return
        if a["cidade"] not in cal.get(alvo, []):
            cal.setdefault(alvo, []).append(a["cidade"])
        self._rc_mudar(cal)

    def _rc_nome_cidade(self, ch):
        c = next((c for c in self._rc_cidades if c["chave"] == ch), None)
        return ((c["cidade"] if c else "") or ch.split("|")[-1],
                c["clientes"] if c else 0)

    def _rc_tirar_da_rota(self, ch):
        """CLIQUE NA CIDADE (fixa ou automatica): a cidade sai da rota do
        vendedor no mes - os clientes dela ficam sem visita."""
        if getattr(self, "_rc_fantasma", None) or not self._rc_cod or not ch:
            return
        nome, n = self._rc_nome_cidade(ch)
        if not messagebox.askyesno(
                "Planner BAP",
                f"Tirar {nome} ({n} cliente(s)) da rota de "
                f"{self._rotulo_mes()}?\n\nOs clientes dela ficam sem visita "
                f"no mês. Para voltar, clique na cidade (cinza) na lista "
                f"à esquerda ou arraste-a para um dia.", parent=self):
            return
        cal = {d: [c for c in chs if c != ch]
               for d, chs in self._rc_cal().items()}
        nu.gravar_cidades_fora(
            self.cfg, self._rc_cod,
            nu.cidades_fora_da_rota(self.cfg, self._rc_cod) | {ch})
        self._rc_mudar(cal)
        self.aviso(f"{nome} fora da rota. GRAVAR E RECALCULAR para valer.",
                   COR_OK)

    def _rc_voltar_para_rota(self, ch):
        nome, _n = self._rc_nome_cidade(ch)
        if not messagebox.askyesno(
                "Planner BAP", f"Voltar {nome} para a rota (automático)?",
                parent=self):
            return
        nu.gravar_cidades_fora(
            self.cfg, self._rc_cod,
            nu.cidades_fora_da_rota(self.cfg, self._rc_cod) - {ch})
        self._rc_mudar(self._rc_cal())

    def _rc_dia_em(self, x, y):
        w = self.winfo_containing(x, y)
        while w is not None:
            iso = getattr(w, "_rc_iso", "missing")
            if iso != "missing":
                return iso
            w = w.master
        return None

    # ---- botoes
    def _rc_limpar(self):
        if not self._rc_cod or not self._rc_cal():
            return
        if messagebox.askyesno("Planner BAP", "Tirar todas as cidades do "
                                              "calendário deste vendedor?"):
            self._rc_mudar({})

    def _rc_menu_copiar(self):
        import calendar as _cal                         # noqa: PLC0415
        m = self.menu_rc_copiar
        m.delete(0, "end")
        ano, mes = (int(x) for x in self.cfg["mes"].split("-")[:2])
        semanas = [s for s in _cal.Calendar(0).monthdatescalendar(ano, mes)
                   if any(d.month == mes and d.weekday() < 6 for d in s)]
        for i, _s in enumerate(semanas, start=1):
            m.add_command(label=f"Semana {i} para todas as semanas",
                          command=lambda n=i: self._rc_copiar_semana(n))

    def _rc_copiar_semana(self, n):
        import calendar as _cal                         # noqa: PLC0415
        ano, mes = (int(x) for x in self.cfg["mes"].split("-")[:2])
        semanas = [s for s in _cal.Calendar(0).monthdatescalendar(ano, mes)
                   if any(d.month == mes and d.weekday() < 6 for d in s)]
        rota = {d[0] for d in nu.dias_do_mes(self.cfg["mes"],
                                             self.cfg.get("feriados") or [],
                                             True)}
        cal = self._rc_cal()
        origem = {d.weekday(): cal.get(d.isoformat(), [])
                  for d in semanas[n - 1] if d.month == mes}
        for i, sem in enumerate(semanas, start=1):
            if i == n:
                continue
            for d in sem:
                if d.month != mes or d not in rota or d.weekday() not in origem:
                    continue
                if origem[d.weekday()]:
                    cal[d.isoformat()] = list(origem[d.weekday()])
                else:
                    cal.pop(d.isoformat(), None)
        self._rc_mudar(cal)

    def _rc_gravar(self):
        self.salvar()
        self.recalcular_planner()
        self._rc_desenhar()

    # =================================================================== 5
    # os recortes do analitico: por onde dá para olhar a carteira
    RECORTES_AN = ["ZONA", "VENDEDOR", "SUPERVISOR", "CIDADE", "UF", "SEGMENTO"]
    VISAO_CLIENTE = "CLIENTE (sem repetir)"
    VISAO_VISITA = "DIA E SEMANA (repetindo)"
    TODOS = "(todos)"
    # quantas linhas a aba 5 mostra na tela: a previa e so para conferir o
    # formato - o arquivo sai inteiro, com todas as visitas do recorte
    PREVIA_PR = 500

    # as colunas fixas da lista, e as que so aparecem na visao de visita
    COLUNAS_AN = [
        ("cod", "COD", 66, "w", False),
        ("loja", "LOJA", 46, "center", False),
        ("cliente", "CLIENTE", 220, "w", True),
        ("fantasia", "NOME FANTASIA", 160, "w", False),
        ("segmento", "SEGMENTO", 150, "w", False),
        ("zona", "ZONA", 90, "w", False),
        ("vendedor", "VENDEDOR", 150, "w", False),
        ("cidade", "CIDADE", 130, "w", False),
        ("bairro", "BAIRRO", 140, "w", False),
        ("endereco", "ENDERECO", 200, "w", False),
        ("curva", "CURVA", 62, "center", False),
        ("status", "STATUS", 70, "center", False),
        ("situacao", "SITUAÇÃO", 116, "w", False),
        ("limite", "LIMITE DISP. R$", 116, "e", False),
        ("atraso", "EM ATRASO R$", 112, "e", False),
        ("fat6", "FAT. M6M R$", 106, "e", False),
        ("facum", "FAT. ACUM. R$", 100, "e", False),
        ("ultima", "ULT. COMPRA", 86, "center", False),
        ("ultvend", "ULT. VEND.", 74, "center", False),
    ]
    COLUNAS_AN_VISITA = [
        ("semana", "SEMANA", 74, "center", False),
        ("dia", "DIA", 44, "center", False),
        ("diasem", "DIA DA SEMANA", 100, "w", False),
        ("data", "DATA", 84, "center", False),
        ("ordem", "ORDEM", 60, "center", False),
    ]
    COLUNAS_AN_CLIENTE = [
        ("visitas", "VISITAS/MES", 84, "center", False),
        ("dias", "DIAS DE VISITA", 130, "w", False),
        ("semanas", "SEMANAS", 90, "w", False),
    ]

    def _montar_analitico(self):
        # A aba e SO a rota. O IMPORTAR ROTA saiu: o caminho de ida e volta
        # do arquivo agora e um so - IMPORTAR e EXPORTAR o PLANNER, na aba
        # 5 PARAMETROS. Duas portas de entrada para a mesma coisa so
        # criavam duvida sobre qual valia.
        self._faixa_recalcular(self.aba_analitico)
        f = ttk.Frame(self.aba_analitico, padding=(2, 8, 2, 2))
        f.pack(fill="both", expand=True)

        topo = ttk.Frame(f)
        topo.pack(fill="x", pady=(0, 6))
        ttk.Label(topo, text="Ver por:").pack(side="left")
        self.var_tipo_an = tk.StringVar(value="ZONA")
        cb_tipo = ttk.Combobox(topo, textvariable=self.var_tipo_an, width=13,
                               values=self.RECORTES_AN, state="readonly")
        cb_tipo.pack(side="left", padx=(6, 12))
        cb_tipo.bind("<<ComboboxSelected>>", lambda _: self._tipo_an_mudou())

        self.lbl_alvo_an = ttk.Label(topo, text="Zona:")
        self.lbl_alvo_an.pack(side="left")
        self.var_zona_an = tk.StringVar()
        self.cb_zona_an = ttk.Combobox(topo, textvariable=self.var_zona_an,
                                       width=32, state="readonly")
        self.cb_zona_an.pack(side="left", padx=6)
        self.cb_zona_an.bind("<<ComboboxSelected>>",
                             lambda _: self.desenhar_analitico())

        ttk.Label(topo, text="   Visao:").pack(side="left")
        self.var_visao_an = tk.StringVar(value=self.VISAO_CLIENTE)
        cb_visao = ttk.Combobox(topo, textvariable=self.var_visao_an, width=24,
                                values=[self.VISAO_CLIENTE, self.VISAO_VISITA],
                                state="readonly")
        cb_visao.pack(side="left", padx=6)
        cb_visao.bind("<<ComboboxSelected>>", lambda _: self._visao_an_mudou())

        ttk.Button(topo, text="EXPORTAR ROTA", style="Big.TButton",
                   command=self.exportar_rota).pack(side="right")

        # ---- filtros de agenda: so fazem sentido na visao de visita ------
        self.linha_agenda = ttk.Frame(f)
        ttk.Label(self.linha_agenda, text="Semana:").pack(side="left")
        self.var_semana_an = tk.StringVar(value=self.TODOS)
        self.cb_semana_an = ttk.Combobox(self.linha_agenda, width=12,
                                         textvariable=self.var_semana_an,
                                         state="readonly")
        self.cb_semana_an.pack(side="left", padx=(6, 14))
        self.cb_semana_an.bind("<<ComboboxSelected>>",
                               lambda _: self.desenhar_analitico())
        ttk.Label(self.linha_agenda, text="Dia do mes:").pack(side="left")
        self.var_dia_an = tk.StringVar(value=self.TODOS)
        self.cb_dia_an = ttk.Combobox(self.linha_agenda, width=12,
                                      textvariable=self.var_dia_an,
                                      state="readonly")
        self.cb_dia_an.pack(side="left", padx=6)
        self.cb_dia_an.bind("<<ComboboxSelected>>",
                            lambda _: self.desenhar_analitico())
        ttk.Button(self.linha_agenda, text="Limpar dia e semana",
                   command=self.limpar_agenda_an).pack(side="left", padx=10)
        ttk.Label(self.linha_agenda, style="Sub.TLabel",
                  text="Nesta visao o cliente aparece uma vez por visita. "
                       "Na visao CLIENTE ele aparece uma vez so, com os dias "
                       "dele na ultima coluna.").pack(side="left", padx=10)

        self.lbl_an = ttk.Label(f, text="", style="Sub.TLabel",
                                background=COR_ZEBRA, padding=(10, 6),
                                anchor="w")
        self.lbl_an.pack(fill="x", pady=(0, 4))

        self.quadro_an = ttk.Frame(f)
        self.quadro_an.pack(fill="both", expand=True)
        self.tab_an = None
        self._montar_tabela_an()

        # ---- mover o cliente de zona ou de vendedor ----------------------
        mover = ttk.LabelFrame(f, text=" Mudar os clientes marcados na lista ",
                               padding=(12, 8, 12, 10))
        mover.pack(fill="x", pady=(10, 0))
        linha = ttk.Frame(mover)
        linha.pack(fill="x")
        ttk.Label(linha, text="Zona:").pack(side="left")
        self.var_nova_zona_an = tk.StringVar()
        self.cb_nova_zona_an = ttk.Combobox(linha, width=32, state="readonly",
                                            textvariable=self.var_nova_zona_an)
        self.cb_nova_zona_an.pack(side="left", padx=(6, 6))
        ttk.Button(linha, text="Mudar de zona",
                   command=self.mudar_zona_cliente).pack(side="left")

        ttk.Label(linha, text="     Vendedor:").pack(side="left")
        self.var_novo_vend_an = tk.StringVar()
        self.cb_novo_vend_an = ttk.Combobox(linha, width=30, state="readonly",
                                            textvariable=self.var_novo_vend_an)
        self.cb_novo_vend_an.pack(side="left", padx=(6, 6))
        ttk.Button(linha, text="Mudar de vendedor",
                   command=self.mudar_vendedor_cliente).pack(side="left")

        linha2 = ttk.Frame(mover)
        linha2.pack(fill="x", pady=(8, 0))
        ttk.Label(linha2, text="Semana:").pack(side="left")
        self.var_nova_semana_an = tk.StringVar()
        self.cb_nova_semana_an = ttk.Combobox(
            linha2, width=12, state="readonly",
            textvariable=self.var_nova_semana_an)
        self.cb_nova_semana_an.pack(side="left", padx=(6, 6))
        ttk.Button(linha2, text="Mudar a semana",
                   command=self.mudar_semana_cliente).pack(side="left")

        ttk.Label(linha2, text="     Dia do mes:").pack(side="left")
        self.var_novo_dia_an = tk.StringVar()
        self.cb_novo_dia_an = ttk.Combobox(linha2, width=12, state="readonly",
                                           textvariable=self.var_novo_dia_an)
        self.cb_novo_dia_an.pack(side="left", padx=(6, 6))
        ttk.Button(linha2, text="Mudar o dia",
                   command=self.mudar_dia_cliente).pack(side="left")
        ttk.Button(linha2, text="Desfazer (voltar ao automatico)",
                   command=self.desfazer_excecao).pack(side="left", padx=10)

        self.lbl_mover_an = ttk.Label(
            mover, style="Sub.TLabel", wraplength=1250,
            text="Marque um ou mais clientes na lista (Ctrl+clique) e escolha "
                 "a zona, o vendedor, a semana ou o dia. A troca vale so para "
                 "esses clientes - o bairro deles continua onde esta. Linha "
                 "amarela = cliente trocado a mao.")
        self.lbl_mover_an.pack(anchor="w", pady=(8, 0))
        legenda_de_cores(f, [
            (COR_ESTOURO, "cliente INADIMPLENTE (valor em atraso)"),
            (COR_AVISO, "cliente TROCADO A MAO por voce"),
            (COR_SELECAO, "linha marcada agora"),
            (COR_TOTAL, "linha TOTAL - o que esta na tela"),
        ]).pack(anchor="w", pady=(10, 0))
        self._visao_an_mudou(redesenhar=False)

    def _montar_tabela_an(self):
        """A tabela muda de colunas conforme a visao escolhida."""
        if self.tab_an is not None:
            for filho in self.quadro_an.winfo_children():
                filho.destroy()
        if self.var_visao_an.get() == self.VISAO_VISITA:
            colunas = self.COLUNAS_AN_VISITA + self.COLUNAS_AN
        else:
            colunas = self.COLUNAS_AN + self.COLUNAS_AN_CLIENTE
        quadro, self.tab_an = tabela(self.quadro_an, colunas,
                                     selecao="extended", rodape=True)
        quadro.pack(fill="both", expand=True)
        self.tab_an.tag_configure("inad", background=COR_ESTOURO)
        self.tab_an.tag_configure("excecao", background=COR_AVISO)

    def _visao_an_mudou(self, redesenhar=True):
        de_visita = self.var_visao_an.get() == self.VISAO_VISITA
        if de_visita:
            self.linha_agenda.pack(fill="x", pady=(0, 6),
                                   before=self.lbl_an)
        else:
            self.linha_agenda.pack_forget()
        self._montar_tabela_an()
        if redesenhar:
            self.desenhar_analitico()

    def limpar_agenda_an(self):
        self.var_semana_an.set(self.TODOS)
        self.var_dia_an.set(self.TODOS)
        self.desenhar_analitico()

    def _tipo_an_mudou(self):
        self.lbl_alvo_an.configure(text=self.var_tipo_an.get().capitalize() + ":")
        self.recarregar_zonas_analitico(manter=False)

    def _opcoes_do_recorte(self, tipo=None):
        """
        A lista do combo, conforme o recorte escolhido.

        A PRIMEIRA OPCAO E SEMPRE "(todos)": a base inteira, sem recorte
        nenhum. Sem ela so dava para olhar uma UF, uma zona ou um
        vendedor de cada vez - e a pergunta "como esta a BAP toda" nao
        tinha resposta nesta aba.
        """
        return [self.TODOS] + self._alvos_do_recorte(tipo)

    def _alvos_do_recorte(self, tipo=None):
        tipo = tipo or self.var_tipo_an.get()
        if tipo == "ZONA":
            return [f"{z.get('codigo','')} - {z['nome']}"
                    for z in sorted(self.cfg["zonas"],
                                    key=lambda x: x.get("codigo") or "ZZZ")
                    if self.contagem_zona.get(z["id"], 0)
                    or any(nu.zona_do_cliente(self.cfg, c) == z["id"]
                           for c in self.clientes)]
        if tipo == "VENDEDOR":
            usados = {nu.vendedor_do_cliente(self.cfg, c) for c in self.clientes}
            return [nu.rotulo_pessoa(p) for p in
                    sorted(nu.vendedores(self.cfg), key=lambda x: x["nome"])
                    if p["cod_protheus"] in usados]
        if tipo == "SUPERVISOR":
            nomes = {nu.nome_supervisor(self.cfg,
                                        nu.vendedor_do_cliente(self.cfg, c))
                     for c in self.clientes}
            return sorted(n for n in nomes if n)
        if tipo == "CIDADE":
            return sorted({f"{c['UF']} - {c['CIDADE']}" for c in self.clientes})
        if tipo == "SEGMENTO":
            usados = {nu.segmento_do_cliente(c) for c in self.clientes}
            return [sg for sg in nu.SEGMENTOS if sg in usados] + sorted(
                usados - set(nu.SEGMENTOS))
        return sorted({c["UF"] for c in self.clientes if c["UF"]})

    def _clientes_do_recorte(self, tipo=None, alvo=None):
        """Os clientes que o recorte escolhido seleciona."""
        tipo = tipo or self.var_tipo_an.get()
        alvo = alvo if alvo is not None else self.var_zona_an.get()
        if not alvo or not self.clientes:
            return []
        if alvo == self.TODOS:
            return list(self.clientes)
        if tipo == "ZONA":
            codigo = alvo.split(" - ")[0]
            z = next((x for x in self.cfg["zonas"]
                      if x.get("codigo") == codigo), None)
            if not z:
                return []
            return [c for c in self.clientes
                    if nu.zona_do_cliente(self.cfg, c) == z["id"]]
        if tipo == "VENDEDOR":
            cod = alvo.split(" - ")[0]
            return [c for c in self.clientes
                    if nu.vendedor_do_cliente(self.cfg, c) == cod]
        if tipo == "SUPERVISOR":
            return [c for c in self.clientes
                    if nu.nome_supervisor(
                        self.cfg, nu.vendedor_do_cliente(self.cfg, c)) == alvo]
        if tipo == "CIDADE":
            uf, _, cidade = alvo.partition(" - ")
            return [c for c in self.clientes
                    if c["UF"] == uf and c["CIDADE"] == cidade]
        if tipo == "SEGMENTO":
            return [c for c in self.clientes
                    if nu.segmento_do_cliente(c) == alvo]
        return [c for c in self.clientes if c["UF"] == alvo]

    def recarregar_zonas_analitico(self, manter=True):
        opcoes = self._opcoes_do_recorte()
        self.cb_zona_an.configure(values=opcoes)
        if not opcoes:
            self.var_zona_an.set("")
        elif not manter or self.var_zona_an.get() not in opcoes:
            self.var_zona_an.set(opcoes[0])
        # as listas de destino da troca
        self.cb_nova_zona_an.configure(
            values=[f"{z.get('codigo','')} - {z['nome']}"
                    for z in sorted(self.cfg["zonas"],
                                    key=lambda x: x.get("codigo") or "ZZZ")])
        self.cb_novo_vend_an.configure(
            values=[nu.rotulo_pessoa(p) for p in
                    sorted(nu.vendedores(self.cfg), key=lambda x: x["nome"])])
        # as semanas e os dias que o mes tem
        agenda_mes = nu.dias_do_mes(self.cfg["mes"],
                                    self.cfg.get("feriados") or [], True)
        self.cb_nova_semana_an.configure(
            values=[str(s_) for s_ in sorted({d[2] for d in agenda_mes})])
        self.cb_novo_dia_an.configure(
            values=[f"{d[0].day} ({d[1][:3]})" for d in agenda_mes])
        self._rota_an = None            # a agenda e refeita na proxima pintura
        self.desenhar_analitico()

    # ---- a agenda do mes, por cliente -----------------------------------
    def _agenda_do_mes(self):
        """
        As visitas do mes, guardadas para nao refazer a rota a cada clique.
        Devolve {chave_cliente: [linha da rota, ...]}.
        """
        if getattr(self, "_rota_an", None) is None:
            porcliente = defaultdict(list)
            if self.clientes and self.cfg["zonas"]:
                for r in nu.gerar_rota(self.cfg, self.clientes):
                    porcliente[r["CHAVE_CLIENTE"]].append(r)
                # cidade cujo dia marcado nao existia no mes: nao se muda a
                # rota em silencio - o log diz qual foi e para onde ela foi
                for aviso in getattr(nu.gerar_rota, "avisos", []) or []:
                    self.log(f"DIA DA CIDADE: {aviso}")
            self._rota_an = porcliente
        return self._rota_an

    def _encher_filtros_agenda(self, visitas):
        semanas = sorted({r["SEMANA"] for r in visitas},
                         key=lambda x: int(x.split()[-1]) if x.split()[-1].isdigit() else 0)
        dias = sorted({r["DIA_DO_MES"] for r in visitas})
        self.cb_semana_an.configure(values=[self.TODOS] + semanas)
        self.cb_dia_an.configure(values=[self.TODOS] + [str(d) for d in dias])
        if self.var_semana_an.get() not in ([self.TODOS] + semanas):
            self.var_semana_an.set(self.TODOS)
        if self.var_dia_an.get() not in ([self.TODOS] + [str(d) for d in dias]):
            self.var_dia_an.set(self.TODOS)

    def desenhar_analitico(self):
        lista = self._clientes_do_recorte()
        zonas = {z["id"]: z for z in self.cfg["zonas"]}
        agenda = self._agenda_do_mes()
        de_visita = self.var_visao_an.get() == self.VISAO_VISITA

        # na visao de visita a linha e a VISITA, e o filtro de dia/semana vale
        visitas = []
        for c in lista:
            visitas.extend(agenda.get(c["CHAVE_CLIENTE"], []))
        if de_visita:
            self._encher_filtros_agenda(visitas)
            if self.var_semana_an.get() != self.TODOS:
                visitas = [r for r in visitas
                           if r["SEMANA"] == self.var_semana_an.get()]
            if self.var_dia_an.get() != self.TODOS:
                visitas = [r for r in visitas
                           if str(r["DIA_DO_MES"]) == self.var_dia_an.get()]
            visitas.sort(key=lambda r: (r["DATA"], r["ORDEM_DE_VISITA"]))
            self._visitas_an = visitas
            porchave = {c["CHAVE_CLIENTE"]: c for c in lista}
            fonte = [(r, porchave[r["CHAVE_CLIENTE"]]) for r in visitas]
        else:
            lista.sort(key=lambda c: (c["UF"], c["CIDADE"], c["BAIRRO"],
                                      -c["RECEITA_ACUMULADA"], c["NOME_CLIENTE"]))
            self._visitas_an = visitas
            fonte = [(None, c) for c in lista]
        self._linhas_an = lista

        self._silencio = True
        try:
            self.tab_an.delete(*self.tab_an.get_children())
            if not fonte:
                escrever_total(self.tab_an, None)
                self.lbl_an.configure(
                    text="Nada para mostrar. Importe a base na aba 3 e "
                         "cadastre as zonas, ou troque o recorte aqui em cima."
                    if not lista else
                    "Nenhuma visita neste filtro de dia/semana. "
                    "Use 'Limpar dia e semana'.")
                return
            for i, (r, c) in enumerate(fonte):
                zid = nu.zona_do_cliente(self.cfg, c)
                cod_v = nu.vendedor_do_cliente(self.cfg, c, zonas)
                v = nu.pessoa_por_codigo(self.cfg, cod_v)
                excecao = nu.excecao_do_cliente(self.cfg, c)
                if excecao:
                    tags = ("excecao",)
                elif c["VALOR_EM_ATRASO"] > 0:
                    tags = ("inad",)
                else:
                    tags = ("zebra",) if i % 2 else ()
                comum = (
                    c["COD_CLIENTE"], c["LOJA"], c["NOME_CLIENTE"],
                    c.get("NOME_FANTASIA", ""), c.get("SEGMENTO", ""),
                    (zonas.get(zid) or {}).get("codigo", "") or "(sem zona)",
                    (f"{cod_v} {v.get('nome','')}".strip()
                     if cod_v else SEM_VENDEDOR),
                    c["CIDADE"], c["BAIRRO"], c["ENDERECO"],
                    c["CURVA_RECEITA"],
                    # STATUS: o ATIVO/INATIVO do Planner (so e INATIVO quem
                    # foi inativado na aba Base cliente; no .json vai ATIVO
                    # com o vendedor padrao - 20/10);
                    # SITUACAO: os dias sem compra
                    nu.status_para_protheus(nu.cliente_inativo(self.cfg, c)),
                    c["STATUS_CLIENTE"],
                    dinheiro(c["LIMITE_DISPONIVEL"]),
                    dinheiro(c["VALOR_EM_ATRASO"]),
                    dinheiro(c.get("RECEITA_6M", c["RECEITA_PERIODO"])),
                    dinheiro(c["RECEITA_ACUMULADA"]),
                    c["ULTIMA_COMPRA"].strftime("%d/%m/%Y")
                    if c["ULTIMA_COMPRA"] else "",
                    c["COD_ULTIMO_VENDEDOR"])
                if de_visita:
                    valores = (r["SEMANA"].replace("Semana ", ""),
                               r["DIA_DO_MES"], r["DIA_DA_SEMANA"],
                               r["DATA"].strftime("%d/%m/%Y"),
                               r["ORDEM_DE_VISITA"]) + comum
                    iid = f"{c['CHAVE_CLIENTE']}|{r['DATA']}|{r['VISITA_NO_MES']}"
                else:
                    minhas = agenda.get(c["CHAVE_CLIENTE"], [])
                    dias = sorted({x["DIA_DO_MES"] for x in minhas})
                    semanas = sorted({x["SEMANA"].replace("Semana ", "")
                                      for x in minhas})
                    valores = comum + (
                        len(minhas),
                        ", ".join(str(d) for d in dias) or "-",
                        ", ".join(semanas) or "-")
                    iid = c["CHAVE_CLIENTE"]
                self.tab_an.insert("", "end", iid=iid, tags=tags,
                                   values=valores)
            escrever_total(self.tab_an,
                           self._total_analitico(fonte, de_visita, visitas))
            reaplicar_ordem(self.tab_an)
        finally:
            self._silencio = False

        inad = sum(1 for c in lista if c["VALOR_EM_ATRASO"] > 0)
        acum = sum(c["RECEITA_ACUMULADA"] for c in lista)
        m6 = sum(c.get("RECEITA_6M", 0.0) for c in lista)
        trocados = sum(1 for c in lista if nu.excecao_do_cliente(self.cfg, c))
        sem_rota = sum(1 for c in lista if not agenda.get(c["CHAVE_CLIENTE"]))
        self.lbl_an.configure(
            text=("A BAP INTEIRA (todos)"
                  if self.var_zona_an.get() == self.TODOS else
                  f"{self.var_tipo_an.get()}: {self.var_zona_an.get()}")
                 + f"   |   {len(lista)} cliente(s)"
                 + (f"   |   {len(visitas)} visita(s) no mes" if visitas else "")
                 + f"   |   {inad} inadimplente(s)"
                 f"   |   FAT. M6M R$ {dinheiro(m6 / 6)}"
                 f"   |   FAT. ACUM. R$ {dinheiro(acum)}"
                 + (f"   |   {trocados} trocado(s) a mao" if trocados else "")
                 + (f"   |   {sem_rota} sem rota (zona sem vendedor)"
                    if sem_rota else ""))

    def _total_analitico(self, fonte, de_visita, visitas):
        """
        A linha TOTAL presa no rodape do analitico. Ela conta o que esta
        na tela AGORA (o filtro de dia e semana ja entrou), e o dinheiro
        e somado por CLIENTE - na visao de visita o mesmo cliente aparece
        duas vezes e nao pode contar duas vezes.
        """
        vistos, unicos = set(), []
        for _, c in fonte:
            if c["CHAVE_CLIENTE"] not in vistos:
                vistos.add(c["CHAVE_CLIENTE"])
                unicos.append(c)
        soma = lambda campo: dinheiro(sum(c.get(campo, 0.0) or 0.0
                                          for c in unicos))
        celulas = {
            self.tab_an["columns"][0]: ROTULO_TOTAL,
            "diasem": f"{len(fonte)} visitas" if de_visita else "",
            "cliente": f"{len(unicos)} clientes",
            "cidade": f"{len({(c['UF'], c['CIDADE']) for c in unicos})} cidades",
            "bairro": f"{len({(c['UF'], c['CIDADE'], c['BAIRRO']) for c in unicos})}"
                      " bairros",
            "situacao": f"{sum(1 for c in unicos if c['VALOR_EM_ATRASO'] > 0)}"
                        " inadimplentes",
            "limite": soma("LIMITE_DISPONIVEL"),
            "atraso": soma("VALOR_EM_ATRASO"),
            "fat6": soma("RECEITA_6M"),
            "facum": soma("RECEITA_ACUMULADA"),
            "visitas": len(visitas) if not de_visita else "",
        }
        return tuple(celulas.get(c, "") for c in self.tab_an["columns"])

    # ---- trocar o cliente de zona / de vendedor -------------------------
    def _marcados_an(self):
        """As chaves de cliente marcadas (a visao de visita repete a linha)."""
        marcados = [x.split("|")[0] for x in self.tab_an.selection()]
        vistos, saida = set(), []
        for m in marcados:
            if m not in vistos:
                vistos.add(m)
                saida.append(m)
        if not saida:
            messagebox.showinfo("Planner BAP",
                                "Marque na lista os clientes que voce quer "
                                "mudar (clique numa linha; Ctrl+clique para "
                                "varias).")
        return saida

    def mudar_zona_cliente(self):
        marcados = self._marcados_an()
        if not marcados:
            return
        escolha = self.var_nova_zona_an.get()
        if not escolha:
            messagebox.showinfo("Planner BAP", "Escolha a zona de destino.")
            return
        codigo = escolha.split(" - ")[0]
        z = next((x for x in self.cfg["zonas"] if x.get("codigo") == codigo), None)
        if not z:
            return
        nu.marcar_excecao(self.cfg, marcados, zona=z["id"])
        self._depois_de_trocar(f"{len(marcados)} cliente(s) foram para a zona "
                               f"{z.get('codigo','')} - {z['nome']}.")

    def mudar_vendedor_cliente(self):
        marcados = self._marcados_an()
        if not marcados:
            return
        escolha = self.var_novo_vend_an.get()
        if not escolha:
            messagebox.showinfo("Planner BAP",
                                "Escolha o vendedor de destino.")
            return
        cod = escolha.split(" - ")[0]
        nu.marcar_excecao(self.cfg, marcados, vendedor=cod)
        self._depois_de_trocar(f"{len(marcados)} cliente(s) passaram a ser do "
                               f"vendedor {escolha}.")

    def mudar_semana_cliente(self):
        marcados = self._marcados_an()
        if not marcados:
            return
        semana = self.var_nova_semana_an.get().strip()
        if not semana.isdigit():
            messagebox.showinfo("Planner BAP",
                                "Escolha a semana de destino.")
            return
        nu.marcar_excecao(self.cfg, marcados, semana=int(semana), dia="")
        self._depois_de_trocar(f"{len(marcados)} cliente(s) passaram para a "
                               f"semana {semana}.")

    def mudar_dia_cliente(self):
        marcados = self._marcados_an()
        if not marcados:
            return
        escolha = self.var_novo_dia_an.get().split(" ")[0].strip()
        if not escolha.isdigit():
            messagebox.showinfo("Planner BAP",
                                "Escolha o dia do mes de destino.")
            return
        nu.marcar_excecao(self.cfg, marcados, dia=int(escolha), semana="")
        self._depois_de_trocar(f"{len(marcados)} cliente(s) passaram para o "
                               f"dia {escolha}.")

    def desfazer_excecao(self):
        marcados = self._marcados_an()
        if not marcados:
            return
        nu.marcar_excecao(self.cfg, marcados, zona="", vendedor="",
                          semana="", dia="")
        self._depois_de_trocar(f"{len(marcados)} cliente(s) voltaram para o "
                               f"automatico: zona e vendedor do bairro, e o "
                               f"dia que a rota calcular.")

    def _depois_de_trocar(self, mensagem):
        self.salvar()
        self._ger_sujo = True
        self._rota_an = None            # a agenda mudou: refaz na proxima
        self.marcar_pendente()
        self.desenhar_analitico()
        self.lbl_mover_an.configure(text=mensagem + "  " + AVISO_RECALCULAR,
                                    foreground=COR_ALERTA)
        self.log(mensagem)
        self.aviso(mensagem, COR_OK)

    # ---- exportar so o que esta na tela ---------------------------------
    def exportar_rota(self):
        lista = getattr(self, "_linhas_an", [])
        if not lista:
            messagebox.showinfo("Planner BAP",
                                "Nao ha nada na tela para exportar.")
            return
        de_visita = self.var_visao_an.get() == self.VISAO_VISITA
        tipo, alvo = self.var_tipo_an.get(), self.var_zona_an.get()
        rotulo = f"{tipo} = {alvo}"
        semanas = ([self.var_semana_an.get()]
                   if de_visita and self.var_semana_an.get() != self.TODOS else None)
        dias = ([int(self.var_dia_an.get())]
                if de_visita and self.var_dia_an.get() != self.TODOS else None)
        if semanas:
            rotulo += f" | {semanas[0]}"
        if dias:
            rotulo += f" | dia {dias[0]}"
        pedaco = nu.norm(alvo).replace(" ", "_").replace("/", "-")[:28]
        visao = "VISITA" if de_visita else "CLIENTE"
        destino = (self.caminho("saida") /
                   f"ROTA_{nu.norm(tipo)}_{pedaco}_{visao}_"
                   f"{dt.date.today():%Y%m%d}.xlsx")
        chaves = [c["CHAVE_CLIENTE"] for c in lista]
        cfg = json.loads(json.dumps(self.cfg))
        clientes = self.clientes

        def pronto(linhas, erro):
            if erro:
                messagebox.showerror("Planner BAP", str(erro[0]))
                self.log(erro[1])
                self.aviso("Falhou ao exportar a rota.", COR_ALERTA)
                return
            unidade = "visita(s)" if de_visita else "cliente(s)"
            self.log(f"Rota exportada: {destino} ({len(linhas)} {unidade} de "
                     f"{len(chaves)} cliente(s), {rotulo})")
            self.aviso(f"{destino.name}: {len(linhas)} {unidade}.", COR_OK)
            if not linhas:
                messagebox.showinfo(
                    "Planner BAP",
                    f"{destino.name}\n\nO arquivo saiu VAZIO: nenhum desses "
                    f"clientes entra na rota (zona sem vendedor).\n\n"
                    f"Gravado em:\n{destino.parent}")
                return
            if messagebox.askyesno(
                    "Planner BAP",
                    f"{destino.name}\n\n{rotulo}\n"
                    f"{'Uma linha por visita' if de_visita else 'Uma linha por cliente'}"
                    f"\n{len(linhas)} {unidade}\n\nGravado em:{destino.parent}"
                    f"\n\nAbrir agora?"):
                self._abrir(destino)

        self._tarefa(lambda: nu.gravar_recorte(cfg, clientes, destino, chaves,
                                               rotulo, visao, dias, semanas),
                     pronto, f"Gerando {destino.name}...")

    # =================================================================== 5
    # EXPORTAR FORMATO PROTHEUS
    #
    # O Protheus nao le o Excel do PLANNER. Esta aba escreve A MESMA ROTA
    # num arquivo .json com os doze campos que ele espera - nada aqui
    # recalcula visita, dia ou ordem: tudo sai do mesmo gerar_rota que
    # monta o PLANNER e o analitico. O que muda e so o nome dos campos e
    # o formato do arquivo.
    def _montar_protheus(self):
        self._faixa_recalcular(self.aba_protheus)
        f = ttk.Frame(self.aba_protheus, padding=(2, 8, 2, 2))
        f.pack(fill="both", expand=True)

        topo = ttk.Frame(f)
        topo.pack(fill="x", pady=(0, 6))
        ttk.Label(topo, text="Exportar:").pack(side="left")
        self.var_tipo_pr = tk.StringVar(value="ZONA")
        cb_tipo = ttk.Combobox(topo, textvariable=self.var_tipo_pr, width=13,
                               values=self.RECORTES_AN, state="readonly")
        cb_tipo.pack(side="left", padx=(6, 12))
        cb_tipo.bind("<<ComboboxSelected>>", lambda _: self._tipo_pr_mudou())

        self.lbl_alvo_pr = ttk.Label(topo, text="Zona:")
        self.lbl_alvo_pr.pack(side="left")
        self.var_alvo_pr = tk.StringVar()
        self.cb_alvo_pr = ttk.Combobox(topo, textvariable=self.var_alvo_pr,
                                       width=32, state="readonly")
        self.cb_alvo_pr.pack(side="left", padx=6)
        self.cb_alvo_pr.bind("<<ComboboxSelected>>",
                             lambda _: self.desenhar_protheus())

        ttk.Button(topo, text="GERAR ARQUIVO JSON", style="Big.TButton",
                   command=self.exportar_protheus).pack(side="right")
        ttk.Button(topo, text="EXPORTAR BASE DE CLIENTES (JSON)",
                   command=self.exportar_base_protheus).pack(
                       side="right", padx=(0, 8))

        ttk.Label(f, style="Sub.TLabel", anchor="w", justify="left",
                  text="Uma linha por VISITA, do jeito que o Protheus le. "
                       "O cliente sai como codigo (6) + loja (2); o vendedor, "
                       "com 6 digitos. A PERIODICIDADE vem da curva - S e A "
                       "7 dias, B 14, C 30, Z 60 - e e a mesma conta que "
                       "montou as datas. HASH e HASHREGISTRO saem em branco, "
                       "como combinado."
                  ).pack(fill="x", pady=(0, 6))

        self.lbl_pr = ttk.Label(f, text="", style="Sub.TLabel",
                                background=COR_ZEBRA, padding=(10, 6),
                                anchor="w")
        self.lbl_pr.pack(fill="x", pady=(0, 4))

        # stretch em todas: sao so doze colunas e elas cabem na tela -
        # assim a tabela ocupa a largura inteira, sem barra de rolagem
        # horizontal e sem sobrar um vazio do lado direito
        colunas = [(c, nu.ROTULO_PROTHEUS[c], l,
                    "center" if c in ("sequencia", "numsemana",
                                      "periodicidade", "hash") else "w",
                    True)
                   for c, l in zip(nu.CAMPOS_PROTHEUS, nu.LARGURA_PROTHEUS)]
        quadro, self.tab_pr = tabela(f, colunas, selecao="none")
        quadro.pack(fill="both", expand=True)
        self.tab_pr.tag_configure("zebra", background=COR_ZEBRA)

        self._linhas_pr = []
        self._compromisso_pr = nu.codigo_do_compromisso()
        self._tipo_pr_mudou()

    def _tipo_pr_mudou(self):
        rotulos = {"ZONA": "Zona:", "VENDEDOR": "Vendedor:",
                   "SUPERVISOR": "Supervisor:", "CIDADE": "Cidade:",
                   "UF": "UF:"}
        self.lbl_alvo_pr.configure(
            text=rotulos.get(self.var_tipo_pr.get(), "Alvo:"))
        self.recarregar_protheus(manter=False)

    def recarregar_protheus(self, manter=True):
        if not hasattr(self, "cb_alvo_pr"):
            return
        opcoes = self._opcoes_do_recorte(self.var_tipo_pr.get())
        self.cb_alvo_pr.configure(values=opcoes)
        if not opcoes:
            self.var_alvo_pr.set("")
        elif not manter or self.var_alvo_pr.get() not in opcoes:
            self.var_alvo_pr.set(opcoes[0])
        self.desenhar_protheus()

    def _linhas_protheus_da_tela(self):
        """As linhas do recorte escolhido, ja no layout do Protheus."""
        lista = self._clientes_do_recorte(self.var_tipo_pr.get(),
                                          self.var_alvo_pr.get())
        if not lista:
            return []
        agenda = self._agenda_do_mes()
        visitas = []
        for c in lista:
            visitas.extend(agenda.get(c["CHAVE_CLIENTE"], []))
        if not visitas:
            return []
        return nu.linhas_protheus(self.cfg, lista, linhas=visitas,
                                  compromisso=self._compromisso_pr)

    def desenhar_protheus(self):
        if not hasattr(self, "tab_pr"):
            return
        # o codigo do compromisso e o mesmo da previa e do arquivo: ele so
        # nasce de novo quando a tela e redesenhada
        self._compromisso_pr = nu.codigo_do_compromisso()
        linhas = self._linhas_protheus_da_tela()
        self._linhas_pr = linhas
        self._silencio = True
        try:
            self.tab_pr.delete(*self.tab_pr.get_children())
            for i, r in enumerate(linhas[:self.PREVIA_PR]):
                self.tab_pr.insert("", "end", iid=str(i),
                                   tags=("zebra",) if i % 2 else (),
                                   values=[r[c] for c in nu.CAMPOS_PROTHEUS])
        finally:
            self._silencio = False
        if not linhas:
            self.lbl_pr.configure(
                text="Nada para exportar. Importe a base e cadastre as zonas, "
                     "ou troque o recorte aqui em cima.")
            return
        clientes = len({r["codcli"] for r in linhas})
        vendedores = sorted({r["codusur"] for r in linhas})
        # O codigo do Protheus tem SEIS digitos ("000015"). Quem esta
        # marcado como provisorio na aba 2, ou cujo codigo nao tem esse
        # formato (o "1001" dos VAGO, por exemplo), sai avisado: o
        # Protheus recusa a linha inteira por causa dele.
        suspeitos = {nu._codusur_protheus(p["cod_protheus"]): p
                     for p in nu.vendedores(self.cfg)
                     if p.get("provisorio")
                     or not re.fullmatch(r"\d{6}", str(p["cod_protheus"]))}
        provisorios = sorted(set(suspeitos) & set(vendedores))
        texto = (f"{len(linhas)} visita(s) de {clientes} cliente(s), "
                 f"{len(vendedores)} vendedor(es). "
                 f"Compromisso {self._compromisso_pr}. ")
        texto += (f"A tela mostra as {self.PREVIA_PR} primeiras; "
                  f"o arquivo sai inteiro."
                  if len(linhas) > self.PREVIA_PR else "Tudo na tela.")
        if provisorios:
            texto += ("   ATENCAO: vendedor provisorio na lista ("
                      + ", ".join(provisorios)
                      + ") - o Protheus vai recusar esse codigo.")
        self.lbl_pr.configure(text=texto)

    def exportar_json_protheus(self, qual):
        """(07/10) Parametros > PROTHEUS (JSON): a rota do MES INTEIRO
        ("rota") ou a base de clientes inteira ("base"), sem recorte."""
        if not self.clientes:
            messagebox.showinfo("Planner BAP",
                                "Nao ha base de clientes carregada.")
            return
        quando = dt.datetime.now()
        periodo = "mes"
        if qual == "rota":
            # (26/10, Alexandre) o mes inteiro ou so a partir de hoje
            periodo = self._periodo_da_rota()
            if periodo is None:
                return
            destino = self.caminho("saida") / (
                f"ROTA_PROTHEUS_{self.cfg['mes']}_"
                + (nu.sufixo_a_partir_de() if periodo == "hoje" else "")
                + f"{quando:%Y%m%d_%H%M}.json")
        else:
            destino = self.caminho("saida") / (
                f"BASE_CLIENTES_PROTHEUS_{quando:%Y%m%d_%H%M}.json")

        def trabalho():
            if qual == "rota":
                ls = nu.linhas_protheus(
                    self.cfg, self.clientes,
                    linhas=nu.rota_do_mes(self.cfg, self.clientes),
                    compromisso=nu.codigo_do_compromisso(quando))
                return nu.rota_a_partir_de(ls) if periodo == "hoje" else ls
            return nu.base_protheus(
                self.cfg, self.clientes,
                nu.filiais_dos_clientes(self.caminho("tabela_bap")))

        def pronto(linhas, erro):
            if erro:
                messagebox.showerror("Planner BAP", str(erro[0]))
                self.log(erro[1])
                return
            if not linhas:
                messagebox.showinfo("Planner BAP", "Nada para exportar.")
                return
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(nu.json_protheus(linhas),
                                   encoding="utf-8")
            except OSError as e:
                messagebox.showerror("Planner BAP", f"Nao consegui gravar:\n"
                                     f"{destino}\n\n{e}")
                return
            if qual == "rota":
                resumo = (f"{len(linhas)} visita(s) de "
                          f"{len({x['codcli'] for x in linhas})} cliente(s) "
                          + ("- o mes inteiro" if periodo == "mes" else
                             f"- a partir de hoje ({dt.date.today():%d/%m})")
                          + "\nCompromisso "
                          f"{linhas[0]['codcompromisso']}")
            else:
                resumo = (f"{len(linhas)} cliente(s) de "
                          f"{len({x['A1_VEND'] for x in linhas})} "
                          f"vendedor(es) - todos ATIVO\n"
                          + self._resumo_padrao(linhas))
            self.log(f"JSON do Protheus: {destino} ({resumo})")
            self.aviso(f"{destino.name} gravado.", COR_OK)
            if messagebox.askyesno("Planner BAP",
                                   f"{destino.name}\n\n{resumo}\n\n"
                                   f"Gravado em:\n{destino.parent}\n\n"
                                   f"Abrir a pasta?"):
                self._abrir(destino.parent)
            if qual == "rota":
                self._aviso_remessa_anterior(destino)
        self._tarefa(trabalho, pronto, "Montando o JSON do Protheus...")

    def _aviso_remessa_anterior(self, gravado):
        """(20/11) So le a pasta (exceto o recem-gravado) e pergunta a
        nu.remessas_a_excluir: so abre se sobrou remessa com dtfinal
        3000-01-01 mais nova que a ultima remessa curta (uma vez so). Mostra
        o aviso + botao que copia o pedido de exclusao (so periodo e codusur,
        sem nome de arquivo)."""
        pares = []
        for p in gravado.parent.glob("ROTA_PROTHEUS_*.json"):
            if p.name == gravado.name:
                continue
            try:
                dados = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(dados, list):
                try:
                    mtime = dt.datetime.fromtimestamp(p.stat().st_mtime)
                except OSError:
                    mtime = None
                pares.append((mtime, dados))
        remessas = nu.remessas_a_excluir(pares)
        if not remessas:
            return
        j = tk.Toplevel(self)
        j.title("Planner BAP")
        ttk.Label(j, text=AVISO_REMESSA_ANTERIOR, wraplength=420
                  ).pack(padx=16, pady=(14, 8))
        msg = ttk.Label(j, text="", wraplength=420)

        def copiar():
            self.clipboard_clear()
            self.clipboard_append(nu.pedido_exclusao_maxima(remessas))
            msg.configure(text="Pedido copiado. Cole no e-mail à Máxima.")
        ttk.Button(j, text="Copiar pedido à Máxima", command=copiar
                   ).pack(pady=4)
        msg.pack(padx=16)
        ttk.Button(j, text="Fechar", command=j.destroy).pack(pady=(4, 12))

    def _resumo_padrao(self, linhas) -> str:
        """(20/10) Quantos clientes foram para o vendedor/supervisor padrao
        (os que nenhum vendedor da equipe ve)."""
        v_p, s_p = nu.vendedor_padrao(self.cfg), nu.supervisor_padrao(self.cfg)
        n = sum(1 for x in linhas if x.get("A1_VEND") == v_p)
        return (f"{len(linhas) - n} com vendedor da equipe · {n} sem vendedor "
                f"(vendedor padrão {v_p} / supervisor {s_p})")

    def exportar_base_protheus(self):
        """A base de clientes (A1_FILIAL, A1_COD, A1_LOJA, A1_VEND, A1_NOME,
        A1_NREDUZ, SUPERVISOR, STATUS) do recorte escolhido aqui em cima,
        com o vendedor que a roteirizacao deu a cada cliente. STATUS e o
        nome da coluna do BAP Tools, com o ATIVO/INATIVO do Planner."""
        tipo, alvo = self.var_tipo_pr.get(), self.var_alvo_pr.get()
        lista = self._clientes_do_recorte(tipo, alvo)
        if not lista:
            messagebox.showinfo("Planner BAP",
                                "Nao ha cliente nesse recorte para exportar.")
            return
        filiais = nu.filiais_dos_clientes(self.caminho("tabela_bap"))
        # (20/10) todo cliente sai ATIVO; sem vendedor: vendedor/sup. padrao
        linhas = nu.base_protheus(self.cfg, lista, filiais)
        sem = len(lista) - len(linhas)
        if not linhas:
            messagebox.showinfo("Planner BAP",
                                "Nenhum cliente desse recorte tem vendedor.")
            return
        pedaco = nu.norm(alvo).replace(" ", "_").replace("/", "-")[:28]
        destino = (self.caminho("saida") /
                   f"BASE_CLIENTES_PROTHEUS_{nu.norm(tipo)}_{pedaco}_"
                   f"{dt.date.today():%Y%m%d}.json")
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(
                nu.json_protheus(linhas),
                encoding="utf-8")
        except OSError as erro:
            messagebox.showerror(
                "Planner BAP",
                f"Nao consegui gravar o arquivo:\n{destino}\n\n{erro}")
            return
        vend = len({x["A1_VEND"] for x in linhas})
        self.log(f"Base de clientes Protheus exportada: {destino} "
                 f"({len(linhas)} clientes, {vend} vendedores, {tipo} = {alvo})")
        self.aviso(f"{destino.name}: {len(linhas)} cliente(s).", COR_OK)
        if messagebox.askyesno(
                "Planner BAP",
                f"{destino.name}\n\n{tipo} = {alvo}\n"
                f"{len(linhas)} cliente(s) de {vend} vendedor(es) - todos "
                f"ATIVO\n" + self._resumo_padrao(linhas)
                + (f"\n{sem} cliente(s) ficaram de fora" if sem else "")
                + f"\n\nGravado em:\n{destino.parent}\n\nAbrir agora?"):
            self._abrir(destino)

    def _periodo_da_rota(self):
        """(26/10, Alexandre) "mes" (o mes inteiro), "hoje" (so a partir de
        hoje) ou None (cancelou)."""
        try:
            import bap_visual as bv_                    # noqa: PLC0415
            return bv_.escolher_periodo_rota(self)
        except Exception:                               # noqa: BLE001
            r = messagebox.askyesnocancel(
                "Exportar JSON da roteirização",
                "Exportar o MÊS INTEIRO?\n\nSim = o mês inteiro\nNão = só "
                f"a partir de hoje ({dt.date.today():%d/%m})")
            return None if r is None else ("mes" if r else "hoje")

    def exportar_protheus(self):
        linhas = self._linhas_pr
        if not linhas:
            messagebox.showinfo("Planner BAP",
                                "Nao ha nada na tela para exportar.")
            return
        periodo = self._periodo_da_rota()
        if periodo is None:
            return
        if periodo == "hoje":
            linhas = nu.rota_a_partir_de(linhas)
            if not linhas:
                messagebox.showinfo("Planner BAP", "Esse recorte nao tem "
                                    "visita de hoje em diante.")
                return
        tipo, alvo = self.var_tipo_pr.get(), self.var_alvo_pr.get()
        pedaco = nu.norm(alvo).replace(" ", "_").replace("/", "-")[:28]
        destino = self.caminho("saida") / (
            f"ROTA_PROTHEUS_{nu.norm(tipo)}_{pedaco}_"
            + (nu.sufixo_a_partir_de() if periodo == "hoje" else "")
            + f"{dt.date.today():%Y%m%d}.json")
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(
                nu.json_protheus(linhas),
                encoding="utf-8")
        except OSError as erro:
            messagebox.showerror(
                "Planner BAP",
                f"Nao consegui gravar o arquivo:\n{destino}\n\n{erro}")
            self.aviso("Falhou ao gerar o arquivo do Protheus.", COR_ALERTA)
            return
        clientes = len({r["codcli"] for r in linhas})
        self.log(f"Rota Protheus exportada: {destino} ({len(linhas)} visitas "
                 f"de {clientes} clientes, {tipo} = {alvo})")
        self.aviso(f"{destino.name}: {len(linhas)} visita(s).", COR_OK)
        if messagebox.askyesno(
                "Planner BAP",
                f"{destino.name}\n\n{tipo} = {alvo}\n"
                f"{len(linhas)} visita(s) de {clientes} cliente(s)"
                + (f" - a partir de hoje ({dt.date.today():%d/%m})"
                   if periodo == "hoje" else " - o mes inteiro")
                + f"\nCompromisso {linhas[0]['codcompromisso']}\n\n"
                f"Gravado em:\n{destino.parent}\n\nAbrir agora?"):
            self._abrir(destino)

    # =================================================================== 6
    CAMPOS_PARAMETRO = [
        ("CURVA DE RECEITA (media mensal, em R$)", None, None),
        ("Curva S a partir de", "curva_s", "dinheiro"),
        ("Curva A a partir de", "curva_a", "dinheiro"),
        ("Curva B a partir de", "curva_b", "dinheiro"),
        ("Curva C a partir de", "curva_c", "dinheiro"),
        ("Meses da janela da curva", "meses_curva", "inteiro"),
        ("FATURAMENTO DO GERENCIAL", None, None),
        ("Meses do FAT. M6M", "meses_faturamento", "inteiro"),
        ("COMPRANTE: comprou nos ultimos (dias)", "dias_comprante", "inteiro"),
        ("STATUS DO CLIENTE (dias sem comprar)", None, None),
        ("ATIVO ate", "churn_30", "inteiro"),
        ("CHURN 30 ate", "churn_60", "inteiro"),
        ("CHURN 60 ate", "churn_90", "inteiro"),
        ("CHURN 90+ acima de", "inativo", "inteiro"),
        ("ROTA", None, None),
        ("Visitas por dia (padrao das zonas)", "visitas_por_dia", "inteiro"),
        ("Visitas na sexta (prospecção)", "visitas_sexta", "inteiro"),
        ("Colocar os clientes excedentes no sabado",
         "excedentes_no_sabado", "sim_nao"),
        # (17/10, Alexandre) as regras da cidade base e da visita semanal
        ("CIDADE BASE E VISITA SEMANAL", None, None),
        ("Dias úteis só na cidade base (início do mês)", "dias_cidade_base",
         "inteiro"),
        ("Raio da cidade base (km)", "raio_base_km", "inteiro"),
        ("Top clientes com visita semanal", "top_semanal", "inteiro"),
        ("Raio da capital p/ visita semanal (km)", "raio_capital_km",
         "inteiro"),
        # (15/10) o A1_VEND e o SUPERVISOR do cliente fora do Planner no
        # .json do Protheus - ficam na caixa PROTHEUS (JSON), la em cima
        ("Vendedor padrão", "vendedor_padrao", "codigo"),
        ("Supervisor padrão", "supervisor_padrao", "codigo"),
        # (22/10, Alexandre) o expediente do vendedor (Farol de Visita e
        # Parcial Visitas: JORNADA LIQUIDA e dias abaixo dela)
        ("JORNADA DE TRABALHO (segunda a sexta)", None, None),
        ("Início do expediente", "jornada_inicio", "hora"),
        ("Fim do expediente (seg. a qui.)", "jornada_fim", "hora"),
        ("Fim do expediente (sexta)", "jornada_fim_sexta", "hora"),
        ("Jornada líquida mínima (meta)", "jornada_liquida", "hora"),
        ("Intervalo de almoço máximo", "jornada_almoco_max", "hora"),
        # (22/10, Alexandre) a prospeccao do Microsoft Forms conta como
        # visita (o "Atualizar visitas" le o Excel de respostas)
        ("PROSPECÇÃO (MICROSOFT FORMS)", None, None),
        ("Excel de respostas do Forms", "arquivo_prospeccao_forms",
         "arquivo"),
    ]
    # "Atualizar a base ao abrir" saiu daqui: o Planner nao gera mais a
    # BASE_CLIENTE, so le a que esta em RELATORIOS. A chave continua no
    # planner_config.json de quem ja a tinha - configuracao de ninguem se
    # apaga - mas nao liga mais nada.

    def _montar_parametros(self):
        f = self.aba_parametros
        self._faixa_recalcular(f)
        ttk.Label(f, text="Parametros", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(f, text="Curva e status sao recalculados em cima da base ja "
                          "carregada - nao precisa importar de novo. Depois de "
                          "salvar, clique em RECALCULAR PLANNER para os "
                          "numeros de todas as abas refletirem a mudanca.",
                  style="Sub.TLabel", wraplength=900).pack(anchor="w", pady=(2, 8))

        # ---- o arquivo do PLANNER ----------------------------------------
        # (07/10) o arquivo do PLANNER e a agenda de cidades lado a lado:
        # um embaixo do outro empurrava o RECALCULAR para fora da tela
        duas = ttk.Frame(f)
        duas.pack(anchor="w", fill="x", pady=(0, 8))
        arq = ttk.LabelFrame(duas, text=" O ARQUIVO DO PLANNER ",
                             padding=(12, 8, 12, 10))
        arq.pack(side="left", fill="both", expand=True)
        linha_arq = ttk.Frame(arq)
        linha_arq.pack(anchor="w", fill="x")
        ttk.Button(linha_arq, text="EXPORTAR PLANNER DE ROTA",
                   style="Big.TButton",
                   command=lambda: self.exportar_planner(perguntar=True)
                   ).pack(side="left")
        ttk.Button(linha_arq, text="IMPORTAR ARQUIVO DO PLANNER",
                   style="Big.TButton",
                   command=self.importar_planner).pack(side="left", padx=8)
        ttk.Label(arq, style="Sub.TLabel", wraplength=560,
                  text="EXPORTAR grava o PLANNER_BAP do mes em "
                       "RELATORIOS\\Roteirizacao - "
                       "e dele que o Gerador de Meta tira a meta. IMPORTAR "
                       "traz um PLANNER de volta para dentro do programa, "
                       "com zonas, equipe e rota do jeito que estavam."
                  ).pack(anchor="w", pady=(6, 0))

        # ---- (07/10) a agenda de cidades dos supervisores -----------------
        ag = ttk.LabelFrame(duas, text=" AGENDA DE CIDADE DOS SUPERVISORES ",
                            padding=(12, 8, 12, 10))
        ag.pack(side="left", fill="both", expand=True, padx=(10, 0))
        linha_ag = ttk.Frame(ag)
        linha_ag.pack(anchor="w", fill="x")
        ttk.Button(linha_ag, text="EXPORTAR MODELO DE AGENDA DE CIDADE",
                   style="Big.TButton",
                   command=self.exportar_modelo_agenda).pack(side="left")
        ttk.Button(linha_ag, text="IMPORTAR AGENDA DE CIDADE",
                   style="Big.TButton",
                   command=self.importar_agenda_e_recalcular
                   ).pack(side="left", padx=8)
        ttk.Label(ag, style="Sub.TLabel", wraplength=560,
                  text="EXPORTAR gera o Excel do mes (uma aba por vendedor) "
                       "para os supervisores escolherem ate 2 cidades por "
                       "dia. IMPORTAR traz o Excel preenchido e recalcula a "
                       "rota; quem ficou em branco segue as regras normais."
                  ).pack(anchor="w", pady=(6, 0))

        # ---- (07/10) os dois .json do Protheus/Maxima (sairam do Farol
        # Roteirizacao): a rota do mes inteiro e a base de clientes
        # lado a lado com o MES DA ROTA: um embaixo do outro empurrava o
        # SALVAR/RECALCULAR para fora da tela (Windows em 125%)
        duas_b = ttk.Frame(f)
        duas_b.pack(anchor="w", fill="x")
        pj = ttk.LabelFrame(duas_b, text=" PROTHEUS (JSON) ",
                            padding=(12, 8, 12, 10))
        linha_pj = ttk.Frame(pj)
        linha_pj.pack(anchor="w", fill="x")
        ttk.Button(linha_pj, text="EXPORTAR JSON DA ROTEIRIZAÇÃO",
                   style="Big.TButton",
                   command=lambda: self.exportar_json_protheus("rota")
                   ).pack(side="left")
        ttk.Button(linha_pj, text="EXPORTAR JSON DA BASE DE CLIENTES",
                   style="Big.TButton",
                   command=lambda: self.exportar_json_protheus("base")
                   ).pack(side="left", padx=8)
        # (15/10) cliente fora do Planner: vai com estes codigos (ATIVO, 20/10)
        self._linha_padrao = ttk.Frame(pj)
        self._linha_padrao.pack(anchor="w", pady=(8, 0))
        ttk.Label(pj, style="Sub.TLabel", wraplength=560,
                  text="ROTEIRIZAÇÃO: todas as visitas do mês, data exata "
                       "(numsemana 1, dtfinal = data + periodicidade - 1 "
                       "dia; fora do arquivo: inativo, interno, conta "
                       "000040). BASE DE "
                       "CLIENTES: o vendedor e o supervisor de cada cliente "
                       "pelo Planner (A1_VEND). TODOS vão ATIVO: quem está "
                       "fora do Planner (sem vendedor, cadeira vaga ou "
                       "inativado) vai com o vendedor e o supervisor padrão "
                       "(salvos com SALVAR PARAMETROS) e ninguém da equipe vê."
                  ).pack(anchor="w", pady=(6, 0))

        # ---- o mes da rota e os feriados ---------------------------------
        cal = ttk.LabelFrame(duas_b, text=" MES DA ROTA ",
                             padding=(12, 6, 12, 8))
        cal.pack(side="left", fill="both", expand=True)
        pj.pack(side="left", fill="both", expand=True, padx=(10, 0))
        linha_cal = ttk.Frame(cal)
        linha_cal.pack(anchor="w")
        ttk.Label(linha_cal, text="Mes da rota:").pack(side="left")
        hoje = dt.date.today()
        anos = [str(a) for a in range(hoje.year - 1, hoje.year + 3)]
        self.var_ano = tk.StringVar(value=self.cfg["mes"][:4])
        self.var_mes = tk.StringVar(value=nu.MESES_PT[int(self.cfg["mes"][5:7])])
        cb_ano = ttk.Combobox(linha_cal, textvariable=self.var_ano, values=anos,
                              width=6, state="readonly")
        cb_ano.pack(side="left", padx=6)
        cb_mes = ttk.Combobox(linha_cal, textvariable=self.var_mes,
                              values=nu.MESES_PT[1:], width=12, state="readonly")
        cb_mes.pack(side="left", padx=4)
        cb_ano.bind("<<ComboboxSelected>>", lambda _: self.trocar_mes())
        cb_mes.bind("<<ComboboxSelected>>", lambda _: self.trocar_mes())
        ttk.Button(linha_cal, text="Feriados...",
                   command=self.editar_feriados).pack(side="left", padx=14)
        self.lbl_calendario = ttk.Label(cal, text="", style="Cod.TLabel")
        self.lbl_calendario.pack(anchor="w", pady=(6, 0))
        ttk.Label(cal, text="O feriado sai da conta de dias uteis e da agenda "
                            "da rota. Vale para o PLANNER e para a coluna "
                            "CLI/DIA do resumo gerencial.",
                  style="Sub.TLabel", wraplength=900).pack(anchor="w",
                                                           pady=(4, 0))
        self.lbl_sabado = ttk.Label(f, style="Sub.TLabel", wraplength=1000)
        self.lbl_curvas = ttk.Label(f, style="Sub.TLabel", wraplength=1000)

        # duas colunas de secoes, para sobrar espaco para o log embaixo
        corpo = ttk.Frame(f)
        corpo.pack(anchor="w", fill="x", pady=(4, 0))
        self.var_par = {}
        secao = -1
        coluna, linha = 0, 0
        alturas = [0, 0, 0]
        for rotulo, chave, tipo in self.CAMPOS_PARAMETRO:
            if chave is None:
                secao += 1
                # CURVA + CIDADE BASE | FATURAMENTO, STATUS e ROTA (17/10)
                # | (22/10) JORNADA DE TRABALHO numa 3a coluna (embaixo, a
                # tela de 125% cortava)
                # | (22/10) PROSPECCAO embaixo da JORNADA
                coluna = 6 if secao in (5, 6) else (3 if secao in (1, 2, 3)
                                                     else 0)
                linha = alturas[coluna // 3]
                ttk.Label(corpo, text=rotulo, font=("Segoe UI", 9, "bold"),
                          foreground=COR_TITULO).grid(
                    row=linha, column=coluna, columnspan=2, sticky="w",
                    pady=(12 if linha else 0, 4))
                linha += 1
                alturas[coluna // 3] = linha
                continue
            if tipo == "codigo" and getattr(self, "_linha_padrao", None):
                var = tk.StringVar()
                self.var_par[chave] = (var, tipo)
                ttk.Label(self._linha_padrao, text=rotulo).pack(
                    side="left", padx=(0, 6))
                ttk.Entry(self._linha_padrao, textvariable=var,
                          width=9).pack(side="left", padx=(0, 18))
                continue
            ttk.Label(corpo, text=rotulo).grid(row=linha, column=coluna,
                                               sticky="w", pady=2, padx=(16, 10))
            var = tk.StringVar()
            self.var_par[chave] = (var, tipo)
            if tipo == "sim_nao":
                ttk.Combobox(corpo, textvariable=var, values=["SIM", "NAO"],
                             width=10, state="readonly").grid(
                    row=linha, column=coluna + 1, sticky="w")
            elif tipo == "arquivo":
                # (22/10) o caminho do Excel + o botao para procurar
                cx = ttk.Frame(corpo)
                cx.grid(row=linha, column=coluna + 1, sticky="w")
                ttk.Entry(cx, textvariable=var, width=26).pack(side="left")
                ttk.Button(cx, text="...", width=3,
                           command=lambda v=var: self._procurar_arquivo(v)
                           ).pack(side="left", padx=(4, 0))
            else:
                ttk.Entry(corpo, textvariable=var, width=14).grid(
                    row=linha, column=coluna + 1, sticky="w")
            linha += 1
            alturas[coluna // 3] = linha
        corpo.columnconfigure(2, minsize=60)
        corpo.columnconfigure(5, minsize=60)

        botoes = ttk.Frame(f)
        botoes.pack(anchor="w", pady=(16, 0))
        ttk.Button(botoes, text="SALVAR PARAMETROS", style="Big.TButton",
                   command=self.salvar_parametros).pack(side="left")
        ttk.Button(botoes, text="RECALCULAR PLANNER", style="Big.TButton",
                   command=lambda: self.recalcular_planner(agenda=True)
                   ).pack(side="left", padx=10)
        ttk.Button(botoes, text="Voltar ao padrao",
                   command=self.parametros_padrao).pack(side="left", padx=6)
        self.lbl_sabado.pack(anchor="w", pady=(10, 0))
        self.lbl_curvas.pack(anchor="w", pady=(4, 0))
        self.lbl_par_msg = ttk.Label(f, text="", style="Sub.TLabel",
                                     wraplength=900)
        self.lbl_par_msg.pack(anchor="w", pady=(8, 0))

        ttk.Button(f, text="COMO A ROTA E MONTADA (passo a passo)",
                   command=self.mostrar_mecanica).pack(anchor="w", pady=(10, 0))

        self.txt_log = tk.Text(f, height=5, relief="flat", borderwidth=0,
                               font=("Consolas", 9), background=COR_PAPEL,
                               foreground=COR_SUAVE, highlightthickness=1,
                               highlightbackground=COR_LINHA, padx=10, pady=6)
        self.txt_log.pack(fill="both", expand=True, pady=(8, 0))
        self.txt_log.insert("end", self._historico)
        self._encher_parametros()
        self._mostrar_calendario()

    def _procurar_arquivo(self, var):
        """(22/10) escolhe o Excel de respostas do Forms (prospeccao)."""
        from tkinter import filedialog                  # noqa: PLC0415
        atual = var.get().strip()
        ini = str(Path(atual).parent) if atual else str(Path.home())
        cam = filedialog.askopenfilename(
            parent=self, title="Excel de respostas do Forms (prospecção)",
            initialdir=ini, filetypes=[("Excel", "*.xlsx")])
        if cam:
            var.set(cam)

    def _semanas_do_mes(self) -> int:
        """Quantas semanas uteis o mes da rota tem - o curva S visita todas."""
        return len({d[2] for d in nu.dias_do_mes(
            self.cfg["mes"], self.cfg.get("feriados") or [], False)}) or 1

    def _explicar_sabado(self):
        """Diz o que cada sabado do mes faz na rota."""
        if not getattr(self, "lbl_sabado", None):
            return
        par = self.cfg["parametros"]
        cap = par.get("visitas_por_dia", 0)
        fixo = (f"ULTIMO SABADO DO MES: dia de rota de TODOS os vendedores, "
                f"sempre, com o mesmo teto de {cap} visita(s) dos dias uteis "
                f"(regra fixa, sem chave para ligar ou desligar).\n")
        if par.get("excedentes_no_sabado"):
            texto = (f"PRIMEIRO SABADO = DEPOSITO: cada dia util enche ate "
                     f"{cap} visita(s) e TODO o excedente e visitado uma vez, "
                     f"no PRIMEIRO sabado do mes, sem limite de quantos cabem "
                     f"la. Quem fica de fora da semana e o curva Z, na ordem: "
                     f"S, A, B e C entram primeiro.")
            cor = COR_ACENTO
        else:
            texto = (f"PRIMEIRO SABADO: nao se usa. O que passar de {cap} "
                     f"visita(s) fica no proprio dia util (o gerencial mostra "
                     f"a zona em vermelho quando nao cabe).")
            cor = COR_SUAVE
        self.lbl_sabado.configure(text=fixo + texto, foreground=cor)
        if getattr(self, "lbl_curvas", None):
            n = self._semanas_do_mes()
            partes = []
            for k, como in (("S", "semanal"), ("A", "semana sim, semana nao"),
                            ("B", "quinzenal"), ("C", "quinzenal"),
                            ("Z", "so se sobrar espaco")):
                partes.append(f"{k} = {nu.plano_da_curva(k, n)[0]}x ({como})")
            self.lbl_curvas.configure(
                text="VISITAS POR CLIENTE: nao e mais escolha, vem da CURVA. "
                     f"Neste mes ({n} semanas uteis): " + "   |   ".join(partes)
                     + ".  A curva sai da media mensal de faturamento, cujos "
                       "cortes estao aqui em cima.",
                foreground=COR_ACENTO)

    def _encher_parametros(self):
        par = self.cfg["parametros"]
        for chave, (var, tipo) in self.var_par.items():
            valor = par.get(chave, nu.PARAMETROS_PADRAO.get(chave))
            if tipo == "sim_nao":
                var.set("SIM" if valor else "NAO")
            elif tipo == "codigo":
                var.set(nu.vendedor_padrao(self.cfg, chave))
            elif tipo == "dinheiro":
                var.set(f"{float(valor):.2f}".replace(".", ","))
            elif tipo in ("hora", "arquivo"):
                var.set(str(valor or ""))
            else:
                var.set(str(int(valor)))
        self._explicar_sabado()

    def salvar_parametros(self):
        novos = {}
        for chave, (var, tipo) in self.var_par.items():
            texto = var.get().strip()
            try:
                if tipo == "arquivo":
                    novos[chave] = texto            # vazio = acha sozinho
                elif tipo == "codigo":
                    dig = re.sub(r"\D", "", texto)
                    if not dig or len(dig) > 6:
                        raise ValueError(texto)
                    novos[chave] = dig.zfill(6)
                elif tipo == "sim_nao":
                    novos[chave] = (texto.upper() == "SIM")
                elif tipo == "dinheiro":
                    novos[chave] = float(texto.replace(".", "").replace(",", "."))
                elif tipo == "hora":
                    # (22/10) HH:MM (07:30, 7h30, 7.30)
                    m_ = re.match(r"^(\d{1,2})[:hH.](\d{2})$", texto)
                    if not m_ or int(m_.group(1)) > 23 or \
                            int(m_.group(2)) > 59:
                        raise ValueError(texto)
                    novos[chave] = f"{int(m_.group(1)):02d}:{m_.group(2)}"
                else:
                    novos[chave] = int(float(texto.replace(",", ".")))
            except ValueError:
                messagebox.showwarning(
                    "Planner BAP",
                    f"O valor '{texto}' nao serve para {chave}.")
                return
        if not (novos["curva_s"] >= novos["curva_a"] >= novos["curva_b"]
                >= novos["curva_c"]):
            messagebox.showwarning(
                "Planner BAP",
                "As curvas tem de ser decrescentes: S >= A >= B >= C.")
            return
        if not (novos["churn_30"] < novos["churn_60"] < novos["churn_90"]):
            messagebox.showwarning(
                "Planner BAP",
                "Os cortes de churn tem de crescer: 30 < 60 < 90.")
            return
        if novos["meses_curva"] < 1 or novos["meses_faturamento"] < 1:
            messagebox.showwarning("Planner BAP",
                                   "As janelas precisam de pelo menos 1 mes.")
            return
        if "jornada_inicio" in novos and not (
                novos["jornada_inicio"] < novos["jornada_fim_sexta"]
                <= novos["jornada_fim"]):
            messagebox.showwarning(
                "Planner BAP",
                "Jornada: o início tem de vir antes do fim (e a sexta não "
                "pode terminar depois de segunda a quinta).")
            return
        if novos["dias_comprante"] < 1:
            messagebox.showwarning("Planner BAP",
                                   "O corte de COMPRANTE precisa de pelo "
                                   "menos 1 dia.")
            return
        self.cfg["parametros"].update(novos)
        self.salvar()
        self.marcar_pendente()
        self._encher_parametros()          # ja chama _explicar_sabado()
        self.lbl_par_msg.configure(
            text="Parametros salvos. Clique em RECALCULAR PLANNER para "
                 "recalcular curva, status e os indicadores.",
            foreground=COR_OK)
        self.aviso("Parametros salvos.", COR_OK)

    def _perguntar_modo_recalculo(self):
        """(15/10, Alexandre) RECALCULAR PLANNER: COMPLETO (todos os
        vendedores) ou SO OS ALTERADOS (vendedores/zonas que mudaram desde o
        ultimo calculo - os outros ficam com a rota de hoje). Devolve
        "parcial", "completo" ou None (cancelou)."""
        try:
            alt = nu.vendedores_alterados(self.cfg, self.clientes)
        except Exception:                               # noqa: BLE001
            alt = {"tem_fixa": False, "alterados": [], "iguais": [],
                   "parametros": False}
        escolha = {"v": None}
        j = tk.Toplevel(self)
        j.title("Recalcular Planner")
        j.configure(background=COR_PAPEL)
        j.transient(self.winfo_toplevel())
        j.resizable(False, False)
        corpo = tk.Frame(j, background=COR_PAPEL, padx=24, pady=18)
        corpo.pack(fill="both", expand=True)
        tk.Label(corpo, text="Recalcular Planner", background=COR_PAPEL,
                 foreground=COR_TEXTO, font=(self.FONTE, 14, "bold"),
                 anchor="w").pack(anchor="w")

        def nome(cod):
            p_ = nu.pessoa_por_codigo(self.cfg, cod) or {}
            return f"{cod} - {p_.get('nome', '')}".strip(" -")
        if alt["tem_fixa"]:
            quem = alt["alterados"]
            txt = (f"{len(quem)} vendedor(es) com carteira, zona ou agenda "
                   f"alterada desde o último cálculo"
                   + (":" if quem else ".")
                   + "".join(f"\n   • {nome(c)}" for c in quem[:12])
                   + (f"\n   • e mais {len(quem) - 12}" if len(quem) > 12
                      else "")
                   + f"\n\n{len(alt['iguais'])} vendedor(es) sem mudança: "
                   f"no SÓ OS ALTERADOS a rota deles fica como está.")
            if alt["parametros"]:
                txt += ("\n\nOs PARÂMETROS (aba 6) mudaram: no SÓ OS "
                        "ALTERADOS eles valem só para quem for recalculado.")
        else:
            txt = ("Ainda não há rota guardada neste mês: o primeiro "
                   "cálculo é o COMPLETO.")
        tk.Label(corpo, text=txt, background=COR_PAPEL, foreground=COR_TEXTO,
                 font=(self.FONTE, 10), justify="left", anchor="w",
                 wraplength=520).pack(anchor="w", pady=(10, 16))
        botoes = tk.Frame(corpo, background=COR_PAPEL)
        botoes.pack(fill="x")

        def fim(v):
            escolha["v"] = v
            j.destroy()
        if alt["tem_fixa"]:
            ttk.Button(botoes, text=f"SÓ OS ALTERADOS "
                                    f"({len(alt['alterados'])})",
                       style="Big.TButton",
                       command=lambda: fim("parcial")).pack(side="left")
        ttk.Button(botoes, text="PLANNER COMPLETO",
                   style="Big.TButton" if not alt["tem_fixa"] else
                   "TButton", command=lambda: fim("completo")).pack(
                       side="left", padx=10)
        ttk.Button(botoes, text="Cancelar", command=j.destroy).pack(
            side="right")
        j.bind("<Escape>", lambda e: j.destroy())
        j.update_idletasks()
        try:
            x = self.winfo_rootx() + (self.winfo_width() - j.winfo_width()) // 2
            y = self.winfo_rooty() + 80
            j.geometry(f"+{max(0, x)}+{max(0, y)}")
            j.grab_set()
        except tk.TclError:
            pass
        self.wait_window(j)
        return escolha["v"]

    def recalcular_planner(self, agenda=False, modo=None):
        """
        Poe TUDO em dia de uma vez: os parametros, a curva e o status de
        cada cliente, a lotacao das zonas, a equipe, as trocas feitas no
        analitico e os cinco quadros da tela. No fim, oferece o PLANNER.
        (15/10) modo: "completo" refaz a rota de todos; "parcial" (o padrao
        dos recalculos internos) so a dos vendedores alterados - os outros
        ficam com a ROTA FIXA guardada. O botao pergunta.
        """
        if not self.clientes:
            self.lbl_par_msg.configure(
                text="Nao ha base carregada para recalcular. Importe a base "
                     "na aba 3 ou um PLANNER na aba 1.",
                foreground=COR_ALERTA)
            self.aviso("Nada para recalcular.", COR_ALERTA)
            return
        if agenda and modo is None:
            modo = self._perguntar_modo_recalculo()
            if modo is None:
                self.aviso("Recalculo cancelado.")
                return
        modo = modo or "parcial"

        # (07/10) a agenda de cidades dos supervisores (opcional) - so pelo
        # botao RECALCULAR PLANNER (os recalculos internos nao perguntam)
        if agenda:
            self.perguntar_agenda()
        antes = Counter(c["CURVA_RECEITA"] for c in self.clientes)
        antes_zona = {c["CHAVE_CLIENTE"]: nu.zona_do_cliente(self.cfg, c)
                      for c in self.clientes}
        antes_vend = {c["CHAVE_CLIENTE"]: nu.vendedor_do_cliente(self.cfg, c)
                      for c in self.clientes}

        # 1. a equipe e os vinculos vendedor -> supervisor -> gerente
        nu.normalizar_pessoas(self.cfg)
        # 2. as excecoes que apontam para zona/vendedor/cliente que sumiu
        soltas = nu.limpar_excecoes(self.cfg, self.clientes)
        # 3. curva e status com os cortes da aba 6
        nu.aplicar_parametros(self.cfg, self.clientes)
        # 4. a lotacao das areas e a contagem por zona
        self._indexar()
        # 4b. (15/10) a ROTA FIXA: o completo refaz todo mundo; o parcial
        # so quem mudou. A rota que sai fica guardada para o proximo
        alt_antes = nu.vendedores_alterados(self.cfg, self.clientes)
        nu.IGNORAR_ROTA_FIXA[0] = modo == "completo"
        try:
            n_fix = nu.fotografar_rota(self.cfg, self.clientes)
        finally:
            nu.IGNORAR_ROTA_FIXA[0] = False
        self.salvar()

        depois = Counter(c["CURVA_RECEITA"] for c in self.clientes)
        mudou_curva = sum(abs(depois[k] - antes[k])
                          for k in set(antes) | set(depois))
        mudou_zona = sum(1 for c in self.clientes
                         if nu.zona_do_cliente(self.cfg, c)
                         != antes_zona[c["CHAVE_CLIENTE"]])
        mudou_vend = sum(1 for c in self.clientes
                         if nu.vendedor_do_cliente(self.cfg, c)
                         != antes_vend[c["CHAVE_CLIENTE"]])

        # 5. redesenha as seis abas
        self.atualizar_tudo()
        self._pendente = False
        self._pintar_faixas()

        du = nu.dias_uteis(self.cfg["mes"], self.cfg.get("feriados") or [])
        sem_vend = [r for r in self.resumo["zona"]
                    if r["clientes"] and not r["vendedor"]]
        sem_zona = sum(1 for c in self.clientes
                       if not nu.zona_do_cliente(self.cfg, c))
        excecoes = len(self.cfg.get("excecoes") or {})
        partes = [
            ("COMPLETO" if modo == "completo" or not alt_antes["tem_fixa"]
             else f"SÓ OS ALTERADOS ({len(alt_antes['alterados'])} de "
                  f"{n_fix} vendedores refeitos)"),
            "Curva: " + "  ".join(f"{k}={depois.get(k, 0)}" for k in nu.CURVAS),
            f"{len(self.cfg['zonas'])} zona(s)",
            f"{len(nu.vendedores(self.cfg))} vendedor(es)",
            f"{du} dias uteis em "
            f"{nu.MESES_PT[int(self.cfg['mes'][5:7])]}/{self.cfg['mes'][:4]}",
        ]
        if excecoes:
            partes.append(f"{excecoes} cliente(s) trocado(s) a mao")
        aviso = []
        if sem_zona:
            aviso.append(f"{sem_zona} cliente(s) sem zona")
        if sem_vend:
            aviso.append(f"{len(sem_vend)} zona(s) sem vendedor")
        # quem nao cabe no mes com o teto de visitas por dia
        nao_cabe = [r for r in self.resumo["vendedor"]
                    if r["vendedor"] and not r.get("cabe", True)]
        if nao_cabe:
            aviso.append(f"{len(nao_cabe)} vendedor(es) com carteira ACIMA DO "
                         f"TETO de {self.cfg['parametros']['visitas_por_dia']} "
                         f"visita(s)/dia")
        self.lbl_par_msg.configure(
            text="Planner recalculado.  " + "   |   ".join(partes)
                 + (f"   |   ATENCAO: {', '.join(aviso)} - nao entram na rota"
                    if aviso else ""),
            foreground=(COR_ALERTA if aviso else COR_OK))
        self.log(f"\nRECALCULAR PLANNER: {' | '.join(partes)}"
                 + (f"\n  {mudou_curva} mudanca(s) de curva" if mudou_curva else "")
                 + (f"\n  {mudou_zona} cliente(s) mudaram de zona" if mudou_zona else "")
                 + (f"\n  {mudou_vend} cliente(s) mudaram de vendedor" if mudou_vend else "")
                 + (f"\n  {soltas} excecao(oes) solta(s) removida(s)" if soltas else "")
                 + ("\n  ATENCAO: " + ", ".join(aviso) if aviso else "")
                 + "".join(
                     f"\n     {r['vendedor']} {r['vendedor_nome']}: "
                     f"{r['clientes']} cli, {r['visitas_mes']} visitas no mes -> "
                     f"precisa de {r['dias_necessarios']} dias e a agenda tem "
                     f"{r['dias_agenda']} (a rota ficou com {r['clientes_dia']}/dia)"
                     for r in sorted(nao_cabe, key=lambda x: x["folga_dias"])))
        self.aviso("Planner recalculado.", COR_OK)

        if nao_cabe:
            pior = min(nao_cabe, key=lambda x: x["folga_dias"])
            teto = self.cfg["parametros"]["visitas_por_dia"]
            messagebox.showwarning(
                "Planner BAP",
                f"A CARTEIRA NAO CABE NO MES com {teto} visita(s) por dia.\n\n"
                f"{len(nao_cabe)} vendedor(es) precisam de mais dias do que o "
                f"mes tem. O pior:\n\n"
                f"    {pior['vendedor']} - {pior['vendedor_nome']}\n"
                f"    {pior['clientes']} clientes x "
                f"{max(1, pior['visitas_mes'] // max(1, pior['clientes']))} "
                f"visita(s) = {pior['visitas_mes']} visitas no mes\n"
                f"    com {teto}/dia isso da {pior['dias_necessarios']} dias, "
                f"e a agenda dele tem {pior['dias_agenda']}\n"
                f"    a rota saiu com {pior['clientes_dia']} visitas por dia\n\n"
                f"A rota sai COMPLETA assim mesmo - ninguem fica de fora - "
                f"mas os dias passam do teto. As linhas em VERMELHO no resumo "
                f"gerencial sao essas.\n\n"
                f"Para caber, uma destas duas:\n"
                f"  - subir o teto de visitas por dia (aba 6);\n"
                f"  - dividir a carteira com mais vendedores (abas 2 e 3).\n\n"
                f"Com 'colocar os clientes excedentes no sabado' em SIM, o "
                f"excedente nao se perde: ele e visitado uma vez, no primeiro "
                f"sabado do mes.")

        if messagebox.askyesno("Planner BAP",
                               "Planner recalculado.\n\n"
                               "DESEJA EXPORTAR O ARQUIVO PLANNER AGORA?"):
            self.exportar_planner(perguntar=False)

    def mostrar_mecanica(self):
        """A caixa que conta, passo a passo, como a rota e montada."""
        janela = tk.Toplevel(self)
        janela.title("Como a rota e montada")
        janela.configure(background=COR_PAPEL)
        janela.transient(self)
        janela.geometry("980x720")

        topo = tk.Frame(janela, background=COR_CABECALHO)
        topo.pack(fill="x")
        tk.Label(topo, text="Como a rota e montada", background=COR_CABECALHO,
                 foreground=COR_TEXTO, font=(self.FONTE, 14),
                 padx=20, pady=12).pack(anchor="w")

        corpo = ttk.Frame(janela, padding=(18, 14))
        corpo.pack(fill="both", expand=True)
        ttk.Label(corpo, style="Sub.TLabel", wraplength=900,
                  text="Esta e a mecanica que o programa usa, na ordem em que "
                       "ela acontece. Os numeros entre parenteses sao os "
                       "valores que estao valendo agora, nesta pasta."
                  ).pack(anchor="w", pady=(0, 10))

        caixa = tk.Text(corpo, wrap="word", relief="flat", borderwidth=0,
                        background=COR_PAPEL, foreground=COR_TEXTO,
                        font=(self.FONTE, 9), padx=4, pady=4,
                        highlightthickness=1, highlightbackground=COR_LINHA)
        rolagem = ttk.Scrollbar(corpo, orient="vertical", command=caixa.yview)
        caixa.configure(yscrollcommand=rolagem.set)
        caixa.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="left", fill="y")
        caixa.tag_configure("titulo", font=(self.FONTE, 10, "bold"),
                            foreground=COR_ACENTO, spacing1=10, spacing3=4)
        caixa.tag_configure("texto", lmargin1=14, lmargin2=14, spacing3=6)

        par = self.cfg["parametros"]
        for titulo, texto_ in nu.MECANICA_DA_ROTA:
            caixa.insert("end", titulo + "\n", "titulo")
            caixa.insert("end", texto_ + "\n", "texto")
        caixa.insert("end", "\nO que esta valendo agora nesta pasta\n",
                     "titulo")
        agora = [
            f"Mes: {nu.MESES_PT[int(self.cfg['mes'][5:7])]}/{self.cfg['mes'][:4]}"
            f" - {nu.dias_uteis(self.cfg['mes'], self.cfg.get('feriados') or [])}"
            f" dias uteis, {len(self.cfg.get('feriados') or [])} feriado(s)",
            f"Teto de visitas por dia: {par.get('visitas_por_dia')}",
            f"COMPRANTE: comprou nos ultimos {par.get('dias_comprante')} dias",
            "Visitas por cliente: pela CURVA, no automatico - "
            + ", ".join(
                f"{k}={nu.plano_da_curva(k, self._semanas_do_mes())[0]}"
                for k in ("S", "A", "B", "C", "Z"))
            + f" visita(s) (o mes tem {self._semanas_do_mes()} semanas uteis)",
            "Ultimo sabado do mes: TODOS os vendedores trabalham, sempre, "
            f"com o mesmo teto de {par.get('visitas_por_dia')} visita(s)",
            "Primeiro sabado: " + ("deposito - o dia util para no teto e o "
                                   "excedente e visitado la"
                                   if par.get("excedentes_no_sabado")
                                   else "nao se usa"),
            "Vendedores do interior (rota por cidade): "
            + (", ".join(v["nome"] for v in nu.vendedores(self.cfg)
                         if v.get("interior")) or "nenhum marcado na aba 2"),
            f"Zonas cadastradas: {len(self.cfg['zonas'])}   |   "
            f"vendedores: {len(nu.vendedores(self.cfg))}   |   "
            f"clientes trocados a mao: {len(self.cfg.get('excecoes') or {})}",
            f"Municipios com coordenada na tabela: {len(nu.geo.CIDADES)}   |   "
            f"bairros de Manaus reconhecidos: "
            f"{len([b for b, z in nu.geo.BAIRROS_MANAUS.items() if z])}",
        ]
        for linha in agora:
            caixa.insert("end", "- " + linha + "\n", "texto")
        caixa.configure(state="disabled")

        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(
            pady=(0, 14))
        self._centralizar(janela)

    def parametros_padrao(self):
        if not messagebox.askyesno("Planner BAP",
                                   "Voltar todos os parametros ao padrao?"):
            return
        self.cfg["parametros"].update(nu.PARAMETROS_PADRAO)
        self.salvar()
        self._encher_parametros()
        self.lbl_par_msg.configure(text="Parametros de volta ao padrao.",
                                   foreground=COR_OK)

    # ---- caixinhas -----------------------------------------------------
    def _perguntar_texto(self, titulo, texto, inicial=""):
        janela = tk.Toplevel(self)
        janela.title(titulo)
        janela.transient(self)
        janela.grab_set()
        janela.resizable(False, False)
        ttk.Label(janela, text=texto, wraplength=460,
                  padding=(16, 14, 16, 6)).pack()
        var = tk.StringVar(value=inicial)
        e = ttk.Entry(janela, textvariable=var, width=56)
        e.pack(padx=16, pady=4)
        e.focus_set()
        e.select_range(0, "end")
        resultado = {"valor": None}

        def ok(_=None):
            resultado["valor"] = var.get().strip()
            janela.destroy()
        e.bind("<Return>", ok)
        bt = ttk.Frame(janela, padding=(16, 10))
        bt.pack()
        ttk.Button(bt, text="Confirmar", command=ok).pack(side="left", padx=6)
        ttk.Button(bt, text="Cancelar", command=janela.destroy).pack(side="left")
        self._centralizar(janela)
        janela.wait_window()
        return resultado["valor"]

    def _centralizar(self, janela):
        janela.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - janela.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - janela.winfo_height()) // 3
        janela.geometry(f"+{max(0, x)}+{max(0, y)}")

    @staticmethod
    def _abrir(caminho):
        try:
            if os.name == "nt":
                os.startfile(caminho)                  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", str(caminho)], check=False)
            else:
                subprocess.run(["xdg-open", str(caminho)], check=False)
        except OSError:
            pass


class DiaDaRota(tk.Toplevel):
    """
    O DIA do calendario da aba Rota por cidade (clique no dia): os clientes
    que a rota pos nele e a cidade do dia.
      * CIDADE DO DIA: escolher uma cidade fixa o dia nela (o mesmo que
        arrastar a cidade para o dia); "(automático)" devolve o dia ao
        automatico.
      * CLIENTES: mover os escolhidos para outro dia, voltar ao automatico
        ou trazer um cliente da carteira para este dia (fica marcado como
        excecao do cliente, o mesmo dia fixo do Analitico da rota).
    Nada vale para o Farol ate GRAVAR E RECALCULAR.
    """
    NOMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado",
             "domingo")
    AUTO = "(automático)"

    def __init__(self, app, iso):
        super().__init__(app)
        self.app, self.iso = app, iso
        self.d = dt.date.fromisoformat(iso)
        self.title(f"Dia {self.d:%d/%m/%Y} · Planner BAP")
        self.configure(background=COR_FUNDO)
        self.geometry("1280x620")
        self.transient(app)
        topo = tk.Frame(self, background=COR_CABECALHO)
        topo.pack(fill="x")
        self.lbl_tit = tk.Label(topo, text="", background=COR_CABECALHO,
                                foreground=COR_TEXTO,
                                font=("Segoe UI", 15, "bold"), anchor="w")
        self.lbl_tit.pack(fill="x", padx=18, pady=(10, 0))
        self.lbl_sub = tk.Label(topo, text="", background=COR_CABECALHO,
                                foreground=COR_SUAVE, font=("Segoe UI", 9),
                                anchor="w")
        self.lbl_sub.pack(fill="x", padx=18, pady=(0, 10))
        tk.Frame(self, background=COR_ACENTO, height=2).pack(fill="x")
        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True, padx=16, pady=12)
        # a cidade do dia
        lc = ttk.Frame(corpo)
        lc.pack(fill="x", pady=(0, 10))
        ttk.Label(lc, text="Cidade do dia").pack(side="left")
        self.var_cid = tk.StringVar()
        self.cb_cid = ttk.Combobox(lc, textvariable=self.var_cid, width=34,
                                   state="readonly")
        self.cb_cid.pack(side="left", padx=8)
        ttk.Button(lc, text="Aplicar cidade", command=self.aplicar_cidade
                   ).pack(side="left")
        self.lbl_cid = ttk.Label(lc, text="", style="Sub.TLabel")
        self.lbl_cid.pack(side="left", padx=12)
        # os clientes
        q, self.tab = tabela(
            corpo, [("ordem", "ORDEM", 55, "center", False),
                    ("cod", "CLIENTE", 85, "w", False),
                    ("nome", "NOME", 250, "w", True),
                    ("fant", "FANTASIA", 180, "w", True),
                    ("cid", "CIDADE", 120, "w", False),
                    ("bairro", "BAIRRO", 140, "w", False),
                    ("seg", "SEGMENTO", 130, "w", False),
                    ("curva", "CURVA", 55, "center", False),
                    ("vis", "VISITA", 60, "center", False),
                    ("fixo", "DIA FIXO", 75, "center", False)],
            selecao="extended")
        q.pack(fill="both", expand=True)
        self.tab.tag_configure("fixo", background="#EAF1FB")
        rod = ttk.Frame(corpo)
        rod.pack(fill="x", pady=(10, 0))
        ttk.Label(rod, text="Escolhidos:").pack(side="left")
        self.var_para = tk.StringVar()
        self.cb_para = ttk.Combobox(rod, textvariable=self.var_para, width=16,
                                    state="readonly")
        self.cb_para.pack(side="left", padx=(8, 4))
        ttk.Button(rod, text="Mover para o dia", command=self.mover
                   ).pack(side="left")
        ttk.Button(rod, text="Voltar ao automático",
                   command=self.automatico).pack(side="left", padx=8)
        ttk.Button(rod, text="Trazer cliente para este dia…",
                   command=self.trazer).pack(side="left", padx=(16, 0))
        ttk.Button(rod, text="Fechar", command=self.destroy).pack(side="right")
        ttk.Label(rod, text="vale ao GRAVAR E RECALCULAR",
                  style="Sub.TLabel").pack(side="right", padx=12)
        self.recarregar()

    # ---- dados
    def _dias_da_rota(self):
        return [d for d in nu.dias_do_mes(self.app.cfg["mes"],
                                          self.app.cfg.get("feriados") or [],
                                          True)]

    def _cidades(self):
        return self.app._rc_cidades or []

    def recarregar(self):
        app = self.app
        app._rc_rota = app._rc_rota_dele()
        linhas = sorted(app._rc_rota.get(self.iso, []),
                        key=lambda r: r.get("ORDEM_DE_VISITA") or 0)
        self._linhas = linhas
        cal = app._rc_cal()
        nome = {c["chave"]: c["cidade"] or "(SEM CIDADE)"
                for c in self._cidades()}
        fixas = cal.get(self.iso, [])
        teto = nu.teto_do_dia(getattr(app, "_rc_teto", 0), self.d,
                              app.cfg["parametros"])
        self.lbl_tit.configure(
            text=f"{self.NOMES[self.d.weekday()].capitalize()}, "
                 f"{self.d:%d/%m/%Y} · {app.var_rc_vend.get()}")
        cids = Counter(str(r.get("CIDADE") or "").title() for r in linhas)
        self.lbl_sub.configure(
            text=f"{len(linhas)} visita(s)" + (f" de {teto}" if teto else "")
            + ("  ·  " + " · ".join(f"{c} {n}" for c, n in cids.most_common(3))
               if cids else "") + ("  ·  cidade fixa" if fixas
                                   else "  ·  automático"))
        self.cb_cid.configure(values=[self.AUTO] + [
            nome[c["chave"]] for c in self._cidades()])
        self._chave_de = {nome[c["chave"]]: c["chave"] for c in self._cidades()}
        self.var_cid.set(nome.get(fixas[0], self.AUTO) if fixas else self.AUTO)
        self.lbl_cid.configure(
            text=("Também: " + ", ".join(nome.get(c, c) for c in fixas[1:]))
            if len(fixas) > 1 else "")
        dias = self._dias_da_rota()
        self._dia_por_rot = {f"{d[0]:%d/%m} ({self.NOMES[d[0].weekday()][:3]})":
                             d[0] for d in dias if d[0] != self.d}
        self.cb_para.configure(values=list(self._dia_por_rot))
        t = self.tab
        t.delete(*t.get_children())
        self._por_iid = {}
        for i, r in enumerate(linhas):
            c = self._cliente(r.get("CHAVE_CLIENTE"))
            exc = nu.excecao_do_cliente(app.cfg, c) if c else {}
            fixo = exc.get("dia") or (f"sem. {exc['semana']}"
                                      if exc.get("semana") else "")
            iid = f"l{i}"
            self._por_iid[iid] = r
            t.insert("", "end", iid=iid, tags=("fixo",) if fixo else (),
                     values=(r.get("ORDEM_DE_VISITA") or "",
                             f"{r.get('COD_CLIENTE')}-{r.get('LOJA') or '01'}",
                             r.get("NOME_CLIENTE") or "",
                             r.get("NOME_FANTASIA") or "",
                             str(r.get("CIDADE") or "").title(),
                             str(r.get("BAIRRO") or "").title(),
                             r.get("SEGMENTO") or "",
                             r.get("CURVA_RECEITA") or "",
                             f"{r.get('VISITA_NO_MES') or 1}/"
                             f"{r.get('VISITAS_DO_CLIENTE') or 1}",
                             fixo))

    def _cliente(self, chave):
        if not hasattr(self, "_cli"):
            self._cli = {c["CHAVE_CLIENTE"]: c for c in self.app.clientes}
        return self._cli.get(chave)

    def _mudou(self):
        self.app.marcar_pendente()
        self.app._rc_desenhar()
        self.recarregar()

    # ---- acoes
    def aplicar_cidade(self):
        cal = self.app._rc_cal()
        esc = self.var_cid.get()
        if esc == self.AUTO:
            cal.pop(self.iso, None)
        else:
            ch = self._chave_de.get(esc)
            if not ch:
                return
            if not self.app._rc_pode(ch, self.iso):
                return
            outras = [c for c in cal.get(self.iso, []) if c != ch]
            cal[self.iso] = [ch]
        nu.gravar_rota_cidade(self.app.cfg, self.app._rc_cod, cal)
        self._mudou()

    def _escolhidos(self):
        return [self._por_iid[i] for i in self.tab.selection()
                if i in self._por_iid]

    def mover(self):
        rs = self._escolhidos()
        d = self._dia_por_rot.get(self.var_para.get())
        if not rs or not d:
            messagebox.showinfo("Planner BAP", "Escolha os clientes na lista "
                                "e o dia de destino.", parent=self)
            return
        nu.marcar_excecao(self.app.cfg, [r["CHAVE_CLIENTE"] for r in rs],
                          dia=d.day)
        self._mudou()

    def automatico(self):
        rs = self._escolhidos()
        if not rs:
            return
        nu.marcar_excecao(self.app.cfg, [r["CHAVE_CLIENTE"] for r in rs],
                          dia="", semana="")
        self._mudou()

    def trazer(self):
        """Um cliente da carteira (que nao esta neste dia) vem para ca."""
        no_dia = {r.get("CHAVE_CLIENTE") for r in self._linhas}
        carteira = [c for c, _z in nu.clientes_do_vendedor(
            self.app.cfg, self.app.clientes, self.app._rc_cod)
            if c["CHAVE_CLIENTE"] not in no_dia]
        w = tk.Toplevel(self)
        w.title("Trazer cliente")
        w.configure(background=COR_FUNDO)
        w.geometry("760x480")
        w.transient(self)
        f = ttk.Frame(w)
        f.pack(fill="both", expand=True, padx=12, pady=10)
        lb = ttk.Frame(f)
        lb.pack(fill="x", pady=(0, 6))
        ttk.Label(lb, text="Buscar").pack(side="left")
        var = tk.StringVar()
        ent = ttk.Entry(lb, textvariable=var, width=40)
        ent.pack(side="left", padx=8)
        q, t = tabela(f, [("cod", "CLIENTE", 85, "w", False),
                          ("nome", "NOME", 260, "w", True),
                          ("cid", "CIDADE", 130, "w", False),
                          ("bairro", "BAIRRO", 140, "w", False),
                          ("curva", "CURVA", 55, "center", False)],
                      selecao="extended")
        q.pack(fill="both", expand=True)

        def encher(*_):
            b = var.get().strip().upper()
            t.delete(*t.get_children())
            for c in carteira:
                txt = f"{c.get('COD_CLIENTE')} {c.get('NOME_CLIENTE')} " \
                      f"{c.get('NOME_FANTASIA', '')} {c.get('CIDADE')} " \
                      f"{c.get('BAIRRO', '')}".upper()
                if b and b not in txt:
                    continue
                t.insert("", "end", iid=c["CHAVE_CLIENTE"], values=(
                    f"{c.get('COD_CLIENTE')}-{c.get('LOJA') or '01'}",
                    c.get("NOME_CLIENTE") or "",
                    str(c.get("CIDADE") or "").title(),
                    str(c.get("BAIRRO") or "").title(),
                    c.get("CURVA_RECEITA") or ""))
        var.trace_add("write", encher)
        encher()

        def ok():
            ch = list(t.selection())
            if ch:
                nu.marcar_excecao(self.app.cfg, ch, dia=self.d.day)
                w.destroy()
                self._mudou()
        ttk.Button(f, text=f"Trazer para {self.d:%d/%m}", command=ok,
                   style="Big.TButton").pack(side="right", pady=(8, 0))
        ent.focus_set()


def main():
    App.ABA_INICIAL = pb.aba_pedida()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
