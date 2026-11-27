"""
COBRAR NO WHATSAPP (06/11, Alexandre: "coloque o botao de cobrar no
whatsapp para a assistente ir enviando a cobranca cliente a cliente")

Farol de Inadimplencia > botao "Cobrar no WhatsApp": a FILA dos clientes
inadimplentes (do maior atraso em R$ para o menor). Para cada cliente a
janela mostra os titulos vencidos e a mensagem pronta (editavel); "Abrir no
WhatsApp" abre a conversa no WhatsApp do computador com o texto escrito - a
assistente confere, aperta Enter la e clica "Enviado, proximo".

Nao usa API nem robo: quem envia e a assistente (o WhatsApp bloqueia
numero que dispara mensagem automatica em massa). So texto: o boleto/PDF,
se precisar, ela arrasta para a conversa.

Diario (so acrescenta): RELATORIOS/_COBRANCA_WHATSAPP/
COBRANCA_<MAQUINA>.csv - quando; maquina; usuario; cliente; nome;
telefone; em_atraso; titulos; acao (ENVIADO, PULADO). A fila mostra quem
ja foi cobrado hoje e nos ultimos dias.
"""
from __future__ import annotations

import csv
import os
import platform
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

PASTA = Path("RELATORIOS") / "_COBRANCA_WHATSAPP"
CAMPOS_CSV = ("quando", "maquina", "usuario", "cliente", "nome", "telefone",
              "em_atraso", "titulos", "acao")
DIAS_RECENTE = 7          # cobrado ha menos de 7 dias: aparece na fila
MODELO = (
    "Olá, {cliente}! Tudo bem?\n"
    "Aqui é do financeiro da BAP AUTOPARTS.\n\n"
    "Consta em aberto na sua conta {qtd_txt}, total de *{total}*:\n"
    "{titulos}\n\n"
    "Podemos ajudar a regularizar? Se o pagamento já foi feito, por favor "
    "nos envie o comprovante por aqui e desconsidere esta mensagem.\n"
    "Obrigado!")


def texto(v) -> str:
    return "" if v is None else str(v).strip()


def br(v, c=2) -> str:
    s = f"{float(v or 0):,.{c}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def moeda(v) -> str:
    return f"R$ {br(v)}"


def maquina() -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_",
                  os.environ.get("COMPUTERNAME") or platform.node() or "PC")


# ------------------------------------------------------------- telefone
def celular(v) -> tuple[str, str]:
    """(numero para o WhatsApp '5598991181527', aviso). O primeiro numero
    do campo que pareca telefone; 0 do DDD sai; celular de 8 digitos
    ganha o 9. Numero falso (99 99999999) ou curto: vazio + aviso."""
    for parte in re.split(r"[/;,|]| e ", texto(v)) or [""]:
        d = re.sub(r"\D", "", parte)
        if d.startswith("55") and len(d) >= 12:
            d = d[2:]
        d = d.lstrip("0")
        if len(d) < 10:
            continue
        ddd, num = d[:2], d[2:]
        if len(num) == 8 and num[0] in "6789":
            num = "9" + num
        if len(set(num[1:])) <= 1:
            return "", "telefone inválido (repetido)"
        if len(num) == 8:
            return f"55{ddd}{num}", "telefone fixo: pode não ter WhatsApp"
        if len(num) == 9:
            return f"55{ddd}{num}", ""
    return "", "sem telefone no cadastro"


def fone_bonito(n: str) -> str:
    d = n[2:] if n.startswith("55") else n
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return n


# ------------------------------------------------------------- a fila
_DOC_INICIAL = re.compile(r"^\s*(?=(?:[.\-/\s]*\d){6})[\d.\-/\s]+")


def nome_sem_documento(nome) -> str:
    """Nome sem CPF/CNPJ (nem pedaco com 6+ digitos, ponto, traco ou barra)
    no comeco. MEI: '12.345.678 FULANO' -> 'FULANO' (RN-POS-004)."""
    return _DOC_INICIAL.sub("", texto(nome)).strip()


def nome_saudacao(nome) -> str:
    """Nome para a saudacao (sem documento no comeco)."""
    return nome_sem_documento(nome)


