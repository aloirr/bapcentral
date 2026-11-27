"""T-0055 (RN-GER-020): porta de leitura da web (leitura v1, contrato §10.12). Montagem, filtro e limite.

Quem pode ver (perfil diretor), os números e os textos vêm dos módulos que a tela já usa (`render`, `tabelas`):
nada é recalculado nem reformatado aqui. A montagem copia só as chaves da lista fechada e só aceita `valor` com número
e unidade; o corte por texto (dado pessoal, meta RH, TOTAL A PAGAR) fica todo em `limpar`. Nunca sai: tabela, nome,
documento, telefone ou e-mail de cliente/vendedor, meta RH, TOTAL A PAGAR. `Limite` é a única parte com estado."""
from __future__ import annotations

import re
import time
from collections import deque

from . import render, tabelas

VERSAO_LEITURA = 1
PERFIL = "diretor"
POR_IP, TOTAL, JANELA, MAX_IPS = 30, 120, 60.0, 1000       # proteção técnica (recomendação do gerente), não é RN

# só o que é da porta (RN-GER-001 e RN-GER-015); o resto da lista vem de `render.texto_proibido` (RD-0251)
_TOTAL_A_PAGAR = "TOTAL A PAGAR"
_SO_DA_PORTA = re.compile(rf"\bRH\b|{_TOTAL_A_PAGAR}", re.I)


