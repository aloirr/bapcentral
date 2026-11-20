"""
LATITUDE E LONGITUDE DOS CLIENTES (06/10)

Cada cliente da BASE_CLIENTE ganha um ponto no mapa, pelo ENDERECO. O
ponto e o que o Planner usa para montar a rota pelo caminho mais curto
(geografia.caminho_mais_curto).

De onde sai: o OpenStreetMap (Nominatim), de graca e sem cadastro - nao
precisa de chave nem de aprovacao do TI. A regra de uso do servico e no
maximo UMA consulta por segundo, entao a primeira vez (a base inteira)
leva perto de uma hora; depois so vao os clientes NOVOS e os que tiveram
o ENDERECO ALTERADO.

Guardado em RELATORIOS/COORDENADAS_CLIENTES.json (ao lado da BASE_CLIENTE):
    {"CHAVE_CLIENTE" : {"end" : "<endereco normalizado>",
                        "LATITUDE" : "-3.010709",
                        "LONGITUDE" : "-60.0082203",
                        "precisao" : "endereco|cep|rua|bairro",
                        "em" : "2026-10-06"}}
    (23/10: o formato do modelo do roteirizador - texto com ponto, ate 7
    casas; o arquivo antigo, com "lat"/"lon" em numero, continua sendo
    lido e vira o formato novo na proxima gravacao)
Endereco que mudou (o "end" nao bate) e consultado de novo; o que nao foi
achado so e tentado outra vez depois de 30 dias.
(28/10) Ponto MANUAL ("origem" : "MANUAL", do Excel de preenchimento da
analista, ou com "fonte", posto a mao pelo Google Maps): quando o
endereco muda, so e trocado se o OpenStreetMap achar o ENDERECO (rua e
numero); achou so a rua/bairro ou nada, o ponto manual fica.

(28/10, Alexandre - recado do analista 20261028-1020) REGRA 2: o ponto
achado tem de BATER COM O BAIRRO da base. Casos: AUTO PECAS FORTALEZA (o
OSM nao tem o numero 5548 da Cosme Ferreira e devolve um ponto da avenida,
a 1,65 km) e M. ABREU BRAGA (existe outra R. Ioruba em Manaus, no Novo
Aleixo, e o ponto caiu la, a 5 km). Agora:
  * o NUMERO que vem dentro do ENDERECO (N 253, ", 39A", numero no fim) e
    separado da rua (separar_numero; RUA 10, BR 010, KM 5 nao sao numero);
  * a consulta pede os detalhes do endereco (addressdetails) e tenta
    (Alexandre: "o CEP deve ser o primeiro item: CEP + o numero"): o
    numero + o logradouro do CEP (BrasilAPI) + o CEP > o numero + a rua da
    base > o PONTO DO CEP (precisao "cep") > rua > bairro;
  * o OSM achou a rua mas nao a casa (sem house_number): precisao "rua";
  * BAIRRO DIFERENTE: o OSM devolveu outro bairro a mais de RAIO_BAIRRO_KM
    do centro do bairro da base (ou sem bairro, a mais do dobro): a
    consulta nao vale e tenta a proxima; nada valeu, fica o CENTRO DO
    BAIRRO da base (precisao "bairro", "alerta": "BAIRRO DIFERENTE");
  * grava "regra": 2, "alerta" e "bairro_osm";
  * os pontos da regra antiga (sem "regra") sao refeitos (pendentes com
    refazer=True), menos os MANUAL; o MANUAL so e trocado se o OSM achar
    o ENDERECO exato e sem alerta.
  [SUPOSICAO 2,5 km] A rota so melhora no ponto exato com o link do
  Google (Divergencias > Sem coordenada / endereco > Importar preenchidos).

Quem roda:
  * o BAP Tools, ao gerar a BASE_CLIENTE (base_cliente.py): as colunas
    LATITUDE e LONGITUDE, e consulta os pendentes por alguns minutos;
  * o Planner, aba Base cliente, botao "Atualizar coordenadas": a base
    toda, em segundo plano;
  * atualizar_coordenadas.bat: o mesmo, sozinho.
Sem internet, nada quebra: a rota usa o centro do bairro (e o da cidade).
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
import sys

# (29/10, Alexandre: "o minimo de pasta possivel") o cache do Python fica fora
# da pasta do BAP (no %LOCALAPPDATA%\BAP_TOOLS\cache de cada maquina): sem
# __pycache__ na pasta e sem sincronizar cache pelo OneDrive.
try:
    import os as _os_c
    sys.pycache_prefix = sys.pycache_prefix or _os_c.path.join(
        _os_c.environ.get("LOCALAPPDATA") or _os_c.path.join(
            _os_c.path.dirname(_os_c.path.abspath(__file__)), "SISTEMA BAP"),
        *(("BAP_TOOLS", "cache") if _os_c.environ.get("LOCALAPPDATA")
          else ("cache",)))
except Exception:                                       # noqa: BLE001
    pass

URL = "https://nominatim.openstreetmap.org/search"
AGENTE = "BAP-AutoParts-Planner/1.0 (roteirizacao de visitas)"
INTERVALO = 1.1                 # segundos entre consultas (regra do servico)
REPETIR_FALHA_DIAS = 30
ARQUIVO = "COORDENADAS_CLIENTES.json"
RAIO_MAX_KM = 60.0              # o ponto tem de cair perto da cidade
ORIGEM_MANUAL = "MANUAL"        # (28/10) o ponto preenchido a mao
REGRA = 2                       # (28/10) a regra que fez o ponto
RAIO_BAIRRO_KM = 2.5            # (28/10) outro bairro mais longe que isso
RAIO_BAIRRO_SEM_NOME_KM = 5.0   # (28/10) sem nome de bairro no OSM
ALERTA_BAIRRO = "BAIRRO DIFERENTE"
# (28/10) refazer, em toda atualizacao, os pontos da regra antiga
REFAZER_REGRA_ANTIGA = True

ABREVIACOES = {
    "AV": "AVENIDA", "AVN": "AVENIDA", "R": "RUA", "TV": "TRAVESSA",
    "TRAV": "TRAVESSA", "TR": "TRAVESSA", "EST": "ESTRADA",
    "ESTR": "ESTRADA", "ROD": "RODOVIA", "AL": "ALAMEDA", "PC": "PRACA",
    "PCA": "PRACA", "PRC": "PRACA", "BC": "BECO", "VL": "VILA",
    "CJ": "CONJUNTO", "CONJ": "CONJUNTO", "RES": "RESIDENCIAL",
    "PQ": "PARQUE", "JD": "JARDIM", "LOT": "LOTEAMENTO", "STA": "SANTA",
    "STO": "SANTO", "S": "SAO", "N": "", "NR": "", "NO": "", "Nº": "",
    "PROF": "PROFESSOR", "DR": "DOUTOR", "GAL": "GENERAL",
    "GEN": "GENERAL", "CEL": "CORONEL", "PRES": "PRESIDENTE",
    "GOV": "GOVERNADOR", "MAL": "MARECHAL", "DEP": "DEPUTADO",
}


def _norm(v) -> str:
    t = unicodedata.normalize("NFKD", str(v or "")).encode(
        "ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def rua_por_extenso(endereco) -> str:
    """ "AV AUTAZ MIRIM 1020" -> "AVENIDA AUTAZ MIRIM 1020"."""
    partes = [ABREVIACOES.get(p, p) for p in _norm(endereco).split()]
    return " ".join(p for p in partes if p)


def numero_de(numero, endereco="") -> str:
    """O numero da porta (so digitos); "SN", "S/N" e vazio viram ""."""
    # (14/10) CORRIGIDO: o 1o padrao nao tem grupo - m.group(1) dava "no
    # such group" no 1o cliente com numero e a atualizacao parava inteira
    m = re.search(r"(\d+)", str(numero or ""))
    if not m:
        m = re.search(r"\b(\d{1,5})\b\s*$", _norm(endereco))
    return m.group(1) if m else ""


# (28/10) palavras que fazem parte do NOME da via quando vem um numero
# logo depois: "RUA 10", "BR 010", "KM 5", "QUADRA 3", "AM 010"
_PREFIXO_NUMERADO = {"RUA", "R", "TRAVESSA", "TV", "BR", "KM", "QD",
                     "QUADRA", "LOTE", "LT", "ALAMEDA", "AL", "ESTRADA", "EST",
                     "RODOVIA", "ROD", "VIA", "BECO", "BC", "CONJUNTO", "CJ",
                     "AVENIDA", "AV", "AM", "PA", "MA", "AP", "RR", "MT",
                     "VILA", "VL", "PASSAGEM", "PSG", "VICINAL", "RAMAL",
                     "ETAPA", "SETOR", "BLOCO", "BL", "CASA"}


def _sem_milhar(t: str) -> str:
    """(02/11) "4.010" -> "4010"; "1.234.567" -> "1234567" (so o ponto
    entre digitos com 3 depois; "KM 5.5" e "R. 10" ficam)."""
    return re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", str(t or ""))


def separar_numero(endereco, numero="") -> tuple:
    """(28/10) (rua sem o numero, numero da porta). O numero vem do campo
    NUMERO ("0", "S/N" e vazio nao valem) ou de DENTRO do endereco:
    "AV COSME FERREIRA 5548" -> 5548; "R SOBRAL N 253" -> 253;
    "RUA X, 39A" -> 39A; "RUA 10" e "BR 010" nao tem numero. "S/N" sai."""
    bruto = unicodedata.normalize("NFKD", str(endereco or "")).encode(
        "ascii", "ignore").decode().upper()
    # (02/11, amostra: BMW "AVENIDA TORQUATO TAPAJOS 4.010" virou o nº 4)
    # ponto de milhar no numero: "4.010" -> "4010"
    bruto = _sem_milhar(bruto)
    bruto = re.sub(r"\bS\s*/?\s*N\b|\bS\.\s*N\.?", " ", bruto)
    num = ""
    m_ = re.search(r"\d+[A-Z]?", re.sub(r"\bS\s*/?\s*N\b", "",
                                        _sem_milhar(str(numero or "")
                                                    .upper())))
    if m_ and m_.group(0).lstrip("0"):
        num = m_.group(0)
    m = re.search(r"(?:\bN[O\u00ba\u00b0]?|\bNR|\bNUM(?:ERO)?)\.?\s*(\d+[A-Z]?)\b",
                  bruto)
    if m:
        num = num or m.group(1)
        bruto = bruto[:m.start()] + " " + bruto[m.end():]
    else:
        m = re.search(r",\s*(\d+[A-Z]?)\b", bruto)
        if m:
            num = num or m.group(1)
            bruto = bruto[:m.start()] + " " + bruto[m.end():]
        else:
            toks = re.sub(r"[^A-Z0-9 ]", " ", bruto).split()
            if len(toks) >= 2 and re.fullmatch(r"\d{1,5}[A-Z]?", toks[-1]) \
                    and toks[-2] not in _PREFIXO_NUMERADO \
                    and not toks[-2].isdigit() or (
                        len(toks) >= 3 and re.fullmatch(r"\d{1,5}[A-Z]?",
                                                        toks[-1])
                        and toks[-2].isdigit()
                        and toks[-3] in _PREFIXO_NUMERADO):
                num = num or toks[-1]
                bruto = " ".join(toks[:-1])
            else:
                # (02/11, Alexandre: "ajuste o numero da rua, separando do
                # endereco") o numero NO MEIO, com o complemento depois:
                # "AV TORQUATO TAPAJOS 5550 FUNDOS", "R SALVADOR 120 SALA
                # 802", "AV MAX TEIXEIRA 3043 LETRA B": o numero sai e o
                # complemento fica fora da rua (o Google nao precisa dele)
                n_, corte = _numero_do_meio(toks)
                if n_:
                    num = num or n_
                    bruto = " ".join(toks[:corte])
    rua = rua_por_extenso(bruto)
    if num and rua.endswith(" " + num):
        rua = rua[: -len(num) - 1]
    return rua, (num if num.lstrip("0") else "")


# (02/11) depois do numero, palavra que comeca OUTRA via ou faz parte do
# nome ("CONJ JOAO PAULO 2 RUA 5", "28 DE DEZEMBRO", "2 ETAPA"): nao e a
# porta
_DEPOIS_NAO_E_PORTA = {"RUA", "R", "AV", "AVENIDA", "TV", "TRAVESSA",
                       "AL", "ALAMEDA", "EST", "ESTRADA", "ROD", "RODOVIA",
                       "BECO", "BC", "PASSAGEM", "PSG", "VICINAL", "RAMAL",
                       "DE", "DO", "DA", "DOS", "DAS", "ETAPA", "FASE",
                       "SETOR", "KM", "BR", "ANOS", "MIL"}


def _numero_do_meio(toks) -> tuple:
    """(02/11) (numero, quantos tokens sao a rua) do 1o numero de porta
    no meio do endereco (ver separar_numero); ("", 0) quando nao tem."""
    for i in range(2, len(toks)):
        t = toks[i]
        if not re.fullmatch(r"\d{1,5}[A-Z]?", t) or not t.strip("0"):
            continue
        antes = toks[i - 1]
        if antes in _PREFIXO_NUMERADO or antes.isdigit() or \
                re.fullmatch(r"\d+[A-Z]?", antes):
            continue                    # "RUA 10", "BR 174 518", "QD 3"
        depois = toks[i + 1] if i + 1 < len(toks) else ""
        if depois in _DEPOIS_NAO_E_PORTA:
            continue
        return t, i
    return "", 0


def endereco_do_cliente(c) -> str:
    """O endereco normalizado: e ele que diz se o cliente mudou de lugar.
    (O bairro fica de fora: o Planner escreve o bairro do jeito dele.)"""
    return " | ".join(_norm(c.get(k)) for k in
                      ("ENDERECO", "NUMERO", "CIDADE", "UF"))


def caminho(raiz_ou_base) -> Path:
    p = Path(raiz_ou_base)
    if p.suffix.lower() == ".json":                 # (28/10) o proprio arquivo
        return p
    if p.suffix.lower() == ".xlsx":
        return p.parent / ARQUIVO
    rel = p / "RELATORIOS"
    return (rel if rel.exists() else p) / ARQUIVO


def ler(arq) -> dict:
    try:
        return json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def texto_coordenada(v) -> str:
    """(23/10, Alexandre) como no modelo do roteirizador: texto com ponto,
    ate 7 casas, sem zero sobrando ("-3.010709", "-60.0082203"); vazio
    quando nao localizado."""
    try:
        t = f"{float(str(v).replace(',', '.')):.7f}".rstrip("0")
    except (TypeError, ValueError):
        return ""
    return t + "0" if t.endswith(".") else t


def ponto(g) -> tuple:
    """(lat, lon) em numero de uma entrada do arquivo - o formato novo
    ("LATITUDE" : "-3.010709") ou o antigo ("lat": -3.01); (None, None)
    quando nao foi localizado."""
    if not g:
        return None, None
    la, lo = g.get("LATITUDE", g.get("lat")), g.get("LONGITUDE", g.get("lon"))
    try:
        if la in (None, "") or lo in (None, ""):
            return None, None
        return (float(str(la).replace(",", ".")),
                float(str(lo).replace(",", ".")))
    except (TypeError, ValueError):
        return None, None


def no_formato(g) -> dict:
    """A entrada no formato de 23/10: LATITUDE/LONGITUDE em texto (o
    antigo lat/lon sai)."""
    la, lo = ponto(g)
    novo = {k: v for k, v in g.items() if k not in ("lat", "lon")}
    novo["LATITUDE"] = texto_coordenada(la) if la is not None else ""
    novo["LONGITUDE"] = texto_coordenada(lo) if lo is not None else ""
    ordem = ("end", "LATITUDE", "LONGITUDE", "precisao", "em")
    return {**{k: novo[k] for k in ordem if k in novo},
            **{k: v for k, v in novo.items() if k not in ordem}}


def gravar(arq, dados: dict) -> None:
    """(23/10) grava no formato do modelo: '"LATITUDE" : "-3.010709"', tab
    na margem."""
    arq = Path(arq)
    tmp = arq.with_suffix(".tmp")
    dados = {k: no_formato(v) for k, v in dados.items()}
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent="\t",
                              separators=(",", " : ")), encoding="utf-8")
    # (02/11) no Windows o OneDrive (ou outro programa lendo o arquivo)
    # segura o COORDENADAS por instantes e a troca dava "Acesso negado"
    # (WinError 5) no meio da rodada do Google: tenta de novo por ~40 s
    for espera in (0.5, 1, 1, 2, 2, 3, 5, 5, 10, 10, None):
        try:
            tmp.replace(arq)
            return
        except PermissionError:
            if espera is None:
                raise
            time.sleep(espera)


def eh_manual(g) -> bool:
    """(28/10) Ponto posto a mao: "origem" MANUAL (Excel de preenchimento)
    ou com "fonte" (corrigido pelo Google Maps)."""
    return bool(g) and (str(g.get("origem") or "").upper() == ORIGEM_MANUAL
                        or bool(g.get("fonte")))


# =========================================================================
# (13/11, Alexandre: "Altere para usar a lat long da base cliente agora")
# O Protheus passou a trazer a coordenada do cliente (A1_LATITU/A1_LONGIT,
# no Relatorio Clientes desde 10/11; os cadastros novos vem com o GPS de
# campo). Ponto do Protheus VALIDO (diferente de zero e a ate RAIO_MAX_KM do
# centro da cidade da base) passa na frente do OpenStreetMap e do Google;
# so o ponto MANUAL (posto a mao pela analista) fica na frente dele
# [SUPOSICAO]. Gravado no COORDENADAS_CLIENTES.json com "origem":
# "PROTHEUS" e "fonte" - como o MANUAL, nao entra na fila do OSM nem do
# Google. Ponto do Protheus fora da cidade fica de fora (conta em
# "recusados") e o cliente segue pelo caminho de antes. REGRA 2 vale
# tambem aqui: quando o ponto de antes BATE com o bairro da base (ate
# RAIO_BAIRRO_KM do centro do bairro) e o do Protheus NAO, fica o de antes
# (conta em "bairro"; ex.: MUNIZ MOTO PECAS, Jorge Teixeira, Protheus a
# 14 km no Centro).
# =========================================================================
ORIGEM_PROTHEUS = "PROTHEUS"


def numero_coordenada(v):
    """'-3.0470962   ' / '-3,04' / -3.04 -> float; vazio ou zero -> None."""
    try:
        f = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return f if f else None


def ponto_protheus_valido(c, la, lo) -> bool:
    if la is None or lo is None:
        return False
    if not (-35 < la < 6 and -75 < lo < -33):          # fora do Brasil
        return False
    try:
        import geografia as geo                         # noqa: PLC0415
        centro = geo.coordenada(c.get("UF"), c.get("CIDADE"))
        if centro and geo.distancia_km(centro, (la, lo)) > RAIO_MAX_KM:
            return False
    except ImportError:
        pass
    return True


def _antes_bate_bairro(c, antes, novo) -> bool:
    """O ponto de antes esta no bairro da base e o do Protheus nao (os dois
    a mais de 100 m um do outro)."""
    try:
        import geografia as geo                         # noqa: PLC0415
        if geo.distancia_km(antes, novo) < 0.1:
            return False
        bairro = _norm(c.get("BAIRRO"))
        if not bairro or bairro in ("SEM BAIRRO", "(SEM BAIRRO)"):
            return False
        c_b = geo.coordenada_do_bairro(_norm(c.get("UF")),
                                       _norm(c.get("CIDADE")), bairro)
        if not c_b:
            return False
        return (geo.distancia_km(c_b, antes) <= RAIO_BAIRRO_KM
                < geo.distancia_km(c_b, novo))
    except Exception:                                   # noqa: BLE001
        return False


def aplicar_protheus(clientes, arq, pontos: dict) -> dict:
    """Poe o ponto do Protheus (pontos = {CHAVE_CLIENTE: (lat, lon)}) no
    COORDENADAS_CLIENTES.json, na frente do OSM/Google (menos o MANUAL).
    Devolve {"protheus": com ponto do Protheus em uso, "trocados": gravados
    agora, "recusados": fora da cidade, "manuais": mantidos}."""
    out = {"protheus": 0, "trocados": 0, "recusados": 0, "manuais": 0,
           "bairro": 0}
    if not pontos:
        return out
    arq = Path(arq)
    dados = ler(arq)
    hoje = date.today().isoformat()
    for c in clientes:
        p = pontos.get(c.get("CHAVE_CLIENTE"))
        if not p:
            continue
        la, lo = numero_coordenada(p[0]), numero_coordenada(p[1])
        if la is None or lo is None:                    # sem ponto
            continue
        if not ponto_protheus_valido(c, la, lo):
            out["recusados"] += 1
            continue
        g = dados.get(c["CHAVE_CLIENTE"])
        if g and str(g.get("origem") or "").upper() == ORIGEM_MANUAL \
                and ponto(g)[0] is not None:
            out["manuais"] += 1
            continue
        if g and ponto(g)[0] is not None and \
                str(g.get("origem") or "").upper() != ORIGEM_PROTHEUS and \
                _antes_bate_bairro(c, ponto(g), (la, lo)):
            out["bairro"] += 1
            continue
        out["protheus"] += 1
        end = endereco_do_cliente(c)
        la_t, lo_t = texto_coordenada(la), texto_coordenada(lo)
        if g and str(g.get("origem") or "").upper() == ORIGEM_PROTHEUS \
                and g.get("end") == end and g.get("LATITUDE") == la_t \
                and g.get("LONGITUDE") == lo_t:
            continue                                    # nada mudou
        novo = {"end": end, "LATITUDE": la_t, "LONGITUDE": lo_t,
                "precisao": "protheus", "em": hoje, "regra": REGRA,
                "origem": ORIGEM_PROTHEUS,
                "fonte": "Protheus (A1_LATITU/A1_LONGIT)"}
        if g and ponto(g)[0] is not None and \
                str(g.get("origem") or "").upper() != ORIGEM_PROTHEUS:
            # o ponto de antes fica anotado (para comparar/voltar)
            novo["antes"] = {k: g.get(k) for k in (
                "LATITUDE", "LONGITUDE", "precisao", "origem", "em")
                if g.get(k) not in (None, "")}
        dados[c["CHAVE_CLIENTE"]] = novo
        out["trocados"] += 1
    if out["trocados"]:
        gravar(arq, dados)
    return out


def completar(clientes, arq) -> int:
    """Poe LATITUDE/LONGITUDE do arquivo nos clientes (quando o endereco
    e o mesmo que foi consultado). Devolve quantos ganharam ponto."""
    dados = ler(arq)
    n = 0
    for c in clientes:
        g = dados.get(c.get("CHAVE_CLIENTE"))
        la, lo = ponto(g)
        if la is not None and g.get("end") == endereco_do_cliente(c):
            c["LATITUDE"], c["LONGITUDE"] = la, lo
            n += 1
    return n


def pendentes(clientes, dados, hoje=None, refazer=None) -> list:
    """Os clientes a consultar: novos, com endereco alterado, ou que nao
    foram achados ha mais de 30 dias. (28/10) refazer (padrao:
    REFAZER_REGRA_ANTIGA): tambem os pontos da regra antiga (sem
    "regra": 2), menos os MANUAL - eles vao no FIM da fila."""
    hoje = hoje or date.today()
    refazer = REFAZER_REGRA_ANTIGA if refazer is None else refazer
    saida, antigos = [], []
    for c in clientes:
        g = dados.get(c.get("CHAVE_CLIENTE"))
        if not g or g.get("end") != endereco_do_cliente(c) \
                or ponto_cep_ruim(g):    # (29/10) ponto da cidade: refaz ja
            saida.append(c)
        elif ponto(g)[0] is None:
            try:
                quando = date.fromisoformat(g.get("em", "")[:10])
            except ValueError:
                quando = date.min
            if hoje - quando > timedelta(days=REPETIR_FALHA_DIAS):
                saida.append(c)
            elif refazer and str(g.get("regra") or "") != str(REGRA):
                antigos.append(c)
        elif refazer and not eh_manual(g) and \
                str(g.get("regra") or "") != str(REGRA):
            antigos.append(c)
    return saida + antigos


def _consultar(params: dict):
    """(28/10) {"lat", "lon", "address"} do 1o resultado (com os detalhes
    do endereco: house_number, road, suburb...), ou None."""
    import urllib.parse                                 # noqa: PLC0415
    import urllib.request                               # noqa: PLC0415
    q = dict(params, format="json", limit=1, countrycodes="br",
             addressdetails=1)
    req = urllib.request.Request(
        f"{URL}?{urllib.parse.urlencode(q)}",
        headers={"User-Agent": AGENTE, "Accept-Language": "pt-BR"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if res:
        return {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]),
                "address": res[0].get("address") or {}}
    return None


def _resposta(r):
    """((lat, lon), address ou None) - aceita o dict do _consultar e a
    tupla (lat, lon) dos testes/consultas antigas."""
    if not r:
        return None, None
    if isinstance(r, dict):
        return (float(r["lat"]), float(r["lon"])), (r.get("address") or {})
    return (float(r[0]), float(r[1])), None


def bairro_do_osm(address) -> str:
    """O bairro que o OSM devolveu (suburb, neighbourhood, quarter...)."""
    if not address:
        return ""
    for k in ("suburb", "neighbourhood", "quarter", "city_district",
              "residential", "hamlet"):
        if address.get(k):
            return _norm(address[k])
    return ""


def _mesmo_bairro(a, b) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a in b or b in a)


# (28/10, Alexandre) "O CEP DEVE SER O PRIMEIRO ITEM A SER PESQUISADO: CEP +
# O NUMERO DA RUA". O CEP (A1_CEP da BASE_CLIENTE) e consultado na BrasilAPI
# (a mesma do CNAE, sem cadastro): ela devolve o LOGRADOURO OFICIAL do CEP,
# o bairro e, as vezes, o ponto. A 1a consulta ao OpenStreetMap e o
# numero + esse logradouro + o CEP. O ponto do CEP (quando a BrasilAPI tem)
# vale antes do "so a rua". CEP generico da cidade (termina em 000) nao vira
# ponto. As respostas ficam em RELATORIOS\CEPS_CONSULTADOS.json.
CEP_API = "https://brasilapi.com.br/api/cep/v2/{}"
ARQUIVO_CEPS = "CEPS_CONSULTADOS.json"
_CEPS = {}                      # {cep: info ou {} (nao achado)}


def cep8(v) -> str:
    c = re.sub(r"\D", "", str(v or ""))
    return c.zfill(8) if 5 <= len(c) <= 8 else ""


def _consultar_cep(cep: str):
    """A BrasilAPI (cep v2): {"rua", "bairro", "cidade", "uf", "lat",
    "lon"} ou None. Erro de rede sobe (quem chama decide)."""
    import urllib.error                                 # noqa: PLC0415
    import urllib.request                               # noqa: PLC0415
    req = urllib.request.Request(CEP_API.format(cep), headers={
        "User-Agent": AGENTE, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            j = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None                 # CEP que nao existe
        raise
    coord = ((j.get("location") or {}).get("coordinates") or {})
    try:
        la = float(coord.get("latitude"))
        lo = float(coord.get("longitude"))
    except (TypeError, ValueError):
        la = lo = None
    return {"rua": j.get("street") or "", "bairro": j.get("neighborhood") or "",
            "cidade": j.get("city") or "", "uf": j.get("state") or "",
            "lat": la, "lon": lo}


# (29/10) A BrasilAPI devolve, para a maioria dos CEPs, o ponto da CIDADE
# (na rodada de 28/10: 1.281 clientes de Manaus no mesmo ponto, -3.10194 /
# -60.025; amostra de 10 PDVs x Google: os pontos "cep" a 4-23 km). O ponto
# do CEP so vale quando NENHUM outro CEP consultado tem o mesmo ponto.
_REPETIDOS = {"n": -1, "pontos": set()}


def _chave_ponto(la, lo) -> tuple:
    return round(float(la), 4), round(float(lo), 4)


def pontos_de_cidade() -> set:
    """Os pontos que a BrasilAPI deu para 2 CEPs ou mais (= ponto da
    cidade/regiao, nao do CEP)."""
    if _REPETIDOS["n"] != len(_CEPS):
        cnt = {}
        for v in _CEPS.values():
            if v and v.get("lat") is not None:
                k = _chave_ponto(v["lat"], v["lon"])
                cnt[k] = cnt.get(k, 0) + 1
        _REPETIDOS.update(n=len(_CEPS),
                          pontos={k for k, n in cnt.items() if n > 1})
    return _REPETIDOS["pontos"]


def ponto_do_cep_valido(info) -> bool:
    """O ponto do CEP e do CEP mesmo (nao o da cidade)?"""
    if not info or info.get("lat") is None:
        return False
    try:
        return _chave_ponto(info["lat"], info["lon"]) not in pontos_de_cidade()
    except (TypeError, ValueError):
        return False


def ponto_cep_ruim(g) -> bool:
    """Entrada do arquivo com precisao "cep" num ponto de cidade (a
    rodada de 28/10): tem de ser refeita."""
    if not g or str(g.get("precisao") or "").lower() != "cep":
        return False
    la, lo = ponto(g)
    return la is not None and _chave_ponto(la, lo) in pontos_de_cidade()


def info_do_cep(cep, consultar_cep=None):
    """O que se sabe do CEP (memoria + arquivo), ou None."""
    cep = cep8(cep)
    if not cep:
        return None
    if cep in _CEPS:
        return _CEPS[cep] or None
    try:
        info = (consultar_cep or _consultar_cep)(cep)
    except Exception:                                   # noqa: BLE001
        return None                     # sem rede: nao guarda, tenta depois
    _CEPS[cep] = info or {}
    return info or None


def carregar_ceps(pasta) -> None:
    try:
        _CEPS.update(json.loads((Path(pasta) / ARQUIVO_CEPS).read_text(
            encoding="utf-8")))
    except (OSError, ValueError):
        pass


def gravar_ceps(pasta) -> None:
    try:
        arq = Path(pasta) / ARQUIVO_CEPS
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(_CEPS, ensure_ascii=False, indent="\t"),
                       encoding="utf-8")
        tmp.replace(arq)
    except OSError:
        pass


def localizar_detalhe(c, consultar=None, esperar=time.sleep,
                      consultar_cep=None) -> dict:
    """(28/10, regra 2) {"lat", "lon", "precisao", "alerta", "bairro_osm"}.
    Ordem (pedido do Alexandre, CEP primeiro):
      1. CEP + NUMERO: o numero + o logradouro do CEP (BrasilAPI) + o CEP;
      2. o numero + a rua escrita na base (sem o CEP);
      -> achou a CASA (house_number): precisao "endereco";
      3. (29/10) a rua que o OSM achou nas tentativas 1-2 (sem a casa):
         "rua";
      4. o PONTO DO CEP (BrasilAPI; CEP generico ...000 nao; ponto
         repetido em outro CEP = ponto da cidade, nao): "cep"; senao a
         consulta da rua do CEP / da base: "rua";
      5. o bairro: "bairro".
    O ponto tem de cair a menos de 60 km do centro da cidade e BATER COM O
    BAIRRO da base (ate RAIO_BAIRRO_KM do centro do bairro, ou o mesmo nome
    no OSM); nada valeu por bairro diferente: o centro do bairro da base com
    o alerta BAIRRO DIFERENTE."""
    import geografia as geo                             # noqa: PLC0415
    consultar = consultar or _consultar
    cidade, uf = _norm(c.get("CIDADE")), _norm(c.get("UF"))
    rua, num = separar_numero(c.get("ENDERECO"), c.get("NUMERO"))
    cep = cep8(c.get("CEP"))
    cep_fmt = f"{cep[:5]}-{cep[5:]}" if cep else ""
    info = info_do_cep(cep, consultar_cep) if cep else None
    rua_cep = rua_por_extenso((info or {}).get("rua"))
    bairro = _norm(c.get("BAIRRO"))
    centro = geo.coordenada(uf, cidade)
    c_bairro = geo.coordenada_do_bairro(uf, cidade, bairro) \
        if bairro and bairro != "SEM BAIRRO" else None
    vazio = {"lat": None, "lon": None, "precisao": "", "alerta": "",
             "bairro_osm": ""}
    estado = {"divergiu": False, "b_div": "", "n": 0}

    def perguntar(params, checar_bairro=True):
        """(ponto, address) que vale, ou (None, None)."""
        if estado["n"]:
            esperar(INTERVALO)
        estado["n"] += 1
        p, adr = _resposta(consultar(params))
        if not p:
            return None, None
        if centro and geo.distancia_km(centro, p) > RAIO_MAX_KM:
            return None, None
        b_osm = bairro_do_osm(adr)
        if checar_bairro and c_bairro:
            d_b = geo.distancia_km(c_bairro, p)
            if (b_osm and not _mesmo_bairro(b_osm, bairro)
                    and d_b > RAIO_BAIRRO_KM) or \
                    (not b_osm and d_b > RAIO_BAIRRO_SEM_NOME_KM):
                estado["divergiu"], estado["b_div"] = True, b_osm
                return None, None
        return p, adr

    def saida(p, precisao, adr):
        div = estado["divergiu"]
        b_osm = bairro_do_osm(adr)
        return dict(vazio, lat=p[0], lon=p[1], precisao=precisao,
                    bairro_osm=(estado["b_div"] or b_osm) if div else b_osm,
                    alerta=ALERTA_BAIRRO if div else "")

    so_rua = None                       # a rua achada sem a casa
    # 1-2: CEP + numero (logradouro do CEP), depois numero + rua da base
    tent = []
    if num and cep and (rua_cep or rua):
        tent.append({"street": f"{num} {rua_cep or rua}", "city": cidade,
                     "state": uf, "postalcode": cep_fmt})
    if num and rua:
        tent.append({"street": f"{num} {rua}", "city": cidade, "state": uf})
    for params in tent:
        p, adr = perguntar(params)
        if not p:
            continue
        if adr is None or adr.get("house_number"):
            return saida(p, "endereco", adr)
        so_rua = so_rua or (p, adr)
    # (29/10) a rua que o OSM achou pelo logradouro do CEP vem antes do
    # ponto do CEP (o da BrasilAPI e, quase sempre, o ponto da cidade)
    if so_rua:
        return saida(so_rua[0], "rua", so_rua[1])
    # 3: o ponto do CEP (BrasilAPI) - CEP generico da cidade nao; ponto
    # repetido em outro CEP (= ponto da cidade) nao
    if info and ponto_do_cep_valido(info) and not cep.endswith("000"):
        p = (info["lat"], info["lon"])
        if not centro or geo.distancia_km(centro, p) <= RAIO_MAX_KM:
            return dict(vazio, lat=p[0], lon=p[1], precisao="cep",
                        bairro_osm=_norm(info.get("bairro")))
    # 4: a rua
    for r_ in dict.fromkeys(x for x in (rua_cep, rua) if x):
        p, adr = perguntar({"street": r_, "city": cidade, "state": uf})
        if p:
            return saida(p, "rua", adr)
    # 5: o bairro
    if bairro and bairro not in ("(SEM BAIRRO)", "SEM BAIRRO"):
        p, adr = perguntar({"q": f"{bairro}, {cidade}, {uf}, Brasil"},
                           checar_bairro=False)
        if p:
            return saida(p, "bairro", adr)
    if estado["divergiu"] and c_bairro:
        return dict(vazio, lat=c_bairro[0], lon=c_bairro[1],
                    precisao="bairro", alerta=ALERTA_BAIRRO,
                    bairro_osm=estado["b_div"])
    return vazio


def localizar(c, consultar=None, esperar=time.sleep):
    """(lat, lon, precisao) do endereco do cliente, ou (None, None, "")
    (a regra 2 de 28/10 - ver localizar_detalhe)."""
    r = localizar_detalhe(c, consultar, esperar)
    return r["lat"], r["lon"], r["precisao"]


def ceps_da_base(base) -> dict:
    """(28/10) {chave do cliente: CEP} da coluna CEP da BASE_CLIENTE
    (vazio quando a base ainda nao tem a coluna)."""
    try:
        try:            # (02/11) o rapido; sem ele, o openpyxl
            from xlsx_rapido import load_workbook       # noqa: PLC0415
        except ImportError:
            from openpyxl import load_workbook          # noqa: PLC0415
        wb = load_workbook(base, read_only=True, data_only=True)
    except Exception:                                   # noqa: BLE001
        return {}
    try:
        ws = wb["BASE_CLIENTE"] if "BASE_CLIENTE" in wb.sheetnames \
            else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        cab = [str(c or "").strip().upper() for c in next(it)]
        if "CEP" not in cab:
            return {}
        i_c, i_l, i_p = cab.index("COD_CLIENTE"), cab.index("LOJA"), \
            cab.index("CEP")
        saida = {}
        for r in it:
            cod = str(r[i_c] or "").strip()
            if cod:
                cod = cod.zfill(6) if cod.isdigit() else cod
                loja = str(r[i_l] or "").strip() or "00"
                saida[f"{cod}-{loja}"] = str(r[i_p] or "").strip()
        return saida
    except (StopIteration, ValueError, IndexError):
        return {}
    finally:
        wb.close()


def atualizar(raiz_ou_base, clientes=None, limite_seg=None, log=None,
              parar=None, consultar=None, esperar=time.sleep,
              refazer=None) -> dict:
    """
    Consulta os pendentes (novos e alterados) ate acabar, passar do
    limite de tempo ou parar() dizer que e para parar. Grava a cada 20.
    Devolve {"consultados", "achados", "faltam", "erro"}.
    """
    arq = caminho(raiz_ou_base)
    if clientes is None:
        import planner_nucleo as nu                     # noqa: PLC0415
        base = Path(raiz_ou_base)
        if base.suffix.lower() != ".xlsx":
            base = arq.parent / "BASE_CLIENTE.xlsx"
        clientes = nu.ler_base_cliente(base)
    dados = ler(arq)
    # (28/10) o CEP da BASE_CLIENTE para quem veio sem ele (Planner)
    if clientes and not any(c.get("CEP") for c in clientes):
        base_ = Path(raiz_ou_base)
        if base_.suffix.lower() != ".xlsx":
            base_ = arq.parent / "BASE_CLIENTE.xlsx"
        cep_de = ceps_da_base(base_)
        if cep_de:
            for c in clientes:
                c.setdefault("CEP", cep_de.get(c.get("CHAVE_CLIENTE"), ""))
    carregar_ceps(arq.parent)           # (29/10) antes: pendentes usa
    fila = pendentes(clientes, dados, refazer=refazer)
    ini = time.time()
    feitos = achados = 0
    erro = ""
    for c in fila:
        if parar and parar():
            break
        if limite_seg is not None and time.time() - ini >= limite_seg:
            break
        try:
            r_ = localizar_detalhe(c, consultar, esperar)
            lat, lon, prec = r_["lat"], r_["lon"], r_["precisao"]
        except OSError as e:          # rede: sem internet / bloqueado
            erro = str(e)[:200]
            if feitos == 0:     # nem a 1a respondeu: nem insiste
                break
            esperar(5)
            continue
        except Exception as e:                          # noqa: BLE001
            # (14/10) problema SO deste cliente (endereco estranho): anota
            # e segue - antes um cliente parava a base inteira
            erro = f"{c.get('CHAVE_CLIENTE')}: {str(e)[:150]}"
            continue
        ant = dados.get(c["CHAVE_CLIENTE"])
        if eh_manual(ant) and ponto(ant)[0] is not None and \
                (prec != "endereco" or r_["alerta"]):
            # (28/10) o ponto manual nao sai por um ponto pior (so da rua
            # ou do bairro) nem por nada: fica, com o endereco novo
            dados[c["CHAVE_CLIENTE"]] = dict(
                ant, end=endereco_do_cliente(c), em=date.today().isoformat())
            feitos += 1
            esperar(INTERVALO)
            continue
        dados[c["CHAVE_CLIENTE"]] = {
            "end": endereco_do_cliente(c),
            "LATITUDE": texto_coordenada(lat) if lat is not None else "",
            "LONGITUDE": texto_coordenada(lon) if lon is not None else "",
            "precisao": prec, "em": date.today().isoformat(),
            "regra": REGRA}
        if r_["alerta"]:
            dados[c["CHAVE_CLIENTE"]]["alerta"] = r_["alerta"]
        if r_["bairro_osm"]:
            dados[c["CHAVE_CLIENTE"]]["bairro_osm"] = r_["bairro_osm"]
        feitos += 1
        achados += lat is not None
        if log and feitos % 10 == 0:
            log(f"Coordenadas: {feitos} de {len(fila)} "
                f"({achados} localizados)")
        if feitos % 20 == 0:
            gravar(arq, dados)
            gravar_ceps(arq.parent)
        esperar(INTERVALO)
    if feitos:
        gravar(arq, dados)
        gravar_ceps(arq.parent)
    return {"consultados": feitos, "achados": achados,
            "faltam": len(fila) - feitos, "erro": erro, "arquivo": str(arq)}


# =========================================================================
# (28/10, Alexandre) GOOGLE GEOCODING API - SO PARA OS DIVERGENTES
# Quem ficou sem ponto, com ponto recusado (> 60 km da cidade), so da rua,
# so do bairro ou com BAIRRO DIFERENTE (a aba "Sem coordenada / endereco"
# das Divergencias) e consultado na API oficial do Google (geocode/json):
# endereco + numero + bairro + cidade/UF + CEP. ROOFTOP/RANGE_INTERPOLATED
# = "endereco"; GEOMETRIC_CENTER = "rua"; APPROXIMATE nao troca um ponto
# que ja existe. O ponto gravado leva "origem": "GOOGLE" e "fonte" (o
# OpenStreetMap nao o troca depois, como o MANUAL). Ponto MANUAL nunca e
# consultado.
#
# A CHAVE e do Alexandre (Google Cloud, cobranca dele, nao da TI): fica em
# google_maps_config.json na pasta do BAP (Regionais - Leandro; 29/10,
# pedido do Alexandre), ou na variavel GOOGLE_MAPS_API_KEY. NUNCA fica no
# codigo, nunca e impressa.
# Sem chave, nao faz nada. Teto por mes em GOOGLE_LIMITE_MES (a conta fica
# em RELATORIOS\GOOGLE_MAPS_USO.json) [SUPOSICAO: 9.000, dentro da cota
# gratis de 10 mil/mes; conferir no console do Google]. Os termos do Google
# limitam guardar o resultado da API (conferir o prazo) [SUPOSICAO].
# Roda pelo atualizar_coordenadas_google.bat (geocodificar.py --google).
# =========================================================================
GOOGLE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_CONFIG = "google_maps_config.json"
GOOGLE_USO = "GOOGLE_MAPS_USO.json"
GOOGLE_LIMITE_MES = 9000
GOOGLE_INTERVALO = 0.05         # a API aceita bem mais que 1 por segundo
GOOGLE_DE_VEZ = 5                # (02/11) consultas em paralelo
ORIGEM_GOOGLE = "GOOGLE"


GOOGLE_SEM_CHAVE = "COLE_A_CHAVE_AQUI"


def configs_google(raiz) -> list:
    """(29/10, Alexandre: "tudo tem que ficar em Regionais - Leandro") a
    chave fica SO na pasta do BAP."""
    return [Path(raiz) / GOOGLE_CONFIG]


def chave_google(raiz) -> str:
    """A chave da API: google_maps_config.json ({"api_key": "..."}) ou a
    variavel GOOGLE_MAPS_API_KEY. Vazio = sem chave."""
    import os                                           # noqa: PLC0415
    for arq in configs_google(raiz):
        try:
            k = str(json.loads(arq.read_text(encoding="utf-8-sig"))
                    .get("api_key") or "").strip()
        except (OSError, ValueError, AttributeError):
            continue
        if k and k != GOOGLE_SEM_CHAVE:
            return k
    return (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()


def divergente(c, g) -> bool:
    """O cliente da aba "Sem coordenada / endereco" (o ponto): sem ponto,
    recusado (> 60 km), so da rua, so do bairro ou BAIRRO DIFERENTE. O
    MANUAL (e o que ja veio do Google) nao."""
    if g and eh_manual(g):
        return False
    la, lo = ponto(g)
    if la is None or ponto_cep_ruim(g):
        return True
    try:
        import geografia as geo                         # noqa: PLC0415
        centro = geo.coordenada(c.get("UF"), c.get("CIDADE"))
        if centro and geo.distancia_km(centro, (la, lo)) > RAIO_MAX_KM:
            return True
    except ImportError:
        pass
    return (str(g.get("precisao") or "").lower() in ("rua", "bairro")
            or bool(g.get("alerta")))


# (28/10) faixa de CEP de cada UF (5 primeiros digitos): CEP fora da UF
# (erro de cadastro, ex.: Manaus com 06904-301) nao vai para o Google
_CEP_UF = {
    "SP": [(1000, 19999)], "RJ": [(20000, 28999)], "ES": [(29000, 29999)],
    "MG": [(30000, 39999)], "BA": [(40000, 48999)], "SE": [(49000, 49999)],
    "PE": [(50000, 56999)], "AL": [(57000, 57999)], "PB": [(58000, 58999)],
    "RN": [(59000, 59999)], "CE": [(60000, 63999)], "PI": [(64000, 64999)],
    "MA": [(65000, 65999)], "PA": [(66000, 68899)], "AP": [(68900, 68999)],
    "AM": [(69000, 69299), (69400, 69899)], "RR": [(69300, 69399)],
    "AC": [(69900, 69999)], "DF": [(70000, 72799), (73000, 73699)],
    "GO": [(72800, 72999), (73700, 76799)], "RO": [(76800, 76999)],
    "TO": [(77000, 77999)], "MT": [(78000, 78899)], "MS": [(79000, 79999)],
    "PR": [(80000, 87999)], "SC": [(88000, 89999)], "RS": [(90000, 99999)]}


def cep_da_uf(cep, uf) -> bool:
    """O CEP cai na faixa da UF? (UF desconhecida: aceita)"""
    c = cep8(cep)
    if not c:
        return False
    faixas = _CEP_UF.get(_norm(uf))
    return not faixas or any(a <= int(c[:5]) <= b for a, b in faixas)


def _num_base(v) -> float:
    try:
        return float(str(v or 0).replace(".", "").replace(",", ".")
                     if "," in str(v or "") else str(v or 0))
    except ValueError:
        return 0.0


def _ordem_google(c, g) -> tuple:
    """(29/10, Alexandre: a TomTom tem limite de 2.500 - "priorize os
    clientes mais importantes") Quem vai primeiro: a curva (S, A, B, C, Z),
    a receita de 6 meses, o limite aprovado/disponivel (o desempate do
    TOP 30); so depois o tipo do ponto (sem ponto/recusado, bairro ou
    BAIRRO DIFERENTE, rua). O que o OSM achou na casa ("endereco") nao
    entra (nao e divergente)."""
    prec = str((g or {}).get("precisao") or "").lower()
    grupo = (0 if ponto(g)[0] is None or prec not in ("rua", "bairro")
             and not (g or {}).get("alerta") else 2 if prec == "rua"
             and not g.get("alerta") else 1)
    curva = "SABCZ".find(_norm(c.get("CURVA_RECEITA"))[:1] or "Z")
    rec = _num_base(c.get("RECEITA_6M"))
    lim = max(_num_base(c.get("LIMITE_APROVADO")),
              _num_base(c.get("LIMITE_DISPONIVEL")))
    return curva if curva >= 0 else 9, -rec, -lim, grupo


def endereco_google(c) -> str:
    """ "5548 Avenida Cosme Ferreira, Zumbi dos Palmares, Manaus - AM,
    69084-425, Brasil" (o numero de dentro do endereco separado)."""
    rua, num = separar_numero(c.get("ENDERECO"), c.get("NUMERO"))
    cep = cep8(c.get("CEP")) if cep_da_uf(c.get("CEP"), c.get("UF")) else ""
    partes = [f"{rua}, {num}" if num else rua, _norm(c.get("BAIRRO")),
              f"{_norm(c.get('CIDADE'))} - {_norm(c.get('UF'))}",
              f"{cep[:5]}-{cep[5:]}" if cep else "", "Brasil"]
    return ", ".join(p for p in partes
                     if p and p not in ("(SEM BAIRRO)", "SEM BAIRRO"))


def endereco_pelo_cep(c) -> str:
    """(02/11, Alexandre: "onde o endereco esta divergente, use o CEP e
    numero como base principal") "<rua do CEP>, <numero>, <bairro do CEP>,
    <cidade> - UF, <CEP>, Brasil": a rua e o bairro OFICIAIS do CEP (cache
    da BrasilAPI, CEPS_CONSULTADOS.json) no lugar dos da base. Sem numero,
    sem CEP da UF ou CEP generico (sem rua): o endereco da base
    (endereco_google)."""
    _rua, num = separar_numero(c.get("ENDERECO"), c.get("NUMERO"))
    cep = cep8(c.get("CEP")) if cep_da_uf(c.get("CEP"), c.get("UF")) else ""
    info = _CEPS.get(cep) if cep else None
    if not (num and info and _norm(info.get("rua"))):
        return endereco_google(c)
    partes = [f"{info['rua']}, {num}", info.get("bairro") or "",
              f"{_norm(c.get('CIDADE'))} - {_norm(c.get('UF'))}",
              f"{cep[:5]}-{cep[5:]}", "Brasil"]
    return ", ".join(p for p in partes if p)


# (02/11, amostra Belem/Manaus x Google Maps: "R. do Una, 115" caiu na rua
# de mesmo nome do Telegrafo (o cliente e na Cabanagem, 8,8 km) e "Doutor
# Ernesto Adolfo, 03" voltou como "R. Barra Branca, 3" - os dois como CASA)
# A rua e o bairro que o Google devolve sao conferidos com os da base/CEP.
_TIPO_DE_VIA = {"RUA", "AVENIDA", "TRAVESSA", "ESTRADA", "RODOVIA",
                "ALAMEDA", "PASSAGEM", "VILA", "CONJUNTO", "BECO", "PRACA",
                "VIELA", "RAMAL", "VICINAL", "LOTEAMENTO", "RESIDENCIAL",
                "DE", "DA", "DO", "DAS", "DOS", "E", "AVE", "LARGO",
                "QUADRA", "TRAV", "ESTR", "ROD", "AV", "R", "TV", "PSG"}
ALERTA_RUA = "RUA DIFERENTE"
ALERTA_NUMERO = "NUMERO DIFERENTE"


def _miolo_da_rua(rua) -> set:
    return {t for t in rua_por_extenso(rua).split()
            if t not in _TIPO_DE_VIA and len(t) >= 3 and not t.isdigit()}


def mesma_rua(a, b) -> bool:
    """(02/11) "R. do Una" = "RUA DO UNA"; "Av. Des. Joao Machado" =
    "AV DESEMBARGADOR JOAO MACHADO"; "R. Barra Branca" != "DOUTOR ERNESTO
    ADOLFO". Sem nome de um dos lados: nao da para dizer (vale)."""
    import difflib                                      # noqa: PLC0415
    ta, tb = _miolo_da_rua(a), _miolo_da_rua(b)
    if not ta or not tb:
        return True
    if len(ta & tb) * 2 >= min(len(ta), len(tb)):
        return True
    return difflib.SequenceMatcher(None, " ".join(sorted(ta)),
                                   " ".join(sorted(tb))).ratio() >= 0.75


def _bairro_parecido(a, b) -> bool:
    import difflib                                      # noqa: PLC0415
    a, b = _norm(a), _norm(b)
    return _mesmo_bairro(a, b) or (bool(a and b) and difflib.SequenceMatcher(
        None, a, b).ratio() >= 0.8)


def conferir_rua_bairro(c, p, rua_g, bairro_g) -> str:
    """(02/11) "" quando a rua e o bairro do Google batem com os da base;
    senao o alerta: RUA DIFERENTE (nem a rua da base nem a do CEP) ou
    BAIRRO DIFERENTE (outro bairro a mais de RAIO_BAIRRO_KM do centro do
    bairro da base; sem nome, a mais de RAIO_BAIRRO_SEM_NOME_KM)."""
    import geografia as geo                             # noqa: PLC0415
    if rua_g:
        rua_b = separar_numero(c.get("ENDERECO"), c.get("NUMERO"))[0]
        cep = cep8(c.get("CEP"))
        rua_c = (_CEPS.get(cep) or {}).get("rua") if cep else ""
        if not (mesma_rua(rua_g, rua_b) or (rua_c and mesma_rua(rua_g,
                                                                 rua_c))):
            return ALERTA_RUA
    bairro = _norm(c.get("BAIRRO"))
    if bairro and bairro not in ("SEM BAIRRO", "(SEM BAIRRO)"):
        try:
            c_b = geo.coordenada_do_bairro(_norm(c.get("UF")),
                                           _norm(c.get("CIDADE")), bairro)
        except Exception:                               # noqa: BLE001
            c_b = None
        # so quando o Google DIZ outro bairro (nome parecido vale: "Santa
        # Tereza" = "SANTA TERESA") e o ponto esta a mais de RAIO_BAIRRO_KM
        # do centro do bairro da base; sem o nome do bairro, nao acusa
        if c_b and bairro_g and not _bairro_parecido(bairro_g, bairro) \
                and geo.distancia_km(c_b, p) > RAIO_BAIRRO_KM:
            return ALERTA_BAIRRO
    return ""


_COMECO_DE_RUA = {"R", "RUA", "AV", "AVENIDA", "TV", "TRAVESSA", "ESTR",
                  "ESTRADA", "ROD", "RODOVIA", "AL", "ALAMEDA", "PSG",
                  "PASSAGEM", "BECO", "BC", "PCA", "PRACA", "VILA", "VL",
                  "CONJ", "CONJUNTO", "VIELA", "RAMAL", "VICINAL", "LARGO",
                  "TRAV", "VIA", "ALAM", "PASS", "BR"}


def rua_bairro_da_fonte(fonte) -> tuple:
    """(02/11) (rua, bairro) do endereco que o Google devolveu, guardado
    na "fonte": "Google ... (ROOFTOP): R. do Una, 115 - Telegrafo, Belem -
    PA, ..." -> ("R. do Una", "Telegrafo"). As vezes vem o NOME do lugar
    antes ("RESTAURANTE OLIVEIRA - Av. Brasil, ..."): vale o 1o pedaco que
    comeca com tipo de via (R., Av., Tv., Estr...); sem nenhum: ("", "")."""
    t = str(fonte or "").split("): ", 1)
    if len(t) < 2:
        return "", ""
    partes = [x.strip() for x in t[1].split(",")]
    for i, parte in enumerate(partes[:3]):
        pedacos = [x.strip() for x in parte.split(" - ")]
        for k, ped in enumerate(pedacos):
            prim = (_norm(ped).split() or [""])[0]
            if prim not in _COMECO_DE_RUA:
                continue
            bairro = ""
            if k + 1 < len(pedacos):
                bairro = pedacos[k + 1]
            elif i + 1 < len(partes) and " - " in partes[i + 1]:
                bairro = partes[i + 1].rsplit(" - ", 1)[1].strip()
            if re.fullmatch(r"[A-Z]{2}", bairro.upper()) or \
                    re.fullmatch(r"[\d\-]+", bairro):
                bairro = ""             # "Belem - PA": era a cidade
            return ped, bairro
    return "", ""


def mesma_cidade(a, b) -> bool:
    """(02/11) "SAO LUIS" = "São Luís"; "SANTA ISABEL DO PARA" ~ "Santa
    Izabel do Pará" (grafia parecida tambem vale)."""
    import difflib                                      # noqa: PLC0415
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a in b or b in a or
                              difflib.SequenceMatcher(None, a, b).ratio()
                              >= 0.85)


