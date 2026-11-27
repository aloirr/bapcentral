"""
ENVIAR PARCIAL VIA E-MAIL (Farol de Metas Equipe)

Cada colaborador recebe a SUA parcial do mes, no formato do RH:
    vendedor   - a linha dele
    supervisor - a linha dele e a dos vendedores dele
    gerente    - o time inteiro
O e-mail leva os numeros no corpo (meta, realizado, % e RV de faturamento,
positivacao e visita) e o PDF em anexo. O endereco e o do cadastro da
pessoa no Planner (cadastro e alteracao de vendedor, campo E-mail).

Como sai:
    1. Outlook do computador (o "classico", que aceita automacao): envia
       direto, ou abre cada e-mail para revisar antes.
    2. Sem esse Outlook: grava um .eml por pessoa (abre como e-mail pronto,
       e so clicar em Enviar) e um .html com o mesmo conteudo.
Tudo fica em RELATORIOS/EXPORTADOS/PARCIAIS_<MES>_<data>/.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import bap_visual as bv
import relatorios_nucleo as rn

VERDE, CINZA, TEXTO = "#2F7D32", "#6B7280", "#1F2937"


def nome_bonito(nome: str) -> str:
    """ "DENYLSON DA SILVA COSTA" -> "Denylson da Silva Costa"."""
    miudas = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    return " ".join(p.lower() if p.upper() in miudas and i else p.title()
                    for i, p in enumerate(str(nome).split()))


def _slug(nome: str) -> str:
    s = re.sub(r"[^A-Z0-9]+", "_", rn.norm_nome(nome))
    return s.strip("_")[:40] or "SEM_NOME"


# O QUE TEM NO PDF: a lista no corpo do e-mail (para abrir o anexo)
# o que cada tabela do PDF traz (a lista do e-mail segue a ORDEM do PDF)
PESSOAS_PDF = ("Por gerente", "Por supervisor", "Por vendedor")
TOP_LUGAR = ("Top 30 cidades", "Top 30 bairros")
DETALHE_PDF = {
    "pessoas": "meta, real, projeção, mix e RV",
    "Por UF": "onde está o resultado na carteira",
    "Por categoria": "peças, baterias, lubrificantes, químicos, pneus e "
                     "acessórios",
    "Por segmento": "resultado por tipo de cliente",
    "Por família da peça": "amortecedores, filtros, pastilhas...",
    "lugares": "as de maior meta, uma página cada",
    "Top 30 clientes": "os maiores dos últimos 6 meses",
    "Notas fiscais": "nota por nota (devolução em vermelho)",
    "Pedidos em aberto": "pedido a pedido, para acompanhar (atrasado em "
                         "vermelho)",
}
CARTOES_PDF = ("Cartões", "atingimento, projeção, necessidade por dia e "
                          "pedidos em aberto")


def _no_pdf(rel: dict) -> list:
    """[(o que, detalhe)] do PDF desta pessoa, NA ORDEM DO PDF: cartões,
    gerente/supervisor/vendedor, UF, categoria, segmento, família, Top 30
    cidades/bairros, Top 30 clientes e as notas fiscais por último."""
    saida = [CARTOES_PDF]
    pessoas, lugares = [], []
    for tit in [t["titulo"] for t in rel.get("tabelas") or []]:
        if tit in PESSOAS_PDF:
            if not pessoas:
                saida.append(None)              # o lugar do grupo na ordem
                i_pes = len(saida) - 1
            pessoas.append(tit)
            continue
        if tit in TOP_LUGAR:
            if not lugares:
                saida.append(None)
                i_lug = len(saida) - 1
            lugares.append(tit)
            continue
        if tit.startswith("Notas fiscais"):
            saida.append((tit, DETALHE_PDF["Notas fiscais"]))
        elif tit.startswith("Pedidos em aberto"):
            saida.append((tit, DETALHE_PDF["Pedidos em aberto"]))
        elif tit in DETALHE_PDF:
            saida.append((tit, DETALHE_PDF[tit]))
    if pessoas:
        saida[i_pes] = ("Por " + " / ".join(x.replace("Por ", "")
                                            for x in pessoas),
                        DETALHE_PDF["pessoas"])
    if lugares:
        saida[i_lug] = (" / ".join(lugares), DETALHE_PDF["lugares"])
    return [x for x in saida if x]


def assunto(rot: str, nome: str, rel: dict) -> str:
    """Parcial OUT/26 - Alexandre Guerreiro - Resultado até 04/10/2026."""
    partes = str(nome).split()
    curto = " ".join([partes[0], partes[-1]]) if len(partes) > 2 else nome
    return (f"Parcial {rot} - {nome_bonito(curto)} - Resultado até "
            f"{rel.get('resultado_ate') or rel.get('posicao', '')}")


def _rotulo(g: str) -> str:
    """O nome do indicador no e-mail (o que vem em CAIXA ALTA vira titulo)."""
    g = str(g).split(" (")[0]
    return g.title().replace(" Rh", " RH") if g.isupper() else g


def _cor_rv(txt) -> str:
    """RV: R$ 0,00 em vermelho; com valor, em verde."""
    t = str(txt).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        v = float(t)
    except ValueError:
        return ""
    return "color:#B3261E;font-weight:700;" if v <= 0 else \
        f"color:{VERDE};font-weight:700;"


def _quadro(cab, linhas, destaque=False, col_rv=None) -> str:
    """Um quadro do e-mail: o nome do indicador e os numeros a direita,
    com LINHAS VERTICAIS entre as colunas. col_rv: a coluna da RV
    (vermelha em R$ 0,00, verde com valor)."""
    def borda(i, n):
        return "" if i == n - 1 else "border-right:1px solid #E5E7EB;"
    th = "".join(
        f"<th style='padding:6px 10px;text-align:{'left' if i == 0 else 'right'};"
        f"color:{CINZA};font-weight:600;white-space:nowrap;border-bottom:2px "
        f"solid {VERDE};{borda(i, len(cab))}'>{html.escape(t)}</th>"
        for i, t in enumerate(cab))
    tr = "".join(
        "<tr>" + "".join(
            f"<td style='padding:6px 10px;white-space:nowrap;"
            f"text-align:{'left' if i == 0 else 'right'};{borda(i, len(ln))}"
            f"{'font-weight:600;' if destaque and i == 0 else ''}"
            f"{_cor_rv(v) if i == col_rv else ''}'>"
            f"{html.escape(str(v))}</td>" for i, v in enumerate(ln)) + "</tr>"
        for ln in linhas)
    return (f"<table style='border-collapse:collapse;font-size:13px;"
            f"border-bottom:1px solid #E5E7EB'>"
            f"<tr>{th}</tr>{tr}</table>")


CAB_RESUMO = ("Meta", "Realizado", "% Ating.", "Projeção", "% Ating. Proj.",
              "GAP mês", "Nec./dia")


def corpo_html(rel: dict, pessoa: dict) -> str:
    """O e-mail: saudacao, o DESAFIO FAT. COMERCIAL (sem RV), os indicadores
    da RV, o que tem no PDF e o fim em negrito."""
    primeiro = (pessoa["nome"].split() or [""])[0].title()
    des = rel.get("resumo_desafio")
    quadro_des = ""
    if des:
        quadro_des = (
            f"<p style='margin:16px 0 4px 0'><b>Desafio Fat. Comercial</b>"
            f"</p>"
            + _quadro(("Indicador", "Desafio") + CAB_RESUMO[1:],
                      [(_rotulo(des[0]),) + tuple(des[1:4]) + tuple(des[5:9])],
                      destaque=True))
    quadro_rv = (
        f"<p style='margin:16px 0 4px 0'><b>Indicadores da RV</b></p>"
        + _quadro(("Indicador",) + CAB_RESUMO + ("RV",),
                  [(_rotulo(x[0]),) + tuple(x[1:4]) + tuple(x[5:9]) + (x[4],)
                   for x in rel.get("resumo_pessoa") or []],
                  col_rv=len(CAB_RESUMO) + 1))
    rv = rel.get("rv_pessoa")
    equipe = {"SUPERVISOR": "o seu resultado e o da sua equipe",
              "GERENTE": "o resultado de toda a equipe"}.get(
        pessoa["cargo"], "o seu resultado")
    itens_pdf = [(equipe[0].upper() + equipe[1:], "")] + _no_pdf(rel)
    return (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;color:{TEXTO};"
        f"font-size:14px'>"
        f"<p>Olá, {html.escape(primeiro)}.</p>"
        f"<p>Segue a sua parcial de "
        f"{html.escape(rn.rotulo_mes(rel.get('competencia', '')))}, com o "
        f"resultado até "
        f"{html.escape(rel.get('resultado_ate') or rel.get('posicao', ''))}"
        f".</p>"
        # a MOLDURA: do Desafio ate a RV parcial, separada do resto
        + f"<table cellpadding='0' cellspacing='0' style='border:1px solid "
        f"#C9D3C6;border-collapse:separate;border-radius:6px;"
        f"margin:14px 0 0 0'><tr><td style='padding:2px 18px 14px 18px'>"
        + quadro_des + quadro_rv
        + (f"<p style='margin:14px 0 0 0'><b>RV parcial: <span style='"
           f"{_cor_rv(bv.moeda(rv or 0, 2))}'>"
           f"{html.escape(bv.moeda(rv or 0, 2))}</span></b></p>"
           if rv is not None else "")
        + "</td></tr></table>"
        + f"<p style='margin:30px 0 6px 0'><b>Informações contidas no PDF"
        f"</b></p>"
        f"<table style='border-collapse:collapse;font-size:13px;"
        f"width:100%;max-width:760px'>"
        + "".join(f"<tr><td style='padding:6px 10px 6px 0;color:{VERDE};"
                  f"font-weight:700;border-bottom:1px solid #E5E7EB;"
                  f"width:14px'>&#9632;</td>"
                  f"<td style='padding:6px 18px 6px 0;white-space:nowrap;"
                  f"border-bottom:1px solid #E5E7EB'><b>{html.escape(o)}</b>"
                  f"</td><td style='padding:6px 0;color:{CINZA};"
                  f"white-space:nowrap;border-bottom:1px solid #E5E7EB'>"
                  f"{html.escape(d)}</td></tr>" for o, d in itens_pdf)
        + "</table>"
        # o FIM do e-mail: em preto e negrito, igual para todo mundo
        f"<p style='color:#000000;font-weight:700;font-style:italic;"
        f"font-size:13px;margin-top:16px;line-height:1.6'>"
        f"O PDF em anexo traz {html.escape(equipe)}. Valores parciais: mudam "
        f"até o fechamento do mês.<br>"
        f"BAP AUTOPARTS · Farol de Metas (Gerado automaticamente)<br>"
        f"Resultado até "
        f"{html.escape(rel.get('resultado_ate') or rel.get('posicao', ''))}"
        f"</p></div>")


def preparar(raiz, params, pessoas, pasta=None, log=None) -> list[dict]:
    """Um PDF por pessoa e o corpo do e-mail. Devolve os itens prontos:
    {pessoa, assunto, html, anexo}."""
    raiz = Path(raiz)
    ctx = rn.Contexto(raiz, params=dict(params or {}))
    comp = rn.meta_do_periodo(ctx)["competencia"]
    rot = rn.rotulo_mes(comp)
    pasta = Path(pasta or raiz / "RELATORIOS" / "EXPORTADOS" /
                 f"PARCIAIS_{rot.replace('/', '')}_{datetime.now():%Y%m%d_%H%M}")
    pasta.mkdir(parents=True, exist_ok=True)
    itens = []
    for p in pessoas:
        if log:
            log(f"Montando a parcial de {p['nome']}...")
        rel = rn.exportar_rh(ctx, parcial=p)
        rel["area"] = rn.VEN
        anexo = bv.exportar_pdf(rel, pasta / f"PARCIAL_{rot.replace('/', '')}_"
                                f"{p['cargo']}_{_slug(p['nome'])}.pdf")
        itens.append({
            "pessoa": p,
            "assunto": assunto(rot, p["nome"], rel),
            "html": corpo_html(rel, p), "texto": corpo_texto(rel, p),
            "anexo": Path(anexo)})
    return itens


def _outlook():
    """O Outlook classico por automacao (pywin32), ou None."""
    try:
        import pythoncom                                # noqa: PLC0415
        import win32com.client as com                   # noqa: PLC0415
        pythoncom.CoInitialize()
        return com.Dispatch("Outlook.Application")
    except Exception:                                   # noqa: BLE001
        return None


def anexos_de(item) -> list:
    """Os anexos do e-mail: "anexos" (varios, a rota da semana do
    supervisor) ou o "anexo" de sempre."""
    return [Path(a) for a in (item.get("anexos") or [item["anexo"]])]


def gravar_eml(item, destino: Path) -> Path:
    """O e-mail pronto num .eml (X-Unsent: abre como rascunho para enviar)."""
    msg = EmailMessage()
    msg["To"] = item["pessoa"]["email"]
    if item["pessoa"].get("cc"):
        msg["Cc"] = ", ".join(x.strip() for x in
                              item["pessoa"]["cc"].split(";") if x.strip())
    msg["Subject"] = item["assunto"]
    msg["X-Unsent"] = "1"
    msg.set_content(item.get("texto") or "Parcial do Farol de Metas em "
                                          "anexo.")
    msg.add_alternative(item["html"], subtype="html")
    for anexo in anexos_de(item):
        dados = anexo.read_bytes()
        sub = "pdf" if anexo.suffix.lower() == ".pdf" else "html"
        msg.add_attachment(dados, maintype="application" if sub == "pdf"
                           else "text", subtype=sub, filename=anexo.name)
    destino.write_bytes(bytes(msg))
    return destino


def corpo_texto(rel: dict, pessoa: dict) -> str:
    """O mesmo e-mail em texto puro (o MAPI do Windows nao leva HTML)."""
    primeiro = (pessoa["nome"].split() or [""])[0].title()
    linhas = [f"Olá, {primeiro}.", "",
              f"Segue a sua parcial de "
              f"{rn.rotulo_mes(rel.get('competencia', ''))}, com o resultado "
              f"até {rel.get('resultado_ate') or rel.get('posicao', '')}.",
              ""]
    def linha_(x, com_rv):
        g, meta, real, pct, rv, proj, pproj, gap, nec = x
        return (f"{_rotulo(g)}: realizado {real} de {meta} ({pct}) · "
                f"projeção {proj} ({pproj}) · GAP {gap} · nec./dia {nec}"
                + (f" · RV {rv}" if com_rv else ""))
    if rel.get("resumo_desafio"):
        linhas += ["DESAFIO FAT. COMERCIAL",
                   linha_(rel["resumo_desafio"], False), ""]
    linhas.append("INDICADORES DA RV")
    for x in rel.get("resumo_pessoa") or []:
        linhas.append(linha_(x, True))
    if rel.get("rv_pessoa") is not None:
        linhas += ["", f"RV parcial: {bv.moeda(rel['rv_pessoa'] or 0, 2)}"]
    if pessoa["cargo"] in ("SUPERVISOR", "GERENTE"):
        for t in rel.get("tabelas") or []:
            if t["titulo"] != "Vendedores" or not t["linhas"]:
                continue
            linhas += ["", "Vendedores (faturamento: realizado de meta, %):"]
            for l in t["linhas"]:
                linhas.append(f"- {nome_bonito(l[0])}: {bv.moeda(l[3] or 0)}"
                              f" de {bv.moeda(l[2] or 0)} "
                              f"({rn.p(l[4])})")
    eq_ = {"SUPERVISOR": "O seu resultado e o da sua equipe",
           "GERENTE": "O resultado de toda a equipe"}.get(
        pessoa["cargo"], "O seu resultado")
    linhas += ["", "Informações contidas no PDF:", f"- {eq_}"]
    linhas += [f"- {o}: {d}" for o, d in _no_pdf(rel)]
    equipe = {"SUPERVISOR": "o seu resultado e o da sua equipe",
              "GERENTE": "o resultado de toda a equipe"}.get(
        pessoa["cargo"], "o seu resultado")
    linhas += ["", f"O PDF em anexo traz {equipe}. Valores parciais: mudam "
               f"até o fechamento do mês.",
               "BAP AUTOPARTS · Farol de Metas (Gerado automaticamente)",
               f"Resultado até {rel.get('resultado_ate') or rel.get('posicao', '')}"]
    return "\n".join(linhas)


# ------------------------------------------------------------ Outlook
def _motivo_outlook(erro) -> str:
    """O erro do Outlook em portugues claro (sem o texto gigante do COM)."""
    t = str(erro)
    if "-2147221231" in t or "arquivo de dados" in t.lower() or \
            "data file" in t.lower():
        return ("o Outlook clássico está instalado, mas sem conta de e-mail "
                "configurada (o e-mail deve estar no novo Outlook ou na web)")
    if "-2147221005" in t or "Invalid class string" in t:
        return "o Outlook clássico não está instalado"
    return t.split(",")[2].strip(" '") if t.count(",") > 2 else t[:160]


def _outlook_pronto():
    """(Outlook classico, None) se ele cria e-mail; (None, motivo) se nao.
    Testa UMA vez, em vez de errar o mesmo erro para cada pessoa."""
    ol = _outlook()
    if ol is None:
        return None, "o Outlook clássico não respondeu"
    try:
        m = ol.CreateItem(0)
        m.Close(1)                      # olDiscard: so o teste
        return ol, None
    except Exception as erro:                           # noqa: BLE001
        return None, _motivo_outlook(erro)


# ------------------------------------------------------------ MAPI
def _mapi_enviar(para, assunto, texto, anexo, com_janela=True, cc=""):
    """O 'Enviar para > Destinatario de e-mail' do Windows (Simple MAPI):
    vale para o aplicativo de e-mail padrao, inclusive o novo Outlook.
    com_janela=True: abre o e-mail pronto para clicar em Enviar.
    Devolve 0 se deu certo (1 = cancelado pela pessoa)."""
    import ctypes                                       # noqa: PLC0415
    from ctypes import POINTER, Structure, c_size_t, c_ulong, c_void_p, \
        c_wchar_p                                       # noqa: PLC0415

    class Recip(Structure):
        _fields_ = [("ulReserved", c_ulong), ("ulRecipClass", c_ulong),
                    ("lpszName", c_wchar_p), ("lpszAddress", c_wchar_p),
                    ("ulEIDSize", c_ulong), ("lpEntryID", c_void_p)]

    class Arq(Structure):
        _fields_ = [("ulReserved", c_ulong), ("flFlags", c_ulong),
                    ("nPosition", c_ulong), ("lpszPathName", c_wchar_p),
                    ("lpszFileName", c_wchar_p), ("lpFileType", c_void_p)]

    class Msg(Structure):
        _fields_ = [("ulReserved", c_ulong), ("lpszSubject", c_wchar_p),
                    ("lpszNoteText", c_wchar_p),
                    ("lpszMessageType", c_wchar_p),
                    ("lpszDateReceived", c_wchar_p),
                    ("lpszConversationID", c_wchar_p), ("flFlags", c_ulong),
                    ("lpOriginator", POINTER(Recip)),
                    ("nRecipCount", c_ulong), ("lpRecips", POINTER(Recip)),
                    ("nFileCount", c_ulong), ("lpFiles", POINTER(Arq))]
    mapi = ctypes.WinDLL("mapi32.dll")
    fn = mapi.MAPISendMailW
    fn.argtypes = [c_size_t, c_size_t, POINTER(Msg), c_ulong, c_ulong]
    fn.restype = c_ulong
    copias = [x.strip() for x in (cc or "").split(";") if x.strip()]
    recs = (Recip * (1 + len(copias)))()
    recs[0] = Recip(0, 1, para, f"SMTP:{para}", 0, None)       # MAPI_TO
    for n, x in enumerate(copias, 1):
        recs[n] = Recip(0, 2, x, f"SMTP:{x}", 0, None)          # MAPI_CC
    lista = [Path(a) for a in (anexo if isinstance(anexo, (list, tuple))
                               else [anexo])]
    arqs = (Arq * len(lista))()
    for n, a in enumerate(lista):
        arqs[n] = Arq(0, 0, 0xFFFFFFFF, str(a.resolve()), a.name, None)
    msg = Msg(0, assunto, texto, None, None, None, 0, None,
              len(recs), recs, len(lista),
              ctypes.cast(arqs, POINTER(Arq)))
    flags = 0x1 | (0x8 if com_janela else 0)       # LOGON_UI | DIALOG
    return fn(0, 0, ctypes.byref(msg), flags, 0)


def cliente_de_email_padrao() -> str:
    """O programa de e-mail que o Windows usa no 'Enviar para' (Simple
    MAPI). "" quando nao da para saber."""
    try:
        import winreg                                   # noqa: PLC0415
    except ImportError:
        return ""
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, r"Software\Clients\Mail") as k:
                v = winreg.QueryValueEx(k, "")[0]
                if v:
                    return str(v)
        except OSError:
            continue
    return ""


def _mapi_disponivel(outlook_sem_conta=False) -> bool:
    """Da para usar o e-mail padrao do Windows? Se o padrao for o Outlook
    classico e ele esta sem conta, nao: abriria o assistente de perfil."""
    try:
        import ctypes                                   # noqa: PLC0415
        if not hasattr(ctypes.WinDLL("mapi32.dll"), "MAPISendMailW"):
            return False
    except Exception:                                   # noqa: BLE001
        return False
    if outlook_sem_conta and \
            cliente_de_email_padrao().strip().lower() == "microsoft outlook":
        return False
    return True


def _abrir_na_web(para, assunto, texto, cc=""):
    """O e-mail pronto no Outlook na Web (a conta Microsoft 365 da pessoa,
    no navegador): so clicar em Enviar. Sem anexo - o PDF fica na pasta."""
    import webbrowser                                   # noqa: PLC0415
    from urllib.parse import quote, urlencode           # noqa: PLC0415
    url = ("https://outlook.office.com/mail/deeplink/compose?"
           + urlencode({"to": para, **({"cc": ",".join(x.strip() for x in cc.split(";")
                              if x.strip())} if cc else {}),
                        "subject": assunto, "body": texto},
                       quote_via=quote))
    return webbrowser.open(url, new=2)


ERROS_MAPI = {1: "cancelado", 2: "falha geral", 3: "sem login no e-mail",
              11: "anexo não encontrado", 26: "MAPI não suportado"}


def enviar(itens, revisar=False, log=None) -> dict:
    """
    Manda a parcial de cada um. Tenta, nesta ordem:
      1. Outlook classico (envia direto ou abre para revisar);
      2. o aplicativo de e-mail padrao do Windows (Simple MAPI - serve o
         novo Outlook): abre cada e-mail pronto, com o PDF anexado, e a
         pessoa so clica em Enviar;
      3. Outlook na Web (navegador): uma aba por pessoa com o e-mail pronto
         (numeros no corpo; o PDF fica na pasta, para anexar se quiser);
      4. .eml ao lado dos PDFs (dois cliques abre o e-mail pronto).
    Devolve {enviados, abertos, eml, erros, avisos, pasta, metodo}.
    """
    saida = {"enviados": [], "abertos": [], "eml": [], "erros": [],
             "avisos": [], "metodo": "",
             "pasta": str(anexos_de(itens[0])[0].parent) if itens else ""}
    if not itens:
        return saida
    ol, motivo = _outlook_pronto()
    if ol is not None:
        saida["metodo"] = "Outlook"
    else:
        saida["avisos"].append(f"Outlook: {motivo}.")
        if _mapi_disponivel(outlook_sem_conta="sem conta" in motivo):
            saida["metodo"] = "MAPI"
        else:
            saida["metodo"] = "WEB"     # Outlook na Web, no navegador
    falhou_mapi = False
    for it in itens:
        p = it["pessoa"]
        if saida["metodo"] == "Outlook":
            try:
                m = ol.CreateItem(0)
                m.To = p["email"]
                if p.get("cc"):         # o chefe vai sempre em copia
                    m.CC = p["cc"]
                m.Subject = it["assunto"]
                m.HTMLBody = it["html"]
                for anexo in anexos_de(it):
                    m.Attachments.Add(str(anexo.resolve()))
                if revisar:
                    m.Display(False)
                    saida["abertos"].append(p["nome"])
                else:
                    m.Send()
                    saida["enviados"].append(p["nome"])
                continue
            except Exception as erro:                   # noqa: BLE001
                saida["erros"].append(f"{p['nome']}: {_motivo_outlook(erro)}")
        elif saida["metodo"] == "MAPI" and not falhou_mapi:
            try:
                r = _mapi_enviar(p["email"], it["assunto"],
                                 it.get("texto") or "", anexos_de(it),
                                 com_janela=True, cc=p.get("cc") or "")
            except Exception as erro:                   # noqa: BLE001
                r = str(erro)
            if r == 0:
                saida["abertos"].append(p["nome"])
                continue
            if r == 1:                  # a pessoa cancelou esse e-mail
                saida["erros"].append(f"{p['nome']}: cancelado")
                continue
            falhou_mapi = True          # nao adianta insistir nos outros
            saida["avisos"].append(
                "E-mail padrão do Windows: "
                + (ERROS_MAPI.get(r, f"erro {r}") if isinstance(r, int)
                   else r) + ".")
        elif saida["metodo"] == "WEB":
            try:
                if _abrir_na_web(p["email"], it["assunto"],
                                 it.get("texto") or "", p.get("cc") or ""):
                    saida["abertos"].append(p["nome"])
                    import time                         # noqa: PLC0415
                    time.sleep(0.8)     # uma aba de cada vez no navegador
                    continue
            except Exception as erro:                   # noqa: BLE001
                saida["erros"].append(f"{p['nome']}: {erro}")
        try:
            saida["eml"].append(str(gravar_eml(
                it, Path(it.get("eml") or anexos_de(it)[0].with_suffix(
                    ".eml")))))
        except OSError as erro:
            saida["erros"].append(f"{p['nome']}: {erro}")
    # o Outlook aberto pelo programa (escondido) as vezes deixa o e-mail
    # na Caixa de Saida ate alguem abrir o Outlook: forca o envio agora
    if saida["metodo"] == "Outlook" and saida["enviados"]:
        try:
            ol.GetNamespace("MAPI").SendAndReceive(False)
        except Exception:                               # noqa: BLE001
            pass
    return saida
