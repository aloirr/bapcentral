"""T-0035, ponta a ponta: robô (antigo/novo) x web (antiga/nova) em uvicorn local,
com o pacote montado das bases congeladas (ponta_a_ponta_T0035_gera.py). Nada de valor de célula
ou nome no stdout: só contagens, status, tamanhos e os cartões (agregados).

Fora do pytest (docs/testes/T-0035.md). Uso: python tests/ponta_a_ponta_T0035.py <rotulo> <raiz_robo> <dir_web> <pacote.json> <saida.json> [--herda]
"""
import copy
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROT, RAIZ, WEBDIR, PAC, SAIDA = sys.argv[1:6]
HERDA = "--herda" in sys.argv
MANAUS = ZoneInfo("America/Manaus")
TOKEN = "t" * 43
ADMIN, SENHA0, SENHA1 = "admteste", "Senha-de-teste-1234", "Senha-nova-forte-5678"
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

sys.path.insert(0, RAIZ)
import requests  # noqa: E402
import bap_automation as ba  # noqa: E402

res = {"rotulo": ROT, "erros": []}


def falha(msg):
    res["erros"].append(msg)
    print("  FALHA:", msg)


def ok(cond, msg):
    if not cond:
        falha(msg)
    return cond


# ------------------------------------------------------------------ web em uvicorn
s = socket.socket()
s.bind(("127.0.0.1", 0))
porta = s.getsockname()[1]
s.close()
dados = Path(tempfile.mkdtemp(prefix="bapweb_"))
env = dict(os.environ, SESSION_SECRET="s" * 40, BAP_WEB_TOKEN=TOKEN, BAP_ADMIN_USUARIO=ADMIN,
           BAP_ADMIN_SENHA_INICIAL=SENHA0, BAP_WEB_DADOS=str(dados), TZ="America/Manaus",
           BAP_WEB_COOKIE_SEGURO="0", BAP_WEB_PACOTE_MAX_MB="25")
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:criar_app", "--factory",
                         "--app-dir", WEBDIR, "--host", "127.0.0.1", "--port", str(porta),
                         "--log-level", "warning"], env=env, cwd=WEBDIR,
                        stdout=subprocess.DEVNULL, stderr=open(SAIDA + ".web.log", "w"))
base = f"http://127.0.0.1:{porta}"
for _ in range(100):
    try:
        if requests.get(base + "/saude", timeout=2).status_code == 200:
            break
    except Exception:
        time.sleep(0.2)
ba._base_web = lambda u: base


def proc_mem():
    st = Path(f"/proc/{proc.pid}/status").read_text()
    g = lambda k: round(int(re.search(rf"{k}:\s+(\d+)", st).group(1)) / 1024, 1)  # noqa: E731
    return {"VmRSS_mb": g("VmRSS"), "VmHWM_mb": g("VmHWM")}


def saude():
    return requests.get(base + "/saude", timeout=10).json()


res["saude_inicio"] = saude()
res["mem_inicio"] = proc_mem()

# ------------------------------------------------------------------ envio
pac0 = json.loads(Path(PAC).read_text(encoding="utf-8"))


def com_data(p, quando):
    p = copy.deepcopy(p)
    p["gerado_em"] = quando.isoformat(timespec="seconds")
    return p


def enviar(p):
    msgs = []
    t0 = time.time()
    if hasattr(ba, "enviar_pacote"):
        r = ba.enviar_pacote(p, url="https://x.exemplo", token=TOKEN, log=msgs.append)
    else:
        r = ba.enviar_pacote_web(p, url="https://x.exemplo", token=TOKEN, log=msgs.append)
    return r, msgs, round(time.time() - t0, 1)


agora = datetime.now(MANAUS).replace(microsecond=0)
inicio = agora - timedelta(hours=26) + timedelta(seconds=240) if HERDA else agora
pac = com_data(pac0, inicio)
r, msgs, seg = enviar(pac)
res["envio1"] = {"ok": r, "seg": seg, "log": msgs}
ok(r is True, "envio 1 não aceito")
rotas_web = {"saude": saude()}
res["saude_pos_envio"] = rotas_web["saude"]
res["mem_pos_envio"] = proc_mem()
res["disco"] = sorted(str(x.relative_to(dados)) for x in dados.rglob("*") if x.is_file()
                      and "pacotes" in x.parts)

