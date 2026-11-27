"""
ENVIAR ROTA DA SEMANA POR E-MAIL (Farol Roteirizacao)

A rota da semana (segunda a sexta) de cada vendedor, num PDF por vendedor:
    vendedor   - o PDF dele
    supervisor - um PDF por vendedor da equipe (anexos separados)
    gerente    - um PDF por vendedor de todo o time
Ninguem vai em copia. O endereco e o do cadastro da pessoa no Planner.
A rota e a do Planner de cada mes (a semana que vira o mes usa os dois).
O envio e o mesmo da parcial (email_parcial.enviar): Outlook classico,
e-mail padrao do Windows, Outlook na Web ou .eml na pasta.
Tudo fica em RELATORIOS/Roteirizacao/ROTA_SEMANA_<segunda>_<agora>/
(20/10: era a EXPORTADOS).
"""
from __future__ import annotations

import html
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import bap_visual as bv
import email_parcial as ep
import planner_nucleo as nu
import relatorios_nucleo as rn

VERDE, CINZA, TEXTO = ep.VERDE, ep.CINZA, ep.TEXTO
DIAS = ("Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
        "Sexta-feira", "Sábado", "Domingo")
COLUNAS_PDF = [
    ("SEQ.", "int", 30), ("COD. CLIENTE", "texto", 62),
    ("RAZÃO SOCIAL", "texto", 140), ("NOME FANTASIA", "texto", 105),
    ("UF", "texto", 22), ("CIDADE", "texto", 75), ("BAIRRO", "texto", 80),
    ("ENDEREÇO", "texto", 125), ("NÚMERO", "texto", 48),
    ("SALDO LIMITE", "moeda", 62), ("EM ATRASO", "moeda", 58),
    ("DIAS S/ COMPRA", "int", 58), ("SEGMENTO", "texto", 80),
    ("CURVA", "texto", 40), ("CONTATO (TELEFONE)", "texto", 120)]


def semana_de(hoje=None) -> date:
    """A SEGUNDA da semana atual. No sabado e no domingo, a da semana que
    vem (a rota que o vendedor ainda vai fazer)."""
    hoje = hoje or date.today()
    seg = hoje - timedelta(days=hoje.weekday())
    return seg + timedelta(days=7) if hoje.weekday() >= 5 else seg


def sabado_de_rota(segunda: date) -> bool:
    """(27/10) O sabado da semana e dia de rota quando e o ULTIMO sabado do
    mes (regra fixa); o primeiro sabado e o deposito do excedente e nao
    entra no PDF/e-mail do vendedor."""
    s = segunda + timedelta(days=5)
    return (s + timedelta(days=7)).month != s.month and s.day > 7


def dias_da_semana(segunda: date) -> list:
    n = 6 if sabado_de_rota(segunda) else 5
    return [segunda + timedelta(days=i) for i in range(n)]


def ate_quando(segunda: date) -> str:
    return "segunda a sábado" if sabado_de_rota(segunda) else \
        "segunda a sexta"


def rotulo_semana(segunda: date) -> str:
    return f"{segunda:%d/%m} a {dias_da_semana(segunda)[-1]:%d/%m/%Y}"


def _cfg_do_mes(raiz, mes):
    import pastas_bap as pb                             # noqa: PLC0415
    arq = pb.config_do_mes(raiz, mes)
    if arq.exists():
        return nu.carregar_config(arq)
    cfg = nu.carregar_config(Path(raiz) / "planner_config.json")
    return cfg if cfg.get("mes") == mes else None


