"""Monta o pacote do robô (antigo ou novo) com as bases congeladas, como o 4f
(passo_pacote_web): robô novo com cortar=False (corta no envio). Grava o JSON
fora do repositório. Uso (fora do pytest; a saída tem dado da base, não vai ao repositório):
    python tests/ponta_a_ponta_T0035_gera.py <raiz> <saida.json>"""
import inspect
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
import bap_automation as ba  # noqa: E402
import relatorios_nucleo as rn  # noqa: E402

HOJE = date(2026, 11, 24)
t0 = time.time()
params = {"ANO": "2026", "MÊS": "11"}
rels, cob = {}, {}
for rid in ["vc_painel"] + list(ba.FAROIS_WEB):
    rels[rid] = rn.montar(rid, RAIZ, hoje=HOJE, params=dict(params),
                          tela=(rid == ba.RID_META_WEB))
    if rid in ("vc_painel", ba.RID_META_WEB):
        rels[rid + "_uf"] = ba.montar_por_uf_web(rid, rels[rid], RAIZ, dict(params), HOJE)
    if rid == ba.RID_COBRANCA_WEB:
        cob.update(ba.preparar_cobranca_web({rid: rels[rid]}, RAIZ, HOJE, False, log=lambda m: None))
kw = dict(raiz=RAIZ, cobranca=cob, parciais=ba.parciais_web(RAIZ, HOJE),
          csvs=ba.csvs_importar_web(RAIZ, HOJE),
          agora=datetime(2026, 11, 24, 8, 30, tzinfo=ZoneInfo("America/Manaus")))
if "cortar" in inspect.signature(ba.montar_pacote_web).parameters:
    kw["cortar"] = False
pac = ba.montar_pacote_web(rels, 2026, 11, **kw)
Path(sys.argv[2]).write_text(json.dumps(pac, ensure_ascii=False), encoding="utf-8")
tam = {r: len(json.dumps(f, ensure_ascii=False).encode()) for r, f in pac["relatorios"].items()}
print("cortar" in kw, f"{time.time() - t0:.0f}s", {r: round(v / 1048576, 2) for r, v in tam.items()})
