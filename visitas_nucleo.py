# -*- coding: utf-8 -*-
"""
VISITAS - o arquivo de visitas da Maxima (maxGestao > Painel Auditoria >
GridRca.csv), dia a dia, e o acompanhamento em Excel.

Onde fica (tudo relativo a pasta deste script):
    RELATORIOS/Visitas/diario/AAAAMMDD.csv     um GridRca por dia
    RELATORIOS/Visitas/AAAAMM.csv              o GridRca do mes (o Farol de
                                               Metas le este, como antes)
    RELATORIOS/Visitas/maxima_equipe.json      filiais, supervisores e
                                               representantes como a Maxima
                                               chama (lido da tela)
    RELATORIOS/Visitas/ACOMPANHAMENTO_VISITAS_BAP.xlsx
                                               uma linha por vendedor por dia.
                                               SO ACRESCENTA LINHA: dia ja
                                               gravado nunca muda.

O GridRca traz uma linha por representante. Os tempos (TEMPODESLOCAMENTO e
TEMPOATENDIMENTO) sao MEDIAS por visita (TMD e TMA), e os horarios sao o
primeiro e o ultimo cliente atendido - por isso o arquivo e baixado DIA A
DIA: num periodo longo a Maxima junta tudo numa linha so.

DIA FECHADO: o arquivo do dia foi baixado num dia DEPOIS dele (o de hoje
ainda muda ate o vendedor sincronizar). So dia fechado vai para o Excel.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SUB_VISITAS = Path("RELATORIOS") / "Visitas"
SUB_DIARIO = SUB_VISITAS / "diario"
ARQ_EQUIPE = "maxima_equipe.json"
ARQ_INDICE = "_baixados.json"
ARQ_ACOMP = "ACOMPANHAMENTO_VISITAS_BAP.xlsx"
ABA_ACOMP = "VISITAS_DIA"

# o cabecalho do GridRca (para o dia sem nenhuma linha na Maxima)
CABECALHO_GRID = (
    "CODIGOGERAL;NOME;PREPOSTO;CODIGOGRUPOFILIAL;CODIGOGRUPOSUPERVISOR;"
    "HORAATENDIMENTOPRIMEIROCLIENTE;HORAATENDIMENTOULTIMOCLIENTE;"
    "HORAULTIMAPOSICAO;TEMPODESLOCAMENTO;TEMPOATENDIMENTO;STATUS;AGENDADOS;"
    "VISITADOSA;VISITADOSFORAA;TOTALVISITADOSDENTROAGENDAFORAAGENDA;"
    "POSITIVADOSA;POSITIVADOSFORAA;TOTALPOSITIVADOSDENTROAGENDAFORAAGENDA;"
    "PERCENTFORAASOBREPOSITIVADOSA;PERCPOSITIVADOSOBRECARTEIRA;"
    "PERCPOSITIVADODENTROFORASOBRECARTEIRA;PERCCLIENTENAOPOSITIVADO;"
    "PERCVISITADOORDEM;PERCEFICIENCIA;VALORVENDA;VALORVENDATOTAL;"
    "VALORVENDAPREV;TICKETMEDIO;KMTRABALHADO;"
    "PRODUTOENTREVALORAJUDACUSTOEKMTRABALHADO;KMTOTALRODADO;"
    "PRODUTOENTREVALORAJUDACUSTOEKMTOTALRODADO;"
    "TOTALACURACIADISTANCIATOTALRODADO;"
    "PERCMARGEMERRODISTANCIATOTALRODADOFORMAT;STATUSGPS;VERSAOGPS")

DIAS_SEMANA = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM")


# =========================================================================
# pastas e nomes
# =========================================================================
def pasta_visitas(raiz=None) -> Path:
    return Path(raiz or AQUI) / SUB_VISITAS


def pasta_diario(raiz=None) -> Path:
    return Path(raiz or AQUI) / SUB_DIARIO


def arquivo_do_dia(raiz, d: date) -> Path:
    return pasta_diario(raiz) / f"{d:%Y%m%d}.csv"


def arquivo_do_mes(raiz, ano: int, mes: int) -> Path:
    return pasta_visitas(raiz) / f"{ano}{mes:02d}.csv"


def arquivo_acompanhamento(raiz=None) -> Path:
    return pasta_visitas(raiz) / ARQ_ACOMP


def dias_entre(de: date, ate: date):
    d = de
    while d <= ate:
        yield d
        d += timedelta(days=1)


def meses_entre(de: date, ate: date):
    """[(ano, mes)] de 'de' ate 'ate'."""
    a, m = de.year, de.month
    saida = []
    while (a, m) <= (ate.year, ate.month):
        saida.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return saida


def fim_do_mes(ano: int, mes: int) -> date:
    prox = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return prox - timedelta(days=1)


# =========================================================================
# o indice: quando cada arquivo foi baixado (para saber se o dia fechou)
# =========================================================================
def _ler_json(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text("utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(caminho)


def indice(raiz=None) -> dict:
    """{"AAAAMMDD" ou "AAAAMM": "AAAA-MM-DDTHH:MM:SS" (quando baixou)}"""
    return _ler_json(pasta_diario(raiz) / ARQ_INDICE, {})


def anotar_baixado(raiz, chave: str, quando: datetime | None = None) -> None:
    ind = indice(raiz)
    ind[chave] = (quando or datetime.now()).isoformat(timespec="seconds")
    _gravar_json(pasta_diario(raiz) / ARQ_INDICE, ind)


def baixado_em(raiz, chave: str, caminho: Path) -> datetime | None:
    v = indice(raiz).get(chave)
    if v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            pass
    try:                       # arquivo posto a mao: vale a data do arquivo
        return datetime.fromtimestamp(caminho.stat().st_mtime)
    except OSError:
        return None


def dia_fechado(raiz, d: date) -> bool:
    """O arquivo do dia existe e foi baixado num dia depois dele (a regra
    unica esta em dia_fechado_no_indice, RN-VIS-002)."""
    arq = arquivo_do_dia(raiz, d)
    if not arq.exists():
        return False
    quando = baixado_em(raiz, f"{d:%Y%m%d}", arq)
    return bool(quando) and dia_fechado_no_indice(
        {f"{d:%Y%m%d}": quando.isoformat()}, d)


def mes_fechado(raiz, ano: int, mes: int) -> bool:
    arq = arquivo_do_mes(raiz, ano, mes)
    if not arq.exists():
        return False
    quando = baixado_em(raiz, f"{ano}{mes:02d}", arq)
    return bool(quando and quando.date() > fim_do_mes(ano, mes))


# =========================================================================
# leitura do GridRca
# =========================================================================
def _texto(v) -> str:
    return "" if v is None else str(v).strip().strip('"').strip()


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


_LIGACAO = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def chave_de_nome(nome) -> str:
    """Igual a do Gerador de Meta: sem acento, sem pontuacao, sem 'da/de'."""
    limpo = re.sub(r"[^A-Z ]", " ", _sem_acento(_texto(nome)).upper())
    return " ".join(p for p in limpo.split() if p and p not in _LIGACAO)


def _curta(chave: str) -> str:
    p = chave.split()
    return f"{p[0]} {p[-1]}" if len(p) > 1 else chave


def _num(v) -> float:
    s = _texto(v).replace("R$", "").replace("%", "").replace(" ", "")
    if not s or s in ("-",):
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _antes_da_barra(v) -> float:
    """'24 / 63,16%' -> 24"""
    return _num(_texto(v).split("/")[0])


def _segundos(v) -> int | None:
    """'08:57:45' -> segundos; vazio -> None."""
    m = re.match(r"^\s*(\d{1,3}):(\d{2})(?::(\d{2}))?", _texto(v))
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0)


def _hora(v) -> int | None:
    """Horario do dia: 00:00:00 na Maxima = nao teve."""
    s = _segundos(v)
    return s if s else None


def _decodificar(dados: bytes) -> str:
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(cod)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", errors="replace")


def csv_valido(texto: str) -> bool:
    cab = texto.lstrip("﻿").split("\n", 1)[0].upper()
    return "CODIGOGERAL" in cab and "TOTALVISITADOS" in cab


def ler_grid(caminho) -> list[dict]:
    """As linhas do GridRca, ja convertidas."""
    caminho = Path(caminho)
    try:
        txt = _decodificar(caminho.read_bytes())
    except OSError:
        return []
    if not txt.strip():
        return []
    amostra = txt[:4096]
    sep = ";" if amostra.count(";") >= amostra.count(",") else ","
    leitor = csv.DictReader(io.StringIO(txt.lstrip("﻿")), delimiter=sep)
    titulos = {re.sub(r"[^A-Z0-9]", "", (c or "").upper()): c
               for c in (leitor.fieldnames or [])}

    def g(linha, nome):
        c = titulos.get(nome)
        return linha.get(c) if c else None
    saida = []
    for ln in leitor:
        cod = _texto(g(ln, "CODIGOGERAL"))
        nome = re.sub(r"\s+", " ", _texto(g(ln, "NOME")))
        if not cod and not nome:
            continue
        vis = g(ln, "TOTALVISITADOSDENTROAGENDAFORAAGENDA")
        if vis is None:
            vis = g(ln, "TOTALVISITAS")
        saida.append({
            "cod": cod, "nome_max": nome,
            "filial": _texto(g(ln, "CODIGOGRUPOFILIAL")),
            "cod_sup": _texto(g(ln, "CODIGOGRUPOSUPERVISOR")),
            "primeiro": _hora(g(ln, "HORAATENDIMENTOPRIMEIROCLIENTE")),
            "ultimo": _hora(g(ln, "HORAATENDIMENTOULTIMOCLIENTE")),
            "ult_pos": _hora(g(ln, "HORAULTIMAPOSICAO")),
            "tmd": _segundos(g(ln, "TEMPODESLOCAMENTO")) or 0,
            "tma": _segundos(g(ln, "TEMPOATENDIMENTO")) or 0,
            "agendados": int(_num(g(ln, "AGENDADOS"))),
            "vis_agenda": int(_antes_da_barra(g(ln, "VISITADOSA"))),
            "vis_fora": int(_antes_da_barra(g(ln, "VISITADOSFORAA"))),
            "visitas": int(_num(vis)),
            "venda": _num(g(ln, "VALORVENDATOTAL")),
            "km_trab": _num(g(ln, "KMTRABALHADO")),
            "km_total": _num(g(ln, "KMTOTALRODADO")),
            "gps": _texto(g(ln, "STATUSGPS")).upper() == "TRUE",
            "versao": _texto(g(ln, "VERSAOGPS")).strip(" -"),
        })
    return saida


# =========================================================================
# quem e quem: o Planner (cod Maxima, nome, cargo, supervisor) e a Maxima
# =========================================================================
def _cod6(v) -> str:
    t = _texto(v)
    return t.zfill(6) if t.isdigit() else t


def _ativos_do_planner_do_mes(raiz, mes: str) -> dict:
    """(05/11) {cod Protheus do vendedor: ativo?} do PLANNER_BAP_AAAA-MM do
    mes (RELATORIOS ou backup), pela coluna VENDEDOR_ATIVO. Sem o PLANNER
    do mes: {} (fica a equipe de agora, como sempre)."""
    try:
        import meta_nucleo as mn                        # noqa: PLC0415
        import pastas_bap as pb                         # noqa: PLC0415
        arq = pb.planner_do_mes(raiz, mes)
        if arq is None:
            return {}
        saida = {}
        for c in mn.ler_planner(arq).get("clientes") or []:
            cod = _cod6(c.get("cod_vendedor"))
            if cod:
                saida[cod] = saida.get(cod, False) or \
                    c.get("vendedor_ativo", True) is not False
        return saida
    except Exception:                                   # noqa: BLE001
        return {}


class Equipe:
    """Casa a linha do GridRca com a pessoa do Planner: pelo codigo Maxima,
    depois pelo nome, depois por nome que comeca igual (so se for um)."""

    def __init__(self, raiz=None, mes: str | None = None):
        """mes 'AAAA-MM': a equipe do Planner daquele mes (PLANNER_MESES),
        para saber quem estava ATIVO; sem o arquivo do mes, a de agora -
        com o ATIVO/INATIVO do PLANNER_BAP_AAAA-MM do mes, quando ele
        existe (05/11)."""
        raiz = Path(raiz or AQUI)
        cfg = {}
        if mes:
            cfg = _ler_json(raiz / "SISTEMA BAP" / "PLANNER_MESES" /
                            f"planner_config_{mes}.json", {})
        sem_cfg_do_mes = not cfg.get("pessoas")
        if sem_cfg_do_mes:
            cfg = _ler_json(raiz / "planner_config.json", {})
        self.pessoas = [p for p in cfg.get("pessoas") or []
                        if p.get("nome")]
        # (05/11, Alexandre) MES FECHADO FICA COMO ERA: quem trabalhou no
        # mes conta no mes, mesmo inativado depois. Sem a configuracao do
        # mes, o ATIVO de cada vendedor vem do PLANNER do mes (coluna
        # VENDEDOR_ATIVO) e nao do planner_config.json de hoje
        if mes and sem_cfg_do_mes and self.pessoas:
            ativo_mes = _ativos_do_planner_do_mes(raiz, mes)
            self.pessoas = [
                dict(p, ativo=ativo_mes[_cod6(p.get("cod_protheus"))])
                if _cod6(p.get("cod_protheus")) in ativo_mes else p
                for p in self.pessoas]
        self.por_cod_max = {}
        self.por_cod = {}
        self.por_nome = {}
        for p in self.pessoas:
            cm = _texto(p.get("cod_maxima"))
            if cm:
                self.por_cod_max.setdefault(cm, p)
            cp = _texto(p.get("cod_protheus"))
            if cp:
                self.por_cod.setdefault(cp, p)
            self.por_nome.setdefault(chave_de_nome(p["nome"]), p)
        mx = _ler_json(pasta_visitas(raiz) / ARQ_EQUIPE, {})
        self.sup_max = mx.get("supervisores") or {}
        self.fil_max = mx.get("filiais") or {}
        self._cache = {}

    def pessoa(self, cod, nome):
        k = (cod, nome)
        if k in self._cache:
            return self._cache[k]
        p = self.por_cod_max.get(_texto(cod))
        if p is None:
            ch = chave_de_nome(nome)
            p = self.por_nome.get(ch)
            if p is None and ch:
                parecidos = [q for c, q in self.por_nome.items()
                             if c and (c.startswith(ch + " ")
                                       or ch.startswith(c + " "))]
                if len(parecidos) == 1:
                    p = parecidos[0]
            if p is None and ch:      # primeiro nome + ultimo sobrenome
                curta = _curta(ch)
                iguais = [q for c, q in self.por_nome.items()
                          if c and _curta(c) == curta]
                if len(iguais) == 1:
                    p = iguais[0]
        self._cache[k] = p
        return p

    def supervisor(self, cod_sup, pessoa=None) -> str:
        cod_sup = _texto(cod_sup)
        for cand in (self.por_cod.get(cod_sup), self.por_cod_max.get(cod_sup)):
            if cand and _texto(cand.get("cargo")).upper() in (
                    "SUPERVISOR", "GERENTE", "COORDENADOR"):
                return _texto(cand["nome"]).upper()
        if cod_sup in self.sup_max:
            return _texto(self.sup_max[cod_sup]).upper()
        if pessoa and pessoa.get("responde_a"):
            chefe = self.por_cod.get(_texto(pessoa["responde_a"]))
            if chefe:
                return _texto(chefe["nome"]).upper()
        return f"SUPERVISOR {cod_sup}" if cod_sup else "(SEM SUPERVISOR)"

    def filial(self, cod) -> str:
        cod = _texto(cod)
        nome = _texto(self.fil_max.get(cod))
        return f"{cod} - {nome}" if nome else cod

    def completar(self, ln: dict) -> dict:
        p = self.pessoa(ln["cod"], ln["nome_max"])
        ln = dict(ln)
        ln["vendedor"] = (_texto(p["nome"]) if p else ln["nome_max"]).upper()
        ln["cargo"] = _texto(p.get("cargo")).upper() if p else "FORA DO PLANNER"
        ln["cod_protheus"] = _texto(p.get("cod_protheus")) if p else ""
        ln["supervisor"] = self.supervisor(ln["cod_sup"], p)
        ln["filial_nome"] = self.filial(ln["filial"])
        # VENDEDOR ATIVO no Planner do mes (o Farol de Visita so mostra
        # estes; supervisor, gerente e quem saiu ficam de fora)
        ln["ativo"] = bool(p and ln["cargo"] == "VENDEDOR"
                           and p.get("ativo", True) is not False)
        return ln


# =========================================================================
# o consolidado (o que o Farol de Visita usa)
# =========================================================================
def em_campo(ln: dict) -> bool:
    return ln["visitas"] > 0 or bool(ln["primeiro"])


def registros(raiz=None, de: date | None = None, ate: date | None = None,
              equipe: Equipe | None = None) -> list[dict]:
    """Uma linha por representante por dia, dos arquivos diarios."""
    pasta = pasta_diario(raiz)
    if not pasta.exists():
        return []
    equipes = {}

    def eq_do(d):
        if equipe is not None:
            return equipe
        m = f"{d:%Y-%m}"
        if m not in equipes:
            equipes[m] = Equipe(raiz, m)
        return equipes[m]
    saida = []
    for arq in sorted(pasta.glob("*.csv")):
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", arq.stem)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if (de and d < de) or (ate and d > ate):
            continue
        fechado = dia_fechado(raiz, d)
        eq = eq_do(d)
        for ln in ler_grid(arq):
            ln = eq.completar(ln)
            ln["data"] = d
            ln["fechado"] = fechado
            ln["arquivo"] = arq.name
            saida.append(ln)
    return saida


def dias_baixados(raiz=None) -> set:
    pasta = pasta_diario(raiz)
    saida = set()
    for arq in pasta.glob("*.csv") if pasta.exists() else []:
        try:
            saida.add(datetime.strptime(arq.stem, "%Y%m%d").date())
        except ValueError:
            pass
    return saida


def dias_faltando(raiz, de: date, ate: date) -> list[date]:
    """Dias de segunda a sexta sem o arquivo do dia."""
    tem = dias_baixados(raiz)
    return [d for d in dias_entre(de, ate) if d.weekday() < 5 and d not in tem]


def hhmm(seg) -> str:
    if seg is None:
        return "—"
    seg = int(round(seg))
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}"


def hms(seg) -> str:
    """TMA/TMD como a Maxima mostra: 00:24:30."""
    if seg is None:
        return "—"
    seg = int(round(seg))
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def resumir(linhas: list[dict]) -> dict:
    """As medias de um grupo de linhas (dias x vendedores)."""
    campo = [l for l in linhas if em_campo(l)]
    vis = sum(l["visitas"] for l in linhas)
    ag = sum(l["agendados"] for l in linhas)
    na_ag = sum(l["vis_agenda"] for l in linhas)
    # JORNADA (06/10): inicio, fim e jornada so de SEGUNDA A SEXTA - o
    # sabado (meio periodo) nao entra nessas medias
    util = [l for l in campo if l["data"].weekday() < 5]
    com_ini = [l["primeiro"] for l in util if l["primeiro"]]
    com_fim = [l["ultimo"] for l in util if l["ultimo"]]
    jorn = [l["ultimo"] - l["primeiro"] for l in util
            if l["primeiro"] and l["ultimo"] and l["ultimo"] >= l["primeiro"]]
    pv = [(l["tma"], l["visitas"]) for l in campo if l["visitas"]]
    pd = [(l["tmd"], l["visitas"]) for l in campo if l["visitas"] > 1]

    def pond(pares):
        peso = sum(p for _, p in pares)
        return sum(v * p for v, p in pares) / peso if peso else None
    dias = len(campo)
    return {
        "dias": dias,
        "dias_jornada": len(util),      # dias em campo de segunda a sexta
        # DIAS DE CALENDARIO com visita (06/10): um grupo (supervisor, total)
        # nunca passa dos dias do mes - "dias" e vendedor x dia (a media)
        "dias_corridos": len({l["data"] for l in campo}),
        "pessoas": len({l["cod"] for l in campo}),
        "visitas": vis,
        "vis_dia": vis / dias if dias else None,
        "agendados": ag,
        "na_agenda": na_ag,
        "fora": sum(l["vis_fora"] for l in linhas),
        "pct_agenda": na_ag / ag * 100.0 if ag else None,
        "tma": pond(pv),
        "tmd": pond(pd),
        "inicio": sum(com_ini) / len(com_ini) if com_ini else None,
        "fim": sum(com_fim) / len(com_fim) if com_fim else None,
        "jornada": sum(jorn) / len(jorn) if jorn else None,
        "km_dia": (sum(l["km_trab"] for l in campo) / dias) if dias else None,
        "km_rodado": sum(l["km_total"] for l in linhas),
        "km_rod_dia": (sum(l["km_total"] for l in campo) / dias)
        if dias else None,
        "venda": sum(l["venda"] for l in linhas),
        "sem_gps": sum(1 for l in campo if not l["gps"]),
    }


# =========================================================================
# o Excel de acompanhamento (SO ACRESCENTA)
# =========================================================================
COLUNAS_ACOMP = [
    ("DATA", 11), ("DIA", 6), ("COD MAXIMA", 11), ("VENDEDOR", 34),
    ("CARGO", 14), ("SUPERVISOR", 30), ("FILIAL", 30),
    ("PRIMEIRO CLIENTE", 10), ("ULTIMO CLIENTE", 10), ("JORNADA", 10),
    ("ULTIMA POSICAO GPS", 11), ("TMD (MEDIA)", 10), ("TMA (MEDIA)", 10),
    ("AGENDADOS", 10), ("VISITADOS NA AGENDA", 11),
    ("VISITADOS FORA DA AGENDA", 11), ("TOTAL VISITADOS", 10),
    ("% AGENDA", 9), ("VENDA MAXIMA R$", 13), ("KM TRABALHADO", 11),
    ("KM TOTAL", 10), ("GPS LIGADO", 8), ("ARQUIVO", 14), ("GRAVADO EM", 17)]


def _t(seg):
    return None if seg is None else time(seg // 3600 % 24, seg % 3600 // 60,
                                         seg % 60)


def _td(seg):
    return None if seg is None else timedelta(seconds=int(seg))


def _linha_excel(ln: dict, agora: datetime) -> list:
    jorn = (ln["ultimo"] - ln["primeiro"]) if (
        ln["primeiro"] and ln["ultimo"] and ln["ultimo"] >= ln["primeiro"]) \
        else None
    return [ln["data"], DIAS_SEMANA[ln["data"].weekday()], ln["cod"],
            ln["vendedor"], ln["cargo"], ln["supervisor"], ln["filial_nome"],
            _t(ln["primeiro"]), _t(ln["ultimo"]), _td(jorn), _t(ln["ult_pos"]),
            _td(ln["tmd"]), _td(ln["tma"]), ln["agendados"], ln["vis_agenda"],
            ln["vis_fora"], ln["visitas"],
            (ln["vis_agenda"] / ln["agendados"]) if ln["agendados"] else None,
            round(ln["venda"], 2), round(ln["km_trab"], 1),
            round(ln["km_total"], 1), "SIM" if ln["gps"] else "NAO",
            ln["arquivo"], agora.replace(microsecond=0)]


def atualizar_acompanhamento(raiz=None, log=None) -> dict:
    """Acrescenta no Excel os dias FECHADOS que ainda nao estao la.
    Nunca altera linha gravada. Devolve {"novas": n, "dias": [...],
    "erro": texto ou ""}."""
    log = log or (lambda *_: None)
    from openpyxl import Workbook, load_workbook          # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    arq = arquivo_acompanhamento(raiz)
    ja = set()
    if arq.exists():
        try:
            wb = load_workbook(arq)
        except Exception as e:                           # noqa: BLE001
            return {"novas": 0, "dias": [],
                    "erro": f"Não abri o {arq.name}: {e}"}
        ws = wb[ABA_ACOMP] if ABA_ACOMP in wb.sheetnames else wb.worksheets[0]
        for d, _dia, cod, *_ in ws.iter_rows(min_row=2, values_only=True):
            if d is None:
                continue
            dd = d.date() if isinstance(d, datetime) else d
            ja.add((dd, _texto(cod)))
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = ABA_ACOMP
        ws.append([c for c, _ in COLUNAS_ACOMP])
        for i, (_, larg) in enumerate(COLUNAS_ACOMP, start=1):
            cel = ws.cell(row=1, column=i)
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = PatternFill("solid", fgColor="2F7D3A")
            cel.alignment = Alignment(horizontal="center", vertical="center",
                                      wrap_text=True)
            ws.column_dimensions[cel.column_letter].width = larg
        ws.row_dimensions[1].height = 30
        ws.freeze_panes = "E2"
    novas = [ln for ln in registros(raiz) if ln["fechado"]
             and (ln["data"], ln["cod"]) not in ja]
    if not novas:
        return {"novas": 0, "dias": [], "erro": ""}
    novas.sort(key=lambda l: (l["data"], l["supervisor"], l["vendedor"]))
    agora = datetime.now()
    formatos = {1: "dd/mm/yyyy", 8: "hh:mm", 9: "hh:mm", 10: "[h]:mm",
                11: "hh:mm", 12: "[h]:mm:ss", 13: "[h]:mm:ss", 18: "0%",
                19: "#,##0.00", 24: "dd/mm/yyyy hh:mm"}
    for ln in novas:
        ws.append(_linha_excel(ln, agora))
        r = ws.max_row
        for c, f in formatos.items():
            ws.cell(row=r, column=c).number_format = f
    ultima = ws.cell(row=1, column=len(COLUNAS_ACOMP)).column_letter
    ws.auto_filter.ref = f"A1:{ultima}{ws.max_row}"
    arq.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = arq.with_name(arq.stem + "_gravando.xlsx")
        wb.save(tmp)
        tmp.replace(arq)
    except PermissionError:
        return {"novas": 0, "dias": [],
                "erro": f"O {arq.name} está aberto no Excel: feche e "
                        f"atualize de novo (nada se perde)."}
    dias = sorted({ln["data"] for ln in novas})
    log(f"Excel: {len(novas)} linhas novas ({len(dias)} dia(s)).")
    return {"novas": len(novas), "dias": dias, "erro": ""}


def gravar_equipe_maxima(raiz, filiais: dict, supervisores: dict,
                         representantes: dict) -> None:
    """Os nomes que a Maxima mostra nos filtros (mescla com o que ja tem)."""
    arq = pasta_visitas(raiz) / ARQ_EQUIPE
    atual = _ler_json(arq, {})
    for chave, novo in (("filiais", filiais), ("supervisores", supervisores),
                        ("representantes", representantes)):
        d = dict(atual.get(chave) or {})
        d.update(novo or {})
        atual[chave] = d
    atual["lido_em"] = datetime.now().isoformat(timespec="seconds")
    _gravar_json(arq, atual)


# =========================================================================
# (18/10) O SINTETICO SAI DO ANALITICO
#   O robo nao baixa mais o GridRca. Para cada dia e cada representante ele
#   salva o Espelho de Rotas (Analitico) em Excel:
#     RELATORIOS/Visitas/ANALITICO/<NOME>/VISITA-<NOME>-DD-MM-AAAA-HH-MM.xlsx
#   (DD-MM-AAAA = o dia da visita; HH-MM = quando foi salvo). O cabecalho do
#   Espelho tem os mesmos numeros do GridRca (primeiro/ultimo cliente, TMD,
#   TMA, agendados, visitados na/fora da agenda, km, venda) e as linhas tem
#   cliente a cliente. Daqui saem:
#     diario/AAAAMMDD.csv   - uma linha por representante, NO FORMATO DO
#                             GridRca (o Farol de Visita, o acompanhamento e
#                             a RV continuam lendo igual)
#     AAAAMM.csv            - a soma do mes (o Farol de Metas)
#     VISITAS_POR_CLIENTE.xlsx - cliente a cliente: visitado, agendado e nao
#                             visitado, fora da agenda
# =========================================================================
SUB_ANALITICO = "ANALITICO"
ARQ_POR_CLIENTE = "VISITAS_POR_CLIENTE.xlsx"

# o rotulo do cabecalho do Espelho -> o campo
_ROTULOS_ESPELHO = {
    "PERIODO": "periodo", "FILIAL": "filial", "SUPERVISOR": "supervisor",
    "RCA": "rca", "PRIMEIRO CLIENTE": "primeiro",
    "ULTIMO CLIENTE": "ultimo", "ULTIMA POSICAO": "ult_pos",
    "TEMPO DESLOCAMENTO": "tmd", "TEMPO MEDIO ATENDIMENTO": "tma",
    "VALOR VENDIDO": "venda", "EM ANDAMENTO": "andamento",
    "KM TRABALHADO": "km_trab", "KM TOTAL": "km_total",
    "CLIENTES AGENDADOS": "agendados",
    "QTDE VISITADOS AGENDA": "vis_agenda",
    "QTDE VISITADOS FORA AGENDA": "vis_fora",
    "QTDE POSITIVADOS AGENDA": "pos_agenda",
    "QTDE POSITIVADOS FORA AGENDA": "pos_fora",
    "% VISITAS REALIZADAS NA SEQUENCIA PREVISTA": "pct_sequencia",
}
# as colunas da lista de clientes (o titulo da coluna -> o campo)
_COLUNAS_ESPELHO = {
    "DATA": "data", "ORD PREV": "ord_prev", "ORD REA": "ord_rea",
    "INICIO": "inicio", "FIM": "fim", "ATEND": "atend", "PER": "per",
    "ENDERECO": "endereco", "KM DIST": "km_dist", "CODIGO": "codigo",
    "CLIENTE": "cliente", "N PEDIDO": "n_pedido", "PEDIDO": "pedido",
    "BONIF": "bonif", "OBSERVACAO": "obs", "JUSTIFICATIVA": "justificativa",
    "AGEN": "agen", "PDV": "pdv",
}


def _rotulo(v) -> str:
    s = _sem_acento(_texto(v)).upper().replace("º", "").replace("°", "")
    s = re.sub(r"[^A-Z0-9% ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _data_espelho(v) -> date | None:
    """'10/16/2026' (o Excel da Maxima vem MES/DIA/ANO) ou data."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _texto(v)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if not m:
        return None
    a, b, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # o Espelho sai em ingles (mes/dia); se o 1o passar de 12, e dia/mes
    mes, dia = (a, b) if a <= 12 else (b, a)
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _periodo(txt) -> tuple:
    """'16/10/2026 à 18/10/2026' -> (date, date) (aqui e dia/mes/ano)."""
    ds = re.findall(r"(\d{2})/(\d{2})/(\d{4})", _texto(txt))
    out = []
    for d, m, a in ds[:2]:
        try:
            out.append(date(int(a), int(m), int(d)))
        except ValueError:
            pass
    if len(out) == 1:
        out.append(out[0])
    return tuple(out) if len(out) == 2 else (None, None)