def fila(farol: dict, nomes=None) -> list[dict]:
    """Os clientes INADIMPLENTES do Farol de Inadimplencia com os titulos
    vencidos (do maior atraso em R$ para o menor). nomes: {cod: nome para
    a mensagem} (fantasia do cadastro), opcional."""
    tc = {t["titulo"]: t for t in farol.get("tabelas") or []}
    c, t = tc.get("Por cliente"), tc.get("Títulos")
    if not c or not t:
        return []
    ic = {x["nome"]: i for i, x in enumerate(c["colunas"])}
    it = {x["nome"]: i for i, x in enumerate(t["colunas"])}
    tits = {}
    for l in t["linhas"]:
        if l[it["SITUAÇÃO"]] != "VENCIDO":
            continue
        tits.setdefault(l[it["CLIENTE"]], []).append({
            "nf": texto(l[it["NF"]]), "parc": texto(l[it["PARC."]]),
            "venc": l[it["VENCIMENTO"]], "dias": l[it["DIAS ATRASO"]] or 0,
            "saldo": l[it["SALDO"]] or 0.0})
    saida = []
    for l in c["linhas"]:
        if l[ic["SITUAÇÃO"]] != "INADIMPLENTE":
            continue
        cod = texto(l[ic["CLIENTE"]])
        num, aviso = celular(l[ic["TELEFONE"]])
        ts = sorted(tits.get(cod, []), key=lambda x: -x["dias"])
        saida.append({
            "cod": cod, "nome": texto(l[ic["NOME"]]),
            "nome_msg": nome_saudacao(
                (nomes or {}).get(cod.split("-")[0])) or nome_saudacao(
                l[ic["NOME"]]) or "cliente",
            "cidade": texto(l[ic["CIDADE"]]), "uf": texto(l[ic["UF"]]),
            "vendedor": texto(l[ic["VENDEDOR"]]),
            "supervisor": texto(l[ic["SUPERVISOR"]]),
            "em_atraso": l[ic["EM ATRASO"]] or 0.0,
            "maior": l[ic["MAIOR ATRASO"]] or 0,
            "telefone_cad": texto(l[ic["TELEFONE"]]), "whatsapp": num,
            "aviso": aviso, "titulos": ts})
    saida.sort(key=lambda x: -x["em_atraso"])
    return saida


def _venc(v) -> str:
    return f"{v:%d/%m/%Y}" if hasattr(v, "strftime") else texto(v)


def mensagem(cli: dict, modelo: str = MODELO) -> str:
    ts = cli["titulos"]
    linhas = [f"• NF {x['nf']}" + (f"/{x['parc']}" if x["parc"] else "")
              + f" · venc. {_venc(x['venc'])} · {moeda(x['saldo'])}"
              for x in ts[:12]]
    if len(ts) > 12:
        linhas.append(f"• e mais {len(ts) - 12} título(s)")
    nome = " ".join(w.lower() if w.lower() in ("da", "das", "de", "do",
                                               "dos", "e") else
                    w.capitalize() for w in (nome_saudacao(cli["nome_msg"]) or "cliente").split())
    total = sum(x["saldo"] for x in ts) or cli["em_atraso"]
    return modelo.format(
        cliente=nome, total=moeda(total), titulos="\n".join(linhas),
        qtd_txt=(f"{len(ts)} título vencido" if len(ts) == 1
                 else f"{len(ts)} títulos vencidos"))


def link(numero: str, msg: str, app=True) -> str:
    """whatsapp://send (abre o WhatsApp do computador) ou wa.me (navegador)."""
    if app:
        return f"whatsapp://send?phone={numero}&text={quote(msg)}"
    return f"https://wa.me/{numero}?text={quote(msg)}"


def abrir(numero: str, msg: str) -> None:
    """Abre a conversa no WhatsApp instalado; sem ele, no navegador
    (WhatsApp Web)."""
    try:
        os.startfile(link(numero, msg))                 # type: ignore[attr]
        return
    except (AttributeError, OSError):
        pass
    import webbrowser                                   # noqa: PLC0415
    webbrowser.open(link(numero, msg, app=False))


# ------------------------------------------------------------- o diario
def pasta(raiz) -> Path:
    return Path(raiz) / PASTA