def rota_da_semana(raiz, segunda: date) -> dict:
    """{"linhas": {cod_vendedor: [linhas da rota, seg a sex]}, "cfg": o
    Planner do mes da segunda (equipe e e-mails), "avisos": [...]}."""
    raiz = Path(raiz)
    dias = set(dias_da_semana(segunda))
    meses = sorted({d.strftime("%Y-%m") for d in dias})
    base = raiz / "RELATORIOS" / "BASE_CLIENTE.xlsx"
    por_vend, avisos, cfg_seg = defaultdict(list), [], None
    for mes in meses:
        cfg = _cfg_do_mes(raiz, mes)
        if cfg is None:
            avisos.append(f"{nu.rotulo_do_mes(mes)} ainda não tem Planner: "
                          f"os dias desse mês ficaram de fora.")
            continue
        if mes == segunda.strftime("%Y-%m") or cfg_seg is None:
            cfg_seg = cfg
        clientes = [dict(c) for c in nu.ler_base_cliente(base)]
        nu.aplicar_parametros(cfg, clientes)
        nu.migrar_areas_antigas(cfg, clientes)
        nu.sincronizar_areas(cfg, clientes)
        for r in nu.gerar_rota(cfg, clientes):
            d = r.get("DATA")
            d = d.date() if isinstance(d, datetime) else d
            if d in dias:
                por_vend[nu.texto(r.get("COD_VENDEDOR"))].append(r)
    for ls in por_vend.values():
        ls.sort(key=lambda r: (r["DATA"], r.get("ORDEM_DE_VISITA") or 0))
    return {"linhas": dict(por_vend), "cfg": cfg_seg or {}, "avisos": avisos}


def _vago(p) -> bool:
    nome = rn.norm_nome(p.get("nome"))
    return "VAGO" in nome.split() or "(VAGO)" in nome


def destinatarios_rota(raiz, segunda: date, rota=None) -> list:
    """Quem recebe: vendedor ATIVO com rota na semana; supervisor e
    gerente ATIVOS com pelo menos um vendedor desses. Sem copia."""
    rota = rota or rota_da_semana(raiz, segunda)
    cfg, linhas = rota["cfg"], rota["linhas"]
    if not cfg:
        return []
    ativos = {nu.texto(p.get("cod_protheus")): p
              for p in cfg.get("pessoas") or []
              if p.get("ativo") is not False and not _vago(p)}
    vendedores = [c for c in linhas if c in ativos and
                  nu.texto(ativos[c].get("cargo")).upper() == "VENDEDOR"]
    equipe = defaultdict(list)
    for v in vendedores:
        sup = nu.chefe_de(cfg, v) or {}
        if nu.texto(sup.get("cargo")).upper() == "SUPERVISOR":
            equipe[nu.texto(sup.get("cod_protheus"))].append(v)
        ger = nu.gerente_de(cfg, v) or {}
        if ger.get("cod_protheus"):
            equipe[nu.texto(ger.get("cod_protheus"))].append(v)
    saida = []
    ordem = {"GERENTE": 0, "SUPERVISOR": 1, "VENDEDOR": 2}
    for cod, p in ativos.items():
        cargo = nu.texto(p.get("cargo")).upper()
        if cargo == "VENDEDOR" and cod in vendedores:
            vs = [cod]
        elif cargo in ("SUPERVISOR", "GERENTE") and equipe.get(cod):
            vs = sorted(set(equipe[cod]),
                        key=lambda c: nu.texto(ativos[c].get("nome")))
        else:
            continue
        email = nu.texto(p.get("email")).strip().lower()
        saida.append({"cargo": cargo, "cod": cod,
                      "nome": nu.texto(p.get("nome")),
                      "email": email if nu.email_valido(email) else "",
                      "cc": "", "cc_nome": "", "vendedores": vs,
                      "visitas": sum(len(linhas[v]) for v in vs)})
    saida.sort(key=lambda x: (ordem[x["cargo"]], x["nome"]))
    return saida