def _abrir_excel(caminho):
    """O Excel do Espelho, so leitura (o leitor rapido do BAP, se houver)."""
    try:
        from xlsx_rapido import load_workbook             # noqa: PLC0415
    except Exception:                                     # noqa: BLE001
        from openpyxl import load_workbook                # noqa: PLC0415
    return load_workbook(caminho, read_only=True, data_only=True)


_RX_CODIGO_CLIENTE = re.compile(r"^\d{6,8}$")


def _linha_de_cliente(reg: dict) -> bool:
    """A UNICA regra do que e linha de cliente da lista (ler_espelho e
    filtrar_espelho): data valida ou codigo de 6 a 8 digitos. Rodape e
    total no meio da lista nao entram."""
    return bool(_data_espelho(reg.get("data"))
                or _RX_CODIGO_CLIENTE.fullmatch(_texto(reg.get("codigo"))))


def _eventos_espelho(linhas):
    """O laco UNICO de leitura do Espelho (ler_espelho e filtrar_espelho).
    Por linha nao vazia, gera:
      ("titulo",  ri, cel, colunas)            linha de titulos da lista
      ("cliente", ri, cel, reg, colunas)       linha da lista (reg: campo->valor)
      ("rotulo",  ri, i, campo, vals, rotulo, cels) cabecalho "Rotulo:" + valores
      ("solta",   ri, i, v)                    celula sem rotulo no cabecalho
    ri comeca em 1; cel = [(coluna, valor)]; cels = [(coluna, valor)] do rotulo."""
    colunas = None
    for ri, r in enumerate(linhas, start=1):
        cel = [(i, v) for i, v in enumerate(r)
               if v is not None and _texto(v) != ""]
        if not cel:
            continue
        rot = [_rotulo(v) for _, v in cel]
        # a linha de titulos da lista (repete a cada pagina)
        if "DATA" in rot and "CLIENTE" in rot and "CODIGO" in rot:
            colunas = {}
            for i, v in cel:
                campo = _COLUNAS_ESPELHO.get(_rotulo(v))
                if campo:
                    colunas[i] = campo
            yield ("titulo", ri, cel, colunas)
            continue
        if colunas:
            reg = {campo: r[i] if i < len(r) else None
                   for i, campo in colunas.items()}
            if _linha_de_cliente(reg):
                yield ("cliente", ri, cel, reg, colunas)
            continue
        # cabecalho: "Rotulo:" e o valor nas celulas seguintes
        k = 0
        while k < len(cel):
            i, v = cel[k]
            txt = _texto(v)
            if txt.endswith(":"):
                chave = _rotulo(txt[:-1])
                campo = next((c for r_, c in _ROTULOS_ESPELHO.items()
                              if chave == r_ or chave.startswith(
                                  r_ + " ")), None)
                j = k + 1
                while j < len(cel) and not _texto(
                        cel[j][1]).endswith(":"):
                    j += 1
                yield ("rotulo", ri, i, campo, [x for _, x in cel[k + 1:j]],
                       chave, cel[k + 1:j])
                k = j
            else:
                yield ("solta", ri, i, v)
                k += 1


