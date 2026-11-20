# -*- coding: utf-8 -*-
"""
O DESENHO DA PASTA BAP - um lugar so onde ele esta escrito.

A pasta de trabalho (a "Regionais - Leandro", no OneDrive) tinha 40 arquivos
soltos na raiz. Este modulo define o desenho novo e sabe arrumar a pasta
sozinho, sem apagar nada:

    <a pasta>\\
        RELATORIOS\\                      os Excel do dia a dia, os ATUAIS
            Visitas\\                     um CSV por mes: 202609.csv
            TABELA_BAP.xlsx
            SOLICITACAO_BAP.xlsx
            ESTOQUE_BAP.xlsx
            BASE_CLIENTE.xlsx
            ALTERACOES_PRECO.xlsx
            Roteirizacao\\                (20/10) tudo o que o Planner exporta:
                                          PLANNER_BAP_<mes>_<data>.xlsx (so o
                                          do mes vigente), ROTA_PROTHEUS_*.json,
                                          BASE_CLIENTES_PROTHEUS_*.json,
                                          EQUIPE_BAP_<mes>.xlsx,
                                          AGENDA_CIDADES_<mes>.xlsx
        BACKUP_RELATORIOS\\               o guarda-chuva de tudo que e copia
            BKP_RELATORIOS_BAPTOOLS\\     os relatorios baixados do BAP Tools
            BKP_RELATORIOS_PRECO\\        historico_precos + copias do
                                          ALTERACOES_PRECO
            BKP_RELATORIOS_AUXILIARES\\   copias da TABELA_BAP, do ESTOQUE_BAP
                                          e a base unificada de produtos
            BKP_RELATORIOS_PLANNER\\      PLANNER e BASE_CLIENTE antigos
        Arquivos para Importar\\          os CSV de importacao
        PLANNER_MESES\\                   a configuracao do Planner, mes a mes
        cards\\  evidencias\\  logs\\  auth\\
        (os .py e os .bat)

REGRAS QUE VALEM PARA SEMPRE
  - nada de caminho absoluto: tudo sai da pasta onde o programa esta, para a
    pasta poder ser movida de micro, de OneDrive ou de lugar;
  - arrumar a pasta MOVE, nunca apaga. Se ja houver um arquivo com o mesmo
    nome no destino, o que estava na raiz vira "<nome> (da raiz).xlsx";
  - a arrumacao roda toda vez que qualquer um dos programas abre, e nao faz
    nada quando ja esta tudo no lugar.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

# --------------------------------------------------------------------------
# os nomes das pastas - mude aqui e muda em todo lugar
# --------------------------------------------------------------------------
RELATORIOS = "RELATORIOS"
# (29/10, Alexandre: "o minimo de pasta possivel") tudo o que e do PROGRAMA
# (copias, configuracao do mes, logs, login, imagens, CSV de importacao, cache
# do CNAE) mora numa pasta so, a SISTEMA BAP. Na raiz ficam RELATORIOS,
# DOCUMENTOS BAP, SISTEMA BAP, ARQUIVO MORTO (e as pastas dos apps parceiros).
SISTEMA = "SISTEMA BAP"
BACKUP = f"{SISTEMA}/BACKUP_RELATORIOS"

# AS VISITAS FEITAS, um CSV por mes com o nome AAAAMM (202609.csv). E de
# la que o Gerador de Meta tira o REAL da meta de visita.
VISITAS = f"{RELATORIOS}/Visitas"
# a mesma coisa do jeito que o Windows escreve, para aparecer na tela
VISITAS_TELA = VISITAS.replace("/", "\\")

# (20/10, Alexandre) A ROTEIRIZACAO: o que o Planner exporta (PLANNER,
# ROTA_PROTHEUS e BASE_CLIENTES_PROTHEUS .json, equipe, agenda das cidades)
# fica junto, numa pasta so. Os antigos que estavam soltos na RELATORIOS (e
# na EXPORTADOS) sao movidos para ca na abertura dos programas.
ROTEIRIZACAO = f"{RELATORIOS}/Roteirizacao"
ROTEIRIZACAO_TELA = ROTEIRIZACAO.replace("/", "\\")

BKP_BAPTOOLS = f"{BACKUP}/BKP_RELATORIOS_BAPTOOLS"
BKP_PRECO = f"{BACKUP}/BKP_RELATORIOS_PRECO"
BKP_AUXILIARES = f"{BACKUP}/BKP_RELATORIOS_AUXILIARES"
BKP_PLANNER = f"{BACKUP}/BKP_RELATORIOS_PLANNER"

# o historico de fotos de preco continua com o nome dele, agora dentro do
# backup de preco
HISTORICO_PRECOS = f"{BKP_PRECO}/historico_precos"

SUBPASTAS = (RELATORIOS, VISITAS, ROTEIRIZACAO, BACKUP, BKP_BAPTOOLS,
             BKP_PRECO, BKP_AUXILIARES, BKP_PLANNER, HISTORICO_PRECOS)

# (20/10) o que e da ROTEIRIZACAO e sai da RELATORIOS (e da EXPORTADOS)
DA_ROTEIRIZACAO = re.compile(
    r"^(PLANNER_BAP.*\.xlsx?|ROTA_PROTHEUS_.*\.json|"
    r"BASE_CLIENTES_PROTHEUS_.*\.json|EQUIPE_BAP_.*\.xlsx?|"
    r"AGENDA_CIDADES_.*\.xlsx?|ROTA_.*\.(xlsx?|html)|"
    r"CLIENTES_FORA_DA_MAXIMA.*\.xlsx?|"
    r"CONFERENCIA_VENDEDOR_PLANNER_X_PROTHEUS.*\.xlsx?)$", re.IGNORECASE)

# --------------------------------------------------------------------------
# quem mora onde
# --------------------------------------------------------------------------
# os arquivos do dia a dia, na RELATORIOS
ATUAIS = ("TABELA_BAP.xlsx", "SOLICITACAO_BAP.xlsx", "ESTOQUE_BAP.xlsx",
          "BASE_CLIENTE.xlsx", "ALTERACOES_PRECO.xlsx")

# as pastas antigas que viraram subpasta do BACKUP_RELATORIOS
PASTAS_ANTIGAS = {
    "SEPARACAO_BAP": BKP_BAPTOOLS,      # nome de duas versoes atras
    "backups": BKP_AUXILIARES,          # copias datadas da TABELA_BAP
    "historico_precos": HISTORICO_PRECOS,
}

# padrao de nome -> onde o arquivo deve ficar. A ordem importa: o primeiro
# que casar manda.
DESTINOS = (
    # o PLANNER e a BASE_CLIENTE do mes: o mais novo fica na RELATORIOS e os
    # anteriores vao para o backup do planner (ver _arrumar_planner)
    (r"^PLANNER_BAP.*\.xlsx?$", BKP_PLANNER),
    (r"^ROTA_.*\.xlsx?$", BKP_PLANNER),
    (r"^BASE_CLIENTE.*\.xlsx?$", BKP_PLANNER),
    # preco
    (r"^ALTERACOES_PRECO_.*\.xlsx?$", BKP_PRECO),
    # auxiliares
    (r"^TABELA_BAP_\d.*\.xlsx?$", BKP_AUXILIARES),
    (r"^ESTOQUE_BAP_\d.*\.xlsx?$", BKP_AUXILIARES),
    (r"^BASE_BAP_UNIFICADA.*\.xlsx?$", BKP_AUXILIARES),
    (r"^BASE.*UNIFICADA.*PRODUTO.*\.xlsx?$", BKP_AUXILIARES),
    # relatorios crus do BAP Tools, que vem com a data no nome
    (r"^BAP.*\d{6,}.*\.(xlsx?|csv|txt)$", BKP_BAPTOOLS),
)

# arquivos que NUNCA se mexe: sao o programa, nao dado
NAO_MEXER = re.compile(
    r"\.(py|bat|ps1|json|txt|md|log|bin|cmd|xml|html)$", re.IGNORECASE)

# As TABELAS DE APOIO ficam na raiz, ao lado dos programas: sao parte do
# programa, nao relatorio do mes. Elas nao entram nem na RELATORIOS nem no
# backup.
#     COORDENADAS_CIDADES_BAIRRO_BAP.xlsx  a coordenada de cada cidade e
#                                          de cada bairro - e o que faz a
#                                          rota andar de vizinho em vizinho
#     CATEGORIAS_PRODUTO.csv               a categoria de cada produto
#                                          (pecas, bateria, lubrificante,
#                                          pneu), para o acompanhamento
#                                          da meta
TABELAS_DE_APOIO = re.compile(
    r"^(COORDENADAS_CIDADES_BAIRRO_BAP|CATEGORIAS_PRODUTO|"
    r"Estoque[ _]Total|ESTOQUE_TOTAL)\.(xlsx?|csv)$", re.IGNORECASE)


# (29/10) as pastas do programa que saem da raiz e vao para a SISTEMA BAP.
# Quem ainda tiver uma delas na raiz (outra maquina com o OneDrive atrasado,
# um .bat antigo que criou "logs") tem o conteudo juntado la, sem escrever
# por cima de nada; a pasta da raiz so some se ficar vazia.
PARA_O_SISTEMA = ("BACKUP_RELATORIOS", "PLANNER_MESES", "Arquivos para Importar",
                  "auth", "cards", "evidencias", "logs", "recursos",
                  "Consulta CNAE")


def _juntar(de: Path, para: Path) -> int:
    """Move o conteudo de 'de' para 'para' sem nunca escrever por cima
    (subpasta que existe dos dois lados: junta por dentro). Devolve quantos
    itens mudaram de lugar; 'de' sai se ficar vazia."""
    para.mkdir(parents=True, exist_ok=True)
    n = 0
    for item in list(de.iterdir()):
        alvo = para / item.name
        try:
            if not alvo.exists():
                shutil.move(str(item), str(alvo))
                n += 1
            elif item.is_dir() and alvo.is_dir():
                n += _juntar(item, alvo)
        except OSError:
            pass
    try:
        de.rmdir()
    except OSError:
        pass
    return n


def para_o_sistema(raiz, anotar=None) -> int:
    """As pastas do programa que ainda estejam na raiz vao para a SISTEMA
    BAP. A pasta inteira muda de lugar quando ainda nao existe la."""
    raiz = Path(raiz)
    total = 0
    for nome in PARA_O_SISTEMA:
        de = raiz / nome
        if not de.is_dir():
            continue
        para = raiz / SISTEMA / nome
        try:
            if not para.exists():
                para.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(de), str(para))
                n = 1
            else:
                n = _juntar(de, para)
        except OSError:
            n = 0
        if n and anotar:
            anotar(f"{nome} -> {SISTEMA}")
        total += n
    return total


def garantir(raiz) -> None:
    """Cria a estrutura de pastas. Idempotente."""
    raiz = Path(raiz)
    for sub in SUBPASTAS:
        (raiz / sub).mkdir(parents=True, exist_ok=True)


def _mover(origem: Path, pasta_destino: Path) -> Path | None:
    """
    Move sem NUNCA escrever por cima. Devolve o destino, ou None se nao deu.
    """
    pasta_destino.mkdir(parents=True, exist_ok=True)
    destino = pasta_destino / origem.name
    if destino.exists():
        # ja existe um la: o da raiz e o duvidoso, entao e ele que ganha
        # sufixo. Nada e apagado nem sobrescrito.
        if destino.stat().st_size == origem.stat().st_size:
            try:
                origem.unlink()          # copia identica: some a duplicata
                return destino
            except OSError:
                return None
        destino = pasta_destino / f"{origem.stem} (da raiz){origem.suffix}"
        n = 2
        while destino.exists():
            destino = pasta_destino / f"{origem.stem} (da raiz {n}){origem.suffix}"
            n += 1
    try:
        shutil.move(str(origem), str(destino))
        return destino
    except OSError:
        return None


def _destino_de(nome: str) -> str | None:
    """A subpasta onde este arquivo deve ficar, ou None se ele fica na raiz."""
    if NAO_MEXER.search(nome) or TABELAS_DE_APOIO.match(nome):
        return None
    if nome in ATUAIS:
        return RELATORIOS
    for padrao, pasta in DESTINOS:
        if re.match(padrao, nome, re.IGNORECASE):
            return pasta
    return None


def _mais_novo(arquivos):
    return max(arquivos, key=lambda p: p.stat().st_mtime) if arquivos else None


def arrumar(raiz, registrar=None) -> list[str]:
    """
    Poe a pasta no desenho novo. Roda em toda abertura dos programas; quando
    ja esta tudo no lugar nao faz nada e nao escreve nada.

    Devolve a lista do que foi movido, em portugues, para o log.
    """
    raiz = Path(raiz)
    feito = []

    def anotar(texto):
        feito.append(texto)
        if registrar:
            registrar(texto)
    # 0) (29/10) as pastas do programa vao para a SISTEMA BAP - antes de
    #    garantir(), para a pasta inteira mudar de lugar de uma vez
    para_o_sistema(raiz, anotar)
    garantir(raiz)

    # 1) as pastas que mudaram de lugar
    for antiga, nova in PASTAS_ANTIGAS.items():
        de = raiz / antiga
        para = raiz / nova
        if not de.is_dir() or de.resolve() == para.resolve():
            continue
        movidos = 0
        for item in list(de.iterdir()):
            alvo = para / item.name
            if alvo.exists():
                continue
            try:
                shutil.move(str(item), str(alvo))
                movidos += 1
            except OSError:
                pass
        if movidos:
            anotar(f"{antiga}: {movidos} arquivo(s) para {nova}")
        try:
            de.rmdir()                    # so sai se ficou vazia
        except OSError:
            pass

    # 2) a BACKUP_RELATORIOS era, ela mesma, a pasta dos relatorios do BAP
    #    Tools. Agora ela e o guarda-chuva: o que estava solto dentro dela
    #    desce para a BKP_RELATORIOS_BAPTOOLS, que e o lugar deles.
    guarda_chuva = raiz / BACKUP
    if guarda_chuva.is_dir():
        desceram = 0
        for item in sorted(guarda_chuva.iterdir()):
            if (not item.is_file() or NAO_MEXER.search(item.name)
                    or TABELAS_DE_APOIO.match(item.name)):
                continue
            sub = _destino_de(item.name)
            # relatorio do BAP Tools nao tem padrao de nome garantido: o que
            # estiver solto aqui e dele, salvo se casar com outra gaveta
            alvo = raiz / (sub if sub and sub != RELATORIOS else BKP_BAPTOOLS)
            if _mover(item, alvo):
                desceram += 1
        if desceram:
            anotar(f"{BACKUP}: {desceram} relatorio(s) desceram para as "
                   f"gavetas certas")

    # 3) os arquivos soltos na raiz
    for arq in sorted(raiz.iterdir()):
        if not arq.is_file():
            continue
        sub = _destino_de(arq.name)
        if not sub:
            continue
        novo = _mover(arq, raiz / sub)
        if novo:
            anotar(f"{arq.name} -> {sub}")

    # 3b) (20/10) a ROTEIRIZACAO: o que o Planner exportou e estava solto na
    #     RELATORIOS ou na EXPORTADOS vai para RELATORIOS\Roteirizacao
    rot = raiz / ROTEIRIZACAO
    movidos = 0
    for pasta in (raiz / RELATORIOS, raiz / RELATORIOS / "EXPORTADOS"):
        if not pasta.is_dir():
            continue
        for arq in sorted(pasta.iterdir()):
            if arq.is_file() and DA_ROTEIRIZACAO.match(arq.name) \
                    and _mover(arq, rot):
                movidos += 1
            elif arq.is_dir() and arq.name.upper().startswith(
                    "ROTA_SEMANA_") and not (rot / arq.name).exists():
                # a rota da semana mandada por e-mail (email_rota.py)
                try:
                    shutil.move(str(arq), str(rot / arq.name))
                    movidos += 1
                except OSError:
                    pass
    if movidos:
        anotar(f"{movidos} arquivo(s) da roteirização -> {ROTEIRIZACAO}")

    # 4) o PLANNER e a BASE_CLIENTE: o mais novo volta para o lugar dele
    #    (o PLANNER na Roteirizacao, a BASE_CLIENTE na RELATORIOS)
    for padrao, casa in (("PLANNER_BAP*.xls*", ROTEIRIZACAO),
                         ("BASE_CLIENTE*.xls*", RELATORIOS)):
        anteriores = list((raiz / BKP_PLANNER).glob(padrao))
        atuais = list((raiz / casa).glob(padrao))
        if atuais or not anteriores:
            continue
        novo = (_o_vigente(anteriores)
                if padrao.startswith("PLANNER") else _mais_novo(anteriores))
        alvo = raiz / casa / novo.name
        if not alvo.exists():
            try:
                shutil.move(str(novo), str(alvo))
                anotar(f"{novo.name} -> {casa} (e o mais recente)")
            except OSError:
                pass
    return feito


def guardar_anterior(atual: Path, raiz, subpasta=BKP_PLANNER,
                     copiar: bool = False) -> Path | None:
    """
    Antes de gravar um arquivo novo por cima de um que ja existe, guarda o
    que estava la no backup. Devolve para onde foi, ou None.

    copiar=True COPIA em vez de mover: e o que se usa quando a gravacao
    nova pode falhar (gerar a BASE_CLIENTE, por exemplo). Assim, se der
    errado, o arquivo de antes continua no lugar e o programa nao fica
    vazio.
    """
    atual = Path(atual)
    if not atual.exists():
        return None
    if not copiar:
        return _mover(atual, Path(raiz) / subpasta)
    pasta = Path(raiz) / subpasta
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / atual.name
    if destino.exists() and destino.stat().st_size == atual.stat().st_size:
        return destino
    n = 2
    while destino.exists():
        destino = pasta / f"{atual.stem} ({n}){atual.suffix}"
        n += 1
    try:
        shutil.copy2(str(atual), str(destino))
        return destino
    except OSError:
        return None


def aposentar_planners(raiz, manter: str = "") -> int:
    """
    Deixa na Roteirizacao SO O PLANNER MAIS RECENTE (o `manter`, quando
    dado) e manda os outros para o BKP_RELATORIOS_PLANNER. Devolve quantos
    sairam.
    """
    raiz = Path(raiz)
    pasta = raiz / ROTEIRIZACAO
    if not pasta.is_dir():
        return 0
    # fica o do MES VIGENTE (o gerado por ultimo nele): gerar o de outro
    # mes nao tira o do mes que esta rodando da RELATORIOS
    todos = list(pasta.glob("PLANNER_BAP*.xls*"))
    fica = _o_vigente(todos)
    planners = [p for p in todos if p != fica]
    saiu = 0
    for p in planners:
        if _mover(p, raiz / BKP_PLANNER):
            saiu += 1
    return saiu


def planner_mais_recente(raiz, hoje=None) -> Path | None:
    """O PLANNER atual: o do MES VIGENTE (o mes de hoje ou, sem ele, o
    ultimo antes de hoje) e, nele, o gerado por ultimo. O PLANNER de um mes
    que ainda nao comecou nao passa na frente do mes que esta rodando."""
    raiz = Path(raiz)
    achados = [a for pasta in (raiz / ROTEIRIZACAO, raiz / RELATORIOS,
                               raiz / BKP_PLANNER, raiz)
               for a in pasta.glob("PLANNER_BAP*.xls*")]
    return _o_vigente(achados, hoje)


def _mes_de_hoje(hoje=None) -> str:
    from datetime import date                           # noqa: PLC0415
    hoje = hoje or date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def _o_vigente(planners, hoje=None):
    if not planners:
        return None
    atual = _mes_de_hoje(hoje)
    ate_hoje = [p for p in planners if mes_do_planner(p) <= atual]
    if ate_hoje:
        return max(ate_hoje, key=_chave_do_planner)
    return min(planners, key=lambda p: (mes_do_planner(p),
                                        -_chave_do_planner(p)[1]))


# --------------------------------------------------------------------------
# O PLANNER MES A MES
# --------------------------------------------------------------------------
# Cada mes tem a sua configuracao (zonas, equipe, quem responde a quem):
#     PLANNER_MESES\planner_config_2026-09.json
# O planner_config.json da pasta continua existindo e e a copia do mes
# VIGENTE (o de hoje) - e ele que o BAP Tools e os farois leem.
# O PLANNER gerado leva o mes no nome: PLANNER_BAP_2026-09_20261004.xlsx.
PLANNER_MESES = f"{SISTEMA}/PLANNER_MESES"
CONFIG_PLANNER = "planner_config.json"
_RE_CONFIG_MES = re.compile(r"^planner_config_(\d{4}-\d{2})\.json$", re.I)
_RE_PLANNER_MES = re.compile(r"^PLANNER_BAP_(\d{4})-(\d{2})_", re.I)
_RE_PLANNER_DATA = re.compile(r"^PLANNER_BAP_(\d{4})(\d{2})\d{2}", re.I)


def config_do_mes(raiz, mes: str) -> Path:
    return Path(raiz) / PLANNER_MESES / f"planner_config_{mes}.json"


def meses_do_planner(raiz) -> list:
    """Os meses que ja tem configuracao propria, em ordem."""
    pasta = Path(raiz) / PLANNER_MESES
    try:
        return sorted(m.group(1) for a in pasta.iterdir()
                      if (m := _RE_CONFIG_MES.match(a.name)))
    except OSError:
        return []


def mes_vigente(raiz, hoje=None) -> str:
    """O mes do Planner que esta valendo: o de hoje; sem ele, o ultimo
    antes de hoje; sem nenhum antes, o primeiro. '' sem meses."""
    meses = meses_do_planner(raiz)
    if not meses:
        return ""
    atual = _mes_de_hoje(hoje)
    antes = [m for m in meses if m <= atual]
    return antes[-1] if antes else meses[0]


def config_vigente(raiz) -> Path:
    """A configuracao do mes vigente (sem meses: o planner_config.json)."""
    mes = mes_vigente(raiz)
    return config_do_mes(raiz, mes) if mes else Path(raiz) / CONFIG_PLANNER


def config_do_planner(raiz, mes: str = "") -> Path:
    """A configuracao do mes pedido; sem ela (ou sem mes), a da pasta."""
    if mes:
        arq = config_do_mes(raiz, mes)
        if arq.exists():
            return arq
    return Path(raiz) / CONFIG_PLANNER


def mes_do_planner(arquivo) -> str:
    """O mes do PLANNER pelo nome. Nome antigo (so a data em que foi
    gerado): o mes dessa data."""
    nome = Path(arquivo).name
    m = _RE_PLANNER_MES.match(nome) or _RE_PLANNER_DATA.match(nome)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def _chave_do_planner(arquivo):
    try:
        quando = arquivo.stat().st_mtime
    except OSError:
        quando = 0
    return (mes_do_planner(arquivo), quando)


def planner_do_mes(raiz, mes: str) -> Path | None:
    """O PLANNER daquele mes (o gerado por ultimo, com o mes no nome), na
    RELATORIOS ou no backup. None se o mes nao tem PLANNER."""
    if not mes:
        return None
    raiz = Path(raiz)
    # so os que ja nasceram com o mes no nome: os antigos (so a data) sao
    # de antes do Planner mes a mes - faltam colunas e a equipe e outra
    achados = [a for pasta in (raiz / ROTEIRIZACAO, raiz / RELATORIOS,
                               raiz / BKP_PLANNER, raiz)
               for a in pasta.glob("PLANNER_BAP*.xls*")
               if _RE_PLANNER_MES.match(a.name) and mes_do_planner(a) == mes]
    return max(achados, key=_chave_do_planner) if achados else None



# --------------------------------------------------------------------------
# O MODO EMBUTIDO - o Planner, o Gerador de Meta e o Oportunidades dentro
# do BAP Analista
# --------------------------------------------------------------------------
# Cada um dos tres programas continua abrindo sozinho (a janela dele e um
# tk.Tk). O BAP Analista liga MODO_EMBUTIDO antes de importa-los: ai a
# "janela" de cada um vira um quadro (tk.Frame) dentro da aba do Analista,
# e o que so janela de verdade tem (titulo, tamanho) vira "nao faz nada".
MODO_EMBUTIDO = False
PAI_EMBUTIDO = None


def base_da_janela():
    """tk.Tk normalmente; um tk.Frame quando o BAP Analista embute."""
    import tkinter as tk
    if not MODO_EMBUTIDO:
        return tk.Tk

    class JanelaEmbutida(tk.Frame):
        def __init__(self, *args, **kwargs):
            super().__init__(PAI_EMBUTIDO)
            self.pack(fill="both", expand=True)

        def title(self, *args, **kwargs):
            return ""

        def geometry(self, *args, **kwargs):
            return ""

        def minsize(self, *args, **kwargs):
            return None

        def protocol(self, *args, **kwargs):
            return None

        def state(self, *args, **kwargs):
            return "normal"

        def mainloop(self, n=0):
            self.winfo_toplevel().mainloop(n)

    return JanelaEmbutida

if __name__ == "__main__":
    import sys
    onde = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    print(f"Arrumando {onde}...")
    mudou = arrumar(onde, registrar=lambda t: print("  " + t))
    print(f"  {len(mudou)} movimentacao(oes)." if mudou
          else "  ja estava tudo no lugar.")


def aba_pedida(argv=None):
    """
    O --aba N da linha de comando, contado de 1 como na tela (1. PARAMETROS),
    devolvido contado de 0 como o Notebook quer. Sem --aba, None.

    E assim que o BAP Central abre cada programa ja na aba do papel de quem
    clicou: a pre-venda cai direto na OPORTUNIDADE DE CLIENTE, a gestao no
    ACOMPANHAMENTO da meta.
    """
    import sys
    argv = sys.argv[1:] if argv is None else list(argv)
    for i, a in enumerate(argv):
        valor = None
        if a.startswith("--aba="):
            valor = a.split("=", 1)[1]
        elif a == "--aba" and i + 1 < len(argv):
            valor = argv[i + 1]
        if valor is not None:
            try:
                n = int(valor)
            except ValueError:
                return None
            return n - 1 if n >= 1 else None
    return None
