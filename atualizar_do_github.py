"""
ATUALIZAR DO GITHUB - leva o codigo do ``main`` para a pasta de producao (T-0003).

Desenho: ``docs/desenho/T-0003.md``. Regra 11 do CLAUDE.md: so roda depois do
"instale" do Alexandre, com backup ``SISTEMA BAP\\BACKUP_RELATORIOS\\
ANTES_<ASSUNTO>_<MES><ANO>`` e conferencia byte a byte (SHA-256).

Fluxo:
 1. Origem do ``main``: ``--origem <pasta>`` (se tiver ``.git`` e houver Git,
    faz ``git pull --ff-only``); sem ``--origem``, baixa o zip do ``main`` do
    GitHub para uma pasta temporaria (``tempfile``).
 2. Candidatos: so ``*.py`` e ``*.bat`` da RAIZ do ``main``.
 3. Exclusoes (``eh_excluido``) checadas ANTES de qualquer leitura: ``*.json``,
    as bases, os dados digitados (regra 7) e os segredos (regra 5).
 4. Comparacao por SHA-256: novo / alterado / igual.
 5. Trava "instalado por fora": arquivo alterado cuja data na producao e mais
    nova que a do ``main`` (+2 s de tolerancia) -> sai 2 sem trocar nada.
 6. ``--simular``: mostra o plano e a pasta de backup prevista; nao grava nada.
 7. Backup dos arquivos que serao substituidos, conferido por hash (falha -> 3).
 8. Troca atomica (temporario na mesma pasta + ``os.replace``), conferida por
    hash; falha -> restaura do backup, remove os novos e sai 4.
 9. Relatorio final. O log so mostra nomes de arquivo de codigo e hashes curtos.

Codigos de saida: 0 ok (ou nada a fazer) | 1 erro de origem ou argumento |
2 trava "instalado por fora" (limite 5) | 3 backup falhou | 4 troca falhou
(restaurado) | 10 limite 1: nenhum commit do main com 2 h ou mais (ou o
instalado ja e mais novo que ele) | 11 limite 2: CI do PR de origem nao esta
verde | 12 limite 3: web do commit escolhido diferente da do ``/saude``
(ou sem resposta) | 13 limite 4: fora da janela 06h00-07h30 (Manaus) | 14
limite 4: robo rodando | 15 API do GitHub indisponivel ou sem cota (60/h) |
16 rotina pausada (``SISTEMA BAP\\PAUSAR_ATUALIZACAO``).

Modos (T-0018, ADR 0002, R-20261124-214958-alexandre):
 - ``--diario``: a tarefa agendada das 06h30 no notebook do robo. So instala
   se os 5 limites passarem (funcoes puras ``escolher_commit_maduro``,
   ``ci_verde``, ``versoes_batem``,
   ``dentro_da_janela``/``robo_rodando`` e a trava do ``planejar``). Com o
   HEAD do ``main`` com menos de 2 h, instala o commit mais novo com 2 h ou
   mais (T-0056), se a web dele for igual a do ``/saude``. Nunca instala os ``.bat`` de instalacao, o proprio
   atualizador, o ``tarefa_bap.xml`` nem ``.json`` (esses seguem com
   "instale"). Baixa o zip do SHA conferido, sem token (repositorio
   publico). Grava ``SISTEMA BAP\\VERSAO_INSTALADA.txt`` e uma linha por
   rodada em ``SISTEMA BAP\\LOGS\\atualizacao_diaria.log``.
 - ``--primeira-vez``: so manual, exige ``--confirmar`` (ou ``--simular``);
   backup TOTAL dos ``.py``/``.bat`` da raiz e ignora a trava 5.
 - ``--agendar`` / ``--remover-agendamento``: cria/remove a tarefa do
   Windows (06h30, usuario atual, so com ele logado).

``--assunto`` e opcional; o padrao e ``ATUALIZACAO`` (vira
``ANTES_ATUALIZACAO_<MES><ANO>``). Use o numero da tarefa, ex.: ``T0003``.

So biblioteca padrao (o PC do robo nao tem Git nem pacotes extras).
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from fnmatch import fnmatch
from pathlib import Path, PurePath, PureWindowsPath
from typing import NamedTuple

URL_ZIP_MAIN = "https://github.com/aloirr/bapcentral/archive/refs/heads/main.zip"
TOLERANCIA_S = 2.0
EXTENSOES = (".py", ".bat")
ASSUNTO_PADRAO = "ATUALIZACAO"

MESES = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
         "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")

# Pastas de base (congeladas; o dado vem do robo).
_PASTAS_BASE = {"relatorios", "sistema bap", "bap ajuda 2.0"}
# Dados digitados (regra 7): prefixos de nome.
_PREFIXOS_DIGITADOS = ("_EDICOES_POS_VENDA", "_NCC", "_GARANTIAS", "_AUTORIZACOES")
# Configuracoes digitadas e segredos (regras 5 e 7). Ja caem em "*.json",
# mas ficam explicitos para a regra nao depender da extensao.
_NOMES_PROTEGIDOS = (
    "champions_config.json", "transportadoras_config.json",
    "painel_diretor_config.json", "visitas_config.json",
    "tomtom_config*.json", "google_maps_config*.json",
)

CODIGO_OK = 0
CODIGO_ERRO = 1
CODIGO_TRAVA = 2
CODIGO_BACKUP = 3
CODIGO_TROCA = 4
CODIGO_LIMITE_IDADE = 10      # limite 1
CODIGO_LIMITE_CI = 11         # limite 2
CODIGO_LIMITE_VERSAO_WEB = 12  # limite 3
CODIGO_LIMITE_JANELA = 13     # limite 4 (horario)
CODIGO_LIMITE_ROBO = 14       # limite 4 (robo rodando)
CODIGO_API = 15
CODIGO_PAUSA = 16

# --- Rotina diaria (T-0018) -------------------------------------------------
REPO = "aloirr/bapcentral"
URL_API = "https://api.github.com"
URL_ZIP_SHA = "https://github.com/aloirr/bapcentral/archive/{sha}.zip"
HORAS_MINIMAS_COMMIT = 2.0
JANELA_INICIO = dtime(6, 0)
JANELA_FIM = dtime(7, 30)
# Trava do robo: bap_automation.NOME_TRAVA dentro de SUBPASTA_DOWNLOADS
# (SISTEMA BAP/BACKUP_RELATORIOS/BKP_RELATORIOS_BAPTOOLS), valida por
# IDADE_MAXIMA_TRAVA (4 h). Copiado aqui para nao importar o robo.
TRAVA_ROBO_REL = PurePath("SISTEMA BAP", "BACKUP_RELATORIOS",
                          "BKP_RELATORIOS_BAPTOOLS", "_EXECUCAO_EM_ANDAMENTO.txt")
IDADE_MAXIMA_TRAVA_ROBO_S = 4 * 60 * 60
ARQ_PAUSA_REL = PurePath("SISTEMA BAP", "PAUSAR_ATUALIZACAO")
ARQ_VERSAO_REL = PurePath("SISTEMA BAP", "VERSAO_INSTALADA.txt")
ARQ_LOG_REL = PurePath("SISTEMA BAP", "LOGS", "atualizacao_diaria.log")
# So com "instale" (regra 11 nova, decisao 4 A): nunca no --diario.
SO_COM_INSTALE = frozenset(n.lower() for n in (
    "instalar_bap.bat", "INSTALAR_PDF.bat", "REPARAR_PYTHON_BAP.bat",
    "VERIFICAR_REQUISITOS.bat", "ATUALIZAR_DO_GITHUB.bat",
    "INSTALAR_ROTINA_DIARIA.bat", "atualizar_do_github.py", "tarefa_bap.xml",
))
# rate_limit nao conta; main + (lista de commits, so com o HEAD novo, T-0056)
# + pulls + check-runs = ate 4 pagas, mais 1 de folga.
REQUISICOES_MINIMAS_API = 5
COMMITS_LISTADOS = 100        # 1 pagina de /commits?sha=main (T-0056)
ASSUNTO_DIARIO = "DIARIO"
ASSUNTO_PRIMEIRA_VEZ = "PRIMEIRA_VEZ"
NOME_TAREFA = "BAP - Atualizacao diaria do codigo"
HORA_TAREFA = "06:30"
LIMITE_TR_SCHTASKS = 261
_CONCLUSOES_OK = frozenset({"success", "neutral", "skipped"})
_RE_SHA = re.compile(r"^[0-9a-f]{40}$")


# --------------------------------------------------------------------------
# Funcoes puras
# --------------------------------------------------------------------------

def nome_backup(assunto: str, quando: date) -> str:
    """Nome da pasta de backup: ``ANTES_<ASSUNTO>_<MES><ANO>``.

    O assunto vai para maiusculas e fica so com ``[A-Z0-9_]`` (espacos e
    hifens viram ``_``; o resto sai). Mes em 3 letras pt-BR.

    >>> nome_backup("T0003", date(2026, 11, 20))
    'ANTES_T0003_NOV2026'
    """
    limpo = re.sub(r"[\s\-]+", "_", assunto.strip().upper())
    limpo = re.sub(r"[^A-Z0-9_]", "", limpo).strip("_")
    if not limpo:
        raise ValueError("assunto vazio depois de normalizar")
    return f"ANTES_{limpo}_{MESES[quando.month - 1]}{quando.year:04d}"


def eh_excluido(rel: PurePath) -> bool:
    """True se o caminho (relativo a raiz) nunca pode ser lido nem copiado.

    Exclui: qualquer ``*.json``; ``RELATORIOS/``, ``SISTEMA BAP/``,
    ``BAP Ajuda 2.0/``; nomes que comecam por ``_EDICOES_POS_VENDA``, ``_NCC``,
    ``_GARANTIAS``, ``_AUTORIZACOES``; as configuracoes digitadas e os segredos
    (``tomtom_config*.json``, ``google_maps_config*.json``,
    ``visitas_config.json``, qualquer componente ``auth``, ``.env``).
    Caminho absoluto ou com ``..`` tambem e excluido. Nao toca no disco.
    """
    partes = rel.parts
    if not partes or rel.is_absolute() or rel.anchor:
        return True
    if any(p in ("", ".", "..") for p in partes):
        return True
    if partes[0].strip().lower() in _PASTAS_BASE:
        return True
    if any(p.lower() == "auth" for p in partes):
        return True
    nome = partes[-1]
    baixo = nome.lower()
    if baixo == ".env" or baixo.startswith(".env."):
        return True
    if baixo.endswith(".json"):
        return True
    if any(nome.upper().startswith(p) for p in _PREFIXOS_DIGITADOS):
        return True
    return any(fnmatch(baixo, padrao) for padrao in _NOMES_PROTEGIDOS)


def _eh_candidato_nome(rel: PurePath) -> bool:
    """Candidato = um so componente (raiz), nao excluido, ``.py``/``.bat``."""
    if eh_excluido(rel):
        return False
    return len(rel.parts) == 1 and rel.suffix.lower() in EXTENSOES


def _fuso_manaus():
    """Fuso America/Manaus (fallback: UTC-4 fixo, Manaus nao tem horario de verao)."""
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        return ZoneInfo("America/Manaus")
    except (ImportError, ZoneInfoNotFoundError, ValueError, OSError):  # sem tzdata
        return timezone(timedelta(hours=-4))


def agora_manaus() -> datetime:
    """Agora, com fuso America/Manaus."""
    return datetime.now(_fuso_manaus())


def hoje_manaus() -> date:
    """Data de hoje no fuso America/Manaus (fallback: UTC-4 fixo)."""
    return agora_manaus().date()


# --- Os 5 limites da rotina diaria (ADR 0002) -------------------------------

def data_iso(texto: str) -> datetime:
    """Data ISO 8601 da API do GitHub (``...Z``) -> datetime com fuso."""
    d = datetime.fromisoformat(str(texto).strip().replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("data sem fuso")
    return d


def commit_maduro(data_commit: datetime, agora: datetime,
                  horas: float = HORAS_MINIMAS_COMMIT) -> bool:
    """Limite 1: o commit do ``main`` tem ``horas`` (2) ou mais.

    As duas datas tem de ter fuso. Commit "no futuro" (relogio torto) nao passa.
    """
    if data_commit.tzinfo is None or agora.tzinfo is None:
        raise ValueError("datas sem fuso")
    return agora - data_commit >= timedelta(hours=horas)


class EscolhaCommit(NamedTuple):
    """Resultado de ``escolher_commit_maduro`` (T-0056).

    ``situacao``: ``"maduro"`` (instalar ``sha``), ``"ja_instalado"`` (o mais
    novo com 2 h e o instalado), ``"instalado_mais_novo"`` (a producao ja tem
    um commit mais novo que o ultimo com 2 h; nao volta para tras) ou
    ``"nenhum_maduro"``. ``sha``/``data`` so vem nas duas primeiras.
    """
    situacao: str
    sha: str | None = None
    data: datetime | None = None


def escolher_commit_maduro(commits: list, agora: datetime,
                           instalado: str | None = None,
                           horas: float = HORAS_MINIMAS_COMMIT) -> EscolhaCommit:
    """Limite 1 (T-0056): o commit mais novo do ``main`` com ``horas`` (2) ou mais.

    ``commits`` e a lista de ``/repos/{REPO}/commits?sha=main`` na ordem da API
    (o mais novo primeiro, a historia do ``main``); a idade e a data do
    committer (``commit_maduro``). Item sem SHA valido e ignorado; item sem
    data valida conta como novo (nao e escolhido). Se o ``instalado`` aparece
    antes do primeiro commit maduro, a producao ja esta a frente e nada volta
    para tras (``"instalado_mais_novo"``).
    """
    alvo = (instalado or "").strip().lower() or None
    for item in commits or []:
        if not isinstance(item, dict):
            continue
        sha = str(item.get("sha", "")).lower()
        if not _RE_SHA.match(sha):
            continue
        try:
            data = data_iso(item["commit"]["committer"]["date"])
            maduro = commit_maduro(data, agora, horas)
        except (KeyError, TypeError, ValueError):
            data, maduro = None, False
        if maduro:
            return EscolhaCommit("ja_instalado" if sha == alvo else "maduro", sha, data)
        if sha == alvo:
            return EscolhaCommit("instalado_mais_novo")
    return EscolhaCommit("nenhum_maduro")


def horas_desde(data: datetime, agora: datetime) -> str:
    """Idade em horas com 1 casa e virgula (pt-BR), para o log: ``'2,3'``."""
    return f"{(agora - data).total_seconds() / 3600:.1f}".replace(".", ",")


def pr_de_origem(pulls: list, sha: str) -> dict | None:
    """Limite 2 (parte 1): o PR mesclado no ``main`` que gerou o commit ``sha``.

    So vale o PR mesclado no ``main`` cujo ``merge_commit_sha`` e o proprio
    ``sha``: commit sem PR proprio nao herda o CI de outro PR -> ``None``.
    """
    mesclados = [p for p in (pulls or []) if isinstance(p, dict)
                 and p.get("merged_at")
                 and (p.get("base") or {}).get("ref") == "main"]
    for p in mesclados:
        if p.get("merge_commit_sha") == sha:
            return p
    return None


def ci_verde(check_runs: list) -> tuple[bool, str]:
    """Limite 2 (parte 2): todas as verificacoes do head do PR terminaram verdes.

    Verde = todas ``completed`` com conclusao ``success``/``neutral``/``skipped``
    e pelo menos uma ``success``. Lista vazia nao passa.
    """
    runs = [r for r in (check_runs or []) if isinstance(r, dict)]
    if not runs:
        return False, "sem CI no head do PR"
    andando = [r for r in runs if r.get("status") != "completed"]
    if andando:
        return False, f"{len(andando)} verificacao(oes) em andamento"
    ruins = sorted({str(r.get("name", "?")) for r in runs
                    if r.get("conclusion") not in _CONCLUSOES_OK})
    if ruins:
        return False, "nao verde: " + ", ".join(ruins)[:200]
    if not any(r.get("conclusion") == "success" for r in runs):
        return False, "nenhuma verificacao com sucesso"
    return True, "verde"


def versao_do_init(texto: str) -> str | None:
    """``VERSAO = "x.y.z"`` de ``web/app/__init__.py`` (``None`` se faltar)."""
    m = re.search(r"""^VERSAO\s*=\s*["']([^"'\s]+)["']""", texto or "", re.MULTILINE)
    return m.group(1) if m else None


def versoes_batem(versao_main: str | None, versao_site: str | None) -> bool:
    """Limite 3: a versao da web no ``main`` e a mesma do ``/saude``.

    O deploy do Render e automatico a cada publicacao no ``main``
    (R-20261124-210855-alexandre): versao diferente = deploy ainda nao
    terminou (ou falhou) -> espera.
    """
    if not versao_main or not versao_site:
        return False
    return str(versao_main).strip() == str(versao_site).strip()


def dentro_da_janela(agora: datetime, inicio: dtime = JANELA_INICIO,
                     fim: dtime = JANELA_FIM) -> bool:
    """Limite 4 (horario): ``inicio <= hora <= fim`` no fuso America/Manaus."""
    if agora.tzinfo is None:
        raise ValueError("agora sem fuso")
    hora = agora.astimezone(_fuso_manaus()).time().replace(tzinfo=None)
    return inicio <= hora <= fim


def robo_rodando(idade_trava_s: float | None,
                 maximo_s: float = IDADE_MAXIMA_TRAVA_ROBO_S) -> bool:
    """Limite 4 (robo): a trava do ``bap_automation`` existe e e recente.

    ``None`` = sem trava. A regra e a do robo: trava com 4 h ou mais esta
    presa e e ignorada. Idade negativa (relogio torto) conta como rodando.
    """
    if idade_trava_s is None:
        return False
    return idade_trava_s < maximo_s


def so_com_instale(rel: PurePath) -> bool:
    """True se o arquivo nunca e instalado pelo ``--diario`` (pede "instale")."""
    return rel.name.lower() in SO_COM_INSTALE or eh_excluido(rel)


def linha_log(agora: datetime, modo: str, codigo: int, motivo: str,
              sha: str | None) -> str:
    """Uma linha do log da rotina, sem dado pessoal: data, modo, codigo,
    SHA curto e o motivo (so nomes de programa e hashes curtos)."""
    quando = agora.astimezone(_fuso_manaus()).strftime("%Y-%m-%d %H:%M:%S")
    curto = (sha or "-")[:7]
    limpo = " ".join(str(motivo).split())
    return f"{quando} | {modo} | codigo {codigo} | main {curto} | {limpo}"


def texto_versao_instalada(sha: str, agora: datetime, n_trocados: int,
                           modo: str) -> str:
    """Conteudo do ``VERSAO_INSTALADA.txt`` (1a linha = SHA completo)."""
    quando = agora.astimezone(_fuso_manaus()).strftime("%Y-%m-%d %H:%M:%S")
    return (f"{sha}\ninstalado em {quando} (America/Manaus)\n"
            f"modo {modo}; {n_trocados} arquivo(s) trocado(s)\n")


def sha_do_texto_versao(texto: str) -> str | None:
    """SHA da 1a linha do ``VERSAO_INSTALADA.txt`` (``None`` se invalido)."""
    primeira = (texto or "").strip().splitlines()[:1]
    sha = primeira[0].strip().lower() if primeira else ""
    return sha if _RE_SHA.match(sha) else None


def comando_agendar(pasta: Path) -> list[str]:
    """``schtasks /Create`` da tarefa diaria das 06h30 na ``pasta``.

    Sem ``/RU``: fica com o usuario atual e so roda com ele logado (nao pede
    nem guarda senha). ``/F`` substitui a tarefa se ja existir.
    """
    script = PureWindowsPath(str(pasta)) / "atualizar_do_github.py"
    tr = f'py -3.12 "{script}" --diario'
    if len(tr) > LIMITE_TR_SCHTASKS:
        raise ValueError(f"caminho longo demais para o schtasks ({len(tr)} > "
                         f"{LIMITE_TR_SCHTASKS} caracteres)")
    return ["schtasks", "/Create", "/TN", NOME_TAREFA, "/TR", tr,
            "/SC", "DAILY", "/ST", HORA_TAREFA, "/F"]


def comando_remover() -> list[str]:
    """``schtasks /Delete`` da tarefa diaria."""
    return ["schtasks", "/Delete", "/TN", NOME_TAREFA, "/F"]


# --------------------------------------------------------------------------
# Leitura (sem escrita)
# --------------------------------------------------------------------------

def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def candidatos(origem: Path) -> list[PurePath]:
    """Lista (ordenada) dos ``*.py``/``*.bat`` da raiz de ``origem``.

    A exclusao e checada pelo nome, antes de qualquer leitura; so lista a
    pasta (nao abre arquivo nenhum).
    """
    saida: list[PurePath] = []
    for item in origem.iterdir():
        rel = PurePath(item.name)
        if not _eh_candidato_nome(rel):
            continue
        if item.is_file() and not item.is_symlink():
            saida.append(rel)
    return sorted(saida, key=lambda p: p.name.lower())


@dataclass
class Plano:
    """O que a atualizacao faria. Montado por ``planejar`` sem gravar nada.

    - ``novos``: existem no ``main`` e nao na producao;
    - ``alterados``: existem nos dois com SHA-256 diferente;
    - ``iguais``: mesmo SHA-256;
    - ``mais_novos_na_producao``: alterados cuja data na producao e mais nova
      que a do ``main`` (+ tolerancia) -> trava;
    - ``hash_main`` / ``hash_producao``: SHA-256 por arquivo;
    - ``data_main``: data (epoch) do ``main`` por arquivo, gravada como
      ``mtime`` do arquivo instalado;
    - ``pendentes_instale``: arquivos deixados de fora pelo filtro ``excluir``
      (``--diario``) que estao diferentes na producao: seguem com "instale".
    """
    origem: Path
    producao: Path
    novos: list[PurePath] = field(default_factory=list)
    alterados: list[PurePath] = field(default_factory=list)
    iguais: list[PurePath] = field(default_factory=list)
    mais_novos_na_producao: list[PurePath] = field(default_factory=list)
    hash_main: dict[PurePath, str] = field(default_factory=dict)
    hash_producao: dict[PurePath, str] = field(default_factory=dict)
    data_main: dict[PurePath, float] = field(default_factory=dict)
    pendentes_instale: list[PurePath] = field(default_factory=list)

    @property
    def a_trocar(self) -> list[PurePath]:
        """Alterados e novos, nessa ordem."""
        return list(self.alterados) + list(self.novos)


def planejar(origem: Path, producao: Path,
             data_main: Callable[[PurePath], float],
             excluir: Callable[[PurePath], bool] | None = None) -> Plano:
    """Compara ``origem`` (o ``main``) com ``producao``. Nao grava nada.

    ``data_main(rel)`` devolve a data (epoch, s) do ``main`` para o arquivo:
    commit (git), item do zip ou ``mtime`` na origem. ``excluir(rel)`` tira
    arquivos do plano (``--diario``: ``so_com_instale``); os que estiverem
    diferentes vao para ``pendentes_instale``.
    """
    origem = Path(origem)
    producao = Path(producao)
    plano = Plano(origem=origem, producao=producao)
    for rel in candidatos(origem):
        if excluir is not None and excluir(rel):
            destino = producao / rel
            if (not destino.is_file()
                    or _sha256(destino) != _sha256(origem / rel)):
                plano.pendentes_instale.append(rel)
            continue
        h_main = _sha256(origem / rel)
        plano.hash_main[rel] = h_main
        quando = float(data_main(rel))
        plano.data_main[rel] = quando
        destino = producao / rel
        if not destino.exists():
            plano.novos.append(rel)
            continue
        if not destino.is_file():
            raise ValueError(f"na producao, {rel.name} nao e arquivo")
        h_prod = _sha256(destino)
        plano.hash_producao[rel] = h_prod
        if h_prod == h_main:
            plano.iguais.append(rel)
            continue
        plano.alterados.append(rel)
        if destino.stat().st_mtime > quando + TOLERANCIA_S:
            plano.mais_novos_na_producao.append(rel)
    return plano


def pasta_backup(producao: Path, assunto: str, hoje: date) -> Path:
    """Pasta de backup livre: ``ANTES_...``, ``ANTES_..._2``, ``_3``... (so le)."""
    base = Path(producao) / "SISTEMA BAP" / "BACKUP_RELATORIOS"
    nome = nome_backup(assunto, hoje)
    pasta = base / nome
    n = 2
    while pasta.exists():
        pasta = base / f"{nome}_{n}"
        n += 1
    return pasta


# --------------------------------------------------------------------------
# Execucao
# --------------------------------------------------------------------------

def _curto(h: str) -> str:
    return h[:10]


def _rel_producao(caminho: Path, producao: Path) -> str:
    try:
        return str(caminho.relative_to(producao))
    except ValueError:
        return caminho.name


def _copiar_atomico(fonte: Path, destino: Path, mtime: float | None) -> None:
    """Copia para temporario na mesma pasta e troca com ``os.replace``."""
    tmp = destino.with_name(f".{destino.name}.atualizando.tmp")
    try:
        shutil.copyfile(fonte, tmp)
        if mtime is not None:
            os.utime(tmp, (mtime, mtime))
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _imprimir_plano(plano: Plano) -> None:
    print(f"Arquivos do main conferidos: {len(plano.hash_main)}")
    print(f"  iguais: {len(plano.iguais)} | alterados: {len(plano.alterados)}"
          f" | novos: {len(plano.novos)}")
    for rel in plano.alterados:
        print(f"  ALTERADO {rel.name}: {_curto(plano.hash_producao[rel])}"
              f" -> {_curto(plano.hash_main[rel])}")
    for rel in plano.novos:
        print(f"  NOVO     {rel.name}: {_curto(plano.hash_main[rel])}")
    for rel in plano.pendentes_instale:
        print(f"  PENDENTE {rel.name}: diferente do main, so com \"instale\"")


def executar(plano: Plano, producao: Path, assunto: str, simular: bool,
             hoje: date, *, ignorar_trava: bool = False,
             backup_total: bool = False) -> int:
    """Aplica o plano (ou so mostra, com ``simular``). Devolve o codigo de saida.

    ``ignorar_trava`` e ``backup_total`` sao do ``--primeira-vez``: a trava
    "instalado por fora" so avisa e o backup leva TODOS os ``.py``/``.bat``
    da raiz da producao, nao so os que serao substituidos.
    """
    producao = Path(producao)
    _imprimir_plano(plano)

    if plano.mais_novos_na_producao and ignorar_trava:
        print("\nTRAVA IGNORADA (--primeira-vez): mais novos na producao,"
              " vao para o backup total:")
        for rel in plano.mais_novos_na_producao:
            print(f"  {rel.name}")
    elif plano.mais_novos_na_producao:
        print("\nTRAVA: a producao tem arquivo(s) mais novo(s) que o main"
              " (instalado por fora?). Nada foi trocado:")
        for rel in plano.mais_novos_na_producao:
            print(f"  {rel.name}")
        print("Leve essa versao para o GitHub (PR) antes de atualizar.")
        return CODIGO_TRAVA

    trocar = plano.a_trocar
    if not trocar:
        print("\nNada a fazer: a producao ja esta igual ao main.")
        return CODIGO_OK

    a_guardar = candidatos(producao) if backup_total else list(plano.alterados)
    backup = pasta_backup(producao, assunto, hoje) if a_guardar else None

    if simular:
        print("\nSIMULACAO: nada foi gravado.")
        if backup is not None:
            print(f"Backup previsto: {_rel_producao(backup, producao)}"
                  f" ({len(a_guardar)} arquivo(s))")
        else:
            print("Sem backup: so arquivos novos.")
        return CODIGO_OK

    # 7. Backup dos que serao substituidos.
    if backup is not None:
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.mkdir(exist_ok=False)
            for rel in a_guardar:
                esperado = plano.hash_producao.get(rel) or _sha256(producao / rel)
                copia = backup / rel.name
                shutil.copy2(producao / rel, copia)
                if _sha256(copia) != esperado:
                    raise OSError(f"hash do backup de {rel.name} nao confere")
        except OSError as erro:
            print(f"\nERRO NO BACKUP ({type(erro).__name__}): {erro}")
            print("Nada foi trocado.")
            return CODIGO_BACKUP
        print(f"\nBackup conferido: {_rel_producao(backup, producao)}"
              f" ({len(a_guardar)} arquivo(s))")

    # 8. Troca.
    trocados: list[PurePath] = []
    try:
        for rel in trocar:
            destino = producao / rel
            _copiar_atomico(plano.origem / rel, destino, plano.data_main.get(rel))
            trocados.append(rel)
            if _sha256(destino) != plano.hash_main[rel]:
                raise OSError(f"hash de {rel.name} instalado nao confere")
    except OSError as erro:
        print(f"\nERRO NA TROCA ({type(erro).__name__}): {erro}")
        falhas = _restaurar(plano, producao, backup, trocados)
        if falhas:
            print("ATENCAO: nao consegui restaurar: " + ", ".join(falhas))
            if backup is not None:
                print(f"Copie a mao de {_rel_producao(backup, producao)}.")
        else:
            print("Producao restaurada como estava.")
        print("Feche os programas BAP (e espere o OneDrive sincronizar) e"
              " rode de novo.")
        return CODIGO_TROCA

    # 9. Relatorio.
    print(f"\nOK: {len(trocados)} arquivo(s) trocado(s), hashes conferidos.")
    for rel in trocados:
        print(f"  {rel.name}: {_curto(plano.hash_main[rel])}")
    if backup is not None:
        print(f"Backup: {_rel_producao(backup, producao)}")
    return CODIGO_OK


def _restaurar(plano: Plano, producao: Path, backup: Path | None,
               trocados: list[PurePath]) -> list[str]:
    """Desfaz a troca: alterados voltam do backup, novos sao removidos.

    Inclui o arquivo que falhou no meio (o temporario ja foi limpo; se o
    ``os.replace`` chegou a acontecer, o arquivo e restaurado). Devolve os
    nomes que nao deu para restaurar.
    """
    falhas: list[str] = []
    for rel in plano.a_trocar:
        destino = producao / rel
        try:
            if rel in plano.alterados:
                if backup is None:
                    continue
                if destino.exists() and _sha256(destino) == plano.hash_producao[rel]:
                    continue
                _copiar_atomico(backup / rel.name, destino, None)
                shutil.copystat(backup / rel.name, destino)
                if _sha256(destino) != plano.hash_producao[rel]:
                    falhas.append(rel.name)
            elif rel in trocados or destino.exists():
                if destino.exists():
                    destino.unlink()
        except OSError:
            falhas.append(rel.name)
    return falhas


# --------------------------------------------------------------------------
# Origem do main
# --------------------------------------------------------------------------

def _data_zip(info: zipfile.ZipInfo) -> float:
    """Data do item do zip (campo estendido UT se houver; senao, UTC)."""
    extra = info.extra
    i = 0
    while i + 4 <= len(extra):
        tag, tam = struct.unpack("<HH", extra[i:i + 4])
        dados = extra[i + 4:i + 4 + tam]
        if tag == 0x5455 and len(dados) >= 5 and dados[0] & 1:
            return float(struct.unpack("<I", dados[1:5])[0])
        i += 4 + tam
    return float(calendar.timegm(info.date_time + (0, 0, -1)))


def baixar_main(destino: Path, url: str = URL_ZIP_MAIN,
                info: dict | None = None) -> dict[PurePath, float]:
    """Baixa o zip do ``main`` e extrai so os candidatos para ``destino``.

    Item excluido nao e extraido nem lido. Devolve a data de cada candidato.
    Com ``info``, preenche ``info["sha"]`` (o comentario do zip do GitHub e o
    SHA do commit) e ``info["versao_web"]`` (``VERSAO`` de
    ``web/app/__init__.py``), sem extrair mais nada.
    """
    destino.mkdir(parents=True, exist_ok=True)
    arq_zip = destino.parent / "main.zip"
    with urllib.request.urlopen(url, timeout=120) as resp, open(arq_zip, "wb") as f:
        shutil.copyfileobj(resp, f)
    datas: dict[PurePath, float] = {}
    with zipfile.ZipFile(arq_zip) as z:
        if info is not None:
            comentario = z.comment.decode("ascii", "ignore").strip().lower()
            info["sha"] = comentario if _RE_SHA.match(comentario) else None
            info["versao_web"] = None
        for item in z.infolist():
            if item.is_dir():
                continue
            partes = PurePath(item.filename).parts
            if info is not None and partes[1:] == ("web", "app", "__init__.py"):
                texto = z.read(item).decode("utf-8", "replace")
                info["versao_web"] = versao_do_init(texto)
                continue
            if len(partes) != 2:  # <raiz-do-zip>/<arquivo>: so a raiz do main
                continue
            rel = PurePath(partes[1])
            if not _eh_candidato_nome(rel):
                continue
            with z.open(item) as src, open(destino / rel.name, "wb") as out:
                shutil.copyfileobj(src, out)
            datas[rel] = _data_zip(item)
    return datas


def _git_disponivel(origem: Path) -> bool:
    return (origem / ".git").exists() and shutil.which("git") is not None


def _data_git(origem: Path, rel: PurePath) -> float | None:
    r = subprocess.run(
        ["git", "-C", str(origem), "log", "-1", "--format=%ct", "--", rel.name],
        capture_output=True, text=True, check=False)
    texto = r.stdout.strip()
    return float(texto) if r.returncode == 0 and texto.isdigit() else None


# --------------------------------------------------------------------------
# Rotina diaria (T-0018): rede, trava do robo, log e versao instalada
# --------------------------------------------------------------------------

class ErroApi(Exception):
    """Falha na API publica do GitHub ou no ``/saude`` (sem token, sem segredo)."""


def _get_json(url: str, timeout: float = 30):
    """GET de JSON sem token (repositorio publico; limite de 60 req/h por IP).

    Cota esgotada (403/429 com ``X-RateLimit-Remaining: 0``) ou qualquer erro
    de rede vira ``ErroApi`` com mensagem curta, sem a URL.
    """
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "bap-atualizador",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        if erro.code in (403, 429) and erro.headers.get("X-RateLimit-Remaining") == "0":
            raise ErroApi("cota da API do GitHub esgotada (60/h)") from None
        raise ErroApi(f"HTTP {erro.code}") from None
    except (OSError, ValueError) as erro:
        raise ErroApi(type(erro).__name__) from None


def cota_api() -> int:
    """Requisicoes restantes na cota sem token (``/rate_limit`` nao gasta cota)."""
    dados = _get_json(f"{URL_API}/rate_limit")
    return int(dados["resources"]["core"]["remaining"])


def _url_site() -> str | None:
    """URL da web: ``BAP_WEB_URL`` ou o cofre (servico ``BAP_WEB``, ``url``),
    a mesma do envio do pacote no ``bap_automation``. Nunca vai para o log."""
    url = (os.environ.get("BAP_WEB_URL") or "").strip()
    if not url:
        try:
            import keyring
            url = (keyring.get_password("BAP_WEB", "url") or "").strip()
        except Exception:  # noqa: BLE001
            url = ""
    return url if url.lower().startswith("https://") else None


def versao_do_site() -> str | None:
    """``versao`` do ``/saude`` da web, ou ``None`` (sem URL ou sem resposta)."""
    url = _url_site()
    if not url:
        return None
    try:
        dados = _get_json(url.rstrip("/") + "/saude")
    except ErroApi:
        return None
    versao = dados.get("versao") if isinstance(dados, dict) else None
    return str(versao) if versao else None


def idade_trava_robo(producao: Path, agora_epoch: float) -> float | None:
    """Idade (s) da trava do robo na producao; ``None`` se nao existe.

    So olha a data do arquivo: o conteudo (usuario e maquina) nao e lido.
    """
    try:
        mtime = (Path(producao) / TRAVA_ROBO_REL).stat().st_mtime
    except FileNotFoundError:
        return None
    return agora_epoch - mtime


def sha_instalado(producao: Path) -> str | None:
    """SHA gravado no ``VERSAO_INSTALADA.txt`` (``None`` se nao houver)."""
    try:
        texto = (Path(producao) / ARQ_VERSAO_REL).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return sha_do_texto_versao(texto)


def gravar_versao(producao: Path, sha: str, agora: datetime, n_trocados: int,
                  modo: str) -> None:
    """Grava ``SISTEMA BAP\\VERSAO_INSTALADA.txt`` (troca atomica)."""
    destino = Path(producao) / ARQ_VERSAO_REL
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f".{destino.name}.tmp")
    tmp.write_text(texto_versao_instalada(sha, agora, n_trocados, modo),
                   encoding="utf-8")
    os.replace(tmp, destino)


def registrar(producao: Path, linha: str) -> None:
    """Acrescenta uma linha ao ``SISTEMA BAP\\LOGS\\atualizacao_diaria.log``."""
    arq = Path(producao) / ARQ_LOG_REL
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        with open(arq, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError as erro:
        print(f"AVISO: nao consegui gravar o log ({type(erro).__name__}).")


def rodar_diario(producao: Path, simular: bool = False,
                 agora: datetime | None = None) -> int:
    """``--diario``: confere os 5 limites e, se todos passarem, instala.

    Ordem (do mais barato ao mais caro): pausa; limite 4 (janela e robo);
    cota da API; SHA do ``main`` (ja instalado -> 0); limite 1 (HEAD com
    menos de 2 h -> o commit mais novo com 2 h, ``escolher_commit_maduro``,
    T-0056); limite 2; zip do SHA escolhido; limite 3
    (``versoes_batem``); plano com ``so_com_instale``; limite 5;
    troca. Limite que falha -> nada trocado, codigo proprio e 1 linha no log,
    que diz qual commit foi escolhido e por que.
    """
    producao = Path(producao)
    agora = agora or agora_manaus()
    modo = "diario"
    sha: str | None = None
    contexto = ""  # qual commit foi escolhido e por que (T-0056)

    def fim(codigo: int, motivo: str) -> int:
        motivo = contexto + motivo
        print(f"[codigo {codigo}] {motivo}")
        if not simular:  # simulacao nao grava nada, nem o log
            registrar(producao, linha_log(agora, modo, codigo, motivo, sha))
        return codigo

    if (producao / ARQ_PAUSA_REL).exists():
        return fim(CODIGO_PAUSA, "rotina pausada (SISTEMA BAP\\PAUSAR_ATUALIZACAO)")
    if not dentro_da_janela(agora):
        hora = agora.astimezone(_fuso_manaus()).strftime("%H:%M")
        return fim(CODIGO_LIMITE_JANELA,
                   f"limite 4: {hora} fora da janela 06h00-07h30 (Manaus)")
    if robo_rodando(idade_trava_robo(producao, agora.timestamp())):
        return fim(CODIGO_LIMITE_ROBO, "limite 4: robo rodando (trava do bap_automation)")

    try:
        restantes = cota_api()
        if restantes < REQUISICOES_MINIMAS_API:
            return fim(CODIGO_API, f"API do GitHub sem cota ({restantes} restantes)")
        commit = _get_json(f"{URL_API}/repos/{REPO}/commits/main")
        candidato = str(commit["sha"]).lower()
        if not _RE_SHA.match(candidato):
            raise ValueError("sha invalido")
        data_commit = data_iso(commit["commit"]["committer"]["date"])
        sha = candidato
    except (ErroApi, KeyError, TypeError, ValueError) as erro:
        return fim(CODIGO_API, f"API do GitHub: {type(erro).__name__} {erro}")

    instalado = sha_instalado(producao)
    if instalado == sha:
        return fim(CODIGO_OK, "nada a fazer: este main ja esta instalado")
    if commit_maduro(data_commit, agora):
        contexto = f"HEAD com {horas_desde(data_commit, agora)} h; "
    else:
        # T-0056: HEAD com menos de 2 h nao derruba o dia; vale o commit mais
        # novo do main com 2 h ou mais, com os mesmos limites 2, 3 e 5.
        cabeca = f"HEAD {sha[:7]} com {horas_desde(data_commit, agora)} h"
        try:
            lista = _get_json(f"{URL_API}/repos/{REPO}/commits"
                              f"?sha=main&per_page={COMMITS_LISTADOS}")
        except ErroApi as erro:
            return fim(CODIGO_API, f"{cabeca}; API do GitHub: {erro}")
        if not isinstance(lista, list):
            return fim(CODIGO_API, f"{cabeca}; API do GitHub: lista de commits invalida")
        escolha = escolher_commit_maduro(lista, agora, instalado)
        if escolha.situacao == "nenhum_maduro":
            return fim(CODIGO_LIMITE_IDADE,
                       f"limite 1: {cabeca}; nenhum commit com {HORAS_MINIMAS_COMMIT:g} h entre os "
                       f"{COMMITS_LISTADOS} mais novos do main")
        if escolha.situacao == "instalado_mais_novo":
            return fim(CODIGO_LIMITE_IDADE,
                       f"limite 1: {cabeca}; o instalado ({instalado[:7]}) ja e mais "
                       f"novo que o ultimo commit com {HORAS_MINIMAS_COMMIT:g} h")
        sha = escolha.sha
        contexto = f"{cabeca}; escolhido {sha[:7]} ({horas_desde(escolha.data, agora)} h); "
        if escolha.situacao == "ja_instalado":
            return fim(CODIGO_OK, f"nada a fazer: o commit mais novo com "
                       f"{HORAS_MINIMAS_COMMIT:g} h ja esta instalado")

    try:
        pulls = _get_json(f"{URL_API}/repos/{REPO}/commits/{sha}/pulls")
        pr = pr_de_origem(pulls if isinstance(pulls, list) else [], sha)
        if pr is None:
            return fim(CODIGO_LIMITE_CI, "limite 2: commit sem PR de origem mesclado")
        head = str((pr.get("head") or {}).get("sha", ""))
        if not _RE_SHA.match(head):
            return fim(CODIGO_LIMITE_CI, f"limite 2: PR #{pr.get('number')} sem head SHA")
        runs = _get_json(f"{URL_API}/repos/{REPO}/commits/{head}/check-runs?per_page=100")
        ok, motivo = ci_verde(runs.get("check_runs", []) if isinstance(runs, dict) else [])
    except ErroApi as erro:
        return fim(CODIGO_API, f"API do GitHub: {erro}")
    if not ok:
        return fim(CODIGO_LIMITE_CI, f"limite 2: CI do PR #{pr.get('number')} {motivo}")

    temp = Path(tempfile.mkdtemp(prefix="bap_main_"))
    try:
        origem = temp / "main"
        info: dict = {}
        try:
            datas = baixar_main(origem, URL_ZIP_SHA.format(sha=sha), info=info)
        except (OSError, zipfile.BadZipFile) as erro:
            return fim(CODIGO_ERRO, f"erro ao baixar o zip ({type(erro).__name__})")
        if info.get("sha") != sha:
            return fim(CODIGO_ERRO, "o zip baixado nao traz o SHA conferido"
                       " (outro commit ou sem comentario)")

        v_main = info.get("versao_web")
        v_site = versao_do_site()
        if not versoes_batem(v_main, v_site):
            return fim(CODIGO_LIMITE_VERSAO_WEB,
                       f"limite 3: web do commit {v_main or '?'} x /saude "
                       f"{v_site or 'sem resposta'} (tem de ser igual; deploy pendente?)")

        try:
            plano = planejar(origem, producao, lambda rel: datas[rel],
                             excluir=so_com_instale)
        except (OSError, ValueError) as erro:
            return fim(CODIGO_ERRO, f"erro ao comparar ({type(erro).__name__})")
        if plano.mais_novos_na_producao:
            _imprimir_plano(plano)
            nomes = ", ".join(r.name for r in plano.mais_novos_na_producao)
            return fim(CODIGO_TRAVA, f"limite 5: instalado por fora: {nomes}")

        codigo = executar(plano, producao, ASSUNTO_DIARIO, simular,
                          agora.astimezone(_fuso_manaus()).date())
        trocados = plano.a_trocar
        resumo = ", ".join(f"{r.name} {plano.hash_main[r][:7]}"
                           for r in trocados) or "nenhum arquivo diferente"
        pendentes = ", ".join(r.name for r in plano.pendentes_instale)
        if pendentes:
            resumo += f"; pendente de instale: {pendentes}"
        if codigo == CODIGO_OK and not simular:
            try:
                gravar_versao(producao, sha, agora, len(trocados), "diario")
            except OSError as erro:
                print(f"AVISO: VERSAO_INSTALADA.txt nao gravado ({type(erro).__name__}).")
        if simular:
            prefixo = "simulado"
        else:
            prefixo = "instalado" if codigo == CODIGO_OK else "falhou"
        return fim(codigo, f"{prefixo}: {resumo}")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def agendar(pasta: Path, remover: bool = False) -> int:
    """``--agendar`` / ``--remover-agendamento`` (so no Windows)."""
    if os.name != "nt":
        print("ERRO: o agendamento so existe no Windows.")
        return CODIGO_ERRO
    try:
        cmd = comando_remover() if remover else comando_agendar(pasta)
    except ValueError as erro:
        print(f"ERRO: {erro}")
        return CODIGO_ERRO
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        print("ERRO: o schtasks falhou.")
        return CODIGO_ERRO
    print("Tarefa removida." if remover else
          f"Tarefa '{NOME_TAREFA}' criada: todo dia as {HORA_TAREFA}.")
    return CODIGO_OK


def _configurar_saida() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _sha_git(origem: Path) -> str | None:
    r = subprocess.run(["git", "-C", str(origem), "rev-parse", "HEAD"],
                       capture_output=True, text=True, check=False)
    sha = r.stdout.strip().lower()
    return sha if r.returncode == 0 and _RE_SHA.match(sha) else None


def main(argv: list[str] | None = None) -> int:
    """Linha de comando. Ver a docstring do modulo para fluxo e codigos."""
    _configurar_saida()
    ap = argparse.ArgumentParser(
        prog="atualizar_do_github",
        description="Leva os .py/.bat do main para a pasta de producao.")
    ap.add_argument("--origem", type=Path, default=None,
                    help="pasta local com o main (padrao: baixa o zip do GitHub)")
    ap.add_argument("--producao", type=Path,
                    default=Path(__file__).resolve().parent,
                    help="pasta de producao (padrao: a pasta deste programa)")
    ap.add_argument("--assunto", default=None,
                    help=f"assunto do backup (padrao: {ASSUNTO_PADRAO})")
    ap.add_argument("--simular", action="store_true",
                    help="so mostra o plano; nao grava nada")
    modos = ap.add_mutually_exclusive_group()
    modos.add_argument("--diario", action="store_true",
                       help="rotina agendada: so instala se os 5 limites passarem")
    modos.add_argument("--primeira-vez", action="store_true",
                       help="manual: backup total e ignora a trava 'instalado por fora'")
    modos.add_argument("--agendar", action="store_true",
                       help="cria a tarefa do Windows das 06h30 nesta pasta")
    modos.add_argument("--remover-agendamento", action="store_true",
                       help="remove a tarefa do Windows")
    ap.add_argument("--confirmar", action="store_true",
                    help="obrigatorio no --primeira-vez (fora do --simular)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return CODIGO_OK if e.code == 0 else CODIGO_ERRO

    if args.agendar or args.remover_agendamento:
        return agendar(Path(__file__).resolve().parent, args.remover_agendamento)

    if args.diario and (args.origem is not None or args.assunto is not None):
        print("ERRO: --diario nao aceita --origem nem --assunto.")
        return CODIGO_ERRO
    if args.primeira_vez and not (args.confirmar or args.simular):
        print("ERRO: --primeira-vez troca tudo com backup total e ignora a trava"
              " 'instalado por fora'. Rode antes com --simular e, depois, com"
              " --confirmar.")
        return CODIGO_ERRO

    padrao = ASSUNTO_PRIMEIRA_VEZ if args.primeira_vez else ASSUNTO_PADRAO
    assunto = args.assunto or padrao
    try:
        nome_backup(assunto, date(2000, 1, 1))
    except ValueError:
        print("ERRO: --assunto invalido (use letras, numeros e _).")
        return CODIGO_ERRO

    producao = args.producao.resolve()
    if not producao.is_dir():
        print("ERRO: a pasta de producao nao existe.")
        return CODIGO_ERRO

    if args.diario:
        return rodar_diario(producao, simular=args.simular)

    agora = agora_manaus()
    if args.primeira_vez and robo_rodando(idade_trava_robo(producao, agora.timestamp())):
        print("ERRO: o robo esta rodando (trava do bap_automation). Espere ele terminar.")
        return CODIGO_LIMITE_ROBO

    temp: Path | None = None
    sha: str | None = None
    try:
        if args.origem is None:
            temp = Path(tempfile.mkdtemp(prefix="bap_main_"))
            origem = temp / "main"
            print("Baixando o main do GitHub...")
            info: dict = {}
            try:
                datas = baixar_main(origem, info=info)
            except (OSError, zipfile.BadZipFile) as erro:
                print(f"ERRO ao baixar o main ({type(erro).__name__}): {erro}")
                return CODIGO_ERRO
            sha = info.get("sha")

            def data_main(rel: PurePath) -> float:
                return datas[rel]
        else:
            origem = args.origem.resolve()
            if not origem.is_dir():
                print("ERRO: a pasta de origem nao existe.")
                return CODIGO_ERRO
            if origem == producao:
                print("ERRO: origem e producao sao a mesma pasta.")
                return CODIGO_ERRO
            usa_git = _git_disponivel(origem)
            if usa_git:
                print("Atualizando a origem (git pull --ff-only)...")
                r = subprocess.run(["git", "-C", str(origem), "pull", "--ff-only"],
                                   capture_output=True, text=True, check=False)
                if r.returncode != 0:
                    print("ERRO: git pull --ff-only falhou na origem.")
                    return CODIGO_ERRO
                sha = _sha_git(origem)

            def data_main(rel: PurePath) -> float:
                if usa_git:
                    d = _data_git(origem, rel)
                    if d is not None:
                        return d
                return (origem / rel).stat().st_mtime

        try:
            plano = planejar(origem, producao, data_main)
        except (OSError, ValueError) as erro:
            print(f"ERRO ao comparar ({type(erro).__name__}): {erro}")
            return CODIGO_ERRO
        codigo = executar(plano, producao, assunto, args.simular, agora.date(),
                          ignorar_trava=args.primeira_vez,
                          backup_total=args.primeira_vez)
        modo = "primeira-vez" if args.primeira_vez else "manual"
        if codigo == CODIGO_OK and not args.simular and sha:
            try:
                gravar_versao(producao, sha, agora, len(plano.a_trocar), modo)
            except OSError as erro:
                print(f"AVISO: VERSAO_INSTALADA.txt nao gravado ({type(erro).__name__}).")
        if args.primeira_vez and not args.simular:
            nomes = ", ".join(r.name for r in plano.a_trocar) or "nenhum"
            registrar(producao, linha_log(agora, modo, codigo,
                                          f"trocados: {nomes}", sha))
        return codigo
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