def _consultar_google(endereco, chave):
    """A resposta da Geocoding API: {"lat", "lon", "tipo", "parcial",
    "endereco"} ou None. Erro de chave/cota sobe (para parar a rodada)."""
    import urllib.parse                                 # noqa: PLC0415
    import urllib.request                               # noqa: PLC0415
    q = {"address": endereco, "components": "country:BR", "region": "br",
         "language": "pt-BR", "key": chave}
    codigo, j = _http_json(f"{GOOGLE_URL}?{urllib.parse.urlencode(q)}")
    j = j or {}
    if codigo != 200 and not j:
        raise RuntimeError(f"Google: HTTP {codigo}")
    st = j.get("status")
    if st in ("ZERO_RESULTS", "INVALID_REQUEST", "UNKNOWN_ERROR"):
        return None                     # so este endereco; segue a fila
    if st != "OK":
        # REQUEST_DENIED (chave), OVER_QUERY_LIMIT, OVER_DAILY_LIMIT...
        raise RuntimeError(f"Google: {st} {j.get('error_message', '')}"[:200])
    r = j["results"][0]
    loc = r["geometry"]["location"]
    # (02/11) o numero, a cidade e o CEP que o Google achou (para conferir
    # com o da base: o parcial com o MESMO numero na MESMA cidade e a casa)
    comp = {}
    for a in r.get("address_components") or []:
        for t in a.get("types") or []:
            comp.setdefault(t, a.get("long_name") or "")
    return {"lat": float(loc["lat"]), "lon": float(loc["lng"]),
            "tipo": r["geometry"].get("location_type", ""),
            "parcial": bool(r.get("partial_match")),
            "endereco": r.get("formatted_address", ""),
            "numero": comp.get("street_number", ""),
            "cidade": comp.get("administrative_area_level_2")
            or comp.get("locality", ""),
            "cep": comp.get("postal_code", ""),
            "rua": comp.get("route", ""),
            "bairro": comp.get("sublocality_level_1")
            or comp.get("sublocality") or comp.get("neighborhood", "")}


