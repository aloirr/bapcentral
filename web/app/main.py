"""Rotas da BAP Central web. Uso: uvicorn app.main:criar_app --factory"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import VERSAO, acesso, cobranca, config, edicoes, exportar, leitura, marca, pacotes, render, tabelas, visitas
from .usuarios import PERFIS, Erro, ErroGravacao, Usuarios, MAX_ERROS, MSG_LISTA_MUDOU

log = logging.getLogger("bap_web")
AQUI = Path(__file__).parent
MANAUS = ZoneInfo("America/Manaus")
PAINEL_RID = render.PAINEL_RID        # T-0050: quem vê o Painel Executivo e cada farol é `acesso.pode_ver` (perfil + exceções do admin)
FORM_MAX = 32 * 1024                               # §10.9.1: o Editar da Garantia leva 4 textos de até 600 caracteres
FECHAR_MAX = 256 * 1024
PODEM_PEDIR, SO_ADMIN = visitas.PODEM_PEDIR, visitas.SO_ADMIN      # uma constante só (visitas.py), a mesma da lateral
ISENTAS_FUSO = ("/saude", "/static", "/api/pacote", "/api/cobranca", "/api/edicoes", "/api/visitas")   # saúde e robô seguem; as telas param


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


def carimbo(ind, rid, ent=None, info=None):
    """Carimbo "gerado em" do farol: o da entrada no índice, com reserva no do lote. A página e a porta de leitura usam esta."""
    info = info or ind.indice()
    ent = ent or (ind.entrada(rid) if rid else None)
    return (ent or {}).get("gerado_em") or (info["gerado_em"] if info else None)


def fmt_manaus(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=MANAUS)
    return d.astimezone(MANAUS).strftime("%d/%m/%Y %H:%M")


def fmt_manaus_curto(iso: str | None) -> str:
    """"dd/mm hh:mm", a data da faixa no celular (contrato tela-bc3 §8)."""
    f = fmt_manaus(iso)
    return f[:5] + " " + f[-5:] if len(f) >= 16 else f


def hhmm(iso: str | None) -> str:
    """"hh:mm" se for de hoje (Manaus); senão "dd/mm hh:mm"."""
    f = fmt_manaus(iso)
    return f[-5:] if f[:10] == cobranca.agora().strftime("%d/%m/%Y") else fmt_manaus_curto(iso)


def criar_app() -> FastAPI:
    cfg = config.carregar()
    cfg.dados.mkdir(parents=True, exist_ok=True)
    usuarios = Usuarios(cfg)
    aviso_disco: list[str] = []
    try:
        pacotes.converter_legado(cfg.dados)    # T-0035: disco do formato 1 vira um lote, uma vez só
        pacotes.retencao(cfg.dados)
    except Exception as e:                     # arquivo antigo estragado não derruba a web
        log.error("pacote antigo não convertido: %s", type(e).__name__)
        aviso_disco.append("pacote antigo do disco não pôde ser convertido; aguardando a próxima rodada do PC")
    ind = pacotes.Indice(cfg.dados, cfg.cache_mb)
    modelos = Jinja2Templates(directory=str(AQUI / "templates"))
    modelos.env.autoescape = True
    modelos.env.filters["manaus"] = fmt_manaus
    modelos.env.filters["hhmm"] = hhmm
    modelos.env.globals["kpi_curto"] = tabelas.kpi_curto
    modelos.env.globals["selo_curto"] = tabelas.selo_curto
    modelos.env.globals["titulo_cel"] = tabelas.TITULO_CEL
    modelos.env.globals["analista"] = tabelas.RIDS_ANALISTA        # T-0036: faróis do Analista Comercial
    modelos.env.filters["dia_br"] = visitas.dia_br                 # T-0045: AAAAMMDD -> dd/mm
    modelos.env.filters["dia_hora"] = visitas.dia_hora             # T-0045: "27/11 06h06", o formato único da tela
    modelos.env.filters["fone"] = cobranca.fone_bonito
    modelos.env.filters["aba_curta"] = tabelas.aba_curta           # T-0033: nomes curtos nas abas (cabem a 1366)
    modelos.env.globals["dados_popup"] = tabelas.dados_do_popup
    modelos.env.filters["manaus_curto"] = fmt_manaus_curto
    modelos.env.globals["kpis_da_faixa"] = render.kpis_da_faixa    # RD-0065: a regra "comum na faixa, rico no corpo" é uma só
    modelos.env.globals["kpis_do_corpo"] = render.kpis_do_corpo
    modelos.env.globals["abas_no_celular"] = render.abas_no_celular   # RD-0065: a regra das 3 abas + "Mais" é uma só
    modelos.env.globals["livres"] = tabelas.FAROIS_LIVRES          # T-0024: faróis de abas livres (lote 2)
    modelos.env.globals["datas_proximas"] = render.datas_proximas  # T-0020: uma data só
    diario = cobranca.Diario(cfg.dados)
    diario.limpar()                                   # §10.6.5: também quando o app sobe
    fila = edicoes.Fila(cfg.dados)                    # T-0021: edições da web, só acréscimo
    vis = visitas.Visitas(cfg.dados, cfg.visitas_token)   # T-0045: visitas da Máxima no Render (ADR 0004)
    try:
        vis.retencao()
    except Exception as e:                            # retenção atrasada não derruba a web
        log.error("retenção dos lotes de visitas: %s", type(e).__name__)

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
        if request.url.path.startswith("/static/fontes/"):
            r.headers["Cache-Control"] = "public, max-age=31536000, immutable"      # a Inter hospedada (MC-0020) não muda
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

    def exige(u: dict, rid: str) -> None:
        """RN-GER-018: a tela do farol é de quem `acesso.pode_ver` (perfil + exceções); fora = 403. Os cortes de dado seguem pelo perfil."""
        if not acesso.pode_ver(u, rid):
            raise PermissionError

    def exige_farol(u: dict, rid: str) -> None:
        """Rotas `/farol/{rid}`: além do `exige`, o rid precisa ser de um farol (o Painel tem a rota `/painel`): senão 403."""
        if rid not in render.FAROIS:
            raise PermissionError
        exige(u, rid)

    @app.exception_handler(PermissionError)
    async def _nega(request, exc):
        return pagina(request, "erro.html", status=403, u=None,
                      msg="Você não tem acesso a esta página.")

    def pagina(request, nome, status=200, u="auto", **ctx):
        if u == "auto":
            u = usuarios.obter(request.session.get("u", ""))
        info = ind.indice()
        # T-0035 (ADR 0003, §4.4): a faixa mostra a data do farol; passou de 26 h = selo "Desatualizado"
        no_painel = request.url.path == "/painel"
        rid_pg = ctx.get("rid") or (PAINEL_RID if no_painel else None)
        ent = ind.entrada(rid_pg) if rid_pg else None
        gerado_farol = carimbo(ind, rid_pg, ent, info)
        try:
            velho = bool(ent) and (cobranca.agora() - pacotes._como_manaus(gerado_farol)).total_seconds() > pacotes.HERDA_HORAS * 3600
        except (TypeError, ValueError):
            velho = False
        ctx.update(usuario=u, csrf=csrf(request), versao=VERSAO, empresa=marca.EMPRESA, indisponivel=render.INDISPONIVEL,
                   gerado_em=gerado_farol, desatualizado=velho, sem_calculo=edicoes.SEM_CALCULO)
        # T-0034 (RD-0043): uma casca só (barra lateral + faixa) para toda tela com usuário; o item ativo é o farol
        # ou, no Painel Executivo, "painel". Sem usuário (login, acesso negado): a mesma casca, sem lateral.
        if u:
            no_pacote = (info or {}).get("farois") or {}
            # o item da lateral marcado: o farol, o painel ou, na conta, "usuarios" e "senha" (contrato §3)
            ativo = ctx.get("rid") or {"/painel": "painel", "/usuarios": "usuarios", "/senha": "senha",
                                       "/visitas/atualizar": "visitas_atualizar"}.get(request.url.path)
            # o link "Atualizar" só para quem pode apertar (UX 8): calculado uma vez, para a lateral e para a tela
            pode_vis = u["perfil"] in PODEM_PEDIR and acesso.pode_ver(u, "vc_visitas")
            ctx["nav"] = render.menu_lateral(u["perfil"], no_pacote, ativo, painel=acesso.pode_ver(u, PAINEL_RID),
                                             admin=u["perfil"] == "admin", vistos=acesso.farois_do_usuario(u),
                                             atualizar_visitas=pode_vis)
            ctx["pode_visitas"] = pode_vis
            if u["trocar_senha"]:
                ctx["nav"] = []             # troca obrigatória: só a casca (marca e Sair), sem links que não levam a lugar nenhum
        return modelos.TemplateResponse(request, nome, ctx, status_code=status)

    async def formulario(request: Request) -> dict:
        corpo = b""
        async for parte in request.stream():
            corpo += parte
            if len(corpo) > FORM_MAX:
                break
        multi = parse_qs(corpo[:FORM_MAX].decode("utf-8", "replace"), keep_blank_values=True)
        d = {k: v[0] for k, v in multi.items()}
        d["_multi"] = multi                          # T-0050: as caixas repetidas (`farol`)
        if not hmac.compare_digest(d.get("csrf", "").encode(), str(request.session.get("csrf", "x")).encode()):
            raise PermissionError
        return d

    # ------------------------------------------------------------ saúde
    @app.get("/saude")
    async def saude():
        info = ind.indice()
        tz = os.environ.get("TZ")
        motivo = fuso_motivo()
        mem = pacotes.memoria(ind)
        extra = {"memoria_alerta": True} if (mem["pico_mb"] or 0) > 400 else {}
        return {"status": "ok", "versao": VERSAO, **extra,
                "pacote": {"formatos": pacotes.FORMATOS, "lote": info["lote"] if info else None,
                           "farois": len(info["farois"]) if info else 0,
                           "origem": info["origem"] if info else None},
                "memoria": mem,
                **({"aviso_pacote": aviso_disco[0]} if aviso_disco else {}),
                "hora_manaus": datetime.now(MANAUS).strftime("%Y-%m-%d %H:%M:%S"),
                "tz": tz, "tz_ok": motivo is None, "telas_bloqueadas": motivo is not None,
                "motivo": motivo, "visitas": vis.saude(),
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
    @app.get("/")
    async def home(request: Request):
        """T-0034: não há mais grade de quadrados. Cada perfil cai na tela dele (a lateral é o menu)."""
        u = usuario(request)
        vistos = acesso.farois_do_usuario(u)
        com_painel = acesso.pode_ver(u, PAINEL_RID)
        if u["perfil"] == "trade" and not vistos and not com_painel:
            # T-0036 (2 A, UX 9): até a T-0025-v2 o Trade Marketing não tem farol; casca BC3, uma frase neutra
            return pagina(request, "trade_inicio.html", bc3=True, sem_pacote_ok=True)
        destino = render.pagina_inicial(u["perfil"], vistos, com_painel, acesso.padrao_do_perfil(u["perfil"]))
        return RedirectResponse(destino, status_code=302)

    @app.get("/painel", response_class=HTMLResponse)
    async def painel(request: Request, aba: str = "resultado", uf: str = ""):
        exige(usuario(request), PAINEL_RID)
        rel = ind.farol(PAINEL_RID)
        abas = render.localizar_abas(rel) if rel else []
        paineis = render.localizar_paineis(rel) if rel else []     # T-0022: as outras 9 abas do PC
        if not abas and not paineis:
            return pagina(request, "painel.html", abas=[], tela=None, tela_f=None, aba=aba)
        du = render.du_do_painel(abas)                      # U8: os dias úteis ficam na faixa de todas as abas
        nav = [{"chave": a["chave"], "curta": render.PAINEL_CURTO.get(a["chave"], a["titulo"]), "so_bap": False}
               for a in abas] + \
              [{"chave": p["chave"], "curta": render.PAINEL_CURTO.get(p["chave"], p["titulo"]), "so_bap": p["so_bap"]}
               for p in paineis]
        p_atual = next((p for p in paineis if p["chave"] == aba), None)
        if p_atual:
            dados = rel["paineis"][p_atual["chave"]]
            # o filtro só escolhe a visão pronta do PC (por estado); aba da BAP inteira ignora o estado
            escolhido = uf.upper()[:2] if (not p_atual["so_bap"] and uf.upper()[:2] in p_atual["ufs"]) else ""
            tela_f = render.farol_para_tela(dados, escolhido or None)
            return pagina(request, "painel.html", abas=nav, aba=p_atual["chave"], tela=None, tela_f=tela_f,
                          faixa_ks=render.faixa_painel(tela_f), uf=escolhido, du=du,
                          filtros=None if p_atual["so_bap"] else {"ufs": p_atual["ufs"]},
                          # aba só da BAP: o seletor fica no lugar, desligado, com os estados das outras abas (contrato §4.2)
                          ufs_off=(p_atual["ufs"] or sorted({u for q in paineis for u in q["ufs"]})) if p_atual["so_bap"] else [])
        if not abas:
            tela_f = render.farol_para_tela(rel["paineis"][nav[0]["chave"]], None)
            return pagina(request, "painel.html", abas=nav, aba=nav[0]["chave"], tela=None, tela_f=tela_f,
                          faixa_ks=render.faixa_painel(tela_f), filtros=None, uf="", du=du)
        atual = next((a for a in abas if a["chave"] == aba), abas[0])
        # T-0014: o filtro só escolhe a visão pronta do PC (por estado)
        escolhido = render.escolher_uf(atual, uf[:4] or None)
        tela = render.aba_para_tela(atual, escolhido)
        return pagina(request, "painel.html", abas=nav, aba=atual["chave"], tela=tela, tela_f=None,
                      faixa_ks=[], sub_painel=tela["sub"], du=du,
                      filtros=render.filtros(atual), uf=escolhido or "")

    def rel_do(rid):
        rel = ind.farol(rid)
        return rel if isinstance(rel, dict) and rel.get("forma") == "farol" else None

    def consulta_de(request: Request) -> dict:
        c: dict = {}
        for k, v in request.query_params.multi_items():
            c.setdefault(k, []).append(v[:80])
        return c

    def urls_tabela(request: Request, rid: str, aba: str, tab: dict, sub, uf: str, fora: bool) -> dict:
        """T-0033: os endereços da tabela (ordenação, filtros, recorte) e o do "carregar mais" (500 em 500 linhas)."""
        base0 = f"/farol/{rid}?aba={aba}"
        base = base0 + (f"&sub={sub}" if sub is not None else "") + (f"&uf={uf}" if uf else "") + ("&fora=1" if fora else "")
        sem_rec = "".join(f"&{f['chave']}={quote(str(v))}" for f in tab["filtros"] for v in f["sel"])
        sem_rec += f"&busca={quote(tab['busca'])}" if tab["busca"] else ""
        fq = sem_rec + (f"&rec={tab['rec']}" if tab["rec"] is not None else "")
        mais = ""
        if tab["pag"] < tab["paginas"]:
            q = urlencode([(k, v) for k, v in request.query_params.multi_items() if k != "pag"])
            mais = f"/farol/{rid}/linhas?{q}&pag={tab['pag'] + 1}"
        return {"base0": base0, "base": base, "sem_rec": sem_rec, "fq": fq, "mais": mais}

    def farol_abas(request: Request, u: dict, rid: str, aba: str, uf: str, linhas: bool = False):
        """Pedidos, Entregas e Visita (§10.7): Resumo e abas de tabela. Perfil e aba conferidos aqui."""
        perfil = u["perfil"]
        rel = rel_do(rid)
        abas_rid = tabelas.abas_do_farol(rid, rel)
        if aba in [c for c, _ in abas_rid] and not tabelas.ve_aba(rid, aba, perfil):
            raise PermissionError                       # aba fora do perfil = 403 (diretor só vê o Resumo)
        if aba not in [c for c, _ in abas_rid]:
            if aba in [c for c, _ in cobranca.ABAS[1:]]:
                raise PermissionError                   # aba da Inadimplência pedida em outro farol
            aba = "resumo"
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba, "ver")
        nome = render.FAROIS[rid][0]
        if not rel:
            return pagina(request, "farol.html", farol_nome=nome, rid=rid, tela=None, abas=[], aba="resumo")
        ufs = render.recortes_farol(rel)
        uf_ok = uf.upper()[:2] if uf.upper()[:2] in ufs else ""
        do_uf = ((rel["recortes"][uf_ok] or {}).get("tabelas") or []) if (rid == "vc_meta" and uf_ok) else []
        # T-0022: o PC monta as abas do Farol de Metas já com o filtro de estado; a que o estado não trouxe vai da BAP inteira, com aviso
        por_chave, sem_uf = {}, set()
        for c, tit in abas_rid:
            t_uf = next((t for t in do_uf if t.get("titulo") == tit), None)
            por_chave[c] = t_uf or next((t for t in rel.get("tabelas") or [] if t.get("titulo") == tit), None)
            if do_uf and t_uf is None:
                sem_uf.add(c)
        aviso_tabs_uf = f"Sem as tabelas de {uf_ok} neste pacote: abaixo, a BAP inteira." if aba in sem_uf else ""
        com_aba = [(c, tit) for c, tit in abas_rid if por_chave[c] and tabelas.ve_aba(rid, c, perfil)]
        # T-0024 (R1): rótulo curto na barra; o título do PC segue sendo a chave da tabela
        barra = [tabelas.RESUMO] + [(c, tabelas.rotulo_aba(rid, tit)) for c, tit in com_aba] if com_aba else []
        ctx = dict(farol_nome=nome, rid=rid, abas=barra, aba=aba, noindex=aba != "resumo", ufs_off=ufs,
                   # T-0032 (Alexandre, 26/11: "assim como tem no bap central do python"): o botão aparece sempre
                   # para quem pode; sem imagem no pacote, a página da parcial diz que ainda não chegou
                   parcial=tem_parcial(u, rid),
                   csvs=csvs_de(rel, rid, perfil) if aba in ("pedidos", "solicitacao") else [],
                   correcao=(rid == "an_divergencias" and perfil == "admin"
                             and bool(((ind.entrada(rid) or {}).get("anexos") or {}).get("correcao"))))
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
            topo = render.farol_para_tela(rel, None, rid)   # sem estado, os cartões de cima são os da BAP inteira (D5)
            try:
                sub = int(consulta.get("sub", ["0"])[0])
            except ValueError:
                sub = 0
            subnomes, tab = tabelas.subabas_para_tela(t, sub, consulta)
            sub = tab["sub"]
        else:
            fora_base = tabelas.linhas_fora_da_base(t) if rid == "pv_pedidos" else frozenset()
            mostrar_fora = consulta.get("fora") == ["1"]
            tab = tabelas.tabela_para_tela(t, consulta, uf=uf_ok or None,
                                           excluir=frozenset() if mostrar_fora else fora_base, rid=rid)
            tab["fora_base"] = {"qtd": len(fora_base), "mostrar": mostrar_fora} if fora_base else None
            # T-0024 (R4): a dica da busca dos faróis do lote 2 (GRADE, contrato tela-bc3 §6.2)
            tabelas.aplicar_rotulos(tab, rid)                  # T-0036: sem unidade repetida no título da coluna
            tab["dica_busca"] = tabelas.dica_busca(rid, t["titulo"], len(t["linhas"]))
            sel = selecao(t, tab, consulta)              # um clique no pedido: as de baixo só com ele (PC)
            juntas = tabelas.juntas_para_tela(t, [sel] if sel is not None else tab["idxs"], uf_ok or None, rid=rid)
            volta = request.url.path + "?" + request.url.query
            sit = fila.situacao(rid)
            recebido = ind.recebido_em(rid)               # T-0035: o do farol, não o do lote
            tab["edicao"] = edicao_tela(rid, t["titulo"], t, tab["linhas"], u, volta, sit, recebido)
            tab["novo"] = novo_tela(rid, t["titulo"], t, u, volta, sit, recebido)
            if uf_ok and rid in SEM_ESTADO_AVISO and not t.get("uf_linhas"):
                aviso_tabs_uf = tabelas.AVISO_SEM_ESTADO       # P3 A: a tabela sem a filial da nota vai da BAP inteira, com aviso
            for j in juntas:
                jt = next((x["tabela"] for x in t.get("juntas") or [] if x["tabela"]["titulo"] == j["tabela"]), None)
                j["edicao"] = edicao_tela(rid, j["tabela"], jt, j["linhas"], u, volta, sit, recebido)
        # RD-0023 (decisão do gerente, 26/11): o aviso "Sem filtro por estado" do Visita é um só, na faixa (`_bc3_cab.html`)
        aviso_uf = aviso_tabs_uf
        # §10.7.2 (`kpis_padrao`), §10.7.6 e D5: os cartões da aba só valem no padrão; com filtro, recorte ou estado
        # eles saem e entra o AVISO_CARTOES. Os de cima (`topo["kpis"]`) seguem a RN-GER-006 e vêm prontos do núcleo.
        aviso_kpis = ""
        kpis_da_aba = False                             # A1 (revisão): só o `kpis_padrao` leva o cartão inteiro à faixa
        if rid in tabelas.FAROIS_LIVRES:                # T-0024: a mesma faixa (a do Resumo) em todas as abas do lote 2
            if tab["filtrado"] or uf_ok:                # filtro ou estado: os cartões da aba saem (§10.7.2)
                kpis, aviso_kpis = [], tabelas.AVISO_CARTOES
            else:
                kpis = topo["kpis"]
        elif t.get("kpis_padrao") is not None and not solicitacao:
            if tab["filtrado"] or (uf_ok and rid != "vc_meta"):
                kpis, aviso_kpis = [], tabelas.AVISO_CARTOES
            else:
                kpis = render.kpis_para_tela(t["kpis_padrao"])
                kpis_da_aba = True
        else:
            kpis = topo["kpis"]
        uf = uf_ok
        urls = urls_tabela(request, rid, aba, tab, sub, uf, bool(tab.get("fora_base") and tab["fora_base"]["mostrar"]))
        if linhas:                                      # "carregar mais": só as linhas da página pedida (mesmo corte de perfil)
            return pagina(request, "_linhas.html", tabela=tab, **urls, **ctx)
        return pagina(request, "farol.html", tela=None, tabela=tab, juntas=juntas, kpis=kpis, **urls,
                      faixa=True, ufs=ufs, uf=uf, subnomes=subnomes, sub=sub,
                      ed_enviada=edicoes.MSG_ENVIADA if consulta.get("ed") == ["1"] else "",
                      aviso_uf=aviso_uf, aviso_kpis=aviso_kpis, kpis_da_aba=kpis_da_aba, titulo_aba=t["titulo"], **ctx)

    # ------------------------------------------------------------ T-0026: parcial em imagem e exportação
    QUANDOS = (("acum", "Acumulado"), ("d1", "D-1"), ("hoje", "Hoje"))
    PARCIAIS = ("pv_pedidos", "vc_visitas", "pl_entregas")

    def tem_parcial(u, rid):
        """RN-GER-018: a parcial é de quem vê a tela do farol; a de Entregas lista cliente: também só quem vê a tabela (perfil)."""
        return rid in PARCIAIS and acesso.pode_ver(u, rid) and (rid != "pl_entregas" or u["perfil"] in tabelas.VE_TABELAS[rid])

    def parciais_de(rid, u):
        """{quando: {"rotulo","png"}} do farol, só para quem pode ver (senão PermissionError)."""
        if not tem_parcial(u, rid):
            raise PermissionError
        return ind.parciais(rid)                        # T-0035: {quando: {"rotulo", "arquivo"}} do disco

    def csvs_de(rel, rid, perfil):
        """T-0021: CSVs para importar no Protheus, só em Pedidos e para quem vê as tabelas do farol (admin, gerente, pre_venda)."""
        if rid != "pv_pedidos" or perfil not in tabelas.VE_TABELAS[rid]:
            return []
        return sorted(ind.csvs(rid), key=lambda c: c["nome"], reverse=True)

    @app.get("/farol/pv_pedidos/csv/{nome}")
    async def csv_protheus(request: Request, nome: str):
        u = usuario(request)
        exige(u, "pv_pedidos")
        if u["perfil"] not in tabelas.VE_TABELAS["pv_pedidos"]:
            raise PermissionError
        c = next((x for x in csvs_de(rel_do("pv_pedidos") or {}, "pv_pedidos", u["perfil"]) if x["nome"] == nome), None)
        if c is None:
            return JSONResponse({"erro": "arquivo indisponível"}, status_code=404)
        cobranca.registrar_acesso(cfg.dados, u["login"], "pv_pedidos", "csv-protheus", "baixar")
        return baixar(c["conteudo"].encode("utf-8"), "text/csv; charset=utf-8", c["nome"])

    @app.get("/farol/an_divergencias/correcao.xlsx")
    async def correcao_xlsx(request: Request):
        """T-0036 (contrato §10.11.4): o Excel de correção do A1_VEND, só para o admin; sem cliente (RN-GER-011)."""
        u = usuario(request, ("admin",))
        exige(u, "an_divergencias")
        c = ind.correcao("an_divergencias")
        if not c:
            return JSONResponse({"erro": "arquivo indisponível"}, status_code=404)
        cobranca.registrar_acesso(cfg.dados, u["login"], "an_divergencias", "correcao", "baixar")
        return baixar(exportar.xlsx_correcao(c),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      f"correcao_divergencias_{datetime.now(MANAUS):%Y%m%d_%H%M}.xlsx")

    def baixar(dados: bytes, tipo: str, nome: str, anexo: bool = True):
        cab = {"Content-Disposition": f'{"attachment" if anexo else "inline"}; filename="{nome}"',
               "Cache-Control": "no-store", "X-Robots-Tag": "noindex"}
        return Response(dados, media_type=tipo, headers=cab)

    def nome_do(rid, q):
        return f"parcial_{rid.split('_', 1)[1]}_{q}_{datetime.now(MANAUS):%Y%m%d_%H%M}"

    @app.get("/farol/{rid}/parcial", response_class=HTMLResponse)
    async def parcial(request: Request, rid: str, q: str = "acum"):
        u = usuario(request)
        pars = parciais_de(rid, u)
        opcoes = [(k, nome) for k, nome in QUANDOS if k in pars]
        if not opcoes:
            return pagina(request, "parcial.html", farol_nome=render.FAROIS[rid][0], rid=rid, opcoes=[], q="")
        q = q if q in pars else opcoes[0][0]
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, "parcial-" + q, "ver")
        return pagina(request, "parcial.html", farol_nome=render.FAROIS[rid][0], rid=rid, opcoes=opcoes, q=q,
                      rotulo=pars[q].get("rotulo", ""), noindex=True, pdf_ok=True)

    @app.get("/farol/{rid}/parcial.png")
    async def parcial_png(request: Request, rid: str, q: str = "acum"):
        u = usuario(request)
        par = parciais_de(rid, u).get(q)
        raw = par["arquivo"].read_bytes() if isinstance(par, dict) else None
        if raw is None:
            return JSONResponse({"erro": "parcial indisponível"}, status_code=404)
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, "parcial-" + q, "png")
        return baixar(raw, "image/png", nome_do(rid, q) + ".png", anexo=request.query_params.get("baixar") == "1")

    @app.get("/farol/{rid}/parcial.pdf")
    async def parcial_pdf(request: Request, rid: str, q: str = "acum"):
        u = usuario(request)
        par = parciais_de(rid, u).get(q)
        raw = par["arquivo"].read_bytes() if isinstance(par, dict) else None
        pdf = exportar.pdf_imagem(raw, f"{marca.EMPRESA} · {render.FAROIS[rid][0]} · {par.get('rotulo', '')}") if raw else None
        if pdf is None:
            return JSONResponse({"erro": "parcial indisponível"}, status_code=404)
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, "parcial-" + q, "pdf")
        return baixar(pdf, "application/pdf", nome_do(rid, q) + ".pdf")

    def tabelas_para_exportar(request, u, rid, aba, todas):
        """[(tabela plana)] do que a pessoa vê (o que a tela mostra, todas as páginas). PermissionError fora do perfil."""
        perfil, rel, consulta = u["perfil"], rel_do(rid), consulta_de(request)
        exige_farol(u, rid)
        if not rel:
            raise PermissionError
        abas = []                                          # (titulo no pacote, bruta, consulta)
        if rid in tabelas.RIDS:
            for c, tit in tabelas.abas_do_farol(rid, rel):
                if (todas or c == aba) and tabelas.ve_aba(rid, c, perfil):
                    t = next((x for x in rel.get("tabelas") or [] if x.get("titulo") == tit), None)
                    if t:
                        abas.append((c, t))
            ufs = render.recortes_farol(rel)
            uf = request.query_params.get("uf", "").upper()[:2]
            uf = uf if uf in ufs and not todas else ""
        elif rid == cobranca.RID and perfil in cobranca.VE_TABELAS:
            for c, tit in cobranca.ABA_TABELA.items():
                if todas or c == aba:
                    t = next((x for x in rel.get("tabelas") or [] if x.get("titulo") == tit), None)
                    if t:
                        abas.append((c, t))
            uf = ""
        if not abas:
            raise PermissionError
        saida = []
        for c, t in abas:
            q = {} if todas else consulta
            if t.get("subabas"):                           # Solicitação BAP: a sub-aba escolhida (ou todas, no Excel completo)
                n = len(t["subabas"])
                try:
                    k0 = int(q.get("sub", ["0"])[0])
                except ValueError:
                    k0 = 0
                subs = range(n) if todas else [min(max(k0, 0), n - 1)]
                for k in subs:
                    _, tela = tabelas.subabas_para_tela(t, k, q, pagina_tam=10 ** 9)
                    saida.append(exportar.tabela_plana(tela, t["subabas"][k]))
                continue
            if rid == cobranca.RID:
                cols = cobranca.colunas_esperadas(t["titulo"], t["colunas"])
                tela = tabelas.tabela_para_tela(t, q, pagina_tam=10 ** 9, ordem_tela=cobranca.ordem_tela(t["titulo"], cols),
                                                centavos=True, total_sempre=True, vazios_no_fim=False, titulo=t["titulo"])
            else:
                tela = tabelas.tabela_para_tela(t, q, uf=uf or None, pagina_tam=10 ** 9)
            saida.append(exportar.tabela_plana(tela, t, centavos=rid == cobranca.RID))
        return saida

    @app.get("/farol/{rid}/exportar")
    async def exportar_tabela(request: Request, rid: str, aba: str = "", formato: str = "xlsx", todas: str = ""):
        u = usuario(request)
        if formato not in ("xlsx", "pdf") or (formato == "pdf" and todas):
            return JSONResponse({"erro": "formato inválido"}, status_code=400)
        tabs = tabelas_para_exportar(request, u, rid, aba, bool(todas))
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba or "todas", formato)
        nome = f"{rid}_{'todas' if todas else aba}_{datetime.now(MANAUS):%Y%m%d_%H%M}"
        if formato == "xlsx":
            return baixar(exportar.xlsx(tabs), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          nome + ".xlsx")
        t = tabs[0]
        rod = f"{marca.EMPRESA} · {render.FAROIS[rid][0]} · {len(t['linhas'])} linhas · dados de {fmt_manaus(ind.gerado_em(rid))}"
        return baixar(exportar.pdf_tabela(t, rod), "application/pdf", nome + ".pdf")

    # ------------------------------------------------------------ T-0021: edição (admin e, nas Entregas, o pós-venda)
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
        """Por linha da tela: botão de editar (quem edita o lugar, com chave) e a marca "Aguardando o PC"/"O PC recusou".
        Sem `edicao` no pacote, ou perfil sem edição e sem marca, a coluna não aparece."""
        ed = t_pc.get("edicao") if isinstance(t_pc, dict) else None
        if not isinstance(ed, dict):
            return None
        pode = edicoes.pode_editar(u["perfil"], (rid, titulo))
        algum = False
        for ln in linhas:
            ch = edicoes.chave_da_linha(ed, ln["k"])
            s = sit.get((titulo, ch)) if ch else None
            m = edicoes.marca(s, recebido)
            url = (f"/farol/{rid}/editar?" + urlencode({"tab": titulo, "chave": ch, "volta": volta})
                   if pode and ch else "")
            ln["ed"] = {"url": url, "marca": m, "dica": edicoes.dica(s, ed, m, pode), "sem_chave": pode and not ch,
                          "msg_sem_chave": edicoes.msg_sem_chave(rid, titulo)}
            algum = algum or bool(m)
        if not pode and not algum:
            return None
        return {"cab": ed.get("acao") or "Editar", "pode": pode}

    SEM_ESTADO_AVISO = ("pl_garantias", "pl_devolucoes", "pl_ncc")
    RESUMO_PELA_GRADE = SEM_ESTADO_AVISO + ("pl_entregas",)     # T-0054: "NF 900502 · CLIENTE ... · MA"

    def novo_tela(rid, titulo, t_pc, u, volta, sit, recebido):
        """O botão da linha nova (`novo`, §10.9.2): só o admin (RN-POS-011: o pós-venda edita a linha, não cria), só onde o pacote traz `edicao.novo`.
        O servidor decide; quem não é admin não recebe nem o botão nem a contagem."""
        ed = t_pc.get("edicao") if isinstance(t_pc, dict) else None
        nv = ed.get("novo") if isinstance(ed, dict) else None
        if not nv or not edicoes.pode_criar(u["perfil"], (rid, titulo)):
            return None
        n = edicoes.contagem_novas(sit, titulo, recebido)
        return {"rotulo": nv["rotulo"], "url": f"/farol/{rid}/editar?" + urlencode({"tab": titulo, "novo": "1", "volta": volta}),
                "pendentes": n["pendentes"], "recusadas": n["recusadas"],
                "marca": f"{n['pendentes']} · {edicoes.MSG_AGUARDA}" if n["pendentes"] else "",
                "erro": f"{n['recusadas']} · {edicoes.MSG_ERRO}" if n["recusadas"] else ""}

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

    def resumo_da_linha(rid, titulo, cols, linha):
        """Qual linha se edita. Faróis do Pós-venda: a chave e o nome da GRADE, mais a UF ("NCC 901 · CLIENTE ... · PA");
        os outros: as 6 primeiras colunas, como na T-0021."""
        g = tabelas.GRADE.get((rid, titulo)) if rid in RESUMO_PELA_GRADE else None
        nomes = [str(c["nome"]).upper() for c in cols]
        if not g:
            return [render.fmt_celula(linha[i], c["tipo"]) for i, c in enumerate(cols)
                    if not c.get("oculta") and linha[i] not in (None, "")][:6]
        saida = []
        for n, rot in ((g["chave"], True), (g["cel"][1], False), ("UF", False)):
            if n in nomes and not (n == "UF" and g["cel"][1] == "UF"):
                v = render.fmt_celula(linha[nomes.index(n)], cols[nomes.index(n)]["tipo"])
                v = tabelas.cod_e_nome(v)[1]
                if v:
                    saida.append(f"{n} {v}" if rot else v)
        return saida

    def form_ctx(rid, titulo, t, aba, k, sit_linha, volta, digitado=None, erro=""):
        """`digitado` (volta de um erro): o que a pessoa escreveu (`c_`) volta; só o campo recusado fica vazio e marcado."""
        ed = t["edicao"]
        digitado = digitado or {}
        cols, linha = t["colunas"], t["linhas"][k]
        nomes = [c["nome"] for c in cols]
        pend = (sit_linha or {}).get("valores") or {} if (sit_linha or {}).get("status") == "pendente" else {}
        campos = []
        for c in edicoes.campos_da_linha(ed, k):
            v = linha[nomes.index(c["coluna"])] if c.get("coluna") in nomes else None
            atual = edicoes.atual_txt(c, v)
            ops = list(c["opcoes_linha"])
            if atual and atual not in ops and c["tipo"] == "lista":
                ops = [atual] + ops                       # como o PC: o valor de hoje entra na lista
            ruim = bool(erro) and erro.startswith(c["rotulo"] + ":")
            if "c_" + c["campo"] in digitado:
                atual = "" if ruim else str(digitado["c_" + c["campo"]])[:edicoes.MAX_TEXTO_TETO]
                if atual and c["tipo"] == "lista" and atual not in ops:
                    ops = [atual] + ops
            campos.append(edicoes.campo_tela(c, atual, ops, sugestao=c.get("sugestao", ""), pendente=pend.get(c["campo"]),
                                             invalido=ruim))
        liga = next((j for j in t.get("juntas") or [] if j.get("liga")), None)
        ver = f"/farol/{rid}?aba={aba}&sel={k}" if liga and aba else ""      # "Ver pedido", como no PC
        return dict(farol_nome=render.FAROIS[rid][0], rid=rid, tab=titulo, chave=ed["chaves"][k],
                    acao=ed.get("acao") or "Editar", resumo=resumo_da_linha(rid, titulo, cols, linha), campos=campos,
                    volta=volta, ver_pedido=ver, sit=sit_linha, noindex=True)

    def novo_ctx(rid, titulo, t, aba, volta, valores=None):
        """O formulário da linha nova (§10.9.2): os campos sem `linhas`, cada um com o `padrao` dele. Sem linha de origem,
        não há resumo nem "Ver pedido". O ticket sugerido vem do pacote: a web não calcula número. Na volta de um erro,
        o que a pessoa digitou (`c_`) e o padrão que o formulário mostrou (`p_`) voltam como estavam."""
        ed = t["edicao"]
        valores = valores or {}
        obrig = edicoes.LUGARES_NOVO.get((rid, titulo), ())
        campos = [edicoes.campo_tela(c, str(valores.get("c_" + c["campo"], c["padrao_txt"])), list(c["opcoes_linha"]),
                                     padrao=c["padrao_txt"], mostrado=edicoes.mostrado(valores, c),
                                     obrigatorio=c["campo"] in obrig)
                  for c in edicoes.campos_novos(ed)]
        return dict(farol_nome=render.FAROIS[rid][0], rid=rid, tab=titulo, chave="", novo=True,
                    acao=ed["novo"]["rotulo"], resumo=[], campos=campos, volta=volta, ver_pedido="", sit=None,
                    noindex=True)

    def volta_ed(volta):
        return RedirectResponse(volta + ("&" if "?" in volta else "?") + "ed=1", status_code=303)

    @app.get("/farol/{rid}/editar", response_class=HTMLResponse)
    async def editar_get(request: Request, rid: str, tab: str = "", chave: str = "", volta: str = "", novo: str = ""):
        u = usuario(request)
        exige_farol(u, rid)
        if not edicoes.pode_editar(u["perfil"], (rid, tab[:80])):
            raise PermissionError                       # só quem a EDITA_LUGAR diz (RN-GER-012, RN-POS-011)
        volta = volta_ok(rid, volta)
        t, aba = tabela_editavel(rid, tab[:80])
        ed = (t or {}).get("edicao")
        if novo == "1":                                 # linha nova (§10.9.2): só o admin, só onde o pacote traz `edicao.novo`
            if not edicoes.pode_criar(u["perfil"], (rid, tab)):
                raise PermissionError
            if not (isinstance(ed, dict) and ed.get("novo")):
                return pagina(request, "erro.html", status=404, titulo_erro=edicoes.TITULO_SEM_NOVO, msg=edicoes.MSG_SEM_NOVO)
            return pagina(request, "editar.html", erro="", aviso="", **novo_ctx(rid, tab, t, aba, volta))
        k = edicoes.linha_da_chave(ed, chave[:80]) if isinstance(ed, dict) else None
        if k is None:
            return pagina(request, "erro.html", status=404,
                          titulo_erro="Linha não encontrada",
                          msg="Esta linha não está mais no pacote do PC. Volte ao farol e abra de novo.")
        sit = fila.situacao(rid).get((tab, chave))
        return pagina(request, "editar.html", erro="", aviso="",
                      **form_ctx(rid, tab, t, aba, k, sit, volta))

    @app.post("/farol/{rid}/editar")
    async def editar_post(request: Request, rid: str):
        u = usuario(request)
        exige_farol(u, rid)
        if u["perfil"] not in edicoes.perfis_do_rid(rid):
            raise PermissionError                       # 403 antes de ler o formulário
        f = await formulario(request)                   # CSRF errado = 403
        tab, chave = str(f.get("tab", ""))[:80], str(f.get("chave", ""))[:80]
        if not edicoes.pode_editar(u["perfil"], (rid, tab)):
            raise PermissionError                       # o lugar exato (RN-POS-011)
        volta = volta_ok(rid, f.get("volta"))
        t, aba = tabela_editavel(rid, tab)
        ed = (t or {}).get("edicao")
        if f.get("novo") == "1":
            return await editar_novo(request, u, rid, tab, t, aba, ed, f, volta)
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
                          aviso="" if erro else "Nada mudou.",
                          **form_ctx(rid, tab, t, aba, k, sit, volta, digitado=f if erro else None, erro=erro))
        try:
            fila.registrar(usuario=u["login"], rid=rid, tabela=tab, modulo=ed["modulo"], chave=chave,
                           valores=mudou, antes=antes, perfil=u["perfil"])
        except OSError:
            log.error("edição: falha ao gravar a fila")
            return pagina(request, "editar.html", status=503, erro=edicoes.MSG_FALHA_FILA,
                          aviso="", **form_ctx(rid, tab, t, aba, k, sit, volta))
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba or "-", "editar")
        return volta_ed(volta)

    async def editar_novo(request, u, rid, tab, t, aba, ed, f, volta):
        """POST da linha nova (§10.9.2): só o admin; vai só o que difere do `padrao`, mais o ticket; chave NOVO-xxxxxxxx; `antes.ticket`."""
        if not edicoes.pode_criar(u["perfil"], (rid, tab)):
            raise PermissionError
        if not (isinstance(ed, dict) and ed.get("novo")):
            return pagina(request, "erro.html", status=409, titulo_erro=edicoes.TITULO_SEM_NOVO, msg=edicoes.MSG_SEM_NOVO)
        valores, antes, erro = edicoes.valores_do_novo(ed, f, edicoes.LUGARES_NOVO.get((rid, tab), ()))
        if erro:
            return pagina(request, "editar.html", status=400, erro=erro, aviso="",
                          **novo_ctx(rid, tab, t, aba, volta, f))
        try:
            fila.registrar(usuario=u["login"], rid=rid, tabela=tab, modulo=ed["modulo"], chave=edicoes.chave_nova(),
                           valores=valores, antes=antes, novo=True, perfil=u["perfil"])
        except OSError:
            log.error("edição: falha ao gravar a fila")
            return pagina(request, "editar.html", status=503, erro=edicoes.MSG_FALHA_FILA,
                          aviso="", **novo_ctx(rid, tab, t, aba, volta, f))
        cobranca.registrar_acesso(cfg.dados, u["login"], rid, aba or "-", "editar-novo")
        return volta_ed(volta)

    @app.get("/farol/{rid}/linhas", response_class=HTMLResponse)
    @app.get("/farol/{rid}", response_class=HTMLResponse)
    async def farol(request: Request, rid: str, uf: str = "", aba: str = "resumo"):
        linhas = request.url.path.endswith("/linhas")   # T-0033: a mesma regra de perfil, só as linhas
        u = usuario(request)
        exige_farol(u, rid)                             # perfil + exceções do admin conferidos no servidor (RN-GER-018)
        perfil = u["perfil"]
        if rid in tabelas.RIDS:
            return farol_abas(request, u, rid, aba, uf, linhas=linhas)
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
            tem = {t["titulo"] for t in rel["tabelas"]}              # T-0026: robô antigo não manda as 5 de resumo
            abas = [(c, n) for c, n in cobranca.ABAS
                    if c == "resumo" or (c in cobranca.ABA_TABELA and perfil in cobranca.VE_TABELAS
                                         and cobranca.ABA_TABELA[c] in tem)
                    or (c == "cobrar" and perfil in cobranca.COBRA)]
        ctx = dict(farol_nome=nome, rid=rid, abas=abas if len(abas) > 1 else [], aba=aba, noindex=aba != "resumo",
               ufs_off=render.recortes_farol(rel))
        if aba == "resumo":
            return pagina(request, "farol.html", tela=render.farol_para_tela(rel, uf[:4] or None, rid), **ctx)
        if "tabelas" not in rel:                        # robô antigo: sem as abas novas
            return pagina(request, "farol.html", tela=None, **ctx)
        if aba in cobranca.ABA_TABELA:
            titulo = cobranca.ABA_TABELA[aba]
            t = next((x for x in rel["tabelas"] if x["titulo"] == titulo), None)
            if t is None:                               # aba de resumo que o robô ainda não manda
                return pagina(request, "farol.html", tela=None, **ctx)
            tab = cobranca.tabela_para_tela(t, titulo, consulta_de(request))
            urls = urls_tabela(request, rid, aba, tab, None, "", False)
            if linhas:
                return pagina(request, "_linhas.html", tabela=tab, **urls, **ctx)
            return pagina(request, "farol.html", tela=None, kpis=render.farol_para_tela(rel, None, rid)["kpis"],
                          tabela=tab, **urls, **ctx)
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
        return pagina(request, "farol.html", tela=None, kpis=render.farol_para_tela(rel, None, rid)["kpis"],
                      fila=pendentes[ini:ini + cobranca.FILA_POR_PAGINA],
                      tratados=tratados if pag == paginas else [], n_fila=len(pendentes), n_tratados=len(tratados),
                      pag=pag, paginas=paginas, pc_ate=cob["gerado_em"], pacote_sha=ind.sha(cobranca.RID), **ctx)

    @app.post("/farol/pl_inadimplencia/cobranca")
    async def cobrar(request: Request):
        u = usuario(request, cobranca.COBRA)
        exige(u, cobranca.RID)
        f = await formulario(request)
        # §10.6.4: o item sai do pacote da página (se ainda entre os 7); senão do vigente; senão 404
        def acha(rel):
            cob = rel.get("cobranca") if isinstance(rel, dict) else None
            return next((i for i in (cob or {}).get("fila", []) if i["cod"] == f.get("cliente")), None)
        sha_pag = f.get("pacote_sha", "")
        item, sha_item = None, ""
        if sha_pag and sha_pag != ind.sha(cobranca.RID):
            item = acha(pacotes.por_sha(cfg.dados, cobranca.RID, sha_pag))
            sha_item = sha_pag
        if not item:
            item, sha_item = acha(ind.farol(cobranca.RID)), ind.sha(cobranca.RID)
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
    def linhas_usuarios(reabrir: str = "", marcados=None) -> list[dict]:
        """A lista da tela Usuários, com o acesso de cada um (marcados, partes, selos, última mudança)."""
        saida = []
        for x in usuarios.listar():
            marc = set(marcados) if (marcados is not None and x["login"] == reabrir) else acesso.visiveis(x["perfil"], x["acesso"])
            tirados, liberados = acesso.contagem(x)
            saida.append({**x, "partes": acesso.partes(x["perfil"], marc), "tirados": tirados, "liberados": liberados,
                          "alterado": usuarios.ultima_mudanca(x["login"]), "aberto": x["login"] == reabrir})
        return saida

    def tela_usuarios(request, status=200, msg="", erro="", reabrir="", marcados=None, novo_aberto=False):
        return pagina(request, "usuarios.html", status=status, lista=linhas_usuarios(reabrir, marcados), perfis=PERFIS,
                      novo_partes={**{p: acesso.partes(p, acesso.padrao_do_perfil(p)) for p in PERFIS},
                                   "__generico__": acesso.partes("", set())},
                      novo_aberto=novo_aberto, msg=msg, erro=erro)

    def resumo_mudancas(alvo, mud) -> str:
        lib = [acesso.nome_do(r) for r, sinal, _ in mud if sinal == "+"]
        tir = [acesso.nome_do(r) for r, sinal, _ in mud if sinal == "-"]
        txt = f"Acesso de {alvo} salvo."
        if lib:
            txt += f" Liberado: {', '.join(lib)}."
        if tir:
            txt += f" Tirado: {', '.join(tir)}."
        return txt

    @app.get("/usuarios", response_class=HTMLResponse)
    async def usuarios_get(request: Request):
        usuario(request, ("admin",))
        return tela_usuarios(request)

    @app.post("/usuarios")
    async def usuarios_post(request: Request):
        eu = usuario(request, ("admin",))
        f = await formulario(request)
        acao, alvo = f.get("acao"), (f.get("login") or "").strip().lower()
        marcados = set(f["_multi"].get("farol", []))
        reabrir, msg = "", "Feito."
        try:
            if acao == "criar":
                perfil = f.get("perfil", "")
                if f.get("lista") != "1":               # sem JS: as caixas são só as liberadas; o perfil entra sempre
                    marcados |= acesso.padrao_do_perfil(perfil)
                usuarios.criar(alvo, f.get("senha", ""), perfil, marcados=marcados if (marcados or f.get("lista") == "1") else None, quem=eu["login"])
            elif acao == "acesso":
                reabrir = alvo
                if f.get("lista") != "1":
                    raise Erro(MSG_LISTA_MUDOU)
                msg = resumo_mudancas(alvo, usuarios.definir_acesso(alvo, marcados, eu["login"]))
                reabrir = ""
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
        except ErroGravacao as e:
            log.error("acesso de usuário: falha ao gravar")
            return tela_usuarios(request, status=503, erro=str(e), reabrir=reabrir, marcados=marcados, novo_aberto=acao == "criar")
        except Erro as e:
            return tela_usuarios(request, status=400, erro=str(e), reabrir=reabrir, marcados=marcados, novo_aberto=acao == "criar")
        if acao == "acesso" or acao == "criar":
            log.info("acesso de usuário alterado")
        return tela_usuarios(request, msg=msg)

    # ------------------------------------------------------------ pacote do robô
    def bearer(request: Request, esperado: str):
        """Bearer em tempo constante: 401 se faltar, errar ou se o segredo não estiver configurado."""
        auth = request.headers.get("authorization", "")
        entrada = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not esperado or not hmac.compare_digest(entrada.encode(), esperado.encode()):
            return JSONResponse({"erro": "não autorizado"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        return None

    def sem_token(request: Request):
        return bearer(request, cfg.token)

    # ------------------------------------------------------------ porta de leitura (T-0055, RN-GER-020, contrato §10.12)
    limite = leitura.Limite()
    METODOS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

    def _ip(request: Request) -> str:
        """O último item do X-Forwarded-For é o que o proxy do Render acrescenta; sem ele, o par da conexão."""
        xff = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        return xff or (request.client.host if request.client else "-")

    def _muitas():
        return JSONResponse({"erro": "muitas chamadas"}, status_code=429, headers={"Retry-After": "60"})

    def _porta(request: Request):
        """A ordem do desenho: 404 desligada, 429 (IP), 405, 401, 429 (total, só com token válido). Devolve a recusa ou None.
        O IP só vale em memória, para o limite. As falhas não gravam em `acessos/`: viram contadores e, a cada minuto,
        uma linha agregada no log (sem token, query nem IP)."""
        if not cfg.leitura_token:
            return JSONResponse({"erro": "não encontrado"}, status_code=404)
        linha = limite.agregada()
        if linha:
            log.warning("porta de leitura: %s", linha)
        if not limite.ip_ok(_ip(request)):
            limite.falha("limite")
            return _muitas()
        if request.method != "GET":
            return JSONResponse({"erro": "só leitura"}, status_code=405, headers={"Allow": "GET"})
        negado = bearer(request, cfg.leitura_token)
        if negado:
            limite.falha("negado")
            return negado
        if not limite.total_ok():
            limite.falha("limite")
            return _muitas()
        return None

    def dados_ate(rel):
        """O `baixado_em` do farol como a tela mostra (`fmt_manaus`); None se o pacote não traz."""
        return fmt_manaus(rel["baixado_em"]) if rel.get("baixado_em") else None

    def _entrega(rid: str, saida: dict):
        saida = leitura.limpar(saida)
        saida["versao_web"] = VERSAO
        rid_log = rid if rid in render.FAROIS or rid == PAINEL_RID else "-"
        cobranca.registrar_acesso(cfg.dados, "porta-leitura", rid_log, "ok", "api")
        return JSONResponse(saida)

    @app.api_route("/api/leitura/painel", methods=METODOS)
    async def api_leitura_painel(request: Request):
        recusa = _porta(request)
        if recusa:
            return recusa
        rel = ind.farol(PAINEL_RID)
        saida = leitura.montar_painel(rel, ind.indice(), carimbo(ind, PAINEL_RID), dados_ate(rel)) \
            if isinstance(rel, dict) and acesso.perfil_ve(leitura.PERFIL, PAINEL_RID) else None
        if not saida or not saida["visoes"]:
            return JSONResponse({"erro": "sem pacote"}, status_code=503)
        return _entrega(PAINEL_RID, saida)

    @app.api_route("/api/leitura/resumo/{rid}", methods=METODOS)
    async def api_leitura_resumo(request: Request, rid: str):
        recusa = _porta(request)
        if recusa:
            return recusa
        if rid == PAINEL_RID or not acesso.perfil_ve(leitura.PERFIL, rid):       # o que o diretor não vê: 404
            return JSONResponse({"erro": "não encontrado"}, status_code=404)
        rel = rel_do(rid)
        if rel is None:
            return JSONResponse({"erro": "sem pacote"}, status_code=503)
        return _entrega(rid, leitura.montar_resumo(rid, rel, ind.indice(), carimbo(ind, rid), dados_ate(rel)))

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

    # ------------------------------------------------------------ visitas da Máxima (T-0045, contrato visitas-nuvem)
    def sem_token_cron(request: Request):
        """O token do cron só abre as rotas do §3 (não o pacote, não as edições)."""
        return bearer(request, vis.token)

    @app.exception_handler(visitas.ErroVisitas)
    async def _erro_visitas(request, e):
        return JSONResponse(e.corpo, status_code=e.status)

    async def ler_corpo(request: Request, limite: int, msg: str = "corpo grande demais") -> bytes:
        """O corpo inteiro, em partes, com teto: passou = 413 (ErroVisitas)."""
        bruto = b""
        async for parte in request.stream():
            bruto += parte
            if len(bruto) > limite:
                raise visitas.ErroVisitas(413, {"erro": msg})
        return bruto

    async def corpo_json(request: Request, limite: int = 65536):
        try:
            return json.loads((await ler_corpo(request, limite)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise visitas.ErroVisitas(400, {"erro": "corpo não é JSON"})

    @app.get("/api/visitas/trabalho")
    async def api_visitas_trabalho(request: Request):
        return sem_token_cron(request) or vis.trabalho()

    @app.post("/api/visitas/rodada")
    async def api_visitas_rodada(request: Request):
        return sem_token_cron(request) or JSONResponse(vis.conceder(await corpo_json(request)), status_code=201)

    @app.post("/api/visitas/rodada/{rid}/progresso")
    async def api_visitas_progresso(request: Request, rid: str):
        return sem_token_cron(request) or vis.progresso(rid, await corpo_json(request))

    @app.post("/api/visitas/rodada/{rid}/dia/{dia}")
    async def api_visitas_lote(request: Request, rid: str, dia: str):
        negado = sem_token_cron(request)
        if negado:
            return negado
        bruto = await ler_corpo(request, visitas.LOTE_GZ_MAX, "lote grande demais")
        h = request.headers
        # a leitura dos Excel (zip, regex) é trabalho de CPU: fora do laço de eventos, para não travar o site
        return await run_in_threadpool(vis.receber_lote, rid, dia, h.get("content-type", ""),
                                       h.get("content-encoding", ""), h.get("x-bap-sha256", ""), bruto)

    @app.post("/api/visitas/rodada/{rid}/fim")
    async def api_visitas_fim(request: Request, rid: str):
        return sem_token_cron(request) or vis.fim(rid, await corpo_json(request))

    # robô do PC (BAP_WEB_TOKEN): a mesma forma da /api/edicoes
    @app.get("/api/visitas/lotes")
    async def api_visitas_lotes(request: Request):
        negado = sem_token(request)
        if negado:
            return negado
        bruto = request.query_params.get("desde", "0")
        if not (bruto.isascii() and bruto.isdigit()) or len(bruto) > 15:
            return JSONResponse({"erro": "desde precisa ser inteiro >= 0"}, status_code=400)
        return vis.lotes(int(bruto))

    @app.get("/api/visitas/lote/{seq}")
    async def api_visitas_lote_corpo(request: Request, seq: int):
        negado = sem_token(request)
        if negado:
            return negado
        achou = vis.corpo_do_lote(seq)
        if not achou:
            return JSONResponse({"erro": "lote não existe ou saiu pela retenção"}, status_code=404)
        return Response(achou[0], media_type="application/json",
                        headers={"Content-Encoding": "gzip", "X-BAP-SHA256": achou[1]})

    @app.post("/api/visitas/lotes/confirmar")
    async def api_visitas_confirmar(request: Request):
        return sem_token(request) or vis.confirmar(await corpo_json(request, 262144))

    # tela "Atualizar visitas" (Farol de Visita): sessão e perfil conferidos aqui, em toda rota
    @app.get("/visitas/atualizar", response_class=HTMLResponse)
    async def visitas_tela(request: Request):
        u = usuario(request)
        exige(u, "vc_visitas")
        if not acesso.perfil_ve(u["perfil"], "vc_visitas"):
            raise PermissionError                       # o liberado vê só o Resumo: a tela de atualizar é de quem tem o farol pelo perfil (P4 A)
        flash = request.session.pop("visitas_msg", None) or {}
        return pagina(request, "visitas.html", v=vis.tela(),
                      pode_pedir=u["perfil"] in PODEM_PEDIR, admin=u["perfil"] in SO_ADMIN,
                      msg=flash.get("msg", ""), erro=flash.get("erro", ""))

    async def acao_visitas(request: Request, perfis, fn):
        u = usuario(request, perfis)
        exige(u, "vc_visitas")
        f = await formulario(request)
        try:
            request.session["visitas_msg"] = {"msg": fn(f, u)}
        except visitas.ErroVisitas as e:
            request.session["visitas_msg"] = {"erro": e.corpo.get("erro", "Não foi possível.")}
        return RedirectResponse("/visitas/atualizar", status_code=303)

    @app.post("/visitas/atualizar")
    async def visitas_atualizar(request: Request):
        return await acao_visitas(request, PODEM_PEDIR, lambda f, u: vis.pedir(
            f.get("de", ""), f.get("ate", ""), False, u["perfil"]))

    @app.post("/visitas/refazer")
    async def visitas_refazer(request: Request):
        return await acao_visitas(request, SO_ADMIN, lambda f, u: vis.pedir(
            f.get("de", ""), f.get("ate", ""), True, u["perfil"]))

    @app.post("/visitas/retomar")
    async def visitas_retomar(request: Request):
        return await acao_visitas(request, SO_ADMIN, lambda f, u: vis.retomar(f.get("recado", ""), u["perfil"]))

    @app.post("/visitas/diagnostico")
    async def visitas_diagnostico(request: Request):
        return await acao_visitas(request, SO_ADMIN, lambda f, u: vis.diagnostico())

    @app.post("/visitas/agenda")
    async def visitas_agenda(request: Request):
        return await acao_visitas(request, SO_ADMIN, lambda f, u: vis.agenda(f.get("ligar") == "1"))

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
        ind.esvaziar()                                   # T-0035: baixa o pico de memória antes do corpo grande
        try:
            corpo = json.loads(b"".join(partes))
        except (ValueError, RecursionError):
            return JSONResponse({"erro": "JSON inválido"}, status_code=422)
        del partes
        erros = pacotes.validar(corpo)
        if erros:
            return JSONResponse({"erro": "esquema inválido", "detalhes": erros}, status_code=422)
        # formato 1: a web divide o pacote num lote (origem "inteiro"); a aba com CPF/CNPJ cai por farol
        try:
            pacotes.gravar(cfg.dados, corpo, datetime.now(MANAUS).isoformat(timespec="seconds"))
        except pacotes.ErroPacote as e:
            return JSONResponse(e.corpo, status_code=e.status)
        log.info("pacote recebido: %s (%d bytes)", pacotes.nome_arquivo(corpo["gerado_em"]), total)
        return {"ok": True, "gerado_em": corpo["gerado_em"], "bytes": total}

    @app.post("/api/pacote/{lote}/farol/{rid}")
    async def api_pacote_farol(request: Request, lote: str, rid: str):
        """T-0035, contrato §10.8.3: um farol (gzip ou não), conferido pelo sha256, guardado no lote em recebimento."""
        negado = sem_token(request)
        if negado:
            return negado
        if not pacotes.RE_LOTE.fullmatch(lote):
            return JSONResponse({"erro": "lote inválido"}, status_code=400)
        if rid not in pacotes.ACEITOS:
            return JSONResponse({"erro": "relatório não aceito"}, status_code=404)
        h = request.headers
        if h.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return JSONResponse({"erro": "só application/json"}, status_code=415)
        cod = h.get("content-encoding", "").strip().lower()
        if cod not in ("", "gzip"):
            return JSONResponse({"erro": "Content-Encoding só gzip"}, status_code=415)
        sha = h.get("x-bap-sha256", "").strip().lower()
        if not pacotes.RE_SHA.fullmatch(sha):
            return JSONResponse({"erro": "X-BAP-SHA256 mal formado"}, status_code=400)
        cl = h.get("content-length")
        if cl is not None and (not cl.isdigit() or int(cl) > pacotes.FAROL_GZ_MAX):
            return JSONResponse({"erro": "farol grande demais"}, status_code=413)
        t0, partes, total = time.monotonic(), [], 0
        async for parte in request.stream():
            total += len(parte)
            if total > pacotes.FAROL_GZ_MAX:
                return JSONResponse({"erro": "farol grande demais"}, status_code=413)
            partes.append(parte)
        try:
            bruto = b"".join(partes)
            del partes
            if cod == "gzip":
                bruto = pacotes.descomprimir(bruto, pacotes.FAROL_CORPO_MAX)
            elif len(bruto) > pacotes.FAROL_CORPO_MAX:
                return JSONResponse({"erro": "farol grande demais"}, status_code=413)
            ent = pacotes.receber_farol(cfg.dados, lote, rid, bruto, sha, cfg.farol_max)
        except pacotes.ErroPacote as e:
            return JSONResponse(e.corpo, status_code=e.status)
        log.info("farol recebido: %s gz=%d json=%d ms=%d rss_mb=%s", rid, total, ent["bytes_json"],
                 int((time.monotonic() - t0) * 1000), pacotes.memoria(ind)["rss_mb"])
        return {"ok": True, "rid": rid, "sha256": sha, "bytes_json": ent["bytes_json"]}

    @app.post("/api/pacote/{lote}/fechar")
    async def api_pacote_fechar(request: Request, lote: str):
        """T-0035, contrato §10.8.4: confere o topo e os faróis, aplica o `manter` (§4.4) e troca o vigente."""
        negado = sem_token(request)
        if negado:
            return negado
        if not pacotes.RE_LOTE.fullmatch(lote):
            return JSONResponse({"erro": "lote inválido"}, status_code=400)
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return JSONResponse({"erro": "só application/json"}, status_code=415)
        partes, total = [], 0
        async for parte in request.stream():
            total += len(parte)
            if total > FECHAR_MAX:
                return JSONResponse({"erro": "corpo grande demais"}, status_code=413)
            partes.append(parte)
        try:
            corpo = json.loads(b"".join(partes))
        except (ValueError, RecursionError):
            return JSONResponse({"erro": "JSON inválido"}, status_code=400)
        if not isinstance(corpo, dict):
            return JSONResponse({"erro": "corpo precisa ser objeto JSON"}, status_code=400)
        try:
            r = pacotes.fechar(cfg.dados, lote, corpo, corpo.get("farois"), corpo.get("manter"),
                               datetime.now(MANAUS).isoformat(timespec="seconds"))
        except pacotes.ErroPacote as e:
            return JSONResponse(e.corpo, status_code=e.status)
        log.info("lote fechado: %s farois=%d herdados=%d vigente=%s", lote, r["farois"], len(r["herdados"]), r["vigente"])
        return r

    return app
