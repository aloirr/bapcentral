# -*- coding: utf-8 -*-
"""
Teste dos processos novos de out/2026, sem abrir janela nenhuma:

  [1] Farol DDR ............ o mes nasce da rotina, pela frequencia; nao
                             sobrescreve mes que ja existe; a nota e por
                             pontos (conferida recalculando no LibreOffice)
  [2] Pos-venda ............ o acompanhamento so ACRESCENTA: linha gravada
                             nunca muda; devolucao aberta a mao nao duplica
  [3] TABELA_BAP ........... as 22 colunas do ftPedidos calculadas em Python
                             batem com o que o Excel tinha gravado
  [4] BAP Central e --aba .. os botoes apontam para relatorios e abas que
                             existem
  [7] TABELA_BAP so saida .. a fotografia (.csv.gz) volta com os tipos; o
                             leitor hibrido = .xlsx; formulas em Python =
                             Excel; a rodada rapida = a completa
  [8] Arquivo em aberto .... o aviso Continuar / Cancelar, a espera, o
                             Excel preso encerrado pelo PID
  [9] Salvar e fechar ...... o Excel sem janela encerrado, o com janela
                             nunca; somente leitura nao e "em aberto"

Roda numa pasta temporaria. Uso:  python smoke_processos.py
"""
import json
from collections import Counter, defaultdict
import shutil
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
import tempfile
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import openpyxl                                              # noqa: E402

import farol_ddr as fd                                       # noqa: E402
import pastas_bap as pb                                      # noqa: E402
import pos_venda as pv                                       # noqa: E402

PASTA = Path(tempfile.mkdtemp(prefix="smoke_proc_")) / "RELATORIOS"
PASTA.mkdir()
TABELA = AQUI / "RELATORIOS" / "TABELA_BAP.xlsx"
falhas = []


def checar(cond, msg):
    print(("  ok    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


# --------------------------------------------------------------------------
print("\n[1] FAROL DDR")
destino = fd.gerar_farol(2026, 10, PASTA)
checar(destino.exists(), f"o mes nasce: {destino.name}")
wb = openpyxl.load_workbook(destino)
abas = wb.sheetnames
checar(abas[:2] == ["Leia-me", "Painel"], f"Leia-me e Painel na frente: {abas[:3]}")
for quem in ("Juliana Almeida", "Mayara Santos", fd.NOVA):
    checar(quem in abas, f"aba de {quem}")
checar(not any("em aberto" in a for a in abas),
       "vaga em aberto fica fora do Farol (nao derruba a nota do time)")
uteis = fd.dias_uteis(2026, 10, {f for f, _ in fd.FERIADOS_INICIAIS})
checar(len(uteis) == 21 and date(2026, 10, 12) not in uteis,
       f"outubro/2026 tem 21 dias uteis, sem o 12/10 ({len(uteis)})")


def linhas_de(aba, comeco):
    ws = wb[aba]
    return [ws.cell(r, 1).value for r in range(5, ws.max_row + 1)
            if str(ws.cell(r, 4).value or "").startswith(comeco)]


checar(len(linhas_de("Mayara Santos", "Integração diária")) == 21,
       "atividade DIÁRIA aparece nos 21 dias")
checar(len(linhas_de("Juliana Almeida", "Enviar o painel da semana")) == 3,
       "atividade de SEGUNDA aparece nas 3 segundas uteis (12/10 e feriado)")
brindes = linhas_de("Allaiza Menezes", "Controle de brindes")
checar(len(brindes) == 9 and all(d.weekday() in (1, 3) for d in brindes),
       f"TER,QUI aparece so terca e quinta ({len(brindes)})")
checar(len(linhas_de("Allaiza Menezes", "Relatório de produtos")) == 3,
       "QUINZENAL SEX: 1a, 3a e 5a sexta")
matinal = linhas_de("Allaiza Menezes", "Matinal de trade")
checar(len(matinal) == 4 and all(d.weekday() == 2 for d in matinal),
       f"Allaiza: matinal de trade toda quarta ({len(matinal)})")
rota = linhas_de("Allaiza Menezes", "Rota trade")
checar(len(rota) == 5 and all(d.weekday() == 4 for d in rota),
       f"Allaiza: rota trade toda sexta ({len(rota)})")
brief = linhas_de("Allaiza Menezes", "Briefings completos")
checar(brief and not any(d.weekday() == 4 for d in brief),
       "Allaiza: atividade de escritorio fica fora da sexta (dia de rota)")
camp = linhas_de("Allaiza Menezes", "Atualização dos controles")
checar(camp and not any(d.weekday() in (2, 4) for d in camp),
       "Allaiza: controles de campanha fora da quarta (matinal) e da sexta")
checar(fd.NOVA == "Estefanie Pacheco" and "NOVA ASSISTENTE" not in abas,
       "a assistente de pos-venda tem nome no Farol")
checar(not linhas_de("Allaiza Menezes", "Criação de código"),
       "SOB DEMANDA nao entra como obrigacao")
ws = wb["Juliana Almeida"]
formula = ws.cell(5, 8).value
checar(isinstance(formula, str) and formula.startswith("=IF(")
       and '"ENTREGUE PARCIAL"' in formula and "/2" in formula,
       f"Pontos ganhos e FORMULA (era 0 digitado): {formula}")
checar(fd.STATUS == ["ENTREGUE", "ENTREGUE PARCIAL", "NÃO ENTREGUE"]
       and [wb["Listas"].cell(i, 1).value for i in (1, 2, 3)] == fd.STATUS
       and fd.pontos_do_status("ENTREGUE PARCIAL", 5) == 2.5
       and fd.pontos_do_status("SIM", 5) == 5
       and fd.pontos_do_status("NÃO ENTREGUE", 5) == 0,
       "Farol DDR: status ENTREGUE / ENTREGUE PARCIAL (metade) / NÃO ENTREGUE")
checar(ws.cell(5, 6).value in (3, 5),
       "pontos da linha gravados como numero (mudar a Rotina nao reescreve o passado)")
try:
    fd.gerar_farol(2026, 10, PASTA)
    checar(False, "gerar o mesmo mes de novo e recusado")
except FileExistsError:
    checar(True, "gerar o mesmo mes de novo e recusado - ele guarda as marcacoes")
# (11/10) o mes seguinte nasce do CADASTRO DO ANALISTA (farol_ddr_config
# .json, BAP Analista › Farol DDR) - o Excel e so consulta (protegido)
cfg_ddr = fd.ler_config(PASTA.parent)
checar(cfg_ddr is not None and all(
    openpyxl.load_workbook(destino)[a_].protection.sheet
    for a_ in ("Equipe", "Rotina", "Feriados")),
       "Farol DDR: o cadastro nasce do 1o mes; Equipe, Rotina e Feriados "
       "protegidas no Excel")
eq_c, rot_c, fer_c = cfg_ddr
eq_c = [(("Fulana de Tal",) + tuple(e_[1:])) if e_[0] == fd.NOVA else e_
        for e_ in eq_c]
rot_c = [tuple(("Fulana de Tal" if j_ == 1 and v_ == fd.NOVA else
                ("SEG,QUA" if j_ == 5 and str(r_[3]).startswith(
                    "Enviar o painel da semana") else v_))
               for j_, v_ in enumerate(r_)) for r_ in rot_c]
fd.salvar_config(eq_c, rot_c, fer_c, PASTA.parent)
# mexer no Excel nao muda mais o proximo mes
wb_r = openpyxl.load_workbook(destino)
wb_r["Equipe"].cell(5, 1).value = "NAO VALE"
wb_r.save(destino)
nov = fd.gerar_farol(2026, 11, PASTA)
wb2 = openpyxl.load_workbook(nov)
checar("Fulana de Tal" in wb2.sheetnames and fd.NOVA not in wb2.sheetnames
       and "NAO VALE" not in wb2.sheetnames,
       "trocou o nome no cadastro do Analista: novembro nasce com o nome "
       "dela (a edição no Excel não vale)")
k = [wb2["Juliana Almeida"].cell(r, 1).value
     for r in range(5, wb2["Juliana Almeida"].max_row + 1)
     if str(wb2["Juliana Almeida"].cell(r, 4).value or "").startswith("Enviar o painel da semana")]
checar(k and {d.weekday() for d in k} == {0, 2},
       "mudou a frequencia na Rotina: novembro ja nasce com ela")

# a nota, recalculada de verdade
soffice = shutil.which("soffice") or shutil.which("libreoffice")
if soffice:
    wb3 = openpyxl.load_workbook(destino)
    ws = wb3["Juliana Almeida"]
    for r in range(5, ws.max_row + 1):
        d = ws.cell(r, 1).value
        if isinstance(d, datetime) and d.day == 1 and ws.cell(r, 4).value:
            ws.cell(r, 7).value = "SIM"
    ws = wb3["Mayara Santos"]
    for r in range(5, ws.max_row + 1):
        d = ws.cell(r, 1).value
        if isinstance(d, datetime) and d.day == 1 and ws.cell(r, 4).value:
            ws.cell(r, 7).value = "NÃO"
            ws.cell(r, 9).value = fd.AUSENCIA
    teste = PASTA / "farol_marcado.xlsx"
    wb3.save(teste)
    saida = PASTA / "calc"
    subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(saida), str(teste)], capture_output=True,
                   timeout=240)
    calc = saida / teste.name
    if calc.exists():
        p = openpyxl.load_workbook(calc, data_only=True)["Painel"]
        por = {p.cell(r, 1).value: [p.cell(r, c).value for c in range(1, 12)]
               for r in range(5, 15)}
        ju, ma = por.get("Juliana Almeida"), por.get("Mayara Santos")
        hoje_dentro = date.today() >= date(2026, 10, 1)
        if ju and hoje_dentro:
            checar(ju[5] and ju[5] > 0, f"Juliana: SIM no dia 1 vira pontos ({ju[5]})")
        if ma and hoje_dentro:
            checar(ma[9] == 0, "Mayara: ausencia justificada NAO conta como NAO")
        checar(p.cell(5, 11).value is not None, "o Painel calcula a situacao")
    else:
        print("  (LibreOffice nao converteu - nota nao conferida)")
