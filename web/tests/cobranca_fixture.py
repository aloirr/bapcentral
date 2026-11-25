"""Fixture FICTÍCIA da cobrança (T-0017, §10.2): "Cliente 001", "Vendedor 01", telefone 5592900000001."""
from copy import deepcopy

from app import cobranca
from farol_fixture import farol_inadimplencia, pacote_farol

HOJE = "2026-11-24"


def _cols(titulo):
    return [{"nome": n, "tipo": t, "oculta": n in ("STATUS PROTHEUS", "SITUAÇÃO PLANNER")}
            for n, t in cobranca.COLUNAS[titulo]]


def _titulos():
    linhas, tons = [], []
    for i in range(1, 13):
        dias = 10 + i * 9
        linhas.append(["VENCIDO", "31-60" if dias < 61 else "61-90", "AM", str(1000 + i), "1",
                       "2026-09-01", "2026-10-%02d" % min(i + 10, 28), dias, f"{i:06d}-01",
                       f"Cliente {i:03d}", "LIBERADO", "OK", "SEM PENDÊNCIA",
                       "MANAUS" if i % 3 else "BELÉM", "AM" if i % 3 else "PA",
                       f"Vendedor {(i % 4) + 1:02d}", "Supervisor 01", "30 DIAS", 1500.0 * i, 1200.0 * i])
        tons.append("alerta" if dias > 60 else "atencao")
    return {"titulo": "Títulos", "colunas": _cols("Títulos"), "linhas": linhas, "tons": tons,
            "total": ["", "", "", "", "", None, None, None, "", "", "", "", "", "", "", "", "", "", 117000.0, 93600.0],
            "filtros": ["SITUAÇÃO", {"coluna": "UF", "multi": True}, "VENDEDOR"]}


def _por_cliente():
    linhas, tons = [], []
    for i in range(1, 7):
        linhas.append(["INADIMPLENTE", "31-60", f"{i:06d}-01", f"Cliente {i:03d}", "LIBERADO", "OK", "SEM PENDÊNCIA",
                       "MANAUS" if i % 3 else "BELÉM", "AM" if i % 3 else "PA", f"Vendedor {(i % 4) + 1:02d}",
                       "Supervisor 01", 2, 2400.0 * i, 20 + i * 12, 800.0, "2026-12-05", 20000.0, 0.0,
                       "2026-10-02"])
        tons.append("alerta")
    return {"titulo": "Por cliente", "colunas": _cols("Por cliente"), "linhas": linhas, "tons": tons,
            "total": None, "filtros": ["UF", "VENDEDOR"]}


def _fila():
    base = {"supervisor": "Supervisor 01", "aviso": "", "uf": "AM", "cidade": "MANAUS"}
    itens = []
    for i, (zap, aviso, ultimo) in enumerate([
            ("5592900000001", "", None),
            ("559232000002", "telefone fixo: pode não ter WhatsApp", None),
            ("", "sem telefone no cadastro", None),
            ("5592900000004", "", {"quando": "2026-11-24 09:00:00", "acao": "ENVIADO", "origem": "PC"}),
            ("5592900000005", "", {"quando": "2026-11-21 10:15:00", "acao": "ENVIADO", "origem": "WEB"})], 1):
        n = f"{i:03d}"
        itens.append({**base, "cod": f"{i:06d}-01", "nome": f"Cliente {n}", "nome_msg": f"Cliente {n}",
                      "vendedor": f"Vendedor {(i % 4) + 1:02d}", "em_atraso": 9000.0 - 1000 * i,
                      "maior": 90 - 10 * i, "whatsapp": zap, "aviso": aviso,
                      "titulos": [{"nf": str(1000 + i), "parc": "1", "venc": "2026-10-20", "dias": 35,
                                   "saldo": 4000.0},
                                  {"nf": str(2000 + i), "parc": "2", "venc": "2026-11-05", "dias": 19,
                                   "saldo": 5000.0 - 1000 * i}],
                      "mensagem": f"Olá, Cliente {n}! Tudo bem? Identificamos 2 títulos em atraso. "
                                  f"NF {1000 + i} parcela 1, vencida em 20/10. Pode nos dar um retorno?",
                      "ultimo": ultimo})
    return itens


def cobranca_bloco(web_ate_seq=0, web_epoca=""):
    return {"gerado_em": "2026-11-24T08:07:00-04:00", "web_epoca": web_epoca, "web_ate_seq": web_ate_seq, "dias_recente": 7,
            "modelo": "Olá, {cliente}! ...", "fila": _fila()}


def farol_com_cobranca(web_ate_seq=0, web_epoca=""):
    f = farol_inadimplencia()
    f["tabelas"] = [_titulos(), _por_cliente()]
    f["cobranca"] = cobranca_bloco(web_ate_seq, web_epoca)
    return f


def pacote_cobranca(web_ate_seq=0, gerado_em="2026-11-24T08:30:00-04:00", web_epoca=""):
    p = pacote_farol(pl_inadimplencia=farol_com_cobranca(web_ate_seq, web_epoca))
    p["gerado_em"] = gerado_em
    return deepcopy(p)
