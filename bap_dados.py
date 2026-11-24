# -*- coding: utf-8 -*-
"""
BAP DADOS - os dados dos relatorios, lidos UMA vez e guardados prontos.

O que deixava o Oportunidades com mais de 1 minuto para abrir era ler a
TABELA_BAP (16 MB) tres vezes a cada clique. Aqui cada pedaco de dado e
um BLOCO com as suas fontes:

    tabela ........ ftPedidos (VND, VEA, EXC, DEV), limite dos clientes,
                    condicoes de pagamento, filiais, estoque BAP, produtos
    base .......... BASE_CLIENTE + a carteira de cada cliente pelo Planner
                    (zona + segmento -> vendedor -> supervisor) e o resumo
                    gerencial do Planner
    posvenda ...... ACOMPANHAMENTO_POS_VENDA (entregas, devolucoes,
                    garantias)
    oportunidade .. a base de oportunidade (meta x realizado x limite)
    meta .......... o acompanhamento da meta e a RV do mes
    executivo ..... os indicadores executivos do ano
    comercial ..... o custo (P. PEDIDO) de cada filial+produto, a sucata da
                    bateria e as solicitacoes da SOLICITACAO_BAP que ainda
                    pedem ID

Cada bloco fica gravado em RELATORIOS\\_CACHE_RELATORIOS\\<bloco>.pkl com a
"assinatura" das fontes (data e tamanho de cada arquivo). Abriu um
relatorio e as fontes nao mudaram: carrega em 1 segundo. Mudou alguma:
refaz so aquele bloco. O BAP Tools chama atualizar_tudo() no fim de cada
rodada, entao quem abre um relatorio quase nunca espera.

Nada aqui grava em planilha: so le. O cache pode ser apagado a vontade.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

VERSAO = 27
RELATORIOS = "RELATORIOS"
PASTA_CACHE = "_CACHE_RELATORIOS"

# ---------------------------------------------------------------------------
# REGRAS DO NEGOCIO (decididas em 03/10/2026)
# ---------------------------------------------------------------------------
# Prazo do pedido, a contar da DATA DO PEDIDO, em dias UTEIS:
PRAZO_FATURAR = 2          # ate 2 dias uteis para faturar
PRAZO_ENTREGAR = 3         # ate 3 dias uteis para entregar (cidades BAP)
PRAZO_ENTREGAR_FRETE = 5   # interior (frete): o prazo de 5 dias uteis

# As cidades onde a BAP entrega sem frete. Pedido para cliente FORA delas
# e FRETE.
CIDADES_SEM_FRETE = {"MANAUS", "BOA VISTA", "BELEM", "SANTAREM", "SAO LUIS",
                     "CUIABA", "VARZEA GRANDE"}


def sem_acento(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def e_frete(cidade) -> bool:
    c = sem_acento(cidade)
    return bool(c) and c not in CIDADES_SEM_FRETE


# ---------------------------------------------------------------------------
# miudezas
# ---------------------------------------------------------------------------
def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def numero(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def data_de(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(t[:10] if fmt != "%Y%m%d" else t[:8],
                                     fmt).date()
        except ValueError:
            continue
    return None


def cod6(v) -> str:
    t = texto(v)
    return t.zfill(6) if t.isdigit() else t


FERIADOS_FIXOS = None


def feriados(raiz) -> set:
    """Feriados do Planner + os nacionais do pos-venda."""
    saida = set()
    try:
        cfg = json.loads(_cfg_planner(raiz)
                         .read_text("utf-8"))
        saida |= {data_de(f) for f in cfg.get("feriados") or []}
    except (OSError, ValueError):
        pass
    try:
        import pos_venda                                # noqa: PLC0415
        saida |= pos_venda._feriados_padrao()           # noqa: SLF001
    except Exception:                                   # noqa: BLE001
        pass
    saida.discard(None)
    return saida


def dias_uteis_entre(inicio, fim, fer=()) -> int | None:
    """Dias uteis de inicio (exclusive) ate fim (inclusive)."""
    if not inicio or not fim:
        return None
    if fim <= inicio:
        return 0
    from datetime import timedelta                      # noqa: PLC0415
    n, d = 0, inicio
    while d < fim:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in fer:
            n += 1
    return n


def somar_uteis(inicio, dias, fer=()):
    from datetime import timedelta                      # noqa: PLC0415
    d, n = inicio, 0
    while n < dias:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in fer:
            n += 1
    return d


# ---------------------------------------------------------------------------
# o cache
# ---------------------------------------------------------------------------
def pasta_relatorios(raiz) -> Path:
    return Path(raiz) / RELATORIOS


def _assinatura(arquivos, extra="") -> str:
    partes = [f"v{VERSAO}", extra]
    for a in arquivos:
        a = Path(a) if a else None
        if a and a.exists():
            st = a.stat()
            partes.append(f"{a.name}:{st.st_mtime_ns}:{st.st_size}")
            if a.name.lower() == "tabela_bap.xlsx":
                # (05/11) a rodada rapida nao regrava a TABELA_BAP: o dado
                # novo esta na fotografia (RELATORIOS\DADOS) - ela entra
                partes.append(f"foto:{_carimbo_da_fotografia(a)}")
        else:
            partes.append(f"{a.name if a else '-'}:ausente")
    return "|".join(partes)


def _abrir_mesmo_aberto(arq, abrir, tentativas: int = 3, intervalo=2.0):
    """
    (05/11) So LEITURA: a planilha aberta no Excel (ou no meio de um
    salvamento) da "Permission denied" de vez em quando - foi assim que o
    bloco comercial caiu com a SOLICITACAO_BAP aberta. Tenta de novo e, se
    ainda negar, le uma COPIA temporaria (o Excel deixa copiar o arquivo
    aberto). Nao grava nada no arquivo de verdade.
    """
    import shutil                                       # noqa: PLC0415
    import tempfile                                     # noqa: PLC0415
    ultimo = None
    for i in range(tentativas):
        try:
            return abrir(arq, read_only=True, data_only=True)
        except PermissionError as erro:
            ultimo = erro
        try:
            import atexit                               # noqa: PLC0415
            pasta = Path(tempfile.mkdtemp(prefix="bap_leitura_"))
            atexit.register(shutil.rmtree, pasta, True)
            copia = pasta / Path(arq).name
            shutil.copyfile(arq, copia)
            return abrir(copia, read_only=True, data_only=True)
        except PermissionError as erro:
            ultimo = erro
        if i < tentativas - 1:
            time.sleep(intervalo)
    raise ultimo


def _carimbo_da_fotografia(tabela) -> str:
    try:
        import dados_bap                                # noqa: PLC0415
        foto = dados_bap.fotografia_para(tabela)
        return str(foto["carimbo"]) if foto else "-"
    except Exception:                                   # noqa: BLE001
        return "-"


def _fontes(raiz, bloco) -> tuple[list, str]:
    raiz = Path(raiz)
    rel = pasta_relatorios(raiz)
    tabela = rel / "TABELA_BAP.xlsx"
    base = rel / "BASE_CLIENTE.xlsx"
    csv = raiz / "CATEGORIAS_PRODUTO.csv"
    hoje = date.today().isoformat()
    bloco, _, comp_pedida = bloco.partition("@")    # "meta@2026-10"
    try:
        import pastas_bap as pb                         # noqa: PLC0415
        planner, comp = _planner_da_meta(raiz, comp_pedida or None)
        cfg_mes = pb.config_do_planner(raiz, comp)
    except Exception:                                   # noqa: BLE001
        planner, cfg_mes = None, raiz / "planner_config.json"
    if bloco == "tabela":
        # "t2" (14/10): agua desmineralizada na familia ARREFECIMENTO -
        # refaz a familia dos produtos
        # "t3" (15/10): a tabela de preco do cliente (A1_TABELA)
        # "t4" (15/10): CATEGORIA/SISTEMA/FAMILIA/LINHA do Catalogo BAP 2026
        # (o ESTOQUE_BAP e a BASE_BAP_UNIFICADA entram na assinatura)
        try:
            import catalogo_bap as cbp                  # noqa: PLC0415
            base_cat = cbp.achar_base(raiz)
        except Exception:                               # noqa: BLE001
            base_cat = None
        # "t5" (19/10): familia ARREFECIMENTO DO MOTOR (catalogo_bap)
        # "t6" (19/10): o prazo cadastrado do cliente (A1_COND) e a loja -
        # o detalhe dos visitados da Parcial Visitas
        # "t7" (20/10): agua desmineralizada e aditivos em QUIMICOS
        # (familia_nucleo) e a base v9
        # "t8" (03/11): PECAS LINHA LEVE / PESADA / MOTO (catalogo_bap)
        return [tabela, csv, rel / "ESTOQUE_BAP.xlsx", base_cat], "t8"
    if bloco == "base":
        # "b2" (06/10): CHURN 90+ e o cliente inativo - refaz SO a base (a
        # TABELA_BAP fica, e o BAP Central nao acusa dado desatualizado)
        # "b3" (14/10): lat/lon de cada cliente (o .json da base)
        # "b4" (21/10): a RECEITA_PERIODO (3M) - o COMPRADOR (SIM/NAO) do
        # Farol Roteirizacao
        # "b5" (20/11, T-0010): a VISITA_SEMANAL nas visitas (RN-ROT-001)
        return [base, _cfg_planner(raiz),
                rel / "COORDENADAS_CLIENTES.json"], "b5"
    if bloco == "posvenda":
        # (09/10) o diario de edicoes tambem: editou no BAP, o farol refaz
        # (10/10) e o SLA de entrega cadastrado (BAP Analista › Entrega)
        return [rel / "ACOMPANHAMENTO_POS_VENDA.xlsx",
                *sorted((rel / "_EDICOES_POS_VENDA").glob("EDICOES_*.csv")),
                raiz / "transportadoras_config.json"], hoje
    if bloco == "oportunidade":
        return [planner, base, tabela, raiz / "meta_config.json", csv,
                cfg_mes], hoje
    if bloco == "meta":
        # o arquivo de visita do mes entra na assinatura: chegou o
        # RELATORIOS\Visitas\AAAAMM.csv, o Farol de Metas refaz na hora
        try:
            import meta_nucleo as mn                    # noqa: PLC0415
            vis = mn.achar_visitas_do_mes(raiz, comp)
        except Exception:                               # noqa: BLE001
            vis = None
        # "|cv1" (15/10): cadastro novo do mes conta como visita
        # "|adm10" (20/10): mes de casa pela admissao ja em outubro
        # "|du12" (21/10): meta de visita 12 por dia util e o lote de 16/10
        # fora da visita
        # "|v90" (26/10): meta de visita = 90% dos 12 por dia e a visita /
        # positivacao travadas no mes (metas_travadas_ind)
        # "|pf1" (22/10): a PROSPECCAO do Forms tambem e visita - o arquivo
        # do mes (RELATORIOS\Visitas\PROSPECCAO\PROSPECCAO_AAAAMM.xlsx)
        # entra na assinatura
        # "|pf2" (27/10): + a prospeccao do app BAP Ajuda (RELATORIOS\
        # BAP_AJUDA_RESPOSTAS\RESPOSTAS_BAP_AJUDA.xlsx) e o teste 000040 fora
        # "|pl3" (03/11): a meta por CATEGORIA com PECAS LINHA LEVE /
        # PESADA / MOTO (catalogo_bap)
        # "|in1" (03/11): vendedor INATIVO no Planner do mes sem desafio,
        # sem meta RH/RV (visita, positivacao, cadastro) - meta_nucleo
        # "|rv3" (04/11): a faixa da RV com o atingimento arredondado a 3
        # casas (meta_nucleo.valor_da_rv), igual a formula do Excel do RH
        # "|vi1" (10/11): a visita realizada casa tambem pelo comeco do nome
        # (Planner "JUGLAISON RODRIGUES" x Maxima "... DOS PRAZES")
        # "|in2" (06/11): os clientes do vendedor INATIVO sem meta de visita
        # e de positivacao (o Amapa do 000040 somava 30 na BAP)
        try:
            prosp = rel / "Visitas" / "PROSPECCAO" / (
                "PROSPECCAO_" + str(comp).replace("-", "")[:6] + ".xlsx")
        except NameError:                   # sem o PLANNER do mes
            prosp = None
        return [planner, base, tabela, raiz / "meta_config.json", csv,
                raiz / "planner_config.json", cfg_mes, vis, prosp,
                rel / "BAP_AJUDA_RESPOSTAS" / "RESPOSTAS_BAP_AJUDA.xlsx"], \
            hoje + "|cv1|cat1|arr1|adm10|du12|pf2|v90|pl3|in1|rv3|in2|vi1" + (
                f"|{comp_pedida}" if comp_pedida else "")
    if bloco == "executivo":
        # "e2" (14/10): positivacao = comprou e nao devolveu tudo e a PMZ
        # DISTRIBUIDORA interna - refaz SO este bloco
        return [tabela, raiz / "meta_config.json", csv], "e2"
    if bloco == "inadimplencia":
        # "fi1" (24/11, T-0017): as fotos diarias sem os CNPJs internos
        # (RN-GER-004) - refaz SO este bloco
        return [tabela] + _fotos_de_titulos(raiz), "fi1"
    if bloco == "comercial":
        return [tabela, rel / "SOLICITACAO_BAP.xlsx",
                raiz / "oportunidade_config.json"], \
            "|".join(a.name for a in _relatorios_de_estoque(raiz))
    raise KeyError(bloco)


BLOCOS = ("tabela", "base", "posvenda", "meta", "oportunidade", "executivo",
          "comercial", "inadimplencia")


def carregar(raiz, bloco: str, forcar: bool = False, log=None):
    """O bloco pronto - do cache, ou refeito se alguma fonte mudou."""
    raiz = Path(raiz)
    arquivos, extra = _fontes(raiz, bloco)
    assinatura = _assinatura(arquivos, extra)
    pasta = pasta_relatorios(raiz) / PASTA_CACHE
    arq = pasta / f"{bloco.replace('@', '_')}.pkl"
    if not forcar and arq.exists():
        try:
            with open(arq, "rb") as f:
                guardado = pickle.load(f)
            if guardado.get("assinatura") == assinatura:
                return guardado["dados"]
        except Exception:                               # noqa: BLE001
            pass
    if log:
        log(f"Montando {bloco}...")
    inicio = time.time()
    nome, _, comp = bloco.partition("@")
    dados = (CONSTRUTORES[nome](raiz, comp) if comp
             else CONSTRUTORES[nome](raiz))
    dados["_montado_em"] = datetime.now()
    dados["_segundos"] = round(time.time() - inicio, 1)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            pickle.dump({"assinatura": assinatura, "dados": dados}, f,
                        protocol=4)
        os.replace(tmp, arq)
    except OSError:
        pass                    # sem gravar o cache, so fica mais lento
    return dados


def do_cache(raiz, bloco: str):
    """O bloco SO se o cache estiver em dia - nunca refaz (para telas que
    precisam abrir na hora, como o BAP Central)."""
    try:
        arquivos, extra = _fontes(raiz, bloco)
        arq = pasta_relatorios(raiz) / PASTA_CACHE / f"{bloco}.pkl"
        with open(arq, "rb") as f:
            guardado = pickle.load(f)
        if guardado.get("assinatura") == _assinatura(arquivos, extra):
            return guardado["dados"]
    except Exception:                                   # noqa: BLE001
        pass
    return None


def atualizar_tudo(raiz, log=print) -> dict:
    """Para o BAP Tools, no fim da rodada: deixa todos os blocos prontos."""
    saida = {}
    for b in BLOCOS:
        try:
            t = time.time()
            carregar(raiz, b, log=None)
            saida[b] = round(time.time() - t, 1)
        except Exception as erro:                       # noqa: BLE001
            saida[b] = f"ERRO: {erro}"
            if log:
                log(f"  relatorios: bloco {b} falhou: {erro}")
    return saida


# ---------------------------------------------------------------------------
# bloco TABELA
# ---------------------------------------------------------------------------
def _interno(nome="", fantasia="") -> bool:
    """(12/10) CNPJ do proprio grupo (FRW, BAP AUTOPARTS): nao conta para o
    resultado. A MESMA regra de meta_nucleo.e_cliente_interno - aqui sem
    importar nada pesado (quem so le o cache nao tem openpyxl)."""
    s = sem_acento(f"{nome or ''} {fantasia or ''}").upper()
    return bool(re.search(r"\bFRW\b", s)) or "BAP AUTOPARTS" in s \
        or "BAP AUTO PARTS" in s \
        or "PMZ DISTRIBUIDORA" in s       # (14/10) 000560, 001287


def _clientes_internos(clientes) -> set:
    """Os codigos dos CNPJs do grupo (FRW, BAP AUTOPARTS) no cadastro."""
    return {cod for cod, c in (clientes or {}).items()
            if _interno(c.get("nome"), c.get("fantasia"))}


def _bloco_tabela(raiz) -> dict:
    try:  # leitura rapida com cache (sem o arquivo: openpyxl)
        from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
    except ImportError:
        from openpyxl import load_workbook  # noqa: PLC0415
    raiz = Path(raiz)
    tabela = pasta_relatorios(raiz) / "TABELA_BAP.xlsx"
    if not tabela.exists():
        raise FileNotFoundError("TABELA_BAP.xlsx não está na RELATORIOS.")
    wb = load_workbook(tabela, read_only=True, data_only=True)
    try:
        itens = _ler_pedidos(wb)
        transferencias = _ler_transferencias(wb)
        status_lojas, protheus_lojas = {}, {}
        clientes = _ler_clientes_tabela(wb, status_lojas, protheus_lojas)
        # (12/10) CLIENTES INTERNOS (FRW, BAP AUTOPARTS): os CNPJs do grupo
        # nao contam para o resultado - saem de todos os farois
        internos = _clientes_internos(clientes)
        itens = [it for it in itens if it["cliente"] not in internos
                 and not _interno(it.get("razao"))]
        condpag, condpag_fin = {}, {}
        if "ftCondicaoPagamentos" in wb.sheetnames:
            it = wb["ftCondicaoPagamentos"].iter_rows(values_only=True)
            next(it, None)
            for r in it:
                if r and r[0]:
                    condpag[texto(r[0]).zfill(3)] = texto(r[2])
                    # (13/10) o % ACRES. FIN. da condicao (a vista -1,71;
                    # 30/60/90 +2,89): o financeiro fora do saldo
                    if len(r) > 8:
                        condpag_fin[texto(r[0]).zfill(3)] = numero(r[8])
        # (13/10) os codigos de aprovacao de venda do Protheus
        autorizacoes = []
        if "ftAutorizacaoVenda" in wb.sheetnames:
            it = wb["ftAutorizacaoVenda"].iter_rows(values_only=True)
            cab = [texto(c).upper() for c in next(it, ()) or ()]

            def _i(*nomes):
                for n_ in nomes:
                    for j, c in enumerate(cab):
                        if n_ in sem_acento(c).upper():
                            return j
                return None
            i_fil, i_ped, i_cli, i_cod = (_i("FILIAL"), _i("PEDIDO"),
                                          _i("CLIENTE"), _i("APROVA"))
            for r in it:
                if not r or i_ped is None or i_cod is None or \
                        r[i_ped] in (None, "") or not texto(r[i_cod]):
                    continue
                autorizacoes.append({
                    "filial": texto(r[i_fil]) if i_fil is not None else "",
                    "pedido": texto(r[i_ped]).split(".")[0],
                    "cliente": texto(r[i_cli]) if i_cli is not None else "",
                    "codigo": texto(r[i_cod])})
        filiais = {}
        if "Filiais" in wb.sheetnames:
            it = wb["Filiais"].iter_rows(values_only=True)
            next(it, None)
            for r in it:
                if r and r[4]:
                    fb = texto(r[4])
                    filiais[fb[1:] if fb.startswith("4") else fb] = texto(r[2])
        estoque, nomes_est = _ler_estoque(wb)
        # o estoque das LOJAS PMZ somado por filial BAP (a mesma conta do
        # ESTOQUE_BAP.xlsx e do Oportunidades), com o custo do CD
        estoque_pmz = []
        try:
            import oportunidade_nucleo as on            # noqa: PLC0415
            for (fb, cod), x in on.ler_estoque_pmz(wb)["juntas"].items():
                if x.get("estoque"):
                    estoque_pmz.append({
                        "filial": fb[1:] if fb.startswith("4") else fb,
                        "cod": cod, "qtd": x["estoque"],
                        "custo": x.get("custo") or 0.0})
        except Exception:                               # noqa: BLE001
            estoque_pmz = []
        fornecedores = {}            # codigo do produto -> "5980 - BAP LUB"
        if "ProdutosBAP" in wb.sheetnames:
            it = wb["ProdutosBAP"].iter_rows(values_only=True)
            cab = [texto(c) for c in next(it, [])]
            if "FORNECEDOR" in cab and "Cód. Produto" in cab:
                i_f, i_c = cab.index("FORNECEDOR"), cab.index("Cód. Produto")
                for r in it:
                    if r and len(r) > max(i_f, i_c) and r[i_c]:
                        fornecedores[texto(r[i_c])] = texto(r[i_f])
    finally:
        wb.close()
    nomes, categorias, crua = {}, {}, {}
    csv = raiz / "CATEGORIAS_PRODUTO.csv"
    if csv.exists():
        try:
            import meta_nucleo as mn                    # noqa: PLC0415
            nomes = mn.nomes_de_produto(csv)
            categorias = mn.ler_categorias_de_produto(csv)
            crua = mn.ler_categoria_crua(csv)
        except Exception:                               # noqa: BLE001
            pass
    for k, v in nomes_est.items():
        nomes.setdefault(k, v)
    # a CATEGORIA BAP de cada produto (linha leve, pesada, moto, pneu,
    # bateria, lubrificantes) - pelo CSV e pelo fornecedor
    try:
        import meta_nucleo as mn                        # noqa: PLC0415
        cat_bap = {k: mn.categoria_bap(crua.get(k, ""), fornecedores.get(k, ""),
                                       nomes.get(k, ""))
                   for k in set(crua) | set(fornecedores)
                   | {it["cod"] for it in itens}}
    except Exception:                                   # noqa: BLE001
        cat_bap = {}
    # (15/10) A CLASSIFICACAO DO CATALOGO BAP 2026: CATEGORIA, SISTEMA,
    # FAMILIA e LINHA vem do ESTOQUE_BAP.xlsx (a referencia; a Automacao
    # grava as colunas) e, de quem nao esta nele, da BASE_BAP_UNIFICADA v8.
    # Sem nenhum dos dois, a regra antiga convertida (catalogo_bap)
    classe = {}
    try:
        import catalogo_bap as cbp                      # noqa: PLC0415
        catalogo = cbp.Catalogo(raiz)
        for k in set(cat_bap) | set(nomes) | {it["cod"] for it in itens}:
            classe[k] = catalogo.de(k, cat_bap.get(k, ""), nomes.get(k, ""))
    except Exception:                                   # noqa: BLE001
        classe = {}
    if classe:
        cat_bap = {k: v["CATEGORIA"] for k, v in classe.items()}
        familias = {k: v["FAMILIA"] for k, v in classe.items()}
    else:
        try:
            import familia_nucleo as fam                # noqa: PLC0415
            familias = {k: fam.familia_de(v) for k, v in nomes.items()}
        except Exception:                               # noqa: BLE001
            familias = {}
    return {"classe": classe,
            "sistemas": {k: v["SISTEMA"] for k, v in classe.items()},
            "linhas": {k: v["LINHA"] for k, v in classe.items()},
            "itens": itens, "clientes": clientes, "condpag": condpag,
            "filiais": filiais, "estoque": estoque, "nomes": nomes,
            "estoque_pmz": estoque_pmz, "status_lojas": status_lojas,
            # (07/10) o cadastro do Protheus loja a loja, com o A1_VEND: a
            # BASE PROTHEUS dos farois e as Divergencias Maxima x Protheus
            "protheus_lojas": protheus_lojas,
            "categorias": categorias, "familias": familias,
            "categorias_bap": cat_bap, "internos": sorted(internos),
            "condpag_fin": condpag_fin, "autorizacoes": autorizacoes,
            "transferencias": transferencias, "fornecedores": fornecedores}


def _ler_pedidos(wb) -> list:
    ws = wb["ftPedidos"]
    it = ws.iter_rows(values_only=True)
    cab = [texto(c) for c in next(it)]

    def i(n):
        return cab.index(n) if n in cab else None
    ix = {k: i(k) for k in (
        "D2_FILIAL", "D2_CLIENTE", "C5_VEND1", "D2_EMISSAO", "C5_CONDPAG",
        "D2_DOC", "D2_COD", "D2_PEDIDO", "D2_SERIE", "PRECO_TABELA",
        "PRECO_VENDA", "PORCENTAGEM_DESCONTO", "D2_QUANT", "TIPO", "C5_XHORA",
        "DATA_PEDIDO", "PEDIDO_MAXIMA", "DT_PEDIDO", "DATA_NF", "DATA_DEV",
        "NUM_PEDIDO", "NUM_NF", "VALOR TOTAL", "ESTOQUE_PRODUTO", "% ATENDIDO",
        "RAZÃO_SOCIAL", "STATUS VENDA", "QTD_ATENDIDA", "ESTOQUE_DISPONIVEL",
        "MEN_NOTA", "DEMANDA_ANTERIOR", "ACRES_FIN")}

    def g(r, k):
        j = ix.get(k)
        return r[j] if j is not None and j < len(r) else None
    saida = []
    for r in it:
        tipo = texto(g(r, "TIPO")).upper()
        if tipo not in ("VND", "VEA", "EXC", "DEV"):
            continue
        filial = texto(g(r, "D2_FILIAL"))
        if tipo == "VND":
            pedido = texto(g(r, "D2_PEDIDO")) or texto(g(r, "NUM_PEDIDO"))
            nf = texto(g(r, "D2_DOC"))
            dt_ped = data_de(g(r, "DATA_PEDIDO")) or data_de(g(r, "DT_PEDIDO"))
            dt_nf = data_de(g(r, "DATA_NF")) or data_de(g(r, "D2_EMISSAO"))
        elif tipo == "DEV":
            pedido = texto(g(r, "D2_PEDIDO"))
            nf = texto(g(r, "D2_DOC"))
            dt_nf = data_de(g(r, "D2_EMISSAO")) or data_de(g(r, "DATA_NF"))
            dt_ped = dt_nf
        else:                                           # VEA / EXC
            pedido = texto(g(r, "NUM_PEDIDO")) or texto(g(r, "D2_DOC"))
            nf = ""
            dt_ped = data_de(g(r, "DT_PEDIDO")) or data_de(g(r, "D2_EMISSAO"))
            dt_nf = None
        pct_at = g(r, "% ATENDIDO")
        saida.append({
            "tipo": tipo, "filial": filial, "cliente": cod6(g(r, "D2_CLIENTE")),
            "razao": texto(g(r, "RAZÃO_SOCIAL")),
            "vend": texto(g(r, "C5_VEND1")), "pedido": pedido, "nf": nf,
            "serie": texto(g(r, "D2_SERIE")), "dt_pedido": dt_ped,
            "dt_nf": dt_nf, "hora": texto(g(r, "C5_XHORA")),
            "cond": texto(g(r, "C5_CONDPAG")), "cod": texto(g(r, "D2_COD")),
            "qtd": numero(g(r, "D2_QUANT")),
            "qtd_at": numero(g(r, "QTD_ATENDIDA")),
            "pct_at": (numero(pct_at) * 100.0) if pct_at not in (None, "")
            else None,
            "valor": numero(g(r, "VALOR TOTAL")),
            "p_tab": numero(g(r, "PRECO_TABELA")),
            "p_venda": numero(g(r, "PRECO_VENDA")),
            "desc": numero(g(r, "PORCENTAGEM_DESCONTO")),
            "est_disp": numero(g(r, "ESTOQUE_DISPONIVEL")),
            "est_prod": numero(g(r, "ESTOQUE_PRODUTO")),
            "dem_ant": numero(g(r, "DEMANDA_ANTERIOR")),
            "acres": numero(g(r, "ACRES_FIN")),     # % da condicao (-1,71)
            "maxima": texto(g(r, "PEDIDO_MAXIMA")),
            "status": texto(g(r, "STATUS VENDA")).upper(),
            "obs": texto(g(r, "MEN_NOTA")),
        })
    return saida


def status_protheus_de(status, msblql) -> str:
    """ATIVO/INATIVO do cliente no Protheus. A coluna STATUS do Relatorio
    Clientes do BAP Tools (OUT/2026) manda; sem ela, o A1_MSBLQL antigo
    ("1" = bloqueado = INATIVO, "2" = ATIVO). Sem nenhum: ""."""
    st = sem_acento(texto(status)).upper()
    if st in ("ATIVO", "INATIVO"):
        return st
    b = texto(msblql)
    return "INATIVO" if b == "1" else ("ATIVO" if b == "2" else "")


def _ler_clientes_tabela(wb, status_lojas=None, lojas=None) -> dict:
    """status_lojas (dict), se vier, recebe {(cod6, loja2): ATIVO/INATIVO}
    de TODAS as lojas - o cadastro abaixo guarda uma loja por codigo.
    lojas (dict), se vier, recebe {(cod6, loja2): {vend (A1_VEND com 6
    digitos), nome, fantasia, cidade, uf, status, filial}} - linha apagada
    (D_E_L_E_T_ = *) fica de fora."""
    if "dClientesBap" not in wb.sheetnames:
        return {}
    it = wb["dClientesBap"].iter_rows(values_only=True)
    cab = [texto(c) for c in next(it)]
    pega = {k: (cab.index(k) if k in cab else None) for k in (
        "Limite", "Saldo Disponivel", "Valores em aberto", "Valor  em atraso",
        "Dias em atraso", "A1_COD", "A1_LOJA", "A1_NOME", "A1_NREDUZ",
        "A1_MUN", "A1_EST", "A1_VEND", "A1_DTCAD", "A1_MSBLQL", "A1_BAIRRO",
        "A1_DDD", "A1_TEL", "STATUS", "A1_FILIAL", "D_E_L_E_T_",
        "A1_TABELA", "A1_COND")}
    saida = {}
    for r in it:
        def g(k):
            j = pega[k]
            return r[j] if j is not None and j < len(r) else None
        cod = cod6(g("A1_COD"))
        if not cod:
            continue
        st = status_protheus_de(g("STATUS"), g("A1_MSBLQL"))
        if status_lojas is not None:
            loja = re.sub(r"\D", "", texto(g("A1_LOJA"))).zfill(2)
            status_lojas[(cod, loja)] = st
        if lojas is not None and texto(g("D_E_L_E_T_")) != "*":
            v = texto(g("A1_VEND"))
            lojas[(cod, re.sub(r"\D", "", texto(g("A1_LOJA"))).zfill(2))] = {
                "vend": v.zfill(6) if v.isdigit() else v,
                "nome": texto(g("A1_NOME")), "fantasia": texto(g("A1_NREDUZ")),
                "cidade": texto(g("A1_MUN")).upper(),
                "uf": texto(g("A1_EST")).upper(), "status": st,
                "filial": texto(g("A1_FILIAL")),
                # (19/10) o PRAZO cadastrado (A1_COND) e o limite da loja
                "cond": texto(g("A1_COND")), "limite": numero(g("Limite"))}
        reg = {"nome": texto(g("A1_NOME")), "fantasia": texto(g("A1_NREDUZ")),
               "cidade": texto(g("A1_MUN")).upper(),
               "uf": texto(g("A1_EST")).upper(),
               "bairro": texto(g("A1_BAIRRO")).upper(),
               "limite": numero(g("Limite")),
               "saldo": numero(g("Saldo Disponivel")),
               "aberto": numero(g("Valores em aberto")),
               "atraso_valor": numero(g("Valor  em atraso")),
               "dias_atraso": numero(g("Dias em atraso")),
               "vend": texto(g("A1_VEND")), "dtcad": data_de(g("A1_DTCAD")),
               "bloqueado": st == "INATIVO", "status_protheus": st,
               "fone": " ".join(x for x in (texto(g("A1_DDD")),
                                            texto(g("A1_TEL"))) if x),
               # (15/10) a TABELA DE PRECO do cliente (AM1 = capital,
               # AM2 = interior) - o Farol de Preco filtra por ela
               "tabela_preco": texto(g("A1_TABELA")).upper(),
               # (19/10) o PRAZO cadastrado do cliente (A1_COND) e a loja
               "cond": texto(g("A1_COND")),
               "loja": re.sub(r"\D", "", texto(g("A1_LOJA"))).zfill(2)}
        atual = saida.get(cod)
        # o codigo tem varias lojas: fica a de maior limite
        if atual is None or reg["limite"] > atual["limite"]:
            saida[cod] = reg
    return saida


def _ler_transferencias(wb) -> list:
    """As linhas TRF do ftPedidos: a entrada do item numa filial BAP (FRW),
    transferido da PMZ. {filial, cod, qtd, data, valor}."""
    ws = wb["ftPedidos"]
    it = ws.iter_rows(values_only=True)
    cab = [texto(c) for c in next(it)]
    ix = {k: (cab.index(k) if k in cab else None) for k in (
        "TIPO", "D2_FILIAL", "D2_COD", "D2_QUANT", "DATA_NF", "D2_EMISSAO",
        "VALOR TOTAL", "D2_DOC")}

    def g(r, k):
        j = ix[k]
        return r[j] if j is not None and j < len(r) else None
    saida = []
    for r in it:
        if texto(g(r, "TIPO")).upper() != "TRF":
            continue
        saida.append({"filial": texto(g(r, "D2_FILIAL")),
                      "cod": texto(g(r, "D2_COD")),
                      "qtd": numero(g(r, "D2_QUANT")),
                      "data": data_de(g(r, "DATA_NF")) or
                      data_de(g(r, "D2_EMISSAO")),
                      "valor": numero(g(r, "VALOR TOTAL")),
                      "nf": texto(g(r, "D2_DOC"))})
    return saida


def _ler_estoque(wb):
    """ftEstoqueBap: o estoque das filiais BAP no Protheus."""
    if "ftEstoqueBap" not in wb.sheetnames:
        return [], {}
    it = wb["ftEstoqueBap"].iter_rows(values_only=True)
    cab = [texto(c) for c in next(it)]
    ix = {k: (cab.index(k) if k in cab else None) for k in (
        "B2_FILIAL_ORIGINAL", "B2_COD", "B1_DESC", "B2_QATU", "B2_RESERVA",
        "B2_QPEDVEN", "B2_CM1", "B2_VATU1", "B2_LOCAL")}
    saida, nomes = [], {}
    for r in it:
        def g(k):
            j = ix[k]
            return r[j] if j is not None and j < len(r) else None
        fil, cod = texto(g("B2_FILIAL_ORIGINAL")), texto(g("B2_COD"))
        if not fil or not cod:
            continue
        nomes[cod] = texto(g("B1_DESC"))
        saida.append({"filial": fil, "cod": cod, "desc": texto(g("B1_DESC")),
                      "qatu": numero(g("B2_QATU")),
                      "reserva": numero(g("B2_RESERVA")),
                      "pedven": numero(g("B2_QPEDVEN")),
                      "custo": numero(g("B2_CM1")),
                      "valor": numero(g("B2_VATU1"))})
    return saida, nomes


# ---------------------------------------------------------------------------
# bloco BASE (BASE_CLIENTE + carteira pelo Planner + resumo gerencial)
# ---------------------------------------------------------------------------
def _bloco_base(raiz) -> dict:
    import planner_nucleo as nu                         # noqa: PLC0415
    raiz = Path(raiz)
    base = pasta_relatorios(raiz) / "BASE_CLIENTE.xlsx"
    if not base.exists():
        raise FileNotFoundError("BASE_CLIENTE.xlsx não está na RELATORIOS.")
    cfg = nu.carregar_config(_cfg_planner(raiz))
    clientes = nu.ler_base_cliente(base)
    nu.aplicar_parametros(cfg, clientes)
    nu.migrar_areas_antigas(cfg, clientes)
    nu.sincronizar_areas(cfg, clientes)
    pessoas = {texto(p.get("cod_protheus")): {
        "nome": texto(p.get("nome")), "cargo": texto(p.get("cargo")),
        "chefe": texto(p.get("responde_a")), "ativo": bool(p.get("ativo", True)),
        "provisorio": bool(p.get("provisorio"))}
        for p in cfg.get("pessoas", []) if p.get("cod_protheus")}
    zonas = {z.get("id"): z for z in cfg.get("zonas", [])}
    saida = []
    for c in clientes:
        zid = nu.zona_do_cliente(cfg, c)
        z = zonas.get(zid) or {}
        vend = texto(nu.vendedor_do_cliente(cfg, c))
        pv = pessoas.get(vend, {})
        sup = pessoas.get(pv.get("chefe", ""), {})
        saida.append({
            "cod": cod6(c.get("COD_CLIENTE")), "loja": texto(c.get("LOJA")),
            "nome": texto(c.get("NOME_CLIENTE")),
            "fantasia": texto(c.get("NOME_FANTASIA")),
            "uf": texto(c.get("UF")).upper(),
            "cidade": texto(c.get("CIDADE")).upper(),
            "bairro": texto(c.get("BAIRRO")).upper(),
            "endereco": texto(c.get("ENDERECO")),
            "numero": texto(c.get("NUMERO")),
            # (14/10) o ponto do cliente (para o .json da base de clientes)
            "lat": c.get("LATITUDE"), "lon": c.get("LONGITUDE"),
            # CONTATO (TELEFONE): o nome do contato e o telefone da base
            "contato": nu.contato_do_cliente(c),
            "segmento": texto(c.get("SEGMENTO")) or "(SEM SEGMENTO)",
            "status": texto(c.get("STATUS_CLIENTE")),
            "chave": texto(c.get("CHAVE_CLIENTE")),
            # INATIVO so o inativado a mao no Planner (aba Base cliente)
            "inativo": nu.cliente_inativo(cfg, c) or _interno(
                c.get("NOME_CLIENTE"), c.get("NOME_FANTASIA")),
            "interno": _interno(c.get("NOME_CLIENTE"),
                                c.get("NOME_FANTASIA")),
            "curva": texto(c.get("CURVA_RECEITA")),
            "limite": numero(c.get("LIMITE_APROVADO")),
            "limite_disp": numero(c.get("LIMITE_DISPONIVEL")),
            "atraso": numero(c.get("VALOR_EM_ATRASO")),
            "receita_6m": numero(c.get("RECEITA_6M")),
            # (21/10) a receita da janela da curva (3M): COMPRADOR no Planner
            "receita_periodo": numero(c.get("RECEITA_PERIODO")),
            "media_6m": numero(c.get("MEDIA_MENSAL_6M")),
            "dias_sem_compra": c.get("DIAS_SEM_COMPRA"),
            "ultima_compra": data_de(c.get("ULTIMA_COMPRA")),
            "zona": texto(z.get("codigo")) or texto(zid),
            "zona_nome": texto(z.get("nome")),
            "vend": vend, "vend_nome": pv.get("nome", "") or
            ("(SEM VENDEDOR)" if not vend else vend),
            "supervisor": sup.get("nome", "") or "(SEM SUPERVISOR)",
        })
    try:
        resumo = nu.indicadores(cfg, clientes)
        resumo = {k: v for k, v in resumo.items()
                  if k in ("mes", "du", "zona", "vendedor", "supervisor",
                           "gerente", "cidade", "uf", "segmento",
                           "segmento_vendedor", "total")}
        def limpar(d):
            saida = {a: b for a, b in d.items() if not a.startswith("_")}
            # quem atende (para filtrar cidade/zona por vendedor e supervisor)
            saida["vendedores_lista"] = sorted(
                f"{c} - {pessoas.get(c, {}).get('nome', c)}"
                for c in (d.get("_vendedores_cadeira") or ()))
            saida["supervisores_lista"] = sorted(
                s for s in (d.get("_supervisores") or ()) if s)
            return saida
        for k, v in list(resumo.items()):
            if isinstance(v, list):
                resumo[k] = [limpar(d) for d in v]
            elif isinstance(v, dict):
                resumo[k] = limpar(v)
    except Exception as erro:                           # noqa: BLE001
        resumo = {"erro": str(erro)}
    # A ROTA DO MES, visita a visita (a mesma do PLANNER e do resumo): o
    # Farol Roteirizacao mostra por cliente, com e sem repeticao
    visitas = []
    try:
        for r in nu.rota_do_mes(cfg, clientes):
            cv = texto(r.get("COD_VENDEDOR"))
            d = r.get("DATA")
            visitas.append({
                "data": d, "dia": texto(r.get("DIA_DA_SEMANA")),
                "semana": texto(r.get("SEMANA")),
                "ordem": r.get("ORDEM_DE_VISITA") or 0,
                "visita": r.get("VISITA_NO_MES") or 1,
                "de": r.get("VISITAS_DO_CLIENTE") or 1,
                "cod": cod6(r.get("COD_CLIENTE")), "loja": texto(r.get("LOJA")),
                # o que o arquivo do Protheus precisa, como sai da rota
                "cod_cliente": r.get("COD_CLIENTE"), "loja_cru": r.get("LOJA"),
                "cod_vend": cv, "chave": texto(r.get("CHAVE_CLIENTE")),
                "nome": texto(r.get("NOME_CLIENTE")),
                "fantasia": texto(r.get("NOME_FANTASIA")),
                "uf": texto(r.get("UF")).upper(),
                "cidade": texto(r.get("CIDADE")).upper(),
                "bairro": texto(r.get("BAIRRO")).upper(),
                "zona": texto(r.get("COD_ZONA")) or texto(r.get("ZONA_ID")),
                "vendedor": f"{cv} - {texto(r.get('VENDEDOR'))}".strip(" -")
                or "(SEM VENDEDOR)",
                "supervisor": texto(r.get("SUPERVISOR")) or "(SEM SUPERVISOR)",
                "segmento": texto(r.get("SEGMENTO")) or "(SEM SEGMENTO)",
                "curva": texto(r.get("CURVA_RECEITA")),
                "limite_disp": numero(r.get("LIMITE_DISPONIVEL")),
                "atraso": numero(r.get("VALOR_EM_ATRASO")),
                # o e-mail da rota da semana (06/10)
                "endereco": texto(r.get("ENDERECO")),
                "numero": texto(r.get("NUMERO")),
                "contato": nu.contato_do_cliente(r),
                "dias_sem_compra": r.get("DIAS_SEM_COMPRA"),
                # (20/11, T-0010) a VISITA_SEMANAL da rota, como texto: o
                # JSON da rota da Maxima (RN-ROT-001)
                "visita_semanal": texto(r.get("VISITA_SEMANAL")),
            })
    except Exception:                                   # noqa: BLE001
        visitas = []
    # (06/10) quem esta na rota do mes (sabado tambem) e ATIVO no Planner
    na_rota = {v["chave"] for v in visitas}
    for x in saida:
        x["na_rota"] = x["chave"] in na_rota
    # o teto de visitas por dia de cada vendedor (o calendario do Farol
    # pinta de vermelho o dia que passa dele)
    tetos = {}
    try:
        por_vend = defaultdict(dict)
        for c in clientes:
            zid = nu.zona_do_cliente(cfg, c)
            if zid in zonas:
                por_vend[texto(nu.vendedor_do_cliente(cfg, c))][zid] = \
                    zonas[zid]
        for cv, zs in por_vend.items():
            nome = pessoas.get(cv, {}).get("nome", "")
            tetos[f"{cv} - {nome}".strip(" -")] = nu._teto_do_vendedor(
                cfg, list(zs.values()))
    except Exception:                                   # noqa: BLE001
        tetos = {}
    excluidos = 0
    try:
        try:  # leitura rapida com cache (sem o arquivo: openpyxl)
            from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
        except ImportError:
            from openpyxl import load_workbook  # noqa: PLC0415
        wb = load_workbook(base, read_only=True)
        if "EXCLUIDOS" in wb.sheetnames:
            excluidos = max(0, (wb["EXCLUIDOS"].max_row or 1) - 1)
        wb.close()
    except Exception:                                   # noqa: BLE001
        pass
    return {"clientes": saida, "pessoas": pessoas, "resumo": resumo,
            "excluidos": excluidos, "mes": cfg.get("mes", ""),
            "visitas": visitas, "tetos": tetos,
            "feriados": list(cfg.get("feriados") or []),
            "teto_padrao": int((cfg.get("parametros") or {}).get(
                "visitas_por_dia") or 0),
            # a sexta de prospeccao (06/10): o teto da sexta
            "teto_sexta": int((cfg.get("parametros") or {}).get(
                "visitas_sexta", 6) or 0)}


# ---------------------------------------------------------------------------
# bloco POS-VENDA
# ---------------------------------------------------------------------------
def _bloco_posvenda(raiz) -> dict:
    import pos_venda                                    # noqa: PLC0415
    arq = pasta_relatorios(raiz) / "ACOMPANHAMENTO_POS_VENDA.xlsx"
    if not arq.exists():
        return {"existe": False, "entregas": [], "devolucoes": [],
                "garantias": [], "indicadores": {}}
    dados = pos_venda.ler_acompanhamento(arq)
    dados["existe"] = True
    return dados


# ---------------------------------------------------------------------------
# blocos da META (oportunidade, acompanhamento, executivo)
# ---------------------------------------------------------------------------
_MEMO = {}


def _realizado(mn, raiz, par, comp):
    """O realizado do mes - lido uma vez por processo (meta e oportunidade
    usam o mesmo)."""
    raiz = Path(raiz)
    tabela = pasta_relatorios(raiz) / "TABELA_BAP.xlsx"
    base = pasta_relatorios(raiz) / "BASE_CLIENTE.xlsx"
    chave = (_assinatura([tabela, base, raiz / "meta_config.json"]), comp)
    if chave not in _MEMO:
        csv = mn.achar_csv_de_categorias(raiz)
        cats = mn.ler_categorias_de_produto(csv) if csv else {}
        mapa = mn.mapa_de_categorias(tabela, par.get("categoria_por_fornecedor"))
        _MEMO.clear()
        _MEMO[chave] = mn.ler_realizado(
            tabela, comp, mapa, cats,
            segmento_do_cliente=mn.segmentos_da_base(base))
    return _MEMO[chave]


def _cfg_planner(raiz) -> Path:
    """A configuracao do Planner do mes vigente (o Planner e mes a mes)."""
    try:
        import pastas_bap as pb                         # noqa: PLC0415
        return pb.config_vigente(raiz)
    except Exception:                                   # noqa: BLE001
        return Path(raiz) / "planner_config.json"


def _planner_da_meta(raiz, comp=None):
    """(PLANNER, mes da meta): o PLANNER do MES DA META (cada mes tem o
    seu); o mes sem PLANNER usa o mais recente, como sempre foi.
    comp: um mes escolhido no farol (sem ele, o do Gerador de Meta)."""
    import meta_nucleo as mn                            # noqa: PLC0415
    import pastas_bap as pb                             # noqa: PLC0415
    raiz = Path(raiz)
    if comp:
        comp = mn.normalizar_competencia(comp)
    else:
        try:
            par = json.loads((raiz / "meta_config.json").read_text("utf-8"))
            comp = mn.normalizar_competencia(par.get("competencia"))
        except (OSError, ValueError, AttributeError):
            comp = ""
    return (pb.planner_do_mes(raiz, comp) or pb.planner_mais_recente(raiz),
            comp)


def _contexto_meta(raiz, comp=None):
    import meta_nucleo as mn                            # noqa: PLC0415
    import pastas_bap as pb                             # noqa: PLC0415
    raiz = Path(raiz)
    planner, _comp = _planner_da_meta(raiz, comp)
    if planner is None:
        raise FileNotFoundError("Nenhum PLANNER_BAP na RELATORIOS - o "
                                "Analista gera no BAP Analista.")
    par = mn.carregar_parametros(raiz / "meta_config.json")
    if comp:                          # o mes escolhido no farol manda
        # o que foi escrito a mao fica no mes do arquivo antes de trocar
        mn.sincronizar_ajustes(par)
        par["competencia"] = mn.normalizar_competencia(comp)
    dados = mn.ler_planner(planner)
    comp = mn.competencia_da_meta(par, dados)
    # a EQUIPE do mes da meta: a configuracao do Planner daquele mes manda
    cfg_mes = pb.config_do_mes(raiz, comp) if comp else None
    if cfg_mes is not None and cfg_mes.exists():
        mn.aplicar_equipe_do_mes(dados, cfg_mes)
    resultado = mn.calcular(dados, par)
    return mn, par, planner, resultado


def _bloco_oportunidade(raiz) -> dict:
    mn, par, planner, resultado = _contexto_meta(raiz)
    raiz = Path(raiz)
    tabela = pasta_relatorios(raiz) / "TABELA_BAP.xlsx"
    base = pasta_relatorios(raiz) / "BASE_CLIENTE.xlsx"
    comp = resultado["competencia"]
    csv = mn.achar_csv_de_categorias(raiz)
    nomes = mn.nomes_de_produto(csv) if csv else {}
    realizado = {"clientes": {}, "competencia": comp, "sem_categoria": 0,
                 "com_csv": False, "notas": 0, "linhas": 0}
    ultimo = {}
    if tabela.exists():
        realizado = _realizado(mn, raiz, par, comp)
        ultimo = mn.ultimo_item_comprado(tabela, nomes)
    acomp = mn.acompanhar(resultado, realizado)
    cadastro = mn.ler_cadastro_do_cliente(base)
    linhas = mn.montar_oportunidade(acomp, cadastro, ultimo)
    return {"linhas": linhas, "competencia": comp, "planner": planner.name}


def _bloco_meta(raiz, comp=None) -> dict:
    import pastas_bap as pb                             # noqa: PLC0415
    mn, par, planner, resultado = _contexto_meta(raiz, comp)
    raiz = Path(raiz)
    tabela = pasta_relatorios(raiz) / "TABELA_BAP.xlsx"
    base = pasta_relatorios(raiz) / "BASE_CLIENTE.xlsx"
    comp = resultado["competencia"]
    real = _realizado(mn, raiz, par, comp)
    vis = mn.achar_visitas_do_mes(raiz, comp)
    feitas = mn.ler_visitas_realizadas(vis) if vis else {}
    datas = mn.datas_de_cadastro(base)
    # (15/10) cadastro novo do mes conta como visita (dClientesBap)
    try:
        cad_vis = mn.cadastros_por_vendedor(tabela, comp)
    except Exception:                                   # noqa: BLE001
        cad_vis = {}
    try:
        fer = json.loads((raiz / "planner_config.json").read_text("utf-8")) \
            .get("feriados") or []
    except (OSError, ValueError):
        fer = []
    ac = mn.acompanhar(resultado, real, feitas, datas, feriados=fer, par=par,
                       zonas_supervisor=mn.zonas_dos_supervisores(
                           pb.config_do_planner(raiz, comp)),
                       cad_visita=cad_vis)
    _resumo_dos_clientes(mn, ac, resultado)
    ac.pop("clientes", None)
    return {"acomp": ac, "competencia": comp, "planner": planner.name,
            "tem_visitas": bool(vis), "tem_rv": bool(par.get("rv")),
            "modo": resultado.get("modo", "")}


CAMPOS_CLIENTE_SLIM = ("cod_cliente", "loja", "cod_vendedor", "supervisor",
                       "gerente", "segmento", "uf", "cidade", "bairro",
                       "meta", "meta_rh_vend", "meta_positivacao",
                       "meta_pecas", "positivou", "meta_familia",
                       "meta_categoria", "meta_sistema", "meta_linha",
                       "fora_do_planner")


def _resumo_dos_clientes(mn, ac, resultado) -> None:
    """O que os farois precisam dos clientes (o "clientes" inteiro e
    pesado demais para o cache): a chave de cada recorte do cliente (para
    as colunas de mix), o supervisor/gerente de cada vendedor, a meta por
    familia de cada pessoa e a versao enxuta dos clientes (PDF da
    parcial)."""
    clientes = ac.get("clientes") or []
    # A META RH NOS TERRITORIOS: a meta comercial do cliente x (meta RH /
    # meta comercial) do vendedor dele - a soma de UF, cidade, bairro,
    # segmento e familia fecha com a soma das metas RH dos vendedores
    fator_v = {}
    for l in (resultado.get("recortes") or {}).get("vendedor") or []:
        if l.get("chave"):
            fator_v[l["chave"]] = ((l.get("meta_rh") or 0.0) / l["meta"]
                                   if l.get("meta") else 0.0)
    ac["rh_por"] = {r: defaultdict(float) for r in
                    ("segmento", "uf", "zona", "cidade", "bairro")}
    for c in clientes:
        c["meta_rh_vend"] = (c.get("meta") or 0.0) * fator_v.get(
            c.get("cod_vendedor"), 0.0)
        if c.get("fora_do_planner"):
            continue
        for r in ac["rh_por"]:
            ac["rh_por"][r][mn.chave_da_linha(r, c)] += c["meta_rh_vend"]
    ac["rh_por"] = {r: dict(v) for r, v in ac["rh_por"].items()}
    ac["fator_rh_vendedor"] = fator_v
    ac["mapa_cliente"] = {}
    for c in clientes:
        if c.get("fora_do_planner"):
            continue
        ac["mapa_cliente"].setdefault(c["cod_cliente"], {
            r: mn.chave_da_linha(r, c)
            for r in ("segmento", "uf", "zona", "cidade", "bairro")})
    ac["equipe_vend"] = {}
    for c in resultado.get("clientes") or []:
        cod = mn._cod_vendedor(c.get("cod_vendedor"))       # noqa: SLF001
        if c.get("cod_vendedor") and cod not in ac["equipe_vend"]:
            ac["equipe_vend"][cod] = {
                "vendedor": mn.chave_da_linha("vendedor", c),
                "supervisor": mn.chave_da_linha("supervisor", c),
                "gerente": mn.chave_da_linha("gerente", c)}
    base = resultado.get("clientes") or []
    ac["familia_meta"] = {
        "bap": {f["familia"]: f["meta"]
                for f in resultado.get("familias") or []},
        **{r: mn.metas_de_familia_por(base, r)
           for r in ("gerente", "supervisor", "vendedor")}}
    ac["categoria_meta"] = {
        "bap": {f["familia"]: f["meta"]
                for f in resultado.get("categorias_bap") or []},
        **{r: mn.metas_de_familia_por(base, r, "meta_categoria")
           for r in ("gerente", "supervisor", "vendedor")}}
    # (15/10) SISTEMA e LINHA do Catalogo BAP 2026
    for campo_, chave_ in (("sistemas", "sistema"),
                           ("linhas_catalogo", "linha")):
        ac[f"{chave_}_meta"] = {
            "bap": {f["familia"]: f["meta"]
                    for f in resultado.get(campo_) or []},
            **{r: mn.metas_de_familia_por(base, r, f"meta_{chave_}")
               for r in ("gerente", "supervisor", "vendedor")}}
    ac["clientes_slim"] = [{k: c.get(k) for k in CAMPOS_CLIENTE_SLIM}
                           for c in clientes]


def _bloco_executivo(raiz) -> dict:
    import meta_nucleo as mn                            # noqa: PLC0415
    raiz = Path(raiz)
    par = mn.carregar_parametros(raiz / "meta_config.json")
    exe = par.setdefault("executivo", {})
    if not exe.get("indicadores"):
        exe["indicadores"] = mn.indicadores_padrao()
    ano = int(mn._numero(exe.get("ano")) or date.today().year)  # noqa: SLF001
    exe["ano"] = ano
    exe["meses"] = mn.meses_do_ano(ano)
    csv = mn.achar_csv_de_categorias(raiz)
    analitico = []          # (08/10) a auditoria do Farol Executivo
    real = mn.apurar_executivo(pasta_relatorios(raiz) / "TABELA_BAP.xlsx",
                               exe["meses"],
                               mn.ler_categorias_de_produto(csv) if csv else {},
                               analitico=analitico)
    return {"painel": mn.montar_executivo(par, real), "ano": ano,
            "analitico": analitico}


# ---------------------------------------------------------------------------
# bloco COMERCIAL (custo para o markup + solicitacoes do BAP Tools)
# ---------------------------------------------------------------------------
LEGADO = "Relatorio_Estoques_PMZ_WEB_LEGADO_"
OLHAR_PARA_TRAS = 15          # quantos relatorios antigos procurar
RELATORIO_COMPLETO = 10000    # com custo em tantas filial+produto: chega


def _relatorios_de_estoque(raiz) -> list:
    """Os relatorios de estoque PMZ que o BAP Tools guarda a cada rodada
    (BKP_RELATORIOS_BAPTOOLS), do mais novo para o mais antigo."""
    pasta = Path(raiz) / "SISTEMA BAP" / "BACKUP_RELATORIOS" / "BKP_RELATORIOS_BAPTOOLS"
    try:
        arqs = sorted(pasta.glob(f"{LEGADO}*.xlsx"), reverse=True)
    except OSError:
        return []
    return arqs[:OLHAR_PARA_TRAS]


class _Abas:
    """Junta abas de planilhas diferentes num 'workbook' so (para usar a
    mesma conta de custo do Oportunidades num relatorio antigo)."""

    def __init__(self, abas):
        self.abas = abas

    @property
    def sheetnames(self):
        return list(self.abas)

    def __getitem__(self, nome):
        return self.abas[nome]


def _custos_do_estoque(wb_filiais, ws_estoque) -> dict:
    """{(FILIAL_BAP, produto): (custo, origem)} - a MESMA conta do BAP Tools
    para o PPEDIDO do ESTOQUE_BAP: o do CD da filial; sem ele, a media das
    lojas da filial; por ultimo, a da rede."""
    import oportunidade_nucleo as on                    # noqa: PLC0415
    s = on.ler_estoque_pmz(_Abas({"Filiais": wb_filiais["Filiais"],
                                  "ftEstoquePMZ": ws_estoque}))
    return {k: (v["custo"], v.get("origem_custo") or "CD")
            for k, v in s["juntas"].items() if v.get("custo")}


def _bloco_comercial(raiz) -> dict:
    """
    custos: {(FILIAL_BAP, produto): {custo, origem}} - o P. PEDIDO da
             TABELA_BAP (ftEstoquePMZ), com a conta do BAP Tools (CD, media
             da filial, media da rede). Quando o relatorio do site vem com o
             P. PEDIDO ZERADO (desde 01/10/2026 o fornecedor 980 vem sem
             custo), vale o ULTIMO CUSTO CONHECIDO: o dos relatorios que o
             BAP Tools arquivou nas rodadas anteriores.
    kit: a tabela de sucata da bateria e o markup minimo (Oportunidades).
    solicitacoes: as linhas da SOLICITACAO_BAP (CD e Lojas) de pedido EM
             ABERTO que ainda estao em ABRIR SOLICITACAO e sem ID.
    """
    try:  # leitura rapida com cache (sem o arquivo: openpyxl)
        from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
    except ImportError:
        from openpyxl import load_workbook  # noqa: PLC0415
    rel = pasta_relatorios(raiz)
    custos, quando, info = {}, "", {"recuperados": 0, "de": ""}
    precos, precos_filial = {}, {}
    tabela = rel / "TABELA_BAP.xlsx"
    if tabela.exists():
        quando = f"{datetime.fromtimestamp(tabela.stat().st_mtime):%d/%m/%Y}"
        wb = load_workbook(tabela, read_only=True, data_only=True)
        try:
            # o PRECO DE TABELA de cada produto (ftTabelaPreco): a media
            # das filiais, na tabela de capital e na de interior
            try:
                import oportunidade_nucleo as on        # noqa: PLC0415
                par_p = on.carregar_parametros(raiz / "oportunidade_config.json")
                junta = defaultdict(lambda: ([], []))
                for (_f, prod), x in on.ler_precos(wb, par_p).items():
                    # (07/10) o preco de CADA filial (o mesmo da
                    # ALTERACOES_PRECO); a media fica para a visao "todas"
                    precos_filial[(_f, prod)] = (x.get("capital") or 0.0,
                                                 x.get("interior") or 0.0)
                    if x.get("capital"):
                        junta[prod][0].append(x["capital"])
                    if x.get("interior"):
                        junta[prod][1].append(x["interior"])
                precos = {k: (sum(a) / len(a) if a else 0.0,
                              sum(b) / len(b) if b else 0.0)
                          for k, (a, b) in junta.items()}
            except Exception:                           # noqa: BLE001
                precos, precos_filial = {}, {}
            if "ftEstoquePMZ" in wb.sheetnames and "Filiais" in wb.sheetnames:
                for k, (c, o) in _custos_do_estoque(
                        wb, wb["ftEstoquePMZ"]).items():
                    custos[k] = {"custo": c, "origem": o}
                # o ultimo custo conhecido, dos relatorios ja arquivados
                cache = rel / PASTA_CACHE / "custos_legado.pkl"
                try:
                    with open(cache, "rb") as f:
                        por_arquivo = pickle.load(f)
                except Exception:                       # noqa: BLE001
                    por_arquivo = {}
                novos = {}
                for arq in _relatorios_de_estoque(raiz):
                    chave = f"{arq.name}:{arq.stat().st_size}"
                    if chave in por_arquivo:
                        achados = por_arquivo[chave]
                    else:
                        try:
                            wl = load_workbook(arq, read_only=True,
                                               data_only=True)
                            try:
                                achados = {k: c for k, (c, _o) in
                                           _custos_do_estoque(
                                               wb, wl.worksheets[0]).items()}
                            finally:
                                wl.close()
                        except Exception:               # noqa: BLE001
                            achados = {}
                    novos[chave] = achados
                    data = arq.stem.replace(LEGADO, "")
                    data = f"{data[8:10]}/{data[5:7]}/{data[:4]}" \
                        if len(data) == 10 else data
                    for k, c in achados.items():
                        if k not in custos:
                            custos[k] = {"custo": c,
                                         "origem": f"ÚLTIMO CONHECIDO {data}"}
                            info["recuperados"] += 1
                            info["de"] = info["de"] or data
                    if len(achados) >= RELATORIO_COMPLETO:
                        break           # achou um relatorio com custo cheio
                try:
                    (rel / PASTA_CACHE).mkdir(parents=True, exist_ok=True)
                    tmp = cache.with_suffix(f".{os.getpid()}.tmp")
                    with open(tmp, "wb") as f:
                        pickle.dump(novos, f, protocol=4)
                    os.replace(tmp, cache)
                except OSError:
                    pass
        finally:
            wb.close()
    kit = {}
    try:
        import oportunidade_nucleo as on                # noqa: PLC0415
        par = on.carregar_parametros(raiz / "oportunidade_config.json")
        kit = {"sucata": par["kit"].get("sucata") or on.sucata_padrao(),
               "sucata_ss": par["kit"].get("sucata_ss")
               or on.sucata_ss_padrao(),
               "markup_min_bateria": par["kit"].get("markup_min_bateria")}
    except Exception:                                   # noqa: BLE001
        pass
    solic = {"cd": [], "lojas": []}
    arq = rel / "SOLICITACAO_BAP.xlsx"
    if arq.exists():
        wb = _abrir_mesmo_aberto(arq, load_workbook)
        try:
            # (09/10) o item que foi para a ProdutosExcluir NAQUELA loja (a
            # troca de loja de coleta) sai da lista de "gerar": a linha nova,
            # na outra loja, e que vale
            fora = set()
            if "ProdutosExcluir" in wb.sheetnames:
                it = wb["ProdutosExcluir"].iter_rows(values_only=True)
                cab_x = [texto(c).upper() for c in next(it, [])]
                i_fx = cab_x.index("FILIAL") if "FILIAL" in cab_x else None
                i_cx = next((cab_x.index(c) for c in ("CÓD", "COD")
                             if c in cab_x), None)
                for r in it:
                    if r and i_fx is not None and i_cx is not None and \
                            r[i_fx] not in (None, "") and r[i_cx]:
                        fora.add((texto(r[i_fx]), texto(r[i_cx]).upper()))
            for chave, aba, campo_id in (("cd", "Solicitacao CD", "ID_SEPARACAO"),
                                         ("lojas", "Solicitacao Lojas",
                                          "ID_REVERSA")):
                if aba not in wb.sheetnames:
                    continue
                it = wb[aba].iter_rows(values_only=True)
                cab = [texto(c).upper() for c in next(it, [])]
                for r in it:
                    if not r or not any(v not in (None, "") for v in r):
                        continue
                    d = {c: (r[k] if k < len(r) else None)
                         for k, c in enumerate(cab) if c}
                    st = sem_acento(texto(d.get("STATUS"))).upper()
                    sit = texto(d.get("SITUACAO_PEDIDO")).upper()
                    if sit != "EM ABERTO" or st != "ABRIR SOLICITACAO" or \
                            texto(d.get(campo_id)):
                        continue
                    if (texto(d.get("COLETAR_EM")),
                            texto(d.get("COD_PRODUTO")).upper()) in fora:
                        continue
                    solic[chave].append({
                        "data": data_de(d.get("DATA")),
                        "hora": texto(d.get("HORA")),
                        "uf": texto(d.get("UF")), "cidade": texto(d.get("CIDADE")),
                        "cod": texto(d.get("COD_PRODUTO")),
                        "coletar": texto(d.get("COLETAR_EM")),
                        "destino": texto(d.get("FILIAL_DESTINO")),
                        "qtd": numero(d.get("QUANTIDADE")),
                        "pedidos": texto(d.get("PEDIDOS")),
                        "controle": texto(d.get("CONTROLE_SEP_CD")
                                          or d.get("CONTROLE_SEP_LOJA"))})
        finally:
            wb.close()
    return {"custos": custos, "kit": kit, "solicitacoes": solic,
            "precos": precos, "precos_filial": precos_filial,
            "estoque_de": quando, "recuperados": info}


# ---------------------------------------------------------------------------
# bloco INADIMPLENCIA (titulos em aberto do Protheus)
# ---------------------------------------------------------------------------
BKP_BAPTOOLS = Path("SISTEMA BAP") / "BACKUP_RELATORIOS" / "BKP_RELATORIOS_BAPTOOLS"
_FOTO_TITULOS = re.compile(r"^Relatorio_Titulos_em_Abertos_(\d{4}-\d{2}-\d{2})"
                           r"\.xlsx$", re.IGNORECASE)


def _fotos_de_titulos(raiz) -> list:
    """As fotos diarias dos titulos em aberto que o BAP Tools baixa e a
    automacao guarda em BKP_RELATORIOS_BAPTOOLS (uma por dia de rodada)."""
    pasta = Path(raiz) / BKP_BAPTOOLS
    try:
        return sorted(a for a in pasta.iterdir() if _FOTO_TITULOS.match(a.name))
    except OSError:
        return []


def _ler_titulos(ws) -> list:
    """As linhas do relatorio Titulos em Abertos (ftTitulos ou o arquivo
    baixado): um titulo por linha, com o SALDO em aberto."""
    it = ws.iter_rows(values_only=True)
    cab = [texto(c).upper() for c in next(it, [])]
    ix = {k: (cab.index(k) if k in cab else None) for k in (
        "E1_FILIAL", "E1_CLIENTE", "E1_LOJA", "A1_CGC", "E1_NOMCLI",
        "E1_EMISSAO", "E1_VENCREA", "E1_PREFIXO", "E1_NUM", "E1_PARCELA",
        "E1_TIPO", "E1_VALOR", "E1_SALDO", "F2_COND", "E4_DESCRI")}
    if ix["E1_CLIENTE"] is None or ix["E1_SALDO"] is None:
        return []
    saida = []
    for r in it:
        def g(k):
            j = ix[k]
            return r[j] if j is not None and j < len(r) else None
        cod = cod6(g("E1_CLIENTE"))
        if not cod or not r:
            continue
        saida.append({
            "filial": texto(g("E1_FILIAL")), "cod": cod,
            "loja": texto(g("E1_LOJA")).zfill(2) if texto(g("E1_LOJA"))
            else "", "cgc": texto(g("A1_CGC")), "nome": texto(g("E1_NOMCLI")),
            "emissao": data_de(g("E1_EMISSAO")),
            "venc": data_de(g("E1_VENCREA")),
            "prefixo": texto(g("E1_PREFIXO")), "num": texto(g("E1_NUM")),
            "parcela": texto(g("E1_PARCELA")), "tipo": texto(g("E1_TIPO")),
            "valor": numero(g("E1_VALOR")), "saldo": numero(g("E1_SALDO")),
            "cond": texto(g("F2_COND")), "cond_desc": texto(g("E4_DESCRI"))})
    return saida


def _chave_titulo(t) -> tuple:
    return (t["filial"], t["prefixo"], t["num"], t["parcela"], t["tipo"])


def titulos_sem_internos(titulos) -> list:
    """RN-GER-004 (funcao pura, fonte unica): tira dos titulos em aberto os
    de CNPJ interno (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA), pela regra de
    _interno. Usada nas fotos diarias e nos titulos do farol, para o atraso,
    o recebido e o recuperado baterem com o cartao do farol e com o Diretor.
    O 000040 e o vendedor de teste, nao cliente: nao sai do saldo."""
    return [t for t in titulos or []
            if not _interno(t.get("nome"), t.get("fantasia"))]


def resumo_da_foto(titulos, dia) -> dict:
    """Carteira aberta, a vencer e em atraso (vencimento real antes do dia)."""
    atraso = [t for t in titulos if t["venc"] and t["venc"] < dia
              and t["saldo"] > 0]
    aberto = sum(t["saldo"] for t in titulos if t["saldo"] > 0)
    em_atraso = sum(t["saldo"] for t in atraso)
    return {"data": dia, "aberto": aberto, "atraso": em_atraso,
            "a_vencer": aberto - em_atraso,
            "clientes": len({t["cod"] for t in atraso}),
            "titulos": len(atraso)}


def _bloco_inadimplencia(raiz) -> dict:
    try:  # leitura rapida com cache (sem o arquivo: openpyxl)
        from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
    except ImportError:
        from openpyxl import load_workbook  # noqa: PLC0415
    raiz = Path(raiz)
    tabela = pasta_relatorios(raiz) / "TABELA_BAP.xlsx"
    titulos = []
    if tabela.exists():
        wb = load_workbook(tabela, read_only=True, data_only=True)
        try:
            if "ftTitulos" in wb.sheetnames:
                titulos = _ler_titulos(wb["ftTitulos"])
        finally:
            wb.close()
    # a foto de cada dia e o que saiu dela de um dia para o outro:
    # RECEBIDO = o saldo que baixou (titulo pago, inteiro ou em parte);
    # RECUPERADO = a parte disso que ja estava VENCIDA na foto anterior
    fotos, anterior = [], None
    for arq in _fotos_de_titulos(raiz):
        dia = data_de(_FOTO_TITULOS.match(arq.name).group(1))
        try:
            wb = load_workbook(arq, read_only=True, data_only=True)
            try:
                lidos = titulos_sem_internos(_ler_titulos(wb.worksheets[0]))
            finally:
                wb.close()
        except Exception:                               # noqa: BLE001
            continue
        foto = resumo_da_foto(lidos, dia)
        agora = {_chave_titulo(t): t["saldo"] for t in lidos}
        rec = recup = 0.0
        if anterior is not None:
            dia_ant, ant = anterior
            for k, (saldo, venc) in ant.items():
                baixou = saldo - agora.get(k, 0.0)
                if baixou > 0.005:
                    rec += baixou
                    if venc and venc < dia_ant:
                        recup += baixou
        foto["recebido"] = rec if anterior is not None else None
        foto["recuperado"] = recup if anterior is not None else None
        fotos.append(foto)
        anterior = (dia, {_chave_titulo(t): (t["saldo"], t["venc"])
                          for t in lidos})
    return {"titulos": titulos, "fotos": fotos}


CONSTRUTORES = {"tabela": _bloco_tabela, "base": _bloco_base,
                "posvenda": _bloco_posvenda,
                "oportunidade": _bloco_oportunidade, "meta": _bloco_meta,
                "executivo": _bloco_executivo, "comercial": _bloco_comercial,
                "inadimplencia": _bloco_inadimplencia}


if __name__ == "__main__":
    raiz = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI
    t0 = time.time()
    print(atualizar_tudo(raiz))
    print(f"{time.time() - t0:.1f} s")
