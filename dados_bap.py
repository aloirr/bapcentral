# -*- coding: utf-8 -*-
"""
A FOTOGRAFIA DAS ABAS DE DADOS DA TABELA_BAP (nov/2026)
=======================================================

(05/11, Alexandre: "coloque o python para calcular as formulas. TABELA_BAP
fica uma saida" - em CSV compactado.)

O robo abria, gravava, salvava e mandava o Excel recalcular a TABELA_BAP
(15 MB, 104 MB por dentro) em TODA rodada: uns 4 minutos de 12. Agora:

  * a 1a rodada do dia (ou sem fotografia valida, ou --completa) continua
    IGUAL a de sempre - abre, grava, salva, o Excel recalcula - e no fim
    tira a FOTOGRAFIA das 7 abas de dados;
  * as outras rodadas NAO abrem a TABELA_BAP: montam as 7 abas em memoria a
    partir da fotografia, gravam os relatorios novos com as MESMAS rotinas
    de sempre, calculam as formulas aqui (com a regra do Excel) e gravam a
    fotografia nova;
  * quem le a TABELA_BAP (xlsx_rapido.abrir / load_workbook de leitura) recebe
    as 7 abas da fotografia e as de cadastro do .xlsx.

ONDE FICA
    RELATORIOS\\DADOS\\<aba>.csv.gz     uma por aba de dados
    RELATORIOS\\DADOS\\_estado.json     a rodada, as linhas, as formulas

O CSV (UTF-8, separador ";", compactado com gzip)
    linha 1   o cabecalho da aba (a linha 1 da planilha)
    linha 2   o TIPO de cada coluna (o tipo que mais aparece nela):
                s texto   i inteiro   f numero com casas   d data e hora
                h hora    t duracao   b verdadeiro/falso   - coluna vazia
    linha 3+  as linhas 2, 3, ... da planilha, TODAS as colunas, na ordem

    Campo vazio = celula vazia (None). Celula de tipo diferente do da coluna
    leva prefixo "~<tipo>:" (ex.: "~f:1.5" numa coluna i, "~s:" = texto
    vazio, "~s:~abc" = texto que comeca com ~). Assim o valor volta EXATO:
    int e float distintos, zeros a esquerda ("000123" e texto), data como
    datetime. Formatos de cada tipo:
        i  "123"            f  repr do float ("0.30000000000000004")
        d  "2026-05-18T10:11:12.346000"         h  "10:30:00"
        t  "dias:segundos:microssegundos"       b  "1" / "0"
    O cabecalho (linha 1) e lido como se a coluna fosse s.

O _estado.json
    formato, gerada_em, carimbo, maquina, rodada (completa/rapida),
    completa_em (a ultima rodada completa), xlsx_base (o CRC das 7 abas
    dentro do .xlsx no momento da fotografia - se a TABELA_BAP for salva por
    outra pessoa/programa, a fotografia deixa de valer ate a proxima rodada)
    e, por aba: arquivo, bytes, sha256, linhas (max_row), colunas
    (max_column), calculadas (as colunas com formula, como o robo as ve),
    formulas (os MODELOS por coluna, com "#" no lugar do numero da linha, e
    em que linhas valem), datas (as celulas com formato de data).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import socket
import time
import zipfile
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

FORMATO = 1
SUBPASTA = "DADOS"                     # ao lado da TABELA_BAP (RELATORIOS)
ARQ_ESTADO = "_estado.json"
NOME_TABELA = "TABELA_BAP.xlsx"
# As abas que o robo grava (dados dos relatorios). As outras abas sao de
# CADASTRO e continuam vivendo so no Excel.
ABAS_DADOS = ["dClientesBap", "ftTitulos", "ftEstoqueBap", "ftPedidos",
              "ftEstoquePMZ", "ftNCC", "ftTabelaPreco"]
# Desliga a leitura pela fotografia (volta a ler so o .xlsx)
VARIAVEL_DESLIGAR = "BAP_SEM_FOTOGRAFIA"
TENTATIVAS_TROCA = 12                  # arquivo travado: 12 x 2,5 s
csv.field_size_limit(1 << 30)


class NaoSuportado(Exception):
    """Algo que o calculo daqui nao sabe fazer IGUAL ao Excel: a rodada
    rapida desiste e o robo faz a completa (o Excel resolve)."""


# =============================================================================
# 1. COMO O EXCEL TRANSFORMA VALOR (os _xl_* que eram do bap_automation)
# =============================================================================
VAZIO_XL = ""                  # o "" que a formula devolvia
_EPOCA_XL = datetime(1899, 12, 30)


def _xl_texto(valor) -> str:
    """Como o Excel transforma um valor em texto ao concatenar (&, CONCAT)."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, datetime):
        dias = (valor - _EPOCA_XL).total_seconds() / 86400.0
        return _xl_texto(dias)
    if isinstance(valor, date):
        return str((datetime(valor.year, valor.month, valor.day)
                    - _EPOCA_XL).days)
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return f"{valor:.15g}"
    return str(valor)


def _xl_trim(valor) -> str:
    """TRIM do Excel: tira as pontas e junta espacos repetidos no meio."""
    return re.sub(r" {2,}", " ", _xl_texto(valor).strip(" "))


def _xl_vazio(valor) -> bool:
    return _xl_trim(valor) == ""


def _xl_value(valor):
    """VALUE do Excel para os codigos de nota e pedido. None = erro."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return valor
    texto = _xl_trim(valor)
    if re.fullmatch(r"[+-]?\d+", texto):
        return int(texto)
    if re.fullmatch(r"[+-]?\d*\.\d+", texto):
        return float(texto)
    return None


def _xl_numero(valor) -> float:
    """O numero de uma celula usada numa conta. Texto vira 0 (como SUMIFS)."""
    if isinstance(valor, bool):
        return float(valor)
    if isinstance(valor, (int, float)):
        return float(valor)
    return 0.0


def _xl_serial(valor):
    """
    DATA_NF_NUM / DT_PED_NUM: a data como numero do Excel.
    =IFERROR(IF(ISNUMBER(x), x, DATE(RIGHT 4, MID 4 2, LEFT 2)), 0)
    """
    if isinstance(valor, bool):
        return 0
    if isinstance(valor, datetime):
        dias = (valor - _EPOCA_XL).total_seconds() / 86400.0
        return int(dias) if float(dias).is_integer() else dias
    if isinstance(valor, date):
        return (datetime(valor.year, valor.month, valor.day) - _EPOCA_XL).days
    if isinstance(valor, (int, float)):
        return valor
    texto = _xl_trim(valor)
    try:
        ano = _xl_value(texto[-4:])
        mes = _xl_value(texto[3:5])
        dia = _xl_value(texto[:2])
        if None in (ano, mes, dia) or len(texto) < 4:
            return 0
        return (datetime(int(ano), int(mes), int(dia)) - _EPOCA_XL).days
    except (ValueError, OverflowError):
        return 0


def _xl_chave(valor):
    """
    Chave de busca com a regra do Excel: texto nao diferencia maiuscula, e
    texto nao casa com numero ("10483" e diferente de 10483).
    """
    if valor is None or (isinstance(valor, str) and valor == ""):
        return None
    if isinstance(valor, bool):
        return ("b", valor)
    if isinstance(valor, (int, float)):
        return ("n", float(valor))
    if isinstance(valor, (datetime, date)):
        return ("n", float(_xl_serial(valor)))
    return ("s", str(valor).lower())


def _xl_limpo(valor):
    """Inteiro que veio como float (46.0) volta a ser inteiro na planilha."""
    if isinstance(valor, float) and valor.is_integer() and abs(valor) < 1e15:
        return int(valor)
    return valor


# =============================================================================
# 2. O VALOR COMO ELE VOLTA DEPOIS DE GRAVADO (openpyxl -> Excel -> leitura)
# =============================================================================
# A rodada completa grava com o openpyxl, o Excel recalcula e salva, e quem
# le recebe o que esta no arquivo. A rodada rapida nao grava arquivo nenhum,
# entao imita aqui o caminho de ida e volta - para a fotografia sair igual:
#   * numero: o openpyxl escreve com 16 algarismos ("%.16g") e o Excel
#     guarda o que leu (escreve com 17, que voltam exatos). 46.0 vira 46
#     (inteiro), 0.30000000000000004 vira 0.3;
#   * numero em celula com FORMATO DE DATA volta como data (o leitor
#     converte) - e o caso da DATA_DEV do ftPedidos;
#   * data/hora volta arredondada no milissegundo (from_excel);
#   * texto vazio volta como celula vazia; CR vira LF (o XML normaliza);
#   * texto que comeca com "=" o openpyxl grava como FORMULA - so o Excel
#     sabe o resultado: NaoSuportado (a rodada vira completa).
_ILEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _numero_do_texto(txt: str):
    if "." in txt or "E" in txt or "e" in txt:
        return float(txt)
    return int(txt)


def _de_excel(num, tipo_data: str):
    from openpyxl.utils.datetime import CALENDAR_WINDOWS_1900, from_excel
    try:
        return from_excel(num, CALENDAR_WINDOWS_1900,
                          timedelta=(tipo_data == "t"))
    except (OverflowError, ValueError):
        return "#VALUE!"


def como_volta_gravado(valor, tipo_data: str | None = None):
    """O valor de uma celula SEM formula depois de gravado pelo openpyxl,
    salvo pelo Excel e lido de volta. tipo_data: 'd' (formato de data),
    't' (formato de duracao) ou None."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        if valor == "":
            return None
        if valor.startswith("="):
            raise NaoSuportado(f"texto que vira formula: {valor[:40]!r}")
        if _ILEGAL_XML.search(valor):
            raise NaoSuportado("caractere que o Excel nao grava")
        if "\r" in valor:
            valor = valor.replace("\r\n", "\n").replace("\r", "\n")
        return valor
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and (valor != valor or
                                         valor in (float("inf"),
                                                   float("-inf"))):
            return None
        num = _numero_do_texto("%.16g" % valor)
        if tipo_data:
            return _de_excel(num, tipo_data)
        return num
    if isinstance(valor, (datetime, date, dtime, timedelta)):
        from openpyxl.utils.datetime import CALENDAR_WINDOWS_1900, to_excel
        num = _numero_do_texto("%.16g" % to_excel(valor,
                                                  CALENDAR_WINDOWS_1900))
        return _de_excel(num, "t" if isinstance(valor, timedelta) else "d")
    raise NaoSuportado(f"tipo de valor {type(valor).__name__}")