def _uso_google(pasta, mes, somar=0) -> int:
    return _uso_api(pasta, GOOGLE_USO, mes, somar)


def _uso_api(pasta, nome, mes, somar=0) -> int:
    """Consultas gastas no periodo (mes do Google, dia da TomTom)."""
    arq = Path(pasta) / nome
    try:
        uso = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        uso = {}
    if somar:
        uso[mes] = int(uso.get(mes, 0)) + somar
        try:
            arq.write_text(json.dumps(uso, indent="\t"), encoding="utf-8")
        except OSError:
            pass
    return int(uso.get(mes, 0))


# =========================================================================
# (02/11, Alexandre: "faca os tres pontos", depois da amostra de 30 PDVs de
# Belem e Manaus x Google Maps) PLACES API (NOVA) - o ponto da EMPRESA:
# para quem o Geocoding deixou na rua/bairro ou com alerta (RUA/BAIRRO
# DIFERENTE), procura a empresa pelo nome (fantasia; senao a razao social)
# + bairro + cidade na Places API (Text Search, places:searchText, POST,
# chave no cabecalho X-Goog-Api-Key - a MESMA chave do google_maps_config;
# a "Places API (New)" tem de estar ativa no projeto da chave). Vale o 1o
# resultado que: cai a ate 60 km da cidade, e da mesma cidade, e o NOME
# bate (uma palavra que nao e generica - MOTOS, AUTO, PECAS... nao contam)
# ou o ENDERECO bate (a mesma rua e o mesmo numero da base). Entra como
# precisao "endereco", origem GOOGLE, fonte "Google Places (empresa): ...",
# marca "places_em" (nao repete). Teto PLACES_LIMITE_MES por mes em
# RELATORIOS\GOOGLE_PLACES_USO.json [SUPOSICAO: 4.500, abaixo das 5.000
# gratis por mes do Text Search Pro; conferir no console do Google].
# =========================================================================
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_USO = "GOOGLE_PLACES_USO.json"
PLACES_LIMITE_MES = 4500
# (02/11, Alexandre: "pesquisei 1000 places, depois deu quota day exceed")
# a Places tem cota por DIA no projeto: no maximo PLACES_LIMITE_DIA por dia
# (conta em GOOGLE_PLACES_USO.json, chave AAAA-MM-DD); estourou a cota
# (RESOURCE_EXHAUSTED / quota) = o dia fica cheio e o resto vai amanha
PLACES_LIMITE_DIA = 1000
PLACES_DE_VEZ = 4
PLACES_CAMPOS = ("places.displayName,places.formattedAddress,"
                 "places.location,places.addressComponents,places.types")
