# -*- coding: utf-8 -*-
"""
AGENDA DE CIDADES DOS SUPERVISORES (07/10)

O Planner gera a rota sozinho, com as regras de sempre. A agenda e uma
AJUDA: o supervisor escolhe, para cada dia do mes, ate 2 CIDADES da
carteira do vendedor (lista em cada celula). Na hora de RECALCULAR ou de
EXPORTAR o PLANNER, o programa pergunta "Importar agenda?" e, com o
arquivo, cada vendedor preenchido vai para o calendario da aba ROTA POR
CIDADE. Quem ficou em branco segue o algoritmo normal.

    modelo(cfg, clientes, caminho)   o Excel do mes (uma aba por vendedor
                                     ativo, lista de cidades em cada dia)
    ler(cfg, clientes, caminho)      {cod: {data ISO: [chave da cidade]}}
                                     + os avisos (o que nao deu para usar)
    aplicar(cfg, calendario)         grava no calendario do Planner

Nao usa caminho absoluto: o arquivo e escolhido na tela.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path

import planner_nucleo as nu

VERDE_ESC = "2F7D32"
CINZA = "F3F4F2"
DIAS = ["SEGUNDA", "TERÇA", "QUARTA", "QUINTA", "SEXTA"]
MESES = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
         "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
CIDADES_POR_DIA = 2
MARCA = "AGENDA_CIDADES"          # A3 de cada aba: AGENDA_CIDADES|cod|mes


def nome_do_modelo(mes: str) -> str:
    return f"AGENDA_CIDADES_{mes}.xlsx"


def _nomes_bonitos(raiz=None) -> dict:
    """{(UF, CIDADE normalizada): 'Nome com Acento'} do arquivo de
    coordenadas (o IBGE); sem ele, o nome em Title Case."""
    import geografia as geo                              # noqa: PLC0415
    caminho = geo.caminho_das_coordenadas()
    saida = {}
    try:
        from openpyxl import load_workbook                # noqa: PLC0415
        wb = load_workbook(caminho, read_only=True, data_only=True)
        if "Cidades" in wb.sheetnames:
            it = wb["Cidades"].iter_rows(values_only=True)
            next(it, None)
            for r in it:
                if r and r[0] and r[2]:
                    saida[(geo.normalizar(r[0]), geo.normalizar(r[2]))] = \
                        str(r[2]).strip()
        wb.close()
    except Exception:                                    # noqa: BLE001
        pass
    return saida


def cidades_da_carteira(cfg, clientes, cod) -> list:
    """[(rotulo, chave UF|CIDADE, n clientes)] da maior para a menor."""
    conta = Counter()
    for c, _z in nu.clientes_do_vendedor(cfg, clientes, cod):
        if nu.texto(c.get("CIDADE")):               # cliente sem cidade fica fora da lista
            conta[(c["UF"], c["CIDADE"])] += 1
    bonito = _cache_nomes()
    nomes = Counter(nu.norm(cid) for (_uf, cid) in conta)
    saida = []
    for (uf, cid), n in sorted(conta.items(), key=lambda kv: (-kv[1], kv[0])):
        rot = bonito.get((nu.norm(uf), nu.norm(cid))) or str(cid).title()
        if nomes[nu.norm(cid)] > 1:                 # mesma cidade em 2 UFs
            rot = f"{rot} ({uf})"
        saida.append((rot, nu.chave_da_cidade(uf, cid), n))
    return saida


_NOMES = {}


def _cache_nomes():
    if not _NOMES:
        _NOMES.update(_nomes_bonitos() or {("", ""): ""})
    return _NOMES


def _semanas(ano, mes):
    d = dt.date(ano, mes, 1)
    d -= dt.timedelta(days=d.weekday())
    saida = []
    while d <= dt.date(ano, mes, 28) or d.month == mes:
        semana = [d + dt.timedelta(days=i) for i in range(5)]
        if any(x.month == mes for x in semana):
            saida.append(semana)
        d += dt.timedelta(days=7)
    return saida


# ------------------------------------------------------------------ modelo
def modelo(cfg, clientes, caminho) -> Path:
    """O Excel do mes do Planner: COMO PREENCHER, uma aba por vendedor
    ATIVO (em cada dia, 2 celulas com a lista das cidades da carteira) e a
    aba escondida LISTAS (de onde as listas saem)."""
    from openpyxl import Workbook                         # noqa: PLC0415
    from openpyxl.styles import (Alignment, Border, Font,  # noqa: PLC0415
                                 PatternFill, Side)
    from openpyxl.workbook.defined_name import DefinedName  # noqa: PLC0415
    from openpyxl.worksheet.datavalidation import DataValidation  # noqa

    mes = cfg["mes"]
    ano, m = (int(x) for x in mes.split("-")[:2])
    fer = {nu.data_de(f) for f in cfg.get("feriados") or []}
    fino = Side(style="thin", color="C9D3CC")
    cab_fill = PatternFill("solid", fgColor=VERDE_ESC)
    cinza = PatternFill("solid", fgColor=CINZA)
    teto = int(cfg["parametros"].get("visitas_por_dia") or 0)
    sexta = int(cfg["parametros"].get("visitas_sexta") or 0)
    vendedores = [p for p in nu.vendedores_ativos(cfg)
                  if nu.clientes_do_vendedor(cfg, clientes,
                                             p.get("cod_protheus"))]

    wb = Workbook()
    ins = wb.active
    ins.title = "COMO PREENCHER"
    ins.sheet_view.showGridLines = False
    texto = [
        (f"AGENDA DE CIDADES · {MESES[m]} {ano}", 16, True, VERDE_ESC),
        ("Uma aba por vendedor. Preencha só a equipe de vocês.", 11, False,
         "69736D"),
        ("", 11, False, "1E2722"),
        ("1. Em cada dia há 2 linhas: escolha na LISTA a 1ª e, se o vendedor "
         "for a duas cidades, a 2ª.", 11, False, "1E2722"),
        ("2. A lista mostra as cidades da carteira do vendedor, da maior para "
         "a menor.", 11, False, "1E2722"),
        ("3. Dia em branco: o Planner escolhe a cidade sozinho.", 11, False,
         "1E2722"),
        ("4. Cidade da carteira que não aparecer em nenhum dia entra no dia "
         "mais PERTO que tiver vaga — nenhum cliente fica de fora.", 11, False,
         "1E2722"),
        (f"5. Teto: {teto} visitas por dia" + (f" (sexta {sexta})" if sexta
                                                else "")
         + ". O que passar vai para o 1º sábado do mês.", 11, False,
         "1E2722"),
        ("6. Não mude as abas, as datas nem a ordem das linhas. Devolva o "
         "arquivo preenchido ao Alexandre.", 11, False, "1E2722"),
    ]
    for i, (t, tam, neg, cor) in enumerate(texto, start=1):
        ins.cell(i, 1, t).font = Font(size=tam, bold=neg, color=cor)
    ins.column_dimensions["A"].width = 110

    listas = wb.create_sheet("LISTAS")
    semanas = _semanas(ano, m)
    for k, p in enumerate(vendedores, start=1):
        cod = nu.texto(p.get("cod_protheus"))
        nome = nu.texto(p.get("nome"))
        cids = cidades_da_carteira(cfg, clientes, cod)
        col = k
        listas.cell(1, col, cod)
        for i, (rot, _ch, _n) in enumerate(cids, start=2):
            listas.cell(i, col, rot)
        letra = listas.cell(1, col).column_letter
        nome_lista = f"LISTA_{cod}"
        ref = f"LISTAS!${letra}$2:${letra}${max(2, len(cids) + 1)}"
        try:
            wb.defined_names[nome_lista] = DefinedName(nome_lista,
                                                       attr_text=ref)
        except TypeError:                       # openpyxl antigo
            wb.defined_names.append(DefinedName(nome_lista, attr_text=ref))

        ws = wb.create_sheet(f"{cod} {nome.split()[0] if nome else ''}"[:31])
        ws.sheet_view.showGridLines = False
        ws.merge_cells("A1:F1")
        ws.cell(1, 1, f"AGENDA DE CIDADES · {MESES[m]} {ano}").font = Font(
            size=16, bold=True, color=VERDE_ESC)
        ws.merge_cells("A2:F2")
        sup = nu.nome_supervisor(cfg, cod)
        ws.cell(2, 1, f"{nome.title()}  ·  cód. {cod}"
                + (f"  ·  supervisor {sup.title()}" if sup else "")).font = \
            Font(size=11, color="69736D")
        ws.cell(3, 1, f"{MARCA}|{cod}|{mes}").font = Font(size=1,
                                                         color="FFFFFF")
        for j, x in enumerate(["SEM."] + DIAS):
            h = ws.cell(4, 1 + j, x)
            h.font = Font(bold=True, color="FFFFFF")
            h.fill = cab_fill
            h.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[4].height = 22
        dv = DataValidation(type="list", formula1=f"={nome_lista}",
                            allow_blank=True, showDropDown=False)
        dv.error = "Escolha uma cidade da lista."
        dv.errorTitle = "Cidade"
        dv.showErrorMessage = True
        ws.add_data_validation(dv)
        r = 5
        for n, sem in enumerate(semanas, start=1):
            ws.merge_cells(start_row=r, start_column=1, end_row=r + 2,
                           end_column=1)
            a = ws.cell(r, 1, f"{n}ª")
            a.font = Font(bold=True, color="69736D")
            a.alignment = Alignment(horizontal="center", vertical="center")
            for j, d in enumerate(sem):
                fora = d.month != m or d in fer
                h = ws.cell(r, 2 + j, f"{d:%d/%m}")
                h.font = Font(size=9, bold=True,
                              color="A7B0AA" if fora else VERDE_ESC)
                h.alignment = Alignment(horizontal="left", indent=1)
                h.border = Border(left=fino, right=fino, top=fino)
                for i in (1, 2):
                    v = ws.cell(r + i, 2 + j)
                    v.alignment = Alignment(horizontal="center",
                                            vertical="center")
                    v.font = Font(size=11)
                    v.border = Border(left=fino, right=fino,
                                      bottom=fino if i == 2 else
                                      Side(style="hair", color="C9D3CC"))
                    if fora:
                        if i == 1:
                            v.value = "FERIADO" if d in fer else "—"
                            v.font = Font(size=9, color="A7B0AA")
                        v.fill = cinza
                    else:
                        dv.add(v.coordinate)
                if fora:
                    h.fill = cinza
            ws.row_dimensions[r].height = 15
            ws.row_dimensions[r + 1].height = 24
            ws.row_dimensions[r + 2].height = 24
            r += 3
        ws.column_dimensions["A"].width = 6
        for j in range(5):
            ws.column_dimensions["BCDEF"[j]].width = 26
        ws.freeze_panes = "A5"
        ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
    listas.sheet_state = "hidden"
    wb.move_sheet("LISTAS", offset=len(wb.sheetnames))
    caminho = Path(caminho)
    wb.save(caminho)
    return caminho


# -------------------------------------------------------------------- ler
_DATA = re.compile(r"^(\d{2})/(\d{2})$")


def ler(cfg, clientes, caminho):
    """
    Le o Excel preenchido. Devolve (calendario, avisos, resumo):
      calendario = {cod: {data ISO: [chave UF|CIDADE]}} (so quem preencheu)
      avisos     = o que nao entrou (cidade fora da carteira, feriado...)
      resumo     = {cod: (nome, dias preenchidos)}
    """
    from openpyxl import load_workbook                    # noqa: PLC0415
    mes = cfg["mes"]
    ano = int(mes[:4])
    dias_rota = {d[0].isoformat() for d in nu.dias_do_mes(
        mes, cfg.get("feriados") or [], True)}
    wb = load_workbook(caminho, data_only=True)
    calendario, avisos, resumo = {}, [], {}
    for ws in wb.worksheets:
        marca = str(ws.cell(3, 1).value or "")
        if not marca.startswith(MARCA + "|"):
            continue
        _m, cod, mes_arq = (marca.split("|") + ["", ""])[:3]
        p = nu.pessoa_por_codigo(cfg, cod) or {}
        nome = nu.texto(p.get("nome")) or ws.title
        if mes_arq != mes:
            avisos.append(f"{nome}: a aba é de {mes_arq}, o Planner está em "
                          f"{mes} - não importei")
            continue
        cids = {nu.norm(rot.split(" (")[0]) if " (" in rot and
                rot.endswith(")") and len(rot.split(" (")[-1]) == 3
                else nu.norm(rot): ch
                for rot, ch, _n in cidades_da_carteira(cfg, clientes, cod)}
        rotulos = {nu.norm(rot): ch for rot, ch, _n in
                   cidades_da_carteira(cfg, clientes, cod)}
        cal = {}
        for row in ws.iter_rows(min_row=5, min_col=2, max_col=6):
            for c in row:
                mt = _DATA.match(str(c.value or "").strip())
                if not mt:
                    continue
                d = dt.date(ano, int(mt.group(2)), int(mt.group(1)))
                if d.strftime("%Y-%m") != mes:
                    continue
                escolhidas = []
                for i in range(1, CIDADES_POR_DIA + 2):
                    v = ws.cell(c.row + i, c.column).value
                    if i > CIDADES_POR_DIA:
                        # a 3a linha ja e a data da semana seguinte
                        break
                    v = nu.texto(v)
                    if not v or v in ("—", "-") or nu.norm(v) == "FERIADO":
                        continue
                    ch = rotulos.get(nu.norm(v)) or cids.get(nu.norm(v))
                    if not ch:
                        avisos.append(f"{nome} {d:%d/%m}: “{v}” não é cidade "
                                      f"da carteira - ficou de fora")
                        continue
                    if ch not in escolhidas:
                        escolhidas.append(ch)
                if not escolhidas:
                    continue
                if d.isoformat() not in dias_rota:
                    avisos.append(f"{nome} {d:%d/%m}: não é dia de rota "
                                  f"(feriado/domingo) - ficou de fora")
                    continue
                cal[d.isoformat()] = escolhidas
        if cal:
            calendario[cod] = cal
            resumo[cod] = (nome, len(cal))
    wb.close()
    return calendario, avisos, resumo


def aplicar(cfg, calendario) -> int:
    """Grava o calendario de cada vendedor PREENCHIDO (quem nao veio no
    arquivo fica como estava). Devolve quantos vendedores."""
    for cod, cal in calendario.items():
        nu.gravar_rota_cidade(cfg, cod, cal)
        # (17/10) a agenda IMPORTADA e a excecao a regra da cidade base:
        # as datas que vieram no arquivo ficam como foram importadas
        nu.liberar_datas(cfg, cod, cal.keys())
    return len(calendario)
