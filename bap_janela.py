#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
===============================================================================
 AUTOMACAO BAP - JANELA DE ACOMPANHAMENTO
===============================================================================

 Abre uma janela, executa a automacao e mostra o progresso ao vivo: em que
 etapa esta, quais relatorios ja vieram, o tempo decorrido e o log rolando.
 No fim, um painel com o resultado e botoes para abrir as pastas.

 Nao precisa de nada alem do Python: usa tkinter, que ja vem junto.

 Antes de comecar, a janela SEMPRE encerra a execucao anterior:
   1. derruba qualquer bap_automation.py que ainda esteja rodando nesta maquina
      (uma rodada travada, ou a tarefa das 08h/14h que nao terminou)
   2. roda "bap_automation.py --destravar" para remover a trava presa
   3. so entao inicia a rodada nova
 Assim nunca aparece "execucao em andamento" e nunca ficam dois processos
 escrevendo na mesma planilha.

 Como abrir:
     duplo clique no atalho "Automacao BAP" da Area de Trabalho
 ou, na mao:
     pythonw bap_janela.py                 (execucao normal)
     pythonw bap_janela.py --simular       (nao altera nada na nuvem)
     pythonw bap_janela.py --nao-encerrar  (nao mexe na execucao anterior)

 O agendamento das 08h e 14h continua rodando sozinho, sem abrir janela.
===============================================================================
"""

from __future__ import annotations

import json
import os
import queue
import re
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
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, scrolledtext

PASTA = Path(__file__).resolve().parent
SCRIPT = PASTA / "bap_automation.py"
ARQUIVO_RESUMO = PASTA / "ultimo_resumo.json"
PASTA_LOGS = PASTA / "SISTEMA BAP" / "logs"
PASTA_IMPORTAR = PASTA / "SISTEMA BAP" / "Arquivos para Importar"

# ------------------------------- aparencia -----------------------------------
FUNDO = "#0E1614"
CARTAO = "#16211E"
LINHA = "#2C3B36"
TEXTO = "#E4EBE8"
TEXTO_FRACO = "#A6B5AF"
ACENTO = "#4FBFAF"
OK = "#6FC08C"
ALERTA = "#E0A94A"
ERRO = "#E58179"

FONTE = "Segoe UI"

# Quanto esperar, depois de derrubar a execucao anterior, para o Windows soltar
# os arquivos que ela tinha abertos.
ESPERA_APOS_ENCERRAR = 2.0

# Quantas linhas de log ficam na tela. O arquivo em logs\\ guarda tudo; aqui
# so as ultimas, para o widget nao ficar pesado numa rodada longa.
MAX_LINHAS_LOG = 600

# O log encolhe para caber na janela, mas nunca abaixo disto (nem alem).
MIN_LINHAS_VISIVEIS = 4
MAX_LINHAS_VISIVEIS = 40

# PowerShell que lista e derruba os pythons rodando a automacao, menos este.
PS_ENCERRAR = r"""
$meu = {pid}
# ATENCAO: a linha de comando DESTE powershell contem 'bap_automation.py'
# (esta ali no filtro logo abaixo), entao ele aparece na propria busca. Sem
# excluir $PID, o script se matava antes de derrubar o alvo de verdade.
$ignorar = @($meu, $PID)
$alvos = @()
try {{
    $alvos = @(Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {{ $_.CommandLine -like '*bap_automation.py*' -and
                       $_.Name -notlike 'powershell*' -and
                       $_.Name -notlike 'pwsh*' -and
                       $ignorar -notcontains $_.ProcessId }})
}} catch {{
    $alvos = @(Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {{ $_.CommandLine -like '*bap_automation.py*' -and
                       $_.Name -notlike 'powershell*' -and
                       $_.Name -notlike 'pwsh*' -and
                       $ignorar -notcontains $_.ProcessId }})
}}
foreach ($p in $alvos) {{
    Write-Output ("PID " + $p.ProcessId + "  " + $p.Name)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}}