# (02/11, 2a amostra: "POSTO ALEIXO" virou o BAIRRO Aleixo) so vale
# ESTABELECIMENTO: lugar que e bairro/cidade/rua fica de fora
_TIPO_NAO_EMPRESA = {"political", "locality", "sublocality",
                     "sublocality_level_1", "neighborhood", "route",
                     "administrative_area_level_1",
                     "administrative_area_level_2", "postal_code",
                     "country", "street_address", "premise", "geocode"}
_NOME_GENERICO = {
    "MOTOS", "MOTO", "AUTO", "AUTOS", "PECAS", "PECA", "AUTOPECAS", "CENTER",
    "CENTRO", "COMERCIO", "COM", "LTDA", "EIRELI", "EPP", "CIA", "SERVICOS",
    "SERVICO", "SERV", "MECANICA", "OFICINA", "BORRACHARIA", "PNEUS",
    "DISTRIBUIDORA", "DISTRIBUIDOR", "ACESSORIOS", "LOJA", "VEICULOS",
    "COMERCIAL", "INDUSTRIA", "IND", "EMPRESA", "REPRESENTACOES", "PNEU",
    "BATERIAS", "BATERIA", "ELETRICA", "ELETRO", "LUBRIFICANTES", "OLEO",
    "TRANSPORTES", "TRANSPORTE", "MANAUS", "BELEM", "BRASIL", "NORTE", "DOS",
    "DAS", "DE", "DA", "DO", "E", "ME", "SA", "S/A", "FILIAL", "MATRIZ",
    "CAR", "CARS", "MOTOPECAS", "DIESEL", "TRUCK", "CAMINHOES", "BIKE",
    "SOLUCOES", "MANUTENCAO", "REPAROS", "ATACADO", "VAREJO", "GERAL"}


