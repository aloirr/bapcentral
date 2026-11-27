"""T-0045 (ADR 0004, contrato visitas-nuvem v1.1): o cron job `bap-visitas-maxima`.

`python -m nuvem.visitas.rodar` = uma volta: pergunta ao site se há trabalho (`GET trabalho`), pede a
concessão (`POST rodada`), baixa os dias na Máxima com o `visitas_maxima.Robo`, passa cada Excel pelo
filtro do Espelho (`visitas_nucleo.filtrar_espelho`), manda o lote de cada dia e fecha com o `fim`.

IMPORTAR este arquivo não faz nada: sem rede, sem navegador, sem ler segredo. Tudo acontece em
`principal()`, chamada só sob `if __name__ == "__main__"`. Toda dependência externa (ambiente, relógio,
HTTP, pausa, Robo, saída, sinal) entra por parâmetro, para o teste usar dublês.

Regras que o código segura:
- uma tentativa só de login por rodada; nunca resolve captcha; nunca espera humano (§5.1);
- o Excel que a Máxima entrega nunca sai do contêiner: só o `destino` filtrado (§3.6);
- achado de dado pessoal em qualquer Excel: o lote do dia não sobe, a rodada para (`DADO_PESSOAL`);
- o log tem só `evento=<nome> fase=.. dia=.. n=.. codigo=..` (sem nome, sem valor de célula, sem `PWE=`),
  e um filtro final troca usuário e senha por `***`;
- exceção não prevista: só o nome da classe.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from nuvem.visitas import agenda

import visitas_maxima as vm
import visitas_nucleo as vn

# --- constantes do contrato §2 que são do cron ------------------------------------------------------------------
RODADA_MAX_MIN = 45          # conferido no fim de cada dia: passou, fecha com PARCIAL_TEMPO
RODADA_TETO_MIN = 55         # o vigia liga o `parar`
RODADA_MATA_MIN = 58         # o vigia sai com os._exit(1)
DIAGNOSTICO_MAX_MIN = 15
HTTP_TEMPO_S = 30
HTTP_TEMPO_TRABALHO_S = 15
HTTP_TENTATIVAS = 3
HTTP_PAUSA_S = 30
DIAGNOSTICO_VENDEDORES = 2
VERSAO_ROBO = "2026.11.27"

VAR_USUARIO = "BAP_MAXIMA_USUARIO"
VAR_SENHA = "BAP_MAXIMA_SENHA"
VAR_TOKEN = "BAP_VISITAS_TOKEN"
VAR_HOST = "BAP_WEB_HOSTPORT"

SAIDA_OK = ("OK", "NADA_A_FAZER", "PARCIAL_VENDEDOR", "PARCIAL_TEMPO", "SITE_RECUSOU", "DESCOMPRESSAO_TETO")  # saída 0
PEDE_FASE = ("TELA_MUDOU", "ERRO_INTERNO")
RX_ID = re.compile(r"^R\d{8}T\d{6}$")
RX_HOSTPORT = re.compile(r"^[A-Za-z0-9.-]+(:\d{1,5})?$")
RX_ROTULO = re.compile(r"^[A-Z0-9% ]{1,40}$")
RX_PERIGO_ENV = re.compile(r"(^|_)(TRACE|VIDEO|HAR)(_|$)", re.I)
TIPOS_ACHADO = vn.TIPOS_ACHADO
CGROUP_V2 = "/sys/fs/cgroup/memory.peak"
CGROUP_V1 = "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"


# --- configuração (funções puras sobre o dicionário do ambiente) -------------------------------------------------
def config_insegura(env) -> bool:
    """§1: `DEBUG` com `pw`, `PWDEBUG` ou `PLAYWRIGHT_*` de trace, vídeo ou HAR ligados."""
    if "pw" in str(env.get("DEBUG", "")).lower():
        return True
    if str(env.get("PWDEBUG", "")).strip() not in ("", "0"):
        return True
    for k, v in env.items():
        if str(k).upper().startswith("PLAYWRIGHT_") and RX_PERIGO_ENV.search(str(k)) \
                and str(v).strip().lower() not in ("", "0", "false", "off"):
            return True
    return False


def variaveis_faltando(env) -> list[str]:
    """§5 `CONFIG_FALTANDO`: só os NOMES (nunca valor). Host mal formado conta como faltando."""
    falta = [v for v in (VAR_USUARIO, VAR_SENHA, VAR_TOKEN, VAR_HOST) if not str(env.get(v, "")).strip()]
    h = str(env.get(VAR_HOST, "")).strip()
    if h and not RX_HOSTPORT.match(h) and VAR_HOST not in falta:
        falta.append(VAR_HOST)
    return falta


def ler_pico_mb(ler=None) -> tuple[float | None, str]:
    """(pico em MB, fonte): cgroup v2 `memory.peak`; senão v1 `memory.max_usage_in_bytes`; senão (None, "indisponivel")."""
    ler = ler or _ler_texto
    for caminho, fonte in ((CGROUP_V2, "cgroup"), (CGROUP_V1, "cgroup_v1")):
        txt = ler(caminho)
        try:
            return round(int(str(txt).strip()) / 1048576, 1), fonte
        except (TypeError, ValueError):
            continue
    return None, "indisponivel"


def _ler_texto(caminho):
    try:
        return Path(caminho).read_text()
    except OSError:
        return None


def codigo_e_saida(codigo: str) -> int:
    return 0 if codigo in SAIDA_OK else 1


def caminho_rodada(rid: str, resto: str) -> str:
    """`/api/visitas/rodada/<id>/<resto>` (progresso, dia/AAAAMMDD, fim). Nenhum nome na URL."""
    return f"/api/visitas/rodada/{rid}/{resto}"


# --- log ---------------------------------------------------------------------------------------------------------
class Registro:
    """O log do cron: uma linha por evento. Troca usuário e senha por `***` e tira o `PWE=`."""

    def __init__(self, saida=None):
        self._saida = saida or (lambda linha: print(linha, flush=True))
        self._segredos: list[str] = []

    def segredos(self, *valores):
        self._segredos = [str(v) for v in valores if v and len(str(v)) >= 6]

    def limpar(self, linha: str) -> str:
        linha = vm.RX_PWE.sub("PWE=***", str(linha))
        for s in self._segredos:
            linha = linha.replace(s, "***")
        return linha

    def __call__(self, linha):
        self._saida(self.limpar(linha))

    def evento(self, nome, **campos):
        partes = [f"evento={_campo(nome)}"]
        for k in ("fase", "dia", "n", "codigo", "classe"):
            if campos.get(k) not in (None, ""):
                partes.append(f"{k}={_campo(campos[k])}")
        self(" ".join(partes))


def _campo(v) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "", str(v))[:40]


# --- HTTP (só biblioteca padrão) ---------------------------------------------------------------------------------
class ErroSite(Exception):
    """O cron não fala com o site depois de HTTP_TENTATIVAS (-> SITE_FORA)."""


def json_bytes(corpo) -> bytes:
    return json.dumps(corpo, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _abrir_padrao(req, timeout):
    # sem proxy: o site está na rede privada do Render
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)


class Site:
    def __init__(self, hostport, token, abrir=None, pausa=time.sleep):
        self._base = f"http://{hostport}"
        self._token = token
        self._abrir = abrir or _abrir_padrao
        self._pausa = pausa

    def chamar(self, metodo, caminho, corpo=None, tempo=HTTP_TEMPO_S, bruto=None, cabecalhos=None):
        """(status, dict). Tenta HTTP_TENTATIVAS vezes (com HTTP_PAUSA_S entre elas) em falha de rede ou 5xx;
        4xx volta na hora. Depois das tentativas: ErroSite. `bruto` = corpo já pronto (bytes)."""
        dados = bruto if bruto is not None else (json_bytes(corpo) if corpo is not None else None)
        cab = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if dados is not None:
            cab["Content-Type"] = "application/json"
        cab.update(cabecalhos or {})
        for tentativa in range(HTTP_TENTATIVAS):
            status, texto = None, b""
            try:
                req = urllib.request.Request(self._base + caminho, data=dados, headers=cab, method=metodo)
                r = self._abrir(req, timeout=tempo)
                try:
                    status, texto = int(r.status), r.read()
                finally:
                    getattr(r, "close", lambda: None)()
            except urllib.error.HTTPError as e:
                status = e.code
                try:
                    texto = e.read()
                except Exception:                                            # noqa: BLE001
                    texto = b""
            except Exception:                                                # noqa: BLE001
                status = None
            if status is not None and status < 500:
                try:
                    obj = json.loads(texto.decode("utf-8")) if texto else {}
                except (ValueError, UnicodeDecodeError):
                    obj = {}
                return status, (obj if isinstance(obj, dict) else {})
            if tentativa < HTTP_TENTATIVAS - 1:
                self._pausa(HTTP_PAUSA_S)
        raise ErroSite()


# --- vigia -------------------------------------------------------------------------------------------------------
class Vigia:
    """Thread que vigia o tempo: TETO liga o `parar`; MATA sai com código 1; o diagnóstico para em
    DIAGNOSTICO_MAX_MIN. `verificar()` é síncrona (o teste chama direto)."""

    def __init__(self, parar, monotonic, sair, registro, diagnostico=False, passo_s=5.0):
        self.parar, self._mono, self._sair, self._reg = parar, monotonic, sair, registro
        self.inicio = monotonic()
        self.diagnostico = diagnostico
        self.estourou = False                      # TETO ou teto do diagnóstico
        self._fim = threading.Event()
        self._passo = passo_s

    def decorrido_s(self) -> float:
        return self._mono() - self.inicio

    def verificar(self):
        t = self.decorrido_s()
        if t >= RODADA_MATA_MIN * 60:
            self._reg.evento("vigia_mata", codigo="RODADA_INTERROMPIDA")
            self._sair(1)
        limite = DIAGNOSTICO_MAX_MIN if self.diagnostico else RODADA_TETO_MIN
        if t >= limite * 60 and not self.estourou:
            self.estourou = True
            self._reg.evento("vigia_teto")
            self.parar.set()

    def iniciar(self):
        def laco():
            while not self._fim.wait(self._passo):
                self.verificar()
        threading.Thread(target=laco, name="vigia", daemon=True).start()

    def encerrar(self):
        self._fim.set()


# --- credenciais -------------------------------------------------------------------------------------------------
class Credenciais:
    """Guarda usuário e senha até o login; `entregar()` devolve e esquece."""

    def __init__(self, usuario, senha):
        self._u, self._s = usuario, senha

    def entregar(self):
        u, s = self._u, self._s
        self._u = self._s = None
        return u, s


# --- a rodada ----------------------------------------------------------------------------------------------------
def _sanear_achados(lista) -> list[dict]:
    """[{"coluna","tipo","n"}] até 20, no formato que o site confere. Nunca valor."""
    out = []
    for a in (lista or [])[:20]:
        if not isinstance(a, dict):
            continue
        col, tipo = str(a.get("coluna", "")), a.get("tipo")
        out.append({"coluna": col if RX_ROTULO.match(col) else "CELULA",
                    "tipo": tipo if tipo in TIPOS_ACHADO else "formato",
                    "n": max(0, int(a.get("n", 0) or 0))})
    return out


def _somar_achados(atual: list[dict], novos: list[dict]) -> list[dict]:
    soma = {(a["coluna"], a["tipo"]): a["n"] for a in atual}
    for a in novos:
        k = (a["coluna"], a["tipo"])
        soma[k] = soma.get(k, 0) + a["n"]
    return [{"coluna": c, "tipo": t, "n": n} for (c, t), n in list(soma.items())[:20]]


class Rodada:
    """O estado e os ganchos de uma rodada concedida. Os ganchos (`ao_fase`, `ao_fechar_dia`) nunca levantam
    exceção para o Robo: guardam o motivo e ligam o `parar`."""

    def __init__(self, site, rid, motivo, dias, raiz, destino, parar, registro, monotonic, vigia, filtrar=None):
        self.site, self.rid, self.motivo = site, rid, motivo
        self.dias = list(dias)
        self.raiz, self.destino = Path(raiz), Path(destino)
        self.parar, self.reg, self._mono, self.vigia = parar, registro, monotonic, vigia
        self.diagnostico = motivo == "diagnostico"
        self._filtrar = filtrar or vn.filtrar_espelho
        self.robo = None
        self.dias_ok: list[str] = []
        self.dias_vazios: list[str] = []
        self.erros_vendedor = 0
        self.recusas: list[str] = []            # SITE_RECUSOU / DESCOMPRESSAO_TETO
        self.achados: list[dict] = []
        self.fatal: tuple[str, str | None] | None = None      # (codigo, fase) que encerra a rodada
        self.sem_fim = False                    # 404/409: a concessão não é mais nossa
        self.tempo_estourou = False
        self.colunas_fora: list[str] = []
        self.limpos = {"CLIENTE": 0, "JUSTIFICATIVA": 0}
        self._marcas: list[tuple[str, float]] = []
        self._feitos_t: list[float] = []
        self.chromium: str | None = None
        self.n_filtrados = 0

    # ---- progresso (§3.3) e medidas (§6)
    def _caminho(self, fim: str) -> str:
        return caminho_rodada(self.rid, fim)

    def ao_fase(self, fase, dia, feitos, total):
        if self.parar.is_set() and (self.fatal or self.sem_fim):
            return
        agora = self._mono()
        if not self._marcas or self._marcas[-1][0] != fase:
            self._marcas.append((fase, agora))
        if self.chromium is None and fase not in ("login", "inicio") and self.robo is not None:
            try:
                v = str(self.robo.page.context.browser.version)
                self.chromium = re.sub(r"[^0-9.]", "", v)[:20] or None
            except Exception:                                                # noqa: BLE001
                self.chromium = None
        if feitos is not None:
            self._feitos_t.append(agora)
        try:
            corpo = {"fase": fase, "dia": dia, "feitos": feitos, "total": total}
            status, _ = self.site.chamar("POST", self._caminho("progresso"), corpo)
        except ErroSite:
            self._falha_site()
            return
        if status in (404, 409):                    # a concessão não é mais nossa: para no fim do vendedor, sem `fim`
            self._concessao_perdida(fase, None, status)
        elif status != 200:
            self.reg.evento("progresso_recusado", fase=fase, n=status)
        if self.diagnostico and feitos is not None and feitos >= DIAGNOSTICO_VENDEDORES:
            self.parar.set()                        # o diagnóstico mede 2 vendedores

    def _concessao_perdida(self, fase, dia, status):
        self.sem_fim = True
        self.reg.evento("concessao_perdida", fase=fase, dia=dia, n=status)
        self.parar.set()

    def _falha_site(self):
        self.fatal = ("SITE_FORA", None)
        self.reg.evento("site_fora", codigo="SITE_FORA")
        self.parar.set()

    def tempos(self) -> dict:
        """§6 `tempos_s`: login, maxgestao, filtros (tempo em cada fase) e o de cada vendedor."""
        t: dict = {}
        fim = self._mono()
        for i, (fase, ini) in enumerate(self._marcas):
            prox = self._marcas[i + 1][1] if i + 1 < len(self._marcas) else fim
            if fase in ("login", "maxgestao", "filtros"):
                t[fase] = round(t.get(fase, 0.0) + (prox - ini), 1)
        grade = next((ini for f, ini in self._marcas if f == "grade"), None)
        base, vend = grade, []
        for x in self._feitos_t:
            if base is not None:
                vend.append(round(x - base, 1))
            base = x
        t["vendedor"] = vend[:DIAGNOSTICO_VENDEDORES]
        return t

    # ---- o filtro do Espelho (§3.6)
    def _filtrar_um(self, origem: Path, destino: Path):
        """"ok" (limpo), "achado" (dado pessoal: o dia não sobe) ou "falhou" (vendedor perdido). Soma achados/limpos."""
        if origem.suffix.lower() != ".xlsx":
            self.reg.evento("arquivo_fora_do_formato", fase="filtro")
            return "falhou"
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            res = self._filtrar(origem, destino)
        except Exception as e:                                               # noqa: BLE001
            self.reg.evento("filtro_falhou", fase="filtro", classe=type(e).__name__)
            return "falhou"
        self.n_filtrados += 1
        for c in (res.get("colunas_fora") or []):
            c = str(c)
            if RX_ROTULO.match(c) and c not in self.colunas_fora and len(self.colunas_fora) < 20:
                self.colunas_fora.append(c)
        for k in ("CLIENTE", "JUSTIFICATIVA"):
            self.limpos[k] += int((res.get("limpos") or {}).get(k, 0) or 0)
        novos = _sanear_achados(res.get("achados"))
        if novos:
            self.achados = _somar_achados(self.achados, novos)
            return "achado"
        return "ok"

    def filtrar_sobras_do_diagnostico(self):
        """§6: filtra os Excel que o diagnóstico baixou (nada sai do contêiner). Chamado depois do `rodar`."""
        for i, arq in enumerate(sorted(self.raiz.rglob("*.xlsx"))):
            self._filtrar_um(arq, self.destino / f"d{i}" / arq.name)
        if self.achados:
            self.fatal = ("DADO_PESSOAL", "filtro")

    # ---- o dia (§3.4)
    def ao_fechar_dia(self, d: date, r: dict):
        if self.diagnostico or self.fatal or self.sem_fim:
            return
        dia = f"{d:%Y%m%d}"
        try:
            self._fechar_dia(d, dia, r)
        except Exception as e:                                               # noqa: BLE001
            self.fatal = ("ERRO_INTERNO", "envio")
            self.reg.evento("excecao", fase="envio", dia=dia, classe=type(e).__name__)
            self.parar.set()

    def _fechar_dia(self, d: date, dia: str, r: dict):
        arquivos = list(r.get("ok") or [])
        erros_dia = len(r.get("erro") or [])
        if not arquivos:
            self.erros_vendedor += erros_dia
            self.dias_vazios.append(dia)
            self.reg.evento("dia_sem_excel", dia=dia)
            return
        itens, mtimes = [], []
        achou = False
        for i, (nome, arq) in enumerate(arquivos):
            arq = Path(arq)
            dest = self.destino / dia / f"{i}" / arq.name
            res = self._filtrar_um(arq, dest)
            if res == "achado":
                achou = True
            if res != "ok":
                erros_dia += 1 if res == "falhou" else 0
                continue
            conteudo = dest.read_bytes()
            try:
                mtimes.append(arq.stat().st_mtime)
            except OSError:
                pass
            itens.append({"pasta": nome, "nome": arq.name, "sha256": hashlib.sha256(conteudo).hexdigest(),
                          "bytes": len(conteudo), "b64": base64.b64encode(conteudo).decode("ascii")})
        if achou:
            self.fatal = ("DADO_PESSOAL", "filtro")
            self.reg.evento("dado_pessoal", fase="filtro", dia=dia, n=sum(a["n"] for a in self.achados))
            self.parar.set()
            return
        self.erros_vendedor += erros_dia
        if not itens:
            self.dias_vazios.append(dia)
            return
        robo = self.robo
        equipe = dict(getattr(robo, "equipe", None) or {})
        for k in ("filiais", "supervisores", "representantes"):
            equipe.setdefault(k, {})
        extras = {k: {"gps": (v or {}).get("gps"), "versao": (v or {}).get("versao")}
                  for k, v in (r.get("extras") or {}).items()}
        baixado = datetime.fromtimestamp(max(mtimes), agenda.MANAUS) if mtimes else datetime.now(agenda.MANAUS)
        corpo = {"versao": 1, "rodada": self.rid, "dia": dia,
                 "baixado_em": baixado.isoformat(timespec="seconds"),
                 "vendedores": int(r.get("vendedores") or len(arquivos)), "erros_vendedor": erros_dia,
                 "equipe": {k: equipe[k] for k in ("filiais", "supervisores", "representantes")},
                 "extras": extras, "arquivos": itens}
        bruto = json_bytes(corpo)
        cab = {"Content-Encoding": "gzip", "X-BAP-SHA256": hashlib.sha256(bruto).hexdigest()}
        try:
            status, resp = self.site.chamar("POST", self._caminho(f"dia/{dia}"), bruto=gzip.compress(bruto, mtime=0),
                                            cabecalhos=cab)
        except ErroSite:
            self._falha_site()
            return
        self._tratar_resposta_dia(dia, status, resp)
        if self.fatal or self.sem_fim:
            return
        restam = [x for x in self.dias if f"{x:%Y%m%d}" not in self.dias_ok + self.dias_vazios + [dia]]
        if restam and self.vigia.decorrido_s() >= RODADA_MAX_MIN * 60:
            self.tempo_estourou = True
            self.reg.evento("rodada_max", dia=dia, codigo="PARCIAL_TEMPO")
            self.parar.set()

    def _tratar_resposta_dia(self, dia, status, resp):
        if status == 200:
            self.dias_ok.append(dia)
            self.reg.evento("dia_enviado", fase="envio", dia=dia, n=int(resp.get("arquivos", 0) or 0))
            return
        if status in (404, 409):
            self._concessao_perdida("envio", dia, status)
            return
        if status == 422 and resp.get("erro") == "dado pessoal":
            self.achados = _somar_achados(self.achados, _sanear_achados(resp.get("achados")))
            self.fatal = ("DADO_PESSOAL", "envio")
            self.reg.evento("dado_pessoal", fase="envio", dia=dia, codigo="DADO_PESSOAL")
            self.parar.set()
            return
        if status == 401:                       # token recusado: o site não é alcançável para o cron
            self._falha_site()
            return
        codigo = "DESCOMPRESSAO_TETO" if (status == 413 and resp.get("codigo") == "DESCOMPRESSAO_TETO") else "SITE_RECUSOU"
        if codigo not in self.recusas:
            self.recusas.append(codigo)
        self.reg.evento("lote_recusado", fase="envio", dia=dia, n=status, codigo=codigo)

    # ---- o resultado
    def dias_faltando(self) -> list[str]:
        feitos = set(self.dias_ok) | set(self.dias_vazios)
        return [f"{d:%Y%m%d}" for d in self.dias if f"{d:%Y%m%d}" not in feitos]

    def codigo_final(self, erro_robo: tuple[str, str | None] | None, teto_vigia: bool) -> tuple[str, str | None]:
        if self.fatal:
            return self.fatal
        if erro_robo:
            return erro_robo
        if (self.tempo_estourou or teto_vigia) and self.dias_faltando() and not self.diagnostico:
            return "PARCIAL_TEMPO", None
        if self.diagnostico and teto_vigia and len(self._feitos_t) < DIAGNOSTICO_VENDEDORES:
            return "PARCIAL_TEMPO", None
        if self.recusas:
            return ("SITE_RECUSOU" if "SITE_RECUSOU" in self.recusas else self.recusas[0]), None
        if self.erros_vendedor > 0:
            return "PARCIAL_VENDEDOR", None
        if not self.dias_ok and not self.diagnostico:
            return "NADA_A_FAZER", None
        return "OK", None


# --- a volta -----------------------------------------------------------------------------------------------------
def principal(ambiente=None, relogio=None, monotonic=time.monotonic, abrir=None, pausa=time.sleep,
              fabrica_robo=None, saida=None, sair=os._exit, ler_cgroup=None, tmp_base=None,
              instalar_sinal=True, iniciar_vigia=True, filtrar=None) -> int:
    """Uma volta do cron. Devolve o código de saída (0 ok/parcial/sem trabalho/pausado/409/429; 1 erro).
    Exceção fora dos ganchos: ERRO_INTERNO, só o nome da classe no log; manda o `fim` se a concessão veio."""
    reg = Registro(saida)
    ctx: dict = {"reg": reg}
    try:
        return _volta(ctx, ambiente, relogio, monotonic, abrir, pausa, fabrica_robo, sair, ler_cgroup, tmp_base,
                      instalar_sinal, iniciar_vigia, filtrar)
    except Exception as e:                                                   # noqa: BLE001
        reg.evento("excecao", codigo="ERRO_INTERNO", classe=type(e).__name__)
        rid, site, rod = ctx.get("rid"), ctx.get("site"), ctx.get("rod")
        if rid and site:
            try:
                fase = getattr(getattr(rod, "robo", None), "fase", None)
                site.chamar("POST", caminho_rodada(rid, "fim"), {
                    "codigo": "ERRO_INTERNO", "fase": fase if fase in vm.FASES else "inicio",
                    "dias_ok": sorted(rod.dias_ok) if rod else [],
                    "dias_faltando": rod.dias_faltando() if rod else [],
                    "erros_vendedor": rod.erros_vendedor if rod else 0, "duracao_s": None,
                    "pico_mb": None, "achados": None, "medidas": None})
            except Exception:                                                # noqa: BLE001
                pass
        return 1


def _volta(ctx, ambiente, relogio, monotonic, abrir, pausa, fabrica_robo, sair, ler_cgroup, tmp_base,
           instalar_sinal, iniciar_vigia, filtrar) -> int:
    env = os.environ if ambiente is None else ambiente
    relogio = relogio or (lambda: datetime.now(agenda.MANAUS))
    fabrica_robo = fabrica_robo or vm.Robo
    reg = ctx["reg"]
    t0 = monotonic()

    if config_insegura(env):
        reg.evento("config", codigo="CONFIG_INSEGURA")
        return 1
    faltam = variaveis_faltando(env)
    if faltam:
        reg.evento("config", codigo="CONFIG_FALTANDO")
        reg(f"evento=config_faltando n={len(faltam)} variaveis={','.join(faltam)}")
        return 1

    # os segredos saem do ambiente ANTES do Playwright existir (o driver, filho, não herda)
    u, s = env.pop(VAR_USUARIO), env.pop(VAR_SENHA)
    token = str(env.pop(VAR_TOKEN)).strip()
    reg.segredos(u, s)                                  # só para o filtro do log
    cred = Credenciais(u, s)
    u = s = None
    site = Site(str(env[VAR_HOST]).strip(), token, abrir=abrir, pausa=pausa)
    ctx["site"] = site

    try:
        status, trabalho = site.chamar("GET", "/api/visitas/trabalho", tempo=HTTP_TEMPO_TRABALHO_S)
    except ErroSite:
        reg.evento("trabalho", codigo="SITE_FORA")
        return 1
    if status != 200 or not trabalho:
        reg.evento("trabalho", codigo="SITE_FORA", n=status)
        return 1

    agora = relogio()
    motivo = agenda.deve_rodar(agora, trabalho)
    if motivo is None:
        reg.evento("sem_trabalho")
        return 0
    dias = agenda.dias_da_rodada(motivo, trabalho, agora.date())
    if not dias:
        reg.evento("sem_dias", fase=motivo)
        return 0

    corpo = {"motivo": motivo, "pedido": (trabalho.get("pedido") or {}).get("id") if motivo == "pedido" else None,
             "dias": [f"{d:%Y%m%d}" for d in dias], "versao_robo": VERSAO_ROBO}
    try:
        status, conc = site.chamar("POST", "/api/visitas/rodada", corpo)
    except ErroSite:
        reg.evento("rodada", codigo="SITE_FORA")
        return 1
    if status in (409, 423, 429):                       # já há rodada / pausa nova / teto: sai sem erro
        reg.evento("rodada_negada", fase=motivo, n=status)
        return 0
    rid = str(conc.get("id", ""))
    if status != 201 or not RX_ID.match(rid):
        reg.evento("rodada_recusada", fase=motivo, n=status)
        return 1
    reg.evento("rodada", fase=motivo, n=len(dias))
    ctx["rid"] = rid

    parar = threading.Event()
    sigterm = {"ligado": False}
    if instalar_sinal:
        def _term(*_a):
            sigterm["ligado"] = True
            parar.set()
        try:
            signal.signal(signal.SIGTERM, _term)
        except ValueError:                              # fora da thread principal
            pass
    vigia = Vigia(parar, monotonic, sair, reg, diagnostico=(motivo == "diagnostico"))
    if iniciar_vigia:
        vigia.iniciar()

    tmp = Path(tempfile.mkdtemp(prefix="bapvis_", dir=tmp_base))
    erro_robo = None
    rod = Rodada(site, rid, motivo, dias, tmp / "raiz", tmp / "filtrado", parar, reg, monotonic, vigia, filtrar)
    ctx["rod"] = rod
    try:
        robo = fabrica_robo(tmp / "raiz", reg, parar=parar, visivel=False, canal="chromium", foto=False,
                            eventos=True, ao_fechar_dia=rod.ao_fechar_dia, ao_fase=rod.ao_fase)
        rod.robo = robo
        try:
            u, s = cred.entregar()
            robo.rodar(u, s, dias, set())
        except vm.Cancelado:
            pass
        except Exception as e:                                               # noqa: BLE001
            cod = getattr(robo, "codigo", None)
            fase = getattr(robo, "fase_erro", None)
            if not cod:
                cod, fase = vm.codigo_da_excecao(e, getattr(robo, "fase", None))
            erro_robo = (cod, fase)
            if not isinstance(e, vm.ErroRobo):
                reg.evento("excecao", classe=type(e).__name__)
        finally:
            u = s = None
        if rod.diagnostico and not rod.sem_fim:
            rod.filtrar_sobras_do_diagnostico()
    finally:
        vigia.encerrar()
        shutil.rmtree(tmp, ignore_errors=True)

    if sigterm["ligado"] or rod.sem_fim:
        reg.evento("sem_fim", codigo="RODADA_INTERROMPIDA" if sigterm["ligado"] else "")
        return 1 if sigterm["ligado"] else 0

    codigo, fase = rod.codigo_final(erro_robo, vigia.estourou)
    if codigo in PEDE_FASE and not fase:
        fase = "inicio"
    pico, fonte = ler_pico_mb(ler_cgroup)
    duracao = int(monotonic() - t0)
    fim = {"codigo": codigo, "fase": fase, "dias_ok": sorted(rod.dias_ok),
           "dias_faltando": [] if rod.diagnostico else rod.dias_faltando(),
           "erros_vendedor": rod.erros_vendedor, "duracao_s": duracao, "pico_mb": pico,
           "achados": (rod.achados or None) if codigo == "DADO_PESSOAL" else None, "medidas": None}
    if rod.diagnostico:
        fim["medidas"] = {"tempos_s": rod.tempos(), "fonte_pico": fonte, "chromium": rod.chromium or "desconhecido",
                          "espelho": {"colunas_fora": rod.colunas_fora, "limpos": rod.limpos}}
        t = fim["medidas"]["tempos_s"]
        reg(f"DIAGNOSTICO codigo={codigo} pico_mb={pico} login_s={t.get('login')} "
            f"vendedor_s={'/'.join(str(x) for x in t.get('vendedor', []))} colunas_fora={len(rod.colunas_fora)} "
            f"limpos={sum(rod.limpos.values())} achados={sum(a['n'] for a in rod.achados)}")
    try:
        st, _ = site.chamar("POST", rod._caminho("fim"), fim)
        if st != 200:
            reg.evento("fim_recusado", codigo=codigo, n=st)
    except ErroSite:
        reg.evento("fim", codigo="SITE_FORA")
        return 1
    reg.evento("fim", fase=fase, codigo=codigo, n=len(rod.dias_ok))
    return codigo_e_saida(codigo)


if __name__ == "__main__":
    sys.exit(principal())