def ler_espelho(caminho) -> dict | None:
    """O Excel do Espelho de Rotas (Analitico) de UM representante: o
    cabecalho (os numeros do GridRca) e a lista de clientes."""
    try:
        wb = _abrir_excel(caminho)
    except Exception:                                     # noqa: BLE001
        return None
    cab, linhas = {}, []
    try:
        for ws in wb.worksheets:
            for ev in _eventos_espelho(ws.iter_rows(values_only=True)):
                if ev[0] == "cliente":
                    linhas.append(ev[3])
                elif ev[0] == "rotulo" and ev[3]:
                    cab[ev[3]] = ev[4]
    finally:
        wb.close()
    if "rca" not in cab:
        return None

    def um(campo):
        v = cab.get(campo) or []
        return v[0] if v else None
    rca = cab.get("rca") or []
    sup = cab.get("supervisor") or []
    de, ate = _periodo(um("periodo"))
    clientes = []
    for reg in linhas:
        # (18/10) o codigo vem cod(6)+loja(2); a Maxima manda 7 digitos
        # quando a loja nao tem o zero ("0108114" = 010811 loja 04)
        cod = chave_cliente8(reg.get("codigo"))
        clientes.append({
            "data": _data_espelho(reg.get("data")),
            "ord_prev": _texto(reg.get("ord_prev")),
            "ord_rea": _texto(reg.get("ord_rea")),
            "inicio": _hora(reg.get("inicio")),
            "fim": _hora(reg.get("fim")),
            "atend": _segundos(reg.get("atend")) or 0,
            "per": _segundos(reg.get("per")) or 0,
            "endereco": _texto(reg.get("endereco")),
            "codigo": cod,
            "cod_cliente": cod[:6] if len(cod) >= 8 else cod,
            "loja": cod[6:8] if len(cod) >= 8 else "",
            "cliente": _texto(reg.get("cliente")),
            "pedido": _num(reg.get("pedido")),
            "n_pedido": _texto(reg.get("n_pedido")),
            "agendado": _texto(reg.get("agen")).upper().startswith("S"),
            "justificativa": _texto(reg.get("justificativa")),
            "pdv": _texto(reg.get("pdv")),
        })
    for c in clientes:
        c["visitado"] = bool(c["data"] or c["inicio"])
        # (18/10) o Excel da Maxima grava a data como mes/dia: ate o dia
        # 12 o Excel vira data trocada (01/10 -> 10/jan). Fora do periodo
        # do Espelho e com dia e mes trocados dentro dele: destroca
        dt = c["data"]
        if dt and de and ate and not (de <= dt <= ate) and dt.day <= 12:
            try:
                troca = date(dt.year, dt.day, dt.month)
            except ValueError:
                troca = None
            if troca and de <= troca <= ate:
                c["data"] = troca
    return {
        "de": de, "ate": ate,
        "filial": _texto(um("filial")),
        "cod_sup": re.sub(r"\D", "", _texto(sup[0])) if sup else "",
        "nome_sup": _texto(sup[1]) if len(sup) > 1 else "",
        "cod": re.sub(r"\D", "", _texto(rca[0])) if rca else "",
        "nome": _texto(rca[1]) if len(rca) > 1 else "",
        "primeiro": _texto(um("primeiro")) or "00:00:00",
        "ultimo": _texto(um("ultimo")) or "00:00:00",
        "ult_pos": _texto(um("ult_pos")) or "00:00:00",
        "tmd": _texto(um("tmd")) or "00:00:00",
        "tma": _texto(um("tma")) or "00:00:00",
        "agendados": int(_num(um("agendados"))),
        "vis_agenda_txt": _texto(um("vis_agenda")) or "0 / 0%",
        "vis_fora_txt": _texto(um("vis_fora")) or "0 / 0%",
        "pos_agenda_txt": _texto(um("pos_agenda")) or "0 / 0%",
        "pos_fora_txt": _texto(um("pos_fora")) or "0 / 0%",
        "pct_sequencia": _texto(um("pct_sequencia")),
        "venda": _num(um("venda")),
        "km_trab": _num(um("km_trab")),
        "km_total": _num(um("km_total")),
        "clientes": clientes,
        "arquivo": Path(caminho).name,
    }