def _palavras_do_nome(nome) -> set:
    return {t for t in _norm(nome).split()
            if len(t) >= 3 and t not in _NOME_GENERICO and not t.isdigit()}


def mesmo_nome(a, b) -> bool:
    """(02/11) "AUTO CENTER NOBRE" = "AUTO CENTER NOBRE DWR TUNING";
    "EXPRESS SERVICOS" = "Mecanica Express"; "IRMAOS DIAMANTINO" !=
    "Tropical Nissan"."""
    return bool(_palavras_do_nome(a) & _palavras_do_nome(b))


def _consultar_places(texto, chave, centro=None):
    """Os lugares (ate 3) da Places API (nova): [{"nome", "endereco",
    "lat", "lon", "numero", "rua", "cidade"}]. Erro de chave/cota/API
    desligada sobe (para o passo)."""
    corpo = {"textQuery": texto, "languageCode": "pt-BR",
             "regionCode": "BR", "pageSize": 3}
    if centro:
        corpo["locationBias"] = {"circle": {
            "center": {"latitude": centro[0], "longitude": centro[1]},
            "radius": 30000.0}}
    codigo, j = _http_json(PLACES_URL, cabecalhos={
        "X-Goog-Api-Key": chave, "X-Goog-FieldMask": PLACES_CAMPOS,
        "Content-Type": "application/json"},
        corpo=json.dumps(corpo, ensure_ascii=False))
    j = j or {}
    if codigo != 200:
        err = j.get("error") or {}
        raise RuntimeError(f"Places: {err.get('status') or codigo} "
                           f"{err.get('message', '')}"[:220])
    saida = []
    for pl in (j.get("places") or [])[:3]:
        comp = {}
        for a in pl.get("addressComponents") or []:
            for t in a.get("types") or []:
                comp.setdefault(t, a.get("longText") or "")
        loc = pl.get("location") or {}
        try:
            la, lo = float(loc["latitude"]), float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        tipos = set(pl.get("types") or [])
        if tipos & _TIPO_NAO_EMPRESA and not tipos & {"establishment",
                                                      "point_of_interest"}:
            continue                    # bairro/cidade/rua, nao a empresa
        saida.append({"nome": (pl.get("displayName") or {}).get("text", ""),
                      "endereco": pl.get("formattedAddress", ""),
                      "lat": la, "lon": lo,
                      "numero": comp.get("street_number", ""),
                      "rua": comp.get("route", ""),
                      "cidade": comp.get("administrative_area_level_2")
                      or comp.get("locality", "")})
    return saida


def lugar_que_vale(c, lugares):
    """(02/11) O 1o lugar da Places que e o cliente (ver acima), ou None."""
    import geografia as geo                             # noqa: PLC0415
    centro = geo.coordenada(_norm(c.get("UF")), _norm(c.get("CIDADE")))
    rua_b, num_b = separar_numero(c.get("ENDERECO"), c.get("NUMERO"))
    for lg in lugares or []:
        p = (lg["lat"], lg["lon"])
        if centro and geo.distancia_km(centro, p) > RAIO_MAX_KM:
            continue
        if lg.get("cidade") and not mesma_cidade(lg["cidade"],
                                                 c.get("CIDADE")):
            continue
        # a palavra em comum nao pode ser so o nome do bairro/cidade do
        # cliente ("POSTO ALEIXO" x "Aleixo")
        lugar_ = _palavras_do_nome(c.get("BAIRRO")) | \
            _palavras_do_nome(c.get("CIDADE"))
        p_lg = _palavras_do_nome(lg["nome"]) - lugar_
        nome_ok = bool(p_lg & (_palavras_do_nome(c.get("NOME_FANTASIA"))
                               | _palavras_do_nome(c.get("NOME_CLIENTE"))))
        n_b = re.sub(r"\D", "", str(num_b or "")).lstrip("0")
        n_g = (re.match(r"\d+", str(lg.get("numero") or "")) or [""])[0] \
            .lstrip("0")
        end_ok = bool(n_b and n_b == n_g and lg.get("rua")
                      and mesma_rua(lg["rua"], rua_b))
        if nome_ok or end_ok:
            return lg
    return None


def conferir_pontos_google(dados, clientes) -> int:
    """(02/11) Os pontos CASA do Google ja gravados: a rua e o bairro que o
    Google devolveu (na "fonte") x os da base. Diferente: precisao "rua" +
    alerta (o ponto fica; vai para a Places). Marca "conferido_em"."""
    hoje = date.today().isoformat()
    n = 0
    for c in clientes:
        g = dados.get(c.get("CHAVE_CLIENTE"))
        if not g or str(g.get("origem") or "").upper() != ORIGEM_GOOGLE \
                or g.get("conferido_em") or g.get("places_em") \
                or str(g.get("precisao") or "").lower() != "endereco":
            continue
        g["conferido_em"] = hoje
        la, lo = ponto(g)
        if la is None:
            continue
        rua_g, bairro_g = rua_bairro_da_fonte(g.get("fonte"))
        alerta = conferir_rua_bairro(c, (la, lo), rua_g, bairro_g)
        if not alerta and rua_g:
            # (02/11) o numero que o Google pos x o da base (amostra: BMW
            # "4.010" lido como 4 - o ponto ficou no nº 4)
            m_ = re.search(re.escape(rua_g) + r",\s*(\d+)",
                           str(g.get("fonte") or ""))
            n_b = re.sub(r"\D", "", str(separar_numero(
                c.get("ENDERECO"), c.get("NUMERO"))[1] or ""))
            if m_ and n_b and m_.group(1).lstrip("0") != n_b.lstrip("0"):
                alerta = ALERTA_NUMERO      # ("02" = "2")
        if alerta:
            g["precisao"], g["alerta"] = "rua", alerta
            g["obs"] = (f"02/11: o Google pos o ponto em {rua_g}"
                        f"{' - ' + bairro_g if bairro_g else ''}; "
                        "conferir")[:200]
            n += 1
    return n


