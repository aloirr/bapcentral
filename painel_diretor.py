# -*- coding: utf-8 -*-
"""
PAINEL DO DIRETOR (29/10/2026, recado do analista 20261029-1510, aprovado
pelo Alexandre): a 1a aba do Painel Executivo, uma tela so, 16 cartoes em 4
blocos + coluna (Leitura do mes, Acoes, Compromisso). Cada cartao tem valor,
referencia, selo de cor e abre o farol de origem.

REGRAS (fechadas com o analista no recado 1650):
  - TUDO E DESAFIO COMERCIAL (decisao do Alexandre de 29/10): o faturamento
    e contra o desafio do gerente (Farol de Metas > Por gerente > FAT. META);
    a meta RH nunca aparece aqui.
  - (30/10, Alexandre) TODO CARTAO NO MESMO PADRAO, so isto: REALIZADO,
    PROJECAO, DU, GAP META (meta - realizado) e % ATING. DA META PROJETADO
    (projecao / meta). Sem meta: MoM (projecao x mes anterior fechado) e M3M
    (projecao x media dos 3 meses anteriores fechados). Razao (ticket,
    markup, %) e foto do dia (inadimplencia, estoque): projecao = o proprio
    realizado. A foto do dia tira o mes anterior do painel_diretor_hist.json.
  - (05/11, Alexandre: "visita por dia util, conta simples") A LINHA DU E A
    MEDIA POR DIA UTIL, nao "3 de 19": realizado / DU decorridos ATE
    ONTEM (Alexandre: "tirar a venda de hoje da conta do DU" - o dia de hoje,
    aberto, sai do realizado, da media e da projecao; notas ate a ultima NF
    e visitas ate o ultimo Espelho, nunca depois de ontem). A projecao e essa media x DU do mes. Razao (ticket, markup,
    desconto, %): a media/DU do que forma a razao (ex.: "36 de 66 visitas").
    Foto do dia (inadimplencia, estoque): a variacao por DU desde o
    fechamento do mes anterior. Compraveis: quantos deles compraram por DU
    e a projecao de quantos ainda ficam sem pedido no fim do mes.
  - Cor: com meta, pelo % ating. projetado (verde >= 100%, amarelo 80-99%,
    vermelho < 80%); sem meta, pelo MoM (vermelho quando piora).
  - Estoque parado: curva A sem venda ha mais de 60 dias, so nas filiais com
    equipe de venda (AM, RR, PA, MA); Cuiaba e Macapa numa linha a parte.
  - Contas-chave: >= R$ 10 mil liquidos somados nos 4 meses anteriores, de
    qualquer vendedor.
  - Leitura do mes: o 1o cartao vermelho de cada bloco (ate 3).

So LE os dados (TABELA_BAP, BASE_CLIENTE, ESTOQUE_BAP, Espelhos e os
farois de origem). Grava apenas:
  - painel_diretor_config.json (pasta do BAP): os textos livres do
    Alexandre (acoes, compromisso, acao de preco) - so pelo botao Editar;
  - RELATORIOS/painel_diretor_hist.json: os numeros de cada mes (so muda
    quando um numero muda).
Nenhum dado digitado (pedido, garantia, entrega, NCC, autorizacao) e tocado.
"""
import json
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ARQ_CONFIG = "painel_diretor_config.json"
ARQ_HIST = "painel_diretor_hist.json"
CONFIG_PADRAO = {
    "acoes": [],
    "compromisso": {"t": "", "d": ""},
    "acao_preco": {},
}
FORA_OPERACAO = {"MATOGROSSO", "MATO GROSSO", "MACAPÁ", "MACAPA", "CUIABÁ",
                 "CUIABA", "VÁRZEA GRANDE", "VARZEA GRANDE"}
MESES_C = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
           "out", "nov", "dez"]
MESES_L = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
           "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
# (09/11, recado 20261109-1100) o registro CLIENTE A CLIENTE (Espelho x
# Planner) comeca em OUT/26: a % 1a VISITA so tem base a partir de NOV/26
INICIO_REGISTRO_CLIENTE = (2026, 10)
INICIO_ESPELHO = date(2026, 8, 27)      # o Espelho da Maxima comeca aqui