# ------------------------------------------------------------ o PDF
def link_maps(r) -> str:
    """(27/10, Alexandre) o link do Google Maps para o vendedor so clicar e
    ir: com a coordenada do ENDERECO abre a rota ate o ponto; sem ela (ou
    so com o ponto do bairro/cidade) busca pelo endereco escrito."""
    from urllib.parse import quote  # noqa: PLC0415
    try:
        la, lo = float(r.get("LATITUDE")), float(r.get("LONGITUDE"))
    except (TypeError, ValueError):
        la = lo = None
    exato = nu.texto(r.get("PRECISAO_GEO")).strip().lower() in (
        "", "endereco", "endereço")
    if la is not None and lo is not None and (la or lo) and exato:
        return ("https://www.google.com/maps/dir/?api=1&destination="
                f"{la:.6f},{lo:.6f}")
    end = ", ".join(x for x in (
        " ".join(x for x in (nu.texto(r.get("ENDERECO")),
                             nu.texto(r.get("NUMERO"))) if x),
        nu.texto(r.get("BAIRRO")), nu.texto(r.get("CIDADE")),
        nu.texto(r.get("UF"))) if x.strip())
    if not end:
        return ""
    return ("https://www.google.com/maps/search/?api=1&query="
            + quote(end, safe=""))


def _linha_pdf(r) -> list:
    return [r.get("ORDEM_DE_VISITA") or 0,
            f"{nu.texto(r.get('COD_CLIENTE'))}-{nu.texto(r.get('LOJA')) or '01'}",
            nu.texto(r.get("NOME_CLIENTE")), nu.texto(r.get("NOME_FANTASIA")),
            nu.texto(r.get("UF")), nu.texto(r.get("CIDADE")),
            nu.texto(r.get("BAIRRO")), nu.texto(r.get("ENDERECO")),
            nu.texto(r.get("NUMERO")), r.get("LIMITE_DISPONIVEL") or 0.0,
            r.get("VALOR_EM_ATRASO") or 0.0,
            r.get("DIAS_SEM_COMPRA") if isinstance(
                r.get("DIAS_SEM_COMPRA"), (int, float)) else None,
            nu.texto(r.get("SEGMENTO")), nu.texto(r.get("CURVA_RECEITA")),
            nu.contato_do_cliente(r)]


def rel_do_vendedor(linhas, nome, supervisor, segunda) -> dict:
    """O relatorio (para o bap_visual.exportar_pdf): os cartoes da semana
    e uma tabela por dia, na ordem da visita."""
    por_dia = defaultdict(list)
    for r in linhas:
        d = r["DATA"].date() if isinstance(r["DATA"], datetime) else r["DATA"]
        por_dia[d].append(r)
    cols = [rn.col(n, t, l) for n, t, l in COLUNAS_PDF]
    # larguras fixas (as colunas uma embaixo da outra em todos os dias),
    # cabendo na folha A4 deitada (762 pt uteis)
    fator = 760.0 / sum(l for _n, _t, l in COLUNAS_PDF)
    for c, (_n, _t, l) in zip(cols, COLUNAS_PDF):
        c["pdf_larg"] = l * fator
    tabelas, avisos = [], []
    for d in dias_da_semana(segunda):
        ls = por_dia.get(d) or []
        if not ls:
            avisos.append(f"{DIAS[d.weekday()]}, {d:%d/%m}: sem visita na rota.")
            continue
        cid = Counter(nu.texto(r.get("CIDADE")).title() for r in ls)
        t = rn.tabela(
            f"{DIAS[d.weekday()]}, {d:%d/%m/%Y} · {len(ls)} visita(s) · "
            + " · ".join(f"{c} {n}" for c, n in sorted(cid.items())),
            [dict(c) for c in cols], [_linha_pdf(r) for r in ls])
        t["pdf"] = {"corpo": 6.3, "cab": 6.3, "pad": 2.5}
        tabelas.append(t)
    clientes = {r["CHAVE_CLIENTE"] for r in linhas}
    return {
        "titulo": f"Rota da semana · {ep.nome_bonito(nome)}",
        "subtitulo": f"{rotulo_semana(segunda)} · {ate_quando(segunda)}"
                     + (f" · supervisor {ep.nome_bonito(supervisor)}"
                        if supervisor else ""),
        "area": rn.VEN,
        "kpis": [rn.kpi("Visitas na semana", rn.br(len(linhas)), "info"),
                 rn.kpi("Clientes", rn.br(len(clientes)), "neutro"),
                 rn.kpi("Dias com rota", rn.br(len(por_dia)), "neutro"),
                 rn.kpi("Cidades", rn.br(len({(r.get('UF'), r.get('CIDADE'))
                                              for r in linhas})), "neutro"),
                 rn.kpi("Em atraso", bv.moeda(sum(
                     max(0.0, float(r.get("VALOR_EM_ATRASO") or 0))
                     for r in {r["CHAVE_CLIENTE"]: r for r in linhas}.values())),
                     "alerta" if any((r.get("VALOR_EM_ATRASO") or 0) > 0
                                     for r in linhas) else "ok")],
        "avisos": avisos, "graficos": [], "tabelas": tabelas,
        "tabelas_seguidas": True}


