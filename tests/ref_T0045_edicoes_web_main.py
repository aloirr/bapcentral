"""Referência congelada do laço das edições do site no robô (T-0045).

O texto abaixo é o de `bap_automation.py` no main e1d80a8 (27/11/2026), antes
de o modulo-robo extrair o laço para `puxar_fila_web`: `ler_estado_edicoes_web`,
`gravar_estado_edicoes_web`, `baixar_edicoes_web`, `confirmar_edicoes_web` e
`sincronizar_edicoes_web`, sem nenhuma mudança. O teste
`tests/test_T0045_edicoes_web_igual_main.py` roda o mesmo cenário nesta cópia
e no `bap_automation` do momento e exige o mesmo resultado, as mesmas chamadas
ao site, o mesmo log e o mesmo estado em disco.

As funções de apoio que a extração não tocou (`aplicar_edicao_web`,
`aplicadas_web`, `_registrar_aplicada_web`, `opcoes_edicao_web`,
`_pasta_edicoes_web` e as constantes) vêm do módulo do momento: o que se
compara é só o laço. Não é código de produção; não edite o texto (ele é a
régua). Se o main mudar o laço de propósito, a régua muda num PR do testes.
"""
from types import SimpleNamespace

ORIGEM = "bap_automation.py @ e1d80a8 (linhas 9538-9560 e 9601-9727)"

