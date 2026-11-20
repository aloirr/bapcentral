# -*- coding: utf-8 -*-
"""
ARQUIVO EM ABERTO: o pop-up "Continuar / Cancelar" do robo (05/11/2026)

(05/11, Alexandre) "Se o arquivo estiver aberto, deve aparecer um POP-UP
alerta com a mensagem 'Arquivo XXXX em aberto. Feche e clique em
Continuar.' Ai deve ter dois botoes: Continuar e Cancelar. Caso clique em
cancelar o processo e interrompido e caso clique em continuar ele tenta
novamente. Enquanto clicar em continuar ele vai continuar tentando verificar
se o arquivo esta livre."

Uso (bap_automation, antes de gravar por cima ou de recalcular no Excel):

    passo = aguardar_livre(caminho, "gravar", log=log)
        "livre" -> pode gravar
        "pular" -> ninguem respondeu em ESPERA_POPUP_ARQUIVO (ou nao ha tela
                   para mostrar o aviso): o robo pula SO aquele passo
    Cancelar -> levanta Cancelado (BaseException: nenhum "except Exception"
                do caminho engole - a rodada para de verdade)

(05/11, Alexandre: "Nao ta aberto mas diz que ta aberto. consigo colocar
para 'salvar e fechar' para forcar o fechamento") O aviso ganhou o botao
"Salvar e fechar": salva e fecha o arquivo no Excel desta maquina (pelo
COM), encerra o Excel SEM JANELA que esteja segurando (o que sobra de um
recalculo abandonado) e apaga o ~$ solto. Excel COM janela nunca e
encerrado - o aviso pede para salvar e fechar por la.

O aviso e uma janela Tk do PROPRIO processo do robo: aparece rodando pela
janela do BAP Tools (bap_janela) e pelo Agendador (console). Sem tela - a
tarefa rodando sem ninguem logado, ou a tela bloqueada - nao trava: o passo
e pulado e fica no log.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

# segundos que o aviso espera uma resposta antes de fechar sozinho e o robo
# pular o passo (para a rodada agendada sem ninguem na maquina nao ficar
# parada - a trava do robo dura 4 h). 0 = espera para sempre.
ESPERA_POPUP_ARQUIVO = 15 * 60
# o arquivo so conta como aberto se continuar travado nestas tentativas (o
# OneDrive sincronizando trava o arquivo por 1-2 s)
TENTATIVAS = 3
INTERVALO = 1.5
# (05/11, revisor) o "~$NOME" que o Excel cria ao lado do arquivo aberto so
# conta se estiver TRAVADO (o Excel segura o ~$ enquanto o arquivo esta
# aberto). ~$ solto - Excel que caiu ou foi encerrado - nao conta: senao o
# aviso voltava em toda rodada e o Continuar nunca resolvia.
TITULO = "Automação BAP"
VERDE = "#1E4620"           # o verde dos cabecalhos do robo (bap_visual)
FUNDO = "#FFFFFF"
TEXTO = "#1F2933"


class Cancelado(BaseException):
    """O usuario clicou em Cancelar no aviso de arquivo em aberto."""

    def __init__(self, arquivo):
        super().__init__(f"{arquivo} em aberto")
        self.arquivo = str(arquivo)


def mensagem(nome: str) -> str:
    return f"Arquivo {nome} em aberto. Feche e clique em Continuar."


LINHA_FECHAR = ("Salvar e fechar salva e fecha o arquivo no Excel desta "
                "máquina.")
MSG_EXCEL_VISIVEL = ("O arquivo está aberto num Excel com janela. Salve e "
                     "feche por lá.")
MSG_OUTRO_PROGRAMA = ("Ainda em uso por outro programa (OneDrive?). Aguarde "
                      "e clique em Continuar.")
def msg_nao_salvou(nome: str) -> str:
    return f"Não consegui salvar {nome} no Excel. Salve e feche por lá."


MSG_SEM_SUPORTE = ("Não consegui salvar e fechar por aqui (sem Windows ou "
                   "sem pywin32). Feche o arquivo e clique em Continuar.")


def somente_leitura(arq: Path) -> bool:
    """O arquivo tem o atributo "somente leitura" (nao e travamento)."""
    try:
        st = os.stat(arq)
    except OSError:
        return False
    atributos = getattr(st, "st_file_attributes", None)
    if atributos is not None:
        return bool(atributos & 0x1)            # FILE_ATTRIBUTE_READONLY
    return not (st.st_mode & 0o200)


def travado(arq: Path) -> bool:
    """Um programa segura o arquivo (nao abre para escrita). (05/11) O
    arquivo marcado "somente leitura" tambem nega a abertura para escrita,
    mas nao e ninguem segurando: nao conta (era um falso "em aberto" que o
    Continuar nunca resolvia)."""
    if not Path(arq).exists():
        return False
    try:
        with open(arq, "r+b"):
            return False
    except PermissionError:
        return not somente_leitura(arq)
    except OSError:
        return False


def arquivo_dono(caminho: Path) -> Path:
    caminho = Path(caminho)
    return caminho.parent / f"~${caminho.name}"


def _travado_agora(caminho: Path) -> bool:
    """Uma olhada: o Excel segura o arquivo aberto (nao deixa abrir para
    escrita) ou segura o ~$ dele na mesma pasta. ~$ solto nao conta."""
    return travado(caminho) or travado(arquivo_dono(caminho))


def apagar_dono_solto(caminho: Path, tentativas: int = 3,
                      intervalo: float = 1.0) -> bool:
    """Depois de encerrar o Excel do robo: apaga o ~$ que ele deixou, SO se
    ninguem estiver segurando (o ~$ do Excel de uma pessoa fica travado e
    nao e tocado). True = apagou."""
    dono = arquivo_dono(caminho)
    for i in range(max(1, tentativas)):
        if not dono.exists():
            return False
        if not travado(dono):
            try:
                dono.unlink()
                return True
            except OSError:
                pass
        if i < tentativas - 1:
            time.sleep(intervalo)       # o Excel encerrado ainda soltando
    return False


def em_uso(caminho, tentativas: int = TENTATIVAS,
           intervalo: float = INTERVALO, olhar=None) -> bool:
    """Aberto de verdade: travado em TODAS as tentativas (nao confunde com o
    OneDrive sincronizando)."""
    olhar = olhar or _travado_agora
    caminho = Path(caminho)
    for i in range(max(1, tentativas)):
        if not olhar(caminho):
            return False
        if i < tentativas - 1:
            time.sleep(intervalo)
    return True


def _tem_area_de_trabalho() -> bool:
    """No Windows: ha uma area de trabalho de verdade (alguem logado, tela
    desbloqueada) para mostrar o aviso? Fora do Windows: o Tk decide."""
    if os.name != "nt":
        return True
    try:
        import ctypes                                   # noqa: PLC0415
        u = ctypes.windll.user32
        h = u.OpenInputDesktop(0, False, 0x0001)        # DESKTOP_READOBJECTS
        if not h:
            return False
        u.CloseDesktop(h)
        return True
    except Exception:                                   # noqa: BLE001
        return True


def perguntar(nome: str, espera: float = ESPERA_POPUP_ARQUIVO,
              extra: str | None = None) -> str:
    """O aviso. Devolve "continuar", "fechar" (Salvar e fechar), "cancelar",
    "tempo" (ninguem respondeu) ou "sem_tela" (nao deu para mostrar).
    `extra`: o recado da tentativa anterior de Salvar e fechar."""
    if not _tem_area_de_trabalho():
        return "sem_tela"
    try:
        import tkinter as tk                            # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return "sem_tela"
    raiz = None
    try:
        pai = getattr(tk, "_default_root", None)
        if pai is None:
            raiz = tk.Tk()
            raiz.withdraw()
            pai = raiz
        janela = tk.Toplevel(pai)
    except Exception:                                   # noqa: BLE001
        if raiz is not None:
            try:
                raiz.destroy()
            except Exception:                           # noqa: BLE001
                pass
        return "sem_tela"
    resposta = {"v": "cancelar"}

    def fim(valor):
        resposta["v"] = valor
        try:
            janela.destroy()
        except Exception:                               # noqa: BLE001
            pass

    try:
        janela.title(TITULO)
        janela.configure(bg=FUNDO)
        janela.resizable(False, False)
        faixa = tk.Frame(janela, bg=VERDE, height=6)
        faixa.pack(fill="x")
        tk.Label(janela, text=mensagem(nome), bg=FUNDO, fg=TEXTO,
                 font=("Segoe UI", 11), wraplength=460, justify="left",
                 anchor="w", padx=24, pady=(18)).pack(fill="x")
        tk.Label(janela, text=LINHA_FECHAR, bg=FUNDO, fg="#5F6B76",
                 font=("Segoe UI", 9), wraplength=460, justify="left",
                 anchor="w", padx=24).pack(fill="x")
        if extra:
            tk.Label(janela, text=extra, bg=FUNDO, fg="#B54708",
                     font=("Segoe UI", 10, "bold"), wraplength=460,
                     justify="left", anchor="w", padx=24,
                     pady=6).pack(fill="x")
        botoes = tk.Frame(janela, bg=FUNDO, padx=24, pady=(0))
        botoes.pack(fill="x", pady=(12, 18))
        cancelar = tk.Button(botoes, text="Cancelar", width=12,
                             font=("Segoe UI", 10), relief="groove",
                             command=lambda: fim("cancelar"))
        cancelar.pack(side="right", padx=(8, 0))
        continuar = tk.Button(botoes, text="Continuar", width=12,
                              font=("Segoe UI", 10, "bold"), bg=VERDE,
                              fg="white", activebackground=VERDE,
                              activeforeground="white", relief="flat",
                              command=lambda: fim("continuar"))
        continuar.pack(side="right")
        fechar = tk.Button(botoes, text="Salvar e fechar", width=14,
                           font=("Segoe UI", 10), relief="groove",
                           command=lambda: fim("fechar"))
        fechar.pack(side="right", padx=(0, 8))
        janela.protocol("WM_DELETE_WINDOW", lambda: fim("cancelar"))
        janela.bind("<Return>", lambda _e: fim("continuar"))
        janela.bind("<Escape>", lambda _e: fim("cancelar"))
        janela.update_idletasks()
        w, h = janela.winfo_reqwidth(), janela.winfo_reqheight()
        x = (janela.winfo_screenwidth() - w) // 2
        y = (janela.winfo_screenheight() - h) // 3
        janela.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        janela.attributes("-topmost", True)
        janela.lift()
        janela.focus_force()
        continuar.focus_set()
        try:
            janela.bell()
        except Exception:                               # noqa: BLE001
            pass
        if espera and espera > 0:
            janela.after(int(espera * 1000), lambda: fim("tempo"))
        janela.wait_window()
    except Exception:                                   # noqa: BLE001
        resposta["v"] = "sem_tela"
        try:
            janela.destroy()
        except Exception:                               # noqa: BLE001
            pass
    finally:
        if raiz is not None:
            try:
                raiz.destroy()
            except Exception:                           # noqa: BLE001
                pass
    return resposta["v"]


def aguardar_livre(caminho, passo: str = "", log=None,
                   espera: float | None = None, verificar=None,
                   pergunta=None, cancelar_interrompe: bool = True) -> str:
    """
    "livre" se o arquivo nao esta (ou deixou de estar) em uso; "pular" se o
    aviso fechou sozinho ou nao havia tela. Cancelar levanta Cancelado (com
    cancelar_interrompe=False - fora de uma rodada do robo - vira "pular").
    `verificar(caminho) -> bool` e `pergunta(nome, espera) -> str` podem ser
    trocados (testes; a TABELA_BAP usa a conferencia do armazenamento).
    """
    caminho = Path(caminho)
    verificar = verificar or em_uso
    pergunta = pergunta or perguntar
    espera = ESPERA_POPUP_ARQUIVO if espera is None else espera
    if not verificar(caminho):
        return "livre"
    vezes = 0
    extra = None
    while True:
        vezes += 1
        if log:
            log.warning("%s em aberto%s: aguardando no aviso (Salvar e fechar"
                        " / Continuar / Cancelar)%s.", caminho.name,
                        f" ({passo})" if passo else "",
                        f" - {vezes}a vez" if vezes > 1 else "")
        r = pergunta(caminho.name, espera, *([extra] if extra else []))
        extra = None
        if r == "fechar":
            res = salvar_e_fechar(caminho, log=log, verificar=verificar)
            if res["livre"]:
                if log:
                    log.info("%s livre depois do Salvar e fechar: seguindo.",
                             caminho.name)
                return "livre"
            extra = res["mensagem"]
            continue
        if r == "cancelar":
            if not cancelar_interrompe:
                if log:
                    log.warning("Cancelado no aviso: %s nao foi feito com o "
                                "%s em aberto.", passo or "o passo",
                                caminho.name)
                return "pular"
            raise Cancelado(caminho.name)
        if r in ("tempo", "sem_tela"):
            if log:
                log.warning(
                    "%s continua em aberto e %s: PULEI %s nesta rodada.",
                    caminho.name,
                    ("ninguem respondeu o aviso em " + (
                        f"{round(espera / 60)} min" if espera >= 60
                        else f"{round(espera)} s"))
                    if r == "tempo" else "nao ha tela para mostrar o aviso",
                    passo or "o passo")
            return "pular"
        if not verificar(caminho):
            if log:
                log.info("%s livre: seguindo.", caminho.name)
            return "livre"


# =============================================================================
# "SALVAR E FECHAR" (05/11)
# =============================================================================
# Trocaveis nos testes (a nuvem nao tem Windows nem Excel)
WINDOWS = os.name == "nt"
ESPERA_COM = 30          # segundos: Excel travado num dialogo nao prende o robo
ESPERA_SOLTAR = 2.0      # segundos depois do taskkill (o Windows solta o arquivo)


def _normal(caminho) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(caminho)))
                            ).lower()


def _mesmo_arquivo(full_name: str, alvo: Path) -> bool:
    """O FullName do Excel e este arquivo? Caminho local: igual sem
    diferenciar maiuscula. Arquivo do OneDrive aberto pela nuvem (o FullName
    vira https://...): a pasta e o nome do arquivo no fim da URL."""
    if not full_name:
        return False
    if full_name.lower().startswith(("http://", "https://")):
        from urllib.parse import unquote                # noqa: PLC0415
        fim = unquote(full_name).replace("\\", "/").rstrip("/").split("/")
        return [x.lower() for x in fim[-2:]] == \
            [alvo.parent.name.lower(), alvo.name.lower()]
    return _normal(full_name) == _normal(alvo)


def _livros_no_com(alvo: Path, log=None) -> list:
    """Os livros abertos com este arquivo em QUALQUER Excel desta maquina:
    a tabela de objetos em execucao (ROT, onde cada livro aberto se
    registra) e o Excel ativo. (Nao usa GetObject(caminho): com o arquivo
    fechado ele ABRIRIA o arquivo num Excel novo.)"""
    import pythoncom                                    # noqa: PLC0415
    import win32com.client as wc                        # noqa: PLC0415
    achados, vistos = [], set()

    def guardar(wb):
        try:
            chave = (int(wb.Application.Hwnd), str(wb.FullName).lower())
        except Exception:                               # noqa: BLE001
            chave = (id(wb), "")
        if chave not in vistos:
            vistos.add(chave)
            achados.append(wb)

    try:
        rot = pythoncom.GetRunningObjectTable()
        ctx = pythoncom.CreateBindCtx(0)
        for mk in rot.EnumRunning():
            try:
                nome = mk.GetDisplayName(ctx, None)
            except Exception:                           # noqa: BLE001
                continue
            if not _mesmo_arquivo(nome, alvo):
                continue
            try:
                obj = rot.GetObject(mk)
                wb = wc.Dispatch(obj.QueryInterface(pythoncom.IID_IDispatch))
                guardar(wb)
            except Exception as erro:                   # noqa: BLE001
                if log:
                    log.warning("  Salvar e fechar: livro na ROT nao "
                                "respondeu (%s)", erro)
    except Exception as erro:                           # noqa: BLE001
        if log:
            log.warning("  Salvar e fechar: nao li a ROT (%s)", erro)
    try:
        app = wc.GetActiveObject("Excel.Application")
        for wb in list(app.Workbooks):
            if _mesmo_arquivo(str(wb.FullName), alvo):
                guardar(wb)
    except Exception:                                   # noqa: BLE001
        pass                                            # nenhum Excel ativo
    return achados


def _fechar_pelo_com(alvo: Path, log=None) -> dict:
    """a) Salva e fecha o livro em cada Excel que o tenha aberto. Fecha o
    Excel so se ele ficou SEM livro nenhum e e invisivel."""
    res = {"livros": 0, "fechados": 0, "excel_encerrados": 0, "erro": ""}
    try:
        import pythoncom                                # noqa: PLC0415
        pythoncom.CoInitialize()
    except Exception as erro:                           # noqa: BLE001
        res["erro"] = f"sem pywin32 ({erro})"
        return res
    try:
        livros = _livros_no_com(alvo, log)
        res["livros"] = len(livros)
        for wb in livros:
            try:
                app = wb.Application
                try:
                    wb.Save()
                except Exception as erro:               # noqa: BLE001
                    if log:
                        log.warning("  Salvar e fechar: o Excel nao salvou "
                                    "%s (%s)", alvo.name, erro)
                # (05/11, revisor) so fecha o que esta SALVO: livro com
                # alteracao que nao foi gravada (somente leitura, disco,
                # dialogo...) nunca e fechado - a edicao da pessoa ficaria
                # para tras
                try:
                    salvo = bool(wb.Saved)
                except Exception:                       # noqa: BLE001
                    salvo = False
                if not salvo:
                    res["nao_salvou"] = True
                    if log:
                        log.warning("  Salvar e fechar: %s tem alteracao "
                                    "que nao foi salva - NAO fechei.",
                                    alvo.name)
                    continue
                wb.Close(SaveChanges=False)
                res["fechados"] += 1
                if log:
                    log.warning("  Salvar e fechar: %s salvo e fechado no "
                                "Excel.", alvo.name)
                try:
                    if int(app.Workbooks.Count) == 0 and not bool(app.Visible):
                        app.Quit()
                        res["excel_encerrados"] += 1
                        if log:
                            log.warning("  Salvar e fechar: o Excel invisivel "
                                        "que ficou sem livro foi fechado.")
                except Exception:                       # noqa: BLE001
                    pass
            except Exception as erro:                   # noqa: BLE001
                if log:
                    log.warning("  Salvar e fechar: nao fechei pelo COM (%s)",
                                erro)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:                               # noqa: BLE001
            pass
    return res


def _com_com_espera(alvo: Path, log=None) -> dict:
    """O passo do COM numa linha separada: um Excel parado num dialogo
    prenderia o robo para sempre - passou de ESPERA_COM, segue sem ele."""
    import threading                                    # noqa: PLC0415
    saida = {}

    def rodar():
        try:
            saida.update(_fechar_pelo_com(alvo, log))
        except Exception as erro:                       # noqa: BLE001
            saida["erro"] = str(erro)

    t = threading.Thread(target=rodar, daemon=True)
    t.start()
    t.join(ESPERA_COM)
    if t.is_alive():
        if log:
            log.warning("  Salvar e fechar: o Excel nao respondeu em %d s "
                        "(parado num dialogo?)", ESPERA_COM)
        return {"erro": "Excel sem resposta"}
    return saida


def _sessao_do_robo():
    """A sessao do Windows deste processo (None = nao deu para saber)."""
    try:
        import ctypes                                   # noqa: PLC0415
        sessao = ctypes.c_ulong()
        if ctypes.windll.kernel32.ProcessIdToSessionId(
                os.getpid(), ctypes.byref(sessao)):
            return int(sessao.value)
    except Exception:                                   # noqa: BLE001
        pass
    return None


def _rodar(cmd, timeout=30):
    import subprocess                                   # noqa: PLC0415
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout,
                          creationflags=getattr(subprocess,
                                                "CREATE_NO_WINDOW", 0))