# ------------------------------------------------------------------ telas
S = requests.Session()


def csrf(url):
    m = re.search(r'name="csrf" value="([^"]+)"', S.get(base + url).text)
    return m.group(1) if m else ""


S.post(base + "/login", data={"usuario": ADMIN, "senha": SENHA0, "csrf": csrf("/login")})
S.post(base + "/senha", data={"atual": SENHA0, "nova": SENHA1, "confirma": SENHA1, "csrf": csrf("/senha")})

RE_CART = [re.compile(p, re.S) for p in (
    r'class="bc3-k[^"]*"><small>(.*?)</small><b>(.*?)</b>',
    r'class="kpi-valor">(.*?)</div>',
    r'class="pl-v">(.*?)(?:<small>|</div>)',
    r'class="rc-valor">(.*?)</div>')]


def cartoes(html):
    out = []
    for rx in RE_CART:
        for m in rx.findall(html):
            out.append(" | ".join(m) if isinstance(m, tuple) else m)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in out]


def url_de(rid):
    return "/painel" if rid == "vc_painel" else f"/farol/{rid}"


RIDS = [r for r in pac0["relatorios"] if not r.endswith("_uf")]
home = S.get(base + "/")
res["home_links"] = sorted(set(re.findall(r'href="(/farol/[a-z_]+|/painel)"', home.text)))
paginas = {}
for rid in RIDS:
    pg = S.get(base + url_de(rid))
    cs = cartoes(pg.text)
    selo = "Desatualizado" in pg.text
    paginas[rid] = {"status": pg.status_code, "bytes": len(pg.content), "n_cartoes": len(cs),
                    "cartoes": cs, "selo": selo,
                    "dados_de": (re.search(r"Dados de ([^<(]+)", pg.text) or [None, None])[1]}
    ok(pg.status_code == 200, f"{rid}: página {pg.status_code}")
    ok(len(cs) > 0, f"{rid}: sem cartões na página")
    ok(not selo, f"{rid}: selo Desatualizado num farol do dia")
    # valor x regra: todo cartão da tela existe no farol do pacote (o número não nasce na web)
    txt = json.dumps(pac0["relatorios"][rid], ensure_ascii=False)
    fora = [c for c in cs if c.split(" | ")[-1] and c.split(" | ")[-1].replace("&amp;", "&") not in txt]
    paginas[rid]["fora_do_pacote"] = len(fora)
    ok(not fora, f"{rid}: {len(fora)} cartões da tela fora do pacote")
    # abas de tabela: cada aba abre
    abas = sorted(set(re.findall(rf'href="/farol/{rid}\?aba=([a-z0-9_\-]+)', pg.text)))
    st = {}
    for a in abas[:12]:
        st[a] = S.get(base + f"/farol/{rid}?aba={a}").status_code
    paginas[rid]["abas"] = st
    ok(all(v == 200 for v in st.values()), f"{rid}: aba com status {st}")
res["paginas"] = paginas
res["mem_pos_paginas"] = proc_mem()
res["saude_pos_paginas"] = saude()

# parciais e CSV (anexos do disco na web nova)
par = {}
for rid in ("pv_pedidos", "pl_entregas", "vc_visitas"):
    for q in ("acum", "d1", "hoje"):
        x = S.get(base + f"/farol/{rid}/parcial.png?q={q}")
        par[f"{rid}/{q}"] = (x.status_code, x.content[:8] == b"\x89PNG\r\n\x1a\n")
res["parciais"] = par
ok(all(v == (200, True) for v in par.values()), f"parciais: {par}")

