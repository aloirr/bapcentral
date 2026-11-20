# -*- coding: utf-8 -*-
"""
PROSPECCAO (MICROSOFT FORMS) COMO VISITA - (22/10/2026, Alexandre; recado
do Analista 20261022-1127)

O vendedor registra no formulario "Prospeccao BAP . visita a cliente fora
da base" a visita a um estabelecimento que NAO e cliente da base. Cada
resposta valida (STATUS = CONTA) soma 1 na visita do vendedor no dia, como
o cadastro novo ja soma (relatorios_nucleo.com_cadastro_como_visita), e
entra como FORA DE ROTA (nao entra na aderencia ao Planner).

FONTE (sem TI, sem Graph): o Excel de respostas que o Forms mantem no
OneDrive (Forms > Exibir respostas > Abrir no Excel), sincronizado no PC.
  1. o caminho do parametro do Planner "arquivo_prospeccao_forms";
  2. senao, o .xlsx mais novo entre os do OneDrive com "Prospec" e "BAP"
     no nome e os soltos em RELATORIOS\\Visitas\\PROSPECCAO (baixados a mao
     ou por Power Automate).

"Atualizar visitas" chama atualizar(): le as respostas, valida e grava
RELATORIOS\\Visitas\\PROSPECCAO\\PROSPECCAO_AAAAMM.xlsx (uma linha por
resposta, com VENDEDOR BAP, STATUS e OBSERVACAO). E SO ACRESCENTA: a
resposta (pelo ID do Forms) que ja esta no arquivo fica como estava.
Os farois leem esses arquivos (contagem / linhas).

VENDEDOR = o e-mail da conta que respondeu, cruzado com o e-mail do
cadastro do Planner (pessoas > email). A pergunta "Vendedor" so confere.

(22/10, Alexandre - recado 20261022-1351) A DATA DA VISITA E A DATA DO
ENVIO do formulario (coluna "Hora de conclusao"): enviou hoje, e visita de
hoje. A hora do Forms vem em UTC [SUPOSICAO a conferir no teste de 1 dia]:
passa para o fuso da UF do vendedor (uf_base do Planner: AM/RR/MT -4,
PA/MA/AP -3) antes de pegar o dia. A pergunta "Data da visita" nao vale
mais (se ainda existir, e ignorada). Nao ha mais FORA DO PRAZO.

STATUS (so CONTA vira visita):
  CONTA              CNPJ valido, fora da BASE_CLIENTE, 1a vez do vendedor
                     nesse CNPJ no dia
  DUPLICADO          mesmo vendedor + CNPJ + dia (conta 1)
  CLIENTE DA BASE    CNPJ na BASE_CLIENTE (aba BASE_CLIENTE): vai pela
                     Maxima
  CADASTRADO NO DIA  DATA_CADASTRO do CNPJ = dia da visita (ja conta CAD.)
  CNPJ INVALIDO      digito verificador errado
  DIA DO LOTE        data em datas_cadastro_lote_fora (Planner)
  SEM VENDEDOR       e-mail e nome fora do cadastro do Planner
  TESTE              (27/10) resposta da conta de teste do Alexandre
                     (000040 ALEXNADRE LOHAN): fora da visita

(27/10, Alexandre - recado do BAP Ajuda 20261027-0740) A PROSPECCAO DO APP
BAP AJUDA 2.0 (RELATORIOS\\BAP_AJUDA_RESPOSTAS\\RESPOSTAS_BAP_AJUDA.xlsx, aba
PROSPECCAO; respostas_bap_ajuda) entra JUNTO com o Forms, com a mesma
validacao: vendedor pelo nome do app, dia = a coluna data do app. Mesmo
vendedor + CNPJ + dia que ja CONTOU no Forms = DUPLICADO (conta 1 so)
[SUPOSICAO: o Forms vale primeiro]. O app nao e gravado nos
PROSPECCAO_AAAAMM.xlsx: e lido direto a cada farol (o arquivo do app e
refeito inteiro a cada sincronizacao). Coluna FONTE = FORMS ou APP.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SUB_PROSPECCAO = Path("RELATORIOS") / "Visitas" / "PROSPECCAO"
PREFIXO_SAIDA = "PROSPECCAO_"
# (22/10) o Forms grava a hora em UTC [SUPOSICAO]: o dia da visita sai da
# hora de conclusao no fuso da UF do vendedor
HORA_DO_FORMS_EM_UTC = True
FUSO_UF = {"AM": -4, "RR": -4, "MT": -4, "RO": -4, "AC": -5,
           "PA": -3, "MA": -3, "AP": -3}

ST_CONTA = "CONTA"
ST_DUPLICADO = "DUPLICADO"
ST_BASE = "CLIENTE DA BASE"
ST_CADASTRADO = "CADASTRADO NO DIA"
ST_CNPJ = "CNPJ INVÁLIDO"
ST_LOTE = "DIA DO LOTE"
ST_SEM_VEND = "SEM VENDEDOR"
ST_TESTE = "TESTE"
STATUS = (ST_CONTA, ST_DUPLICADO, ST_BASE, ST_CADASTRADO, ST_CNPJ, ST_LOTE,
          ST_SEM_VEND, ST_TESTE)
FONTE_FORMS, FONTE_APP = "FORMS", "APP"

# o titulo da coluna no Excel do Forms (sem acento, minusculo) -> campo
COL = {
    "id": "id", "hora de inicio": "inicio", "hora de conclusao": "conclusao",
    "email": "email", "nome": "nome_conta",
    "hora da ultima modificacao": "modificado",
    "vendedor": "vendedor", "data da visita": "data_forms",
    "nome do estabelecimento": "estab", "cnpj (somente numeros)": "cnpj",
    "segmento": "segmento", "uf": "uf", "cidade": "cidade",
    "bairro e endereco": "endereco", "nome do contato": "contato",
    "telefone / whatsapp": "telefone", "resultado da visita": "resultado",
    "linhas de interesse": "linhas", "foto da fachada": "foto",
    "observacoes": "obs",
}
# o arquivo do mes: as colunas do Forms + o que o BAP calcula
COLUNAS_SAIDA = [
    ("ID", "id"), ("HORA DE CONCLUSÃO", "conclusao"), ("E-MAIL", "email"),
    ("NOME DA CONTA", "nome_conta"), ("VENDEDOR (FORMS)", "vendedor"),
    ("VENDEDOR BAP", "vendedor_bap"), ("CÓD. VENDEDOR", "cod6"),
    ("DATA DA VISITA", "dia"), ("ESTABELECIMENTO", "estab"),
    ("CNPJ", "cnpj"), ("SEGMENTO", "segmento"), ("UF", "uf"),
    ("CIDADE", "cidade"), ("BAIRRO E ENDEREÇO", "endereco"),
    ("CONTATO", "contato"), ("TELEFONE", "telefone"),
    ("RESULTADO", "resultado"), ("LINHAS DE INTERESSE", "linhas"),
    ("FOTO", "foto"), ("OBSERVAÇÕES", "obs"), ("STATUS", "status"),
    ("OBSERVAÇÃO BAP", "obs_bap"), ("VALIDADO EM", "validado"),
]


# ------------------------------------------------------------------ basico
def _sa(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore")
    return re.sub(r"\s+", " ", s.decode().strip().lower())


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def so_digitos(v) -> str:
    return re.sub(r"\D", "", _texto(v))


def cnpj_valido(c) -> bool:
    c = so_digitos(c)
    if len(c) != 14 or len(set(c)) == 1:
        return False

    def dv(base, pesos):
        s = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return "0" if s < 2 else str(11 - s)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(c[:12], p1)
    d2 = dv(c[:12] + d1, [6] + p1)
    return c[12:] == d1 + d2


def _dia(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < float(v) < 80000:
        # numero de serie do Excel
        from datetime import timedelta                  # noqa: PLC0415
        return date(1899, 12, 30) + timedelta(days=int(float(v)))
    t = _texto(v)
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%y", "%m/%d/%y"):
        try:
            return datetime.strptime(t.split(" ")[0][:10], f).date()
        except ValueError:
            pass
    return None


def _cod6(v) -> str:
    v = _texto(v)
    return v.zfill(6) if v.isdigit() else v


def pasta_prospeccao(raiz=None) -> Path:
    return Path(raiz or AQUI) / SUB_PROSPECCAO


def _config(raiz) -> dict:
    try:
        return json.loads((Path(raiz) / "planner_config.json")
                          .read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def parametros(raiz=None, cfg=None) -> dict:
    """{arquivo} do Planner (Parametros > PROSPECCAO)."""
    cfg = cfg if cfg is not None else _config(raiz or AQUI)
    par = cfg.get("parametros") or {}
    return {"arquivo": _texto(par.get("arquivo_prospeccao_forms"))}


def _momento(v) -> datetime | None:
    """A hora de conclusao do Forms (datetime, numero do Excel ou texto)."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)) and 20000 < float(v) < 80000:
        return datetime(1899, 12, 30) + timedelta(days=float(v))
    t = _texto(v)
    for f in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
              "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
              "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M"):
        try:
            return datetime.strptime(t[:19], f)
        except ValueError:
            pass
    d = _dia(v)
    return datetime(d.year, d.month, d.day) if d else None