def pasta_analitico(raiz=None) -> Path:
    return pasta_visitas(raiz) / SUB_ANALITICO


_RX_ARQ_ANALITICO = re.compile(
    r"^VISITA-(?P<nome>.+)-(?P<d>\d{2})-(?P<m>\d{2})-(?P<a>\d{4})-"
    r"(?P<h>\d{2})-(?P<mi>\d{2})(?:-\d+)?\.xlsx?$", re.I)


def chave_cliente8(cod) -> str:
    """O cliente como a rota do Planner (ROTA_PROTHEUS) grava: cod(6) +
    loja(2). "0108114" (loja sem o zero) -> "01081104"."""
    c = re.sub(r"\D", "", _texto(cod))
    if len(c) == 7:
        return c[:6] + "0" + c[6]
    return c


# (18/10) o que ja foi lido dos Espelhos fica guardado (por arquivo, data
# e tamanho): abrir o Farol de Visita nao rele 300 Excel toda vez
ARQ_CACHE_ANALITICO = "_leitura_analitico.pkl"
_VERSAO_CACHE_ANALITICO = 1
_MEM_ANALITICO = {}


def _ler_espelhos(raiz, arquivos) -> dict:
    """{Path: espelho ou None}, relendo so o arquivo novo ou mudado."""
    import os                                             # noqa: PLC0415
    import pickle                                         # noqa: PLC0415
    pasta = pasta_analitico(raiz)
    arq_cache = pasta / ARQ_CACHE_ANALITICO
    chave_mem = str(arq_cache)
    cache = _MEM_ANALITICO.get(chave_mem)
    if cache is None:
        try:
            cache = pickle.loads(arq_cache.read_bytes())
        except Exception:                                 # noqa: BLE001
            cache = {}
        if not isinstance(cache, dict) or cache.get(
                "_versao") != _VERSAO_CACHE_ANALITICO:
            cache = {"_versao": _VERSAO_CACHE_ANALITICO}
        _MEM_ANALITICO[chave_mem] = cache
    saida, mudou = {}, False
    for arq in arquivos:
        try:
            st = arq.stat()
        except OSError:
            continue
        assin = (st.st_mtime_ns, st.st_size)
        try:
            rel = arq.relative_to(pasta).as_posix()
        except ValueError:
            rel = str(arq)
        hit = cache.get(rel)
        if hit and hit[0] == assin:
            saida[arq] = hit[1]
            continue
        esp = ler_espelho(arq)
        cache[rel] = (assin, esp)
        saida[arq] = esp
        mudou = True
    if mudou:
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            tmp = arq_cache.with_name(f"{arq_cache.stem}_{os.getpid()}.tmp")
            tmp.write_bytes(pickle.dumps(cache, protocol=4))
            tmp.replace(arq_cache)
        except Exception:                                 # noqa: BLE001
            pass          # sem o cache so fica mais lento na proxima vez
    return saida