# ------------------------------------------------------------------ cobrança (diário e pacote_sha)
cob = S.get(base + "/farol/pl_inadimplencia?aba=cobrar").text
m_sha = re.search(r'data-sha="([0-9a-f]{64})"', cob)
m_cod = re.search(r'data-cod="([^"]+)"', cob)
m_cs = re.search(r'data-csrf="([^"]+)"', cob)
res["cobranca"] = {"tem_fila": bool(m_cod), "tem_sha": bool(m_sha)}
if ok(m_sha and m_cod and m_cs, "cobrança: página sem fila/sha/csrf"):
    rr = S.post(base + "/farol/pl_inadimplencia/cobranca",
                data={"csrf": m_cs.group(1), "cliente": m_cod.group(1), "acao": "PULADO",
                      "pacote_sha": m_sha.group(1), "telefone": ""})
    ok(rr.status_code == 200 and rr.json().get("ok"), f"cobrança: POST {rr.status_code}")
    linhas = [json.loads(x) for a in sorted((dados / "cobranca").glob("COBRANCA_WEB_*.jsonl"))
              for x in a.read_text(encoding="utf-8").splitlines() if x.strip()]
    reg = [x for x in linhas if x.get("acao") == "PULADO"]
    ok(len(reg) == 1, f"cobrança: {len(reg)} registros")
    sha_reg = reg[0]["pacote_sha"] if reg else ""
    lote_dir = sorted(d for d in (dados / "pacotes").iterdir() if (d / "indice.json").is_file()) \
        if (dados / "pacotes").is_dir() else []
    if lote_dir:                                        # web nova: sha do farol no índice
        ind = json.loads((lote_dir[-1] / "indice.json").read_text(encoding="utf-8"))
        esperado = ind["farois"]["pl_inadimplencia"]["sha256"]
        res["cobranca"]["regra"] = "sha do farol pl_inadimplencia no índice"
    else:                                               # web antiga: sha do pacote inteiro
        arq = sorted((dados / "pacotes").glob("*.json"))[-1]
        esperado = hashlib.sha256(arq.read_bytes()).hexdigest()
        res["cobranca"]["regra"] = "sha do pacote inteiro"
    res["cobranca"]["sha_bate"] = sha_reg == esperado == m_sha.group(1)
    ok(res["cobranca"]["sha_bate"], "cobrança: pacote_sha não bate com a regra")
    api = requests.get(base + "/api/cobranca?desde=0", headers={"Authorization": f"Bearer {TOKEN}"})
    ok(api.status_code == 200 and len(api.json().get("linhas", [])) == 1, f"/api/cobranca {api.status_code}")
    res["cobranca"]["api"] = api.status_code

# ------------------------------------------------------------------ edições (fila e marca)
ed = {"api": requests.get(base + "/api/edicoes?desde=0",
                          headers={"Authorization": f"Bearer {TOKEN}"}).status_code}
ok(ed["api"] == 200, f"/api/edicoes {ed['api']}")
ent = S.get(base + "/farol/pl_entregas?aba=entregas").text
links = re.findall(r'class="bt-ed" href="([^"]+)"', ent)
ed["links_editar"] = len(links)
if links:
    form = S.get(base + links[0].replace("&amp;", "&")).text
    campos = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form))
    campos = {k: v.replace("&amp;", "&") for k, v in campos.items()}
    textos = re.findall(r'<input[^>]*name="(c_[a-z_]+)"[^>]*type="text"|<input[^>]*type="text"[^>]*name="(c_[a-z_]+)"', form)
    nomes = [a or b for a, b in textos]
    alvo = "c_responsavel" if "c_responsavel" in nomes else (nomes[0] if nomes else None)
    ed["campo"] = alvo
    if alvo:
        rr = S.post(base + "/farol/pl_entregas/editar", data=dict(campos, **{alvo: "TESTE E2E"}),
                    allow_redirects=False)
        ed["post"] = rr.status_code
        fila = requests.get(base + "/api/edicoes?desde=0", headers={"Authorization": f"Bearer {TOKEN}"}).json()
        regs = fila.get("edicoes") or fila.get("linhas") or []
        ed["fila"] = len(regs)
        if regs:
            e0 = regs[0]
            conf = requests.post(base + "/api/edicoes/confirmar", headers={"Authorization": f"Bearer {TOKEN}"},
                                 json={"epoca": fila.get("epoca"), "resultados": [
                                     {"id": e0.get("id"), "seq": e0.get("seq"), "status": "aplicada"}]})
            ed["confirmar"] = conf.status_code
            time.sleep(1.1)
            ed["marca_apos_aplicada"] = "Aguardando o PC" in S.get(base + "/farol/pl_entregas?aba=entregas").text
