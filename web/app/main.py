"""Rotas da BAP Central web. Uso: uvicorn app.main:criar_app --factory"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import VERSAO, cobranca, config, pacotes, render
from .usuarios import PERFIS, Erro, Usuarios, MAX_ERROS

log = logging.getLogger("bap_web")
AQUI = Path(__file__).parent
MANAUS = ZoneInfo("America/Manaus")
VERES = ("admin", "diretor", "gerente")          # [SUPOSIÇÃO] os 3 veem o painel
RELATORIO = ("vc_painel", "Painel Executivo")
FORM_MAX = 16 * 1024
ISENTAS_FUSO = ("/saude", "/static", "/api/pacote", "/api/cobranca")   # saúde e robô seguem; as telas param


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
    diario = cobranca.Diario(cfg.dados)
    diario.limpar()                                   # §10.6.5: também quando o app sobe

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

    @app.get("/farol/{rid}", response_class=HTMLResponse)
    async def farol(request: Request, rid: str, uf: str = "", aba: str = "resumo"):
        u = usuario(request)
        if rid not in render.FAROIS or u["perfil"] not in render.FAROIS[rid][1]:
            raise PermissionError                       # perfil conferido no servidor
        perfil = u["perfil"]
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
            return pagina(request, "farol.html", tela=render.farol_para_tela(rel, uf[:4] or None), **ctx)
        if "tabelas" not in rel:                        # robô antigo: sem as abas novas
            return pagina(request, "farol.html", tela=None, **ctx)
        if aba in cobranca.ABA_TABELA:
            titulo = cobranca.ABA_TABELA[aba]
            t = next(x for x in rel["tabelas"] if x["titulo"] == titulo)
            consulta = {}
            for k, v in request.query_params.multi_items():
                consulta.setdefault(k, []).append(v[:80])
            return pagina(request, "farol.html", tela=None, tabela=cobranca.tabela_para_tela(t, titulo, consulta),
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
        if not bruto.isdigit() or len(bruto) > 15:
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
        pacotes.gravar(cfg.dados, corpo, datetime.now(MANAUS).isoformat(timespec="seconds"))
        log.info("pacote recebido: %s (%d bytes)", pacotes.nome_arquivo(corpo["gerado_em"]), total)
        return {"ok": True, "gerado_em": corpo["gerado_em"], "bytes": total}

    return app