def espelhos_do_periodo(raiz, de: date, ate: date) -> dict:
    """{dia: [Espelho MAIS RECENTE de cada representante]} (o dia vem no
    nome do arquivo e e conferido no Periodo de dentro dele)."""
    pasta = pasta_analitico(raiz)
    if not pasta.exists():
        return {}
    candidatos = {}
    for arq in pasta.glob("*/VISITA-*.xls*"):
        m = _RX_ARQ_ANALITICO.match(arq.name)
        if not m:
            continue
        try:
            dia = date(int(m["a"]), int(m["m"]), int(m["d"]))
        except ValueError:
            continue
        if de <= dia <= ate:
            try:
                mt = arq.stat().st_mtime
            except OSError:
                continue
            candidatos.setdefault(dia, []).append((m["h"] + m["mi"], mt,
                                                   str(arq), arq))
    lidos = _ler_espelhos(raiz, [x[3] for lst in candidatos.values()
                                 for x in lst])
    saida = {}
    for d, lst in candidatos.items():
        por_rep = {}
        for *_, arq in sorted(lst, key=lambda x: x[:3]):
            esp = lidos.get(arq)
            if not esp or (esp["de"] and (esp["de"], esp["ate"]) != (d, d)):
                continue
            por_rep[esp["cod"] or esp["nome"]] = esp    # o ultimo vence
        if por_rep:
            saida[d] = list(por_rep.values())
    return saida


def espelhos_do_dia(raiz, d: date) -> list[dict]:
    """O Espelho MAIS RECENTE de cada representante daquele dia."""
    return espelhos_do_periodo(raiz, d, d).get(d, [])


def _linha_gridrca(esp: dict, gps=None, versao="") -> list:
    """Uma linha no formato do GridRca (as colunas do CABECALHO_GRID)."""
    va = int(_antes_da_barra(esp["vis_agenda_txt"]))
    vf = int(_antes_da_barra(esp["vis_fora_txt"]))
    pa = int(_antes_da_barra(esp["pos_agenda_txt"]))
    pf = int(_antes_da_barra(esp["pos_fora_txt"]))
    n = lambda x: (f"{x:.6f}".rstrip("0").rstrip(".")       # noqa: E731
                   .replace(".", ",") or "0")
    return [esp["cod"], esp["nome"], "", esp["filial"], esp["cod_sup"],
            esp["primeiro"], esp["ultimo"], esp["ult_pos"], esp["tmd"],
            esp["tma"], "", str(esp["agendados"]), esp["vis_agenda_txt"],
            esp["vis_fora_txt"], str(va + vf), esp["pos_agenda_txt"],
            esp["pos_fora_txt"], str(pa + pf), "", "", "", "",
            esp["pct_sequencia"], "", n(esp["venda"]), n(esp["venda"]), "",
            "", n(esp["km_trab"]), "", n(esp["km_total"]), "", "", "",
            "" if gps is None else ("True" if gps else "False"),
            versao or ""]


def _gravar_csv(destino: Path, linhas: list) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    buf.write(CABECALHO_GRID + "\n")
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    for ln in linhas:
        w.writerow(ln)
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    tmp.replace(destino)


def montar_dia(raiz, d: date, extras: dict | None = None) -> int:
    """diario/AAAAMMDD.csv (formato GridRca) com os Espelhos do dia.
    extras = {cod ou nome: {"gps": bool, "versao": str}} lido na tela.
    Devolve quantos representantes."""
    extras = extras or {}
    esps = espelhos_do_dia(raiz, d)
    if not esps:
        return 0
    linhas = []
    for e in sorted(esps, key=lambda e: e["nome"]):
        x = extras.get(e["cod"]) or extras.get(nome_chave(e["nome"])) or {}
        linhas.append(_linha_gridrca(e, x.get("gps"), x.get("versao", "")))
    _gravar_csv(arquivo_do_dia(raiz, d), linhas)
    return len(linhas)


def nome_chave(nome) -> str:
    return chave_de_nome(nome)


def montar_mes(raiz, ano: int, mes: int) -> int:
    """AAAAMM.csv: a soma dos dias do mes (diario/AAAAMMDD.csv), uma linha
    por representante - o Farol de Metas le o TOTALVISITADOS daqui."""
    pasta = pasta_diario(raiz)
    soma = {}
    for arq in sorted(pasta.glob(f"{ano}{mes:02d}[0-3][0-9].csv")):
        for ln in ler_grid(arq):
            k = ln["cod"] or ln["nome_max"]
            s = soma.setdefault(k, {
                "cod": ln["cod"], "nome": ln["nome_max"],
                "filial": ln["filial"], "sup": ln["cod_sup"], "ag": 0,
                "va": 0, "vf": 0, "venda": 0.0, "kt": 0.0, "km": 0.0,
                "tmd": 0, "tma": 0, "n": 0, "pri": None, "ult": None})
            s["ag"] += ln["agendados"]
            s["va"] += ln["vis_agenda"]
            s["vf"] += ln["vis_fora"]
            s["venda"] += ln["venda"]
            s["kt"] += ln["km_trab"]
            s["km"] += ln["km_total"]
            if ln["visitas"]:
                s["tmd"] += ln["tmd"] * ln["visitas"]
                s["tma"] += ln["tma"] * ln["visitas"]
                s["n"] += ln["visitas"]
    if not soma:
        return 0

    def hms_(seg):
        seg = int(seg or 0)
        return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
    linhas = []
    for s in sorted(soma.values(), key=lambda s: s["nome"]):
        n = s["n"] or 1
        pct = lambda x: (f"{x / s['ag'] * 100:.2f}%".replace(".", ",")  # noqa
                         if s["ag"] else "0%")
        esp = {"cod": s["cod"], "nome": s["nome"], "filial": s["filial"],
               "cod_sup": s["sup"], "primeiro": "00:00:00",
               "ultimo": "00:00:00", "ult_pos": "00:00:00",
               "tmd": hms_(s["tmd"] / n), "tma": hms_(s["tma"] / n),
               "agendados": s["ag"],
               "vis_agenda_txt": f"{s['va']} / {pct(s['va'])}",
               "vis_fora_txt": f"{s['vf']} / {pct(s['vf'])}",
               "pos_agenda_txt": "0 / 0%", "pos_fora_txt": "0 / 0%",
               "pct_sequencia": "", "venda": s["venda"],
               "km_trab": s["kt"], "km_total": s["km"]}
        linhas.append(_linha_gridrca(esp))
    _gravar_csv(arquivo_do_mes(raiz, ano, mes), linhas)
    return len(linhas)


