"""T-0045 (ADR 0004, contrato visitas-nuvem v1): as visitas da Máxima no Render, lado do site.

O cron `bap-visitas-maxima` pede uma concessão, baixa o Espelho dos vendedores e manda um lote por dia; o robô do PC
importa o lote na volta de 30 min. Aqui ficam só a guarda e o registro: concessão (RN-VIS-004), teto de entradas por
dia (RN-VIS-008), pausa por código (RN-VIS-005 e 007), índice dos dias baixados (RN-VIS-002), fila de lotes
(`edicoes.Fila`) e o que a tela mostra. Quem baixa, filtra e monta o dia é o cron e o PC; o site nunca serve o Excel.

Disco (`<dados>/visitas/`): `estado.json` (gravação atômica), `lotes/` (a `Fila` e os corpos `<seq>.json.gz`),
`pedidos.jsonl` e `rodadas.jsonl` (só acréscimo). Nenhum nome de vendedor ou de cliente em log, resposta ou arquivo
de estado; o perfil, nunca o usuário, vai no registro dos pedidos.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import threading
import zipfile
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path

from .arquivos import gravar_json
from .edicoes import MANAUS, ErroEdicao, Fila

try:                                    # Linux (Render); no Windows de teste só a trava de thread
    import fcntl
except ImportError:                     # pragma: no cover
    fcntl = None

# ------------------------------------------------------------------ constantes (contrato §2; teste confere)
TENTATIVAS_DIA = {"agenda": 4, "pedido": 3, "retentativa": 1, "diagnostico": 2}      # RN-VIS-008
LOGINS_DIA_MAX = 8                                                                  # RN-VIS-008
CONCESSAO_MIN = 10                                                                  # RN-VIS-004
PEDIDO_MAX_DIAS = 7
PEDIDO_MAX_RODADAS = 3
FECHADOS_PC_DIAS = 40
LOTE_GZ_MAX = 8 * 1024 * 1024
LOTE_BRUTO_MAX = 24 * 1024 * 1024        # o JSON já descomprimido (trava de "bomba" de gzip)
ARQUIVO_MAX = 2 * 1024 * 1024
ARQUIVOS_MAX = 60
LOTE_GUARDA_DIAS = 7                     # depois de confirmado
LOTE_GUARDA_SEM_CONFIRMAR_DIAS = 30
RODADAS_NA_TELA = 10
MOTIVOS = tuple(TENTATIVAS_DIA)
RETENTATIVAS_AGENDA = ("06h30", "07h00", "07h30")
FASES = ("login", "inicio", "maxgestao", "menu", "filtros", "grade", "espelho", "filtro", "salvar", "envio")
NOVA_TENTATIVA = ("MAXIMA_FORA", "TELA_MUDOU", "NAVEGADOR_FALHOU", "SITE_RECUSOU", "RODADA_INTERROMPIDA",
                  "PARCIAL_TEMPO", "ERRO_INTERNO")
# o pedido do botão continua nas voltas seguintes (até PEDIDO_MAX_RODADAS) com estes códigos; os outros o encerram
PEDIDO_CONTINUA = tuple(c for c in NOVA_TENTATIVA if c != "MAXIMA_FORA")
PAUSAM = ("MAXIMA_SENHA", "MAXIMA_CONFIRMACAO", "MAXIMA_CAPTCHA", "MAXIMA_BLOQUEIO", "DADO_PESSOAL")   # RN-VIS-005/007
PEDE_FASE = ("TELA_MUDOU", "ERRO_INTERNO")
TELA_MUDOU_SEGUIDAS = 2

_CONF = "A Máxima pediu uma confirmação. Use o Atualizar visitas do PC; o admin retoma aqui depois."
# contrato §5: código -> (status, texto). `{h}` hora do fim, `{f}` etapa, `{d}` dia, `{n}` Excel com erro, `{c}` coluna,
# `{t}` "Tentamos de novo às HHhMM." (ou vazio)
CODIGOS = {
    "OK": ("ok", "Atualizado às {h}."),
    "NADA_A_FAZER": ("ok", ""),
    "PARCIAL_VENDEDOR": ("parcial", "{n} Excel com erro ({d})."),
    "PARCIAL_TEMPO": ("parcial", "Parte dos dias veio; o resto vem na próxima volta."),
    "MAXIMA_SENHA": ("erro", "A Máxima recusou o usuário ou a senha. Só o Alexandre troca no painel do Render; "
                             "depois, o admin clica em Retomar."),
    "MAXIMA_CONFIRMACAO": ("erro", _CONF),
    "MAXIMA_CAPTCHA": ("erro", _CONF),
    "MAXIMA_BLOQUEIO": ("erro", "A Máxima bloqueou o acesso do site. Use o Atualizar visitas do PC."),
    "DADO_PESSOAL": ("erro", "O Espelho da Máxima trouxe um dado que o site não pode guardar (coluna: {c}). "
                             "Use o Atualizar visitas do PC."),
    "MAXIMA_FORA": ("erro", "A Máxima não respondeu. {t}"),
    "TELA_MUDOU": ("erro", "A tela da Máxima mudou (etapa: {f}). Use o Atualizar visitas do PC até a correção."),
    "NAVEGADOR_FALHOU": ("erro", "O navegador do site parou. {t}"),
    "SITE_RECUSOU": ("parcial", "Um dia não foi aceito pelo site ({d})."),
    "SITE_FORA": ("erro", "O site não foi alcançado pelo serviço de visitas."),
    "RODADA_INTERROMPIDA": ("erro", "A rodada parou sem terminar. {t}"),
    "CONFIG_FALTANDO": ("erro", "Faltam as variáveis do serviço de visitas no Render."),
    "CONFIG_INSEGURA": ("erro", "O serviço de visitas está com depuração ligada e não roda assim."),
    "ERRO_INTERNO": ("erro", "Erro inesperado (etapa: {f})."),
}
STATUS_DO_CODIGO = {c: s for c, (s, _) in CODIGOS.items()}
TETO_DIA_TEXTO = ("O site já entrou o máximo de vezes hoje na Máxima. Use o Atualizar visitas do PC; "
                  "amanhã volta sozinho.")
TIPOS_ACHADO = ("cnpj", "cpf", "telefone", "email", "formato")

RE_ID_RODADA = re.compile(r"^R\d{8}T\d{6}$")
RE_DIA = re.compile(r"^\d{8}$")
RE_RECADO = re.compile(r"^R-\d{8}-\d{6}-alexandre$")
RE_ROTULO = re.compile(r"^[A-Z0-9% ]{1,40}$")
RE_SHA = re.compile(r"^[0-9a-f]{64}$")
RE_PASTA_MAL = re.compile(r"[\\/\x00-\x1f\x7f]|\.\.")
RE_NOME_ARQ = re.compile(r"^VISITA-(?P<pasta>.+)-(?P<d>\d{2})-(?P<m>\d{2})-(?P<a>\d{4})-\d{2}-\d{2}(?:-\d+)?\.xlsx$")
# varredura (RN-VIS-007): a mesma rede do cron (contrato §3.6), repetida aqui antes de gravar
RE_PESSOAL = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "cnpj": re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\d)\d{14}(?!\d)"),
    "cpf": re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|(?<!\d)\d{11}(?!\d)"),
    "telefone": re.compile(r"\(?\d{2}\)?\s?9?\d{4}-\d{4}|\(\d{2}\)\s?\d{8,9}"),
}
# colunas do Espelho que nunca saem do contêiner (contrato §3.6): o rótulo no Excel é motivo de recusa
COLUNAS_PROIBIDAS = ("KM DIST", "BONIF", "OBSERVACAO")
ZIP_MEMBRO_MAX = 8 * 1024 * 1024
_RX_TEXTO_XML = re.compile(r"<t(?:\s[^>]*)?>([^<]*)</t>")
_ESTADO_VAZIO = {"agenda": "desligada",
                 "diagnostico": {"estado": "pendente", "em": None, "codigo": None},
                 "pausado": None, "pedido": None, "rodada_ativa": None,
                 "falhas_seguidas": {"fase": None, "n": 0}, "indice": {}, "pc": {},
                 "tentativas_hoje": {"dia": "", "total": 0, "por_motivo": {}},
                 "fechados_pc_em": None, "conhecidas": {}, "avisos": {"lotes_sem_confirmar_vencidos": 0}}


def agora() -> datetime:
    return datetime.now(MANAUS)


def iso(d: datetime) -> str:
    return d.astimezone(MANAUS).isoformat(timespec="seconds")


def _dt(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None
    return d.replace(tzinfo=MANAUS) if d.tzinfo is None else d.astimezone(MANAUS)


def dia_ymd(d: date | datetime) -> str:
    return d.strftime("%Y%m%d")


def dia_valido(s) -> date | None:
    if not (isinstance(s, str) and RE_DIA.match(s)):
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def hhmm_h(d: datetime | None) -> str:
    return d.strftime("%Hh%M") if d else ""


class ErroVisitas(Exception):
    """Erro com resposta pronta: `corpo` é o JSON devolvido ao cron, ao robô ou à tela."""

    def __init__(self, status: int, corpo: dict):
        super().__init__(corpo.get("erro", ""))
        self.status, self.corpo = status, corpo


# ------------------------------------------------------------------ regras puras (testadas)
def dia_fechado(dia: str, baixado_em: str | None) -> bool:
    """RN-VIS-002: o dia fecha quando foi baixado num dia depois dele, pela hora da baixa em Manaus."""
    d, b = dia_valido(dia), _dt(baixado_em)
    return bool(d and b and b.date() > d)


def juntar_baixado(nuvem: dict | None, pc: str | None) -> dict | None:
    """RN-VIS-002: a maior das duas horas de baixa vale; `origem` é de quem é a maior (empate: o PC)."""
    n = _dt((nuvem or {}).get("baixado_em"))
    p = _dt(pc)
    if n is None and p is None:
        return None
    if p is None or (n is not None and n > p):
        return {"baixado_em": iso(n), "origem": "nuvem", "erros_vendedor": int(nuvem.get("erros_vendedor") or 0),
                "refeito": bool(nuvem.get("refeito"))}
    return {"baixado_em": iso(p), "origem": "pc", "erros_vendedor": 0, "refeito": False}


def periodo_padrao(indice: dict, hoje: date) -> tuple[str, str]:
    """O período do botão "Atualizar visitas": do dia aberto mais antigo (até PEDIDO_MAX_DIAS) até hoje."""
    de = hoje
    for k in range(PEDIDO_MAX_DIAS - 1, -1, -1):
        d = hoje - timedelta(days=k)
        e = indice.get(dia_ymd(d))
        if e is None or not dia_fechado(dia_ymd(d), e.get("baixado_em")):
            de = d
            break
    return dia_ymd(de), dia_ymd(hoje)


def validar_periodo(de, ate, hoje: date) -> tuple[date | None, date | None, str]:
    a, b = dia_valido(de), dia_valido(ate)
    if a is None or b is None:
        return None, None, "Período inválido."
    if a > b:
        return None, None, "A data inicial vem depois da final."
    if b > hoje:
        return None, None, "Não há visitas depois de hoje."
    if (b - a).days + 1 > PEDIDO_MAX_DIAS:
        return None, None, f"No máximo {PEDIDO_MAX_DIAS} dias por pedido; períodos maiores continuam no PC."
    return a, b, ""


def _texto_xml(xml: str) -> list[str]:
    return [t for t in _RX_TEXTO_XML.findall(xml)]


def achar_no_excel(dados: bytes) -> list[tuple[str, str]]:
    """RN-VIS-007 (segunda guarda): lê só o TEXTO das células (zip + XML; nunca serve nem interpreta o Excel) e
    devolve [(tipo, coluna_ou_"")] do que não pode ficar: dado pessoal e coluna fora da lista. Nenhum valor sai."""
    achados: list[tuple[str, str]] = []
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
        nomes = [n for n in z.namelist() if n == "xl/sharedStrings.xml" or n.startswith("xl/worksheets/")]
        textos: list[str] = []
        for n in nomes:
            info = z.getinfo(n)
            if info.file_size > ZIP_MEMBRO_MAX:
                return [("formato", "")]
            textos += _texto_xml(z.read(n).decode("utf-8", "replace"))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        return [("formato", "")]
    for t in textos:
        s = t.strip().upper()
        if s in COLUNAS_PROIBIDAS:
            achados.append(("coluna", s))
        for tipo, rx in RE_PESSOAL.items():
            if rx.search(t):
                achados.append((tipo, ""))
    return achados


def validar_lote(dia_url: str, corpo, hoje: date | None = None) -> list[str]:
    """Contrato §3.4: erros do esquema do lote, só com chave e índice (nunca nome nem valor). [] = confere."""
    er: list[str] = []
    hoje = hoje or agora().date()
    if not isinstance(corpo, dict):
        return ["corpo"]
    d = dia_valido(dia_url)
    if d is None:
        er.append("dia")
    elif d > hoje:
        er.append("dia: no futuro")
    if corpo.get("versao") != 1:
        er.append("versao")
    if not (isinstance(corpo.get("rodada"), str) and RE_ID_RODADA.match(corpo["rodada"])):
        er.append("rodada")
    if corpo.get("dia") != dia_url:
        er.append("dia: diferente da URL")
    if _dt(corpo.get("baixado_em")) is None:
        er.append("baixado_em")
    for k in ("vendedores", "erros_vendedor"):
        if not (_int(corpo.get(k)) and corpo[k] >= 0):
            er.append(k)
    eq = corpo.get("equipe")
    if not (isinstance(eq, dict) and set(eq) == {"filiais", "supervisores", "representantes"}
            and all(isinstance(v, dict) for v in eq.values())):
        er.append("equipe")
    if not isinstance(corpo.get("extras"), dict):
        er.append("extras")
    arqs = corpo.get("arquivos")
    if not (isinstance(arqs, list) and 0 < len(arqs) <= ARQUIVOS_MAX):
        er.append("arquivos")
        return er[:10]
    for i, a in enumerate(arqs):
        if not (isinstance(a, dict) and set(a) == {"pasta", "nome", "sha256", "bytes", "b64"}):
            er.append(f"arquivos[{i}]")
            continue
        p, nm = a["pasta"], a["nome"]
        if not (isinstance(p, str) and 0 < len(p) <= 120 and not RE_PASTA_MAL.search(p)):
            er.append(f"arquivos[{i}].pasta")
        m = RE_NOME_ARQ.match(nm) if isinstance(nm, str) and len(nm) <= 200 and not RE_PASTA_MAL.search(nm) else None
        if not (m and isinstance(p, str) and nm.startswith(f"VISITA-{p}-")
                and f"{m['a']}{m['m']}{m['d']}" == dia_url):
            er.append(f"arquivos[{i}].nome")
        if not (isinstance(a["sha256"], str) and RE_SHA.match(a["sha256"])):
            er.append(f"arquivos[{i}].sha256")
        if not (_int(a["bytes"]) and 0 < a["bytes"] <= ARQUIVO_MAX):
            er.append(f"arquivos[{i}].bytes")
        if not isinstance(a["b64"], str) or len(a["b64"]) > ARQUIVO_MAX * 4 // 3 + 8:
            er.append(f"arquivos[{i}].b64")
    return er[:10]


def decodificar_arquivos(corpo: dict) -> tuple[list[tuple[int, bytes]], list[str]]:
    """[(índice, bytes)] dos Excel (base64 válido, `bytes` e `sha256` certos) e os erros (chave e índice)."""
    import base64
    import binascii
    out, er = [], []
    for i, a in enumerate(corpo["arquivos"]):
        try:
            b = base64.b64decode(a["b64"], validate=True)
        except (binascii.Error, ValueError):
            er.append(f"arquivos[{i}].b64")
            continue
        if len(b) != a["bytes"] or len(b) > ARQUIVO_MAX:
            er.append(f"arquivos[{i}].bytes")
        elif hashlib.sha256(b).hexdigest() != a["sha256"]:
            er.append(f"arquivos[{i}].sha256")
        else:
            out.append((i, b))
    return out, er[:10]


def descomprimir(corpo_gz: bytes, limite: int = LOTE_BRUTO_MAX) -> bytes | None:
    """Descomprime com teto (None = inválido ou grande demais)."""
    try:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        bruto = d.decompress(corpo_gz, limite + 1)
        if len(bruto) > limite or d.unconsumed_tail:
            return None
        return bruto
    except zlib.error:
        return None


def texto_do_codigo(codigo: str, r: dict) -> str:
    """O texto do contrato §5 para uma rodada do `rodadas.jsonl` (sem nome de vendedor nem de cliente)."""
    _, modelo = CODIGOS.get(codigo, ("erro", "Código desconhecido."))
    dias = r.get("dias_faltando") or r.get("dias") or []
    d = dia_valido(dias[0]) if dias else None
    achados = r.get("achados") or []
    prox = r.get("proxima") or ""
    texto = modelo.format(
        h=hhmm_h(_dt(r.get("em"))), f=r.get("fase") or "?", d=d.strftime("%d/%m") if d else "?",
        n=int(r.get("erros_vendedor") or 0), c=(achados[0].get("coluna") if achados else "") or "?",
        t=f"Tentamos de novo às {prox}." if prox else "Tente mais tarde.")
    return texto.strip()


# ------------------------------------------------------------------ o estado em disco
class _Trava:
    """Thread + flock: a concessão e os contadores não podem se atropelar entre processos."""

    def __init__(self, v: "Visitas"):
        self.v = v

    def __enter__(self):
        self.v._trinco.acquire()
        self.f = None
        try:
            if fcntl:
                self.v.pasta.mkdir(parents=True, exist_ok=True)
                self.f = open(self.v.pasta / ".trava", "a")
                fcntl.flock(self.f, fcntl.LOCK_EX)
        except BaseException:
            if self.f:
                self.f.close()
            self.v._trinco.release()
            raise

    def __exit__(self, *a):
        if self.f:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()
        self.v._trinco.release()


class Visitas:
    def __init__(self, dados: Path, token: str = ""):
        self.pasta = Path(dados) / "visitas"
        self.token = token if len(token or "") >= 32 else ""        # sem o token (ou curto), as rotas do cron dão 401
        self._trinco = threading.RLock()
        self.fila = Fila(dados, "visitas/lotes", "LOTES_VISITAS")

    def _tranca(self):
        return _Trava(self)

    # -- estado
    def _ler(self, agora_: datetime) -> dict:
        try:
            e = json.loads((self.pasta / "estado.json").read_text(encoding="utf-8"))
            if not isinstance(e, dict):
                e = {}
        except (OSError, ValueError):
            e = {}
        for k, v in _ESTADO_VAZIO.items():
            e.setdefault(k, json.loads(json.dumps(v)))
        hoje = dia_ymd(agora_)
        if e["tentativas_hoje"].get("dia") != hoje:                 # RN-VIS-008: o dia de Manaus zera os contadores
            e["tentativas_hoje"] = {"dia": hoje, "total": 0, "por_motivo": {}}
        corte = dia_ymd(agora_ - timedelta(days=FECHADOS_PC_DIAS))   # o índice só guarda os últimos 40 dias
        for k in ("indice", "pc"):
            e[k] = {d: v for d, v in e[k].items() if d >= corte}
        self._vencer(e, agora_)
        return e

    def _gravar(self, e: dict) -> None:
        gravar_json(self.pasta / "estado.json", e)

    def _acrescentar(self, nome: str, reg: dict) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        with open(self.pasta / nome, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _vencer(self, e: dict, agora_: datetime) -> None:
        """RN-VIS-004: a concessão sem `progresso` por CONCESSAO_MIN vira RODADA_INTERROMPIDA (gravada pelo site)."""
        ra = e.get("rodada_ativa")
        if ra and (_dt(ra.get("vence_em")) or agora_) <= agora_:
            self._encerrar(e, ra["id"], {"codigo": "RODADA_INTERROMPIDA", "fase": ra.get("fase"), "dias_ok": [],
                                          "dias_faltando": ra.get("dias") or [], "erros_vendedor": 0,
                                          "duracao_s": None, "pico_mb": None, "achados": None, "medidas": None},
                           agora_, interrompida=True)
            self._gravar(e)

    def _tentativa(self, e: dict, motivo: str, agora_: datetime) -> dict:
        t = e["tentativas_hoje"]
        m = t["por_motivo"].setdefault(motivo, {"n": 0, "ultima_em": None, "codigo": None})
        return m

    def _proxima(self, e: dict, motivo: str, codigo: str) -> str:
        """"06h30" etc.: a próxima tentativa da agenda (contrato §3.1, item 7); só a agenda e dentro do teto."""
        if motivo != "agenda" or codigo not in NOVA_TENTATIVA:
            return ""
        n = e["tentativas_hoje"]["por_motivo"].get("agenda", {}).get("n", 0)
        return RETENTATIVAS_AGENDA[n - 1] if 1 <= n <= len(RETENTATIVAS_AGENDA) else ""

    def _encerrar(self, e: dict, rid: str, f: dict, agora_: datetime, interrompida: bool = False) -> bool:
        """Fecha a concessão `rid` com o `fim` `f` (já validado). Devolve se há pausa. Chamar com a trava."""
        ra = e["rodada_ativa"]
        motivo = ra["motivo"]
        codigo = f["codigo"]
        m = self._tentativa(e, motivo, agora_)
        m["codigo"] = codigo
        proxima = self._proxima(e, motivo, codigo)
        self._acrescentar("rodadas.jsonl", {
            "id": rid, "motivo": motivo, "codigo": codigo, "status": STATUS_DO_CODIGO.get(codigo, "erro"),
            "fase": f.get("fase"), "dias": ra.get("dias") or [], "dias_ok": f.get("dias_ok") or [],
            "dias_faltando": f.get("dias_faltando") or [], "erros_vendedor": f.get("erros_vendedor") or 0,
            "duracao_s": f.get("duracao_s"), "pico_mb": f.get("pico_mb"), "achados": f.get("achados"),
            "medidas": f.get("medidas"), "proxima": proxima, "em": iso(agora_)})
        e["rodada_ativa"] = None
        e["conhecidas"][rid] = codigo
        for k in sorted(e["conhecidas"])[:-100]:
            del e["conhecidas"][k]
        pausa = False
        if codigo in PAUSAM:                                        # RN-VIS-005/007: sem segunda tentativa
            e["pausado"] = {"codigo": codigo, "desde": iso(agora_)}
            pausa = True
        fs = e["falhas_seguidas"]
        if codigo == "TELA_MUDOU":
            fs["n"] = fs["n"] + 1 if fs.get("fase") == f.get("fase") else 1
            fs["fase"] = f.get("fase")
            if fs["n"] >= TELA_MUDOU_SEGUIDAS and not e["pausado"]:
                e["pausado"] = {"codigo": codigo, "desde": iso(agora_)}
                pausa = True
        elif not interrompida:
            e["falhas_seguidas"] = {"fase": None, "n": 0}
        if motivo == "diagnostico":
            e["diagnostico"] = {"estado": "ok" if codigo == "OK" else "falhou", "em": iso(agora_), "codigo": codigo}
        if motivo == "pedido" and e.get("pedido"):
            if codigo in PEDIDO_CONTINUA and e["pedido"].get("rodadas", 0) < PEDIDO_MAX_RODADAS and not pausa:
                pass
            else:
                e["pedido"] = None                                  # terminou, ou o botão "sai da fila"
        return pausa

    # -- 3.1 trabalho
    def trabalho(self, agora_: datetime | None = None) -> dict:
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            self._gravar(e)
        indice = {}
        for d in sorted(set(e["indice"]) | set(e["pc"])):
            j = juntar_baixado(e["indice"].get(d), e["pc"].get(d))
            if j:
                indice[d] = j
        ra = e["rodada_ativa"]
        return {"versao": 1, "agora": iso(agora_), "agenda": e["agenda"], "diagnostico": e["diagnostico"],
                "pausado": e["pausado"], "pedido": e["pedido"], "indice": indice,
                "tentativas_hoje": e["tentativas_hoje"], "falhas_seguidas": e["falhas_seguidas"],
                "fechados_pc_em": e["fechados_pc_em"],
                "rodada_ativa": {"id": ra["id"], "vence_em": ra["vence_em"]} if ra else None}

    # -- 3.2 concessão
    def conceder(self, corpo, agora_: datetime | None = None) -> dict:
        agora_ = agora_ or agora()
        if not (isinstance(corpo, dict) and corpo.get("motivo") in MOTIVOS):
            raise ErroVisitas(400, {"erro": "motivo fora da lista"})
        dias = corpo.get("dias")
        if not (isinstance(dias, list) and dias and all(dia_valido(x) for x in dias) and len(set(dias)) == len(dias)):
            raise ErroVisitas(400, {"erro": "dias vazio ou fora do formato"})
        if len(dias) > PEDIDO_MAX_DIAS or (corpo["motivo"] == "diagnostico" and len(dias) > 1):
            raise ErroVisitas(400, {"erro": "dias demais"})
        if corpo.get("pedido") is not None and not isinstance(corpo["pedido"], str):
            raise ErroVisitas(400, {"erro": "pedido fora do formato"})
        motivo = corpo["motivo"]
        with self._tranca():
            e = self._ler(agora_)
            if e["rodada_ativa"]:
                self._gravar(e)
                raise ErroVisitas(409, {"erro": "rodada ativa", "id": e["rodada_ativa"]["id"]})
            if e["pausado"]:
                self._gravar(e)
                raise ErroVisitas(423, {"erro": "pausado", "codigo": e["pausado"]["codigo"]})
            t = e["tentativas_hoje"]
            if t["total"] >= LOGINS_DIA_MAX or t["por_motivo"].get(motivo, {}).get("n", 0) >= TENTATIVAS_DIA[motivo]:
                self._gravar(e)
                raise ErroVisitas(429, {"erro": "teto do dia", "motivo": motivo})
            rid = "R" + agora_.strftime("%Y%m%dT%H%M%S")
            if rid in e["conhecidas"]:                              # duas concessões no mesmo segundo
                rid = "R" + (agora_ + timedelta(seconds=1)).strftime("%Y%m%dT%H%M%S")
            vence = agora_ + timedelta(minutes=CONCESSAO_MIN)
            e["rodada_ativa"] = {"id": rid, "vence_em": iso(vence), "motivo": motivo, "dias": list(dias),
                                 "fase": None, "inicio": iso(agora_)}
            t["total"] += 1                                         # RN-VIS-008: conta na concessão, cada uma é um login
            m = self._tentativa(e, motivo, agora_)
            m["n"] += 1
            m["ultima_em"] = iso(agora_)
            m["codigo"] = None
            if motivo == "pedido" and e["pedido"]:
                e["pedido"]["rodadas"] = int(e["pedido"].get("rodadas") or 0) + 1
            if motivo == "retentativa":                             # RN-VIS-006: uma só, com sucesso ou falha
                for d in dias:
                    if d in e["indice"]:
                        e["indice"][d]["refeito"] = True
            e["conhecidas"][rid] = None
            self._gravar(e)
        return {"id": rid, "vence_em": iso(vence)}

    # -- 3.3 progresso
    def progresso(self, rid: str, corpo, agora_: datetime | None = None) -> dict:
        agora_ = agora_ or agora()
        if not (isinstance(corpo, dict) and corpo.get("fase") in FASES
                and (corpo.get("dia") is None or dia_valido(corpo["dia"]))
                and all(corpo.get(k) is None or (_int(corpo[k]) and 0 <= corpo[k] <= 100000) for k in ("feitos", "total"))):
            raise ErroVisitas(400, {"erro": "corpo fora do formato"})
        with self._tranca():
            e = self._ler(agora_)
            ra = e["rodada_ativa"]
            if not ra or ra["id"] != rid:
                self._gravar(e)
                if rid in e["conhecidas"]:
                    raise ErroVisitas(409, {"erro": "concessão vencida"})
                raise ErroVisitas(404, {"erro": "rodada desconhecida"})
            ra["vence_em"] = iso(agora_ + timedelta(minutes=CONCESSAO_MIN))
            ra["fase"] = corpo["fase"]
            ra["dia"], ra["feitos"], ra["total"] = corpo.get("dia"), corpo.get("feitos"), corpo.get("total")
            self._gravar(e)
            return {"vence_em": ra["vence_em"]}

    # -- 3.4 lote do dia
    def receber_lote(self, rid: str, dia_url: str, tipo: str, codificacao: str, sha_cab: str, corpo_gz: bytes,
                     agora_: datetime | None = None) -> dict:
        agora_ = agora_ or agora()
        if not RE_ID_RODADA.match(rid) or dia_valido(dia_url) is None:
            raise ErroVisitas(400, {"erro": "id ou dia mal formado"})
        if (tipo or "").split(";")[0].strip().lower() != "application/json" or (codificacao or "").lower() != "gzip":
            raise ErroVisitas(415, {"erro": "Content-Type ou Content-Encoding errado"})
        with self._tranca():
            e = self._ler(agora_)
            ra = e["rodada_ativa"]
            self._gravar(e)
            if not ra or ra["id"] != rid:
                if rid in e["conhecidas"]:
                    rep = self._repetido(rid, dia_url, sha_cab)
                    if rep is not None:
                        return rep
                    raise ErroVisitas(409, {"erro": "concessão vencida"})
                raise ErroVisitas(404, {"erro": "rodada desconhecida"})
        if len(corpo_gz) > LOTE_GZ_MAX:
            raise ErroVisitas(413, {"erro": "lote grande demais"})
        bruto = descomprimir(corpo_gz)
        if bruto is None:
            raise ErroVisitas(413 if len(corpo_gz) >= 1024 else 400, {"erro": "lote grande demais ou corpo inválido"})
        if not (isinstance(sha_cab, str) and hashlib.sha256(bruto).hexdigest() == sha_cab.lower()):
            raise ErroVisitas(422, {"erro": "sha256"})
        try:
            corpo = json.loads(bruto.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ErroVisitas(400, {"erro": "corpo não é JSON"})
        det = validar_lote(dia_url, corpo, agora_.date())
        if not det and corpo["rodada"] != rid:
            det = ["rodada: diferente da URL"]
        if det:
            raise ErroVisitas(422, {"erro": "esquema inválido", "detalhes": det})
        arqs, det = decodificar_arquivos(corpo)
        if det:
            raise ErroVisitas(422, {"erro": "sha256" if all(x.endswith(".sha256") for x in det) else "esquema inválido",
                                    "detalhes": det})
        # RN-VIS-007, segunda guarda: coluna fora da lista ou dado pessoal = o lote não é gravado e a nuvem pausa
        achou: list[str] = []
        for i, b in arqs:
            for tipo_a, col in achar_no_excel(b):
                achou.append(f"arquivos[{i}]: {'coluna ' + col if tipo_a == 'coluna' else tipo_a}")
        if achou:
            with self._tranca():
                e = self._ler(agora_)
                if not e["pausado"]:
                    e["pausado"] = {"codigo": "DADO_PESSOAL", "desde": iso(agora_)}
                self._acrescentar("rodadas.jsonl", {"id": rid, "evento": "LOTE_RECUSADO", "codigo": "DADO_PESSOAL",
                                                   "dia": dia_url, "achados": len(achou), "em": iso(agora_)})
                self._gravar(e)
            raise ErroVisitas(422, {"erro": "dado pessoal", "detalhes": achou[:10]})
        with self._tranca():
            rep = self._repetido(rid, dia_url, sha_cab)
            if rep is not None:
                return rep
            reg = self.fila.registrar_item(
                {"dia": dia_url, "rodada": rid, "baixado_em": corpo["baixado_em"], "arquivos": len(arqs),
                 "bytes_gz": len(corpo_gz), "sha256": sha_cab.lower()},
                antes_de_gravar=lambda seq: self._gravar_corpo(seq, corpo_gz), agora_=agora_)
            e = self._ler(agora_)
            ant = e["indice"].get(dia_url) or {}
            e["indice"][dia_url] = {"baixado_em": iso(_dt(corpo["baixado_em"])), "origem": "nuvem",
                                    "erros_vendedor": corpo["erros_vendedor"], "refeito": bool(ant.get("refeito"))}
            self._gravar(e)
            self.retencao(agora_)
            return {"ok": True, "seq": reg["seq"], "arquivos": len(arqs)}

    def _gravar_corpo(self, seq: int, gz: bytes) -> None:
        import tempfile
        pasta = self.pasta / "lotes"
        pasta.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=pasta, prefix=".tmp-", suffix=".gz")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(gz)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, pasta / f"{seq}.json.gz")
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _repetido(self, rid: str, dia: str, sha: str) -> dict | None:
        for r in self.fila.itens():
            if r.get("rodada") == rid and r.get("dia") == dia and r.get("sha256") == (sha or "").lower():
                return {"ok": True, "seq": r["seq"], "arquivos": r.get("arquivos", 0)}
        return None

    # -- 3.5 fim
    def fim(self, rid: str, corpo, agora_: datetime | None = None) -> dict:
        agora_ = agora_ or agora()
        f = self._validar_fim(corpo)
        with self._tranca():
            e = self._ler(agora_)
            ra = e["rodada_ativa"]
            if not ra or ra["id"] != rid:
                self._gravar(e)
                if rid in e["conhecidas"]:
                    if e["conhecidas"][rid] == f["codigo"]:         # o `fim` repetido responde igual
                        return {"ok": True, "pausado": bool(e["pausado"])}
                    raise ErroVisitas(409, {"erro": "concessão vencida"})
                raise ErroVisitas(404, {"erro": "rodada desconhecida"})
            self._encerrar(e, rid, f, agora_)
            self._gravar(e)
            return {"ok": True, "pausado": bool(e["pausado"])}

    def _validar_fim(self, c) -> dict:
        if not isinstance(c, dict) or set(c) - {"codigo", "fase", "dias_ok", "dias_faltando", "erros_vendedor",
                                                "duracao_s", "pico_mb", "achados", "medidas"}:
            raise ErroVisitas(400, {"erro": "corpo fora do formato"})
        cod = c.get("codigo")
        if cod not in CODIGOS:
            raise ErroVisitas(400, {"erro": "codigo fora da lista"})
        fase = c.get("fase")
        if fase is not None and fase not in FASES:
            raise ErroVisitas(400, {"erro": "fase fora da lista"})
        if cod in PEDE_FASE and fase is None:
            raise ErroVisitas(400, {"erro": "fase obrigatória neste código"})
        for k in ("dias_ok", "dias_faltando"):
            v = c.get(k) or []
            if not (isinstance(v, list) and len(v) <= PEDIDO_MAX_DIAS and all(dia_valido(x) for x in v)):
                raise ErroVisitas(400, {"erro": f"{k} fora do formato"})
        ev = c.get("erros_vendedor", 0)
        if not (_int(ev) and 0 <= ev <= 10000):
            raise ErroVisitas(400, {"erro": "erros_vendedor fora do formato"})
        for k in ("duracao_s", "pico_mb"):
            v = c.get(k)
            if v is not None and not (isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1e9):
                raise ErroVisitas(400, {"erro": f"{k} fora do formato"})
        ach = c.get("achados")
        if ach is not None:
            if not (isinstance(ach, list) and len(ach) <= 20 and all(
                    isinstance(a, dict) and set(a) == {"coluna", "tipo", "n"} and isinstance(a["coluna"], str)
                    and RE_ROTULO.match(a["coluna"]) and a["tipo"] in TIPOS_ACHADO and _int(a["n"]) and a["n"] >= 0
                    for a in ach)):
                raise ErroVisitas(400, {"erro": "achados fora do formato (rótulo, tipo e n; nunca o valor)"})
        med = c.get("medidas")
        if med is not None and not (isinstance(med, dict) and len(json.dumps(med)) <= 8192):
            raise ErroVisitas(400, {"erro": "medidas fora do formato"})
        return {"codigo": cod, "fase": fase, "dias_ok": c.get("dias_ok") or [], "dias_faltando": c.get("dias_faltando") or [],
                "erros_vendedor": ev, "duracao_s": c.get("duracao_s"), "pico_mb": c.get("pico_mb"),
                "achados": ach, "medidas": med}

    # -- 4.1 a 4.3 robô do PC
    def lotes(self, desde: int) -> dict:
        r = self.fila.desde(desde, limite=20)
        campos = ("seq", "dia", "rodada", "baixado_em", "arquivos", "bytes_gz", "sha256", "status")
        r["linhas"] = [{k: x.get(k) for k in campos} for x in r["linhas"]]
        return r

    def corpo_do_lote(self, seq: int) -> tuple[bytes, str] | None:
        item = next((x for x in self.fila.itens() if x["seq"] == seq), None)
        arq = self.pasta / "lotes" / f"{seq}.json.gz"
        if not item or not arq.is_file():
            return None
        return arq.read_bytes(), item["sha256"]

    def confirmar(self, corpo, agora_: datetime | None = None) -> dict:
        agora_ = agora_ or agora()
        if not isinstance(corpo, dict):
            raise ErroVisitas(400, {"erro": "corpo precisa ser objeto JSON"})
        fpc = corpo.get("fechados_pc")
        if not (isinstance(fpc, dict) and len(fpc) <= 400 and all(dia_valido(k) and _dt(v) for k, v in fpc.items())):
            raise ErroVisitas(400, {"erro": "fechados_pc é obrigatório (AAAAMMDD: hora da baixa)"})
        res = corpo.get("resultados")
        if not isinstance(res, list):
            raise ErroVisitas(400, {"erro": "resultados (lista) é obrigatório"})
        for r in res:
            if isinstance(r, dict) and r.get("status") == "erro" and r.get("motivo") not in ("sha256", "nome", "pasta", "dia"):
                raise ErroVisitas(400, {"erro": "motivo do erro fora da lista"})
        dias_erro = {x["dia"] for x in self.fila.itens()
                     if any(isinstance(r, dict) and r.get("seq") == x["seq"] and r.get("status") == "erro" for r in res)}
        try:
            r = self.fila.confirmar(corpo.get("epoca"), res, agora_)
        except ErroEdicao as ex:
            raise ErroVisitas(ex.status, {"erro": ex.msg})
        with self._tranca():
            e = self._ler(agora_)
            corte = dia_ymd(agora_ - timedelta(days=FECHADOS_PC_DIAS))
            e["pc"] = {d: iso(_dt(v)) for d, v in fpc.items() if d >= corte}
            e["fechados_pc_em"] = iso(agora_)
            for d in dias_erro:                                     # a parte da nuvem sai; a nuvem baixa de novo
                e["indice"].pop(d, None)
            self._gravar(e)
            self.retencao(agora_)
        return {"ok": True, **{k: v for k, v in r.items() if k == "gravados"}}

    def retencao(self, agora_: datetime | None = None) -> None:
        """LOTE_GUARDA_DIAS: o corpo sai 7 dias depois de confirmado e 30 sem confirmação (esse conta no /saude)."""
        agora_ = agora_ or agora()
        vencidos = 0
        for x in self.fila.itens():
            arq = self.pasta / "lotes" / f"{x['seq']}.json.gz"
            if not arq.is_file():
                continue
            conf = (x.get("confirmado_em") or "")
            base = conf or x.get("quando", "")
            try:
                d = datetime.strptime(base, "%Y-%m-%d %H:%M:%S").replace(tzinfo=MANAUS)
            except ValueError:
                continue
            limite = LOTE_GUARDA_DIAS if conf else LOTE_GUARDA_SEM_CONFIRMAR_DIAS
            if agora_ - d > timedelta(days=limite):
                try:
                    arq.unlink()
                except OSError:
                    continue
                if not conf:
                    vencidos += 1
        if vencidos:
            e = self._ler(agora_)
            e["avisos"]["lotes_sem_confirmar_vencidos"] += vencidos
            self._gravar(e)

    # -- tela (4.5)
    def pedir(self, de: str, ate: str, refazer: bool, perfil: str, agora_: datetime | None = None) -> str:
        """Grava o pedido do botão. Devolve o texto de sucesso; ErroVisitas(400/409) com a mensagem da tela."""
        agora_ = agora_ or agora()
        a, b, erro = validar_periodo(de, ate, agora_.date())
        if erro:
            raise ErroVisitas(400, {"erro": erro})
        with self._tranca():
            e = self._ler(agora_)
            if e["pedido"]:
                self._gravar(e)
                raise ErroVisitas(409, {"erro": "Já há um pedido na fila; espere a rodada terminar."})
            if e["pausado"]:
                self._gravar(e)
                raise ErroVisitas(409, {"erro": "A nuvem está pausada. O admin precisa retomar antes."})
            pid = "P" + agora_.strftime("%Y%m%dT%H%M%S")
            e["pedido"] = {"id": pid, "de": dia_ymd(a), "ate": dia_ymd(b), "refazer": bool(refazer),
                           "pedido_em": iso(agora_), "perfil": perfil, "rodadas": 0}
            self._acrescentar("pedidos.jsonl", {"id": pid, "de": dia_ymd(a), "ate": dia_ymd(b), "refazer": bool(refazer),
                                                "perfil": perfil, "em": iso(agora_)})
            self._gravar(e)
        return "Pedido na fila. A próxima volta do site na Máxima baixa os dias."

    def retomar(self, recado: str, perfil: str, agora_: datetime | None = None) -> str:
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            p = e["pausado"]
            if not p:
                self._gravar(e)
                raise ErroVisitas(409, {"erro": "A nuvem não está pausada."})
            recado = (recado or "").strip()
            if p["codigo"] == "DADO_PESSOAL" and not RE_RECADO.match(recado):    # RN-VIS-007
                self._gravar(e)
                raise ErroVisitas(400, {"erro": "Informe o recado do Alexandre que autoriza (R-AAAAMMDD-HHMMSS-alexandre)."})
            self._acrescentar("pedidos.jsonl", {"retomar": True, "codigo": p["codigo"],
                                                "recado": recado if p["codigo"] == "DADO_PESSOAL" else "",
                                                "perfil": perfil, "em": iso(agora_)})
            e["pausado"] = None
            e["falhas_seguidas"] = {"fase": None, "n": 0}
            if p["codigo"] == "DADO_PESSOAL":
                e["diagnostico"] = {"estado": "pendente", "em": None, "codigo": None}
            self._gravar(e)
        return "Retomado." + (" O diagnóstico volta a rodar." if p["codigo"] == "DADO_PESSOAL" else "")

    def diagnostico(self, agora_: datetime | None = None) -> str:
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            e["diagnostico"] = {"estado": "pendente", "em": None, "codigo": None}
            self._gravar(e)
        return "Diagnóstico pedido. Roda na próxima volta do site na Máxima."

    def agenda(self, ligar: bool, agora_: datetime | None = None) -> str:
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            if ligar:
                pc = _dt(e["fechados_pc_em"])
                if e["diagnostico"]["estado"] != "ok":
                    self._gravar(e)
                    raise ErroVisitas(409, {"erro": "A agenda só liga com o diagnóstico ok."})
                if not pc or agora_ - pc > timedelta(hours=24):
                    self._gravar(e)
                    raise ErroVisitas(409, {"erro": "A agenda só liga com o robô do PC novo no ar (nas últimas 24 h)."})
            e["agenda"] = "ligada" if ligar else "desligada"
            self._gravar(e)
        return "Agenda ligada." if ligar else "Agenda desligada."

    def rodadas(self, n: int = RODADAS_NA_TELA) -> list[dict]:
        """As últimas `n` rodadas fechadas (a mais recente primeiro), com o texto do contrato §5."""
        try:
            linhas = (self.pasta / "rodadas.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for ln in reversed(linhas):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("codigo") in CODIGOS and r.get("motivo"):
                out.append({**r, "texto": texto_do_codigo(r["codigo"], r), "hora": hhmm_h(_dt(r.get("em"))),
                            "dia_br": (_dt(r.get("em")) or agora()).strftime("%d/%m")})
            if len(out) >= n:
                break
        return out

    def tela(self, agora_: datetime | None = None) -> dict:
        """O que a tela "Atualizar visitas" mostra (nada de dado pessoal)."""
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            self._gravar(e)
        rod = self.rodadas()
        total = e["tentativas_hoje"]["total"]
        pedidos_esp = [x for x in self.fila.itens() if x["status"] == "pendente"]
        indice = {d: j for d in set(e["indice"]) | set(e["pc"]) if (j := juntar_baixado(e["indice"].get(d), e["pc"].get(d)))}
        de, ate = periodo_padrao(indice, agora_.date())
        return {"e": e, "rodadas": rod, "ultima": rod[0] if rod else None, "teto_dia": total >= LOGINS_DIA_MAX,
                "teto_texto": TETO_DIA_TEXTO, "logins": total, "logins_max": LOGINS_DIA_MAX,
                "a_importar": [{"hora": hhmm_h(_dt(x.get("baixado_em"))), "dia": x["dia"],
                                "dia_br": f"{x['dia'][6:]}/{x['dia'][4:6]}"} for x in pedidos_esp],
                "pausa_texto": self._texto_pausa(e, rod),
                "padrao": {"de": de, "ate": ate},
                "de_iso": f"{de[:4]}-{de[4:6]}-{de[6:]}", "ate_iso": f"{ate[:4]}-{ate[4:6]}-{ate[6:]}",
                "hoje_iso": agora_.strftime("%Y-%m-%d")}

    @staticmethod
    def _texto_pausa(e: dict, rod: list[dict]) -> str:
        p = e["pausado"]
        if not p:
            return ""
        ref = next((r for r in rod if r["codigo"] == p["codigo"]), {})
        return texto_do_codigo(p["codigo"], {"em": p["desde"], "fase": e["falhas_seguidas"].get("fase"),
                                             "achados": ref.get("achados")})

    def saude(self, agora_: datetime | None = None) -> dict:
        """Bloco `visitas` do /saude: estado sem dado sensível (contrato §4.5)."""
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
        rod = self.rodadas(1)
        ra = e["rodada_ativa"]
        return {"agenda": e["agenda"], "diagnostico": e["diagnostico"]["estado"],
                "ultima_rodada": rod[0]["em"] if rod else None, "codigo": rod[0]["codigo"] if rod else None,
                "pausado": e["pausado"]["codigo"] if e["pausado"] else None,
                "rodada_ativa": ra["id"] if ra else None, "fase": ra.get("fase") if ra else None,
                "lotes_a_importar": sum(1 for x in self.fila.itens() if x["status"] == "pendente"),
                "tentativas_hoje": e["tentativas_hoje"]["total"],
                "lotes_sem_confirmar_vencidos": e["avisos"]["lotes_sem_confirmar_vencidos"]}