def ja_visitados(ctx, raiz, ate_exclusive) -> set:
    """(09/11) os clientes ja visitados (Espelho cliente a cliente +
    cadastros novos, qualquer vendedor) de 27/08/2026 ate a vespera de
    `ate_exclusive`, mes a mes (a mesma base da conversao). Memo no ctx."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    import visitas_nucleo as vn                         # noqa: PLC0415
    memo = ctx.__dict__.setdefault("_ja_visitados", {})
    if ate_exclusive in memo:
        return memo[ate_exclusive]
    todos = [r for r in vn.registros(raiz) if r.get("ativo")]
    vistos, ini = set(), INICIO_ESPELHO
    while ini < ate_exclusive:
        prox = (date(ini.year + 1, 1, 1) if ini.month == 12
                else date(ini.year, ini.month + 1, 1))
        fim = min(prox, ate_exclusive) - timedelta(days=1)
        regs = [r for r in todos if ini <= r["data"] <= fim]
        if regs:
            regs = rn.com_cadastro_como_visita(ctx, regs, ini, fim)
            visd, _c = rn._visitados_e_compras(ctx, regs, ini, fim)
            for cl in visd.values():
                vistos.update(cl)
        ini = prox
    memo[ate_exclusive] = vistos
    return vistos


# (06/11) os DU do mes no titulo do bloco 1 (verde do BAP no PNG/PDF)
VERDE_DU = (46, 125, 50)


def _du_titulo(dados) -> str:
    """(06/11, Alexandre: "coloque o DU do mes ao lado do titulo") os dias
    uteis fechados (ate ontem) de quantos o mes tem."""
    return f"· {dados.get('ndp', 0)} de {dados.get('ndm', 0)} DU"


BLOCOS = [(1, "RESULTADO DO MÊS", "faturamento líquido = venda − devolução "
           "pela data da NF, sem CNPJs internos"),
          (2, "EXECUÇÃO NO PDV", "o que vem antes do faturamento"),
          (3, "CARTEIRA E CRÉDITO", "onde está a venda que não veio"),
          (4, "PREÇO E ESTOQUE", "estoque que não vira venda")]


# ------------------------------------------------------------ cadastro
def ler_config(raiz) -> dict:
    cfg = json.loads(json.dumps(CONFIG_PADRAO))
    try:
        d = json.loads((Path(raiz) / ARQ_CONFIG).read_text("utf-8"))
        if isinstance(d, dict):
            cfg.update({k: v for k, v in d.items() if k in CONFIG_PADRAO})
    except (OSError, ValueError):
        pass
    return cfg


def gravar_config(raiz, cfg: dict):
    """Grava os textos livres (troca atomica: escreve ao lado e renomeia)."""
    alvo = Path(raiz) / ARQ_CONFIG
    limpo = {k: cfg.get(k, v) for k, v in CONFIG_PADRAO.items()}
    limpo["_leia"] = ("Painel do Diretor: textos livres do Alexandre "
                      "(BAP Relatórios › Painel Executivo › Painel do "
                      "Diretor › Editar). A leitura do mês sai sozinha.")
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps(limpo, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, alvo)


def _hist_path(raiz) -> Path:
    return Path(raiz) / "RELATORIOS" / ARQ_HIST


# ------------------------------------------------------------ formatos
def br(v, c=0):
    if v is None:
        return "—"
    s = f"{v:,.{c}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def moeda(v, mil=False):
    if v is None:
        return "—"
    if mil and abs(v) >= 1000:
        if abs(v) >= 1e6:
            return f"R$ {br(v / 1e6, 2)} mi"
        if abs(v) < 10000:
            return f"R$ {br(v / 1000, 1)} mil"
        return f"R$ {br(v / 1000)} mil"
    return f"R$ {br(v)}"


def pct(v, c=0):
    return "—" if v is None else br(v * 100, c) + "%"


def _num(s):
    s = str(s or "").replace("R$", "")
    m = re.search(r"-?[\d\.]+(,\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _hhmm(s):
    m = re.match(r"(\d+):(\d+)", str(s or ""))
    return int(m.group(1)) + int(m.group(2)) / 60 if m else None


def tom_ritmo(x):
    """x = real / esperado ate a data"""
    if x is None:
        return ""
    return "ok" if x >= 1.0 else "atencao" if x >= 0.8 else "alerta"


def _mes_ant(ano, mes, n=1):
    for _ in range(n):
        mes -= 1
        if not mes:
            ano, mes = ano - 1, 12
    return ano, mes


# ------------------------------------------------------------ calculo
def calcular(ctx, ano=None, mes=None, gravar_hist=True) -> dict:
    """Os 16 cartoes, a leitura do mes e os textos livres. ctx: o Contexto
    do Painel Executivo (raiz, hoje, tabela, base, feriados)."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    import visitas_nucleo as vn                         # noqa: PLC0415
    raiz = Path(ctx.raiz)
    itens = ctx.tabela["itens"]
    hoje = ctx.hoje if hasattr(ctx.hoje, "year") else date.today()
    ano = ano or hoje.year
    mes = mes or hoje.month
    fim_mes = date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)
    datas = [it["dt_nf"] for it in itens if it.get("dt_nf")]
    ult = max(datas) if datas else hoje
    # "dados ate": a ultima NF que entrou (nunca depois de hoje / do mes)
    corte = min(hoje, fim_mes, ult) if ult >= date(ano, mes, 1) else \
        min(hoje, fim_mes)
    # (05/11, Alexandre: "tirar a venda de hoje da conta do DU") o mes
    # corrente vai ate ONTEM, o ultimo dia fechado: a venda e as visitas de
    # hoje (dia aberto) ficam fora do realizado, da media/DU e da projecao
    if (ano, mes) == (hoje.year, hoje.month):
        corte = min(corte, hoje - timedelta(days=1))
    comp = f"{ano}-{mes:02d}"
    fer = getattr(ctx, "fer", set()) or set()

    def dus(a, m):
        d, s = date(a, m, 1), []
        while d.month == m:
            if d.weekday() < 5 and d not in fer:
                s.append(d)
            d += timedelta(days=1)
        return s
    du_mes = dus(ano, mes)

    def du_ate(d):
        """(05/11) DU do mes decorridos ate a data d (inclusive)."""
        return len([x for x in du_mes if d and x <= d])
    ndp = du_ate(corte)                 # 0 = nenhum dia util fechado
    ndm = len(du_mes) or 1
    ritmo = ndp / ndm
    a_ant = _mes_ant(ano, mes)
    a_jul = (ano, 7) if mes > 7 else _mes_ant(ano, mes, 3)

    def mesmo_ponto(a, m):
        du = dus(a, m)
        return du[min(max(ndp, 1), len(du)) - 1] if du else date(a, m, 1)
    pt_ant, pt_jul = mesmo_ponto(*a_ant), mesmo_ponto(*a_jul)

    def por_cliente_ate(a, m, ate):
        soma = defaultdict(float)
        for it in itens:
            d = it.get("dt_nf")
            if d and d.year == a and d.month == m and d <= ate:
                v = rn._liquido(it)
                if v is not None:
                    soma[it["cliente"]] += v
        return soma

    def fat_e_pos(a, m, ate):
        s = por_cliente_ate(a, m, ate)
        return sum(s.values()), rn.clientes_positivados_ate(itens, ate)

    # os farois de origem (o mesmo numero que o farol mostra)
    params_mes = {"MÊS": mes, "ANO": ano}
    farois = {}
    avisos = []
    for rid, prm in (("vc_meta", params_mes), ("vc_markup", params_mes),
                     ("vc_saldo", params_mes), ("vc_visitas", params_mes),
                     ("pl_inadimplencia", None), ("pl_giro", None)):
        try:
            # (05/11) o Farol de Visita ate o dia fechado (visitas, aderencia
            # e jornada sem o dia de hoje, ainda aberto)
            hj_f = corte if rid == "vc_visitas" and corte < hoje else hoje
            farois[rid] = rn.montar(rid, raiz, hoje=hj_f, params=prm)
        except Exception as erro:                       # noqa: BLE001
            farois[rid] = {}
            avisos.append(f"{rn.POR_ID.get(rid, (0, 0, rid))[2]}: {erro}")

    def kpi_de(rid, rot):
        for k in farois[rid].get("kpis", []) or []:
            if str(k.get("rotulo", "")).lower().startswith(rot.lower()):
                return k
        return {}

    def lin(k, nome):
        for x in k.get("linhas") or []:
            if str(x[0]).lower().startswith(nome.lower()):
                return x[1]
        return ""

    def tab(rid, titulo):
        for t in farois[rid].get("tabelas", []) or []:
            if t.get("titulo") == titulo:
                return ([c["nome"] for c in t["colunas"]], t["linhas"],
                        t.get("total"))
        return [], [], None

    cards = []

    # (30/10, Alexandre) TODO CARTAO NO MESMO PADRAO, "somente isso":
    # REALIZADO (o numero grande), PROJECAO, DU, GAP META e % ATING. DA META
    # PROJETADO. Cartao sem meta: no lugar do GAP e do % ating., o MoM
    # (projecao do mes x mes anterior fechado) e o M3M (projecao x media dos
    # 3 meses anteriores fechados, sem o mes atual).
    hist = {}
    try:
        hist = json.loads(_hist_path(raiz).read_text("utf-8"))
    except (OSError, ValueError):
        hist = {}
    meses3 = [_mes_ant(ano, mes, n) for n in (3, 2, 1)]
    rot3 = f"{MESES_C[meses3[0][1]]}–{MESES_C[meses3[-1][1]]}"
    ma = MESES_C[a_ant[1]]
    def por_du(v, n, fmt_):
        """(05/11) a linha DU: a media por dia util (v / n). (06/11,
        Alexandre: "coloque o DU do mes ao lado do titulo e tire dos
        cards") o "· 3 DU" saiu: os DU ficam no titulo do bloco 1."""
        if v is None or not n:
            return "—"
        return fmt_(v / n)

    def _media3(chave_):
        """(09/11) a media dos 3 meses anteriores no historico (M3M)."""
        v3 = [do_hist(chave_, a, m) for a, m in meses3]
        return sum(v3) / 3 if all(v is not None for v in v3) else None

    def do_hist(chave_, a, m):
        v = (hist.get(f"{a}-{m:02d}") or {}).get(chave_)
        return v if isinstance(v, (int, float)) else None

    def var(proj_, base):
        return (proj_ / base - 1) if proj_ is not None and base else None

    def sinal(v):
        if v is None:
            return "—"
        return ("+" if v >= 0 else "−") + br(abs(v) * 100) + "%"

    def card(bloco, chave, titulo, real, proj, fmt, rid, origem, regra,
             meta=None, menor_melhor=False, gap_fmt=None, ant=None,
             media3=None, sobe_ruim=False, valor=None, linhas=None,
             du=None, rot_du="Média/DU"):
        """Um cartao no padrao. real/proj/meta em numero; fmt formata.
        du: o texto da linha da media por dia util (05/11)."""
        gap_fmt = gap_fmt or fmt
        # decisao 48: o grupo B segue ate ONTEM e diz o periodo no titulo;
        # markup e desconto vao ate o dia do cabecalho: sem rotulo
        if (ano, mes) == (hoje.year, hoje.month):
            if chave in rn.GRUPO_B_CARTOES and corte < corte_a:
                titulo += rn.sufixo_periodo(corte)
        if linhas is None:
            linhas = [("Projeção", fmt(proj)), (rot_du, du or "—")]
            if meta and real is None:
                # (31/10) sem dado no mes (ex.: 1o dia util, antes do
                # Espelho baixar): o cartao fica com "—" e nao derruba o
                # Painel do Diretor inteiro
                linhas += [("GAP meta", "—"), ("% ating. proj.", "—")]
                tom = ""
            elif meta:
                gap = (real - meta) if menor_melhor else (meta - real)
                at = None
                if proj is not None:
                    at = (meta / proj if proj else None) if menor_melhor \
                        else proj / meta
                linhas += [("GAP meta", gap_fmt(gap) if gap > 1e-9 else
                            ("dentro do teto" if menor_melhor
                             else "meta batida")),
                           ("% ating. proj.", pct(at))]
                tom = tom_ritmo(at)
            else:
                mom, m3m = var(proj, ant), var(proj, media3)
                linhas += [("MoM", sinal(mom) + (f" vs {ma}" if mom
                                                 is not None else "")),
                           ("M3M", sinal(m3m) + (f" vs {rot3}" if m3m
                                                 is not None else ""))]
                tom = ""
                if mom is not None:
                    ruim = mom > 0 if sobe_ruim else mom < 0
                    tom = "alerta" if ruim and abs(mom) > 1e-9 else "ok"
        else:
            tom = "atencao" if valor not in (None, "", "—") else ""
        cards.append({"bloco": bloco, "chave": chave, "titulo": titulo,
                      "valor": valor if valor is not None else fmt(real),
                      "linhas": linhas, "meta": meta, "projecao": proj,
                      "small": "", "selo": "",
                      "sub": "\n".join(f"{a}: {b}" for a, b in linhas),
                      "tom": tom, "rid": rid, "origem": origem,
                      "regra": regra + (f" · meta {fmt(meta)}" if meta and
                                        "meta" not in regra else ""),
                      "numero": real})

    def f_moeda(v):
        return moeda(v, True)

    def f_int(v):
        return br(v)

    def f_1(v):                         # media por DU (1 casa)
        return br(v, 1)

    def f_pct1(v):                      # numero ja em % (28,4)
        return "—" if v is None else br(v, 1) + "%"

    def f_pp(v):                        # diferenca em pontos
        return "—" if v is None else br(v, 1) + " p.p."

    def f_frac(v):                      # fracao (0,57)
        return pct(v)

    def f_frac_pp(v):
        return "—" if v is None else br(v * 100, 1) + " p.p."

    def f_hora(v):
        if v is None:
            return "—"
        m_ = int(round(v * 60))
        return f"{m_ // 60}h{m_ % 60:02d}"

    # ================= 1 · RESULTADO
    cols, _ls, tot = tab("vc_meta", "Por gerente")
    ix = {c: i for i, c in enumerate(cols)}
    desafio = tot[ix["FAT. META"]] if tot and "FAT. META" in ix else None
    # T-0060 / decisao 43: faturamento, positivacao e pedidos CONTAM hoje
    # (hoje = DU passado); o resto (visitas, TMA...) segue ate ontem
    corte_a, ndp_a = corte, ndp
    if (ano, mes) == (hoje.year, hoje.month):
        corte_a = min(hoje, fim_mes, ult)       # o rotulo vem da ultima NF
        ndp_a = du_ate(hoje)                    # o DU conta hoje (decisao 43)
    fat, pos = fat_e_pos(ano, mes, corte_a)
    proj = rn.projecao_ritmo(fat, ndp_a / ndm) if ndp_a else None
    card(1, "fat", "Faturamento líquido", fat, proj, f_moeda, "vc_meta",
         "Farol de Metas (Por gerente, FAT. META = desafio comercial)",
         "VND − DEV pela data da NF, sem internos; projeção = real ÷ DU "
         "passados × DU do mês; GAP = desafio − real; % ating. = projeção "
         "÷ desafio", meta=desafio, du=por_du(fat, ndp_a, f_moeda))

    k_pos = kpi_de("vc_meta", "Positivação")
    meta_pos = _num(re.sub(r".*meta do mês", "", k_pos.get("detalhe", "")))
    card(1, "pos", "Positivação", len(pos),
         rn.projecao_ritmo(len(pos), ndp_a / ndm) if ndp_a else None, f_int,
         "vc_meta", "Farol de Metas (POSIT.)",
         "cliente com líquido (VND − DEV) > 0 no mês; média/DU = "
         "positivados ÷ DU até a última NF", meta=meta_pos,
         du=por_du(len(pos), ndp_a, f_1))

    def fim_de(a, m):
        return date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)

    def ticket_de(a, m, ate=None):
        f_, p_ = fat_e_pos(a, m, ate or fim_de(a, m))
        return f_ / len(p_) if p_ else None
    tk = fat / len(pos) if pos else None
    tk3 = [t for t in (ticket_de(a, m) for a, m in meses3) if t]
    card(1, "ticket", "Ticket por cliente", tk, tk, f_moeda, "vc_painel",
         "Painel Executivo",
         "faturamento líquido ÷ positivados (razão: a projeção é o próprio "
         "realizado); média/DU = faturamento/DU ÷ positivados/DU; MoM x mês anterior fechado, M3M x média dos 3 meses "
         "anteriores", ant=ticket_de(*a_ant),
         media3=sum(tk3) / len(tk3) if len(tk3) == 3 else None,
         du=(f"{f_moeda(fat / ndp_a)} ÷ {f_1(len(pos) / ndp_a)}"
             if pos and ndp_a else "—"))

    k_mk = kpi_de("vc_markup", "Markup")
    mk = _num(k_mk.get("valor"))
    mg = _num(kpi_de("vc_markup", "Margem").get("valor"))
    # (05/11) os farois de markup e saldo trazem o mes inteiro (com hoje):
    # a parte ate ontem = o valor x faturamento ate ontem / do mes
    fat_mes = fat_e_pos(ano, mes, fim_mes)[0]
    f_ont = (fat / fat_mes) if fat_mes else None
    mg = mg * f_ont if mg is not None and f_ont is not None else None
    card(1, "markup", "Markup", mk, mk, f_pct1, "vc_markup",
         "Farol de Markup", "venda ÷ custo (P. PEDIDO + sucata) − 1; meta = "
         "mínimo da política; média/DU = margem ÷ DU", meta=15.0,
         gap_fmt=f_pp, du=por_du(mg, ndp, f_moeda) if mk is not None
         else "—")

    k_dc = kpi_de("vc_saldo", "Desconto comercial")
    dc = _num(k_dc.get("valor"))
    dc_rs = _num(k_dc.get("detalhe"))
    dc_rs = dc_rs * f_ont if dc_rs is not None and f_ont is not None \
        else None
    card(1, "desconto", "Desconto comercial", dc, dc, f_pct1, "vc_saldo",
         "Farol de Saldo", "% sobre a tabela, sem o financeiro; meta = teto "
         "da política (menor é melhor); média/DU = R$ de desconto ÷ DU",
         meta=15.0, menor_melhor=True, gap_fmt=f_pp,
         du=por_du(dc_rs, ndp, f_moeda) if dc is not None else "—")

    # ================= 2 · EXECUCAO NO PDV
    k_v = kpi_de("vc_visitas", "Visitas")
    vis = _num(k_v.get("valor"))
    meta_v = _num(re.sub(r".*meta do mês", "", k_v.get("detalhe", "")))
    # (05/11) os DU das visitas: ate ontem (o dia fechado), ou ate o ultimo
    # dia do Espelho quando falta arquivo
    de = date(ano, mes, 1)
    regs_m = []
    try:
        regs_m = [r for r in vn.registros(raiz)
                  if de <= r["data"] <= min(hoje, fim_mes) and r.get("ativo")]
    except Exception as erro:                           # noqa: BLE001
        avisos.append(f"Visitas (Espelho): {erro}")
    ult_v = max((r["data"] for r in regs_m), default=None)
    ndp_v = du_ate(min(corte, ult_v)) if ult_v else 0
    ndp_r = ndp_v
    # (05/11) o Farol de Visita soma o mes inteiro baixado: as visitas do
    # Espelho de hoje (dia aberto) saem do realizado do painel
    if vis is not None:
        vis = max(0.0, vis - sum(r.get("visitas") or 0 for r in regs_m
                                 if r["data"] > corte))
    proj_v = (vis / ndp_v * ndm) if vis is not None and ndp_v else None
    card(2, "visitas", "Visitas", vis, proj_v, f_int, "vc_visitas",
         "Farol de Visita (até ontem, sem o dia de hoje)",
         "visitas do Espelho + prospecção que conta, até ontem (o dia de "
         "hoje, aberto, fica fora); média/DU = visitas ÷ DU até ontem; "
         "projeção = média/DU × DU do mês; "
         "meta do mês = 12 por dia útil por vendedor (interior 6) × 90%",
         meta=meta_v, du=por_du(vis, ndp_v, f_1))

    # (09/11, Alexandre - recado 20261109-1100) sairam "Visitas em nao
    # comprador" e "Conversao em quem compra"; entram % CONVERSAO NOS
    # VISITADOS (o cliente conta uma vez na BAP, ja compre ou nao) e % 1a
    # VISITA (visitado no mes que nunca tinha sido visitado antes, por
    # nenhum vendedor). Mesma base do Farol de Visita: Espelho cliente a
    # cliente x Planner + cadastros novos. Sem meta ate o Alexandre definir
    # [SUPOSICAO].
    cli_m, conv_n, prim_n, conv_uf = {}, 0, None, {}
    try:
        regs = [r for r in regs_m if r["data"] <= corte]
        regs = rn.com_cadastro_como_visita(ctx, regs, de, corte)
        visd, compras = rn._visitados_e_compras(ctx, regs, de, corte)
        for _v, cl in visd.items():
            for cod, ds in cl.items():
                cli_m.setdefault(cod, set()).update(ds)
        conv_n = sum(1 for cod, ds in cli_m.items()
                     if any(x_ >= min(ds) for x_ in compras.get(cod, ())))
        antes = None
        if (ano, mes) > INICIO_REGISTRO_CLIENTE:
            antes = ja_visitados(ctx, raiz, de)
            prim_n = sum(1 for cod in cli_m if cod not in antes)
        # (10/11, recado 20261109-1345) conversao e 1a visita POR ESTADO,
        # pelo supervisor do vendedor (MA Denylson, PA Lais, AM Francisco)
        sup_de = {}
        for r_ in regs:
            if r_.get("vendedor"):
                sup_de.setdefault(rn._curto_pessoa(r_["vendedor"]),
                                  r_.get("supervisor") or "")
        por_uf_ = {}
        for v_, cl in visd.items():
            nm_ = rn.sem_acento(str(sup_de.get(v_, ""))).upper()
            uf_ = next((u for p_, u in rn.SUPERVISOR_UF.items()
                        if nm_.startswith(p_)), None)
            if not uf_:
                continue
            d_ = por_uf_.setdefault(uf_, {})
            for cod, ds in cl.items():
                d_.setdefault(cod, set()).update(ds)
        for uf_, cm_ in por_uf_.items():
            conv_uf[uf_] = (
                len(cm_),
                sum(1 for cod, ds in cm_.items()
                    if any(x_ >= min(ds) for x_ in compras.get(cod, ()))),
                None if antes is None else
                sum(1 for cod in cm_ if cod not in antes))
    except Exception as erro:                           # noqa: BLE001
        avisos.append(f"Conversão / 1ª visita: {erro}")
    nvis = len(cli_m)
    cvv = conv_n / nvis if nvis else None
    card(2, "conv_visitados", "% Conversão nos visitados", cvv, cvv, f_frac,
         "vc_visitas", "Farol de Visita (Espelho cliente a cliente)",
         f"visitados no mês com pedido VND/VEA no dia da 1ª visita ou "
         f"depois ÷ visitados ({br(conv_n)} de {br(nvis)}; o cliente conta "
         "uma vez na BAP, já compre ou não); sem meta",
         ant=do_hist("conv_visitados", *a_ant),
         media3=_media3("conv_visitados"),
         du=(f"{f_1(conv_n / ndp_r)} convertidos" if nvis and ndp_r
             else "—"))
    if prim_n is None:
        card(2, "primeira_visita", "% 1ª visita", None, None, f_frac,
             "vc_visitas", "Farol de Visita (Espelho cliente a cliente)",
             "visitados no mês que nunca tinham sido visitados antes (em "
             "nenhum mês, por nenhum vendedor) ÷ visitados; o registro "
             "cliente a cliente começa em OUT/26",
             valor="início do registro",
             linhas=[("Visitados", br(nvis)), ("Média/DU", "—")])
        cards[-1]["tom"] = ""           # sem cor: nao ha base ainda
    else:
        pv_ = prim_n / nvis if nvis else None
        card(2, "primeira_visita", "% 1ª visita", pv_, pv_, f_frac,
             "vc_visitas", "Farol de Visita (Espelho cliente a cliente)",
             f"visitados no mês que nunca tinham sido visitados antes (em "
             f"nenhum mês, por nenhum vendedor) ÷ visitados ({br(prim_n)} "
             f"de {br(nvis)}); sem meta",
             ant=do_hist("primeira_visita", *a_ant),
             media3=_media3("primeira_visita"),
             du=(f"{f_1(prim_n / ndp_r)} 1ª visita" if nvis and ndp_r
                 else "—"))

    k_ad = kpi_de("vc_visitas", "Aderência")
    ad = _num(k_ad.get("valor"))
    m_ad = re.search(r"([\d\.]+) visitados de ([\d\.]+) programados",
                     str(k_ad.get("detalhe") or ""))
    ad_v, ad_p = ((_num(m_ad.group(1)), _num(m_ad.group(2))) if m_ad
                  else (None, None))
    card(2, "aderencia", "Aderência à rota", ad, ad,
         lambda v: "—" if v is None else br(v) + "%", "vc_visitas",
         "Farol de Visita (Aderência ao Planner)",
         "programados do Planner que foram visitados; média/DU = visitados "
         "de programados por DU; meta 90%", meta=90.0,
         gap_fmt=f_pp,
         du=(f"{f_1(ad_v / ndp_v)} de {f_1(ad_p / ndp_v)}"
             if ad_p and ndp_v else "—"))

    k_j = kpi_de("vc_visitas", "Jornada líquida")
    jl = _hhmm(k_j.get("valor"))
    try:                # (05/11) a jornada so dos dias fechados (ate ontem)
        # (09/11, recado 20261109-1300) com a hora da prospeccao (o 1o e
        # o ultimo horario do dia), como no Farol de Visita
        rj_ = rn.resumo_jornada(rn.com_cadastro_como_visita(
            ctx, [r for r in regs_m if r["data"] <= corte], de, corte),
            rn._jornada_do_mes(ctx, ano, mes))
        jl = rj_["media"] / 3600.0 if rj_["media"] is not None else (
            jl if corte >= hoje else None)
    except Exception as erro:                           # noqa: BLE001
        avisos.append(f"Jornada até ontem: {erro}")
    card(2, "jornada", "Jornada líquida", jl, jl, f_hora, "vc_visitas",
         "Farol de Visita (Jornada líquida)",
         "1ª à última atividade (cliente ou prospecção), no expediente "
         "(média dos dias: já é por "
         "dia útil); meta 8h", meta=8.0, du=por_du(
             jl * ndp_v if jl is not None and ndp_v else None, ndp_v,
             f_hora))

    # ================= 3 · CARTEIRA E CREDITO (fotos do dia: projecao =
    # o numero de hoje; MoM/M3M pelo painel_diretor_hist.json)
    dt_ant = None
    try:
        dt_ant = date.fromisoformat(str((hist.get(
            f"{a_ant[0]}-{a_ant[1]:02d}") or {}).get("_dados_ate")))
    except (TypeError, ValueError):
        dt_ant = None
    hoje_m = min(hoje, fim_mes)
    n_foto = (len([x for x in dus(*a_ant) + du_mes
                   if dt_ant < x <= hoje_m]) if dt_ant else du_ate(hoje_m))

    def var_du(atual, ant_, fmt_):
        """(05/11) foto do dia: a variacao por DU desde o fechamento do mes
        anterior gravado no historico."""
        if atual is None or ant_ is None or not n_foto or not dt_ant:
            return "—"
        v = (atual - ant_) / n_foto
        return (("+" if v >= 0 else "−") + fmt_(abs(v))
                + f" desde {dt_ant:%d/%m}")

    def ant_e_m3(chave_):
        v3 = [do_hist(chave_, a, m) for a, m in meses3]
        return (do_hist(chave_, *a_ant),
                sum(v3) / 3 if all(v is not None for v in v3) else None)

    k_in = kpi_de("pl_inadimplencia", "Em atraso")
    inad = _num(k_in.get("valor"))
    a_, m3_ = ant_e_m3("inad")
    card(3, "inad", "Inadimplência", inad, inad, f_moeda,
         "pl_inadimplencia", "Farol de Inadimplência",
         "títulos vencidos em aberto (foto do dia); MoM/M3M pelo fechamento "
         "dos meses anteriores gravado pelo painel; variação/DU desde esse "
         "fechamento", ant=a_, media3=m3_, sobe_ruim=True,
         du=var_du(inad, a_, f_moeda), rot_du="Variação/DU")

    compr, ja = [], 0
    for c in ctx.base["clientes"]:
        if c.get("interno") or c.get("inativo"):
            continue
        if (c.get("receita_6m") or 0) > 0 and (c.get("limite_disp") or 0) > 0 \
                and (c.get("atraso") or 0) <= 0:
            if not rn.positivou(ctx, c["cod"], comp):
                compr.append(c)
            elif c["cod"] in pos:       # (05/11) comprou ate ontem
                ja += 1
    a_, m3_ = ant_e_m3("compraveis")
    # (05/11) quantos dos compraveis compraram por DU (ate a ultima NF) e a
    # projecao de quantos ainda ficam sem pedido no fim do mes
    proj_c = (max(0.0, len(compr) - ja / ndp_a * max(0, ndm - ndp_a))
              if ndp_a else None)
    card(3, "compraveis", "Compram, têm limite e estão em dia, sem pedido "
         "no mês", len(compr), proj_c, f_int, "vc_base",
         "Farol de Clientes",
         "receita 6 meses > 0, limite disponível > 0, sem atraso, sem compra "
         "líquida no mês (foto do dia); média/DU = desses, quantos já "
         "compraram ÷ DU; projeção = os de hoje − média/DU × DU que faltam",
         ant=a_, media3=m3_, sobe_ruim=True,
         du=f"{f_1(ja / ndp_a)} compraram" if ndp_a else "—")

    meses4 = [_mes_ant(ano, mes, n) for n in (4, 3, 2, 1)]
    soma4 = defaultdict(float)
    for it in itens:
        d = it.get("dt_nf")
        if d and (d.year, d.month) in meses4:
            v = rn._liquido(it)
            if v is not None:
                soma4[it["cliente"]] += v
    chave = {c for c, v in soma4.items() if v >= 10000}
    comp_ch = {c for c in chave if c in pos}
    rot4 = f"{MESES_C[meses4[0][1]]}–{MESES_C[meses4[-1][1]]}"
    card(3, "contas_chave", f"Contas-chave que compraram (≥ R$ 10 mil "
         f"{rot4})", len(comp_ch),
         min(len(chave), len(comp_ch) / ndp_a * ndm) if chave and ndp_a
         else None,
         f_int, "vc_base", "Farol de Clientes",
         f"clientes com ≥ R$ 10 mil líquidos nos 4 meses anteriores "
         f"({len(chave)}, somaram "
         f"{moeda(sum(soma4[c] for c in chave), True)}); meta = todas "
         "comprarem no mês", meta=len(chave) or None,
         du=por_du(len(comp_ch), ndp_a, f_1))

    # ================= 4 · PRECO E ESTOQUE
    est, ixe = [], {}
    try:
        try:
            from xlsx_rapido import load_workbook  # noqa: PLC0415
        except ImportError:
            from openpyxl import load_workbook  # noqa: PLC0415
        wb = load_workbook(raiz / "RELATORIOS" / "ESTOQUE_BAP.xlsx",
                           read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        h = [str(x) for x in next(rows)]
        ixe = {c: i for i, c in enumerate(h)}
        est = [r for r in rows if r and len(r) > ixe["ESTOQUE"]
               and r[ixe["ESTOQUE"]]]
        try:
            wb.close()
        except Exception:                               # noqa: BLE001
            pass
    except Exception as erro:                           # noqa: BLE001
        avisos.append(f"ESTOQUE_BAP: {erro}")

    def f0(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0
    sem, outra, v_sem = [], set(), None
    custo = defaultdict(list)
    if est:
        pc, pi, cp = ixe["PRECO_CAPITAL"], ixe["PRECO_INTERIOR"], \
            ixe["COD_PRODUTO"]
        com_preco = {r[cp] for r in est if f0(r[pc]) > 0 and f0(r[pi]) > 0}
        sem = [r for r in est if f0(r[ixe["ESTOQUE"]]) > 0
               and (f0(r[pc]) <= 0 or f0(r[pi]) <= 0)]
        v_sem = sum(f0(r[ixe["ESTOQUE"]]) * f0(r[ixe["PPEDIDO"]])
                    for r in sem)
        outra = {r[cp] for r in sem if r[cp] in com_preco}
        for r in est:
            custo[r[cp]].append(f0(r[ixe["PPEDIDO"]]))
    a_, m3_ = ant_e_m3("sem_preco")
    card(4, "sem_preco", "Estoque sem preço de venda", v_sem, v_sem,
         f_moeda, "vc_preco", "ESTOQUE_BAP",
         f"estoque > 0 com preço capital ou interior vazio/zero, a P. "
         f"PEDIDO ({br(len(sem))} itens; {br(len(outra))} já têm preço em "
         "outra filial); foto do dia; variação/DU desde o fechamento do mês "
         "anterior", ant=a_, media3=m3_, sobe_ruim=True,
         du=var_du(v_sem, a_, f_moeda), rot_du="Variação/DU")

    cols, ls, _t = tab("pl_giro", "Curva A parada")
    ig = {c: i for i, c in enumerate(cols)}

    def cu(cod):
        v = [x for x in custo.get(cod, []) if x > 0]
        return sum(v) / len(v) if v else 0.0
    par, fora = [], []
    if {"PARADO (D)", "EST.", "FILIAL", "PRODUTO"} <= set(ig):
        for r in ls:
            d_ = r[ig["PARADO (D)"]]
            if (r[ig["EST."]] or 0) > 0 and (d_ is None or d_ > 60):
                (fora if str(r[ig["FILIAL"]]).upper() in FORA_OPERACAO
                 else par).append(r)
    vpar = [(r, (r[ig["EST."]] or 0) * cu(r[ig["PRODUTO"]])) for r in par]
    v_par = sum(v for _r, v in vpar)
    v_fora = sum((r[ig["EST."]] or 0) * cu(r[ig["PRODUTO"]]) for r in fora)
    a_, m3_ = ant_e_m3("parado")
    card(4, "parado", "Estoque parado · curva A, +60 dias sem venda",
         v_par, v_par, f_moeda, "pl_giro",
         "Farol de Giro (Curva A parada) × P. PEDIDO",
         f"curva A com estoque e sem venda há mais de 60 dias, filiais com "
         f"equipe (AM, RR, PA, MA): {br(len(par))} itens; fora da operação "
         f"(Cuiabá, Macapá) {moeda(v_fora, True)}; foto do dia; variação/DU "
         "desde o fechamento do mês anterior",
         ant=a_, media3=m3_, sobe_ruim=True,
         du=var_du(v_par, a_, f_moeda), rot_du="Variação/DU")

    cfg = ler_config(raiz)
    ap = cfg.get("acao_preco") or {}
    card(4, "acao_preco", "Ação de preço" + (f" · {ap['titulo']}"
                                            if ap.get("titulo") else ""),
         None, None, f_int, "", "Cadastro do Painel do Diretor (Editar)",
         "kit ou campanha em aprovação (digitado, sem meta)",
         valor=" ".join(x for x in (ap.get("valor"), ap.get("small"))
                        if x) or "—",
         linhas=[("", re.sub(r"</?b>", "", ap.get("sub")
                             or "nenhuma ação em aprovação"))])

    # ================= historico: os numeros do mes (o fechamento de cada
    # mes e a base do MoM/M3M dos cartoes que sao foto do dia)
    hp = _hist_path(raiz)
    novo = {c["chave"]: c["numero"] for c in cards
            if c["numero"] is not None}
    if gravar_hist and corte.month == hoje.month and corte.year == hoje.year \
            and hist.get(comp, {}).get("_valores") != novo:
        try:
            hist[comp] = {**novo, "_valores": novo,
                          "_dados_ate": corte.isoformat()}
            hp.parent.mkdir(parents=True, exist_ok=True)
            tmp = hp.with_suffix(".tmp")
            tmp.write_text(json.dumps(hist, ensure_ascii=False, indent=1,
                                      default=str), "utf-8")
            os.replace(tmp, hp)
        except OSError as erro:
            avisos.append(f"Histórico do Painel do Diretor: {erro}")

    # ================= coluna da direita
    leitura = []
    for b in (1, 2, 3, 4):
        r_ = [c for c in cards if c["bloco"] == b and c["tom"] == "alerta"]
        if r_ and len(leitura) < 3:
            c = r_[0]
            leitura.append((f"{c['titulo']}: {c['valor']}", " · ".join(
                f"{a} {b}" for a, b in c["linhas"]
                if a in ("Projeção", "GAP meta", "% ating. proj.", "MoM"))))
    return {"comp": comp, "ano": ano, "mes": mes, "mes_nome": MESES_L[mes],
            "prox_mes": MESES_C[mes % 12 + 1], "dados_ate": corte, "dados_ate_a": corte_a,
            "ndp": ndp, "ndp_a": ndp_a, "ndm": ndm, "cards": cards, "leitura": leitura,
            "acoes": [(a.get("t", ""), a.get("d", ""))
                      for a in cfg.get("acoes") or [] if isinstance(a, dict)],
            "compromisso": cfg.get("compromisso") or {},
            "avisos": avisos,
            # (10/11, recado 20261109-1345) as tabelas por estado/supervisor
            # dos farois de origem, para os cartoes do modelo RRM
            # (painel_rrm.py): (colunas, linhas, total)
            "_tabs": {"vis_sup": tab("vc_visitas", "Por supervisor"),
                      "mk_uf": tab("vc_markup", "Por UF"),
                      "saldo_uf": tab("vc_saldo", "Por UF"),
                      "inad_uf": tab("pl_inadimplencia", "Por UF"),
                      "meta_sup": tab("vc_meta", "Por supervisor")},
            "_conv_uf": conv_uf, "_ndp_vis": ndp_v}


def kpis(dados) -> list:
    """Os 16 cartoes no formato kpi() (Exportar > Aba atual)."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    cor = {"ok": "ok", "atencao": "atencao", "alerta": "alerta"}
    return [rn.kpi(c["titulo"], c["valor"], cor.get(c["tom"], "neutro"),
                   " · ".join(f"{a} {b}".strip() for a, b in c["linhas"]),
                   [(a or "Detalhe", b, "") for a, b in c["linhas"]]
                   + [("Origem", c["origem"], "")])
            for c in dados["cards"]]


# ------------------------------------------------------------ imagem/PDF
VERDE_T = (63, 140, 46)
AMAR_T = (232, 163, 23)
VERM_T = (214, 69, 69)
CINZA_T = (187, 187, 187)
ACENTO = (98, 187, 71)
PRETO = (17, 17, 17)
FUNDO_I = (244, 245, 244)
BRANCO_I = (255, 255, 255)
TXT = (21, 21, 21)
TXT2 = (85, 85, 85)
TXT3 = (68, 68, 68)
TOM_COR = {"ok": VERDE_T, "atencao": AMAR_T, "alerta": VERM_T}


def imagem(dados, destino_png=None, destino_pdf=None, rodape=""):
    """O painel numa imagem 1600 x 1000 (x1,5 = 2400 x 1500) para o
    WhatsApp e/ou um PDF A4 deitado de 1 pagina."""
    from PIL import Image, ImageDraw                    # noqa: PLC0415
    import parcial_imagem as pi                         # noqa: PLC0415
    s = 1.5
    W, H = int(1600 * s), int(1000 * s)
    img = Image.new("RGB", (W, H), FUNDO_I)
    d = ImageDraw.Draw(img)

    def F(tam, peso="normal"):
        return pi.fonte(tam, peso, s)

    def P(v):
        return int(v * s)

    def quebra(txt, fonte, larg):
        linhas = []
        for par in str(txt).split("\n"):
            pal, atual = par.split(), ""
            for w_ in pal:
                t = (atual + " " + w_).strip()
                if d.textlength(t, font=fonte) <= larg:
                    atual = t
                else:
                    if atual:
                        linhas.append(atual)
                    atual = w_
            linhas.append(atual)
        return linhas

    # cabecalho
    d.rectangle([0, 0, W, P(86)], fill=PRETO)
    d.text((P(40), P(22)), "BAP", font=F(34, "black"), fill=BRANCO_I)
    d.text((P(40) + d.textlength("BAP", font=F(34, "black")) + P(10), P(40)),
           "AUTOPARTS", font=F(13, "bold"), fill=ACENTO)
    t1 = f"PAINEL DO DIRETOR · {dados['mes_nome']} {dados['ano']}"
    d.text((W - P(40) - d.textlength(t1, font=F(26, "bold")), P(14)), t1,
           font=F(26, "bold"), fill=BRANCO_I)
    da = dados.get("dados_ate_a") or dados["dados_ate"]
    t2 = (f"BAP AUTOPARTS · dados até {da:%d/%m} · {dados.get('ndp_a', dados['ndp'])} de "
          f"{dados['ndm']} dias úteis")
    d.text((W - P(40) - d.textlength(t2, font=F(14)), P(52)), t2,
           font=F(14), fill=(189, 189, 189))
    d.rectangle([0, P(86), W, P(91)], fill=ACENTO)
    # rodape
    d.rectangle([0, H - P(42), W, H], fill=PRETO)
    d.text((P(40), H - P(30)), "Fonte: BAP Tools · regras do Painel "
           "Executivo · cada cartão abre o farol de origem", font=F(12.5),
           fill=(189, 189, 189))
    rd = rodape or f"gerado em {date.today():%d/%m/%Y}"
    d.text((W - P(40) - d.textlength(rd, font=F(12.5)), H - P(30)), rd,
           font=F(12.5), fill=(189, 189, 189))

    x0, y = P(40), P(109)
    larg_esq = W - P(40) - P(330) - P(20) - x0
    cols_bloco = {1: [1.25, 1, 1, 1, 1], 2: [1] * 5, 3: [1] * 3, 4: [1] * 3}
    alt_bloco = {1: P(172), 2: P(172), 3: P(172), 4: P(172)}
    for b, tit, sub in BLOCOS:
        cs = [c for c in dados["cards"] if c["bloco"] == b]
        d.text((x0, y), f"{b} · {tit}", font=F(15, "bold"), fill=TXT)
        x_t = x0 + d.textlength(f"{b} · {tit}", font=F(15, "bold")) + P(12)
        if b == 1:                       # (06/11) os DU ao lado do titulo
            t_du = _du_titulo(dados)
            d.text((x_t, y), t_du, font=F(15, "bold"), fill=VERDE_DU)
            x_t += d.textlength(t_du, font=F(15, "bold")) + P(12)
        d.text((x_t, y + P(2)), sub, font=F(13), fill=(102, 102, 102))
        y += P(26)
        pesos = cols_bloco[b][:len(cs)] or [1]
        gap = P(12)
        unid = (larg_esq - gap * (len(pesos) - 1)) / sum(pesos)
        x = x0
        h = alt_bloco[b]
        for c, pz in zip(cs, pesos):
            w = int(unid * pz)
            cor = TOM_COR.get(c["tom"], CINZA_T)
            d.rounded_rectangle([x, y, x + w, y + h], radius=P(10),
                                fill=BRANCO_I)
            d.rectangle([x, y + P(4), x + P(6), y + h - P(4)], fill=cor)
            # rotulo (sem selo: o cartao e so o padrao)
            fl = F(12.5, "bold")
            ty = y + P(13)
            for ln in quebra(c["titulo"].upper(), fl, w - P(34))[:2]:
                d.text((x + P(21), ty), ln, font=fl, fill=TXT2)
                ty += P(17)
            ty = max(ty, y + P(47)) + P(2)
            fv = F(30 if len(str(c["valor"])) <= 10 else 24, "bold")
            d.text((x + P(21), ty), str(c["valor"]), font=fv, fill=TXT)
            ty += P(42)
            # as linhas do padrao: rotulo a esquerda, numero a direita
            fr_, fn_ = F(12.5), F(12.5, "bold")
            for rot, val in c["linhas"]:
                if ty + P(17) > y + h - P(4):
                    break
                if not rot:
                    for ln in quebra(val, fr_, w - P(34)):
                        if ty + P(17) > y + h - P(4):
                            break
                        d.text((x + P(21), ty), ln, font=fr_, fill=TXT3)
                        ty += P(17.5)
                    continue
                d.text((x + P(21), ty), rot, font=fr_, fill=TXT2)
                vt = str(val)
                while len(vt) > 3 and d.textlength(vt, font=fn_) > \
                        w - P(34) - d.textlength(rot, font=fr_) - P(8):
                    vt = vt[:-2] + "…"
                d.text((x + w - P(13) - d.textlength(vt, font=fn_), ty), vt,
                       font=fn_, fill=TXT)
                ty += P(18)
            x += w + gap
        y += h + P(14)

    # coluna da direita
    xs, ys = W - P(40) - P(330), P(109)
    ws_ = P(330)
    d.rounded_rectangle([xs, ys, xs + ws_, H - P(56)], radius=P(10),
                        fill=BRANCO_I)
    xx, yy = xs + P(20), ys + P(18)
    lw_ = ws_ - P(40)

    def secao(titulo, itens, numerado=True):
        nonlocal yy
        d.text((xx, yy), titulo, font=F(15, "bold"), fill=TXT)
        yy += P(28)
        if not itens:
            d.text((xx, yy), "a preencher (Editar)", font=F(13), fill=(150,
                                                                       150,
                                                                       150))
            yy += P(22)
        for i, (t, dsc) in enumerate(itens, 1):
            pre = f"{i}. " if numerado else ""
            for k_, ln in enumerate(quebra(pre + t, F(13.5, "bold"), lw_)):
                d.text((xx, yy), ln, font=F(13.5, "bold"), fill=TXT)
                yy += P(19)
            for ln in quebra(dsc, F(13.5), lw_ - P(14)):
                d.text((xx + P(14), yy), ln, font=F(13.5), fill=TXT3)
                yy += P(19)
            yy += P(8)

    secao("LEITURA DO MÊS", dados["leitura"])
    d.line([xx, yy, xx + lw_, yy], fill=(227, 227, 227), width=P(1))
    yy += P(12)
    secao(f"AÇÕES · {dados['prox_mes'].upper()}", dados["acoes"])
    d.line([xx, yy, xx + lw_, yy], fill=(227, 227, 227), width=P(1))
    yy += P(12)
    cp = dados["compromisso"] or {}
    d.text((xx, yy), f"COMPROMISSO {dados['prox_mes'].upper()}",
           font=F(15, "bold"), fill=TXT)
    yy += P(28)
    for ln in quebra(cp.get("t") or "a preencher (Editar)", F(22, "bold"),
                     lw_):
        d.text((xx, yy), ln, font=F(22, "bold"), fill=TXT)
        yy += P(28)
    for ln in quebra(cp.get("d") or "", F(13.5), lw_):
        d.text((xx, yy), ln, font=F(13.5), fill=TXT3)
        yy += P(19)
    yy += P(10)
    lx = xx
    for cor, t in ((VERDE_T, "ating. proj. ≥ 100%"), (AMAR_T, "80–99%"),
                   (VERM_T, "< 80% · sem meta: piorou no MoM")):
        tw = d.textlength(t, font=F(12)) + P(28)
        if lx + tw > xx + lw_:
            lx, yy = xx, yy + P(20)
        d.ellipse([lx, yy + P(3), lx + P(10), yy + P(13)], fill=cor)
        d.text((lx + P(15), yy), t, font=F(12), fill=TXT2)
        lx += tw

    if destino_png:
        img.save(destino_png, "PNG", optimize=True)
    if destino_pdf:
        # A4 deitado a 200 dpi: 2339 x 1654, o painel centrado
        A4 = (2339, 1654)
        pag = Image.new("RGB", A4, BRANCO_I)
        k_ = min((A4[0] - 80) / W, (A4[1] - 80) / H)
        im2 = img.resize((int(W * k_), int(H * k_)), Image.LANCZOS)
        pag.paste(im2, ((A4[0] - im2.width) // 2, (A4[1] - im2.height) // 2))
        pag.save(destino_pdf, "PDF", resolution=200.0)
    return img


# ------------------------------------------------------------ tela (Tk)
def tela(pai, dados, abrir=None, ao_editar=None, exportar=None):
    """O Painel do Diretor dentro da aba do Painel Executivo: 4 blocos de
    cartoes (clique = abre o farol de origem) e a coluna da direita
    (Leitura do mes, Acoes, Compromisso) com Editar, PDF A4 e PNG."""
    import tkinter as tk                                # noqa: PLC0415
    from tkinter import ttk                             # noqa: PLC0415
    import bap_visual as bv                             # noqa: PLC0415
    cores = {"ok": "#3F8C2E", "atencao": "#E8A317", "alerta": "#D64545"}
    raiz_f = tk.Frame(pai, background=bv.FUNDO)
    dir_ = tk.Frame(raiz_f, background=bv.CARTAO, highlightthickness=1,
                    highlightbackground=bv.CINZA_LINHA, width=330)
    dir_.pack(side="right", fill="y", padx=(10, 0))
    dir_.pack_propagate(False)
    esq = tk.Frame(raiz_f, background=bv.FUNDO)
    esq.pack(side="left", fill="both", expand=True)
    pesos = {1: [5, 4, 4, 4, 4], 2: [1] * 5, 3: [1] * 3, 4: [1] * 3}
    for b, tit, sub in BLOCOS:
        cab = tk.Frame(esq, background=bv.FUNDO)
        cab.pack(fill="x", pady=(4 if b > 1 else 0, 3))
        tk.Label(cab, text=f"{b} · {tit}", background=bv.FUNDO,
                 foreground=bv.TEXTO, font=bv.fonte(10, "bold")).pack(
            side="left")
        if b == 1:                       # (06/11) os DU ao lado do titulo
            tk.Label(cab, text=_du_titulo(dados), background=bv.FUNDO,
                     foreground="#2E7D32", font=bv.fonte(10, "bold")).pack(
                side="left", padx=(8, 0))
        tk.Label(cab, text=sub, background=bv.FUNDO, foreground=bv.SUAVE,
                 font=bv.fonte(8)).pack(side="left", padx=(8, 0))
        lin = tk.Frame(esq, background=bv.FUNDO)
        lin.pack(fill="x")
        lin.rowconfigure(0, weight=1)
        cs = [c for c in dados["cards"] if c["bloco"] == b]
        for j, (c, pz) in enumerate(zip(cs, pesos[b])):
            lin.columnconfigure(j, weight=pz, uniform=f"b{b}")
            cor = cores.get(c["tom"], bv.CINZA_LINHA)
            f = tk.Frame(lin, background=bv.CARTAO, highlightthickness=1,
                         highlightbackground=bv.CINZA_LINHA,
                         cursor="hand2" if c["rid"] and abrir else "")
            f.grid(row=0, column=j, sticky="nsew", padx=(0, 8))
            tk.Frame(f, background=cor, width=5).pack(side="left", fill="y")
            d = tk.Frame(f, background=bv.CARTAO)
            d.pack(side="left", fill="both", expand=True, padx=(9, 8),
                   pady=6)
            top = tk.Frame(d, background=bv.CARTAO)
            top.pack(fill="x")
            ws = [f, d, top]
            ws.append(tk.Label(top, text=c["titulo"].upper(),
                               background=bv.CARTAO, foreground=bv.SUAVE,
                               font=bv.fonte(8, "bold"), anchor="w",
                               justify="left", wraplength=170))
            ws[-1].pack(side="left", fill="x", expand=True)
            d.bind("<Configure>", lambda e, w_=ws[-1]: w_.configure(
                wraplength=max(90, e.width - 4)))
            ws.append(tk.Label(d, text=c["valor"], background=bv.CARTAO,
                               foreground=bv.TEXTO, anchor="w",
                               font=bv.fonte(16, "bold")))
            ws[-1].pack(fill="x", pady=(2, 1))
            # as linhas do padrao (30/10): projecao, DU, GAP meta e % ating.
            # projetado - ou MoM e M3M quando nao tem meta
            grade = tk.Frame(d, background=bv.CARTAO)
            grade.pack(fill="x")
            grade.columnconfigure(1, weight=1)
            ws.append(grade)
            for i_, (rot, val) in enumerate(c["linhas"]):
                if rot:
                    ws.append(tk.Label(grade, text=rot, background=bv.CARTAO,
                                       foreground=bv.SUAVE, anchor="w",
                                       font=bv.fonte(8)))
                    ws[-1].grid(row=i_, column=0, sticky="w")
                    ws.append(tk.Label(grade, text=val, background=bv.CARTAO,
                                       foreground=bv.TEXTO, anchor="e",
                                       font=bv.fonte(8, "bold")))
                    ws[-1].grid(row=i_, column=1, sticky="e")
                else:
                    ws.append(tk.Label(grade, text=val, background=bv.CARTAO,
                                       foreground=bv.SUAVE, anchor="w",
                                       justify="left", font=bv.fonte(8),
                                       wraplength=170))
                    ws[-1].grid(row=i_, column=0, columnspan=2, sticky="w")
            ajuda = (f"{c['regra']}\nOrigem: {c['origem']}"
                     + ("\n\nClique para abrir o farol." if c["rid"] and abrir
                        else ""))
            for w_ in ws:
                bv.Dica(w_, ajuda)
                if c["rid"] and abrir:
                    w_.bind("<Button-1>", lambda _e, r=c["rid"]: abrir(r))
    # a coluna da direita
    pad = {"padx": 14}

    def titulo(t):
        tk.Label(dir_, text=t, background=bv.CARTAO, foreground=bv.TEXTO,
                 font=bv.fonte(10, "bold"), anchor="w").pack(
            fill="x", pady=(10, 2), **pad)

    def itens(lst):
        if not lst:
            tk.Label(dir_, text="a preencher (Editar)", background=bv.CARTAO,
                     foreground=bv.SUAVE, font=bv.fonte(8), anchor="w").pack(fill="x",
                                                                   **pad)
        for i, (t, d_) in enumerate(lst, 1):
            tk.Label(dir_, text=f"{i}. {t}", background=bv.CARTAO,
                     foreground=bv.TEXTO, font=bv.fonte(9, "bold"),
                     anchor="w", justify="left", wraplength=295).pack(
                fill="x", **pad)
            tk.Label(dir_, text=d_, background=bv.CARTAO,
                     foreground=bv.SUAVE, font=bv.fonte(8), anchor="w",
                     justify="left", wraplength=280).pack(
                fill="x", padx=(28, 14), pady=(0, 4))
    titulo("LEITURA DO MÊS")
    itens(dados["leitura"])
    titulo(f"AÇÕES · {dados['prox_mes'].upper()}")
    itens(dados["acoes"])
    titulo(f"COMPROMISSO {dados['prox_mes'].upper()}")
    cp = dados["compromisso"] or {}
    tk.Label(dir_, text=cp.get("t") or "a preencher (Editar)",
             background=bv.CARTAO, foreground=bv.TEXTO,
             font=bv.fonte(13, "bold"), anchor="w", justify="left",
             wraplength=295).pack(fill="x", **pad)
    tk.Label(dir_, text=cp.get("d") or "", background=bv.CARTAO,
             foreground=bv.SUAVE, font=bv.fonte(8), anchor="w",
             justify="left", wraplength=295).pack(fill="x", **pad)
    leg = tk.Frame(dir_, background=bv.CARTAO)
    leg.pack(fill="x", pady=(10, 0), **pad)
    for cor, t in ((cores["ok"], "≥ 100%"), (cores["atencao"], "80–99%"),
                   (cores["alerta"], "< 80% / piorou")):
        tk.Label(leg, text="●", background=bv.CARTAO, foreground=cor,
                 font=bv.fonte(9)).pack(side="left")
        tk.Label(leg, text=t, background=bv.CARTAO, foreground=bv.SUAVE,
                 font=bv.fonte(8)).pack(side="left", padx=(1, 8))
    bts = tk.Frame(dir_, background=bv.CARTAO)
    bts.pack(fill="x", pady=(14, 4), **pad)
    for txt, cmd in (("Editar ações e compromisso", ao_editar),
                     ("PDF A4", exportar and (lambda: exportar("pdf"))),
                     ("PNG (WhatsApp)", exportar and (lambda: exportar("png")))):
        if cmd:
            ttk.Button(bts, text=txt, command=cmd).pack(fill="x", pady=2)
    tk.Label(dir_, text=f"dados até {dados.get('dados_ate_a') or dados['dados_ate']:%d/%m}"
             f" · {dados.get('ndp_a', dados['ndp'])} de {dados['ndm']} dias úteis",
             background=bv.CARTAO, foreground=bv.SUAVE,
             font=bv.fonte(7)).pack(fill="x", **pad)
    return raiz_f


def editar(janela, raiz, ao_gravar=None):
    """Os textos livres do Alexandre: ate 3 acoes, o compromisso e a acao de
    preco em aprovacao. Grava o painel_diretor_config.json."""
    import tkinter as tk                                # noqa: PLC0415
    from tkinter import messagebox                      # noqa: PLC0415
    cfg = ler_config(raiz)
    top = tk.Toplevel(janela)
    top.title("Painel do Diretor · textos")
    top.transient(janela)
    top.resizable(False, False)
    fr = tk.Frame(top, padx=14, pady=10)
    fr.pack(fill="both", expand=True)
    campos = {}

    def campo(rot, valor, larg=60, linha=None):
        tk.Label(fr, text=rot, anchor="w").grid(row=linha, column=0,
                                                sticky="w", pady=2)
        e = tk.Entry(fr, width=larg)
        e.insert(0, valor or "")
        e.grid(row=linha, column=1, sticky="we", pady=2)
        return e
    ln = 0
    acoes = list(cfg.get("acoes") or []) + [{}] * 3
    for i in range(3):
        a = acoes[i] if isinstance(acoes[i], dict) else {}
        campos[f"at{i}"] = campo(f"Ação {i + 1} (título)", a.get("t"),
                                 linha=ln)
        campos[f"ad{i}"] = campo("   detalhe", a.get("d"), linha=ln + 1)
        ln += 2
    cp = cfg.get("compromisso") or {}
    campos["ct"] = campo("Compromisso (destaque)", cp.get("t"), linha=ln)
    campos["cd"] = campo("   a conta", cp.get("d"), linha=ln + 1)
    ln += 2
    ap = cfg.get("acao_preco") or {}
    campos["pt"] = campo("Ação de preço (nome)", ap.get("titulo"), linha=ln)
    campos["pv"] = campo("   número", ap.get("valor"), linha=ln + 1)
    campos["ps"] = campo("   unidade (kits, baldes...)", ap.get("small"),
                         linha=ln + 2)
    campos["pd"] = campo("   detalhe", re.sub(r"</?b>", "", ap.get("sub")
                                              or ""), linha=ln + 3)
    ln += 4

    def gravar():
        g = {k: e.get().strip() for k, e in campos.items()}
        novo = {"acoes": [{"t": g[f"at{i}"], "d": g[f"ad{i}"]}
                          for i in range(3) if g[f"at{i}"]],
                "compromisso": {"t": g["ct"], "d": g["cd"]},
                "acao_preco": ({"titulo": g["pt"], "valor": g["pv"],
                                "small": g["ps"], "sub": g["pd"]}
                               if g["pv"] or g["pt"] else {})}
        try:
            gravar_config(raiz, novo)
        except OSError as erro:
            messagebox.showerror("Painel do Diretor", str(erro), parent=top)
            return
        top.destroy()
        if ao_gravar:
            ao_gravar()
    bt = tk.Frame(fr)
    bt.grid(row=ln, column=0, columnspan=2, sticky="e", pady=(10, 0))
    tk.Button(bt, text="Cancelar", command=top.destroy).pack(side="right")
    tk.Button(bt, text="Gravar", command=gravar).pack(side="right", padx=6)
    top.grab_set()