FONTE = r'''
def ler_estado_edicoes_web(raiz) -> dict:
    """{"epoca", "ate_seq", "a_confirmar"}; sem arquivo (ou torto): do zero."""
    try:
        d = json.loads((_pasta_edicoes_web(raiz) / ARQ_ESTADO_EDICOES_WEB)
                       .read_text(encoding="utf-8"))
        n, ep = int(d.get("ate_seq")), d.get("epoca")
        ac = d.get("a_confirmar") or []
        if n < 0 or not isinstance(ep, str) or not isinstance(ac, list):
            raise ValueError("estado")
        return {"epoca": ep, "ate_seq": n, "a_confirmar": ac}
    except Exception:                                   # noqa: BLE001
        return {"epoca": "", "ate_seq": 0, "a_confirmar": []}


def gravar_estado_edicoes_web(raiz, estado: dict) -> None:
    pasta = _pasta_edicoes_web(raiz)
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / ARQ_ESTADO_EDICOES_WEB
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, alvo)




def baixar_edicoes_web(desde: int, base: str, token: str, sessao=None,
                       log=print) -> dict | None:
    """GET <base>/api/edicoes?desde=<seq> (Bearer), repetindo enquanto
    `mais`. {"epoca", "linhas", "ate_seq"} ou None (404 = web antiga, 401,
    rede...). Log sem dado pessoal e sem token."""
    sessao = sessao or __import__("requests")
    cab = {"Authorization": f"Bearer {token}"}
    linhas, atual, epoca = [], int(desde), None
    for _ in range(_PAGINAS_MAX_EDICOES_WEB):
        try:
            r = sessao.get(f"{base}/api/edicoes", params={"desde": atual},
                           headers=cab, timeout=30)
            if r.status_code != 200:
                log(f"Edicoes web: o site respondeu {r.status_code}; sigo "
                    "sem importar.")
                break
            d = r.json()
            pag, ate, ep = d["linhas"], int(d["ate_seq"]), str(d["epoca"])
            if not isinstance(pag, list) or (epoca is not None
                                              and ep != epoca):
                raise ValueError("resposta")
        except Exception as erro:                       # noqa: BLE001
            log("Edicoes web: falha ao puxar as edicoes do site "
                f"({type(erro).__name__}); sigo sem importar.")
            break
        epoca = ep
        linhas.extend(x for x in pag if isinstance(x, dict))
        mais = bool(d.get("mais"))
        if ate < atual or (mais and ate == atual):
            mais = False
        atual = max(atual, ate)
        if not mais:
            break
    if epoca is None:
        return None
    return {"epoca": epoca, "linhas": linhas, "ate_seq": atual}


def confirmar_edicoes_web(epoca: str, resultados: list, base: str,
                          token: str, sessao=None, log=print) -> bool:
    sessao = sessao or __import__("requests")
    try:
        r = sessao.post(f"{base}/api/edicoes/confirmar",
                        json={"epoca": str(epoca), "resultados": resultados},
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30)
        if r.status_code == 200:
            return True
        log(f"Edicoes web: a confirmacao voltou {r.status_code}; confirmo "
            "de novo na proxima rodada.")
    except Exception as erro:                           # noqa: BLE001
        log(f"Edicoes web: falha ao confirmar ({type(erro).__name__}); "
            "confirmo de novo na proxima rodada.")
    return False


def sincronizar_edicoes_web(raiz, base: str, token: str, sessao=None,
                            log=print, gravar=gravar_edicoes_pc,
                            opcoes=None) -> dict:
    """Puxa, grava no PC (na ordem do seq; a primeira que fica pendente -
    Excel aberto - para a fila ate a proxima rodada), guarda o estado e
    confirma. Devolve {"aplicadas", "erros", "pendentes", "confirmado"}.
    Nunca levanta."""
    cont = {"aplicadas": 0, "erros": 0, "pendentes": 0, "confirmado": False}
    try:
        estado = ler_estado_edicoes_web(raiz)
        desde = estado["ate_seq"] if estado["epoca"] else 0
        res = baixar_edicoes_web(desde, base, token, sessao, log)
        if res and res["epoca"] != estado["epoca"]:
            if estado["epoca"]:
                log("Edicoes web: a fila do site recomecou (epoca nova); "
                    "puxo tudo de novo.")
            estado = {"epoca": res["epoca"], "ate_seq": 0, "a_confirmar": []}
            if desde:
                res = baixar_edicoes_web(0, base, token, sessao, log)
                if res and res["epoca"] != estado["epoca"]:
                    res = None
        if not res:
            if estado["a_confirmar"] and estado["epoca"]:
                cont["confirmado"] = confirmar_edicoes_web(
                    estado["epoca"], estado["a_confirmar"], base, token,
                    sessao, log)
            return cont
        opcoes = opcoes if opcoes is not None else opcoes_edicao_web(raiz)
        ja = aplicadas_web(raiz)
        resultados = {int(x["seq"]): x for x in estado["a_confirmar"]
                      if isinstance(x, dict) and "seq" in x}
        ate = estado["ate_seq"]
        for reg in sorted(res["linhas"], key=lambda x: int(x.get("seq") or 0)):
            seq = int(reg.get("seq") or 0)
            if seq <= ate:
                continue
            if reg.get("status") != "pendente":
                ate = seq                   # ja confirmada no site
                continue
            if str(reg.get("id")) in ja:
                status, motivo = ja[str(reg.get("id"))]
            else:
                status, motivo = aplicar_edicao_web(raiz, reg, opcoes, gravar)
                if status == "pendente":
                    cont["pendentes"] += 1
                    log(f"Edicoes web: {motivo}; a fila espera a proxima "
                        "rodada.")
                    break
                _registrar_aplicada_web(raiz, reg, status, motivo,
                                        res["epoca"])
            cont["aplicadas" if status == "aplicada" else "erros"] += 1
            resultados[seq] = {"seq": seq, "status": status, "motivo": motivo}
            ate = seq
        estado = {"epoca": res["epoca"], "ate_seq": ate,
                  "a_confirmar": sorted(resultados.values(),
                                        key=lambda x: x["seq"])}
        gravar_estado_edicoes_web(raiz, estado)
        if cont["aplicadas"] or cont["erros"]:
            log(f"Edicoes web: {cont['aplicadas']} gravada(s) no PC, "
                f"{cont['erros']} recusada(s).")
        if estado["a_confirmar"]:
            cont["confirmado"] = confirmar_edicoes_web(
                estado["epoca"], estado["a_confirmar"], base, token, sessao,
                log)
            if cont["confirmado"]:
                gravar_estado_edicoes_web(raiz, dict(estado, a_confirmar=[]))
    except Exception as erro:                           # noqa: BLE001
        log(f"Edicoes web: nao terminei ({type(erro).__name__}); tento de "
            "novo na proxima rodada.")
    return cont

'''


def carregar(ba):
    """As 5 funções do main, ligadas às funções de apoio do `ba` de agora
    (lidas na hora: um monkeypatch no `ba` vale para as duas versões)."""
    ns = dict(vars(ba))
    exec(compile(FONTE, f"<{ORIGEM}>", "exec"), ns)            # noqa: S102
    return SimpleNamespace(**{k: ns[k] for k in (
        "ler_estado_edicoes_web", "gravar_estado_edicoes_web", "baixar_edicoes_web",
        "confirmar_edicoes_web", "sincronizar_edicoes_web")})