if ($alvos.Count -gt 0) {{
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object {{ $_.Path -like '*ms-playwright*' }} |
        ForEach-Object {{
            Write-Output ("PID " + $_.Id + "  navegador da automacao")
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }}
}}
"""


# =============================================================================
# 1. LEITURA DO LOG  (separado da janela para poder ser testado sozinho)
# =============================================================================

class LeitorDeProgresso:
    """
    Transforma as linhas do log da automacao em estado para a tela.
    Os pesos abaixo distribuem a barra: baixar e a parte longa.
    """

    PESO_PREPARO = 6
    PESO_DOWNLOADS = 56
    PESO_GRAVACAO = 26
    PESO_SOLICITACAO = 12

    RE_RELATORIO = re.compile(r"\[(\d+)/(\d+)\]\s+(.+?)\s+->\s+aba\s+(\S+)")
    RE_BAIXADO = re.compile(r"Baixado \(([\d.,]+) KB\)")
    RE_FALHA_REL = re.compile(r"FALHA em '(.+?)':\s*(.*)")
    RE_GRAVANDO = re.compile(r"Gravando na aba '(.+?)'")
    RE_CONCLUIDO = re.compile(r"Concluido em ([\d.,]+) s \| (\d+) de (\d+)")
    RE_LINHAS = re.compile(r"linhas: (\d+) atualizadas, (\d+) incluidas")

    def __init__(self):
        self.etapa = "Iniciando"
        self.progresso = 0.0
        self.relatorios: list[dict] = []
        self.total_relatorios = 0
        self.indice_atual = 0
        self.abas_gravadas = 0
        self.terminou = False
        self.houve_erro = False
        self.mensagem_erro = ""

    # ---------------------------------------------------------------- helpers
    def _garantir(self, total: int) -> None:
        self.total_relatorios = max(self.total_relatorios, total)
        while len(self.relatorios) < self.total_relatorios:
            self.relatorios.append({"nome": "aguardando...", "estado": "pendente",
                                    "detalhe": ""})

    def _atual(self) -> dict | None:
        if 0 < self.indice_atual <= len(self.relatorios):
            return self.relatorios[self.indice_atual - 1]
        return None

    def _recalcular(self) -> None:
        base = self.PESO_PREPARO if self.etapa != "Iniciando" else 0
        if self.total_relatorios:
            prontos = sum(1 for r in self.relatorios
                          if r["estado"] in ("ok", "falhou"))
            base += self.PESO_DOWNLOADS * prontos / self.total_relatorios
        if self.abas_gravadas and self.total_relatorios:
            base += min(self.PESO_GRAVACAO,
                        self.PESO_GRAVACAO * self.abas_gravadas / self.total_relatorios)
        if self.etapa.startswith("Solicitacao"):
            base = self.PESO_PREPARO + self.PESO_DOWNLOADS + self.PESO_GRAVACAO + 6
        if self.terminou:
            base = 100
        self.progresso = max(self.progresso, min(base, 100))

    # ------------------------------------------------------------------ parse
    def processar(self, linha: str) -> None:
        corpo = linha.split("|", 2)[-1].strip() if "|" in linha else linha.strip()

        if "Nuvem:" in corpo:
            self.etapa = "Conectado a nuvem"
        elif corpo.startswith("Planilha:"):
            self.etapa = "Planilha localizada"
        elif corpo.startswith("Backup local"):
            self.etapa = "Backup da planilha"
        elif corpo.startswith("Abrindo http"):
            self.etapa = "Abrindo o BAP Tools"
        elif "Login confirmado" in corpo:
            self.etapa = "Autenticado no BAP Tools"

        achado = self.RE_RELATORIO.search(corpo)
        if achado:
            indice, total, nome, aba = achado.groups()
            self._garantir(int(total))
            self.indice_atual = int(indice)
            atual = self._atual()
            if atual:
                atual.update({"nome": nome.strip(), "estado": "rodando",
                              "detalhe": f"-> {aba}"})
            self.etapa = f"Baixando {int(indice)} de {int(total)}"
            self._recalcular()
            return

        atual = self._atual()
        if atual and atual["estado"] == "rodando":
            if "Executar Consulta" in corpo:
                atual["detalhe"] = "consultando..."
            elif "consulta concluida" in corpo:
                atual["detalhe"] = "gerando arquivo..."
            elif "aguardando o botao" in corpo:
                atual["detalhe"] = "aguardando o download..."
            elif self.RE_BAIXADO.search(corpo):
                kb = self.RE_BAIXADO.search(corpo).group(1)
                atual.update({"estado": "ok", "detalhe": f"{kb} KB"})
                self._recalcular()

        falha = self.RE_FALHA_REL.search(corpo)
        if falha:
            nome, motivo = falha.groups()
            alvo = next((r for r in self.relatorios if r["nome"] == nome.strip()),
                        self._atual())
            if alvo:
                alvo.update({"estado": "falhou", "detalhe": motivo[:60]})
            self.houve_erro = True
            self._recalcular()
            return

        gravando = self.RE_GRAVANDO.search(corpo)
        if gravando:
            self.abas_gravadas += 1
            self.etapa = f"Gravando a aba {gravando.group(1)}"
            self._recalcular()
            return

        if "Montando a solicitacao" in corpo:
            self.etapa = "Solicitacao de coleta"
            self._recalcular()
        elif "arquivo(s) CSV" in corpo:
            self.etapa = "Solicitacao: gerando CSVs"
        elif corpo.startswith("FALHA:"):
            self.houve_erro = True
            self.mensagem_erro = corpo[6:].strip()
            self.etapa = "Falhou"

        concluido = self.RE_CONCLUIDO.search(corpo)
        if concluido:
            self.terminou = True
            self.etapa = "Concluído"
            self._recalcular()


# =============================================================================
# 2. A JANELA
# =============================================================================

class JanelaBAP:

    def __init__(self, raiz: tk.Tk, argumentos: list[str],
                 encerrar_anterior: bool = True):
        self.raiz = raiz
        self.argumentos = argumentos
        self.encerrar_anterior = encerrar_anterior
        self.leitor = LeitorDeProgresso()
        self.fila: queue.Queue = queue.Queue()
        self.inicio = time.time()
        self.processo: subprocess.Popen | None = None
        self.linhas_relatorio: dict[int, tuple] = {}

        self.cartao_resumo: tk.Frame | None = None
        self.progresso_mostrado = 0.0

        raiz.title("Automação BAP")
        raiz.configure(bg=FUNDO)
        raiz.geometry("1060x780")
        raiz.minsize(760, 520)

        self._montar_estilo()
        # ORDEM IMPORTA: o rodape e empacotado ANTES do resto, preso embaixo.
        # Assim o botao Fechar tem lugar reservado e nunca e empurrado para
        # fora quando o cartao de resumo entra no fim da execucao.
        self._montar_cabecalho()
        self._montar_rodape()
        self._montar_corpo()
        self._montar_progresso()
        self._montar_relatorios()
        self._montar_log()

        self.raiz.after(200, self._iniciar)
        self.raiz.after(100, self._drenar)
        self.raiz.after(500, self._tique)
        self.raiz.after(40, self._animar_barra)

    # ------------------------------------------------------------ construcao
    def _montar_estilo(self) -> None:
        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("BAP.Horizontal.TProgressbar", troughcolor=LINHA,
                         background=ACENTO, bordercolor=LINHA,
                         lightcolor=ACENTO, darkcolor=ACENTO, thickness=10)
        estilo.configure("BAP.Vertical.TScrollbar", troughcolor=FUNDO,
                         background=LINHA, bordercolor=FUNDO,
                         arrowcolor=TEXTO_FRACO, darkcolor=LINHA, lightcolor=LINHA)

    def _cartao(self, pai, **kw):
        quadro = tk.Frame(pai, bg=CARTAO, highlightbackground=LINHA,
                          highlightthickness=1, **kw)
        return quadro

    def _montar_corpo(self) -> None:
        """
        Miolo rolavel. Em tela grande os cartoes ocupam tudo e o log estica;
        em tela pequena (ou quando o cartao de resumo entra) aparece uma barra
        de rolagem em vez de cortar o conteudo.
        """
        quadro = tk.Frame(self.raiz, bg=FUNDO)
        quadro.pack(side="top", fill="both", expand=True)

        self.tela = tk.Canvas(quadro, bg=FUNDO, highlightthickness=0, bd=0)
        self.tela.pack(side="left", fill="both", expand=True)

        self.rolagem = ttk.Scrollbar(quadro, orient="vertical",
                                     style="BAP.Vertical.TScrollbar",
                                     command=self.tela.yview)
        self.tela.configure(yscrollcommand=self.rolagem.set)

        self.corpo = tk.Frame(self.tela, bg=FUNDO)
        self.item_corpo = self.tela.create_window((0, 0), window=self.corpo,
                                                  anchor="nw")
        self._altura_aplicada = -1

        self.corpo.bind("<Configure>", lambda e: self._ajustar_rolagem())
        self.tela.bind("<Configure>", self._tela_redimensionada)
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.raiz.bind_all(evento, self._roda_do_mouse)

    def _tela_redimensionada(self, evento) -> None:
        self.tela.itemconfigure(self.item_corpo, width=evento.width)
        self._ajustar_rolagem()

    def _altura_de_linha(self) -> int:
        if getattr(self, "_linha_px", 0) <= 0:
            try:
                from tkinter import font as tkfont
                self._linha_px = tkfont.Font(
                    font=self.log.cget("font")).metrics("linespace")
            except Exception:
                self._linha_px = 14
        return max(self._linha_px, 8)

    def _encaixar_log(self, altura_tela: int, preciso: int) -> int:
        """
        Da ao log o espaco que sobra, entre 4 e 40 linhas. E o que faz a janela
        acompanhar o redimensionamento em vez de simplesmente rolar.
        """
        try:
            outros = preciso - self.cartao_log.winfo_reqheight()
            sobra = altura_tela - outros - 58      # rotulo DETALHES + margens
            linhas = int(sobra / self._altura_de_linha())
            linhas = max(MIN_LINHAS_VISIVEIS, min(MAX_LINHAS_VISIVEIS, linhas))
            if linhas != int(self.log.cget("height")):
                self.log.configure(height=linhas)
                self.raiz.update_idletasks()
                preciso = self.corpo.winfo_reqheight()
        except Exception:
            pass
        return preciso

    def _ajustar_rolagem(self) -> None:
        largura = self.tela.winfo_width()
        altura = self.tela.winfo_height()
        if largura <= 1 or altura <= 1:
            return
        preciso = self._encaixar_log(altura, self.corpo.winfo_reqheight())
        # em tela sobrando, o corpo ocupa a altura toda (o log estica)
        alvo = max(preciso, altura)
        if alvo != self._altura_aplicada:
            self._altura_aplicada = alvo
            self.tela.itemconfigure(self.item_corpo, height=alvo)
            self.tela.configure(scrollregion=(0, 0, largura, alvo))
            # o log mudou de tamanho: volta a mostrar a ultima linha
            try:
                self.log.see("end")
            except Exception:
                pass

        precisa_barra = preciso > altura + 2
        visivel = bool(self.rolagem.winfo_ismapped())
        if precisa_barra and not visivel:
            self.rolagem.pack(side="right", fill="y")
        elif not precisa_barra and visivel:
            self.rolagem.pack_forget()
            self.tela.yview_moveto(0)

    def _roda_do_mouse(self, evento) -> None:
        if not self.rolagem.winfo_ismapped():
            return
        # com o ponteiro sobre o log, a roda rola o proprio log
        alvo = getattr(evento, "widget", None)
        if alvo is not None and str(alvo).startswith(str(self.log)):
            return
        if getattr(evento, "num", None) == 4:
            passos = -1
        elif getattr(evento, "num", None) == 5:
            passos = 1
        else:
            passos = -1 if evento.delta > 0 else 1
        self.tela.yview_scroll(passos, "units")

    def _montar_cabecalho(self) -> None:
        topo = tk.Frame(self.raiz, bg=FUNDO)
        topo.pack(fill="x", padx=18, pady=(12, 4))

        tk.Label(topo, text="AUTOMAÇÃO BAP", bg=FUNDO, fg=ACENTO,
                 font=(FONTE, 9, "bold")).pack(anchor="w")
        tk.Label(topo, text="Relatórios do BAP Tools → TABELA_BAP → solicitação de coleta",
                 bg=FUNDO, fg=TEXTO_FRACO, font=(FONTE, 10)).pack(anchor="w")

        if "--simular" in self.argumentos:
            tk.Label(topo, text="  MODO SIMULAÇÃO — nada será alterado na nuvem  ",
                     bg=ALERTA, fg=FUNDO, font=(FONTE, 9, "bold")).pack(anchor="w",
                                                                        pady=(8, 0))

    def _montar_progresso(self) -> None:
        cartao = self._cartao(self.corpo)
        cartao.pack(fill="x", padx=18, pady=(6, 5))

        linha = tk.Frame(cartao, bg=CARTAO)
        linha.pack(fill="x", padx=16, pady=(10, 3))

        self.rotulo_etapa = tk.Label(linha, text="Iniciando...", bg=CARTAO, fg=TEXTO,
                                     font=(FONTE, 13, "bold"))
        self.rotulo_etapa.pack(side="left")

        self.rotulo_tempo = tk.Label(linha, text="00:00", bg=CARTAO, fg=TEXTO_FRACO,
                                     font=("Consolas", 12))
        self.rotulo_tempo.pack(side="right")

        self.barra = ttk.Progressbar(cartao, style="BAP.Horizontal.TProgressbar",
                                     maximum=100, value=0)
        self.barra.pack(fill="x", padx=16, pady=(3, 4))

        self.rotulo_pct = tk.Label(cartao, text="0%", bg=CARTAO, fg=TEXTO_FRACO,
                                   font=(FONTE, 9))
        self.rotulo_pct.pack(anchor="e", padx=16, pady=(0, 8))

    def _montar_relatorios(self) -> None:
        cartao = self._cartao(self.corpo)
        cartao.pack(fill="x", padx=18, pady=5)
        self.cartao_relatorios = cartao
        tk.Label(cartao, text="RELATÓRIOS", bg=CARTAO, fg=TEXTO_FRACO,
                 font=(FONTE, 8, "bold")).pack(anchor="w", padx=16, pady=(10, 4))
        self.area_relatorios = tk.Frame(cartao, bg=CARTAO)
        self.area_relatorios.pack(fill="x", padx=16, pady=(0, 8))

    def _montar_log(self) -> None:
        cartao = self._cartao(self.corpo)
        cartao.pack(fill="both", expand=True, padx=18, pady=(5, 6))
        self.cartao_log = cartao
        tk.Label(cartao, text="DETALHES", bg=CARTAO, fg=TEXTO_FRACO,
                 font=(FONTE, 8, "bold")).pack(anchor="w", padx=16, pady=(10, 3))
        self.log = scrolledtext.ScrolledText(
            cartao, bg="#0A100E", fg=TEXTO_FRACO, insertbackground=TEXTO,
            font=("Consolas", 9), relief="flat", height=6, wrap="none")
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self.log.tag_config("erro", foreground=ERRO)
        self.log.tag_config("aviso", foreground=ALERTA)
        self.log.tag_config("bom", foreground=OK)
        self.log.configure(state="disabled")

    def _montar_rodape(self) -> None:
        rodape = tk.Frame(self.raiz, bg=FUNDO)
        rodape.pack(side="bottom", fill="x", padx=18, pady=(6, 14))

        def botao(texto, comando, principal=False):
            b = tk.Button(rodape, text=texto, command=comando,
                          bg=ACENTO if principal else CARTAO,
                          fg=FUNDO if principal else TEXTO,
                          activebackground=ACENTO, activeforeground=FUNDO,
                          relief="flat", font=(FONTE, 9, "bold" if principal else "normal"),
                          padx=14, pady=7, cursor="hand2",
                          highlightbackground=LINHA, highlightthickness=1)
            b.pack(side="left", padx=(0, 8))
            return b

        botao("Abrir solicitação", self._abrir_solicitacao)
        botao("Alterações de preço", self._abrir_precos)
        botao("Card do trade", self._abrir_card)
        botao("Estoque x preço", self._abrir_estoque_bap)
        botao("Arquivos para importar", lambda: self._abrir(PASTA_IMPORTAR))
        botao("Logs", lambda: self._abrir(PASTA_LOGS))

        self.botao_fechar = tk.Button(
            rodape, text="Fechar", command=self._fechar, bg=CARTAO, fg=TEXTO,
            activebackground=ERRO, relief="flat", font=(FONTE, 9), padx=14, pady=7,
            cursor="hand2", highlightbackground=LINHA, highlightthickness=1)
        self.botao_fechar.pack(side="right")

    # ------------------------------------------------------------------ start
    def _iniciar(self) -> None:
        threading.Thread(target=self._rodar, daemon=True).start()

    # ------------------------------------------- encerrar a execucao anterior
    def _derrubar_processos(self, criacao: int) -> list[str]:
        """
        Mata qualquer bap_automation.py que ainda esteja rodando nesta maquina.
        Devolve a lista do que foi derrubado (vazia quando nao havia nada).
        """
        derrubados: list[str] = []
        try:
            if os.name == "nt":
                script = PS_ENCERRAR.format(pid=os.getpid())
                saida = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-Command", script],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=30, creationflags=criacao)
            else:
                saida = subprocess.run(
                    ["pkill", "-f", "-e", "bap_automation.py"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=30)
            for linha in (saida.stdout or "").splitlines():
                if linha.strip():
                    derrubados.append(linha.strip())
            # pkill devolve 1 quando nao achou nada: isso e normal, nao e erro.
            if saida.returncode not in (0, 1) and (saida.stderr or "").strip():
                self.fila.put(("linha", "AVISO: nao consegui varrer os processos: "
                                        f"{saida.stderr.strip()[:200]}"))
        except subprocess.TimeoutExpired:
            self.fila.put(("linha", "AVISO: a varredura de processos demorou demais."))
        except Exception as erro:
            self.fila.put(("linha", f"AVISO: nao consegui checar execucoes antigas: {erro}"))
        return derrubados

    def _encerrar_execucao_anterior(self, executavel: str, ambiente: dict,
                                    criacao: int) -> None:
        """
        Sempre roda antes de comecar: derruba a rodada anterior e libera a trava
        com --destravar, para nunca esbarrar em "execucao em andamento".
        """
        self.fila.put(("etapa", "Encerrando a execução anterior"))
        derrubados = self._derrubar_processos(criacao)
        if derrubados:
            for item in derrubados:
                self.fila.put(("linha", f"Execucao anterior encerrada: {item}"))
            time.sleep(ESPERA_APOS_ENCERRAR)
        else:
            self.fila.put(("linha", "Nenhuma execucao anterior estava rodando."))

        self.fila.put(("etapa", "Liberando a trava"))
        try:
            saida = subprocess.run(
                [executavel, str(SCRIPT), "--destravar"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(PASTA), env=ambiente, timeout=180, creationflags=criacao)
            texto = (saida.stdout or "") + (saida.stderr or "")
            for linha in texto.splitlines():
                if linha.strip():
                    self.fila.put(("linha", linha.rstrip()))
            if saida.returncode != 0:
                self.fila.put(("linha",
                               "AVISO: --destravar terminou com codigo "
                               f"{saida.returncode}; seguindo mesmo assim."))
        except subprocess.TimeoutExpired:
            self.fila.put(("linha", "AVISO: --destravar demorou demais; seguindo."))
        except Exception as erro:
            self.fila.put(("linha", f"AVISO: nao consegui destravar: {erro}"))

    # --------------------------------------------------------------- execucao
    # ------------------------------------------------- qual Python usar
    def _candidatos_de_python(self) -> list[str]:
        """
        Onde procurar um Python que tenha as bibliotecas. A ordem importa:
        o ambiente virtual do instalador vem primeiro, porque e o unico que
        com certeza tem pandas, openpyxl e playwright.
        """
        nomes = (("Scripts", "python.exe") if os.name == "nt"
                 else ("bin", "python3"))
        locais = []
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME", "")
        if appdata:
            locais.append(Path(appdata) / "BAP_TOOLS" / ".venv" / nomes[0] / nomes[1])
        locais.append(PASTA / ".venv" / nomes[0] / nomes[1])

        candidatos = [str(c) for c in locais if c.exists()]

        # por ultimo, o Python que abriu esta janela
        atual = sys.executable
        if atual.lower().endswith("pythonw.exe"):
            alternativo = Path(atual).with_name("python.exe")
            if alternativo.exists():
                atual = str(alternativo)
        if atual and atual not in candidatos:
            candidatos.append(atual)
        return candidatos

    def _escolher_python(self) -> str | None:
        """
        Devolve o primeiro Python que consegue importar o que a automacao usa.
        Sem isso, a janela abria com o Python do sistema e a automacao morria
        num "No module named 'pandas'" que nao dizia nada ao usuario.
        """
        teste = "import pandas, openpyxl, playwright"
        criacao = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        for caminho in self._candidatos_de_python():
            try:
                saida = subprocess.run([caminho, "-c", teste], capture_output=True,
                                       text=True, timeout=90, creationflags=criacao)
            except Exception:
                continue
            if saida.returncode == 0:
                self.fila.put(("linha", f"Python em uso: {caminho}"))
                return caminho
            faltando = (saida.stderr or "").strip().splitlines()
            if faltando:
                self.fila.put(("linha", f"  {caminho} nao serve: {faltando[-1][:120]}"))
        return None

    def _rodar(self) -> None:
        self.fila.put(("etapa", "Procurando o Python"))
        executavel = self._escolher_python()
        if executavel is None:
            for linha in (
                "NAO ACHEI UM PYTHON COM AS BIBLIOTECAS DA AUTOMACAO.",
                "",
                "Isso acontece quando a janela e aberta dando duplo clique no",
                "arquivo bap_janela.py: o Windows abre com o Python do sistema,",
                "que nao tem pandas, openpyxl nem playwright.",
                "",
                "COMO RESOLVER:",
                "  1. rode o instalar_bap.bat desta pasta (uma vez por maquina);",
                "  2. abra sempre pelo atalho 'Automacao BAP' da Area de Trabalho,",
                "     nao pelo arquivo .py.",
                "",
                "Procurei nestes lugares:",
                *[f"  - {c}" for c in self._candidatos_de_python()],
            ):
                self.fila.put(("linha", linha))
            self.fila.put(("fim", 1))
            return

        comando = [executavel, str(SCRIPT), "--verboso", *self.argumentos]
        ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")

        criacao = 0
        if os.name == "nt":
            criacao = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        if self.encerrar_anterior:
            self._encerrar_execucao_anterior(executavel, ambiente, criacao)

        self.fila.put(("etapa", "Iniciando a automacao"))
        try:
            self.processo = subprocess.Popen(
                comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                cwd=str(PASTA), env=ambiente, creationflags=criacao)
        except Exception as erro:
            self.fila.put(("linha", f"NAO CONSEGUI INICIAR: {erro}"))
            self.fila.put(("fim", 1))
            return

        for linha in self.processo.stdout:
            self.fila.put(("linha", linha.rstrip("\n")))
        self.processo.wait()
        self.fila.put(("fim", self.processo.returncode))

    # ------------------------------------------------------------- interface
    def _drenar(self) -> None:
        """
        Esvazia a fila de uma vez e escreve o log em UMA operacao. Escrever
        linha a linha, rolando o texto a cada uma, e o que deixava a janela
        pesada quando o log vinha em rajada.
        """
        pendentes: list[str] = []
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "linha":
                    self.leitor.processar(valor)
                    pendentes.append(valor)
                elif tipo == "etapa":
                    self.leitor.etapa = valor
                elif tipo == "fim":
                    if pendentes:
                        self._escrever(pendentes)
                        pendentes = []
                    self._finalizar(valor)
        except queue.Empty:
            pass
        if pendentes:
            self._escrever(pendentes)
        self._atualizar()
        self.raiz.after(120, self._drenar)

    @staticmethod
    def _marca_da_linha(linha: str) -> str:
        alta = linha.upper()
        if "ERROR" in alta or "FALHA" in alta:
            return "erro"
        if "WARNING" in alta or alta.startswith("AVISO"):
            return "aviso"
        if "Baixado" in linha or "Concluido" in linha:
            return "bom"
        return ""

    def _escrever(self, linhas) -> None:
        if isinstance(linhas, str):
            linhas = [linhas]
        if not linhas:
            return
        self.log.configure(state="normal")
        for linha in linhas:
            self.log.insert("end", linha + "\n", self._marca_da_linha(linha))

        # nao deixa o widget crescer sem limite: so as ultimas MAX_LINHAS_LOG
        total = int(self.log.index("end-1c").split(".")[0])
        if total > MAX_LINHAS_LOG:
            self.log.delete("1.0", f"{total - MAX_LINHAS_LOG + 1}.0")

        self.log.see("end")
        self.log.configure(state="disabled")

    def _animar_barra(self) -> None:
        """
        Aproxima a barra do valor real aos poucos, em vez de dar saltos. E so
        aparencia, mas e o que faz a janela parecer viva enquanto um relatorio
        demora para vir.
        """
        alvo = self.leitor.progresso
        atual = self.progresso_mostrado
        if abs(alvo - atual) > 0.15:
            atual += (alvo - atual) * 0.18
            if abs(alvo - atual) < 0.15:
                atual = alvo
            self.progresso_mostrado = atual
            self.barra["value"] = atual
            self.rotulo_pct.configure(text=f"{atual:.0f}%")
        self.raiz.after(40, self._animar_barra)

    def _atualizar(self) -> None:
        leitor = self.leitor
        if self.rotulo_etapa.cget("text") != leitor.etapa:
            self.rotulo_etapa.configure(text=leitor.etapa)

        for indice, relatorio in enumerate(leitor.relatorios):
            if indice not in self.linhas_relatorio:
                linha = tk.Frame(self.area_relatorios, bg=CARTAO)
                linha.pack(fill="x", pady=2)
                marca = tk.Label(linha, text="○", bg=CARTAO, fg=TEXTO_FRACO,
                                 font=(FONTE, 11), width=2)
                marca.pack(side="left")
                nome = tk.Label(linha, text="", bg=CARTAO, fg=TEXTO,
                                font=(FONTE, 10), anchor="w", width=34)
                nome.pack(side="left")
                detalhe = tk.Label(linha, text="", bg=CARTAO, fg=TEXTO_FRACO,
                                   font=(FONTE, 9), anchor="w")
                detalhe.pack(side="left", fill="x", expand=True)
                self.linhas_relatorio[indice] = (marca, nome, detalhe)

            marca, nome, detalhe = self.linhas_relatorio[indice]
            simbolo, cor = {
                "pendente": ("○", TEXTO_FRACO),
                "rodando": ("◐", ACENTO),
                "ok": ("✓", OK),
                "falhou": ("✕", ERRO),
            }[relatorio["estado"]]
            marca.configure(text=simbolo, fg=cor)
            nome.configure(text=relatorio["nome"],
                           fg=TEXTO if relatorio["estado"] != "pendente" else TEXTO_FRACO)
            detalhe.configure(text=relatorio["detalhe"], fg=cor if
                              relatorio["estado"] == "falhou" else TEXTO_FRACO)

    def _tique(self) -> None:
        if not self.leitor.terminou:
            passado = int(time.time() - self.inicio)
            self.rotulo_tempo.configure(text=f"{passado // 60:02d}:{passado % 60:02d}")
        # Confere a rolagem por tempo, nao so por evento: quando a altura do
        # corpo esta fixada, acrescentar um cartao NAO dispara <Configure>.
        self._ajustar_rolagem()
        self.raiz.after(500, self._tique)

    def _finalizar(self, codigo: int) -> None:
        if self.cartao_resumo is not None:      # ja finalizou uma vez
            return
        self.leitor.terminou = True
        self.leitor.progresso = 100
        self._atualizar()
        self._mostrar_resumo(codigo)

    def _mostrar_resumo(self, codigo: int) -> None:
        # O ultimo_resumo.json fica na pasta compartilhada: pode ser de OUTRA
        # maquina ou de uma rodada anterior. So vale se foi escrito DEPOIS que
        # esta execucao comecou - senao a janela mostraria numeros alheios.
        resumo = {}
        try:
            if (ARQUIVO_RESUMO.exists()
                    and ARQUIVO_RESUMO.stat().st_mtime >= self.inicio - 5):
                resumo = json.loads(ARQUIVO_RESUMO.read_text(encoding="utf-8"))
        except Exception:
            pass

        situacao = resumo.get("status")
        if situacao is None:
            situacao = "sucesso" if codigo == 0 and not self.leitor.houve_erro else "erro"
        deu_certo = codigo == 0 and situacao == "sucesso" and not self.leitor.houve_erro
        parcial = codigo == 0 and not deu_certo
        cor = OK if deu_certo else (ALERTA if parcial else ERRO)
        titulo = ("Concluído com sucesso" if deu_certo
                  else ("Concluído com pendências" if parcial else "Falhou"))

        cartao = tk.Frame(self.corpo, bg=CARTAO, highlightbackground=cor,
                          highlightthickness=2)
        self.cartao_resumo = cartao
        cartao.pack(fill="x", padx=18, pady=(0, 8),
                    before=self.cartao_relatorios)

        tk.Label(cartao, text=titulo, bg=CARTAO, fg=cor,
                 font=(FONTE, 12, "bold")).pack(anchor="w", padx=16, pady=(9, 2))

        if not resumo:
            tk.Label(cartao,
                     text="Esta execucao nao chegou a gerar resumo. "
                          "Veja os detalhes abaixo.",
                     bg=CARTAO, fg=TEXTO_FRACO, font=(FONTE, 10),
                     wraplength=900, justify="left").pack(anchor="w", padx=16,
                                                          pady=(0, 12))
            self.botao_fechar.configure(bg=ACENTO, fg=FUNDO,
                                        font=(FONTE, 9, "bold"))
            return

        sol = resumo.get("solicitacao") or {}
        itens = [
            ("Relatórios", f"{resumo.get('relatorios_ok', '-')} de "
                           f"{resumo.get('relatorios_pedidos', '-')}"),
            ("Duração", f"{resumo.get('duracao_segundos', '-')} s"),
            ("Coletas novas", str(sol.get("linhas", "-"))),
            ("Já solicitadas", str(sol.get("repetidas", "-"))),
            ("Pedidos novos", str(sol.get("novos_pedidos", "-"))),
            ("Arquivos CSV", str(len(sol.get("csv_gerados") or []))),
        ]
        grade = tk.Frame(cartao, bg=CARTAO)
        grade.pack(fill="x", padx=16, pady=(4, 9))
        for coluna, (rotulo, valor) in enumerate(itens):
            celula = tk.Frame(grade, bg=CARTAO)
            celula.grid(row=0, column=coluna, sticky="w", padx=(0, 26))
            tk.Label(celula, text=rotulo.upper(), bg=CARTAO, fg=TEXTO_FRACO,
                     font=(FONTE, 8)).pack(anchor="w")
            tk.Label(celula, text=valor, bg=CARTAO, fg=TEXTO,
                     font=(FONTE, 14, "bold")).pack(anchor="w")

        if resumo.get("mensagem"):
            tk.Label(cartao, text=resumo["mensagem"][:200], bg=CARTAO, fg=ERRO,
                     font=(FONTE, 9), wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 12))

        # Pedidos com mais unidades solicitadas do que a demanda.
        excessos = sol.get("excessos") or []
        criados = [c for c in excessos if not c.get("herdado")]
        herdados = len(excessos) - len(criados)
        if criados:
            tk.Label(cartao,
                     text=f"⚠ {len(criados)} pedido(s) passaram da demanda "
                          f"NESTA rodada. Isso não deveria acontecer — avise "
                          f"antes de abrir as SEPs.",
                     bg=CARTAO, fg=ERRO, font=(FONTE, 9, "bold"),
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))
        if herdados:
            unidades = sum(c.get("excesso", 0) for c in excessos
                           if c.get("herdado"))
            tk.Label(cartao,
                     text=f"{herdados} pedido(s) já estavam com mais unidades "
                          f"solicitadas do que a demanda ({unidades:.0f} "
                          f"unidades). Nada novo foi gerado para eles; as SEPs "
                          f"em excesso precisam ser canceladas na mão.",
                     bg=CARTAO, fg=TEXTO_FRACO, font=(FONTE, 9),
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 8))

        # Tabela de preco: o que mudou desde a rodada anterior.
        precos = resumo.get("precos") or {}
        if precos.get("linhas"):
            tipos = precos.get("por_tipo") or {}
            detalhe = ", ".join(f"{q} {t.lower()}" for t, q in sorted(tipos.items()))
            texto_preco = (f"Tabela de preço: {precos['linhas']} alteração(ões) "
                           f"desde {precos.get('comparado_com', 'a rodada anterior')}")
            if detalhe:
                texto_preco += f" — {detalhe}"
            if precos.get("maior_alta") is not None:
                texto_preco += (f". Maior alta {precos['maior_alta']:+.2f}%, "
                                f"maior baixa {precos['maior_baixa']:+.2f}%")
            if precos.get("estoque_impactado"):
                texto_preco += (f". Estoque afetado: "
                                f"{int(precos['estoque_impactado']):,} un"
                                .replace(",", "."))
            if precos.get("card"):
                texto_preco += ". Card do trade pronto em \"Card do trade\""
            tk.Label(cartao, text=texto_preco + ".", bg=CARTAO, fg=TEXTO_FRACO,
                     font=(FONTE, 9), wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))
        elif precos.get("primeira_foto"):
            tk.Label(cartao,
                     text="Tabela de preço: primeira foto guardada. A próxima "
                          "rodada já compara com ela.",
                     bg=CARTAO, fg=TEXTO_FRACO, font=(FONTE, 9)).pack(
                         anchor="w", padx=16, pady=(0, 6))

        eb = resumo.get("estoque_bap") or {}
        if eb.get("erro"):
            # ANTES ESTA FALHA ERA MUDA: o passo do estoque e envolvido num
            # try/except, a rodada seguia e o cartao so falava do ESTOQUE_BAP
            # quando ele dava certo. Resultado: o arquivo ficou nove dias
            # parado sem ninguem perceber.
            tk.Label(cartao,
                     text=f"⚠ O ESTOQUE_BAP NAO foi atualizado nesta rodada: "
                          f"{eb['erro'][:160]}",
                     bg=CARTAO, fg=ERRO, font=(FONTE, 9, "bold"),
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))
            tk.Label(cartao,
                     text="   O arquivo continua com a foto da ultima rodada "
                          "que deu certo. O MIX, a oportunidade de estoque e "
                          "a sugestao de kits leem esse arquivo.",
                     bg=CARTAO, fg=TEXTO_FRACO, font=(FONTE, 9),
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))
        elif eb.get("linhas"):
            texto_eb = (f"ESTOQUE_BAP: {eb['linhas']:,} linha(s), "
                        f"{eb.get('produtos', 0):,} produtos em "
                        f"{eb.get('filiais', 0)} filiais".replace(",", "."))
            if eb.get("com_estoque_sem_preco"):
                texto_eb += (f". {eb['com_estoque_sem_preco']:,} com estoque e "
                             f"SEM preço na filial".replace(",", "."))
            tk.Label(cartao, text=texto_eb + ".", bg=CARTAO, fg=TEXTO_FRACO,
                     font=(FONTE, 9), wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))

        bc = resumo.get("base_cliente") or {}
        if bc.get("erro"):
            tk.Label(cartao,
                     text=f"⚠ A BASE_CLIENTE NAO foi atualizada nesta rodada: "
                          f"{bc['erro'][:160]}",
                     bg=CARTAO, fg=ERRO, font=(FONTE, 9, "bold"),
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))
            tk.Label(cartao,
                     text="   O arquivo continua com a carteira da ultima "
                          "rodada que deu certo. O Planner e o Gerador de "
                          "Meta leem esse arquivo.",
                     bg=CARTAO, fg=TEXTO_FRACO, font=(FONTE, 9),
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))
        elif bc.get("clientes"):
            texto_bc = (f"BASE_CLIENTE: {bc['clientes']:,} cliente(s), "
                        f"{bc.get('notas', 0):,} nota(s) e "
                        f"{bc.get('itens', 0):,} item(ns) de histórico"
                        .replace(",", "."))
            tk.Label(cartao, text=texto_bc + ".", bg=CARTAO, fg=TEXTO_FRACO,
                     font=(FONTE, 9), wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 6))

        recalculadas = sol.get("sem_estoque_recalculadas") or 0
        if recalculadas:
            tk.Label(cartao,
                     text=f"{recalculadas} linha(s) SEM ESTOQUE foram "
                          f"recalculadas.",
                     bg=CARTAO, fg=TEXTO_FRACO, font=(FONTE, 9)).pack(
                         anchor="w", padx=16, pady=(0, 6))

        csvs = sol.get("csv_gerados") or []
        for nome in csvs[:4]:
            tk.Label(cartao, text=f"   • {nome}", bg=CARTAO, fg=TEXTO_FRACO,
                     font=("Consolas", 9)).pack(anchor="w", padx=16)
        if len(csvs) > 4:
            tk.Label(cartao, text=f"   • e mais {len(csvs) - 4} arquivo(s) "
                                  f"— veja em \"Arquivos para importar\"",
                     bg=CARTAO, fg=TEXTO_FRACO,
                     font=(FONTE, 9)).pack(anchor="w", padx=16)
        if csvs:
            tk.Frame(cartao, bg=CARTAO, height=10).pack()

        self.botao_fechar.configure(bg=ACENTO, fg=FUNDO, font=(FONTE, 9, "bold"))

    # ----------------------------------------------------------------- acoes
    def _abrir(self, caminho: Path) -> None:
        try:
            caminho.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            if os.name == "nt":
                os.startfile(str(caminho))          # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(caminho)])
            else:
                subprocess.Popen(["xdg-open", str(caminho)])
        except Exception as erro:
            self._escrever(f"Nao consegui abrir {caminho}: {erro}")

    def _abrir_solicitacao(self) -> None:
        """Abre a SOLICITACAO_BAP direto da pasta da nuvem."""
        try:
            sys.path.insert(0, str(PASTA))
            import bap_automation as bap
            alvo = Path(str(bap.caminho_da_solicitacao()))
            if alvo.exists():
                self._abrir(alvo)
                return
            self._abrir(alvo.parent)
        except Exception as erro:
            self._escrever(f"Nao consegui localizar a solicitacao: {erro}")
            self._abrir(PASTA)

    def _abrir_precos(self) -> None:
        """Abre o Excel com as alteracoes da tabela de preco."""
        try:
            sys.path.insert(0, str(PASTA))
            import bap_automation as bap
            alvo = Path(str(bap.PASTA_RELATORIOS)) / bap.ARQUIVO_PRECOS
            if alvo.exists():
                self._abrir(alvo)
                return
            self._escrever("Ainda nao existe o arquivo de alteracoes de preco. "
                           "Ele nasce na primeira rodada em que algum preco "
                           "mudar.")
            self._abrir(alvo.parent)
        except Exception as erro:
            self._escrever(f"Nao consegui localizar as alteracoes de preco: {erro}")
            self._abrir(PASTA)

    def _abrir_card(self) -> None:
        """Abre a pasta com os cards de preco para mandar nos grupos."""
        try:
            sys.path.insert(0, str(PASTA))
            import bap_automation as bap
            pasta = Path(str(bap.PASTA_LOCAL)) / bap.SUBPASTA_CARDS
            cards = sorted(pasta.glob("card_precos_*.png")) if pasta.is_dir() else []
            if cards:
                self._abrir(cards[-1])
                return
            self._escrever("Ainda nao existe card. Ele nasce na primeira rodada "
                           "em que algum preco mudar.")
            self._abrir(pasta)
        except Exception as erro:
            self._escrever(f"Nao consegui localizar o card: {erro}")
            self._abrir(PASTA)

    def _abrir_estoque_bap(self) -> None:
        """Abre o ESTOQUE_BAP com o estoque e os precos por filial."""
        try:
            sys.path.insert(0, str(PASTA))
            import bap_automation as bap
            alvo = Path(str(bap.PASTA_RELATORIOS)) / bap.ARQUIVO_ESTOQUE_BAP
            if alvo.exists():
                self._abrir(alvo)
                return
            self._escrever("O ESTOQUE_BAP nasce ao fim da primeira rodada.")
            self._abrir(alvo.parent)
        except Exception as erro:
            self._escrever(f"Nao consegui localizar o ESTOQUE_BAP: {erro}")
            self._abrir(PASTA)

    def _fechar(self) -> None:
        if self.processo and self.processo.poll() is None:
            if not tk.messagebox.askyesno(
                    "Automação BAP",
                    "A execução ainda está em andamento.\nFechar mesmo assim?"):
                return
            try:
                self.processo.terminate()
            except Exception:
                pass
        self.raiz.destroy()


# Flags que sao da janela e NAO devem ir para o bap_automation.py.
FLAGS_DA_JANELA = {"--nao-encerrar", "--sem-encerrar", "--manter-execucao"}


def main() -> int:
    todas = [a for a in sys.argv[1:] if a.startswith("--")]
    encerrar_anterior = not any(a.lower() in FLAGS_DA_JANELA for a in todas)
    argumentos = [a for a in todas if a.lower() not in FLAGS_DA_JANELA]

    raiz = tk.Tk()
    from tkinter import messagebox
    tk.messagebox = messagebox
    JanelaBAP(raiz, argumentos, encerrar_anterior=encerrar_anterior)
    raiz.protocol("WM_DELETE_WINDOW", lambda: None)
    raiz.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