def _excel_da_sessao(sessao: int) -> list:
    """Os PIDs de EXCEL.EXE SO desta sessao do Windows (o Excel de outro
    usuario logado na maquina fica de fora)."""
    import csv as _csv                                  # noqa: PLC0415
    r = _rodar(["tasklist", "/fo", "csv", "/nh", "/fi",
                "IMAGENAME eq EXCEL.EXE", "/fi", f"SESSION eq {sessao}"])
    pids = []
    for linha in _csv.reader((r.stdout or "").splitlines()):
        if len(linha) >= 2 and linha[0].lower() == "excel.exe":
            try:
                pids.append(int(linha[1]))
            except ValueError:
                pass
    return pids


def _linhas_de_comando():
    """{pid: linha de comando} dos EXCEL.EXE (None = nao deu para ler)."""
    cmd_ps = ("Get-CimInstance Win32_Process -Filter \"Name='EXCEL.EXE'\" "
              "| ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        r = _rodar(["powershell", "-NoProfile", "-NonInteractive",
                    "-Command", cmd_ps], timeout=60)
        if r.returncode == 0:
            saida = {}
            for linha in (r.stdout or "").splitlines():
                pid, _, cmd = linha.partition("\t")
                if pid.strip().isdigit():
                    saida[int(pid)] = cmd.strip()
            return saida
    except Exception:                                   # noqa: BLE001
        pass
    return None