COLUNAS_POR_CLIENTE = [
    ("DATA", 11), ("DIA", 6), ("COD MAXIMA", 11), ("VENDEDOR", 32),
    ("SUPERVISOR", 26), ("COD CLIENTE", 11), ("LOJA", 6), ("CLIENTE", 40),
    ("SITUACAO", 22), ("AGENDADO", 9), ("ORDEM PREVISTA", 9),
    ("ORDEM REALIZADA", 9), ("INICIO", 9), ("FIM", 9), ("ATENDIMENTO", 10),
    ("DESLOCAMENTO", 10), ("PEDIDO R$", 11), ("JUSTIFICATIVA", 26),
    ("ENDERECO", 44), ("ARQUIVO", 40)]


def atualizar_por_cliente(raiz=None, de: date | None = None,
                          ate: date | None = None, log=None) -> dict:
    """VISITAS_POR_CLIENTE.xlsx: cliente a cliente, de todos os dias que
    tem Espelho. Refeito inteiro a cada rodada (e um retrato, nao um
    acompanhamento: o acompanhamento que so acrescenta linha e o
    ACOMPANHAMENTO_VISITAS_BAP)."""
    from openpyxl import Workbook                         # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    log = log or (lambda *_: None)
    pasta = pasta_analitico(raiz)
    dias = set()
    for arq in pasta.glob("*/VISITA-*.xls*") if pasta.exists() else []:
        m = _RX_ARQ_ANALITICO.match(arq.name)
        if m:
            try:
                dias.add(date(int(m["a"]), int(m["m"]), int(m["d"])))
            except ValueError:
                pass
    dias = sorted(x for x in dias if (not de or x >= de)
                  and (not ate or x <= ate))
    wb = Workbook()
    ws = wb.active
    ws.title = "VISITAS_POR_CLIENTE"
    ws.append([c for c, _ in COLUNAS_POR_CLIENTE])
    for i, (_, larg) in enumerate(COLUNAS_POR_CLIENTE, start=1):
        cel = ws.cell(row=1, column=i)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="2F7D3A")
        cel.alignment = Alignment(horizontal="center", vertical="center",
                                  wrap_text=True)
        ws.column_dimensions[cel.column_letter].width = larg
    ws.freeze_panes = "E2"
    n = 0
    for d in dias:
        for e in espelhos_do_dia(raiz, d):
            for c in e["clientes"]:
                if c["visitado"]:
                    sit = ("VISITADO NA AGENDA" if c["agendado"]
                           else "VISITADO FORA DA AGENDA")
                else:
                    sit = "AGENDADO NAO VISITADO"
                dia = c["data"] or d
                ws.append([dia, DIAS_SEMANA[dia.weekday()], e["cod"],
                           e["nome"], e["nome_sup"], c["cod_cliente"],
                           c["loja"], c["cliente"], sit,
                           "SIM" if c["agendado"] else "NAO",
                           c["ord_prev"], c["ord_rea"], _t(c["inicio"]),
                           _t(c["fim"]), _td(c["atend"]) if c["atend"]
                           else None, _td(c["per"]) if c["per"] else None,
                           c["pedido"] or None, c["justificativa"],
                           c["endereco"], e["arquivo"]])
                r = ws.max_row
                ws.cell(row=r, column=1).number_format = "dd/mm/yyyy"
                for col in (13, 14):
                    ws.cell(row=r, column=col).number_format = "hh:mm"
                for col in (15, 16):
                    ws.cell(row=r, column=col).number_format = "[h]:mm"
                ws.cell(row=r, column=17).number_format = "#,##0.00"
                n += 1
    ultima = ws.cell(row=1, column=len(COLUNAS_POR_CLIENTE)).column_letter
    ws.auto_filter.ref = f"A1:{ultima}{max(ws.max_row, 1)}"
    arq = pasta_visitas(raiz) / ARQ_POR_CLIENTE
    arq.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = arq.with_name(arq.stem + "_gravando.xlsx")
        wb.save(tmp)
        tmp.replace(arq)
    except PermissionError:
        return {"linhas": 0, "erro": f"O {arq.name} está aberto no Excel: "
                                     f"feche e atualize de novo."}
    log(f"Por cliente: {n} linha(s) em Visitas\\{arq.name}.")
    return {"linhas": n, "erro": ""}


# =========================================================================
# ADERENCIA AO PLANNER (18/10, Alexandre): a aderencia do dia e medida
# contra a VISITA PROGRAMADA DO DIA NO PLANNER, nao contra a agenda da
# Maxima. A programacao e a rota que o Planner exportou para a Maxima
# (RELATORIOS/ROTA_PROTHEUS_AAAA-MM_*.json e EXPORTADOS/ROTA_PROTHEUS_TODOS_
# *.json): para cada vendedor e dia vale, entre os envios feitos ate o dia,
# o que mais bate com a agenda que a Maxima mostrou a ele (empate: o ultimo
# envio antes do dia). Os PROGRAMADOS sao sempre os do Planner. Dia sem
# nenhum envio do Planner ate ele: fica a agenda da Maxima (marcado). O
# sabado-deposito do Planner nao e dia de agenda.
# =========================================================================
_RX_ROTA_PLANNER = re.compile(
    r"^ROTA_PROTHEUS_(?:TODOS_|\d{4}-\d{2}_)(?:A_PARTIR_\d{2}-\d{2}_)?"
    r"(AJUSTADA_)?(\d{8})_(\d{4})"
    r"\.json$", re.I)
_MEM_ROTAS = {}

SIT_NA_ROTA = "VISITADO NA ROTA"
SIT_FORA = "VISITADO FORA DA ROTA"
SIT_NAO = "PROGRAMADO NÃO VISITADO"
FONTE_PLANNER = "PLANNER"
FONTE_MAXIMA = "AGENDA MÁXIMA"
# (18/10, Alexandre) A ROTA AJUSTADA: ROTA_PROTHEUS_AAAA-MM_AJUSTADA_*.json -
# os dias que ja passaram foram refeitos com o REALIZADO do vendedor e
# completados ate a meta do dia (12, sexta 6, interior 6) com a regra
# normal do Planner; o resto do mes e a rota nova. Ela vale para TODOS os
# dias do mes dela ate a data em que foi feita (passa por cima dos envios
# antigos); depois dela, um envio mais novo volta a valer.
FONTE_AJUSTADA = "PLANNER AJUSTADO"


