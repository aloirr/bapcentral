"""Gravação atômica de JSON (tmp + fsync + os.replace)."""
from __future__ import annotations

import json
import os
import tempfile
import zlib
from pathlib import Path


def gravar_json(caminho: Path, obj, indent=None) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, caminho)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def gravar_bytes(caminho: Path, dados: bytes) -> None:
    """Gravação atômica de bytes (tmp + fsync + os.replace), arquivo só do dono (0600)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(f".tmp-{os.getpid()}-{caminho.name}")
    try:
        with open(tmp, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, caminho)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def acrescentar_linha(caminho: Path, reg: dict) -> None:
    """Uma linha JSON no fim do arquivo (só acréscimo), com flush e fsync."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


class GzipGrande(Exception):
    """A saída passou do teto (bomba de gzip)."""


class GzipInvalido(Exception):
    """O corpo não é um gzip completo."""


def descomprimir_com_teto(bruto: bytes, maximo: int) -> bytes:
    """gzip com teto de saída: levanta GzipGrande ou GzipInvalido (quem chama escolhe o status)."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    saida, resto, total = [], bruto, 0
    try:
        while resto:
            parte = d.decompress(resto, maximo + 1 - total)
            total += len(parte)
            if total > maximo:
                raise GzipGrande
            saida.append(parte)
            resto = d.unconsumed_tail
        parte = d.flush()
    except zlib.error as e:
        raise GzipInvalido from e
    if total + len(parte) > maximo:
        raise GzipGrande
    if not d.eof:
        raise GzipInvalido
    saida.append(parte)
    return b"".join(saida)