# ------------------------------------------------------------ o PDF novo
# (06/10, desenho do Claude Design): A4 deitado, faixa verde em cima, o
# nome do vendedor e os numeros da semana; um bloco por dia com a linha do
# dia e a tabela com cabecalho de UMA linha (letra pequena, sem fundo, so o
# traco verde embaixo); atraso em vermelho, zero como "—".
PDF_CAB = ["SEQ", "CÓDIGO", "RAZÃO SOCIAL", "NOME FANTASIA", "UF", "CIDADE",
           "BAIRRO", "ENDEREÇO", "Nº", "SALDO LIMITE", "EM ATRASO",
           "DIAS S/ COMPRA", "SEGMENTO", "CURVA", "CONTATO (TELEFONE)",
           "MAPS"]
# o peso de cada coluna no que sobra depois do minimo do cabecalho
PDF_PESO = [0, 0.4, 3.0, 2.0, 0, 1.1, 1.3, 2.6, 0.2, 0.3, 0.3, 0, 1.2, 0,
            2.4, 0]
PDF_DIREITA = {0, 9, 10, 11}
PDF_CENTRO = {4, 13, 15}


def pdf_da_rota(linhas, nome, supervisor, segunda, caminho) -> Path:
    """O PDF da rota da semana de UM vendedor. Sem o reportlab, cai no
    exportar_pdf de sempre (que grava .html)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not bv.pdf_disponivel():
        return Path(bv.exportar_pdf(rel_do_vendedor(
            linhas, nome, supervisor, segunda), caminho))
    from reportlab.lib import colors                    # noqa: PLC0415
    from reportlab.lib.pagesizes import A4, landscape   # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle     # noqa: PLC0415
    from reportlab.lib.units import mm                  # noqa: PLC0415
    from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: PLC0415
    from reportlab.platypus import (Paragraph,  # noqa: PLC0415
                                    SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    C = colors.HexColor
    VERDE_B, VERDE_T, TXT, SUA, LIN, ZEB, VERM = (
        C("#59BA61"), C("#2F7D32"), C("#1E2722"), C("#5E6B63"),
        C("#E3E7E2"), C("#F7F9F6"), C("#B42318"))
    ZEB2 = C("#F1F4F0")         # um pouco mais forte: e ela que separa a linha
    pag = landscape(A4)
    mg = 12 * mm
    larg = pag[0] - 2 * mm * 12
    gerado = datetime.now()
    titulo_pdf = f"Rota da semana · {ep.nome_bonito(nome)}"

    def moldura(cv, doc):
        cv.saveState()
        cv.setFillColor(VERDE_B)
        cv.rect(0, pag[1] - 4, pag[0], 4, stroke=0, fill=1)
        cv.setFont("Helvetica", 6.5)
        cv.setFillColor(SUA)
        cv.drawString(mg, 7 * mm, f"BAP AUTOPARTS · {titulo_pdf} · "
                                  f"{rotulo_semana(segunda)}")
        cv.drawRightString(pag[0] - mg, 7 * mm,
                           f"gerado em {gerado:%d/%m/%Y %H:%M} · página "
                           f"{doc.page}")
        cv.restoreState()

    doc = SimpleDocTemplate(str(caminho), pagesize=pag, leftMargin=mg,
                            rightMargin=mg, topMargin=11 * mm,
                            bottomMargin=13 * mm, title=titulo_pdf,
                            author="BAP AUTOPARTS")
    est = {
        "marca": ParagraphStyle("m", fontName="Helvetica-Bold", fontSize=7,
                                leading=9, textColor=VERDE_T),
        "nome": ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=17,
                               leading=21, textColor=TXT),
        "sub": ParagraphStyle("s", fontName="Helvetica", fontSize=8,
                              leading=10, textColor=SUA),
        "num": ParagraphStyle("k", fontName="Helvetica-Bold", fontSize=13,
                              leading=15, textColor=TXT, alignment=2),
        "rot": ParagraphStyle("r", fontName="Helvetica", fontSize=6.5,
                              leading=8, textColor=SUA, alignment=2),
        "dia": ParagraphStyle("d", fontName="Helvetica-Bold", fontSize=9.5,
                              leading=12, textColor=TXT),
        "dia_d": ParagraphStyle("dd", fontName="Helvetica", fontSize=7.5,
                                leading=12, textColor=SUA, alignment=2),
        "cel": ParagraphStyle("c", fontName="Helvetica", fontSize=6.4,
                              leading=7.6, textColor=TXT),
    }
    # ---- o topo: o vendedor e os numeros da semana
    clientes = {r["CHAVE_CLIENTE"]: r for r in linhas}
    atraso = sum(max(0.0, float(r.get("VALOR_EM_ATRASO") or 0))
                 for r in clientes.values())
    cidades = {(r.get("UF"), r.get("CIDADE")) for r in linhas}
    nums = [("VISITAS", rn.br(len(linhas)), TXT),
            ("CLIENTES", rn.br(len(clientes)), TXT),
            ("CIDADES", rn.br(len(cidades)), TXT),
            ("EM ATRASO", bv.moeda(atraso) if atraso else "—",
             VERM if atraso else TXT)]
    esq = [Paragraph("BAP AUTOPARTS · ROTA DA SEMANA", est["marca"]),
           Paragraph(html.escape(ep.nome_bonito(nome)), est["nome"]),
           Paragraph(html.escape(
               f"{rotulo_semana(segunda)} · {ate_quando(segunda)}"
               + (f" · supervisor {ep.nome_bonito(supervisor)}"
                  if supervisor else "")), est["sub"])]
    cel_n = [[Paragraph(f"<font color='{c.hexval().replace('0x', '#')}'>"
                        f"{html.escape(v)}</font>", est["num"]),
              Paragraph(r_, est["rot"])] for r_, v, c in nums]
    t_num = Table([[x[0] for x in cel_n], [x[1] for x in cel_n]],
                  colWidths=[24 * mm] * 3 + [30 * mm])
    t_num.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.5, LIN),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    topo = Table([[esq, t_num]], colWidths=[larg - 102 * mm, 102 * mm])
    topo.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, LIN),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    hist = [topo, Spacer(1, 10)]

    # ---- as larguras: o cabecalho cabe numa linha, o resto pelo peso
    tam_cab, pad = 5.6, 2.6
    minimo = [stringWidth(c, "Helvetica-Bold", tam_cab) + 2 * pad + 1
              for c in PDF_CAB]
    # as colunas curtas nunca quebram: cabem o cabecalho E o maior valor
    for r in linhas:
        v = _linha_pdf(r)
        txt = {0: str(v[0]), 1: str(v[1]), 4: str(v[4]), 8: str(v[8])[:8],
               9: bv.moeda(v[9]) if v[9] else "—",
               10: bv.moeda(v[10]) if v[10] else "—",
               11: "" if v[11] is None else str(int(v[11])), 13: str(v[13]),
               15: "IR ›"}
        for j, t_ in txt.items():
            minimo[j] = max(minimo[j], stringWidth(
                t_, "Helvetica-Bold", 6.4) + 2 * pad + 1)
    sobra = max(0.0, larg - sum(minimo))
    peso = sum(PDF_PESO) or 1
    col_w = [m + sobra * w / peso for m, w in zip(minimo, PDF_PESO)]

    def fmt_moeda(v, vermelho=False):
        v = float(v or 0)
        if not v:
            return Paragraph("<font color='#A0A8A2'>—</font>",
                             ParagraphStyle("z", parent=est["cel"],
                                            alignment=2))
        txt = bv.moeda(v)
        if vermelho:
            txt = f"<font color='#B42318'><b>{txt}</b></font>"
        return Paragraph(txt, ParagraphStyle("v", parent=est["cel"],
                                             alignment=2))

    def p_(v, j):
        al = 2 if j in PDF_DIREITA else (1 if j in PDF_CENTRO else 0)
        return Paragraph(html.escape(str(v if v not in (None, "") else "")),
                         ParagraphStyle(f"t{al}", parent=est["cel"],
                                        alignment=al))
    def maps_(r):
        # (27/10) o vendedor toca no IR e o Maps abre a rota ate o cliente
        url = link_maps(r)
        if not url:
            return p_("", 15)
        return Paragraph(
            f"<a href=\"{html.escape(url)}\" color=\"#1A73E8\"><u><b>"
            f"IR ›</b></u></a>",
            ParagraphStyle("mp", parent=est["cel"], alignment=1,
                           fontSize=7.6, leading=8.6))

    def end_(r, v):
        # o ENDERECO tambem abre o Maps: alvo maior para o dedo no celular
        url = link_maps(r)
        if not url or v in (None, ""):
            return p_(v, 7)
        return Paragraph(f"<a href=\"{html.escape(url)}\">"
                         f"{html.escape(str(v))}</a>", est["cel"])
    por_dia = defaultdict(list)
    for r in linhas:
        d = r["DATA"].date() if isinstance(r["DATA"], datetime) else r["DATA"]
        por_dia[d].append(r)
    for d in dias_da_semana(segunda):
        ls = por_dia.get(d) or []
        cid = Counter(nu.texto(r.get("CIDADE")).title() for r in ls)
        linha_dia = Table([[
            Paragraph(f"<font color='#59BA61'>■</font>&nbsp; "
                      f"{DIAS[d.weekday()].upper()} · {d:%d/%m}", est["dia"]),
            Paragraph(html.escape(
                (f"{len(ls)} visita(s) · " + " · ".join(
                    f"{c} {n}" for c, n in sorted(cid.items())))
                if ls else "sem visita na rota"), est["dia_d"])]],
            colWidths=[larg * 0.5, larg * 0.5])
        linha_dia.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 0)]))
        if not ls:
            hist += [linha_dia, Spacer(1, 10)]
            continue
        # a LINHA DO DIA e o CABECALHO sao as duas primeiras linhas da
        # tabela: a tabela passa de pagina repetindo as duas, sem deixar
        # meia folha em branco
        dados = [[linha_dia] + [""] * (len(PDF_CAB) - 1),
                 [Paragraph(c, ParagraphStyle(
                     f"h{j}", fontName="Helvetica-Bold", fontSize=tam_cab,
                     leading=tam_cab + 1.4, textColor=SUA,
                     alignment=2 if j in PDF_DIREITA else (
                         1 if j in PDF_CENTRO else 0)))
                  for j, c in enumerate(PDF_CAB)]]
        for r in ls:
            v = _linha_pdf(r)
            dias_ = v[11]
            dados.append([
                p_(v[0], 0), p_(v[1], 1), p_(v[2], 2), p_(v[3], 3),
                p_(v[4], 4), p_(v[5], 5), p_(v[6], 6), end_(r, v[7]),
                p_(v[8], 8), fmt_moeda(v[9]), fmt_moeda(v[10], True),
                p_("" if dias_ is None else int(dias_), 11), p_(v[12], 12),
                p_(v[13], 13), p_(v[14], 14), maps_(r)])
        t = Table(dados, colWidths=col_w, repeatRows=2)
        estilo = [
            ("SPAN", (0, 0), (-1, 0)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 1), (-1, -1), pad),
            ("RIGHTPADDING", (0, 1), (-1, -1), pad),
            ("LEFTPADDING", (0, 0), (-1, 0), 0),
            ("RIGHTPADDING", (0, 0), (-1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
            ("TOPPADDING", (0, 1), (-1, 1), 1),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 2.5),
            ("TOPPADDING", (0, 2), (-1, -1), 2.4),
            ("BOTTOMPADDING", (0, 2), (-1, -1), 2.4),
            ("LINEBELOW", (0, 1), (-1, 1), 0.8, VERDE_B),
            # (06/10) LINHAS VERTICAIS entre as colunas (mais facil de ler);
            # a linha alternada em cinza claro separa os clientes
            ("LINEAFTER", (0, 1), (-2, -1), 0.5, C("#C9D3C6")),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, C("#C9D3C6"))]
        for i in range(3, len(dados), 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), ZEB2))
        t.setStyle(TableStyle(estilo))
        hist += [t, Spacer(1, 12)]
    doc.build(hist, onFirstPage=moldura, onLaterPages=moldura)
    return caminho


def _resumo_dias(linhas, segunda) -> list:
    """[(dia, visitas, cidades)] da semana do vendedor (para o corpo)."""
    por = defaultdict(list)
    for r in linhas:
        d = r["DATA"].date() if isinstance(r["DATA"], datetime) else r["DATA"]
        por[d].append(r)
    saida = []
    for d in dias_da_semana(segunda):
        ls = por.get(d) or []
        cid = Counter(nu.texto(r.get("CIDADE")).title() for r in ls)
        saida.append((f"{DIAS[d.weekday()].split('-')[0]} {d:%d/%m}",
                      len(ls), ", ".join(sorted(cid)) or "—"))
    return saida


def _quadro(cab, linhas) -> str:
    th = "".join(
        f"<th style='padding:6px 10px;text-align:{'left' if i != 1 else 'right'};"
        f"color:{CINZA};font-weight:600;white-space:nowrap;border-bottom:2px "
        f"solid {VERDE}'>{html.escape(t)}</th>" for i, t in enumerate(cab))
    tr = "".join(
        "<tr>" + "".join(
            f"<td style='padding:6px 10px;text-align:"
            f"{'left' if i != 1 else 'right'};border-bottom:1px solid "
            f"#E5E7EB'>{html.escape(str(v))}</td>" for i, v in enumerate(ln))
        + "</tr>" for ln in linhas)
    return (f"<table style='border-collapse:collapse;font-size:13px'>"
            f"<tr>{th}</tr>{tr}</table>")


def corpo(pessoa, linhas_de, nomes, segunda) -> tuple:
    """(html, texto) do e-mail."""
    primeiro = (pessoa["nome"].split() or [""])[0].title()
    sem = rotulo_semana(segunda)
    if pessoa["cargo"] == "VENDEDOR":
        ls = linhas_de[pessoa["cod"]]
        res = _resumo_dias(ls, segunda)
        quadro = _quadro(("Dia", "Visitas", "Cidades"), res)
        txt_q = [f"- {d}: {n} visita(s) · {c}" for d, n, c in res]
        intro = f"Segue a sua rota da semana de {sem} ({ate_quando(segunda)})."
        fim = "O PDF em anexo traz os clientes de cada dia, na ordem da visita."
    else:
        res = []
        for v in pessoa["vendedores"]:
            ls = linhas_de[v]
            res.append((ep.nome_bonito(nomes.get(v, v)), len(ls),
                        len({r["CHAVE_CLIENTE"] for r in ls})))
        quadro = _quadro(("Vendedor", "Visitas", "Clientes"), res)
        txt_q = [f"- {n}: {v} visita(s), {c} cliente(s)" for n, v, c in res]
        intro = (f"Segue a rota da semana de {sem} ({ate_quando(segunda)}) "
                 f"{'da sua equipe' if pessoa['cargo'] == 'SUPERVISOR' else 'do time'}.")
        fim = ("Em anexo, um PDF por vendedor, com os clientes de cada dia na "
               "ordem da visita.")
    rodape = ("BAP AUTOPARTS · Farol Roteirização (Gerado automaticamente)<br>"
              f"Rota do Planner · semana de {sem}")
    h = (f"<div style='font-family:Segoe UI,Arial,sans-serif;color:{TEXTO};"
         f"font-size:14px'><p>Olá, {html.escape(primeiro)}.</p>"
         f"<p>{html.escape(intro)}</p>{quadro}"
         f"<p style='margin-top:16px'>{html.escape(fim)}</p>"
         f"<p style='color:#000000;font-weight:700;font-style:italic;"
         f"font-size:13px;margin-top:16px;line-height:1.6'>{rodape}</p></div>")
    t = "\n".join([f"Olá, {primeiro}.", "", intro, ""] + txt_q +
                  ["", fim, "", rodape.replace("<br>", "\n")])
    return h, t


def gerar_pdfs(raiz, cods, segunda: date, rota=None, pasta=None) -> list:
    """So os PDFs (Ver PDF no Farol Roteirizacao): um por vendedor."""
    raiz = Path(raiz)
    rota = rota or rota_da_semana(raiz, segunda)
    nomes = {nu.texto(p.get("cod_protheus")): nu.texto(p.get("nome"))
             for p in rota["cfg"].get("pessoas") or []}
    pasta = Path(pasta or raiz / "RELATORIOS" / "Roteirizacao" /
                 f"ROTA_SEMANA_{segunda:%Y%m%d}_{datetime.now():%Y%m%d_%H%M}")
    saida = []
    for cod in cods:
        if not rota["linhas"].get(cod):
            continue
        saida.append(pdf_da_rota(
            rota["linhas"][cod], nomes.get(cod, cod),
            nu.nome_supervisor(rota["cfg"], cod), segunda,
            pasta / f"ROTA_{segunda:%Y%m%d}_{cod}_"
                    f"{ep._slug(nomes.get(cod, cod))}.pdf"))
    return saida


def preparar(raiz, pessoas, segunda: date, rota=None, pasta=None,
             log=None) -> list:
    """Um PDF por vendedor (feito uma vez so) e o e-mail de cada pessoa:
    [{pessoa, assunto, html, texto, anexos, eml}]."""
    raiz = Path(raiz)
    rota = rota or rota_da_semana(raiz, segunda)
    cfg, linhas_de = rota["cfg"], rota["linhas"]
    nomes = {nu.texto(p.get("cod_protheus")): nu.texto(p.get("nome"))
             for p in cfg.get("pessoas") or []}
    pasta = Path(pasta or raiz / "RELATORIOS" / "Roteirizacao" /
                 f"ROTA_SEMANA_{segunda:%Y%m%d}_{datetime.now():%Y%m%d_%H%M}")
    pasta.mkdir(parents=True, exist_ok=True)
    pdfs = {}

    def pdf_de(cod):
        if cod not in pdfs:
            if log:
                log(f"Montando a rota de {nomes.get(cod, cod)}...")
            pdfs[cod] = pdf_da_rota(
                linhas_de[cod], nomes.get(cod, cod),
                nu.nome_supervisor(cfg, cod), segunda,
                pasta / f"ROTA_{segunda:%Y%m%d}_{cod}_"
                        f"{ep._slug(nomes.get(cod, cod))}.pdf")
        return pdfs[cod]
    itens = []
    for p in pessoas:
        anexos = [pdf_de(v) for v in p["vendedores"] if linhas_de.get(v)]
        if not anexos:
            continue
        h, t = corpo(p, linhas_de, nomes, segunda)
        partes = p["nome"].split()
        curto = " ".join([partes[0], partes[-1]]) if len(partes) > 2 \
            else p["nome"]
        itens.append({
            "pessoa": dict(p, cc=""),          # rota: ninguem em copia
            "assunto": f"Rota da semana {segunda:%d/%m} a "
                       f"{dias_da_semana(segunda)[-1]:%d/%m} - "
                       f"{ep.nome_bonito(curto)}",
            "html": h, "texto": t, "anexo": anexos[0], "anexos": anexos,
            "eml": str(pasta / f"EMAIL_{p['cargo']}_{ep._slug(p['nome'])}"
                               f".eml")})
    return itens