def atualizar_places(raiz_ou_base, clientes=None, limite=None, log=None,
                     consultar=None, chave=None, parar=None) -> dict:
    """(02/11) O passo da Places API (ver acima). Devolve {"fila",
    "consultados", "achados", "erro", "uso"}."""
    import geografia as geo                             # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor   # noqa: PLC0415
    arq = caminho(raiz_ou_base)
    raiz = arq.parent.parent if arq.parent.name.upper() == "RELATORIOS" \
        else arq.parent
    res = {"fila": 0, "consultados": 0, "achados": 0, "erro": "", "uso": 0,
           "conferidos": 0}
    chave = chave if chave is not None else chave_google(raiz)
    if not chave and consultar is None:
        res["erro"] = "sem a chave da API do Google"
        return res
    if clientes is None:
        import planner_nucleo as nu                     # noqa: PLC0415
        base = Path(raiz_ou_base)
        if base.suffix.lower() != ".xlsx":
            base = arq.parent / "BASE_CLIENTE.xlsx"
        try:
            import xlsx_rapido as _xr                   # noqa: PLC0415
            _lw, nu.load_workbook = nu.load_workbook, _xr.load_workbook
        except Exception:                               # noqa: BLE001
            _xr = None
        try:
            clientes = nu.ler_base_cliente(base)
        finally:
            if _xr is not None:
                nu.load_workbook = _lw
        cep_de = ceps_da_base(base)
        for c in clientes:
            if not c.get("CEP"):
                c["CEP"] = cep_de.get(c.get("CHAVE_CLIENTE"), "")
    dados = ler(arq)
    carregar_ceps(arq.parent)
    res["conferidos"] = conferir_pontos_google(dados, clientes)
    if log and res["conferidos"]:
        log(f"PLACES: {res['conferidos']} pontos CASA do Google com outra "
            "rua ou outro bairro (voltam para conferir)")

    def manual(g):
        return bool(g) and (
            str(g.get("origem") or "").upper() == ORIGEM_MANUAL or (
                bool(g.get("fonte")) and str(g.get("origem") or "").upper()
                not in (ORIGEM_GOOGLE, ORIGEM_TOMTOM)))
    fila, vistos = [], set()
    for c in clientes:
        k = c.get("CHAVE_CLIENTE")
        g = dados.get(k)
        nome = _norm(c.get("NOME_FANTASIA")) or _norm(c.get("NOME_CLIENTE"))
        if k in vistos or not nome or not _norm(c.get("CIDADE")) or \
                manual(g) or (g and g.get("places_em")):
            continue
        if g and ponto(g)[0] is not None and \
                str(g.get("precisao") or "").lower() == "endereco" and \
                not g.get("alerta"):
            continue                    # ja esta na casa
        vistos.add(k)
        fila.append(c)
    fila.sort(key=lambda c: _ordem_google(c, dados.get(c["CHAVE_CLIENTE"])))
    res["fila"] = len(fila)
    periodo = date.today().strftime("%Y-%m")
    dia = date.today().isoformat()
    usados_dia = _uso_api(arq.parent, PLACES_USO, dia)
    teto = min(PLACES_LIMITE_MES - _uso_api(arq.parent, PLACES_USO, periodo),
               PLACES_LIMITE_DIA - usados_dia)
    res["uso_dia"] = usados_dia
    if limite is not None:
        teto = min(teto, limite)
    ate = max(0, min(teto, len(fila)))
    if log:
        log(f"PLACES: {len(fila)} clientes fora da casa para procurar a "
            f"empresa (ate {ate} nesta rodada; hoje ja foram {usados_dia} "
            f"de {PLACES_LIMITE_DIA} por dia). "
            + ("Consultando..." if ate else "Limite do dia: o resto vai "
               "na proxima rodada (amanha)."))
    consultar = consultar or (lambda t, cen: _consultar_places(t, chave,
                                                                cen))

    def _um(c_):
        cen = geo.coordenada(_norm(c_.get("UF")), _norm(c_.get("CIDADE")))
        bairro = _norm(c_.get("BAIRRO"))
        txt = ", ".join(x for x in (
            _norm(c_.get("NOME_FANTASIA")) or _norm(c_.get("NOME_CLIENTE")),
            bairro if bairro not in ("", "SEM BAIRRO", "(SEM BAIRRO)")
            else "", f"{_norm(c_.get('CIDADE'))} - {_norm(c_.get('UF'))}")
            if x)
        for espera in (2, 5, 10, None):
            try:
                return consultar(txt, cen), None
            except Exception as e:                      # noqa: BLE001
                t_ = str(e).upper()
                if espera is None or any(x in t_ for x in (
                        "DENIED", "LIMIT", "INVALID", "EXHAUSTED", "403",
                        "401", "NOT_FOUND", "UNAUTHENTICATED")):
                    return None, e
                if log:
                    log(f"PLACES: rede caiu ({str(e)[:60]}); tento de "
                        f"novo em {espera} s...")
                time.sleep(espera)
        return None, None
    feitos = achados = somados = 0
    hoje = date.today().isoformat()
    inicio = time.time()
    try:
        with ThreadPoolExecutor(max_workers=PLACES_DE_VEZ) as ex:
            for i in range(0, ate, PLACES_DE_VEZ * 2):
                if i and parar and parar():
                    break
                bloco = fila[i:min(ate, i + PLACES_DE_VEZ * 2)]
                parou = False
                for c, (lugares, erro) in zip(bloco, ex.map(_um, bloco)):
                    if erro is not None:
                        res["erro"] = str(erro).replace(chave or "\0",
                                                        "***")[:400]
                        parou = True
                        break
                    feitos += 1
                    k = c["CHAVE_CLIENTE"]
                    lg = lugar_que_vale(c, lugares)
                    ant = dados.get(k) or {}
                    if lg:
                        novo = {"end": endereco_do_cliente(c),
                                "LATITUDE": texto_coordenada(lg["lat"]),
                                "LONGITUDE": texto_coordenada(lg["lon"]),
                                "precisao": "endereco", "em": hoje,
                                "origem": ORIGEM_GOOGLE,
                                "fonte": (f"Google Places (empresa): "
                                          f"{lg['nome']} - {lg['endereco']}"
                                          )[:250],
                                "regra": REGRA, "places_em": hoje}
                        if ponto(ant)[0] is not None:
                            novo["antes"] = (
                                f"{ant.get('LATITUDE')}, "
                                f"{ant.get('LONGITUDE')} "
                                f"({ant.get('precisao')}"
                                f"{', ' + ant['alerta'] if ant.get('alerta') else ''})")
                        dados[k] = novo
                        achados += 1
                    elif ant:
                        ant["places_em"] = hoje
                    else:
                        dados[k] = {"places_em": hoje}
                    if log and (feitos == 1 or feitos % 10 == 0):
                        falta = (ate - feitos) * (time.time() - inicio) \
                            / feitos / 60
                        log(f"PLACES: {feitos} de {ate} procurados, "
                            f"{achados} empresas achadas "
                            f"(~{falta:.0f} min para acabar)")
                    if feitos % 50 == 0:
                        try:
                            gravar(arq, dados)
                            _uso_api(arq.parent, PLACES_USO, periodo,
                                     feitos - somados)
                            _uso_api(arq.parent, PLACES_USO, dia,
                                     feitos - somados)
                            somados = feitos
                        except OSError as e:
                            if log:
                                log(f"(arquivo ocupado, gravo depois: {e})"
                                    [:120])
                if parou:
                    break
    finally:
        if feitos or res["conferidos"]:
            try:
                gravar(arq, dados)
            except OSError as e:
                reserva = arq.with_name(arq.stem + "_PENDENTE.json")
                gravar(reserva, dados)
                res["erro"] = (f"o {arq.name} estava preso ({e}); o "
                               f"resultado ficou em {reserva.name}")[:400]
        if feitos > somados:
            _uso_api(arq.parent, PLACES_USO, periodo, feitos - somados)
            _uso_api(arq.parent, PLACES_USO, dia, feitos - somados)
        if any(x in str(res.get("erro") or "").upper() for x in (
                "EXHAUSTED", "QUOTA", "429")):
            # cota do dia acabou no Google (ele zera a meia-noite do
            # Pacifico, 4h de Manaus): para sem erro e continua amanha
            res["cota_dia"] = True
    res.update(consultados=feitos, achados=achados,
               uso=_uso_api(arq.parent, PLACES_USO, periodo),
               uso_dia=_uso_api(arq.parent, PLACES_USO, dia),
               faltam=len(fila) - feitos)
    return res


def atualizar_google(raiz_ou_base, clientes=None, limite=None, log=None,
                     consultar=None, chave=None, esperar=time.sleep,
                     parar=None, todos=False) -> dict:
    """(28/10) Consulta na API do Google SO os divergentes (ver acima).
    (02/11, Alexandre: "mude o script para pegar todas as coordenadas
    novamente") todos=True: TODOS os clientes da base com endereco ou CEP,
    menos o ponto posto a mao (MANUAL/link do Google) e quem o Google ja
    consultou (origem GOOGLE ou "google_em": rodou, para, roda de novo e
    continua de onde parou). O ponto do Google entra quando a precisao e
    IGUAL ou melhor que a de antes (no empate, vale o Google).
    Devolve {"divergentes", "consultados", "melhorados", "faltam",
    "erro", "uso_mes"}."""
    return _atualizar_api(PROV_GOOGLE, raiz_ou_base, clientes, limite, log,
                          consultar, chave, esperar, parar, todos=todos)


def _atualizar_api(prov, raiz_ou_base, clientes=None, limite=None,
                   log=None, consultar=None, chave=None, esperar=time.sleep,
                   parar=None, todos=False) -> dict:
    """(29/10) O mesmo caminho para o Google e a TomTom (prov = PROV_*)."""
    import geografia as geo                             # noqa: PLC0415
    arq = caminho(raiz_ou_base)
    raiz = arq.parent.parent if arq.parent.name.upper() == "RELATORIOS" \
        else arq.parent
    res = {"divergentes": 0, "consultados": 0, "melhorados": 0, "faltam": 0,
           "erro": "", "uso_mes": 0, "uso": 0, "arquivo": str(arq)}
    chave = chave if chave is not None else prov["chave"](raiz)
    if not chave and consultar is None:
        res["erro"] = (f"sem a chave da API {prov['nome']}: cole a chave no "
                       f"{prov['configs'](raiz)[0]}")
        res["sem_chave"] = True
        return res
    if clientes is None:
        if log:
            log("Lendo a BASE_CLIENTE...")
        import planner_nucleo as nu                     # noqa: PLC0415
        base = Path(raiz_ou_base)
        if base.suffix.lower() != ".xlsx":
            base = arq.parent / "BASE_CLIENTE.xlsx"
        # (02/11) no PC do Alexandre (Python 3.15) o openpyxl levou mais
        # de 2 min so para ler a BASE_CLIENTE: le pelo xlsx_rapido (o mesmo
        # resultado, direto do XML), como os relatorios ja fazem
        try:
            import xlsx_rapido as _xr                   # noqa: PLC0415
            _lw = nu.load_workbook
            nu.load_workbook = _xr.load_workbook
        except Exception:                               # noqa: BLE001
            _xr = None
        try:
            clientes = nu.ler_base_cliente(base)
        finally:
            if _xr is not None:
                nu.load_workbook = _lw
        cep_de = ceps_da_base(base)
        for c in clientes:
            if not c.get("CEP"):
                c["CEP"] = cep_de.get(c.get("CHAVE_CLIENTE"), "")
    if log:
        log(f"Lendo as coordenadas ({len(clientes)} clientes na base)...")
    dados = ler(arq)
    carregar_ceps(arq.parent)
    marca = f"{prov['origem'].lower()}_em"      # "google_em"
    # (02/11, Alexandre: "ajuste o numero da rua, separando do endereco;
    # onde o endereco esta divergente, use o CEP e numero como base
    # principal") 2o PASSO do modo todos: quem ja passou pelo Google e NAO
    # ficou na casa (rua/bairro) e tem numero de porta vai de novo, agora
    # com a rua e o bairro do CEP + o numero (endereco_pelo_cep); marca
    # "google_cep_em" (nao repete).
    marca2 = f"{prov['origem'].lower()}_cep_em"
    passo2 = set()

    def manual_de_verdade(g):
        return bool(g) and (
            str(g.get("origem") or "").upper() == ORIGEM_MANUAL or (
                bool(g.get("fonte")) and str(g.get("origem") or "").upper()
                not in (ORIGEM_GOOGLE, ORIGEM_TOMTOM)))

    def na_fila(g):
        if todos:                       # (02/11) todos, menos o ja feito
            if manual_de_verdade(g):
                return False
            if not (g and (g.get(marca) or str(g.get("origem") or "")
                           .upper() == prov["origem"])):
                return True             # 1o passo: ainda nao consultado
            if str(g.get("precisao") or "").lower() == "endereco" or \
                    g.get(marca2) or not separar_numero(
                        c.get("ENDERECO"), c.get("NUMERO"))[1]:
                return False
            passo2.add(c.get("CHAVE_CLIENTE"))
            return True                 # 2o passo: CEP + numero
        return divergente(c, g)
    fila = []
    vistos = set()
    for c in clientes:
        k_ = c.get("CHAVE_CLIENTE")
        if k_ in vistos or not ((_norm(c.get("ENDERECO"))
                                 or cep8(c.get("CEP")))
                                and _norm(c.get("CIDADE"))):
            continue
        if na_fila(dados.get(k_)):
            vistos.add(k_)
            fila.append(c)
    fila.sort(key=lambda c: _ordem_google(c, dados.get(c["CHAVE_CLIENTE"])))
    res["divergentes"] = len(fila)
    res["pelo_cep"] = len(passo2)
    periodo = date.today().strftime(prov["periodo"])
    usados = _uso_api(arq.parent, prov["uso"], periodo)
    teto = prov["limite"] - usados
    if limite is not None:
        teto = min(teto, limite)
    consultar = consultar or (lambda e: prov["consultar"](e, chave))
    feitos = melhores = 0
    # (02/11, Alexandre: "5 minutos nessa mensagem e nao sai") mostra a
    # fila e o andamento a cada 10 consultas (antes so falava a cada 25
    # MELHORADOS) e consulta de VARIOS_DE_VEZ em paralelo: nesta maquina o
    # Python recusa o certificado e cada consulta vai pelo curl/PowerShell
    # do Windows (lento um por um). O Google aceita 50 por segundo.
    if log:
        log(f"{prov['origem']}: {len(fila)} clientes na fila "
            f"(ate {max(0, min(teto, len(fila)))} nesta rodada"
            + (f"; {len(passo2)} de novo pelo CEP + numero" if passo2
               else "") + "). Consultando...")
    inicio = time.time()

    def _um(c_):
        # (02/11) a rede derrubou a conexao no meio ("WinError 10054 ...
        # cancelamento de uma conexao existente pelo host remoto") e a
        # rodada parou na consulta 142: erro de REDE tenta de novo (3x,
        # esperando 2, 5 e 10 s); erro da CHAVE/COTA para na hora.
        for espera in (2, 5, 10, None):
            try:
                return consultar(
                    endereco_pelo_cep(c_)
                    if c_.get("CHAVE_CLIENTE") in passo2
                    else endereco_google(c_)), None
            except Exception as e:                      # noqa: BLE001
                txt = str(e).upper()
                if espera is None or any(x in txt for x in (
                        "DENIED", "LIMIT", "INVALID", "SEM A CHAVE")):
                    return None, e
                if log:
                    log(f"{prov['origem']}: rede caiu ({str(e)[:60]}); "
                        f"tento de novo em {espera} s...")
                time.sleep(espera)
        return None, None
    ate = max(0, min(teto, len(fila)))
    if parar and parar():
        ate = 0

    def _resultados():
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        n = max(1, int(prov.get("de_vez") or 1))
        with ThreadPoolExecutor(max_workers=n) as ex:
            passo = n * 2 if n > 1 else 1   # TomTom: um por vez
            for i in range(0, ate, passo):
                if i and parar and parar():
                    return
                bloco = fila[i:min(ate, i + passo)]
                for c_, (r_, e_) in zip(bloco, ex.map(_um, bloco)):
                    yield c_, r_, e_
                    if e_ is not None:
                        return
                esperar(prov["intervalo"])
    somados = [0]

    def _somar_uso(n=None):         # (02/11) o uso vai junto de cada gravacao
        n = res.get("_feitos", 0) if n is None else n
        if n > somados[0]:
            _uso_api(arq.parent, prov["uso"], periodo, n - somados[0])
            somados[0] = n

    def _gravar_meio():
        try:
            gravar(arq, dados)
            _somar_uso()
        except OSError as e:    # (02/11) preso: grava na proxima
            if log:
                log(f"(arquivo ocupado, gravo depois: {e})"[:120])
    try:
        feitos, melhores = _rodar_fila(
            _resultados, res, chave, log, inicio, ate, todos, dados, marca,
            marca2, passo2, _gravar_meio, prov, c_geo=geo)
    finally:
        # (02/11) mesmo se algo quebrar no meio, o que ja foi consultado
        # fica gravado e o uso e contado
        feitos, melhores = res.pop("_feitos", feitos), \
            res.pop("_melhores", melhores)
        if melhores or (todos and feitos):
            try:
                gravar(arq, dados)
            except OSError as e:
                # (02/11) ultimo recurso: nada se perde - fica num arquivo
                # ao lado para o BAP Tools juntar; o COORDENADAS como estava
                reserva = arq.with_name(arq.stem + "_PENDENTE.json")
                gravar(reserva, dados)
                res["erro"] = (f"o {arq.name} estava preso ({e}); o "
                               f"resultado ficou em {reserva.name}")[:400]
        _somar_uso(feitos)
    uso = _uso_api(arq.parent, prov["uso"], periodo)
    res.update(consultados=feitos, melhorados=melhores,
               faltam=len(fila) - feitos, uso=uso, uso_mes=uso)
    return res