res["edicoes"] = ed

# ------------------------------------------------------------------ herança (só robô novo x web nova)
if HERDA:
    h = {}
    # lote 2: o vc_visitas é recusado pela web (422: parcial com chave fora do contrato) -> manter
    p2 = com_data(pac0, datetime.now(MANAUS).replace(microsecond=0))
    p2["relatorios"]["vc_visitas"]["parciais"]["zz"] = p2["relatorios"]["vc_visitas"]["parciais"]["acum"]
    r2, m2, _ = enviar(p2)
    h["envio2"] = {"ok": r2, "log": m2}
    lotes_ = sorted(d for d in (dados / "pacotes").iterdir() if (d / "indice.json").is_file())
    ind2 = json.loads((lotes_[-1] / "indice.json").read_text(encoding="utf-8"))
    e = ind2["farois"].get("vc_visitas") or {}
    h["herdado_de"] = e.get("herdado_de")
    h["herdado_gerado_em_lote1"] = e.get("gerado_em") == pac["gerado_em"]
    ok(e.get("herdado_de") == lotes_[0].name, "herança: vc_visitas não herdado do lote 1")
    pg = S.get(base + "/farol/vc_visitas").text
    h["pagina_logo_apos"] = {"selo": "Desatualizado" in pg, "dados_de": (re.search(r"Dados de ([^<(]+)", pg) or [None, None])[1]}
    h["outro_farol_selo"] = "Desatualizado" in S.get(base + "/farol/pv_pedidos").text
    ok(not h["outro_farol_selo"], "herança: selo no farol do dia")
    # edição aplicada continua "Aguardando o PC" no farol herdado? (pl_entregas foi reenviado: some)
    if ed.get("marca_apos_aplicada") is not None:
        h["marca_entregas_reenviado"] = "Aguardando o PC" in S.get(base + "/farol/pl_entregas?aba=entregas").text
    espera = (pac["gerado_em"] and (datetime.fromisoformat(pac["gerado_em"]) + timedelta(hours=26)
                                    - datetime.now(MANAUS)).total_seconds() + 3)
    if espera > 0:
        time.sleep(espera)
    pg = S.get(base + "/farol/vc_visitas").text
    h["pagina_apos_26h"] = {"selo": "Desatualizado" in pg}
    ok(h["pagina_apos_26h"]["selo"], "herança: sem selo depois de 26 h")
    # lote 3: o vc_visitas falha de novo; o herdado tem mais de 26 h -> fica fora
    p3 = com_data(p2, datetime.now(MANAUS).replace(microsecond=0) + timedelta(seconds=2))
    r3, m3, _ = enviar(p3)
    lotes_ = sorted(d for d in (dados / "pacotes").iterdir() if (d / "indice.json").is_file())
    ind3 = json.loads((lotes_[-1] / "indice.json").read_text(encoding="utf-8"))
    h["lote3"] = {"ok": r3, "vc_visitas_no_indice": "vc_visitas" in ind3["farois"],
                  "pagina": S.get(base + "/farol/vc_visitas").status_code,
                  "link_no_menu": "/farol/vc_visitas" in S.get(base + "/").text}
    ok(not h["lote3"]["vc_visitas_no_indice"], "herança: farol com mais de 26 h herdado de novo")
    res["heranca"] = h
    res["saude_fim"] = saude()
    res["mem_fim"] = proc_mem()

proc.terminate()
proc.wait(10)
Path(SAIDA).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(ROT, "erros:", len(res["erros"]))
