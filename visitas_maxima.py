# -*- coding: utf-8 -*-
"""
ATUALIZAR VISITAS - baixa da Maxima (maxGestao > Painel Auditoria) o Espelho
de Rotas (Analitico) de cada representante, dia a dia, e monta com ele o
sintetico e o acompanhamento.

    pythonw visitas_maxima.py          (ou o botao "Atualizar visitas" do
                                        Farol de Visita)

O caminho, igual ao que a gente faz na mao:
    1. app.solucoesmaxima.com.br/login  (usuario e senha pedidos na hora;
       a senha NUNCA e gravada - so o usuario fica no visitas_config.json)
    2. o cartao maxGestao  ->  o maxGestao novo (maxgestao-pwa)
    3. Painel Auditoria: marca TODAS as filiais, supervisores e
       representantes
    4. (18/10) para cada dia: Data inicial = Data final = o dia, PESQUISAR e,
       para cada representante da grade: o OLHO (ultima coluna, Acoes) ->
       IMPRIMIR -> no Espelho de Rotas: Salvar > Arquivo Microsoft Excel >
       OK (Configuracao de Exportacao) ->
         RELATORIOS/Visitas/ANALITICO/<NOME>/VISITA-<NOME>-DD-MM-AAAA-HH-MM.xlsx
       (DD-MM-AAAA = o dia da visita; HH-MM = quando foi salvo). Um vendedor
       que der erro nao para os outros: o print fica em Visitas/_erros.
    5. O SINTETICO SAI DESSES EXCEL (o GridRca nao e mais baixado): o
       cabecalho do Espelho tem os mesmos numeros -> diario/AAAAMMDD.csv
       (no formato do GridRca, o Farol de Visita le igual) e AAAAMM.csv
       (a soma do mes, o Farol de Metas).
    6. ACOMPANHAMENTO_VISITAS_BAP.xlsx: acrescenta os dias fechados.
    7. VISITAS_POR_CLIENTE.xlsx: cliente a cliente (visitado na agenda,
       fora da agenda, agendado e nao visitado).

Dia ja baixado e FECHADO (baixado num dia depois dele) nao baixa de novo,
a nao ser que marque "Baixar de novo".

Precisa do Playwright (pip install playwright). Usa o Edge ou o Chrome que
ja estao no computador - nao baixa navegador. Se faltar, a janela oferece
instalar.

Se der erro, a tela do navegador fica em RELATORIOS/Visitas/_erros/ (sem
senha) para a gente ver onde parou.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys

# (29/10, Alexandre: "o minimo de pasta possivel") o cache do Python fica fora
# da pasta do BAP (no %LOCALAPPDATA%\BAP_TOOLS\cache de cada maquina): sem
# __pycache__ na pasta e sem sincronizar cache pelo OneDrive.
try:
    import os as _os_c
    sys.pycache_prefix = sys.pycache_prefix or _os_c.path.join(
        _os_c.environ.get("LOCALAPPDATA") or _os_c.path.join(
            _os_c.path.dirname(_os_c.path.abspath(__file__)), "SISTEMA BAP"),
        *(("BAP_TOOLS", "cache") if _os_c.environ.get("LOCALAPPDATA")
          else ("cache",)))
except Exception:                                       # noqa: BLE001
    pass
import threading
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import relatorios_nucleo                                   # noqa: E402
import visitas_nucleo as vn                               # noqa: E402

URL_LOGIN = os.environ.get("BAP_MAXIMA_LOGIN",
                           "https://app.solucoesmaxima.com.br/login")
URL_PWA = os.environ.get("BAP_MAXIMA_PWA",
                         "https://maxgestao-pwa.solucoesmaxima.com.br")
URL_AUDITORIA = URL_PWA + "/painel-auditoria"
ARQ_CONFIG = AQUI / "visitas_config.json"
MAX_DIAS = 93                # um trimestre por vez

# o gancho que roda em toda pagina: guarda as abas que o site tenta abrir
# (o maxGestao abre o sistema em aba nova - aqui a gente abre na mesma) e o
# texto do CSV que o botao de download monta
GANCHO_JS = r"""
(() => {
  if (window.__bapGancho) return;
  window.__bapGancho = true;
  window.__bapAbertos = [];
  window.open = function (u) {
    try { window.__bapAbertos.push(String(u)); } catch (e) {}
    return null;
  };
  const cria = URL.createObjectURL;
  URL.createObjectURL = function (b) {
    try {
      if (b && b.text && /csv|text/i.test(b.type || ''))
        b.text().then(t => { window.__bapCsv = t; });
    } catch (e) {}
    return cria.apply(URL, arguments);
  };
})();
"""

# tira da frente tour, aviso de notificacao e afins (nada que aceite termo)
LIMPAR_JS = r"""
(() => {
  document.querySelectorAll('.driver-overlay,.driver-popover,'
    + '#onesignal-slidedown-container,#onesignal-bell-container')
    .forEach(e => e.remove());
  const b = document.querySelector('#onesignal-slidedown-cancel-button');
  if (b) b.click();
  return true;
})()
"""

CAPTCHA_JS = r"""
() => {
  // so captcha VISIVEL (caixa na tela); o selo do reCAPTCHA invisivel nao conta
  const vis = e => {
    if (e.closest('.grecaptcha-badge')) return false;
    const r = e.getBoundingClientRect(), st = getComputedStyle(e);
    return r.width >= 60 && r.height >= 40 && st.visibility !== 'hidden'
      && st.display !== 'none' && st.opacity !== '0';
  };
  return Array.from(document.querySelectorAll(
    'iframe[src*="captcha" i], iframe[title*="captcha" i], .g-recaptcha, '
    + '.h-captcha')).some(vis);
}
"""

CARTOES_JS = r"""
() => {
  const out = [];
  document.querySelectorAll('mat-card').forEach((c, i) => {
    if (c.classList.contains('card-sem-licenca')) return;
    let p = c, secao = '';
    for (let k = 0; k < 8 && p; k++) {
      p = p.parentElement;
      const t = (p && p.innerText || '').trim();
      if (/^Solu[cç][oõ]es para a/i.test(t)) { secao = t.slice(0, 60); break; }
    }
    out.push({i: i, secao: secao});
  });
  return out;
}
"""

# o estado do "marcar todos" de cada filtro (0 filiais, 1 supervisores,
# 2 representantes): o botao fica DENTRO da caixa do campo, junto com as
# etiquetas (chips) do que esta marcado. Marcado de verdade = caixinha
# marcada E etiquetas na caixa (a caixinha pisca marcada enquanto carrega)
ESTADO_TODOS_JS = r"""
(i) => {
  const inp = document.querySelectorAll('input[placeholder^="Selecione"]')[i];
  let box = inp ? inp.parentElement : null;
  while (box && !box.querySelector('#selectAllButton')) box = box.parentElement;
  const b = box ? box.querySelector('#selectAllButton')
                : document.querySelectorAll('#selectAllButton')[i];
  if (!b) return {st: 'sem', chips: 0};
  b.setAttribute('data-bap-todos', String(i));
  const c = b.querySelector('input[type=checkbox]');
  const chips = box ? box.querySelectorAll('.MuiChip-root').length : 0;
  return {st: (c && c.checked) ? 'marcado' : (b.disabled ? 'off' : 'on'),
          chips: chips};
}
"""

EQUIPE_JS = r"""
() => {
  const listas = [];
  document.querySelectorAll('input[placeholder^="Selecione"]').forEach(inp => {
    const raiz = inp.closest('.MuiAutocomplete-root') ||
                 inp.closest('.MuiFormControl-root') || inp.parentElement;
    let itens = [...raiz.querySelectorAll('.MuiChip-label')]
                  .map(e => e.innerText.trim());
    if (!itens.length)
      itens = (raiz.innerText || '').split('\n').map(s => s.trim())
                .filter(s => /^\d+\s*-/.test(s));
    listas.push(itens);
  });
  return listas;
}
"""


# (18/10) VISITA POR CLIENTE - o OLHO da coluna Acoes de cada representante.
# A coluna fica no fim da grade (rolagem para a direita): rola tudo o que
# rola de lado, acha os olhos DENTRO das linhas da grade (fora de janela
# aberta) e marca cada um com data-bap-olho=<n>. Devolve a chave da linha
# (data-id / indice / texto) para nao clicar duas vezes no mesmo
OLHOS_JS = r"""
() => {
  // (18/10, CONFERIDO NA MAXIMA) a grade e um MUI DataGrid: cada linha e
  // .MuiDataGrid-row[data-id="147509-0101006"] (representante-filial) e o
  // olho e o botao da celula [data-field="acoes"] (icone fa-eye)
  const out = [], vistos = new Set();
  const marca = (alvo, linha) => {
    if (!alvo || vistos.has(alvo)) return;
    vistos.add(alvo);
    const chave = linha.getAttribute('data-id')
      || linha.getAttribute('data-rowindex')
      || linha.getAttribute('aria-rowindex')
      || (linha.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    alvo.setAttribute('data-bap-olho', String(out.length));
    out.push({k: out.length, chave: String(chave),
              txt: (linha.innerText || '').replace(/\s+/g, ' ').trim()
                     .slice(0, 120)});
  };
  document.querySelectorAll('.MuiDataGrid-row').forEach(linha => {
    marca(linha.querySelector('[data-field="acoes"] button'), linha);
  });
  if (out.length) return out;
  // reserva: qualquer icone de olho dentro de uma linha de grade
  const ehOlho = el => /visibility|fa-eye|eye|olho|visualiz/i.test(
    [el.getAttribute('data-testid'), el.getAttribute('class'),
     el.getAttribute('aria-label'), el.getAttribute('title')].join(' '));
  document.querySelectorAll('svg, i, span, button, [role="button"]')
    .forEach(el => {
      if (!ehOlho(el)) return;
      const linha = el.closest('[role="row"], tr');
      if (!linha || el.closest('[role="dialog"]')) return;
      marca(el.closest('button, [role="button"], a') || el, linha);
    });
  return out;
}
"""

# a grade so desenha as linhas que estao na tela (MUI DataGrid): rola para
# baixo; devolve false quando ja estava no fim
ROLAR_GRADE_JS = r"""
() => {
  const v = document.querySelector('.MuiDataGrid-virtualScroller');
  if (!v) return false;
  const antes = v.scrollTop;
  v.scrollTop = antes + Math.max(150, v.clientHeight * 0.7);
  return v.scrollTop !== antes;
}
"""

TOPO_GRADE_JS = r"""
() => { const v = document.querySelector('.MuiDataGrid-virtualScroller');
        if (v) v.scrollTop = 0; return true; }
"""

# a janela do representante (abre no olho): tem o botao IMPRIMIR. Marca o
# botao com data-bap-imprimir e devolve o texto da janela (o nome do
# vendedor e a primeira linha)
DIALOGO_JS = r"""
() => {
  const vis = e => !!(e && e.getClientRects().length);
  const ds = [...document.querySelectorAll(
      '[role="dialog"], .MuiDialog-paper, mat-dialog-container, '
      + '.modal-content')].filter(vis);
  for (const d of ds.reverse()) {
    const b = [...d.querySelectorAll('button, [role="button"]')].find(
      b => vis(b) && /^\s*imprimir\s*$/i.test(b.innerText || ''));
    if (!b) continue;
    document.querySelectorAll('[data-bap-imprimir]').forEach(
      x => x.removeAttribute('data-bap-imprimir'));
    b.setAttribute('data-bap-imprimir', '1');
    // (conferido 18/10) Status GPS e um icone: ToggleOnIcon / ToggleOffIcon
    const on = d.querySelector('[data-testid="ToggleOnIcon"]');
    const off = d.querySelector('[data-testid="ToggleOffIcon"]');
    const v = /Vers[aã]o:\s*([\d.]+)/i.exec(d.innerText || '');
    return {texto: (d.innerText || '').slice(0, 3000),
            gps: on ? true : (off ? false : null), versao: v ? v[1] : ''};
  }
  return null;
}
"""

SUB_ANALITICO = vn.SUB_ANALITICO


def nome_limpo(nome: str) -> str:
    """O nome do vendedor como vai na pasta e no arquivo (sem os caracteres
    que o Windows recusa)."""
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(nome or ""))
    nome = re.sub(r"\s+", " ", nome).strip().strip(".").upper()
    return nome or "SEM NOME"


def arquivo_analitico(raiz, nome: str, dia: date, quando: datetime,
                      ext: str = ".xlsx") -> Path:
    """RELATORIOS/Visitas/ANALITICO/<NOME>/VISITA-<NOME>-DD-MM-AAAA-HH-MM.xlsx
    DD-MM-AAAA = o DIA da visita; HH-MM = a hora em que foi salvo (se ja
    existir um no mesmo minuto, acrescenta -2, -3...)."""
    nome = nome_limpo(nome)
    pasta = vn.pasta_analitico(raiz) / nome
    base = f"VISITA-{nome}-{dia:%d-%m-%Y}-{quando:%H-%M}"
    arq = pasta / f"{base}{ext}"
    n = 2
    while arq.exists():
        arq = pasta / f"{base}-{n}{ext}"
        n += 1
    return arq


def gravar_excel_importado(raiz, pasta: str, nome: str, conteudo: bytes):
    """Grava um Excel que veio da nuvem no ANALITICO (RN-VIS-003, contrato
    §4.4): `.tmp` + `os.replace`; mesmo sha256 que ja existe (com ou sem
    sufixo -2, -3...) = pula; outro conteudo no mesmo nome = sufixo novo
    (`arquivo_analitico`). NUNCA sobrescreve nem apaga. Devolve
    (caminho, "novo" | "igual") ou levanta ValueError se pasta/nome nao
    casam (o chamador ja conferiu; e a ultima trava)."""
    import hashlib                                       # noqa: PLC0415
    m = vn._RX_ARQ_ANALITICO.match(nome or "")
    if (not m or nome_limpo(pasta) != pasta or m.group("nome") != pasta
            or any(c in nome for c in "/\\") or ".." in nome):
        raise ValueError("nome")
    dia = date(int(m.group("a")), int(m.group("m")), int(m.group("d")))
    quando = datetime(dia.year, dia.month, dia.day, int(m.group("h")),
                      int(m.group("mi")))
    ext = Path(nome).suffix.lower()
    dest_dir = vn.pasta_analitico(raiz) / pasta
    sha = hashlib.sha256(conteudo).hexdigest()
    base = f"VISITA-{pasta}-{dia:%d-%m-%Y}-{quando:%H-%M}"
    if dest_dir.is_dir():
        for f in sorted(dest_dir.iterdir()):
            if (f.suffix.lower() == ext and re.fullmatch(
                    re.escape(base) + r"(-\d+)?", f.stem)):
                try:
                    if hashlib.sha256(f.read_bytes()).hexdigest() == sha:
                        return f, "igual"
                except OSError:
                    continue
    destino = arquivo_analitico(raiz, pasta, dia, quando, ext)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(conteudo)
    os.replace(tmp, destino)
    return destino, "novo"


def nome_do_vendedor(texto: str, conhecidos) -> str:
    """O nome do vendedor na janela do olho: o nome da equipe da Maxima que
    aparece no texto (o mais comprido); senao, a primeira linha."""
    alvo = vn._sem_acento(texto or "").upper()
    achados = [n for n in conhecidos
               if n and vn._sem_acento(n).upper() in alvo]
    if achados:
        return max(achados, key=len)
    for linha in (texto or "").splitlines():
        if linha.strip():
            return linha.strip()
    return ""


class ErroRobo(Exception):
    """Erro com recado para o usuario. `codigo` (um dos do contrato, §5) e
    `fase` (§3.3) so existem quando quem levantou sabe; o PC ignora."""

    def __init__(self, msg="", codigo: str | None = None,
                 fase: str | None = None):
        super().__init__(msg)
        self.codigo = codigo
        self.fase = fase


class Cancelado(Exception):
    pass


# =========================================================================
# T-0045: codigos e fases fixos (contrato visitas-nuvem v1, §3.3 e §5). A
# nuvem nao tira print: manda so o codigo e a fase.
# =========================================================================
FASES = ("login", "inicio", "maxgestao", "menu", "filtros", "grade",
         "espelho", "filtro", "salvar", "envio")
CODIGOS_LOGIN = ("MAXIMA_SENHA", "MAXIMA_CONFIRMACAO", "MAXIMA_CAPTCHA",
                 "MAXIMA_BLOQUEIO")
FECHADOS_PC_DIAS = 40
AVISO_SITE_BAIXANDO = ("O site está baixando agora; baixar aqui também pode "
                       "derrubar a sessão da Máxima. Continuar?")

_RX_URL_VERIFICACAO = re.compile(
    r"verific|confirm|mfa|2fa|otp|autentic|dispositivo|device|termo|"
    r"redefin|trocar-?senha|alterar-?senha", re.I)
_RX_BLOQUEIO = re.compile(
    r"conta bloquead|usuario bloquead|acesso (foi )?(negado|bloquead)|"
    r"bloquead[ao] (por|temporari)|403 forbidden|forbidden", re.I)
_RX_CONFIRMACAO = re.compile(
    r"codigo (de )?(verificacao|seguranca|confirmacao|acesso|enviado)|"
    r"(enviamos|enviado|informe|digite).{0,40}codigo|\bsms\b|"
    r"novo dispositivo|dispositivo (nao )?(reconhecid|confiavel)|"
    r"confirm(e|ar|acao) (o |seu |sua )?(dispositivo|acesso|identidade|"
    r"e-?mail)|autenticacao (em|de) (dois|2)|aceit(e|ar) (o |os )?termo|"
    r"termos? (de uso|e condicoes)|trocar? (a |sua )?senha|"
    r"(altere|redefina|crie|defina|troque|cadastre) (a |sua |uma |o seu )?"
    r"(nova )?senha|nova senha|senha nova|senha (expirou|"
    r"expirada)|primeiro acesso", re.I)
_RX_CREDENCIAL = re.compile(
    r"senha|usuario|credencia|invalid|incorret|inexistente|nao (foi )?"
    r"(encontrad|autorizad)|erro ao (entrar|autentic)|login", re.I)


def _caminho(url) -> str:
    """So o caminho da URL (sem host, query nem #): a verificacao olha ali."""
    from urllib.parse import urlparse                   # noqa: PLC0415
    try:
        return urlparse(str(url or "")).path
    except ValueError:
        return ""


def _sem_acento_min(txt) -> str:
    return vn._sem_acento(str(txt or "")).lower()


def classificar_login(url, texto, tem_captcha, http_status) -> str | None:
    """Depois do "Entrar" (contrato §5.1). Funcao pura. Devolve o codigo da
    Maxima que pede parada ou None (saiu do /login, segue). `texto` = a
    mensagem de erro da tela (ou o texto da pagina de verificacao).
    Nunca tenta resolver captcha nem repete o login."""
    if http_status == 403:
        return "MAXIMA_BLOQUEIO"
    url = _caminho(url)
    no_login = "/login" in url.lower()
    if not (no_login or _RX_URL_VERIFICACAO.search(url)):
        return None
    if tem_captcha:
        return "MAXIMA_CAPTCHA"
    t = _sem_acento_min(texto)
    if _RX_BLOQUEIO.search(t):
        return "MAXIMA_BLOQUEIO"
    if _RX_CONFIRMACAO.search(t):
        return "MAXIMA_CONFIRMACAO"
    if not no_login:
        # caminho de verificacao (so o caminho da URL): com qualquer redacao,
        # a Maxima pediu confirmacao; nunca repete o login (§5.1)
        return "MAXIMA_CONFIRMACAO"
    if no_login and t.strip() and _RX_CREDENCIAL.search(t):
        return "MAXIMA_SENHA"
    return None


_RX_NAVEGADOR_CAIU = re.compile(
    r"target (page, context or browser has been )?closed|browser has been "
    r"closed|browser (has )?crash|page crashed|out of memory|"
    r"cannot allocate memory|connection closed", re.I)


def codigo_da_excecao(exc, fase: str | None = None):
    """(codigo, fase) do contrato §5 para uma excecao do Robo. Funcao pura.
    Nunca olha a mensagem da Maxima para o codigo, so a classe e as marcas
    do proprio navegador."""
    if isinstance(exc, ErroRobo):
        if exc.codigo:
            return exc.codigo, exc.fase or fase
        return "TELA_MUDOU", exc.fase or fase
    nome = type(exc).__name__
    if _RX_NAVEGADOR_CAIU.search(str(exc) or ""):
        return "NAVEGADOR_FALHOU", fase
    if nome == "TimeoutError" and fase == "login":
        return "MAXIMA_FORA", fase
    if nome == "TimeoutError":
        return "TELA_MUDOU", fase
    return "ERRO_INTERNO", fase


def fechados_pc(indice: dict, hoje: date, dias: int = FECHADOS_PC_DIAS
                ) -> dict:
    """{AAAAMMDD: iso com -04:00} dos dias dos ultimos `dias` dias que o
    `_baixados.json` do PC conhece (contrato §4.3). Funcao pura. Chave de
    mes (AAAAMM) e data torta ficam fora. [SUPOSICAO] o relogio do PC e o de
    Manaus."""
    saida = {}
    corte = hoje - timedelta(days=dias)
    for chave, v in (indice or {}).items():
        if not re.fullmatch(r"\d{8}", str(chave)):
            continue
        try:
            dia = datetime.strptime(chave, "%Y%m%d").date()
            quando = datetime.fromisoformat(str(v))
        except ValueError:
            continue
        if corte <= dia <= hoje:
            saida[chave] = quando.replace(tzinfo=None).isoformat(
                timespec="seconds") + "-04:00"
    return saida


def aviso_site_baixando(saude) -> str | None:
    """O aviso do botao do PC (contrato §4.5) quando o /saude diz que o site
    esta com a rodada ativa. Funcao pura."""
    try:
        if (saude or {}).get("visitas", {}).get("rodada_ativa"):
            return AVISO_SITE_BAIXANDO
    except AttributeError:
        pass
    return None


def consultar_saude(base=None, sessao=None, tempo=5):
    """GET <site>/saude (sem login). None se nao der (sem URL, rede, 404):
    o botao do PC segue sem aviso. Nunca levanta."""
    try:
        if not base:
            import bap_automation as ba                   # noqa: PLC0415
            base = ba._base_web(ba._segredo_web("BAP_WEB_URL", "url"))
        if not base:
            return None
        sessao = sessao or __import__("requests")
        r = sessao.get(f"{base}/saude", timeout=tempo)
        return r.json() if r.status_code == 200 else None
    except Exception:                                    # noqa: BLE001
        return None


# =========================================================================
# o que baixar
# =========================================================================
def indice_do_pc(raiz, de: date, ate: date) -> dict:
    """{AAAAMMDD: iso} dos dias fechados no PC entre `de` e `ate`. A leitura
    "arquivo do dia -> hora da baixa" e a do nucleo (vn.dia_fechado e
    vn.baixado_em); aqui so se monta o indice para vn.dias_a_baixar."""
    ind = {}
    for d in vn.dias_entre(de, ate):
        if vn.dia_fechado(raiz, d):
            chave = f"{d:%Y%m%d}"
            ind[chave] = vn.baixado_em(
                raiz, chave, vn.arquivo_do_dia(raiz, d)).isoformat()
    return ind


def plano(raiz, de: date, ate: date, refazer=False, hoje: date | None = None):
    """([dias], [(ano, mes)]) que precisam ser baixados. Os dias vêm da
    função única do núcleo (RN-VIS-002), a mesma da nuvem."""
    hoje = hoje or relatorios_nucleo.hoje_manaus()
    ate = min(ate, hoje)
    dias = vn.dias_a_baixar(indice_do_pc(raiz, de, ate), de, ate, hoje,
                            refazer)
    # o arquivo do MES sai junto sempre que algum dia dele foi baixado
    # (antes: um AAAAMM.csv antigo, posto a mao, fazia o mes ser pulado)
    com_dia = {(d.year, d.month) for d in dias}
    meses = [(a, m) for a, m in vn.meses_entre(de, ate)
             if refazer or (a, m) in com_dia
             or not vn.mes_fechado(raiz, a, m)]
    return dias, meses


def ler_config() -> dict:
    try:
        return json.loads(ARQ_CONFIG.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def gravar_usuario(usuario: str) -> None:
    cfg = ler_config()
    cfg["usuario"] = usuario       # SO o usuario. Senha nunca.
    try:
        ARQ_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                              "utf-8")
    except OSError:
        pass


# =========================================================================
# Playwright: instalar e abrir o navegador
# =========================================================================
def tem_playwright() -> bool:
    try:
        import playwright.sync_api                       # noqa: F401,PLC0415
        return True
    except Exception:                                    # noqa: BLE001
        return False


def _python_console() -> str:
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe" and (py.parent / "python.exe").exists():
        return str(py.parent / "python.exe")
    return str(py)


def _rodar(cmd, log) -> int:
    flags = 0x08000000 if os.name == "nt" else 0          # sem janela preta
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace",
                            creationflags=flags)
    for linha in proc.stdout:
        linha = linha.rstrip()
        if linha:
            log(linha[:160])
    return proc.wait()


def instalar_playwright(log) -> bool:
    log("Instalando o Playwright (uma vez só)…")
    cod = _rodar([_python_console(), "-m", "pip", "install", "--upgrade",
                  "playwright", "--disable-pip-version-check"], log)
    import importlib                                     # noqa: PLC0415
    importlib.invalidate_caches()
    ok = cod == 0 and tem_playwright()
    log("Playwright instalado." if ok else
        "Não consegui instalar o Playwright (internet/proxy?).")
    return ok


ARGS_NUVEM = ["--disable-dev-shm-usage"]


def _abrir_navegador(p, visivel, log, canal: str | None = None):
    """Sem `canal`: Edge, Chrome e o Chromium do Playwright (o PC, como
    sempre). Com `canal` (T-0045): so ele; "chromium" = o Chromium da imagem
    da nuvem (sem instalar nada, com --disable-dev-shm-usage)."""
    if canal:
        kw = {"headless": not visivel}
        if canal.lower() == "chromium":
            kw["args"] = list(ARGS_NUVEM)
        else:
            kw["channel"] = canal
        try:
            nav = p.chromium.launch(**kw)
        except Exception as e:                           # noqa: BLE001
            raise ErroRobo("Não consegui abrir o navegador.",
                           "NAVEGADOR_FALHOU") from e
        log(f"Navegador: {canal}")
        return nav
    erros = []
    for canal in ("msedge", "chrome", None):
        try:
            kw = {"headless": not visivel}
            if canal:
                kw["channel"] = canal
            nav = p.chromium.launch(**kw)
            log(f"Navegador: {canal or 'chromium do Playwright'}")
            return nav
        except Exception as e:                           # noqa: BLE001
            erros.append(f"{canal or 'chromium'}: {str(e).splitlines()[0]}")
    log("Sem Edge/Chrome: baixando o navegador do Playwright…")
    if _rodar([_python_console(), "-m", "playwright", "install", "chromium"],
              log) == 0:
        return p.chromium.launch(headless=not visivel)
    raise ErroRobo("Não consegui abrir o Edge nem o Chrome.\n" + "\n".join(erros))


# =========================================================================
# o robo
# =========================================================================
class Robo:
    def __init__(self, raiz, log, parar: threading.Event | None = None,
                 visivel=False, canal: str | None = None, foto=True,
                 eventos=False, ao_fechar_dia=None, ao_fase=None):
        """PC: so (raiz, log, parar, visivel), como sempre. Nuvem (T-0045):
        `canal="chromium"` (o da imagem), `foto=False` (sem print),
        `eventos=True` (o log vira uma linha por evento, sem nome de
        pessoa; as frases livres ficam mudas), `ao_fechar_dia(d, resultado)`
        (chamado quando o dia termina, depois do sintetico) e
        `ao_fase(fase, dia, feitos, total)` (a cada troca de fase e a cada
        vendedor: o progresso do contrato §3.3)."""
        self.raiz = Path(raiz)
        self._saida = log
        self.eventos = bool(eventos)
        self.log = (lambda *_a, **_k: None) if self.eventos else log
        self.parar = parar or threading.Event()
        self.visivel = visivel
        self.canal = canal
        self.usar_foto = bool(foto)
        self.ao_fechar_dia = ao_fechar_dia
        self.ao_fase = ao_fase
        self.page = None
        self.foto = None
        self.onde = ""
        self.ctx = None
        self.analitico = None
        self.fase = None
        self.dia_atual = None
        self.codigo = None            # o codigo do contrato, se a rodada caiu
        self.fase_erro = None
        self.equipe = {}              # os 3 dicionarios lidos nos filtros
        self._abrindo = False         # abrindo o navegador (ainda sem pagina)
        self.vendedores = 0           # o que a grade mostrou, no ultimo dia

    # ---------------------------------------------------------- eventos
    @staticmethod
    def _campo(v) -> str:
        return re.sub(r"[^A-Za-z0-9_.:-]", "", str(v))[:40]

    def evento(self, nome, **campos):
        """Uma linha `evento=<nome> fase=.. dia=.. n=.. codigo=..` (so com
        `eventos=True`). So valor de lista fixa, numero e data: nunca nome."""
        if not self.eventos:
            return
        partes = [f"evento={self._campo(nome)}"]
        for k in ("fase", "dia", "n", "codigo"):
            if campos.get(k) not in (None, ""):
                partes.append(f"{k}={self._campo(campos[k])}")
        self._saida(" ".join(partes))

    def _fase(self, fase, dia=None, feitos=None, total=None):
        mudou = fase != self.fase
        self.fase = fase
        if dia is not None:
            self.dia_atual = dia
        if mudou:
            self.evento("fase", fase=fase, dia=self.dia_atual)
        if self.ao_fase and (mudou or feitos is not None):
            self.ao_fase(fase, self.dia_atual, feitos, total)

    def _registrar_falha(self, exc):
        """Guarda o codigo e a fase do contrato para quem chamou."""
        self.codigo, self.fase_erro = codigo_da_excecao(exc, self.fase)
        if self._abrindo and not (isinstance(exc, ErroRobo) and exc.codigo):
            self.codigo, self.fase_erro = "NAVEGADOR_FALHOU", "inicio"
        self.evento("erro", fase=self.fase_erro, codigo=self.codigo)

    # ---------------------------------------------------------- ajudantes
    def _checar(self):
        if self.parar.is_set():
            raise Cancelado()

    def _esperar(self, cond, seg, passo=0.4):
        fim = _time.time() + seg
        while _time.time() < fim:
            self._checar()
            try:
                v = cond()
            except Exception:                            # noqa: BLE001
                v = None
            if v:
                return v
            _time.sleep(passo)
        return None

    def _limpar(self):
        try:
            self.page.evaluate(LIMPAR_JS)
        except Exception:                                # noqa: BLE001
            pass

    def _abertos(self, trecho):
        try:
            for u in self.page.evaluate("window.__bapAbertos || []"):
                if trecho in u:
                    return u
        except Exception:                                # noqa: BLE001
            pass
        return None

    def foto_do_erro(self) -> Path | None:
        if not self.page or not self.usar_foto:
            return None
        try:
            pasta = vn.pasta_visitas(self.raiz) / "_erros"
            pasta.mkdir(parents=True, exist_ok=True)
            arq = pasta / f"erro_{datetime.now():%Y%m%d_%H%M%S}.png"
            self.page.screenshot(path=str(arq), full_page=True)
            return arq
        except Exception:                                # noqa: BLE001
            return None

    def url_limpa(self) -> str:
        try:
            return re.sub(r"PWE=[^&#]*", "PWE=…", self.page.url)
        except Exception:                                # noqa: BLE001
            return ""

    # ---------------------------------------------------------- passos
    def entrar(self, usuario, senha):
        pg = self.page
        self._fase("login")
        self.log("Abrindo o login da Máxima…")
        resp = pg.goto(URL_LOGIN, wait_until="domcontentloaded",
                       timeout=60000)
        if getattr(resp, "status", None) == 403:
            raise ErroRobo("A Máxima negou o acesso à página de login "
                           "(HTTP 403).", "MAXIMA_BLOQUEIO", "login")
        pg.wait_for_selector("input[name=username]", timeout=40000)
        pg.fill("input[name=username]", usuario)
        pg.fill("input[name=password]", senha)
        pg.click("button[type=submit]:has-text('Entrar')")
        self.log("Entrando…")

        def pronto():
            url = pg.url
            if ("/login" not in _caminho(url).lower()
                    and not _RX_URL_VERIFICACAO.search(_caminho(url))):
                return "ok"
            msg = pg.evaluate("""() => { const e = document.querySelector(
              'simple-snack-bar, .mat-mdc-snack-bar-label, mat-error, '
              + '.mat-mdc-form-field-error, .toast-message, '
              + '.swal2-html-container, .alert-danger');
              return e ? e.innerText.trim() : ''; }""")
            captcha = pg.evaluate(CAPTCHA_JS)
            texto = msg
            if not msg and "/login" not in _caminho(url).lower():
                texto = pg.evaluate(
                    "() => (document.body.innerText || '').slice(0, 3000)")
            cod = classificar_login(url, texto, captcha, None)
            if cod:
                return f"cod:{cod}:{msg}"
            if "/login" not in _caminho(url).lower():
                return "ok"
            return f"erro:{msg}" if msg else None
        r = self._esperar(pronto, 45)
        if not r:
            raise ErroRobo("O login não respondeu em 45 s.")
        if r.startswith("cod:"):
            _, cod, msg = r.split(":", 2)
            raise ErroRobo(self._texto_login(cod, msg), cod, "login")
        if r.startswith("erro:"):
            # mensagem de erro na tela de login que nao casou com nada:
            # tratada como credencial recusada (pausa; nunca repete o login)
            raise ErroRobo(self._texto_login("MAXIMA_SENHA", r[5:]),
                           "MAXIMA_SENHA", "login")
        self.log("Login ok.")

    def _texto_login(self, cod, msg) -> str:
        if cod == "MAXIMA_SENHA":
            # no PC a mensagem da Maxima ajuda a pessoa; na nuvem ela nunca
            # sai do navegador (contrato §5)
            return ("A Máxima recusou o login" +
                    ("" if self.eventos or not msg else f": {msg}"))
        return {"MAXIMA_CONFIRMACAO": "A Máxima pediu uma confirmação (código, "
                "novo dispositivo, termo ou troca de senha); faça o login "
                "uma vez à mão e tente de novo.",
                "MAXIMA_CAPTCHA": "A Máxima pediu captcha.",
                "MAXIMA_BLOQUEIO": "A Máxima bloqueou ou negou o acesso."
                }.get(cod, "A Máxima não deixou entrar.")

    def abrir_maxgestao(self):
        pg = self.page
        self._fase("inicio")
        if not self._esperar(lambda: pg.locator("mat-card").count(), 40):
            raise ErroRobo("A página inicial da Máxima não carregou os "
                           "cartões dos sistemas.")
        _time.sleep(1.0)
        cartoes = pg.evaluate(CARTOES_JS)
        cartoes.sort(key=lambda c: 0 if re.search(
            r"gest[aã]o comercial", c["secao"], re.I) else 1)
        url = None
        for c in cartoes:
            self._checar()
            pg.evaluate("window.__bapAbertos = []")
            card = pg.locator("mat-card").nth(c["i"])
            try:
                alvo = card.locator("img").first
                (alvo if alvo.count() else card).click(timeout=8000)
            except Exception:                            # noqa: BLE001
                continue
            url = self._esperar(lambda: self._abertos("maxgestao")
                                or ("maxgestao" in pg.url and pg.url), 10)
            if url:
                break
        if not url:
            raise ErroRobo("Não achei o cartão do maxGestão na página "
                           "inicial (o usuário tem licença do maxGestão?).")
        self._fase("maxgestao")
        self.log("Abrindo o maxGestão…")
        if url != pg.url:
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        # (13/10) A MAXIMA MUDOU: o cartao agora abre o maxGestao novo
        # (maxgestao-pwa, Painel Geral) DIRETO, na mesma aba. Antes o
        # maxGestao antigo abria o novo em aba nova - os dois caminhos valem
        no_pwa = self._esperar(lambda: "maxgestao-pwa" in pg.url, 15)
        if not no_pwa:
            pwa = self._esperar(lambda: self._abertos("maxgestao-pwa")
                                or ("maxgestao-pwa" in pg.url and pg.url), 30)
            if not pwa:
                raise ErroRobo("O maxGestão não abriu a tela nova "
                               "(maxgestao-pwa).")
            if pwa != pg.url:
                pg.goto(pwa, wait_until="domcontentloaded", timeout=60000)
        # (14/10) CONFERIDO NA TELA DE VERDADE: o maxGestao novo abre no
        # Painel Geral e pode ficar com o ?PWE= no endereco - entrou quando
        # o botao ☰ aparece (ou o Painel Geral, ou o token gravado). Antes
        # o robo exigia o endereco sem PWE e parava com a tela pronta.
        def entrou():
            if self._botao_menu() is not None:
                return True
            if "painel-geral" in pg.url:
                return True
            try:
                return bool(pg.evaluate("!!localStorage.getItem('token')")
                            and pg.locator("header, .MuiToolbar-root")
                            .count())
            except Exception:                            # noqa: BLE001
                return False
        if not self._esperar(entrou, 60):
            raise ErroRobo("O maxGestão novo não terminou de entrar.")
        self._limpar()
        self.log("maxGestão aberto (Painel Geral).")

    MENU = ("button[aria-label=menu]", "button[aria-label=Menu]",
            "button:has(mat-icon:text-is('menu'))",
            "mat-toolbar button:first-child", "header button:first-child")

    def _botao_menu(self):
        """O botao das 3 listras (canto de cima, a esquerda)."""
        for sel in self.MENU:
            try:
                b = self.page.locator(sel).first
                if b.count() and b.is_visible():
                    return b
            except Exception:                            # noqa: BLE001
                continue
        return None

    def _clicar_texto(self, padrao, seg=10) -> bool:
        """Clica no primeiro item VISIVEL do menu com esse texto."""
        rx = re.compile(padrao, re.I)

        def achar():
            try:
                loc = self.page.get_by_text(rx)
                for k in range(min(loc.count(), 12)):
                    if loc.nth(k).is_visible():
                        return loc.nth(k)
            except Exception:                            # noqa: BLE001
                return None
            return None
        alvo = self._esperar(achar, seg)
        if not alvo:
            return False
        try:
            alvo.click(timeout=8000)
            return True
        except Exception:                                # noqa: BLE001
            return False

    AUDITORIA_RX = r"^\s*painel\s+(de\s+)?auditoria\s*$"

    def _auditoria_pelo_menu(self) -> bool:
        """O caminho conferido na tela em 14/10:
            ☰ (menu)  >  Geolocalizacao  >  Painel de Auditoria
        (Inteligencia Geografica so tem o Mapa de Oportunidades). Primeiro
        pela busca do menu ("Pesquisar menu..." = Auditoria), que acha o
        item em qualquer grupo; senao abre o grupo na mao."""
        pg = self.page
        self._limpar()
        b = self._botao_menu()
        if b is None:
            return False
        try:
            b.click(timeout=8000)
        except Exception:                                # noqa: BLE001
            return False
        _time.sleep(0.8)
        self.log("  ☰ menu aberto")
        achou = False
        busca = pg.locator('input[placeholder^="Pesquisar menu"]')
        try:
            if busca.count() and busca.first.is_visible():
                busca.first.fill("Auditoria")
                _time.sleep(0.8)
                achou = self._clicar_texto(self.AUDITORIA_RX, 5)
                if achou:
                    self.log("  busca do menu: Auditoria > Painel de "
                             "Auditoria")
        except Exception:                                # noqa: BLE001
            achou = False
        if not achou:
            for grupo in (r"^\s*geolocaliza[cç][aã]o\s*$",
                          r"^\s*intelig[eê]ncia\s+geogr[aá]fica\s*$"):
                if self._clicar_texto(self.AUDITORIA_RX, 2):
                    achou = True
                    break
                if self._clicar_texto(grupo, 5):
                    _time.sleep(0.8)
                    if self._clicar_texto(self.AUDITORIA_RX, 5):
                        self.log("  Geolocalização > Painel de Auditoria")
                        achou = True
                        break
        if not achou:
            return False
        return bool(self._esperar(
            lambda: pg.locator("#dataInicialInput").count(), 40))

    def abrir_auditoria(self):
        pg = self.page
        self._fase("menu")
        self.log("Abrindo o Painel Auditoria…")
        # (13/10) primeiro pelo MENU, como sempre foi feito na mao (3
        # listras > Geolocalizacao > Painel de Auditoria); se o menu
        # nao responder, o endereco direto da tela
        if not self._auditoria_pelo_menu():
            self.log("Menu não respondeu - tentando o endereço direto…")
            pg.goto(URL_AUDITORIA, wait_until="domcontentloaded",
                    timeout=60000)
            if not self._esperar(
                    lambda: pg.locator("#dataInicialInput").count(), 30):
                if not self._auditoria_pelo_menu():
                    raise ErroRobo(
                        "O Painel de Auditoria não abriu (menu ☰ > "
                        "Geolocalização > Painel de Auditoria).")
        self._limpar()
        self._fase("filtros")
        self._marcar_todos()
        self._ler_equipe()

    FILTROS = ("Filiais", "Supervisores", "Representantes")

    def _estado(self, i) -> dict:
        try:
            return self.page.evaluate(ESTADO_TODOS_JS, i)
        except Exception:                                # noqa: BLE001
            return {"st": "sem", "chips": 0}

    def _todos_ok(self) -> bool:
        return all(self._estado(i)["st"] == "marcado"
                   and self._estado(i)["chips"] > 0 for i in range(3))

    def _calmo(self):
        """Espera a tela terminar de carregar (listas, filtros salvos)."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:                                # noqa: BLE001
            pass
        _time.sleep(2.0)

    def _marcar_em_ordem(self, seg=60) -> bool:
        """Filial -> supervisor -> representante, sempre nessa ordem: a cada
        volta acha o PRIMEIRO filtro que nao esta marcado e clica nele (se a
        tela desmarcar algo enquanto carrega, volta para ele). Pronto quando
        os tres ficam marcados por 3 s seguidos."""
        pg = self.page
        fim = _time.time() + seg
        firme_desde = None
        while _time.time() < fim:
            self._checar()
            est = [self._estado(i) for i in range(3)]
            falta = [i for i in range(3) if not (
                est[i]["st"] == "marcado" and est[i]["chips"] > 0)]
            if not falta:
                firme_desde = firme_desde or _time.time()
                if _time.time() - firme_desde >= 3:
                    return True
                _time.sleep(0.5)
                continue
            firme_desde = None
            i = falta[0]
            if est[i]["st"] == "on":
                try:
                    pg.locator(f'[data-bap-todos="{i}"]').first.click(
                        timeout=5000)
                except Exception:                        # noqa: BLE001
                    pass
                _time.sleep(2.0)
            else:
                _time.sleep(0.5)        # carregando a lista (ou desabilitado)
        return False

    def _marcar_todos(self):
        """Marca todas as filiais, depois todos os supervisores, depois
        todos os representantes. Se nao firmar, recarrega a tela e tenta
        de novo (ate 3 vezes)."""
        pg = self.page
        for tentativa in range(1, 4):
            if tentativa > 1:
                self.log(f"Os filtros não firmaram; recarregando a tela "
                         f"({tentativa}/3)…")
                pg.reload(wait_until="domcontentloaded", timeout=60000)
                self._esperar(lambda: pg.locator("#dataInicialInput").count(),
                              40)
                self._limpar()
            self._calmo()
            if self._marcar_em_ordem():
                n = [self._estado(i)["chips"] for i in range(3)]
                self.log(f"Marcados: {n[0]} filiais, {n[1]} supervisores, "
                         f"{n[2]} representantes.")
                return
        e = [self._estado(i) for i in range(3)]
        self.log("Estado dos filtros: " + "; ".join(
            f"{self.FILTROS[i]} {e[i]['st']} ({e[i]['chips']} marcados)"
            for i in range(3)))
        falta = [self.FILTROS[i] for i in range(3)
                 if not (e[i]["st"] == "marcado" and e[i]["chips"])]
        raise ErroRobo("Não consegui marcar todos em "
                       f"{', '.join(falta) or 'Representantes'}.")

    def _ler_equipe(self):
        try:
            listas = self.page.evaluate(EQUIPE_JS)
        except Exception:                                # noqa: BLE001
            return
        if len(listas) < 3:
            return

        def separar(txt):
            m = re.match(r"^\s*(\d+)\s*-\s*(.*)$", txt)
            return (m.group(1), m.group(2).strip()) if m else (None, txt)
        fil, sup, rep = {}, {}, {}
        for t in listas[0]:
            c, n = separar(t)
            if c:
                fil[c] = n
        for t in listas[1]:
            c, n = separar(t)
            if c:
                sup[c] = re.sub(r"\s*-\s*\(filial.*\)\s*$", "", n).strip()
        for t in listas[2]:
            c, n = separar(t)
            if c:
                m = re.search(r"\(Supervisor:\s*(\d+)\)", n)
                rep[c] = {"nome": re.sub(r"\s*\(Supervisor:.*\)\s*$", "",
                                         n).strip(),
                          "supervisor": m.group(1) if m else ""}
        self.equipe = {"filiais": fil, "supervisores": sup,
                       "representantes": rep}
        try:
            vn.gravar_equipe_maxima(self.raiz, fil, sup, rep)
        except OSError:
            pass

    def _datas(self, de: date, ate: date):
        pg = self.page
        a, b = de.isoformat(), ate.isoformat()
        for _ in range(3):
            pg.fill("#dataFinalInput", b)
            pg.fill("#dataInicialInput", a)
            pg.fill("#dataFinalInput", b)
            if (pg.input_value("#dataInicialInput") == a
                    and pg.input_value("#dataFinalInput") == b):
                return
            _time.sleep(0.5)
        raise ErroRobo(f"Não consegui pôr as datas {de:%d/%m/%Y} a "
                       f"{ate:%d/%m/%Y}.")

    def _pesquisar(self):
        pg = self.page
        try:
            with pg.expect_response(
                    lambda r: "/geolocalizacao/pesquisar" in r.url
                    and r.request.method != "OPTIONS",
                    timeout=120000) as info:
                pg.get_by_role("button", name="PESQUISAR").click()
            if info.value.status >= 400:
                raise ErroRobo(f"A pesquisa voltou com erro "
                               f"{info.value.status}.")
        except ErroRobo:
            raise
        except Exception:                                # noqa: BLE001
            # a Maxima mudou o nome da consulta: espera a rede acalmar
            self.log("(aviso) não vi a resposta da pesquisa; esperando…")
            try:
                pg.wait_for_load_state("networkidle", timeout=60000)
            except Exception:                            # noqa: BLE001
                pass
        _time.sleep(1.5)                       # o grid se redesenha

    # ------------------------------------- (18/10) visita por cliente
    def _paginas(self):
        """As paginas abertas (a do maxGestao e, se o relatorio abrir em aba
        nova, ela tambem)."""
        try:
            return [p for p in self.ctx.pages if not p.is_closed()]
        except Exception:                                # noqa: BLE001
            return [self.page]

    def _visivel(self, padrao, paginas=None, ultimo=False):
        """(pagina, locator) do primeiro elemento VISIVEL com esse texto, em
        qualquer pagina e em qualquer quadro (o visualizador pode vir num
        iframe). ultimo=True: o ultimo da pagina (o que esta por cima)."""
        rx = re.compile(padrao, re.I)
        achado = None
        for pg in (paginas or self._paginas()):
            for fr in pg.frames:
                try:
                    loc = fr.get_by_text(rx)
                    for k in range(min(loc.count(), 10)):
                        if loc.nth(k).is_visible():
                            achado = (pg, loc.nth(k))
                            if not ultimo:
                                return achado
                except Exception:                        # noqa: BLE001
                    continue
        return achado

    SALVAR_RX = r"^\s*salvar\s*$"
    EXCEL_RX = r"(arquivo\s+)?microsoft\s+excel"

    def _abrir_visualizador(self):
        """Clica IMPRIMIR na janela do vendedor e espera o visualizador do
        Espelho de Rotas (barra com Imprimir / Salvar). Devolve a pagina."""
        pg = self.page
        self._fase("espelho")
        pg.evaluate("window.__bapAbertos = []")
        pg.locator('[data-bap-imprimir="1"]').first.click(timeout=10000)

        def pronto():
            achou = self._visivel(self.SALVAR_RX)
            if achou:
                return achou[0]
            u = self._abertos("")          # abriu em aba nova (window.open)
            if u and u.startswith("http"):
                return u
            return None
        r = self._esperar(pronto, 60)
        if not r:
            raise ErroRobo("O relatório (Espelho de Rotas) não abriu depois "
                           "do Imprimir.")
        if isinstance(r, str):
            nova = self.ctx.new_page()
            nova.goto(r, wait_until="domcontentloaded", timeout=60000)
            if not self._esperar(lambda: self._visivel(self.SALVAR_RX,
                                                       [nova]), 60):
                raise ErroRobo("O relatório abriu em outra aba, mas não "
                               "achei o Salvar.")
            return nova
        return r

    def _salvar_excel(self, vpg, nome, dia: date) -> Path:
        """Salvar > Arquivo Microsoft Excel… (e o OK das opções, se a tela
        pedir) e grava o download no arquivo do vendedor."""
        self._fase("salvar")
        sal = self._visivel(self.SALVAR_RX, [vpg])
        if not sal:
            raise ErroRobo("Não achei o Salvar no relatório.")
        with vpg.expect_download(timeout=120000) as dl:
            sal[1].click(timeout=10000)
            item = self._esperar(lambda: self._visivel(self.EXCEL_RX,
                                                       [vpg]), 10)
            if not item:
                raise ErroRobo("O menu Salvar não mostrou 'Arquivo "
                               "Microsoft Excel'.")
            item[1].click(timeout=10000)
            # as opcoes da exportacao (quando aparecem): OK
            ok = self._esperar(lambda: self._visivel(r"^\s*ok\s*$", [vpg]),
                               8)
            if ok:
                ok[1].click(timeout=10000)
        sug = dl.value.suggested_filename or ""
        ext = Path(sug).suffix.lower() if Path(sug).suffix else ".xlsx"
        destino = arquivo_analitico(self.raiz, nome, dia, datetime.now(), ext)
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(destino.name + ".tmp")
        dl.value.save_as(str(tmp))
        tmp.replace(destino)
        return destino

    def _fechar_janelas(self, vpg=None):
        """Fecha o relatorio e a janela do vendedor (FECHAR / Fechar / Esc)
        e confere que a grade ficou livre."""
        if vpg is not None and vpg is not self.page:
            try:
                vpg.close()
            except Exception:                            # noqa: BLE001
                pass
        for _ in range(6):
            aberto = (self._visivel(self.SALVAR_RX, [self.page])
                      or self.page.evaluate(DIALOGO_JS))
            if not aberto:
                return
            f = self._visivel(r"^\s*fechar\s*$", [self.page], ultimo=True)
            try:
                if f:
                    f[1].click(timeout=5000)
                else:
                    self.page.keyboard.press("Escape")
            except Exception:                            # noqa: BLE001
                self.page.keyboard.press("Escape")
            _time.sleep(1.0)

    def _nomes_equipe(self):
        try:
            eq = json.loads((vn.pasta_visitas(self.raiz) / vn.ARQ_EQUIPE)
                            .read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [r.get("nome", "") for r in
                (eq.get("representantes") or {}).values()]

    def baixar_dia(self, d: date, progresso=None) -> dict:
        """O DIA d (Data inicial = Data final = d): para cada representante
        da grade, o OLHO, IMPRIMIR, Salvar > Arquivo Microsoft Excel > OK.
        Devolve {"ok": [(nome, arquivo)], "erro": [(nome, msg)],
        "extras": {nome_chave: {"gps", "versao"}}}."""
        pg = self.page
        self._checar()
        self._fase("filtros", dia=f"{d:%Y%m%d}")
        if not self._todos_ok():
            self._marcar_todos()
        self._datas(d, d)
        self._pesquisar()
        _time.sleep(1.5)
        conhecidos = self._nomes_equipe()
        feitos, ok, erros, extras = set(), [], [], {}
        self._fase("grade")
        pg.evaluate(TOPO_GRADE_JS)
        for _ in range(80):                      # trava contra laco infinito
            self._checar()
            olhos = pg.evaluate(OLHOS_JS)
            if not feitos and not olhos:
                raise ErroRobo("Não achei o olho (coluna Ações) na grade dos "
                               "representantes.")
            falta = [o for o in olhos if o["chave"] not in feitos]
            if not falta:
                # a grade so desenha o que esta na tela: rola e procura
                # de novo; no fim da grade, acabou
                if pg.evaluate(ROLAR_GRADE_JS):
                    _time.sleep(0.6)
                    continue
                break
            o = falta[0]
            feitos.add(o["chave"])
            nome, vpg = "", None
            try:
                pg.locator(f'[data-bap-olho="{o["k"]}"]').first.click(
                    timeout=10000)
                dlg = self._esperar(lambda: pg.evaluate(DIALOGO_JS), 40)
                if not dlg:
                    raise ErroRobo("a janela do vendedor não abriu")
                nome = nome_do_vendedor(dlg["texto"], conhecidos) or o["txt"]
                extras[vn.nome_chave(nome)] = {"gps": dlg.get("gps"),
                                               "versao": dlg.get("versao")}
                vpg = self._abrir_visualizador()
                arq = self._salvar_excel(vpg, nome, d)
                ok.append((nome_limpo(nome), arq))
                self.log(f"  {nome_limpo(nome)} ✔")
            except Cancelado:
                raise
            except Exception as e:                       # noqa: BLE001
                msg = str(e).splitlines()[0] if str(e) else type(e).__name__
                if self.eventos:         # a mensagem crua da Maxima nao sai
                    msg = type(e).__name__
                erros.append((nome or o["txt"], msg))
                self.foto = self.foto_do_erro() or self.foto
                self.log(f"  ✖ {nome or o['txt'][:40]}: {msg}")
            finally:
                try:
                    self._fechar_janelas(vpg)
                except Exception:                        # noqa: BLE001
                    pass
            self.vendedores = len(feitos)
            self.evento("vendedor", fase="grade", n=len(feitos))
            self._fase("grade", feitos=len(feitos),
                       total=len(feitos) + max(0, len(falta) - 1))
            if progresso:
                progresso()
        self.vendedores = len(feitos)
        if erros and not ok:
            raise ErroRobo(f"{d:%d/%m/%Y}: nenhum vendedor salvo. Primeiro "
                           f"erro: {erros[0][1]}")
        return {"ok": ok, "erro": erros, "extras": extras}

    # ---------------------------------------------------------- tudo
    def rodar(self, usuario, senha, dias, meses, progresso=None):
        """Para cada dia: o Excel de cada representante (ANALITICO), e com
        eles o diario/AAAAMMDD.csv; no fim de cada mes, o AAAAMM.csv.
        Se cair, `self.codigo` e `self.fase_erro` dizem o codigo e a fase do
        contrato (a nuvem manda so isso)."""
        self._fase("inicio")             # fase do contrato; o navegador abre antes
        self._abrindo = True
        try:
            return self._rodada(usuario, senha, dias, meses, progresso)
        except Cancelado:
            raise
        except Exception as e:                           # noqa: BLE001
            self._registrar_falha(e)
            raise

    def _rodada(self, usuario, senha, dias, meses, progresso=None):
        from playwright.sync_api import sync_playwright   # noqa: PLC0415
        progresso = progresso or (lambda *_: None)
        feitos, linhas = 0, {}
        self.erros_vendedor = []
        with sync_playwright() as p:
            nav = _abrir_navegador(p, self.visivel, self.log, self.canal)
            self._abrindo = False
            try:
                ctx = nav.new_context(accept_downloads=True, locale="pt-BR",
                                      viewport={"width": 1440, "height": 900})
                ctx.add_init_script(GANCHO_JS)
                self.ctx = ctx
                self.page = ctx.new_page()
                self.page.set_default_timeout(30000)
                self.entrar(usuario, senha)
                senha = None                               # noqa: F841
                self.abrir_maxgestao()
                self.abrir_auditoria()
                n_rep = max(1, len(self._nomes_equipe()))
                total = max(1, len(dias) * n_rep)
                self.log("Baixando…")
                # MES A MES: os dias do mes e, logo em seguida, o arquivo do
                # mes (se cancelar no meio, o que terminou ja ficou salvo)
                ordem = sorted({(d.year, d.month) for d in dias} | set(meses))
                for a, m in ordem:
                    for d in [x for x in dias if (x.year, x.month) == (a, m)]:
                        self.log(f"{d:%d/%m/%Y}:")

                        def passo():
                            nonlocal feitos
                            feitos += 1
                            progresso(feitos, max(total, feitos + 1))
                        r = self.baixar_dia(d, passo)
                        self.erros_vendedor += [(d, n, e)
                                                for n, e in r["erro"]]
                        n = vn.montar_dia(self.raiz, d, r["extras"])
                        vn.anotar_baixado(self.raiz, f"{d:%Y%m%d}")
                        linhas[d] = n
                        self.evento("dia_fechado", dia=f"{d:%Y%m%d}",
                                    n=len(r["ok"]))
                        if self.ao_fechar_dia:
                            # a nuvem manda o lote do dia aqui; ela pode
                            # ligar o `parar` (o proximo dia nao comeca)
                            self.ao_fechar_dia(d, dict(
                                r, linhas=n, vendedores=self.vendedores))
                        self.log(f"{d:%d/%m/%Y}: {len(r['ok'])} Excel salvo(s)"
                                 f"; sintético do dia com {n} "
                                 f"representante(s).")
                    if (a, m) in meses and vn.montar_mes(self.raiz, a, m):
                        vn.anotar_baixado(self.raiz, f"{a}{m:02d}")
                        self.log(f"Mês {m:02d}/{a}: Visitas\\{a}{m:02d}.csv "
                                 f"refeito com os dias.")
            except Cancelado:
                raise
            except Exception:
                self.onde = self.url_limpa()
                self.foto = self.foto_do_erro()
                raise
            finally:
                try:
                    nav.close()
                except Exception:                        # noqa: BLE001
                    pass
        return linhas


def executar(raiz, de, ate, usuario, senha, log, parar=None, visivel=False,
             refazer=False, progresso=None) -> dict:
    """Baixa o que falta (o Excel de cada vendedor, dia a dia), monta o
    sintetico e atualiza os Excel. Devolve o resumo."""
    dias, meses = plano(raiz, de, ate, refazer)
    res = {"dias": [], "meses": meses, "excel": None, "erro": "", "foto": None,
           "erros_vendedor": [], "por_cliente": None}
    if not dias and not meses:
        log("Tudo já baixado nesse período (dias fechados).")
    else:
        log(f"A baixar: {len(dias)} dia(s), um Excel por vendedor por dia.")
        robo = Robo(raiz, log, parar, visivel)
        try:
            res["dias"] = sorted(robo.rodar(usuario, senha, dias, meses,
                                            progresso))
        except Cancelado:
            res["erro"] = "Cancelado. O que já baixou ficou salvo."
        except ErroRobo as e:
            res["erro"] = str(e)
        except Exception as e:                           # noqa: BLE001
            res["erro"] = f"{type(e).__name__}: {str(e).splitlines()[0]}"
        res["foto"] = robo.foto
        res["erros_vendedor"] = getattr(robo, "erros_vendedor", [])
        if robo.onde:
            log(f"Parou em: {robo.onde}")
    res.update(depois_de_baixar(raiz, log))
    return res


def depois_de_baixar(raiz, log) -> dict:
    """O que vem depois do download, igual para o botao do PC e para a
    importacao dos lotes da nuvem (contrato §4.4): atualiza o acompanhamento
    (Excel), o VISITAS_POR_CLIENTE e a prospeccao do Forms. Cada parte falha
    sozinha. Devolve {"excel", "por_cliente", "prospeccao"}."""
    res = {}
    try:
        res["excel"] = vn.atualizar_acompanhamento(raiz, log)
    except Exception as e:                               # noqa: BLE001
        res["excel"] = {"novas": 0, "dias": [], "erro": str(e)}
    try:
        res["por_cliente"] = vn.atualizar_por_cliente(raiz, log=log)
    except Exception as e:                               # noqa: BLE001
        res["por_cliente"] = {"linhas": 0, "erro": str(e)}
    # (22/10, Alexandre) junto com a Maxima, a PROSPECCAO do Microsoft Forms
    # (visita a cliente fora da base): valida e grava PROSPECCAO_AAAAMM
    try:
        import prospeccao_forms as pf                   # noqa: PLC0415
        res["prospeccao"] = pf.atualizar(raiz, log)
    except Exception as e:                               # noqa: BLE001
        res["prospeccao"] = {"novas": 0, "erro": str(e)}
        log(f"Prospecção (Forms): {e}")
    return res


# =========================================================================
# a janela
# =========================================================================
def _data(txt: str) -> date | None:
    txt = (txt or "").strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, f).date()
        except ValueError:
            pass
    return None


def periodo_padrao(hoje: date | None = None):
    hoje = hoje or date.today()
    base = hoje - timedelta(days=1) if hoje.day == 1 else hoje
    return base.replace(day=1), hoje


def janela(pai=None, raiz=None, ao_terminar=None):
    """Abre a janela (Toplevel se houver pai)."""
    import tkinter as tk                                 # noqa: PLC0415
    from tkinter import messagebox, ttk                  # noqa: PLC0415
    import bap_visual as bv                              # noqa: PLC0415
    raiz = Path(raiz or AQUI)
    w = tk.Toplevel(pai) if pai is not None else tk.Tk()
    if pai is None:
        bv.aplicar_tema(w)
    w.title("Atualizar visitas · Máxima")
    w.configure(background=bv.FUNDO)
    w.resizable(False, False)
    if pai is not None:
        w.transient(pai)
    cab = bv.Cabecalho(w, "Vendas e CRM", "Atualizar visitas",
                       "Máxima · Painel Auditoria")
    cab.pack(fill="x")
    tk.Frame(w, background=bv.VERDE, height=2).pack(fill="x")
    corpo = tk.Frame(w, background=bv.FUNDO)
    corpo.pack(fill="both", expand=True, padx=22, pady=14)

    def rot(txt, lin, colu=0):
        tk.Label(corpo, text=txt, background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(9)).grid(row=lin, column=colu, sticky="w",
                                         pady=(6, 2))
    de0, ate0 = periodo_padrao()
    v_de = tk.StringVar(value=f"{de0:%d/%m/%Y}")
    v_ate = tk.StringVar(value=f"{ate0:%d/%m/%Y}")
    v_user = tk.StringVar(value=ler_config().get("usuario", ""))
    v_senha = tk.StringVar()
    v_refazer = tk.BooleanVar(value=False)
    v_ver = tk.BooleanVar(value=False)
    rot("De", 0, 0)
    rot("Até", 0, 1)
    e_de = ttk.Entry(corpo, textvariable=v_de, width=14)
    e_de.grid(row=1, column=0, sticky="w", padx=(0, 12))
    ttk.Entry(corpo, textvariable=v_ate, width=14).grid(row=1, column=1,
                                                       sticky="w")
    rot("Usuário da Máxima", 2, 0)
    rot("Senha", 2, 1)
    e_user = ttk.Entry(corpo, textvariable=v_user, width=24)
    e_user.grid(row=3, column=0, sticky="w", padx=(0, 12))
    e_senha = ttk.Entry(corpo, textvariable=v_senha, width=22, show="•")
    e_senha.grid(row=3, column=1, sticky="w")
    opc = tk.Frame(corpo, background=bv.FUNDO)
    opc.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
    for lin, itens in enumerate((
            (("Baixar de novo os dias já baixados", v_refazer),
             ("Mostrar o navegador", v_ver)),)):
        fr = tk.Frame(opc, background=bv.FUNDO)
        fr.pack(anchor="w", pady=(0, 2))
        for txt, var in itens:
            tk.Checkbutton(fr, text=txt, variable=var, background=bv.FUNDO,
                           activebackground=bv.FUNDO, font=bv.fonte(9),
                           foreground=bv.TEXTO, selectcolor=bv.CARTAO,
                           relief="flat", borderwidth=0,
                           highlightthickness=0).pack(
                               side="left", padx=(0, 14))
    est = ttk.Style(w)
    est.configure("Visitas.Horizontal.TProgressbar", background=bv.VERDE,
                  troughcolor=bv.CARTAO, bordercolor=bv.CINZA_LINHA,
                  lightcolor=bv.VERDE, darkcolor=bv.VERDE, thickness=8)
    barra = ttk.Progressbar(corpo, mode="determinate", length=420,
                            style="Visitas.Horizontal.TProgressbar")
    barra.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 6))
    txt_log = tk.Text(corpo, height=9, width=60, relief="flat",
                      background=bv.CARTAO, foreground=bv.TEXTO,
                      font=bv.fonte(9), wrap="word", state="disabled",
                      highlightthickness=1,
                      highlightbackground=bv.CINZA_LINHA)
    txt_log.grid(row=6, column=0, columnspan=2, sticky="ew")
    botoes = tk.Frame(corpo, background=bv.FUNDO)
    botoes.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))
    fila = queue.Queue()
    estado = {"thread": None, "parar": threading.Event()}

    def escrever(msg):
        txt_log.configure(state="normal")
        txt_log.insert("end", msg + "\n")
        txt_log.see("end")
        txt_log.configure(state="disabled")

    def ouvir():
        try:
            while True:
                tipo, val = fila.get_nowait()
                if tipo == "log":
                    escrever(val)
                elif tipo == "prog":
                    feitos, total = val
                    barra.configure(maximum=max(total, 1), value=feitos)
                elif tipo == "fim":
                    terminou(val)
                    return
        except queue.Empty:
            pass
        if estado["thread"] is not None:
            w.after(200, ouvir)

    def terminou(res):
        estado["thread"] = None
        bt_baixar.configure(state="normal")
        bt_fechar.configure(text="Fechar")
        x = res.get("excel") or {}
        partes = []
        if res.get("dias"):
            partes.append(f"{len(res['dias'])} dia(s) baixado(s)")
        pc = res.get("por_cliente") or {}
        if pc.get("linhas"):
            partes.append(f"{pc['linhas']} linha(s) em "
                          f"{vn.ARQ_POR_CLIENTE}")
        if pc.get("erro"):
            partes.append(pc["erro"])
        ev = res.get("erros_vendedor") or []
        if ev:
            partes.append(f"{len(ev)} Excel com erro (o print ficou em "
                          f"Visitas\\_erros): " + ", ".join(
                              f"{n} {d:%d/%m}" for d, n, _ in ev[:5]))
        if x.get("novas"):
            partes.append(f"{x['novas']} linha(s) novas no Excel")
        if x.get("erro"):
            partes.append(x["erro"])
        # (22/10) a prospeccao do Forms (visita a cliente fora da base)
        pr = res.get("prospeccao") or {}
        if pr.get("novas"):
            partes.append(f"prospecção: {pr['novas']} resposta(s) nova(s), "
                          f"{pr.get('conta', 0)} contam como visita")
        if pr.get("erro"):
            partes.append("prospecção: " + pr["erro"])
        if res.get("erro"):
            msg = res["erro"]
            if res.get("foto"):
                msg += ("\n\nO print da tela onde parou ficou salvo — "
                        "clique em “Abrir o print do erro”.")
            if partes:
                msg += "\n\n" + " · ".join(partes)
            escrever("✖ " + res["erro"])
            # (13/10) o botao para abrir o print junto da mensagem
            bv.erro_com_print(w, "Atualizar visitas", msg, res.get("foto"))
        else:
            escrever("✔ Pronto. " + " · ".join(partes))
            barra.configure(value=barra["maximum"])
        if ao_terminar:
            try:
                ao_terminar()
            except Exception:                            # noqa: BLE001
                pass

    def baixar(_e=None):
        if estado["thread"] is not None:
            return
        de, ate = _data(v_de.get()), _data(v_ate.get())
        hoje = date.today()
        if not de or not ate:
            messagebox.showwarning("Atualizar visitas",
                                   "Data no formato dd/mm/aaaa.", parent=w)
            return
        if de > ate:
            messagebox.showwarning("Atualizar visitas",
                                   "A data inicial passou da final.", parent=w)
            return
        if de > hoje:
            messagebox.showwarning("Atualizar visitas",
                                   "Período no futuro.", parent=w)
            return
        ate = min(ate, hoje)
        if (ate - de).days + 1 > MAX_DIAS:
            messagebox.showwarning(
                "Atualizar visitas",
                f"No máximo {MAX_DIAS} dias por vez.", parent=w)
            return
        usuario, senha = v_user.get().strip(), v_senha.get()
        dias, meses = plano(raiz, de, ate, v_refazer.get())
        precisa = bool(dias or meses)
        if precisa and (not usuario or not senha):
            messagebox.showwarning("Atualizar visitas",
                                   "Informe usuário e senha da Máxima.",
                                   parent=w)
            (e_user if not usuario else e_senha).focus_set()
            return
        if precisa and not tem_playwright():
            if not messagebox.askyesno(
                    "Atualizar visitas",
                    "Falta instalar o Playwright (o componente que controla "
                    "o navegador). Instalar agora? Precisa de internet.",
                    parent=w):
                return
        if precisa:
            # (T-0045, contrato §4.5) o site pode estar baixando agora: dois
            # logins ao mesmo tempo derrubam a sessao da Maxima
            aviso = aviso_site_baixando(consultar_saude())
            if aviso and not messagebox.askyesno("Atualizar visitas", aviso,
                                                 parent=w):
                return
        gravar_usuario(usuario)
        v_senha.set("")                          # a senha so fica na memoria
        bt_baixar.configure(state="disabled")
        bt_fechar.configure(text="Cancelar")
        estado["parar"] = threading.Event()
        barra.configure(value=0, maximum=max(len(dias) + len(meses), 1))
        escrever(f"— {de:%d/%m/%Y} a {ate:%d/%m/%Y} —")

        def log(m):
            fila.put(("log", m))

        def trabalho():
            try:
                if precisa and not tem_playwright():
                    if not instalar_playwright(log):
                        fila.put(("fim", {"erro": "Sem o Playwright não dá "
                                          "para baixar. Rode de novo com "
                                          "internet liberada."}))
                        return
                res = executar(raiz, de, ate, usuario, senha, log,
                               estado["parar"], v_ver.get(), v_refazer.get(),
                               lambda f, t: fila.put(("prog", (f, t))))
            except Exception as e:                       # noqa: BLE001
                res = {"erro": f"{type(e).__name__}: {e}"}
            fila.put(("fim", res))
        estado["thread"] = threading.Thread(target=trabalho, daemon=True)
        estado["thread"].start()
        w.after(200, ouvir)

    def fechar():
        if estado["thread"] is not None:
            estado["parar"].set()
            escrever("Cancelando…")
            return
        w.destroy()
    bt_fechar = ttk.Button(botoes, text="Fechar", command=fechar)
    bt_fechar.pack(side="right")
    bt_baixar = ttk.Button(botoes, text="Baixar", style="Verde.TButton",
                           command=baixar)
    bt_baixar.pack(side="right", padx=(0, 8))
    w.protocol("WM_DELETE_WINDOW", fechar)
    e_senha.bind("<Return>", baixar)
    (e_senha if v_user.get() else e_user).focus_set()
    escrever("Um Excel por vendedor por dia em RELATORIOS\\Visitas\\"
             "ANALITICO\\<vendedor>; deles saem o sintético do dia "
             "(Farol de Visita) e o VISITAS_POR_CLIENTE.xlsx. "
             "A senha não é gravada.")
    return w


def main():
    w = janela()
    w.mainloop()


if __name__ == "__main__":
    main()
