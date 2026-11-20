"""Usuários e perfis: senha com scrypt + sal, bloqueio após 5 erros."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

from .arquivos import gravar_json
from .config import Config, ConfigErro

PERFIS = ("admin", "diretor", "gerente")
MAX_ERROS = 5
BLOQUEIO_S = 15 * 60
SENHA_MIN = 10
_LOGIN = re.compile(r"^[a-z0-9._-]{3,40}$")
_N, _R, _P = 2 ** 14, 8, 1


def hash_senha(senha: str, sal: bytes | None = None) -> tuple[str, str]:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return h.hex(), sal.hex()


def confere_senha(senha: str, hash_hex: str, sal_hex: str) -> bool:
    h, _ = hash_senha(senha, bytes.fromhex(sal_hex))
    return hmac.compare_digest(h, hash_hex)


class Erro(ValueError):
    pass


class Usuarios:
    def __init__(self, cfg: Config):
        self.caminho = cfg.dados / "usuarios.json"
        self.trava = threading.Lock()
        if not self.caminho.exists():
            if not cfg.admin_usuario or not cfg.admin_senha:
                raise ConfigErro("Sem usuarios.json e sem BAP_ADMIN_USUARIO / "
                                 "BAP_ADMIN_SENHA_INICIAL: não há como criar o primeiro admin.")
            if not _LOGIN.match(cfg.admin_usuario):
                raise ConfigErro("BAP_ADMIN_USUARIO inválido (3-40: a-z 0-9 . _ -).")
            self._dados = {"usuarios": {}}
            self._novo(cfg.admin_usuario, cfg.admin_senha, "admin", trocar=True)
            self._salvar()
        else:
            self._dados = json.loads(self.caminho.read_text(encoding="utf-8"))

    def _salvar(self):
        gravar_json(self.caminho, self._dados, indent=1)

    def _novo(self, login, senha, perfil, trocar=True):
        h, s = hash_senha(senha)
        self._dados["usuarios"][login] = {
            "hash": h, "sal": s, "perfil": perfil, "ativo": True,
            "trocar_senha": trocar, "erros": 0, "bloqueado_ate": 0}

    # ---- consulta
    def obter(self, login: str) -> dict | None:
        u = self._dados["usuarios"].get((login or "").lower())
        return None if u is None else {"login": login.lower(), **{
            k: u[k] for k in ("perfil", "ativo", "trocar_senha", "bloqueado_ate", "erros")}}

    def listar(self) -> list[dict]:
        return [self.obter(l) for l in sorted(self._dados["usuarios"])]

    # ---- login
    def autenticar(self, login: str, senha: str, agora=None) -> tuple[dict | None, str]:
        """(usuario, motivo). motivo: ok | invalido | bloqueado."""
        agora = agora if agora is not None else time.time()
        login = (login or "").strip().lower()
        with self.trava:
            u = self._dados["usuarios"].get(login)
            if u is None or not u["ativo"]:
                hash_senha(senha or "")           # gasta o mesmo tempo
                return None, "invalido"
            if u["bloqueado_ate"] > agora:
                return None, "bloqueado"
            if confere_senha(senha or "", u["hash"], u["sal"]):
                u["erros"], u["bloqueado_ate"] = 0, 0
                self._salvar()
                return self.obter(login), "ok"
            u["erros"] += 1
            if u["erros"] >= MAX_ERROS:
                u["bloqueado_ate"] = agora + BLOQUEIO_S
                u["erros"] = 0
                self._salvar()
                return None, "bloqueado"
            self._salvar()
            return None, "invalido"

    # ---- administração
    @staticmethod
    def _checa_senha(senha: str):
        if len(senha or "") < SENHA_MIN:
            raise Erro(f"A senha precisa de pelo menos {SENHA_MIN} caracteres.")

    def criar(self, login: str, senha: str, perfil: str):
        login = (login or "").strip().lower()
        if not _LOGIN.match(login):
            raise Erro("Usuário inválido (3 a 40 caracteres: a-z, 0-9, ponto, _ e -).")
        if perfil not in PERFIS:
            raise Erro("Perfil inválido.")
        self._checa_senha(senha)
        with self.trava:
            if login in self._dados["usuarios"]:
                raise Erro("Esse usuário já existe.")
            self._novo(login, senha, perfil, trocar=True)
            self._salvar()

    def definir_ativo(self, login: str, ativo: bool):
        with self.trava:
            u = self._dados["usuarios"].get(login)
            if u is None:
                raise Erro("Usuário não encontrado.")
            if not ativo and u["perfil"] == "admin" and sum(
                    1 for x in self._dados["usuarios"].values()
                    if x["perfil"] == "admin" and x["ativo"]) <= 1:
                raise Erro("Não dá para desativar o último admin ativo.")
            u["ativo"] = ativo
            self._salvar()

    def trocar_senha(self, login: str, senha: str, *, exigir_troca: bool):
        """exigir_troca=True quando o admin define (o usuário troca no 1º acesso)."""
        self._checa_senha(senha)
        with self.trava:
            u = self._dados["usuarios"].get(login)
            if u is None:
                raise Erro("Usuário não encontrado.")
            u["hash"], u["sal"] = hash_senha(senha)
            u["trocar_senha"] = exigir_troca
            u["erros"], u["bloqueado_ate"] = 0, 0
            self._salvar()
