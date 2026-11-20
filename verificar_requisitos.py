# -*- coding: utf-8 -*-
"""
Scan de requisitos do BAP Tools e do Planner BAP.

Roda com o Python "pelado": nao importa nada que possa faltar. Escreve o
relatorio na tela e no arquivo DIAGNOSTICO_BAP.txt, ao lado deste script.

    python verificar_requisitos.py

Ou clique duas vezes em VERIFICAR_REQUISITOS.bat.
"""
import datetime as dt
import os
import platform
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
import traceback
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RELATORIO = AQUI / "DIAGNOSTICO_BAP.txt"

# atributos do Windows que denunciam arquivo "so na nuvem" (OneDrive)
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000

linhas = []
problemas = []
avisos = []


def diz(texto=""):
    print(texto)
    linhas.append(texto)


def titulo(texto):
    diz()
    diz("=" * 72)
    diz(f" {texto}")
    diz("=" * 72)


def item(rotulo, valor, estado=""):
    marca = {"ok": "[ OK ]", "erro": "[FALTA]", "aviso": "[AVISO]"}.get(estado, "      ")
    diz(f" {marca} {rotulo:<34} {valor}")


def falha(texto):
    problemas.append(texto)


def aviso(texto):
    avisos.append(texto)


def rodar(comando, tempo=25):
    """Roda um comando e devolve (codigo, saida). Nunca levanta excecao."""
    try:
        r = subprocess.run(comando, capture_output=True, text=True,
                           timeout=tempo, shell=False,
                           encoding="utf-8", errors="replace")
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as erro:                          # noqa: BLE001
        return -1, f"{type(erro).__name__}: {erro}"