def dia_do_envio(conclusao, uf="AM") -> date | None:
    """(22/10, Alexandre) O DIA DA VISITA = o dia do envio, no fuso da UF
    do vendedor (a hora do Forms em UTC)."""
    m = _momento(conclusao)
    if m is None:
        return None
    if HORA_DO_FORMS_EM_UTC:
        m = m + timedelta(hours=FUSO_UF.get(_texto(uf).upper(), -4))
    return m.date()


# ------------------------------------------------------------ o arquivo
def candidatos(raiz=None) -> list[Path]:
    """Os .xlsx de respostas que podem ser a fonte: os do OneDrive com
    "Prospec" e "BAP" no nome (a raiz do OneDrive, onde o Forms grava) e os
    soltos em RELATORIOS\\Visitas\\PROSPECCAO (menos os PROSPECCAO_AAAAMM
    que o BAP grava)."""
    achados = []
    pasta = pasta_prospeccao(raiz)
    if pasta.exists():
        achados += [p for p in pasta.glob("*.xlsx")
                    if not p.name.upper().startswith(PREFIXO_SAIDA)
                    and not p.name.startswith("~$")]
    try:
        casa = Path.home()
        for od in casa.glob("OneDrive*"):
            if od.is_dir():
                for p in od.glob("*.xlsx"):
                    n = _sa(p.name)
                    if "prospec" in n and "bap" in n and \
                            not p.name.startswith("~$"):
                        achados.append(p)
    except OSError:
        pass
    return achados