def resultado_de_formula(valor, tipo_data: str | None = None):
    """O resultado de uma formula como o leitor o recebe do arquivo salvo
    pelo Excel (que escreve o numero com 17 algarismos: volta exato)."""
    if isinstance(valor, _Erro):
        return valor.codigo
    if valor is None:
        return 0                       # =A1 com A1 vazia da 0
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        if valor == "":
            return None                # <v></v>: o leitor devolve None
        if "\r" in valor:
            valor = valor.replace("\r\n", "\n").replace("\r", "\n")
        return valor
    if isinstance(valor, (datetime, date)):
        valor = _xl_serial(valor)
    if isinstance(valor, (int, float)):
        if tipo_data:
            return _de_excel(_xl_limpo(float(valor)), tipo_data)
        return _xl_limpo(float(valor))
    raise NaoSuportado(f"resultado {type(valor).__name__}")


# =============================================================================
# 3. O CSV: tipos e codificacao
# =============================================================================
def _codigo(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "b"
    if isinstance(v, int):
        return "i"
    if isinstance(v, float):
        return "f"
    if isinstance(v, str):
        return "s"
    if isinstance(v, datetime):
        return "d"
    if isinstance(v, dtime):
        return "h"
    if isinstance(v, timedelta):
        return "t"
    raise TypeError(f"tipo sem codigo na fotografia: {type(v).__name__}")


def _cru(v, cod: str) -> str:
    if cod == "s":
        return v
    if cod == "i":
        return str(v)
    if cod == "f":
        return repr(v)
    if cod == "d":
        return v.isoformat()
    if cod == "h":
        return v.isoformat()
    if cod == "t":
        return f"{v.days}:{v.seconds}:{v.microseconds}"
    if cod == "b":
        return "1" if v else "0"
    raise TypeError(cod)


def _do_cru(txt: str, cod: str):
    if cod == "s":
        return txt
    if cod == "i":
        return int(txt)
    if cod == "f":
        return float(txt)
    if cod == "d":
        return datetime.fromisoformat(txt)
    if cod == "h":
        return dtime.fromisoformat(txt)
    if cod == "t":
        d, s, us = txt.split(":")
        return timedelta(days=int(d), seconds=int(s), microseconds=int(us))
    if cod == "b":
        return txt == "1"
    raise ValueError(f"tipo desconhecido na fotografia: {cod!r}")


def _campo(v, cod_col: str) -> str:
    if v is None:
        return ""
    cod = _codigo(v)
    if cod == cod_col:
        txt = _cru(v, cod)
        if cod == "s" and (txt == "" or txt.startswith("~")):
            return "~s:" + txt
        return txt
    return f"~{cod}:{_cru(v, cod)}"


def _valor(campo: str, cod_col: str):
    if campo == "":
        return None
    if campo[0] == "~":
        cod, _, resto = campo[1:].partition(":")
        return _do_cru(resto, cod)
    return _do_cru(campo, cod_col)


def tipos_das_colunas(linhas, largura: int) -> list[str]:
    """O tipo que mais aparece em cada coluna (sem o cabecalho)."""
    contagem = [defaultdict(int) for _ in range(largura)]
    for r in linhas[1:]:
        for j, v in enumerate(r):
            if v is not None:
                contagem[j][_codigo(v)] += 1
    return [max(c.items(), key=lambda x: x[1])[0] if c else "-"
            for c in contagem]


def gravar_csv(destino: Path, linhas, largura: int) -> tuple[list, int]:
    """Grava a aba (linhas = tuplas, a 1a e o cabecalho) em .csv.gz.
    Devolve (tipos, linhas gravadas)."""
    tipos = tipos_das_colunas(linhas, largura)
    # gzip sem data nem nome no cabecalho: o mesmo conteudo da sempre o
    # mesmo arquivo (o mesmo sha256)
    with open(destino, "wb") as bruto, \
            gzip.GzipFile(filename="", mode="wb", compresslevel=5,
                          fileobj=bruto, mtime=0) as gz, \
            io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        cab = linhas[0] if linhas else ()
        w.writerow([_campo(v, "s") for v in cab] +
                   [""] * (largura - len(cab)))
        w.writerow(tipos)
        for r in linhas[1:]:
            if len(r) != largura:
                raise ValueError("linha com largura diferente da aba")
            w.writerow([_campo(v, tipos[j]) for j, v in enumerate(r)])
    return tipos, len(linhas)


def ler_csv(arquivo: Path, largura: int | None = None) -> list[tuple]:
    """As linhas da aba (tuplas, a 1a e o cabecalho), com os tipos de volta."""
    with gzip.open(arquivo, "rt", encoding="utf-8", newline="") as f:
        return _ler_csv_texto(f, largura)


def _ler_csv_texto(f, largura=None) -> list[tuple]:
    rd = csv.reader(f, delimiter=";")
    cab = next(rd)
    tipos = next(rd)
    n = len(tipos)
    if largura is not None and n != largura:
        raise ValueError("largura do CSV diferente da do _estado.json")
    saida = [tuple(_valor(c, "s") for c in cab)]
    # um conversor por coluna: o campo sem prefixo vai direto
    conv = []
    for cod in tipos:
        conv.append({"s": str, "i": int, "f": float,
                     "d": datetime.fromisoformat, "-": None}.get(cod))
    # o mesmo texto vira o MESMO objeto (como o texto compartilhado do
    # .xlsx): sem isto a aba lida da fotografia ocupava quase o dobro da
    # memoria da lida do .xlsx
    textos = {}
    for campos in rd:
        if len(campos) != n:
            raise ValueError("linha com largura diferente no CSV")
        linha = []
        for j, c in enumerate(campos):
            if not c:
                linha.append(None)
            elif c[0] == "~" or conv[j] is None:
                v = _valor(c, tipos[j])
                if isinstance(v, str):
                    v = textos.setdefault(v, v)
                linha.append(v)
            elif conv[j] is str:
                linha.append(textos.setdefault(c, c))
            else:
                linha.append(conv[j](c))
        saida.append(tuple(linha))
    return saida


# =============================================================================
# 4. A PASTA, O ESTADO E A GRAVACAO ATOMICA
# =============================================================================
def pasta_dados(caminho_tabela) -> Path:
    return Path(caminho_tabela).resolve().parent / SUBPASTA


def _sha256(arq: Path) -> str:
    h = hashlib.sha256()
    with open(arq, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _trocar(origem: Path, destino: Path) -> None:
    """os.replace com paciencia: no Windows, arquivo aberto por outro
    programa (o BAP Central lendo) nao deixa ser trocado na hora."""
    for tentativa in range(TENTATIVAS_TROCA):
        try:
            os.replace(origem, destino)
            return
        except PermissionError:
            if tentativa == TENTATIVAS_TROCA - 1:
                raise
            time.sleep(2.5)


def ler_estado(pasta: Path) -> dict | None:
    try:
        with open(Path(pasta) / ARQ_ESTADO, "r", encoding="utf-8") as f:
            est = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(est, dict) or est.get("formato") != FORMATO:
        return None
    return est


def invalidar(pasta: Path, motivo: str = "") -> bool:
    """Tira a fotografia de circulacao (os leitores voltam ao .xlsx). Nao
    apaga os CSVs: renomeia o _estado.json (guarda os 5 ultimos). O motivo
    fica no log de quem chamou."""
    arq = Path(pasta) / ARQ_ESTADO
    if not arq.exists():
        return False
    destino = arq.with_name(f"_estado_invalido_{datetime.now():%Y%m%d_%H%M%S}"
                            ".json")
    try:
        _trocar(arq, destino)
    except OSError:
        try:
            arq.unlink()
        except OSError:
            return False
    try:
        for velho in sorted(Path(pasta).glob("_estado_invalido_*.json"))[:-5]:
            velho.unlink(missing_ok=True)
    except OSError:
        pass
    _VALIDA_CACHE.clear()
    return True


def gravar_fotografia(pasta: Path, abas: dict, estrutura: dict,
                      xlsx_base: dict, rodada: str,
                      completa_em: str | None = None,
                      ordem: list | None = None, extra: dict | None = None
                      ) -> dict:
    """
    Grava a fotografia: abas = {aba: linhas (tuplas, a 1a e o cabecalho,
    todas da mesma largura)}, estrutura = {aba: {calculadas, formulas,
    datas}}. Tudo vai primeiro para .tmp; o _estado.json e o ULTIMO a ser
    trocado - quem le antes disso continua com a fotografia anterior
    inteira (os sha256 conferem cada arquivo).
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    # .tmp de outra gravacao que morreu no meio (outro processo): mais de 1
    # hora parado, sai
    limite = time.time() - 3600
    for velho in pasta.glob("*.tmp"):
        try:
            if velho.stat().st_mtime < limite:
                velho.unlink()
        except OSError:
            pass
    agora = datetime.now()
    carimbo = f"{time.time_ns()}"
    est = {
        "formato": FORMATO,
        "gerada_em": agora.isoformat(timespec="seconds"),
        "carimbo": carimbo,
        "maquina": os.environ.get("COMPUTERNAME") or socket.gethostname(),
        "rodada": rodada,
        "completa_em": completa_em or agora.isoformat(timespec="seconds"),
        "xlsx_base": xlsx_base,
        "ordem": list(ordem or []),
        "abas": {},
    }
    if extra:
        est.update(extra)
    temporarios = []
    try:
        for aba, linhas in abas.items():
            info = dict(estrutura.get(aba) or {})
            largura = info.get("colunas") or (len(linhas[0]) if linhas else 0)
            nome = f"{aba}.csv.gz"
            tmp = pasta / f"{nome}.{os.getpid()}.tmp"
            tipos, n = gravar_csv(tmp, linhas, largura)
            temporarios.append((tmp, pasta / nome))
            info.update({"arquivo": nome, "linhas": n, "colunas": largura,
                         "bytes": tmp.stat().st_size, "sha256": _sha256(tmp),
                         "tipos": "".join(tipos)})
            est["abas"][aba] = info
        tmp_est = pasta / f"{ARQ_ESTADO}.{os.getpid()}.tmp"
        with open(tmp_est, "w", encoding="utf-8") as f:
            json.dump(est, f, ensure_ascii=False, indent=1, default=str)
        temporarios.append((tmp_est, pasta / ARQ_ESTADO))
        for i, (tmp, final) in enumerate(temporarios):
            try:
                _trocar(tmp, final)
            except OSError:
                # metade trocada: a fotografia velha nao confere mais com
                # os arquivos - sai de circulacao (o .xlsx volta a valer)
                if i:
                    invalidar(pasta, "troca pela metade")
                raise
    finally:
        for tmp, _ in temporarios:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
        _VALIDA_CACHE.clear()
    return est


def ler_aba(pasta: Path, est: dict, aba: str, conferir: bool = True
            ) -> list[tuple]:
    """As linhas da aba da fotografia (a 1a e o cabecalho). Confere o sha256
    e o tamanho; qualquer diferenca levanta ValueError."""
    info = est["abas"][aba]
    arq = Path(pasta) / info["arquivo"]
    bruto = arq.read_bytes()
    if conferir:
        if len(bruto) != info["bytes"] or \
                hashlib.sha256(bruto).hexdigest() != info["sha256"]:
            raise ValueError(f"{arq.name} nao confere com o _estado.json")
    with gzip.open(io.BytesIO(bruto), "rt", encoding="utf-8",
                   newline="") as f:
        linhas = _ler_csv_texto(f, info["colunas"])
    if len(linhas) != info["linhas"]:
        raise ValueError(f"{arq.name}: {len(linhas)} linhas, esperava "
                         f"{info['linhas']}")
    return linhas


# =============================================================================
# 5. A TABELA_BAP: o CRC das abas de dados (sem abrir as abas)
# =============================================================================
def abas_do_zip(z: zipfile.ZipFile) -> dict:
    """{nome da aba: caminho da aba dentro do .xlsx}."""
    from html import unescape
    wbxml = z.read("xl/workbook.xml").decode("utf-8")
    rels = {}
    try:
        rx = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    except KeyError:
        rx = ""
    for m in re.finditer(r"<(?:\w+:)?Relationship\b([^>]*)/?>", rx):
        a = m.group(1)
        i = re.search(r'\bId="([^"]+)"', a)
        t = re.search(r'\bTarget="([^"]+)"', a)
        if i and t:
            alvo = unescape(t.group(1))
            alvo = alvo[1:] if alvo.startswith("/") else "xl/" + alvo
            partes = []
            for p in alvo.split("/"):
                if p == "..":
                    if partes:
                        partes.pop()
                elif p and p != ".":
                    partes.append(p)
            rels[i.group(1)] = "/".join(partes)
    saida = {}
    for m in re.finditer(r"<(?:\w+:)?sheet\b([^>]*)/?>", wbxml):
        a = m.group(1)
        nome = re.search(r'\bname="([^"]*)"', a)
        rid = re.search(r'\br:id="([^"]+)"', a) or re.search(
            r'\b\w+:id="([^"]+)"', a)
        if nome and rid and rid.group(1) in rels:
            saida[unescape(nome.group(1))] = rels[rid.group(1)]
    return saida


def base_do_xlsx(caminho) -> dict:
    """O que identifica as abas de dados DENTRO do .xlsx: {aba: [crc, bytes]}
    (o diretorio do zip - le poucos KB, nao abre aba nenhuma)."""
    with zipfile.ZipFile(caminho) as z:
        mapa = abas_do_zip(z)
        saida = {}
        for aba in ABAS_DADOS:
            p = mapa.get(aba)
            if p is None:
                saida[aba] = None
                continue
            i = z.getinfo(p)
            saida[aba] = [i.CRC, i.file_size]
        saida["_abas"] = list(mapa)
    return saida


_VALIDA_CACHE: dict = {}


def fotografia_para(caminho_xlsx, conferir_xlsx: bool = True) -> dict | None:
    """
    O _estado.json da fotografia que VALE para esta TABELA_BAP, ou None:
      - o arquivo se chama TABELA_BAP.xlsx e tem RELATORIOS\\DADOS ao lado;
      - BAP_SEM_FOTOGRAFIA nao esta ligada;
      - o formato e o desta versao e os 7 arquivos existem com o tamanho
        anotado;
      - as abas de dados dentro do .xlsx sao as MESMAS de quando a
        fotografia foi tirada (CRC): a TABELA_BAP salva por outra pessoa ou
        programa depois disso faz o leitor voltar a ela.
    """
    if os.environ.get(VARIAVEL_DESLIGAR):
        return None
    caminho = Path(caminho_xlsx)
    if caminho.name.lower() != NOME_TABELA.lower():
        return None
    pasta = caminho.resolve().parent / SUBPASTA
    arq_est = pasta / ARQ_ESTADO
    try:
        st_e = arq_est.stat()
        st_x = caminho.stat()
    except OSError:
        return None
    chave = (str(arq_est), st_e.st_mtime_ns, st_e.st_size,
             st_x.st_mtime_ns, st_x.st_size, conferir_xlsx)
    if chave in _VALIDA_CACHE:
        return _VALIDA_CACHE[chave]
    est = ler_estado(pasta)
    ok = est is not None
    if ok:
        try:
            for aba, info in est["abas"].items():
                if (pasta / info["arquivo"]).stat().st_size != info["bytes"]:
                    ok = False
                    break
        except (OSError, KeyError, TypeError):
            ok = False
    if ok and conferir_xlsx:
        try:
            base = base_do_xlsx(caminho)
            anotada = est.get("xlsx_base") or {}
            ok = all(base.get(a) == (anotada.get(a) and list(anotada[a]))
                     for a in ABAS_DADOS)
        except (OSError, zipfile.BadZipFile, KeyError):
            ok = False
    saida = est if ok else None
    if len(_VALIDA_CACHE) > 20:
        _VALIDA_CACHE.clear()
    _VALIDA_CACHE[chave] = saida
    if saida is not None:
        saida["_pasta"] = str(pasta)
    return saida


# =============================================================================
# 6. AS FORMULAS: modelo por coluna ("#" = numero da linha)
# =============================================================================
_RE_REF = re.compile(r"(?<![A-Za-z0-9_$.])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\d(])")


def _pedacos_fora_de_texto(formula: str):
    """[(trecho, esta_dentro_de_aspas)]"""
    partes, i, n = [], 0, len(formula)
    while i < n:
        j = formula.find('"', i)
        if j < 0:
            partes.append((formula[i:], False))
            break
        partes.append((formula[i:j], False))
        k = j + 1
        while True:
            k = formula.find('"', k)
            if k < 0:
                k = n
                break
            if k + 1 < n and formula[k + 1] == '"':
                k += 2
                continue
            break
        partes.append((formula[j:k + 1], True))
        i = k + 1
    return partes


def modelo_da_formula(formula: str, linha: int) -> str | None:
    """'=BD12-(BV12)' na linha 12 -> '=BD#-(BV#)'. None = nao da modelo
    (tem '#' proprio, como #REF!)."""
    saida = []
    for trecho, texto in _pedacos_fora_de_texto(formula):
        if texto:
            saida.append(trecho)
            continue
        if "#" in trecho:
            return None

        def troca(m):
            if m.group(3) == "" and int(m.group(4)) == linha:
                return f"{m.group(1)}{m.group(2)}#"
            return m.group(0)
        saida.append(_RE_REF.sub(troca, trecho))
    return "".join(saida)


def formula_do_modelo(modelo: str, linha: int) -> str:
    n = str(linha)
    return "".join(t if dentro else t.replace("#", n)
                   for t, dentro in _pedacos_fora_de_texto(modelo))


def _faixas(linhas: list[int]) -> list[list[int]]:
    linhas = sorted(linhas)
    saida = []
    for r in linhas:
        if saida and r == saida[-1][1] + 1:
            saida[-1][1] = r
        else:
            saida.append([r, r])
    return saida


def estrutura_de_formulas(celulas: dict) -> dict:
    """celulas = {(linha, coluna): texto | ('matriz', ref, texto)} ->
    {"colunas": {col: [[modelo, faixas], ...]}, "excecoes": [[l, c, texto]],
     "matriz": [[l, c, ref, texto]]}"""
    por_coluna = defaultdict(lambda: defaultdict(list))
    excecoes, matriz = [], []
    for (r, c), f in celulas.items():
        if isinstance(f, tuple):
            matriz.append([r, c, f[1], f[2]])
            continue
        m = modelo_da_formula(f, r)
        if m is None or formula_do_modelo(m, r) != f:
            excecoes.append([r, c, f])
            continue
        por_coluna[c][m].append(r)
    colunas = {}
    for c, modelos in por_coluna.items():
        colunas[str(c)] = [[m, _faixas(rs)] for m, rs in modelos.items()]
    return {"colunas": colunas, "excecoes": sorted(excecoes),
            "matriz": sorted(matriz)}


def celulas_de_formula(estr: dict) -> dict:
    """O contrario de estrutura_de_formulas."""
    saida = {}
    for c, modelos in (estr.get("colunas") or {}).items():
        c = int(c)
        for modelo, faixas in modelos:
            for a, b in faixas:
                for r in range(a, b + 1):
                    saida[(r, c)] = formula_do_modelo(modelo, r)
    for r, c, f in estr.get("excecoes") or []:
        saida[(r, c)] = f
    for r, c, ref, f in estr.get("matriz") or []:
        saida[(r, c)] = ("matriz", ref, f)
    return saida


def formulas_do_ws(ws) -> dict:
    """As formulas de uma aba do openpyxl (aberta com data_only=False)."""
    from openpyxl.worksheet.formula import ArrayFormula
    saida = {}
    for (r, c), cel in ws._cells.items():
        v = cel._value
        if isinstance(v, str):
            if cel.data_type == "f" and v.startswith("="):
                saida[(r, c)] = v
        elif isinstance(v, ArrayFormula):
            saida[(r, c)] = ("matriz", v.ref, v.text)
    return saida


# --- as celulas com formato de data ----------------------------------------
def mascara_de_datas(ws) -> dict:
    """{col: {"d": faixas, "t": faixas}} das celulas com formato de data
    (d) ou de duracao (t) - o leitor devolve datetime/timedelta para o
    numero que estiver nelas."""
    from openpyxl.styles.numbers import is_date_format, is_timedelta_format
    por_id = {}
    linhas = defaultdict(lambda: defaultdict(list))
    for (r, c), cel in ws._cells.items():
        if not cel.has_style:
            continue
        fid = cel._style.numFmtId
        tipo = por_id.get(fid, 0)
        if tipo == 0:
            fmt = cel.number_format
            tipo = ("t" if is_timedelta_format(fmt) else
                    "d" if is_date_format(fmt) else None)
            por_id[fid] = tipo
        if tipo:
            linhas[c][tipo].append(r)
    return {str(c): {t: _faixas(rs) for t, rs in tipos.items()}
            for c, tipos in linhas.items()}


class Mascara:
    """Consulta rapida da mascara de datas: tipo(linha, coluna)."""

    def __init__(self, dados: dict | None):
        self.faixas = {}
        for c, tipos in (dados or {}).items():
            lst = []
            for t, fx in tipos.items():
                lst += [(a, b, t) for a, b in fx]
            lst.sort()
            self.faixas[int(c)] = ([a for a, _, _ in lst], lst)

    def tipo(self, r: int, c: int):
        f = self.faixas.get(c)
        if not f:
            return None
        i = bisect_right(f[0], r) - 1
        if i >= 0:
            a, b, t = f[1][i]
            if a <= r <= b:
                return t
        return None

    def como_dict(self) -> dict:
        saida = {}
        for c, (_, lst) in self.faixas.items():
            tipos = defaultdict(list)
            for a, b, t in lst:
                tipos[t] += list(range(a, b + 1))
            saida[str(c)] = {t: _faixas(rs) for t, rs in tipos.items()}
        return saida

    def acrescentar(self, celulas: dict):
        """celulas = {(r, c): tipo}: junta e refaz as faixas."""
        if not celulas:
            return
        base = self.como_dict()
        por = defaultdict(lambda: defaultdict(set))
        for c, tipos in base.items():
            for t, fx in tipos.items():
                for a, b in fx:
                    por[int(c)][t].update(range(a, b + 1))
        for (r, c), t in celulas.items():
            for outro in list(por[c]):
                if outro != t:
                    por[c][outro].discard(r)
            por[c][t].add(r)
        novo = {str(c): {t: _faixas(list(rs)) for t, rs in tipos.items() if rs}
                for c, tipos in por.items()}
        self.__init__(novo)


def colunas_calculadas(ws, linha_cabecalho: int = 1,
                       amostra: int = 40) -> list[int]:
    """A MESMA conta do bap_automation.colunas_calculadas (as 40 primeiras
    linhas de dados): e o que o robo e a solicitacao usam para pular as
    colunas de formula."""
    formulas = set()
    primeira = linha_cabecalho + 1
    ultima = min(ws.max_row, primeira + amostra - 1)
    if ultima < primeira:
        return []
    for linha in ws.iter_rows(min_row=primeira, max_row=ultima):
        for celula in linha:
            if isinstance(celula.value, str) and celula.value.startswith("="):
                formulas.add(celula.column)
    return sorted(formulas)


# =============================================================================
# 7. O CALCULO DAS FORMULAS (a regra do Excel, so o que a TABELA_BAP usa)
# =============================================================================
class _Erro:
    __slots__ = ("codigo",)

    def __init__(self, codigo):
        self.codigo = codigo

    def __repr__(self):
        return self.codigo


_NA = _Erro("#N/A")
_VALUE = _Erro("#VALUE!")
_NAME = _Erro("#NAME?")
_MAX_LINHAS = 1048576


def _col_num(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n


_TOKEN = re.compile(r"""
    (?P<espaco>\s+)
  | (?P<texto>"(?:[^"]|"")*")
  | (?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)!)?
            (?:\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?
              |\$?[A-Z]{1,3}:\$?[A-Z]{1,3}))(?![\w(])
  | (?P<numero>\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)
  | (?P<funcao>[A-Za-z_][\w.]*)\(
  | (?P<op><>|<=|>=|[-+*/&=<>(),])
""", re.X)


def _tokens(txt: str):
    i, saida = 0, []
    while i < len(txt):
        m = _TOKEN.match(txt, i)
        if not m:
            raise NaoSuportado(f"formula que nao sei ler: {txt[:60]!r}")
        i = m.end()
        tipo = m.lastgroup
        if tipo != "espaco":
            saida.append((tipo, m.group(tipo)))
    return saida


class _Parser:
    def __init__(self, txt):
        self.t = _tokens(txt)
        self.i = 0

    def ver(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def tirar(self):
        tok = self.ver()
        self.i += 1
        return tok

    def expr(self):
        no = self.termo()
        while self.ver()[1] in ("+", "-", "&"):
            op = self.tirar()[1]
            no = ("bin", op, no, self.termo())
        return no

    def termo(self):
        no = self.fator()
        while self.ver()[1] in ("*", "/"):
            op = self.tirar()[1]
            no = ("bin", op, no, self.fator())
        return no

    def fator(self):
        tipo, v = self.tirar()
        if tipo == "op" and v == "-":
            return ("neg", self.fator())
        if tipo == "op" and v == "+":
            return self.fator()
        if tipo == "op" and v == "(":
            no = self.expr()
            if self.tirar()[1] != ")":
                raise NaoSuportado("parentese")
            return no
        if tipo == "numero":
            return ("const", float(v) if any(ch in v for ch in ".eE")
                    else int(v))
        if tipo == "texto":
            return ("const", v[1:-1].replace('""', '"'))
        if tipo == "ref":
            return ("ref", _ler_ref(v))
        if tipo == "funcao":
            args = []
            if self.ver()[1] == ")":
                self.tirar()
                return ("func", v.upper(), args)
            while True:
                if self.ver()[1] in (",", ")"):
                    args.append(("vazio",))
                else:
                    args.append(self.expr())
                sep = self.tirar()[1]
                if sep == ")":
                    break
                if sep != ",":
                    raise NaoSuportado("argumento")
            return ("func", v.upper(), args)
        raise NaoSuportado(f"pedaco de formula: {v!r}")


def _ler_ref(txt: str):
    folha = None
    if "!" in txt:
        folha, txt = txt.rsplit("!", 1)
        if folha.startswith("'"):
            folha = folha[1:-1].replace("''", "'")
    txt = txt.replace("$", "")
    if ":" in txt:
        a, b = txt.split(":")
        ma = re.fullmatch(r"([A-Z]+)(\d*)", a)
        mb = re.fullmatch(r"([A-Z]+)(\d*)", b)
        c1, c2 = _col_num(ma.group(1)), _col_num(mb.group(1))
        r1 = int(ma.group(2)) if ma.group(2) else 1
        r2 = int(mb.group(2)) if mb.group(2) else _MAX_LINHAS
        if _SENTINELA in (r1, r2):
            raise NaoSuportado("faixa que anda com a linha")
        return ("faixa", folha, c1, r1, c2, r2)
    m = re.fullmatch(r"([A-Z]+)(\d+)", txt)
    return ("celula", folha, _col_num(m.group(1)), int(m.group(2)))


_ARVORES: dict = {}
# a formula de um MODELO e lida uma vez so, com esta linha no lugar do "#";
# na conta, a referencia a ela vira a linha da celula
_SENTINELA = 9999999


def _arvore(formula: str):
    a = _ARVORES.get(formula)
    if a is None:
        p = _Parser(formula[1:] if formula.startswith("=") else formula)
        a = p.expr()
        if p.i != len(p.t):
            raise NaoSuportado(f"sobrou pedaco: {formula[:60]!r}")
        if len(_ARVORES) > 5000:
            _ARVORES.clear()
        _ARVORES[formula] = a
    return a


_RE_INTEIRO = re.compile(r"\s*[+-]?\d+\s*")
_RE_AMBIGUO = re.compile(r"\s*[+-]?[\d.,]+%?\s*|\s*\d{1,4}[/-]\d{1,2}"
                         r"(?:[/-]\d{1,4})?\s*|\s*\d{1,2}:\d{2}(?::\d{2})?\s*")


def _texto_numerico(s: str):
    """O numero que o Excel enxerga num TEXTO de criterio/celula (COUNTIFS
    compara '000123' com 123 pelo numero). So inteiro e seguro; decimal,
    data e hora dependem do idioma do Excel -> NaoSuportado."""
    if _RE_INTEIRO.fullmatch(s):
        return float(int(s))
    if _RE_AMBIGUO.fullmatch(s) and any(ch.isdigit() for ch in s):
        raise NaoSuportado(f"texto que parece numero/data: {s!r}")
    return None


class _Contexto:
    """As abas (valores ja como o leitor ve) e os indices de busca."""

    def __init__(self, valores: dict):
        self.valores = valores            # {aba: [linhas]} (linha 1 = cab)
        self._indices = {}

    def celula(self, folha, r, c):
        linhas = self.valores.get(folha)
        if linhas is None:
            raise NaoSuportado(f"aba {folha!r} fora do calculo")
        if r - 1 < len(linhas):
            linha = linhas[r - 1]
            if c - 1 < len(linha):
                return linha[c - 1]
        return None

    def coluna(self, folha, c, r1=1, r2=_MAX_LINHAS):
        linhas = self.valores.get(folha)
        if linhas is None:
            raise NaoSuportado(f"aba {folha!r} fora do calculo")
        fim = min(r2, len(linhas))
        return [(linhas[r - 1][c - 1] if c - 1 < len(linhas[r - 1])
                 else None) for r in range(r1, fim + 1)]


def _como_numero(v):
    """Operando de conta (+ - * /): o que o Excel faz com cada tipo."""
    if isinstance(v, _Erro):
        return v
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (datetime, date)):
        return float(_xl_serial(v))
    if isinstance(v, str):
        if v.strip() == "":
            return _VALUE
        if _texto_numerico(v) is not None:
            raise NaoSuportado("conta com texto numerico")
        return _VALUE
    raise NaoSuportado(f"conta com {type(v).__name__}")


def _como_texto(v):
    if isinstance(v, _Erro):
        return v
    if isinstance(v, bool):
        raise NaoSuportado("verdadeiro/falso concatenado (idioma do Excel)")
    if isinstance(v, (dtime, timedelta)):
        raise NaoSuportado("hora concatenada")
    if isinstance(v, float) and not v.is_integer() and abs(v) >= 1e15:
        raise NaoSuportado("numero grande concatenado")
    if isinstance(v, (int, float)) and abs(v) >= 1e15:
        raise NaoSuportado("numero grande concatenado")
    return _xl_texto(v)


class _Criterio:
    """Um criterio de SUMIFS/COUNTIFS/MAXIFS com a regra do Excel."""

    def __init__(self, v):
        if isinstance(v, _Erro):
            raise NaoSuportado("criterio com erro")
        self.op, self.num, self.txt = "=", None, None
        # a "forma" do valor (texto ou numero) - para conferir, no indice,
        # se o Excel poderia casar por numero o que por texto nao casa
        if isinstance(v, str):
            self.forma = ("t", v.strip().lower())
        elif isinstance(v, (datetime, date)):
            self.forma = ("n", float(_xl_serial(v)))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            self.forma = ("n", float(v))
        else:
            self.forma = ("n", 0.0)
        if v is None:
            self.num = 0.0         # celula vazia como criterio vale 0
            return
        if isinstance(v, bool):
            raise NaoSuportado("criterio verdadeiro/falso")
        if isinstance(v, (int, float)):
            self.num = float(v)
            return
        if isinstance(v, (datetime, date)):
            self.num = float(_xl_serial(v))
            return
        s = str(v)
        for p in ("<=", ">=", "<>", "<", ">", "="):
            if s.startswith(p):
                self.op, s = p, s[len(p):]
                break
        n = _texto_numerico(s)
        if n is not None:
            self.num = n
            return
        if any(ch in s for ch in "*?~"):
            raise NaoSuportado("criterio com curinga")
        if self.op not in ("=", "<>"):
            raise NaoSuportado("criterio de texto com < >")
        if s.upper() in ("TRUE", "FALSE", "VERDADEIRO", "FALSO"):
            raise NaoSuportado("criterio verdadeiro/falso")
        self.txt = s.lower()

    def chave(self):
        """Para indice: so criterio de igualdade."""
        if self.op != "=":
            return None
        return ("n", self.num) if self.num is not None else ("s", self.txt)

    def casa(self, x) -> bool:
        if self.num is not None:
            if isinstance(x, bool) or x is None or isinstance(x, _Erro):
                xn = None
            elif isinstance(x, (int, float)):
                xn = float(x)
            elif isinstance(x, (datetime, date)):
                xn = float(_xl_serial(x))
            elif isinstance(x, str):
                xn = _texto_numerico(x)
            else:
                xn = None
            if xn is None:
                return self.op == "<>"
            return {"=": xn == self.num, "<>": xn != self.num,
                    ">": xn > self.num, "<": xn < self.num,
                    ">=": xn >= self.num, "<=": xn <= self.num}[self.op]
        # texto
        if self.txt == "":
            vazio = x is None or x == ""
            return vazio if self.op == "=" else not vazio
        igual = isinstance(x, str) and _texto_numerico(x) is None and \
            x.lower() == self.txt
        return igual if self.op == "=" else not igual


def _chave_de_celula(x):
    """A chave de igualdade de uma celula na faixa de criterio (o mesmo que
    _Criterio.chave devolveria para quem casa com ela)."""
    if x is None or isinstance(x, bool) or isinstance(x, _Erro):
        return None
    if isinstance(x, (int, float)):
        return ("n", float(x))
    if isinstance(x, (datetime, date)):
        return ("n", float(_xl_serial(x)))
    if isinstance(x, str):
        n = _texto_numerico(x)
        if n is not None:
            return ("n", n)
        return ("s", x.lower())
    return None


def _ifs(ctx: _Contexto, func: str, args, folha, linha):
    """SUMIFS / COUNTIFS / MAXIFS com indice por chave."""
    if func == "COUNTIFS":
        alvo, pares = None, args
    else:
        alvo, pares = args[0], args[1:]
    if len(pares) % 2:
        raise NaoSuportado("criterios impares")
    faixas, criterios = [], []
    for k in range(0, len(pares), 2):
        f = pares[k]
        if f[0] != "ref" or f[1][0] != "faixa":
            raise NaoSuportado("criterio sem faixa")
        faixas.append(f[1])
        criterios.append(_Criterio(_avaliar(ctx, pares[k + 1], folha, linha)))
    if alvo is not None and (alvo[0] != "ref" or alvo[1][0] != "faixa"):
        raise NaoSuportado("faixa de soma")
    # o indice: as faixas e os criterios FIXOS (os de texto/numero literal)
    # sao os mesmos em todas as linhas; os que vem de celula entram na chave
    assinatura = (func, alvo[1] if alvo else None, tuple(faixas),
                  tuple(isinstance(pares[k + 1], tuple) and
                        pares[k + 1][0] == "const" and
                        _avaliar(ctx, pares[k + 1], folha, linha)
                        for k in range(0, len(pares), 2)))
    variaveis = [k // 2 for k in range(0, len(pares), 2)
                 if pares[k + 1][0] != "const"]
    fixos = [k // 2 for k in range(0, len(pares), 2)
             if pares[k + 1][0] == "const"]
    usar_indice = all(criterios[j].chave() is not None for j in variaveis)
    if usar_indice:
        indice = ctx._indices.get(assinatura)
        if indice is None:
            indice = _montar_indice(ctx, faixas, criterios, fixos, variaveis,
                                    alvo)
            ctx._indices[assinatura] = indice
        chave = tuple(criterios[j].chave() for j in variaveis)
        grupo, formas = indice
        fs = formas.get(chave)
        if fs and (len(fs) > 1 or
                   tuple(criterios[j].forma for j in variaveis) not in fs):
            raise NaoSuportado("chave que o Excel pode casar por numero"
                               " e por texto")
        valores = grupo.get(chave, [])
    else:
        valores = _varrer(ctx, faixas, criterios, alvo)
    return _fechar_ifs(func, valores)


def _faixa_valores(ctx, fx):
    _, folha, c1, r1, c2, r2 = fx
    if c1 != c2:
        raise NaoSuportado("faixa com mais de uma coluna")
    return ctx.coluna(folha, c1, r1, r2)


def _montar_indice(ctx, faixas, criterios, fixos, variaveis, alvo):
    colunas = [_faixa_valores(ctx, f) for f in faixas]
    alvo_v = _faixa_valores(ctx, alvo[1]) if alvo else None
    n = max(len(c) for c in colunas)
    grupo = defaultdict(list)
    formas = defaultdict(set)          # chave -> formas de texto que casam
    for i in range(n):
        ok = True
        for j in fixos:
            x = colunas[j][i] if i < len(colunas[j]) else None
            if not criterios[j].casa(x):
                ok = False
                break
        if not ok:
            continue
        chave, forma = [], []
        for j in variaveis:
            x = colunas[j][i] if i < len(colunas[j]) else None
            k = _chave_de_celula(x)
            if k is None:
                chave = None
                break
            chave.append(k)
            forma.append(("t", x.strip().lower()) if isinstance(x, str)
                         else ("n", float(_xl_serial(x)) if isinstance(
                             x, (datetime, date)) else float(x)))
        if chave is None:
            continue
        v = alvo_v[i] if alvo_v is not None and i < len(alvo_v) else None
        grupo[tuple(chave)].append(v)
        formas[tuple(chave)].add(tuple(forma))
    # chave numerica que junta formas diferentes ("01" e "1", 1 e "1"): o
    # Excel casa pelo numero, mas e facil errar - quem cair nela desiste
    return dict(grupo), dict(formas)


def _varrer(ctx, faixas, criterios, alvo):
    colunas = [_faixa_valores(ctx, f) for f in faixas]
    alvo_v = _faixa_valores(ctx, alvo[1]) if alvo else None
    n = max(len(c) for c in colunas)
    saida = []
    for i in range(n):
        if all(criterios[j].casa(colunas[j][i] if i < len(colunas[j])
                                 else None) for j in range(len(faixas))):
            saida.append(alvo_v[i] if alvo_v is not None and
                         i < len(alvo_v) else None)
    return saida


def _fechar_ifs(func, valores):
    if func == "COUNTIFS":
        return len(valores)
    nums = []
    for v in valores:
        if isinstance(v, _Erro):
            return v
        if isinstance(v, bool) or v is None or isinstance(v, str):
            continue
        if isinstance(v, (int, float)):
            nums.append(float(v))
        elif isinstance(v, (datetime, date)):
            nums.append(float(_xl_serial(v)))
    if func == "SUMIFS":
        total = 0.0
        for x in nums:
            total += x
        return total
    return max(nums) if nums else 0.0          # MAXIFS


def _xlookup(ctx, args, folha, linha):
    if len(args) < 3:
        raise NaoSuportado("XLOOKUP sem argumentos")
    procura = _avaliar(ctx, args[0], folha, linha)
    if isinstance(procura, _Erro):
        return procura
    if args[1][0] != "ref" or args[2][0] != "ref":
        raise NaoSuportado("XLOOKUP sem faixa")
    if len(args) > 3 and args[3][0] != "vazio":
        raise NaoSuportado("XLOOKUP com se_nao_achar")
    if len(args) > 4:
        modo = _avaliar(ctx, args[4], folha, linha) if args[4][0] != "vazio" \
            else 0
        if modo not in (0, 0.0):
            raise NaoSuportado("XLOOKUP com modo diferente de exato")
    if len(args) > 5:
        raise NaoSuportado("XLOOKUP com modo de busca")
    fa, fr = args[1][1], args[2][1]
    if fa[0] != "faixa" or fr[0] != "faixa" or fa[2] != fa[4] or \
            fr[2] != fr[4] or fa[3] != fr[3]:
        raise NaoSuportado("XLOOKUP com faixas diferentes")
    chave_idx = ("XLOOKUP", fa, fr)
    idx = ctx._indices.get(chave_idx)
    if idx is None:
        procurar = _faixa_valores(ctx, fa)
        devolver = _faixa_valores(ctx, fr)
        primeiro = {}
        primeiro_vazio = None
        for i, x in enumerate(procurar):
            if x is None:
                if primeiro_vazio is None:
                    primeiro_vazio = i
                continue
            k = _xl_chave(x)
            if k is not None and k not in primeiro:
                primeiro[k] = i
        if primeiro_vazio is None:
            # a faixa e a coluna inteira: depois da ultima linha so ha vazio
            primeiro_vazio = len(procurar) if fa[5] > fa[3] + len(
                procurar) - 1 else None
        idx = (primeiro, primeiro_vazio, devolver)
        ctx._indices[chave_idx] = idx
    primeiro, primeiro_vazio, devolver = idx
    if procura is None:
        i = primeiro_vazio
    else:
        if isinstance(procura, bool):
            raise NaoSuportado("XLOOKUP de verdadeiro/falso")
        i = primeiro.get(_xl_chave(procura))
    if i is None:
        return _NA
    v = devolver[i] if i < len(devolver) else None
    return v


def _avaliar(ctx: _Contexto, no, folha, linha):
    tipo = no[0]
    if tipo == "const":
        return no[1]
    if tipo == "vazio":
        return None
    if tipo == "ref":
        ref = no[1]
        if ref[0] != "celula":
            raise NaoSuportado("faixa fora de funcao")
        r = linha if ref[3] == _SENTINELA else ref[3]
        return ctx.celula(ref[1] or folha, r, ref[2])
    if tipo == "neg":
        v = _como_numero(_avaliar(ctx, no[1], folha, linha))
        return v if isinstance(v, _Erro) else -v
    if tipo == "bin":
        op = no[1]
        a = _avaliar(ctx, no[2], folha, linha)
        b = _avaliar(ctx, no[3], folha, linha)
        if op == "&":
            a, b = _como_texto(a), _como_texto(b)
            for x in (a, b):
                if isinstance(x, _Erro):
                    return x
            return a + b
        a, b = _como_numero(a), _como_numero(b)
        for x in (a, b):
            if isinstance(x, _Erro):
                return x
        if op == "+":
            r = a + b
        elif op == "-":
            r = a - b
        elif op == "*":
            return a * b
        else:
            if b == 0:
                return _Erro("#DIV/0!")
            return a / b
        # o Excel zera o resultado de + e - que sobra so como erro de
        # arredondamento; quando isso pode acontecer, o Excel decide
        if r != 0 and max(abs(a), abs(b)) > 0 and \
                abs(r) < max(abs(a), abs(b)) * 2.0 ** -48:
            raise NaoSuportado("soma/subtracao no limite da precisao")
        return r
    if tipo == "func":
        nome, args = no[1], no[2]
        base = nome.split(".")[-1] if nome.startswith("_XLFN.") else nome
        if nome.startswith("_XLUDF."):
            return _NAME                 # funcao que o Excel nao conhece
        if base in ("SUMIFS", "COUNTIFS", "MAXIFS"):
            return _ifs(ctx, base, args, folha, linha)
        if base == "CONCAT":
            partes = []
            for a in args:
                if a[0] == "ref" and a[1][0] == "faixa":
                    raise NaoSuportado("CONCAT de faixa")
                t = _como_texto(_avaliar(ctx, a, folha, linha))
                if isinstance(t, _Erro):
                    return t
                partes.append(t)
            return "".join(partes)
        if base == "IFERROR":
            v = _avaliar(ctx, args[0], folha, linha)
            if isinstance(v, _Erro):
                return _avaliar(ctx, args[1], folha, linha) if \
                    len(args) > 1 else ""
            return v
        if base == "XLOOKUP":
            return _xlookup(ctx, args, folha, linha)
        if base == "SUBSTITUTE" and len(args) == 3:
            t = _como_texto(_avaliar(ctx, args[0], folha, linha))
            de = _como_texto(_avaliar(ctx, args[1], folha, linha))
            para = _como_texto(_avaliar(ctx, args[2], folha, linha))
            for x in (t, de, para):
                if isinstance(x, _Erro):
                    return x
            return t.replace(de, para) if de else t
        raise NaoSuportado(f"funcao {nome}")
    raise NaoSuportado(f"no {tipo}")


def calcular_formulas(valores: dict, formulas: dict,
                      datas: dict | None = None) -> dict:
    """
    As formulas das abas, com a regra do Excel.

      valores  {aba: [linhas]} - o que o leitor ve (linha 1 = cabecalho).
               Nas celulas de formula o valor e ignorado. As abas que as
               formulas consultam (ftTitulos, ProdutosBAP...) tem de estar.
      formulas {aba: {(linha, coluna): texto | ('matriz', ref, texto)}}
      datas    {aba: Mascara} - celula de formula com formato de data
               devolve datetime, como o leitor.

    Devolve {aba: {(linha, coluna): valor como o leitor devolveria}}.
    Formula que nao da para calcular IGUAL ao Excel levanta NaoSuportado.
    As formulas destas abas so leem celulas de DADO (nao ha formula que
    dependa de formula) - se um dia houver, NaoSuportado.
    """
    ctx = _Contexto(valores)
    com_formula = {(aba, c) for aba, fs in formulas.items() for (_, c) in fs}
    saida = {}
    for aba, fs in formulas.items():
        masc = (datas or {}).get(aba)
        grupos = defaultdict(list)
        soltas = []
        for (r, c), f in fs.items():
            texto = f[2] if isinstance(f, tuple) else f
            m = modelo_da_formula(texto, r)
            if m is None:
                soltas.append((r, c, texto))
            else:
                grupos[m].append((r, c))
        res = {}
        for m, cels in grupos.items():
            arv = _arvore(formula_do_modelo(m, _SENTINELA))
            _conferir_dependencias(arv, aba, com_formula)
            for r, c in cels:
                v = _avaliar(ctx, arv, aba, r)
                res[(r, c)] = resultado_de_formula(
                    v, masc.tipo(r, c) if masc else None)
        for r, c, texto in soltas:
            arv = _arvore(texto)
            _conferir_dependencias(arv, aba, com_formula)
            v = _avaliar(ctx, arv, aba, r)
            res[(r, c)] = resultado_de_formula(
                v, masc.tipo(r, c) if masc else None)
        saida[aba] = res
    return saida


def _conferir_dependencias(arv, aba, com_formula):
    """Nenhuma formula pode ler uma COLUNA que tenha formula (o calculo
    daqui e de uma passada so)."""
    if arv[0] == "ref":
        ref = arv[1]
        folha = ref[1] or aba
        cols = [ref[2]] if ref[0] == "celula" else range(ref[2], ref[4] + 1)
        for c in cols:
            if (folha, c) in com_formula:
                raise NaoSuportado("formula que le coluna de formula")
        return
    for filho in arv[1:]:
        if isinstance(filho, tuple):
            _conferir_dependencias(filho, aba, com_formula)
        elif isinstance(filho, list):
            for x in filho:
                _conferir_dependencias(x, aba, com_formula)


# =============================================================================
# 8. A RODADA RAPIDA: o livro em memoria e a fotografia nova
# =============================================================================
def livro_em_memoria(pasta: Path, est: dict, caminho_xlsx,
                     abas_cadastro=("ProdutosBAP",)):
    """
    Um Workbook do openpyxl, so na memoria, com as 7 abas da fotografia -
    VALOR nas celulas de dado e o TEXTO DA FORMULA (do modelo) nas de
    formula, como o openpyxl entregaria abrindo a TABELA_BAP com
    data_only=False - mais as abas de cadastro que a gravacao consulta
    (lidas do .xlsx, do mesmo jeito: formula como texto).
    """
    from openpyxl import Workbook, load_workbook
    from openpyxl.cell.cell import Cell
    from openpyxl.worksheet.formula import ArrayFormula
    wb = Workbook()
    wb.remove(wb.active)
    ordem = [a for a in est.get("ordem") or [] if a in est["abas"]
             or a in abas_cadastro]
    ordem += [a for a in est["abas"] if a not in ordem]
    ro = None
    try:
        for aba in ordem:
            ws = wb.create_sheet(aba)
            celulas = ws._cells
            if aba in est["abas"]:
                info = est["abas"][aba]
                linhas = ler_aba(pasta, est, aba)
                formulas = celulas_de_formula(info.get("formulas") or {})
                for r, linha in enumerate(linhas, start=1):
                    for c, v in enumerate(linha, start=1):
                        if (r, c) in formulas:
                            continue
                        if v is not None:
                            celulas[(r, c)] = Cell(ws, row=r, column=c,
                                                   value=v)
                for (r, c), f in formulas.items():
                    if isinstance(f, tuple):
                        val = ArrayFormula(f[1], f[2])
                    else:
                        val = f
                    celulas[(r, c)] = Cell(ws, row=r, column=c, value=val)
            else:
                if ro is None:
                    ro = load_workbook(caminho_xlsx, read_only=True,
                                       data_only=False)
                if aba not in ro.sheetnames:
                    wb.remove(ws)
                    continue
                for r, linha in enumerate(ro[aba].iter_rows(
                        values_only=True), start=1):
                    for c, v in enumerate(linha, start=1):
                        if v is not None:
                            celulas[(r, c)] = Cell(ws, row=r, column=c,
                                                   value=v)
    finally:
        if ro is not None:
            ro.close()
    return wb


def _grade(ws, max_row, max_col):
    linhas = []
    cel = ws._cells
    for r in range(1, max_row + 1):
        linha = []
        for c in range(1, max_col + 1):
            x = cel.get((r, c))
            linha.append(None if x is None else x._value)
        linhas.append(linha)
    return linhas


def fotografia_do_livro(wb, est_ant: dict, resumos: list | None = None,
                        valores_cadastro: dict | None = None,
                        abas=None) -> tuple[dict, dict]:
    """
    Depois da gravacao no livro em memoria: os VALORES das 7 abas como o
    leitor os veria na TABELA_BAP salva e recalculada pelo Excel, e a
    estrutura nova (formulas, datas, calculadas, linhas, colunas).

    valores_cadastro = {aba: linhas} das abas de cadastro que as formulas
    consultam (os valores do .xlsx, ja recalculados pelo Excel).
    """
    abas = list(abas or [a for a in ABAS_DADOS if a in wb.sheetnames])
    resumos = {r["aba"]: r for r in (resumos or [])}
    valores, formulas, mascaras, estrutura = {}, {}, {}, {}
    for aba in abas:
        ws = wb[aba]
        info = (est_ant.get("abas") or {}).get(aba) or {}
        masc = Mascara(info.get("datas"))
        # linha nova clonada do modelo herda o formato do modelo
        rs = resumos.get(aba)
        novos = {}
        if rs and rs.get("linhas_incluidas") and rs.get("linhas_antes"):
            modelo = 1 + rs["linhas_antes"]
            for c in list(masc.faixas):
                t = masc.tipo(modelo, c)
                if t:
                    for r in range(modelo + 1,
                                   modelo + 1 + rs["linhas_incluidas"]):
                        novos[(r, c)] = t
        # data gravada pelo openpyxl leva formato de data
        fs = formulas_do_ws(ws)
        for (r, c), cel in ws._cells.items():
            v = cel._value
            if (r, c) in fs:
                continue
            if isinstance(v, timedelta):
                novos[(r, c)] = "t"
            elif isinstance(v, (datetime, date, dtime)):
                if masc.tipo(r, c) is None:
                    novos[(r, c)] = "d"
        masc.acrescentar(novos)
        max_row = max(info.get("linhas") or 0, ws.max_row)
        max_col = max(info.get("colunas") or 0, ws.max_column)
        grade = _grade(ws, max_row, max_col)
        for r, linha in enumerate(grade, start=1):
            for c, v in enumerate(linha, start=1):
                if (r, c) in fs:
                    linha[c - 1] = None
                else:
                    linha[c - 1] = como_volta_gravado(v, masc.tipo(r, c))
        valores[aba] = grade
        formulas[aba] = fs
        mascaras[aba] = masc
        estrutura[aba] = {
            "colunas": max_col,
            "calculadas": colunas_calculadas(ws, 1),
            "formulas": estrutura_de_formulas(fs),
            "datas": masc.como_dict(),
        }
    contexto = dict(valores)
    for aba, linhas in (valores_cadastro or {}).items():
        if aba not in contexto:
            contexto[aba] = linhas
    calc = calcular_formulas(contexto, formulas, mascaras)
    for aba, res in calc.items():
        grade = valores[aba]
        for (r, c), v in res.items():
            grade[r - 1][c - 1] = v
    return ({aba: [tuple(x) for x in grade] for aba, grade in
             valores.items()}, estrutura)


def estrutura_do_livro(wb, abas=None) -> dict:
    """A estrutura das abas de dados num livro do openpyxl aberto com
    data_only=False (a rodada completa, antes de salvar)."""
    abas = list(abas or [a for a in ABAS_DADOS if a in wb.sheetnames])
    saida = {}
    for aba in abas:
        ws = wb[aba]
        fs = formulas_do_ws(ws)
        saida[aba] = {
            "calculadas": colunas_calculadas(ws, 1),
            "formulas": estrutura_de_formulas(fs),
            "datas": mascara_de_datas(ws),
        }
    saida["_ordem"] = list(wb.sheetnames)
    return saida


def linhas_do_xlsx(caminho, abas) -> dict:
    """{aba: linhas} lidas do arquivo (valores em cache do Excel), pelo
    leitor rapido SEM a fotografia."""
    import xlsx_rapido as xr
    saida = {}
    wb = xr._Livro(caminho)                     # noqa: SLF001
    try:
        for aba in abas:
            if aba in wb.sheetnames:
                ws = wb[aba]
                saida[aba] = (list(ws.iter_rows(values_only=True)),
                              ws.max_row, ws.max_column)
    finally:
        wb.close()
    return saida


def fotografia_da_completa(caminho_recalculado, estrutura: dict,
                           excel_recalculou: bool) -> tuple[dict, dict, dict]:
    """
    A rodada completa: os valores vem do arquivo que o Excel acabou de
    recalcular (a verdade). Se o Excel nao recalculou, as formulas saem
    em branco no arquivo - entao vem do calculo daqui. Nos dois casos o
    calculo daqui e conferido contra o arquivo.
    Devolve (abas {aba: linhas}, estrutura {aba: ...}, conferencia).
    """
    abas = [a for a in ABAS_DADOS if a in estrutura]
    lidas = linhas_do_xlsx(caminho_recalculado, abas + ["ProdutosBAP"])
    valores, est_final, formulas, mascaras = {}, {}, {}, {}
    for aba in abas:
        linhas, max_row, max_col = lidas[aba]
        if any(len(r) != max_col for r in linhas) or len(linhas) != max_row:
            raise ValueError(f"aba {aba} sem dimensao regular")
        info = dict(estrutura[aba])
        info["colunas"] = max_col
        est_final[aba] = info
        valores[aba] = linhas
        formulas[aba] = celulas_de_formula(info["formulas"])
        mascaras[aba] = Mascara(info.get("datas"))
    conferencia = {"celulas": 0, "diferencas": 0, "exemplos": [],
                   "erro": ""}
    contexto = {a: [list(r) for r in v] for a, v in valores.items()}
    if "ProdutosBAP" in lidas:
        contexto["ProdutosBAP"] = lidas["ProdutosBAP"][0]
    for aba in abas:                 # as celulas de formula nao sao entrada
        for (r, c) in formulas[aba]:
            if r - 1 < len(contexto[aba]):
                contexto[aba][r - 1][c - 1] = None
    try:
        calc = calcular_formulas(contexto, formulas, mascaras)
    except NaoSuportado as erro:
        calc = None
        conferencia["erro"] = str(erro)
    if calc is not None and not excel_recalculou:
        conferencia["erro"] = ("o Excel nao recalculou: as formulas da "
                               "fotografia sao as calculadas em Python")
    elif calc is not None:
        for aba, res in calc.items():
            for (r, c), v in res.items():
                conferencia["celulas"] += 1
                excel = (valores[aba][r - 1][c - 1]
                         if r - 1 < len(valores[aba]) else None)
                if not mesmo_valor(v, excel):
                    conferencia["diferencas"] += 1
                    if len(conferencia["exemplos"]) < 10:
                        conferencia["exemplos"].append(
                            [aba, r, c, repr(excel), repr(v)])
    if not excel_recalculou:
        if calc is None:
            raise NaoSuportado("sem o Excel e sem calculo: " +
                               conferencia["erro"])
        for aba, res in calc.items():
            linhas = [list(r) for r in valores[aba]]
            for (r, c), v in res.items():
                linhas[r - 1][c - 1] = v
            valores[aba] = [tuple(x) for x in linhas]
    return valores, est_final, conferencia


def mesmo_valor(a, b) -> bool:
    """Igualdade de celula: mesmo tipo e mesmo valor (int != float)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float) and a != a and b != b:
        return True
    return a == b


# =============================================================================
# 9. CONFERENCIA: as formulas direto do XML (sem abrir o livro inteiro)
# =============================================================================
_RE_F = re.compile(r'<f\b([^>]*?)(?:/>|>(.*?)</f>)', re.S)


def formulas_do_arquivo(caminho, abas=None) -> dict:
    """{aba: {(linha, coluna): texto | ('matriz', ref, texto)}} lidas do XML
    do .xlsx, com as formulas compartilhadas traduzidas para cada celula -
    o mesmo que o openpyxl entrega com data_only=False. Para os testes e
    para conferir a fotografia contra a planilha."""
    from html import unescape
    from openpyxl.formula.translate import Translator
    abas = list(abas or ABAS_DADOS)
    saida = {}
    with zipfile.ZipFile(caminho) as z:
        mapa = abas_do_zip(z)
        for aba in abas:
            if aba not in mapa:
                continue
            xml = z.read(mapa[aba]).decode("utf-8")
            mestres, fs = {}, {}
            for m in _RE_F.finditer(xml):
                a_f, txt = m.group(1), m.group(2)
                ini = xml.rfind("<c ", 0, m.start())
                a_c = xml[ini:xml.find(">", ini)]
                ref = re.search(r'\br="([A-Z]+)(\d+)"', a_c)
                if not ref:
                    continue
                coord = ref.group(1) + ref.group(2)
                r, c = int(ref.group(2)), _col_num(ref.group(1))
                t = re.search(r'\bt="(\w+)"', a_f)
                t = t.group(1) if t else None
                if t == "array":
                    rf = re.search(r'\bref="([^"]+)"', a_f)
                    fs[(r, c)] = ("matriz", rf.group(1) if rf else coord,
                                  "=" + unescape(txt or ""))
                    continue
                if t == "shared":
                    si = re.search(r'\bsi="(\d+)"', a_f).group(1)
                    if txt:
                        mestres[si] = (coord, "=" + unescape(txt))
                        fs[(r, c)] = "=" + unescape(txt)
                    elif si in mestres:
                        orig, f = mestres[si]
                        fs[(r, c)] = Translator(f, origin=orig) \
                            .translate_formula(coord)
                    continue
                if txt is not None:
                    fs[(r, c)] = "=" + unescape(txt)
            saida[aba] = fs
    return saida
