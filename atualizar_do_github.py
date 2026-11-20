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
2 trava "instalado por fora" | 3 backup falhou | 4 troca falhou (restaurado).

``--assunto`` e opcional; o padrao e ``ATUALIZACAO`` (vira
``ANTES_ATUALIZACAO_<MES><ANO>``). Use o numero da tarefa, ex.: ``T0003``.

So biblioteca padrao (o PC do robo nao tem Git nem pacotes extras).
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path, PurePath

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


def hoje_manaus() -> date:
    """Data de hoje no fuso America/Manaus (fallback: UTC-4 fixo)."""
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        fuso = ZoneInfo("America/Manaus")
    except (ImportError, ZoneInfoNotFoundError, ValueError, OSError):  # sem tzdata
        fuso = timezone(timedelta(hours=-4))
    return datetime.now(fuso).date()


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
      ``mtime`` do arquivo instalado.
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

    @property
    def a_trocar(self) -> list[PurePath]:
        """Alterados e novos, nessa ordem."""
        return list(self.alterados) + list(self.novos)


def planejar(origem: Path, producao: Path,
             data_main: Callable[[PurePath], float]) -> Plano:
    """Compara ``origem`` (o ``main``) com ``producao``. Nao grava nada.

    ``data_main(rel)`` devolve a data (epoch, s) do ``main`` para o arquivo:
    commit (git), item do zip ou ``mtime`` na origem.
    """
    origem = Path(origem)
    producao = Path(producao)
    plano = Plano(origem=origem, producao=producao)
    for rel in candidatos(origem):
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


def executar(plano: Plano, producao: Path, assunto: str, simular: bool,
             hoje: date) -> int:
    """Aplica o plano (ou so mostra, com ``simular``). Devolve o codigo de saida."""
    producao = Path(producao)
    _imprimir_plano(plano)

    if plano.mais_novos_na_producao:
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

    backup = pasta_backup(producao, assunto, hoje) if plano.alterados else None

    if simular:
        print("\nSIMULACAO: nada foi gravado.")
        if backup is not None:
            print(f"Backup previsto: {_rel_producao(backup, producao)}"
                  f" ({len(plano.alterados)} arquivo(s))")
        else:
            print("Sem backup: so arquivos novos.")
        return CODIGO_OK

    # 7. Backup dos que serao substituidos.
    if backup is not None:
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.mkdir(exist_ok=False)
            for rel in plano.alterados:
                copia = backup / rel.name
                shutil.copy2(producao / rel, copia)
                if _sha256(copia) != plano.hash_producao[rel]:
                    raise OSError(f"hash do backup de {rel.name} nao confere")
        except OSError as erro:
            print(f"\nERRO NO BACKUP ({type(erro).__name__}): {erro}")
            print("Nada foi trocado.")
            return CODIGO_BACKUP
        print(f"\nBackup conferido: {_rel_producao(backup, producao)}"
              f" ({len(plano.alterados)} arquivo(s))")

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


def baixar_main(destino: Path, url: str = URL_ZIP_MAIN) -> dict[PurePath, float]:
    """Baixa o zip do ``main`` e extrai so os candidatos para ``destino``.

    Item excluido nao e extraido nem lido. Devolve a data de cada candidato.
    """
    destino.mkdir(parents=True, exist_ok=True)
    arq_zip = destino.parent / "main.zip"
    with urllib.request.urlopen(url, timeout=120) as resp, open(arq_zip, "wb") as f:
        shutil.copyfileobj(resp, f)
    datas: dict[PurePath, float] = {}
    with zipfile.ZipFile(arq_zip) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            partes = PurePath(info.filename).parts
            if len(partes) != 2:  # <raiz-do-zip>/<arquivo>: so a raiz do main
                continue
            rel = PurePath(partes[1])
            if not _eh_candidato_nome(rel):
                continue
            with z.open(info) as src, open(destino / rel.name, "wb") as out:
                shutil.copyfileobj(src, out)
            datas[rel] = _data_zip(info)
    return datas


def _git_disponivel(origem: Path) -> bool:
    return (origem / ".git").exists() and shutil.which("git") is not None


def _data_git(origem: Path, rel: PurePath) -> float | None:
    r = subprocess.run(
        ["git", "-C", str(origem), "log", "-1", "--format=%ct", "--", rel.name],
        capture_output=True, text=True, check=False)
    texto = r.stdout.strip()
    return float(texto) if r.returncode == 0 and texto.isdigit() else None


def _configurar_saida() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


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
    ap.add_argument("--assunto", default=ASSUNTO_PADRAO,
                    help=f"assunto do backup (padrao: {ASSUNTO_PADRAO})")
    ap.add_argument("--simular", action="store_true",
                    help="so mostra o plano; nao grava nada")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return CODIGO_OK if e.code == 0 else CODIGO_ERRO

    try:
        nome_backup(args.assunto, date(2000, 1, 1))
    except ValueError:
        print("ERRO: --assunto invalido (use letras, numeros e _).")
        return CODIGO_ERRO

    producao = args.producao.resolve()
    if not producao.is_dir():
        print("ERRO: a pasta de producao nao existe.")
        return CODIGO_ERRO

    temp: Path | None = None
    try:
        if args.origem is None:
            temp = Path(tempfile.mkdtemp(prefix="bap_main_"))
            origem = temp / "main"
            print("Baixando o main do GitHub...")
            try:
                datas = baixar_main(origem)
            except (OSError, zipfile.BadZipFile) as erro:
                print(f"ERRO ao baixar o main ({type(erro).__name__}): {erro}")
                return CODIGO_ERRO

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
        return executar(plano, producao, args.assunto, args.simular,
                        hoje_manaus())
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