def achar_arquivo(raiz=None, cfg=None) -> Path | None:
    raiz = Path(raiz or AQUI)
    par = parametros(raiz, cfg)
    if par["arquivo"]:
        p = Path(par["arquivo"])
        if not p.is_absolute():
            p = raiz / p
        if p.exists():
            return p
    cands = [p for p in candidatos(raiz) if p.exists()]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def ler_respostas(caminho) -> list[dict]:
    """As respostas do Excel do Forms (1a aba). O arquivo e copiado antes
    (o Excel/OneDrive pode estar com ele aberto)."""
    from openpyxl import load_workbook                  # noqa: PLC0415
    caminho = Path(caminho)
    tmp = Path(tempfile.mkdtemp(prefix="bap_prosp_")) / "respostas.xlsx"
    try:
        shutil.copy2(caminho, tmp)
        wb = load_workbook(tmp, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        try:
            cab = [_sa(c) for c in next(it)]
        except StopIteration:
            wb.close()
            return []

        def campo(t):
            if t in COL:
                return COL[t]
            if "cnpj" in t:
                return "cnpj"
            if t.startswith("data da visita"):
                return "data_forms"
            if t.startswith("vendedor"):
                return "vendedor"
            return None
        campos = [campo(t) for t in cab]
        saida = []
        for r in it:
            if not any(v not in (None, "") for v in r):
                continue
            d = {}
            for c, v in zip(campos, r):
                if c and c not in d:
                    d[c] = v
            saida.append(d)
        wb.close()
        return saida
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


# ---------------------------------------------------- o que valida contra
def equipe_do_planner(cfg) -> dict:
    """{e-mail ou nome sem acento: (cod6, nome, uf_base)} - so VENDEDOR
    ativo."""
    eq = {}
    for p in cfg.get("pessoas") or []:
        if _texto(p.get("cargo")).upper() != "VENDEDOR" or \
                p.get("ativo", True) is False:
            continue
        cod = _cod6(p.get("cod_protheus"))
        nome = _texto(p.get("nome")).upper()
        uf = _texto(p.get("uf_base")).upper() or "AM"
        if not cod:
            continue
        v = (cod, nome, uf)
        if _texto(p.get("email")):
            eq[_sa(p["email"])] = v
        if nome:
            eq.setdefault(_sa(nome), v)
            partes = _sa(nome).split()
            if len(partes) > 1:      # primeiro + ultimo nome
                eq.setdefault(f"{partes[0]} {partes[-1]}", v)
    return eq


_MEMO_BASE = {}


def base_e_cadastros(raiz) -> tuple[set, dict]:
    """(CNPJs da aba BASE_CLIENTE, {CNPJ: DATA_CADASTRO} das abas
    BASE_CLIENTE e EXCLUIDOS) da BASE_CLIENTE.xlsx. (27/10) guardado
    enquanto a BASE_CLIENTE nao muda (o app e validado a cada farol)."""
    arq = Path(raiz) / "RELATORIOS" / "BASE_CLIENTE.xlsx"
    try:
        st_ = arq.stat()
        chave = (str(arq), st_.st_mtime, st_.st_size)
    except OSError:
        return set(), {}
    if _MEMO_BASE.get("chave") == chave:
        return _MEMO_BASE["valor"]
    valor = _ler_base_e_cadastros(arq)
    _MEMO_BASE.update(chave=chave, valor=valor)
    return valor


def _ler_base_e_cadastros(arq) -> tuple[set, dict]:
    from openpyxl import load_workbook                  # noqa: PLC0415
    base, cad = set(), {}
    tmp = Path(tempfile.mkdtemp(prefix="bap_prosp_")) / arq.name
    try:
        shutil.copy2(arq, tmp)
        wb = load_workbook(tmp, read_only=True, data_only=True)
        for aba in ("BASE_CLIENTE", "EXCLUIDOS"):
            if aba not in wb.sheetnames:
                continue
            it = wb[aba].iter_rows(values_only=True)
            try:
                cab = [_texto(c).upper() for c in next(it)]
            except StopIteration:
                continue
            if "CNPJ" not in cab:
                continue
            i_c = cab.index("CNPJ")
            i_d = cab.index("DATA_CADASTRO") if "DATA_CADASTRO" in cab \
                else None
            for r in it:
                c = so_digitos(r[i_c]) if i_c < len(r) else ""
                if not c:
                    continue
                c = c.zfill(14) if len(c) > 11 else c
                if aba == "BASE_CLIENTE":
                    base.add(c)
                if i_d is not None and i_d < len(r):
                    d = _dia(r[i_d])
                    if d:
                        cad.setdefault(c, d)
        wb.close()
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    return base, cad


def _lote_fora(cfg) -> set:
    try:
        import planner_nucleo as nu                     # noqa: PLC0415
        return nu.datas_cadastro_lote_fora(cfg)
    except Exception:                                   # noqa: BLE001
        return set()


# ---------------------------------------------------------------- validar
def validar(respostas, equipe, base_cnpj, cad_por_cnpj, lote_fora=(),
            ja_contados=None):
    """Devolve a lista com STATUS e OBSERVACAO por resposta (ordem de
    envio). O dia da visita = o dia do envio (hora de conclusao) no fuso
    da UF do vendedor. ja_contados: {(cod6, cnpj, dia)} que ja CONTARAM
    numa rodada anterior (o DUPLICADO vale entre rodadas)."""
    vistos = set(ja_contados or ())
    saida = []
    for r in sorted(respostas, key=lambda x: (str(_momento(x.get(
            "conclusao")) or ""), str(x.get("id")))):
        st, obs = ST_CONTA, []
        cnpj = so_digitos(r.get("cnpj"))
        if 12 <= len(cnpj) < 14:
            cnpj = cnpj.zfill(14)        # o Excel come o zero da esquerda
        por_email = equipe.get(_sa(r.get("email")))
        por_nome = equipe.get(_sa(r.get("vendedor")))
        dono = por_email or por_nome
        dia = dia_do_envio(r.get("conclusao"), dono[2] if dono else "AM")
        if por_email and por_nome and por_email[0] != por_nome[0]:
            obs.append(f"respondeu com a conta de {por_email[1]} e marcou "
                       f"{por_nome[1]}: conta para o dono da conta")
        if dono and not por_email:
            obs.append("e-mail da conta fora do cadastro do Planner: "
                       "vendedor pela pergunta Vendedor")
        if not dono:
            st = ST_SEM_VEND
        elif not cnpj_valido(cnpj):
            st = ST_CNPJ
        elif dia is None:
            st = ST_CNPJ
            obs.append("sem a hora de envio")
        elif dia in lote_fora:
            st = ST_LOTE
        elif cad_por_cnpj.get(cnpj) == dia:
            st = ST_CADASTRADO
            obs.append("já conta como CAD. no Farol: não soma de novo")
        elif cnpj in base_cnpj:
            st = ST_BASE
            obs.append("é cliente da base: a visita vai pela Máxima")
        elif (dono[0], cnpj, dia) in vistos:
            st = ST_DUPLICADO
        if st == ST_CONTA:
            vistos.add((dono[0], cnpj, dia))
        saida.append(dict(r, cod6=dono[0] if dono else "",
                          vendedor_bap=dono[1] if dono else "",
                          dia=dia, cnpj=cnpj, status=st,
                          obs_bap="; ".join(obs)))
    return saida


def validar_app(respostas, equipe, base_cnpj, cad_por_cnpj, lote_fora=(),
                ja_contados=None):
    """(27/10) A PROSPECCAO do app BAP Ajuda (respostas_bap_ajuda
    .prospeccoes), com as mesmas regras do validar(): vendedor pelo NOME
    gravado pelo app, dia = a data do app. ja_contados: {(cod6, cnpj,
    dia)} que ja CONTARAM no Forms (vira DUPLICADO)."""
    forms = set(ja_contados or ())
    vistos = set(forms)
    saida = []
    for r in respostas:
        st, obs = ST_CONTA, []
        cnpj = so_digitos(r.get("cnpj"))
        if 12 <= len(cnpj) < 14:
            cnpj = cnpj.zfill(14)
        n = _sa(r.get("vendedor"))
        partes = n.split()
        dono = equipe.get(n) or (equipe.get(f"{partes[0]} {partes[-1]}")
                                 if len(partes) > 1 else None)
        d = r.get("dia_app")
        if r.get("ja_na_base") == "SIM":
            obs.append("o app marcou JÁ NA BASE")
        if r.get("teste") or (dono and dono[0] in _cod_teste()):
            st = ST_TESTE
            obs.append("conta de teste do Alexandre: fora da visita")
        elif not dono:
            st = ST_SEM_VEND
        elif not cnpj_valido(cnpj):
            st = ST_CNPJ
        elif d is None:
            st = ST_CNPJ
            obs.append("sem a data")
        elif d in lote_fora:
            st = ST_LOTE
        elif cad_por_cnpj.get(cnpj) == d:
            st = ST_CADASTRADO
            obs.append("já conta como CAD. no Farol: não soma de novo")
        elif cnpj in base_cnpj:
            st = ST_BASE
            obs.append("é cliente da base: a visita vai pela Máxima")
        elif (dono[0], cnpj, d) in vistos:
            st = ST_DUPLICADO
            if (dono[0], cnpj, d) in forms:
                obs.append("já registrada no Forms")
        if st == ST_CONTA:
            vistos.add((dono[0], cnpj, d))
        saida.append(dict(r, cod6=dono[0] if dono else "",
                          vendedor_bap=dono[1] if dono else
                          _texto(r.get("vendedor")).upper(),
                          dia=d, cnpj=cnpj, status=st,
                          obs_bap="; ".join(obs)))
    return saida


def _cod_teste() -> set:
    try:
        import respostas_bap_ajuda as rb                # noqa: PLC0415
        return set(rb.COD_TESTE)
    except Exception:                                   # noqa: BLE001
        return {"000040"}


# ---------------------------------------------------- os arquivos do mes
def arquivo_do_mes(raiz, ano, mes) -> Path:
    return pasta_prospeccao(raiz) / f"{PREFIXO_SAIDA}{ano:04d}{mes:02d}.xlsx"


def _ler_saida(caminho) -> list[dict]:
    from openpyxl import load_workbook                  # noqa: PLC0415
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except (OSError, ValueError):
        return []
    try:
        it = wb.worksheets[0].iter_rows(values_only=True)
        cab = [_texto(c) for c in next(it)]
        mapa = {t: k for t, k in COLUNAS_SAIDA}
        saida = []
        for r in it:
            if not any(v not in (None, "") for v in r):
                continue
            d = {mapa[t]: v for t, v in zip(cab, r) if t in mapa}
            d["dia"] = _dia(d.get("dia"))
            d["cod6"] = _cod6(d.get("cod6"))
            saida.append(d)
        return saida
    except StopIteration:
        return []
    finally:
        wb.close()


def _gravar_saida(caminho, linhas) -> None:
    from openpyxl import Workbook                       # noqa: PLC0415
    from openpyxl.styles import Font, PatternFill       # noqa: PLC0415
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "PROSPECCAO"
    ws.append([t for t, _ in COLUNAS_SAIDA])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F7A4D")
    for l in linhas:
        lin = []
        for _, k in COLUNAS_SAIDA:
            v = l.get(k)
            if isinstance(v, datetime):
                v = v.strftime("%d/%m/%Y %H:%M")
            elif isinstance(v, date):
                v = v.strftime("%d/%m/%Y")
            lin.append(v)
        ws.append(lin)
    for i, (t, _) in enumerate(COLUNAS_SAIDA, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = \
            max(10, min(40, len(t) + 4))
    ws.freeze_panes = "A2"
    tmp = caminho.with_name(caminho.stem + "_gravando.xlsx")
    wb.save(tmp)
    tmp.replace(caminho)


def atualizar(raiz=None, log=None) -> dict:
    """Le o Excel do Forms, valida e ACRESCENTA as respostas novas (pelo ID)
    no PROSPECCAO_AAAAMM.xlsx do mes da visita. Devolve um resumo."""
    raiz = Path(raiz or AQUI)
    log = log or (lambda *_: None)
    cfg = _config(raiz)
    par = parametros(raiz, cfg)
    arq = achar_arquivo(raiz, cfg)
    res = {"arquivo": str(arq) if arq else "", "respostas": 0, "novas": 0,
           "conta": 0, "status": {}, "meses": []}
    if arq is None:
        res["erro"] = ("Excel de respostas do Forms não encontrado (Planner > "
                       "Parâmetros > PROSPECÇÃO, ou um .xlsx em "
                       "RELATORIOS\\Visitas\\PROSPECCAO).")
        log("Prospecção (Forms): " + res["erro"])
        return res
    resp = ler_respostas(arq)
    res["respostas"] = len(resp)
    # o que ja foi gravado (so acrescenta: a resposta gravada nao muda)
    gravados, ja_contados, por_mes = set(), set(), {}
    pasta = pasta_prospeccao(raiz)
    for p in sorted(pasta.glob(f"{PREFIXO_SAIDA}*.xlsx")) \
            if pasta.exists() else []:
        m = re.fullmatch(PREFIXO_SAIDA + r"(\d{4})(\d{2})", p.stem)
        if not m:
            continue
        ls = _ler_saida(p)
        por_mes[(int(m.group(1)), int(m.group(2)))] = ls
        for l in ls:
            gravados.add(_texto(l.get("id")))
            if l.get("status") == ST_CONTA:
                ja_contados.add((l["cod6"], so_digitos(l.get("cnpj")),
                                 l["dia"]))
    novas = [r for r in resp if _texto(r.get("id")) not in gravados
             or not _texto(r.get("id"))]
    if not novas:
        log(f"Prospecção (Forms): {len(resp)} resposta(s), nenhuma nova.")
        return res
    base, cad = base_e_cadastros(raiz)
    val = validar(novas, equipe_do_planner(cfg), base, cad, _lote_fora(cfg),
                  ja_contados)
    agora = datetime.now()
    mexidos = set()
    for v in val:
        v["validado"] = agora
        d = v["dia"] or agora.date()
        por_mes.setdefault((d.year, d.month), []).append(v)
        mexidos.add((d.year, d.month))
    for (a, m) in sorted(mexidos):
        _gravar_saida(arquivo_do_mes(raiz, a, m), por_mes[(a, m)])
        res["meses"].append(f"{a:04d}-{m:02d}")
    st = Counter(v["status"] for v in val)
    res.update(novas=len(val), conta=st.get(ST_CONTA, 0), status=dict(st))
    log(f"Prospecção (Forms): {len(val)} resposta(s) nova(s), "
        f"{st.get(ST_CONTA, 0)} contam como visita · arquivo "
        f"{arq.name}")
    return res


# ------------------------------------------------------- o que os farois leem
_MEMO = {}


def linhas(raiz=None) -> list[dict]:
    """Todas as respostas ja validadas: as do Forms (os PROSPECCAO_AAAAMM
    .xlsx, FONTE = FORMS) e (27/10) as do app BAP Ajuda (FONTE = APP),
    validadas na hora. A conta de teste (000040) vira TESTE nas duas."""
    raiz = Path(raiz or AQUI)
    pasta = pasta_prospeccao(raiz)
    arqs = sorted(p for p in pasta.glob(f"{PREFIXO_SAIDA}*.xlsx")
                  if re.fullmatch(PREFIXO_SAIDA + r"\d{6}", p.stem)) \
        if pasta.exists() else []
    try:
        import respostas_bap_ajuda as rb                # noqa: PLC0415
        ass_app = rb.assinatura(raiz)
    except Exception:                                   # noqa: BLE001
        rb, ass_app = None, ()
    try:
        b_ = (raiz / "RELATORIOS" / "BASE_CLIENTE.xlsx").stat()
        ass_base = (b_.st_mtime, b_.st_size)
    except OSError:
        ass_base = ()
    try:
        c_ = (raiz / "planner_config.json").stat()
        ass_cfg = (c_.st_mtime, c_.st_size)
    except OSError:
        ass_cfg = ()
    chave = (tuple((p.name, p.stat().st_mtime, p.stat().st_size)
                   for p in arqs), ass_app,
             ass_base if ass_app else (), ass_cfg if ass_app else ())
    if _MEMO.get("chave") == chave and str(pasta) == _MEMO.get("pasta"):
        return _MEMO["linhas"]
    saida = []
    teste = _cod_teste()
    for p in arqs:
        for l in _ler_saida(p):
            l["fonte"] = FONTE_FORMS
            if l.get("cod6") in teste:
                l["status"] = ST_TESTE
                l["obs_bap"] = "conta de teste do Alexandre: fora da visita"
            saida.append(l)
    if rb is not None and ass_app:
        try:
            cfg = _config(raiz)
            app = rb.prospeccoes(raiz, cfg)
            if app:
                base, cad = base_e_cadastros(raiz)
                ja = {(l["cod6"], so_digitos(l.get("cnpj")), l["dia"])
                      for l in saida if l.get("status") == ST_CONTA}
                saida += validar_app(app, equipe_do_planner(cfg), base, cad,
                                     _lote_fora(cfg), ja)
        except Exception:                               # noqa: BLE001
            pass
    _MEMO.update(chave=chave, pasta=str(pasta), linhas=saida)
    return saida


def contagem(raiz=None, de=None, ate=None) -> dict:
    """{(cod6 do vendedor, dia): visitas de prospeccao que CONTAM}."""
    c = Counter()
    for l in linhas(raiz):
        if l.get("status") != ST_CONTA or not l.get("dia") or \
                not l.get("cod6"):
            continue
        if (de and l["dia"] < de) or (ate and l["dia"] > ate):
            continue
        c[(l["cod6"], l["dia"])] += 1
    return dict(c)