def _rodar_fila(_resultados, res, chave, log, inicio, ate, todos, dados,
                marca, marca2, passo2, _gravar_meio, prov, c_geo):
    """(02/11) o laco das consultas (era o miolo do _atualizar_api)."""
    geo = c_geo
    feitos = melhores = 0
    for c, r, erro in _resultados():
        res["_feitos"], res["_melhores"] = feitos, melhores
        if erro is not None:
            res["erro"] = str(erro).replace(chave or "\0", "***")[:400]
            break                       # chave/cota/rede: para a rodada
        feitos += 1
        if log and (feitos == 1 or feitos % 10 == 0):
            seg = time.time() - inicio
            falta = (ate - feitos) * seg / feitos / 60
            via = {"python": "Python", "windows": "curl do Windows",
                   "powershell": "PowerShell"}.get(_TRANSPORTE["modo"], "")
            log(f"{prov['origem']}: {feitos} de {ate} consultados, "
                f"{melhores} melhorados, via {via} "
                f"(~{falta:.0f} min para acabar)")
        pelo_cep = c.get("CHAVE_CLIENTE") in passo2
        if todos:                       # consultado: nao volta para a fila
            g_ = dados.get(c["CHAVE_CLIENTE"])
            if g_ is not None:
                g_[marca2 if pelo_cep else marca] = date.today().isoformat()
            res["_feitos"] = feitos
            if feitos % 50 == 0:
                _gravar_meio()
        if not r:
            continue
        p = (r["lat"], r["lon"])
        centro = geo.coordenada(_norm(c.get("UF")), _norm(c.get("CIDADE")))
        if centro and geo.distancia_km(centro, p) > RAIO_MAX_KM:
            continue
        tipo = str(r.get("tipo") or "").upper()
        prec = prov["precisao"](tipo)
        if not prec:
            continue                    # ponto da cidade: nao serve
        _rua, _num = separar_numero(c.get("ENDERECO"), c.get("NUMERO"))
        _d = re.match(r"\d+", re.sub(r"^\D+", "", str(_num or "")))
        _dg = re.match(r"\d+", re.sub(r"^\D+", "", str(r.get("numero") or "")))
        mesmo_numero = bool(_d and _dg and _d.group(0).lstrip("0")
                            == _dg.group(0).lstrip("0"))
        if r.get("parcial") and prec == "endereco" and not (
                mesmo_numero and (not r.get("cidade") or mesma_cidade(
                    r["cidade"], c.get("CIDADE")))):
            prec = "rua"                # achou so parte: fica para conferir
        # (02/11) parcial com o MESMO numero na MESMA cidade = a casa
        if r.get("cidade") and prec == "endereco" and \
                not mesma_cidade(r["cidade"], c.get("CIDADE")):
            prec = "rua"                # caiu na cidade vizinha: conferir
        if r.get("numero") and prec == "endereco" and _d and _dg and \
                not mesmo_numero:
            prec = "rua"                # achou OUTRA casa: conferir
        # (02/11) a rua e o bairro que o Google achou batem com a base?
        alerta = conferir_rua_bairro(c, p, r.get("rua"), r.get("bairro")) \
            if prec in ("endereco", "rua") else ""
        if alerta:
            prec = "rua"                # outra rua / outro bairro: conferir
        ant = dados.get(c["CHAVE_CLIENTE"]) or {}
        rank = {"endereco": 3, "cep": 2, "rua": 1, "bairro": 0}
        r_ant = rank.get(str(ant.get("precisao") or "").lower(), 0)
        if ponto(ant)[0] is not None and not ant.get("alerta") and (
                alerta or (rank.get(prec, 0) < r_ant if todos
                           else rank.get(prec, 0) <= r_ant)):
            continue                    # a API nao melhorou
        novo = {"end": endereco_do_cliente(c),
                "LATITUDE": texto_coordenada(p[0]),
                "LONGITUDE": texto_coordenada(p[1]),
                "precisao": prec, "em": date.today().isoformat(),
                "origem": prov["origem"],
                "fonte": f"{prov['fonte']}"
                         f"{' pelo CEP + numero' if pelo_cep else ''}"
                         f" ({tipo or '?'}"
                         f"{', parcial' if r.get('parcial') else ''}): "
                         f"{r.get('endereco', '')}"[:250],
                "regra": REGRA}
        if ponto(ant)[0] is not None:
            novo["antes"] = (f"{ant.get('LATITUDE')}, {ant.get('LONGITUDE')}"
                             f" ({ant.get('precisao')})")
        if pelo_cep:
            novo[marca2] = date.today().isoformat()
        if alerta:
            novo["alerta"] = alerta
        dados[c["CHAVE_CLIENTE"]] = novo
        melhores += 1
        res["_melhores"] = melhores
        if not todos and melhores % 50 == 0:
            _gravar_meio()
    res["_feitos"], res["_melhores"] = feitos, melhores
    return feitos, melhores


# =========================================================================
# (29/10, Alexandre: "nao consigo ter a API do Google") TOMTOM SEARCH API
# Mesmo caminho do Google (so os divergentes, a mesma ordem, a mesma
# checagem de 60 km, ponto protegido depois): geocode/{endereco}.json com
# countrySet=BR. "Point Address" = "endereco" (a casa); "Address Range" =
# "endereco" (interpolado no quarteirao); "Street"/"Cross Street" = "rua";
# "Geography" de bairro = "bairro"; ponto da cidade/estado = nao serve.
# Achou o endereco em OUTRA cidade (vizinha) = "rua" (para conferir).
# Confianca (matchConfidence) abaixo de TOMTOM_CONFIANCA = parcial.
# CHAVE do Alexandre (developer.tomtom.com, plano gratis): fica em
# tomtom_config.json na pasta do BAP (Regionais - Leandro, ao lado do .bat;
# 29/10, pedido do Alexandre) - {"api_key": "..."}; o .bat cria o arquivo e
# abre no Bloco de Notas. Ou a variavel TOMTOM_API_KEY. NUNCA no codigo,
# nunca impressa.
# Teto por MES em TOMTOM_LIMITE_MES (conta em RELATORIOS\TOMTOM_USO.json)
# [SUPOSICAO: 19.000, abaixo das 20.000 gratis por mes do painel; conferir
# da TomTom]. Os termos da TomTom sobre guardar o resultado: conferir
# [SUPOSICAO]. Roda pelo atualizar_coordenadas_tomtom.bat (--tomtom).
# =========================================================================
TOMTOM_URL = "https://api.tomtom.com/search/2/geocode"     # chave antiga
# (29/10) a chave nova do portal (produto "Geocoding API", Orbis Maps) da
# 401 no endereco antigo: vai no Orbis v2, chave no cabecalho
TOMTOM_URL_ORBIS = "https://api.tomtom.com/maps/orbis/places/geocode"
_TOMTOM_API = {"qual": ""}      # "orbis" ou "antiga", a que respondeu
TOMTOM_CONFIG = "tomtom_config.json"
TOMTOM_USO = "TOMTOM_USO.json"
# (29/10) o painel da conta mostra o Geocoding gratis por MES (20.000);
# teto 19.000 por mes, com folga [SUPOSICAO: conferir no painel]
TOMTOM_LIMITE_MES = 19000
TOMTOM_LIMITE_DIA = TOMTOM_LIMITE_MES   # nome antigo
TOMTOM_INTERVALO = 0.25         # gratis: ate 5 por segundo [SUPOSICAO]
TOMTOM_CONFIANCA = 0.6
ORIGEM_TOMTOM = "TOMTOM"


# (29/10) Na maquina do Alexandre o Python recusou o certificado da
# api.tomtom.com ("self-signed certificate in certificate chain"), mas o
# navegador abre (o Windows confia na cadeia: inspecao de SSL da rede ou do
# antivirus). Entao: tenta o urllib; se o erro for de CERTIFICADO, passa a
# usar o proprio Windows (curl.exe do Windows, que usa o Schannel e a lista
# de certificados do Windows; sem curl, o PowerShell) - a verificacao do
# certificado continua ligada, so muda quem verifica. A URL (com a chave)
# vai pela entrada padrao/variavel de ambiente, nunca na linha de comando.
_TRANSPORTE = {"modo": "python"}


def _json_ou_none(b):
    try:
        return json.loads(b.decode("utf-8") if isinstance(b, bytes) else b)
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def _http_json(url, timeout=20, cabecalhos=None, corpo=None):
    """(codigo HTTP, json ou None). Erro de rede sobe. (29/10) cabecalhos:
    a chave da TomTom nova vai no cabecalho TomTom-Api-Key. (02/11) corpo:
    texto JSON -> POST (a Places API nova so aceita POST)."""
    cab = {"User-Agent": AGENTE, **(cabecalhos or {})}
    import ssl                                          # noqa: PLC0415
    import urllib.error                                 # noqa: PLC0415
    import urllib.request                               # noqa: PLC0415
    if _TRANSPORTE["modo"] == "python":
        try:
            req = urllib.request.Request(
                url, headers=cab, method="POST" if corpo else "GET",
                data=corpo.encode("utf-8") if corpo else None)
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                return getattr(r, "status", 200) or 200, _json_ou_none(
                    r.read())
        except urllib.error.HTTPError as e:
            try:
                corpo = e.read()
            except Exception:                           # noqa: BLE001
                corpo = b""
            return e.code, _json_ou_none(corpo)
        except urllib.error.URLError as e:
            if not isinstance(getattr(e, "reason", None), ssl.SSLError):
                raise
            _TRANSPORTE["modo"] = "windows"     # certificado: o Windows
    return _http_json_windows(url, timeout, cab, corpo)


def _http_json_windows(url, timeout=20, cab=None, corpo=None):
    import os                                           # noqa: PLC0415
    import subprocess                                   # noqa: PLC0415
    sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    curl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / \
        "System32" / "curl.exe"
    p = None
    arq_corpo = None
    if corpo:                   # (02/11) POST: o corpo vai num arquivo
        import tempfile                                 # noqa: PLC0415
        fd, arq_corpo = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f_:
            f_.write(corpo)
    if _TRANSPORTE["modo"] == "windows" and curl.exists():
        cfg = f'url = "{url}"\n' + "".join(
            f'header = "{k}: {v}"\n' for k, v in (cab or {}).items())
        if arq_corpo:
            cfg += ('data-binary = "@' + arq_corpo.replace("\\", "/")
                    + '"\n')
        p = subprocess.run(
            [str(curl), "-s", "-S", "--ssl-revoke-best-effort",
             "--max-time", str(timeout), "-w", "\n%{http_code}", "-K", "-"],
            input=cfg.encode("utf-8"), capture_output=True,
            timeout=timeout + 15, creationflags=sem_janela, check=False)
        if p.returncode in (2, 4, 35, 53, 58, 60, 77, 83):
            # curl antigo (sem --ssl-revoke-best-effort) ou recusa do
            # certificado/revogacao no Schannel: fica com o PowerShell
            _TRANSPORTE["modo"] = "powershell"
            p = None
        elif p.returncode != 0:
            raise RuntimeError(
                f"curl {p.returncode}: "
                f"{p.stderr.decode('utf-8', 'replace').strip()[:150]}")
    if p is None:
        ps = ("$ProgressPreference='SilentlyContinue';"
              "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "$h=@{};(ConvertFrom-Json $env:BAP_CAB).psobject.properties|"
              "%{$h[$_.Name]=$_.Value};"
              "$p=@{Uri=$env:BAP_URL;UseBasicParsing=$true;Headers=$h;"
              f"TimeoutSec={timeout}}};"
              "if($env:BAP_CORPO){$h.Remove('Content-Type');"
              "$p.Method='POST';$p.ContentType='application/json; "
              "charset=utf-8';$p.Body=[IO.File]::ReadAllBytes("
              "$env:BAP_CORPO)};"
              "try{$r=Invoke-WebRequest @p;[Console]::Out.Write($r.Content);"
              "[Console]::Out.Write(\"`n\"+[int]$r.StatusCode)}catch{"
              "$x=$_.Exception.Response;if($x){$c=[int]$x.StatusCode;"
              "$t=(New-Object IO.StreamReader($x.GetResponseStream()))"
              ".ReadToEnd();[Console]::Out.Write($t);"
              "[Console]::Out.Write(\"`n\"+$c)}else{"
              "[Console]::Error.Write($_.Exception.Message);exit 1}}")
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            env=dict(os.environ, BAP_URL=url, BAP_CORPO=arq_corpo or "",
                     BAP_CAB=json.dumps(
                         {k: v for k, v in (cab or {}).items()
                          if k.lower() != "user-agent"})),
            capture_output=True,
            timeout=timeout + 30, creationflags=sem_janela, check=False)
        if p.returncode != 0:
            raise RuntimeError(
                "PowerShell: "
                f"{p.stderr.decode('utf-8', 'replace').strip()[:150]}")
    if arq_corpo:
        try:
            os.remove(arq_corpo)
        except OSError:
            pass
    saida = p.stdout.decode("utf-8", "replace")
    corpo, _, codigo = saida.rpartition("\n")
    try:
        return int(codigo.strip()), _json_ou_none(corpo)
    except ValueError:
        return 0, _json_ou_none(saida)