def _automacao(cmd: str) -> bool:
    """Excel aberto por programa (DispatchEx/COM): /automation -Embedding."""
    c = (cmd or "").lower()
    return "/automation" in c or "-embedding" in c


def _listar_excel():
    """(candidatos a encerrar, pids com janela, motivo) - SO da sessao do
    robo. Candidato: sem janela visivel E (quando da para ler a linha de
    comando) aberto por automacao. Sem pywin32 ou sem saber a sessao:
    nenhum candidato."""
    sessao = _sessao_do_robo()
    if sessao is None:
        return [], [], "sessao desconhecida"
    try:
        import win32gui                                 # noqa: PLC0415
        import win32process                             # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return [], [], "sem pywin32"
    pids = _excel_da_sessao(sessao)
    visiveis = set()

    def ver(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            visiveis.add(win32process.GetWindowThreadProcessId(hwnd)[1])
        return True
    win32gui.EnumWindows(ver, None)
    comandos = _linhas_de_comando()
    candidatos, com_janela = [], []
    for pid in pids:
        if pid in visiveis:
            com_janela.append(pid)
        elif comandos is None or pid not in comandos:
            candidatos.append(pid)          # sem janela + mesma sessao
        elif _automacao(comandos[pid]):
            candidatos.append(pid)          # sem janela + automacao
    return candidatos, com_janela, ("" if comandos is not None
                                    else "sem linha de comando")


def _matar(pid: int) -> bool:
    import subprocess                                   # noqa: PLC0415
    r = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW",
                                             0))
    return r.returncode == 0