# ==========================================================================
def secao_maquina():
    titulo("1. MAQUINA")
    item("Data do scan", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
    item("Computador", platform.node())
    item("Usuario", os.environ.get("USERNAME") or os.environ.get("USER") or "?")
    item("Sistema", f"{platform.system()} {platform.release()} "
                    f"({platform.version()})")
    item("Arquitetura", platform.machine())
    try:
        total, usado, livre = shutil.disk_usage(AQUI)
        estado = "ok" if livre > 2 * 1024**3 else "aviso"
        item("Espaco livre no disco", f"{livre / 1024**3:.1f} GB de "
                                      f"{total / 1024**3:.1f} GB", estado)
        if estado == "aviso":
            aviso("Menos de 2 GB livres no disco.")
    except OSError as erro:
        item("Espaco livre no disco", f"nao consegui medir ({erro})", "aviso")


def secao_python():
    titulo("2. PYTHON")
    item("Python rodando este scan", sys.version.split()[0], "ok")
    item("Executavel", sys.executable)
    versao = sys.version_info
    if versao < (3, 10):
        item("Versao minima (3.10)", f"tem {versao.major}.{versao.minor}", "erro")
        falha(f"Python {versao.major}.{versao.minor} e antigo demais. "
              f"Instale o 3.11 ou mais novo.")
    else:
        item("Versao minima (3.10)", "atende", "ok")

    diz()
    diz(" Todos os Python que achei neste computador:")
    achados = []
    for comando in (["py", "-0p"], ["where", "python"], ["where", "pythonw"],
                    ["where", "py"]):
        codigo, saida = rodar(comando)
        if codigo == 0 and saida:
            diz(f"   $ {' '.join(comando)}")
            for l in saida.splitlines():
                l = l.strip()
                if l:
                    diz(f"       {l}")
                    achados.append(l)

    # o atalho da Microsoft Store finge ser python.exe e nao roda nada
    for a in achados:
        if "WindowsApps" in a and a.lower().endswith(("python.exe", "python3.exe")):
            item("Atalho da Microsoft Store", "encontrado no PATH", "aviso")
            aviso("Existe um 'python.exe' de atalho da Microsoft Store no PATH "
                  "(pasta WindowsApps). Ele nao roda nada: abre a loja. Se o "
                  ".bat encontrar esse antes do Python de verdade, o programa "
                  "some sem mensagem. Desligue em: Configuracoes > Aplicativos "
                  "> Configuracoes avancadas de aplicativo > Aliases de "
                  "execucao de aplicativo > desmarque python.exe e python3.exe.")
            break

    codigo, saida = rodar([sys.executable, "-m", "pip", "--version"])
    if codigo == 0:
        item("pip", saida.split(" (")[0], "ok")
    else:
        item("pip", "nao respondeu", "erro")
        falha("O pip nao funciona neste Python. Sem ele nao da para instalar "
              "as bibliotecas. Reinstale o Python marcando 'pip'.")


MODULOS_PLANNER = [
    ("tkinter", "a janela do Planner", "vem junto com o Python "
     "(no instalador, marque 'tcl/tk and IDLE')"),
    ("openpyxl", "ler e gravar Excel", "pip install openpyxl"),
]
MODULOS_AUTOMATION = [
    ("pandas", "tratar as tabelas", "pip install pandas"),
    ("openpyxl", "ler e gravar Excel", "pip install openpyxl"),
    ("xlrd", "ler xls antigo", "pip install xlrd"),
    ("requests", "falar com o SharePoint", "pip install requests"),
    ("msal", "login da Microsoft", "pip install msal"),
    ("keyring", "guardar o login", "pip install keyring"),
    ("playwright", "baixar os relatorios", "pip install playwright"),
]
MODULOS_OPCIONAIS = [
    ("win32com.client", "recalcular no Excel (pywin32)", "pip install pywin32"),
    ("reportlab", "exportar relatorio em PDF (BAP Central)",
     "rode o INSTALAR_PDF.bat (ou pip install reportlab)"),
]


def testar_modulo(nome):
    codigo, saida = rodar([sys.executable, "-c",
                           f"import {nome}; "
                           f"print(getattr({nome.split('.')[0]}, "
                           f"'__version__', 'ok'))"])
    return (codigo == 0), saida.splitlines()[-1] if saida else ""


def secao_bibliotecas():
    titulo("3. BIBLIOTECAS")
    diz(" --- Planner BAP (o minimo para a janela abrir) ---")
    faltando_rot = []
    for nome, para_que, como in MODULOS_PLANNER:
        ok, versao = testar_modulo(nome)
        item(f"{nome}  ({para_que})", versao if ok else "NAO INSTALADO",
             "ok" if ok else "erro")
        if not ok:
            faltando_rot.append((nome, como))
    if faltando_rot:
        falha("O Planner NAO vai abrir. Falta: "
              + ", ".join(n for n, _ in faltando_rot)
              + ". Resolva com: " + " ; ".join(c for _, c in faltando_rot))

    diz()
    diz(" --- BAP Automation (a rotina de solicitacao e preco) ---")
    faltando_aut = []
    for nome, para_que, como in MODULOS_AUTOMATION:
        ok, versao = testar_modulo(nome)
        item(f"{nome}  ({para_que})", versao if ok else "NAO INSTALADO",
             "ok" if ok else "erro")
        if not ok:
            faltando_aut.append((nome, como))
    if faltando_aut:
        falha("O BAP Automation nao roda completo. Falta: "
              + ", ".join(n for n, _ in faltando_aut))

    diz()
    diz(" --- Opcionais ---")
    for nome, para_que, como in MODULOS_OPCIONAIS:
        ok, versao = testar_modulo(nome)
        item(f"{nome}  ({para_que})", versao if ok else "nao instalado",
             "ok" if ok else "aviso")
        if not ok:
            aviso(f"{nome} nao esta instalado ({para_que}). "
                  f"Se precisar: {como}")

    ok, _ = testar_modulo("playwright")
    if ok:
        codigo, saida = rodar([sys.executable, "-c",
                               "from playwright.sync_api import sync_playwright\n"
                               "with sync_playwright() as p:\n"
                               "    print(p.chromium.executable_path)"], 40)
        if codigo == 0 and saida:
            caminho = saida.splitlines()[-1].strip()
            existe = Path(caminho).exists() if caminho else False
            item("Navegador do playwright", caminho if existe else
                 "instalado o pacote, mas falta o navegador",
                 "ok" if existe else "erro")
            if not existe:
                falha("Falta baixar o navegador do playwright. "
                      "Rode: playwright install chromium")
        else:
            item("Navegador do playwright", "nao consegui verificar", "aviso")


ARQUIVOS_ESPERADOS = [
    ("bap_planner.py", True, "a janela do Planner"),
    ("planner_nucleo.py", True, "o motor da roteirizacao"),
    ("pastas_bap.py", True, "o desenho da pasta (RELATORIOS e os backups)"),
    ("COORDENADAS_CIDADES_BAIRRO_BAP.xlsx", False,
     "a coordenada de cada cidade e de cada bairro (a rota fica mais curta)"),
    ("CATEGORIAS_PRODUTO.csv", False,
     "a categoria de cada produto (pecas, bateria, lubrificante, pneu)"),
    ("bap_meta.py", False, "o Gerador de Meta (a tela)"),
    ("meta_nucleo.py", False, "o Gerador de Meta (a conta)"),
    ("zonas_padrao.py", True, "o desenho inicial das zonas"),
    ("xlsx_rapido.py", False, "a leitura rapida das planilhas (com cache)"),
    ("base_cliente.py", True, "gera a BASE_CLIENTE"),
    ("bap_automation.py", False, "a rotina do BAP Tools"),
    ("dados_bap.py", False, "a fotografia da TABELA_BAP e as formulas em Python (o robo precisa)"),
    ("aviso_arquivo.py", False, "o aviso de arquivo em aberto (Continuar / Cancelar) do robo"),
    ("TABELA_BAP.xlsx", False, "a base que alimenta tudo"),
    ("BASE_CLIENTE.xlsx", False, "a base do Planner"),
    ("planner_config.json", False, "SUAS zonas e vendedores"),
    ("planner_pastas.json", False, "os caminhos"),
]


def descrever_arquivo(p: Path):
    try:
        st = p.stat()
    except OSError as erro:
        return f"erro ao ler ({erro})", "erro"
    tamanho = st.st_size
    quando = dt.datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")
    atributos = getattr(st, "st_file_attributes", 0)
    so_na_nuvem = bool(atributos & (FILE_ATTRIBUTE_OFFLINE
                                    | FILE_ATTRIBUTE_RECALL_ON_OPEN
                                    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS))
    texto = f"{tamanho / 1024:>10,.0f} KB   {quando}"
    if so_na_nuvem:
        return texto + "   *** SO NA NUVEM ***", "aviso"
    return texto, "ok"


def secao_pasta():
    titulo("4. PASTA DE TRABALHO")
    diz(f" {AQUI}")
    diz()
    na_nuvem = []
    for nome, obrigatorio, para_que in ARQUIVOS_ESPERADOS:
        p = AQUI / nome
        if not p.exists():
            item(nome, "NAO ESTA NESTA PASTA",
                 "erro" if obrigatorio else "aviso")
            if obrigatorio:
                falha(f"Falta o arquivo {nome} ({para_que}) nesta pasta.")
            continue
        texto, estado = descrever_arquivo(p)
        item(nome, texto, estado)
        if "SO NA NUVEM" in texto:
            na_nuvem.append(nome)
    if na_nuvem:
        falha("Estes arquivos estao marcados como 'disponivel somente online' "
              "pelo OneDrive: " + ", ".join(na_nuvem) + ". Num notebook novo "
              "isso e comum e QUEBRA a leitura. Clique com o botao direito na "
              "pasta > 'Sempre manter neste dispositivo'.")

    # a pasta e dentro do OneDrive?
    caminho = str(AQUI).lower()
    if "onedrive" in caminho:
        item("Pasta dentro do OneDrive", "sim", "ok")
        codigo, saida = rodar(["powershell", "-NoProfile", "-Command",
                               "(Get-Process OneDrive -ErrorAction "
                               "SilentlyContinue | Measure-Object).Count"])
        if codigo == 0 and saida.strip().isdigit():
            n = int(saida.strip())
            item("OneDrive rodando", "sim" if n else "NAO", "ok" if n else "aviso")
            if not n:
                aviso("O OneDrive nao esta rodando. Os arquivos podem estar "
                      "desatualizados em relacao a outra maquina.")
    else:
        item("Pasta dentro do OneDrive", "nao", "aviso")

    # da para gravar aqui?
    teste = AQUI / "_teste_de_escrita.tmp"
    try:
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
        item("Permissao de gravacao", "pode gravar nesta pasta", "ok")
    except OSError as erro:
        item("Permissao de gravacao", f"NAO PODE GRAVAR ({erro})", "erro")
        falha("Nao consigo gravar nesta pasta. O programa nao vai conseguir "
              "salvar a configuracao nem a rota.")


def secao_abrir():
    """A prova real: importa o Planner e mostra o erro de verdade."""
    titulo("5. TESTE DE ABERTURA DO PLANNER")
    if not (AQUI / "bap_planner.py").exists():
        item("Importar bap_planner", "arquivo nao esta na pasta", "erro")
        return
    codigo, saida = rodar([sys.executable, "-c",
                           "import sys; sys.path.insert(0, r'%s')\n"
                           "import bap_planner\n"
                           "print('IMPORTOU')" % str(AQUI)], 60)
    if codigo == 0 and "IMPORTOU" in saida:
        item("Importar bap_planner", "sem erro", "ok")
    else:
        item("Importar bap_planner", "FALHOU", "erro")
        diz()
        diz(" ---- erro de verdade que estava sendo escondido ----")
        for l in saida.splitlines():
            diz(f"   {l}")
        diz(" ----------------------------------------------------")
        falha("O Planner nao consegue nem ser carregado. O erro acima e "
              "o motivo de o .bat abrir e fechar sem mostrar nada.")
        return

    # abre a janela de verdade por 1 segundo e fecha
    codigo, saida = rodar([sys.executable, "-c",
                           "import sys; sys.path.insert(0, r'%s')\n"
                           "import bap_planner as ap\n"
                           "a = ap.App()\n"
                           "a.after(1200, a.destroy)\n"
                           "a.mainloop()\n"
                           "print('JANELA ABRIU E FECHOU')" % str(AQUI)], 90)
    if codigo == 0 and "JANELA ABRIU" in saida:
        item("Abrir a janela", "abriu normalmente", "ok")
    else:
        item("Abrir a janela", "FALHOU", "erro")
        diz()
        diz(" ---- erro ao montar a janela ----")
        for l in saida.splitlines():
            diz(f"   {l}")
        diz(" ---------------------------------")
        falha("A janela nao monta. Veja o erro acima.")


def secao_extras():
    titulo("6. EXTRAS DO BAP AUTOMATION")
    codigo, saida = rodar(["powershell", "-NoProfile", "-Command",
                           "$PSVersionTable.PSVersion.ToString()"])
    if codigo == 0 and saida.strip():
        item("PowerShell", saida.strip().splitlines()[-1], "ok")
    else:
        item("PowerShell", "nao respondeu", "aviso")

    codigo, saida = rodar(["powershell", "-NoProfile", "-Command",
                           "if (Get-Module -ListAvailable -Name "
                           "MicrosoftPowerBIMgmt) { 'sim' } else { 'nao' }"], 60)
    if codigo == 0 and "sim" in saida.lower():
        item("Modulo MicrosoftPowerBIMgmt", "instalado", "ok")
    else:
        item("Modulo MicrosoftPowerBIMgmt", "nao instalado", "aviso")
        aviso("Falta o modulo do Power BI (so precisa se voce for atualizar o "
              "dataset por aqui). Instale com: Install-Module "
              "-Name MicrosoftPowerBIMgmt -Scope CurrentUser")

    codigo, saida = rodar(["schtasks", "/query", "/fo", "LIST"], 40)
    if codigo == 0:
        achou = [l for l in saida.splitlines()
                 if "bap" in l.lower() and "nome" in l.lower()[:12]]
        if achou:
            item("Tarefa agendada do BAP", "; ".join(a.strip() for a in achou[:3]), "ok")
        else:
            item("Tarefa agendada do BAP", "nao encontrei nenhuma", "aviso")
            aviso("Nao ha tarefa agendada do BAP neste computador. Se a rotina "
                  "deve rodar sozinha, recrie a tarefa (tarefa_bap.xml).")
    else:
        item("Tarefa agendada do BAP", "nao consegui consultar", "aviso")

    excel = rodar(["powershell", "-NoProfile", "-Command",
                   "if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Office') "
                   "{ 'sim' } else { 'nao' }"])
    if excel[0] == 0:
        tem = "sim" in excel[1].lower()
        item("Office / Excel instalado", "sim" if tem else "nao encontrado",
             "ok" if tem else "aviso")


def secao_conclusao():
    titulo("RESUMO")
    if not problemas:
        diz(" TUDO CERTO. Os dois programas tem o que precisam para rodar.")
    else:
        diz(f" {len(problemas)} PROBLEMA(S) QUE IMPEDEM DE RODAR:")
        diz()
        for i, p in enumerate(problemas, 1):
            diz(f"   {i}. {p}")
    if avisos:
        diz()
        diz(f" {len(avisos)} aviso(s) - nao impedem, mas vale olhar:")
        diz()
        for i, a in enumerate(avisos, 1):
            diz(f"   {i}. {a}")
    diz()
    diz(" Comando unico que instala tudo o que os dois programas usam:")
    diz()
    diz(f'   "{sys.executable}" -m pip install --upgrade pip')
    diz(f'   "{sys.executable}" -m pip install openpyxl pandas xlrd requests '
        f'msal keyring playwright pywin32 reportlab')
    diz(f'   "{sys.executable}" -m playwright install chromium')
    diz()
    diz(f" Este relatorio foi salvo em: {RELATORIO}")
    diz(" Mande esse arquivo para mim que eu digo exatamente o que fazer.")


def main():
    diz()
    diz("#" * 72)
    diz("#  SCAN DE REQUISITOS - BAP TOOLS + PLANNER BAP")
    diz("#" * 72)
    for secao in (secao_maquina, secao_python, secao_bibliotecas,
                  secao_pasta, secao_abrir, secao_extras):
        try:
            secao()
        except Exception:                              # noqa: BLE001
            titulo(f"ERRO INESPERADO EM {secao.__name__}")
            for l in traceback.format_exc().splitlines():
                diz(f"   {l}")
            falha(f"O proprio scan falhou em {secao.__name__} - me mande o "
                  f"relatorio.")
    secao_conclusao()
    try:
        RELATORIO.write_text("\n".join(linhas), encoding="utf-8")
    except OSError as erro:
        print(f"\nNao consegui gravar o relatorio: {erro}")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