def _configs(raiz, nome) -> list:
    """(29/10, Alexandre: "tudo tem que ficar em Regionais - Leandro") a
    chave fica SO na pasta do BAP (tomtom_config.json ao lado do .bat)."""
    return [Path(raiz) / nome]


def configs_tomtom(raiz) -> list:
    return _configs(raiz, TOMTOM_CONFIG)


# (29/10) a TomTom deu 401 "missing valid authentication credentials" nas
# duas APIs: a chave lida pode ter vindo errada do Bloco de Notas (aspas,
# espaco, o COLE_A_CHAVE_AQUI junto, JSON quebrado). Agora a leitura limpa
# o texto e o erro mostra a chave MASCARADA (4 primeiros...4 ultimos, como
# o painel da TomTom mostra) e de onde veio, para conferir.
_CHAVE_LIDA = {"mascara": "", "tamanho": 0, "de": ""}


def _limpar_chave(texto) -> str:
    t = str(texto or "")
    try:
        j = json.loads(t)
        if isinstance(j, dict):
            t = str(j.get("api_key") or j.get("key") or "")
        elif isinstance(j, str):
            t = j
    except ValueError:
        pass                            # JSON quebrado: procura no texto
    t = t.replace(GOOGLE_SEM_CHAVE, "")
    achadas = re.findall(r"[A-Za-z0-9_\-]{20,}", t)
    return achadas[0] if achadas else ""


def _mascara(k) -> str:
    return f"{k[:4]}...{k[-4:]}" if len(k) >= 8 else "?" * len(k)


def chave_tomtom(raiz) -> str:
    import os                                           # noqa: PLC0415
    for arq in configs_tomtom(raiz):
        try:
            k = _limpar_chave(arq.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            continue
        if k:
            _CHAVE_LIDA.update(mascara=_mascara(k), tamanho=len(k),
                               de=str(arq))
            return k
    k = _limpar_chave(os.environ.get("TOMTOM_API_KEY") or "")
    if k:
        _CHAVE_LIDA.update(mascara=_mascara(k), tamanho=len(k),
                           de="variavel TOMTOM_API_KEY")
    return k


_CIDADE_OU_MAIS = ("COUNTRY", "COUNTRYSUBDIVISION",
                   "COUNTRYSECONDARYSUBDIVISION", "COUNTRYTERTIARYSUBDIVISION",
                   "MUNICIPALITY", "POSTALCODEAREA")


def _erro_tomtom(codigo, j) -> str:
    det = (j or {}).get("detailedError") or (j or {}).get("error") or {}
    msg = det.get("message") if isinstance(det, dict) else str(det)
    return (f"TomTom: HTTP {codigo}"
            + (f" - {msg}" if msg else "")
            + (" (chave sem permissao para o Geocoding ou invalida)"
               if codigo in (401, 403) else "")
            + (f" | chave lida: {_CHAVE_LIDA['mascara']} "
               f"({_CHAVE_LIDA['tamanho']} caracteres) de {_CHAVE_LIDA['de']}"
               if codigo in (401, 403) and _CHAVE_LIDA["mascara"] else ""))[:400]


def _pedir_tomtom(qual, endereco, chave, esperar):
    """(codigo, json) de uma das duas APIs, com 429 = espera e repete."""
    import urllib.parse                                 # noqa: PLC0415
    if qual == "orbis":
        url = (f"{TOMTOM_URL_ORBIS}?" + urllib.parse.urlencode(
            {"query": endereco, "maxResults": 1, "countryCodesIso2": "BR"}))
        cab = {"TomTom-Api-Key": chave, "TomTom-Api-Version": "2",
               "Attributes": "results",     # obrigatorio na doc da TomTom
               "Accept-Language": "pt-BR"}
    else:
        url = (f"{TOMTOM_URL}/{urllib.parse.quote(endereco, safe='')}.json?"
               + urllib.parse.urlencode({"key": chave, "countrySet": "BR",
                                         "limit": 1, "language": "pt-BR"}))
        cab = None
    for tentativa in range(3):
        codigo, j = _http_json(url, cabecalhos=cab)
        if codigo == 429 and tentativa < 2:
            esperar(2 * (tentativa + 1))        # muitas por segundo
            continue
        return codigo, j
    return codigo, j


def _ler_orbis(r):
    pos = (r.get("position") or {}).get("coordinates") or []
    if len(pos) < 2:
        return None
    adr = r.get("address") or {}
    tipo = str(r.get("type") or "").lower()
    if tipo == "address":
        tipo = "Point Address" if adr.get("houseNumber") else "Street"
    elif tipo in ("street", "intersection"):
        tipo = "Street"
    elif tipo == "area":
        at = str(r.get("areaType") or "").upper()
        tipo = ("BAIRRO" if "MUNICIPALITYSUBDIVISION" in at
                or "MUNICIPALITYSECONDARYSUBDIVISION" in at
                or "NEIGHBO" in at else "CIDADE")
    return {"lat": float(pos[1]), "lon": float(pos[0]), "tipo": tipo,
            "parcial": False, "endereco": r.get("title", ""),
            "cidade": adr.get("municipality", ""),
            "bairro": adr.get("municipalitySubdivision")
            or adr.get("neighborhood", ""),
            "numero": str(adr.get("houseNumber") or "")}


def _ler_antiga(r):
    tipo = str(r.get("type") or "")
    if tipo == "Geography":
        ent = str(r.get("entityType") or "").upper()
        tipo = "CIDADE" if ent in _CIDADE_OU_MAIS else "BAIRRO"
    adr = r.get("address") or {}
    pos = r.get("position") or {}
    if pos.get("lat") is None:
        return None
    score = (r.get("matchConfidence") or {}).get("score")
    return {"lat": float(pos["lat"]), "lon": float(pos["lon"]),
            "tipo": tipo,
            "parcial": score is not None and float(score) < TOMTOM_CONFIANCA,
            "endereco": adr.get("freeformAddress", ""),
            "cidade": adr.get("municipality", ""),
            "bairro": adr.get("municipalitySubdivision", ""),
            "numero": str(adr.get("streetNumber") or "")}


def _consultar_tomtom(endereco, chave, esperar=time.sleep):
    """A resposta da TomTom: {"lat", "lon", "tipo", "parcial", "endereco",
    "cidade", "bairro", "numero"} ou None. Chave/cota/rede: sobe (para a
    rodada). (29/10) Tenta a API nova (Orbis v2, chave no cabecalho) e, se
    a chave nao servir nela (401/403), a antiga (search/2); a que
    responder fica para o resto da rodada."""
    ordem = ([_TOMTOM_API["qual"]] if _TOMTOM_API["qual"]
             else ["orbis", "antiga"])
    codigo, j = 0, None
    for qual in ordem:
        codigo, j = _pedir_tomtom(qual, endereco, chave, esperar)
        if codigo in (401, 403) and not _TOMTOM_API["qual"]:
            continue                    # tenta a outra API
        if codigo == 200:
            _TOMTOM_API["qual"] = qual
        break
    if codigo in (400, 404):
        return None                     # so este endereco; segue a fila
    if codigo != 200:
        raise RuntimeError(_erro_tomtom(codigo, j))
    res = (j or {}).get("results") or []
    if not res:
        return None
    return (_ler_orbis if _TOMTOM_API["qual"] == "orbis"
            else _ler_antiga)(res[0])


def _precisao_tomtom(tipo) -> str:
    return {"POINT ADDRESS": "endereco", "ADDRESS RANGE": "endereco",
            "STREET": "rua", "CROSS STREET": "rua", "POI": "rua",
            "BAIRRO": "bairro"}.get(tipo.upper(), "")


def _precisao_google(tipo) -> str:
    return ("endereco" if tipo in ("ROOFTOP", "RANGE_INTERPOLATED")
            else "rua" if tipo == "GEOMETRIC_CENTER" else "bairro")


PROV_GOOGLE = {"nome": "do Google", "chave": chave_google,
               "configs": configs_google, "consultar": _consultar_google,
               "uso": GOOGLE_USO, "periodo": "%Y-%m",
               "limite": GOOGLE_LIMITE_MES, "intervalo": GOOGLE_INTERVALO,
               "precisao": _precisao_google, "origem": ORIGEM_GOOGLE,
               "fonte": "Google Geocoding API", "de_vez": GOOGLE_DE_VEZ}
PROV_TOMTOM = {"nome": "da TomTom", "chave": chave_tomtom,
               "configs": configs_tomtom, "consultar": _consultar_tomtom,
               "uso": TOMTOM_USO, "periodo": "%Y-%m",
               "limite": TOMTOM_LIMITE_MES, "intervalo": TOMTOM_INTERVALO,
               "precisao": _precisao_tomtom, "origem": ORIGEM_TOMTOM,
               "fonte": "TomTom Search API"}


def atualizar_tomtom(raiz_ou_base, clientes=None, limite=None, log=None,
                     consultar=None, chave=None, esperar=time.sleep,
                     parar=None) -> dict:
    """(29/10) Os divergentes pela TomTom (ver acima). Devolve o mesmo que
    o atualizar_google; "uso" = consultas gastas hoje."""
    return _atualizar_api(PROV_TOMTOM, raiz_ou_base, clientes, limite, log,
                          consultar, chave, esperar, parar)


if __name__ == "__main__":                              # atualizar_coordenadas.bat
    import sys
    raiz = Path(__file__).resolve().parent
    sys.path.insert(0, str(raiz))
    # (02/11) se travar, de 2 em 2 minutos grava ONDE esta parado em
    # SISTEMA BAP\logs\coordenadas_travado.txt (para o BAP Tools ver)
    try:
        import faulthandler
        _pasta_log = raiz / "SISTEMA BAP" / "logs"
        _pasta_log.mkdir(parents=True, exist_ok=True)
        _arq_trav = open(_pasta_log / "coordenadas_travado.txt", "w",
                         encoding="utf-8")
        faulthandler.dump_traceback_later(120, repeat=True, file=_arq_trav)
    except Exception:                                   # noqa: BLE001
        pass
    if "--google" in sys.argv:          # atualizar_coordenadas_google.bat
        _todos = "--todos" in sys.argv  # (02/11) todos os clientes
        print("Coordenadas pela API do Google - "
              + ("TODOS os clientes (menos os pontos postos a mao)..."
                 if _todos else "so os divergentes..."))
        r = atualizar_google(raiz, log=print, todos=_todos)
        print(f"Pronto: {r['divergentes']} na fila, {r['consultados']} "
              f"consultados, {r['melhorados']} melhorados, {r['faltam']} "
              f"faltam. Uso no mes: {r['uso_mes']} de {GOOGLE_LIMITE_MES}."
              + (f" Erro: {r['erro']}" if r["erro"] else ""))
        if r.get("sem_chave"):
            sys.exit(2)
        if _todos and "--sem-places" not in sys.argv:
            # (02/11) depois do Geocoding: a EMPRESA pela Places API para
            # quem ficou fora da casa
            print()
            print("Empresas pela Places API (quem ficou na rua/bairro ou "
                  "com outra rua/outro bairro)...")
            rp = atualizar_places(raiz, log=print)
            print(f"Pronto: {rp['fila']} na fila, {rp['consultados']} "
                  f"procurados, {rp['achados']} empresas achadas no Google "
                  f"Maps, {rp.get('faltam', 0)} faltam. Uso da Places: hoje "
                  f"{rp.get('uso_dia', 0)} de {PLACES_LIMITE_DIA}, no mes "
                  f"{rp['uso']} de {PLACES_LIMITE_MES}."
                  + ("" if not rp["erro"] or rp.get("cota_dia") else
                     f" Erro: {rp['erro']}"))
            if rp.get("cota_dia") or (rp.get("faltam") and
                                      rp.get("uso_dia", 0)
                                      >= PLACES_LIMITE_DIA):
                print("  -> Acabou a cota do DIA da Places. Rode de novo "
                      "amanha: continua de onde parou.")
            if rp["erro"] and any(x in rp["erro"].upper() for x in (
                    "PERMISSION", "DENIED", "403", "NOT BEEN USED",
                    "DISABLED")):
                print("  -> Ative a \"Places API (New)\" no Google Cloud, "
                      "no mesmo projeto da chave, e rode de novo.")
        sys.exit(0)
    if "--tomtom" in sys.argv:          # atualizar_coordenadas_tomtom.bat
        print("Coordenadas pela TomTom - so os divergentes...")
        r = atualizar_tomtom(raiz, log=print)
        print(f"Pronto: {r['divergentes']} divergentes, {r['consultados']} "
              f"consultados, {r['melhorados']} melhorados, {r['faltam']} "
              f"faltam. Uso no mes: {r['uso']} de {TOMTOM_LIMITE_MES}"
              + (f" (API {_TOMTOM_API['qual']})" if _TOMTOM_API["qual"]
                 else "") + "."
              + (f" Erro: {r['erro']}" if r["erro"] else ""))
        sys.exit(2 if r.get("sem_chave") else 0)
    print("Atualizando as coordenadas dos clientes (1 por segundo)...")
    r = atualizar(raiz, log=print)
    print(f"Pronto: {r['consultados']} consultados, {r['achados']} "
          f"localizados, {r['faltam']} pendentes."
          + (f" Erro: {r['erro']}" if r["erro"] else ""))
