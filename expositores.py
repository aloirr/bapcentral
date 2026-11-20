# -*- coding: utf-8 -*-
"""
EXPOSITORES - o Farol de Expositores do TRADE MARKETING (Allaiza Menezes).

Dois arquivos, sempre relativos a pasta dos programas:

  RELATORIOS/ACOMPANHAMENTO_EXPOSITORES.xlsx  (aba EXPOSITORES)
      uma linha por expositor colocado/pedido em cliente. Quem escreve e a
      assistente de Trade, pela tela do farol (duplo clique numa linha ou
      NOVO). O programa so ACRESCENTA linha nova; numa linha existente ele
      so troca os campos que a assistente mudou.

  expositores_config.json
      o CADASTRO de expositores que o Analista Comercial mantem no BAP
      Analista: NOME, CATEGORIA FOCO, QTD e FILIAL (cidade).
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARQUIVO = "ACOMPANHAMENTO_EXPOSITORES.xlsx"
ABA = "EXPOSITORES"
CADASTRO = "expositores_config.json"

STATUS = ["Solicitado", "Contrato assinado", "Entregue", "Cancelado",
          "Devolvido"]
CATEGORIAS = ["BATERIAS", "PEÇAS", "LUBRIFICANTES", "PNEUS"]
UFS = ["AM", "RR", "PA", "AP", "MA", "MT"]
# (titulo, chave, largura, tipo)  tipo: "data" | "num" | ""
COLUNAS = [
    ("CHAVE", "chave", 9, ""),
    ("DATA SOLICITAÇÃO", "data", 12, "data"),
    ("DATA ASSINATURA", "data_assinatura", 12, "data"),
    ("CÓD. CLIENTE", "cod_cliente", 12, ""),
    ("CLIENTE", "cliente", 44, ""),
    ("DESCRIÇÃO DO EXPOSITOR", "descricao", 38, ""),
    ("CATEGORIA", "categoria", 15, ""),
    ("QTD", "qtd", 7, "num"),
    ("CIDADE", "cidade", 24, ""),
    ("UF", "uf", 6, ""),
    ("STATUS", "status", 18, ""),
    ("OBSERVAÇÕES", "observacoes", 60, ""),
    ("FONTE", "fonte", 22, ""),
    ("ATUALIZADO EM", "atualizado_em", 14, "data"),
]
CAMPOS = [c[1] for c in COLUNAS]
# titulos antigos que ainda valem na leitura
APELIDOS = {"DATA": "DATA SOLICITAÇÃO", "DATA DA SOLICITAÇÃO": "DATA SOLICITAÇÃO",
            "DATA DA ASSINATURA": "DATA ASSINATURA"}


def _cabecalho(valores) -> list:
    cab = [_texto(c).upper() for c in valores]
    return [APELIDOS.get(c, c) for c in cab]


def caminho(raiz=None) -> Path:
    return Path(raiz or AQUI) / "RELATORIOS" / ARQUIVO


def categoria_da_descricao(desc: str) -> str:
    d = (desc or "").lower()
    if "bater" in d:
        return "BATERIAS"
    if "óleo" in d or "oleo" in d or "lubrific" in d:
        return "LUBRIFICANTES"
    if "pneu" in d:
        return "PNEUS"
    return "PEÇAS"


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = _texto(v)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(t[:10], fmt).date()
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------ arquivo
def criar(raiz=None, registros=()) -> Path:
    """Cria o acompanhamento (vazio ou com registros iniciais)."""
    from openpyxl import Workbook                       # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    from openpyxl.utils import get_column_letter        # noqa: PLC0415
    from openpyxl.worksheet.datavalidation import DataValidation  # noqa
    arq = caminho(raiz)
    arq.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = ABA
    verde = PatternFill("solid", fgColor="2F7D32")
    for j, (tit, _k, larg, _t) in enumerate(COLUNAS, 1):
        c = ws.cell(1, j, tit)
        c.fill = verde
        c.font = Font(bold=True, color="FFFFFF")
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = larg
    ws.freeze_panes = "A2"
    for n, reg in enumerate(registros, 2):
        _escrever(ws, n, reg)
    letra = {k: get_column_letter(j) for j, (_t, k, _l, _x) in
             enumerate(COLUNAS, 1)}
    for chave, lista in (("status", STATUS), ("categoria", CATEGORIAS),
                         ("uf", UFS)):
        dv = DataValidation(type="list",
                            formula1='"' + ",".join(lista) + '"',
                            allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{letra[chave]}2:{letra[chave]}2000")
    wb.save(arq)
    return arq


def _escrever(ws, n, reg: dict):
    for j, (_t, k, _l, tipo) in enumerate(COLUNAS, 1):
        v = reg.get(k)
        if tipo == "data":
            v = _data(v)
            if v:
                v = datetime(v.year, v.month, v.day)
                ws.cell(n, j).number_format = "dd/mm/yyyy"
        elif tipo == "num":
            try:
                v = float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                v = None
        elif v == "":
            v = None
        ws.cell(n, j).value = v


def ler(raiz=None) -> list:
    arq = caminho(raiz)
    if not arq.exists():
        return []
    from openpyxl import load_workbook                  # noqa: PLC0415
    wb = load_workbook(arq, read_only=True, data_only=True)
    try:
        ws = wb[ABA] if ABA in wb.sheetnames else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        cab = _cabecalho(next(it, []))
        ix = {k: (cab.index(t) if t in cab else None)
              for t, k, _l, _x in COLUNAS}
        saida = []
        for r in it:
            if not r or not any(v not in (None, "") for v in r):
                continue
            d = {}
            for t, k, _l, tipo in COLUNAS:
                j = ix[k]
                v = r[j] if j is not None and j < len(r) else None
                if tipo == "data":
                    v = _data(v)
                elif tipo == "num":
                    try:
                        v = float(v) if v not in (None, "") else 0.0
                    except (TypeError, ValueError):
                        v = 0.0
                else:
                    v = _texto(v)
                d[k] = v
            if not d["chave"]:
                continue
            saida.append(d)
        return saida
    finally:
        wb.close()


_RX_CLIENTE = re.compile(r"^\s*(\d{4,6})\s*-\s*(.+)$")


def separar_cliente(valor: str):
    """'000123 - NOME' -> ('000123', 'NOME'); 'NOME' -> ('', 'NOME')."""
    m = _RX_CLIENTE.match(valor or "")
    if m:
        return m.group(1).zfill(6), m.group(2).strip()
    return "", (valor or "").strip()


def gravar_edicoes(raiz, edicoes: dict) -> int:
    """
    edicoes = {chave: {campo: valor}}. Chave que comeca com NOVO vira linha
    nova (chave sequencial). O campo 'cliente' aceita 'COD - NOME' (grava o
    codigo e o nome). Levanta PermissionError se o Excel estiver aberto.
    """
    from openpyxl import load_workbook                  # noqa: PLC0415
    arq = caminho(raiz)
    if not arq.exists():
        criar(raiz)
    wb = load_workbook(arq)
    ws = wb[ABA] if ABA in wb.sheetnames else wb.worksheets[0]
    cab = _cabecalho(c.value for c in ws[1])
    col = {k: cab.index(t) + 1 for t, k, _l, _x in COLUNAS if t in cab}
    for t, k, _l, _x in COLUNAS:          # coluna nova: entra no fim
        if k not in col:
            col[k] = ws.max_column + 1
            ws.cell(1, col[k], t)
    tipos = {k: tipo for _t, k, _l, tipo in COLUNAS}
    linhas = {}
    ultima, maior = 1, 0
    for n in range(2, ws.max_row + 1):
        k = _texto(ws.cell(n, col["chave"]).value)
        if k:
            linhas[k] = n
            ultima = n
            try:
                maior = max(maior, int(re.sub(r"\D", "", k) or 0))
            except ValueError:
                pass
    hoje = date.today()
    mudou = 0
    for chave, campos in edicoes.items():
        campos = dict(campos)
        if "cliente" in campos:
            cod, nome = separar_cliente(campos.pop("cliente"))
            campos["cliente"] = nome
            if cod:
                campos["cod_cliente"] = cod
        if str(chave).upper().startswith("NOVO"):
            maior += 1
            ultima += 1
            n = ultima
            campos.setdefault("data", hoje)
            campos.setdefault("status", "Solicitado")
            campos.setdefault("qtd", 1)
            if not campos.get("categoria"):
                campos["categoria"] = categoria_da_descricao(
                    campos.get("descricao", ""))
            campos["chave"] = f"EXP{maior:04d}"
        else:
            n = linhas.get(str(chave))
            if n is None:
                raise ValueError(f"Não achei o expositor {chave}.")
        campos["atualizado_em"] = hoje
        for campo, valor in campos.items():
            if campo not in col:
                continue
            c = ws.cell(n, col[campo])
            tipo = tipos.get(campo)
            if tipo == "data":
                valor = _data(valor)
                if valor:
                    valor = datetime(valor.year, valor.month, valor.day)
                    c.number_format = "dd/mm/yyyy"
            elif tipo == "num":
                try:
                    valor = float(str(valor).replace(",", ".")) \
                        if valor not in (None, "") else None
                except ValueError:
                    valor = None
            elif valor == "":
                valor = None
            if c.value != valor:
                c.value = valor
                mudou += 1
    tmp = arq.with_name(f"~salvando_{arq.name}")
    wb.save(tmp)
    try:
        os.replace(tmp, arq)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return mudou


# ------------------------------------------------------------------ cadastro
def carregar_cadastro(raiz=None) -> list:
    arq = Path(raiz or AQUI) / CADASTRO
    if not arq.exists():
        return []
    try:
        dados = json.loads(arq.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return dados.get("expositores", []) if isinstance(dados, dict) else []


def salvar_cadastro(itens: list, raiz=None) -> Path:
    arq = Path(raiz or AQUI) / CADASTRO
    vistos = set()
    for i in itens:
        i["nome"] = _texto(i.get("nome")).upper()
        if not i["nome"]:
            raise ValueError("Todo expositor precisa de NOME.")
        k = (i["nome"], _texto(i.get("filial")).upper())
        if k in vistos:
            raise ValueError(f"{i['nome']} já está cadastrado nessa filial.")
        vistos.add(k)
    itens.sort(key=lambda i: (i["nome"], i.get("filial", "")))
    tmp = arq.with_name(f"~{arq.name}")
    tmp.write_text(json.dumps({"expositores": itens}, ensure_ascii=False,
                              indent=1), "utf-8")
    os.replace(tmp, arq)
    return arq


def categorias_foco(raiz=None) -> list:
    """As categorias de produto que ja existem (CATEGORIAS_PRODUTO.csv)."""
    mapa = {"pecas": "PEÇAS", "peças": "PEÇAS", "lubrificante": "LUBRIFICANTES",
            "bateria": "BATERIAS", "pneu": "PNEUS"}
    achadas = []
    csv = Path(raiz or AQUI) / "CATEGORIAS_PRODUTO.csv"
    try:
        import meta_nucleo as mn                        # noqa: PLC0415
        for v in set(mn.ler_categorias_de_produto(csv).values()):
            achadas.append(mapa.get(str(v).lower(), str(v).upper()))
    except Exception:                                   # noqa: BLE001
        pass
    return sorted(set(achadas) | set(CATEGORIAS),
                  key=lambda c: (CATEGORIAS.index(c) if c in CATEGORIAS
                                 else 99, c))
