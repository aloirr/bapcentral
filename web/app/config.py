"""Configuração só por variável de ambiente (segredos nunca no código)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

TZ_ALVO = "America/Manaus"


class ConfigErro(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    dados: Path
    segredo: str
    token: str
    admin_usuario: str
    admin_senha: str
    pacote_max: int
    cookie_seguro: bool


def carregar() -> Config:
    segredo = os.environ.get("SESSION_SECRET", "")
    if len(segredo) < 16:
        raise ConfigErro("SESSION_SECRET ausente ou curto (mínimo 16 caracteres): "
                         "o app não sobe sem ele. Crie-o no painel do Render.")
    if len(os.environ.get("BAP_WEB_TOKEN", "")) < 32:
        raise ConfigErro("BAP_WEB_TOKEN ausente ou curto (mínimo 32 caracteres): "
                         "o app não sobe sem ele. Crie-o no painel do Render.")
    dados = os.environ.get("BAP_WEB_DADOS", "")
    if not dados:
        raise ConfigErro("BAP_WEB_DADOS ausente (pasta do disco, ex.: /var/data).")
    try:
        mb = float(os.environ.get("BAP_WEB_PACOTE_MAX_MB", "2"))
    except ValueError as e:
        raise ConfigErro("BAP_WEB_PACOTE_MAX_MB inválido.") from e
    return Config(
        dados=Path(dados),
        segredo=segredo,
        token=os.environ.get("BAP_WEB_TOKEN", ""),
        admin_usuario=os.environ.get("BAP_ADMIN_USUARIO", "").strip().lower(),
        admin_senha=os.environ.get("BAP_ADMIN_SENHA_INICIAL", ""),
        pacote_max=int(mb * 1024 * 1024),
        cookie_seguro=os.environ.get("BAP_WEB_COOKIE_SEGURO", "1") != "0",
    )
