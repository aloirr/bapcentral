"""T-0045 (ADR 0004, contrato visitas-nuvem v1): as visitas da Máxima no Render, lado do site.

O cron `bap-visitas-maxima` pede uma concessão, baixa o Espelho dos vendedores e manda um lote por dia; o robô do PC
importa o lote na volta de 30 min. Aqui ficam só a guarda e o registro: concessão (RN-VIS-004), teto de entradas por
dia (RN-VIS-008), pausa por código (RN-VIS-005 e 007), índice dos dias baixados (RN-VIS-002), fila de lotes
(`edicoes.Fila`) e o que a tela mostra. Quem baixa, filtra e monta o dia é o cron e o PC; o site nunca serve o Excel.

ESPELHO: as regras de RN-VIS-002 (`_dt`, `juntar_baixado`, `dia_fechado_no_indice`, `dias_a_baixar`) e os regex de dado
pessoal (`RE_PESSOAL`, `TIPOS_ACHADO`, `COLUNAS_PROIBIDAS`) são espelho MÍNIMO de `visitas_nucleo` (`_quando_manaus`,
`juntar_baixado`, `dia_fechado_no_indice`, `dias_a_baixar`, `_RX_EMAIL`/`_RX_CNPJ`/`_RX_CPF`/`_RX_FONE`,
`_FORA_DO_ESPELHO` e `TIPOS_ACHADO`): o Render publica só `web/` e não
importa a raiz. A regra é a do núcleo (empate: a nuvem, contrato §3.1). O teste de paridade (`tests/`, do agente
`testes`, branch `testes/T-0045-testes`) prende as cópias ao núcleo.

Disco (`<dados>/visitas/`): `estado.json` (gravação atômica), `lotes/` (a `Fila` e os corpos `<seq>.json.gz`),
`pedidos.jsonl` e `rodadas.jsonl` (só acréscimo). Nenhum nome de vendedor ou de cliente em log, resposta ou arquivo
de estado; o perfil, nunca o usuário, vai no registro dos pedidos.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import re
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from .arquivos import GzipGrande, GzipInvalido, acrescentar_linha, descomprimir_com_teto, gravar_bytes, gravar_json
from .edicoes import MANAUS, RE_ISO, ErroEdicao, Fila, _int, agora, iso_de_br

try:                                    # Linux (Render); no Windows de teste só a trava de thread
    import fcntl
except ImportError:                     # pragma: no cover
    fcntl = None

# ------------------------------------------------------------------ constantes (contrato §2; teste confere)
TENTATIVAS_DIA = {"agenda": 4, "pedido": 3, "retentativa": 1, "diagnostico": 2}      # RN-VIS-008
LOGINS_DIA_MAX = 8                                                                  # RN-VIS-008
CONCESSAO_MIN = 10                                                                  # RN-VIS-004
PODEM_PEDIR = ("admin", "gerente")       # 4 A (Alexandre): quem aperta o "Atualizar visitas" (tela, link e lateral)
SO_ADMIN = ("admin",)                    # baixar de novo, diagnóstico, agenda e Retomar
PEDIDO_MAX_DIAS = 7
PEDIDO_MAX_RODADAS = 3
FECHADOS_PC_DIAS = 40
LOTE_GZ_MAX = 8 * 1024 * 1024
LOTE_BRUTO_MAX = 24 * 1024 * 1024        # o JSON já descomprimido (trava de "bomba" de gzip)
DESCOMPRESSAO_MAX = 50 * 1024 * 1024     # teto TOTAL de leitura dos Excel (por lote e por arquivo), segunda guarda
ZIP_MEMBROS_MAX = 64
CODIGO_TETO = "DESCOMPRESSAO_TETO"
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

_PC = "Use o Atualizar visitas do PC"
_CONF = f"A Máxima pediu uma confirmação. {_PC}; o admin retoma aqui depois."
_CONFIG = "A atualização pelo site está desligada por configuração. Avise o Alexandre."
# código -> (status, texto): o que aconteceu e o que fazer, sem jargão. `{h}` hora do fim, `{d}` dia, `{n}` vendedores sem
# visita, `{c}` coluna, `{t}` "Tentamos de novo às HHhMM." (ou "Tente mais tarde."). O código em si (e a etapa) vão
# pequenos, "para o suporte" (decisão 6 B: o código no lugar do print).
CODIGOS = {
    "OK": ("ok", "Atualizado às {h}."),
    "NADA_A_FAZER": ("ok", "Já estava em dia."),
    "PARCIAL_VENDEDOR": ("parcial", "Faltou a visita de {n} em {d}. Peça de novo esse dia."),
    "PARCIAL_TEMPO": ("parcial", "Parte dos dias veio; o resto vem na próxima atualização."),
    "MAXIMA_SENHA": ("erro", "A Máxima recusou a senha do site. Avise o Alexandre; depois, o admin clica em Retomar."),
    "MAXIMA_CONFIRMACAO": ("erro", _CONF),
    "MAXIMA_CAPTCHA": ("erro", _CONF),
    "MAXIMA_BLOQUEIO": ("erro", f"A Máxima bloqueou o acesso do site. {_PC}."),
    "DADO_PESSOAL": ("erro", f"O Espelho da Máxima trouxe um dado que o site não pode guardar (coluna: {{c}}). {_PC}."),
    "MAXIMA_FORA": ("erro", "A Máxima não respondeu. {t}"),
    "TELA_MUDOU": ("erro", f"A tela da Máxima mudou. {_PC} por enquanto."),
    "NAVEGADOR_FALHOU": ("erro", "O navegador do site parou. {t}"),
    "SITE_RECUSOU": ("parcial", "Um dia não foi aceito pelo site ({d})."),
    "DESCOMPRESSAO_TETO": ("parcial", f"Um dia não foi aceito pelo site ({{d}}): Excel grande demais. {_PC}."),
    "SITE_FORA": ("erro", "O site não respondeu. {t}"),
    "RODADA_INTERROMPIDA": ("erro", "A rodada parou sem terminar. {t}"),
    "CONFIG_FALTANDO": ("erro", _CONFIG),
    "CONFIG_INSEGURA": ("erro", _CONFIG),
    "ERRO_INTERNO": ("erro", f"Algo deu errado. {_PC} e avise o admin."),
}
STATUS_DO_CODIGO = {c: s for c, (s, _) in CODIGOS.items()}
TETO_DIA_TEXTO = f"O site já acessou a Máxima o máximo de vezes hoje. {_PC}; amanhã volta sozinho."
TRAVADO = {"pausado": "Pausado: o admin retoma antes.", "pedido": "Já há um pedido na fila.",       # um motivo, uma redação:
           "teto": "Limite de hoje atingido."}                                                     # botão (title) e erro do servidor
SITUACAO = {"ok": "Em dia", "parcial": "Parcial", "erro": "Erro"}          # a palavra que a tela mostra no lugar do código
SITUACAO_COR = {"ok": "ok", "parcial": "atencao", "erro": "alerta"}
TIPOS_ACHADO = ("email", "cnpj", "cpf", "telefone", "formato")      # espelho de visitas_nucleo.TIPOS_ACHADO (mesma ordem)

RE_ID_RODADA = re.compile(r"^R\d{8}T\d{6}$")
RE_DIA = re.compile(r"^\d{8}$")
RE_RECADO = re.compile(r"^R-\d{8}-\d{6}-alexandre$")
RE_ROTULO = re.compile(r"^[A-Z0-9% ]{1,40}$")
RE_SHA = re.compile(r"^[0-9a-f]{64}$")
RE_PASTA_MAL = re.compile(r"[\\/\x00-\x1f\x7f]|\.\.")
RE_NOME_ARQ = re.compile(r"^VISITA-(?P<pasta>.+)-(?P<d>\d{2})-(?P<m>\d{2})-(?P<a>\d{4})-\d{2}-\d{2}(?:-\d+)?\.xlsx$")
# varredura (RN-VIS-007): a mesma rede do cron (contrato §3.6), repetida aqui antes de gravar
RE_PESSOAL = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"),
    "cnpj": re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\d)\d{14}(?!\d)"),
    "cpf": re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|(?<!\d)\d{11}(?!\d)"),
    "telefone": re.compile(r"\(?\d{2}\)?\s?9?\d{4}-\d{4}|\(\d{2}\)\s?\d{8,9}"),
}
# colunas do Espelho que nunca saem do contêiner (contrato §3.6): o rótulo no Excel é motivo de recusa
COLUNAS_PROIBIDAS = ("KM DIST", "BONIF", "OBSERVACAO")        # espelho de visitas_nucleo._FORA_DO_ESPELHO
_RX_TEXTO_XML = re.compile(r"<(?:t(?:\s[^>]*)?|v)>([^<]*)</(?:t|v)>")      # texto e número das células
_DIAG_PENDENTE = {"estado": "pendente", "em": None, "codigo": None}
_ESTADO_VAZIO = {"agenda": "desligada",
                 "diagnostico": dict(_DIAG_PENDENTE),
                 "pausado": None, "pedido": None, "rodada_ativa": None,
                 "falhas_seguidas": {"fase": None, "n": 0}, "indice": {}, "pc": {},
                 "tentativas_hoje": {"dia": "", "total": 0, "por_motivo": {}},
                 "fechados_pc_em": None, "conhecidas": {}, "avisos": {"lotes_sem_confirmar_vencidos": 0}}


def iso(d: datetime) -> str:
    return d.astimezone(MANAUS).isoformat(timespec="seconds")


def _dt(v) -> datetime | None:
    """Espelho de `visitas_nucleo._quando_manaus`: iso, datetime ou {"baixado_em": iso} -> Manaus (sem fuso = Manaus)."""
    if isinstance(v, dict):
        v = v.get("baixado_em")
    if isinstance(v, datetime):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v))
        except (TypeError, ValueError):
            return None
    return d.replace(tzinfo=MANAUS) if d.tzinfo is None else d.astimezone(MANAUS)


def dia_ymd(d: date | datetime) -> str:
    return d.strftime("%Y%m%d")


def dia_br(ymd: str) -> str:
    """AAAAMMDD -> dd/mm."""
    return f"{ymd[6:]}/{ymd[4:6]}"


def dia_iso(ymd: str) -> str:
    """AAAAMMDD -> AAAA-MM-DD (o valor do `<input type="date">`; o navegador mostra no idioma dele)."""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def ymd_do_form(v) -> str:
    """O que veio do formulário (aaaa-mm-dd do `<input type="date">`, ou dd/mm/aaaa) -> AAAAMMDD; "" se não for data."""
    v = (v or "").strip()
    return (iso_de_br(v) or (v if RE_ISO.match(v) else "")).replace("-", "")


def dia_hora(v) -> str:
    """O único formato de data e hora da tela: "27/11 06h06" (Manaus)."""
    d = _dt(v)
    return d.strftime("%d/%m %Hh%M") if d else ""


def _corte(agora_: datetime) -> str:
    return dia_ymd(agora_ - timedelta(days=FECHADOS_PC_DIAS))


def dia_valido(s) -> date | None:
    if not (isinstance(s, str) and RE_DIA.match(s)):
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def hhmm_h(d: datetime | None) -> str:
    return d.strftime("%Hh%M") if d else ""


class ErroVisitas(Exception):
    """Erro com resposta pronta: `corpo` é o JSON devolvido ao cron, ao robô ou à tela."""

    def __init__(self, status: int, corpo: dict):
        super().__init__(corpo.get("erro", ""))
        self.status, self.corpo = status, corpo


# ------------------------------------------------------------------ regras puras (testadas)
def juntar_baixado(nuvem: dict | None, pc: dict | None) -> dict:
    """Espelho de `visitas_nucleo.juntar_baixado` (RN-VIS-002). Entradas {AAAAMMDD: iso | {"baixado_em", "erros_vendedor",
    "refeito"}}. Vale a MAIOR hora entre a nuvem e o PC (empate: a nuvem, porque o PC anota o `baixado_em` da nuvem).
    Saída {AAAAMMDD: {"baixado_em", "origem"}}; `erros_vendedor` e `refeito` só acompanham a origem "nuvem"."""
    saida: dict = {}
    nuvem, pc = nuvem or {}, pc or {}
    for dia in sorted(set(nuvem) | set(pc)):
        n, p = _dt(nuvem.get(dia)), _dt(pc.get(dia))
        if n is None and p is None:
            continue
        if p is None or (n is not None and n >= p):
            ent = {"baixado_em": iso(n), "origem": "nuvem"}
            bruto = nuvem.get(dia)
            if isinstance(bruto, dict):
                ent.update({k: bruto[k] for k in ("erros_vendedor", "refeito") if k in bruto})
        else:
            ent = {"baixado_em": iso(p), "origem": "pc"}
        saida[dia] = ent
    return saida


def dia_fechado_no_indice(indice: dict | None, d: date) -> bool:
    """Espelho de `visitas_nucleo.dia_fechado_no_indice` (RN-VIS-002): fechado = baixado num dia depois dele (Manaus)."""
    q = _dt((indice or {}).get(dia_ymd(d)))
    return bool(q and q.date() > d)


def dias_a_baixar(indice: dict | None, de: date, ate: date, hoje: date, refazer: bool = False) -> list[date]:
    """Espelho de `visitas_nucleo.dias_a_baixar`: nunca passa de hoje; sem `refazer`, pula o dia fechado."""
    ate = min(ate, hoje)
    n = (ate - de).days
    return [de + timedelta(days=k) for k in range(n + 1)
            if refazer or not dia_fechado_no_indice(indice, de + timedelta(days=k))]


def periodo_padrao(indice: dict, hoje: date) -> tuple[str, str]:
    """O período do botão: do dia aberto mais antigo (até PEDIDO_MAX_DIAS) até hoje."""
    abertos = dias_a_baixar(indice, hoje - timedelta(days=PEDIDO_MAX_DIAS - 1), hoje, hoje)
    return dia_ymd(abertos[0] if abertos else hoje), dia_ymd(hoje)


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


def _teto_descompressao() -> ErroVisitas:
    return ErroVisitas(413, {"erro": "lote grande demais", "codigo": CODIGO_TETO})


def achar_no_excel(dados: bytes, orcamento: list[int] | None = None) -> list[tuple[str, str]]:
    """RN-VIS-007, segunda guarda (rede extra: a garantia é o filtro do cron, contrato §3.6). Lê só o TEXTO e os
    NÚMEROS das células (zip + regex; nunca serve nem interpreta o Excel) e devolve [(tipo, coluna_ou_"")] do que não
    pode ficar: dado pessoal e coluna fora da lista. Nenhum valor sai.
    Teto TOTAL de descompressão: `orcamento` = [bytes que ainda podem ser lidos neste lote] (DESCOMPRESSAO_MAX por
    lote e por arquivo) e no máximo ZIP_MEMBROS_MAX membros; passou = 413 com `codigo` DESCOMPRESSAO_TETO."""
    orcamento = orcamento if orcamento is not None else [DESCOMPRESSAO_MAX]
    achados: list[tuple[str, str]] = []
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
        infos = [i for i in z.infolist() if i.filename == "xl/sharedStrings.xml" or i.filename.startswith("xl/worksheets/")]
        if len(z.infolist()) > ZIP_MEMBROS_MAX:
            raise _teto_descompressao()
        previsto = sum(i.file_size for i in infos)           # o tamanho declarado; o zipfile corta no declarado
        if previsto > DESCOMPRESSAO_MAX or previsto > orcamento[0]:
            raise _teto_descompressao()
        orcamento[0] -= previsto
        textos: list[str] = []
        for i in infos:
            textos += _RX_TEXTO_XML.findall(z.read(i).decode("utf-8", "replace"))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        return [("formato", "")]
    for t in textos:
        t = html.unescape(t)                                  # `&#64;` e afins não escondem nada
        if t.strip().upper() in COLUNAS_PROIBIDAS:
            achados.append(("coluna", t.strip().upper()))
        achados += [(tipo, "") for tipo, rx in RE_PESSOAL.items() if rx.search(t)]
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


def texto_do_codigo(codigo: str, r: dict) -> str:
    """O texto da tela para uma rodada do `rodadas.jsonl` (sem nome de vendedor nem de cliente)."""
    _, modelo = CODIGOS.get(codigo, ("erro", "Código desconhecido."))
    dias = r.get("dias_faltando") or r.get("dias") or []
    d = dia_valido(dias[0]) if dias else None
    achados = r.get("achados") or []
    n = int(r.get("erros_vendedor") or 0)
    prox = r.get("proxima") or ""
    return modelo.format(
        h=hhmm_h(_dt(r.get("em"))), d=dia_br(dia_ymd(d)) if d else "?",
        n=f"{n} vendedor" + ("es" if n != 1 else ""), c=(achados[0].get("coluna") if achados else "") or "?",
        t=f"Tentamos de novo às {prox}." if prox else "Tente mais tarde.").strip()


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
        corte = _corte(agora_)                                        # o índice só guarda os últimos 40 dias
        for k in ("indice", "pc"):
            e[k] = {d: v for d, v in e[k].items() if d >= corte}
        self._vencer(e, agora_)
        return e

    def _gravar(self, e: dict) -> None:
        gravar_json(self.pasta / "estado.json", e)

    def _acrescentar(self, nome: str, reg: dict) -> None:
        acrescentar_linha(self.pasta / nome, reg)

    def _vencer(self, e: dict, agora_: datetime) -> None:
        """RN-VIS-004: a concessão sem `progresso` por CONCESSAO_MIN vira RODADA_INTERROMPIDA (gravada pelo site)."""
        ra = e.get("rodada_ativa")
        if ra and (_dt(ra.get("vence_em")) or agora_) <= agora_:
            self._encerrar(e, ra["id"], {"codigo": "RODADA_INTERROMPIDA", "fase": ra.get("fase"), "dias_ok": [],
                                          "dias_faltando": ra.get("dias") or [], "erros_vendedor": 0,
                                          "duracao_s": None, "pico_mb": None, "achados": None, "medidas": None},
                           agora_, interrompida=True)
            self._gravar(e)

    @staticmethod
    def _tentativa(e: dict, motivo: str) -> dict:
        return e["tentativas_hoje"]["por_motivo"].setdefault(motivo, {"n": 0, "ultima_em": None, "codigo": None})

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
        m = self._tentativa(e, motivo)
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
        ra = e["rodada_ativa"]
        return {"versao": 1, "agora": iso(agora_), "agenda": e["agenda"], "diagnostico": e["diagnostico"],
                "pausado": e["pausado"], "pedido": e["pedido"], "indice": juntar_baixado(e["indice"], e["pc"]),
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
            m = self._tentativa(e, motivo)
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
        try:
            bruto = descomprimir_com_teto(corpo_gz, LOTE_BRUTO_MAX)
        except GzipGrande:
            raise ErroVisitas(413, {"erro": "lote grande demais"})
        except GzipInvalido:
            raise ErroVisitas(400, {"erro": "gzip inválido"})
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
        achou: dict[tuple[str, str], int] = {}
        orcamento = [DESCOMPRESSAO_MAX]
        for i, b in arqs:
            for tipo_a, col in achar_no_excel(b, orcamento):
                chave = (col, "formato") if tipo_a == "coluna" else ("CELULA", tipo_a)     # rótulo e tipo, nunca o valor
                achou[chave] = achou.get(chave, 0) + 1
        if achou:
            lista = [{"coluna": c, "tipo": t, "n": n} for (c, t), n in list(achou.items())[:20]]
            with self._tranca():
                e = self._ler(agora_)
                if not e["pausado"]:
                    e["pausado"] = {"codigo": "DADO_PESSOAL", "desde": iso(agora_)}
                self._acrescentar("rodadas.jsonl", {"id": rid, "evento": "LOTE_RECUSADO", "codigo": "DADO_PESSOAL",
                                                   "dia": dia_url, "achados": lista, "em": iso(agora_)})
                self._gravar(e)
            raise ErroVisitas(422, {"erro": "dado pessoal", "achados": lista})
        with self._tranca():
            rep = self._repetido(rid, dia_url, sha_cab)
            if rep is not None:
                return rep
            reg = self.fila.registrar_item(
                {"dia": dia_url, "rodada": rid, "baixado_em": corpo["baixado_em"], "arquivos": len(arqs),
                 "bytes_gz": len(corpo_gz), "sha256": sha_cab.lower()},
                antes_de_gravar=lambda seq: gravar_bytes(self._arq_lote(seq), corpo_gz), agora_=agora_)
            e = self._ler(agora_)
            ant = e["indice"].get(dia_url) or {}
            e["indice"][dia_url] = {"baixado_em": iso(_dt(corpo["baixado_em"])), "origem": "nuvem",
                                    "erros_vendedor": corpo["erros_vendedor"], "refeito": bool(ant.get("refeito"))}
            self._gravar(e)
            self.retencao(agora_)
            return {"ok": True, "seq": reg["seq"], "arquivos": len(arqs)}

    def _pendentes(self) -> list[dict]:
        return [x for x in self.fila.itens() if x["status"] == "pendente"]

    def _arq_lote(self, seq: int) -> Path:
        return self.pasta / "lotes" / f"{seq}.json.gz"

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
        arq = self._arq_lote(seq)
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
            corte = _corte(agora_)
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
            arq = self._arq_lote(x["seq"])
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
        a, b, erro = validar_periodo(ymd_do_form(de), ymd_do_form(ate), agora_.date())
        if erro:
            raise ErroVisitas(400, {"erro": erro})
        with self._tranca():
            e = self._ler(agora_)
            if e["pedido"]:
                self._gravar(e)
                raise ErroVisitas(409, {"erro": TRAVADO["pedido"]})
            if e["pausado"]:
                self._gravar(e)
                raise ErroVisitas(409, {"erro": TRAVADO["pausado"]})
            pid = "P" + agora_.strftime("%Y%m%dT%H%M%S")
            e["pedido"] = {"id": pid, "de": dia_ymd(a), "ate": dia_ymd(b), "refazer": bool(refazer),
                           "pedido_em": iso(agora_), "perfil": perfil, "rodadas": 0}
            self._acrescentar("pedidos.jsonl", {"id": pid, "de": dia_ymd(a), "ate": dia_ymd(b), "refazer": bool(refazer),
                                                "perfil": perfil, "em": iso(agora_)})
            self._gravar(e)
        return "Pedido enviado."

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
                e["diagnostico"] = dict(_DIAG_PENDENTE)
            self._gravar(e)
        return "Retomado."

    def diagnostico(self, agora_: datetime | None = None) -> str:
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            e["diagnostico"] = dict(_DIAG_PENDENTE)
            self._gravar(e)
        return "Diagnóstico pedido."

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

    def _linhas_rodadas(self):
        """As rodadas fechadas do `rodadas.jsonl`, da mais recente para a mais antiga."""
        try:
            linhas = (self.pasta / "rodadas.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for ln in reversed(linhas):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("codigo") in CODIGOS and r.get("motivo"):
                yield r

    def rodadas(self, n: int = RODADAS_NA_TELA) -> list[dict]:
        """As últimas `n` rodadas fechadas (a mais recente primeiro), com a situação e o texto da tela."""
        out = []
        for r in self._linhas_rodadas():
            out.append({**r, "texto": texto_do_codigo(r["codigo"], r), "situacao": SITUACAO.get(r.get("status"), "Erro"),
                        "quando": dia_hora(r.get("em"))})
            if len(out) >= n:
                break
        return out

    def diagnostico_linhas(self) -> list[tuple[str, str]]:
        """O que o admin precisa ver do último diagnóstico (contrato §6): tempos, pico, e só a CONTAGEM do que o filtro
        tirou, limpou ou achou. Nenhum nome de coluna, nenhum valor."""
        r = next((x for x in self._linhas_rodadas() if x["motivo"] == "diagnostico"), None)
        if not r:
            return []
        m = r.get("medidas") if isinstance(r.get("medidas"), dict) else {}
        t = m.get("tempos_s") if isinstance(m.get("tempos_s"), dict) else {}
        esp = m.get("espelho") if isinstance(m.get("espelho"), dict) else {}

        def seg(v):
            return f"{float(v):.0f} s" if isinstance(v, (int, float)) and not isinstance(v, bool) else "—"
        vend = t.get("vendedor") if isinstance(t.get("vendedor"), list) else []
        limpos = esp.get("limpos") if isinstance(esp.get("limpos"), dict) else {}
        out = [("Duração", seg(r.get("duracao_s"))),
               ("Memória (pico)", f"{r['pico_mb']:.0f} MB" if isinstance(r.get("pico_mb"), (int, float)) else "—"),
               ("Login", seg(t.get("login"))), ("maxGestão", seg(t.get("maxgestao"))), ("Filtros", seg(t.get("filtros"))),
               ("Por vendedor", " e ".join(seg(v) for v in vend[:3]) or "—")]
        if esp:
            out += [("Colunas retiradas", str(len(esp.get("colunas_fora") or []))),
                    ("Células limpas", str(sum(v for v in limpos.values() if _int(v)))),
                    ("Achados", str(sum(a.get("n", 0) for a in (r.get("achados") or []) if isinstance(a, dict)
                                        and _int(a.get("n")))))]
        return out

    def tela(self, agora_: datetime | None = None) -> dict:
        """O que a tela "Atualizar visitas" mostra (nada de dado pessoal)."""
        agora_ = agora_ or agora()
        with self._tranca():
            e = self._ler(agora_)
            self._gravar(e)
        rod = self.rodadas()
        total = e["tentativas_hoje"]["total"]
        teto = total >= LOGINS_DIA_MAX
        de, ate = periodo_padrao(juntar_baixado(e["indice"], e["pc"]), agora_.date())
        ultima = rod[0] if rod else None
        if e["pausado"]:
            sit = ("Pausado", "alerta")
        elif e["rodada_ativa"]:
            sit = ("Baixando", "atencao")
        elif ultima:
            sit = (ultima["situacao"], SITUACAO_COR.get(ultima["status"], "alerta"))
        else:
            sit = ("—", "")
        return {"e": e, "rodadas": rod, "ultima": ultima, "teto_dia": teto, "teto_texto": TETO_DIA_TEXTO,
                "logins": total, "logins_max": LOGINS_DIA_MAX, "situacao": sit[0], "situacao_cor": sit[1],
                "pode_apertar": not (e["pedido"] or e["pausado"] or teto),
                "motivo_travado": (TRAVADO["pausado"] if e["pausado"] else TRAVADO["pedido"] if e["pedido"] else
                                   TRAVADO["teto"] if teto else ""),
                "a_importar": [{"hora": hhmm_h(_dt(x.get("baixado_em"))), "dia": x["dia"]} for x in self._pendentes()],
                "pausa_texto": self._texto_pausa(e, rod), "diag": self.diagnostico_linhas(),
                "padrao": {"de": de, "ate": ate}, "de_iso": dia_iso(de), "ate_iso": dia_iso(ate), "hoje_iso": agora_.strftime("%Y-%m-%d"),
                "andamento": self._andamento(e["rodada_ativa"])}

    @staticmethod
    def _andamento(ra: dict | None) -> str:
        """O que o site está fazendo agora, em palavras simples (a etapa técnica fica só no código do suporte)."""
        if not ra:
            return ""
        fase, d = ra.get("fase"), dia_valido(ra.get("dia"))
        if fase in ("filtros", "grade", "espelho", "filtro", "salvar"):
            txt = f"Baixando o dia {dia_br(dia_ymd(d))}" if d else "Baixando"
        elif fase == "envio":
            txt = "Enviando"
        else:
            txt = "Entrando na Máxima"
        return txt + (f" ({ra.get('feitos') or 0} de {ra['total']})" if ra.get("total") else "")

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
                "lotes_a_importar": len(self._pendentes()),
                "tentativas_hoje": e["tentativas_hoje"]["total"],
                "lotes_sem_confirmar_vencidos": e["avisos"]["lotes_sem_confirmar_vencidos"]}