# ------------------------------------------------------------------ filtro
def _textos(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _textos(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _textos(v)


def proibido(o) -> bool:
    """Algum texto é da lista da porta, de `render.texto_proibido` ou muda em `tabelas.limpar_texto` (e-mail, CPF/CNPJ,
    telefone): o cartão sai inteiro. Aqui fica a única defesa de dado pessoal da porta (RD-0252)."""
    return any(_SO_DA_PORTA.search(t) or render.texto_proibido(t) or tabelas.limpar_texto(t) != t for t in _textos(o))


# o `valor` só tem número, R$, mi, mil, %, DU, dia(s), h, min, un, x e —; qualquer outra palavra pode ser nome de pessoa e o cartão sai (desenho §6)
_UNIDADES = {"r", "mi", "mil", "du", "dia", "dias", "s", "h", "min", "un", "x"}     # lista fechada (o "s" é o de "dia(s)")
_PALAVRA = re.compile(r"[^\W\d_]+")


def valor_so_numero(v) -> bool:
    return all(p.lower() in _UNIDADES for p in _PALAVRA.findall(str(v)))


def _sub(itens, chaves) -> list[dict]:
    # `render._lista`: o mesmo teste de lista do render (não se cria outro)
    return [{k: str(i.get(k) or "") for k in chaves} for i in render._lista(itens) if isinstance(i, dict)]


def _estados(e) -> dict | None:
    """As barras por estado como `render._barras`/`_mini` entregam, só com as chaves da lista: {"legenda", "barras"}."""
    if not isinstance(e, dict) or not e.get("barras"):
        return None
    return {"legenda": str(e.get("legenda") or ""),
            "barras": _sub(e["barras"], ("uf", "txt", "rot", "tom"))}


def cartao_rrm(c: dict) -> dict | None:
    """Cartão das abas RRM (saída de `render.cartao`) só com as chaves da lista fechada; None = o cartão sai."""
    if not valor_so_numero(c.get("valor", "")):
        return None
    return {"titulo": str(c.get("titulo", "")), "valor": str(c.get("valor", "")), "legenda": str(c.get("legenda", "")),
            "aneis": _sub(c.get("aneis"), ("rot", "pct", "sub", "tom")),
            "faixa": _sub(c.get("faixa"), ("rot", "var", "tom", "real")), "estados": _estados(c.get("estados"))}


def cartao_farol(k: dict, fora: frozenset = frozenset()) -> dict | None:
    """Cartão de aba de painel ou de Resumo (saída de `render._kpi`), sem `linhas` nem `detalhe`.
    `fora` = rótulos dos cartões cuja `coluna` de origem é TOTAL A PAGAR (o `_kpi` descarta a chave)."""
    if str(k.get("rot", "")) in fora or not valor_so_numero(k.get("valor", "")):
        return None
    return {"rot": str(k.get("rot", "")), "valor": str(k.get("valor", "")), "cor": str(k.get("cor", "")),
            "estados": _estados(k.get("estados"))}


def rotulos_fora(rel: dict) -> frozenset:
    """RN-GER-015: rótulos dos `kpis` da origem com `coluna` = TOTAL A PAGAR (no farol e nos recortes por estado)."""
    rel = rel or {}
    ks = list(render._lista(rel.get("kpis")))
    rec = rel.get("recortes")
    for r in (rec.values() if isinstance(rec, dict) else ()):
        ks += render._lista(r.get("kpis")) if isinstance(r, dict) else []
    return frozenset(str(k.get("rotulo", "")) for k in ks if isinstance(k, dict)
                     and str(k.get("coluna", "")).strip().upper() == _TOTAL_A_PAGAR)


def limpar(saida: dict) -> dict:
    """Filtro final de toda resposta (função pura: devolve cópia). O cartão com QUALQUER texto proibido (rótulo, valor,
    anel, faixa, estados, legenda) sai inteiro; o `sub` proibido de uma visão fica vazio."""
    out = dict(saida)
    if "visoes" in out:
        out["visoes"] = [{**v, **({"sub": ""} if proibido(v.get("sub", "")) else {}),
                          "cartoes": [c for c in v["cartoes"] if not proibido(c)]} for v in out["visoes"]]
    if "cartoes" in out:
        out["cartoes"] = [c for c in out["cartoes"] if not proibido(c)]
    return out


# ------------------------------------------------------------------ montagem
def rids_do_diretor(no_pacote) -> list[dict]:
    """Os faróis (sem o Painel) que o perfil diretor vê e que já chegaram no pacote, na ordem do menu."""
    return [{"rid": r, "nome": n} for r, n in render.farois_do_perfil(PERFIL) if r in no_pacote]


def pacote_de(indice: dict | None, gerado_em: str | None, dados_ate: str | None = None, du: str | None = None) -> dict:
    return {"lote": str((indice or {}).get("lote", "")), "gerado_em": gerado_em or "", "dados_ate": dados_ate, "du": du}


def montar_painel(rel: dict, indice: dict | None, gerado_em: str | None, dados_ate: str | None = None) -> dict:
    """`rel` = farol do Painel Executivo (`vc_painel`). Visões: as abas RRM e as abas de painel, como no site.
    Sem nenhuma visão = sem pacote (a rota responde 503)."""
    abas = render.localizar_abas(rel)
    visoes = []
    for a in abas:
        t = render.aba_para_tela(a, None)
        visoes.append({"chave": a["chave"], "titulo": render.PAINEL_CURTO.get(a["chave"], a["titulo"]),
                       "sub": t["sub"], "cartoes": [c for c in map(cartao_rrm, t["cartoes"]) if c]})
    for p in render.localizar_paineis(rel):
        dados = rel["paineis"][p["chave"]]
        fora = rotulos_fora(dados)
        kpis = render.farol_para_tela(dados, None)["kpis"]
        visoes.append({"chave": p["chave"], "titulo": p["titulo"],
                       "cartoes": [c for c in (cartao_farol(k, fora) for k in kpis) if c]})
    return {"versao_leitura": VERSAO_LEITURA, "versao_web": None,
            "pacote": pacote_de(indice, gerado_em, dados_ate, render.du_do_painel(abas) or None),
            "visoes": visoes, "farois": rids_do_diretor((indice or {}).get("farois") or {})}


def montar_resumo(rid: str, rel: dict, indice: dict | None, gerado_em: str | None, dados_ate: str | None = None) -> dict:
    fora = rotulos_fora(rel)
    kpis = render.farol_para_tela(rel, None, rid)["kpis"]
    return {"versao_leitura": VERSAO_LEITURA, "versao_web": None, "pacote": pacote_de(indice, gerado_em, dados_ate),
            "rid": rid, "nome": render.FAROIS[rid][0],
            "cartoes": [c for c in (cartao_farol(k, fora) for k in kpis) if c]}


# ------------------------------------------------------------------ limite por minuto (proteção técnica)
class Limite:
    """Janela deslizante de 60 s na memória. `ip_ok` conta toda chamada por IP (antes do token); `total_ok` conta só as
    chamadas com token válido (falha não esgota a cota do consumidor legítimo). Relógio injetável para o teste.
    O IP só vive aqui, na memória: nunca vai ao log nem ao registro. As falhas (401/429) viram contadores, com no
    máximo uma linha agregada por janela (`agregada`, no log)."""

    def __init__(self, por_ip: int = POR_IP, total: int = TOTAL, relogio=time.monotonic):
        self.por_ip, self.total, self.relogio = por_ip, total, relogio
        self._ips: dict[str, deque] = {}
        self._todos: deque = deque()
        self._falhas = {"negado": 0, "limite": 0}
        self._desde = None

    def _podar(self, d: deque, agora: float) -> None:
        while d and agora - d[0] >= JANELA:
            d.popleft()

    def ip_ok(self, ip: str) -> bool:
        """Conta a chamada do IP; falso quando estoura (a recusada não conta: não alonga o bloqueio)."""
        agora = self.relogio()
        d = self._ips.setdefault(ip, deque())
        self._podar(d, agora)
        if len(d) >= self.por_ip:
            return False
        d.append(agora)
        if len(self._ips) > MAX_IPS:                 # memória limitada: tira os IPs com a fila vazia (fora da janela)
            for k in list(self._ips):
                self._podar(self._ips[k], agora)
                if not self._ips[k] and k != ip:
                    del self._ips[k]
            while len(self._ips) > MAX_IPS:          # ainda cheio: o IP mais antigo sai (dict mantém a ordem de chegada)
                self._ips.pop(next(iter(self._ips)))
        return True

    def total_ok(self) -> bool:
        agora = self.relogio()
        self._podar(self._todos, agora)
        if len(self._todos) >= self.total:
            return False
        self._todos.append(agora)
        return True

    def falha(self, tipo: str) -> None:
        """Conta uma falha ("negado" ou "limite"); nada vai ao disco por chamada."""
        if self._desde is None:
            self._desde = self.relogio()
        self._falhas[tipo] += 1

    def agregada(self) -> str | None:
        """Quando a janela de 60 s virou e há falhas contadas, devolve a linha agregada (uma vez) para o log; senão None.
        Chame em toda chamada: a linha pendente sai mesmo sem nova falha."""
        agora = self.relogio()
        if self._desde is None or agora - self._desde < JANELA:
            return None
        linha = f"falhas negado={self._falhas['negado']} limite={self._falhas['limite']}"
        self._falhas, self._desde = {"negado": 0, "limite": 0}, None
        return linha
