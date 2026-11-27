"""
ENVIAR INADIMPLENCIA VIA E-MAIL (Farol de Inadimplencia)

Cada pessoa recebe os CLIENTES INADIMPLENTES da sua carteira, no mesmo
jeito da parcial do RH (email_parcial):
    vendedor   - os clientes dele (o supervisor em copia)
    supervisor - os clientes da equipe (o gerente em copia)
    gerente    - todos, inclusive os clientes sem vendedor
O e-mail leva o resumo e os maiores devedores no corpo e o PDF em anexo
(clientes inadimplentes + titulos vencidos, com telefone). O endereco e o
do cadastro da pessoa no Planner. O envio usa o mesmo caminho da parcial
(Outlook do computador; sem ele, .eml pronto para enviar).
Tudo fica em RELATORIOS/EXPORTADOS/INADIMPLENCIA_<data>/.

(13/11, Alexandre: "Ajuste o email de inadimplencia para ter uma tabela com
os clientes faltando ate 7 dias para vencer com os dados dele para o
vendedor acompanhar") Tabela nova "A vencer em até 7 dias" no corpo do
e-mail e no PDF: os titulos que vencem de hoje ate daqui a DIAS_A_VENCER
dias corridos [SUPOSICAO: corridos, hoje incluso], com cliente, cidade,
NF/parcela, vencimento, quantos dias faltam, condicao, saldo e telefone;
coluna JÁ INADIMPLENTE quando o cliente tambem tem titulo vencido. Recebe
quem tem cliente inadimplente OU titulo a vencer na semana.
(13/11, Alexandre: "Coloque o telefone do cliente e bairro") BAIRRO (da
BASE_CLIENTE, pelo codigo-loja) em todas as tabelas do PDF e do e-mail, e o
TELEFONE tambem nos maiores valores em atraso do corpo do e-mail.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

import bap_visual as bv
import email_parcial as ep
import relatorios_nucleo as rn

VERDE, CINZA, TEXTO, VERMELHO = ep.VERDE, ep.CINZA, ep.TEXTO, "#B3261E"
TOP_NO_EMAIL = 10          # os maiores devedores no corpo do e-mail
DIAS_A_VENCER = 7          # (13/11) a tabela dos titulos que vencem logo
MAX_A_VENCER_EMAIL = 40    # linhas no corpo do e-mail (o resto no PDF)
COD_TESTE = {"000040"}     # a conta de teste do Alexandre fica fora


def _n(x) -> str:
    return rn.norm_nome(rn.texto(x).split(" - ", 1)[-1])


def destinatarios(raiz) -> list[dict]:
    """Gerente, supervisores e vendedores ATIVOS do Planner com e-mail.
    Em copia: o supervisor no e-mail do vendedor e o gerente no do
    supervisor (como na parcial)."""
    cfg = json.loads((Path(raiz) / "planner_config.json")
                     .read_text("utf-8"))
    pessoas = [p for p in cfg.get("pessoas") or []
               if p.get("ativo") is not False
               and rn.texto(p.get("cargo")).upper() in
               ("GERENTE", "SUPERVISOR", "VENDEDOR")
               and rn.texto(p.get("cod_protheus")) not in COD_TESTE
               and "VAGO" not in rn.norm_nome(p.get("nome")).split()]
    por_cod = {rn.texto(p.get("cod_protheus")): p for p in pessoas}
    ordem = {"GERENTE": 0, "SUPERVISOR": 1, "VENDEDOR": 2}
    saida = []
    for p in pessoas:
        cargo = rn.texto(p.get("cargo")).upper()
        chefe = por_cod.get(rn.texto(p.get("responde_a"))) or {}
        saida.append({"nome": rn.texto(p.get("nome")).upper(),
                      "cargo": cargo,
                      "cod": rn.texto(p.get("cod_protheus")),
                      "email": rn.texto(p.get("email")).strip().lower(),
                      "cc": (rn.texto(chefe.get("email")).strip().lower()
                             if cargo != "GERENTE" else "")})
    saida.sort(key=lambda x: (ordem[x["cargo"]], x["nome"]))
    return saida


def _filtro(pessoa):
    """Quais linhas do farol sao dessa pessoa (pelo VENDEDOR/SUPERVISOR)."""
    alvo = _n(pessoa["nome"])
    if pessoa["cargo"] == "VENDEDOR":
        return lambda vend, sup: _n(vend) == alvo
    if pessoa["cargo"] == "SUPERVISOR":
        return lambda vend, sup: _n(sup) == alvo
    return lambda vend, sup: True


def _chave(cli) -> str:
    """'011172-01' / '10685-1' -> '011172-01'."""
    t = rn.texto(cli).strip()
    cod, _, loja = t.partition("-")
    return f"{cod.zfill(6)}-{(loja or '1').zfill(2)}"


def bairros(raiz) -> dict:
    """(13/11) {codigo-loja: BAIRRO} da BASE_CLIENTE (abas BASE_CLIENTE e
    EXCLUIDOS). Sem o arquivo: {} (a coluna sai vazia)."""
    arq = Path(raiz) / "RELATORIOS" / "BASE_CLIENTE.xlsx"
    saida = {}
    try:
        try:
            from xlsx_rapido import load_workbook       # noqa: PLC0415
        except ImportError:
            from openpyxl import load_workbook          # noqa: PLC0415
        wb = load_workbook(arq, read_only=True, data_only=True)
        try:
            for aba in ("BASE_CLIENTE", "EXCLUIDOS"):
                if aba not in wb.sheetnames:
                    continue
                it = wb[aba].iter_rows(values_only=True)
                cab = [rn.texto(c).upper() for c in next(it)]
                ic, il, ib = (cab.index("COD_CLIENTE"), cab.index("LOJA"),
                              cab.index("BAIRRO"))
                for r in it:
                    if r and r[ic] not in (None, ""):
                        saida.setdefault(
                            _chave(f"{rn.texto(r[ic])}-{rn.texto(r[il])}"),
                            rn.texto(r[ib]).upper())
        finally:
            wb.close()
    except Exception:                                   # noqa: BLE001
        return {}
    return saida


def montar_pessoa(farol: dict, pessoa: dict, posicao: str,
                  bairros_cli: dict | None = None) -> dict:
    """O relatorio (para o PDF) so com os clientes da pessoa."""
    tc = {t["titulo"]: t for t in farol["tabelas"]}
    c, t = tc["Por cliente"], tc["Títulos"]
    ic = {x["nome"]: i for i, x in enumerate(c["colunas"])}
    it = {x["nome"]: i for i, x in enumerate(t["colunas"])}
    dela = _filtro(pessoa)
    ver_vend = pessoa["cargo"] != "VENDEDOR"
    clis = [l for l in c["linhas"] if l[ic["SITUAÇÃO"]] == "INADIMPLENTE"
            and dela(l[ic["VENDEDOR"]], l[ic["SUPERVISOR"]])]
    clis.sort(key=lambda l: -(l[ic["EM ATRASO"]] or 0))
    tits = [l for l in t["linhas"] if l[it["SITUAÇÃO"]] == "VENCIDO"
            and dela(l[it["VENDEDOR"]], l[it["SUPERVISOR"]])]
    ordem_cli = {l[ic["CLIENTE"]]: i for i, l in enumerate(clis)}
    tits.sort(key=lambda l: (ordem_cli.get(l[it["CLIENTE"]], 9999),
                             -(l[it["DIAS ATRASO"]] or 0)))
    col = rn.col
    bairros_cli = bairros_cli or {}

    def _bairro(cli):
        return bairros_cli.get(_chave(cli), "")
    nome_c = ("CLIENTE", "NOME", "BAIRRO", "CIDADE", "UF") + (
        ("VENDEDOR",) if ver_vend else ()) + (
        "TÍTULOS VENCIDOS", "EM ATRASO", "MAIOR ATRASO", "FAIXA",
        "A VENCER", "ÚLTIMA COMPRA", "TELEFONE")   # (30/10) sem PEDIDO EM ABERTO
    larg = {"NOME": 190, "BAIRRO": 120, "CIDADE": 110, "VENDEDOR": 150,
            "TELEFONE": 105}
    tipo = {x["nome"]: x["tipo"] for x in c["colunas"]}
    cols_c = [col(n_ if n_ != "MAIOR ATRASO" else "DIAS (MAIOR)",
                  tipo.get(n_, "texto"), larg.get(n_)) for n_ in nome_c]
    lin_c = []
    for l in clis:
        x = [_bairro(l[ic["CLIENTE"]]) if n_ == "BAIRRO" else l[ic[n_]]
             for n_ in nome_c]
        if ver_vend:
            j_ = nome_c.index("VENDEDOR")
            x[j_] = rn._curto_pessoa(x[j_]) if x[j_] and not \
                str(x[j_]).startswith("(") else x[j_]
        lin_c.append(x)
    tons_c = ["alerta" if (l[ic["MAIOR ATRASO"]] or 0) > 30 else "atencao"
              for l in clis]
    nome_t = ("CLIENTE", "NOME", "BAIRRO", "FILIAL", "NF", "PARC.", "EMISSÃO",
              "VENCIMENTO", "DIAS ATRASO", "CONDIÇÃO", "SALDO", "TELEFONE")
    tipo_t = {x["nome"]: x["tipo"] for x in t["colunas"]}
    cols_t = [col(n_, tipo_t.get(n_, "texto"),
                  {"NOME": 190, "BAIRRO": 120, "CONDIÇÃO": 120,
                   "TELEFONE": 105}.get(n_))
              for n_ in nome_t]
    lin_t = [[_bairro(l[it["CLIENTE"]]) if n_ == "BAIRRO" else l[it[n_]]
              for n_ in nome_t] for l in tits]
    tons_t = ["alerta" if (l[it["DIAS ATRASO"]] or 0) > 30 else "atencao"
              for l in tits]
    # (13/11) os titulos que vencem de hoje ate DIAS_A_VENCER dias
    # (DIAS ATRASO negativo = faltam dias; 0 = vence hoje)
    inad_cli = {l[ic["CLIENTE"]] for l in clis}
    avenc = [l for l in t["linhas"]
             if l[it["SITUAÇÃO"]] in ("A VENCER", "VENCE HOJE")
             and -DIAS_A_VENCER <= (l[it["DIAS ATRASO"]] or 0) <= 0
             and dela(l[it["VENDEDOR"]], l[it["SUPERVISOR"]])]
    avenc.sort(key=lambda l: (-(l[it["DIAS ATRASO"]] or 0),
                              -(l[it["SALDO"]] or 0)))
    nome_a = ("CLIENTE", "NOME", "BAIRRO", "CIDADE") + (
        ("VENDEDOR",) if ver_vend else ()) + (
        "NF", "PARC.", "VENCIMENTO", "VENCE EM", "CONDIÇÃO", "SALDO",
        "JÁ INADIMPLENTE", "TELEFONE")
    tipo_a = dict(tipo_t, **{"VENCE EM": "texto",
                             "JÁ INADIMPLENTE": "texto"})
    cols_a = [col(n_, tipo_a.get(n_, "texto"),
                  {"NOME": 190, "BAIRRO": 120, "CIDADE": 110,
                   "VENDEDOR": 150, "CONDIÇÃO": 120,
                   "TELEFONE": 105}.get(n_))
              for n_ in nome_a]

    def _vence_em(d):
        d = -(d or 0)
        return "hoje" if d == 0 else ("amanhã" if d == 1 else f"{d} dias")
    lin_a = []
    for l in avenc:
        x = []
        for n_ in nome_a:
            if n_ == "VENCE EM":
                x.append(_vence_em(l[it["DIAS ATRASO"]]))
            elif n_ == "BAIRRO":
                x.append(_bairro(l[it["CLIENTE"]]))
            elif n_ == "JÁ INADIMPLENTE":
                x.append("SIM" if l[it["CLIENTE"]] in inad_cli else "")
            elif n_ == "VENDEDOR":
                v_ = l[it["VENDEDOR"]]
                x.append(rn._curto_pessoa(v_) if v_ and not
                         str(v_).startswith("(") else v_)
            else:
                x.append(l[it[n_]])
        lin_a.append(x)
    tons_a = ["alerta" if (l[it["DIAS ATRASO"]] or 0) >= -1 else "atencao"
              for l in avenc]
    soma_a = sum(l[it["SALDO"]] or 0 for l in avenc)
    tot_a = ["TOTAL", f"{rn.br(len({l[it['CLIENTE']] for l in avenc}))} "
             f"clientes"] + [""] * (len(nome_a) - 2)
    tot_a[nome_a.index("SALDO")] = soma_a
    atraso = sum(l[ic["EM ATRASO"]] or 0 for l in clis)
    mais90 = sum(l[it["SALDO"]] or 0 for l in tits
                 if (l[it["DIAS ATRASO"]] or 0) > 90)
    com_ped = [l for l in clis if (l[ic["PEDIDO EM ABERTO"]] or 0) > 0]
    rel = rn.novo("pl_inadimplencia", rn.POS,
                  "Clientes inadimplentes",
                  f"{ep.nome_bonito(pessoa['nome'])} · posição de {posicao}"
                  " · vencido = vencimento real antes de hoje",
                  "TABELA_BAP › ftTitulos (Protheus)")
    # o mesmo formato do PDF da parcial do RH (faixa preta com o logo)
    rel.update({"estilo": "bap",
                "faixa": f"CLIENTES INADIMPLENTES · POSIÇÃO {posicao}",
                "eyebrow": pessoa["cargo"] + (
                    f" · CÓD. {pessoa['cod']}" if pessoa["cargo"] ==
                    "VENDEDOR" and pessoa.get("cod") else ""),
                "titulo_curto": ep.nome_bonito(pessoa["nome"]),
                "subtitulo": f"Clientes inadimplentes {('da carteira', 'da equipe', 'de toda a BAP')[('VENDEDOR', 'SUPERVISOR', 'GERENTE').index(pessoa['cargo'])]} · posição de {posicao} · vencido = vencimento real antes de hoje"})
    rel["kpis"] = [
        rn.kpi("Clientes inadimplentes", rn.br(len(clis)),
               "alerta" if clis else "ok"),
        rn.kpi("Em atraso", rn.moeda(atraso), "alerta" if atraso else "ok",
               f"{rn.br(len(tits))} títulos vencidos"),
        rn.kpi("Acima de 90 dias", rn.moeda(mais90),
               "alerta" if mais90 else "ok",
               rn.p(rn.pct_de(mais90, atraso)) + " do atraso"
               if atraso else ""),
        rn.kpi("Com pedido em aberto", rn.br(len(com_ped)),
               "atencao" if com_ped else "ok",
               rn.moeda(sum(l[ic["PEDIDO EM ABERTO"]] for l in com_ped))
               if com_ped else ""),
        rn.kpi(f"A vencer em até {DIAS_A_VENCER} dias", rn.moeda(soma_a),
               "atencao" if avenc else "ok",
               f"{rn.br(len(avenc))} títulos · "
               f"{rn.br(len({l[it['CLIENTE']] for l in avenc}))} clientes")]
    tot_c = ["TOTAL", f"{rn.br(len(clis))} clientes"] + [""] * (
        len(nome_c) - 2)
    tot_c[nome_c.index("TÍTULOS VENCIDOS")] = len(tits)
    tot_c[nome_c.index("EM ATRASO")] = atraso
    tot_c[nome_c.index("A VENCER")] = sum(l[ic["A VENCER"]] or 0
                                          for l in clis)
    rel["tabelas"] = [
        rn.tabela("Clientes inadimplentes", cols_c, lin_c, tons_c,
                  total=tot_c if lin_c else None),
        rn.tabela("Títulos vencidos", cols_t, lin_t, tons_t,
                  total=(["TOTAL"] + [""] * (nome_t.index("SALDO") - 1)
                         + [sum(l[nome_t.index("SALDO")] for l in lin_t), ""])
                  if lin_t else None),
        rn.tabela(f"A vencer em até {DIAS_A_VENCER} dias", cols_a, lin_a,
                  tons_a, total=tot_a if lin_a else None)]
    if not clis:
        rel["avisos"].append("Nenhum cliente inadimplente na carteira.")
    rel["_resumo"] = {"clientes": len(clis), "atraso": atraso,
                      "titulos": len(tits), "mais90": mais90,
                      "com_pedido": len(com_ped),
                      # (13/11) os titulos que vencem nos proximos dias
                      "a_vencer": soma_a, "a_vencer_titulos": len(avenc),
                      "a_vencer_clientes": len({l[it["CLIENTE"]]
                                                for l in avenc}),
                      "a_vencer_linhas": [
                          (l[it["NOME"]], l[it["CIDADE"]],
                           _bairro(l[it["CLIENTE"]]),
                           (rn._curto_pessoa(l[it["VENDEDOR"]])
                            if l[it["VENDEDOR"]] and not str(
                                l[it["VENDEDOR"]]).startswith("(")
                            else l[it["VENDEDOR"]]),
                           l[it["NF"]], l[it["PARC."]],
                           l[it["VENCIMENTO"]],
                           _vence_em(l[it["DIAS ATRASO"]]),
                           l[it["SALDO"]], l[it["TELEFONE"]],
                           l[it["CLIENTE"]] in inad_cli)
                          for l in avenc],
                      "top": [(l[ic["NOME"]], l[ic["CIDADE"]],
                               l[ic["EM ATRASO"]], l[ic["MAIOR ATRASO"]],
                               rn._curto_pessoa(l[ic["VENDEDOR"]])
                               if ver_vend and not str(
                                   l[ic["VENDEDOR"]]).startswith("(")
                               else l[ic["VENDEDOR"]],
                               _bairro(l[ic["CLIENTE"]]),
                               l[ic["TELEFONE"]])
                              for l in clis[:TOP_NO_EMAIL]]}
    return rel


def assunto(pessoa, posicao) -> str:
    partes = pessoa["nome"].split()
    curto = " ".join([partes[0], partes[-1]]) if len(partes) > 2 else \
        pessoa["nome"]
    return (f"Clientes inadimplentes e a vencer em {DIAS_A_VENCER} dias - "
            f"{ep.nome_bonito(curto)} - posição de {posicao}")


def corpo_html(rel, pessoa, posicao) -> str:
    rs = rel["_resumo"]
    primeiro = (pessoa["nome"].split() or [""])[0].title()
    de_quem = {"SUPERVISOR": "da sua equipe",
               "GERENTE": "de toda a BAP"}.get(pessoa["cargo"],
                                                "da sua carteira")
    ver_vend = pessoa["cargo"] != "VENDEDOR"
    resumo = ep._quadro(
        ("Clientes inadimplentes", "Em atraso", "Títulos vencidos",
         "Acima de 90 dias", "Com pedido em aberto"),
        [(rn.br(rs["clientes"]), bv.moeda(rs["atraso"]),
          rn.br(rs["titulos"]), bv.moeda(rs["mais90"]),
          rn.br(rs["com_pedido"]))])
    cab = ("Cliente", "Bairro", "Cidade") + (
        ("Vendedor",) if ver_vend else ()) + ("Em atraso", "Dias",
                                              "Telefone")
    top = ep._quadro(cab, [
        (n_, b_, c_) + ((v_,) if ver_vend else ()) +
        (bv.moeda(a_), rn.br(d_), rn.texto(tel_))
        for n_, c_, a_, d_, v_, b_, tel_ in rs["top"]])
    corpo_top = (
        f"<p style='margin:18px 0 4px 0'><b>Maiores valores em atraso</b>"
        f"</p>" + top) if rs["top"] else (
        "<p style='margin:18px 0 0 0'>Nenhum cliente inadimplente. "
        "Parabéns!</p>")
    # (13/11) os titulos que vencem nos proximos DIAS_A_VENCER dias
    av = rs.get("a_vencer_linhas") or []
    if av:
        cab_a = ("Cliente", "Bairro", "Cidade") + (
            ("Vendedor",) if ver_vend else ()) + (
            "NF/Parc.", "Vencimento", "Vence em", "Saldo", "Telefone")
        lin_a = [
            ((n_ + " *") if ja_ else n_, b_, c_)
            + ((v_,) if ver_vend else ())
            + (f"{nf_}/{pc_}" if pc_ else str(nf_),
               dv_.strftime("%d/%m/%Y") if hasattr(dv_, "strftime")
               else rn.texto(dv_),
               ve_, bv.moeda(sd_), rn.texto(tel_))
            for n_, c_, b_, v_, nf_, pc_, dv_, ve_, sd_, tel_, ja_
            in av[:MAX_A_VENCER_EMAIL]]
        resto = len(av) - MAX_A_VENCER_EMAIL
        corpo_av = (
            f"<p style='margin:22px 0 4px 0'><b>A vencer em até "
            f"{DIAS_A_VENCER} dias</b> · {rn.br(rs['a_vencer_titulos'])} "
            f"títulos de {rn.br(rs['a_vencer_clientes'])} clientes · "
            f"{bv.moeda(rs['a_vencer'])}</p>"
            f"<p style='margin:0 0 6px 0;color:{CINZA};font-size:12px'>"
            f"Lembre o cliente antes do vencimento. * = o cliente já tem "
            f"título vencido.</p>" + ep._quadro(cab_a, lin_a)
            + (f"<p style='margin:6px 0 0 0;color:{CINZA};font-size:12px'>"
               f"… e mais {rn.br(resto)} título(s) no PDF.</p>"
               if resto > 0 else ""))
    else:
        corpo_av = (f"<p style='margin:22px 0 0 0'>Nenhum título vencendo "
                    f"nos próximos {DIAS_A_VENCER} dias.</p>")
    itens_pdf = [
        ("Clientes inadimplentes", "bairro, valor em atraso, dias, a "
                                   "vencer, última compra e telefone"),
        ("Títulos vencidos", "nota a nota: emissão, vencimento, dias e "
                             "saldo"),
        (f"A vencer em até {DIAS_A_VENCER} dias", "nota a nota: vencimento, "
                                                  "dias que faltam, saldo e "
                                                  "telefone")]
    return (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;color:{TEXTO};"
        f"font-size:14px'>"
        f"<p>Olá, {html.escape(primeiro)}.</p>"
        f"<p>Segue a posição dos <b>clientes inadimplentes {de_quem}</b> em "
        f"{html.escape(posicao)} (títulos vencidos no Protheus) e dos "
        f"<b>títulos que vencem nos próximos {DIAS_A_VENCER} dias</b>. Fale "
        f"com cada cliente e combine a data do pagamento.</p>"
        f"<table cellpadding='0' cellspacing='0' style='border:1px solid "
        f"#C9D3C6;border-collapse:separate;border-radius:6px;"
        f"margin:14px 0 0 0'><tr><td style='padding:12px 18px 14px 18px'>"
        + resumo + corpo_top + corpo_av + "</td></tr></table>"
        + f"<p style='margin:30px 0 6px 0'><b>Informações contidas no PDF"
        f"</b></p><table style='border-collapse:collapse;font-size:13px;"
        f"width:100%;max-width:760px'>"
        + "".join(f"<tr><td style='padding:6px 10px 6px 0;color:{VERDE};"
                  f"font-weight:700;border-bottom:1px solid #E5E7EB;"
                  f"width:14px'>&#9632;</td><td style='padding:6px 18px 6px "
                  f"0;white-space:nowrap;border-bottom:1px solid #E5E7EB'>"
                  f"<b>{html.escape(o)}</b></td><td style='padding:6px 0;"
                  f"color:{CINZA};white-space:nowrap;border-bottom:1px solid "
                  f"#E5E7EB'>{html.escape(d)}</td></tr>"
                  for o, d in itens_pdf)
        + "</table>"
        f"<p style='color:#000000;font-weight:700;font-style:italic;"
        f"font-size:13px;margin-top:16px;line-height:1.6'>"
        f"Pagamento feito depois desta posição pode ainda não ter baixado "
        f"no Protheus.<br>BAP AUTOPARTS · Farol de Inadimplência (Gerado "
        f"automaticamente)<br>Posição de {html.escape(posicao)}</p></div>")


def corpo_texto(rel, pessoa, posicao) -> str:
    rs = rel["_resumo"]
    primeiro = (pessoa["nome"].split() or [""])[0].title()
    ls = [f"Olá, {primeiro}.", "",
          f"Segue a posição dos clientes inadimplentes em {posicao}.", "",
          f"Clientes inadimplentes: {rn.br(rs['clientes'])} · em atraso "
          f"{bv.moeda(rs['atraso'])} · títulos vencidos "
          f"{rn.br(rs['titulos'])} · acima de 90 dias "
          f"{bv.moeda(rs['mais90'])}", "", "Maiores valores em atraso:"]
    ls += [f"- {n_} ({b_ + ', ' if b_ else ''}{c_}): {bv.moeda(a_)} · "
           f"{rn.br(d_)} dias · {rn.texto(tel_)}"
           for n_, c_, a_, d_, _v, b_, tel_ in rs["top"]]
    av = rs.get("a_vencer_linhas") or []
    ls += ["", f"A vencer em até {DIAS_A_VENCER} dias: "
               f"{rn.br(rs.get('a_vencer_titulos', 0))} títulos · "
               f"{bv.moeda(rs.get('a_vencer', 0))}"]
    ls += [f"- {n_} ({b_ + ', ' if b_ else ''}{c_}): NF {nf_} · vence "
           f"{('em ' if ve_[:1].isdigit() else '') + ve_} · {bv.moeda(sd_)} · "
           f"{rn.texto(tel_)}" + (" · já inadimplente" if ja_ else "")
           for n_, c_, b_, _v, nf_, _p, _d, ve_, sd_, tel_, ja_
           in av[:MAX_A_VENCER_EMAIL]]
    ls += ["", "O PDF em anexo traz os clientes, os títulos vencidos e os "
               "que vencem nos próximos dias.",
           "BAP AUTOPARTS · Farol de Inadimplência (Gerado "
           "automaticamente)", f"Posição de {posicao}"]
    return "\n".join(ls)


def preparar(raiz, pessoas=None, pasta=None, log=None,
             so_com_cliente=True) -> list[dict]:
    """Um PDF por pessoa e o e-mail. Quem nao tem cliente inadimplente nem
    titulo a vencer nos proximos DIAS_A_VENCER dias nao recebe
    (so_com_cliente)."""
    raiz = Path(raiz)
    farol = rn.montar("pl_inadimplencia", raiz)
    ctx = rn.Contexto(raiz)
    posicao = f"{ctx.hoje:%d/%m/%Y}"
    pasta = Path(pasta or raiz / "RELATORIOS" / "EXPORTADOS" /
                 f"INADIMPLENCIA_{datetime.now():%Y%m%d_%H%M}")
    pasta.mkdir(parents=True, exist_ok=True)
    itens = []
    bai = bairros(raiz)                 # (13/11) o bairro de cada cliente
    for p in pessoas or destinatarios(raiz):
        if log:
            log(f"Montando a inadimplência de {p['nome']}...")
        rel = montar_pessoa(farol, p, posicao, bai)
        if so_com_cliente and not rel["_resumo"]["clientes"] \
                and not rel["_resumo"]["a_vencer_titulos"]:
            continue
        anexo = bv.exportar_pdf(rel, pasta / (
            f"INADIMPLENCIA_{ctx.hoje:%Y%m%d}_{p['cargo']}_"
            f"{ep._slug(p['nome'])}.pdf"))
        itens.append({"pessoa": p, "assunto": assunto(p, posicao),
                      "html": corpo_html(rel, p, posicao),
                      "texto": corpo_texto(rel, p, posicao),
                      "anexo": Path(anexo), "resumo": rel["_resumo"]})
    return itens