else:
    print("  (sem LibreOffice - nota nao conferida)")

# --------------------------------------------------------------------------
print("\n[2] ACOMPANHAMENTO DE POS-VENDA")
wb = pv.criar_arquivo()
checar({"Leia-me", "PAINEL", "ENTREGAS", "DEVOLUCOES", "GARANTIAS", "PRAZOS"}
       <= set(wb.sheetnames) and wb.sheetnames[0] == "PAINEL",
       f"as abas, com o PAINEL na frente: {wb.sheetnames}")
nota = {"nf": "000000900", "serie": "1", "data_nf": date(2026, 10, 2),
        "cliente": "CLIENTE A", "cidade": "MANAUS", "uf": "AM", "valor": 100.0,
        "etapa": "FATURADA", "cod_cliente": "1", "vendedor": "", "filial": "0101001",
        "cidade_filial": "MANAUS", "pedido": "1", "itens": 1,
        "chave": pv.chave_nf("0101001", "000000900", "1")}
dev = {"data": date(2026, 10, 3), "nf_dev": "000000512", "nf_origem": "900",
       "data_venda": None, "cliente": "CLIENTE A", "vendedor": "", "valor": 10.0,
       "produtos": "X x1", "etapa": "NF DEV EMITIDA", "cod_cliente": "1",
       "filial": "0101001", "origem": "BAP Tools",
       "chave": pv.chave_nf("0101001", "000000512", "1")}
r = pv.acrescentar(wb, [nota], [])
checar(r["entregas"] == 1, "nota de venda nova vira linha de ENTREGA")
E = [c[1] for c in pv.COLUNAS_ENTREGA]
ws = wb[pv.ABA_ENT]
checar(ws.cell(5, E.index("etapa") + 1).value == "FATURADA",
       "a linha nasce na etapa FATURADA")
ws.cell(5, E.index("etapa") + 1, "ENTREGUE")
ws.cell(5, E.index("entregue_em") + 1, datetime(2026, 10, 3))
r = pv.acrescentar(wb, [nota], [])
checar(r["entregas"] == 0 and ws.cell(5, E.index("etapa") + 1).value == "ENTREGUE",
       "a mesma nota nao entra de novo - e a etapa que a assistente marcou fica")
D = [c[1] for c in pv.COLUNAS_DEVOLUCAO]
wsd = wb[pv.ABA_DEV]
wsd.cell(5, D.index("data") + 1, datetime(2026, 10, 1))
wsd.cell(5, D.index("etapa") + 1, "SOLICITADA")
wsd.cell(5, D.index("nf_dev") + 1, "512")
r = pv.acrescentar(wb, [], [dev])
checar(r["devolucoes"] == 0,
       "devolucao aberta a mao com a NF escrita: o BAP Tools reconhece e nao duplica")
outra = dict(dev, nf_dev="000000513", chave=pv.chave_nf("0101001", "513", "1"))
r = pv.acrescentar(wb, [], [outra])
checar(r["devolucoes"] == 1, "a nota de devolucao que ninguem abriu entra")
interior = dict(nota, nf="000000901", data_nf=date(2026, 10, 9),
                cidade="PARINTINS", chave=pv.chave_nf("0101001", "000000901", "1"))
capital_acento = dict(nota, nf="000000902", data_nf=date(2026, 10, 9),
                      cidade="SÃO LUÍS", uf="MA",
                      chave=pv.chave_nf("0101001", "000000902", "1"))
r = pv.acrescentar(wb, [interior, capital_acento], [])
checar(r["entregas"] == 2, "mais duas notas: interior e capital com acento")
arq = PASTA / pv.ARQUIVO
wb.save(arq)
lido = pv.ler_acompanhamento(arq, hoje=date(2026, 10, 20))
e0, e1, e2 = lido["entregas"][:3]
checar(e0["prevista"] == date(2026, 10, 7) and e0["situacao"] == "NO PRAZO",
       f"Manaus (capital): 3 dias uteis, sex 02/10 -> qua 07/10 ({e0['prevista']}, {e0['situacao']})")
checar(e1["prevista"] == date(2026, 10, 19) and e1["situacao"] == "ATRASADA",
       f"Parintins (interior): 5 dias uteis pulando o 12/10 -> 19/10 ({e1['prevista']}, {e1['situacao']})")
checar(e2["prevista"] == date(2026, 10, 15),
       f"Sao Luis com acento e capital: 3 dias uteis -> 15/10 ({e2['prevista']})")
f_prev = wb[pv.ABA_ENT].cell(5, E.index("prevista") + 1).value
checar(isinstance(f_prev, str) and "WORKDAY(" in f_prev and "PRAZOS!$E$" in f_prev,
       "no Excel a PREVISTA ATE e WORKDAY com os feriados da aba PRAZOS")