def _ler_rota_planner(arq: Path) -> dict | None:
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        try:
            dados = json.loads(arq.read_bytes().decode("latin-1"))
        except Exception:                                 # noqa: BLE001
            return None
    if isinstance(dados, dict):
        dados = next((v for v in dados.values() if isinstance(v, list)), [])
    prog, por_dia = {}, {}
    for r in dados if isinstance(dados, list) else []:
        if not isinstance(r, dict):
            continue
        try:
            d = date.fromisoformat(_texto(r.get("dtproxvisita"))[:10])
        except ValueError:
            continue
        v = re.sub(r"\D", "", _texto(r.get("codusur"))).zfill(6)
        c = chave_cliente8(r.get("codcli"))
        if not c:
            continue
        prog.setdefault((v, d), set()).add(c)
        por_dia[d] = por_dia.get(d, 0) + 1
    # o sabado-deposito: o sabado que junta o excedente da rota (muito
    # mais linhas que um dia normal) - nao e dia de agenda
    uteis = sorted(n for d, n in por_dia.items() if d.weekday() < 5)
    mediana = uteis[len(uteis) // 2] if uteis else 0
    deposito = {d for d, n in por_dia.items()
                if d.weekday() == 5 and mediana and n > 3 * mediana}
    return {"prog": prog, "deposito": deposito}


def rotas_do_planner(raiz=None) -> list[dict]:
    """Os envios de rota do Planner, do mais antigo ao mais novo:
    [{"arquivo", "quando", "prog": {(vend6, dia): {cliente8}},
      "deposito": {dias}}]."""
    base = Path(raiz or AQUI) / "RELATORIOS"
    saida, vistos = [], set()
    # (20/10) os envios ficam na RELATORIOS\Roteirizacao; a RELATORIOS e
    # a EXPORTADOS ficam para os antigos que ainda nao foram movidos
    for pasta in (base / "Roteirizacao", base, base / "EXPORTADOS"):
        if not pasta.exists():
            continue
        for arq in pasta.glob("ROTA_PROTHEUS_*.json"):
            m = _RX_ROTA_PLANNER.match(arq.name)
            if not m:
                continue
            try:
                quando = datetime.strptime(m.group(2) + m.group(3),
                                           "%Y%m%d%H%M")
                st = arq.stat()
            except (ValueError, OSError):
                continue
            ajustada = bool(m.group(1))
            if (quando, ajustada) in vistos:
                continue
            k = (str(arq), st.st_mtime_ns, st.st_size)
            if k not in _MEM_ROTAS:
                _MEM_ROTAS[k] = _ler_rota_planner(arq)
            lida = _MEM_ROTAS[k]
            if not lida:
                continue
            vistos.add((quando, ajustada))
            saida.append({"arquivo": arq.name, "quando": quando,
                          "ajustada": ajustada,
                          "meses": {(d.year, d.month)
                                    for _v, d in lida["prog"]}, **lida})
    saida.sort(key=lambda r: r["quando"])
    return saida


def _escolher_rota(rotas, d: date, vend6: str, agenda_max: set):
    """A rota do Planner que valeu para ESTE vendedor no dia d. O Planner
    foi enviado varias vezes no mes e nem todo envio entrou na Maxima de
    todo vendedor - entao, entre os envios feitos ate o dia, vale o que
    mais bate com a agenda que a Maxima mostrou para ele naquele dia
    (a agenda da Maxima so escolhe a versao: os PROGRAMADOS sao sempre os
    do Planner). Empate (ou nenhum bate): o ultimo envio feito ANTES do dia
    - o do proprio dia so vale se nao houver anterior. Nenhum envio ate o
    dia: None (fica a agenda da Maxima)."""
    aj = [r for r in rotas if r.get("ajustada")
          and (d.year, d.month) in r.get("meses", ())]
    if aj:
        a = max(aj, key=lambda r: r["quando"])
        if d <= a["quando"].date():
            return a              # dia ja passado: vale a rota ajustada
        # depois dela: so ela e os envios mais novos que ela
        cand = [r for r in rotas if r is a or (
            r["quando"] > a["quando"] and r["quando"].date() <= d)]
    else:
        cand = [r for r in rotas if r["quando"].date() <= d]
    if not cand:
        return None

    def nota(r):
        ov = len(agenda_max & r["prog"].get((vend6, d), set()))
        antes = r["quando"].date() < d
        return (ov, antes, r["quando"] if antes else -r["quando"].timestamp())
    return max(cand, key=nota)


def aderencia_planner(raiz, de: date, ate: date) -> dict:
    """
    A aderencia de cada representante em cada dia (os Espelhos do
    ANALITICO x a rota do Planner):
      "dias": {(cod Maxima, dia): {programados, na_rota, fora, nao_visitados,
               visitados, agenda_max, fonte, rota, deposito, cod_protheus}}
      "clientes": cliente a cliente (visitado na rota / fora da rota /
               programado nao visitado)
      "rotas": {dia: {arquivos da rota usada}} (vazio = agenda da Maxima)
    """
    esps = espelhos_do_periodo(raiz, de, ate)
    rotas = rotas_do_planner(raiz) if esps else []
    equipes, dias, clientes, usadas = {}, {}, [], {}
    for d in sorted(esps):
        m = f"{d:%Y-%m}"
        if m not in equipes:
            equipes[m] = Equipe(raiz, m)
        eq = equipes[m]
        reps = []
        for e in esps[d]:
            p = eq.pessoa(e["cod"], e["nome"])
            cp = re.sub(r"\D", "", _texto(p.get("cod_protheus"))).zfill(6) \
                if p and _texto(p.get("cod_protheus")) else ""
            reps.append((e, p, cp))
        # o sabado-deposito vale mesmo antes do 1o envio (o Planner ja
        # tinha marcado o dia): nao e dia de agenda
        dep = any(d in r["deposito"] for r in rotas)
        usadas[d] = set()
        for e, p, cp in reps:
            por_cli = {}
            for c in e["clientes"]:
                k = chave_cliente8(c["codigo"])
                if not k:
                    continue
                atual = por_cli.get(k)
                # o mesmo cliente duas vezes: fica a linha visitada
                if atual is None or (c["visitado"] and not atual["visitado"]):
                    por_cli[k] = c
            visitados = {k for k, c in por_cli.items() if c["visitado"]}
            ag_max = {k for k, c in por_cli.items() if c["agendado"]}
            rota = _escolher_rota(rotas, d, cp, ag_max) if cp else None
            if rota:
                usadas[d].add(rota["arquivo"])
            # na rota ajustada, so o sabado-deposito DELA
            dep_v = (d in rota["deposito"]) if rota and rota.get(
                "ajustada") else dep
            f_pl = FONTE_AJUSTADA if rota and rota.get("ajustada") \
                else FONTE_PLANNER
            if dep_v:
                fonte, prog = (f_pl if rota else FONTE_MAXIMA), set()
            elif rota is None:
                fonte, prog = FONTE_MAXIMA, set(ag_max)
            else:
                fonte = f_pl
                prog = set(rota["prog"].get((cp, d), ()))
            na_rota = visitados & prog
            fora = visitados - prog
            nao = prog - visitados
            dias[(e["cod"], d)] = {
                "programados": len(prog), "na_rota": len(na_rota),
                "fora": len(fora), "nao_visitados": len(nao),
                "visitados": len(visitados), "agenda_max": len(ag_max),
                "fonte": fonte, "rota": rota["arquivo"] if rota else None,
                "deposito": dep_v,
                "cod_protheus": cp}
            for k in sorted(visitados | nao):
                c = por_cli.get(k) or {}
                sit = SIT_NA_ROTA if k in na_rota else (
                    SIT_FORA if k in fora else SIT_NAO)
                clientes.append({
                    "data": d, "cod_max": e["cod"], "nome_max": e["nome"],
                    "cod_protheus": cp, "chave": k, "cod_cliente": k[:6],
                    "loja": k[6:8], "cliente": c.get("cliente", ""),
                    "situacao": sit, "programado": k in prog,
                    "agenda_max": k in ag_max,
                    "inicio": c.get("inicio"), "fim": c.get("fim"),
                    "atend": c.get("atend") or 0, "per": c.get("per") or 0,
                    "ord_prev": c.get("ord_prev", ""),
                    "ord_rea": c.get("ord_rea", ""),
                    "pedido": c.get("pedido") or 0.0,
                    "n_pedido": c.get("n_pedido", ""),
                    "justificativa": c.get("justificativa", ""),
                    "endereco": c.get("endereco", ""), "fonte": fonte})
    return {"dias": dias, "clientes": clientes, "rotas": usadas}


def programados_por_dia(raiz, de: date, ate: date) -> dict:
    """(18/10) {(vendedor6, dia): programados do Planner} de `de` a `ate`,
    pela rota em vigor em cada dia (a mesma escolha da aderencia, sem a
    agenda da Maxima) - e o que falta do mes para o "ate a data" dos
    cartoes. O sabado-deposito nao conta."""
    rotas = rotas_do_planner(raiz)
    if not rotas:
        return {}
    vends = {v for r in rotas for (v, d) in r["prog"] if de <= d <= ate}
    saida = {}
    d = de
    while d <= ate:
        for v in vends:
            r = _escolher_rota(rotas, d, v, set())
            if r is None or d in r["deposito"]:
                continue
            n = len(r["prog"].get((v, d), ()))
            if n:
                saida[(v, d)] = n
        d += timedelta(days=1)
    return saida


# =========================================================================
# Visitas na nuvem (T-0045, ADR 0004, contrato visitas-nuvem.md)
# Funcoes puras: sem I/O (fora o filtrar_espelho), fuso de Manaus.
# =========================================================================
try:
    from zoneinfo import ZoneInfo
    FUSO_MANAUS = ZoneInfo("America/Manaus")
except Exception:                                         # noqa: BLE001
    from datetime import timezone
    FUSO_MANAUS = timezone(timedelta(hours=-4))


def _quando_manaus(v) -> datetime | None:
    """iso (ou datetime) -> datetime com fuso de Manaus; sem fuso = Manaus."""
    if isinstance(v, dict):
        v = v.get("baixado_em")
    if isinstance(v, datetime):
        dt = v
    else:
        try:
            dt = datetime.fromisoformat(str(v))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=FUSO_MANAUS)
    return dt.astimezone(FUSO_MANAUS)


def juntar_baixado(nuvem: dict | None, pc: dict | None) -> dict:
    """RN-VIS-002: o indice unico. Entradas: {AAAAMMDD: iso | {"baixado_em":
    iso, "erros_vendedor": n, "refeito": b}}. Para cada dia vale a MAIOR hora
    entre a nuvem e o PC (empate: a nuvem). Saida: {AAAAMMDD: {"baixado_em":
    iso Manaus, "origem": "nuvem"|"pc"}}; erros_vendedor e refeito so
    acompanham a origem "nuvem"."""
    saida: dict = {}
    nuvem, pc = nuvem or {}, pc or {}
    for chave in sorted(set(nuvem) | set(pc)):
        n = _quando_manaus(nuvem.get(chave))
        p = _quando_manaus(pc.get(chave))
        if n is None and p is None:
            continue
        if p is None or (n is not None and n >= p):
            ent = {"baixado_em": n.isoformat(timespec="seconds"),
                   "origem": "nuvem"}
            bruto = nuvem.get(chave)
            if isinstance(bruto, dict):
                for k in ("erros_vendedor", "refeito"):
                    if k in bruto:
                        ent[k] = bruto[k]
        else:
            ent = {"baixado_em": p.isoformat(timespec="seconds"),
                   "origem": "pc"}
        saida[chave] = ent
    return saida