def salvar_e_fechar(caminho, log=None, verificar=None) -> dict:
    """
    O botao "Salvar e fechar". Para assim que o arquivo fica livre:
      a) COM: salva e fecha o livro no Excel (fecha o Excel so se ficou vazio
         e invisivel);
      b) ainda travado: encerra os EXCEL.EXE SEM janela visivel (os de
         recalculo que sobraram). Excel com janela nunca;
      c) apaga o ~$ solto e confere de novo.
    Devolve {"livre": bool, "mensagem": recado para o aviso, "passos": [...]}.
    """
    alvo = Path(caminho).resolve()
    verificar = verificar or em_uso
    passos = []

    def livre():
        return not verificar(alvo)

    if not WINDOWS:
        if log:
            log.warning("Salvar e fechar: so no Windows.")
        return {"livre": livre(), "mensagem": MSG_SEM_SUPORTE,
                "passos": ["sem_windows"]}
    if log:
        log.warning("Salvar e fechar: %s", alvo)
    # a) pelo COM
    com = _com_com_espera(alvo, log)
    passos.append(("com", com))
    sem_pywin32 = "pywin32" in str(com.get("erro", ""))
    if com.get("fechados") and livre():
        apagar_dono_solto(alvo)
        return {"livre": True, "mensagem": "", "passos": passos}
    if com.get("nao_salvou"):
        # um livro com alteracao nao gravada: nao fecha e nao encerra nada
        msg = msg_nao_salvou(alvo.name)
        if log:
            log.warning("  Salvar e fechar: %s", msg)
        return {"livre": False, "mensagem": msg, "passos": passos}
    # b) Excel de automacao (sem janela, desta sessao) segurando
    try:
        invisiveis, visiveis, motivo = _listar_excel()
    except Exception as erro:                           # noqa: BLE001
        invisiveis, visiveis, motivo = [], [], str(erro)
    if motivo and log:
        log.warning("  Salvar e fechar: Excel em segundo plano %s (%s).",
                    "so os sem janela desta sessao" if motivo ==
                    "sem linha de comando" else "NAO encerrado", motivo)
    if motivo == "sem pywin32":
        sem_pywin32 = True
    mortos = [pid for pid in invisiveis if _matar(pid)]
    passos.append(("excel_sem_janela", mortos))
    if log:
        log.warning("  Salvar e fechar: Excel sem janela encerrado(s): %s%s",
                    ", ".join(map(str, mortos)) or "nenhum",
                    f" | Excel com janela (nao mexo): "
                    f"{', '.join(map(str, visiveis))}" if visiveis else "")
    if mortos:
        time.sleep(ESPERA_SOLTAR)
    # c) o ~$ solto e a conferencia
    if apagar_dono_solto(alvo) and log:
        log.warning("  Salvar e fechar: ~$%s solto apagado.", alvo.name)
    if livre():
        return {"livre": True, "mensagem": "", "passos": passos}
    # d) continua travado
    if visiveis:
        msg = MSG_EXCEL_VISIVEL
    elif sem_pywin32 and not mortos:
        msg = MSG_SEM_SUPORTE
    else:
        msg = MSG_OUTRO_PROGRAMA
    if log:
        log.warning("  Salvar e fechar: %s continua em uso - %s", alvo.name,
                    msg)
    return {"livre": False, "mensagem": msg, "passos": passos}
