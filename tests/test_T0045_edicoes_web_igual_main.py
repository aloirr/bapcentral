"""T-0045 (ADR 0004, §9 item 8; contrato visitas-nuvem §4.4): o laço das
edições do site saiu de `sincronizar_edicoes_web` para `puxar_fila_web`, que
as visitas também usam. As edições não podem mudar: para cada cenário, o
`bap_automation` do momento e a régua do main e1d80a8
(`tests/ref_T0045_edicoes_web_main.py`) dão o mesmo resultado, as mesmas
chamadas ao site (método, rota, parâmetros, corpo, cabeçalho e tempo), o mesmo
log, o mesmo estado em disco e o mesmo registro das aplicadas.

Regra: RN-GER-012 (edição só no site e só pelo admin; chega ao PC pelo robô,
pela mesma gravação da tela; dado digitado é intocável). Roda com o robô novo
e sem ele (no main sem o robô, a régua e o módulo são o mesmo texto).
Dados fictícios; o site é um falso em memória; tudo em pasta temporária.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_automation as ba
import ref_T0045_edicoes_web_main as ref

BASE = "https://web.exemplo.test"
TOKEN = "token-ficticio-t0045-edicoes"
OPCOES = {"por": {"PRICE"}, "etapa": set(), "transportadora": set()}


def _reg(seq, status="pendente", i=None, valores=None, chave="101002|012345"):
    return {"tipo": "edicao", "seq": seq, "id": f"id-{i or seq}", "quando": "2026-11-25 09:00:00",
            "usuario": "admin.ficticio", "rid": "pv_pedidos", "tabela": "Pedidos", "modulo": "autorizacoes",
            "chave": chave, "valores": valores if valores is not None else {"por": "PRICE"}, "antes": {},
            "status": status}


class _Site:
    def __init__(self, linhas, epoca="ep-1", falha=None, pagina=2, conf=200, torto=False):
        self.linhas, self.epoca, self.falha, self.pagina, self.conf = linhas, epoca, falha, pagina, conf
        self.torto = torto
        self.chamadas = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.chamadas.append(("GET", url, dict(params or {}), dict(headers or {}), timeout))
        if self.falha == "rede":
            raise ConnectionError("rede fora (fictício)")
        if self.falha:
            return SimpleNamespace(status_code=self.falha, json=lambda: {})
        if self.torto:
            return SimpleNamespace(status_code=200, json=lambda: {"linhas": "x"})
        d = params["desde"]
        rest = [x for x in self.linhas if x["seq"] > d]
        pag, mais = rest[:self.pagina], len(rest) > self.pagina
        ate = pag[-1]["seq"] if pag else d
        return SimpleNamespace(status_code=200, json=lambda: {
            "epoca": self.epoca, "linhas": pag, "ate_seq": ate, "mais": mais})

    def post(self, url, json=None, headers=None, timeout=None):
        self.chamadas.append(("POST", url, json, dict(headers or {}), timeout))
        if self.conf == "rede":
            raise ConnectionError("rede fora (fictício)")
        return SimpleNamespace(status_code=self.conf)


def _gravar_que(falhas=None):
    """A gravação do PC, falsa: `falhas` = {id: exceção} (PermissionError = Excel aberto)."""
    falhas = dict(falhas or {})
    feitas = []

    def gravar(raiz, modulo, arquivo, aba, edicoes):
        (chave, valores), = edicoes.items()
        feitas.append((modulo, arquivo, aba, chave, dict(valores)))
        for k, exc in list(falhas.items()):
            if k == chave:
                del falhas[k]                                # falha uma vez só
                raise exc
        return 1
    return gravar, feitas


def _rodar(sinc, raiz, rodadas, opcoes=OPCOES, falhas=None):
    logs = []
    gravar, feitas = _gravar_que(falhas)
    saida = []
    for fazer_site in rodadas:
        site = fazer_site()
        r = sinc(raiz, BASE, TOKEN, site, logs.append, gravar, opcoes)
        saida.append((r, site.chamadas))
    pasta = Path(raiz) / "RELATORIOS" / "_EDICOES_WEB"
    est = pasta / ba.ARQ_ESTADO_EDICOES_WEB
    regs = []
    for f in sorted(pasta.glob("APLICADAS_WEB_*.jsonl")) if pasta.is_dir() else []:
        for ln in f.read_text(encoding="utf-8").splitlines():
            d = json.loads(ln)
            d.pop("quando", None)                            # a hora da gravação muda de uma corrida para a outra
            regs.append(d)
    arquivos = sorted(p.relative_to(raiz).as_posix() for p in Path(raiz).rglob("*") if p.is_file())
    return {"saida": saida, "logs": logs, "feitas": feitas, "regs": regs, "arquivos": arquivos,
            "estado": json.loads(est.read_text(encoding="utf-8")) if est.exists() else None}


CENARIOS = {
    "tres_paginas": [lambda: _Site([_reg(i) for i in range(1, 6)])],
    "duas_rodadas_sem_repetir": [lambda: _Site([_reg(1), _reg(2)]),
                                 lambda: _Site([_reg(1), _reg(2), _reg(3)])],
    "epoca_nova_puxa_tudo_de_novo": [lambda: _Site([_reg(1), _reg(2)]),
                                     lambda: _Site([_reg(1, i=11), _reg(2, i=12)], epoca="ep-2")],
    "epoca_nova_mesmo_id_nao_regrava": [lambda: _Site([_reg(1)]),
                                        lambda: _Site([_reg(1)], epoca="ep-2")],
    "confirmar_falha_e_confirma_na_volta": [lambda: _Site([_reg(1)], conf=503), lambda: _Site([_reg(1)])],
    "confirmar_sem_rede": [lambda: _Site([_reg(1)], conf="rede"), lambda: _Site([_reg(1)])],
    "confirmar_pendente_com_site_fora": [lambda: _Site([_reg(1)], conf=503),
                                         lambda: _Site([_reg(1)], falha=503)],
    "web_antiga_404": [lambda: _Site([], falha=404)],
    "token_401": [lambda: _Site([_reg(1)], falha=401)],
    "sem_rede": [lambda: _Site([], falha="rede")],
    "resposta_torta": [lambda: _Site([_reg(1)], torto=True)],
    "ja_confirmada_no_site": [lambda: _Site([_reg(1, status="aplicada"), _reg(2)])],
    "recusada_vai_ao_site": [lambda: _Site([_reg(1, valores={"por": "NINGUEM FICTICIO"}), _reg(2)])],
    "fila_vazia": [lambda: _Site([])],
}


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_RN_GER_012_sincronizar_edicoes_web_igual_ao_main(nome, tmp_path):
    novo = _rodar(ba.sincronizar_edicoes_web, tmp_path / "novo", CENARIOS[nome])
    antigo = _rodar(ref.carregar(ba).sincronizar_edicoes_web, tmp_path / "main", CENARIOS[nome])
    assert novo == antigo


def test_RN_GER_012_excel_aberto_para_a_fila_igual_ao_main(tmp_path):
    """A primeira que fica pendente (Excel aberto) para a fila até a volta seguinte, nos dois."""
    rodadas = [lambda: _Site([_reg(1), _reg(2, chave="101002|000777"), _reg(3)]),
               lambda: _Site([_reg(1), _reg(2, chave="101002|000777"), _reg(3)])]
    falha = {"101002|000777": PermissionError("aberto")}
    novo = _rodar(ba.sincronizar_edicoes_web, tmp_path / "novo", rodadas, falhas=falha)
    antigo = _rodar(ref.carregar(ba).sincronizar_edicoes_web, tmp_path / "main", rodadas, falhas=falha)
    assert novo == antigo
    (r1, _), (r2, _) = novo["saida"]
    assert (r1["aplicadas"], r1["pendentes"], r2["aplicadas"]) == (1, 1, 2)


def test_RN_GER_012_opcoes_lidas_so_quando_ha_o_que_aplicar_igual_ao_main(tmp_path, monkeypatch):
    """Sem `opcoes`, as duas leem as opções do PC uma vez por volta e só se o site respondeu."""
    lidas = []
    monkeypatch.setattr(ba, "opcoes_edicao_web", lambda raiz: lidas.append(Path(raiz).name) or OPCOES)
    rodadas = [lambda: _Site([_reg(1)]), lambda: _Site([], falha=404), lambda: _Site([_reg(1), _reg(2)])]
    novo = _rodar(ba.sincronizar_edicoes_web, tmp_path / "novo", rodadas, opcoes=None)
    antigo = _rodar(ref.carregar(ba).sincronizar_edicoes_web, tmp_path / "main", rodadas, opcoes=None)
    assert novo == antigo
    assert lidas == ["novo", "novo", "main", "main"]


def test_RN_GER_012_estado_torto_recomeca_do_zero_igual_ao_main(tmp_path):
    for raiz in (tmp_path / "novo", tmp_path / "main"):
        p = raiz / "RELATORIOS" / "_EDICOES_WEB"
        p.mkdir(parents=True)
        (p / ba.ARQ_ESTADO_EDICOES_WEB).write_text("{torto", encoding="utf-8")
    rodadas = [lambda: _Site([_reg(1)])]
    novo = _rodar(ba.sincronizar_edicoes_web, tmp_path / "novo", rodadas)
    antigo = _rodar(ref.carregar(ba).sincronizar_edicoes_web, tmp_path / "main", rodadas)
    assert novo == antigo
    assert novo["estado"] == {"epoca": "ep-1", "ate_seq": 1, "a_confirmar": []}


def test_RN_GER_012_funcoes_publicas_das_edicoes_continuam(tmp_path):
    """Assinaturas e efeito das 4 funções públicas que o main tinha (o PC e os testes da T-0021 usam)."""
    import inspect
    r = ref.carregar(ba)
    for nome in ("ler_estado_edicoes_web", "gravar_estado_edicoes_web", "baixar_edicoes_web",
                 "confirmar_edicoes_web", "sincronizar_edicoes_web"):
        a, b = (inspect.signature(getattr(m, nome)).parameters for m in (ba, r))
        assert [(p.name, p.default) for p in a.values()] == [(p.name, p.default) for p in b.values()], nome
    est = {"epoca": "ep-9", "ate_seq": 4, "a_confirmar": [{"seq": 4, "status": "aplicada", "motivo": ""}]}
    ba.gravar_estado_edicoes_web(tmp_path, est)
    assert r.ler_estado_edicoes_web(tmp_path) == ba.ler_estado_edicoes_web(tmp_path) == est
    s1, s2 = _Site([_reg(1), _reg(2), _reg(3)]), _Site([_reg(1), _reg(2), _reg(3)])
    assert ba.baixar_edicoes_web(1, BASE, TOKEN, s1, print) == r.baixar_edicoes_web(1, BASE, TOKEN, s2, print)
    assert s1.chamadas == s2.chamadas
    for conf in (200, 409, 503, "rede"):
        a, b = _Site([], conf=conf), _Site([], conf=conf)
        la, lb = [], []
        assert (ba.confirmar_edicoes_web("ep", [], BASE, TOKEN, a, la.append)
                is r.confirmar_edicoes_web("ep", [], BASE, TOKEN, b, lb.append))
        assert (a.chamadas, la) == (b.chamadas, lb)
