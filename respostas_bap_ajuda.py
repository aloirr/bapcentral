# -*- coding: utf-8 -*-
"""
RESPOSTAS DO BAP AJUDA 2.0 (app) NOS FAROIS - (27/10/2026, Alexandre;
recados do BAP Ajuda 20261027-0740 e 0820)

Os vendedores preenchem no app BAP Ajuda 2.0 a PESQUISA de mercado, a
INDICACAO ("Indicou, ganhou") e a PROSPECCAO (visita a cliente fora da
base). A sincronizacao do BAP Ajuda (BAP Ajuda 2.0\\sincronizar_bap.py)
refaz inteiro, a cada rodada:

    RELATORIOS\\BAP_AJUDA_RESPOSTAS\\RESPOSTAS_BAP_AJUDA.xlsx
        abas PESQUISA, INDICACOES e PROSPECCAO
    RELATORIOS\\BAP_AJUDA_RESPOSTAS\\fotos\\   (foto da fachada da prospeccao)

Este modulo SO LE o arquivo (nunca grava nele) e entrega as linhas para:
  - Farol de Visita > Prospeccao (junto com o Forms; prospeccao_forms);
  - Farol de Visita > Indicacao;
  - Farol de Preco > Pesquisa de mercado.

TESTES: as respostas do vendedor 000040 (ALEXNADRE LOHAN, a conta de teste
do Alexandre) ficam fora de tudo [SUPOSICAO combinada no recado: as
respostas de 27/10 07h28-08h01 sao testes]. Para tirar outro teste,
COD_TESTE / NOMES_TESTE.

VENDEDOR: o nome que o app grava (NOME_VENDEDOR_PLANNER) cruzado com o
cadastro do Planner (pessoas: nome, primeiro + ultimo nome); o supervisor
pelo "responde_a".
"""
from __future__ import annotations

import re
import shutil
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SUB = Path("RELATORIOS") / "BAP_AJUDA_RESPOSTAS"
ARQUIVO = "RESPOSTAS_BAP_AJUDA.xlsx"
ABAS = ("PESQUISA", "INDICACOES", "PROSPECCAO")

COD_TESTE = {"000040"}
NOMES_TESTE = ("ALEXNADRE LOHAN", "ALEXANDRE LOHAN")
SEM_CODIGO = "SEM CÓDIGO BAP"


