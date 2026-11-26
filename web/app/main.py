"""Rotas da BAP Central web. Uso: uvicorn app.main:criar_app --factory"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import VERSAO, cobranca, config, edicoes, pacotes, render, tabelas
from .usuarios import PERFIS, Erro, Usuarios, MAX_ERROS

log = logging.getLogger("bap_web")
AQUI = Path(__file__).parent
MANAUS = ZoneInfo("America/Manaus")
VERES = ("admin", "diretor", "gerente")          # [SUPOSIÇÃO] os 3 veem o painel
RELATORIO = ("vc_painel", "Painel Executivo")
FORM_MAX = 16 * 1024
ISENTAS_FUSO = ("/saude", "/static", "/api/pacote", "/api/cobranca", "/api/edicoes")   # saúde e robô seguem; as telas param


def hoje_local() -> date:
    return date.today()


def fuso_motivo() -> str | None:
    """ADR 0001 §4.1: com o fuso errado o dia útil e a projeção saem errados; telas 503."""
    tz = os.environ.get("TZ")
    if tz != config.TZ_ALVO:
        return f"TZ={tz or 'não definido'}; esperado {config.TZ_ALVO}"
    if hoje_local() != datetime.now(MANAUS).date():
        return "a data do servidor difere da data de Manaus"
    return None


class Redireciona(Exception):
    def __init__(self, para):
        self.para = para


def fmt_manaus(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=MANAUS)
    return d.astimezone(MANAUS).strftime("%d/%m/%Y %H:%M")


def hhmm(iso: str | None) -> str:
    """"hh:mm" se for de hoje (Manaus); senão "dd/mm hh:mm"."""
    f = fmt_manaus(iso)
    return f[-5:] if f[:10] == cobranca.agora().strftime("%d/%m/%Y") else f[:5] + " " + f[-5:]


def criar_app() -> FastAPI:
    cfg = config.carregar()
    cfg.dados.mkdir(parents=True, exist_ok=True)
    usuarios = Usuarios(cfg)
    ultimo = pacotes.Ultimo(cfg.dados)
    modelos = Jinja2Templates(directory=str(AQUI / "templates"))
    modelos.env.autoescape = True
    modelos.env.filters["manaus"] = fmt_manaus
    modelos.env.filters["hhmm"] = hhmm
    modelos.env.filters["fone"] = cobranca.fone_bonito
    modelos.env.globals["ocultas"] = tabelas.colunas_ocultas      # T-0020: coluna que só repete outra
    modelos.env.globals["datas_proximas"] = render.datas_proximas  # T-0020: uma data só
    diario = cobranca.Diario(cfg.dados)
    diario.limpar()                                   # §10.6.5: também quando o app sobe
    fila = edicoes.Fila(cfg.dados)                    # T-0021: edições da web, só acréscimo

    app = FastAPI(title="BAP Central", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=cfg.segredo, session_cookie="bap_sessao",
                       max_age=8 * 3600, same_site="lax", https_only=cfg.cookie_seguro)
    app.mount("/static", StaticFiles(directory=str(AQUI / "static")), name="static")

    @app.middleware("http")
    async def cabecalhos(request: Request, call_next):
        motivo = fuso_motivo()
        if motivo and not request.url.path.startswith(ISENTAS_FUSO):
            r = HTMLResponse(
                "<!doctype html><meta charset=utf-8><title>Indisponível</title>"
                "<h1>Indisponível</h1><p>Fuso do servidor fora do padrão "
                "(America/Manaus). Avise o administrador.</p>", status_code=503)
        else:
            r = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["X-Frame-Options"] = "DENY"
        r.headers["Referrer-Policy"] = "same-origin"
        r.headers["Cache-Control"] = "no-store"
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        return r

    @app.exception_handler(Redireciona)
    async def _redir(request, exc):
        return RedirectResponse(exc.para, status_code=303)

    # ------------------------------------------------------------ helpers
    def csrf(request: Request) -> str:
        t = request.session.get("csrf")
        if not t:
            t = request.session["csrf"] = secrets.token_urlsafe(24)
        return t

    def usuario(request: Request, perfis=None, livre_troca=False) -> dict:
        u = usuarios.obter(request.session.get("u", ""))
        if not u or not u["ativo"] or request.session.get("s") != u["sessao"]:
            request.session.pop("u", None)
            raise Redireciona("/login")
        if u["trocar_senha"] and not livre_troca:
            raise Redireciona("/senha")
        if perfis and u["perfil"] not in perfis:
            raise PermissionError
        return u

    @app.exception_handler(PermissionError)
    async def _nega(request, exc):
        return pagina(request, "erro.html", status=403, u=None,
                      msg="Você não tem acesso a esta página.")

    def pagina(request, nome, status=200, u="auto", **ctx):
        if u == "auto":
            u = usuarios.obter(request.session.get("u", ""))
        info = ultimo.get()
        ctx.update(usuario=u, csrf=csrf(request), versao=VERSAO, indisponivel=render.INDISPONIVEL,
                   gerado_em=info["gerado_em"] if info else None)
        return modelos.TemplateResponse(request, nome, ctx, status_code=status)

    async def formulario(request: Request) -> dict:
        corpo = b""
        async for parte in request.stream():
            corpo += parte
            if len(corpo) > FORM_MAX:
                break
        d = {k: v[0] for k, v in parse_qs(corpo[:FORM_MAX].decode("utf-8", "replace"),
                                           keep_blank_values=True).items()}
        if not hmac.compare_digest(d.get("csrf", "").encode(), str(request.session.get("csrf", "x")).encode()):
            raise PermissionError
        return d

    # ------------------------------------------------------------ saúde
    @app.get("/saude")
    async def saude():
        info = ultimo.get()
        tz = os.environ.get("TZ")
        motivo = fuso_motivo()
        return {"status": "ok", "versao": VERSAO,
                "hora_manaus": datetime.now(MANAUS).strftime("%Y-%m-%d %H:%M:%S"),
                "tz": tz, "tz_ok": motivo is None, "telas_bloqueadas": motivo is not None,
                "motivo": motivo,
                "ultimo_pacote": info["gerado_em"] if info else None}

    # ------------------------------------------------------------ login
    @app.get("/login", response_class=HTMLResponse)
    async def login_get(request: Request):
        return pagina(request, "login.html", erro=None)

    @app.post("/login")
    async def login_post(request: Request):
        try:
            f = await formulario(request)
        except PermissionError:
            return pagina(request, "login.html", status=400, erro="Sessão expirada. Tente de novo.")
        u, motivo = usuarios.autenticar(f.get("usuario", ""), f.get("senha", ""))
        if u:
            request.session.clear()
            request.session["u"] = u["login"]
            request.session["s"] = u["sessao"]
            csrf(request)
            cobranca.registrar_acesso(cfg.dados, u["login"], "-", "-", "login")
            return RedirectResponse("/", status_code=303)
        msg = ("Usuário ou senha inválidos, ou acesso bloqueado após %d tentativas erradas. "
               "Tente em 15 minutos ou peça ao administrador." % MAX_ERROS)
        return pagina(request, "login.html", status=401, erro=msg)

    @app.post("/sair")
    async def sair(request: Request):
        try:
            await formulario(request)
            login = request.session.get("u")
            if login:
                usuarios.encerrar_sessoes(login)      # cookie copiado deixa de valer
        except PermissionError:
            pass
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/senha", response_class=HTMLResponse)
    async def senha_get(request: Request):
        u = usuario(request, livre_troca=True)
        return pagina(request, "senha.html", erro=None, obrigatoria=u["trocar_senha"])

    @app.post("/senha")
    async def senha_post(request: Request):
        u = usuario(request, livre_troca=True)
        f = await formulario(request)
        erro = None
        ok, _ = usuarios.autenticar(u["login"], f.get("atual", ""))
        if not ok:
            erro = "Senha atual incorreta."
        elif f.get("nova") != f.get("confirma"):
            erro = "A confirmação não confere."
        elif f.get("nova") == f.get("atual"):
            erro = "A nova senha precisa ser diferente da atual."
        else:
            try:
                usuarios.trocar_senha(u["login"], f.get("nova", ""), exigir_troca=False)
            except Erro as e:
                erro = str(e)
        if erro:
            return pagina(request, "senha.html", status=400, erro=erro, obrigatoria=u["trocar_senha"])
        request.session["s"] = usuarios.obter(u["login"])["sessao"]   # esta sessão segue; as outras caem
        return RedirectResponse("/", status_code=303)

    # ------------------------------------------------------------ home e relatórios
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        u = usuario(request)
        menu = [{"href": "/painel", "nome": RELATORIO[1]}] if u["perfil"] in VERES else []
        no_pacote = ((ultimo.get() or {}).get("relatorios")) or {}
        for rid, nome in render.farois_do_perfil(u["perfil"]):
            menu.append({"href": f"/farol/{rid}" if rid in no_pacote else "", "nome": nome})
        if u["perfil"] == "admin":
            menu.append({"href": "/usuarios", "nome": "Usuários"})
        menu.append({"href": "/senha", "nome": "Trocar senha"})
        return pagina(request, "home.html", menu=menu)

    @app.get("/painel", response_class=HTMLResponse)
    async def painel(request: Request, aba: str = "resultado", uf: str = ""):
        usuario(request, VERES)
        info = ultimo.get()
        rel = (info or {}).get("relatorios", {}).get(RELATORIO[0])
        abas = render.localizar_abas(rel) if rel else []
        if not abas:
            return pagina(request, "painel.html", abas=[], tela=None, aba=aba)
        atual = next((a for a in abas if a["chave"] == aba), abas[0])
        # T-0014: o filtro só escolhe a visão pronta do PC (por estado)
        escolhido = render.escolher_uf(atual, uf[:4] or None)
        return pagina(request, "painel.html", abas=abas, aba=atual["chave"],
                      tela=render.aba_para_tela(atual, escolhido),
                      filtros=render.filtros(atual), uf=escolhido or "")

    def rel_do(rid):
        rel = ((ultimo.get() or {}).get("relatorios") or {}).get(rid)
        return rel if isinstance(rel, dict) and rel.get("forma") == "farol" else None

    def consulta_de(request: Request) -> dict:
        c: dict = {}
        for k, v in request.query_params.multi_items():
            c.setdefault(k, []).append(v[:80])
        return c

    def farol_abas(request: Request, u: dict, rid: str, aba: str, uf: str):
        """Pedidos, Entregas e Visita (§10.7): Resumo e abas de tabela. Perfil e aba conferidos aqui."""
        perfil = u["perfil"]
        if aba in tabelas.chaves(rid) and not tabelas.ve_aba(rid, aba, perfil):
            raise PermissionError                       # aba fora do perfil = 403 (diretor só vê o Resumo)
        if aba not in tabelas.chaves(rid):
            if aba in [c for c, _ in cobranca.ABAS[1:]]:
                raise PermissionError                   # aba da Inadimplência pedida em outro farol
            aba = "resumo"
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba, "ver")
        nome = render.FAROIS[rid][0]
        rel = rel_do(rid)
        if not rel:
            return pagina(request, "farol.html", farol_nome=nome, rid=rid, tela=None, abas=[], aba="resumo")
        por_chave = {c: next((t for t in rel.get("tabelas") or [] if t.get("titulo") == tit), None)
                     for c, tit in tabelas.ABAS[rid]}
        com_aba = [(c, tit) for c, tit in tabelas.ABAS[rid] if por_chave[c] and tabelas.ve_aba(rid, c, perfil)]
        barra = [tabelas.RESUMO] + com_aba if com_aba else []
        ctx = dict(farol_nome=nome, rid=rid, abas=barra, aba=aba, noindex=aba != "resumo")
        ufs = render.recortes_farol(rel)
        uf_ok = uf.upper()[:2] if uf.upper()[:2] in ufs else ""
        topo = render.farol_para_tela(rel, (uf[:4] if aba == "resumo" else uf_ok) or None, rid)   # uma vez só
        if aba == "resumo":
            return pagina(request, "farol.html", tela=topo, **ctx)
        t = por_chave[aba]
        if not t:                                       # a aba ficou fora desta atualização do PC
            return pagina(request, "farol.html", tela=None, **ctx)
        consulta = consulta_de(request)
        solicitacao = bool(t.get("subabas"))
        subnomes, sub, juntas = [], None, []
        if solicitacao:                                 # Solicitação BAP: sem estado, sem cartões do Resumo (D5)
            ufs, uf_ok = [], ""
            try:
                sub = int(consulta.get("sub", ["0"])[0])
            except ValueError:
                sub = 0
            subnomes, tab = tabelas.subabas_para_tela(t, sub, consulta)
            sub = tab["sub"]
        else:
            tab = tabelas.tabela_para_tela(t, consulta, uf=uf_ok or None)
            sel = selecao(t, tab, consulta)              # um clique no pedido: as de baixo só com ele (PC)
            juntas = tabelas.juntas_para_tela(t, [sel] if sel is not None else tab["idxs"], uf_ok or None)
            volta = request.url.path + "?" + request.url.query
            sit = fila.situacao(rid)
            recebido = (ultimo.get() or {}).get("recebido_em")
            tab["edicao"] = edicao_tela(rid, t["titulo"], t, tab["linhas"], u, volta, sit, recebido)
            for j in juntas:
                jt = next((x["tabela"] for x in t.get("juntas") or [] if x["tabela"]["titulo"] == j["tabela"]), None)
                j["edicao"] = edicao_tela(rid, j["tabela"], jt, j["linhas"], u, volta, sit, recebido)
        # cada aba do Visita é uma página sem seletor de estado: o aviso fica em cada uma (RD-0023)
        aviso_uf = tabelas.AVISO_SEM_ESTADO if rid == "vc_visitas" else ""
        aviso_kpis = ""
        if solicitacao:
            kpis = []
        elif tab["filtrado"] or uf_ok:                  # filtro, recorte ou estado: os cartões da aba saem (§10.7.2)
            kpis, aviso_kpis = [], tabelas.AVISO_CARTOES
        elif t.get("kpis_padrao") is not None:
            kpis = render.kpis_para_tela(t["kpis_padrao"])
        else:
            kpis = topo["kpis"]
        uf = uf_ok
        return pagina(request, "farol.html", tela=None, tabela=tab, juntas=juntas, kpis=kpis,
                      faixa=True, ufs=ufs, uf=uf, subnomes=subnomes, sub=sub,
                      ed_enviada=edicoes.MSG_ENVIADA if consulta.get("ed") == ["1"] else "",
                      aviso_uf=aviso_uf, aviso_kpis=aviso_kpis, titulo_aba=t["titulo"], **ctx)

    # ------------------------------------------------------------ T-0021: edição (só admin)
    def selecao(t, tab, consulta):
        """`sel` = linha (índice da tabela) escolhida com um clique; só nas tabelas com junta ligada."""
        liga = next((j["liga"][1] for j in t.get("juntas") or [] if j.get("liga")), None)
        if not liga:
            return None
        nomes = [c["nome"] for c in tab["cols"]]
        tab["sel_col"] = nomes.index(liga) if liga in nomes else None
        try:
            sel = int(consulta.get("sel", [""])[0])
        except ValueError:
            return None
        if sel not in set(tab["idxs"]):
            return None
        ci = [c["nome"] for c in t["colunas"]].index(liga)
        tab["sel"], tab["sel_rotulo"] = sel, str(t["linhas"][sel][ci] or "")
        return sel

    def edicao_tela(rid, titulo, t_pc, linhas, u, volta, sit, recebido):
        """Por linha da tela: botão de editar (admin com chave) e a marca "Aguardando o PC"/"O PC recusou".
        Sem `edicao` no pacote, ou perfil sem edição e sem marca, a coluna não aparece."""
        ed = t_pc.get("edicao") if isinstance(t_pc, dict) else None
        if not isinstance(ed, dict):
            return None
        admin = u["perfil"] in edicoes.EDITA
        algum = False
        for ln in linhas:
            ch = edicoes.chave_da_linha(ed, ln["k"])
            s = sit.get((titulo, ch)) if ch else None
            m = edicoes.marca(s, recebido)
            url = (f"/farol/{rid}/editar?" + urlencode({"tab": titulo, "chave": ch, "volta": volta})
                   if admin and ch else "")
            ln["ed"] = {"url": url, "marca": m, "dica": edicoes.dica(s, ed, m, admin), "sem_chave": admin and not ch}
            algum = algum or bool(m)
        if not admin and not algum:
            return None
        novo = (f"/farol/{rid}/editar?" + urlencode({"tab": titulo, "chave": edicoes.NOVA, "volta": volta})
                if admin and ed.get("novo") else "")
        n_novos = sum(1 for (tb, ch), s in sit.items()
                      if tb == titulo and ch.startswith(edicoes.NOVA) and edicoes.marca(s, recebido) == "pendente")
        return {"cab": ed.get("acao") or "Editar", "admin": admin, "novo": novo, "n_novos": n_novos}

    def tabela_editavel(rid, titulo):
        """(tabela do pacote, chave da aba) do lugar editável; (None, "") se não houver."""
        rel = rel_do(rid)
        if not rel or (rid, titulo) not in edicoes.LUGARES:
            return None, ""
        chaves = dict((tit, c) for c, tit in tabelas.ABAS.get(rid, ()))
        for t in rel.get("tabelas") or []:
            if t.get("titulo") == titulo:
                return t, chaves.get(titulo, "")
            for j in t.get("juntas") or []:
                if (j.get("tabela") or {}).get("titulo") == titulo:
                    return j["tabela"], chaves.get(t.get("titulo"), "")
        return None, ""

    def volta_ok(rid, v) -> str:
        v = str(v or "").replace("&ed=1", "")
        if (v.startswith(f"/farol/{rid}?") and len(v) <= 800 and "//" not in v and "\\" not in v
                and not any(ch in v for ch in "\r\n<>\"'")):
            return v
        return f"/farol/{rid}"

    def form_ctx_novo(rid, titulo, t, aba, volta, f=None):
        """O formulário da linha nova (Expositores): campos vazios, com os padrões do PC (status, qtd, data de hoje)."""
        ed = t["edicao"]
        padroes = dict(ed["novo"]["padroes"])
        hoje_br = datetime.now(MANAUS).strftime("%d/%m/%Y")
        campos = []
        for c in edicoes.campos_da_linha(ed, 0):
            atual = str((f or {}).get("c_" + c["campo"], padroes.get(c["campo"], "")))[:200]
            if c["tipo"] == "data":
                atual = edicoes.br_data(atual) if atual and atual != "hoje" else (hoje_br if atual == "hoje" else "")
            isos = sorted(edicoes.iso_de_br(x) for x in c["opcoes_linha"]) if c["tipo"] == "data" else []
            campos.append({"campo": c["campo"], "rotulo": c["rotulo"], "tipo": c["tipo"], "atual": atual,
                           "atual_iso": edicoes.iso_de_br(atual), "opcoes": list(c["opcoes_linha"]), "sugestao": "",
                           "min": isos[0] if isos else "", "max": isos[-1] if isos else "",
                           "limite": c.get("max") or edicoes.MAX_TEXTO, "pendente": None})
        return dict(farol_nome=render.FAROIS[rid][0], rid=rid, tab=titulo, chave=edicoes.NOVA,
                    acao="Novo expositor", resumo=[], campos=campos, volta=volta, ver_pedido="", sit=None,
                    noindex=True)

    def form_ctx(rid, titulo, t, aba, k, sit_linha, volta):
        ed = t["edicao"]
        cols, linha = t["colunas"], t["linhas"][k]
        nomes = [c["nome"] for c in cols]
        resumo = [render.fmt_celula(linha[i], c["tipo"]) for i, c in enumerate(cols)
                  if not c.get("oculta") and linha[i] not in (None, "")][:6]
        pend = (sit_linha or {}).get("valores") or {} if (sit_linha or {}).get("status") == "pendente" else {}
        campos = []
        for c in edicoes.campos_da_linha(ed, k):
            v = linha[nomes.index(c["coluna"])] if c.get("coluna") in nomes else None
            atual = edicoes.atual_txt(c, v)
            ops = list(c["opcoes_linha"])
            if atual and atual not in ops and c["tipo"] == "lista":
                ops = [atual] + ops                       # como o PC: o valor de hoje entra na lista
            isos = sorted(edicoes.iso_de_br(x) for x in ops) if c["tipo"] == "data" else []
            campos.append({"campo": c["campo"], "rotulo": c["rotulo"], "tipo": c["tipo"], "atual": atual,
                           "atual_iso": edicoes.iso_de_br(atual), "opcoes": ops, "sugestao": c.get("sugestao", ""),
                           "min": isos[0] if isos else "", "max": isos[-1] if isos else "",
                           "limite": c.get("max") or edicoes.MAX_TEXTO, "pendente": pend.get(c["campo"])})
        liga = next((j for j in t.get("juntas") or [] if j.get("liga")), None)
        ver = f"/farol/{rid}?aba={aba}&sel={k}" if liga and aba else ""      # "Ver pedido", como no PC
        return dict(farol_nome=render.FAROIS[rid][0], rid=rid, tab=titulo, chave=ed["chaves"][k],
                    acao=ed.get("acao") or "Editar", resumo=resumo, campos=campos, volta=volta,
                    ver_pedido=ver, sit=sit_linha, noindex=True)

    @app.get("/farol/{rid}/editar", response_class=HTMLResponse)
    async def editar_get(request: Request, rid: str, tab: str = "", chave: str = "", volta: str = ""):
        u = usuario(request)
        if rid not in render.FAROIS or u["perfil"] not in edicoes.EDITA:
            raise PermissionError                       # só o admin edita (decisão de 25/11)
        volta = volta_ok(rid, volta)
        t, aba = tabela_editavel(rid, tab[:80])
        ed = (t or {}).get("edicao")
        if chave == edicoes.NOVA and isinstance(ed, dict) and ed.get("novo"):
            return pagina(request, "editar.html", erro="", aviso="", **form_ctx_novo(rid, tab, t, aba, volta))
        k = edicoes.linha_da_chave(ed, chave[:80]) if isinstance(ed, dict) else None
        if k is None:
            return pagina(request, "erro.html", status=404,
                          titulo_erro="Linha não encontrada",
                          msg="Esta linha não está mais no pacote do PC. Volte ao farol e abra de novo.")
        sit = fila.situacao(rid).get((tab, chave))
        return pagina(request, "editar.html", erro="", aviso="",
                      **form_ctx(rid, tab, t, aba, k, sit, volta))

    def novo_post(request, u, rid, tab, t, aba, ed, volta, f):
        """Linha nova (Expositores): só vai o que foi preenchido; o PC põe a chave EXPnnnn e a data de hoje."""
        nomes = [c["nome"] for c in t["colunas"]]
        mudou, _antes, erro = edicoes.valores_do_form(ed, 0, [None] * len(nomes), nomes, f)
        padroes = ed["novo"]["padroes"]
        if not erro and not any(padroes.get(c) != v for c, v in mudou.items()):
            erro = "Preencha pelo menos um campo além dos padrões."
        if erro:
            return pagina(request, "editar.html", status=400, erro=erro, aviso="",
                          **form_ctx_novo(rid, tab, t, aba, volta, f))
        chave = edicoes.NOVA + uuid.uuid4().hex[:8].upper()
        try:
            fila.registrar(usuario=u["login"], rid=rid, tabela=tab, modulo=ed["modulo"], chave=chave,
                           valores=mudou, antes={})
        except OSError:
            log.error("edição: falha ao gravar a fila")
            return pagina(request, "editar.html", status=503, erro="Não foi possível gravar agora. Tente de novo.",
                          aviso="", **form_ctx_novo(rid, tab, t, aba, volta, f))
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba or "-", "editar")
        return RedirectResponse(volta + ("&" if "?" in volta else "?") + "ed=1", status_code=303)

    @app.post("/farol/{rid}/editar")
    async def editar_post(request: Request, rid: str):
        u = usuario(request)
        if rid not in render.FAROIS or u["perfil"] not in edicoes.EDITA:
            raise PermissionError                       # 403 antes de ler o formulário
        f = await formulario(request)                   # CSRF errado = 403
        tab, chave = str(f.get("tab", ""))[:80], str(f.get("chave", ""))[:80]
        volta = volta_ok(rid, f.get("volta"))
        t, aba = tabela_editavel(rid, tab)
        ed = (t or {}).get("edicao")
        if chave == edicoes.NOVA and isinstance(ed, dict) and ed.get("novo"):
            return novo_post(request, u, rid, tab, t, aba, ed, volta, f)
        k = edicoes.linha_da_chave(ed, chave) if isinstance(ed, dict) else None
        if k is None:
            return pagina(request, "erro.html", status=409,
                          titulo_erro="Linha não encontrada",
                          msg="Esta linha não está mais no pacote do PC. Volte ao farol e abra de novo.")
        nomes = [c["nome"] for c in t["colunas"]]
        mudou, antes, erro = edicoes.valores_do_form(ed, k, t["linhas"][k], nomes, f)
        sit = fila.situacao(rid).get((tab, chave))
        if erro or not mudou:
            return pagina(request, "editar.html", status=400 if erro else 200, erro=erro,
                          aviso="" if erro else "Nada mudou.", **form_ctx(rid, tab, t, aba, k, sit, volta))
        try:
            fila.registrar(usuario=u["login"], rid=rid, tabela=tab, modulo=ed["modulo"], chave=chave,
                           valores=mudou, antes=antes)
        except OSError:
            log.error("edição: falha ao gravar a fila")
            return pagina(request, "editar.html", status=503, erro="Não foi possível gravar agora. Tente de novo.",
                          aviso="", **form_ctx(rid, tab, t, aba, k, sit, volta))
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba or "-", "editar")
        return RedirectResponse(volta + ("&" if "?" in volta else "?") + "ed=1", status_code=303)

    @app.get("/farol/{rid}", response_class=HTMLResponse)
    async def farol(request: Request, rid: str, uf: str = "", aba: str = "resumo"):
        u = usuario(request)
        if rid not in render.FAROIS or u["perfil"] not in render.FAROIS[rid][1]:
            raise PermissionError                       # perfil conferido no servidor
        perfil = u["perfil"]
        if rid in tabelas.RIDS:
            return farol_abas(request, u, rid, aba, uf)
        chaves = [c for c, _ in cobranca.ABAS]
        if aba in chaves[1:]:                           # aba de tabela ou de fila: 403 fora do perfil
            if (rid != cobranca.RID or (aba in cobranca.ABA_TABELA and perfil not in cobranca.VE_TABELAS)
                    or (aba == "cobrar" and perfil not in cobranca.COBRA)):
                raise PermissionError
        else:
            aba = "resumo"
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba, "ver")
        nome = render.FAROIS[rid][0]
        rel = rel_do(rid)
        if not rel:
            return pagina(request, "farol.html", farol_nome=nome, rid=rid, tela=None, abas=[], aba="resumo")
        abas = []
        if rid == cobranca.RID and "tabelas" in rel and "cobranca" in rel:
            abas = [(c, n) for c, n in cobranca.ABAS
                    if c == "resumo" or (c in cobranca.ABA_TABELA and perfil in cobranca.VE_TABELAS)
                    or (c == "cobrar" and perfil in cobranca.COBRA)]
        ctx = dict(farol_nome=nome, rid=rid, abas=abas if len(abas) > 1 else [], aba=aba, noindex=aba != "resumo")
        if aba == "resumo":
            return pagina(request, "farol.html", tela=render.farol_para_tela(rel, uf[:4] or None, rid), **ctx)
        if "tabelas" not in rel:                        # robô antigo: sem as abas novas
            return pagina(request, "farol.html", tela=None, **ctx)
        if aba in cobranca.ABA_TABELA:
            titulo = cobranca.ABA_TABELA[aba]
            t = next(x for x in rel["tabelas"] if x["titulo"] == titulo)
            return pagina(request, "farol.html", tela=None,
                          tabela=cobranca.tabela_para_tela(t, titulo, consulta_de(request)),
                          **ctx)
        cob = rel["cobranca"]
        extras = diario.pendentes(cob["web_epoca"], cob["web_ate_seq"])
        hoje = cobranca.agora().date()
        pendentes, tratados = [], []
        for it in cob["fila"]:
            sit = cobranca.situacao(cobranca.ultimo_efetivo(it, extras), cob["dias_recente"], hoje)
            link = f"https://wa.me/{it['whatsapp']}?text={quote(it['mensagem'])}" if it["whatsapp"] else ""
            c = {**it, "situacao": sit, "link": link, "aviso": cobranca.aviso_curto(it["aviso"])}
            (tratados if sit.endswith("HOJE") else pendentes).append(c)   # já tratados hoje vão ao fim
        try:
            pag = max(1, int(request.query_params.get("pag", "1")))
        except ValueError:
            pag = 1
        paginas = max(1, -(-len(pendentes) // cobranca.FILA_POR_PAGINA))
        pag = min(pag, paginas)
        ini = (pag - 1) * cobranca.FILA_POR_PAGINA
        return pagina(request, "farol.html", tela=None, fila=pendentes[ini:ini + cobranca.FILA_POR_PAGINA],
                      tratados=tratados if pag == paginas else [], n_fila=len(pendentes), n_tratados=len(tratados),
                      pag=pag, paginas=paginas, pc_ate=cob["gerado_em"], pacote_sha=ultimo.sha(), **ctx)

    @app.post("/farol/pl_inadimplencia/cobranca")
    async def cobrar(request: Request):
        u = usuario(request, cobranca.COBRA)
        f = await formulario(request)
        # §10.6.4: o item sai do pacote da página (se ainda entre os 7); senão do vigente; senão 404
        def acha(pac):
            rel = ((pac or {}).get("relatorios") or {}).get(cobranca.RID)
            cob = rel.get("cobranca") if isinstance(rel, dict) else None
            return next((i for i in (cob or {}).get("fila", []) if i["cod"] == f.get("cliente")), None)
        sha_pag = f.get("pacote_sha", "")
        item, sha_item = None, ""
        if sha_pag and sha_pag != ultimo.sha():
            item = acha(pacotes.por_sha(cfg.dados, sha_pag))
            sha_item = sha_pag
        if not item:
            item, sha_item = acha(ultimo.get()), ultimo.sha()
        if not item:
            return JSONResponse({"ok": False, "erro": "abra o farol de novo"}, status_code=404)
        acao = f.get("acao")
        if acao not in cobranca.ACOES:
            return JSONResponse({"ok": False, "erro": "ação inválida"}, status_code=400)
        fone = item["whatsapp"]
        if acao == "ENVIADO":
            digitado = (f.get("telefone") or "").strip()
            fone = cobranca.celular(digitado) if digitado else item["whatsapp"]
            if not fone:
                return JSONResponse({"ok": False, "erro": "telefone inválido ou ausente"}, status_code=400)
        try:
            reg, repetido = diario.registrar(
                usuario=u["login"], cliente=item["cod"], acao=acao, telefone=fone,
                em_atraso=item["em_atraso"], titulos=len(item["titulos"]), pacote_sha=sha_item)
        except OSError:                                  # disco cheio ou indisponível: nada foi registrado
            log.error("cobrança: falha ao gravar o diário")
            return JSONResponse({"ok": False, "erro": "Não foi possível gravar agora."}, status_code=503)
        cobranca.registrar_acesso(cfg.dados, u["login"], cobranca.RID, "cobrar", acao)
        sit = "ENVIADO HOJE" if reg["acao"] == "ENVIADO" else "PULADO HOJE"
        return {"ok": True, "seq": reg["seq"], "id": reg["id"], "situacao": sit, "repetido": repetido}

    # ------------------------------------------------------------ usuários (admin)
    @app.get("/usuarios", response_class=HTMLResponse)
    async def usuarios_get(request: Request):
        usuario(request, ("admin",))
        return pagina(request, "usuarios.html", lista=usuarios.listar(), perfis=PERFIS,
                      msg="", erro="")

    @app.post("/usuarios")
    async def usuarios_post(request: Request):
        usuario(request, ("admin",))
        f = await formulario(request)
        acao, alvo = f.get("acao"), (f.get("login") or "").strip().lower()
        try:
            if acao == "criar":
                usuarios.criar(alvo, f.get("senha", ""), f.get("perfil", ""))
            elif acao in ("desativar", "ativar"):
                if alvo == request.session.get("u") and acao == "desativar":
                    raise Erro("Você não pode desativar a si mesmo.")
                usuarios.definir_ativo(alvo, acao == "ativar")
            elif acao == "senha":
                usuarios.trocar_senha(alvo, f.get("senha", ""), exigir_troca=True)
                if alvo == request.session.get("u"):
                    request.session["s"] = usuarios.obter(alvo)["sessao"]
            else:
                raise Erro("Ação desconhecida.")
        except Erro as e:
            return pagina(request, "usuarios.html", status=400, lista=usuarios.listar(),
                          perfis=PERFIS, msg="", erro=str(e))
        return pagina(request, "usuarios.html", lista=usuarios.listar(), perfis=PERFIS,
                      msg="Feito.", erro="")

    # ------------------------------------------------------------ pacote do robô
    def sem_token(request: Request):
        auth = request.headers.get("authorization", "")
        esperado = cfg.token
        entrada = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not esperado or not hmac.compare_digest(entrada.encode(), esperado.encode()):
            return JSONResponse({"erro": "não autorizado"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        return None

    @app.get("/api/cobranca")
    async def api_cobranca(request: Request):
        negado = sem_token(request)
        if negado:
            return negado
        bruto = request.query_params.get("desde", "0")
        if not (bruto.isascii() and bruto.isdigit()) or len(bruto) > 15:
            return JSONResponse({"erro": "desde precisa ser inteiro >= 0"}, status_code=400)
        return diario.desde(int(bruto))

    @app.post("/api/cobranca/confirmar")
    async def api_confirmar(request: Request):
        negado = sem_token(request)
        if negado:
            return negado
        try:
            corpo = json.loads((await request.body())[:1024])
            ate = corpo.get("ate_seq") if isinstance(corpo, dict) else None
            epoca = corpo.get("epoca") if isinstance(corpo, dict) else None
        except ValueError:
            ate = epoca = None
        try:
            return diario.confirmar(epoca, ate)
        except cobranca.ErroCobranca as e:
            return JSONResponse({"erro": e.msg}, status_code=e.status)

    @app.get("/api/edicoes")
    async def api_edicoes(request: Request):
        """T-0021: o robô lista as edições desde um seq (cada uma com o status de agora)."""
        negado = sem_token(request)
        if negado:
            return negado
        bruto = request.query_params.get("desde", "0")
        if not (bruto.isascii() and bruto.isdigit()) or len(bruto) > 15:
            return JSONResponse({"erro": "desde precisa ser inteiro >= 0"}, status_code=400)
        return fila.desde(int(bruto))

    @app.post("/api/edicoes/confirmar")
    async def api_edicoes_confirmar(request: Request):
        """T-0021: o robô confirma o que gravou no PC (aplicada) ou recusou (erro, motivo sem dado pessoal)."""
        negado = sem_token(request)
        if negado:
            return negado
        try:
            corpo = json.loads((await request.body())[:262144])
        except ValueError:
            corpo = None
        if not isinstance(corpo, dict):
            return JSONResponse({"erro": "corpo precisa ser objeto JSON"}, status_code=400)
        try:
            return fila.confirmar(corpo.get("epoca"), corpo.get("resultados"))
        except edicoes.ErroEdicao as e:
            return JSONResponse({"erro": e.msg}, status_code=e.status)

    @app.post("/api/pacote")
    async def api_pacote(request: Request):
        negado = sem_token(request)
        if negado:
            return negado
        ct = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if ct != "application/json":
            return JSONResponse({"erro": "só application/json (nada de arquivo ou .pkl)"},
                                status_code=415)
        cl = request.headers.get("content-length")
        if cl is not None and (not cl.isdigit() or int(cl) > cfg.pacote_max):
            return JSONResponse({"erro": "pacote grande demais"}, status_code=413)
        partes, total = [], 0
        async for parte in request.stream():
            total += len(parte)
            if total > cfg.pacote_max:
                return JSONResponse({"erro": "pacote grande demais"}, status_code=413)
            partes.append(parte)
        try:
            corpo = json.loads(b"".join(partes))
        except (ValueError, RecursionError):
            return JSONResponse({"erro": "JSON inválido"}, status_code=422)
        del partes
        erros = pacotes.validar(corpo)
        if erros:
            return JSONResponse({"erro": "esquema inválido", "detalhes": erros}, status_code=422)
        fora = tabelas.tirar_abas_com_documento(corpo)   # só a aba com CPF/CNPJ cai; o resto do pacote segue
        if fora:
            log.warning("abas fora do pacote por CPF/CNPJ em célula: %d", len(fora))
        pacotes.gravar(cfg.dados, corpo, datetime.now(MANAUS).isoformat(timespec="seconds"))
        log.info("pacote recebido: %s (%d bytes)", pacotes.nome_arquivo(corpo["gerado_em"]), total)
        return {"ok": True, "gerado_em": corpo["gerado_em"], "bytes": total}

    return app
