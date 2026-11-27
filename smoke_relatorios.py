# -*- coding: utf-8 -*-
"""
Bateria dos RELATORIOS dos assistentes, do BAP Central novo e do BAP Analista.

    python smoke_relatorios.py

  [1] regras do negocio ..... frete pelas 7 cidades BAP, dias uteis, prazos
  [2] cache dos dados ....... monta, reaproveita e refaz quando a fonte muda
  [3] os 16 relatorios ...... todos montam, toda linha tem o tamanho do
                              cabecalho, cor por linha, nada quebra
  [4] pedidos em aberto ..... a SITUACAO muda com o dia (no prazo, vence
                              hoje, atrasado)
  [5] exportar .............. Excel com uma aba por tabela; PDF (ou .html
                              sem o reportlab)
  [6] segmento .............. todo cliente da base com segmento; o PLANNER
                              antigo pega o segmento da BASE_CLIENTE; os 41
                              clientes que compram voltaram e o Bruno Furtado
                              nao
  [7] Farol ................. Mayara em Vendas e CRM; Maxima com a Mayara;
                              devolucao e garantia com a Estefanie
  [8] janelas ............... relatorio, Central e Analista abrem (precisa
                              de tela; sem tela, pula)

Nao grava nada nas planilhas de verdade: o teste de cache roda numa copia.
"""
from __future__ import annotations

import json
import re
import os
import shutil
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
import tempfile
from collections import defaultdict
import time
from datetime import date, datetime, timedelta
import tempfile as _tf_d
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import bap_dados as bd                                       # noqa: E402
import bap_visual as bv                                      # noqa: E402
import relatorios_nucleo as rn                               # noqa: E402

FALHAS = []


def checar(cond, texto):
    print(f"  {'ok   ' if cond else 'FALHOU'} {texto}")
    if not cond:
        FALHAS.append(texto)


REL = AQUI / "RELATORIOS"
TEM_DADOS = (REL / "TABELA_BAP.xlsx").exists() and \
    (REL / "BASE_CLIENTE.xlsx").exists()

# --------------------------------------------------------------------------
print("\n[1] REGRAS DO NEGOCIO")
checar(not bd.e_frete("Manaus") and not bd.e_frete("BELÉM")
       and not bd.e_frete("santarém") and not bd.e_frete("VARZEA GRANDE")
       and not bd.e_frete("São Luís") and not bd.e_frete("CUIABA")
       and not bd.e_frete("Boa Vista"),
       "as 7 cidades BAP nao sao frete (com e sem acento)")
checar(bd.e_frete("MACAPA") and bd.e_frete("PARINTINS") and bd.e_frete("IMPERATRIZ"),
       "Macapa, Parintins e Imperatriz sao frete")
sex = date(2026, 10, 2)
checar(bd.somar_uteis(sex, 2) == date(2026, 10, 6),
       "pedido na sexta: faturar ate terca (2 dias uteis)")
checar(bd.somar_uteis(date(2026, 10, 9), 2, {date(2026, 10, 12)}) == date(2026, 10, 14),
       "o feriado de 12/10 nao conta")
checar(bd.dias_uteis_entre(date(2026, 9, 29), date(2026, 10, 3)) == 3,
       "de terca 29/09 a sabado 03/10 = 3 dias uteis")
checar((bd.PRAZO_FATURAR, bd.PRAZO_ENTREGAR) == (2, 3),
       "prazo do pedido: 2 dias para faturar, 3 para entregar")
checar(bv.moeda(1234567.8) == "R$ 1.234.568" and bv.pct(12.34) == "12%"
       and bv.br(1234.5, 1) == "1.234,5", "numero no formato brasileiro")

if not TEM_DADOS:
    print("\n(sem TABELA_BAP / BASE_CLIENTE nesta pasta - o resto pula)")
    sys.exit(1 if FALHAS else 0)

# --------------------------------------------------------------------------
print("\n[2] CACHE DOS DADOS (numa copia da pasta)")
tmp = Path(tempfile.mkdtemp(prefix="bap_cache_"))
try:
    (tmp / "RELATORIOS").mkdir()
    for nome in ("TABELA_BAP.xlsx", "BASE_CLIENTE.xlsx"):
        shutil.copy2(REL / nome, tmp / "RELATORIOS" / nome)
    for nome in ("planner_config.json", "CATEGORIAS_PRODUTO.csv"):
        if (AQUI / nome).exists():
            shutil.copy2(AQUI / nome, tmp / nome)
    t = time.time()
    a = bd.carregar(tmp, "tabela")
    t1 = time.time() - t
    t = time.time()
    b = bd.carregar(tmp, "tabela")
    t2 = time.time() - t
    checar(len(a["itens"]) == len(b["itens"]) > 0 and t2 < max(1.5, t1 / 3),
           f"montou em {t1:.1f}s e reaproveitou em {t2:.2f}s")
    checar(bd.do_cache(tmp, "tabela") is not None, "do_cache acha o bloco em dia")
    os.utime(tmp / "RELATORIOS" / "TABELA_BAP.xlsx")
    time.sleep(0.05)
    checar(bd.do_cache(tmp, "tabela") is None,
           "TABELA_BAP mudou: o cache velho nao vale mais")
    tipos = {i["tipo"] for i in a["itens"]}
    checar({"VND", "VEA", "EXC", "DEV"} <= tipos,
           f"le os 4 tipos do ftPedidos ({sorted(tipos)})")
    checar(all(i["cliente"] == i["cliente"].zfill(6) for i in a["itens"]
               if i["cliente"].isdigit()), "codigo de cliente com 6 digitos")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --------------------------------------------------------------------------
print("\n[3] OS RELATORIOS")
# (T-0037) o Fretes mora no LEGADO (sai do menu do PC), mas vai para a web
for rid, area, titulo, _f in rn.CATALOGO + [
        x for x in getattr(rn, "LEGADO", []) if x[0] == "pl_fretes"]:
    try:
        t = time.time()
        r = rn.montar(rid, AQUI)
        ok = True
        for tab in r["tabelas"]:
            n = len(tab["colunas"])
            if any(len(l) < n for l in tab["linhas"]):
                ok = False
            if len(tab["tons"]) != len(tab["linhas"]):
                ok = False
            if tab.get("total") and len(tab["total"]) != n:
                ok = False
            if any(rn.nome_filtro(f) not in [c["nome"] for c in tab["colunas"]]
                   for f in tab.get("filtros", [])):
                ok = False
            if tab.get("kpis_de"):
                tab["kpis_de"](tab["linhas"])
                tab["kpis_de"]([])
        checar(ok and r["kpis"] and r["area"] == area,
               f"{area[:12]:12} | {titulo:24} {len(r['kpis'])} cartoes, "
               f"{len(r['tabelas'])} tabela(s), {time.time() - t:.1f}s")
    except Exception as erro:                            # noqa: BLE001
        checar(False, f"{area[:12]:12} | {titulo}: {type(erro).__name__}: {erro}")

# --------------------------------------------------------------------------
print("\n[4] PEDIDOS EM ABERTO: A SITUACAO COM O DIA")
abertos = [i for i in bd.carregar(AQUI, "tabela")["itens"] if i["tipo"] == "VEA"
           and i["dt_pedido"]]
if abertos:
    d = abertos[0]["dt_pedido"]
    prazo = bd.somar_uteis(d, bd.PRAZO_FATURAR, bd.feriados(AQUI))
    sit = {}
    for dia in (d, prazo, bd.somar_uteis(prazo, 1)):
        r = rn.montar("pv_abertos", AQUI, hoje=dia)
        lin = next(l for l in r["tabelas"][0]["linhas"]
                   if l[1] == abertos[0]["pedido"])
        sit[dia] = lin[0]
    checar(list(sit.values()) == ["NO PRAZO", "VENCE HOJE", "ATRASADO"],
           f"pedido {abertos[0]['pedido']} de {d:%d/%m}: {list(sit.values())}")
else:
    print("  (nenhum pedido em aberto na TABELA_BAP - pulando)")

# --------------------------------------------------------------------------
print("\n[5] EXPORTAR")
from openpyxl import load_workbook                          # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="bap_exp_"))
try:
    r = rn.montar("pl_devolucoes", AQUI)
    x = bv.exportar_excel(r, tmp / "dev.xlsx")
    abas = load_workbook(x, read_only=True).sheetnames
    checar(abas[0] == "RESUMO" and len(abas) == 1 + len(r["tabelas"]),
           f"Excel com o RESUMO e uma aba por tabela ({len(abas)} abas)")
    r["tabelas"][0]["linhas_visiveis"] = r["tabelas"][0]["linhas"][:3]
    x = bv.exportar_excel(r, tmp / "dev2.xlsx")
    ws = load_workbook(x, read_only=True)[abas[1]]
    checar(ws.max_row == 4, "exporta so o que o filtro deixou na tela")
    p = bv.exportar_pdf(r, tmp / "dev.pdf")
    if p.suffix == ".pdf":
        paginas = p.read_bytes().count(b"/Type /Page\n") + \
            p.read_bytes().count(b"/Type /Page ")
        checar(paginas >= 1 + len(r["tabelas"]),
               f"PDF: cada tabela numa pagina ({paginas} paginas, "
               f"{len(r['tabelas'])} tabelas)")
    checar(p.exists() and p.stat().st_size > 2000,
           f"{'PDF' if p.suffix == '.pdf' else 'HTML (sem reportlab)'} gerado "
           f"({p.stat().st_size // 1024} KB)")
    if p.suffix != ".pdf":
        print("        -> instale o reportlab (INSTALAR_PDF.bat) para sair PDF")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --------------------------------------------------------------------------
print("\n[6] SEGMENTO")
base = bd.carregar(AQUI, "base")
sem = [c for c in base["clientes"] if not c["segmento"]
       or c["segmento"].startswith("(")]
checar(not sem, f"todo cliente da base tem segmento ({len(base['clientes'])} "
                f"clientes, {len(sem)} sem)")
import meta_nucleo as mn                                     # noqa: E402
import pastas_bap as pb                                      # noqa: E402
planner = pb.planner_mais_recente(AQUI)
if planner:
    d = mn.ler_planner(planner)
    semp = [c for c in d["clientes"] if c["segmento"] == mn.SEM_SEGMENTO]
    checar(len(semp) <= len(d["clientes"]) * 0.01,
           f"PLANNER: {len(d['clientes']) - len(semp)} de {len(d['clientes'])} "
           f"clientes com segmento")
op = bd.carregar(AQUI, "oportunidade")["linhas"]
checar(sum(1 for l in op if l.get("segmento") == mn.SEM_SEGMENTO)
       <= len(op) * 0.01, "Oportunidades: os clientes vem com segmento")
cods = {c["cod"] for c in base["clientes"]}
nomes = {c["nome"].upper() for c in base["clientes"]}
checar(not any("BRUNO FURTADO" in n for n in nomes),
       "Bruno Furtado continua fora da base")
volta = {"005981", "010909", "010889", "010491", "000236"}
checar(volta <= cods, "os clientes que compram e estavam excluidos voltaram "
                      "(amostra de 5)")

# --------------------------------------------------------------------------
print("\n[7] FAROL DDR")
import farol_ddr as fd                                       # noqa: E402
eq = {e[0]: e for e in fd.EQUIPE_INICIAL}
checar(eq["Mayara Santos"][2] == "Vendas e CRM", "Mayara: Vendas e CRM")
ma = [r for r in fd.ROTINA_INICIAL if r[1] == "Mayara Santos"]
ju = [r for r in fd.ROTINA_INICIAL if r[1] == "Juliana Almeida"]
es = [r for r in fd.ROTINA_INICIAL if r[1] == fd.NOVA]
checar(any("Máxima" in r[3] for r in ma) and not any("Integração diária do "
       "Máxima" in r[3] for r in ju), "a integração do Máxima foi para a Mayara")
checar(any("Devolu" in r[3] for r in es) and any("Garantia" in r[3] for r in es)
       and not any("Garantia" in r[3] for r in ma),
       "devolução e garantia com a Estefanie")
checar(not any("Oportunidades ›" in (r[6] or "") or "Gerador de Meta ›" in
               (r[6] or "") for r in ju + ma + es),
       "assistentes apontam para o BAP Central, não para os cadastros")
quando_ok = all(fd.dias_da_atividade(r[5], fd.dias_uteis(2026, 11, set()))
                is not None for r in fd.ROTINA_INICIAL)
checar(quando_ok, "toda atividade tem um QUANDO que o Farol entende")

# --------------------------------------------------------------------------
print("\n[8] JANELAS")
try:
    import tkinter as tk
    tk.Tk().destroy()
    tem_tela = True
except Exception:                                            # noqa: BLE001
    tem_tela = False
if not tem_tela:
    print("  (sem tela - pulando)")
else:
    import bap_relatorios as br                              # noqa: E402
    j = br.Relatorio("pv_abertos")
    t = time.time()
    while j.rel is None and time.time() - t < 60:
        j.update()
        time.sleep(0.05)
    checar(bool(j.rel) and len(j.vistas) == len(j.rel["tabelas"]),
           "a janela do relatorio monta as abas")
    v = j.vistas[0]
    if v.filtros:
        i, (var, _multi, _nome) = next(iter(v.filtros.items()))
        valores = sorted({bv.formatar(l[i], "texto") for l in v.t["linhas"]})
        var.set(valores[0])
        v.aplicar()
        checar(len(v.visiveis()) <= len(v.t["linhas"]) and all(
            bv.formatar(l[i], "texto") == valores[0] for l in v.visiveis()),
            "o filtro so muda o que aparece")
        kp = j.kpis_atuais()[0]["valor"]
        checar(kp == bv.br(len(v.visiveis())),
               f"o cartao de cima segue o filtro ({kp} pedido(s) na tela)")
    _dc = j.vistas[0].tab.ao_duplo_clique
    checar(_dc is None or getattr(_dc, "__name__", "") == "ver_pedido",
           "relatorio sem edicao: duplo clique nao edita (so abre o pedido)")
    j.destroy()
    # (10/10) UMA linha de filtros em cima: os gerais (filial, categoria,
    # familia, produto...) valem para todas as abas; embaixo so o da aba
    j = br.Relatorio("pl_giro")
    t = time.time()
    while j.rel is None and time.time() - t < 120:
        j.update()
        time.sleep(0.05)
    _nm_abas = [j.abas.tab(i_, "text") for i_ in j.abas.tabs()]
    j.abas.select(_nm_abas.index("Todos os produtos"))
    j.update()
    _vg = j.vista_atual()
    _loc = [n_ for _v, _m, n_ in _vg.filtros.values()]
    j.gerais["CATEGORIA"].set("BATERIAS")
    j._escolheu_geral("CATEGORIA", "BATERIAS")
    _ic = [c_["nome"] for c_ in _vg.t["colunas"]].index("CATEGORIA")
    _vis = _vg.visiveis()
    j.abas.select(_nm_abas.index("Ruptura"))
    j.update()
    _vr = j.vista_atual()
    checar(list(j.gerais) == ["FILIAL", "CATEGORIA", "SISTEMA", "FAMÍLIA",
                              "LINHA", "PRODUTO"]
           and _loc == ["CURVA", "SITUAÇÃO"] and _vis
           and all(l[_ic] == "BATERIAS" for l in _vis)
           and all(l[_ic] == "BATERIAS" for l in _vr.visiveis())
           and "CATEGORIA: BATERIAS" in _vr.texto_do_filtro(),
           "filtros gerais em cima (filial, categoria, família, produto) "
           "valem em todas as abas; embaixo só curva e situação")
    j.destroy()
    # (10/10) o MES da aba (escondido) continua valendo: a tabela de
    # Entregas mostra so o mes escolhido
    j = br.Relatorio("pl_entregas")
    t = time.time()
    while j.rel is None and time.time() - t < 120:
        j.update()
        time.sleep(0.05)
    _nm_e = [j.abas.tab(i_, "text") for i_ in j.abas.tabs()]
    if "Entregas" in _nm_e:
        j.abas.select(_nm_e.index("Entregas"))
        j.update()
        _ve = j.vista_atual()
        _mes_e = rn.mes_escolhido(rn.Contexto(AQUI))
        checar(all(l_[0] == _mes_e for l_ in _ve.visiveis())
               and len(_ve.visiveis()) < len(_ve.t["linhas"]),
               f"Entregas: a tabela mostra só {_mes_e} (o filtro de mês "
               f"escondido segue o de cima)")
    j.destroy()
    checar(br._repetido("VENDEDOR PLANNER", {"VENDEDOR"})
           and not br._repetido("CURVA", {"VENDEDOR"}),
           "filtro que já está em cima (VENDEDOR = VENDEDOR PLANNER) não "
           "repete embaixo")
    import bap_central as bc                                 # noqa: E402
    c = bc.Central()
    c.update()
    checar(len(c.areas) in (4, 5), f"BAP Central com {len(c.areas)} quadrados")
    # (16/10) sem avisos em cima; Painel Executivo junta os executivos;
    # sem Resumo indicadores e sem Todos os relatorios
    checar(not hasattr(c, "status") and "Painel Executivo" in c.rotulos
           and not {"Indicadores Executivos", "Resumo Indicadores",
                    "Todos os relatórios"} & set(c.rotulos),
           "BAP Central: sem avisos nos quadrados; só o Painel Executivo "
           "(sem Resumo, Indicadores Executivos e Todos os relatórios)")
    c.destroy()
    import subprocess                                        # noqa: E402
if tem_tela and "--tudo" not in sys.argv:
    print("  (BAP Analista: so com --tudo - ele abre o Gerador de Meta, que "
          "regrava o meta_config.json)")
elif tem_tela:
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, r'%s');"
                        "import bap_analista as ba; a = ba.Analista();"
                        "a.update(); a.mostrar('planner'); a.update();"
                        "a.mostrar('meta'); a.update();"
                        "a.mostrar('oportunidade'); a.update();"
                        "print('ok', sorted(a.quadros)); a.destroy()" % AQUI],
                       capture_output=True, text=True, timeout=300)
    checar("ok ['meta', 'oportunidade', 'planner', 'resumo']" in r.stdout,
           "BAP Analista abre o Planner, a Meta e o Oportunidades por dentro"
           + ("" if r.returncode == 0 else f" ({r.stderr[-200:]})"))


# --------------------------------------------------------------------------
print("\n[9] FILTRO, RECORTE E EDICAO")
r = rn.montar("pv_faturados", AQUI)
t = r["tabelas"][0]
mes_atual = rn.rotulo_mes(rn.mes_de(date.today()))
do_mes = [l for l in t["linhas"] if l[0] == mes_atual]
checar(t["kpis_de"](do_mes)[0]["valor"] == bv.br(len(do_mes))
       and t["kpis_de"](t["linhas"])[0]["valor"] == bv.br(len(t["linhas"])),
       "Pedidos faturados: o cartao NOTAS segue o filtro do MES")
checar(isinstance(t["filtros"][0], dict) and t["filtros"][0]["padrao"] == mes_atual,
       "o filtro do mes abre no mes atual")
r = rn.montar("vc_meta", AQUI)
_tvend = next(t_ for t_ in r["tabelas"] if t_["titulo"] == "Por vendedor")
nomes = [c["nome"] for c in _tvend["colunas"]]
_tger = next((t_ for t_ in r["tabelas"] if t_["titulo"] == "Por gerente"), None)
_ig29 = {c_["nome"]: i_ for i_, c_ in enumerate(_tger["colunas"])} \
    if _tger else {}
checar(_tger and r["kpis"][0]["valor"] == rn.moeda(
    sum(l[_ig29["FAT. REAL"]] or 0 for l in _tger["linhas"]))
       and r["kpis"][0]["detalhe"].endswith("desafio do mês " + rn.moeda(
           sum(l[_ig29["FAT. META"]] or 0 for l in _tger["linhas"])))
       and [k["rotulo"] for k in r["kpis"]] == [
           "Faturamento · desafio comercial", "Positivação",
           "Visitas", "Peças", "Cad. com compra", "Clientes por cidade"]
       and all([x[0] for x in k["linhas"]][0] == "Ating. do mês"
               and [x[0] for x in k["linhas"]][-2:] == ["Projeção do mês",
                                                        "Nec./dia"]
               for k in r["kpis"][:-1])
       and [x[0] for x in r["kpis"][-1]["linhas"]] == [
           "Ating.", "Cidades", "Por cidade", "Faltam"]
       and [t_["titulo"] for t_ in r["tabelas"]] == [
           "Por gerente", "Por supervisor", "Por vendedor",
           "Top 30 clientes", "Por UF",
           "Por cidade", "Por bairro", "Por segmento", "Por zona",
           "Por categoria", "Por família da peça"]
       and _tvend["kpis_de"](_tvend["linhas"])[0]["valor"] == r["kpis"][0]["valor"],
       "Farol de Metas: os cartões são os do gerente (aba Por gerente)")
# (29/10, Alexandre) TUDO E DESAFIO COMERCIAL: o Farol de Metas sem a meta
# RH e sem a RV (so no Exportar para o RH, no e-mail e na parcial de RV)
checar(nomes[3:7] == ["FAT. META", "FAT. REAL", "FAT. % ATING.",
                      "FAT. NEC./DIA"]
       and [c.get("curto") for c in _tvend["colunas"][3:7]]
       == ["DESAFIO", "REAL", "% DES.", "NEC. DIA"]
       and [g for g, _ in _tvend["grupos"]][1:] == [
           "CLIENTES", "FATURAMENTO", "POSITIVAÇÃO", "VISITA", "CAD. C/ COMPRA",
           "CLI. P/ CIDADE", "PEÇAS", "MIX"]
       and sum(n for _, n in _tvend["grupos"]) == len(nomes)
       and nomes[-6:] == ["% PART", "M3M R$", "% M3M", "NOTAS", "SKUs",
                          "TICKET"]
       and not any("RH" in n or n.startswith("RV ") for n in nomes)
       and nomes[2] == "CLIENTES ATIVOS"
       and ["CAD. META", "CAD. REAL", "CAD. % ATING."] == [
           n_ for n_ in nomes if n_.startswith("CAD.")]
       and [p_["nome"] for p_ in r["parametros"]][2:] == [
           "SEGMENTO", "SUPERVISOR", "VENDEDOR", "UF", "CIDADE", "BAIRRO"]
       and True,
       "Farol de Metas: desafio / real / % de fat., positivacao, visita e "
       "pecas; necessidade/dia no fim; sem meta RH e sem RV (29/10)")
checar("SUPERVISOR" in [rn.nome_filtro(f) for f in _tvend["filtros"]],
       "Meta e RV: filtro de supervisor na aba do vendedor")
r = rn.montar("vc_base", AQUI)
cli = r["tabelas"][-1]
top = dict(cli["recortes"])["Top 30 (maior faturamento 6M)"]
checar(top["top"] == 30 and len(cli["recortes"]) >= 7
       and "CURVA" in [rn.nome_filtro(f) for f in cli["filtros"]],
       "Base: recortes de churn, limite, adimplentes, top 30 e filtro de curva")
adimpl = dict(cli["recortes"])["Só adimplentes"]
_i_atr = [c["nome"] for c in cli["colunas"]].index("EM ATRASO")
checar(all(not (l[_i_atr] or 0) for l in cli["linhas"] if adimpl(l)),
       "recorte so adimplentes nao traz quem esta em atraso")
r = rn.montar("vc_planner", AQUI)
cid = next(x for x in r["tabelas"] if x["titulo"] == "Por cidade")
checar(any(isinstance(f, dict) and f.get("multi") for f in cid["filtros"])
       and any(l[3] for l in cid["linhas"]),
       "Planner: cidade filtra por vendedor/supervisor (quem atende a cidade)")
r = rn.montar("pl_giro", AQUI)
fin = r["tabelas"][0]
checar(fin["titulo"] == "Resumo por filial"
       and "VENDA PERDIDA PREVISTA" in [c["nome"] for c in fin["colunas"]],
       "Giro: resumo financeiro com a venda perdida por dia")
import pos_venda as pvm                                      # noqa: E402
acomp = REL / "ACOMPANHAMENTO_POS_VENDA.xlsx"
if acomp.exists():
    tmp = Path(tempfile.mkdtemp(prefix="bap_ed_"))
    try:
        copia = tmp / acomp.name
        shutil.copy2(acomp, copia)
        ent = pvm.ler_acompanhamento(copia)["entregas"]
        if ent:
            k = ent[0]["chave"]
            pvm.gravar_edicoes(copia, pvm.ABA_ENT, {k: {
                "etapa": "ENTREGUE", "entregue_em": "03/10/2026",
                "canhoto": "SIM"}})
            e2 = pvm.ler_acompanhamento(copia)["entregas"][0]
            checar(e2["etapa"] == "ENTREGUE" and e2["canhoto"] == "SIM"
                   and e2["entregue_em"] == date(2026, 10, 3),
                   "editar e salvar: grava etapa, data e canhoto no acompanhamento")
            try:
                pvm.gravar_edicoes(copia, pvm.ABA_ENT, {k: {"cliente": "X"}})
                checar(False, "coluna do sistema nao pode ser editada")
            except ValueError:
                checar(True, "coluna do sistema (cliente, NF...) nao se edita")
            # (09/10) diario de edicoes: maquina com copia velha nao apaga
            # o que a assistente editou
            velho = tmp / "velho.xlsx"
            shutil.copy2(acomp, velho)
            dona = pvm.MAQUINA_DO_POS_VENDA
            try:
                pvm.MAQUINA_DO_POS_VENDA = ""            # esta grava
                shutil.copy2(acomp, copia)
                pvm.gravar_edicoes(copia, pvm.ABA_ENT, {k: {
                    "etapa": "ENTREGUE", "entregue_em": "03/10/2026",
                    "observacao": "OK"}})
                shutil.copy2(velho, copia)               # a versao velha volta
                e3 = pvm.ler_acompanhamento(copia)["entregas"][0]
                wb_x = load_workbook(copia)
                n_vol = pvm.aplicar_diario(wb_x, pvm.pasta_do_diario(copia))
                wb_x.save(copia)
                e4 = pvm.ler_acompanhamento(copia)["entregas"][0]
                checar(e3["etapa"] == "ENTREGUE" and e3["observacao"] == "OK"
                       and n_vol >= 2 and e4["etapa"] == "ENTREGUE"
                       and e4["entregue_em"] == date(2026, 10, 3),
                       "pós-venda: arquivo trocado por versão velha - o farol "
                       "mostra e a gravação devolve o que foi editado")
                pvm.MAQUINA_DO_POS_VENDA = "OUTRA-MAQUINA"
                antes_m = copia.stat().st_mtime_ns
                pvm.gravar_edicoes(copia, pvm.ABA_ENT, {k: {
                    "observacao": "SO NO DIARIO"}})
                e5 = pvm.ler_acompanhamento(copia)["entregas"][0]
                checar(copia.stat().st_mtime_ns == antes_m
                       and e5["observacao"] == "SO NO DIARIO",
                       "pós-venda: máquina que não é a dona só escreve no "
                       "diário (não troca o Excel) e o farol já mostra")
            finally:
                pvm.MAQUINA_DO_POS_VENDA = dona
            # (30/10, Alexandre) DT. PREVISTA ajustada na tela: coluna nova
            # PREVISTA AJUSTADA no fim (depois do FRETE REAL), manda na
            # previsao e na situacao; vazio volta a calculada
            try:
                pvm.MAQUINA_DO_POS_VENDA = ""
                shutil.copy2(acomp, copia)
                calc30 = pvm.ler_acompanhamento(copia)["entregas"][0][
                    "prevista"]
                pvm.gravar_edicoes(copia, pvm.ABA_ENT, {k: {
                    "prevista_manual": "20/12/2026", "entregue_em": "",
                    "etapa": "EM TRÂNSITO"}})
                wb30 = load_workbook(copia)
                ws30 = wb30[pvm.ABA_ENT]
                cab30 = [ws30.cell(pvm.LINHA_CABECALHO, i_).value
                         for i_ in range(1, len(pvm.COLUNAS_ENTREGA) + 2)]
                e30 = pvm.ler_acompanhamento(
                    copia, hoje=date(2026, 12, 10))["entregas"][0]
                pvm.gravar_edicoes(copia, pvm.ABA_ENT, {k: {
                    "prevista_manual": ""}})
                e30b = pvm.ler_acompanhamento(
                    copia, hoje=date(2026, 12, 10))["entregas"][0]
                from types import SimpleNamespace as _NS30
                _c30 = _NS30(tabela={"itens": [
                    {"tipo": "VND", "nf": "000585", "filial": "SL",
                     "dt_pedido": date(2026, 10, 15), "pedido": "1"}]},
                    fer=set(), hoje=date(2026, 10, 30))
                _pv30 = {"entregas": [
                    {"data_nf": date(2026, 10, 16), "filial": "SL",
                     "nf": "585", "prevista": date(2026, 10, 21),
                     "etapa": "EM TRÂNSITO",
                     "prevista_manual": date(2026, 11, 5)},
                    {"data_nf": date(2026, 10, 16), "filial": "SL",
                     "nf": "585", "prevista": date(2026, 10, 21),
                     "etapa": "EM TRÂNSITO"}]}
                rn._prever_pelo_pedido(_c30, _pv30)
                _a30, _b30 = _pv30["entregas"]
                checar(cab30[len(pvm.COLUNAS_ENTREGA) - 1] ==
                       "PREVISTA AJUSTADA"
                       and cab30[len(pvm.COLUNAS_ENTREGA) - 2] ==
                       "FRETE REAL R$" and cab30[-1] in (None, "")
                       and e30["prevista"] == date(2026, 12, 20)
                       and e30["situacao"] == "NO PRAZO"
                       and e30["prevista_nf"] == calc30
                       and e30b["prevista"] == calc30
                       and not e30b["prevista_manual"]
                       and e30b["situacao"] == "ATRASADA"
                       and _a30["prevista"] == date(2026, 11, 5)
                       and _a30["situacao"] == "NO PRAZO"
                       and _b30["prevista"] == date(2026, 10, 20)
                       and _b30["situacao"] == "ATRASADA",
                       "Entregas: DT. PREVISTA ajustada na tela (coluna "
                       "PREVISTA AJUSTADA no fim; manda na previsão e na "
                       "situação; vazio volta à calculada pelo pedido)")
            finally:
                pvm.MAQUINA_DO_POS_VENDA = dona
        r = rn.montar("pl_entregas", AQUI)
        ed = r["tabelas"][0]["edicao"]
        _cp30 = {c_["campo"]: c_ for c_ in ed["campos"]}
        _nm30 = [c_["nome"] for c_ in r["tabelas"][0]["colunas"]]
        checar("prevista_manual" in _cp30 and _cp30["prevista_manual"]["data"]
               and _cp30["prevista_manual"]["col"] ==
               _nm30.index("DT. PREVISTA")
               and [c_["campo"] for c_ in ed["campos"]].index(
                   "prevista_manual") < [c_["campo"] for c_ in ed["campos"]
                                         ].index("entregue_em")
               and len(_cp30["prevista_manual"]["opcoes"]) == 61,
               "Entregas: Editar com a DT. PREVISTA (lista de hoje + 45 "
               "dias e 15 para trás), antes da DT. REAL")
        # (30/10, Alexandre) SITUACAO = PENDENTE / CONCLUIDA / CANCELADA;
        # ETAPA = AGUARDANDO COLETA, EM TRANSITO, CANCELADA, ENTREGUE; o
        # prazo na coluna PRAZO (oculta, com filtro)
        _t31 = r["tabelas"][0]
        _ix31 = {c_["nome"]: i_ for i_, c_ in enumerate(_t31["colunas"])}
        _l31 = list(next(l_ for l_ in _t31["linhas"]
                         if l_[_ix31["SITUAÇÃO"]] == "PENDENTE"))
        _l31[_ix31["ETAPA"]] = "ENTREGUE"
        _l31[_ix31["DT. PREVISTA"]] = date(2026, 10, 20)
        _l31[_ix31["DT. REAL"]] = date(2026, 10, 22)
        _t31["edicao"]["ao_mudar"](_l31)
        checar({l_[_ix31["SITUAÇÃO"]] for l_ in _t31["linhas"]}
               <= {"PENDENTE", "CONCLUÍDA", "CANCELADA"}
               and not {l_[_ix31["ETAPA"]] for l_ in _t31["linhas"]}
               & {"FATURADA", "EXPEDIDA"}
               and _t31["colunas"][_ix31["PRAZO"]].get("oculta")
               and "PRAZO" in [rn.nome_filtro(f_) for f_ in _t31["filtros"]]
               and {l_[_ix31["PRAZO"]] for l_ in _t31["linhas"]} <= {
                   "", "NO PRAZO", "ATRASADA", "ENTREGUE COM ATRASO"}
               and _cp30["etapa"]["opcoes"] == [
                   "AGUARDANDO COLETA", "EM TRÂNSITO", "ENTREGUE",
                   "CANCELADA"]
               and pvm.ETAPAS_ENTREGA[0] == "AGUARDANDO COLETA"
               and rn.situacao_da_entrega("EM TRÂNSITO") == "PENDENTE"
               and rn.situacao_da_entrega("ENTREGUE") == "CONCLUÍDA"
               and rn.situacao_da_entrega("CANCELADA") == "CANCELADA"
               and _l31[_ix31["SITUAÇÃO"]] == "CONCLUÍDA"
               and _l31[_ix31["PRAZO"]] == "ENTREGUE COM ATRASO",
               "Entregas: SITUAÇÃO PENDENTE/CONCLUÍDA/CANCELADA, ETAPA "
               "AGUARDANDO COLETA/EM TRÂNSITO/ENTREGUE/CANCELADA (antigas "
               "aparecem como as novas), prazo na coluna PRAZO")
        checar(ed and all(c["opcoes"] or c.get("opcoes_de")
                          for c in ed["campos"] if not c.get("livre")),
               "Entregas: todo campo editavel tem lista de opcoes")
        nomes_e = [c["nome"] for c in r["tabelas"][0]["colunas"]]
        checar(not {"CANHOTO", "EXPEDIDA", "OCORRÊNCIA", "VENDEDOR"} & set(nomes_e)
               and {"DT. PED", "SLA", "VLR NF", "VLR FRETE",
                    "MÊS"} <= set(nomes_e),
               "Entregas: colunas novas (MÊS, DATA PED., SLA, VLR NF/FRETE)")
        checar(any(c.get("livre") and c["campo"] == "responsavel"
                   for c in ed["campos"]),
               "Entregas: RESPONSÁVEL é texto livre (motorista)")
        for rid in ("pl_devolucoes", "pl_fretes"):
            checar(rn.montar(rid, AQUI)["tabelas"][0]["edicao"] is not None,
                   f"{rid}: editavel na tela")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
import transportadoras as trm                                # noqa: E402
_cad = {"pct_padrao": 5.0, "transportadoras": [
    trm.novo("A", pct=8, ufs=["PA"], cidades=["PA|BELEM"]),
    trm.novo("B", ufs=["MA"]), trm.novo("C")]}
checar(trm.opcoes_para(_cad, "PA", "Belém") == ["A", "C"]
       and trm.opcoes_para(_cad, "PA", "CASTANHAL") == ["C"]
       and trm.opcoes_para(_cad, "MA", "CAXIAS") == ["B", "C"],
       "Transportadoras: a lista segue a cidade/UF onde atuam")
checar(trm.pct_de(_cad, "A") == 8 and trm.pct_de(_cad, "B") == 5,
       "Transportadoras: % proprio ou o padrao de 5%")
checar(abs(rn._saldo(100.0, 90.0) - 5.0) < 1e-9
       and abs(rn._saldo(100.0, 80.0) + 5.0) < 1e-9,
       "Saldo: tabela 100 / venda 90 sobra 5; venda 80 passa 5 do teto")
_rs = rn.montar("vc_saldo", AQUI)
checar(_rs["tabelas"][0]["titulo"] == "Pedido a pedido"
       and any(k["rotulo"] == "Saldo" for k in _rs["kpis"]),
       "Farol de Saldo: cartao SALDO e a aba pedido a pedido")
# ---- os farois (04/10): nomes, capa com mes/ano e os 3 graficos
_nomes = {rid: t for rid, _a, t, _f in rn.CATALOGO}
checar(_nomes.get("pv_pedidos") == "Farol de Pedidos"
       and "pv_abertos" not in _nomes and "pl_fretes" not in _nomes
       and _nomes.get("pl_frw") == "Farol de Estoque FRW"
       and dict((x[0], x[1]) for x in rn.CATALOGO)["pl_giro"] == rn.VEN
       and "vc_executivo" not in dict((x[0], x[1]) for x in rn.CATALOGO)
       and rn.POR_ID["vc_executivo"][1] == rn.ANA
       and "an_resumo" not in dict((x[0], x[1]) for x in rn.CATALOGO),
       "Farois: nomes novos, Giro em Vendas e CRM, Executivos no Analista")
_rg = rn.montar("pl_giro", AQUI, params={"ESTOQUE": "FRW + PMZ"})
_tg = next(t_ for t_ in _rg["tabelas"] if t_["titulo"] == "Todos os produtos")
_ng = [c["nome"] for c in _tg["colunas"]]
# (16/10) um EST. so (FRW + PMZ somados), sem as colunas separadas
_ctx_g16 = rn.Contexto(AQUI)
checar("EST." in _ng and not {"EST. FRW", "EST. PMZ"} & set(_ng)
       and not any("EST. FRW" in [c_["nome"] for c_ in t_["colunas"]]
                   for t_ in _rg["tabelas"]),
       "Giro: uma coluna EST. (FRW + PMZ), sem FRW e PMZ separados")
_soma16 = {}
for _e16 in ("FRW", "PMZ"):
    _t16 = next(t_ for t_ in rn.montar("pl_giro", AQUI, params={
        "ESTOQUE": _e16})["tabelas"] if t_["titulo"] == "Todos os produtos")
    _i16 = [c_["nome"] for c_ in _t16["colunas"]].index("EST.")
    for l_ in _t16["linhas"]:
        _soma16[(l_[0], l_[1])] = _soma16.get((l_[0], l_[1]), 0) + l_[_i16]
checar(all(abs(l_[_ng.index("EST.")] - _soma16.get((l_[0], l_[1]), 0))
           < 0.01 for l_ in _tg["linhas"]),
       "Giro: EST. com FRW + PMZ = estoque FRW + estoque PMZ")
_sem_capa = []
for _rid, _a, _t, _f in rn.CATALOGO:
    if not _t.startswith("Farol") or _rid == "vc_executivo":
        continue                  # 06/10: o Executivo e por TRIMESTRE
    _r = rn.montar(_rid, AQUI, params={"MÊS": date.today().month})
    _gs = [g["titulo"] for g in _r["graficos"]]
    if not (_r.get("capa") and len(_gs) >= 3 and "mês a mês" in _gs[0]
            and any(g.startswith("Semana a semana") for g in _gs)
            and any(g.startswith("Dia a dia") for g in _gs)
            and [p_["nome"] for p_ in _r["parametros"]][:2] == ["MÊS", "ANO"]):
        _sem_capa.append(_rid)
checar(not _sem_capa, f"todo farol abre no Resumo gerencial com mes/ano e os "
       f"3 graficos {_sem_capa or ''}")
_rp = rn.montar("pv_pedidos", AQUI, params={"MÊS": 9, "ANO": 2026})
_ci = [c["nome"] for c in _rp["tabelas"][0]["colunas"]]
_sits = {l[_ci.index("SITUAÇÃO")] for l in _rp["tabelas"][0]["linhas"]}
checar(_sits <= set(rn.SITUACOES_PEDIDO) and "FATURADO" in _sits | {"FATURADO"}
       and _rp["tabelas"][0]["filtros"][0]["padrao"] == "SET/26"
       and len(_rp["graficos"][2]["rotulos"]) == 30
       and len(_rp["graficos"][0]["rotulos"]) >= 9,
       "Farol de Pedidos: situacoes, mes escolhido no filtro, dia a dia de SET")
# ---- Farol de Pedidos igual ao BI + Analitico produto + Markup (05/10)
# (23/10, Alexandre) a ordem da tela: FATURAR ATE ao lado da DT. PED, NF
# e DT. NF no fim, sem ENTREGUE EM e sem STATUS
_vi23 = [c["nome"] for c in _rp["tabelas"][0]["colunas"]
         if not c.get("oculta")]
checar(_vi23 == ["DT. PED", "FATURAR ATÉ", "PEDIDO", "PED. MÁX.", "CÓD.",
                 "RAZÃO SOCIAL", "FANTASIA", "UF", "CIDADE", "LIMITE",
                 "DISP.", "ATRASO", "VOL.", "R$ TABELA", "R$ VENDA",
                 "% DESC.", "SLA", "% ATENDIDO", "ANÁLISE CRÉDITO",
                 "COND. PAGTO", "SITUAÇÃO", "FILIAL", "PRAZO", "VENDEDOR",
                 "NF", "DT. NF"]
       and all(l_[_ci.index("SITUAÇÃO")] in rn.SITUACOES_PEDIDO
               for l_ in _rp["tabelas"][0]["linhas"][:50]),
       "Farol de Pedidos: DT. PED e FATURAR ATÉ juntos, NF e DT. NF no fim, "
       "sem ENTREGUE EM e STATUS")
# (08/10) SLA e % ATENDIDO em destaque (selo e barra, largura fixa),
# linhas sem cor (zebra), sem STATUS/RECORTE/BUSCAR, MES pelo de cima
_tp0 = _rp["tabelas"][0]
_cp0 = {c["nome"]: c for c in _tp0["colunas"]}
checar(_cp0["SLA"].get("chip") and _cp0["% ATENDIDO"].get("barra")
       and _cp0["SLA"].get("larg_fixa") and _cp0["% ATENDIDO"].get("larg_fixa")
       and _cp0["R$ TABELA CHEIA"].get("oculta")
       and _tp0.get("zebra") and _tp0.get("enxuta")
       and "STATUS" in (_tp0.get("filtros_fora") or [])
       and _tp0["filtros"][0].get("oculto")
       and _rp.get("kpis_faixa")
       and bv.Tabela._faixa_de(1, _cp0["SLA"]["chip"])[0] == "#E5F3DF"
       and bv.Tabela._faixa_de(9, _cp0["SLA"]["chip"])[0] == "#B3261E"
       and bv.Tabela._faixa_de(100, _cp0["% ATENDIDO"]["barra"]["faixas"]
                               )[0] == "#62BB47",
       "Farol de Pedidos: SLA (selo) e % ATENDIDO (barra) em destaque, "
       "linhas sem cor, filtros enxutos")
_ab = [l for l in _rp["tabelas"][0]["linhas"]
       if l[_ci.index("SITUAÇÃO")] == "EM ABERTO"]
_itens_vea = {}
for _it in rn.Contexto(AQUI).tabela["itens"]:
    if _it["tipo"] == "VEA" and _it["pct_at"] is not None:
        _k = (_it["filial"], _it["pedido"])
        _itens_vea[_k] = max(_itens_vea.get(_k, 0), _it["pct_at"])
checar(all(abs((l[17] or 0) - max(v for (f_, p_), v in _itens_vea.items()
                                  if p_ == l[1])) < 0.01
           for l in _ab if any(p_ == l[1] for _f, p_ in _itens_vea)),
       "% ATENDIDO = MAX(ftPedidos[% ATENDIDO]) do pedido")
_tv = [t["titulo"] for t in _rp["tabelas"]]
# (06/10) Analitico produto, Gerar separacao CD e Gerar reversa de lojas
# na MESMA aba dos Pedidos (tabelas juntas, ligadas pelo pedido)
_jt = {j_["tabela"]["titulo"]: j_ for j_ in
       _rp["tabelas"][0].get("juntas") or []}
_an = _jt["Analítico produto"]["tabela"] if "Analítico produto" in _jt \
    else None
_sep_c = [c["nome"] for c in _jt["Gerar separação CD"]["tabela"]["colunas"]] \
    if "Gerar separação CD" in _jt else []
checar(_an is not None and "Itens faltantes" not in _tv
       and all(l[11] <= l[7] + 1e-6 and abs(l[12] - (l[7] - l[11])) < 1e-6
               for l in _an["linhas"])
       and "Gerar reversa de lojas" in _jt
       and not {"Analítico produto", "Gerar separação CD",
                "Gerar reversa de lojas"} & set(_tv)
       and "FILIAL DEST." in _sep_c and "HORA" not in _sep_c
       and "CONTROLE" not in _sep_c,
       "Pedidos: analítico produto, separação CD e reversa na mesma aba")
_rm = rn.montar("vc_markup", AQUI, params={"MÊS": 9, "ANO": 2026})
checar([t["titulo"] for t in _rm["tabelas"]] ==
       ["Por pedido", "Por UF", "Por cidade", "Por supervisor",
        "Por vendedor", "Por categoria", "Por sistema", "Por família",
        "Por linha", "Por produto", "Todos os produtos"]
       and dict((x[0], x[1]) for x in rn.CATALOGO).get("vc_markup") == rn.ANA,
       "Farol de Markup: as 10 visões + Todos os produtos, no Analista Comercial")
import oportunidade_nucleo as _on                           # noqa: E402
_ctxm = rn.Contexto(AQUI)
_bat = next((i for i in _ctxm.tabela["itens"] if i["tipo"] == "VND"
             and rn._categoria(_ctxm, i["cod"]) == "BATERIA"
             and _on.amperagem_do_produto(_ctxm.produto(i["cod"]))), None)
if _bat:
    _cu, _su, _o = rn._custo_do_item(_ctxm, _bat)
    checar(_cu > 0 and _su == _on.valor_da_sucata(
        _ctxm.produto(_bat["cod"]), _ctxm.comercial["kit"]) and _su > 0,
           "Markup: a bateria soma a sucata ao custo")
_rf = rn.montar("pl_frw", AQUI)
_tf = _rf["tabelas"][0]
checar(all((l[11] == "PEDIR") == (l[10] > 0) and
           (l[11] == "DEVOLVER À PMZ") == (l[10] < 0) for l in _tf["linhas"])
       and [rn.nome_filtro(f) for f in _tf["filtros"]] ==
       ["FILIAL", "CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA", "PRODUTO"],
       "Estoque FRW: necessidade + pedir / - devolver; filtros pedidos")
# (10/10) SLA DE ENTREGA (BAP Analista › Entrega › Parametros): a cidade
# cadastrada vale; sem ela, a filial (local/frete); nada: 3 / 5
import transportadoras as _trs                               # noqa: E402
_sla_t = {"filiais": {"MANAUS": {"local": 1, "frete": 4}},
          "cidades": {"PA|BELEM": 10}}
checar(_trs.sla_de(_sla_t, "AM", "Manaus") == (1, "filial")
       and _trs.sla_de(_sla_t, "AM", "Parintins") == (4, "filial")
       and _trs.sla_de(_sla_t, "PA", "Belém") == (10, "cidade")
       and _trs.sla_de(_sla_t, "PA", "Castanhal") == (None, "padrao")
       and _trs.sla_ou_padrao(_sla_t, "PA", "Castanhal") == 5,
       "SLA de entrega: cidade > filial (local/frete) > padrão 3/5")
_cfg_t = AQUI / _trs.ARQUIVO
_bk_t = _cfg_t.read_bytes() if _cfg_t.exists() else None
try:
    _ctx_t = rn.Contexto(AQUI)
    _ent_t = [e_ for e_ in _ctx_t.posvenda["entregas"] if e_.get("data_nf")]
    if _ent_t:
        e0 = _ent_t[0]
        _trs.salvar_sla({"filiais": {}, "cidades": {_trs.chave_cidade(
            e0["uf"], e0["cidade"]): 9}}, AQUI)
        import pos_venda as _pvs                             # noqa: E402
        _l2 = _pvs.ler_acompanhamento(REL / "ACOMPANHAMENTO_POS_VENDA.xlsx",
                                      hoje=_ctx_t.hoje)["entregas"]
        _e2 = next(x_ for x_ in _l2 if x_.get("chave") == e0.get("chave"))
        checar(_e2["prevista"] == _pvs.somar_dias_uteis(
            _e2["data_nf"], 9, _pvs._feriados_padrao())
               or (_e2["prevista"] - _e2["data_nf"]).days >= 9,
               "SLA da cidade cadastrada muda a DT. PREVISTA da entrega")
finally:
    if _bk_t is None:
        _cfg_t.unlink(missing_ok=True)
    else:
        _cfg_t.write_bytes(_bk_t)
# (22/10, Alexandre) DT. PREVISTA da entrega conta da DATA DO PEDIDO
# (1 dia util depois do pedido = dia 1), com o prazo que o pos-venda deu
class _CtxPrev:
    hoje = date(2026, 10, 22)
    fer = set()
    tabela = {"itens": [{"tipo": "VND", "filial": "01", "nf": "000585",
                         "dt_pedido": date(2026, 10, 15), "pedido": "P1"}]}
_pv_t = {"entregas": [{"filial": "01", "nf": "000585", "etapa": "FATURADA",
                       "data_nf": date(2026, 10, 16),
                       "prevista": date(2026, 10, 23), "entregue_em": None,
                       "situacao": "NO PRAZO", "canhoto": ""},
                      {"filial": "01", "nf": "000999", "etapa": "FATURADA",
                       "data_nf": date(2026, 10, 16),
                       "prevista": date(2026, 10, 23), "entregue_em": None,
                       "situacao": "NO PRAZO", "canhoto": ""}],
         "devolucoes": [], "garantias": []}
rn._prever_pelo_pedido(_CtxPrev(), _pv_t)
_e585, _e999 = _pv_t["entregas"]
rn._prever_pelo_pedido(_CtxPrev(), _pv_t)          # 2a passada nao anda
_CtxPrev.hoje = date(2026, 10, 23)
_pv_t2 = {"entregas": [dict(_e585, prevista=date(2026, 10, 23),
                            prevista_nf=None)], "devolucoes": [],
          "garantias": []}
rn._prever_pelo_pedido(_CtxPrev(), _pv_t2)
checar(_e585["prevista"] == date(2026, 10, 22)
       and _e585["prevista_nf"] == date(2026, 10, 23)
       and _e999["prevista"] == date(2026, 10, 23)
       and _pv_t2["entregas"][0]["situacao"] == "ATRASADA",
       "DT. PREVISTA da entrega conta do PEDIDO (15/10 + 5 d.u. = 22/10); "
       "nota sem pedido fica pela NF; dia 23 sem entrega = ATRASADA")
# (11/10) a aba PRAZOS do acompanhamento segue o SLA do Analista e fica
# protegida (e a Listas tambem)
_tmp_pz = Path(tempfile.mkdtemp(prefix="bap_pz_"))
(_tmp_pz / "RELATORIOS").mkdir()
shutil.copy2(REL / "ACOMPANHAMENTO_POS_VENDA.xlsx", _tmp_pz / "RELATORIOS")
_trs.salvar_sla({"filiais": {"MANAUS": {"local": 2, "frete": 4}},
                 "cidades": {"PA|BELEM": 6}}, _tmp_pz)
import pos_venda as _pvz                                     # noqa: E402
_wbz = load_workbook(_tmp_pz / "RELATORIOS" / "ACOMPANHAMENTO_POS_VENDA.xlsx")
_m1 = _pvz.sincronizar_prazos(_wbz, _tmp_pz)
_m2 = _pvz.sincronizar_prazos(_wbz, _tmp_pz)
_pz = {_wbz["PRAZOS"].cell(i_, 1).value: _wbz["PRAZOS"].cell(i_, 2).value
       for i_ in range(5, _wbz["PRAZOS"].max_row + 1)}
checar(_m1 and not _m2 and _pz.get("PA|BELEM") == 6
       and _pz.get("PADRÃO") == 5
       and _wbz["PRAZOS"].protection.sheet and _wbz["Listas"].protection.sheet,
       "Acompanhamento: aba PRAZOS reescrita pelo SLA do Analista; PRAZOS e "
       "Listas protegidas")
shutil.rmtree(_tmp_pz, ignore_errors=True)
_ne = [c_["nome"] for c_ in rn.montar("pl_entregas", AQUI)["tabelas"][0]
       ["colunas"]]
checar("DT. PREVISTA" in _ne and "DT. REAL" in _ne
       and "PREVISTA" not in _ne and "ENTREGUE" not in _ne,
       "Entregas: colunas DT. PREVISTA e DT. ENTREGA")

# (10/10) Entregas: sem a aba Frete (redundante); embaixo da tabela do mes,
# as PENDENCIAS DOS MESES ANTERIORES; resumo executivo do frete
_re10 = rn.montar("pl_entregas", AQUI)
_te10 = _re10["tabelas"][0]
_bl10 = [b_.get("titulo") or (b_.get("grafico") or {}).get("titulo", "")
         for b_ in (_re10.get("painel") or {}).get("blocos", [])]
checar([t_["titulo"] for t_ in _re10["tabelas"]] == ["Entregas"]
       and (_te10.get("juntas") or [{}])[0].get("titulo")
       == "Pendências dos meses anteriores"
       and _te10["juntas"][0].get("liga") is None
       and any(t_.startswith("Frete por estado") for t_ in _bl10)
       and "Cidades que mais custam frete (R$)" in _bl10
       and any(k_["rotulo"] == "Pendências anteriores" for k_ in _re10["kpis"]),
       "Farol de Entregas: sem aba Frete, pendências dos meses anteriores "
       "embaixo e resumo executivo do frete (estado, cidade, região)")
# (30/10, Alexandre) frete minimo: vale sempre que o % da nota der menos que
# ele; o "aciona o minimo em NF ate" e automatico (minimo / %)
import transportadoras as _tr30  # noqa: E402
_d30 = {"pct_padrao": 5.0, "transportadoras": [
    _tr30.novo("RN", pct=4.5, frete_minimo=150),
    _tr30.novo("VELHA", pct=4.5, frete_minimo=150, minimo_ate=1000)]}
checar(_tr30.minimo_ate_auto(150, 4.5) == 3333.33
       and _tr30.minimo_ate_auto(None, 4.5) is None
       and _tr30.frete_estimado(_d30, "RN", 3000) == 150
       and abs(_tr30.frete_estimado(_d30, "RN", 4000) - 180) < 0.001
       and _tr30.frete_estimado(_d30, "VELHA", 3000) == 150
       and "3.333,33" in _tr30.texto_minimo(_d30["transportadoras"][0]),
       "Frete mínimo: NF 3.000 a 4,5% = R$ 135 < mínimo R$ 150 -> 150; "
       "aciona o mínimo automático (NF até R$ 3.333,33)")
# (30/10, Alexandre) % do frete por cidade na transportadora
_d30c = {"pct_padrao": 5.0, "transportadoras": [_tr30.novo(
    "RN", pct=4.5, frete_minimo=150, cidades=["MA|ACAILANDIA"],
    pct_cidades={"MA|ACAILANDIA": 6.5})]}
checar(abs(_tr30.frete_estimado(_d30c, "RN", 10000, "MA", "Açailândia")
           - 650) < 0.001
       and abs(_tr30.frete_estimado(_d30c, "RN", 10000, "MA", "IMPERATRIZ")
               - 450) < 0.001
       and abs(_tr30.frete_estimado(_d30c, "RN", 10000) - 450) < 0.001
       and _tr30.frete_estimado(_d30c, "RN", 2000, "MA", "ACAILANDIA") == 150
       and abs(rn._frete("RN", 10000, True, _d30c, None, "MA",
                         "ACAILANDIA") - 650) < 0.001,
       "Transportadora: % do frete da cidade (Açailândia 6,5% x 4,5% da "
       "transportadora), com o frete mínimo valendo igual")
# (30/10, Alexandre) Campanhas BAP: sem a aba Resumo geral; PTS RELAMPAGO e
# TOTAL A PAGAR (validos + relampago) nas abas Vendedores e Supervisores;
# letra 8 em todas as tabelas; EXPORTAR CAMPANHA (Excel da premiacao)
_rc30 = rn.montar("vc_champions", AQUI, params={"MÊS": 7, "ANO": 2026})
_tc30 = {t_["titulo"]: t_ for t_ in _rc30.get("tabelas") or []}
_ex30 = (_rc30.get("campanha_export") or {}).get("linhas") or []


def _cols30(t_):
    return {c_["nome"]: i_ for i_, c_ in enumerate(t_.get("colunas") or [])}


_v30 = sum(l_[_cols30(_tc30[t_])["PTS VÁLIDOS"]]
           for t_ in ("Vendedores", "Supervisores", "Aux. Técnico")
           if t_ in _tc30 for l_ in _tc30[t_]["linhas"])
_r30 = sum(l_[13] for l_ in (_tc30.get("Campanha relâmpago") or {})
           .get("linhas", []))
_okp30 = True
_rp30 = 0
for t_ in ("Vendedores", "Supervisores"):
    _i30 = _cols30(_tc30.get(t_) or {})
    for l_ in (_tc30.get(t_) or {}).get("linhas", []):
        _rp30 += l_[_i30["PTS RELÂMPAGO"]]
        _okp30 &= (l_[_i30["TOTAL A PAGAR"]] == l_[_i30["PTS VÁLIDOS"]]
                   + l_[_i30["PTS RELÂMPAGO"]])
_tx30 = Path(tempfile.mkdtemp(prefix="smoke_campanha_")) / "c.xlsx"
try:
    rn.exportar_campanha(_rc30, _tx30)
    _wx30 = load_workbook(_tx30).active
    _okx30 = ([_wx30.cell(2, j_).value for j_ in range(1, 7)]
              == rn.CAB_CAMPANHA and _wx30["D1"].value == "Valor total"
              and str(_wx30["E1"].value).startswith("=SUM(E3:")
              and _wx30.cell(3, 2).value == "60077737000244")
except Exception as _e30:                               # noqa: BLE001
    print("   exportar campanha:", _e30)
    _okx30 = False
checar("Resumo geral" not in _tc30 and _okp30 and 0 < _rp30 <= _r30
       and all(t_.get("letra") == 8 for t_ in _rc30["tabelas"])
       and sum(x_[4] for x_ in _ex30) == _v30 + _r30
       and all(x_[1] == "60077737000244" and x_[4] > 0 for x_ in _ex30)
       and len({x_[3] for x_ in _ex30}) == len(_ex30)
       and any(x_[5] == "CAMPANHA BAP CHAMPIONS - JULHO 2026 + CAMPANHA "
               "RELÂMPAGO - JULHO 2026" for x_ in _ex30)
       and _okx30,
       f"Campanhas BAP: relâmpago nas abas Vendedores/Supervisores "
       f"({_rp30} de {_r30}), TOTAL A PAGAR, letra 8; Exportar campanha "
       f"(válidos {_v30} + relâmpago {_r30}, uma linha por pessoa)")
# (30/10, Alexandre) Farol de Inadimplencia: ENVIAR POR E-MAIL os clientes
# inadimplentes de cada um (vendedor / supervisor / gerente), PDF + e-mail
try:
    import email_inadimplencia as _ei30  # noqa: E402
    _fi30 = rn.montar("pl_inadimplencia", AQUI)
    _pc30 = {t_["titulo"]: t_ for t_ in _fi30["tabelas"]}.get("Por cliente")
    _ic30 = {c_["nome"]: i_ for i_, c_ in enumerate(_pc30["colunas"])}
    _in30 = [l_ for l_ in _pc30["linhas"] if l_[0] == "INADIMPLENTE"]
    _ger30 = {"nome": "GERENTE TESTE", "cargo": "GERENTE", "cod": "1",
              "email": "x@x", "cc": ""}
    _rg30i = _ei30.montar_pessoa(_fi30, _ger30, "30/10/2026")
    _vend30 = next((l_[_ic30["VENDEDOR"]] for l_ in _in30
                    if not str(l_[_ic30["VENDEDOR"]]).startswith("(")), "")
    _pv30 = {"nome": _vend30, "cargo": "VENDEDOR", "cod": "", "email": "x@x",
             "cc": ""}
    _rv30i = _ei30.montar_pessoa(_fi30, _pv30, "30/10/2026")
    _t30i = Path(tempfile.mkdtemp(prefix="smoke_inad_"))
    _it30 = _ei30.preparar(AQUI, [_pv30], pasta=_t30i)
    _cols30i = [c_["nome"] for c_ in _rv30i["tabelas"][0]["colunas"]]
    _ok30i = (_rg30i["_resumo"]["clientes"] == len(_in30)
              and abs(_rg30i["_resumo"]["atraso"]
                      - sum(l_[_ic30["EM ATRASO"]] for l_ in _in30)) < 0.01
              and 0 < _rv30i["_resumo"]["clientes"] < len(_in30)
              and "PEDIDO EM ABERTO" not in _cols30i
              and "VENDEDOR" not in _cols30i
              and len(_it30) == 1 and _it30[0]["anexo"].exists()
              and "inadimplentes" in _it30[0]["html"]
              and _it30[0]["assunto"].startswith("Clientes inadimplentes"))
except Exception as _e30i:                              # noqa: BLE001
    print("   inadimplencia por e-mail:", _e30i)
    _ok30i = False
checar(_ok30i, "Farol de Inadimplência: Enviar por e-mail (o vendedor só "
       "com os clientes dele, o gerente com todos; PDF sem PEDIDO EM "
       "ABERTO)")
# ---- Trade Marketing (expositores) e meta de saldo (04/10)
import expositores as exm                                    # noqa: E402
import saldo_meta as smm                                     # noqa: E402
_areas = {x[0]: x[1] for x in rn.CATALOGO}
checar(_areas.get("tm_expositores") == rn.TRADE
       and _areas.get("vc_saldo") == rn.ANA,
       "Farol de Expositores no Trade Marketing; Farol de Saldo so no Analista")
_re = rn.montar("tm_expositores", AQUI)
_titulos = [t["titulo"] for t in _re["tabelas"]]
checar(_titulos[:3] == ["Expositores", "Por estado", "Por status"]
       and _re["tabelas"][0]["edicao"].get("novo"),
       "Farol de Expositores: farol editavel (com NOVO), por estado e por status")
if exm.caminho(AQUI).exists():
    _tmp = Path(tempfile.mkdtemp(prefix="bap_ex_"))
    try:
        (_tmp / "RELATORIOS").mkdir()
        shutil.copy2(exm.caminho(AQUI), exm.caminho(_tmp))
        _antes = exm.ler(_tmp)
        _k = _antes[0]["chave"]
        exm.gravar_edicoes(_tmp, {_k: {"cliente": "011172 - AUTO PECAS X",
                                       "status": "Entregue",
                                       "data_assinatura": "02/10/2026"},
                                  "NOVO-1": {"cliente": "LOJA NOVA",
                                             "descricao": "Expositor de óleo",
                                             "uf": "PA"}})
        _dep = exm.ler(_tmp)
        _e0 = next(x for x in _dep if x["chave"] == _k)
        _nv = [x for x in _dep if x["cliente"] == "LOJA NOVA"]
        checar(len(_dep) == len(_antes) + 1 and _e0["cod_cliente"] == "011172"
               and _e0["status"] == "Entregue" and _nv
               and str(_e0["data_assinatura"]) == "2026-10-02"
               and _nv[0]["categoria"] == "LUBRIFICANTES"
               and _nv[0]["qtd"] == 1,
               "Expositores: edita codigo/status e acrescenta linha nova")
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)
# ---- TODOS OS MESES e o detalhe do pedido (05/10)
_sem_todos = [x[0] for x in rn.CATALOGO
              if (lambda r_: r_.get("capa") and not any(
                  v[0] == rn.TODOS_MESES for v in r_["parametros"][0]["valores"]))(
                  rn.montar(x[0], AQUI))]
checar(not _sem_todos, "Todo farol tem TODOS OS MESES "
       f"{_sem_todos if _sem_todos else ''}")
_falhou = []
for _rid in ("pv_pedidos", "vc_saldo", "tm_expositores", "farol_pv",
             "pv_indicadores", "pl_entregas"):
    try:
        _r = rn.montar(_rid, AQUI, params={"MÊS": rn.TODOS_MESES})
        if _r.get("capa") and len(_r["graficos"]) < 3:
            _falhou.append(_rid)
    except Exception as _e:                                  # noqa: BLE001
        _falhou.append(f"{_rid}: {_e}")
checar(not _falhou, f"Faróis abrem em TODOS OS MESES {_falhou or ''}")
_rs = rn.montar("vc_saldo", AQUI)
_tp = next(t for t in _rs["tabelas"] if t["titulo"] == "Pedido a pedido")
_d = _rs["detalhe_pedido"](_tp, _tp["linhas"][0]) if _tp["linhas"] else None
checar(_tp["detalhe"] and (_d is None and not _tp["linhas"] or
                           _d and _d["linhas"] and any(
                               c[0] == "Prazo de pagamento"
                               for c in _d["campos"])),
       "Duplo clique no pedido: itens, preços, desconto e prazo de pagamento")
_rp = rn.montar("pv_pedidos", AQUI)
_t0 = _rp["tabelas"][0]
checar(_t0["detalhe"] and all(_rp["detalhe_pedido"](_t0, l)
                              for l in _t0["linhas"][:20]),
       "Farol de Pedidos: todo pedido abre o detalhe")
# ---- zonas do supervisor (04/10): clientes das zonas dele que nao sao da
# equipe dele somam no resultado (menos visita); a equipe nao conta 2 vezes
_mn, _par, _pl, _res = bd._contexto_meta(AQUI)
_real = bd._realizado(_mn, AQUI, _par, _res["competencia"])
_sem = _mn.acompanhar(_res, _real, par=_par, zonas_supervisor={})
_sup0 = {l["chave"]: l for l in _sem["recortes"]["supervisor"]}
_alvo = next((n for n in _sup0 if n.startswith("LAIS")), None)
_den = next((n for n in _sup0 if n.startswith("DENYLSON")), None)
if _alvo and _den:
    _zs = {_alvo.upper(): {"cod": "000006", "zonas": {"Z-PA-01", "Z-PA-02"}},
           _den.upper(): {"cod": "000013", "zonas": {"Z-MA-02"}}}
    _com = _mn.acompanhar(_res, _real, par=_par, zonas_supervisor=_zs)
    _sup1 = {l["chave"]: l for l in _com["recortes"]["supervisor"]}
    _a0, _a1 = _sup0[_alvo], _sup1[_alvo]
    _d0, _d1 = _sup0[_den], _sup1[_den]
    checar(abs(_d1["realizado"] - _d0["realizado"]
               - (_d1.get("real_zonas_proprias") or 0)) < 0.01
           and abs(_d1["meta"] - _d0["meta"]) < 0.01
           and _a1.get("clientes_zonas_proprias") is not None
           and abs(_a1["realizado"] - _a0["realizado"]
                   - _a1["real_zonas_proprias"]) < 0.01
           and abs(_a1["meta"] - _a0["meta"]) < 0.01
           and all(abs(_a1[f"meta_{k}"] - _a0[f"meta_{k}"]) < 0.01
                   for k, _, _ in _mn.CATEGORIAS)
           and _a1["meta_positivacao"] == _a0["meta_positivacao"]
           and (_a1.get("visitas_realizadas") or 0) ==
           (_a0.get("visitas_realizadas") or 0)
           and [round(l["realizado"], 2) for l in _com["recortes"]["gerente"]]
           == [round(l["realizado"], 2) for l in _sem["recortes"]["gerente"]],
           "Supervisor: soma os clientes das zonas dele fora da equipe "
           "(meta = soma dos vendedores; visita e gerente iguais)")
    import planner_nucleo as _pn
    _pc = json.loads((AQUI / "planner_config.json").read_text("utf-8"))
    _zd = _mn.zonas_dos_supervisores(AQUI / "planner_config.json")
    _cz = {z["id"]: z.get("codigo") or z["id"] for z in _pc["zonas"]}
    _sups = [p for p in _pc["pessoas"] if p["cargo"] == "SUPERVISOR"
             and p.get("ativo") is not False
             and _pn.zonas_da_equipe(_pc, p["cod_protheus"])]
    checar(_sups and all(
        {_cz[z] for z in _pn.zonas_da_equipe(_pc, p["cod_protheus"])}
        <= _zd.get(p["nome"].strip().upper(), {}).get("zonas", set())
        for p in _sups),
        "Supervisor: por padrao as zonas dele sao as dos vendedores ativos")
    # a venda de quem NAO e da equipe, nos clientes da carteira da equipe,
    # tambem sobe (04/10, noite: a Lais tinha 9 mil com 47 mil na zona)
    _todos = {_a.upper(): {"cod": "", "zonas": {l.get("cod_zona")
                                               for l in _res["clientes"]
                                               if l.get("supervisor") == _a}}
              for _a in (_alvo, _den)}
    _com2 = _mn.acompanhar(_res, _real, par=_par, zonas_supervisor=_todos)
    _s2 = {l["chave"]: l for l in _com2["recortes"]["supervisor"]}
    checar(all(abs(_s2[_k]["realizado"] - _sup0[_k]["realizado"]
                   - (_s2[_k].get("real_zonas_proprias") or 0)) < 0.01
               and abs(_s2[_k]["meta"] - _sup0[_k]["meta"]) < 0.01
               for _k in (_alvo, _den)),
           "Supervisor: nas zonas dele sobe a venda de quem nao e da equipe")
    # (08/10) A ZONA TEM UM SUPERVISOR SO: a zona extra que ja e da equipe
    # de outro supervisor (ou extra de outro, cadastrada antes) nao vale -
    # e o Planner nao deixa gravar
    import tempfile as _tf_z  # noqa: E402
    _pcz = json.loads((AQUI / "planner_config.json").read_text("utf-8"))
    _sz = [p for p in _pcz["pessoas"] if p["cargo"] == "SUPERVISOR"
           and p.get("ativo") is not False
           and _pn.zonas_da_equipe(_pcz, p["cod_protheus"])]
    if len(_sz) >= 2:
        _sa, _sb = _sz[0], _sz[1]
        _zb = sorted(_pn.zonas_da_equipe(_pcz, _sb["cod_protheus"])
                     - _pn.zonas_da_equipe(_pcz, _sa["cod_protheus"]))
        _sa["zonas_supervisor"] = list(_zb[:2])
        with _tf_z.TemporaryDirectory() as _dz:
            _arq_z = Path(_dz) / "planner_config.json"
            _arq_z.write_text(json.dumps(_pcz), "utf-8")
            _zz = _mn.zonas_dos_supervisores(_arq_z)
        _ia = _zz.get(_sa["nome"].strip().upper(), {})
        _czz = {z["id"]: z.get("codigo") or z["id"] for z in _pcz["zonas"]}
        checar(_zb and not ({_czz[z] for z in _zb[:2]} & _ia.get("extras",
                                                                  set()))
               and set(_ia.get("ignoradas") or []) == {_czz[z]
                                                       for z in _zb[:2]}
               and len(_pn.conflitos_de_zona_supervisor(
                   _pcz, _sa["cod_protheus"], _zb[:2])) == len(_zb[:2])
               and "conflitos_de_zona_supervisor" in (
                   AQUI / "bap_planner.py").read_text("utf-8"),
               "Supervisor: cada zona tem um supervisor só (a extra de outro "
               "não vale e o Planner não grava)")

# ---- (09/10) POSITIVACAO de quem vendeu: o vendedor conta os clientes
# para quem ELE faturou (liquido > 0), igual ao faturamento
_ac_pv = _mn.acompanhar(_res, _real, par=_par, zonas_supervisor={})
_eq_pv = _mn._equipe_por_vendedor(_res["clientes"])  # noqa: SLF001
_esp_pv = {}
for _cc, _c in (_real.get("clientes") or {}).items():
    for _vv, _x in (_c.get("por_vend") or {}).items():
        if (_x.get("liquido") or 0) > 0:
            _k_ = _mn._chaves_do_vendedor(_vv, _eq_pv)["vendedor"]  # noqa
            _esp_pv.setdefault(_k_, set()).add(_cc)
checar(all((l_.get("positivados") or 0) == len(_esp_pv.get(
    _mn._cod_vendedor(l_["chave"]), ())) for l_ in  # noqa: SLF001
    _ac_pv["recortes"]["vendedor"]),
       "Farol de Metas: positivação do vendedor = clientes que ELE faturou "
       "(vendedor da nota)")

# ---- o PLANNER mes a mes (04/10): o mes no nome, o arquivo por mes, a
# equipe do mes na meta
import pastas_bap as _pb                                     # noqa: E402
checar(_pb.mes_do_planner("PLANNER_BAP_2026-09_20261004.xlsx") == "2026-09"
       and _pb.mes_do_planner("PLANNER_BAP_20261003.xlsx") == "2026-10"
       and _pb.config_do_planner(AQUI, "1999-01").name == "planner_config.json"
       and all("_" + m + "_" in (_pb.planner_do_mes(AQUI, m) or Path(
           f"x_{m}_")).name for m in ("2026-08", "2026-09", "2026-10")),
       "Planner mes a mes: o mes do PLANNER pelo nome e a config do mes")
_dados_t = {"clientes": [dict(c) for c in _res["clientes"][:50]]}
import planner_nucleo as _pn2                                # noqa: E402
_cfg_t = _pn2.carregar_config(AQUI / "planner_config.json")
_v = next((p_ for p_ in _cfg_t["pessoas"] if p_["cargo"] == "VENDEDOR"
           and any(_pn2.texto(c.get("cod_vendedor")) == p_["cod_protheus"]
                   for c in _dados_t["clientes"])), None)
if _v:
    _v["responde_a"] = ""                    # no mes, sem supervisor
    _tmp_cfg = Path(tempfile.mkdtemp()) / "planner_config_2026-09.json"
    _pn2.gravar_config(_cfg_t, _tmp_cfg)
    _mn.aplicar_equipe_do_mes(_dados_t, _tmp_cfg)
    checar(all(c["supervisor"] == "(sem supervisor)"
               for c in _dados_t["clientes"]
               if _pn2.texto(c.get("cod_vendedor")) == _v["cod_protheus"]),
           "Meta: a equipe do mes da meta vem do Planner daquele mes")
# ---- metas escritas a mao: visita, positivacao e cadastro (05/10)
import copy as _copy                                         # noqa: E402
_par2 = _copy.deepcopy(_par)
_vend = next(l for l in _res["recortes"]["vendedor"] if l["chave"])
for _campo, _val in (("meta_visita", 321.0), ("meta_positivacao", 77.0),
                     ("meta_cadastro", 31.0)):
    _mn.marcar_ajuste(_par2, "vendedor", _vend["chave"], _val, _campo)
_res2 = _mn.calcular(_mn.ler_planner(_pl), _par2)
_v2 = next(l for l in _res2["recortes"]["vendedor"]
           if l["chave"] == _vend["chave"])
_ac2 = _mn.acompanhar(_res2, _real, par=_par2, zonas_supervisor={})
_va = next(l for l in _ac2["recortes"]["vendedor"]
           if l["chave"] == _vend["chave"])
checar(abs(_v2["meta_visita"] - 321) < 0.01
       and abs(_v2["meta_positivacao"] - 77) < 0.01
       and _v2["meta_cadastro"] == 31.0
       and abs(_va["meta_positivacao"] - 77) < 0.01
       and abs(sum(c["meta_visita"] for c in _res2["clientes"]
                   if c["cod_vendedor"] == _vend["chave"]) - 321) < 0.01,
       "Meta: visita, positivacao e cadastro escritos a mao no vendedor "
       "(clientes e acompanhamento seguem)")

# ---- meta geral do mes (mes sem meta no arquivo) e quem conta (05/10)
_par3 = _copy.deepcopy(_par)
_par3["competencia"] = "2031-01"
_mn.gravar_meta_geral_do_mes(_par3, "2031-01", "1.000.000,00")
_res3 = _mn.calcular(_mn.ler_planner(_pl), _par3)
checar(_res3["modo"] == "geral"
       and abs(sum(c["meta"] for c in _res3["clientes"]) - 1e6) < 1
       and abs(sum(l["meta"] for l in _res3["recortes"]["vendedor"]) - 1e6) < 1
       and abs(sum(l["meta"] for l in _res3["recortes"]["gerente"]) - 1e6) < 1,
       "Meta: mes sem meta no arquivo gera tudo pela META GERAL do mes")
checar(set(_res3["fora_da_meta"]["vendedor"]) == {
    _mn._texto(c["cod_vendedor"]) for c in _res3["clientes"]
    if c.get("vendedor_ativo") is False and _mn._texto(c["cod_vendedor"])},
       "Meta: so a cadeira inativa do Planner fica fora (sem QUEM CONTA)")

# ---- o que foi escrito a mao vale so no mes dele e sobrevive a gravar/abrir
_par4 = _copy.deepcopy(_par)
_par4["competencia"] = "2031-02"
_par4["ajustes"], _par4["ajustes_ind"] = {}, {}
_par4["ajustes_por_mes"], _par4["ajustes_competencia"] = {}, ""
_mn.marcar_ajuste(_par4, "vendedor", _vend["chave"], 12345.0)
_mn.marcar_ajuste(_par4, "vendedor", _vend["chave"], 55.0, "meta_visita")
_mn.gravar_meta_geral_do_mes(_par4, "2031-03", "500.000,00")
_tmp4 = Path(tempfile.mkdtemp()) / "meta_config.json"
_mn.gravar_parametros(_par4, _tmp4)
_par5 = _mn.carregar_parametros(_tmp4)
_ok_a = (_par5["ajustes"].get(f"vendedor|{_vend['chave']}") == 12345.0
         and _par5["ajustes_ind"].get("meta_visita")
         and _mn.meta_geral_do_mes(_par5, "2031-03") == 500000.0)
_par5["competencia"] = "2031-03"
_r5 = _mn.calcular(_mn.ler_planner(_pl), _par5)
_ok_b = (not _par5["ajustes"] and not _par5["ajustes_ind"]
         and abs(sum(l["meta"] for l in _r5["recortes"]["vendedor"])
                 - 500000) < 1)
_par5["competencia"] = "2031-02"
_mn.sincronizar_ajustes(_par5)
_ok_c = _par5["ajustes"].get(f"vendedor|{_vend['chave']}") == 12345.0
checar(_ok_a and _ok_b and _ok_c,
       f"Meta: escrito a mao e META GERAL sobrevivem a gravar/abrir e valem "
       f"so no mes deles ({_ok_a}, {_ok_b}, {_ok_c})")

# ---- Farol Roteirizacao por cliente (com e sem repeticao)
_rv = rn.montar("vc_planner", AQUI)
_tc = next((t_ for t_ in _rv["tabelas"] if t_["titulo"] == "Por cliente"), None)
if _tc:
    _sem = [l for l in _tc["linhas"] if l[0] == rn.ROTA_SEM_REP]
    _com = [l for l in _tc["linhas"] if l[0] == rn.ROTA_COM_REP]
    _icl = [c["nome"] for c in _tc["colunas"]].index("CLIENTE")
    checar(_sem and len({l[_icl] for l in _sem}) == len(_sem)
           and len(_com) == sum(l[[c["nome"] for c in _tc["colunas"]].index(
               "VISITAS NA ROTA")] for l in _sem)
           and "CIDADE" in [rn.nome_filtro(f) for f in _tc["filtros"]],
           f"Farol Roteirização › Por cliente: {len(_sem)} clientes, "
           f"{len(_com)} visitas, filtro por cidade")
else:
    checar(False, "Farol Roteirização › Por cliente: aba não montou")
_tcal = next((t_ for t_ in _rv["tabelas"] if t_["titulo"] == "Calendário"), None)
_pr_todos = _rv["exportar_protheus"]() if _rv.get("exportar_protheus") else []
# (20/11, T-0010, RN-ROT-001, R-20261120-104729 e R-20261120-111303) fora
# do .json: so o CNPJ interno (nome/fantasia) e a conta 000040; o 1o sabado
# (deposito) VAI, com o dtfinal curto. O calendario do Farol nao traz
# inativo (a rota ja o tirou).


def _fora_mx(l_):
    return (mn.e_cliente_interno(l_[11], l_[15])
            or str(l_[4]).split(" - ")[0].strip().zfill(6) == "000040")


_cal_mx = [l_ for l_ in (_tcal["linhas"] if _tcal else []) if l_[0]
           and not _fora_mx(l_)]
_pr_um = (_rv["exportar_protheus"](_tcal, _cal_mx[:5])
          if _tcal else [])
checar(_tcal and _tcal.get("calendario") and len(_cal_mx) == len(_pr_todos)
       and len(_pr_um) == 5 and set(_pr_todos[0]) == set(
           ["codcli", "codusur", "codcompromisso", "dtproxvisita",
            "periodicidade", "sequencia", "diasemana", "numsemana",
            "dtinicio", "dtfinal"])
       # (27/10, validacao da Maxima) periodicidade so com os valores do
       # layout ERP_MXSROTACLI
       and {x_["periodicidade"] for x_ in _pr_todos} <= {
           "1", "7", "14", "15", "21", "28", "30", "35", "42", "45"},
       f"Farol Roteirização › Calendário e Exportar Protheus "
       f"({len(_pr_todos)} visitas; layout ERP_MXSROTACLI, sem hash e "
       f"coordenada, periodicidade aceita)")
# (20/11, T-0010, RN-ROT-001) CNPJ interno (FRW / BAP AUTOPARTS / PMZ
# DISTRIBUIDORA no nome ou na fantasia) tambem nao vai no .json do Farol:
# conferido no calendario INTEIRO (o _cal_mx ja os tirou)
_cal_int = [l_ for l_ in (_tcal["linhas"] if _tcal else []) if l_[0]
            and mn.e_cliente_interno(l_[11], l_[15])]
_int_mx = {l_[10].replace("-", "") for l_ in _cal_int}
checar(not {x_["codcli"][-8:] for x_ in _pr_todos} & {
    c_.split("-")[0].zfill(6) + c_.split("-")[-1].zfill(2)
    for c_ in (l_[10] for l_ in _cal_int)},
       f"Farol Roteirização › Exportar Protheus sem cliente interno "
       f"({len(_int_mx)} visita(s) de interno no calendário)")
# 07/10: BASE PROTHEUS nos farois e Divergencias clientes Planner x Protheus
_dv = rn.montar("an_divergencias", AQUI)
_fc_v = next(t_ for t_ in rn.montar("vc_base", AQUI)["tabelas"]
             if t_["titulo"] == "Por vendedor")
_fr_v = next(t_ for t_ in _rv["tabelas"] if t_["titulo"] == "Por vendedor")
_ctx_dv = rn.Contexto(AQUI)
_lj = _ctx_dv.tabela.get("protheus_lojas") or {}
_dv_t = _dv["tabelas"]
with _tf_d.TemporaryDirectory() as _tmp_d:
    _cor = (_dv["exportar_correcao"](Path(_tmp_d) / "C.xlsx")
            if _dv.get("exportar_correcao") else None)
_dv_js = _dv["exportar_correcao_json"]() if _dv.get(
    "exportar_correcao_json") else []
checar(_fc_v["colunas"][1]["nome"] == "BASE PROTHEUS"
       and _fr_v["colunas"][2]["nome"] == "BASE PROTHEUS"
       and _fc_v["total"][1] == len(_lj)
       and [t_["titulo"] for t_ in _dv_t][:2] == ["Por vendedor",
                                                 "Clientes divergentes"]
       and _cor and _cor[1] == sum(1 for l_ in _dv_t[1]["linhas"]
                                   if l_[10] in rn.SIT_CORRIGIR)
       and all(x_["A1_VEND"] != (_lj.get((x_["A1_COD"], x_["A1_LOJA"]))
                                 or {}).get("vend") for x_ in _dv_js)
       and "an_divergencias" in rn.POR_ID,
       f"BASE PROTHEUS nos farois ({len(_lj)} lojas) e Divergências "
       f"Máxima x Protheus ({len(_dv_t[1]['linhas']) if len(_dv_t) > 1 else 0}"
       f" clientes, {len(_dv_js)} no .json de correção)")
# 07/10: o formato combinado com a Maxima - data EXATA, numsemana 1 (a
# Maxima gera na N-esima DIASEMANA a partir da dtproxvisita: com N = 1 cai
# na propria data). (20/11, T-0010, R-20261120-104729) vigencia 2000 ->
# dtproxvisita + periodicidade - 1 dia: cada linha gera UMA visita
_dias_mx = ["SEGUNDA", "TERCA", "QUARTA", "QUINTA", "SEXTA", "SABADO",
            "DOMINGO"]
checar(_pr_todos and all(
    l_["numsemana"] == 1 and l_["dtinicio"] == "2000-01-01T00:00:00"
    and l_["dtfinal"] == (date.fromisoformat(l_["dtproxvisita"][:10])
                          + timedelta(days=int(l_["periodicidade"]) - 1)
                          ).strftime("%Y-%m-%dT00:00:00")
    and _dias_mx[date.fromisoformat(l_["dtproxvisita"][:10]).weekday()]
    == l_["diasemana"] for l_ in _pr_todos),
       "JSON da rota no formato da Máxima: data exata, numsemana 1, "
       "vigência 2000 a dtproxvisita+periodicidade−1")

# ---- Resumo indicadores
_ri = rn.montar("an_resumo", AQUI)
checar([t["titulo"].split(" · ")[0] for t in _ri["tabelas"]][:2]
       == ["Visão geral", "Pré-venda"]
       and any(l[1] == "Faturamento líquido" for l in _ri["tabelas"][0]["linhas"])
       and len(_ri["tabelas"]) >= 5 and not _ri["avisos"],
       f"Resumo indicadores: visão geral + uma aba por área "
       f"({len(_ri['tabelas'])} tabelas) {_ri['avisos']}")
_ctx = rn.Contexto(AQUI)
_div = smm.dividir(_ctx, "2026-10", {"MA": 3000.0, "PA": 1500.0})
checar(abs(sum(d["meta"] for d in _div) - 4500) < 0.01
       and all(abs(sum(d["peso"] for d in _div if d["uf"] == u) - 100) < 0.01
               for u in ("MA", "PA")),
       "Meta de saldo: a meta da UF se divide inteira pelo peso de venda")
import time as _t                                            # noqa: E402
t0 = _t.time()
mn.ler_planner(pb.planner_mais_recente(AQUI))
checar(_t.time() - t0 < 3, f"Meta: o PLANNER abre do cache ({_t.time() - t0:.1f}s)")

# ---- rota por cidade: o calendario manda nos dias, o resto e automatico
_cfg_r = _pn2.carregar_config(AQUI / "planner_config.json")
_cli_r = _pn2.ler_base_cliente(AQUI / "RELATORIOS" / "BASE_CLIENTE.xlsx")
_pn2.aplicar_parametros(_cfg_r, _cli_r)
_pn2.sincronizar_areas(_cfg_r, _cli_r)
# a mecanica do calendario sozinha (a regra da cidade base, 17/10, tem o
# teste dela no smoke_processos)
_cfg_r["parametros"]["dias_cidade_base"] = 0
# (21/10) estes testes sao da MECANICA da rota (o mes inteiro): o passado
# guardado (recalcular nao reescreve o passado) tem o teste dele no fim
_pn2.REESCREVER_PASSADO[0] = True
_vr = next((p_ for p_ in _pn2.vendedores(_cfg_r)
            if len(_pn2.cidades_do_vendedor(_cfg_r, _cli_r, p_["cod_protheus"])) >= 3), None)
if _vr:
    _cod = _vr["cod_protheus"]
    _cids = _pn2.cidades_do_vendedor(_cfg_r, _cli_r, _cod)
    _d = [d[0].isoformat() for d in _pn2.dias_do_mes(
        _cfg_r["mes"], _cfg_r.get("feriados") or [], False)]
    _cal = {_d[0]: [_cids[0]["chave"]], _d[5]: [_cids[0]["chave"]],
            _d[1]: [_cids[1]["chave"], _cids[2]["chave"]]}
    _pn2.gravar_rota_cidade(_cfg_r, _cod, _cal)
    t0 = _t.time()
    _rot = [r for r in _pn2.gerar_rota(_cfg_r, _cli_r)
            if _pn2.texto(r.get("COD_VENDEDOR")) == _cod]
    _dt_rota = _t.time() - t0
    _por_dia = defaultdict(set)
    for r in _rot:
        _por_dia[r["DATA"] if isinstance(r["DATA"], str) else
                 _pn2.data_de(r["DATA"]).isoformat()].add(
            _pn2.chave_da_cidade(r["UF"], r["CIDADE"]))
    _c0 = {c["CHAVE_CLIENTE"] for c, _z in _pn2.clientes_do_vendedor(_cfg_r, _cli_r, _cod)
           if _pn2.chave_da_cidade(c["UF"], c["CIDADE"]) == _cids[0]["chave"]}
    _vis0 = {r["CHAVE_CLIENTE"] for r in _rot if r["CHAVE_CLIENTE"] in _c0}
    checar(_por_dia.get(_d[0]) == {_cids[0]["chave"]}
           and _por_dia.get(_d[1]) <= {_cids[1]["chave"], _cids[2]["chave"]}
           and _vis0 == _c0,
           f"Rota por cidade: o dia so tem as cidades dele e todo cliente da "
           f"cidade e visitado ({len(_rot)} visitas, {_dt_rota:.1f}s)")
    checar(all(len({r["CHAVE_CLIENTE"] for r in _rot if (r["DATA"] if isinstance(r["DATA"], str) else _pn2.data_de(r["DATA"]).isoformat()) == d})
               == sum(1 for r in _rot if (r["DATA"] if isinstance(r["DATA"], str) else _pn2.data_de(r["DATA"]).isoformat()) == d)
               for d in _por_dia),
           "Rota por cidade: o mesmo cliente nunca duas vezes no mesmo dia")
    _pv = _pn2.previa_rota_cidade(_cfg_r, _cli_r, _cod)
    checar(_pv.get((_d[0], _cids[0]["chave"]), [0])[0] > 0,
           f"Rota por cidade: a previa do dia ({_pv.get((_d[0], _cids[0]['chave']))})")

# ---- Farol Roteirizacao: o .json da base de clientes (as 10 colunas)
import planner_nucleo as _pn14b  # noqa: E402
_bpf = _rv["exportar_base_protheus"]() if _rv.get("exportar_base_protheus") \
    else []
checar(_bpf and list(_bpf[0]) == _pn14b.CAMPOS_BASE_PROTHEUS,
       f"Farol Roteirização › Exportar Protheus › base de clientes "
       f"({len(_bpf)} clientes)")

# ---- giro: visoes por familia e por categoria
_rgv = rn.montar("pl_giro", AQUI)
_tfam = next((t_ for t_ in _rgv["tabelas"] if t_["titulo"] == "Por família"), None)
_tcat = next((t_ for t_ in _rgv["tabelas"] if t_["titulo"] == "Por categoria"), None)
_todos_g = next(t_ for t_ in _rgv["tabelas"] if t_["titulo"] == "Todos os produtos")
checar(_tfam and _tcat and abs(sum(l[7] for l in _tfam["linhas"]
                                    if l[0] == rn.TODAS_FILIAIS)
       - sum(l[[c_["nome"] for c_ in _todos_g["colunas"]].index("EST.")]
             for l in _todos_g["linhas"])) < 1
       and "% NOTAS" in [c["nome"] for c in _tcat["colunas"]],
       "Giro: visões por família e categoria (SKUs, estoque, venda, notas, %)")

# ---- (10/10) Farol de Clientes: CATEGORIA em cima - faturamento 6M e o
# TOP 30 so do produto escolhido (vinha cliente que so comprou pneu)
_rcb = rn.montar("vc_base", AQUI, params={"CATEGORIA": "BATERIAS"})
_tcb = next(t_ for t_ in _rcb["tabelas"] if t_["titulo"] == "Clientes")
_ncb = [c_["nome"] for c_ in _tcb["colunas"]]
_ctx_cb = rn.Contexto(AQUI)
_bat6 = defaultdict(float)
from datetime import timedelta as _td6                        # noqa: E402
_d6 = _ctx_cb.hoje - _td6(days=183)
for _it in _ctx_cb.tabela["itens"]:
    if _it["tipo"] == "VND" and _it["dt_nf"] and _it["dt_nf"] >= _d6 and \
            _ctx_cb.categoria_bap(_it["cod"]) == "BATERIAS":
        _bat6[_it["cliente"]] += _it["valor"]
_top_rec = next(r_ for r_ in _tcb["recortes"] if r_[0].startswith("Top 30"))
_tp = sorted([l for l in _tcb["linhas"]
              if (l[_ncb.index("FAT. 6M")] or 0) > 0],
             key=lambda l: -l[_ncb.index("FAT. 6M")])[:30]
checar(_top_rec[1].get("so_positivo") and _tp and all(
    abs(l[_ncb.index("FAT. 6M")] - _bat6.get(l[0], 0)) < 0.05 for l in _tp)
       and [p_["nome"] for p_ in _rcb["parametros"]][-5:]
       == ["CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA", "PRODUTO"],
       f"Farol de Clientes: categoria em cima - Top 30 só de quem comprou "
       f"BATERIA ({len(_tp)} clientes, FAT. 6M só de bateria)")
_rgc = rn.montar("pl_giro", AQUI)
checar(all("CATEGORIA" in [c_["nome"] for c_ in t_["colunas"]]
           and {"CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA", "PRODUTO"} <= {
               rn.nome_filtro(f_) for f_ in t_["filtros"]}
           for t_ in _rgc["tabelas"] if t_["titulo"] in (
               "Ruptura", "Curva A parada", "Necessidade de compra",
               "Todos os produtos")),
       "Giro: onde tem família tem categoria e produto (coluna e filtro)")

# ---- (09/10) SOLICITACAO BAP: duplo clique no item -> ProdutosExcluir,
# outra loja da cidade sugerida, linha nova e CSV de separacao (numa copia)
try:
    import solicitacao_bap as sbm                            # noqa: E402
    import bap_automation as bam                             # noqa: E402
    _tmp_sb = Path(tempfile.mkdtemp(prefix="bap_sol_"))
    (_tmp_sb / "RELATORIOS").mkdir()
    for _a in ("SOLICITACAO_BAP.xlsx", "TABELA_BAP.xlsx"):
        shutil.copy2(REL / _a, _tmp_sb / "RELATORIOS" / _a)
    _dsb = sbm.ler(_tmp_sb)
    _achou = None
    for _aba in sbm.ABAS_TROCA:
        for _l in (_dsb.get(_aba) or {}).get("linhas", []):
            _it = sbm.item_da_linha(_dsb, _aba, _l)
            _cs = sbm.candidatos(_tmp_sb, _it, _dsb)
            if _cs and _it.get("COLETAR_EM"):
                _achou = (_it, _cs)
                break
        if _achou:
            break
    if not _achou:
        checar(True, "Solicitação BAP: nenhum item com outra loja na cidade "
                     "(nada a trocar nesta base)")
    else:
        _it, _cs = _achou
        _pl_antes = bam.PASTA_LOCAL
        bam.PASTA_LOCAL = _tmp_sb
        try:
            _n_det = len(_dsb[bam.ABA_DETALHE]["linhas"])
            _n_ex = len(_dsb["ProdutosExcluir"]["linhas"])
            _res = sbm.trocar_coleta(_tmp_sb, _it, _cs[0])
        finally:
            bam.PASTA_LOCAL = _pl_antes
        _d2 = sbm.ler(_tmp_sb)
        _ult = _d2["ProdutosExcluir"]["linhas"][-1]
        checar(len(_d2[bam.ABA_DETALHE]["linhas"]) > _n_det
               and len(_d2["ProdutosExcluir"]["linhas"]) == _n_ex + 1
               and str(_ult[0]) == str(_it["COLETAR_EM"])
               and _res["csv"] and all(Path(_res["pasta_csv"], c_).exists()
                                       for c_ in _res["csv"])
               and _cs[0]["filial"] != _it["COLETAR_EM"],
               f"Solicitação BAP: troca de coleta {_it['COLETAR_EM']} -> "
               f"{_cs[0]['filial']} (ProdutosExcluir + linha nova + CSV "
               f"{', '.join(_res['csv'])})")
    shutil.rmtree(_tmp_sb, ignore_errors=True)
except Exception as _e_sb:                                   # noqa: BLE001
    checar(False, f"Solicitação BAP: troca de coleta ({_e_sb})")

# ---- giro: compra 90 dias de venda + 90 de chegada; a sugestao so em
# Necessidade de compra (e Todos); PDF enxuto (uma linha de titulo)
_ocg = {t_["titulo"]: {c_["nome"] for c_ in t_["colunas"] if c_["oculta"]}
        for t_ in _rgv["tabelas"]}
# (16/10) chegada em 45 dias: Necessidade = curva A/B com menos de 45 dias
# de cobertura; venda perdida = (45 - cobertura) x venda R$/dia; o resto
# do farol em unidades (nenhuma coluna de R$ alem da venda perdida)
_tnc = next(t_ for t_ in _rgv["tabelas"]
            if t_["titulo"] == "Necessidade de compra")
_nnc = [c_["nome"] for c_ in _tnc["colunas"]]
_rs_g = [c_["nome"] for t_ in _rgv["tabelas"] if t_["titulo"] in (
    "Ruptura", "Curva A parada", "Necessidade de compra",
    "Todos os produtos") for c_ in t_["colunas"]
    if c_.get("tipo") in ("moeda", "moeda2")]
checar(rn.GIRO_PRAZO_CHEGADA == 45 and rn.GIRO_DIAS_VENDA == 90
       and "SUGESTÃO" in _ocg["Curva A parada"]
       and "SUGESTÃO" in _ocg["Ruptura"]
       and "SUGESTÃO" not in _ocg["Necessidade de compra"]
       and set(_rs_g) == {"VENDA PERDIDA", "VENDA/DIA"}
       and _tnc["total"][0] == "TOTAL" and callable(_tnc.get("total_de"))
       and abs(_tnc["total"][_nnc.index("VENDA PERDIDA")] - sum(
           l_[_nnc.index("VENDA PERDIDA")] or 0 for l_ in _tnc["linhas"]))
       < 0.01
       and all(abs(l_[_nnc.index("DIAS S/ EST.")]
                   * l_[_nnc.index("VENDA/DIA")]
                   - l_[_nnc.index("VENDA PERDIDA")]) < 0.01
               for l_ in _tnc["linhas"])
       and all(l_[_nnc.index("COB (DIAS)")] < 45 for l_ in _tnc["linhas"])
       and all(abs(l_[_nnc.index("DIAS S/ EST.")]
                   - (45 - l_[_nnc.index("COB (DIAS)")])) < 0.01
               for l_ in _tnc["linhas"])
       and {"CATEGORIA", "SISTEMA", "FAMÍLIA"} <= {
           c_["nome"] for c_ in _tnc["colunas"] if not c_["oculta"]}
       and (_todos_g.get("pdf") or {}).get("compacto"),
       "Giro: chegada em 45 dias, Necessidade só abaixo de 45 dias, venda "
       "perdida = dias sem estoque × venda/dia; resto em unidades; "
       "categoria, sistema e família na tela")

# ---- Farol Roteirizacao › Por cliente (06/10): semana antes do dia,
# endereco e nº, STATUS do Planner, ordem data + sequencia no exportar
_rpc = rn.montar("vc_planner", AQUI)
_tpc = next((t_ for t_ in _rpc["tabelas"] if t_["titulo"] == "Por cliente"),
            None)
if _tpc:
    _vpc = [c_["nome"] for c_ in _tpc["colunas"] if not c_.get("oculta")]
    _npc = [c_["nome"] for c_ in _tpc["colunas"]]
    _ord = sorted(_tpc["linhas"][::-1], key=_tpc["ordem_exportar"])
    _i_d, _i_s, _i_v = _npc.index("DATA"), _npc.index("SEQ."), \
        _npc.index("VENDEDOR")
    checar(_vpc.index("SEMANA") < _vpc.index("DIA")
           and {"ENDEREÇO", "Nº", "STATUS"} <= set(_vpc)
           and not {"STATUS PROTHEUS", "SITUAÇÃO PLANNER", "VISITAS NA ROTA",
                    "PREVISTAS", "DATAS DAS VISITAS"} & set(_vpc)
           and all((a_[_i_d] or date.min, str(a_[_i_v]), a_[_i_s] or 0)
                   <= (b_[_i_d] or date.min, str(b_[_i_v]), b_[_i_s] or 0)
                   for a_, b_ in zip(_ord, _ord[1:]))
           and _tpc["protheus"]["i_cliente"] == _npc.index("CLIENTE")
           and _tpc["kpis_de"](_tpc["linhas"]),
           "Farol Roteirização › Por cliente: semana, endereço, STATUS; "
           "exporta por data e sequência")

# ---- Farol de Visita, Dia a dia: META DIA (meta do mes / dias uteis),
# VISITAS e % ATING. (06/10)
_fvd = rn.montar("vc_visitas", AQUI)
_tdd = next((t_ for t_ in _fvd["tabelas"] if t_["titulo"] == "Dia a dia"),
            None)
_ndd = [c_["nome"] for c_ in (_tdd or {}).get("colunas", [])]
checar(_tdd is not None and _ndd[_ndd.index("META") + 1] == "VISIT."
       and _ndd[_ndd.index("META") + 2] == "% META"
       and all(l[_ndd.index("% META")] is None or l[_ndd.index("META")]
               for l in _tdd["linhas"]),
       "Farol de Visita: dia a dia com meta do dia, visitas e % meta")
# (06/10) TOTAL em todas as abas e PEDIDOS ao lado da VENDA
_tvs = {t_["titulo"]: t_ for t_ in _fvd["tabelas"]}
checar(all(t_.get("total") and callable(t_.get("total_de"))
           for k_, t_ in _tvs.items() if k_ in ("Por supervisor",
                                                "Por vendedor", "Dia a dia")
           if t_["linhas"])
       # (22/10, Alexandre) AS COLUNAS DA PARCIAL VISITAS + CAD. C/ COMPRA
       and all([c_["nome"] for c_ in t_["colunas"] if not c_.get("oculta")
                and c_["nome"] in rn.COLUNAS_VISITA_PARCIAL + ["CAD. C/ COMPRA"]]
               == ["META", "VISIT.", "% META", "% CONV.", "% FORA DE ROTA",
                   "CAD.", "CAD. C/ COMPRA", "PROSP.", "INÍCIO",
                   "ÚLT. ATIV.", "JORNADA LÍQ.", "DIAS < JORN. LÍQ.", "INTERV. ALMOÇO",
                   "DIAS ALMOÇO > MÁX.", "TMA", "TMD", "KM", "KM/CLIENTE"]
               and "VENDA" not in [c_["nome"] for c_ in t_["colunas"]]
               and "AGENDADOS" not in [c_["nome"] for c_ in t_["colunas"]]
               for k_, t_ in _tvs.items() if k_ in (
                   "Por supervisor", "Por vendedor", "Dia a dia")),
       "Farol de Visita: linha TOTAL nas abas e as mesmas colunas da Parcial "
       "Visitas (+ CAD. C/ COMPRA)")

# ---- Farol de Visita: DIAS CAMPO em dias do calendario (2 vendedores no
# mesmo dia = 1 dia) e jornada sem o sabado (06/10)
import visitas_nucleo as _vnj                              # noqa: E402
from datetime import date as _dj                            # noqa: E402


def _lj(d, cod, ini, fim):
    return {"data": d, "cod": cod, "visitas": 3, "agendados": 3,
            "vis_agenda": 3, "vis_fora": 0, "primeiro": ini, "ultimo": fim,
            "tma": 600, "tmd": 600, "km_trab": 10, "km_total": 10,
            "venda": 0, "gps": True}
_rj = _vnj.resumir([_lj(_dj(2026, 10, 2), "A", 8 * 3600, 17 * 3600),
                    _lj(_dj(2026, 10, 2), "B", 8 * 3600, 17 * 3600),
                    _lj(_dj(2026, 10, 3), "A", 9 * 3600, 12 * 3600)])
checar(_rj["dias_corridos"] == 2 and _rj["dias"] == 3
       and _rj["inicio"] == 8 * 3600 and _rj["jornada"] == 9 * 3600
       and _rj["dias_jornada"] == 2,
       "Farol de Visita: dias em campo pelo calendário e jornada sem sábado")

# ---- (15/10) categorias do CATALOGO BAP 2026 em todos os acompanhamentos
# (giro, markup, FRW): PEÇAS, BATERIAS, PNEUS...; linha leve/pesada/moto
# virou a coluna LINHA
_catg = next(t_ for t_ in _rgv["tabelas"] if t_["titulo"] == "Por categoria")
checar({l[1] for l in _catg["linhas"]} & {"PEÇAS", "BATERIAS", "PNEUS"}
       and not {l[1] for l in _catg["linhas"]} & {"LINHA LEVE",
                                                   "LINHA PESADA",
                                                   "LINHA MOTO"},
       "Categorias do Catálogo BAP 2026 no Farol de Giro (PEÇAS, BATERIAS, "
       "PNEUS...)")

# ---- (06/10) RESUMO GERENCIAL PADRAO: os farois sem painel proprio ganham
# "O que o farol diz" + indicadores dia a dia, semana a semana e 12 meses
_pad_ok, _pad_x = 0, []
for _rid_p in rn.PAINEIS_PADRAO:
    _rp = rn.montar(_rid_p, AQUI)
    _pn = _rp.get("painel")
    if any("formato antigo" in a_ for a_ in _rp.get("avisos", [])):
        _pad_x.append(_rid_p)
        continue
    if not _pn:
        continue                    # sem dado: fica o resumo antigo
    _tit_p = [(b_.get("grafico") or b_).get("titulo", "") for b_ in _pn["blocos"]]
    if _pn["blocos"][0]["tipo"] == "insights" and \
            any("dia a dia" in t_ for t_ in _tit_p) and \
            any("semana a semana" in t_ for t_ in _tit_p) and \
            any("mês a mês" in t_ for t_ in _tit_p) and \
            "_eventos" not in _rp:
        _pad_ok += 1
    else:
        _pad_x.append(_rid_p)
checar(_pad_ok >= 8 and not _pad_x,
       f"Resumo gerencial padrão: {_pad_ok} farol(is) com insights + dia, "
       f"semana e mês {_pad_x}")

# ---- (26/10, Alexandre) meta de visita = 90% dos 12 por dia; visita e
# positivacao travadas no mes (metas_travadas_ind)
import meta_nucleo as _mn26                               # noqa: E402
_cl26 = [{"cod_vendedor": "000015", "visitas": 3, "meta_visita": 0.0,
          "meta_positivacao": 1.0},
         {"cod_vendedor": "000015", "visitas": 1, "meta_visita": 0.0,
          "meta_positivacao": 1.0}]
_mn26._meta_visita_por_du(_cl26, {"meta_visita_dias": {"000015": {
    "d1": 12, "d2": 12}}}, {"meta_visita_por_du": 12, "pct_visita": 90})
_v26a = sum(c_["meta_visita"] for c_ in _cl26)
_mn26._aplicar_travadas_ind(_cl26, {"metas_travadas_ind": {"2026-10": {
    "meta_visita": {"000015": 226.8}, "meta_positivacao": {"15": 23.5}}}},
    "2026-10")
_mn26_nov = [dict(c_) for c_ in _cl26]
_mn26._aplicar_travadas_ind(_mn26_nov, {"metas_travadas_ind": {"2026-10": {
    "meta_visita": {"000015": 1.0}}}}, "2026-11")
checar(abs(_v26a - 21.6) < 1e-6
       and abs(sum(c_["meta_visita"] for c_ in _cl26) - 226.8) < 1e-6
       and abs(_cl26[0]["meta_visita"] - 170.1) < 1e-6
       and abs(sum(c_["meta_positivacao"] for c_ in _cl26) - 23.5) < 1e-6
       and abs(sum(c_["meta_visita"] for c_ in _mn26_nov) - 226.8) < 1e-6,
       "Meta de visita = 90% dos 12 por dia; visita e positivação travadas "
       "só no mês da trava")

# ---- (26/10, Alexandre) Painel Executivo so com as 9 abas pedidas
_pe26 = rn.montar("vc_painel", AQUI)
_ab26 = [p_["titulo"] for p_ in _pe26.get("paineis") or []]
_pf26 = {p_["titulo"]: p_ for p_ in _pe26.get("paineis") or []}
_q26 = [b_ for p_ in _pf26.values() for b_ in p_["painel"]["blocos"]
        if b_["tipo"] == "tabela"]
_fat26 = next((b_ for b_ in (_pf26.get("Faturamento") or {"painel": {
    "blocos": []}})["painel"]["blocos"] if b_.get("titulo") == "Por filial"),
              None)
checar(_ab26 == ["Painel · resultado",
                "Painel · produtividade", "Painel · por dia útil"]
       + list(rn.ABAS_DO_PAINEL)
       and all(t_.get("so_exportar") for t_ in _pe26["tabelas"])
       and all(p_.get("kpis") is not None for p_ in _pf26.values())
       and all(len(l_) == len(b_["colunas"]) for b_ in _q26
               for l_ in b_["linhas"])
       and _fat26 is not None and abs(_fat26["total"][2] - sum(
           l_[2] or 0 for l_ in _fat26["linhas"])) < 1
       and not any("Abas do Painel" in a_ for a_ in _pe26["avisos"]),
       "Painel Executivo: só as abas Resumo gerencial, Faturamento, Volume, "
       "Produtividade, Positivação, Itens por pedido, Markup, Preço e "
       "Inadimplência (tabelas só no Excel/PDF)")

# ---- (29/10, Alexandre + analista) PAINEL DO DIRETOR: a 1a aba, 16 cartoes
# em 4 blocos (desafio comercial, nunca a meta RH), leitura do mes, imagem
# PNG e PDF A4; textos livres numa pasta temporaria (o cadastro de verdade
# nao e tocado)
import painel_diretor as _pd29  # noqa: E402
import tempfile as _tf29  # noqa: E402
_dd29 = (_pf26.get("Painel · resultado") or {}).get("diretor") or {}
_c29 = {c_["chave"]: c_ for c_ in _dd29.get("cards") or []}
_t29 = Path(_tf29.mkdtemp(prefix="smoke_diretor_"))
_png29, _pdf29 = _t29 / "p.png", _t29 / "p.pdf"
try:
    _pd29.imagem(_dd29, _png29, _pdf29)
    _img29 = _png29.stat().st_size > 50000 and _pdf29.read_bytes()[:4] \
        == b"%PDF"
except Exception as _e29:                               # noqa: BLE001
    print("   imagem:", _e29)
    _img29 = False
_pd29.gravar_config(_t29, {"acoes": [{"t": "A", "d": "b"}],
                           "compromisso": {"t": "X", "d": "y"},
                           "acao_preco": {}})
_cf29 = _pd29.ler_config(_t29)
_tg29 = next((t_ for t_ in _pe26["tabelas"] if t_["titulo"] == "Por filial"),
             None)
checar(len(_c29) == 16 and [b_ for b_, *_r in _pd29.BLOCOS] == [1, 2, 3, 4]
       and [sum(1 for c_ in _c29.values() if c_["bloco"] == b_)
            for b_ in (1, 2, 3, 4)] == [5, 5, 3, 3]
       and "RH" not in " ".join(c_["sub"] for c_ in _c29.values())
       and all([r_ for r_, _v in c_["linhas"]] in (
           ["Projeção", "Média/DU", "GAP meta", "% ating. proj."],
           ["Projeção", "Média/DU", "MoM", "M3M"],
           ["Projeção", "Variação/DU", "MoM", "M3M"])
           for k_, c_ in _c29.items() if k_ != "acao_preco")
       and _c29["fat"]["linhas"][0][0] == "Projeção"
       and _c29["fat"]["meta"] and _c29["ticket"]["meta"] is None
       and _c29["fat"]["numero"] > 0 and _c29["pos"]["numero"] >= 0
       and all(c_["tom"] in ("ok", "atencao", "alerta", "")
               for c_ in _c29.values())
       and len(_dd29["leitura"]) <= 3
       and all(c_["rid"] in rn.POR_ID for c_ in _c29.values() if c_["rid"])
       and len(_dd29["cards"]) == 16
       and "Painel do Diretor" not in _pf26
       and _img29 and _cf29["acoes"][0]["t"] == "A"
       and _cf29["compromisso"]["t"] == "X",
       "Painel do Diretor: o cálculo (base das abas RRM; a aba antiga saiu "
       "em 10/11), 16 cartões em 4 "
       "blocos contra o desafio comercial, todos no padrão (realizado, "
       "projeção, DU, GAP meta e % ating. projetado; sem meta MoM e M3M), "
       "leitura do mês, PNG e PDF A4, textos livres gravados")

# ---- (05/11, Alexandre: "visita por dia util, conta simples; nao e para
# estar 3 de 19") A LINHA DU E A MEDIA POR DIA UTIL de cada cartao (com os
# DU da fonte dele) e a projecao = media/DU x DU do mes
_l05 = {k_: dict(c_["linhas"]) for k_, c_ in _c29.items()}
_vis05 = _c29.get("visitas") or {}
# (06/11) o "· N DU" saiu do cartao (os DU ficam no titulo do bloco 1)
_mv05 = re.fullmatch(r"([\d\.,]+)", _l05.get("visitas", {}).get(
    "Média/DU", ""))
checar(not any(re.fullmatch(r"\d+ de \d+", str(v_)) for d_ in _l05.values()
               for v_ in d_.values())
       and (_vis05.get("numero") is None or (
           _mv05 and abs(float(_mv05.group(1).replace(".", "")
                                .replace(",", ".")) * _dd29["ndm"]
                         - (_vis05["projecao"] or 0)) < 0.06 * _dd29["ndm"]))
       and "Variação/DU" in _l05.get("inad", {})
       and "Média/DU" in _l05.get("fat", {}),
       "Painel do Diretor: a linha DU é a média por dia útil (realizado ÷ DU "
       "decorridos da fonte do cartão), nunca \"3 de 19\"; projeção das "
       "visitas = média/DU × DU do mês")
# (06/11, Alexandre: "coloque o DU do mes ao lado do titulo e tire dos
# cards" e "ajuste a projecao do resumo gerencial do painel do diretor que
# esta divergente") os DU no titulo do bloco 1, nenhum "N DU" nos cartoes;
# o Painel Executivo (cartao Projecao e o "Meta x Real" do Resumo
# gerencial) com os DU fechados e sem a venda de hoje, = Painel do Diretor
_tx06 = " ".join(str(v_) for c_ in _c29.values() for _r, v_ in c_["linhas"])
_kp06 = {k_["rotulo"]: k_["valor"] for k_ in _pe26["kpis"]}
_pj06 = _c29["fat"].get("projecao")
_pe06 = rn._num(_kp06.get("Projeção")) if hasattr(rn, "_num") else None
if _pe06 is None:
    _pe06 = float(re.sub(r"[^\d,]", "", _kp06.get("Projeção", "0"))
                  .replace(",", ".") or 0)
_ct06 = rn.Contexto(AQUI, _dt05_hoje := __import__("datetime").date(2026, 11, 6))
_ok06 = (not re.search(r"\d+ DU", _tx06)
         and _pd29._du_titulo(_dd29) == f"· {_dd29['ndp']} de "
                                         f"{_dd29['ndm']} DU"
         and (_pj06 is None or abs(_pe06 - _pj06) <= max(1.0, 0.001 * _pj06))
         and rn._de_hoje(_ct06, {"dt_nf": _dt05_hoje, "tipo": "VND",
                                 "valor": 10.0, "qtd": 1}) in (0.0, 10.0))
checar(_ok06, "Painel do Diretor: DU do mês no título do bloco 1 e fora dos "
       "cartões; projeção do Painel Executivo (e do Resumo gerencial) = a do "
       "Painel do Diretor (DU fechados, sem a venda de hoje) (06/11)")
# (06/11, Alexandre) REGRA: vendedor INATIVO no Planner do mes fica fora
# das tabelas e parciais de meta, a nao ser que tenha movimento no codigo
# dele no mes (venda, devolucao, pedido, positivacao, visita, cadastro)
class _Cx06:
    tabela = {"itens": [{"vend": "000777", "tipo": "VEA", "dt_nf": None,
                         "dt_pedido": __import__("datetime").date(2026, 11, 3)}]}
_l06 = {"chave": "000999", "vendedor_ativo": False, "realizado": 0.0,
        "visitas_total": 300}
_ok06i = (rn._inativo_oculto(_Cx06(), "2026-11", _l06)
          and not rn._inativo_oculto(_Cx06(), "2026-11",
                                     dict(_l06, realizado=10.0))
          and not rn._inativo_oculto(_Cx06(), "2026-11",
                                     dict(_l06, chave="000777"))
          and not rn._inativo_oculto(_Cx06(), "2026-11",
                                     dict(_l06, vendedor_ativo=True)))
_rm06 = rn.montar("vc_meta", AQUI)
# (10/11, Alexandre: "Tudo deve bater... coloque a filial da nota" e
# "verifique os demais indicadores se estao no formato filial por nota") o
# estado do faturamento e a FILIAL DA NOTA: Por UF do Farol de Metas =
# rel["_por_filial"]; as barras por estado do cartao somam o cartao
_pf10 = _rm06.get("_por_filial") or {}
_tu10 = next((t_ for t_ in _rm06["tabelas"] if t_["titulo"] == "Por UF"),
             None)
_ok10 = (rn.uf_da_filial("0101005") == rn.uf_da_filial("0101007") == "PA"
         and rn.uf_da_filial("0101002") == "AM"
         and rn.uf_da_filial("0101006") == "MA"
         and rn.uf_do_nome_da_filial("SANTARÉM") == "PA"
         and bool(_pf10.get("fat") is not None))
if _ok10 and _tu10:
    _n10 = [c_["nome"] for c_ in _tu10["colunas"]]
    if "FAT. REAL" in _n10:
        _i10 = _n10.index("FAT. REAL")
        for l_ in _tu10["linhas"]:
            if abs((l_[_i10] or 0) - _pf10["fat"].get(l_[0], 0)) > 0.5:
                _ok10 = False
for k_ in _rm06["kpis"]:
    _e10 = rn.estados_do_cartao(_rm06, k_)
    _cf10 = (_e10 or {}).get("conferencia") or {}
    if _cf10.get("cartao") and not _cf10.get("taxa") and \
            _cf10.get("soma_estados") is not None and \
            abs(_cf10["cartao"] - _cf10["soma_estados"]
                - (_cf10.get("fora_dos_estados") or 0)) > \
            max(1.0, 0.005 * abs(_cf10["cartao"])):
        _ok10 = False
checar(_ok10, "Cartões por estado: UF pela filial da nota (0101005/0101007 "
       "PA, 0101002 AM, 0101006 MA); Por UF do Farol de Metas = filial da "
       "nota; as barras por estado somam o cartão (10/11)")
_ct06i = rn.Contexto(AQUI, None, None, dict(_rm06.get("params_usados") or {}))
_ac06i = rn.meta_do_periodo(_ct06i)
_oc06 = {rn.norm_nome(l_.get("nome") or l_.get("rotulo"))
         for l_ in _ac06i["acomp"]["recortes"].get("vendedor", [])
         if rn._inativo_oculto(_ct06i, _ac06i["competencia"], l_)}
_tv06 = next((t_ for t_ in _rm06["tabelas"] if t_["titulo"] == "Por vendedor"),
             {"linhas": []})
checar(_ok06i and not (_oc06 & {rn.norm_nome(l_[0]) for l_ in
                                 _tv06["linhas"]}),
       "Vendedor inativo no Planner sem movimento no mês fica fora das "
       "tabelas e parciais de meta; com venda, pedido ou visita, aparece "
       "(06/11)")
# (05/11, Alexandre: "tirar a venda de hoje da conta do DU") hoje (dia
# aberto) nao conta nos DU corridos e o que e de hoje sai da projecao: o
# Painel do Diretor vai ate ontem; Farol de Metas e de Visita tiram a venda
# / visita de hoje da projecao (o realizado do cartao continua com hoje)
import datetime as _dt05  # noqa: E402
_k05 = rn._cartao_indicador("X", 1000, 100, 10, 50.0, real_proj=60)
_c05 = rn._cartoes_farol(
    [["A", 500.0, 100.0]], [{"nome": "NOME"}, {"nome": "FAT. META"},
                            {"nome": "FAT. REAL"}], 10, 50.0,
    hoje_total={"FAT.": 40.0})
_c05b = rn._cartoes_farol(
    [["ANA", 500.0, 100.0], ["BIA", 500.0, 50.0]],
    [{"nome": "NOME"}, {"nome": "FAT. META"}, {"nome": "FAT. REAL"}], 10,
    50.0, hoje_de={"ANA": {"FAT.": 40.0}})
checar({x_[0]: x_[1] for x_ in _k05["linhas"]}.get("Projeção do mês", "").startswith("120")
       and {x_[0]: x_[1] for x_ in _c05[0]["linhas"]}.get("Projeção do mês", "").startswith(
           "R$ 120")
       and {x_[0]: x_[1] for x_ in _c05b[0]["linhas"]}.get("Projeção do mês", "").startswith(
           "R$ 220")
       and (_dd29.get("dados_ate") is None
            or _dd29["dados_ate"] < _dt05.date.today()
            or _dd29["dados_ate"].month != _dt05.date.today().month),
       "Hoje fora da conta do DU: o Painel do Diretor vai até ontem e o "
       "Farol de Metas tira a venda de hoje da projeção")

# ---- (31/10, Maestro Sistemas) PAINEL DO DIRETOR NUM MES SEM DADO: no 1o dia
# util (antes do Espelho e das notas) o cartao com meta e sem realizado
# quebrava (None - float) e o Painel do Diretor sumia do Painel Executivo.
# Historico numa pasta temporaria (o painel_diretor_hist.json nao e tocado).
import datetime as _dt31  # noqa: E402
_hj31 = _dt31.date.today()
_px31 = _dt31.date(_hj31.year + (_hj31.month == 12), _hj31.month % 12 + 1, 1)
while _px31.weekday() >= 5:
    _px31 += _dt31.timedelta(days=1)
_hp31 = _pd29._hist_path
_pd29._hist_path = lambda raiz: _t29 / "hist_vazio.json"
try:
    _pv31 = rn.montar("vc_painel", AQUI, hoje=_px31,
                      params={"MÊS": _px31.month, "ANO": _px31.year})
finally:
    _pd29._hist_path = _hp31
_pf31 = {p_["titulo"]: p_ for p_ in _pv31.get("paineis") or []}
_c31 = {c_["chave"]: c_ for c_ in ((_pf31.get("Painel · resultado") or {})
                                   .get("diretor") or {}).get("cards") or []}
checar(len(_c31) == 16
       and not any("Painel do Diretor:" in a_ for a_ in _pv31["avisos"])
       and _c31["conv_visitados"]["valor"] == "—",
       "Painel do Diretor num mês ainda sem visita e sem nota: os 16 "
       "cartões aparecem (sem dado = \"—\") e o painel não some")

# (09/11, Alexandre, recado 20261109-1100) Painel do Diretor: % CONVERSAO
# NOS VISITADOS e % 1a VISITA no lugar de nao comprador e conversao em
# quem compra; OUT/26 = inicio do registro cliente a cliente
if TEM_DADOS:
    _x11 = _ctx                     # (memoria: reaproveita o contexto)
    _d11 = _pd29.calcular(_x11, 2026, 11, gravar_hist=False)
    _k11 = {c_["chave"]: c_ for c_ in _d11["cards"]}
    _o11 = {c_["chave"]: c_ for c_ in _pd29.calcular(
        _x11, 2026, 10, gravar_hist=False)["cards"]}
    checar(len(_k11) == 16 and "conv_visitados" in _k11
           and "primeira_visita" in _k11
           and "nao_comprador" not in _k11 and "conversao" not in _k11
           and _o11["primeira_visita"]["valor"] == "início do registro",
           "Painel do Diretor: % conversão nos visitados e % 1ª visita "
           "(OUT = início do registro)")
    if "(12 de 241;" in _k11["conv_visitados"]["regra"]:  # dados de 06/11
        checar("(45 de 241)" in _k11["primeira_visita"]["regra"]
               and "(61 de 666;" in _o11["conv_visitados"]["regra"],
               "Painel do Diretor: conferência do Comercial (nov 12 de 241 "
               "e 45 de 241; out 61 de 666)")

# ---- painel executivo (reuniao)
_pe = rn.montar("vc_painel", AQUI)
_blocos = (_pe.get("painel") or {}).get("blocos") or []
_pz = {b_.get("titulo"): b_ for b_ in _blocos if b_["tipo"] in ("pizza",
                                                                "grupo")}
_f_pe = rn.montar("vc_painel", AQUI, params={"CATEGORIA": "BATERIAS"})
checar(len(_blocos) == 8 and len(_pz["Por filial"]["linhas"][0]) == 12
       and [p_["nome"] for p_ in _pe["parametros"]][-11:] == [
           "UF", "CIDADE", "SUPERVISOR", "VENDEDOR", "SEGMENTO", "CATEGORIA",
           "SISTEMA", "FAMÍLIA", "LINHA", "PRODUTO", "PEDIDOS"]
       and all(b_["grafico"].get("linha") for b_ in _blocos[4:8])
       and "Categoria: BATERIAS" in _f_pe["subtitulo"] and [k["rotulo"] for k in _pe["kpis"]][:4]
       == ["Desafio comercial", "Real", "Pedidos em aberto", "Projeção"]
       and [b_["tipo"] for b_ in _blocos].count("pizza") == 4
       and all([l[1] or 0 for l in b_["linhas"]
                if not str(l[0]).startswith("DEMAIS")] == sorted(
           [l[1] or 0 for l in b_["linhas"]
            if not str(l[0]).startswith("DEMAIS")], reverse=True)
               for b_ in _pz.values())
       and set(_pz) == {"Por filial", "Por categoria", "Por família",
                        "Por segmento"}
       and not any(b_.get("titulo") in ("Vendedores", "Clientes")
                   for b_ in _blocos)
       and all(abs(sum(l[2] or 0 for l in b_["linhas"]) - b_["total"][2]) < 1
               for b_ in _pz.values())
       and {t_["titulo"] for t_ in _pe["tabelas"]} >= {
           "Vendedores", "Clientes", "Produtos", "Mês a mês", "Por filial",
           "Por categoria", "Por sistema", "Por família", "Por linha",
           "Por segmento"},
       f"Painel executivo: filtros, pizzas do projetado (filial, categoria, "
       f"família) e segmento com meta, real, projeção, % proj., positivação, "
       f"IPP, volume e markup; gráficos com a linha do % MoM "
       f"{_pe['avisos']}")

# ---- base de clientes para o Protheus (Planner) e mix por segmento
_bp = _pn2.base_protheus(_cfg_r, _cli_r, _pn2.filiais_dos_clientes(
    AQUI / "RELATORIOS" / "TABELA_BAP.xlsx"))
checar(_bp and list(_bp[0]) == _pn2.CAMPOS_BASE_PROTHEUS
       and all(len(x["A1_COD"]) == 6 and len(x["A1_VEND"]) == 6
               for x in _bp),
       f"Planner: base de clientes no layout do Protheus ({len(_bp)} clientes)")
_rm = rn.montar("vc_meta", AQUI)
_ts = next((t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por segmento"),
           None)
_tf = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por família da peça")
_tcat = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por categoria")
_tcid = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por cidade")
_tbai = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por bairro")
_tg_ = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por gerente")
checar([c["nome"] for c in _tcid["colunas"]][:2] == ["UF", "CIDADE"]
       and [c["nome"] for c in _tbai["colunas"]][:3] == ["UF", "CIDADE",
                                                        "BAIRRO"]
       and all(len(str(l[0])) <= 3 or str(l[0]).startswith("(")
               for l in _tcid["linhas"])
       and [rn.sem_acento(str(l[1])) for l in _tcid["linhas"]
            if not str(l[1]).startswith("(")] == sorted(
                rn.sem_acento(str(l[1])) for l in _tcid["linhas"]
                if not str(l[1]).startswith("("))
       and len(_tbai["linhas"]) <= rn.TOP_BAIRROS + 1
       and abs(sum(l[1] or 0 for l in _tcat["linhas"])
               - (_tg_["total"] or _tg_["linhas"][0])[2]) < 1,
       f"Farol: UF, CIDADE e BAIRRO em colunas separadas (cidade em ordem "
       f"alfabética); categoria soma a meta do gerente "
       f"({len(_tcat['linhas'])} categorias)")
_tger_m = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por gerente")
_bap_f = _tf["linhas"]
_nf_ = [c["nome"] for c in _tf["colunas"]]
_ns_ = [c["nome"] for c in _ts["colunas"]]
checar(_ts and _nf_[1:6] == _ns_[2:6] + ["POSIT. REAL"]
       and not any(n.startswith(("VISITA", "PEÇAS", "RV", "POSIT. META"))
                   for n in _nf_)
       and not any(n.startswith(("VISITA", "RV")) for n in _ns_)
       and any(n.startswith("PEÇAS") for n in _ns_)
       and abs(sum(l[1] or 0 for l in _bap_f)
               - sum(l[2] or 0 for l in _tger_m["linhas"])) < 1
       and abs(sum(l[_nf_.index("FAT. REAL")] or 0 for l in _bap_f)
               - sum(l[_ns_.index("FAT. REAL")] or 0 for l in _ts["linhas"]))
       < 1
       and "Por segmento (mix)" not in [t_["titulo"] for t_ in _rm["tabelas"]],
       "Farol de Metas: família só com faturamento, clientes e mix; território "
       "sem visita e RV; meta das famílias = meta do gerente")
_tv_m = next(t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Por vendedor")
_seg_m = sum(l[2] or 0 for l in _ts["linhas"])
checar(abs(_seg_m - sum(l[2] or 0 for l in _tger_m["linhas"])) < 1
       and "FAT. META RH" not in [c_["nome"] for c_ in _tv_m["colunas"]]
       and "Metas RH" not in [t_["titulo"] for t_ in _rm["tabelas"]]
       and "RV por vendedor" not in [t_["titulo"] for t_ in _rm["tabelas"]],
       "Meta comercial: segmento soma a meta do gerente; a META RH fica "
       "fora do Farol (29/10)")
_p_uf = next(p_ for p_ in _rm["parametros"] if p_["nome"] == "UF")
_uf1 = _p_uf["valores"][1] if len(_p_uf["valores"]) > 1 else None
if _uf1:
    _rmf = rn.montar("vc_meta", AQUI, params={"UF": _uf1})
    _tuf = next(t_ for t_ in _rmf["tabelas"] if t_["titulo"] == "Por UF")
    _tvf = next(t_ for t_ in _rmf["tabelas"] if t_["titulo"] == "Por vendedor")
    _tsf = next(t_ for t_ in _rmf["tabelas"] if t_["titulo"] == "Por segmento")
    checar([l[0] for l in _tuf["linhas"]] == [_uf1]
           and abs(sum(l[2] or 0 for l in _tsf["linhas"])
                   - _tuf["linhas"][0][2]) < 1
           and abs(sum(l[3] or 0 for l in _tvf["linhas"])
                   - _tuf["linhas"][0][2]) < 1
           and f"Uf: {_uf1}" in _rmf["subtitulo"],
           f"Farol de Metas: o recorte UF={_uf1} vale para todas as abas "
           f"(vendedor e segmento somam a UF)")

# ---- STATUS PROTHEUS (BAP Tools) x STATUS PLANNER nos relatorios
checar(rn._cod_loja_de("001234-02") == ("001234", "02")
       and rn._cod_loja_de("001234 - 12 AUTO") == ("001234", None)
       and rn._cod_loja_de("") == ("", None),
       "Status: código e loja lidos da coluna CLIENTE")
_t_st = rn.tabela("T", [rn.col("CLIENTE"), rn.col("V", "num")],
                  [["000001-01", 5], ["000002 - X", 7]],
                  total=["TOTAL", 12], kpis_de=lambda ls: [
                      rn.kpi("S", sum(l[1] for l in ls))],
                  recortes=[("grande", lambda l: l[1] > 6),
                            ("top", {"top": 1, "coluna": 1})])
_t_st["protheus"] = {"i_cliente": 0, "i_visita": 1}


class _CtxSt:
    def status_protheus(self, cod, loja=None):
        return "INATIVO" if cod == "000002" else "ATIVO"

    def status_planner(self, cod, loja=None):
        return "CHURN 30"


rn.com_status(_CtxSt(), _t_st, 1, 0)
checar([c["nome"] for c in _t_st["colunas"]] == [
    "CLIENTE", "STATUS PROTHEUS", "STATUS PLANNER", "SITUAÇÃO PLANNER", "V"]
       and _t_st["linhas"][1][1:4] == ["INATIVO", "ATIVO", "CHURN 30"]
       and _t_st["kpis_de"](_t_st["linhas"])[0]["valor"] == 12
       and [bool(_t_st["recortes"][0][1](l)) for l in _t_st["linhas"]]
       == [False, True] and _t_st["recortes"][1][1]["coluna"] == 4
       and _t_st["total"] == ["TOTAL", "", "", "", 12]
       and _t_st["protheus"] == {"i_cliente": 0, "i_visita": 4}
       and _t_st["filtros"][-3:] == ["STATUS PROTHEUS", "STATUS PLANNER",
                                     "SITUAÇÃO PLANNER"]
       and rn.status_planner_binario("CHURN 90") == "ATIVO"
       and rn.status_planner_binario("NUNCA COMPROU") == "ATIVO"
       and rn.status_planner_binario("CHURN 90+") == "ATIVO"
       and rn.status_planner_binario("CHURN 30", True) == "INATIVO",
       "Status: colunas novas sem quebrar cartões, recortes, total e índices")
import bap_dados as _bd_st  # noqa: E402
checar(_bd_st.status_protheus_de("INATIVO", "2") == "INATIVO"
       and _bd_st.status_protheus_de(None, "1") == "INATIVO"
       and _bd_st.status_protheus_de("", "2") == "ATIVO"
       and _bd_st.status_protheus_de(None, None) == "",
       "Status Protheus: coluna STATUS do BAP Tools, senão A1_MSBLQL")
checar(_pn2.status_para_protheus(True) == "INATIVO"
       and _pn2.status_para_protheus() == "ATIVO"
       # (20/10) TODO cliente sai ATIVO no .json; quem esta fora do
       # Planner (sem vendedor/inativado) vai com o VENDEDOR e o SUPERVISOR
       # PADRAO
       # (10/11) menos o INATIVO no Protheus, que vai INATIVO
       and {x["STATUS"] for x in _bp} <= {"ATIVO", "INATIVO"}
       and sum(1 for x in _bp if x["STATUS"] == "INATIVO")
       == sum(1 for c_ in _cli_r if _pn2.inativo_no_protheus(c_))
       and all(x["SUPERVISOR"] == _pn2.supervisor_padrao(_cfg_r)
               for x in _bp if x["A1_VEND"] == "000000")
       and _pn2.status_no_json(True) == "ATIVO"
       and _pn2.supervisor_padrao({}) == "000037"
       and len(_bp) == len(_cli_r)
       and _pn2.vendedor_padrao({"parametros": {"vendedor_padrao": "12"}})
       == "000012",
       "Base Protheus (.json): ATIVO (só o INATIVO no Protheus vai "
       "INATIVO, 10/11); fora do Planner com o vendedor padrão 000000 e o "
       "supervisor padrão 000037")
# (23/10) o Farol de Pedidos saiu (sem o STATUS do cliente)
for _rid_st, _tit_st in (("vc_base", "Clientes"),
                         ("vc_planner", "Por cliente")):
    _r_st = rn.montar(_rid_st, AQUI)
    _tt = next((t_ for t_ in _r_st["tabelas"] if t_["titulo"] == _tit_st),
               None)
    if _tt is None:
        continue
    _nm = [c["nome"] for c in _tt["colunas"]]
    if _rid_st == "vc_base":
        # 06/10: Farol de Clientes so com STATUS (o do Planner); Protheus,
        # situacao, supervisor e comprou no mes fora da tela e do PDF;
        # UF antes da CIDADE, com ENDERECO e Nº
        _vis = [c["nome"] for c in _tt["colunas"] if not c.get("oculta")]
        _ist = _nm.index("STATUS")
        # (07/10) vendedor e supervisor do Planner e do Protheus visiveis
        checar(_vis[:11] == ["CÓD.", "CLIENTE", "UF", "CIDADE", "ENDEREÇO",
                             "Nº", "SEGMENTO", "VENDEDOR PLANNER",
                             "SUPERVISOR PLANNER", "VENDEDOR PROTHEUS",
                             "SUPERVISOR PROTHEUS"]
               and "STATUS" in _vis and not {
                   "STATUS PROTHEUS", "SITUAÇÃO PLANNER",
                   "COMPROU NO MÊS", "STATUS PLANNER"} & set(_vis)
               and "STATUS" in _tt["filtros"]
               and "STATUS PROTHEUS" not in _tt["filtros"]
               and {l[_ist] for l in _tt["linhas"]} <= {
                   "ATIVO", "INATIVO", rn.FORA_DO_PLANNER, "SEM STATUS", ""}
               and _tt["kpis_de"](_tt["linhas"])
               and set(_tt["pdf"]["quebra"]) == {"ENDEREÇO", "CONTATO"},
               "vc_base/Clientes: UF, cidade, endereço, nº, segmento; só STATUS")
        # (08/10) PDF enxuto: so VENDEDOR (o do Planner), sem supervisor,
        # Protheus, FAT. 6M e ultimo produto; FALTA sai como GAP
        _pdf_c = {c["nome"]: c for c in _tt["colunas"]}
        checar(all(_pdf_c[n_].get("pdf_oculta") for n_ in (
            "SUPERVISOR PLANNER", "VENDEDOR PROTHEUS", "SUPERVISOR PROTHEUS",
            "FAT. 6M", "ÚLTIMO PRODUTO"))
               and _pdf_c["VENDEDOR PLANNER"]["pdf_nome"] == "VENDEDOR"
               and _pdf_c["FALTA"]["pdf_nome"] == "GAP"
               and not _pdf_c["CONTATO"].get("pdf_oculta"),
               "vc_base/Clientes PDF: só VENDEDOR, sem FAT. 6M e último "
               "produto, FALTA = GAP, contato inteiro")
        continue
    if _rid_st == "vc_planner":        # 06/10: so STATUS (o do Planner)
        _ist = _nm.index("STATUS")
        _vis = [c["nome"] for c in _tt["colunas"] if not c.get("oculta")]
        checar("STATUS" in _vis and "STATUS" in _tt["filtros"]
               and not {"STATUS PROTHEUS", "SITUAÇÃO PLANNER"} & set(_vis)
               and {l[_ist] for l in _tt["linhas"]} <= {
                   "ATIVO", "INATIVO", rn.FORA_DO_PLANNER, "SEM STATUS", ""}
               and _tt["kpis_de"](_tt["linhas"]),
               "vc_planner/Por cliente: só STATUS (ATIVO/INATIVO) com filtro")
        continue
    # 06/10: em NENHUM relatorio STATUS PROTHEUS / SITUACAO PLANNER; o
    # status do Planner aparece so como STATUS
    _ip = _nm.index("STATUS") if "STATUS" in _nm else 0
    _vis = [c["nome"] for c in _tt["colunas"] if not c.get("oculta")]
    _fl = [rn.nome_filtro(f_) for f_ in _tt["filtros"]]
    checar("STATUS" in _vis and "STATUS" in _fl
           and not {"STATUS PROTHEUS", "STATUS PLANNER",
                    "SITUAÇÃO PLANNER"} & (set(_vis) | set(_fl))
           and {l[_ip] for l in _tt["linhas"]} <= {
               "ATIVO", "INATIVO", rn.FORA_DO_PLANNER, "SEM STATUS", ""}
           and (not _tt["kpis_de"] or _tt["kpis_de"](_tt["linhas"])),
           f"{_rid_st}/{_tit_st}: só STATUS (o do Planner) com filtro")
_proib = {"STATUS PROTHEUS", "STATUS PLANNER", "SITUAÇÃO PLANNER"}
_com = []
for _rid in ("pv_abertos", "pv_faturados", "pv_pedidos", "vc_markup",
             "pl_inadimplencia", "vc_saldo", "vc_base", "vc_planner"):
    _r9 = rn.montar(_rid, AQUI)
    for _t9 in _r9.get("tabelas") or []:
        _v9 = {c["nome"] for c in _t9["colunas"] if not c.get("oculta")}
        _f9 = {rn.nome_filtro(f_) for f_ in _t9.get("filtros") or []}
        if (_v9 | _f9) & _proib:
            _com.append(f"{_rid}/{_t9['titulo']}")
checar(not _com, "nenhum relatório com STATUS PROTHEUS, STATUS PLANNER ou "
       "SITUAÇÃO PLANNER (só STATUS)" + (f": {_com}" if _com else ""))
_rp_st = rn.montar("vc_planner", AQUI)
_ex_st = _rp_st["exportar_base_protheus"]()
checar(not _ex_st or ("STATUS" in _ex_st[0] and all(
    x["STATUS"] == "ATIVO" for x in _ex_st)),
       "Farol Roteirização: base de clientes .json com TODOS ATIVO (20/10)")

# ---- (21/10) Farol Roteirizacao SO COM ROTA E VISITA: sem R$, BASE
# PLANNER no lugar de CLIENTES, BASE PROTHEUS e as mesmas colunas (na mesma
# ordem) em todas as abas agregadas; Por cliente com SIM/NAO
_NUM_ROT = ["BASE PLANNER", "BASE VISITA", "VISITAS/MÊS",
            "VISITAS/MÊS DIAS ÚTEIS", "CLIENTES/DIA", "CAPACIDADE/DIA",
            "COM LIMITE", "INADIMPL.", "COMPRADORES", "% COMPRADORES"]
_ok_rot, _rs_rot = True, []
for _t_r in _rp_st["tabelas"]:
    _nm_r = [c_["nome"] for c_ in _t_r["colunas"]]
    _rs_rot += [f"{_t_r['titulo']}/{c_['nome']}" for c_ in _t_r["colunas"]
                if c_.get("tipo") == "moeda"]
    if _t_r["titulo"] in ("Por zona", "Por vendedor", "Por supervisor",
                          "Por segmento", "Por UF", "Por cidade"):
        _i_bp = _nm_r.index("BASE PROTHEUS") if "BASE PROTHEUS" in _nm_r \
            else -9
        _ok_rot = _ok_rot and _nm_r[_i_bp + 1:] == _NUM_ROT \
            and "CLIENTES" not in _nm_r \
            and all(len(l_) == len(_nm_r) for l_ in _t_r["linhas"]) \
            and len(_t_r["total"]) == len(_nm_r) \
            and _t_r["kpis_de"](_t_r["linhas"])
_t_uf = next(t_ for t_ in _rp_st["tabelas"] if t_["titulo"] == "Por UF")
_t_pc = next((t_ for t_ in _rp_st["tabelas"] if t_["titulo"] == "Por cliente"),
             None)
_nm_pc = [c_["nome"] for c_ in (_t_pc or {}).get("colunas", [])]
_ok_rot = _ok_rot and not _rs_rot \
    and any(l_[_t_uf["colunas"].index(next(
        c_ for c_ in _t_uf["colunas"] if c_["nome"] == "BASE PROTHEUS"))]
        for l_ in _t_uf["linhas"]) \
    and (_t_pc is None or (
        {"COM LIMITE", "INADIMPLENTE", "COMPRADOR"} <= set(_nm_pc)
        and not {"LIMITE DISP.", "VALOR ATRASO", "RECEITA 6M"} & set(_nm_pc)
        and {l_[_nm_pc.index("COMPRADOR")] for l_ in _t_pc["linhas"]}
        <= {"SIM", "NÃO"}))
checar(_ok_rot, "Farol Roteirização só com rota e visita: sem R$, BASE "
       "PLANNER, BASE PROTHEUS e as mesmas colunas em todas as abas; Por "
       "cliente com COM LIMITE / INADIMPLENTE / COMPRADOR (21/10)"
       + (f" - em R$: {_rs_rot[:5]}" if _rs_rot else ""))

# ---- Farol Roteirizacao › Por segmento com filtro VENDEDOR
_seg = next(t_ for t_ in _rp_st["tabelas"] if t_["titulo"] == "Por segmento")
_seg_todos = [l for l in _seg["linhas"] if l[1] == rn.TODOS_VENDEDORES]
_seg_v = [l for l in _seg["linhas"] if l[1] != rn.TODOS_VENDEDORES]
_soma_seg = defaultdict(float)
_ibp_seg = [c_["nome"] for c_ in _seg["colunas"]].index("BASE PLANNER")
for _l in _seg_v:
    _soma_seg[_l[0]] += _l[_ibp_seg] or 0
checar(_seg_todos and _seg["filtros"][0] == {
    "coluna": "VENDEDOR", "padrao": rn.TODOS_VENDEDORES}
       and all(abs(_soma_seg[l[0]] - (l[_ibp_seg] or 0)) < 0.5
               for l in _seg_todos)
       and all(l[1] in _seg["totais_por"]["valores"] for l in _seg_v),
       "Por segmento: filtro VENDEDOR (segmentos de cada vendedor somam o "
       "total) e TOTAL de cada vendedor")

# ---- Farol de Inadimplencia
checar(rn.faixa_de_atraso(None) == "A VENCER"
       and rn.faixa_de_atraso(0) == "A VENCER"
       and rn.faixa_de_atraso(1) == "1–15 DIAS"
       and rn.faixa_de_atraso(90) == "61–90 DIAS"
       and rn.faixa_de_atraso(181) == "+180 DIAS",
       "Inadimplência: faixas de atraso")
_tit = [{"saldo": 100.0, "venc": date(2026, 10, 1), "cod": "000001"},
        {"saldo": 50.0, "venc": date(2026, 10, 5), "cod": "000002"},
        {"saldo": 0.0, "venc": date(2026, 9, 1), "cod": "000003"}]
_ft = _bd_st.resumo_da_foto(_tit, date(2026, 10, 5))
checar(_ft["aberto"] == 150 and _ft["atraso"] == 100
       and _ft["a_vencer"] == 50 and _ft["clientes"] == 1,
       "Inadimplência: foto do dia (vence hoje ainda não é atraso)")
_ri = rn.montar("pl_inadimplencia", AQUI)
_tt_i = {t_["titulo"]: t_ for t_ in _ri["tabelas"]}
if _tt_i.get("Títulos"):
    _ti = _tt_i["Títulos"]
    _nm = [c["nome"] for c in _ti["colunas"]]
    _venc_i = [l for l in _ti["linhas"] if l[0] == "VENCIDO"]
    _tot_v = _tt_i["Por vendedor"]["total"]
    checar(_ri.get("capa") and len(_ri["graficos"]) >= 5
           and _ti["detalhe"] and _ti["detalhe"]["nf"] == _nm.index("NF")
           and all(l[_nm.index("DIAS ATRASO")] > 0 for l in _venc_i)
           and abs(_tot_v[-3] - sum(l[_nm.index("SALDO")] for l in _venc_i))
           < 0.01 and "STATUS PROTHEUS" in _nm
           and "Por cliente" in _tt_i and "Dia a dia" in _tt_i,
           f"Farol de Inadimplência: {len(_venc_i)} títulos vencidos, aging "
           f"por vendedor fecha com os títulos, NF abre o pedido")
else:
    print("  (sem ftTitulos nesta pasta - pulando o Farol de Inadimplência)")
import bap_central as _bc  # noqa: E402
checar(("Farol de Inadimplência", "pl_inadimplencia") in
       next(q[2] for q in _bc.QUADRADOS if q[0] == _bc.POS),
       "BAP Central: Farol de Inadimplência no quadrado do Pós-venda")

# ---- Farol de Clientes: recorte por vendedor/supervisor/UF/cidade/zona/cliente
_rb = rn.montar("vc_base", AQUI)
_prm = {p_["nome"]: p_ for p_ in _rb["parametros"]}
checar({"VENDEDOR", "SUPERVISOR", "UF", "CIDADE", "ZONA", "CLIENTE"}
       <= set(_prm), "Farol de Clientes: recorte em cima (vendedor, supervisor,"
       " UF, cidade, zona, cliente)")
_v_rec = next((v for v in _prm["VENDEDOR"]["valores"][1:]
               if v != "(SEM VENDEDOR)"), None)
if _v_rec:
    _rb2 = rn.montar("vc_base", AQUI, params={"VENDEDOR": _v_rec})
    _cl2 = next(t_ for t_ in _rb2["tabelas"] if t_["titulo"] == "Clientes")
    _seg2 = next(t_ for t_ in _rb2["tabelas"] if t_["titulo"] == "Por segmento")
    _i_v = [c["nome"] for c in _cl2["colunas"]].index("VENDEDOR PLANNER")
    _cid2 = {p_["nome"]: p_ for p_ in _rb2["parametros"]}["CIDADE"]["valores"]
    checar(_cl2["linhas"] and all(l[_i_v] == _v_rec for l in _cl2["linhas"])
           and sum(l[1] for l in _seg2["linhas"])
           == len({l[0] for l in _cl2["linhas"]})     # (12/10) por codigo
           and len(_cid2) <= len(_prm["CIDADE"]["valores"]),
           f"Farol de Clientes › recorte {_v_rec}: clientes, segmento, "
           f"família e produto só dele; cidades só as dele")

# ---- Farol de Markup › Todos os produtos (com e sem venda)
_rmk = rn.montar("vc_markup", AQUI)
_tp_all = next((t_ for t_ in _rmk["tabelas"]
                if t_["titulo"] == "Todos os produtos"), None)
_tp_prod = next(t_ for t_ in _rmk["tabelas"] if t_["titulo"] == "Por produto")
checar(_tp_all and len(_tp_all["linhas"]) >= len(_tp_prod["linhas"])
       and {l[0] for l in _tp_prod["linhas"]} <= {l[0] for l in _tp_all["linhas"]}
       # (15/10) + SISTEMA e LINHA do catalogo (duas colunas a mais)
       and any(l[17] == "SEM VENDA" for l in _tp_all["linhas"])
       # (09/10) tabela, desconto padrao, venda e markup sobre a venda
       and all(l[11] is None or abs(l[11] - l[9] * (1 - rn.TETO_DESCONTO
                                                    / 100)) < 0.005
               for l in _tp_all["linhas"])
       and [r_[0] for r_ in _tp_all["recortes"]][:2] == ["Com custo",
                                                         "Sem custo"]
       and [c["nome"] for c in _tp_all["colunas"]][2:6] == [
           "CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA"]
       and [c["nome"] for c in _tp_all["colunas"]][9:13] == [
           "PRC. TABELA MÉD.", "% DESC.", "PRC. VENDA MÉD.",
           "MKP VENDA %"]
       and _tp_all["kpis_de"](_tp_all["linhas"]),
       f"Farol de Markup › Todos os produtos: "
       f"{len(_tp_all['linhas']) if _tp_all else 0} produtos, com e sem venda")

# ---- visita do mes: o GridRca solto so vale para o mes em que foi salvo
import meta_nucleo as _mn_v  # noqa: E402
_dv = Path(tempfile.mkdtemp())
(_dv / "RELATORIOS" / "Visitas").mkdir(parents=True)
_gv = _dv / "RELATORIOS" / "GridRca.csv"
_gv.write_text("x")
_tv = time.mktime((2026, 9, 14, 10, 0, 0, 0, 0, -1))
os.utime(_gv, (_tv, _tv))
(_dv / "RELATORIOS" / "Visitas" / "202609.csv").write_text("x")
checar(_mn_v.achar_visitas_do_mes(_dv, "2026-10") is None
       and _mn_v.achar_visitas_do_mes(_dv, "2026-09").name == "202609.csv",
       "Visitas: mês sem arquivo não pega o GridRca de outro mês (out/26 "
       "mostrava 45 visitas de setembro)")
shutil.rmtree(_dv, ignore_errors=True)

# ---- Enviar Parcial via email (Farol de Metas)
_cfg_e = {"pessoas": [
    {"nome": "DENYLSON DA SILVA COSTA", "cod_protheus": "13"},
    {"nome": "JOCIMAR SOARES FRANCA JUNIOR", "cod_protheus": "31"},
    {"nome": "PAULO AUGUSTO MONTEIRO NOVO FILHO", "cod_protheus": "47"},
    {"nome": "PAULO UBIRATAN CURVO DE LIMA", "cod_protheus": "8"},
    {"nome": "VALMIR DE SOUZA ALVES", "cod_protheus": "49"}]}
_pn2.preencher_emails(_cfg_e)
_em = {p_["cod_protheus"]: p_.get("email") for p_ in _cfg_e["pessoas"]}
checar(_em["13"] == "denylson.costa@bapautoparts.com.br"
       and _em["31"] == "jocimar.guimaraes@bapautoparts.com.br"
       and _em["47"] == "paulo.filho@bapautoparts.com.br"
       and _em["8"] == "paulo.ubiratan@bapautoparts.com.br"
       and not _em["49"] and _pn2.email_valido(_em["13"])
       and not _pn2.email_valido("fulano@"),
       "E-mails: pré-cadastro casado pelo nome (os dois Paulos certos)")
_cfg_n = {"pessoas": [{"nome": "FULANO", "cod_protheus": "000099",
                       "cargo": "VENDEDOR", "email": "Fulano@X.com"}]}
_pn2.normalizar_pessoas(_cfg_n)
_tmp_m = Path(tempfile.mkdtemp())
(_tmp_m / "SISTEMA BAP" / "PLANNER_MESES").mkdir(parents=True)
for _arq_m in (_tmp_m / "planner_config.json",
               _tmp_m / "SISTEMA BAP" / "PLANNER_MESES" / "planner_config_2026-09.json"):
    _arq_m.write_text(json.dumps({"pessoas": [
        {"nome": "FULANO", "cod_protheus": "000099", "email": "velho@x.com"},
        {"nome": "BELTRANO", "cod_protheus": "000098", "email": "b@x.com"}]}),
        encoding="utf-8")
_n_m = _pn2.propagar_email(_tmp_m, "000099", "novo@x.com")
_lidos_m = [json.loads(a.read_text("utf-8"))["pessoas"] for a in
            (_tmp_m / "planner_config.json",
             _tmp_m / "SISTEMA BAP" / "PLANNER_MESES" / "planner_config_2026-09.json")]
checar(_cfg_n["pessoas"][0].get("email") == "fulano@x.com" and _n_m == 2
       and all(ps[0]["email"] == "novo@x.com" and ps[1]["email"] == "b@x.com"
               for ps in _lidos_m),
       "E-mail: o Planner não perde o e-mail ao abrir e grava em todos os "
       "meses")
shutil.rmtree(_tmp_m, ignore_errors=True)
_cfg_p = {"pessoas": [{"nome": "PAULO UBIRATAN CURVO DE LIMA",
                       "cod_protheus": "8"}]}
_pn2.preencher_emails(_cfg_p)
checar(_cfg_p["pessoas"][0].get("email") == "paulo.ubiratan@bapautoparts.com.br",
       "E-mail: paulo.filho não cai no Paulo Ubiratan quando o outro Paulo "
       "não está no mês")
import email_parcial as _ep  # noqa: E402
_ctx_e = rn.Contexto(AQUI)
# (10/10) a parcial do vendedor: embaixo das notas, os PEDIDOS EM ABERTO
# dele; e o cartao do resumo na 1a pagina
_vea_v = defaultdict(float)
for its_ in rn._pedidos(_ctx_e, "VEA").values():
    _vea_v[rn._cod6(its_[0].get("vend"))] += sum(i_["valor"] for i_ in its_)
_dv_ab = next((d for d in rn.destinatarios_parcial(_ctx_e)
               if d["cargo"] == "VENDEDOR" and rn._cod6(d["cod"]) in _vea_v),
              None)
if _dv_ab:
    _rab = rn.exportar_rh(_ctx_e, parcial=_dv_ab)
    _tab_ab = _rab["tabelas"][-1]
    _k_ab = next((k_ for k_ in _rab["kpis"]
                  if k_["rotulo"] == "Pedidos em aberto"), None)
    checar(_tab_ab["titulo"].startswith("Pedidos em aberto")
           and _rab["tabelas"][-2]["titulo"].startswith("Notas fiscais")
           and all(l_[4] == rn._cod6(_dv_ab["cod"]) for l_ in _tab_ab["linhas"])
           and abs(sum(l_[7] for l_ in _tab_ab["linhas"])
                   - _vea_v[rn._cod6(_dv_ab["cod"])]) < 0.01
           and _k_ab and _k_ab["valor"] == rn.moeda(
               _vea_v[rn._cod6(_dv_ab["cod"])]),
           f"Parcial do vendedor: pedidos em aberto embaixo das notas "
           f"({len(_tab_ab['linhas'])}) e cartão do resumo na 1a página")
_dest = rn.destinatarios_parcial(_ctx_e)
# (05/11, Alexandre) vendedor inativo no Planner e sem nada realizado no mes
# nao aparece na Remuneracao Variavel; a coluna da regra virou "OBS.:"
checar(rn._inativo_sem_nada({"vendedor_ativo": False, "realizado": 0,
                             "positivados": 0, "visitas_realizadas": 0})
       and not rn._inativo_sem_nada({"vendedor_ativo": False,
                                     "realizado": 1500.0})
       and not rn._inativo_sem_nada({"vendedor_ativo": True})
       and '"OBS.:"' in (AQUI / "bap_visual.py").read_text("utf-8")
       and '"REGRA APLICADA"' not in (AQUI / "bap_visual.py").read_text(
           "utf-8"),
       "Remuneração Variável: inativo no Planner sem nada no mês fora da "
       "tabela; coluna OBS.:")
# (29/10, Alexandre) META RH APENAS no Exportar para o RH, no e-mail e na
# parcial de RV: la ela aparece (cartao e colunas); fora dela, nao
_rrh = rn.exportar_rh(_ctx_e)
_v29 = next((d for d in _dest if d["cargo"] == "VENDEDOR"), None)
_rp29 = rn.exportar_rh(_ctx_e, parcial=_v29) if _v29 else None
_cols29 = [c_["nome"] for t_ in (_rp29 or {}).get("tabelas", [])
           for c_ in t_["colunas"]]
_rm29 = rn.montar("vc_meta", AQUI)
_cols_m29 = [c_["nome"] for t_ in _rm29["tabelas"] for c_ in t_["colunas"]
             if t_.get("titulo") != "Acomp. RH"]
checar(rn._COM_RH[0] is False
       and any("RV" in c_["nome"] for t_ in _rrh["tabelas"]
               for c_ in t_["colunas"])
       and (_rp29 is None or ("FAT. META RH" in _cols29
                              and "RV TOTAL" in _cols29
                              and "Faturamento · meta RH" in [
                                  k_["rotulo"] for k_ in _rp29["kpis"]]))
       and not any("RH" in n_ or n_.startswith("RV ") for n_ in _cols_m29)
       and "Faturamento · meta RH" not in [k_["rotulo"] for k_ in
                                           _rm29["kpis"]],
       "Desafio comercial em tudo; meta RH e RV só no Exportar para o RH, no "
       "e-mail e na parcial de RV (29/10)")
# (04/11, Alexandre) Farol de Metas: Por gerente/supervisor/vendedor viram
# uma aba Equipe (tabelinhas GERENTE, SUPERVISORES e VENDEDORES empilhadas,
# nome do nivel na faixa de grupo) e uma aba Acomp. RH com a meta do RH
_rt04 = rn.montar("vc_meta", AQUI, tela=True)
_tt04 = {t_.get("titulo"): t_ for t_ in _rt04["tabelas"]}
_tf04 = [t_["titulo"] for t_ in _rm29["tabelas"]]
_eq04, _rh04 = _tt04.get("Equipe"), _tt04.get("Acomp. RH")
_okeq04 = False
if _eq04 and _rh04:
    _cn04 = [c_["nome"] for c_ in _rh04["colunas"]]
    _okeq04 = (not any(k_ in _tt04 for k_ in ("Por gerente", "Por supervisor",
                                              "Por vendedor"))
               and list(_tt04).index("Acomp. RH")
               == list(_tt04).index("Equipe") + 1
               and all(t_.get("juntas_em_cima") and [j_["titulo"] for j_ in
                       t_.get("juntas", [])] == ["GERENTE", "SUPERVISORES"]
                       and t_["grupos"][0][0] == "VENDEDORES"
                       and all(j_["tabela"]["grupos"][0][0] == j_["titulo"]
                               for j_ in t_["juntas"])
                       for t_ in (_eq04, _rh04))
               and "FAT. META RH" in _cn04 and "FAT. META" not in _cn04
               and "FAT. META" in [c_["nome"] for c_ in _eq04["colunas"]]
               and not any("RH" in c_["nome"] for c_ in _eq04["colunas"])
               and all(k_ in _tf04 for k_ in ("Por gerente", "Por supervisor",
                                              "Por vendedor"))
               and "Equipe" not in _tf04 and "_equipe" not in _rm29
               # (04/11) sem rolar de lado; espaco para 2 gerentes e 4
               # supervisores
               and all(t_.get("sem_rolar_lado") for t_ in (_eq04, _rh04))
               and [j_["altura"] >= v_ for j_, v_ in
                    zip(_eq04["juntas"], (2, 4))] == [True, True])
checar(_okeq04, "Farol de Metas: na tela, aba Equipe com tabelinhas por "
       "nível (espaço para 2 gerentes e 4 supervisores, sem rolar de lado) e "
       "aba Acomp. RH com a meta do RH; fora da tela (Painel, e-mail, RV) "
       "seguem as abas por pessoa (04/11)")
# (04/11, Alexandre) "Todas abas terem esse formato, onde for possivel":
# cabe="auto" - cabe na largura com o texto inteiro (letra ate 7); se nem
# com a 7 couber, fica como era (letra pedida e barra de rolar de lado)
try:
    import tkinter as _tk04
    import bap_visual as _bv04
    _r04 = _tk04.Tk()
    _r04.geometry("1880x600+0+0")
    _c04 = [rn.col(f"COLUNA {k_}", "texto" if k_ % 3 else "moeda", 90)
            for k_ in range(22)]
    _l04 = [[f"TEXTO DA LINHA {i_} COL {k_}" if k_ % 3 else 12345.6 * i_
             for k_ in range(22)] for i_ in range(31)]
    _t04 = _bv04.Tabela(_r04, _c04, compacta=True, cabe="auto")
    _t04.pack(fill="both", expand=True)
    _t04.mostrar(_l04, [""] * 31)
    _c04b = [rn.col(f"COLUNA {k_}", "moeda", 90) for k_ in range(90)]
    _t04b = _bv04.Tabela(_r04, _c04b, compacta=True, cabe="auto")
    _t04b.pack(fill="both", expand=True)
    _t04b.mostrar([[1234567.8] * 90] * 5, [""] * 5)
    for _ in range(4):
        _r04.update()
    _s04 = sum(_t04.tv.column(f"c{j_}", "width") for j_ in _t04._visiveis)
    _ok04 = (_s04 <= _t04.tv.winfo_width()
             and not _t04._sx.winfo_ismapped()
             and _t04._tam in (7, 8, 9)
             and _t04b._tam == _t04b._tam0
             and _t04b._sx.winfo_ismapped())
    _r04.destroy()
except Exception as _e04:                               # noqa: BLE001
    _ok04 = "sem tela" in str(_e04) or "display" in str(_e04).lower()
checar(_ok04, "Tabelas dos faróis: cabem na largura sem rolar de lado onde "
       "dá (letra até 7); onde não dá, ficam como eram (04/11)")
# (03/11, Alexandre) Exportar para o RH: COMPLEMENTO e TOTAL A PAGAR
# (= RV TOTAL + COMPLEMENTO), PDF numa pagina e o Excel numa aba so com o
# cabecalho da BAP, REMUNERACAO VARIAVEL e o PERIODO
import tempfile as _tf03r  # noqa: E402
import bap_visual as _bv03r  # noqa: E402
_ok03r, _tx03r = True, []
for _t03r in _rrh["tabelas"]:
    _n03r = [c_["nome"] for c_ in _t03r["colunas"]]
    if _n03r[-3:] != ["RV TOTAL", "COMPLEMENTO", "TOTAL A PAGAR"] or any(
            l_[-2] is not None or l_[-1] != l_[-3]
            for l_ in _t03r["linhas"]):
        _ok03r = False; _tx03r.append(_t03r["titulo"])
    # (04/11) MESES DE CASA logo depois do nome (e do supervisor); no TOTAL
    # fica vazio; vendedor com admissao no Planner tem o numero
    _im03r = _n03r.index("MESES DE CASA") if "MESES DE CASA" in _n03r else -1
    if _im03r != (2 if "SUPERVISOR" in _n03r else 1) or (
            _t03r.get("total") and _t03r["total"][_im03r] is not None) or (
            "SUPERVISOR" in _n03r and _t03r["linhas"] and not any(
                isinstance(l_[_im03r], int) for l_ in _t03r["linhas"])):
        _ok03r = False; _tx03r.append("meses de casa " + _t03r["titulo"])
_d03r = Path(_tf03r.mkdtemp(prefix="smoke_rh_"))
_rrh["area"] = rn.VEN
try:
    _pdf03r = _bv03r.exportar_pdf(_rrh, _d03r / "rh.pdf")
    _pg03r = _pdf03r.read_bytes().count(b"/Type /Page\n") or \
        _pdf03r.read_bytes().count(b"/Type /Page ")
    _x03r = _bv03r.exportar_excel(_rrh, _d03r / "rh.xlsx")
    from openpyxl import load_workbook as _lw03r  # noqa: E402
    _wb03r = _lw03r(_x03r)
    _ws03r = _wb03r.worksheets[0]
    _txt03r = [str(c_.value) for r_ in _ws03r.iter_rows() for c_ in r_
               if c_.value is not None]
    if _wb03r.sheetnames != ["REMUNERAÇÃO VARIÁVEL", "MECÂNICA"] \
            or "REMUNERAÇÃO VARIÁVEL" not in _txt03r \
            or not any("SUMPRODUCT(" in t_ and "RV_VENDEDOR_FAT_DE" in t_
                       for t_ in _txt03r) \
            or not any(t_.startswith("PERÍODO: ") for t_ in _txt03r) \
            or not any(t_.startswith("=N(") for t_ in _txt03r) \
            or not any(t_ == "TOTAL GERAL A PAGAR" for t_ in _txt03r):
        _ok03r = False; _tx03r.append("excel")
except Exception as _e03r:                               # noqa: BLE001
    _ok03r = False; _tx03r.append(str(_e03r)[:80])
# (04/11, recado 20261104-0800) a RV por formula bate centavo a centavo
# com a do sistema: recalcula no LibreOffice (quando houver) em OUT e NOV
import shutil as _sh03r  # noqa: E402
import subprocess as _sp03r  # noqa: E402
_lo03r = _sh03r.which("soffice") or _sh03r.which("libreoffice")
_conf03r = "sem LibreOffice: conferência das fórmulas pulada"
if _lo03r:
    _n03r = 0
    for _m03r in ("10", "11"):
        _c03r = rn.Contexto(AQUI, params={"MÊS": _m03r, "ANO": "2026"})
        _r3 = rn.exportar_rh(_c03r)
        _r3["area"] = rn.VEN
        _dx = Path(_tf03r.mkdtemp(prefix="smoke_rv_"))
        _xx = _bv03r.exportar_excel(_r3, _dx / "rv.xlsx")
        _sp03r.run([_lo03r, "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(_dx / "c"), str(_xx)],
                   capture_output=True, timeout=180)
        try:
            _wsc = _lw03r(_dx / "c" / "rv.xlsx", data_only=True)[
                "REMUNERAÇÃO VARIÁVEL"]
        except Exception as _e3:                          # noqa: BLE001
            _ok03r = False; _tx03r.append(f"recalculo {_m03r}: {_e3}")
            continue
        _lin_xl = {}
        for _rw in _wsc.iter_rows():
            if _rw[0].value:
                _lin_xl.setdefault(_rw[0].value, _rw[0].row)
        for _t3 in _r3["tabelas"]:
            _cs3 = [c_["nome"] for c_ in _t3["colunas"]]
            _nu3 = [c_ for c_ in _cs3 if c_ not in ("NOME", "SUPERVISOR")]
            for _l3 in _t3["linhas"]:
                _rr3 = _lin_xl.get(_l3[0])
                for _k3, _nm3 in enumerate(_nu3):
                    if not (_nm3.endswith(" RV") or _nm3 in (
                            "RV TOTAL", "TOTAL A PAGAR")):
                        continue
                    _vx = _wsc.cell(_rr3, 3 + _k3).value if _rr3 else "?"
                    _n03r += 1
                    if _rr3 is None or round(float(_vx or 0), 2) != round(
                            float(_l3[_cs3.index(_nm3)] or 0), 2):
                        _ok03r = False
                        _tx03r.append(f"{_m03r} {_l3[0][:15]} {_nm3}: "
                                      f"{_l3[_cs3.index(_nm3)]} x {_vx}")
    _conf03r = f"{_n03r} células de RV recalculadas no LibreOffice = sistema"
checar(_ok03r, "Exportar para o RH: MESES DE CASA, COMPLEMENTO e TOTAL A PAGAR (RV + "
       "complemento), tudo numa página; Excel numa aba com o cabeçalho BAP, "
       "REMUNERAÇÃO VARIÁVEL e PERÍODO; aba MECÂNICA e RV por fórmula ("
       + _conf03r + ") " + "; ".join(_tx03r[:6]))
_vend_e = next((d for d in _dest if d["cargo"] == "VENDEDOR"), None)
_sup_e = next((d for d in _dest if d["cargo"] == "SUPERVISOR"), None)
if _vend_e and _sup_e:
    _rv_e = rn.exportar_rh(_ctx_e, parcial=_vend_e)
    _rs_e = rn.exportar_rh(_ctx_e, parcial=_sup_e)
    # (10/10) TOP 30 da parcial: BAIRRO e CONTATO (telefone) no PDF;
    # (15/10) PECAS de volta e a POSITIVACAO numa coluna so (SIM/NAO)
    _t30 = next((t_ for t_ in _rv_e["tabelas"]
                 if t_["titulo"] == "Top 30 clientes"), None)
    if _t30 and _t30["linhas"]:
        _pdf30 = [c_["nome"] for c_ in _t30["colunas"]
                  if not c_.get("oculta") and not c_.get("pdf_oculta")]
        _i30 = [c_["nome"] for c_ in _t30["colunas"]].index("CONTATO")
        _ip30 = [c_["nome"] for c_ in _t30["colunas"]].index("POSITIVOU")
        checar("BAIRRO" in _pdf30 and "CONTATO" in _pdf30
               and {"PEÇAS META", "PEÇAS REAL", "PEÇAS % ATING."} <=
               set(_pdf30)
               and not any(n_.startswith("POSIT. ") for n_ in _pdf30)
               and all(l_[_ip30] in ("SIM", "NÃO") for l_ in _t30["linhas"])
               and len(_t30["linhas"][0]) == len(_t30["colunas"])
               and abs(sum(c_.get("pdf_larg") or 0 for c_ in _t30["colunas"]
                           if not c_.get("oculta")
                           and not c_.get("pdf_oculta")) - rn.PDF_UTIL) < 1
               and sum(1 for l_ in _t30["linhas"]
                       if re.search(r"\d{4}", str(l_[_i30]))) > 0,
               "Parcial: Top 30 clientes com bairro e contato (telefone), "
               "PEÇAS e POSITIVOU (SIM/NÃO), na largura da página")
    _tit_v = [t_["titulo"] for t_ in _rv_e["tabelas"]]
    _ven_s = next((t_ for t_ in _rs_e["tabelas"]
                   if t_["titulo"] == "Por vendedor"), {"linhas": []})
    _tmp_e = Path(tempfile.mkdtemp())
    _it_e = _ep.preparar(AQUI, {}, [dict(_vend_e, email="teste@x.com")],
                         pasta=_tmp_e)
    _eml = _ep.gravar_eml(_it_e[0], _tmp_e / "t.eml")
    checar(_tit_v[:10] == ["Por gerente", "Por supervisor", "Por vendedor",
                           "Por UF", "Por categoria", "Por segmento",
                           "Por família da peça", "Top 30 cidades",
                           "Top 30 bairros", "Top 30 clientes"]
           and _tit_v[10].startswith("Notas fiscais do mês")
           # 06/10: o codigo do supervisor e o do vendedor em cada nota
           and [c["nome"] for c in _rv_e["tabelas"][10]["colunas"]][2:4]
           == ["CÓD. SUPERVISOR", "CÓD. VENDEDOR"]
           and all(l[3] == rn._cod6(_vend_e["cod"])
                   for l in _rv_e["tabelas"][10]["linhas"])
           and _rv_e["tabelas"][10].get("pdf_quebra_antes")
           and [l_[3] or 0 for l_ in next(
               t_ for t_ in _rv_e["tabelas"]
               if t_["titulo"] == "Top 30 cidades")["linhas"][:-1]] == sorted(
               [l_[3] or 0 for l_ in next(
                   t_ for t_ in _rv_e["tabelas"]
                   if t_["titulo"] == "Top 30 cidades")["linhas"][:-1]],
               reverse=True)
           and len(next(t_ for t_ in _rv_e["tabelas"]
                        if t_["titulo"] == "Top 30 cidades")["linhas"]) <= 31
           and all(t_.get("pdf_pagina") for t_ in _rv_e["tabelas"]
                   if t_["titulo"].startswith("Top "))
           and True
           and _rv_e["resumo_desafio"][0] == "Desafio Fat. Comercial"
           and [x[0] for x in _rv_e["resumo_pessoa"]] == [
               "Meta Fat.", "Positivação", "Visita"]
           and len(_rv_e["resumo_pessoa"][0]) == 9
           and all(x[4].startswith("R$ ") and "," in x[4]
                   for x in _rv_e["resumo_pessoa"])
           and not any("RV" in k["rotulo"] for k in _rv_e["kpis"])
           and _vend_e.get("cc") is not None
           and len(next(t_ for t_ in _rv_e["tabelas"]
                        if t_["titulo"] == "Por vendedor")["linhas"]) == 1
           and all(rn.norm_nome(l[2]).split()[0]
                   == rn.norm_nome(_sup_e["nome"]).split()[0]
                   for l in _ven_s["linhas"])
           # o CODIGO DE VENDA na frente do nome (06/10)
           and all(len(str(l[0])) == 6 and str(l[0]).isdigit()
                   for l in _ven_s["linhas"])
           and f"CÓD. {rn._cod6(_vend_e['cod'])}" in _rv_e["eyebrow"]
           and _rv_e.get("resumo_pessoa") and _eml.stat().st_size > 1000
           and b"X-Unsent: 1" in _eml.read_bytes(),
           f"Parcial por e-mail: vendedor só a linha dele, supervisor com a "
           f"equipe, .eml pronto ({len(_dest)} destinatários)")
    shutil.rmtree(_tmp_e, ignore_errors=True)
    _seg_p = next(t_ for t_ in _rv_e["tabelas"] if t_["titulo"] == "Por segmento")
    _fam_p = next(t_ for t_ in _rv_e["tabelas"]
                  if t_["titulo"] == "Por família da peça")
    _cat_p = next(t_ for t_ in _rv_e["tabelas"]
                  if t_["titulo"] == "Por categoria")
    _vl_p = next(t_ for t_ in _rv_e["tabelas"]
                 if t_["titulo"] == "Por vendedor")["linhas"][0]
    _meta_rh_p = _vl_p[5]          # [0] = o codigo de venda (06/10)
    checar(abs(_seg_p["total"][3] - _meta_rh_p) < 1
           and abs(_fam_p["total"][2] - _meta_rh_p) < 1
           and abs(_cat_p["total"][2] - _meta_rh_p) < 1
           and abs(_cat_p["total"][1] - _vl_p[4]) < 1
           and {l[0] for l in _cat_p["linhas"]} >= {
               "PEÇAS LINHA LEVE", "PEÇAS LINHA PESADA", "PEÇAS LINHA MOTO",
               "BATERIAS", "LUBRIFICANTES", "QUÍMICOS", "PNEUS",
               "ACESSÓRIOS"}
           and [l[1] or 0 for l in _cat_p["linhas"]] == sorted(
               [l[1] or 0 for l in _cat_p["linhas"]], reverse=True)
           and abs(_seg_p["total"][2] - _vl_p[4]) < 1
           and _seg_p["pdf"]["cab"] < 6,
           f"Parcial: segmento, categoria e família somam a meta do "
           f"vendedor (categorias da maior meta para a menor) - meta RH "
           f"({_meta_rh_p:,.0f}), letra menor no cabeçalho")

# ---- TOP 30 clientes (Farol e parcial)
_t30 = next((t_ for t_ in _rm["tabelas"] if t_["titulo"] == "Top 30 clientes"),
            None)
if _t30 is not None:
    _ctx30 = rn.Contexto(AQUI)
    _comp30 = rn.meta_do_periodo(_ctx30)["competencia"]
    _f6 = rn._fat_6_meses(_ctx30, _comp30)
    _v6 = [l[7] for l in _t30["linhas"]]
    _com6 = [v for v in _v6 if v > 0]
    checar(len(_t30["linhas"]) <= 30
           and [c["nome"] for c in _t30["colunas"]][:8] == [
               "CLIENTE", "CIDADE", "SEGMENTO", "UF", "BAIRRO", "SUPERVISOR",
               "VENDEDOR", "FAT. 6 MESES"]
           and len(_t30["linhas_filtro"]) >= len(_t30["linhas"])
           and {id(l) for l in _t30["linhas_filtro"][:30]} == {
               id(l) for l in _t30["linhas"]}
           and callable(_t30["total_de"])
           and abs(_t30["total_de"](_t30["linhas"])[7]
                   - _t30["total"][7]) < 0.01
           and sorted(_com6, reverse=True)[:len(_com6)] == sorted(
               [l[7] for l in _t30["linhas_filtro"][:30] if l[7] > 0],
               reverse=True)
           and [l[8] or 0 for l in _t30["linhas"]] == sorted(
               [l[8] or 0 for l in _t30["linhas"]], reverse=True)
           and (len(_t30["linhas"]) == 30 or len(_com6) < 30)
           and all(abs(_f6.get(l[0].split(" - ")[0], 0) - l[7]) < 0.01
                   for l in _t30["linhas"]),
           f"Top 30 clientes: maior faturamento em 6 meses, depois o limite "
           f"({len(_com6)} com faturamento)")

# ---- a CATEGORIA BAP de cada produto
import meta_nucleo as _mnk  # noqa: E402
checar([_mnk.categoria_bap(*x) for x in (
    ("PEÇAS - LINHA LEVE", "980 - BAP"), ("PEÇAS - LINHA PESADA", "980 - BAP"),
    ("PEÇAS - LINHA LEVE", "7980 - BAP MOTOS"), ("PNEU", "7980 - BAP MOTOS"),
    ("BATERIA", "980 - BAP"), ("OLEO", "5980 - BAP LUB"),
    ("", "6980 - BAP FILTROS"), ("", ""))] == [
        "LINHA LEVE", "LINHA PESADA", "LINHA MOTO", "PNEU", "BATERIA",
        "LUBRIFICANTES", "LINHA LEVE", "OUTROS"],
       "Categoria BAP: leve, pesada, moto (fornecedor BAP MOTOS), pneu, "
       "bateria e lubrificantes")
_cl_k = [{"cod_cliente": "1", "meta": 1000.0, "segmento": "A"},
         {"cod_cliente": "2", "meta": 500.0, "segmento": "A"}]
_lk = _mnk._metas_por_categoria(_cl_k, {"1": {"PNEUS": 30.0,
                                               "BATERIAS": 70.0}})
checar({x["familia"] for x in _lk} == set(_mnk.categorias_do_catalogo())
       and _lk[0]["familia"] == "BATERIAS"
       and abs(sum(x["meta"] for x in _lk) - 1500) < 0.01
       and abs(_cl_k[1]["meta_categoria"]["BATERIAS"] - 350) < 0.01,
       "Categoria (Catálogo BAP 2026): meta do cliente x mix do M3M (sem "
       "compra: o do segmento), todas sempre")
# (15/10) a classificacao do Catalogo BAP 2026: ESTOQUE_BAP > base v8 >
# regra antiga convertida
import catalogo_bap as _cbk  # noqa: E402
_ck = _cbk.Catalogo(AQUI)
_ctx_k = rn.Contexto(AQUI)
_cods_k = {it_["cod"] for it_ in _ctx_k.tabela["itens"]}
checar(_ck and set(_cbk.CAMPOS) <= set(
    _cbk.regra_antiga("LINHA MOTO", "VELA IGNICAO MOTOCICLETA"))
       and _cbk.regra_antiga("PNEU", "PNEU X")["CATEGORIA"] == "PNEUS"
       and _cbk.regra_antiga("BATERIA", "BATERIA 60")["CATEGORIA"]
       == "BATERIAS"
       and _cbk.regra_antiga("LINHA MOTO", "X")["LINHA"] == "MOTO"
       and {_ctx_k.categoria_bap(c_) for c_ in _cods_k} <= set(
           _cbk.ORDEM_CATEGORIA)
       and {_ctx_k.linha(c_) for c_ in _cods_k} <= set(_cbk.ORDEM_LINHA)
       and sum(1 for c_ in _cods_k if _ctx_k.sistema(c_) != "OUTROS")
       > 0.9 * len(_cods_k),
       f"Catálogo BAP 2026: categoria/sistema/família/linha de "
       f"{len(_cods_k)} produtos (estoque {len(_ck.estoque)}, base "
       f"{len(_ck.base)})")

# ---- a meta COMERCIAL: meses de casa, piso e a meta do gerente
import meta_nucleo as _mnc  # noqa: E402
_rep = _mnc._repartir(1_000_000, {"a": 400, "b": 100, "c": 100},
                      {"a": 120000, "b": 120000, "c": 120000})
_rep2 = _mnc._repartir(300_000, {"a": 4, "b": 1, "c": 1},
                       {"a": 120000, "b": 120000, "c": 120000})
_par_c = _mnc.parametros_novos()
checar(abs(sum(_rep.values()) - 1e6) < 1 and min(_rep.values()) >= 119999
       and abs(sum(_rep2.values()) - 3e5) < 1
       and [_mnc.meta_do_mes_de_casa(_par_c, n) for n in (1, 2, 3, 4, 5)]
       == [60000, 80000, 100000, 120000, None]
       and _par_c["teto_rh_vendedor"] == 120000,
       "Meta comercial: piso de 120 mil sem passar da meta do gerente; "
       "1º a 4º mês de casa = 60/80/100/120 mil")
_cfg_casa = {"pessoas": [{"nome": "NOVATO", "cod_protheus": "000777",
                          "cargo": "VENDEDOR", "meses_de_casa": "2"}]}
_pn2.normalizar_pessoas(_cfg_casa)
checar(_cfg_casa["pessoas"][0].get("meses_de_casa") == 2
       and _mnc.meses_de_casa(_cfg_casa["pessoas"][0]) == 2,
       "Planner: o mês de casa fica no cadastro do mês")

# ---- VISITAS: o GridRca da Maxima dia a dia e o Farol de Visita (06/10)
import tempfile as _tfv  # noqa: E402
import visitas_nucleo as _vn  # noqa: E402
_GRID = (_vn.CABECALHO_GRID + "\n"
         "147509;ANDERSON LIMA SILVA;x;0101006;000013;08:57:45;16:57:55;"
         "17:56:51;00:12:23;00:28:52;x;44;2 / 4,55%;20 / 45,45%;22;0 / 0%;"
         "0 / 0%;0;0%;0;0;100;0;0;0;10504,81;0;0;138,5;R$ 0,00;435,7;R$ 0,00;"
         "1;0,12 %;True;4.056.0\n"
         "999999;\"FULANO FORA DA EQUIPE   \";x;0101001;000040;00:00:00;"
         "00:00:00;00:00:00;00:00:00;00:00:00;x;0;0 / 0%;0 / 0%;0;0 / 0%;"
         "0 / 0%;0;0%;0;0;0;0;0;0;0;0;0;0;R$ 0,00;0;R$ 0,00;0;0;False;\" - \"\n")
with _tfv.TemporaryDirectory() as _dv:
    _dv = Path(_dv)
    (_dv / "planner_config.json").write_text(json.dumps({"pessoas": [
        {"cod_protheus": "000034", "cod_maxima": "000034",
         "nome": "ANDERSON LIMA SILVA", "cargo": "VENDEDOR",
         "responde_a": "000013"},
        {"cod_protheus": "000013", "cod_maxima": "000013",
         "nome": "DENYLSON DA SILVA COSTA", "cargo": "SUPERVISOR"},
        {"cod_protheus": "000099", "cod_maxima": "999999",
         "nome": "FULANO FORA DA EQUIPE", "cargo": "VENDEDOR",
         "ativo": False}]}),
        "utf-8")
    _pdv = _vn.pasta_diario(_dv)
    _pdv.mkdir(parents=True)
    for _d in ("20261001", "20261002"):
        (_pdv / f"{_d}.csv").write_text(_GRID, "utf-8")
        _vn.anotar_baixado(_dv, _d, datetime(2026, 10, 3, 8, 0))
    (_pdv / "20261003.csv").write_text(_GRID, "utf-8")
    _vn.anotar_baixado(_dv, "20261003", datetime(2026, 10, 3, 18, 0))
    _rg = _vn.registros(_dv)
    _a = [l for l in _rg if l["cod"] == "147509"][0]
    checar(len(_rg) == 6 and _a["vendedor"] == "ANDERSON LIMA SILVA"
           and _a["supervisor"] == "DENYLSON DA SILVA COSTA"
           and _a["visitas"] == 22 and _a["vis_agenda"] == 2
           and _a["vis_fora"] == 20 and _a["tma"] == 28 * 60 + 52
           and _a["primeiro"] == 8 * 3600 + 57 * 60 + 45
           and abs(_a["venda"] - 10504.81) < 0.01,
           "Visitas: lê o GridRca (agenda, TMA, 1º cliente, venda) e casa "
           "com o Planner pelo nome")
    checar(_vn.dia_fechado(_dv, date(2026, 10, 2))
           and not _vn.dia_fechado(_dv, date(2026, 10, 3)),
           "Visitas: dia baixado no mesmo dia não está fechado")
    _x1 = _vn.atualizar_acompanhamento(_dv)
    (_pdv / "20261001.csv").write_text(_GRID.replace(";22;", ";99;"), "utf-8")
    _x2 = _vn.atualizar_acompanhamento(_dv)
    import openpyxl as _oxv  # noqa: E402
    _wbv = _oxv.load_workbook(_vn.arquivo_acompanhamento(_dv))
    _vis = [r_[16] for r_ in _wbv.active.iter_rows(min_row=2,
                                                    values_only=True)]
    checar(_x1["novas"] == 4 and _x2["novas"] == 0 and 99 not in _vis
           and len(_vis) == 4,
           "Visitas: o Excel só ACRESCENTA dia fechado (linha gravada não "
           "muda)")
    _rv = rn.montar("vc_visitas", _dv, hoje=date(2026, 10, 3),
                    params={"MÊS": 10, "ANO": 2026})
    _tv = {t["titulo"]: t for t in _rv["tabelas"]}
    _lv = [l for l in _tv["Por vendedor"]["linhas"] if l[1].startswith("AND")]
    _nv_ = [c_["nome"] for c_ in _tv["Por vendedor"]["colunas"]]
    _idv = _nv_.index("VISIT.")
    checar({"Por supervisor", "Por vendedor", "Dia a dia"} <= set(_tv)
           and set(_tv) <= {"Por supervisor", "Por vendedor", "Dia a dia",
                            "Aderência dia a dia", "Cliente a cliente"}
           and _lv and _lv[0][_idv] == 99 + 22 + 22
           and _rv["kpis"][0]["rotulo"] == "Visitas"
           and _tv["Por vendedor"]["total_de"](_tv["Por vendedor"]["linhas"])
           [_idv] == 143
           # (22/10) as colunas da Parcial Visitas na linha do vendedor
           and _nv_[5:8] == ["META", "VISIT.", "% META"]
           and "% ADER. ROTA NOVA" not in _nv_
           and any("parcial" in a for a in _rv["avisos"]),
           "Farol de Visita: supervisor, vendedor e dia a dia, total que "
           "segue o filtro, aviso do dia parcial")
    checar([l[1] for l in _tv["Por vendedor"]["linhas"]]
           == ["ANDERSON LIMA SILVA"]
           and "DATA" in [rn.nome_filtro(f) for f in _tv["Dia a dia"]["filtros"]]
           and _rv.get("painel") and _rv.get("painel_titulo")
           == "Resumo gerencial"
           and {b["tipo"] for b in _rv["painel"]["blocos"]} == {"barras"}
           and [b["col"] for b in _rv["painel"]["blocos"]] == [0, 1] * 8
           and [b["grafico"]["titulo"].split(" dia a dia")[0]
                for b in _rv["painel"]["blocos"] if b["col"] == 0]
           == ["Visitas", "Início do 1º cliente", "% Aderência ao Planner",
               "Último cliente", "Jornada (1º ao último cliente)",
               "TMD (deslocamento)", "TMA (atendimento)", "Km rodado"]
           and all("mês a mês" in b["grafico"]["titulo"]
                   for b in _rv["painel"]["blocos"] if b["col"] == 1),
           "Farol de Visita: só vendedor ATIVO do Planner (inativo e "
           "supervisor fora), filtro por data, Resumo gerencial com 8 pares "
           "dia a dia (esquerda) x mês a mês (direita)")
# ---- (18/10) ADERENCIA AO PLANNER: o cliente da Maxima com 7 digitos
# (loja sem o zero), a rota em vigor no dia (o envio que bate com a agenda;
# empate = o ultimo antes do dia) e o sabado-deposito fora da agenda
import visitas_nucleo as _vna  # noqa: E402
_r1 = {"arquivo": "A", "quando": datetime(2026, 10, 5, 9, 30),
       "prog": {("000034", date(2026, 10, 6)): {"01081104", "00002801"}},
       "deposito": {date(2026, 10, 3)}}
_r2 = {"arquivo": "B", "quando": datetime(2026, 10, 6, 10, 51),
       "prog": {("000034", date(2026, 10, 6)): {"00009901"}},
       "deposito": set()}
checar(_vna.chave_cliente8("0108114") == "01081104"
       and _vna.chave_cliente8("01081104") == "01081104"
       and _vna._escolher_rota([_r1, _r2], date(2026, 10, 6), "000034",
                               {"01081104"})["arquivo"] == "A"
       and _vna._escolher_rota([_r1, _r2], date(2026, 10, 7), "000034",
                               set())["arquivo"] == "B"
       and _vna._escolher_rota([_r2], date(2026, 10, 5), "000034",
                               set()) is None,
       "Aderência: cliente de 7 dígitos casa com a rota do Planner; vale o "
       "envio do Planner que chegou ao vendedor (empate: o último antes do "
       "dia)")
# ---- (18/10) DATA DE ADMISSAO: o mes de casa sai dela (20/10: de out/26 em
# diante; setembro e antes: o escrito) e a proporcao do 1o mes pelos dias
# uteis
import planner_nucleo as _pna  # noqa: E402
import meta_nucleo as _mna  # noqa: E402
_pa = {"cod_protheus": "000099", "meses_de_casa": 1,
       "data_admissao": "01/08/2026"}
with _tfv.TemporaryDirectory() as _da:
    _ca = Path(_da) / "planner_config_2026-11.json"
    _ca.write_text(json.dumps({"mes": "2026-11", "feriados": ["2026-11-02"],
                               "pessoas": [
                                   dict(_pa, cargo="VENDEDOR", nome="X"),
                                   {"cod_protheus": "000098", "nome": "Y",
                                    "cargo": "VENDEDOR",
                                    "data_admissao": "2026-11-16"}]}),
                   encoding="utf-8")
    _dd = {"clientes": []}
    _mna.aplicar_equipe_do_mes(_dd, _ca)
checar(_pna.mes_de_casa_no_mes(_pa, "2026-09") == 1
       and _pna.mes_de_casa_no_mes(_pa, "2026-10") == 3
       and _pna.mes_de_casa_no_mes(_pa, "2026-11") == 4
       and _pna.mes_de_casa_no_mes({"data_admissao": "2026-12-01"},
                                   "2026-11") == 0
       and abs(_pna.fracao_do_mes({"data_admissao": "2026-11-16"}, "2026-11",
                                  ["2026-11-02"]) - 11 / 20) < 1e-9
       and _pna.fracao_do_mes({"data_admissao": "2026-09-16"},
                              "2026-09") == 1.0
       and _dd["meses_de_casa"].get("000099") == 4
       and _dd["meses_de_casa"].get("000098") == 1
       and abs(_dd["fracao_de_casa"].get("000098", 0) - 11 / 20) < 1e-9,
       "Admissão: mês de casa pela data de admissão de out/26 em diante "
       "(setembro e antes com o escrito) e 1º mês proporcional aos dias "
       "úteis")
import visitas_maxima as _vm  # noqa: E402
with _tfv.TemporaryDirectory() as _dv2:
    _dias, _meses = _vm.plano(_dv2, date(2026, 9, 29), date(2026, 10, 9),
                              hoje=date(2026, 10, 6))
    checar(_dias[0] == date(2026, 9, 29) and _dias[-1] == date(2026, 10, 6)
           and _meses == [(2026, 9), (2026, 10)]
           and _vm.periodo_padrao(date(2026, 10, 1)) ==
           (date(2026, 9, 1), date(2026, 10, 1))
           and "senha" not in json.dumps(_vm.ler_config()).lower(),
           "Atualizar visitas: plano dia a dia até hoje, um arquivo por mês; "
           "a senha nunca vai para o config")

# ---- e-mail da parcial: a lista do PDF na ordem do PDF e a moldura (06/10)
import email_parcial as _epo  # noqa: E402
_rel_o = {"tabelas": [{"titulo": t} for t in (
    "Por gerente", "Por supervisor", "Por vendedor", "Por UF", "Por categoria",
    "Por segmento", "Por família da peça", "Top 30 cidades", "Top 30 bairros",
    "Top 30 clientes", "Notas fiscais do mês (2)")]}
_ord = [o for o, _ in _epo._no_pdf(_rel_o)]
checar(_ord == ["Cartões", "Por gerente / supervisor / vendedor", "Por UF",
                "Por categoria", "Por segmento", "Por família da peça",
                "Top 30 cidades / Top 30 bairros", "Top 30 clientes",
                "Notas fiscais do mês (2)"],
       "E-mail da parcial: 'Informações contidas no PDF' na ordem do PDF")


# ---- (06/10) rota da semana por e-mail, contato e cliente da rota ATIVO
import email_rota as _er  # noqa: E402
import planner_nucleo as _pn9  # noqa: E402
checar(_pn9.telefone_de("092", "32373321") == "(92) 3237-3321"
       and _pn9.telefone_de(92.0, "9292156663") == "(92) 9215-6663"
       and _pn9.telefone_de("99", "9999999") == ""
       and _pn9.telefone_de("92", "984399836") == "(92) 98439-9836"
       and _pn9.telefone_de("929", "95350640") == "(92) 99535-0640"
       and _pn9.contato_do_cliente({"CONTATO": "CLOVES",
                                    "TELEFONE": "(92) 3237-3321"})
       == "CLOVES · (92) 3237-3321",
       "Telefone da base: (DDD) número, sem DDD repetido nem número falso")
# (06/10) INATIVO so a mao (aba Base cliente): sai da rota; (20/10) no
# .json vai ATIVO com o vendedor padrao (o vendedor deixa de ver)
_r9 = _pn9.gerar_rota(_cfg_r, _cli_r)
_ch9 = _r9[0]["CHAVE_CLIENTE"]
_n_pad9 = sum(1 for x in _pn9.base_protheus(_cfg_r, _cli_r)
              if x["A1_VEND"] == _pn9.vendedor_padrao(_cfg_r))
_pn9.inativar_clientes(_cfg_r, [_ch9])
_r9b = _pn9.gerar_rota(_cfg_r, _cli_r)
_bp9x = {f"{x['A1_COD']}-{x['A1_LOJA']}": x
         for x in _pn9.base_protheus(_cfg_r, _cli_r)}
_bp9 = {k: x["STATUS"] for k, x in _bp9x.items()}
_c9 = next(c for c in _cli_r if c["CHAVE_CLIENTE"] == _ch9)
_k9 = f"{_c9['COD_CLIENTE'].zfill(6)}-{(_c9['LOJA'] or '').zfill(2)}"
checar(_ch9 not in {r["CHAVE_CLIENTE"] for r in _r9b}
       and _bp9.get(_k9) == "ATIVO"
       and set(_bp9.values()) <= {"ATIVO", "INATIVO"}
       and _bp9x[_k9]["A1_VEND"] == _pn9.vendedor_padrao(_cfg_r)
       and _bp9x[_k9]["SUPERVISOR"] == _pn9.supervisor_padrao(_cfg_r)
       and sum(1 for x in _pn9.base_protheus(_cfg_r, _cli_r)
               if x["A1_VEND"] == _pn9.vendedor_padrao(_cfg_r))
       == _n_pad9 + 1
       and _pn9.status_de(200, _cfg_r["parametros"]) == "CHURN 90+"
       and "INATIVO" not in _pn9.STATUS,
       "Cliente inativado no Planner: sai da rota e vai no .json ATIVO "
       "com o vendedor/supervisor padrão; mais de 90 dias sem compra é "
       "CHURN 90+")
_pn9.inativar_clientes(_cfg_r, [_ch9], False)
checar(_ch9 in {r["CHAVE_CLIENTE"] for r in _pn9.gerar_rota(_cfg_r, _cli_r)}
       and "clientes_inativos" not in _cfg_r,
       "Reativar devolve o cliente à rota")
_rb9 = rn.montar("vc_base", AQUI)
_tc9 = next(t for t in _rb9["tabelas"] if t["titulo"] == "Clientes")
checar("CONTATO" in [c["nome"] for c in _tc9["colunas"]]
       and {"VENDEDOR PLANNER", "SUPERVISOR PLANNER", "VENDEDOR PROTHEUS",
            "SUPERVISOR PROTHEUS"} <= {c["nome"] for c in _tc9["colunas"]},
       "Farol de Clientes › Clientes tem CONTATO e vendedor/supervisor do "
       "Planner e do Protheus")
_seg9 = _er.semana_de(date(2026, 10, 6))
checar(_seg9 == date(2026, 10, 5)
       and _er.semana_de(date(2026, 10, 10)) == date(2026, 10, 12),
       "Rota da semana: segunda da semana (sábado/domingo: a próxima)")
_rota9 = _er.rota_da_semana(AQUI, _seg9)
_pes9 = _er.destinatarios_rota(AQUI, _seg9, _rota9)
with _tfv.TemporaryDirectory() as _dr9:
    _it9 = _er.preparar(AQUI, _pes9, _seg9, _rota9, pasta=_dr9)
    _sup9 = [i for i in _it9 if i["pessoa"]["cargo"] == "SUPERVISOR"]
    _ven9 = [i for i in _it9 if i["pessoa"]["cargo"] == "VENDEDOR"]
    _dias9 = {r["DATA"].weekday() for ls in _rota9["linhas"].values()
              for r in ls}
    checar(_ven9 and all(len(i["anexos"]) == 1 for i in _ven9)
           and all(len(i["anexos"]) == len(i["pessoa"]["vendedores"])
                   for i in _sup9)
           and all(not i["pessoa"]["cc"] for i in _it9)
           and all(a.exists() for i in _it9 for a in i["anexos"])
           and _dias9 <= {0, 1, 2, 3, 4},
           f"Rota da semana: {len(_ven9)} vendedor(es) com o PDF dele, "
           f"{len(_sup9)} supervisor(es) com um PDF por vendedor, sem cópia,"
           f" só de segunda a sexta")
    _rel9 = _er.rel_do_vendedor(next(iter(_rota9["linhas"].values())), "X",
                                "", _seg9)
    checar([c["nome"] for c in _rel9["tabelas"][0]["colunas"]] ==
           [n for n, _t, _l in _er.COLUNAS_PDF]
           and "CONTATO (TELEFONE)" in [n for n, _t, _l in _er.COLUNAS_PDF],
           "PDF da rota: COD. CLIENTE ... CURVA e CONTATO (TELEFONE)")
    _pdfs9 = _er.gerar_pdfs(AQUI, list(_rota9["linhas"])[:2], _seg9, _rota9,
                            pasta=Path(_dr9) / "ver")
    checar(len(_pdfs9) == 2 and all(x.exists() and x.stat().st_size > 2000
                                    for x in _pdfs9),
           "Ver PDF (Farol Roteirização): um PDF por vendedor, sem enviar")
    # (27/10, Alexandre) o link do Maps no PDF: o vendedor so clica e vai
    checar(_er.link_maps({"LATITUDE": -3.1, "LONGITUDE": -60.02,
                          "PRECISAO_GEO": "endereco"}).endswith(
               "destination=-3.100000,-60.020000")
           and "search/?api=1&query=RUA%20A%2010" in _er.link_maps(
               {"LATITUDE": -3.1, "LONGITUDE": -60.0, "PRECISAO_GEO": "bairro",
                "ENDERECO": "RUA A", "NUMERO": "10", "CIDADE": "MANAUS"})
           and all(b"google.com/maps" in x.read_bytes() for x in _pdfs9
                   if x.suffix.lower() == ".pdf"),
           "PDF da rota: link do Google Maps em cada cliente (coordenada do "
           "endereço; sem ela, busca pelo endereço)")
    _rp9 = rn.montar("vc_planner", AQUI)
    _tp9 = next(t for t in _rp9["tabelas"] if t["titulo"] == "Por cliente")
    _fn9 = [rn.nome_filtro(f) for f in _tp9["filtros"]]
    _is9 = [c["nome"] for c in _tp9["colunas"]].index("SEMANA")
    checar("SEMANA" in _fn9 and "DIA" in _fn9
           and any(";" in str(l[_is9]) for l in _tp9["linhas"]),
           "Farol Roteirização › Por cliente: filtros SEMANA e DIA")
    _rr9 = rn.montar("vc_planner", AQUI)
    _tp_9 = {b_["tipo"] for b_ in _rr9["painel"]["blocos"]}
    checar(_rr9.get("painel_titulo") == "Resumo gerencial"
           and {"insights", "hbarras", "barras"} <= _tp_9
           and [k["rotulo"] for k in _rr9["kpis"]][:3] == [
               "Cobertura da carteira", "Visitas no mês",
               "Ocupação da agenda"]
           and _rr9["insights_rota"]
           and [t_ for t_, _x in _rr9["insights_rota"]] == sorted(
               [t_ for t_, _x in _rr9["insights_rota"]],
               key=lambda t_: {"alerta": 0, "atencao": 1, "ok": 2,
                               "info": 3}[t_]),
           "Farol Roteirização: Resumo gerencial com cobertura, ocupação, "
           "positivação e 'O que a rota diz' (do mais grave ao informativo)")
    # (27/10, Alexandre) OCUPACAO: a capacidade so conta os dias uteis em
    # que o vendedor tem rota (quem entrou no meio do mes nao conta antes)
    _tc9 = next((t for t in _rr9["tabelas"] if t["titulo"] == "Calendário"),
                None)
    if _tc9 and _tc9["linhas"]:
        _l9 = [l for l in _tc9["linhas"] if l[0] and l[0].weekday() < 4]
        _v9, _d9 = _l9[0][4], _l9[0][0]
        _so9 = [l for l in _l9 if l[4] == _v9 and l[0] == _d9]
        _teto9 = int((_tc9["calendario"]["tetos"].get(_v9)
                      or _tc9["calendario"]["teto_padrao"]) or 1)
        _oc9 = next(k for k in _tc9["kpis_de"](_so9)
                    if k["rotulo"] == "Ocupação")
        _ocv9 = next(x for x in _rr9["kpis"]
                     if x["rotulo"] == "Ocupação da agenda")
        checar(_oc9["valor"] == rn.p(100.0 * len(_so9) / _teto9)
               and "dias com rota" in _oc9["detalhe"]
               and "com rota" in _ocv9["detalhe"],
               "Ocupação: capacidade só nos dias úteis em que o vendedor "
               "tem rota (1 vendedor, 1 dia = visitas ÷ teto do dia)")
    if _it9:
        _eml9 = _epo.gravar_eml(dict(_it9[0], anexos=_it9[0]["anexos"][:1] * 2),
                                Path(_dr9) / "x.eml")
        checar(_eml9.read_bytes().count(b"Content-Disposition: attachment")
               == 2, "E-mail com vários PDFs em anexo (.eml)")

# ---- (06/10) LATITUDE/LONGITUDE e a rota pelo caminho mais curto
import geografia as _geo9  # noqa: E402
import geocodificar as _gc9  # noqa: E402
_pts = [(-3.10, -60.00), (-3.10, -60.30), (-3.10, -60.10), (-3.10, -60.20)]
checar(_geo9.caminho_mais_curto(_pts, (-3.10, -59.90)) == [0, 2, 3, 1],
       "Caminho mais curto: pontos numa linha saem em sequência")
_cc = {"CHAVE_CLIENTE": "000001-01", "ENDERECO": "AV AUTAZ MIRIM 1020",
       "NUMERO": "", "BAIRRO": "CIDADE DE DEUS", "CIDADE": "MANAUS",
       "UF": "AM"}
_feito = []


def _fake(params):
    _feito.append(params)
    if "street" in params and params["street"].startswith("1020 AVENIDA"):
        return (-3.05, -59.95)
    return None


_l = _gc9.localizar(_cc, consultar=_fake, esperar=lambda s: None)
checar(_l == (-3.05, -59.95, "endereco")
       and _feito[0]["street"] == "1020 AVENIDA AUTAZ MIRIM",
       "Geocodificar: AV vira AVENIDA, número da porta, ponto na cidade")
checar(_gc9.localizar(_cc, consultar=lambda p_: (-23.5, -46.6),
                      esperar=lambda s: None)[0] is None,
       "Geocodificar: ponto longe da cidade (homônimo) é recusado")
with _tfv.TemporaryDirectory() as _dg:
    _arq = Path(_dg) / "BASE_CLIENTE.xlsx"
    _r = _gc9.atualizar(_arq, clientes=[dict(_cc)], consultar=_fake,
                        esperar=lambda s: None)
    _c2 = dict(_cc)
    _n = _gc9.completar([_c2], _gc9.caminho(_arq))
    _mud = dict(_cc, ENDERECO="RUA NOVA 10")
    checar(_r["achados"] == 1 and _n == 1 and _c2["LATITUDE"] == -3.05
           and not _gc9.pendentes([_cc], _gc9.ler(_gc9.caminho(_arq)))
           and _gc9.pendentes([_mud], _gc9.ler(_gc9.caminho(_arq))),
           "Coordenadas: guarda, completa e só consulta de novo quem mudou "
           "de endereço")
    # (23/10) o arquivo no formato do modelo: "LATITUDE" : "-3.05" (texto)
    _txt23 = _gc9.caminho(_arq).read_text("utf-8")
    _old23 = {"x": {"end": "E", "lat": -3.0107090, "lon": -60.0082203,
                    "precisao": "rua", "em": "2026-10-01"}}
    _gc9.gravar(_gc9.caminho(_arq), _old23)
    _new23 = _gc9.ler(_gc9.caminho(_arq))["x"]
    checar('"LATITUDE" : "-3.05"' in _txt23 and "\"lat\"" not in _txt23
           and _new23["LATITUDE"] == "-3.010709"
           and _new23["LONGITUDE"] == "-60.0082203"
           and _gc9.ponto(_new23) == (-3.010709, -60.0082203),
           "Coordenadas: arquivo com LATITUDE/LONGITUDE em texto (formato "
           "do modelo); o antigo (lat/lon) é lido e convertido")
# (14/10) o numero no campo NUMERO ("no such group" parava tudo) e um
# cliente com problema nao para os outros
checar(_gc9.numero_de("1020") == "1020" and _gc9.numero_de("S/N", "RUA X 77")
       == "77" and _gc9.numero_de("SN", "") == "",
       "Geocodificar: número da porta pelo campo NÚMERO")
with _tfv.TemporaryDirectory() as _dg2:
    _arq2 = Path(_dg2) / "BASE_CLIENTE.xlsx"
    _ruim = dict(_cc, CHAVE_CLIENTE="000002-01", NUMERO="55")

    def _fake2(params):
        if "55" in str(params.get("street", "")):
            raise ValueError("resposta estranha")
        return _fake(params)
    _r2 = _gc9.atualizar(_arq2, clientes=[_ruim, dict(_cc, NUMERO="1020")],
                         consultar=_fake2, esperar=lambda s: None)
    checar(_r2["achados"] == 1 and "000002-01" in _r2["erro"],
           "Coordenadas: cliente com problema é pulado e os outros seguem")
import base_cliente as _bc9  # noqa: E402
_nv9 = len(_bc9.COLUNAS_VENDEDOR)
checar(_bc9.CABECALHO[-4 - _nv9:-2 - _nv9] == ["LATITUDE", "LONGITUDE"]
       and _bc9.CABECALHO[-2 - _nv9:-2] == _bc9.COLUNAS_VENDEDOR
       and _bc9.CABECALHO[-2:] == ["CEP", "STATUS_PROTHEUS"]
       and len(_bc9.LARGURA) == len(_bc9.CABECALHO),
       "BASE_CLIENTE com as colunas LATITUDE e LONGITUDE (e o CEP, 28/10, e "
       "o STATUS_PROTHEUS no fim, 10/11)")
# ---- (28/10, Alexandre - recado do analista 20261028-1020) REGRA 2 das
# coordenadas: o numero de dentro do endereco, o CEP na consulta, o ponto
# que nao e da casa vira "rua" e o BAIRRO DIFERENTE vai para o centro do
# bairro da base; o MANUAL nao sai e a regra antiga e refeita
_sn28 = [_gc9.separar_numero(e_, n_) for e_, n_ in (
    ("AV COSME FERREIRA 5548", ""), ("R IORUBA", "N 21"), ("RUA 10", ""),
    ("BR 010", ""), ("R SOBRAL N253", ""), ("RUA X, 39A", ""),
    ("RUA LOURIVAL CRUZ S N", ""), ("AV TORQUATO TAPAJOS KM 5", ""))]


def _osm_fort28(p_):
    if "street" in p_:
        return {"lat": -3.0746697, "lon": -59.9639609,
                "address": {"road": "Avenida Cosme Ferreira",
                            "suburb": "Coroado"}}
    return None


def _osm_braga28(p_):
    if "street" in p_:
        return {"lat": -3.0418064, "lon": -59.9612423,
                "address": {"road": "Rua Iorubá", "suburb": "Novo Aleixo",
                            "house_number": "21"}}
    return None


_cfo28 = []
_f28 = _gc9.localizar_detalhe(
    {"ENDERECO": "AV COSME FERREIRA 5548", "NUMERO": "",
     "BAIRRO": "ZUMBI DOS PALMARES", "CIDADE": "MANAUS", "UF": "AM",
     "CEP": "69084425"},
    consultar=lambda p_: (_cfo28.append(p_), _osm_fort28(p_))[1],
    esperar=lambda s: None, consultar_cep=lambda c_: None)
_b28 = _gc9.localizar_detalhe(
    {"ENDERECO": "R IORUBA", "NUMERO": "N 21", "BAIRRO": "GILBERTO MESTRINHO",
     "CIDADE": "MANAUS", "UF": "AM", "CEP": "69086780"},
    consultar=_osm_braga28, esperar=lambda s: None,
    consultar_cep=lambda c_: None)
_cb28 = _geo9.coordenada_do_bairro("AM", "MANAUS", "GILBERTO MESTRINHO")
_dados28 = {"a-1": {"end": _gc9.endereco_do_cliente({"ENDERECO": "R A"}),
                    "LATITUDE": "-3.1", "LONGITUDE": "-60.0",
                    "precisao": "endereco", "em": "2026-10-14"},
            "m-1": {"end": _gc9.endereco_do_cliente({"ENDERECO": "R M"}),
                    "LATITUDE": "-3.1", "LONGITUDE": "-60.0",
                    "precisao": "endereco", "em": "2026-10-28",
                    "origem": "MANUAL"},
            "n-1": {"end": _gc9.endereco_do_cliente({"ENDERECO": "R N"}),
                    "LATITUDE": "-3.1", "LONGITUDE": "-60.0",
                    "precisao": "rua", "em": "2026-10-28", "regra": 2}}
_pd28 = [c_["CHAVE_CLIENTE"] for c_ in _gc9.pendentes(
    [{"CHAVE_CLIENTE": "a-1", "ENDERECO": "R A"},
     {"CHAVE_CLIENTE": "m-1", "ENDERECO": "R M"},
     {"CHAVE_CLIENTE": "n-1", "ENDERECO": "R N"}], _dados28, refazer=True)]
checar(_sn28 == [("AVENIDA COSME FERREIRA", "5548"), ("RUA IORUBA", "21"),
                 ("RUA 10", ""), ("BR 010", ""), ("RUA SOBRAL", "253"),
                 ("RUA X", "39A"), ("RUA LOURIVAL CRUZ", ""),
                 ("AVENIDA TORQUATO TAPAJOS KM 5", "")]
       and _cfo28[0].get("postalcode") == "69084-425"
       and _f28["precisao"] == "rua" and not _f28["alerta"]
       and _b28["alerta"] == _gc9.ALERTA_BAIRRO
       and _b28["precisao"] == "bairro" and _cb28
       and (_b28["lat"], _b28["lon"]) == tuple(_cb28)
       and _pd28 == ["a-1"],
       "Coordenadas (regra 2): número de dentro do endereço, CEP na "
       "consulta, sem a casa = RUA, BAIRRO DIFERENTE = centro do bairro da "
       "base; refaz a regra antiga e deixa o MANUAL")
# (28/10, Alexandre) o CEP PRIMEIRO: o numero + o logradouro do CEP
# (BrasilAPI) + o CEP; sem a casa, o PONTO DO CEP vale antes da rua; CEP
# generico (...000) nao vira ponto
_cq28 = []
_gc9._CEPS.clear()
_ce28 = _gc9.localizar_detalhe(
    {"ENDERECO": "R IORUBA", "NUMERO": "21", "BAIRRO": "GILBERTO MESTRINHO",
     "CIDADE": "MANAUS", "UF": "AM", "CEP": "69086780"},
    consultar=lambda p_: (_cq28.append(p_), None)[1], esperar=lambda s: None,
    consultar_cep=lambda c_: {"rua": "Rua Iorubá", "bairro":
                              "Gilberto Mestrinho", "cidade": "Manaus",
                              "uf": "AM", "lat": -3.0739, "lon": -59.9262})
_gc9._CEPS.clear()
_cg28 = _gc9.localizar_detalhe(
    {"ENDERECO": "RUA A", "NUMERO": "5", "BAIRRO": "CENTRO",
     "CIDADE": "MANAUS", "UF": "AM", "CEP": "69000000"},
    consultar=lambda p_: None, esperar=lambda s: None,
    consultar_cep=lambda c_: {"rua": "", "bairro": "", "cidade": "Manaus",
                              "uf": "AM", "lat": -3.1, "lon": -60.02})
_gc9._CEPS.clear()
checar(_cq28 and _cq28[0].get("postalcode") == "69086-780"
       and _cq28[0].get("street") == "21 RUA IORUBA"
       and _ce28["precisao"] == "cep" and _ce28["lat"] == -3.0739
       and _cg28["precisao"] != "cep",
       "Coordenadas: o CEP primeiro (número + logradouro do CEP + CEP); o "
       "ponto do CEP antes da rua; CEP genérico (...000) não vira ponto")
# ---- 28/10: API do Google SO para os divergentes (sem ponto, so da rua,
# so do bairro, BAIRRO DIFERENTE); MANUAL e o ja certo nao vao; sem chave
# nao consulta; ponto do Google fica protegido e marcado GOOGLE
import tempfile as _tf28  # noqa: E402
with _tf28.TemporaryDirectory() as _td28:
    _arq28 = Path(_td28) / _gc9.ARQUIVO
    _cl28 = [dict(CHAVE_CLIENTE=k_, ENDERECO="RUA IORUBA", NUMERO="21",
                  BAIRRO="ZUMBI", CIDADE="MANAUS", UF="AM", CEP=cp_)
             for k_, cp_ in (("G1-01", "69086780"), ("G2-01", "06904301"),
                             ("G3-01", ""), ("G4-01", ""), ("G5-01", ""))]
    _gc9.gravar(_arq28, {
        "G2-01": {"end": "x", "LATITUDE": "-3.07", "LONGITUDE": "-59.95",
                  "precisao": "bairro", "em": "2026-10-01"},
        "G3-01": {"end": "x", "LATITUDE": "-3.07", "LONGITUDE": "-59.95",
                  "precisao": "endereco", "em": "2026-10-01"},
        "G4-01": {"end": "x", "LATITUDE": "-3.07", "LONGITUDE": "-59.95",
                  "precisao": "endereco", "em": "2026-10-01",
                  "origem": "MANUAL", "fonte": "x"},
        "G5-01": {"end": "x", "LATITUDE": "-3.07", "LONGITUDE": "-59.95",
                  "precisao": "rua", "em": "2026-10-01"}})
    _sem28 = _gc9.atualizar_google(_arq28, clientes=_cl28, chave="")
    _q28 = []
    _r28 = _gc9.atualizar_google(
        _arq28, clientes=_cl28, chave="x", esperar=lambda s_: None,
        consultar=lambda e_: _q28.append(e_) or {
            "lat": -3.0739, "lon": -59.9491, "tipo": "ROOFTOP",
            "parcial": False, "endereco": "R. Iorubá, 21"})
    _d28 = _gc9.ler(_arq28)
checar(_sem28.get("sem_chave") and _r28["divergentes"] == 3
       and _r28["melhorados"] == 3 and len(_q28) == 3
       and "69086-780" in _q28[0] and "06904" not in " ".join(_q28)
       and _d28["G1-01"]["origem"] == "GOOGLE"
       and _d28["G2-01"]["antes"].endswith("(bairro)")
       and _d28["G3-01"]["precisao"] == "endereco"
       and "origem" not in _d28["G3-01"]
       and _d28["G4-01"]["origem"] == "MANUAL"
       and _gc9.eh_manual(_d28["G1-01"])
       and rn._ponto_do_arquivo(_d28["G1-01"]) == "GOOGLE",  # noqa: SLF001
       "Coordenadas: API do Google só para os divergentes (sem ponto, só "
       "bairro/rua); MANUAL e o já certo ficam; sem chave não consulta")
# ---- 29/10: ponto do CEP repetido em outro CEP = ponto da CIDADE (a
# BrasilAPI deu -3.10194/-60.025 para 1.281 clientes de Manaus): nao vale
_gc9._CEPS.clear()
_gc9._CEPS.update({"69000001": {"lat": -3.10194, "lon": -60.025},
                   "69000002": {"lat": -3.10194, "lon": -60.025},
                   "69086780": {"lat": -3.0739, "lon": -59.9491}})
_ruim29 = {"end": "x", "LATITUDE": "-3.10194", "LONGITUDE": "-60.025",
           "precisao": "cep", "em": "2026-10-28", "regra": 2}
_c29 = dict(CHAVE_CLIENTE="Z1-01", ENDERECO="RUA X", NUMERO="1",
            CIDADE="MANAUS", UF="AM")
_ok29 = (not _gc9.ponto_do_cep_valido(_gc9._CEPS["69000001"])
         and _gc9.ponto_do_cep_valido(_gc9._CEPS["69086780"])
         and _gc9.ponto_cep_ruim(_ruim29)
         and _gc9.divergente(_c29, _ruim29)
         and len(_gc9.pendentes([dict(_c29, ENDERECO="x")], {"Z1-01": dict(
             _ruim29, end=_gc9.endereco_do_cliente(dict(_c29,
                                                        ENDERECO="x")))},
             refazer=False)) == 1)
_gc9._CEPS.clear()
checar(_ok29, "Coordenadas: ponto do CEP repetido em outro CEP (= ponto da "
       "cidade) não vale; o que ficou no arquivo é refeito e vai ao Google")
# ---- 29/10: TomTom (Search API) no lugar do Google: mesma fila dos
# divergentes; Point Address = endereco; ponto da cidade nao serve; cidade
# vizinha = rua; chave nunca aparece no erro; teto por dia
import io as _io29  # noqa: E402
import urllib.error as _ue29  # noqa: E402
from unittest import mock as _mk29  # noqa: E402


class _Resp29(_io29.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a_):
        return False


def _tt29(tipo, ent="", cidade="Manaus", score=0.95):
    return _Resp29(json.dumps({"results": [{
        "type": tipo, "entityType": ent,
        "matchConfidence": {"score": score},
        "position": {"lat": -3.0739, "lon": -59.9491},
        "address": {"freeformAddress": "Rua Iorubá, 21", "municipality":
                    cidade, "municipalitySubdivision": "Zumbi"}}]})
        .encode("utf-8"))


def _so_antiga29(resp):
    """a API nova (Orbis) recusa a chave (401); a antiga responde"""
    def _f(req, timeout=None):
        if "/maps/orbis/" in req.full_url:
            raise _ue29.HTTPError(req.full_url, 401, "Unauthorized", {},
                                  None)
        return resp
    return _f


_gc9._TOMTOM_API["qual"] = ""
with _mk29.patch("urllib.request.urlopen", side_effect=_so_antiga29(_tt29(
        "Point Address"))):
    _t1 = _gc9._consultar_tomtom("RUA IORUBA, 21, MANAUS - AM", "k")
_q1 = _gc9._TOMTOM_API["qual"]
with _mk29.patch("urllib.request.urlopen", return_value=_tt29(
        "Geography", "Municipality")):
    _t2 = _gc9._consultar_tomtom("X", "k")
# Orbis v2 (chave nova): chave no cabecalho, coordinates [lon, lat]
_gc9._TOMTOM_API["qual"] = ""
_hd29 = {}


def _orbis29(req, timeout=None):
    _hd29.update(dict(req.header_items()), url=req.full_url)
    return _Resp29(json.dumps({"results": [{
        "type": "address", "title": "Rua Iorubá, 21, Manaus",
        "position": {"type": "Point", "coordinates": [-59.9491, -3.0739]},
        "address": {"municipality": "Manaus", "houseNumber": "21"}}]})
        .encode("utf-8"))


with _mk29.patch("urllib.request.urlopen", side_effect=_orbis29):
    _t4 = _gc9._consultar_tomtom("RUA IORUBA, 21, MANAUS - AM", "KORB")
_q4 = _gc9._TOMTOM_API["qual"]
_gc9._TOMTOM_API["qual"] = ""
_e403 = _ue29.HTTPError("u", 403, "Forbidden", {}, None)
try:
    with _mk29.patch("urllib.request.urlopen", side_effect=_e403):
        _gc9._consultar_tomtom("X", "CHAVESECRETA")
    _t3 = ""
except RuntimeError as _ex:
    _t3 = str(_ex)
with _tf28.TemporaryDirectory() as _td29:
    _arq29 = Path(_td29) / _gc9.ARQUIVO
    _cl29 = [dict(CHAVE_CLIENTE=f"T{i}-01", ENDERECO="RUA IORUBA",
                  NUMERO="21", BAIRRO="ZUMBI", CIDADE="MANAUS", UF="AM",
                  CEP="69086780") for i in range(4)]
    _gc9.gravar(_arq29, {"T3-01": {"end": "x", "LATITUDE": "-3.07",
                                   "LONGITUDE": "-59.95",
                                   "precisao": "rua", "em": "2026-10-28"}})
    _rs29 = iter([
        {"lat": -3.0739, "lon": -59.9491, "tipo": "Point Address",
         "cidade": "Manaus", "endereco": "a"},
        {"lat": -3.0739, "lon": -59.9491, "tipo": "CIDADE",
         "cidade": "Manaus", "endereco": "b"},
        {"lat": -3.0739, "lon": -59.9491, "tipo": "Point Address",
         "cidade": "Iranduba", "endereco": "c"}])
    _r29 = _gc9.atualizar_tomtom(_arq29, clientes=_cl29, chave="k",
                                 limite=3, esperar=lambda s_: None,
                                 consultar=lambda e_: next(_rs29))
    _d29 = _gc9.ler(_arq29)
    _u29 = json.loads((Path(_td29) / _gc9.TOMTOM_USO).read_text())
_gc9._CEPS.clear()
checar(_t1 and _t1["tipo"] == "Point Address" and _t1["cidade"] == "Manaus"
       and _q1 == "antiga" and _q4 == "orbis" and _t4
       and _t4["tipo"] == "Point Address" and _t4["lat"] == -3.0739
       and _t4["lon"] == -59.9491 and _t4["numero"] == "21"
       and "KORB" not in _hd29["url"]
       and _hd29.get("Tomtom-api-key") == "KORB"
       and _hd29.get("Tomtom-api-version") == "2"
       and _hd29.get("Attributes") == "results"
       and _t2["tipo"] == "CIDADE" and "403" in _t3
       and "CHAVESECRETA" not in _t3
       and _r29["consultados"] == 3 and _r29["melhorados"] == 2
       and _d29["T0-01"]["origem"] == "TOMTOM"
       and _d29["T0-01"]["precisao"] == "endereco"
       and "T1-01" not in _d29 and _d29["T2-01"]["precisao"] == "rua"
       and _d29["T3-01"].get("origem") != "TOMTOM" and list(_u29.values()) == [3]
       and rn._ponto_do_arquivo(_d29["T0-01"]) == "TOMTOM",  # noqa: SLF001
       "Coordenadas: TomTom só para os divergentes (casa = ENDEREÇO, ponto "
       "da cidade não serve, cidade vizinha = RUA, teto do dia, chave fora "
       "do erro)")
# ---- 29/10: certificado recusado pelo Python ("self-signed certificate in
# certificate chain") -> usa o Windows (curl.exe/Schannel; sem ele, o
# PowerShell); a chave nunca vai na linha de comando
import ssl as _ssl29  # noqa: E402
import types as _ty29  # noqa: E402
_tdw = Path(tempfile.mkdtemp(prefix="bap_win_"))
(_tdw / "System32").mkdir()
(_tdw / "System32" / "curl.exe").write_text("x")
_cw29 = []
_cj29 = json.dumps({"results": [{"type": "address", "position": {
    "type": "Point", "coordinates": [-59.94, -3.07]}, "address": {
    "municipality": "Manaus", "houseNumber": "21"}}]})


def _run29(args, **kw):
    _cw29.append((str(args), kw.get("input") or b"",
                  (kw.get("env") or {}).get("BAP_URL", "")))
    if "curl" in str(args[0]) and len(_cw29) > 1:
        return _ty29.SimpleNamespace(returncode=35, stdout=b"",
                                     stderr=b"revogacao")
    return _ty29.SimpleNamespace(returncode=0, stdout=(_cj29 + "\n200")
                                 .encode(), stderr=b"")


_modo29 = dict(_gc9._TRANSPORTE)
_gc9._TOMTOM_API["qual"] = ""
with _mk29.patch.dict(os.environ, {"SystemRoot": str(_tdw)}), \
        _mk29.patch("urllib.request.urlopen", side_effect=_ue29.URLError(
            _ssl29.SSLCertVerificationError(1, "self-signed"))), \
        _mk29.patch("subprocess.run", side_effect=_run29):
    _w1 = _gc9._consultar_tomtom("RUA X, 21", "CHAVE29")
    _m1 = _gc9._TRANSPORTE["modo"]
    _w2 = _gc9._consultar_tomtom("RUA X, 21", "CHAVE29")
    _m2 = _gc9._TRANSPORTE["modo"]
_gc9._TRANSPORTE.update(_modo29)
checar(_w1 and _w2 and _w1["tipo"] == "Point Address" and _m1 == "windows"
       and _m2 == "powershell" and len(_cw29) == 3
       and not any("CHAVE29" in a_ for a_, _i, _e in _cw29)
       and b"TomTom-Api-Key: CHAVE29" in _cw29[0][1]
       and "CHAVE29" not in _cw29[2][2],
       "Coordenadas: certificado recusado pelo Python -> Windows (curl.exe, "
       "depois PowerShell), com a chave fora da linha de comando")
# ---- 29/10: chave colada de qualquer jeito no Bloco de Notas
_k29 = "abcdEFGH1234ijklMNOP5678qrstUVWX"
checar(all(_gc9._limpar_chave(t_) == _k29 for t_ in (
    '{"api_key": "%s"}' % _k29, '{"api_key": " %s "}' % _k29,
    '{"api_key": "COLE_A_CHAVE_AQUI%s"}' % _k29, _k29,
    '{"api_key": ""%s""}' % _k29))
       and _gc9._limpar_chave('{"api_key": "COLE_A_CHAVE_AQUI"}') == ""
       and _gc9._mascara(_k29) == "abcd...UVWX",
       "Coordenadas: chave lida mesmo com aspas/espaço/texto junto; o erro "
       "mostra só a máscara")
_pn9.IGNORAR_ROTA_FIXA[0] = True      # o caminho do GERADOR (nao o realizado)
_rt9 = _pn9.gerar_rota(_cfg_r, _cli_r)
_pn9.IGNORAR_ROTA_FIXA[0] = False
_pd9 = defaultdict(list)
for _x in _rt9:
    _pd9[(_x["COD_VENDEDOR"], _x["DATA"])].append(_x)
_km_n = _km_a = 0.0
for _ls in _pd9.values():
    _ls.sort(key=lambda x: x["ORDEM_DE_VISITA"])
    _p1 = [(x["LATITUDE"], x["LONGITUDE"]) for x in _ls]
    _km_n += _geo9.km_do_caminho(_p1, range(len(_p1)))
    _al = sorted(_ls, key=lambda x: (x["CIDADE"], x["BAIRRO"]))
    _p2 = [(x["LATITUDE"], x["LONGITUDE"]) for x in _al]
    _km_a += _geo9.km_do_caminho(_p2, range(len(_p2)))
checar(_km_n <= _km_a + 0.01 and all("LATITUDE" in x for x in _rt9),
       f"Rota do dia pelo caminho mais curto: {_km_n:.0f} km x "
       f"{_km_a:.0f} km na ordem alfabética do bairro")

# ---- 06/10: Indicadores Executivos por TRIMESTRE (meta, real, ating.
# mes a mes e do tri; pontos; fechamento dos 4); cadastro saiu do Analista
import meta_nucleo as _mn_ex  # noqa: E402
_rx = rn.montar("vc_executivo", AQUI)
_pn_ex = rn.Contexto(AQUI).executivo["painel"]
_tris = _mn_ex.trimestres_do_executivo(_pn_ex)
_tri_t = _rx["tabelas"][0]
_nt = next(n for n, _r in _rx["parametros"][0]["valores"]
           if n == _rx["parametros"][0]["valor"])
_fx = _tris[_nt - 1]["fechamento"]
_iat = [c["nome"] for c in _tri_t["colunas"]].index("% TRI")
checar([t_["titulo"] for t_ in _rx["tabelas"]][1:] == [
    "Fechamento dos trimestres", "Atingimento mês a mês",
    "Realizado mês a mês", "Meta mês a mês", "Analítico"]
       and _rx["parametros"][0]["nome"] == "TRIMESTRE"
       and sum(n_ for _g, n_ in _tri_t["grupos"]) == len(_tri_t["colunas"])
       and len(_tri_t["colunas"]) == 2 + 3 * 3 + 4
       and all(_l[_iat] == (_fx["linhas"][_ln["chave"]]["ating"])
               for _l, _ln in zip(_tri_t["linhas"], _pn_ex["linhas"]))
       and _rx["kpis"][-1]["rotulo"] == "Resultado do tri"
       and not any(b_["tipo"] == "insights" for b_ in _rx["painel"]["blocos"])
       and "_eventos" not in _rx,
       "Indicadores Executivos: painel do trimestre (meta, real, % mês a mês "
       "e do tri, pontos, fechamento dos 4), sem insights")
_rx4 = rn.montar("vc_executivo", AQUI, params={"TRIMESTRE": 4})
checar(_rx4["parametros"][0]["valor"] == 4 and len(_rx4["kpis"]) == len(
    _pn_ex["linhas"]) + 1, "Indicadores Executivos: escolhe o trimestre")
# ---- 08/10: ANALITICO (aba) e EXPORTAR PARA O RH: cada indicador confere
# com o real do farol; o RH sai com o resumo e um analitico por indicador
_an = _rx["tabelas"][-1]
_conf = []
for _ln in _pn_ex["linhas"]:
    _rt = rn._rot_exec(_ln).capitalize()  # noqa: SLF001
    _ls = [x_ for x_ in _an["linhas"] if x_[0] == _rt]
    if _ls:
        _cf = _an["kpis_de"](_ls)
        _conf.append(_cf[-1]["valor"] == "confere")
checar(_an["titulo"] == "Analítico" and _conf and all(_conf)
       and _an["filtros"][0]["coluna"] == "INDICADOR",
       "Indicadores Executivos: aba Analítico confere com o farol em todos "
       "os indicadores")
_rh_x = rn.exportar_rh_executivo(rn.Contexto(AQUI, params={
    "TRIMESTRE": _nt}))
checar(_rh_x["tabelas"][0]["titulo"] == "Resumo executivo"
       and len(_rh_x["tabelas"]) >= 2
       and all(t_.get("pdf_quebra_antes") for t_ in _rh_x["tabelas"][1:])
       and not any("NÃO CONFERE" in (t_.get("nota_pdf") or "")
                   for t_ in _rh_x["tabelas"])
       and _rh_x["fecho_na_1a"] and _rh_x["assinaturas"],
       "Exportar para o RH (executivo): resumo na 1a página e analítico por "
       "indicador, conferido")
import tempfile as _tf_rh  # noqa: E402
with _tf_rh.TemporaryDirectory() as _d_rh:
    _x_rh = bv.exportar_excel(_rh_x, Path(_d_rh) / "rh.xlsx")
    from openpyxl import load_workbook as _lw_rh  # noqa: E402
    _wb_rh = _lw_rh(_x_rh, read_only=True)
    checar(_wb_rh.sheetnames[:2] == ["RESUMO", "Resumo executivo"]
           and len(_wb_rh.sheetnames) == len(_rh_x["tabelas"]) + 1,
           "Exportar para o RH (executivo): Excel com uma aba por indicador")
    _wb_rh.close()
_src_ana = (AQUI / "bap_analista.py").read_text("utf-8")
_src_rel = (AQUI / "bap_relatorios.py").read_text("utf-8")
checar('"<<TreeviewSelect>>", self._encher_juntas' in _src_rel
       and "def _encher_juntas" in _src_rel,
       "Farol de Pedidos: um clique no pedido filtra separação, reversa e "
       "analítico")
checar("DialogoRHExecutivo(self)" in _src_rel,
       "Farol Indicadores Executivos: botão Exportar para o RH")
checar('("meta_exec"' not in _src_ana
       and '"--executivas"' in _src_rel
       and "--executivas" in (AQUI / "bap_meta.py").read_text("utf-8"),
       "Metas executivas: saiu do BAP Analista, abre no Farol Indicadores "
       "Executivos")

# ---- 06/10: Painel Executivo com a VISAO PEDIDO (caixa Somar pedidos)
_pa = rn.montar("vc_painel", AQUI)
_pb = rn.montar("vc_painel", AQUI, params={"PEDIDOS": "SIM"})
_ctx_p = rn.Contexto(AQUI)
_vea = sum(i_["valor"] for i_ in _ctx_p.tabela["itens"] if i_["tipo"] == "VEA")
_ta, _tb = [next(t_ for t_ in x_["tabelas"] if t_["titulo"] == "Por filial")
            ["total"] for x_ in (_pa, _pb)]
_kp = next((k_ for k_ in _pb["kpis"] if k_["rotulo"] == "Pedidos em aberto"),
           None)
checar(_kp and [x[0] for x in _kp["linhas"]] == [
    "Pedidos", "Clientes", "Ticket", "Atrasados"]
       and any(p_.get("tipo") == "flag" and p_["nome"] == "PEDIDOS"
               for p_ in _pb["parametros"])
       and abs((_tb[2] - _ta[2]) - _vea) < 0.5
       and abs((_tb[3] - _ta[3]) - _vea) < 0.5,
       "Painel Executivo: pedidos em aberto somam no real e entram inteiros "
       "na projeção; cartão de pedidos")

# ---- 06/10: PARCIAL PEDIDOS e PARCIAL VISITAS E POSITIVACAO (imagem e PDF)
import tempfile as _tf_p  # noqa: E402
import parcial_imagem as _pi  # noqa: E402
_ctx_pp = rn.Contexto(AQUI)
_ok_pp = []
for _q in ("acum", "d1", "hoje"):
    _a = rn.parcial_pedidos(_ctx_pp, _q)
    _b = rn.parcial_visitas(_ctx_pp, _q)
    _ok_pp.append(
        [t_ for t_, _l, _m in _a["rankings"]] == [
            "Qtd. pedidos", "Faturamento total", "SKU por pedido"]
        # (08/10) pecas e baterias so nas tabelas; desconto saiu
        and _a["tabela"]["colunas"] == [
            "SUPERVISOR", "PED.", "FAT. TOTAL", "FAT. PEÇAS", "FAT. BAT.",
            "SKU/PED.", "ABERTOS", "ATRAS."]
        and not any("esconto" in c_[0] or "peças" in c_[0].lower()
                    for c_ in _a["cartoes"])
        # (08/10) visitas: resultado primeiro, agenda depois; (21/10) a
        # META DE VISITA do Planner e a jornada (inicio, ult. atividade,
        # TMA e TMD)
        and _b["tabela"]["colunas"][1:] == [
            "META", "VISIT.", "% META", "% CONV.", "% FORA DE ROTA",
            "CAD.", "PROSP.", "INÍCIO", "ÚLT. ATIV.", "JORNADA LÍQ.",
            "DIAS < JORN. LÍQ.", "INTERV. ALMOÇO", "DIAS ALMOÇO > MÁX.",
            "TMA", "TMD", "KM", "KM/CLIENTE"]
        and any(c_[0] == "Intervalo almoço" and "máx. 01:30" in c_[2]
                for c_ in _b["cartoes"])
        and any(c_[0] == "Jornada líquida" and "meta 08:00" in c_[2]
                for c_ in _b["cartoes"])
        # (22/10) sem o cartao da meta; KM rodado no cartao; TMA em HH:MM
        and not any(c_[0].startswith("Meta") for c_ in _b["cartoes"])
        and any(c_[0] == "KM rodado" for c_ in _b["cartoes"])
        and all(re.fullmatch(r"\d\d:\d\d|—", str(l_[-4]))
                for l_ in _b["tabela"]["linhas"])
        # (22/10) a POSITIVACAO virou CONVERSAO: % dos clientes visitados
        # que compraram
        and _b["tipo"] == "Parcial Visitas e Conversão"
        and any(c_[0] == "Conversão" for c_ in _b["cartoes"])
        and not any(c_[0] == "Positivação" for c_ in _b["cartoes"])
        and 0 <= _b["numeros"]["total"]["c_com"] <= _b["numeros"]["total"][
            "c_vis"]
        # (22/10) sem a agenda da Maxima: o % fora de rota e o do Planner
        and any(c_[0] == "% fora de rota" for c_ in _b["cartoes"])
        and [t_ for t_, _l, _m in _b["rankings"]] == [
            "Visitados", "% da meta de visita", "Conversão",
            "Cadastros novos"]
        and not any(c_[0] == "Agendados" for c_ in _b["cartoes"])
        and _a["tabela"]["colunas"][0] == "SUPERVISOR"
        and _b["tabela"]["colunas"][0] == "SUPERVISOR"
        and all(len(l_) <= 5 for _t, l_, _m in _a["rankings"] + _b["rankings"])
        and _a["numeros"]["total"]["ped"] == sum(
            v_["ped"] for v_ in _a["numeros"]["sup"].values()))
    # (07/10) depois dos destaques: a tabela de TODOS os vendedores
    _ok_pp.append(all(
        (x_.get("tabela_vend") is None and not x_["numeros"]["vend"])
        or (x_["tabela_vend"]["colunas"][0] == "VENDEDOR"
            and x_["tabela_vend"]["total"] == x_["tabela"]["total"]
            and len(x_["tabela_vend"]["linhas"]) >= len(x_["numeros"]["vend"]))
        for x_ in (_a, _b)))
_de, _ate, _rot = rn.periodo_parcial(_ctx_pp, "d1")
with _tf_p.TemporaryDirectory() as _tmp_p:
    _png = _pi.gravar_png(rn.parcial_pedidos(_ctx_pp, "acum"), _tmp_p)
    _pdf = _pi.gravar_pdf(rn.parcial_visitas(_ctx_pp, "d1"), _tmp_p)
    _ok_arq = _png.stat().st_size > 10000 and _pdf.read_bytes()[:4] == b"%PDF"
    # (08/10) o card executivo (fundo branco) nas parciais com tabela;
    # a de Entregas (chips e listas) segue no layout antigo
    from PIL import Image as _Im_p  # noqa: E402
    _ok_arq = _ok_arq and _Im_p.open(_png).convert("RGB").getpixel(
        (5, 5)) == (255, 255, 255)
# (19/10, Alexandre) Parcial Visitas: o detalhe dos clientes visitados por
# vendedor (limite, comprou no mes, segmento e prazo cadastrado)
_ok_det = True
for _q in ("acum", "d1", "hoje"):
    _dv = rn.parcial_visitas(_ctx_pp, _q).get("detalhe")
    if _dv:
        _cols_ok = ["CLIENTE", "SEGMENTO", "LIMITE", "PRAZO",
                    "ROTA DO DIA", "COMPROU NO MÊS"] + (
                        ["ÚLT. VISITA"] if _q == "acum" else [])
        _ok_det = _ok_det and _dv["colunas"] == _cols_ok and _dv["linhas"] \
            == sum(len(b_["linhas"]) for b_ in _dv["blocos"]) and all(
                l_[4] in ("NA ROTA", "FORA DA ROTA")
                and l_[5] in ("SIM", "NÃO", "EM ABERTO") and len(l_) == len(
                    _cols_ok) for b_ in _dv["blocos"] for l_ in b_["linhas"])
with _tf_p.TemporaryDirectory() as _tmp_d:
    _pv_d = rn.parcial_visitas(_ctx_pp, "acum")
    _png_d = _pi.gravar_png(_pv_d, _tmp_d)
    _pdf_d = _pi.gravar_pdf(_pv_d, _tmp_d)
    # (21/10, Alexandre) o PRINT (PNG) e so o resumo: sem o detalhe e sem
    # a pasta _DETALHE; o detalhe por vendedor so no PDF
    _ok_det = _ok_det and _png_d.exists() and _pdf_d.read_bytes()[:4] == \
        b"%PDF" and not _pv_d.get("_extras") \
        and not _pv_d.get("_pasta_extras") \
        and not any(x_.is_dir() for x_ in Path(_tmp_d).iterdir())
# (20/10, Alexandre) agrupado por SUPERVISOR e sem a nota das regras
for _q in ("acum", "d1", "hoje"):
    _dv = rn.parcial_visitas(_ctx_pp, _q).get("detalhe")
    if _dv:
        _ok_det = _ok_det and [b_ for g_ in _dv["grupos"]
                               for b_ in g_["blocos"]] == _dv["blocos"] \
            and "Espelho da Máxima (o mesmo" not in str(_dv) \
            and all(g_["supervisor"] for g_ in _dv["grupos"])
checar(_ok_det, "Parcial Visitas: detalhe dos clientes visitados por "
      "vendedor (limite, rota do dia, comprou no mês, segmento, prazo) na "
      "imagem e no PDF")
# (21/10, Alexandre) o Farol de Visita filtrado num DIA: a meta do cartao e
# a META DIA da tabela (nao a do mes); e a META DE VISITA da Parcial do dia
# e a mesma
_ok21, _fv21 = True, rn.farol_visitas(rn.Contexto(AQUI))
for t_ in _fv21["tabelas"]:
    if t_["titulo"] != "Dia a dia" or not t_.get("kpis_de"):
        continue
    _dias21 = sorted({l_[0] for l_ in t_["linhas"]})
    if len(_dias21) < 2:
        continue
    _cn21 = [c_["nome"] for c_ in t_["colunas"]]
    _hj21 = [l_ for l_ in t_["linhas"] if l_[0] == _dias21[-1]]
    _md21 = sum(l_[_cn21.index("META")] or 0 for l_ in _hj21)
    _k21 = t_["kpis_de"](_hj21)[0]
    if _md21:
        _ok21 = _ok21 and "meta do dia" in _k21["detalhe"] \
            and _k21["detalhe"].endswith(rn.br(_md21)) \
            and not any(x_[0] == "Nec./dia" for x_ in _k21.get("linhas", []))
        if _dias21[-1] == _ctx_pp.hoje:
            _t21 = rn.parcial_visitas(_ctx_pp, "hoje")["numeros"]["total"]
            _ok21 = _ok21 and rn.br(_t21["meta"]) == rn.br(_md21)
    _kt21 = t_["kpis_de"](t_["linhas"])[0]
    _ok21 = _ok21 and "meta do mês" in _kt21["detalhe"]
checar(_ok21, "Farol de Visita: com filtro de dia, o cartão Visitas usa a "
       "META DIA (12/6 do Planner) e a Parcial Visitas usa a mesma meta")
# (22/10, Alexandre) JORNADA LIQUIDA: do 1o ao ultimo cliente dentro do
# expediente (07:30-18:00; sexta ate 17:00), meta 08:00 - parametro do
# Planner (JORNADA DE TRABALHO), fora da assinatura da rota
import planner_nucleo as _nuj  # noqa: E402
_jt = _nuj.jornada_de_trabalho({})
_lq = {"data": date(2026, 10, 22), "primeiro": 7 * 3600, "ultimo": 19 * 3600,
       "visitas": 5, "fechado": True}
_lsx = dict(_lq, data=date(2026, 10, 23))
_lsb = dict(_lq, data=date(2026, 10, 24))
_cfg_j = {"parametros": dict(_nuj.PARAMETROS_PADRAO)}
_sig_a = _nuj._assinatura_parametros(_cfg_j)
_cfg_j["parametros"]["jornada_liquida"] = "07:00"
checar(_jt == {"inicio": 27000, "fim": 64800, "fim_sexta": 61200,
               "liquida": 28800, "almoco_max": 5400}
       and rn.jornada_liquida(_lq, _jt) == 10.5 * 3600
       and rn.jornada_liquida(_lsx, _jt) == 9.5 * 3600
       and rn.jornada_liquida(_lsb, _jt) is None
       and rn.resumo_jornada([dict(_lq, ultimo=12 * 3600)], _jt)["abaixo"] == 1
       and _nuj._assinatura_parametros(_cfg_j) == _sig_a
       and _nuj.jornada_de_trabalho(_cfg_j)["liquida"] == 7 * 3600,
       "Jornada líquida: expediente 07:30-18:00 (sexta 17:00), meta 08:00, "
       "parâmetro do Planner que não mexe na rota")
# (22/10, Alexandre) INTERVALO DE ALMOCO pelo checkout (max. 01:30)
class _CtxAlm:
    raiz = AQUI
_ca = _CtxAlm()
_ca._ad_memo = {(date(2026, 10, 1), date(2026, 10, 1)): {"clientes": [
    {"cod_max": "X", "data": date(2026, 10, 1), "situacao": "VISITADO NA ROTA",
     "inicio": 9 * 3600, "fim": 9 * 3600 + 900},
    {"cod_max": "X", "data": date(2026, 10, 1), "situacao": "VISITADO NA ROTA",
     "inicio": 11 * 3600 + 1800, "fim": 11 * 3600 + 2700},
    {"cod_max": "X", "data": date(2026, 10, 1), "situacao": "VISITADO NA ROTA",
     "inicio": 14 * 3600, "fim": 14 * 3600 + 600}]}}
_alm = rn.almocos_do_periodo(_ca, date(2026, 10, 1), date(2026, 10, 1))
_ra = rn.resumo_almoco([{"cod": "X", "data": date(2026, 10, 1)}], _alm, _jt)
checar(_alm == {("X", date(2026, 10, 1)): 2 * 3600 + 900}
       and _ra["acima"] == 1 and _ra["dias"] == 1,
       "Intervalo almoço: fim da última visita da manhã → 1ª da tarde, "
       "acima do máximo de 01:30")
_pb_ = rn.parcial_bap(_ctx_pp, "acum")
_ok_pp.append(
    [t_ for t_, _l, _m in _pb_["rankings"]] == [
        "Qtd. pedidos", "R$ Pedidos", "R$ Peças", "SKU por pedido",
        "Visitas", "% visitado na agenda", "Positivação"]
    and len(_pb_["cartoes"]) == 7 and _pb_["tipo"] == "Parcial BAP"
    and _pb_["fecho"] == "PARABÉNS AOS DESTAQUES!"
    and all(len(l_) <= rn.TOP_PARCIAL for _t, l_, _m in _pb_["rankings"])
    and "Parcial BAP" in (AQUI / "bap_central.py").read_text("utf-8"))
# 07/10: Farol de Markup com o filtro FILIAL (vale para todas as abas)
_mk_a = rn.montar("vc_markup", AQUI)
_fil_mk = next((v_ for v_ in _mk_a["parametros"][-1]["valores"]
                if v_ != rn.TODOS_RECORTE), None)
_mk_b = rn.montar("vc_markup", AQUI, params={"FILIAL": _fil_mk}) \
    if _fil_mk else _mk_a
_ok_pp.append(_mk_a["parametros"][-1]["nome"] == "FILIAL" and all(
    len(tb_["linhas"]) <= len(ta_["linhas"])
    for ta_, tb_ in zip(_mk_a["tabelas"], _mk_b["tabelas"])))
# 07/10: com a FILIAL, o preco de Todos os produtos e o DELA (o mesmo
# da ALTERACOES_PRECO), nao a media das filiais
_tp_a = next(t_ for t_ in _mk_a["tabelas"] if t_["titulo"] == "Todos os produtos")
_tp_b = next(t_ for t_ in _mk_b["tabelas"] if t_["titulo"] == "Todos os produtos")
_pf_ = {}
for (_f_, _p_), _v_ in (_ctx_pp.comercial.get("precos_filial") or {}).items():
    if _ctx_pp.filial(_f_[1:] if _f_.startswith("4") else _f_) == _fil_mk:
        _pf_[_p_] = _v_
_ok_pp.append(
    _tp_a["colunas"][9]["nome"] == "PRC. TABELA MÉD."
    and (not _fil_mk or (_tp_b["colunas"][9]["nome"] == "PRC. TABELA"
         and all(abs((l_[9] or 0) - _pf_.get(l_[0], (0, 0))[0]) < 0.005
                 for l_ in _tp_b["linhas"][:300]))))
_pe_ = rn.parcial_entregas(_ctx_pp, "hoje")
_ok_pp.append(
    [l_["titulo"] for l_ in _pe_["listas"]] == [
        "Entregas pendentes", "Pedidos pendentes de faturamento"]
    and all(len(l_["linhas"]) <= rn.MAX_LISTA_PARCIAL
            for l_ in _pe_["listas"])
    and not _pe_["rankings"] and not _pe_["tabela"]
    and "VENDEDOR" not in str([l_["colunas"] for l_ in _pe_["listas"]])
    and _pe_["numeros"]["pedidos"] == len(rn.pedidos_em_aberto(_ctx_pp)[
        "tabelas"][0]["linhas"]))
# (09/10) a entrega ja ENTREGUE (ou cancelada) nao e pendente na parcial
_te_ = rn.entregas(_ctx_pp)["tabelas"][0]
_ie_ = {c["nome"]: i for i, c in enumerate(_te_["colunas"])}
# (a NF pode repetir em outra filial: confere NF + cliente)
_nfs_ent = {(rn.texto(l[_ie_["NF"]]), rn.texto(l[_ie_["CLIENTE"]]))
            for l in _te_["linhas"]
            if rn.texto(l[_ie_["ETAPA"]]).upper() in ("ENTREGUE", "CANCELADA")}
_nfs_pend = {(rn.texto(l_[3]), rn.texto(l_[1][1] if isinstance(l_[1], tuple)
                                        else l_[1]))
             for l_ in _pe_["listas"][0]["linhas"]}
_ok_pp.append(not (_nfs_ent & _nfs_pend))
with _tf_p.TemporaryDirectory() as _tmp_p:
    _ok_arq = _ok_arq and _pi.gravar_png(_pe_, _tmp_p).stat().st_size > 10000
checar(all(_ok_pp) and _ok_arq and _de.weekday() < 5 and _de < date.today()
       and '"Parcial Pedidos"' in (AQUI / "bap_relatorios.py").read_text(
           "utf-8"),
       "Parciais: pedidos e visitas (acumulado, D-1, hoje) por supervisor + "
       "top 5; entregas por cliente (sem vendedor); imagem PNG e PDF")

# (13/10) SALDO: o financeiro da condicao fora; acima de 15% desconta (sem
# autorizacao tambem), so o PRICE nao conta; SEM AUTORIZACAO de 01/08/2026
# em diante fica vermelho (grave) no Saldo e no Farol de Pedidos
import autorizacoes as _au  # noqa: E402
_ctx_s = rn.Contexto(AQUI)
_sp_all = rn.saldos_dos_pedidos(_ctx_s)
_ok_s = True
for (_f_s, _p_s), _x in list(_sp_all.items())[:400]:
    if _x["situacao"] == rn.SIT_DENTRO:
        _ok_s = _ok_s and _x["conta"] >= 0
    elif _x["situacao"] == rn.SIT_AUT_PRICE:      # (22/10) fora do saldo
        _ok_s = _ok_s and abs(_x["conta"] - (_x["frete"] or 0)) < 0.01
    else:
        _ok_s = _ok_s and abs(_x["conta"] - _x["saldo"]) < 0.01
    _ok_s = _ok_s and (not _x["grave"] or _x["situacao"] == rn.SIT_SEM_AUT)
_d_s = [rn.saldo_do_pedido(_ctx_s, [dict(
    tipo="VND", filial="0101099", pedido="999999", nf="1", cliente="000001",
    vend="", cond=_c, cod="X", qtd=1.0, valor=_v, p_tab=100.0,
    dt_nf=date(2026, 9, 1), dt_pedido=date(2026, 9, 1))]) for _c, _v in (
    ("001", 83.55), ("001", 85.0), ("001", 80.0))]
_fin_av = rn.fin_da_cond(_ctx_s, "001")
_ok_s = _ok_s and (not _fin_av or (
    _d_s[0]["situacao"] == rn.SIT_DENTRO and abs(_d_s[0]["pcom"] - 15) < 0.1
    and _d_s[1]["situacao"] == rn.SIT_DENTRO
    and _d_s[2]["situacao"] == rn.SIT_SEM_AUT and _d_s[2]["grave"]
    and _d_s[2]["conta"] < 0))
_rs_ = rn.montar("vc_saldo", AQUI)
_rpp = rn.montar("pv_pedidos", AQUI)
_tps = next(t_ for t_ in _rpp["tabelas"] if t_["titulo"] == "Pedidos")
_nps = [c_["nome"] for c_ in _tps["colunas"]]
_cps = {c_["nome"]: c_ for c_ in _tps["colunas"]}
_ctx_d = rn.Contexto(AQUI)
_k_d = next(iter(rn.saldos_dos_pedidos(_ctx_d)))
_det = rn.detalhe_pedido(_ctx_d, _k_d[0], _k_d[1], "")
checar(_ok_s and _cps["CÓD. AUTORIZAÇÃO"].get("oculta")
       and _cps["AUTORIZADO POR"].get("oculta") and not _tps.get("edicao")
       and _det and (_det.get("autorizacao") or {}).get("chave")
       and "NO SALDO" in [c_["nome"] for c_ in _rs_["tabelas"][0]["colunas"]]
       and _au.chave("0101004", "106") == "0101004|000106",
       "Saldo: financeiro da condição fora, acima de 15% desconta (só o "
       "aprovado pelo Price não); autorização só no Farol de Pedidos")

# (12/10) Painel Executivo › Clientes (desafio, gap, IPP, curva, segmento) e
# Produtos (curva do Giro, M3M, variacao, markup, estoque)
_tc_ = next(t_ for t_ in _pa["tabelas"] if t_["titulo"] == "Clientes")
_tp_ = next(t_ for t_ in _pa["tabelas"] if t_["titulo"] == "Produtos")
_nc_ = [c_["nome"] for c_ in _tc_["colunas"]]
_np_ = [c_["nome"] for c_ in _tp_["colunas"]]
_seg_p = next(t_ for t_ in _pa["tabelas"] if t_["titulo"] == "Por segmento")
checar({"SEGMENTO", "CURVA", "DESAFIO", "REAL", "GAP", "% ATING.", "M3M",
        "IPP"} <= set(_nc_) and {"CURVA", "M3M", "VAR. x M3M", "MKP %",
                                 "ESTOQUE"} <= set(_np_)
       and abs(sum(l_[_nc_.index("DESAFIO")] or 0 for l_ in _tc_["linhas"])
               - (_seg_p["total"][1] or 0)) < 1
       and abs(_tc_["total"][_nc_.index("M3M")]
               - _tp_["total"][_np_.index("M3M")]) < 1
       and {"SEGMENTO", "CURVA"} <= set(_tc_["filtros"])
       and "CURVA" in _tp_["filtros"] and callable(_tc_.get("total_de")),
       "Painel › Clientes com desafio, gap, IPP, curva e segmento; Produtos "
       "com curva, M3M e variação (o M3M fecha entre as duas)")

# (12/10) VISAO EXECUTIVA: o placar de todos os farois com o impacto no
# faturamento, na primeira aba do Painel Executivo (e a tabela Farois)
_vx = (_pa.get("painel_pre") or {}).get("painel") or {}
_vx_b = {b_["tipo"]: b_ for b_ in _vx.get("blocos") or []}
_vx_t = next((t_ for t_ in _pa["tabelas"] if t_["titulo"] == "Faróis"), None)
_vx_c = (_vx_b.get("placar") or {}).get("cartoes") or []
checar(len(_vx_c) == 16 and _vx_t and len(_vx_t["linhas"]) == 16
       and {"Meta x Real", "M3M · média 3 meses", "Clientes", "Visitas",
            "Expositores", "Pedidos em aberto", "Pedidos excluídos",
            "Giro de produtos", "Entregas", "Devoluções", "Garantias",
            "Inadimplência", "Indicadores executivos"}
       <= {c_["farol"] for c_ in _vx_c}
       and "insights" in _vx_b and "hbarras" in _vx_b
       and all(c_["tom"] in ("ok", "atencao", "alerta", "neutro")
               for c_ in _vx_c)
       and not any("Visão executiva fora" in a_ for a_ in _pa["avisos"]),
       f"Visão executiva: {len(_vx_c)} faróis no placar com o impacto no "
       "faturamento + o que move o faturamento")

# (12/10) AUDITORIA: segmento, categoria e familia batendo farol a farol -
# CLIENTES, META, REAL e POSITIVACAO iguais no Painel Executivo, no Farol
# de Clientes e no Farol de Metas
def _por(t_, ch, cols):
    n_ = [c["nome"] for c in t_["colunas"]]
    return {str(l[n_.index(ch)]): [round(float(l[n_.index(c)] or 0))
                                   for c in cols] for l in t_["linhas"]}


def _t(r_, tit):
    return next(t_ for t_ in r_["tabelas"] if t_["titulo"] == tit)


_aud_ok, _aud_txt = True, []
for _prm_a in ({}, {"CATEGORIA": "BATERIA"}):
    _pa_ = rn.montar("vc_painel", AQUI, params=_prm_a)
    _ca_ = rn.montar("vc_base", AQUI, params=_prm_a)
    _P = _por(_t(_pa_, "Por segmento"), "SEGMENTO",
              ["CLIENTES", "DESAFIO", "REAL", "POSITIVAÇÃO"])
    _C = _por(_t(_ca_, "Por segmento"), "SEGMENTO",
              ["CLIENTES", "META", "REALIZADO", "COMPRARAM NO MÊS"])
    for _k in set(_P) | set(_C):
        if any(abs(a - b) > 1 for a, b in zip(_P.get(_k, [0] * 4),
                                              _C.get(_k, [0] * 4))):
            _aud_ok = False
            _aud_txt.append(f"{_prm_a} {_k}: {_P.get(_k)} x {_C.get(_k)}")
    if not _prm_a:
        _ma_ = rn.montar("vc_meta", AQUI)
        _M = _por(_t(_ma_, "Por segmento"), "SEGMENTO",
                  ["CLIENTES ATIVOS", "FAT. META", "FAT. REAL", "POSIT. REAL"])
        for _k in set(_P) | set(_M):
            if any(abs(a - b) > 1 for a, b in zip(_P.get(_k, [0] * 4),
                                                  _M.get(_k, [0] * 4))):
                _aud_ok = False
                _aud_txt.append(f"metas {_k}: {_P.get(_k)} x {_M.get(_k)}")
        for _tp, _tm, _ch in (("Por categoria", "Por categoria", "CATEGORIA"),
                              ("Por família", "Por família da peça",
                               "FAMÍLIA")):
            _P2 = _por(_t(_pa_, _tp), _ch, ["DESAFIO", "REAL", "POSITIVAÇÃO"])
            _M2 = _por(_t(_ma_, _tm), _ch, ["FAT. META", "FAT. REAL",
                                            "POSIT. REAL"])
            for _k in set(_P2) | set(_M2):
                if _P2.get(_k, [0] * 3) != _M2.get(_k, [0] * 3) and any(
                        abs(a - b) > 1 for a, b in zip(_P2.get(_k, [0] * 3),
                                                       _M2.get(_k, [0] * 3))):
                    _aud_ok = False
                    _aud_txt.append(f"{_ch} {_k}: {_P2.get(_k)} x "
                                    f"{_M2.get(_k)}")
        _tot_p = _t(_pa_, "Por segmento")["total"]
        _aud_ok = _aud_ok and sum(l[6] for l in _t(
            _pa_, "Por segmento")["linhas"]) >= _tot_p[6]
checar(_aud_ok, "Auditoria: segmento, categoria e família iguais no Painel "
       "Executivo, Farol de Clientes e Farol de Metas " + "; ".join(
           _aud_txt[:4]))

# (14/10) AUDITORIA DA DIRETORIA: DESCONTO COMERCIAL igual no Painel, Saldo,
# Pedidos, Markup e Resumo; POSITIVACAO do Farol de Metas = clientes
# distintos (= Painel); a linha do Farol de Pedidos leva a base so dos
# itens dela (pedido em varias notas)
def _kv(r_, rot):
    return next((k_["valor"] for k_ in r_.get("kpis") or []
                 if k_["rotulo"] == rot), None)


_ctx_a = rn.Contexto(AQUI)
_vnd_a = [i_ for i_ in _ctx_a.tabela["itens"] if i_["tipo"] == "VND"]
_dc_a = rn.desconto_comercial(_ctx_a, _vnd_a)
_sp_a = rn.saldos_dos_pedidos(_ctx_a).values()
_dc_s = (sum(x_["dcom"] for x_ in _sp_a) / sum(x_["base"] for x_ in _sp_a)
         * 100.0) if _sp_a else None
_pa_a = rn.montar("vc_painel", AQUI)
_ma_a = rn.montar("vc_meta", AQUI)
_seg_a = next(t_ for t_ in _pa_a["tabelas"] if t_["titulo"] == "Por segmento")
_tp_a = next(t_ for t_ in rn.montar("pv_pedidos", AQUI)["tabelas"]
             if t_["titulo"] == "Pedidos")
_n_a = [c_["nome"] for c_ in _tp_a["colunas"]]
_g_a = defaultdict(float)
for l_ in _tp_a["linhas"]:
    if l_[_n_a.index("SITUAÇÃO")] not in ("EM ABERTO", "EXCLUÍDO"):
        _g_a[l_[_n_a.index("CHAVE")] if "CHAVE" in _n_a else
             l_[_n_a.index("PEDIDO")]] += l_[_n_a.index("R$ TABELA")] or 0
_pos_m = _kv(_ma_a, "Positivação")
checar(_dc_a is not None and _dc_s is not None and abs(_dc_a - _dc_s) < 0.01
       and _kv(_pa_a, "Desconto comercial") is not None
       and _kv(_pa_a, "Desconto médio") is None
       and (_pos_m is None or str(_pos_m).replace(".", "")
            == rn.br(_seg_a["total"][7]).replace(".", ""))
       and all(v_ <= max(x_["base"] for x_ in _sp_a) + 1
               for v_ in _g_a.values()),
       f"Diretoria: desconto comercial {rn.br(_dc_a or 0, 2)}% igual em todos"
       f" os faróis; positivação do Farol de Metas {_pos_m} = Painel "
       f"{_seg_a['total'][7]}")

# (14/10) POSITIVACAO = comprou e nao devolveu tudo (liquido do mes > 0)
# em todo farol; MARKUP so do faturado (o em aberto tem cartao proprio);
# PMZ DISTRIBUIDORA e CNPJ interno
import bap_dados as _bd  # noqa: E402
_ctx_p = rn.Contexto(AQUI)
_liq_p = defaultdict(float)
for i_ in _ctx_p.tabela["itens"]:
    v_ = rn._liquido(i_) if i_["dt_nf"] else None
    if v_ is not None:
        _liq_p[(i_["cliente"], rn.mes_de(i_["dt_nf"]))] += v_
_meses_p = {m_ for _c, m_ in _liq_p}
_ok_p = all(_liq_p[(c_, m_)] > 0 for m_ in _meses_p
            for c_ in rn.clientes_positivados(_ctx_p, m_))
_mk_p = rn.montar("vc_markup", AQUI)
_tpm = next(t_ for t_ in _mk_p["tabelas"] if t_["titulo"] == "Por pedido")
_n_m = [c_["nome"] for c_ in _tpm["colunas"]]
_fat_m = [l_[_n_m.index("R$ VENDA")] for l_ in _tpm["linhas"]
          if l_[_n_m.index("SITUAÇÃO")] == "FATURADO"]
_vend_k = next(k_["valor"] for k_ in _mk_p["kpis"] if k_["rotulo"] == "Venda")
_tuf = next(t_ for t_ in _mk_p["tabelas"] if t_["titulo"] == "Por UF")
_tprod = next(t_ for t_ in _pa_a["tabelas"] if t_["titulo"] == "Produtos")
_n_uf = [c_["nome"] for c_ in _tuf["colunas"]]
_n_pr = [c_["nome"] for c_ in _tprod["colunas"]]
checar(_ok_p and _vend_k == rn.moeda(sum(_fat_m))
       and abs((_tuf["total"][_n_uf.index("R$ VENDA")] if _tuf.get("total")
                else 0) - sum(_fat_m)) < 0.01
       and (not _fat_m or _tprod["total"][_n_pr.index("MKP %")] is not None)
       and _bd._interno("PMZ DISTRIBUIDORA SA", "PEMAZA CD")
       and not _bd._interno("AUTO PECAS PMZINHO", ""),
       "Positivação = comprou e não devolveu tudo; Markup só do faturado "
       "(= Painel); PMZ DISTRIBUIDORA interna")

# (14/10) .json da base de clientes com LATITUDE e LONGITUDE (texto, 6
# casas; vazio quando o cliente nao foi localizado)
import planner_nucleo as _pn14  # noqa: E402
_bp14 = _pn14.base_protheus(_cfg_r, _cli_r)
checar(bool(_bp14) and all({"LATITUDE", "LONGITUDE"} <= set(x_) for x_ in _bp14)
       and _pn14.coordenada_protheus(-3.0945621, "-60,0240614")
       == ("-3.0945621", "-60.0240614")
       and _pn14.coordenada_protheus(-3.010709, -60.0082203)
       == ("-3.010709", "-60.0082203")
       and '"LATITUDE" : "-3.010709"' in _pn14.json_protheus(
           [{"LATITUDE": "-3.010709"}])
       and _pn14.coordenada_protheus(None, None) == ("", "")
       and _pn14.coordenada_protheus(0, 0) == ("", ""),
       f".json da base de clientes com LATITUDE/LONGITUDE "
       f"({sum(1 for x_ in _bp14 if x_['LATITUDE'])} de {len(_bp14)} com ponto)")

# (14/10) GOVERNANCA: a autorizacao de venda so se grava no Farol de
# Pedidos; o Farol de Saldo e a janela do pedido nos outros farois so leem
import bap_relatorios as _br14  # noqa: E402
_rs14 = rn.montar("vc_saldo", AQUI)
checar(not any(t_.get("edicao") for t_ in _rs14["tabelas"])
       and _br14.AUTORIZA_EM == ("pv_pedidos",)
       and hasattr(_br14.DetalhePedido, "_autorizacao_leitura"),
       "Autorização de venda: grava só no Farol de Pedidos; Saldo só lê")

# (14/10) FAROL DE NCC (Pos-venda): creditos dos clientes a compensar, da
# aba ftNCC (BAP Tools > NCC Pendentes). Sem a aba: aviso, sem erro.
import bap_automation as _ba14  # noqa: E402
_r_ncc0 = rn.montar("pl_ncc", AQUI)
_orig_aba = rn._ler_aba_da_tabela
_cab_ncc = ("E1_FILIAL", "E1_PREFIXO", "E1_NUM", "E1_PARCELA", "E1_TIPO",
            "E1_CLIENTE", "E1_LOJA", "E1_NOMCLI", "E1_EMISSAO", "E1_VENCTO",
            "E1_VENCREA", "E1_VALOR", "E1_SALDO")
_cli_ncc = next(iter(rn.Contexto(AQUI).tabela["clientes"]))
rn._ler_aba_da_tabela = lambda c_, a_: [_cab_ncc, (
    "0101001", "1", "000000178", "01", "NCC", _cli_ncc, "01", "CLIENTE X",
    "20260904", "20260904", "20260904", 2231.52, 2231.52), (
    "0101001", "1", "000000179", "01", "NCC", "000999", "01",
    "FRW ATACADO LTDA", "20260101", "20260101", "20260101", 500.0, 0.0)] \
    if a_ == "ftNCC" else _orig_aba(c_, a_)
try:
    _r_ncc = rn.montar("pl_ncc", AQUI)
finally:
    rn._ler_aba_da_tabela = _orig_aba
_t_ncc = next(t_ for t_ in _r_ncc["tabelas"] if t_["titulo"] == "NCC pendentes")
_n_ncc = [c_["nome"] for c_ in _t_ncc["colunas"]]
checar(any("ftNCC" in a_ for a_ in _r_ncc0["avisos"])
       and len(_t_ncc["linhas"]) == 1
       and _t_ncc["linhas"][0][_n_ncc.index("SALDO")] == 2231.52
       and _t_ncc["linhas"][0][_n_ncc.index("A COMPENSAR")] in (
           rn.NCC_TITULO, rn.NCC_PEDIDO, rn.NCC_COMPRA, rn.NCC_CONTATO)
       and {"Por cliente", "Por filial", "Por vendedor", "Por supervisor"}
       <= {t_["titulo"] for t_ in _r_ncc["tabelas"]}
       and ("Farol de NCC", "pl_ncc") in [b_ for _a, _p, bs_ in
                                          __import__("bap_central").QUADRADOS
                                          for b_ in bs_]
       and any(r_["id"] == "ncc" and r_["aba_excel"] == "ftNCC"
               and r_.get("criar_aba") for r_ in _ba14.RELATORIOS),
       "Farol de NCC: saldo a compensar por NCC/cliente (sem saldo e CNPJ "
       "interno fora), no quadrado do Pós-venda; robô baixa a NCC Pendentes")

# (20/10, Alexandre) Farol de NCC: A COMPENSAR e DT. ULT. MOV. editaveis
# (diario ncc_controle) e o SLA de 3 dias uteis (FINALIZADO / CANCELADO
# fora do SLA; mudou o status sem data = movimentacao hoje)
import tempfile as _tf20  # noqa: E402
import ncc_controle as _nc20  # noqa: E402
from datetime import date as _d20  # noqa: E402
_ed20 = _t_ncc.get("edicao") or {}
_ok20 = (_ed20.get("modulo") == "ncc"
         and [c_["campo"] for c_ in _ed20.get("campos", [])] == [
             "status", "dt_mov"]
         and set(_nc20.STATUS_NOVOS) <= set(_ed20["campos"][0]["opcoes"])
         and {"SLA NCC", "DT. ÚLT. MOV.", "D.U. S/ MOV."} <= set(_n_ncc))
_ute = lambda a_, b_: __import__("bap_dados").dias_uteis_entre(a_, b_, ())  # noqa
_mai = lambda d_, n_: __import__("bap_dados").somar_uteis(d_, n_, ())  # noqa
_ok20 = _ok20 and _nc20.sla("SOLICITADO FINANCEIRO", _d20(2026, 10, 20),
                            None, _d20(2026, 10, 23), _ute, _mai)[2] == \
    "NO PRAZO" and _nc20.sla("CONTATAR", _d20(2026, 10, 20), None,
                             _d20(2026, 10, 26), _ute, _mai)[2] == \
    "ATRASADO" and _nc20.sla("FINALIZADO", _d20(2026, 9, 1), None,
                             _d20(2026, 10, 26), _ute, _mai)[2] == "ENCERRADO"
with _tf20.TemporaryDirectory() as _tmp20:
    _nc20.gravar(_tmp20, {"0101001|1|178|01": {"status": "REEMBOLSADO"}},
                 hoje=_d20(2026, 10, 21))
    _nc20.gravar(_tmp20, {"0101001|1|178|01": {"dt_mov": "22/10/2026"}})
    _l20 = _nc20.ler(_tmp20).get("0101001|1|178|01") or {}
    _ok20 = _ok20 and _l20.get("status") == "REEMBOLSADO" and \
        _l20.get("dt_mov") == _d20(2026, 10, 22)
checar(_ok20, "Farol de NCC: A COMPENSAR e DT. ÚLT. MOV. editáveis (diário "
       "por máquina), SLA de 3 dias úteis; finalizado/cancelado fora do SLA")

# (14/10) Farol de Pedidos > Solicitacao BAP: a mais nova em cima pela
# DATA + HORA (texto dd/mm/aaaa ou data) e os filtros de cima valendo
_q14 = _br14.AbaSolicitacaoBap._quando
_ls14 = [["03/09/2026", "11:46"], ["13/10/2026", "09:53"],
         [None, None], ["08/10/2026", "11:36"]]
_ord14 = sorted(_ls14, key=lambda l: _q14(l, 0, 1), reverse=True)
checar([l[0] for l in _ord14] == ["13/10/2026", "08/10/2026", "03/09/2026",
                                  None]
       and hasattr(_br14.AbaSolicitacaoBap, "aplicar")
       and _br14.AbaSolicitacaoBap._norm("Belém") == "BELEM",
       "Solicitação BAP: ordem pela data e hora; cidade/UF/produto/vendedor "
       "de cima filtram as sub-abas")

# (14/10) FAROL DE GARANTIAS novo (garantias.py: diario por maquina) e a
# regra das cores: linha pintada so em Pedidos, Markup e Saldo; nos outros
# o alerta vai para a coluna (selo no STATUS/SITUACAO/PRAZO, SLA pintado)
import garantias as _gm14  # noqa: E402
with _tfv.TemporaryDirectory() as _dgm:
    _gs = [{"ticket": "1001", "dt_solicitacao": "01/08/2026",
            "cliente": "R C MELO", "contato_nome": "R C MELO",
            "contato_fone": "(98) 98123-5692", "status": "EM TRATATIVA",
            "resultado": "PENDENTE", "qtd": "1", "observacao": ""},
           {"ticket": "1002", "dt_solicitacao": "10/10/2026",
            "cliente": "Fulano de Tal", "status": "ABERTO"}]
    _base = [{"cod": "011188", "nome": "R C MELO LTDA",
              "fantasia": "EDIM MECANICO",
              "contato": "Rayane · (98) 8123-5692"},
             {"cod": "000001", "nome": "OUTRO MELO", "fantasia": "",
              "contato": ""}]
    _n_cas = _gm14.casar_clientes(_gs, _base)
    _gm14.importar(_dgm, _gs)
    _gm14.importar(_dgm, _gs)                     # de novo: nao duplica
    _gm14.gravar(_dgm, "1001", {"status": "FINALIZADA",
                                "resultado": "PROCEDENTE"})
    _lg = _gm14.ler(_dgm)
    _st = _gm14.situacao(_lg["1002"], date(2026, 11, 20))
    checar(_n_cas == 1 and _gs[0]["cod_cliente"] == "011188"
           and _gs[0]["contato_nome"] == "Rayane"
           and "Contato do ticket" in _gs[0]["observacao"]
           and len(_lg) == 2 and _lg["1001"]["status"] == "FINALIZADA"
           and _lg["1001"]["dt_fechamento"]
           and _st["prevista"] == date(2026, 10, 30) and _st["atrasada"]
           and _gm14.novo_ticket(_dgm) == "G-0001",
           "Garantias: cliente e contato pelo nome na base, importação sem "
           "duplicar, edição só acrescenta, prazo de 15 dias úteis")
# (06/11, Alexandre) DT. FECHAMENTO = 15 dias uteis (editavel); fechada: o
# SLA para e fica cinza; FECHADA verde no prazo, verde-oliva com atraso
_g06 = {"dt_solicitacao": "03/11/2026", "status": "FINALIZADA",
        "dt_fechamento": "20/11/2026"}
_s06a = _gm14.situacao(_g06, date(2026, 12, 15))
_s06b = _gm14.situacao(dict(_g06, dt_fechamento="26/11/2026"),
                       date(2026, 12, 15))
_s06c = _gm14.situacao(dict(_g06, status="EM TRATATIVA",
                            dt_prazo="10/12/2026"), date(2026, 12, 8))
_s06d = _gm14.situacao(dict(_g06, status="EM TRATATIVA"), date(2026, 11, 10),
                       {date(2026, 11, 20)})
checar(_s06a["prevista"] == date(2026, 11, 24) and _s06a["sla"] == 17
       and _s06a["tom_sla"] == "cinza"
       and _s06a["chave_prazo"] == "FECHADA NO PRAZO"
       and _s06b["chave_prazo"] == "FECHADA COM ATRASO"
       and _s06c["prevista"] == date(2026, 12, 10) and _s06c["prazo_editado"]
       and _s06c["tom_sla"] == "atencao" and not _s06c["atrasada"]
       and _s06d["prevista"] == date(2026, 11, 25)
       and _s06d["tom_sla"] == "ok" and "dt_prazo" in _gm14.CAMPOS,
       "Garantias: DT. FECHAMENTO = 15 dias úteis (com feriado) ou a "
       "editada; fechada com SLA cinza; FECHADA no prazo × com atraso")
# (06/11, Alexandre: "Acrescente para poder editar o ticket") a troca do
# numero e uma linha do diario; a garantia segue no numero novo
with _tfv.TemporaryDirectory() as _dgm6:
    _gm14.gravar(_dgm6, "374504", {"dt_solicitacao": "08/07/2026"},
                 agora=datetime(2026, 11, 1, 10))
    _gm14.gravar(_dgm6, "G-0009", {"dt_solicitacao": "01/11/2026"},
                 agora=datetime(2026, 11, 1, 11))
    _r6a = _gm14.renomear(_dgm6, "374504", "G-0009")
    _r6b = _gm14.renomear(_dgm6, "374504", "G-0010",
                          agora=datetime(2026, 11, 2, 9))
    _gm14.gravar(_dgm6, "G-0010", {"status": "FINALIZADA"},
                 agora=datetime(2026, 11, 3, 9))
    _l6 = _gm14.ler(_dgm6)
checar(_r6a.startswith("já existe") and _r6b == ""
       and sorted(_l6) == ["G-0009", "G-0010"]
       and _l6["G-0010"]["dt_solicitacao"] == "08/07/2026"
       and _l6["G-0010"]["status"] == "FINALIZADA"
       and _gm14.renomear(_dgm6, None, "") != ""
       and _br14.DialogoGarantia.CAMPOS[0][0] == "ticket",
       "Garantia: ticket editável (não repete número; a história segue no "
       "número novo)")
# (14/10) o cadastro do cliente editavel na garantia: vale o da garantia,
# em branco o da base (a base nao muda)
with _tfv.TemporaryDirectory() as _dgm2:
    _gm14.gravar(_dgm2, "2001", {"cli_cidade": "SAO LUIS", "cli_bairro": ""})
    _cad = _gm14.cadastro(_gm14.ler(_dgm2)["2001"],
                          {"cli_cidade": "PACO DO LUMIAR",
                           "cli_bairro": "CENTRO", "cli_vendedor": "LEANDRO"})
checar(_cad["cli_cidade"] == "SAO LUIS" and _cad["cli_bairro"] == "CENTRO"
       and _cad["cli_vendedor"] == "LEANDRO"
       and {k for k, _ in _gm14.CAMPOS_CLIENTE} <= set(_gm14.CAMPOS)
       and hasattr(_br14.DialogoGarantia, "_trocou_cliente"),
       "Garantia: cadastro do cliente editável (fica na garantia; em branco "
       "vale a base)")
_rg14 = rn.montar("pl_garantias", AQUI)
_tg14 = next(t_ for t_ in _rg14["tabelas"] if t_["titulo"] == "Garantias")
_ng14 = [c_["nome"] for c_ in _tg14["colunas"]]
_re14 = rn.montar("pl_entregas", AQUI)
_rp14 = rn.montar("pv_pedidos", AQUI)
checar({"STATUS", "RESULTADO ANÁLISE", "DT. SOLICITAÇÃO", "DT. FECHAMENTO",
        "SLA ATUAL", "CÓD. CLIENTE", "CÓD. PRODUTO", "QTD",
        "CONTATO CLIENTE", "CIDADE"} <= set(_ng14)
       and _tg14["colunas"][_ng14.index("DESCRIÇÃO PRODUTO")].get("oculta")
       and _tg14.get("garantia") and callable(
           (_rg14.get("garantia") or {}).get("dados"))
       and hasattr(_br14, "DialogoGarantia")
       and all(not x_ for t_ in _re14["tabelas"] for x_ in t_["tons"])
       and "pv_pedidos" in rn.LINHA_PINTADA
       and rn.CORES_SINAL["ATRASADA"][1] == "#B3261E",
       "Farol de Garantias (colunas, duplo clique, nova garantia); linhas "
       "sem cor fora de Pedidos/Markup/Saldo")

# (15/10) FAROL DE PRECO: faturamento x volume x preco mes a mes; o efeito
# preco (mesmo item) + volume + mix fecha a variacao do faturamento
_cp = rn.comparar_precos(
    {("F", "A"): {"v": 88.0, "q": 8.0, "t": 88.0},
     ("F", "C"): {"v": 30.0, "q": 1.0, "t": 30.0}},
    {("F", "A"): {"v": 100.0, "q": 10.0, "t": 100.0},
     ("F", "B"): {"v": 50.0, "q": 5.0, "t": 50.0}})
_rpr = rn.montar("vc_preco", AQUI)
_tpr = {t_["titulo"]: t_ for t_ in _rpr["tabelas"]}
_lpr = [l for l in _tpr["Por categoria"]["linhas"]
        if l[rn.P_DF] is not None and l[rn.P_EP] is not None]
checar(abs(_cp["var_p"] - 10) < 1e-6 and abs(_cp["ef_p"] - 8) < 1e-6
       and abs(_cp["ef_v"] + 60) < 1e-6 and abs(_cp["ef_mix"] - 20) < 1e-6
       and rn.leitura_preco(_cp["var_p"], _cp["var_fat"]) == rn.L_QUEDA
       and {"Por categoria", "Por família", "Total BAP",
            "Reajustes por produto"} <= set(_tpr)
       and all(abs(l[rn.P_EP] + l[rn.P_EV] + l[rn.P_EM] - l[rn.P_DF]) < 0.01
               for l in _lpr)
       and ("Farol de Preço", "vc_preco") in [(x[2], x[0])
                                              for x in rn.CATALOGO]
       and _rpr.get("painel"),
       f"Farol de Preço: efeito preço + volume + mix = variação do "
       f"faturamento ({len(_lpr)} categoria x mês)")

# (15/10) ROTA FIXA: o recalculo "so os alterados" deixa a rota de quem nao
# mudou como estava; e o cliente sem coordenada ganha o endereco proximo
import geografia as _geo15  # noqa: E402
import planner_nucleo as _nu15  # noqa: E402
_cf15 = _nu15.carregar_config(Path(AQUI) / "planner_config.json")
_cl15 = _nu15.ler_base_cliente(Path(AQUI) / "RELATORIOS" / "BASE_CLIENTE.xlsx")
_nu15.aplicar_parametros(_cf15, _cl15)
_k15 = lambda rs: {(r["COD_VENDEDOR"], r["CHAVE_CLIENTE"], r["DATA"],  # noqa
                    r["ORDEM_DE_VISITA"]) for r in rs}
_nu15.fotografar_rota(_cf15, _cl15)
_r0 = _k15(_nu15.gerar_rota(_cf15, _cl15))
_vs = sorted({x[0] for x in _r0})
_a15, _b15 = _vs[0], _vs[1]
_cf15.setdefault("excecoes", {})[next(x[1] for x in _r0 if x[0] == _a15)] = \
    {"vendedor": _b15}
for _c in _cl15:
    _c["RECEITA_PERIODO"] = _c["RECEITA_PERIODO"] * 2     # a base mudou
_nu15.aplicar_parametros(_cf15, _cl15)
_alt15 = _nu15.vendedores_alterados(_cf15, _cl15)
_r1 = _k15(_nu15.gerar_rota(_cf15, _cl15))
_fora = lambda rs: {x for x in rs if x[0] not in (_a15, _b15)}  # noqa: E731
_ap15 = [{"UF": "AM", "CIDADE": "MANAUS", "BAIRRO": "CENTRO",
          "ENDERECO": "AV EDUARDO RIBEIRO 500", "NUMERO": "500",
          "LATITUDE": -3.13, "LONGITUDE": -60.02},
         {"UF": "AM", "CIDADE": "MANAUS", "BAIRRO": "CENTRO",
          "ENDERECO": "AVENIDA EDUARDO RIBEIRO", "NUMERO": "520",
          "LATITUDE": None, "LONGITUDE": None}]
_geo15.aproximar_pontos(_ap15)
checar(_alt15["alterados"] == sorted([_a15, _b15])
       and _fora(_r0) == _fora(_r1)
       and _geo15.ponto_do_cliente(_ap15[1]) == (-3.13, -60.02,
                                                 "endereco proximo")
       and _ap15[1]["LATITUDE"] is None,
       "Planner: recalcular só os alterados mantém a rota de quem não mudou; "
       "sem coordenada = endereço mais próximo (só para a rota)")

# ---- 15/10: CLIENTES POR CIDADE (12 por cidade do interior), CADASTROS
# NOVOS na Parcial Visitas e o nome do contato do celular
_ctx15 = rn.Contexto(AQUI)
_cc15 = rn.clientes_por_cidade(_ctx15)
_v15 = next(iter(sorted(_cc15)), None)
_ok15 = rn.e_capital("AM", "Manaus") and rn.e_capital("MA", "São Luís") \
    and not rn.e_capital("MA", "IMPERATRIZ")
if _v15:
    _m15, _r15, _n15, _k15c = rn.cobertura_cidades(_ctx15, _v15)
    _ok15 = _ok15 and _m15 == 12 * len(_cc15[_v15]) and _r15 == sum(
        min(n_, 12) for n_ in _cc15[_v15].values()) and _r15 <= _m15
    _ok15 = _ok15 and not any(rn.e_capital(u_, c_) for u_, c_ in _cc15[_v15])
_cp15, _gp15 = rn._cols_farol("pessoa")
_nm15 = [c_["nome"] for c_ in _cp15]
_ok15 = _ok15 and ("CLI. P/ CIDADE", 3) in _gp15 and \
    _nm15.index("CID. META") == _nm15.index("CAD. % ATING.") + 1 and \
    "CID. META" not in [c_["nome"] for c_ in rn._cols_farol("territorio")[0]]
_dv15 = next((d for d in rn.destinatarios_parcial(_ctx15)
              if d["cargo"] == "VENDEDOR"), None)
if _dv15:
    _rp15 = rn.exportar_rh(_ctx15, parcial=_dv15)
    _tv15 = next(t_ for t_ in _rp15["tabelas"] if t_["titulo"] == "Por vendedor")
    _iv15 = [c_["nome"] for c_ in _tv15["colunas"]]
    _l15 = _tv15["linhas"][0]
    _m15b, _r15b = cobert_ = rn.cobertura_cidades(_ctx15, _dv15["cod"])[:2]
    _ok15 = _ok15 and _l15[_iv15.index("CID. META")] == _m15b \
        and _l15[_iv15.index("CID. REAL")] == _r15b \
        and any(k_["rotulo"] == "Clientes por cidade" for k_ in _rp15["kpis"]) \
        and abs(sum(c_.get("pdf_larg") or 0 for c_ in _tv15["colunas"]
                    if not c_.get("oculta") and not c_.get("pdf_oculta"))
                - rn.PDF_UTIL) < 1
checar(_ok15, "Parcial: CLI. P/ CIDADE (meta 12 por cidade do interior, real "
       "até 12 por cidade, % ating.) por pessoa, cartão e na largura do PDF")
_pv15 = rn.parcial_visitas(_ctx15, "acum")
_de15, _ate15, _x15 = rn.periodo_parcial(_ctx15, "acum")
_cad15 = sum(1 for c_ in _ctx15.tabela["clientes"].values()
             if c_.get("dtcad") and _de15 <= rn._dia(c_["dtcad"]) <= _ate15
             and rn._cod6(c_.get("vend") or "0") in {
                 rn._cod6(l_["cod_protheus"]) for l_ in
                 __import__("visitas_nucleo").registros(AQUI)
                 if _de15 <= l_["data"] <= _ate15 and l_.get("ativo")
                 and l_.get("cod_protheus")})
_t15 = _pv15["numeros"]["total"]
checar(any(c_[0] == "Cadastros novos" for c_ in _pv15["cartoes"])
       and _t15["cad"] <= _cad15
       and _pv15["tabela"]["total"][_pv15["tabela"]["colunas"].index(
           "CAD.")] == rn.br(_t15["cad"]),
       f"Parcial Visitas: CADASTROS NOVOS ({_t15['cad']}, meta "
       f"{_t15['m_cad']} = 1 por dia útil por vendedor)")
# (15/10) CADASTRO NOVO DO DIA CONTA COMO VISITA (parcial, farol e RV)
_rg15 = [l_ for l_ in __import__("visitas_nucleo").registros(AQUI)
         if _de15 <= l_["data"] <= _ate15]
_cr15 = rn.com_cadastro_como_visita(_ctx15, _rg15)
_mv15 = rn.meta_do_periodo(_ctx15)["acomp"]["recortes"].get("vendedor") or []
checar(sum(l_["visitas"] for l_ in _cr15) - sum(l_["visitas"] for l_ in _rg15)
       == sum(l_.get("cad_visita", 0) + l_.get("prosp_visita", 0)
              for l_ in _cr15)
       and all("cadastros_como_visita" in l_ for l_ in _mv15)
       and all((l_.get("visitas_realizadas") or 0) >=
               (l_.get("cadastros_como_visita") or 0) for l_ in _mv15),
       f"Visita: cadastro novo do dia soma na visita "
       f"(+{sum(l_.get('cad_visita', 0) for l_ in _cr15)} no período; "
       f"Farol de Metas/RV com cadastros_como_visita)")
# ---- (22/10, Alexandre) PROSPECCAO do Microsoft Forms como visita:
# validacao (CNPJ, prazo, base, cadastro do dia, lote, duplicado, vendedor
# pelo e-mail) e a soma na visita do dia (fora de rota; dia so com
# prospeccao ganha linha propria)
import prospeccao_forms as _pf22  # noqa: E402
from datetime import datetime as _dt22  # noqa: E402
_eq22 = {"ana@x.com": ("000001", "ANA", "AM"), "ana": ("000001", "ANA", "AM"),
         "bia": ("000002", "BIA", "PA")}
_d22 = date(2026, 10, 20)
_c22 = "11222333000181"
# (22/10, recado 1351) o dia da visita = o dia do ENVIO (hora de conclusao
# em UTC, passada para o fuso da UF do vendedor)
_r22 = [
    {"id": 1, "email": "ana@x.com", "vendedor": "ANA", "cnpj": _c22,
     "conclusao": _dt22(2026, 10, 20, 15)},
    {"id": 2, "email": "ana@x.com", "vendedor": "BIA", "cnpj": _c22,
     "conclusao": _dt22(2026, 10, 20, 16)},
    {"id": 3, "email": "ana@x.com", "cnpj": "11222333000182",
     "conclusao": _dt22(2026, 10, 20, 17)},
    {"id": 4, "email": "ana@x.com", "cnpj": "11.444.777/0001-61",
     "conclusao": _dt22(2026, 10, 21, 2, 30)},
    {"id": 5, "email": "zz@x.com", "vendedor": "?", "cnpj": _c22,
     "conclusao": _dt22(2026, 10, 20, 18)},
    {"id": 6, "email": "zz@x.com", "vendedor": "Bia", "cnpj":
     "11444777000161", "conclusao": _dt22(2026, 10, 21, 2, 30)},
    {"id": 7, "email": "ana@x.com", "cnpj": "11444777000161",
     "conclusao": _dt22(2026, 10, 16, 13)},
    {"id": 8, "email": "ana@x.com", "cnpj": "34028316000103",
     "conclusao": _dt22(2026, 10, 20, 13)},
    {"id": 9, "email": "ana@x.com", "cnpj": "60746948000112",
     "conclusao": _dt22(2026, 10, 20, 13)}]
_v22 = {x_["id"]: x_ for x_ in _pf22.validar(
    _r22, _eq22, {"34028316000103"}, {"60746948000112": _d22},
    {date(2026, 10, 16)})}
_st22 = {k_: v_["status"] for k_, v_ in _v22.items()}
checar(_pf22.cnpj_valido(_c22) and not _pf22.cnpj_valido("11222333000182")
       and _st22 == {1: "CONTA", 2: "DUPLICADO", 3: "CNPJ INVÁLIDO",
                     4: "CONTA", 5: "SEM VENDEDOR", 6: "CONTA",
                     7: "DIA DO LOTE", 8: "CLIENTE DA BASE",
                     9: "CADASTRADO NO DIA"}
       and _v22[2]["cod6"] == "000001" and "dono da conta" in _v22[2]["obs_bap"]
       and _v22[6]["cod6"] == "000002"
       and _v22[4]["dia"] == _d22 and _v22[6]["dia"] == _d22
       and _pf22.dia_do_envio(_dt22(2026, 10, 21, 3, 30), "PA")
       == date(2026, 10, 21),
       f"Prospecção (Forms): validação das respostas, dia = dia do envio no "
       f"fuso da UF ({_st22})")
_rg22 = [l_ for l_ in __import__("visitas_nucleo").registros(AQUI)
         if l_.get("cod_protheus")]
if _rg22:
    _ctx22 = rn.Contexto(AQUI)
    _ctx22._cad_dia = {}
    _l22 = _rg22[0]
    _cp22 = rn._cod6(_l22["cod_protheus"])
    _dias22 = {l_["data"] for l_ in _rg22 if rn._cod6(l_["cod_protheus"])
               == _cp22}
    _sem22 = max(_dias22) + __import__("datetime").timedelta(days=30)
    _ctx22._prosp_dia = {(_cp22, _l22["data"]): 2, (_cp22, _sem22): 3}
    _cv22 = rn.com_cadastro_como_visita(_ctx22, _rg22)
    _a22 = [l_ for l_ in _cv22 if l_.get("prosp_visita")]
    _so22 = [l_ for l_ in _a22 if l_.get("so_prospeccao")]
    _ok22 = (len(_cv22) == len(_rg22) + 1 and len(_so22) == 1
             and _so22[0]["visitas"] == 3 and _so22[0]["data"] == _sem22
             and _so22[0]["primeiro"] is None
             and sum(l_["visitas"] for l_ in _cv22)
             - sum(l_["visitas"] for l_ in _rg22) == 5
             and any(l_["data"] == _l22["data"] and l_["prosp_visita"] == 2
                     and l_["vis_fora"] >= 2 for l_ in _a22)
             and len(rn.com_cadastro_como_visita(
                 _ctx22, _rg22, ate=max(_dias22))) == len(_rg22))
    checar(_ok22, "Prospecção (Forms): soma na visita do dia como fora de "
           "rota; dia só com prospecção vira linha própria (sem jornada)")
_fv22 = rn.montar("vc_visitas", AQUI)
_tp22 = next((t_ for t_ in _fv22["tabelas"] if t_["titulo"] == "Prospecção"),
             None)
checar(_tp22 is not None and "STATUS" in _tp22["filtros"]
       and [c_["nome"] for c_ in _tp22["colunas"]][:6] == [
           "DATA", "HORA", "DIA", "SUPERVISOR", "VENDEDOR", "STATUS"]
       and "REGISTRADO EM" not in [c_["nome"] for c_ in _tp22["colunas"]]
       and _tp22["kpis_de"](_tp22["linhas"]),
       f"Farol de Visita: aba Prospecção ({len(_tp22['linhas']) if _tp22 else 0}"
       f" resposta(s) no período)")
# (22/10, Alexandre) Farol de Visita sem a coluna CARGO (nem o filtro)
_tc22 = {t_["titulo"]: t_ for t_ in _fv22["tabelas"]}
checar(all(c_["oculta"] for t_n in ("Por vendedor", "Dia a dia")
           for c_ in _tc22[t_n]["colunas"] if c_["nome"] == "CARGO")
       and all("CARGO" not in (_tc22[t_n].get("filtros") or ())
               for t_n in ("Por vendedor", "Dia a dia")),
       "Farol de Visita: sem a coluna CARGO e sem o filtro Cargo")

# ---- (27/10, Alexandre) ROTEIRIZACAO POR LUGAR (de NOV/26 em diante):
# cidade > bairro > rua > numero; 1 cidade por dia; outubro nao muda
import planner_nucleo as _pl27  # noqa: E402
_c27 = _pl27.carregar_config(AQUI / "planner_config.json")
_k27 = _pl27.ler_base_cliente(AQUI / "RELATORIOS" / "BASE_CLIENTE.xlsx")
_pl27.aplicar_parametros(_c27, _k27)
_pl27.sincronizar_areas(_c27, _k27)
_ant27 = (_pl27.por_lugar_ativo({"mes": "2026-10"}),
          _pl27.por_lugar_ativo({"mes": "2026-11"}))
_c27["mes"], _c27["feriados"] = "2026-11", ["2026-11-02", "2026-11-20"]
_c27["rota_fixa"], _c27["rota_cidade"] = {}, {}
_pl27.REESCREVER_PASSADO[0] = True
try:
    _r27 = _pl27.gerar_rota(_c27, _k27)
finally:
    _pl27.REESCREVER_PASSADO[0] = False
_dep27 = min(d[0] for d in _pl27.dias_do_mes("2026-11", [], True) if d[3])
_dia27 = defaultdict(list)
for r in _r27:
    if r["DATA"] != _dep27:
        _dia27[(r["COD_VENDEDOR"], r["DATA"])].append(r)
_mult27 = [k for k, ls in _dia27.items()
           if len({r["CIDADE"] for r in ls}) > 1]


def _bairro_em_bloco27(ls):
    """bairro em bloco seguido; o mesmo nome so volta no dia quando e outro
    lugar (27/10, dia compacto: mais de RAIO_DIA_KM de qualquer cliente do
    trecho anterior com esse nome - rota_lugar._partir_bairro)"""
    import rota_lugar as _rlb  # noqa: PLC0415
    import geografia as _gb  # noqa: PLC0415
    trechos, ant = defaultdict(list), None
    for r in sorted(ls, key=lambda r: r["ORDEM_DE_VISITA"]):
        if r["BAIRRO"] != ant:
            trechos[r["BAIRRO"]].append([])
        trechos[r["BAIRRO"]][-1].append(_rlb.ponto(r))
        ant = r["BAIRRO"]
    for ts in trechos.values():
        for i in range(1, len(ts)):
            for a in ts[i]:
                for t in ts[:i]:
                    for b in t:
                        if (a[0] is None or b[0] is None
                                or _gb.distancia_km(a, b)
                                <= _rlb.RAIO_DIA_KM):
                            return False
    return True


_bl27 = [k for k, ls in _dia27.items() if not _bairro_em_bloco27(ls)]
checar(_ant27 == (False, True) and _r27 and not _mult27 and not _bl27,
       f"Roteirização por lugar (NOV): 1 cidade por dia e bairro em bloco "
       f"seguido ({len(_dia27)} dias de vendedor; outubro não muda)")

# (27/10, Alexandre) DIA COMPACTO: na capital o dia nao pega o fim de uma
# regiao e o comeco de outra (Marco + Icoaraci); bairro de mesmo nome em dois
# lugares longe vira dois blocos
import rota_lugar as _rl27  # noqa: E402
import geografia as _geo27  # noqa: E402
_raio27 = []
for _ls27 in _dia27.values():
    _ps27 = [p_ for p_ in (_rl27.ponto(r) for r in _ls27) if p_[0] is not None]
    if len(_ps27) >= 2:
        _ce27 = _rl27.centro(_ps27)
        _raio27.append(max(_geo27.distancia_km(_ce27, p_) for p_ in _ps27))
_dup27 = _rl27.ordenar_cidade([
    {"BAIRRO": "COQUEIRO", "ENDERECO": "R A", "LATITUDE": -1.33,
     "LONGITUDE": -48.45, "CIDADE": "BELEM"},
    {"BAIRRO": "COQUEIRO", "ENDERECO": "R B", "LATITUDE": -1.40,
     "LONGITUDE": -48.39, "CIDADE": "BELEM"}])
checar(_rl27.RAIO_DIA_KM == 5.0 and _rl27.RAIO_VAGA_KM == 5.0 and _raio27
       and max(_raio27) <= 2 * _rl27.RAIO_DIA_KM and len(_dup27) == 2,
       f"Dia compacto (NOV): nenhum cliente a mais de "
       f"{2 * _rl27.RAIO_DIA_KM:.0f} km do centro do dia (maior "
       f"{max(_raio27) if _raio27 else 0:.1f} km); bairro de mesmo nome longe "
       f"= 2 blocos")

# (03/11, Alexandre) A ORDEM DO MES: S, A e com limite primeiro, depois B,
# C e o resto, cada grupo na ordem geografica; SEXTA 12 (dia normal)
_k28 = [dict(c) for c in _k27]
_g28 = [_pl27.grupo_do_mes(c) for c in _k28]
_o28 = _pl27.ordem_por_prioridade(_c27, _k28[:400])
_go28 = [_pl27.grupo_do_mes(c) for c in _o28]
_ci28 = _pl27.cidades_por_prioridade([
    {"UF": "MA", "CIDADE": "X", "CURVA_RECEITA": "Z", "LIMITE_APROVADO": 0,
     "LIMITE_DISPONIVEL": 0, "CHAVE_CLIENTE": "1"},
    {"UF": "MA", "CIDADE": "Y", "CURVA_RECEITA": "Z", "LIMITE_APROVADO": 5,
     "LIMITE_DISPONIVEL": 0, "CHAVE_CLIENTE": "2"},
    {"UF": "MA", "CIDADE": "X", "CURVA_RECEITA": "A", "LIMITE_APROVADO": 0,
     "LIMITE_DISPONIVEL": 0, "CHAVE_CLIENTE": "3"}])
_par28 = dict(_c27["parametros"], visitas_sexta=12)
import datetime as _dt28  # noqa: E402
checar(_go28 == sorted(_go28) and len(_o28) == min(400, len(_k28))
       and [c["CHAVE_CLIENTE"] for c in _ci28] == ["3", "1", "2"]
       and _pl27.grupo_do_mes({"CURVA_RECEITA": "Z", "LIMITE_APROVADO": 0,
                               "LIMITE_DISPONIVEL": 10}) == 0
       and _pl27.grupo_do_mes({"CURVA_RECEITA": "B", "LIMITE_APROVADO": 0,
                               "LIMITE_DISPONIVEL": 0}) == 1
       and _pl27.teto_do_dia(12, _dt28.date(2026, 11, 6), _par28) == 12
       and _pl27.PARAMETROS_PADRAO["visitas_sexta"] == 12,
       f"Ordem do mês (NOV): S, A e com limite primeiro ({_g28.count(0)} "
       f"clientes), depois B, C e o resto, cada grupo na ordem geográfica; "
       f"interior: cidade com S/A/limite antes; sexta 12")

# (03/11, Alexandre) DIA FOCO: segunda BATERIA, terca MOTO para quem tem a
# base numa capital, em Ananindeua ou em Castanhal; Fayga e Rodrigo na base
# segunda e terca e no interior de quarta em diante
_v29 = {p_["cod_protheus"]: p_ for p_ in _pl27.vendedores(_c27)}
_kc29 = {c["CHAVE_CLIENTE"]: c for c in _k27}
_fc29, _tot29, _bst29 = 0, 0, []
for (_cv29, _d29), _ls29 in _dia27.items():
    _f29 = _pl27.foco_do_dia(_c27, _v29.get(_cv29, {}), _d29)
    if _f29:
        _tot29 += len(_ls29)
        _fc29 += sum(1 for r in _ls29 if _pl27.nivel_do_foco(
            _kc29[r["CHAVE_CLIENTE"]], _f29) < 2)
    if _cv29 in _pl27.BASE_SEG_TER:
        _nb29 = all(_geo27.normalizar(r["CIDADE"]) == _geo27.normalizar(
            _v29[_cv29]["cidade_base"]) for r in _ls29)
        if (_d29.weekday() in (0, 1)) != _nb29:
            _bst29.append((_cv29, _d29))
_vm29 = {"cidade_base": "MANAUS"}
checar(_pl27.foco_do_dia(_c27, _vm29, _dt28.date(2026, 11, 9)) == "BATERIA"
       and _pl27.foco_do_dia(_c27, _vm29, _dt28.date(2026, 11, 10)) == "MOTO"
       and _pl27.foco_do_dia(_c27, _vm29, _dt28.date(2026, 11, 11)) == ""
       and _pl27.foco_do_dia(_c27, {"cidade_base": "IMPERATRIZ"},
                             _dt28.date(2026, 11, 9)) == ""
       and _pl27.foco_do_dia({"mes": "2026-10"}, _vm29,
                             _dt28.date(2026, 10, 26)) == ""
       and _pl27.nivel_do_foco({"SEGMENTO": "MOTOPEÇAS"}, "MOTO") == 0
       and _pl27.nivel_do_foco({"SEGMENTO": "AUTOPEÇAS",
                                "COMPRA_BATERIA": "SIM"}, "BATERIA") == 0
       and _pl27.nivel_do_foco({"SEGMENTO": "AUTOCENTER"}, "BATERIA") == 1
       and _tot29 and _fc29 >= 0.6 * _tot29 and not _bst29,
       f"Dia foco (NOV): segunda bateria e terça moto ({_fc29} de {_tot29} "
       f"visitas de segunda/terça com cliente do foco); Fayga e Rodrigo na "
       f"base seg/ter e no interior de quarta em diante")

# ---- (10/11, Alexandre) cliente INATIVO no Protheus (STATUS da
# dClientesBap / A1_MSBLQL 1): a BASE_CLIENTE traz STATUS_PROTHEUS, o
# Planner tira o cliente da rota e o .json da base vai INATIVO com o
# vendedor padrao
import base_cliente as _bc10  # noqa: E402
_cin10 = {"CHAVE_CLIENTE": "X|1", "STATUS_PROTHEUS": "INATIVO"}
_cat10 = {"CHAVE_CLIENTE": "X|2", "STATUS_PROTHEUS": "ATIVO"}
_bp10 = []
try:
    _cf10 = _pl27.carregar_config(AQUI / "planner_config.json")
    _cl10 = _pl27.ler_base_cliente(REL / "BASE_CLIENTE.xlsx")
    _in10 = [c_ for c_ in _cl10 if c_.get("STATUS_PROTHEUS") == "INATIVO"]
    if _in10:
        _ch10 = {c_["CHAVE_CLIENTE"] for c_ in _in10}
        _bp10 = [x_ for x_ in _pl27.base_protheus(_cf10, _in10)]
        _rt10 = [r_ for r_ in _pl27.gerar_rota(_cf10, _cl10)
                 if r_["CHAVE_CLIENTE"] in _ch10]
    else:
        _rt10 = []
except Exception as _e10:                               # noqa: BLE001
    _rt10 = [_e10]
checar(_bc10.status_protheus("INATIVO") == "INATIVO"
       and _bc10.status_protheus(None, "1") == "INATIVO"
       and _bc10.status_protheus("", "2") == "ATIVO"
       and "STATUS_PROTHEUS" in _bc10.CABECALHO
       and _pl27.cliente_inativo({}, _cin10)
       and not _pl27.cliente_inativo({}, _cat10)
       and not _rt10
       and all(x_["STATUS"] == "INATIVO" and x_["A1_VEND"] ==
               _pl27.vendedor_padrao(_cf10) for x_ in _bp10),
       f"Cliente INATIVO no Protheus fora da rota e INATIVO no .json da base "
       f"({len(_bp10)} na BASE_CLIENTE desta pasta)")

# ---- (27/10, Alexandre - recados do BAP Ajuda 20261027-0740/0820) as
# respostas do app BAP Ajuda: Prospeccao (junto com o Forms), Indicacao e
# Pesquisa de mercado; testes (000040) fora. Numa pasta temporaria: o
# RESPOSTAS_BAP_AJUDA.xlsx de verdade nao e tocado.
import tempfile as _tf27  # noqa: E402
import shutil as _sh27  # noqa: E402
import respostas_bap_ajuda as _rb27  # noqa: E402
import prospeccao_forms as _pf27  # noqa: E402
from openpyxl import Workbook as _Wb27  # noqa: E402
_t27 = Path(_tf27.mkdtemp(prefix="smoke_bapajuda_"))
try:
    (_t27 / "RELATORIOS" / "BAP_AJUDA_RESPOSTAS").mkdir(parents=True)
    _sh27.copy2(AQUI / "planner_config.json", _t27 / "planner_config.json")
    _wb27 = _Wb27()
    _wb27.remove(_wb27.active)
    _ws = _wb27.create_sheet("PROSPECCAO")
    _ws.append(["enviado_em", "data", "vendedor", "estabelecimento", "cnpj",
                "segmento", "uf", "cidade", "resultado", "foto",
                "observacao"])
    _ws.append(["2026-10-27T08:00:00-03:00", "2026-10-27",
                "EDSON NEVES DO NASCIMENTO", "LOJA A", "11222333000181",
                "Autopeças", "PA", "BELEM", "Pediu orçamento", "f.png", ""])
    _ws.append(["2026-10-27T09:00:00-03:00", "2026-10-27",
                "EDSON NEVES DO NASCIMENTO", "LOJA A", "11222333000181",
                "Autopeças", "PA", "BELEM", "Pediu orçamento", "", ""])
    _ws.append(["2026-10-27T07:30:00-04:00", "2026-10-27",
                "ALEXNADRE LOHAN CEZAR GUERREIRO", "TESTE", "11444777000161",
                "Motopeças", "AM", "MANAUS", "", "", "TESTE"])
    _ws = _wb27.create_sheet("INDICACOES")
    _ws.append(["enviado_em", "data", "vendedor", "indicado_por_cod",
                "indicado_por", "estabelecimento", "cidade", "cnpj"])
    _ws.append(["2026-10-26T10:00:00-03:00", "2026-10-26",
                "EDSON NEVES DO NASCIMENTO", "000917",
                "000917 · CLIENTE X · Belem", "LOJA A", "BELEM",
                "11222333000181"])
    _ws.append(["2026-10-26T10:00:00-04:00", "2026-10-26",
                "ALEXNADRE LOHAN CEZAR GUERREIRO", "000917", "x", "T", "M",
                ""])
    _ws = _wb27.create_sheet("PESQUISA")
    _ws.append(["enviado_em", "data", "vendedor", "cod_cliente", "linha",
                "papel", "codigo_bap", "preco_compra_bap", "preco_venda_bap",
                "preco_compra_concorrencia", "preco_venda_concorrencia",
                "estoque_bap", "estoque_concorrencia"])
    _ws.append(["2026-10-27T08:00:00-03:00", "2026-10-27",
                "EDSON NEVES DO NASCIMENTO", "011095", "LINHA MOTO",
                "PRINCIPAL", "FAR6365", 110, 160, 100, 150, 2, 6])
    _ws.append(["2026-10-27T08:00:00-03:00", "2026-10-27",
                "EDSON NEVES DO NASCIMENTO", "011095", "LINHA MOTO",
                "PESQUISA", "SEM CÓDIGO BAP", None, None, "20,50", "35", 0,
                3])
    _ws.append(["2026-10-27T07:57:00-04:00", "2026-10-27",
                "ALEXNADRE LOHAN CEZAR GUERREIRO", "000920", "LINHA MOTO",
                "PRINCIPAL", "CAR18", 1, 2, 3, 4, 1, 1])
    _wb27.save(_t27 / "RELATORIOS" / "BAP_AJUDA_RESPOSTAS"
               / "RESPOSTAS_BAP_AJUDA.xlsx")
    _pr27 = [x for x in _pf27.linhas(_t27) if x.get("fonte") == "APP"]
    _st27 = [x["status"] for x in _pr27]
    _cn27 = _pf27.contagem(_t27)
    _in27 = _rb27.indicacoes(_t27)
    _pe27 = _rb27.pesquisas(_t27)
    checar(_st27 == [_pf27.ST_CONTA, _pf27.ST_TESTE, _pf27.ST_DUPLICADO]
           and sum(_cn27.values()) == 1
           and len(_in27) == 1 and _in27[0]["cod_indicou"] == "000917"
           and _in27[0]["quem_indicou"] == "CLIENTE X"
           and len(_pe27) == 2 and _pe27[0]["compra_bap"] == 110.0
           and _pe27[1]["sem_codigo"] and _pe27[1]["compra_conc"] == 20.5,
           "BAP Ajuda (app): prospecção valida como o Forms (duplicado no "
           "dia conta 1; teste 000040 fora), indicação e pesquisa lidas "
           "(preço com vírgula; SEM CÓDIGO BAP)")
finally:
    _sh27.rmtree(_t27, ignore_errors=True)
_fv27 = rn.montar("vc_visitas", AQUI)
_fp27 = rn.montar("vc_preco", AQUI)
_tv27 = {t_["titulo"]: t_ for t_ in _fv27["tabelas"]}
_tp27 = {t_["titulo"]: t_ for t_ in _fp27["tabelas"]}
checar("Indicação" in _tv27 and "Prospecção" in _tv27
       and "FONTE" in [c_["nome"] for c_ in _tv27["Prospecção"]["colunas"]]
       and "Pesquisa de mercado" in _tp27
       and "DIF. COMPRA %" in [c_["nome"] for c_ in
                               _tp27["Pesquisa de mercado"]["colunas"]],
       "Farol de Visita com as abas Prospecção (app + Forms) e Indicação; "
       "Farol de Preço com a aba Pesquisa de mercado")

# ---- (21/10, Alexandre) recalcular NAO reescreve o passado; o interior 6 /
# base 12; a meta de visita 12 por dia util desde a admissao; o lote de
# 16/10 fora da visita
import planner_nucleo as _pn21  # noqa: E402
_pn21.REESCREVER_PASSADO[0] = False
_c21 = _pn21.carregar_config(AQUI / "planner_config.json")
_k21 = _pn21.ler_base_cliente(AQUI / "RELATORIOS" / "BASE_CLIENTE.xlsx")
_pn21.aplicar_parametros(_c21, _k21)
_pn21.sincronizar_areas(_c21, _k21)
_fx21 = _pn21.rota_fixa_valida(_c21).get("vendedores") or {}
if _fx21 and _c21.get("mes") == f"{date.today():%Y-%m}":
    _v21 = sorted(_fx21)[0]
    _pn21.HOJE_DA_ROTA[0] = date.today()
    _fx21[_v21]["assin"] = "mudou"          # o vendedor e refeito
    _pn21.esquecer_rota()
    _r21 = _pn21.gerar_rota(_c21, _k21)
    _pas = sorted((x[0], x[1]) for x in _fx21[_v21]["visitas"]
                  if x[1] < date.today().isoformat())
    _gua = sorted((r["CHAVE_CLIENTE"], r["DATA"].isoformat()) for r in _r21
                  if r["COD_VENDEDOR"] == _v21
                  and r["DATA"] < date.today())
    _pn21.HOJE_DA_ROTA[0] = None
    checar(_v21 not in _pn21.gerar_rota.congelados and _gua
           and set(_gua) <= set(_pas),
           f"Recalcular não reescreve o passado: {_v21} refeito, "
           f"{len(_gua)} visita(s) de antes de hoje como estavam")
_cal21 = {"mes": "2026-10", "feriados": ["2026-10-12"], "parametros": {
    "teto_interior": 6, "visitas_sexta": 6},
    "pessoas": [{"cod_protheus": "000034", "nome": "A", "cargo": "VENDEDOR",
                 "interior": True, "cidade_base": "IMPERATRIZ",
                 "uf_base": "MA", "data_admissao": "2026-04-01"},
                {"cod_protheus": "000049", "nome": "V", "cargo": "VENDEDOR",
                 "cidade_base": "MANAUS", "uf_base": "AM",
                 "data_admissao": "2026-10-14"}],
    "rota_cidade": {"000034": {"2026-10-20": ["MA|PORTO FRANCO"],
                               "2026-10-21": ["MA|IMPERATRIZ"]}}}
_pn21._DIAS_NO_INTERIOR[0] = frozenset(_pn21.dias_no_interior(_cal21,
                                                              "000034"))
_t20 = _pn21.teto_do_dia(12, date(2026, 10, 20), _cal21["parametros"])
_t21 = _pn21.teto_do_dia(12, date(2026, 10, 21), _cal21["parametros"])
_pn21._DIAS_NO_INTERIOR[0] = frozenset()
_m21 = _pn21.metas_de_visita_do_mes(_cal21, {})
checar(_t20 == 6 and _t21 == 12
       and _pn21.teto_do_dia(12, date(2026, 10, 20), {}) == 12
       and _m21["000034"][date(2026, 10, 20)] == 6
       and _m21["000034"][date(2026, 10, 21)] == 12
       and _m21["000034"].get(date(2026, 10, 24), 0) == 0
       and sum(_m21["000049"].values()) == 12 * 13
       and _m21["000049"].get(date(2026, 10, 13)) == 0
       and _pn21.datas_cadastro_lote_fora({"parametros": {
           "datas_cadastro_lote_fora": ["2026-10-16"]}})
       == {date(2026, 10, 16)},
       "Interior: 6 fora da cidade base e 12 nela; meta de visita 12 por "
       "dia útil desde a admissão (sábado sem meta); lote de 16/10 fora")
_ct21 = rn.Contexto(AQUI)
checar(all(d not in rn.lote_fora(_ct21) for (_v, d) in
           rn.cadastros_do_dia(_ct21)),
       "Cadastro em lote (16/10) não conta como visita")


# (22/10) SLA de entrega em dias CORRIDOS (o sabado da entrega conta); dia
# util so na DT. PREVISTA
_c22 = rn.Contexto.corridos
checar(_c22(None, date(2026, 10, 20), date(2026, 10, 24)) == 4
       and _c22(None, date(2026, 10, 23), date(2026, 10, 26)) == 3
       and _c22(None, None, date(2026, 10, 24)) is None
       and bd.somar_uteis(date(2026, 10, 22), 3) == date(2026, 10, 27)
       and bd.somar_uteis(date(2026, 10, 22), 5) == date(2026, 10, 29),
       "SLA de entrega em dias corridos (pedido 20/10, entrega sáb 24/10 = 4)"
       "; previsão em dias úteis")

# (28/10, Alexandre - recado do BAP Ajuda 20261028-0833) Divergencias:
# aba "Sem coordenada / endereco", o Excel para a analista preencher e o
# "Importar preenchidos" (ponto MANUAL no COORDENADAS_CLIENTES.json, que
# o geocodificar nao apaga). Numa pasta temporaria.
import tempfile as _tf28  # noqa: E402
import types as _ty28  # noqa: E402
import geocodificar as _gc28  # noqa: E402
from openpyxl import load_workbook as _lw28  # noqa: E402
_dvr28 = rn.montar("an_divergencias", AQUI)
_dv28 = next((t_ for t_ in _dvr28["tabelas"]
              if t_["titulo"] == rn.ABA_SEM_COORD), None)
_t28 = Path(_tf28.mkdtemp(prefix="smoke_semcoord_"))
try:
    (_t28 / "RELATORIOS").mkdir()
    _cl28 = [
        {"cod": "000001", "loja": "01", "chave": "000001-01", "nome": "A",
         "fantasia": "LOJA A", "uf": "AM", "cidade": "MANAUS",
         "bairro": "CENTRO", "endereco": "RUA X, S/N", "numero": "",
         "lat": None, "lon": None, "na_rota": True, "curva": "B"},
        {"cod": "000002", "loja": "01", "chave": "000002-01", "nome": "B",
         "fantasia": "LOJA B", "uf": "AM", "cidade": "MANAUS",
         "bairro": "CENTRO", "endereco": "RUA Y, 39A", "numero": "",
         "lat": -3.13, "lon": -60.02, "na_rota": False, "curva": "S"},
        {"cod": "000003", "loja": "01", "chave": "000003-01", "nome": "C",
         "fantasia": "LOJA C", "uf": "AM", "cidade": "MANAUS",
         "bairro": "", "endereco": "AV Z", "numero": "0",
         "lat": -3.10, "lon": -60.00, "na_rota": False, "curva": "A"},
        {"cod": "000004", "loja": "01", "chave": "000004-01", "nome": "D",
         "fantasia": "LOJA D", "uf": "AM", "cidade": "MANAUS",
         "bairro": "CENTRO", "endereco": "", "numero": "",
         "lat": None, "lon": None, "na_rota": False, "curva": "S"},
        {"cod": "000005", "loja": "01", "chave": "000005-01",
         "nome": "BAP AUTOPARTS", "interno": True, "uf": "AM",
         "cidade": "MANAUS", "bairro": "", "endereco": "", "numero": "",
         "lat": None, "lon": None}]
    _cx28 = _ty28.SimpleNamespace(raiz=_t28, base={"clientes": _cl28},
                                  hoje=date(2026, 10, 28))
    _ls28 = rn.clientes_sem_coordenada(_cx28)
    _xl28, _n28 = rn.gravar_sem_coordenada(_cx28, _t28 / "P.xlsx")
    _wb28 = _lw28(_xl28)
    _ws28 = _wb28["PREENCHER"]
    _cab28 = [c_.value for c_ in _ws28[1]]
    _ok_prot28 = (_ws28.protection.sheet
                  and _ws28.cell(2, 1).protection.locked
                  and not _ws28.cell(
                      2, _cab28.index("LATITUDE") + 1).protection.locked
                  and "COMO PREENCHER" in _wb28.sheetnames)
    # a 1a linha (na rota) com os dois numeros juntos; a 2a trocada
    _ws28.cell(2, _cab28.index("LATITUDE") + 1).value = "-3.1190, -60.0217"
    _ws28.cell(3, _cab28.index("LATITUDE") + 1).value = "-60.02"
    _ws28.cell(3, _cab28.index("LONGITUDE") + 1).value = "-3.11"
    _wb28.save(_t28 / "P.xlsx")
    _res28 = rn.importar_preenchidos(_cx28, _t28 / "P.xlsx")
    _arq28 = _gc28.ler(_gc28.caminho(_t28))
    # o robo: endereco mudou e o OpenStreetMap nao achou -> o manual fica
    _gc28.atualizar(_t28 / "RELATORIOS" / "BASE_CLIENTE.xlsx", clientes=[
        {"CHAVE_CLIENTE": "000001-01", "ENDERECO": "RUA NOVA 5",
         "NUMERO": "", "CIDADE": "MANAUS", "UF": "AM", "BAIRRO": "CENTRO"}],
        consultar=lambda p_: None, esperar=lambda s_: None)
    _fica28 = _gc28.ler(_gc28.caminho(_t28)).get("000001-01") or {}
    checar(_dv28 is not None and any(
               k_["rotulo"] == "Sem coordenada / endereço"
               for k_ in _dvr28["kpis"])
           and [d_["cod"] for d_ in _ls28] == ["000001", "000004", "000003"]
           and _ls28[0]["falta"] == [rn.F_SEM_COORD, rn.F_SEM_NUM]
           and _ls28[1]["falta"] == [rn.F_SEM_COORD, rn.F_SEM_END]
           and _ls28[2]["falta"] == [rn.F_SEM_NUM, rn.F_SEM_BAIRRO]
           and _n28 == 3 and _ok_prot28
           and _res28["gravados"] == ["000001-01 LOJA A"]
           and len(_res28["recusados"]) == 1
           and "trocadas" in _res28["recusados"][0][1]
           and _arq28["000001-01"]["origem"] == "MANUAL"
           and _arq28["000001-01"]["LATITUDE"] == "-3.119"
           and _fica28.get("LATITUDE") == "-3.119"
           and _fica28.get("end", "").startswith("RUA NOVA"),
           "Divergências: aba Sem coordenada / endereço (na rota primeiro, "
           "curva; internos fora), Excel para preencher (protegido, "
           "amarelas livres) e Importar preenchidos (MANUAL; trocada "
           "recusada; o robô não apaga o ponto manual)")
finally:
    import shutil as _sh28  # noqa: E402
    _sh28.rmtree(_t28, ignore_errors=True)

# (28/10, Alexandre) BAP CHAMPIONS: pontos por faturamento (30/15/10 a
# cada R$ 1.000), aceleradores, confronto da semana (+200) e a trava de 80%
# da meta RH; o cadastro (champions_config.json) gravado numa pasta
# temporaria (o de verdade nao e tocado).
import bap_champions as _bc28  # noqa: E402
_pd28 = _bc28.PADRAO
_rc28 = rn.montar("vc_champions", AQUI)
_tc28 = {t_["titulo"]: t_ for t_ in _rc28.get("tabelas") or []}
_okv28 = True
if "Vendedores" in _tc28:
    _nv28 = [c_["nome"] for c_ in _tc28["Vendedores"]["colunas"]]
    _iv28 = {n_: i_ for i_, n_ in enumerate(_nv28)}
    for l_ in _tc28["Vendedores"]["linhas"]:
        _soma = (l_[_iv28["PTS FATUR."]] + l_[_iv28["PTS PEÇAS"]]
                 + l_[_iv28["PTS CLI. NOVO"]] + l_[_iv28["PTS BÔNUS"]])
        _lib = (l_[_iv28["% DESAFIO"]] or 0) >= _pd28["trava_pct"]
        _okv28 &= (abs(_soma - l_[_iv28["PTS"]]) <= 2
                   and (l_[_iv28["SITUAÇÃO"]] == "LIBERADO") == _lib
                   and l_[_iv28["PTS VÁLIDOS"]] == (
                       l_[_iv28["PTS"]] if _lib else 0)
                   and l_[_iv28["PTS PEÇAS"]] == l_[_iv28["PEÇAS (UN.)"]] * 5
                   and abs(l_[_iv28["FAT. BRUTO"]] + l_[_iv28["DEVOLUÇÕES"]]
                           - l_[_iv28["FAT. LÍQUIDO"]]) < 0.01)
_t28c = Path(_tf28.mkdtemp(prefix="smoke_champions_"))
try:
    _cfg28 = _bc28.ler(_t28c)
    _cfg28["jogos"] = [{"semana": "2026-11-02", "tipo": "VENDEDOR",
                        "a": "000034", "b": "000034"}]
    try:
        _bc28.gravar(_t28c, _cfg28)
        _rec28 = False
    except ValueError:
        _rec28 = True
    _cfg28["jogos"] = [{"semana": "2026-11-02", "tipo": "VENDEDOR",
                        "a": "000034", "b": "000031"}]
    _cfg28["aux"] = [{"nome": "Juliana Almeida", "supervisor": "000013"}]
    _bc28.gravar(_t28c, _cfg28, "smoke")
    _vol28 = _bc28.ler(_t28c)
finally:
    _sh28.rmtree(_t28c, ignore_errors=True)
checar(_pd28["pontos_por_mil"] == {"VENDEDOR": 30.0, "SUPERVISOR": 15.0,
                                   "AUX. TÉCNICO": 10.0}
       and _pd28["bonus_confronto"] == 200.0 and _pd28["trava_pct"] == 80.0
       and _pd28["acel_vendedor"] == {"sku_pecas": 5.0, "cliente_novo": 20.0}
       and _pd28["acel_supervisor"] == {"sku_novo": 2.0, "positivado": 5.0}
       and _pd28["acel_aux"] == {"sla_entrega": 200.0,
                                 "sla_faturamento": 200.0}
       and "vc_champions" in rn.POR_ID and not _rc28.get("_erro")
       and {"Vendedores", "Supervisores", "Aux. Técnico", "Confrontos",
            "Pts por semana", "Regras"} <= set(_tc28) and _okv28
       and _rec28 and _vol28["jogos"][0]["b"] == "000031"
       and _vol28["aux"][0]["supervisor"] == "000013"
       and _vol28["alterado_por"] == "smoke",
       "BAP CHAMPIONS: bruto + devoluções = líquido; pontos 30/15/10 por "
       "R$ 1.000, aceleradores, +200 "
       "no confronto, trava 80% da meta RH (pontos válidos só LIBERADO); "
       "cadastro grava e recusa jogo com o mesmo jogador")

# (28/10, Alexandre) CAMPANHA RELAMPAGO (aba das Campanhas BAP): a cada
# R$ 4.000 em pedidos do dia, vendedor 250 e supervisor 150 (equipe + o
# codigo dele); desafio do dia (BAP inteira >= meta) 400/300 so para quem
# vendeu no dia; quem vendeu fora do Planner tambem aparece.
import types as _ty28r  # noqa: E402
_it28r = [{"tipo": t_, "dt_pedido": date(2026, 7, 31), "vend": v_,
           "valor": x_} for t_, v_, x_ in (
    ("VND", "000034", 5000.0), ("VEA", "000034", 3100.0),
    ("EXC", "000031", 9000.0), ("VND", "000099", 4000.0),
    ("VND", "000013", 1000.0))]
_cx28r = _ty28r.SimpleNamespace(tabela={"itens": _it28r},
                                hoje=date(2026, 10, 28),
                                vendedor=lambda c_: c_)
_cf28r = {"fora_do_jogo": [], "relampago": [dict(
    _bc28.PADRAO["relampago"][0], meta_bap_dia=10000.0)]}
_tr28 = rn._tabela_relampago(
    _cx28r, _cf28r, 2026, 7,
    {"000034": {"supervisor": "DENYLSON"}, "000031": {"supervisor":
                                                      "DENYLSON"}},
    {"000013": {}}, {"000013": {"000034", "000031"}},
    {"000034": "ANDERSON", "000031": "JOCIMAR", "000013": "DENYLSON"})
_pr28 = {l_[3].split(" - ")[0]: l_ for l_ in _tr28["linhas"]}
checar(_tr28["titulo"] == "Campanha relâmpago"
       and _pr28["000034"][6] == 2 and _pr28["000034"][13] == 900
       and _pr28["000031"][8] == "NÃO" and _pr28["000031"][13] == 0
       and _pr28["000099"][13] == 650
       and _pr28["000013"][6] == 2 and _pr28["000013"][13] == 600
       and _pr28["000034"][11] == "BATEU",
       "Campanha relâmpago: R$ 4.000 em pedidos = 250/150, desafio do dia "
       "400/300 só para quem vendeu, excluído fora, fora do Planner entra")

# (28/10, Alexandre) equipe e metas do mes cadastradas a mao (julho):
# substituem o Planner; supervisor = soma das metas; sem codigo nao vende
_ls28m, _lv28m = rn._ch_equipe_manual(_bc28.PADRAO["equipes_mes"]["2026-07"])
_sl28m = next(x_ for x_ in _ls28m.values() if x_["nome"].startswith("LAIS"))
checar(len(_lv28m) == 11 and len(_ls28m) == 4
       and _lv28m["000035"]["meta"] == 120000.0
       and _sl28m["meta"] == 180000.0
       and any(k_.startswith("?LUA") for k_ in _lv28m)
       and rn._ch_rot("SUP-LAIS", "LAIS") == "LAIS"
       and _bc28.moeda("R$ 120.000,00") == 120000.0,
       "Campanhas BAP: equipe e metas de JUL/26 do cadastro (11 vendedores, "
       "4 supervisores; supervisor = soma das metas)")

# (06/11, Alexandre) COBRAR NO WHATSAPP: a fila dos inadimplentes, o
# celular do cadastro no formato do WhatsApp e a mensagem com os titulos
import cobranca_whatsapp as _cw06  # noqa: E402
_far06 = {"tabelas": [
    {"titulo": "Por cliente", "colunas": [{"nome": n_} for n_ in (
        "SITUAÇÃO", "CLIENTE", "NOME", "CIDADE", "UF", "VENDEDOR",
        "SUPERVISOR", "EM ATRASO", "MAIOR ATRASO", "TELEFONE")],
     "linhas": [["INADIMPLENTE", "010937-01", "PLANTAO DAS BATERIAS",
                 "SAO LUIS", "MA", "ANDERSON", "LAIS", 300.0, 40,
                 "098 91181527"],
                ["INADIMPLENTE", "010931-01", "CASTANHAL BATERIAS",
                 "CASTANHAL", "PA", "RODRIGO", "LAIS", 900.0, 90,
                 "99 99999999"],
                ["EM DIA", "010000-01", "OUTRO", "", "", "", "", 0, 0, ""]]},
    {"titulo": "Títulos", "colunas": [{"nome": n_} for n_ in (
        "SITUAÇÃO", "CLIENTE", "NF", "PARC.", "VENCIMENTO", "DIAS ATRASO",
        "SALDO")],
     "linhas": [["VENCIDO", "010937-01", "123", "2", date(2026, 9, 27), 40,
                 300.0]]}]}
_fl06 = _cw06.fila(_far06, {"010937": "PLANTAO DAS BATERIAS"})
_ms06 = _cw06.mensagem(_fl06[1])
with _tfv.TemporaryDirectory() as _dcw:
    _cw06.registrar(_dcw, _fl06[1], "ENVIADO")
    _hc06 = _cw06.historico(_dcw)
checar([c_["cod"] for c_ in _fl06] == ["010931-01", "010937-01"]
       and _fl06[0]["whatsapp"] == "" and _fl06[1]["whatsapp"] ==
       "5598991181527" and "NF 123/2 · venc. 27/09/2026 · R$ 300,00" in _ms06
       and "Plantao das Baterias" in _ms06
       and _cw06.link("5598991181527", "Olá").startswith(
           "whatsapp://send?phone=5598991181527&text=Ol%C3%A1")
       and _cw06.situacao(_hc06, "010937-01") == "ENVIADO HOJE"
       and hasattr(_br14.Relatorio, "cobrar_whatsapp"),
       "Cobrar no WhatsApp: fila dos inadimplentes, celular do cadastro "
       "(0 do DDD fora, 9 na frente), mensagem com os títulos e o diário")
# (06/11, Alexandre) "porque amapa esta aparecendo se nao tem meta nem
# real" / "se nao tenho vendedor na area, nao pode contar para a meta": o
# cliente do vendedor INATIVO no Planner nao leva meta de visita nem de
# positivacao; a carteira dele (sem movimento) sai dos territorios
import meta_nucleo as _mn06  # noqa: E402
_ac06 = {"recortes": {"vendedor": [
    {"chave": "000099", "vendedor_ativo": False, "meta": 0},
    {"chave": "000098", "vendedor_ativo": True, "meta": 10}]}}


class _Cx06b:
    hoje = date(2026, 11, 6)
    tabela = {"itens": []}


_oc06 = rn._cods_ocultos(_Cx06b(), _ac06, "2026-11")
_src06 = Path(_mn06.__file__).read_text(encoding="utf-8")
checar(_oc06 == {"000099"} and not rn._tem_meta_ou_mov(
           {"meta": 0, "meta_positivacao": 0, "clientes": 414})
       and rn._tem_meta_ou_mov({"meta_positivacao": 30})
       and 'if c.get("vendedor_ativo") is False:' in _src06
       and "|in2" in Path(bd.__file__).read_text(encoding="utf-8"),
       "Vendedor inativo: a carteira sem movimento sai dos territórios e "
       "não leva meta de visita nem de positivação (o Amapá do 000040)")
if TEM_DADOS:
    _pp06 = _pf26           # o Painel Executivo ja montado (o mes de hoje)
    # (10/11, recado 20261109-1345) as abas no modelo da RRM
    _rr10 = {v_: (_pp06.get(t_) or {}) for v_, t_ in (
        ("res", "Painel · resultado"), ("prod", "Painel · produtividade"),
        ("du", "Painel · por dia útil"))}
    _dr10 = ((_rr10["res"].get("painel") or {}).get("blocos") or [{}])[0] \
        .get("dados") or {}
    _c10 = {c_["chave"]: c_ for c_ in _dr10.get("res") or []}
    _p10 = {c_["chave"]: c_ for c_ in _dr10.get("prod") or []}
    _ok10r = (len(_dr10.get("res") or []) == 10
              and len(_dr10.get("prod") or []) == 10
              and len(_dr10.get("du") or []) == 6
              and all(len(_rr10[v_].get("kpis_export") or []) ==
                      len(_dr10[v_]) for v_ in _rr10)
              and all(len(c_["faixa"]) == 3 for v_ in ("res", "prod", "du")
                      for c_ in _dr10[v_])
              and [a_[0] for a_ in _c10["fat"]["aneis"]] in (
                  ["MTD", "MÊS"], [])
              and [a_[0] for a_ in _c10["markup"]["aneis"]] in (["MÊS"], [])
              and set(_p10) == {"vis", "convv", "prim", "fora", "jorn",
                                "ini", "ult", "alm", "tma", "tmd"})
    _ef10 = (_c10.get("fat") or {}).get("estados") or {}
    if _ef10:
        _rot10 = [b_[0] for b_ in _ef10["barras"]][:4]
        _ok10r = _ok10r and _rot10 == ["PA", "MA", "AM", "RR"]
    if _dr10.get("mes") == 11:
        _ok10r = _ok10r and _c10["fat"]["faixa"][2][0] == "jul (bench.)" \
            and _c10["fat"]["faixa"][0][0] == "out"
    checar(_ok10r, "Painel Executivo no modelo da RRM: resultado (10), "
           "produtividade (10) e por dia útil (6); círculos MTD/MÊS, faixa "
           "mês anterior/anterior/julho e barras PA, MA, AM, RR (10/11)")
# (09/11, Alexandre, recados 20261109-1200 e -1215) Farol de Visita:
# VISITAS POR DIA = visitas dos vendedores / dias uteis de vendedor (com ou
# sem visita, desde a 1a visita; sabado, domingo, feriado e hoje fora);
# Cliente a cliente com NOME FANTASIA e filtro por DATA
if TEM_DADOS:
    _rv09 = rn.montar("vc_visitas", AQUI)
    _k09 = next((k_ for k_ in _rv09["kpis"]
                 if k_["rotulo"] == "Visitas por dia"), {})
    _tc09 = next((t_ for t_ in _rv09["tabelas"]
                  if t_["titulo"] == "Cliente a cliente"), None)
    _nc09 = [c_["nome"] for c_ in (_tc09 or {}).get("colunas", [])]
    checar("por dia útil" in str(_k09.get("detalhe"))
           and (_tc09 is None or (
               _nc09.index("NOME FANTASIA") == _nc09.index("CLIENTE") + 1
               and "DATA" in (_tc09.get("filtros") or ())
               and all(len(l_) == len(_nc09) for l_ in _tc09["linhas"]))),
           "Farol de Visita: visitas por dia útil de vendedor; Cliente a "
           "cliente com NOME FANTASIA e filtro DATA")
    _rd09 = rn.montar("vc_visitas", AQUI, hoje=date(2026, 11, 9), params={
        "MÊS": 11, "ANO": 2026, "SUPERVISOR": "DENYLSON DA SILVA COSTA"})
    _kd09 = next((k_ for k_ in _rd09["kpis"]
                  if k_["rotulo"] == "Visitas por dia"), {})
    if "103 ÷" in str(_kd09.get("detalhe")):    # os dados de 06/11
        checar(_kd09["valor"] == "6,4" and "÷ 16" in _kd09["detalhe"],
               "Farol de Visita: Maranhão 03–06/11 = 103 ÷ 16 dias úteis "
               "de vendedor = 6,4 (o Jocimar sem visita conta)")
# (09/11, Alexandre, recado 20261109-1300) a HORA da prospeccao: aba
# Prospeccao com DATA e HORA; a prospeccao entra no INICIO e na ULT. ATIV.
class _Ctx13:
    pass


_x13 = _Ctx13()
_x13._prosp_dia = {("000099", date(2026, 11, 5)): 2}
_x13._prosp_hora = {("000099", date(2026, 11, 5)): (7 * 3600, 16 * 3600)}
_x13._cad_dia = {}
_r13 = rn.com_cadastro_como_visita(_x13, [
    {"cod_protheus": "000099", "data": date(2026, 11, 5), "visitas": 3,
     "vis_fora": 0, "primeiro": 8 * 3600, "ultimo": 11 * 3600}])
_jt13 = {"inicio": 27000, "fim": 64800, "fim_sexta": 61200}
checar(len(_r13) == 1 and _r13[0]["primeiro"] == 7 * 3600
       and _r13[0]["ultimo"] == 16 * 3600 and _r13[0]["visitas"] == 5
       and rn.jornada_liquida(_r13[0], _jt13) == 16 * 3600 - 27000
       and rn.hora_da_prospeccao({"conclusao": "05/11/2026 10:20",
                                  "fonte": "APP"}) == 37200,
       "Prospecção na jornada: INÍCIO = 1ª prospecção antes do 1º cliente; "
       "ÚLT. ATIV. = a maior entre último cliente e última prospecção; o "
       "expediente (07:30) segue cortando a jornada líquida")
import contatos_vcf as _cv15  # noqa: E402
_c15 = {"COD_CLIENTE": "010650", "LOJA": "01", "CIDADE": "Castanhal",
        "NOME_CLIENTE": "SALVADOR COMERCIAL LTDA",
        "CONTATO": "Salvador (91) 98888-7777", "TELEFONE": "91988887777"}
checar(_cv15.nome_contato(_c15, "TOP30") ==
       "TOP30 - 010650 - CASTANHAL - SALVADOR COMERCIAL LTDA - SALVADOR"
       and _cv15.nome_contato(dict(_c15, CONTATO="9985298010", LOJA="02"),
                              "AUTOPEÇAS") ==
       "AUTOPEÇAS - 010650/02 - CASTANHAL - SALVADOR COMERCIAL LTDA"
       and "FN:TOP30 - 010650" in _cv15.arquivo_vcf([_c15], "", "TOP30"),
       "Contatos do celular: TOP30/SEGMENTO - CÓD - CIDADE - RAZÃO - CONTATO")

# (16/10) FRETE REAL no Farol de Entregas e SALDO DO FRETE no Farol de Saldo:
# 5% da nota - frete real (sobra vira saldo; acima de 5% desconta)
import pos_venda as _pv16  # noqa: E402
_re16 = rn.montar("pl_entregas", AQUI)
_ne16 = [c_["nome"] for c_ in _re16["tabelas"][0]["colunas"]]
_ed16 = [c_["campo"] for c_ in _re16["tabelas"][0]["edicao"]["campos"]]
_rs16 = rn.montar("vc_saldo", AQUI)
_ns16 = {t_["titulo"]: [c_["nome"] for c_ in t_["colunas"]]
         for t_ in _rs16["tabelas"]}
checar(abs(rn.saldo_do_frete(5568.0, 200.0, 5.0)[1] - 78.4) < 0.001
       and rn.saldo_do_frete(6000.0, 400.0, 5.0)[1] == -100.0
       and rn.saldo_do_frete(1000.0, None, 5.0)[1] is None
       and rn.saldo_do_frete(1000.0, 10.0, 5.0, False) == (None, None)
       and _pv16.valor_digitado("R$ 1.234,56") == 1234.56
       and _pv16.valor_digitado("278.40") == 278.4
       and "frete_real" in [c_[1] for c_ in _pv16.COLUNAS_ENTREGA]
       and {"TBL FRETE", "VLR REAL FRETE"} <= set(_ne16)
       and "SALDO FRETE" not in _ne16
       and "frete_real" in _ed16
       and all("SALDO FRETE" in _ns16[t_] for t_ in (
           "Pedido a pedido", "Por vendedor", "Por supervisor", "Por UF"))
       and any(k_["rotulo"] == "Saldo do frete" for k_ in _rs16["kpis"]),
       "Frete: VLR FRETE editável (frete real); saldo do frete = 5% da nota"
       " − frete real, no Farol de Saldo (sobra soma, acima de 5% desconta)")
# (23/10, Alexandre) FRETE MINIMO da transportadora: nota ate o valor que
# aciona paga o minimo; acima, o %
import transportadoras as _tr23  # noqa: E402
_d23 = {"pct_padrao": 5.0, "transportadoras": [
    _tr23.novo("X", pct=5, frete_minimo=120, minimo_ate=2400)]}
checar(_tr23.frete_estimado(_d23, "X", 1000) == 120
       and _tr23.frete_estimado(_d23, "X", 2400) == 120
       and abs(_tr23.frete_estimado(_d23, "X", 6000) - 300) < 0.01
       and _tr23.frete_estimado(_d23, "SEM CADASTRO", 1000) == 50
       and rn._frete("X", 1000, True, _d23) == 120
       and rn._frete("X", 1000, False, _d23) is None,
       "Transportadoras: frete mínimo em R$ até o valor da NF que aciona")
# (23/10, Alexandre) Farol de Garantias: aba HISTORICO DE COMPRA (item a
# item, busca por codigo/razao/fantasia)
_rg23 = rn.montar("pl_garantias", AQUI)
_th23 = next((t_ for t_ in _rg23["tabelas"]
              if t_["titulo"] == "Histórico de compra"), None)
_nh23 = [c_["nome"] for c_ in _th23["colunas"]] if _th23 else []
checar(_th23 is not None and {"CÓD. CLIENTE", "RAZÃO SOCIAL", "FANTASIA",
                              "PEDIDO", "PED. MÁXIMA", "NF", "PRAZO",
                              "DT. PEDIDO", "DT. NF", "DT. ENTREGA",
                              "TRANSPORTADORA", "RESPONSÁVEL",
                              "CÓD. PRODUTO", "QTD", "VALOR"} <= set(_nh23)
       and _th23["kpis_de"](_th23["linhas"][:20])
       and _th23["total_de"](_th23["linhas"][:20])[15] == sum(
           l_[15] or 0 for l_ in _th23["linhas"][:20]),
       f"Farol de Garantias: aba Histórico de compra "
       f"({len(_th23['linhas']) if _th23 else 0} itens)")
# (22/10, Alexandre) Farol de Entregas: a ordem pedida, SLA pintado pelo
# prazo (selo pela linha), ETAPA inteira, sem SALDO FRETE
_te22 = _re16["tabelas"][0]
_vis22 = [c_["nome"] for c_ in _te22["colunas"] if not c_.get("oculta")]
_cs22 = {c_["nome"]: c_ for c_ in _te22["colunas"]}
_ix22 = {c_["nome"]: i_ for i_, c_ in enumerate(_te22["colunas"])}
checar(_vis22 == ["SITUAÇÃO", "SLA", "DT. PED", "DT. NF", "DT. PREVISTA",
                  "DT. REAL", "UF", "CIDADE", "CLIENTE", "VLR NF",
                  "VLR FRETE", "TRANSPORTADORA", "RESPONSÁVEL", "TBL FRETE",
                  "VLR REAL FRETE", "ETAPA", "NF", "FILIAL"]
       and "LOCAL/FRETE" not in (_te22.get("filtros") or ())
       and "SLA" in _vis22 and "SALDO FRETE" not in _ix22
       and _cs22["ETAPA"].get("inteira")
       and _cs22["SLA"].get("chip_tom") == _ix22["TOM SLA"]
       and all(l_[_ix22["TOM SLA"]] in ("", "ok", "atencao", "alerta")
               for l_ in _te22["linhas"])
       and all(l_[_ix22["TOM SLA"]] == "alerta" for l_ in _te22["linhas"]
               if l_[_ix22["PRAZO"]] in ("ATRASADA", "ENTREGUE COM ATRASO"))
       and not any(k_["rotulo"] == "Saldo do frete" for k_ in _re16["kpis"]),
       "Farol de Entregas: colunas na ordem pedida, SLA pintado pelo prazo, "
       "ETAPA inteira, sem SALDO FRETE")
# (22/10, Alexandre) Farol de Saldo refeito: FATURADO real (venda -
# devolucoes), um VLR TABELA so (com o financeiro), sem autorizacao/situacao
# e sem a aba Mes a mes; o autorizado pelo Price tambem desconta
_ctx22s = rn.Contexto(AQUI)
_tit22s = [t_["titulo"] for t_ in _rs16["tabelas"]]
_nom22s = {n_ for t_ in _rs16["tabelas"] for n_ in
           [c_["nome"] for c_ in t_["colunas"]]
           + [rn.nome_filtro(f_) for f_ in t_.get("filtros") or []]}
_tp22s = _rs16["tabelas"][0]
_ix22s = {c_["nome"]: i_ for i_, c_ in enumerate(_tp22s["colunas"])}
_k22s = {k_["rotulo"]: k_ for k_ in _rs16["kpis"]}
_no22s = [l_ for l_ in _tp22s["linhas"] if rn.rotulo_no_periodo(
    _ctx22s, l_[_ix22s["MÊS"]])]
_dev22s = rn.devolucoes_da_vista(
    _ctx22s, {(l_[_ix22s["MÊS"]], l_[_ix22s["FILIAL"]],
               l_[_ix22s["VENDEDOR"]]) for l_ in _no22s},
    {l_[_ix22s["MÊS"]]: {(x_[_ix22s["FILIAL"]], x_[_ix22s["VENDEDOR"]])
                         for x_ in _tp22s["linhas"]
                         if x_[_ix22s["MÊS"]] == l_[_ix22s["MÊS"]]}
     for l_ in _no22s})
_sp22s = rn.saldos_dos_pedidos(_ctx22s)
_ok22s = all(abs(l_[_ix22s["VLR TABELA"]] - _sp22s[(k_.split("|")[0],
                                                    k_.split("|")[1])]["base"])
             < 0.01 for l_ in _tp22s["linhas"][:50]
             for k_ in [l_[_ix22s["CHAVE"]]]
             if (k_.split("|")[0], k_.split("|")[1]) in _sp22s)
checar("Mês a mês" not in _tit22s
       and not {"SITUAÇÃO", "CÓD. AUTORIZAÇÃO", "AUTORIZADO POR",
                "TABELA C/ FINANC.", "% FINANC.", "R$ FINANC.",
                "SEM AUTORIZAÇÃO", "AUTORIZADOS", "STATUS"} & _nom22s
       and "Faturado" in _k22s and "Faturado (tabela)" not in _k22s
       and not any("utoriza" in k_ for k_ in _k22s)
       and _k22s["Faturado"]["valor"] == rn.moeda(
           sum(l_[_ix22s["VLR VENDA"]] for l_ in _no22s) - _dev22s)
       and _ok22s and rn.SIT_AUT_PRICE,
       "Farol de Saldo: FATURADO real (sem as devoluções), um VLR TABELA "
       "(com o financeiro), sem autorização/situação e sem Mês a mês")
# (16/10) Painel Executivo = painel + indicadores executivos
_rp16 = rn.montar("vc_painel", AQUI)
_tp16 = [t_["titulo"] for t_ in _rp16["tabelas"]]
checar(any(t_.startswith("Executivos · ") and t_.endswith("tri")
           for t_ in _tp16) and "Executivos · analítico" in _tp16
       and _rp16.get("exec_tri"),
       "Painel Executivo: os Indicadores Executivos (tri do mês) em abas")

# (16/10) Giro: codigo e descricao inteiros; Necessidade de compra sem
# SITUACAO, vermelho so no EST. zerado e na COB. abaixo de 30 dias
_rg16 = rn.montar("pl_giro", AQUI)
_tn16 = next(t_ for t_ in _rg16["tabelas"]
             if t_["titulo"] == "Necessidade de compra")
_cn16 = {c_["nome"]: c_ for c_ in _tn16["colunas"]}
_nn16 = [c_["nome"] for c_ in _tn16["colunas"]]
checar(_cn16["SITUAÇÃO"]["oculta"] and _cn16["PRODUTO"].get("inteira")
       and _cn16["DESCRIÇÃO"].get("inteira") and _cn16["EST."].get("chip")
       and _cn16["COB (DIAS)"].get("chip")
       and "COBERTURA (DIAS)" not in _nn16
       and all(((l_[_nn16.index("EST.")] <= 0) == (_nn16.index("EST.") in
                                                   c_))
               and (((l_[_nn16.index("COB (DIAS)")] is not None and
                      l_[_nn16.index("COB (DIAS)")] < 30))
                    == (_nn16.index("COB (DIAS)") in c_))
               for l_, c_ in zip(_tn16["linhas"], _tn16["cores_celulas"])),
       "Giro: código e descrição inteiros; Necessidade de compra sem "
       "SITUAÇÃO, vermelho no EST. zerado e na COB. < 30 dias")

# (03/11, Alexandre) Painel Executivo: MoM e M3M nas tabelas de
# Faturamento (R$ e %) e de Volume (unidades e %), com o TOTAL batendo
# com o M3M do topo; em TODOS OS MESES as colunas ficam vazias
def _mm03(r_, aba):
    pn_ = next(p_ for p_ in r_["paineis"] if p_["titulo"] == aba)
    return pn_, [b_ for b_ in pn_["painel"]["blocos"]
                 if b_["tipo"] == "tabela"
                 and any(c_["nome"] == "MoM %" for c_ in b_["colunas"])]


def _num03(txt):
    return float(str(txt).replace("R$", "").replace(".", "")
                 .replace(",", ".").replace("\u2212", "-").strip() or 0)


_ok03, _txt03 = True, []
_r03 = rn.montar("vc_painel", AQUI, params={"MÊS": "10", "ANO": "2026"})
for _aba03, _suf03 in (("Faturamento", "R$"), ("Volume", "UN.")):
    _pn03, _bl03 = _mm03(_r03, _aba03)
    if len(_bl03) < 4:
        _ok03 = False; _txt03.append(f"{_aba03}: {len(_bl03)} tabelas")
        continue
    _m3k = _num03(next(k_["valor"] for k_ in _pn03["kpis"]
                       if k_["rotulo"] == "M3M"))
    for _b03 in _bl03:
        _n03 = [c_["nome"] for c_ in _b03["colunas"]]
        _t03 = _b03["total"]
        _pj03 = _t03[_n03.index("PROJEÇÃO")]
        _m3v = _t03[_n03.index(f"M3M {_suf03}")]
        if f"MoM {_suf03}" not in _n03 or _m3v is None \
                or abs((_pj03 - _m3v) - _m3k) > 1.5:
            _ok03 = False
            _txt03.append(f"{_aba03}/{_b03['titulo']}: M3M {_m3v} x {_m3k}")
_, _blv03 = _mm03(_r03, "Volume")
_bc03 = next(b_ for b_ in _blv03 if b_["titulo"] == "Por categoria")
_nc03 = [c_["nome"] for c_ in _bc03["colunas"]]
_soma03 = sum(l_[_nc03.index("MoM UN.")] or 0 for l_ in _bc03["linhas"])
if abs(_soma03 - _bc03["total"][_nc03.index("MoM UN.")]) > 1.5:
    _ok03 = False; _txt03.append(f"Volume/categoria: soma MoM {_soma03}")
_rt03 = rn.montar("vc_painel", AQUI,
                  params={"MÊS": rn.TODOS_MESES, "ANO": "2026"})
_, _blt03 = _mm03(_rt03, "Faturamento")
if not _blt03 or any(_b03["total"][-1] is not None for _b03 in _blt03):
    _ok03 = False; _txt03.append("TODOS OS MESES com MoM preenchido")
checar(_ok03, "Painel Executivo: MoM e M3M (R$/unidades e %) nas tabelas "
       "de Faturamento e Volume; TOTAL bate com o M3M do topo "
       + "; ".join(_txt03))

# (03/11, Alexandre) CATEGORIA: PEÇAS LINHA LEVE (com LEVE E PESADA),
# PEÇAS LINHA PESADA e PEÇAS LINHA MOTO; a campanha (5 pts por unidade de
# peça) e quem soma "peças" continuam com as três
import catalogo_bap as _cb03  # noqa: E402
_ok03c, _tx03c = True, []
for (_c, _l), _e in ((("PEÇAS", "LEVE"), "PEÇAS LINHA LEVE"),
                     (("PEÇAS", "LEVE E PESADA"), "PEÇAS LINHA LEVE"),
                     (("PEÇAS", "PESADA"), "PEÇAS LINHA PESADA"),
                     (("PEÇAS", "MOTO"), "PEÇAS LINHA MOTO"),
                     (("BATERIAS", "PESADA"), "BATERIAS")):
    if _cb03.categoria_da_linha(_c, _l) != _e:
        _ok03c = False; _tx03c.append(f"{_c}/{_l}")
if _cb03.ORDEM_CATEGORIA[:3] != _cb03.CATEGORIAS_PECAS:
    _ok03c = False; _tx03c.append("ordem")
if not (rn._categoria_e("PEÇAS LINHA MOTO", "PEÇAS")
        and rn._categoria_e("PEÇAS LINHA PESADA", "PECAS")
        and not rn._categoria_e("BATERIAS", "PEÇAS")
        and not rn._categoria_e("PEÇAS LINHA LEVE", "PEÇAS LINHA MOTO")):
    _ok03c = False; _tx03c.append("campanha")
_ctx03c = rn.Contexto(AQUI)
_cats03c = {_ctx03c.categoria_bap(i_["cod"]) for i_ in _ctx03c.tabela["itens"]}
if "PEÇAS" in _cats03c or not {"PEÇAS LINHA LEVE",
                               "PEÇAS LINHA PESADA"} <= _cats03c:
    _ok03c = False; _tx03c.append(f"categorias {sorted(_cats03c)}")
_pn03c, _ = _mm03(_r03, "Faturamento")
_bc03c = next(b_ for b_ in _pn03c["painel"]["blocos"]
              if b_["tipo"] == "tabela" and b_["titulo"] == "Por categoria")
_rl03c = {l_[0]: l_[2] or 0 for l_ in _bc03c["linhas"]}
_pc03c = sum(v_ for k_, v_ in _rl03c.items() if k_.startswith("PEÇAS"))
_it03c = sum(rn._liquido(i_) for i_ in _ctx03c.tabela["itens"]
             if i_["tipo"] in ("VND", "DEV") and i_.get("dt_nf")
             and rn.mes_de(i_["dt_nf"]) == "2026-10"
             and _ctx03c.categoria_bap(i_["cod"]) in rn.LINHAS_PECAS)
if "PEÇAS" in _rl03c or abs(_pc03c - _it03c) > 1:
    _ok03c = False; _tx03c.append(f"painel {_pc03c:.0f} x {_it03c:.0f}")
checar(_ok03c, "Categoria: PEÇAS LINHA LEVE / PESADA / MOTO no catálogo, "
       "no estoque e no Painel (somam as peças); campanha conta as três "
       + "; ".join(_tx03c))

# (03/11, Alexandre) vendedor INATIVO no Planner do mes: sem desafio, sem
# meta RH/RV (visita, positivacao, cadastro); o desafio vai para os ativos
# e o time continua somando a meta geral do mes
import bap_dados as _bd03i  # noqa: E402
_ok03i, _tx03i = True, []
try:
    _mn03i, _par03i, _pl03i, _res03i = _bd03i._contexto_meta(AQUI, "2026-11")
    _rv03i = _res03i["recortes"]["vendedor"]
    _in03i = [l_ for l_ in _rv03i if l_.get("chave")
              and l_.get("vendedor_ativo") is False]
    _geral03i = _mn03i.meta_geral_do_mes(_par03i, "2026-11")
    for l_ in _in03i:
        if any(abs(l_.get(k_) or 0) > 0.5 for k_ in (
                "meta", "meta_rh", "meta_visita", "meta_positivacao",
                "meta_cadastro")):
            _ok03i = False; _tx03i.append(f"{l_['chave']} com meta")
    _soma03i = sum(l_["meta"] for l_ in _rv03i)
    if _geral03i and abs(_soma03i - _geral03i) > 1:
        _ok03i = False; _tx03i.append(f"soma {_soma03i:.0f} x {_geral03i:.0f}")
    _sup03i = sum(l_["meta"] for l_ in _res03i["recortes"]["supervisor"])
    if abs(_sup03i - _soma03i) > 1:
        _ok03i = False; _tx03i.append(f"supervisores {_sup03i:.0f}")
    _txt_in = f"{len(_in03i)} inativo(s)"
except FileNotFoundError:
    _txt_in = "sem PLANNER de NOV (pulado)"
checar(_ok03i, "Meta: vendedor inativo no Planner sem desafio e sem RV; o "
       "desafio vai para os ativos e o time soma a meta geral - "
       + _txt_in + " " + "; ".join(_tx03i))

# (05/11, Alexandre) MES FECHADO FICA COMO ERA: quem trabalhou em OUT conta
# em OUT, mesmo inativado no Planner de NOV. Pasta de teste sem a
# configuracao de OUT (PLANNER_MESES so com NOV): o ATIVO de OUT vem do
# PLANNER_BAP_2026-10 (no backup, como no PC); NOV e dezembro (sem nada)
# ficam com a equipe de hoje
import visitas_nucleo as _vn05e  # noqa: E402
from openpyxl import Workbook as _Wb05e  # noqa: E402
_ok05e, _tx05e = True, []
with tempfile.TemporaryDirectory() as _d05e:
    _r05e = Path(_d05e)
    _pes05e = [{"cod_protheus": "000949", "cod_maxima": "999949",
                "nome": "VENDEDOR TESTE INATIVO", "cargo": "VENDEDOR",
                "responde_a": "", "ativo": False},
               {"cod_protheus": "000948", "cod_maxima": "999948",
                "nome": "VENDEDOR TESTE ATIVO", "cargo": "VENDEDOR",
                "responde_a": "", "ativo": True}]
    _cfg05e = json.dumps({"mes": "2026-11", "pessoas": _pes05e})
    (_r05e / "planner_config.json").write_text(_cfg05e, "utf-8")
    _pm05e = _r05e / "SISTEMA BAP" / "PLANNER_MESES"
    _pm05e.mkdir(parents=True)
    (_pm05e / "planner_config_2026-11.json").write_text(_cfg05e, "utf-8")
    _bk05e = _r05e / "SISTEMA BAP" / "BACKUP_RELATORIOS" / \
        "BKP_RELATORIOS_PLANNER"
    _bk05e.mkdir(parents=True)
    _wb05e = _Wb05e()
    _ws05e = _wb05e.active
    _ws05e.title = "PLANNER"
    _ws05e.append(["COD_CLIENTE", "LOJA", "COD_VENDEDOR", "VENDEDOR",
                   "VENDEDOR_ATIVO", "DATA_VISITA"])
    _ws05e.append(["010001", "01", "000949", "VENDEDOR TESTE INATIVO",
                   "SIM", date(2026, 10, 15)])
    _ws05e.append(["010002", "01", "000948", "VENDEDOR TESTE ATIVO",
                   "SIM", date(2026, 10, 15)])
    _wb05e.save(_bk05e / "PLANNER_BAP_2026-10_20261022.xlsx")
    _dd05e = _r05e / "RELATORIOS" / "Visitas" / "diario"
    _dd05e.mkdir(parents=True)
    _cab05e = ("CODIGOGERAL;NOME;CODIGOGRUPOFILIAL;CODIGOGRUPOSUPERVISOR;"
               "HORAATENDIMENTOPRIMEIROCLIENTE;HORAATENDIMENTOULTIMOCLIENTE;"
               "AGENDADOS;TOTALVISITADOSDENTROAGENDAFORAAGENDA\n")
    for _dia05e in ("20261015", "20261103", "20261201"):
        (_dd05e / f"{_dia05e}.csv").write_text(
            _cab05e + "999949;VENDEDOR TESTE INATIVO;0101002;;08:00:00;"
            "16:00:00;10;7\n999948;VENDEDOR TESTE ATIVO;0101002;;08:00:00;"
            "16:00:00;10;9\n", "utf-8")
    _at05e = {(f"{l_['data']:%Y-%m}", l_["cod"]): l_["ativo"]
              for l_ in _vn05e.registros(_r05e)}
    for (_m05e, _c05e), _q05e in {
            ("2026-10", "999949"): True, ("2026-11", "999949"): False,
            ("2026-12", "999949"): False, ("2026-10", "999948"): True,
            ("2026-11", "999948"): True}.items():
        if _at05e.get((_m05e, _c05e)) is not _q05e:
            _ok05e = False
            _tx05e.append(f"{_c05e} em {_m05e}: {_at05e.get((_m05e, _c05e))}")
# na pasta de verdade: o Planner de cada mes manda (OUT com quem estava)
for _m05e in ("2026-10", "2026-11"):
    _cf05e = AQUI / "SISTEMA BAP" / "PLANNER_MESES" / \
        f"planner_config_{_m05e}.json"
    if not _cf05e.exists():
        continue
    _eq05e = _vn05e.Equipe(AQUI, _m05e)
    for _p05e in json.loads(_cf05e.read_text("utf-8")).get("pessoas") or []:
        _pe05e = _eq05e.por_cod.get(str(_p05e.get("cod_protheus") or ""))
        if _pe05e is not None and (_pe05e.get("ativo") is not False) != \
                (_p05e.get("ativo") is not False):
            _ok05e = False
            _tx05e.append(f"{_p05e.get('nome')} em {_m05e}")
checar(_ok05e, "Equipe do mês: mês fechado usa a equipe do mês - inativo "
       "em NOV conta em OUT (sem a configuração de OUT, pelo PLANNER de OUT "
       "no backup); NOV e meses sem Planner com a equipe de hoje "
       + "; ".join(_tx05e))

print()
print("TUDO CERTO" if not FALHAS else f"{len(FALHAS)} FALHA(S):")
for f in FALHAS:
    print("  -", f)
sys.exit(1 if FALHAS else 0)

