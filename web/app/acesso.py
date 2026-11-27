"""T-0050 (RN-GER-018): quem vê cada farol. Funções puras, sem I/O.

O perfil dá o padrão; o admin guarda por usuário só as exceções: {"menos": [...], "mais": [...]}.
Toda checagem de "este usuário vê este farol?" passa por `pode_ver`. Os cortes de dado (abas de tabela,
TOTAL A PAGAR, meta RH, edição, Cobrar) seguem pelo perfil, por cima: nunca leem as exceções.
Usuários e Trocar senha não são faróis: ficam fora da lista (o admin não tira Usuários de si)."""
from __future__ import annotations

from . import render

PAINEL = render.PAINEL_RID            # o Painel Executivo entra na lista (P2 A)
NOME_PAINEL = render.NOME_PAINEL


def rids_da_lista() -> tuple[str, ...]:
    """Painel + os rids de `render.FAROIS`, na ordem do menu (rid fora do menu vai no fim)."""
    vistos = [PAINEL]
    for _, rids in render.GRUPOS_MENU:
        vistos += [r for r in rids if r in render.FAROIS and r not in vistos]
    vistos += [r for r in render.FAROIS if r not in vistos]
    return tuple(vistos)


def nome_do(rid: str) -> str:
    return NOME_PAINEL if rid == PAINEL else render.nome_curto(rid)


def perfil_ve(perfil: str, rid: str) -> bool:
    """O padrão do perfil. Rid desconhecido = falso."""
    if rid == PAINEL:
        return perfil in render.VEEM_PAINEL
    if rid not in render.FAROIS:
        return False
    return perfil in render.FAROIS[rid][1]


def _lista(usuario: dict, chave: str) -> tuple:
    a = usuario.get("acesso") or {}
    v = a.get(chave) if isinstance(a, dict) else None
    return tuple(v) if isinstance(v, (list, tuple)) else ()


def pode_ver(usuario: dict, rid: str) -> bool:
    if not usuario or rid not in rids_da_lista():       # rid desconhecido (ou que saiu do FAROIS): nunca
        return False
    if rid in _lista(usuario, "menos"):
        return False
    return perfil_ve(usuario.get("perfil", ""), rid) or rid in _lista(usuario, "mais")


def farois_do_usuario(usuario: dict) -> list[tuple[str, str]]:
    """[(rid, nome)] dos faróis (sem o Painel) que o usuário vê, na ordem de `FAROIS`: menu e página inicial."""
    return [(rid, nome) for rid, (nome, _) in render.FAROIS.items() if pode_ver(usuario, rid)]


def padrao_do_perfil(perfil: str) -> set[str]:
    return {r for r in rids_da_lista() if perfil_ve(perfil, r)}


def excecoes(perfil: str, marcados, antigo: dict | None = None) -> dict:
    """Do formulário (caixas marcadas) para {"menos", "mais"}; rid desconhecido: ValueError.
    Os rids desconhecidos do acesso `antigo` ficam guardados (inertes), como no desenho §7."""
    marcados = set(marcados)
    conhecidos = set(rids_da_lista())
    if not marcados <= conhecidos:
        raise ValueError("rid desconhecido")
    pad = padrao_do_perfil(perfil)
    antigo = antigo or {}
    return {"menos": sorted((pad - marcados) | {r for r in antigo.get("menos", ()) if r not in conhecidos}),
            "mais": sorted((marcados - pad) | {r for r in antigo.get("mais", ()) if r not in conhecidos})}


def visiveis(perfil: str, acesso: dict | None) -> set[str]:
    u = {"perfil": perfil, "acesso": acesso or {}}
    return {r for r in rids_da_lista() if pode_ver(u, r)}


def mudancas(perfil: str, antes: dict | None, depois: dict | None) -> list[tuple[str, str, str]]:
    """[(rid, "+"|"-", origem)]: só o que muda para quem vê. origem = "perfil" (o rid é do padrão) ou "liberado"."""
    a, d = visiveis(perfil, antes), visiveis(perfil, depois)
    return [(r, "+" if r in d else "-", "perfil" if perfil_ve(perfil, r) else "liberado")
            for r in rids_da_lista() if (r in a) != (r in d)]


def contagem(usuario: dict) -> tuple[int, int]:
    """(tirados, liberados) com efeito para o usuário: os selos da linha."""
    perfil = usuario.get("perfil", "")
    vis, pad = visiveis(perfil, usuario.get("acesso")), padrao_do_perfil(perfil)
    return len(pad - vis), len(vis - pad)


def _grupos(rids) -> list[dict]:
    rids = set(rids)
    saida = []
    if PAINEL in rids:
        saida.append({"nome": render.GRUPO_PAINEL, "itens": [PAINEL]})
    visto = {PAINEL}
    for nome, lista in render.GRUPOS_MENU:
        itens = [r for r in lista if r in rids]
        visto |= set(itens)
        if itens:
            saida.append({"nome": nome, "itens": itens})
    resto = [r for r in rids_da_lista() if r in rids and r not in visto]
    if resto:
        saida.append({"nome": "Outros", "itens": resto})
    return saida


def partes(perfil: str, marcados) -> dict:
    """A tela: {"perfil": grupos do padrão, "liberar": grupos dos demais}; cada item {rid, nome, marcado}."""
    marcados = set(marcados)
    pad = padrao_do_perfil(perfil)

    def com_nome(g):
        return [{"nome": x["nome"], "itens": [{"rid": r, "nome": nome_do(r), "marcado": r in marcados}
                                                for r in x["itens"]]} for x in g]
    todos = set(rids_da_lista())
    return {"perfil": com_nome(_grupos(pad)),
            "liberar": com_nome(_grupos(todos - pad)) if perfil != "admin" else []}
