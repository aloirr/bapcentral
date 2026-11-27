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

from datetime import datetime
from zoneinfo import ZoneInfo

from . import acesso as ac
from .arquivos import acrescentar_linha, gravar_json
from .config import Config, ConfigErro

PERFIS = ("admin", "diretor", "gerente", "analista", "trade", "pos_venda", "pre_venda", "vendas")   # T-0017: 3 novos; T-0036: analista e trade (RN-GER-017)
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


class ErroGravacao(Erro):
    """Não deu para gravar (disco): a tela mostra 503."""


MSG_SEM_FAROL = "{login}: marque ao menos um farol. Para tirar todo o acesso, use Desativar."
MSG_LISTA_MUDOU = "A lista de faróis mudou. Abra a tela de novo e salve outra vez."
MSG_FALHA = "Não deu para salvar agora. Tente de novo em 1 minuto."
MANAUS = ZoneInfo("America/Manaus")


def _acesso_de(u: dict) -> dict:
    return {k: list((u.get("acesso") or {}).get(k, ())) for k in ("menos", "mais")}


class Usuarios:
    def __init__(self, cfg: Config):
        self.caminho = cfg.dados / "usuarios.json"
        self.registro = cfg.dados / "usuarios_acesso.jsonl"      # T-0050: só de acréscimo (RN-GER-018)
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
            "trocar_senha": trocar, "erros": 0, "bloqueado_ate": 0, "sessao": 0}

    # ---- consulta
    def obter(self, login: str) -> dict | None:
        u = self._dados["usuarios"].get((login or "").lower())
        return None if u is None else {"login": login.lower(), **{
            k: u[k] for k in ("perfil", "ativo", "trocar_senha", "bloqueado_ate", "erros")},
            "sessao": u.get("sessao", 0),
            "acesso": _acesso_de(u)}

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
                hash_senha(senha or "")           # não revela quem existe pelo tempo
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

    def criar(self, login: str, senha: str, perfil: str, marcados=None, quem: str = ""):
        """`marcados` (T-0050): faróis marcados na criação; None = o perfil puro."""
        login = (login or "").strip().lower()
        if not _LOGIN.match(login):
            raise Erro("Usuário inválido (3 a 40 caracteres: a-z, 0-9, ponto, _ e -).")
        if perfil not in PERFIS:
            raise Erro("Perfil inválido.")
        self._checa_senha(senha)
        with self.trava:
            if login in self._dados["usuarios"]:
                raise Erro("Esse usuário já existe.")
            exc = self._excecoes(login, perfil, marcados) if marcados is not None else None
            self._novo(login, senha, perfil, trocar=True)
            if exc and (exc["menos"] or exc["mais"]):
                self._dados["usuarios"][login]["acesso"] = exc
            try:
                self._gravar_com_registro(login, perfil, {}, exc or {}, quem, "criar")
            except ErroGravacao:
                self._dados["usuarios"].pop(login, None)
                raise

    def _excecoes(self, login, perfil, marcados, antigo=None) -> dict:
        marcados = set(marcados)
        try:
            exc = ac.excecoes(perfil, marcados, antigo)
        except ValueError:
            raise Erro(MSG_LISTA_MUDOU)
        if not marcados and ac.padrao_do_perfil(perfil):
            raise Erro(MSG_SEM_FAROL.format(login=login))
        return exc

    def _gravar_com_registro(self, alvo, perfil, antes, depois, quem, acao):
        """RN-GER-018: acrescenta as linhas do registro, grava o json; se o json falhar, acrescenta "desfeito"."""
        lote = secrets.token_hex(8)
        quando = datetime.now(MANAUS).isoformat(timespec="seconds")
        try:
            for rid, sinal, origem in ac.mudancas(perfil, antes, depois):
                acrescentar_linha(self.registro, {"quando": quando, "lote": lote, "quem": quem, "alvo": alvo,
                                                  "perfil": perfil, "rid": rid, "mudanca": sinal,
                                                  "origem": origem, "acao": acao})
            self._salvar()
        except OSError:
            try:
                acrescentar_linha(self.registro, {"quando": quando, "lote": lote, "acao": "desfeito"})
            except OSError:
                pass
            raise ErroGravacao(MSG_FALHA)

    def definir_acesso(self, alvo: str, marcados, quem: str = "") -> list[tuple[str, str, str]]:
        """Admin: o acesso do usuário vira `marcados` (rids). Devolve as mudanças [(rid, +/-, origem)]."""
        with self.trava:
            u = self._dados["usuarios"].get(alvo)
            if u is None:
                raise Erro("Usuário não encontrado.")
            antes = _acesso_de(u)
            depois = self._excecoes(alvo, u["perfil"], marcados, antes)
            mud = ac.mudancas(u["perfil"], antes, depois)
            if depois == antes:
                return []
            if depois == {"menos": [], "mais": []}:
                u.pop("acesso", None)
            else:
                u["acesso"] = depois
            try:
                self._gravar_com_registro(alvo, u["perfil"], antes, depois, quem, "editar")
            except ErroGravacao:
                u["acesso"] = antes
                raise
            return mud

    def ultima_mudanca(self, login: str) -> dict | None:
        """{"quando": ISO de Manaus, "quem": login} da última mudança de acesso do usuário (não desfeita)."""
        try:
            linhas = self.registro.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        regs, desfeitos = [], set()
        for ln in linhas:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("acao") == "desfeito":
                desfeitos.add(r.get("lote"))
            elif r.get("alvo") == login:
                regs.append(r)
        regs = [r for r in regs if r.get("lote") not in desfeitos]
        if not regs:
            return None
        r = regs[-1]
        return {"quando": r.get("quando", ""), "quem": r.get("quem", "")}     # a tela formata com o filtro `manaus`

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
            if not ativo:
                u["sessao"] = u.get("sessao", 0) + 1
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
            u["sessao"] = u.get("sessao", 0) + 1
            self._salvar()

    def encerrar_sessoes(self, login: str):
        """Logout no servidor: invalida todo cookie emitido antes (contador da sessão)."""
        with self.trava:
            u = self._dados["usuarios"].get((login or "").lower())
            if u is not None:
                u["sessao"] = u.get("sessao", 0) + 1
                self._salvar()