def registrar(raiz, cli: dict, acao: str, numero: str = "",
              agora=None) -> None:
    p_ = pasta(raiz)
    p_.mkdir(parents=True, exist_ok=True)
    arq = p_ / f"COBRANCA_{maquina()}.csv"
    novo = not arq.exists()
    with open(arq, "a", encoding="utf-8-sig" if novo else "utf-8",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, delimiter=";")
        if novo:
            w.writeheader()
        w.writerow({"quando": (agora or datetime.now()).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    "maquina": maquina(),
                    "usuario": os.environ.get("USERNAME") or "",
                    "cliente": cli["cod"], "nome": cli["nome"],
                    "telefone": numero or cli.get("whatsapp") or "",
                    "em_atraso": f"{cli['em_atraso']:.2f}",
                    "titulos": len(cli["titulos"]), "acao": acao})


def historico(raiz) -> dict:
    """{cliente: (quando, acao)} - o ultimo registro de cada cliente."""
    return {c: v[:2] for c, v in historico_origem(raiz).items()}


def situacao(hist: dict, cod: str, hoje=None) -> str:
    """'' (a cobrar), 'ENVIADO HOJE', 'ENVIADO dd/mm' ou 'PULADO HOJE'."""
    hoje = hoje or date.today()
    q, a = hist.get(cod, ("", ""))
    if not q:
        return ""
    try:
        d = datetime.strptime(q[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""
    if a == "PULADO":
        return "PULADO HOJE" if d == hoje else ""
    if d == hoje:
        return "ENVIADO HOJE"
    if (hoje - d).days < DIAS_RECENTE:
        return f"ENVIADO {d:%d/%m}"
    return ""


# ------------------------------------------------------------- o site (T-0017)
CAMPOS_WEB = CAMPOS_CSV + ("id",)
ARQ_WEB = "COBRANCA_WEB.csv"


def _iso(v) -> str:
    if hasattr(v, "strftime"):
        return f"{v:%Y-%m-%d}"
    return texto(v)


def historico_origem(raiz) -> dict:
    """{cliente: (quando, acao, maquina)}: como historico(), mas com a
    maquina do registro (WEB = feito no site). historico() nao muda."""
    ult = {}
    p_ = pasta(raiz)
    if not p_.exists():
        return ult
    for arq in sorted(p_.glob("COBRANCA_*.csv")):
        try:
            with open(arq, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f, delimiter=";"):
                    c = texto(r.get("cliente"))
                    q = texto(r.get("quando"))
                    if c and q >= ult.get(c, ("",))[0]:
                        ult[c] = (q, texto(r.get("acao")),
                                  texto(r.get("maquina")))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
    return ult


def _gerado_em(hoje) -> str:
    from datetime import timedelta, timezone               # noqa: PLC0415
    tz = timezone(timedelta(hours=-4))                     # Manaus
    if isinstance(hoje, datetime):
        d = hoje.astimezone(tz) if hoje.tzinfo else hoje.replace(tzinfo=tz)
    else:
        d = datetime.now(tz)
    return d.isoformat(timespec="seconds")


def pacote_web(farol: dict, nomes, hist: dict, hoje=None, *,
               web_ate_seq: int = 0, web_epoca: str = "",
               gerado_em: str = "") -> dict:
    """Bloco `cobranca` do contrato (§10.6.3), sem telefone cadastral.
    hist: historico_origem() (tuplas de 3) ou historico() (tuplas de 2,
    origem PC). gerado_em, web_epoca e web_ate_seq vem do robo (hora da
    rodada, epoca do diario e maior seq ja gravado, §10.6.3). Sem gerado_em,
    usa `hoje` (datetime) ou agora."""
    itens = []
    for it in fila(farol, nomes):
        msg = mensagem(it)
        h = (hist or {}).get(it["cod"])
        ult = None
        if h and h[0]:
            org = "WEB" if len(h) > 2 and h[2].upper() == "WEB" else "PC"
            ult = {"quando": h[0], "acao": h[1], "origem": org}
        itens.append({
            "cod": it["cod"], "nome": nome_sem_documento(it["nome"]),
            "nome_msg": it["nome_msg"],
            "cidade": it["cidade"], "uf": it["uf"],
            "vendedor": it["vendedor"], "supervisor": it["supervisor"],
            "em_atraso": float(it["em_atraso"]), "maior": int(it["maior"]),
            "whatsapp": it["whatsapp"], "aviso": it["aviso"],
            "titulos": [{"nf": x["nf"], "parc": x["parc"],
                         "venc": _iso(x["venc"]), "dias": int(x["dias"]),
                         "saldo": float(x["saldo"])}
                        for x in it["titulos"]],
            "mensagem": msg, "ultimo": ult})
    return {"gerado_em": gerado_em or _gerado_em(hoje),
            "web_epoca": str(web_epoca), "web_ate_seq": int(web_ate_seq),
            "dias_recente": DIAS_RECENTE,
            "modelo": MODELO, "fila": itens}


def importar_web(raiz, linhas, nomes=None) -> int:
    """Acrescenta ao COBRANCA_WEB.csv os registros do diario do site (§10.6.7).
    Pula `id` ja gravado (idempotente). Erro de disco levanta excecao."""
    p_ = pasta(raiz)
    arq = p_ / ARQ_WEB
    vistos = set()
    if arq.exists():
        with open(arq, encoding="utf-8-sig", newline="") as f:
            vistos = {texto(r.get("id")) for r in
                      csv.DictReader(f, delimiter=";")}
    novas = []
    for r in linhas or []:
        i = texto(r.get("id"))
        if not i or i in vistos:
            continue
        vistos.add(i)
        cod = texto(r.get("cliente"))
        novas.append({
            "quando": texto(r.get("quando")), "maquina": "WEB",
            "usuario": texto(r.get("usuario")), "cliente": cod,
            "nome": (nomes or {}).get(cod, ""),
            "telefone": texto(r.get("telefone")),
            "em_atraso": f"{float(r.get('em_atraso') or 0):.2f}",
            "titulos": int(r.get("titulos") or 0),
            "acao": texto(r.get("acao")), "id": i})
    if not novas:
        return 0
    p_.mkdir(parents=True, exist_ok=True)
    novo = not arq.exists()
    with open(arq, "a", encoding="utf-8-sig" if novo else "utf-8",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_WEB, delimiter=";")
        if novo:
            w.writeheader()
        w.writerows(novas)
    return len(novas)


# ------------------------------------------------------------- a janela
def janela(pai, farol: dict, raiz, nomes=None):
    """A janela da cobranca, cliente a cliente."""
    import tkinter as tk                                # noqa: PLC0415
    from tkinter import messagebox, ttk                 # noqa: PLC0415
    import bap_visual as bv                             # noqa: PLC0415

    clis = fila(farol, nomes)
    hist = historico(raiz)
    w = tk.Toplevel(pai)
    w.title("Cobrar no WhatsApp")
    w.configure(background=bv.FUNDO)
    larg = min(1320, w.winfo_screenwidth() - 60)
    alt = min(860, w.winfo_screenheight() - 80)
    w.geometry(f"{larg}x{alt}+30+10")
    total = sum(c["em_atraso"] for c in clis)
    cab = bv.Cabecalho(w, "Inadimplência", "Cobrar no WhatsApp",
                       f"{len(clis)} clientes inadimplentes · "
                       f"{moeda(total)} em atraso · a assistente envia "
                       "cliente a cliente pelo WhatsApp do computador")
    cab.pack(fill="x")
    cab.botao("Fechar", w.destroy)
    tk.Frame(w, background=bv.VERDE, height=2).pack(fill="x")
    corpo = tk.Frame(w, background=bv.FUNDO)
    corpo.pack(fill="both", expand=True, padx=14, pady=10)

    # ---- a fila (esquerda)
    esq = tk.Frame(corpo, background=bv.CARTAO, highlightthickness=1,
                   highlightbackground=bv.CINZA_LINHA, width=470)
    esq.pack(side="left", fill="y")
    esq.pack_propagate(False)
    topo = tk.Frame(esq, background=bv.CARTAO)
    topo.pack(fill="x", padx=10, pady=(8, 4))
    tk.Label(topo, text="FILA DE COBRANÇA", background=bv.CARTAO,
             foreground=bv.TEXTO, font=bv.fonte(9, "bold")).pack(side="left")
    so_pend = tk.BooleanVar(value=False)
    ttk.Checkbutton(topo, text="só quem falta cobrar", variable=so_pend,
                    command=lambda: preencher()).pack(side="right")
    cols = ("st", "nome", "atraso", "dias")
    tv = ttk.Treeview(esq, columns=cols, show="headings", selectmode="browse")
    for c_, t_, l_, a_ in (("st", "SITUAÇÃO", 116, "w"),
                           ("nome", "CLIENTE", 178, "w"),
                           ("atraso", "EM ATRASO", 92, "e"),
                           ("dias", "DIAS", 46, "e")):
        tv.heading(c_, text=t_)
        tv.column(c_, width=l_, anchor=a_, stretch=c_ == "nome")
    tv.tag_configure("enviado", foreground="#2F7D32")
    tv.tag_configure("pulado", foreground="#8A5A00")
    tv.tag_configure("semfone", foreground="#B3261E")
    tv.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ---- o cliente (direita)
    dir_ = tk.Frame(corpo, background=bv.FUNDO)
    dir_.pack(side="left", fill="both", expand=True, padx=(12, 0))
    card = tk.Frame(dir_, background=bv.CARTAO, highlightthickness=1,
                    highlightbackground=bv.CINZA_LINHA)
    card.pack(fill="x")
    lb_nome = tk.Label(card, background=bv.CARTAO, foreground=bv.TEXTO,
                       font=bv.fonte(13, "bold"), anchor="w")
    lb_nome.pack(fill="x", padx=12, pady=(10, 0))
    lb_info = tk.Label(card, background=bv.CARTAO, foreground=bv.SUAVE,
                       font=bv.fonte(9), anchor="w", justify="left")
    lb_info.pack(fill="x", padx=12)
    fl = tk.Frame(card, background=bv.CARTAO)
    fl.pack(fill="x", padx=12, pady=(6, 10))
    tk.Label(fl, text="WhatsApp", background=bv.CARTAO, foreground=bv.SUAVE,
             font=bv.fonte(8)).pack(side="left")
    v_fone = tk.StringVar()
    ttk.Entry(fl, textvariable=v_fone, width=22).pack(side="left",
                                                      padx=(6, 8))
    lb_aviso = tk.Label(fl, background=bv.CARTAO, foreground="#B3261E",
                        font=bv.fonte(8, "bold"))
    lb_aviso.pack(side="left")
    tk.Label(dir_, text="TÍTULOS VENCIDOS", background=bv.FUNDO,
             foreground=bv.SUAVE, font=bv.fonte(8, "bold"),
             anchor="w").pack(fill="x", pady=(10, 2))
    tt = ttk.Treeview(dir_, columns=("nf", "venc", "dias", "saldo"),
                      show="headings", height=6)
    for c_, t_, l_, a_ in (("nf", "NF / PARC.", 150, "w"),
                           ("venc", "VENCIMENTO", 110, "center"),
                           ("dias", "DIAS ATRASO", 100, "e"),
                           ("saldo", "SALDO", 130, "e")):
        tt.heading(c_, text=t_)
        tt.column(c_, width=l_, anchor=a_)
    tt.pack(fill="x")
    tk.Label(dir_, text="MENSAGEM (pode editar antes de abrir)",
             background=bv.FUNDO, foreground=bv.SUAVE,
             font=bv.fonte(8, "bold"), anchor="w").pack(fill="x",
                                                        pady=(10, 2))
    tx = tk.Text(dir_, height=12, wrap="word", font=bv.fonte(10),
                 relief="solid", borderwidth=1)
    tx.pack(fill="both", expand=True)
    bts = tk.Frame(dir_, background=bv.FUNDO)
    bts.pack(fill="x", pady=(10, 0))
    lb_pos = tk.Label(bts, background=bv.FUNDO, foreground=bv.SUAVE,
                      font=bv.fonte(9))
    lb_pos.pack(side="left")
    estado = {"i": 0, "vis": []}

    def preencher():
        tv.delete(*tv.get_children())
        estado["vis"] = [k for k, c in enumerate(clis)
                         if not so_pend.get() or not situacao(
                             hist, c["cod"]).startswith(("ENVIADO HOJE",
                                                         "PULADO"))]
        for k in estado["vis"]:
            c = clis[k]
            st = situacao(hist, c["cod"]) or (
                "SEM WHATSAPP" if not c["whatsapp"] else "A COBRAR")
            tag = ("enviado" if st.startswith("ENVIADO") else
                   "pulado" if st.startswith("PULADO") else
                   "semfone" if st == "SEM WHATSAPP" else "")
            tv.insert("", "end", iid=str(k), tags=(tag,), values=(
                st, c["nome"], br(c["em_atraso"]), c["maior"]))
        if estado["vis"]:
            mostrar(estado["vis"][0])

    def mostrar(k):
        estado["i"] = k
        c = clis[k]
        if tv.exists(str(k)):
            tv.selection_set(str(k))
            tv.see(str(k))
        lb_nome.configure(text=f"{c['cod']} · {c['nome_msg']}")
        lb_info.configure(text=(
            f"{c['cidade']}/{c['uf']} · vendedor {c['vendedor']} · "
            f"{len(c['titulos'])} títulos vencidos · {moeda(c['em_atraso'])}"
            f" em atraso · maior atraso {c['maior']} dias\n"
            f"telefone no cadastro: {c['telefone_cad'] or '—'}"))
        v_fone.set(fone_bonito(c["whatsapp"]) if c["whatsapp"] else "")
        lb_aviso.configure(text=c["aviso"])
        tt.delete(*tt.get_children())
        for x in c["titulos"]:
            tt.insert("", "end", values=(
                x["nf"] + (f" / {x['parc']}" if x["parc"] else ""),
                _venc(x["venc"]), x["dias"], moeda(x["saldo"])))
        tx.delete("1.0", "end")
        tx.insert("1.0", mensagem(c))
        pos = estado["vis"].index(k) + 1 if k in estado["vis"] else 0
        env = sum(1 for c_ in clis
                  if situacao(hist, c_["cod"]) == "ENVIADO HOJE")
        lb_pos.configure(text=f"cliente {pos} de {len(estado['vis'])} · "
                              f"{env} enviados hoje")

    def numero():
        d = re.sub(r"\D", "", v_fone.get())
        if not d:
            return ""
        return d if d.startswith("55") and len(d) >= 12 else "55" + d.lstrip(
            "0")

    def abrir_wpp():
        n = numero()
        if len(n) < 12:
            messagebox.showwarning("Cobrar no WhatsApp", "Digite o WhatsApp "
                                   "do cliente com o DDD.", parent=w)
            return
        abrir(n, tx.get("1.0", "end").strip())

    def proximo(acao=None):
        c = clis[estado["i"]]
        if acao:
            registrar(raiz, c, acao, numero())
            hist[c["cod"]] = (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                              acao)
            st = situacao(hist, c["cod"])
            if tv.exists(str(estado["i"])):
                tv.item(str(estado["i"]), values=(
                    st, c["nome"], br(c["em_atraso"]), c["maior"]),
                    tags=("enviado" if acao == "ENVIADO" else "pulado",))
        vis = estado["vis"]
        j = vis.index(estado["i"]) + 1 if estado["i"] in vis else 0
        if j < len(vis):
            mostrar(vis[j])
        else:
            mostrar(estado["i"])

    def anterior():
        vis = estado["vis"]
        j = vis.index(estado["i"]) - 1 if estado["i"] in vis else 0
        if j >= 0:
            mostrar(vis[j])

    tk.Button(bts, text="Abrir no WhatsApp", command=abrir_wpp,
              background="#25D366", foreground="#FFFFFF",
              activebackground="#1EBE5A", relief="flat",
              font=bv.fonte(10, "bold"), padx=16, pady=6).pack(
        side="right", padx=(8, 0))
    ttk.Button(bts, text="Enviado, próximo  ▶",
               command=lambda: proximo("ENVIADO")).pack(side="right",
                                                        padx=(8, 0))
    ttk.Button(bts, text="Pular", command=lambda: proximo("PULADO")).pack(
        side="right", padx=(8, 0))
    ttk.Button(bts, text="◀ Anterior", command=anterior).pack(side="right")
    tv.bind("<<TreeviewSelect>>", lambda _e: (
        mostrar(int(tv.selection()[0])) if tv.selection()
        and int(tv.selection()[0]) != estado["i"] else None))
    preencher()
    if not clis:
        lb_nome.configure(text="Nenhum cliente inadimplente.")
    return w
