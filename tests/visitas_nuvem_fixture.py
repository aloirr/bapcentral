"""T-0045: fixture das visitas na nuvem, 100% fictícia (nenhum vendedor,
cliente, CNPJ, telefone ou e-mail de verdade).

- `espelho_xlsx`: um Espelho de Rotas da Máxima inventado, com as 3 colunas
  que nunca saem do contêiner (KM DIST, BONIF, OBSERVACAO) e sem dado pessoal;
- `excel_da_nuvem`: o mesmo Espelho depois do `visitas_nucleo.filtrar_espelho`
  (o que o cron manda, contrato §3.6);
- `corpo_lote`: o corpo do lote do dia (contrato §3.4);
- `SiteFalso`: um site de mentira com as rotas do robô do PC (§4.1 a §4.3),
  na web nova ou na antiga (404);
- `SessaoWeb`: a mesma interface do `requests`, ligada à `web/app/visitas.Visitas`
  de verdade (sem rede), para a matriz web × robô.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

TOKEN_WEB = "token-web-ficticio-t0045"             # o BAP_WEB_TOKEN do robô do PC (fictício)
TOKEN_CRON = "token-cron-ficticio-t0045-" + "x" * 32   # o BAP_VISITAS_TOKEN (fictício, >= 32)
BASE = "https://web.exemplo.test"
VENDEDOR = "VENDEDOR FICTICIO UM"
VENDEDOR2 = "VENDEDOR FICTICIO DOIS"
NOMES_FICTICIOS = (VENDEDOR, VENDEDOR2, "SUPERVISOR FICTICIO", "CLIENTE FICTICIO", "FILIAL FICTICIA")


def hoje() -> date:
    import relatorios_nucleo as rn                       # noqa: PLC0415
    return rn.hoje_manaus()


def dia_teste(n: int = 2) -> date:
    """Um dia fechado recente (n dias antes de hoje, em Manaus)."""
    return hoje() - timedelta(days=n)


def ymd(d: date) -> str:
    return f"{d:%Y%m%d}"


def nome_arquivo(pasta: str, d: date, hhmm: str = "06-07") -> str:
    return f"VISITA-{pasta}-{d:%d-%m-%Y}-{hhmm}.xlsx"


def espelho_xlsx(caminho: Path, d: date, cod: str = "900001", nome: str = VENDEDOR,
                 visitados: int = 3) -> Path:
    """Um Espelho inventado de um representante num dia."""
    from openpyxl import Workbook                        # noqa: PLC0415
    br = f"{d:%d/%m/%Y}"
    wb = Workbook()
    ws = wb.active
    for r in (["PERIODO:", f"{br} à {br}"], ["FILIAL:", "1 - FILIAL FICTICIA"],
              ["SUPERVISOR:", "9001", "SUPERVISOR FICTICIO"], ["RCA:", cod, nome],
              ["PRIMEIRO CLIENTE:", "08:00:00"], ["ULTIMO CLIENTE:", "11:30:00"],
              ["ULTIMA POSICAO:", "12:00:00"], ["TEMPO DESLOCAMENTO:", "01:10:00"],
              ["TEMPO MEDIO ATENDIMENTO:", "00:20:00"], ["VALOR VENDIDO:", 1234.5],
              ["KM TRABALHADO:", 42.3], ["KM TOTAL:", 50.1], ["CLIENTES AGENDADOS:", visitados],
              ["QTDE VISITADOS AGENDA:", "2 / 66%"], ["QTDE VISITADOS FORA AGENDA:", "1 / 33%"],
              ["QTDE POSITIVADOS AGENDA:", "1 / 33%"], ["QTDE POSITIVADOS FORA AGENDA:", "0 / 0%"],
              ["% VISITAS REALIZADAS NA SEQUENCIA PREVISTA:", "50%"],
              ["DATA", "ORD PREV", "ORD REA", "INICIO", "FIM", "ATEND", "PER", "ENDERECO", "KM DIST",
               "CODIGO", "CLIENTE", "N PEDIDO", "PEDIDO", "BONIF", "OBSERVACAO", "JUSTIFICATIVA",
               "AGEN", "PDV"]):
        ws.append(r)
    for i in range(visitados):
        ws.append([br, i + 1, i + 1, f"{8 + i:02d}:00:00", f"{8 + i:02d}:20:00", "0:20:00", "0:20:00",
                   f"RUA FICTICIA {100 + i}", "3", f"9{cod[-3:]}{i:02d}01", f"CLIENTE FICTICIO {i}",
                   "1234" if i == 0 else "", 500.0 if i == 0 else 0, "", "obs ficticia", "",
                   "S" if i < 2 else "N", ""])
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def excel_da_nuvem(tmp: Path, d: date, cod: str = "900001", nome: str = VENDEDOR) -> tuple[bytes, bytes]:
    """(original, filtrado) do Espelho: o filtrado é o que sobe (contrato §3.6)."""
    import visitas_nucleo as vn                          # noqa: PLC0415
    org = espelho_xlsx(tmp / f"org_{cod}.xlsx", d, cod, nome)
    dst = tmp / f"dst_{cod}.xlsx"
    rel = vn.filtrar_espelho(org, dst)
    assert rel["achados"] == [], rel                     # a fixture não tem dado pessoal
    return org.read_bytes(), dst.read_bytes()


def arquivo(pasta: str, nome: str, dados: bytes) -> dict:
    return {"pasta": pasta, "nome": nome, "sha256": hashlib.sha256(dados).hexdigest(),
            "bytes": len(dados), "b64": base64.b64encode(dados).decode("ascii")}


def corpo_lote(d: date, arquivos: list[dict], rodada: str = "R20261127T060012",
               baixado_em: str | None = None, extras: dict | None = None) -> dict:
    return {"versao": 1, "rodada": rodada, "dia": ymd(d),
            "baixado_em": baixado_em or f"{d + timedelta(days=1):%Y-%m-%d}T06:07:41-04:00",
            "vendedores": len(arquivos), "erros_vendedor": 0,
            "equipe": {"filiais": {"1": "FILIAL FICTICIA"}, "supervisores": {"9001": "SUPERVISOR FICTICIO"},
                       "representantes": {}},
            "extras": extras or {}, "arquivos": arquivos}


def bruto(corpo: dict) -> bytes:
    return json.dumps(corpo, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def resp(status: int, corpo=None, headers: dict | None = None, content: bytes = b""):
    return SimpleNamespace(status_code=status, headers=headers or {}, content=content,
                           json=lambda: corpo if corpo is not None else {})


class SiteFalso:
    """As rotas do robô do PC (contrato §4.1 a §4.3), em memória.

    lotes: {seq: bytes JSON do corpo}; antigo=True: a web antiga (404 em tudo
    de /api/visitas). Guarda as chamadas para os testes conferirem."""

    def __init__(self, lotes: dict | None = None, epoca: str = "ep-1", antigo: bool = False,
                 sha_cab: str | None = None, sha_linha: str | None = None, gz: bool = True,
                 conf: int = 200, lote_status: int = 200, pagina: int = 20):
        self.lotes = dict(lotes or {})
        self.epoca, self.antigo, self.gz = epoca, antigo, gz
        self.sha_cab, self.sha_linha = sha_cab, sha_linha
        self.conf, self.lote_status, self.pagina = conf, lote_status, pagina
        self.chamadas: list[tuple] = []
        self.confirmados: dict[int, dict] = {}

    @property
    def posts(self):
        return [c for c in self.chamadas if c[0] == "POST"]

    @property
    def gets(self):
        return [c for c in self.chamadas if c[0] == "GET"]

    def _linha(self, seq: int, c: bytes) -> dict:
        dia = json.loads(c).get("dia")
        st = self.confirmados.get(seq, {}).get("status", "pendente")
        return {"seq": seq, "dia": dia, "rodada": "R20261127T060012", "baixado_em": "x",
                "arquivos": 1, "bytes_gz": len(gzip.compress(c)),
                "sha256": self.sha_linha or hashlib.sha256(c).hexdigest(), "status": st}

    def get(self, url, params=None, headers=None, timeout=None):
        rota = url.replace(BASE, "")
        self.chamadas.append(("GET", rota, dict(params or {}), dict(headers or {}), timeout))
        if self.antigo and rota.startswith("/api/visitas"):
            return resp(404, {"detail": "Not Found"})
        if (headers or {}).get("Authorization") != f"Bearer {TOKEN_WEB}":
            return resp(401, {"erro": "token"})
        if rota == "/api/visitas/lotes":
            d = int(params["desde"])
            rest = [s for s in sorted(self.lotes) if s > d]
            pag = rest[:self.pagina]
            return resp(200, {"epoca": self.epoca, "linhas": [self._linha(s, self.lotes[s]) for s in pag],
                              "ate_seq": pag[-1] if pag else d, "mais": len(rest) > len(pag)})
        m = re.fullmatch(r"/api/visitas/lote/(\d+)", rota)
        if m:
            seq = int(m.group(1))
            if self.lote_status != 200 or seq not in self.lotes:
                return resp(self.lote_status if self.lote_status != 200 else 404)
            c = self.lotes[seq]
            sha = self.sha_cab or hashlib.sha256(c).hexdigest()
            return resp(200, headers={"X-BAP-SHA256": sha, "Content-Encoding": "gzip"},
                        content=gzip.compress(c) if self.gz else c)
        return resp(404)

    def post(self, url, json=None, headers=None, timeout=None):
        rota = url.replace(BASE, "")
        self.chamadas.append(("POST", rota, json, dict(headers or {}), timeout))
        if self.antigo and rota.startswith("/api/visitas"):
            return resp(404)
        if rota == "/api/visitas/lotes/confirmar" and self.conf == 200:
            if json.get("epoca") != self.epoca:
                return resp(409, {"erro": "epoca"})
            for r in json.get("resultados") or []:
                self.confirmados[r["seq"]] = r
        return resp(self.conf, {"ok": self.conf == 200})


class SessaoWeb:
    """A interface do `requests` ligada às funções da web de verdade
    (`web/app/visitas.Visitas` e uma fila de edições vazia), sem rede. Confere o
    Bearer do robô do PC como as rotas de `web/app/main.py` (§4).
    vis=None: a web antiga (antes da T-0045), com as edições e sem /api/visitas (404)."""

    def __init__(self, vis=None):
        self.vis = vis
        self.chamadas: list[tuple] = []

    def _token_ok(self, headers) -> bool:
        return (headers or {}).get("Authorization") == f"Bearer {TOKEN_WEB}"

    def get(self, url, params=None, headers=None, timeout=None):
        rota = url.replace(BASE, "")
        self.chamadas.append(("GET", rota, dict(params or {})))
        if not self._token_ok(headers):
            return resp(401)
        if rota == "/api/edicoes":
            return resp(200, {"epoca": "ep-edicoes", "linhas": [], "ate_seq": int(params["desde"]),
                              "mais": False})
        if rota.startswith("/api/visitas") and self.vis is None:
            return resp(404, {"detail": "Not Found"})
        if rota == "/api/visitas/lotes":
            return resp(200, self.vis.lotes(int(params["desde"])))
        m = re.fullmatch(r"/api/visitas/lote/(\d+)", rota)
        if m:
            achou = self.vis.corpo_do_lote(int(m.group(1)))
            if not achou:
                return resp(404)
            return resp(200, headers={"Content-Encoding": "gzip", "X-BAP-SHA256": achou[1]}, content=achou[0])
        return resp(404)

    def post(self, url, json=None, headers=None, timeout=None):
        rota = url.replace(BASE, "")
        self.chamadas.append(("POST", rota, json))
        if not self._token_ok(headers):
            return resp(401)
        if rota.startswith("/api/visitas") and self.vis is None:
            return resp(404, {"detail": "Not Found"})
        if rota == "/api/visitas/lotes/confirmar":
            try:
                return resp(200, self.vis.confirmar(json))
            except Exception as e:                       # noqa: BLE001  (a ErroVisitas da web)
                return resp(getattr(e, "status", 500), getattr(e, "corpo", {}))
        if rota == "/api/edicoes/confirmar":
            return resp(200, {"ok": True})
        return resp(404)


def lote_na_web(vis, d: date, excel: bytes, pasta: str = VENDEDOR, motivo: str = "agenda",
                baixado_em: str | None = None) -> dict:
    """O caminho do cron na web de verdade: concessão, lote do dia (gzip +
    X-BAP-SHA256) e fim OK. Devolve a resposta do lote ({ok, seq, arquivos})."""
    con = vis.conceder({"motivo": motivo, "dias": [ymd(d)]})
    corpo = corpo_lote(d, [arquivo(pasta, nome_arquivo(pasta, d), excel)], rodada=con["id"],
                       baixado_em=baixado_em)
    b = bruto(corpo)
    r = vis.receber_lote(con["id"], ymd(d), "application/json", "gzip", hashlib.sha256(b).hexdigest(),
                         gzip.compress(b))
    vis.fim(con["id"], {"codigo": "OK", "fase": None, "dias_ok": [ymd(d)], "dias_faltando": [],
                        "erros_vendedor": 0, "duracao_s": 60, "pico_mb": None, "achados": None,
                        "medidas": None})
    return r