if shutil.which("soffice") or shutil.which("libreoffice"):
    saida = PASTA / "calc_pv"
    subprocess.run([shutil.which("soffice") or shutil.which("libreoffice"),
                    "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(saida), str(arq)], capture_output=True,
                   timeout=240)
    calc = saida / arq.name
    if calc.exists():
        we = openpyxl.load_workbook(calc, data_only=True)[pv.ABA_ENT]
        col = E.index("prevista") + 1
        excel_prev = [we.cell(n, col).value for n in (5, 6, 7)]
        excel_prev = [v.date() if isinstance(v, datetime) else v for v in excel_prev]
        checar(excel_prev == [e0["prevista"], e1["prevista"], e2["prevista"]],
               f"a formula do Excel da a mesma data que o Python ({excel_prev})")
checar(lido["indicadores"]["devolucoes_sem_motivo"] == 2,
       "o indicador conta as devolucoes sem motivo")
if TABELA.exists():
    r = pv.atualizar_arquivo(TABELA, PASTA / "pv_real.xlsx", date(2026, 9, 1), AQUI)
    checar(r["entregas"] > 0 and r["devolucoes"] > 0,
           f"da TABELA_BAP real: {r['entregas']} nota(s) de venda e "
           f"{r['devolucoes']} de devolucao desde 01/09")

# --------------------------------------------------------------------------
print("\n[3] AS COLUNAS CALCULADAS DO ftPedidos")
if TABELA.exists():
    import bap_automation as ba                              # noqa: E402
    cache = openpyxl.load_workbook(TABELA, read_only=True, data_only=True)
    wsc = cache["ftPedidos"]
    cab = list(next(wsc.iter_rows(min_row=1, max_row=1, values_only=True)))
    excel = [list(x) for x in wsc.iter_rows(min_row=2, values_only=True)]
    cache.close()
    wb = openpyxl.load_workbook(TABELA)
    # imitando o teto antigo, tem de dar EXATAMENTE o que o Excel gravou
    ba.calcular_colunas_do_ftpedidos(wb, limite_linha=11000)
    ws = wb["ftPedidos"]
    difs = 0
    total = 0
    # so as linhas com dado de verdade (o Excel arrastava formula em linha
    # vazia e gravava lixo como '4' e 0; o Python deixa a linha em branco)
    origem = [i for i, t in enumerate(cab) if t and t not in ba.COLUNAS_FTPEDIDOS_EM_PYTHON]
    for n, nome in enumerate(cab):
        if nome not in ba.COLUNAS_FTPEDIDOS_EM_PYTHON:
            continue
        for k, linha in enumerate(excel):
            if not any(linha[i] not in (None, "") for i in origem if i < len(linha)):
                continue
            a, b = ws.cell(k + 2, n + 1).value, linha[n]
            if isinstance(b, datetime) and isinstance(a, (int, float)):
                b = (b - datetime(1899, 12, 30)).days
            total += 1
            if not ((a in (None, "") and b in (None, ""))
                    or (isinstance(a, (int, float)) and isinstance(b, (int, float))
                        and abs(a - b) <= 1e-6 * max(1, abs(a), abs(b)))
                    or a == b):
                difs += 1
    checar(difs == 0, f"{total} celulas conferidas contra o Excel: {difs} diferenca(s)")
    sem = ba.calcular_colunas_do_ftpedidos(wb)
    checar(sem["colunas"] == 22, "sem teto: as 22 colunas calculadas")
else:
    print("  (sem TABELA_BAP nesta maquina - pulando)")

# --------------------------------------------------------------------------
print("\n[3b] dClientesBap: A COLUNA STATUS DO BAP TOOLS (OUT/2026)")
import bap_automation as ba                                  # noqa: E402
import pandas as pd                                          # noqa: E402
_wb = openpyxl.Workbook()
_ws = _wb.active
_ws.title = "dClientesBap"
_ws.append(["A1_FILIAL", "A1_COD", "A1_LOJA", "A1_MSBLQL", "A1_NOME"])
_ws.append(["0101", "000001", "01", "2", "VELHO A"])
_ws.append(["0101", "000002", "01", "2", "VELHO B"])
_df = pd.DataFrame({"STATUS": ["ATIVO", "INATIVO", "INATIVO"],
                    "A1_COD": ["000001", "000002", "000003"],
                    "A1_LOJA": ["01", "01", "01"],
                    "A1_NOME": ["A", "B", "C"], "A1_XNOVA": [1, 2, 3]})
_cfg = next(c for c in ba.RELATORIOS if c["id"] == "clientes")
_res = ba.atualizar_aba(_ws, ba.derivar_colunas_clientes(_df, _ws), _cfg)
_cab = [c.value for c in _ws[1]]
_lin = [[c.value for c in r] for r in _ws.iter_rows(min_row=2)]
checar(_cab == ["A1_FILIAL", "A1_COD", "A1_LOJA", "A1_MSBLQL", "A1_NOME",
                "STATUS"] and _res["colunas_sem_par"] == ["A1_XNOVA"],
       "STATUS vira coluna nova no fim da aba (as outras sem par seguem fora)")
checar([l[3] for l in _lin] == ["2", "1", "1"]
       and [l[5] for l in _lin] == ["ATIVO", "INATIVO", "INATIVO"]
       and [l[0] for l in _lin] == ["0101"] * 3,
       "A1_MSBLQL refeito do STATUS e A1_FILIAL preenchido na linha nova")

# --------------------------------------------------------------------------
print("\n[4] BAP CENTRAL E O --aba")
checar(pb.aba_pedida(["--aba", "3"]) == 2 and pb.aba_pedida(["--aba=1"]) == 0
       and pb.aba_pedida([]) is None and pb.aba_pedida(["--aba", "x"]) is None,
       "--aba N vira o indice certo (1 = primeira aba)")
import bap_central as bc                                     # noqa: E402
import relatorios_nucleo as rn                               # noqa: E402
for area, _q, botoes in bc.QUADRADOS:
    for rotulo, rid in botoes:
        checar(rid in rn.POR_ID, f"{area[:14]:14} | {rotulo}: relatorio {rid}")
checar([q[0] for q in bc.QUADRADOS] == [bc.PRE, bc.VEN, bc.POS, bc.TRADE],
       "os quadrados das assistentes e o do Trade (o do Analista vem a parte)")
checar((AQUI / "bap_analista.py").exists() and (AQUI / "bap_relatorios.py").exists(),
       "BAP Analista e a janela de relatorios estao na pasta")
for script in ("bap_meta.py", "bap_oportunidade.py", "bap_planner.py"):
    texto = (AQUI / script).read_text(encoding="utf-8")
    checar("ABA_INICIAL = pb.aba_pedida()" in texto
           and "self._ir_para_aba_inicial()" in texto
           and "pb.base_da_janela()" in texto,
           f"{script} aceita --aba e abre dentro do BAP Analista")

# --------------------------------------------------------------------------
print("\n[5] CNAE E SEGMENTO DOS CLIENTES")
import cnae_bap as cb                                        # noqa: E402
from datetime import timedelta                               # noqa: E402

seg_arq = PASTA / "SEGMENTACAO_BAP.xlsx"
cache_arq = PASTA / "cache_cnae.json"
c1, c2, c3, c4, c5, c6 = ("11222333000181", "11444777000161", "19131243000197",
                          "45723174000110", "04252011000110", "33000167000101")
cache = {
    c1: {"CNAE_PRINCIPAL": "4530-7/03", "CNAE_PRINCIPAL_DESC": "pecas",
         "CNAES_SECUNDARIOS": [], "SITUACAO_RF": "ATIVA"},
    c2: {"CNAE_PRINCIPAL": "4520-0/01", "CNAE_PRINCIPAL_DESC": "mecanica",
         "CNAES_SECUNDARIOS": [["4530-7/05", "pneus"]], "SITUACAO_RF": "ATIVA"},
    c3: {"CNAE_PRINCIPAL": "4520-0/01", "CNAE_PRINCIPAL_DESC": "mecanica",
         "CNAES_SECUNDARIOS": [["4530-7/03", "pecas"]], "SITUACAO_RF": "ATIVA"},
    c4: {"CNAE_PRINCIPAL": "4120-4/00", "CNAE_PRINCIPAL_DESC": "construcao",
         "CNAES_SECUNDARIOS": [["4930-2/02", "carga"]], "SITUACAO_RF": "BAIXADA"},
    c5: {"CNAE_PRINCIPAL": "4712-1/00", "CNAE_PRINCIPAL_DESC": "mercado",
         "CNAES_SECUNDARIOS": [], "SITUACAO_RF": "ATIVA"},
    c6: {"ERRO": "x", "QUANDO": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")},
}
cb.gravar_cache(cache, cache_arq)
ctx = cb.Contexto(caminho_cache=cache_arq, caminho_segmentacao=seg_arq)
checar(seg_arq.exists() and {"SEGMENTOS", "REGRAS_CNAE", "AJUSTE_MANUAL"}
       <= set(openpyxl.load_workbook(seg_arq).sheetnames),
       "a SEGMENTACAO_BAP nasce sozinha com SEGMENTOS, REGRAS_CNAE e AJUSTE_MANUAL")
checar(len(cb.SEGMENTOS) <= 8 and {cb.AUTOPECAS, cb.MOTOPECAS, cb.AUTOCENTER,
       cb.DISTRIBUIDOR, cb.FROTISTA} <= {x[0] for x in cb.SEGMENTOS},
       f"no maximo 8 segmentos, com os 5 obrigatorios ({len(cb.SEGMENTOS)})")
k = lambda doc, nome="", cod="1", loja="01": ctx.classificar(cod, loja, doc, nome)  # noqa: E731
checar(k(c1)[4:] == [cb.AUTOPECAS, "VAREJO DE PEÇAS NOVAS", "CNAE PRINCIPAL"],
       f"4530-7/03 = AUTOPECAS ({k(c1)[4:]})")
checar(k(c2)[4] == cb.AUTOCENTER, f"oficina com pneu no secundario = AUTOCENTER ({k(c2)[4]})")
checar(k(c3)[4] == cb.OFICINA, f"oficina so com venda de pecas continua OFICINA ({k(c3)[4]})")
checar(k(c4)[4:] == [cb.FROTISTA, "TRANSPORTADORA", "CNAE SECUNDÁRIO"] and k(c4)[3] == "BAIXADA",
       f"construtora com transporte de carga no secundario = FROTISTA ({k(c4)[4:]})")
_dm = ctx.decidir("1", "01", c5, "MERCADINHO MOTO PECAS DO ZE")
checar(_dm["EXCLUIDO"] and _dm["SEGMENTO"] == ""
       and _dm["SEGMENTO_SUGERIDO"] == cb.MOTOPECAS,
       "CNAE de mercadinho com MOTO no nome: o CNAE manda (EXCLUIDO), o nome so sugere")
checar(k("52998224725", "JOSE DA SILVA")[4] == ""
       and k("52998224725")[3] == "PESSOA FÍSICA",
       "CPF = EXCLUIDO (pessoa fisica, sem CNAE)")
wbs = openpyxl.load_workbook(seg_arq)
wbs["AJUSTE_MANUAL"].append(["000001", "", "distribuidor", "BATERIA", "teste"])
wbs["REGRAS_CNAE"].append(["4712", "SUPERMERCADO", "X"])
wbs.save(seg_arq)
ctx = cb.Contexto(caminho_cache=cache_arq, caminho_segmentacao=seg_arq)
checar(k(c1)[4:] == [cb.DISTRIBUIDOR, "BATERIA", "AJUSTE MANUAL"],
       "AJUSTE_MANUAL ganha de tudo (COD sem loja vale para todas as lojas)")
checar(k(c5, cod="2")[4] == "",
       "segmento escrito fora dos 8 na REGRAS_CNAE nao vale: o cliente e EXCLUIDO")

chamados = []
def falsa(cnpj):
    chamados.append(cnpj)
    return {"CNAE_PRINCIPAL": "4530-7/03", "FONTE": "teste"}
r = cb.atualizar_cache([c1, c2, "99888777000155", c6], consulta=falsa,
                       caminho_cache=cache_arq, pausa=0)
checar(chamados == ["99888777000155"] and r["achados"] == 1,
       f"so consulta quem nao tem CNAE (erro de ontem espera {cb.TENTAR_ERRO_DE_NOVO_DIAS} dias): {chamados}")
cache = cb.ler_cache(cache_arq)
cache[c6]["QUANDO"] = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
cb.gravar_cache(cache, cache_arq)
chamados.clear()
cb.atualizar_cache([c6], consulta=falsa, caminho_cache=cache_arq, pausa=0)
checar(chamados == [c6], "erro antigo e consultado de novo")
novos = [f"{i:012d}" for i in range(30)]
r = cb.atualizar_cache(novos, consulta=falsa, caminho_cache=cache_arq, pausa=0, limite=10)
checar(r["consultados"] == 10 and r["ficou_para_depois"] == 20,
       "limite por rodada: o resto fica para a proxima")
r = cb.atualizar_cache([f"{i:012d}x" for i in range(30)], caminho_cache=cache_arq, pausa=0,
                       consulta=lambda c: {"ERRO": "sem rede", "QUANDO": "2026-01-01 00:00"})
checar(r["sem_internet"] and r["consultados"] == 5,
       "sem internet: para em 5 falhas seguidas e a rodada segue")
original = cb._get_json
cb._get_json = lambda url: {"razao_social": "X", "cnae_fiscal": 4530703,
                            "cnae_fiscal_descricao": "pecas",
                            "descricao_situacao_cadastral": "ATIVA",
                            "cnaes_secundarios": [{"codigo": 4520001, "descricao": "mec"}]}
lido = cb.consultar(c1)
cb._get_json = original
checar(lido["CNAE_PRINCIPAL"] == "4530-7/03" and lido["CNAES_SECUNDARIOS"][0][0] == "4520-0/01",
       "a resposta da BrasilAPI vira CNAE formatado")

if TABELA.exists():
    import base_cliente as bcli                              # noqa: E402
    bcli.TEMPO_COORDENADAS = 0      # o teste nao vai a internet
    saida = PASTA / "BASE_CLIENTE_teste.xlsx"
    bcli.gerar_base_cliente(TABELA, saida)
    wsb = openpyxl.load_workbook(saida, read_only=True)["BASE_CLIENTE"]
    linhas_b = list(wsb.iter_rows(values_only=True))
    cab_b = list(linhas_b[0])
    _nv = len(bcli.COLUNAS_VENDEDOR)
    # (28/10) o CEP (A1_CEP); (10/11) depois dele o STATUS_PROTHEUS
    # (ATIVO/INATIVO do cadastro) e a ultima coluna
    checar(cab_b[-11 - _nv:-4 - _nv] == cb.COLUNAS
           and cab_b[-4 - _nv:-2 - _nv] == ["LATITUDE", "LONGITUDE"]
           and cab_b[-2 - _nv:-2] == bcli.COLUNAS_VENDEDOR
           and cab_b[-2:] == ["CEP", "STATUS_PROTHEUS"]
           and {r[-1] for r in linhas_b[1:]} <= {"ATIVO", "INATIVO"},
           "a BASE_CLIENTE ganha as 7 colunas do CNAE, LATITUDE e LONGITUDE "
           "e, no FIM (07/10), vendedor e supervisor do Protheus e do "
           "Planner, o CEP (28/10) e o STATUS_PROTHEUS (10/11)")
    _iv = cab_b.index("VENDEDOR_PROTHEUS")
    checar(any(r[_iv] for r in linhas_b[1:]),
           "VENDEDOR_PROTHEUS (A1_VEND) preenchido na BASE_CLIENTE")
    i_seg, i_doc = cab_b.index("SEGMENTO"), cab_b.index("CNPJ")
    com_cnpj = [r for r in linhas_b[1:] if len(str(r[i_doc] or "")) == 14]
    com_seg = [r for r in linhas_b[1:] if r[i_seg]]
    checar(len(com_seg) == len(linhas_b) - 1,
           f"todo cliente sai com SEGMENTO ({len(com_seg)} de {len(linhas_b) - 1})")
    if (AQUI / "SISTEMA BAP" / "Consulta CNAE" / "cache_cnae.json").exists():
        com_cnae = [r for r in com_cnpj if r[cab_b.index("CNAE_PRINCIPAL")]]
        checar(len(com_cnae) >= 0.95 * len(com_cnpj),
               f"CNAE do cache em {len(com_cnae)} de {len(com_cnpj)} CNPJs")

# --------------------------------------------------------------------------
print("\n[6] OS 8 SEGMENTOS NA BASE, NO PLANNER E NA META")
checar(cb.NOMES_SEGMENTOS == ["AUTOPEÇAS", "MOTOPEÇAS", "DISTRIBUIDOR DE BATERIAS",
                              "AUTOCENTER", "OFICINA MECÂNICA",
                              "POSTO E TROCA DE ÓLEO", "FROTISTA/REVENDEDOR",
                              "INDÚSTRIA"], "os 8 segmentos, nesta ordem")
_ctx = cb.Contexto(caminho_cache=cache_arq, caminho_segmentacao=PASTA / "seg6.xlsx")
_d = _ctx.decidir("9", "01", "52998224725", "MOTO PECAS DO ZE")
checar(_d["EXCLUIDO"] and _d["SEGMENTO_SUGERIDO"] == cb.MOTOPECAS,
       "CPF vai para EXCLUIDOS, com a sugestao pelo nome (o nome nao decide)")
checar(_ctx.decidir("9", "01", c4)["SEGMENTO"] == cb.FROTISTA,
       "CNAE secundario automotivo ainda classifica (construtora com transporte)")
_ind = {"99887766000105": {"CNAE_PRINCIPAL": "2222-6/00",
                           "CNAE_PRINCIPAL_DESC": "embalagens", "CNAES_SECUNDARIOS": []}}
_ctx.cache.update(_ind)
checar(_ctx.decidir("9", "01", "99887766000105")["SEGMENTO"] == cb.INDUSTRIA,
       "fabricacao (divisoes 10-33) = INDUSTRIA")
_ctx.cache["11222333000181"] = {"CNAE_PRINCIPAL": "4712-1/00",
                                "CNAES_SECUNDARIOS": [["2222-6/00", "x"]]}
checar(_ctx.decidir("9", "01", "11222333000181")["EXCLUIDO"],
       "mercadinho com fabricacao so no secundario NAO vira industria")
_velha = PASTA / "seg_velha.xlsx"
_wbv = openpyxl.Workbook(); _wbv.active.title = "SEGMENTOS"
_wbv["SEGMENTOS"].append(["SEGMENTO"]); _wbv["SEGMENTOS"].append(["OUTROS"])
_wa = _wbv.create_sheet("AJUSTE_MANUAL"); _wa.append(["COD_CLIENTE", "LOJA", "SEGMENTO"])
_wa.append(["000123", "", "DISTRIBUIDOR"]); _wbv.save(_velha)
_ctxv = cb.Contexto(caminho_cache=cache_arq, caminho_segmentacao=_velha)
checar(_ctxv.ajustes.get(("000123", "")) and _ctxv.ajustes[("000123", "")][0] == cb.DISTRIBUIDOR
       and "INDÚSTRIA" in [r[0] for r in openpyxl.load_workbook(_velha)["SEGMENTOS"].iter_rows(values_only=True)],
       "a tabela antiga e refeita com os 8 e o ajuste manual fica (DISTRIBUIDOR -> DISTRIBUIDOR DE BATERIAS)")

if TABELA.exists() and (AQUI / "SISTEMA BAP" / "Consulta CNAE" / "cache_cnae.json").exists():
    import base_cliente as bcli                              # noqa: E402
    bcli.TEMPO_COORDENADAS = 0      # o teste nao vai a internet
    import meta_nucleo as mn                                 # noqa: E402
    import planner_nucleo as nu                              # noqa: E402
    _base = PASTA / "BASE_CLIENTE_seg.xlsx"
    bcli.gerar_base_cliente(TABELA, _base)
    _wb = openpyxl.load_workbook(_base, read_only=True)
    checar(_wb.sheetnames[:2] == ["BASE_CLIENTE", "EXCLUIDOS"],
           f"a BASE_CLIENTE tem a aba EXCLUIDOS logo depois: {_wb.sheetnames}")
    _cab = list(next(_wb["BASE_CLIENTE"].iter_rows(values_only=True)))
    _segs_base = {r[_cab.index("SEGMENTO")] for r in
                  _wb["BASE_CLIENTE"].iter_rows(min_row=2, values_only=True)}
    checar(_segs_base <= set(cb.NOMES_SEGMENTOS),
           f"na BASE_CLIENTE so os 8 segmentos ({len(_segs_base)} presentes)")
    _cabx = list(next(_wb["EXCLUIDOS"].iter_rows(values_only=True)))
    checar(_cabx[-2:] == ["MOTIVO_EXCLUSAO", "SEGMENTO_SUGERIDO"],
           "a aba EXCLUIDOS traz o MOTIVO e a SUGESTAO")
    _n_base = _wb["BASE_CLIENTE"].max_row - 1
    _n_exc = _wb["EXCLUIDOS"].max_row - 1
    _wb.close()
    _wt = openpyxl.load_workbook(TABELA, read_only=True)
    _it = _wt["dClientesBap"].iter_rows(values_only=True)
    _ct = list(next(_it))
    _ic, _il = _ct.index("A1_COD"), _ct.index("A1_LOJA")
    _n_tab = len({(bcli.texto(r[_ic]).zfill(6), bcli.texto(r[_il])) for r in _it
                  if r[_ic] is not None})
    _wt.close()
    checar(_n_base + _n_exc == _n_tab,
           f"ninguem some: {_n_base} na base + {_n_exc} excluidos = {_n_tab} na TABELA")

    _clis = nu.ler_base_cliente(_base, usar_cache=False)
    _cfg = nu.carregar_config(AQUI / "planner_config.json") \
        if (AQUI / "planner_config.json").exists() else None
    if _cfg and _cfg.get("zonas"):
        # (21/10) a MECANICA da rota (o mes inteiro): o passado guardado
        # (recalcular nao reescreve o passado) e testado no smoke_relatorios
        nu.REESCREVER_PASSADO[0] = True
        nu.aplicar_parametros(_cfg, _clis)
        _pl = PASTA / "PLANNER_SEG.xlsx"
        nu.gravar_planner(_cfg, _clis, _pl)

        # ---- 07/10: AGENDA DE CIDADES dos supervisores (modelo e volta)
        import agenda_cidades as ac                          # noqa: E402
        _ma = ac.modelo(_cfg, _clis, PASTA / ac.nome_do_modelo(_cfg["mes"]))
        _wa = openpyxl.load_workbook(_ma)
        _abas = [w for w in _wa.worksheets
                 if str(w.cell(3, 1).value or "").startswith(ac.MARCA)]
        _ativos = [p_ for p_ in nu.vendedores_ativos(_cfg)
                   if nu.clientes_do_vendedor(_cfg, _clis,
                                              p_.get("cod_protheus"))]
        checar(len(_abas) == len(_ativos) and _abas and
               _abas[0].data_validations.dataValidation and
               _wa["LISTAS"].sheet_state == "hidden",
               "Modelo de agenda: uma aba por vendedor ativo, lista de "
               "cidades em cada dia (aba LISTAS escondida)")
        _wsa = _abas[0]
        _cod_a = str(_wsa.cell(3, 1).value).split("|")[1]
        _cids_a = ac.cidades_da_carteira(_cfg, _clis, _cod_a)
        _dias_ok = [d_[0] for d_ in nu.dias_do_mes(
            _cfg["mes"], _cfg.get("feriados") or [], False)]
        _preench = 0
        for _row in _wsa.iter_rows(min_row=5, min_col=2, max_col=6):
            for _c in _row:
                _mt = ac._DATA.match(str(_c.value or ""))
                if _mt and _preench < 3 and int(_mt.group(2)) == int(
                        _cfg["mes"][5:7]) and any(
                        d_.day == int(_mt.group(1)) for d_ in _dias_ok):
                    _wsa.cell(_c.row + 1, _c.column, _cids_a[0][0])
                    _wsa.cell(_c.row + 2, _c.column, "Cidade Que Nao Existe")
                    _preench += 1
        _wa.save(PASTA / "AGENDA_PREENCHIDA.xlsx")
        _cal, _av, _rs = ac.ler(_cfg, _clis, PASTA / "AGENDA_PREENCHIDA.xlsx")
        checar(list(_cal) == [_cod_a] and len(_cal[_cod_a]) == _preench
               and all(v_ == [_cids_a[0][1]] for v_ in _cal[_cod_a].values())
               and len(_av) == _preench,
               f"Agenda: lê só quem preencheu ({_preench} dias) e avisa a "
               f"cidade fora da carteira")
        _cfg_a = json.loads(json.dumps(_cfg))
        ac.aplicar(_cfg_a, _cal)
        checar(nu.liberadas_do_vendedor(_cfg_a, _cod_a) == set(_cal[_cod_a]),
               "Agenda importada: as datas do arquivo ficam liberadas da "
               "regra da cidade base")
        # a mecanica da agenda sozinha (a regra da cidade base e testada
        # embaixo): sem os dias da base
        _cfg_a["parametros"]["dias_cidade_base"] = 0
        _lin_a = nu.gerar_rota(_cfg_a, _clis)
        _da = {l_["CHAVE_CLIENTE"] for l_ in _lin_a
               if l_["COD_VENDEDOR"] == _cod_a}
        checar(len(_da) == len(nu.clientes_do_vendedor(_cfg_a, _clis, _cod_a))
               and all(l_["DATA"].isoformat() in _cal[_cod_a]
                       for l_ in _lin_a if l_["COD_VENDEDOR"] == _cod_a
                       and nu.chave_da_cidade(l_["UF"], l_["CIDADE"])
                       == _cids_a[0][1] and l_["DATA"].weekday() < 5),
               "Agenda: a cidade escolhida vai nos dias dela e nenhum "
               "cliente do vendedor fica de fora")
        # (17/10) A CIDADE BASE NOS 10 PRIMEIROS DIAS UTEIS E A VISITA SEMANAL
        _cfg_b = json.loads(json.dumps(_cfg))
        _cfg_b["parametros"].update({"dias_cidade_base": 10,
                                     "raio_base_km": 50, "top_semanal": 30,
                                     "raio_capital_km": 50})
        nu.IGNORAR_ROTA_FIXA[0] = True
        try:
            _lin_b = nu.gerar_rota(_cfg_b, _clis)
        finally:
            nu.IGNORAR_ROTA_FIXA[0] = False
        _dias_b = nu.dias_do_mes(_cfg_b["mes"], _cfg_b.get("feriados") or [],
                                 True)
        _restr = nu.dias_da_cidade_base(_dias_b, _cfg_b["parametros"])
        _vend_b = {p_["cod_protheus"]: p_ for p_ in nu.vendedores(_cfg_b)}
        _fora_b = 0
        for _l in _lin_b:
            _nb = nu.regiao_da_base(_vend_b.get(_l["COD_VENDEDOR"], {}),
                                    _cfg_b["parametros"])
            if _nb and _l["DATA"] in _restr and not _nb(_l) and \
                    _l["DATA"].isoformat() not in nu.liberadas_do_vendedor(
                        _cfg_b, _l["COD_VENDEDOR"]):
                _fora_b += 1
        checar(len(_restr) == min(10, len([d_ for d_ in _dias_b
                                           if not d_[3]])) and _fora_b == 0,
               f"Cidade base: nos {len(_restr)} primeiros dias uteis so a "
               f"regiao da base ({_fora_b} visita(s) fora)")
        _sem_b = defaultdict(set)
        _semanais = set()
        for _l in _lin_b:
            if _l.get("VISITA_SEMANAL") == "SIM":
                _semanais.add((_l["COD_VENDEDOR"], _l["CHAVE_CLIENTE"]))
                _sem_b[(_l["COD_VENDEDOR"], _l["CHAVE_CLIENTE"])].add(
                    _l["SEMANA"])
        _cheias = {f"Semana {w_}" for w_ in {d_[2] for d_ in _dias_b}
                   if sum(1 for d_ in _dias_b if d_[2] == w_
                          and not d_[3]) >= 5}
        _cobre = sum(len(_sem_b[k_] & _cheias) for k_ in _semanais)
        _pede = len(_semanais) * len(_cheias)
        checar(not _semanais or _cobre >= 0.8 * _pede,
               f"Visita semanal (top 30 / limite, vendedor da capital): "
               f"{len(_semanais)} cliente(s), {_cobre}/{_pede} semanas cheias "
               f"com visita")
        _rep_b = Counter((_l["COD_VENDEDOR"], _l["CHAVE_CLIENTE"], _l["SEMANA"])
                         for _l in _lin_b)
        _sab_b = {d_[0] for d_ in _dias_b if d_[3]}
        _carga_b = Counter((_l["COD_VENDEDOR"], _l["DATA"]) for _l in _lin_b
                           if _l["DATA"] not in _sab_b)
        checar(max(_rep_b.values(), default=1) == 1 and all(
            n_ <= nu.teto_do_dia(12, d_, _cfg_b["parametros"])
            for (_v, d_), n_ in _carga_b.items()
            if int(_cfg_b["parametros"].get("visitas_por_dia") or 0) == 12),
               "Com as regras novas: nunca 2x na semana e o teto do dia vale")
        _dados = mn.ler_planner(_pl)
        checar(all(c["segmento"] in cb.NOMES_SEGMENTOS for c in _dados["clientes"]),
               "o PLANNER leva o SEGMENTO de cada cliente para a meta")
        _par = mn.parametros_novos()
        _res = mn.calcular(_dados, _par)
        _comp = _dados["competencia"] or "2026-10"
        _mapa = mn.segmentos_da_base(_base)
        _real = mn.ler_realizado(TABELA, "2026-09", segmento_do_cliente=_mapa)
        _tot = sum(c["liquido"] for c in _real["clientes"].values())
        _por_seg = defaultdict_float = {}
        for _c in _real["clientes"].values():
            _por_seg[_c["segmento"]] = _por_seg.get(_c["segmento"], 0) + _c["liquido"]
        checar(abs(sum(_por_seg.values()) - _tot) < 0.01,
               f"o realizado de set/26 se reparte pelos segmentos sem sobra "
               f"({len(_por_seg)} grupos, R$ {_tot:,.2f})")
        _soma_v = sum(v["liquido"] for (sg, cv), v in
                      _real["por_vendedor_segmento"].items())
        checar(abs(_soma_v - sum(v["liquido"] for v in _real["por_vendedor"].values())) < 0.01,
               "e o 'quem vendeu' por segmento fecha com o do vendedor")
        _seg = max((x for x in _por_seg if x in cb.NOMES_SEGMENTOS),
                   key=lambda x: _por_seg[x])
        _ac = mn.acompanhar(mn.resultado_do_segmento(_res, _seg),
                            mn.realizado_do_segmento(_real, _seg), par=_par)
        _real_v = sum(l["realizado"] for l in _ac["recortes"]["vendedor"])
        _esper = sum(v["liquido"] for (sg, cv), v in
                     _real["por_vendedor_segmento"].items() if sg == _seg)
        checar(abs(_real_v - _esper) < 0.01,
               f"acompanhamento filtrado em {_seg}: o realizado dos vendedores "
               f"e o que eles venderam no segmento (R$ {_esper:,.2f})")
        checar([l["chave"] for l in _ac["recortes"]["segmento"]
                if not l.get("fora_do_planner")] in ([_seg], []),
               "e a aba SEGMENTO so tem ele")
        _ac_todo = mn.acompanhar(_res, _real, par=_par)
        checar({l["chave"] for l in _ac_todo["recortes"]["segmento"]}
               >= set(x for x in _por_seg if x in cb.NOMES_SEGMENTOS),
               "sem filtro, o acompanhamento abre por SEGMENTO")
    else:
        print("  (sem planner_config.json - pulando o PLANNER e a meta)")
else:
    print("  (sem TABELA_BAP ou sem cache de CNAE - pulando a parte com dados)")

# --------------------------------------------------------------------------
print("\n[7] TABELA_BAP SO COMO SAIDA: A FOTOGRAFIA E AS FORMULAS EM PYTHON")
import dados_bap as db                                       # noqa: E402
import xlsx_rapido as xr                                     # noqa: E402
import os as _os7                                            # noqa: E402
from datetime import time as _t7, timedelta as _td7          # noqa: E402
_p7 = PASTA.parent / "foto7"
_p7.mkdir(exist_ok=True)
# (a) ida e volta do CSV com todos os tipos
_lin7 = [("COD", "VALOR", "QUANDO", None, "MISTA"),
         ("000123", 1, datetime(2026, 11, 5, 10, 11, 12, 346000), None, 1.5),
         ("~til", 2.25, datetime(2026, 1, 1), None, "texto"),
         ("", -3, None, None, True),
         (None, 10 ** 15, datetime(1900, 3, 1), None, _t7(10, 30)),
         ("a;b\n\"c\"", 0.30000000000000004, datetime(2026, 12, 31, 23, 59, 59),
          None, _td7(days=2, seconds=5)),
         ("0", 0, None, None, None)]
db.gravar_csv(_p7 / "t.csv.gz", _lin7, 5)
_vol7 = db.ler_csv(_p7 / "t.csv.gz", 5)
checar(len(_vol7) == len(_lin7) and all(
    db.mesmo_valor(a, b) for x, y in zip(_lin7, _vol7) for a, b in zip(x, y)),
       "fotografia: ida e volta do .csv.gz com o tipo de cada celula (texto "
       "com zero a esquerda, int x float, data, hora, duracao, vazio x \"\")")
checar(db.como_volta_gravado(46.0) == 46 and type(db.como_volta_gravado(46.0)) is int
       and db.como_volta_gravado(0.1 + 0.2) == 0.3
       and db.como_volta_gravado(46160, "d") == datetime(2026, 5, 18)
       and db.como_volta_gravado("") is None
       and db.como_volta_gravado("a\r\nb") == "a\nb",
       "o valor como volta depois de gravado (openpyxl 16 algarismos, data "
       "pelo formato, texto vazio, CR)")
checar(db.modelo_da_formula('=BD12-(BV12)', 12) == "=BD#-(BV#)"
       and db.formula_do_modelo('=SUMIFS(T!$M:$M,T!$B:$B,$I#,T!$P:$P,">0")', 7)
       == '=SUMIFS(T!$M:$M,T!$B:$B,$I7,T!$P:$P,">0")'
       and db.modelo_da_formula('=VLOOKUP(A2,#REF!,2,0)', 2) is None,
       "modelo da formula com # no lugar da linha (e #REF! fica de fora)")
# (b) com a TABELA_BAP real: fotografia, leitor hibrido e formulas = Excel
if TABELA.exists():
    _rel7 = _p7 / "RELATORIOS"
    _rel7.mkdir(exist_ok=True)
    _tab7 = _rel7 / "TABELA_BAP.xlsx"
    shutil.copy2(TABELA, _tab7)
    _fs7 = db.formulas_do_arquivo(_tab7)
    _estr7 = {}
    for _a in db.ABAS_DADOS:
        _f = _fs7.get(_a, {})
        _estr7[_a] = {"formulas": db.estrutura_de_formulas(_f), "datas": {},
                      "calculadas": sorted({c for (r, c), v in _f.items()
                                            if r <= 41 and isinstance(v, str)})}
    _abas7, _est7, _conf7 = db.fotografia_da_completa(_tab7, _estr7, True)
    checar(_conf7["celulas"] > 60000 and _conf7["diferencas"] == 0,
           f"formulas em Python = valores do Excel: {_conf7['celulas']} "
           f"celulas, {_conf7['diferencas']} diferenca(s) {_conf7['erro']}")
    db.gravar_fotografia(db.pasta_dados(_tab7), _abas7, _est7,
                         db.base_do_xlsx(_tab7), "completa",
                         ordem=list(_fs7))
    checar(db.fotografia_para(_tab7) is not None, "a fotografia vale para a "
           "TABELA_BAP de onde saiu")
    _os7.environ["BAP_SEM_FOTOGRAFIA"] = "1"
    _w0 = xr.abrir(_tab7)
    _os7.environ.pop("BAP_SEM_FOTOGRAFIA")
    _w1 = xr.abrir(_tab7)
    _ig7 = type(_w1).__name__ == "_LivroHibrido" and _w0.sheetnames == _w1.sheetnames
    for _n in _w0.sheetnames:
        _x, _y = list(_w0[_n].iter_rows(values_only=True)), list(_w1[_n].iter_rows(values_only=True))
        _ig7 = _ig7 and len(_x) == len(_y) and _w0[_n].max_column == _w1[_n].max_column \
            and all(db.mesmo_valor(a, b) for p, q in zip(_x, _y) for a, b in zip(p, q))
    _w0.close()
    _w1.close()
    checar(_ig7, "leitor hibrido = .xlsx em todas as abas (as 7 da fotografia, "
           "o cadastro do .xlsx), valor e tipo")
    # a TABELA_BAP salva por fora: a fotografia deixa de valer
    _velha = db.fotografia_para(_tab7)
    import zipfile as _zf7
    _tmp7 = _rel7 / "x.xlsx"
    with _zf7.ZipFile(_tab7) as _zi, _zf7.ZipFile(_tmp7, "w", _zf7.ZIP_DEFLATED) as _zo:
        _alvo = db.abas_do_zip(_zi)["ftNCC"]
        for _it in _zi.infolist():
            _d = _zi.read(_it.filename)
            if _it.filename == _alvo:
                _d = _d.replace(b"</sheetData>", b"</sheetData>", 1) + b" "
            _zo.writestr(_it, _d)
    _os7.replace(_tmp7, _tab7)
    checar(_velha is not None and db.fotografia_para(_tab7) is None,
           "TABELA_BAP salva por fora (aba de dados mudou): a fotografia "
           "deixa de valer e o leitor volta ao .xlsx")
    # a escolha da rodada
    shutil.copy2(TABELA, _tab7)

    class _Args7:
        completa = False
        simular = False
    _arm7 = ba.ArmazenamentoLocal()
    _arm7.planilha = _tab7
    _r1 = ba.escolher_rodada(_Args7, _arm7)
    _Args7.completa = True
    _r2 = ba.escolher_rodada(_Args7, _arm7)
    _Args7.completa = False
    _e7 = db.ler_estado(db.pasta_dados(_tab7))
    _e7["completa_em"] = "2026-01-01T07:00:00"
    (db.pasta_dados(_tab7) / db.ARQ_ESTADO).write_text(json.dumps(_e7), "utf-8")
    db._VALIDA_CACHE.clear()                                # noqa: SLF001
    _r3 = ba.escolher_rodada(_Args7, _arm7)
    _e7["completa_em"] = datetime.now().isoformat(timespec="seconds")
    _e7["conferencia_excel"] = {"celulas": 10, "diferencas": 2, "exemplos": []}
    (db.pasta_dados(_tab7) / db.ARQ_ESTADO).write_text(json.dumps(_e7), "utf-8")
    db._VALIDA_CACHE.clear()                                # noqa: SLF001
    _r4 = ba.escolher_rodada(_Args7, _arm7)
    checar(_r4[0] == "completa", "a completa do dia achou diferenca Python x "
           f"Excel: as rodadas seguintes sao completas ({_r4[1]})")
    checar(_r1[0] == "rapida" and _r2[0] == "completa" and _r3[0] == "completa",
           f"rodada: rapida com fotografia do dia ({_r1[1]}); completa com "
           f"--completa e na 1a do dia ({_r3[1]})")
else:
    print("  (sem TABELA_BAP nesta maquina - pulando a fotografia real)")

# (c) a rodada rapida num livro pequeno: mesma gravacao, formula clonada nas
# linhas novas, data pelo formato e as contas = LibreOffice (quando houver)
from openpyxl.styles import NamedStyle as _NS7                # noqa: E402,F401
_rel8 = _p7 / "mini" / "RELATORIOS"
_rel8.mkdir(parents=True, exist_ok=True)
_tab8 = _rel8 / "TABELA_BAP.xlsx"
_wb8 = openpyxl.Workbook()
_wb8.active.title = "ftEstoqueBap"
_ws8 = _wb8["ftEstoqueBap"]
_ws8.append(["B2_FILIAL", "ID_PRODUTO", "CONCAT", "B2_FILIAL_ORIGINAL", "B2_LOCAL",
             "B2_COD", "B2_QATU", "DATA_X"])
for _i in range(2, 6):
    _ws8.append([f"=_xlfn.CONCAT(4,D{_i})",
                 f'=IFERROR(_xlfn.XLOOKUP(F{_i},ProdutosBAP!C:C,ProdutosBAP!A:A,,0),"")',
                 f"=_xlfn.CONCAT(D{_i},F{_i})", "0101001", "01", f"P{_i}", _i * 1.5, None])
    _ws8.cell(_i, 8).number_format = "dd/mm/yyyy"
_wp8 = _wb8.create_sheet("ProdutosBAP")
_wp8.append(["ID_PRODUTO", "FORNECEDOR", "Cód. Produto", "ID_PRODUTO_SEM_ESPACO"])
for _i in range(2, 9):
    _wp8.append([f"ID{_i}", "980 - BAP", f"p{_i}", f'=SUBSTITUTE(A{_i}," ","")'])
_wb8.save(_tab8)
_cfg8 = {"id": "estoque", "aba_excel": "ftEstoqueBap", "linha_cabecalho": 1,
         "linhas_a_mais": "limpar", "mapa_colunas": {"B2_FILIAL": "B2_FILIAL_ORIGINAL"}}
import pandas as _pd8                                         # noqa: E402
_df8 = _pd8.DataFrame({"B2_FILIAL": ["0101001"] * 7, "B2_LOCAL": ["01"] * 7,
                       "B2_COD": [f"P{i}" for i in range(2, 9)],
                       "B2_QATU": [1, 2.5, 3, 4, 5, 6, 7],
                       "DATA_X": [46160, 46161, None, None, 46162, 46163, 46164]})
# base "completa": a fotografia do livro pequeno, do jeito da rodada completa
_wf8 = openpyxl.load_workbook(_tab8)
_est8 = db.estrutura_do_livro(_wf8, ["ftEstoqueBap"])
_wf8.close()
_estr8 = {"ftEstoqueBap": _est8["ftEstoqueBap"], "_ordem": _est8["_ordem"]}
_abas8, _ef8, _ = db.fotografia_da_completa(_tab8, _estr8, False)
db.gravar_fotografia(db.pasta_dados(_tab8), _abas8, _ef8, db.base_do_xlsx(_tab8),
                     "completa", ordem=_est8["_ordem"])
# caminho completo: a gravacao de sempre no arquivo
_copia8 = _rel8.parent / "copia.xlsx"
shutil.copy2(_tab8, _copia8)
ba.gravar_planilha(_copia8, {"estoque": _df8}, {"estoque": _cfg8})
_salvo8 = db.linhas_do_xlsx(_copia8, ["ftEstoqueBap"])["ftEstoqueBap"][0]
_fc8 = db.formulas_do_arquivo(_copia8, ["ftEstoqueBap"])["ftEstoqueBap"]
# caminho rapido
# o backup da fotografia vai para o temp do teste, nunca para o
# BKP_RELATORIOS_AUXILIARES de verdade (entraria no rodizio)
_bkp8 = ba.PASTA_BACKUPS
ba.PASTA_BACKUPS = _rel8.parent / "bkp"
try:
    _res8, _info8 = ba.rodada_rapida(_tab8, {"estoque": _df8},
                                     {"estoque": _cfg8})
finally:
    ba.PASTA_BACKUPS = _bkp8
_f8 = db.fotografia_para(_tab8)
_rap8 = db.ler_aba(db.pasta_dados(_tab8), _f8, "ftEstoqueBap")
_dado_ok = all(db.mesmo_valor(_salvo8[r][c], _rap8[r][c])
               for r in range(len(_salvo8)) for c in range(len(_salvo8[0]))
               if (r + 1, c + 1) not in _fc8) and len(_salvo8) == len(_rap8)
checar(_dado_ok and db.celulas_de_formula(_f8["abas"]["ftEstoqueBap"]["formulas"]) == _fc8
       and len(_fc8) == 21,
       "rodada rapida x completa (livro pequeno): mesmos dados, formula "
       "clonada nas 3 linhas novas")
checar(_rap8[1][7] == datetime(2026, 5, 18) and _rap8[6][7] == datetime(2026, 5, 21)
       and _rap8[1][0] == "40101001" and _rap8[7][2] == "0101001P8"
       and _rap8[1][1] == "ID2" and _rap8[7][1] == "ID8",
       "numero em celula com formato de data volta data (a linha nova herda "
       "o formato da linha modelo); CONCAT e XLOOKUP calculados")
_lo8 = shutil.which("soffice") or shutil.which("libreoffice")
if _lo8:
    subprocess.run([_lo8, "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(_rel8.parent / "lo"), str(_copia8)],
                   capture_output=True, timeout=300)
    _arq_lo8 = _rel8.parent / "lo" / "copia.xlsx"
    if _arq_lo8.exists():
        _l8 = db.linhas_do_xlsx(_arq_lo8, ["ftEstoqueBap"])["ftEstoqueBap"][0]
        checar(all(db.mesmo_valor(_l8[r - 1][c - 1], _rap8[r - 1][c - 1])
                   for (r, c) in _fc8 if c != 2),
               "CONCAT calculado em Python = LibreOffice (o XLOOKUP o "
               "LibreOffice 24.2 nao tem)")

# --------------------------------------------------------------------------
print("\n[8] ARQUIVO EM ABERTO: O AVISO CONTINUAR / CANCELAR (05/11)")
import aviso_arquivo as av8                                  # noqa: E402
from pathlib import Path as _P8                              # noqa: E402
_seq8 = iter([True, False])
checar(not av8.em_uso("x.xlsx", intervalo=0.01, olhar=lambda _p: next(_seq8)),
       "travado so por um instante (OneDrive): nao conta como aberto")
checar(av8.em_uso("x.xlsx", intervalo=0.01, olhar=lambda _p: True),
       "travado nas 3 tentativas: em aberto")
_resp8 = iter(["continuar", "continuar", "continuar"])
_est8 = iter([True, True, True, False])
_vez8 = []
checar(av8.aguardar_livre(_P8("SOLICITACAO_BAP.xlsx"), "teste",
                          verificar=lambda _p: next(_est8),
                          pergunta=lambda n, e: _vez8.append(n) or next(_resp8))
       == "livre" and len(_vez8) == 3,
       "Continuar com o arquivo ainda aberto: o aviso volta; livre: segue")
try:
    av8.aguardar_livre(_P8("ESTOQUE_BAP.xlsx"), "teste", verificar=lambda _p: True,
                       pergunta=lambda n, e: "cancelar")
    checar(False, "Cancelar interrompe")
except av8.Cancelado as _c8:
    checar(not isinstance(_c8, Exception) and _c8.arquivo == "ESTOQUE_BAP.xlsx",
           "Cancelar interrompe a rodada (nenhum 'except Exception' engole)")
checar(av8.aguardar_livre(_P8("BASE_CLIENTE.xlsx"), "teste", verificar=lambda _p: True,
                          pergunta=lambda n, e: "tempo") == "pular"
       and av8.aguardar_livre(_P8("BASE_CLIENTE.xlsx"), "teste",
                              verificar=lambda _p: True,
                              pergunta=lambda n, e: "sem_tela") == "pular",
       "ninguem respondeu / sem tela: pula so o passo")
checar(av8.mensagem("X.xlsx") == "Arquivo X.xlsx em aberto. Feche e clique em "
       "Continuar." and av8.TITULO == "Automação BAP"
       and ba.ESPERA_POPUP_ARQUIVO == 15 * 60 and ba.TIMEOUT_RECALCULO == 120,
       "texto e titulo do aviso; espera 15 min; recalculo 120 s")
if _os7.environ.get("DISPLAY"):
    import time as _t8
    _i8 = _t8.time()
    checar(av8.perguntar("TESTE.xlsx", 1) == "tempo" and _t8.time() - _i8 < 5,
           "o aviso de verdade (Tk) fecha sozinho quando a espera acaba")
# o Excel preso: so o PID que o script anotou
_run8, _win8, _tmp8 = ba.subprocess.run, ba.e_windows, ba.PASTA_TEMP
_ch8 = []


def _falso8(cmd, **kw):
    _ch8.append(list(cmd))
    if cmd[0] == "taskkill":
        return subprocess.CompletedProcess(cmd, 0, "", "")
    _P8(cmd[3]).write_text("777", encoding="utf-8")
    raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))


ba.PASTA_TEMP = PASTA.parent / "recalc8"
ba.PASTA_TEMP.mkdir(exist_ok=True)
(ba.PASTA_TEMP / "A.xlsx").write_bytes(b"x")
(ba.PASTA_TEMP / "~$A.xlsx").write_bytes(b"x")
ba.subprocess.run, ba.e_windows = _falso8, (lambda: True)
try:
    _r8 = ba.recalcular_com_excel(ba.PASTA_TEMP / "A.xlsx", "A.xlsx")
    _dono8 = (ba.PASTA_TEMP / "~$A.xlsx").exists()
finally:
    ba.subprocess.run, ba.e_windows, ba.PASTA_TEMP = _run8, _win8, _tmp8
checar(_r8 is False and [c for c in _ch8 if c[0] == "taskkill"]
       == [["taskkill", "/PID", "777", "/F"]] and not _dono8,
       "recalculo preso: encerra SO o EXCEL.EXE que o robo abriu (PID anotado)"
       " e apaga o ~$ solto que ele deixou")
(PASTA.parent / "D8.xlsx").write_bytes(b"x")
(PASTA.parent / "~$D8.xlsx").write_bytes(b"x")
checar(not av8.em_uso(PASTA.parent / "D8.xlsx", intervalo=0.01),
       "~$ solto (Excel que caiu) nao conta como aberto: o aviso nao fica "
       "voltando")
import bap_dados as bd8                                      # noqa: E402
_ab8 = []


def _abrir8(p, **k):
    _ab8.append(p)
    if len(_ab8) == 1:
        raise PermissionError(13, "Permission denied")
    return "ok"


(PASTA.parent / "S8.xlsx").write_bytes(b"x")
checar(bd8._abrir_mesmo_aberto(PASTA.parent / "S8.xlsx", _abrir8, intervalo=0.01)
       == "ok" and _P8(_ab8[1]) != PASTA.parent / "S8.xlsx",
       "bap_dados: SOLICITACAO_BAP aberta no Excel (Permission denied) - le "
       "uma copia")

# --------------------------------------------------------------------------
print("\n[9] SALVAR E FECHAR NO AVISO DE ARQUIVO EM ABERTO (05/11)")
_w9 = (av8.WINDOWS, av8._com_com_espera, av8._listar_excel, av8._matar,
       av8.ESPERA_SOLTAR)
checar(av8._automacao('"EXCEL.EXE" /automation -Embedding')
       and not av8._automacao('"EXCEL.EXE" "C:\\x\\planilha.xlsx"'),
       "so o Excel aberto por automacao (/automation -Embedding) e "
       "candidato a ser encerrado")
_mortos9 = []
av8.WINDOWS, av8.ESPERA_SOLTAR = True, 0
av8._matar = lambda pid: _mortos9.append(pid) or True
av8._com_com_espera = lambda alvo, log=None: {"livros": 0, "fechados": 0}
_arq9 = PASTA.parent / "S9.xlsx"
_arq9.write_bytes(b"x")
try:
    av8._listar_excel = lambda: ([4242], [777], "")
    _r9 = av8.salvar_e_fechar(_arq9, verificar=lambda _p: 4242 not in _mortos9)
    checar(_r9["livre"] and _mortos9 == [4242],
           "Salvar e fechar: encerra SO o Excel sem janela que segurava o "
           "arquivo (o recalculo que sobrou); o Excel com janela fica")
    _mortos9.clear()
    av8._listar_excel = lambda: ([], [777], "")
    _r9 = av8.salvar_e_fechar(_arq9, verificar=lambda _p: True)
    checar(not _r9["livre"] and not _mortos9
           and _r9["mensagem"] == av8.MSG_EXCEL_VISIVEL,
           "arquivo num Excel COM janela: nao encerra; o aviso pede para "
           "salvar e fechar por la")
    av8._listar_excel = lambda: ([], [], "")
    _r9 = av8.salvar_e_fechar(_arq9, verificar=lambda _p: True)
    checar(not _r9["livre"] and _r9["mensagem"] == av8.MSG_OUTRO_PROGRAMA,
           "sem Excel segurando: o aviso fala do OneDrive / outro programa")
    av8._com_com_espera = lambda alvo, log=None: {"livros": 1, "fechados": 0,
                                                  "nao_salvou": True}
    av8._listar_excel = lambda: ([4242], [], "")
    _mortos9.clear()
    _r9 = av8.salvar_e_fechar(_arq9, verificar=lambda _p: True)
    checar(not _r9["livre"] and not _mortos9 and _r9["mensagem"] ==
           "Não consegui salvar S9.xlsx no Excel. Salve e feche por lá.",
           "o Excel nao salvou o livro: nao fecha e nao encerra nada")
finally:
    (av8.WINDOWS, av8._com_com_espera, av8._listar_excel, av8._matar,
     av8.ESPERA_SOLTAR) = _w9
_ro9 = PASTA.parent / "RO9.xlsx"
_ro9.write_bytes(b"x")
_os7.chmod(_ro9, 0o444)


def _negar9(*_a, **_k):
    raise PermissionError(13, "Permission denied")


av8.open = _negar9
try:
    checar(not av8.travado(_ro9) and av8.travado(_arq9),
           "arquivo marcado somente leitura nao conta como 'em aberto' (era "
           "um falso aviso que o Continuar nunca resolvia)")
finally:
    del av8.open
_os7.chmod(_ro9, 0o644)
_seq9 = iter(["fechar", "continuar"])
_ex9 = []
_n9 = {"n": 0}


def _v9(_p):
    _n9["n"] += 1
    return _n9["n"] < 3


av8.WINDOWS = False
try:
    checar(av8.aguardar_livre(_arq9, "teste", verificar=_v9,
                              pergunta=lambda n, e, x=None: _ex9.append(x)
                              or next(_seq9)) == "livre"
           and _ex9 == [None, av8.MSG_SEM_SUPORTE],
           "Salvar e fechar sem Windows: avisa que nao conseguiu e o aviso "
           "volta; Continuar segue")
finally:
    av8.WINDOWS = _w9[0]

shutil.rmtree(PASTA, ignore_errors=True)
print("\n" + "=" * 62)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for f in falhas:
        print("  - " + f)
    sys.exit(1)
print("OK - Farol, pos-venda, TABELA_BAP, BAP Central, CNAE, os 8 segmentos "
      "e a fotografia da TABELA_BAP.")