# ------------------------------------------------------------------ basico
def _sa(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore")
    return re.sub(r"\s+", " ", s.decode().strip().lower())


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:                                       # NaN
            return ""
        if v.is_integer():
            v = int(v)
    return str(v).strip()


def numero(v):
    """R$ / unidades do app: 12,50 / 12.5 / "R$ 1.234,56" -> float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return None if v != v else float(v)
    t = re.sub(r"[^\d,.\-]", "", str(v))
    if not t or t in "-.,":
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def so_digitos(v) -> str:
    return re.sub(r"\D", "", texto(v))


def dia(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = texto(v)
    for f in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(t[:10], f).date()
        except ValueError:
            pass
    return None


def momento(v) -> datetime | None:
    """`enviado_em` (2026-10-27T07:28:51-04:00): a hora LOCAL do envio."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    t = texto(v)
    try:
        return datetime.fromisoformat(t).replace(tzinfo=None)
    except ValueError:
        pass
    d = dia(t)
    return datetime(d.year, d.month, d.day) if d else None


def _ordem(v) -> float:
    """O instante do envio (com o fuso) para pôr em ordem: 07:30-04:00 vem
    depois de 08:00-03:00."""
    try:
        m = v if isinstance(v, datetime) else datetime.fromisoformat(
            texto(v))
        return m.timestamp()
    except (ValueError, OverflowError, OSError):
        return 0.0


def cod6(v) -> str:
    v = texto(v)
    return v.zfill(6) if v.isdigit() else v


# ------------------------------------------------------------- o arquivo
def pasta(raiz=None) -> Path:
    return Path(raiz or AQUI) / SUB


def arquivo(raiz=None) -> Path:
    return pasta(raiz) / ARQUIVO


def pasta_fotos(raiz=None) -> Path:
    return pasta(raiz) / "fotos"


_MEMO = {}


def ler(raiz=None) -> dict:
    """{"PESQUISA": [linhas], "INDICACOES": [...], "PROSPECCAO": [...]} -
    cada linha um dict com o cabecalho do app (minusculo). O arquivo e
    copiado antes (pode estar aberto no Excel). Sem arquivo: abas vazias."""
    arq = arquivo(raiz)
    vazio = {a: [] for a in ABAS}
    try:
        st = arq.stat()
    except OSError:
        return vazio
    chave = (str(arq), st.st_mtime, st.st_size)
    if _MEMO.get("chave") == chave:
        return _MEMO["dados"]
    from openpyxl import load_workbook                  # noqa: PLC0415
    tmp = Path(tempfile.mkdtemp(prefix="bap_ajuda_")) / ARQUIVO
    dados = dict(vazio)
    try:
        shutil.copy2(arq, tmp)
        wb = load_workbook(tmp, read_only=True, data_only=True)
        for nome in wb.sheetnames:
            aba = _sa(nome).upper()
            if aba not in ABAS:
                continue
            it = wb[nome].iter_rows(values_only=True)
            try:
                cab = [_sa(c) for c in next(it)]
            except StopIteration:
                continue
            ls = []
            for r in it:
                if not any(v not in (None, "") for v in r):
                    continue
                ls.append({c: v for c, v in zip(cab, r) if c})
            ls.sort(key=lambda d: _ordem(d.get("enviado_em")))
            dados[aba] = ls
        wb.close()
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    _MEMO.update(chave=chave, dados=dados)
    return dados


def assinatura(raiz=None) -> tuple:
    """Para cache: (mtime, tamanho) do arquivo do app (ou vazio)."""
    try:
        st = arquivo(raiz).stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return ()


# --------------------------------------------------------------- a equipe
def equipe(cfg) -> dict:
    """{nome sem acento (inteiro e primeiro + ultimo): {cod, nome, sup,
    uf, cargo}} de todas as pessoas do Planner (o supervisor pelo
    responde_a)."""
    pessoas = cfg.get("pessoas") or []
    nome_de = {cod6(p.get("cod_protheus")): texto(p.get("nome")).upper()
               for p in pessoas}
    eq = {}
    for p in pessoas:
        nome = texto(p.get("nome")).upper()
        if not nome:
            continue
        v = {"cod": cod6(p.get("cod_protheus")), "nome": nome,
             "sup": nome_de.get(cod6(p.get("responde_a")), ""),
             "uf": texto(p.get("uf_base")).upper() or "AM",
             "cargo": texto(p.get("cargo")).upper(),
             "ativo": p.get("ativo", True) is not False}
        eq.setdefault(_sa(nome), v)
        partes = _sa(nome).split()
        if len(partes) > 1:
            eq.setdefault(f"{partes[0]} {partes[-1]}", v)
    return eq


def quem(eq, nome) -> dict | None:
    n = _sa(nome)
    if n in eq:
        return eq[n]
    partes = n.split()
    if len(partes) > 1:
        return eq.get(f"{partes[0]} {partes[-1]}")
    return None


def e_teste(nome, cod="") -> bool:
    n = texto(nome).upper()
    return cod6(cod) in COD_TESTE or any(t in n for t in NOMES_TESTE)


def config(raiz=None) -> dict:
    import json                                         # noqa: PLC0415
    try:
        return json.loads((Path(raiz or AQUI) / "planner_config.json")
                          .read_text("utf-8"))
    except (OSError, ValueError):
        return {}


# ------------------------------------------------------------- as abas
def _base(r, eq) -> dict:
    """O que as tres abas tem em comum: dia, hora, vendedor (cod, nome,
    supervisor) e se e teste."""
    v = quem(eq, r.get("vendedor"))
    nome = v["nome"] if v else texto(r.get("vendedor")).upper()
    cod = v["cod"] if v else ""
    m = momento(r.get("enviado_em"))
    return {"dia": dia(r.get("data")) or (m.date() if m else None),
            "enviado": m, "vendedor": nome, "cod6": cod,
            "supervisor": (v or {}).get("sup", ""),
            "teste": e_teste(nome, cod)}


def indicacoes(raiz=None, cfg=None, com_teste=False) -> list[dict]:
    """Aba INDICACOES: uma linha por indicacao (\"Indicou, ganhou\").
    NAO conta como visita nem como prospeccao (Alexandre, 24/10)."""
    cfg = cfg if cfg is not None else config(raiz)
    eq = equipe(cfg)
    saida = []
    for r in ler(raiz)["INDICACOES"]:
        b = _base(r, eq)
        if b["teste"] and not com_teste:
            continue
        cnpj = so_digitos(r.get("cnpj"))
        if 12 <= len(cnpj) < 14:
            cnpj = cnpj.zfill(14)
        rot = texto(r.get("indicado_por"))
        cod_i = cod6(r.get("indicado_por_cod"))
        nome_i = rot.split("·")[1].strip() if rot.count("·") >= 2 else rot
        b.update(cod_indicou=cod_i, quem_indicou=nome_i,
                 rotulo_indicou=rot,
                 estab=texto(r.get("estabelecimento")).upper(),
                 contato=texto(r.get("contato")),
                 telefone=texto(r.get("telefone")),
                 cidade=texto(r.get("cidade")).upper(),
                 bairro=texto(r.get("bairro")).upper(),
                 segmento=texto(r.get("segmento")),
                 cnpj=cnpj, obs=texto(r.get("observacao")))
        saida.append(b)
    return saida


def pesquisas(raiz=None, cfg=None, com_teste=False) -> list[dict]:
    """Aba PESQUISA: uma linha por ITEM pesquisado no cliente. Preco de
    COMPRA (o que o cliente paga) e de VENDA (o que ele cobra do
    consumidor), da BAP e do maior concorrente no PDV; estoque e volume
    vendido no PDV. As colunas antigas (preco_bap, preco_concorrencia,
    estoque_linha_*) sao ignoradas."""
    cfg = cfg if cfg is not None else config(raiz)
    eq = equipe(cfg)
    saida = []
    for r in ler(raiz)["PESQUISA"]:
        b = _base(r, eq)
        if b["teste"] and not com_teste:
            continue
        cod = texto(r.get("codigo_bap")).upper()
        b.update(cod_cliente=cod6(r.get("cod_cliente")),
                 loja=texto(r.get("loja")).zfill(2) if texto(
                     r.get("loja")).isdigit() else texto(r.get("loja")),
                 cliente=texto(r.get("cliente")),
                 cidade=texto(r.get("cidade")).upper(),
                 uf=texto(r.get("uf")).upper(),
                 segmento=texto(r.get("segmento")),
                 obs=texto(r.get("observacao")),
                 linha=texto(r.get("linha")).upper(),
                 papel=texto(r.get("papel")).upper(),
                 codigo=cod, sem_codigo=(not cod or _sa(cod) ==
                                         _sa(SEM_CODIGO)),
                 descricao=texto(r.get("descricao_bap")),
                 # (28/10, recado 20261027-1555 do BAP Ajuda) botao "Cliente
                 # nao trabalha com o produto": NAO = item sem nenhum campo;
                 # resposta antiga (sem a coluna) = SIM [SUPOSICAO]
                 trabalha=_sa(texto(r.get("cliente_trabalha"))).upper()
                 != "NAO",
                 est_bap=numero(r.get("estoque_bap")),
                 est_conc=numero(r.get("estoque_concorrencia")),
                 marca=texto(r.get("marca_concorrente")).upper(),
                 cod_conc=texto(r.get("codigo_concorrente")),
                 compra_bap=numero(r.get("preco_compra_bap")),
                 venda_bap=numero(r.get("preco_venda_bap")),
                 compra_conc=numero(r.get("preco_compra_concorrencia")),
                 venda_conc=numero(r.get("preco_venda_concorrencia")),
                 vol_bap=numero(r.get("volume_bap_vendido")),
                 vol_conc=numero(r.get("volume_concorrencia_vendido")))
        saida.append(b)
    return saida


def prospeccoes(raiz=None, cfg=None) -> list[dict]:
    """Aba PROSPECCAO no formato das respostas do Forms (as chaves do
    prospeccao_forms.COL), para validar junto: estab, cnpj, segmento, uf,
    cidade, endereco, contato, telefone, resultado, linhas, foto, obs."""
    cfg = cfg if cfg is not None else config(raiz)
    eq = equipe(cfg)
    saida = []
    for r in ler(raiz)["PROSPECCAO"]:
        b = _base(r, eq)
        env = texto(r.get("enviado_em"))
        saida.append({
            "id": "APP " + env, "fonte": "APP",
            "conclusao": b["enviado"].strftime("%d/%m/%Y %H:%M")
            if b["enviado"] else env,
            "dia_app": b["dia"], "vendedor": texto(r.get("vendedor")),
            "email": "", "teste": b["teste"],
            "estab": texto(r.get("estabelecimento")),
            "cnpj": texto(r.get("cnpj")),
            "segmento": texto(r.get("segmento")),
            "uf": texto(r.get("uf")).upper(),
            "cidade": texto(r.get("cidade")).upper(),
            "endereco": texto(r.get("endereco")),
            "contato": texto(r.get("contato")),
            "telefone": texto(r.get("telefone")),
            "resultado": texto(r.get("resultado")),
            "linhas": texto(r.get("linhas_interesse")),
            "foto": texto(r.get("foto")),
            "obs": texto(r.get("observacao")),
            "indicado_por": texto(r.get("indicado_por")),
            "ja_na_base": texto(r.get("ja_na_base")).upper()})
    return saida