def dia_fechado_no_indice(indice: dict | None, d: date) -> bool:
    """RN-VIS-002: fechado = baixado num dia (Manaus) DEPOIS dele. A
    importacao nao fecha: vale a hora da baixa."""
    q = _quando_manaus((indice or {}).get(f"{d:%Y%m%d}"))
    return bool(q and q.date() > d)


def dias_a_baixar(indice: dict | None, de: date, ate: date, hoje: date,
                  refazer: bool = False) -> list[date]:
    """Os dias da rodada, em ordem. Nunca passa de hoje (hoje so entra
    quando o chamador pede ate=hoje, o botao; o dia fica aberto). Sem
    `refazer`, pula o dia ja fechado no indice."""
    ate = min(ate, hoje)
    return [d for d in dias_entre(de, ate)
            if refazer or not dia_fechado_no_indice(indice, d)]


# --- lista de permitidas do Espelho (RN-VIS-007, contrato 3.6) -----------
# as colunas que NUNCA saem do Espelho (o site espelha esta lista) (o resto das tabelas do ler_espelho sobe)
_FORA_DO_ESPELHO = ("KM DIST", "BONIF", "OBSERVACAO")
ESPELHO_PERMITIDAS = {
    "cabecalho": tuple(_ROTULOS_ESPELHO),
    "colunas": tuple(c for c in _COLUNAS_ESPELHO
                     if c not in _FORA_DO_ESPELHO),
}

# formato conferido por coluna (o resto e texto)
_FORMATO_COLUNA = {
    "DATA": "data", "ORD PREV": "ord", "ORD REA": "ord", "INICIO": "hora",
    "FIM": "hora", "ATEND": "hora", "PER": "hora", "CODIGO": "codigo",
    "N PEDIDO": "n_pedido", "PEDIDO": "numero", "AGEN": "sn",
}
_FORMATO_CABECALHO = {
    "TEMPO DESLOCAMENTO": "hora", "TEMPO MEDIO ATENDIMENTO": "hora",
    "VALOR VENDIDO": "numero", "KM TRABALHADO": "numero",
    "KM TOTAL": "numero", "CLIENTES AGENDADOS": "numero",
    "QTDE VISITADOS AGENDA": "numero", "QTDE VISITADOS FORA AGENDA": "numero",
    "QTDE POSITIVADOS AGENDA": "numero",
    "QTDE POSITIVADOS FORA AGENDA": "numero",
    "% VISITAS REALIZADAS NA SEQUENCIA PREVISTA": "numero",
}

_RX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_RX_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\d)\d{14}(?!\d)")
_RX_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|(?<!\d)\d{11}(?!\d)")
_RX_FONE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}-\d{4}|\(\d{2}\)\s?\d{8,9}")
_RX_FORMATO = {
    "ord": re.compile(r"^\d{1,3}$"),
    "codigo": _RX_CODIGO_CLIENTE,
    "n_pedido": re.compile(r"^\d{1,10}$"),
    "sn": re.compile(r"^[SN]$", re.I),
    "hora": re.compile(r"^\d{1,3}:\d{2}(:\d{2})?$"),
    "data": re.compile(r"^\d{1,2}/\d{1,2}/\d{4}( \d{1,2}:\d{2}(:\d{2})?)?$"),
    # numero, "n / p%" ou "1.234,56"
    "numero": re.compile(
        r"^-?[\d.,]+\s*%?(\s*/\s*-?[\d.,]+\s*%?)?$"),
}


_REDE = (("email", _RX_EMAIL), ("cnpj", _RX_CNPJ), ("cpf", _RX_CPF),
         ("telefone", _RX_FONE))
# os tipos de achado (o site espelha); "formato" vem da conferencia da coluna
TIPOS_ACHADO = tuple(t for t, _ in _REDE) + ("formato",)


def _na_rede(s: str, tipos=None) -> str | None:
    for tipo, rx in _REDE:
        if (tipos is None or tipo in tipos) and rx.search(s):
            return tipo
    return None


def achar_dado_pessoal(valor, formato: str = "texto") -> str | None:
    """RN-VIS-007: a rede da varredura. Devolve o TIPO achado ("email",
    "cnpj", "cpf", "telefone" ou "formato") ou None. Nunca devolve o
    valor. formato: texto, hora, numero, data, ord, codigo, n_pedido, sn."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (datetime, date, time)):
        return None if formato in ("data", "hora", "texto") else "formato"
    if isinstance(valor, (int, float)):
        s = str(int(valor)) if float(valor).is_integer() else str(valor)
        if formato == "texto":
            return _na_rede(s, ("cnpj", "cpf", "telefone"))
        if formato in ("hora", "data", "sn"):
            return "formato"
        if formato in ("ord", "codigo", "n_pedido"):
            return None if _RX_FORMATO[formato].match(s) else "formato"
        return None
    s = str(valor).strip()
    if not s:
        return None
    achado = _na_rede(s)
    if achado:
        return achado
    rx = _RX_FORMATO.get(formato)
    if rx is not None and not rx.match(s):
        return "formato"
    return None


def _rotulo_seguro(rot: str) -> str | None:
    """Nome de coluna/rotulo que pode sair em `colunas_fora`: so se parece
    com nome (sem digitos longos) e passa na varredura; senao None."""
    rot = (rot or "")[:40]
    if not rot or re.search(r"\d{4,}", rot) or achar_dado_pessoal(rot):
        return None
    return rot


def filtrar_espelho(origem, destino, limpar_cliente=None,
                    limpar_texto=None) -> dict:
    """RN-VIS-007: copia o Espelho de `origem` para `destino` so com as
    colunas permitidas (mesma posicao; o resto fica vazio), limpa CLIENTE e
    JUSTIFICATIVA e varre o que sobrou. Devolve {"colunas_fora", "limpos",
    "achados"}: `colunas_fora` leva so NOMES de colunas/rotulos cortados
    (nunca valor de celula); nenhum valor de celula na saida. Com achado,
    quem chama NAO deve mandar o destino. Usa o mesmo laco do ler_espelho."""
    from openpyxl import Workbook                         # noqa: PLC0415
    if limpar_cliente is None or limpar_texto is None:
        import relatorios_nucleo as _rn                   # noqa: PLC0415
        limpar_cliente = limpar_cliente or _rn.cliente_sem_documento
        limpar_texto = limpar_texto or _rn.texto_sem_contato
    perm_cab = {_ROTULOS_ESPELHO[r] for r in ESPELHO_PERMITIDAS["cabecalho"]}
    perm_col = {_COLUNAS_ESPELHO[c] for c in ESPELHO_PERMITIDAS["colunas"]}
    nome_cab = {v: k for k, v in _ROTULOS_ESPELHO.items()}
    nome_col = {v: k for k, v in _COLUNAS_ESPELHO.items()}
    fora: list[str] = []
    limpos = {"CLIENTE": 0, "JUSTIFICATIVA": 0}
    achados: dict = {}

    def _fora(rot):
        rot = _rotulo_seguro(rot)
        if rot and rot not in fora and len(fora) < 20:
            fora.append(rot)

    def _achar(col, v, fmt):
        t = achar_dado_pessoal(v, fmt)
        if t:
            achados[(col[:40], t)] = achados.get((col[:40], t), 0) + 1

    wb = _abrir_excel(origem)
    saida = Workbook()
    saida.remove(saida.active)
    try:
        for ws in wb.worksheets:
            wo = saida.create_sheet(ws.title[:31])
            for ev in _eventos_espelho(ws.iter_rows(values_only=True)):
                tipo, ri = ev[0], ev[1]
                if tipo == "titulo":
                    for i, v in ev[2]:
                        if ev[3].get(i) in perm_col:
                            wo.cell(ri, i + 1, v)
                        else:
                            _fora(_rotulo(v))
                elif tipo == "cliente":
                    cel, reg, colunas = ev[2], ev[3], ev[4]
                    for i, v in cel:
                        campo = colunas.get(i)
                        if campo not in perm_col:
                            continue
                        col = nome_col[campo]
                        if col == "CLIENTE":
                            novo = limpar_cliente(v)
                            limpos[col] += int(novo != _texto(v))
                            v = novo
                        elif col == "JUSTIFICATIVA":
                            novo = limpar_texto(v)
                            limpos[col] += int(novo != _texto(v))
                            v = novo
                        _achar(col, v, _FORMATO_COLUNA.get(col, "texto"))
                        wo.cell(ri, i + 1, v)
                elif tipo == "rotulo":
                    i, campo, cels = ev[2], ev[3], ev[6]
                    if campo not in perm_cab:
                        _fora(ev[5])
                        continue
                    nome = nome_cab[campo]
                    wo.cell(ri, i + 1, nome + ":")
                    for ii, vv in cels:
                        _achar(nome, vv,
                               _FORMATO_CABECALHO.get(nome, "texto"))
                        wo.cell(ri, ii + 1, vv)
                # "solta": celula sem rotulo, descartada sem registrar nada
        saida.save(destino)
    finally:
        wb.close()
    return {"colunas_fora": fora, "limpos": limpos,
            "achados": [{"coluna": c, "tipo": t, "n": n}
                        for (c, t), n in sorted(achados.items())]}
