"""T-0017, entregas 3 a 5 (contrato §10.7): todas as abas de tabela de Pedidos, Entregas e Visita.

Aqui ficam três coisas:
1. a lista fechada de abas e colunas (§10.7.1 e §10.7.3) e a validação do pacote (§10.7.6);
2. quem vê as tabelas (`VE_TABELAS`, decisão D1, recomendação A: o perfil do farol vê tudo);
3. a tela genérica de tabela (`tabela_para_tela`): filtro, recorte, estado, ordenação, páginas,
   selos, juntas. A Inadimplência (`cobranca.py`) usa a mesma função.

Nenhuma regra de negócio é decidida aqui: filtro padrão, recortes, UF de cada linha, cartões da aba e
limpeza de nome vêm prontos do PC. A web só confere o formato e desenha.
"""
from __future__ import annotations

import math
import re
import unicodedata

from . import edicoes, marca, render
from .render import COLUNAS_FORA, RE_DATA, coluna_fora, fmt_celula   # a lista e o formato são do render (fonte única)

# ------------------------------------------------------------------ D1: quem vê as tabelas
# Decisão D1 do Alexandre ainda aberta: recomendação A = o perfil de cada farol vê todas as abas
# (como o pós-venda na Inadimplência). Trocar aqui: B = só ("admin", "gerente"); C = tirar de
# "vendas" as abas cliente, prospeccao e indicacao em `ABAS_SO_GERENCIA`.
# T-0036 (P1 = A): `LEITURA_GERAL` (admin, gerente, analista) é a fonte única; a P1 = B troca só a constante do render.
VE_TABELAS = {
    "pv_pedidos": render.LEITURA_GERAL + ("pre_venda",),
    "pl_entregas": render.LEITURA_GERAL + ("pos_venda",),
    "pl_fretes": render.LEITURA_GERAL + ("pos_venda",),   # T-0037, P4 A (provisória): o pós-venda vê as 4 abas
    "vc_visitas": render.LEITURA_GERAL + ("vendas",),
    # T-0024 (lote 2): o perfil de cada quadrado do PC vê as abas (a mesma D1 recomendação A)
    "pv_indicadores": render.LEITURA_GERAL + ("pre_venda",),
    "vc_base": render.LEITURA_GERAL + ("vendas",),
    "vc_planner": render.LEITURA_GERAL + ("vendas",),
    "pl_giro": render.LEITURA_GERAL + ("vendas",),
    "pl_frw": render.LEITURA_GERAL + ("pre_venda", "pos_venda"),
    # T-0022: o Farol de Metas Equipe segue a mesma regra (D1 A): o diretor vê o Resumo; mude aqui se a D1 mudar
    "vc_meta": render.LEITURA_GERAL + ("vendas",),
    # T-0036 (contrato §10.11.6): faróis do Analista Comercial; o diretor só vê o Resumo
    "vc_saldo": render.LEITURA_GERAL,
    "vc_markup": render.LEITURA_GERAL,
    "vc_preco": render.LEITURA_GERAL,
    "an_divergencias": render.LEITURA_GERAL,
        # T-0023 v2 (contrato §10.10.1): o diretor vê o farol (Resumo), não as abas de tabela (RN-GER-014)
    "pl_garantias": render.LEITURA_GERAL + ("pos_venda",),
    "pl_devolucoes": render.LEITURA_GERAL + ("pos_venda",),
    "pl_ncc": render.LEITURA_GERAL + ("pos_venda",),
}
# T-0024: faróis "livres": as abas e as colunas são as que o PC monta (sem a lista fechada do §10.7.3);
# a web confere só o formato, as colunas que nunca vão e o documento na célula
FAROIS_LIVRES = ("pv_indicadores", "vc_base", "vc_planner", "pl_giro", "pl_frw")
ABAS_SO_GERENCIA: dict[str, tuple[str, ...]] = {}      # D1 C: {"vc_visitas": ("cliente", "prospeccao", "indicacao")}
PERFIS_GERENCIA = render.LEITURA_GERAL   # T-0036 (RD-0003): o analista lê como o gerente (RN-GER-017)

RIDS = tuple(VE_TABELAS)
RESUMO = ("resumo", "Resumo")
# chave na URL -> título da tabela no pacote (§10.7.1), na ordem do PC
ABAS = {
    "pv_pedidos": (("pedidos", "Pedidos"), ("solicitacao", "Solicitação BAP")),
    "pl_entregas": (("entregas", "Entregas"),),
    "pl_fretes": (("notas", "Notas com frete"), ("uf", "Por UF"), ("cidade", "Por cidade"),
                  ("transportadora", "Por transportadora")),
    # T-0023 v2 (§10.10.1): as abas dos 3 faróis do Pós-venda, na ordem do PC
    "pl_garantias": (("garantias", "Garantias"), ("historico", "Histórico de compra"), ("produto", "Por produto"),
                     ("status", "Status x resultado")),
    "pl_devolucoes": (("devolucoes", "Devoluções"), ("motivo", "Por motivo"), ("vendedor", "Por vendedor (12 meses)"),
                      ("cliente", "Por cliente (12 meses)"), ("produto", "Por produto (12 meses)")),
    "pl_ncc": (("pendentes", "NCC pendentes"), ("cliente", "Por cliente"), ("filial", "Por filial"),
               ("vendedor", "Por vendedor"), ("supervisor", "Por supervisor")),
    "vc_meta": (("equipe", "Equipe"), ("top30", "Top 30 clientes"), ("uf", "Por UF"), ("cidade", "Por cidade"),
                ("bairro", "Por bairro"), ("segmento", "Por segmento"), ("zona", "Por zona"),
                ("categoria", "Por categoria"), ("familia", "Por família da peça")),
    "vc_visitas": (("supervisor", "Por supervisor"), ("vendedor", "Por vendedor"), ("dia", "Dia a dia"),
                   ("aderencia", "Aderência dia a dia"), ("cliente", "Cliente a cliente"),
                   ("prospeccao", "Prospecção"), ("indicacao", "Indicação")),
    # T-0036 (contrato §10.11.1): ordem do PC
    "vc_saldo": (("pedido", "Pedido a pedido"), ("vendedor", "Por vendedor"), ("supervisor", "Por supervisor"),
                 ("uf", "Por UF")),
    "vc_markup": (("pedido", "Por pedido"), ("uf", "Por UF"), ("cidade", "Por cidade"),
                  ("supervisor", "Por supervisor"), ("vendedor", "Por vendedor"), ("categoria", "Por categoria"),
                  ("sistema", "Por sistema"), ("familia", "Por família"), ("linha", "Por linha"),
                  ("produto", "Por produto"), ("todos", "Todos os produtos")),
    "vc_preco": (("categoria", "Por categoria"), ("familia", "Por família"), ("total", "Total BAP"),
                 ("reajustes", "Reajustes por produto"), ("pesquisa", "Pesquisa de mercado")),
    "an_divergencias": (("vendedor", "Por vendedor"), ("divergentes", "Clientes divergentes"),
                        ("sem_coordenada", "Sem coordenada / endereço")),
}
SUBABAS = ("Solicitacao Lojas", "Solicitacao CD", "Solicitacao FRW", "Solicitacao Manual",
           "DETALHADO_PEDIDO", "ProdutosExcluir", "FiliaisExcluir")
# D5 (recomendação A): estado filtra as linhas só onde o pacote traz `uf_linhas`
AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."
# coluna que identifica a linha: fica fixa à esquerda ao rolar para o lado (celular)
FIXA = {"Por vendedor": "VENDEDOR", "Dia a dia": "VENDEDOR", "Aderência dia a dia": "VENDEDOR",
        "Cliente a cliente": "VENDEDOR",
        # T-0036: a coluna que identifica a linha nas abas do Analista
        "Pedido a pedido": "PEDIDO", "Por pedido": "PEDIDO", "Por produto": "PRODUTO",
        "Todos os produtos": "PRODUTO", "Reajustes por produto": "PRODUTO"}
LIVRES = {"OBSERVAÇÃO", "JUSTIFICATIVA", "RESULTADO", "LINHAS DE INTERESSE", "DESCRIÇÃO",
          "O QUE FAZER", "O QUE FALTA"}   # texto livre: quebra
ROTULO_SUB = {"Solicitacao Lojas": "Lojas", "Solicitacao CD": "CD", "Solicitacao FRW": "FRW",
              "Solicitacao Manual": "Manual", "DETALHADO_PEDIDO": "Detalhado por pedido",
              "ProdutosExcluir": "Produtos excluídos", "FiliaisExcluir": "Filiais excluídas"}
_TROCA_ROTULO = {"COD": "CÓD.", "DESCRICAO": "DESCRIÇÃO", "JA": "JÁ", "UF": "UF", "CD": "CD", "FRW": "FRW"}


# T-0033 (UX §2.4/§2.5): o nome da aba na barra, curto, para caber a 1366 com a busca (o título do pacote não muda)
ABA_CURTA = {"Por supervisor": "Supervisor", "Por vendedor": "Vendedor", "Aderência dia a dia": "Aderência",
             "Top 30 clientes": "Top 30", "Por UF": "UF", "Por cidade": "Cidade", "Por bairro": "Bairro",
             "Por segmento": "Segmento", "Por zona": "Zona", "Por categoria": "Categoria",
             "Por família da peça": "Família", "Por cliente": "Cliente", "Por filial": "Filial",
             # T-0023 v2 (UX §3): as abas dos 3 faróis do Pós-venda
             "Histórico de compra": "Histórico", "Status x resultado": "Status", "Por motivo": "Motivo",
             "Por vendedor (12 meses)": "Vendedor", "Por cliente (12 meses)": "Cliente",
             "Por produto (12 meses)": "Produto", "NCC pendentes": "Pendentes",
             "Notas com frete": "Notas", "Por transportadora": "Transportadora"}           # T-0037


def aba_curta(nome: str) -> str:
    return ABA_CURTA.get(nome, nome)


def ve_tabelas(rid: str, perfil: str) -> bool:
    return rid in VE_TABELAS and perfil in VE_TABELAS[rid]


def ve_aba(rid: str, chave: str, perfil: str) -> bool:
    if not ve_tabelas(rid, perfil):
        return False
    return perfil in PERFIS_GERENCIA or chave not in ABAS_SO_GERENCIA.get(rid, ())


def _slug(t: str) -> str:
    s = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "aba"


# T-0024 (parecer de UX, R1): rótulo curto da aba dos faróis livres, sem quebra de linha a 1366. O título do PC
# continua sendo a chave da tabela no pacote (contrato §9); a URL usa o rótulo curto, que não leva mês.
ROTULO_ABA = {
    ("pv_indicadores", "Base com compra (mês a mês)"): "Base mês a mês",
    ("pv_indicadores", "Base com compra em NOV/26, por segmento"): "Base por segmento",
    ("vc_base", "Por UF"): "UF", ("vc_base", "Por segmento"): "Segmento", ("vc_base", "Por cidade"): "Cidade",
    ("vc_base", "Por vendedor"): "Vendedor", ("vc_base", "Por supervisor"): "Supervisor",
    ("vc_base", "Por família (6 meses)"): "Família", ("vc_base", "Por produto (top 400, 6 meses)"): "Produto",
    ("pl_giro", "Resumo por filial"): "Por filial",
    # T-0036 (revisão de UX, R2): as abas do Analista numa linha só a 1366 px
    **{("vc_saldo", t): c for t, c in (("Pedido a pedido", "Pedido"), ("Por vendedor", "Vendedor"),
                                       ("Por supervisor", "Supervisor"), ("Por UF", "UF"))},
    **{("vc_markup", t): c for t, c in (("Por pedido", "Pedido"), ("Por UF", "UF"), ("Por cidade", "Cidade"),
                                        ("Por supervisor", "Supervisor"), ("Por vendedor", "Vendedor"),
                                        ("Por categoria", "Categoria"), ("Por sistema", "Sistema"),
                                        ("Por família", "Família"), ("Por linha", "Linha"),
                                        ("Por produto", "Produto"), ("Todos os produtos", "Todos"))},
    **{("vc_preco", t): c for t, c in (("Por categoria", "Categoria"), ("Por família", "Família"),
                                       ("Total BAP", "Total"), ("Reajustes por produto", "Reajustes"),
                                       ("Pesquisa de mercado", "Pesquisa"))},
    **{("an_divergencias", t): c for t, c in (("Por vendedor", "Vendedor"), ("Clientes divergentes", "Divergentes"),
                                              ("Sem coordenada / endereço", "Sem coord."))},
}


def rotulo_aba(rid: str, titulo: str) -> str:
    """Nome da aba na barra. Mês dentro do título (NOV/26) nunca vai para a tela nem para a URL."""
    return ROTULO_ABA.get((rid, titulo), titulo)


def abas_do_farol(rid: str, rel: dict | None = None) -> list[tuple[str, str]]:
    """[(chave na URL, título da tabela)] na ordem do PC. Farol livre: sai das tabelas do pacote."""
    if rid not in FAROIS_LIVRES:
        return list(ABAS.get(rid, ()))
    saida, usadas = [], set()
    for t in (rel or {}).get("tabelas") or []:
        c = _slug(rotulo_aba(rid, t.get("titulo", "")))
        while c in usadas or c == "resumo":
            c += "-2"
        usadas.add(c)
        saida.append((c, t["titulo"]))
    return saida


def chaves(rid: str, rel: dict | None = None) -> list[str]:
    return [c for c, _ in abas_do_farol(rid, rel)]


# ------------------------------------------------------------------ colunas (§10.7.3)
def _c(nome, tipo="texto", oculta=False):
    return (nome, tipo, oculta)


_METRICAS = [_c("META", "num"), _c("VISIT.", "int"), _c("% META", "pct"), _c("% CONV.", "pct"),
             _c("% FORA DE ROTA", "pct"), _c("CAD.", "int"), _c("CAD. C/ COMPRA", "int"), _c("PROSP.", "int"),
             _c("INÍCIO", "hora"), _c("ÚLT. ATIV.", "hora"), _c("JORNADA LÍQ.", "hora"),
             _c("DIAS < JORN. LÍQ.", "int"), _c("INTERV. ALMOÇO", "hora"), _c("DIAS ALMOÇO > MÁX.", "int"),
             _c("TMA", "hora"), _c("TMD", "hora"), _c("KM", "num"), _c("KM/CLIENTE", "num1")]


def _entregas(mes_oculto: bool):
    return [_c("MÊS", "texto", mes_oculto), _c("SITUAÇÃO"), _c("SLA", "int"), _c("DT. PED", "dia"),
            _c("DT. NF", "dia"), _c("DT. PREVISTA", "dia"), _c("DT. REAL", "dia"), _c("UF"), _c("CIDADE"),
            _c("CLIENTE"), _c("VLR NF", "moeda"), _c("VLR FRETE", "moeda"), _c("TRANSPORTADORA"),
            _c("RESPONSÁVEL"), _c("TBL FRETE", "moeda"), _c("VLR REAL FRETE", "moeda"), _c("ETAPA"),
            _c("NF"), _c("FILIAL"), _c("LOCAL/FRETE", "texto", True), _c("TOM SLA", "texto", True),
            _c("PRAZO", "texto", True)]


_GERAR = [_c("DATA", "dia"), _c("UF"), _c("CIDADE"), _c("PEDIDOS"), _c("FORN."), _c("CÓD. PROD."),
          _c("DESCRIÇÃO"), _c("QTD", "num"), _c("COLETAR EM"), _c("FILIAL DEST.")]

COLUNAS: dict[str, list] = {
    "Pedidos": [_c("DT. PED", "dia"), _c("FATURAR ATÉ", "dia"), _c("PEDIDO"), _c("PED. MÁX."), _c("CÓD."),
                _c("RAZÃO SOCIAL"), _c("FANTASIA"), _c("UF"), _c("CIDADE"), _c("LIMITE", "moeda"),
                _c("DISP.", "moeda"), _c("ATRASO", "moeda"), _c("VOL.", "num"), _c("R$ TABELA", "moeda"),
                _c("R$ VENDA", "moeda"), _c("% DESC.", "pct1"), _c("SLA", "int"), _c("% ATENDIDO", "pct"),
                _c("ANÁLISE CRÉDITO"), _c("COND. PAGTO"), _c("SITUAÇÃO"), _c("FILIAL"), _c("PRAZO"),
                _c("VENDEDOR"), _c("NF"), _c("DT. NF", "dia"), _c("R$ TABELA CHEIA", "moeda", True),
                _c("CÓD. AUTORIZAÇÃO", "texto", True), _c("AUTORIZADO POR", "texto", True),
                _c("MÊS", "texto", True), _c("ENTREGUE EM", "dia", True), _c("PRODUTO", "texto", True),
                _c("CHAVE", "texto", True)],
    "Gerar separação CD": _GERAR,
    "Gerar reversa de lojas": _GERAR,
    "Analítico produto": [_c("PEDIDO"), _c("DATA", "dia"), _c("CIDADE"), _c("FILIAL"), _c("FORN."),
                          _c("CÓD. PROD."), _c("DESCRIÇÃO"), _c("QTD", "num"), _c("EST. FRW", "num"),
                          _c("PEDIDOS ANTES", "num"), _c("DISP. P/ ESTE", "num"), _c("ATENDIDO", "num"),
                          _c("FALTA", "num"), _c("CLIENTE"), _c("FILIAL BAP", "texto", True),
                          _c("VALOR FALTANTE", "moeda")],
    "Notas com frete": [_c("MÊS", "texto", True), _c("DATA PED.", "dia"), _c("DATA NF", "dia"), _c("NF"),
                        _c("FILIAL"), _c("CLIENTE"), _c("CIDADE"), _c("UF"), _c("VLR NF", "moeda"),
                        _c("VLR FRETE", "moeda"), _c("ETAPA"), _c("TRANSPORTADORA"), _c("ENTREGAR ATÉ", "dia"),
                        _c("ENTREGUE", "dia"), _c("SLA ENTREGA", "int"), _c("RESPONSÁVEL")],
    "Entregas": _entregas(True),
    "Pendências dos meses anteriores": _entregas(False),
    "Por supervisor": [_c("SUPERVISOR"), _c("REPRES.", "int")] + _METRICAS + [_c("CHAVE", "texto", True)],
    "Por vendedor": [_c("SUPERVISOR"), _c("VENDEDOR"), _c("CARGO", "texto", True), _c("FILIAL", "texto", True),
                     _c("CÓD.", "texto", True)] + _METRICAS + [_c("CHAVE", "texto", True)],
    "Dia a dia": [_c("DATA", "data"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"), _c("CARGO", "texto", True),
                  _c("SITUAÇÃO")] + _METRICAS + [_c("CHAVE", "texto", True)],
    "Cliente a cliente": [_c("DATA", "data"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"), _c("SITUAÇÃO"),
                          _c("CÓD."), _c("CLIENTE"), _c("NOME FANTASIA"), _c("SEGMENTO"), _c("BAIRRO"),
                          _c("CIDADE"), _c("CURVA"), _c("STATUS"), _c("DIAS S/ COMPRA", "int"),
                          _c("ATRASO", "moeda"), _c("SEQ. PREV."), _c("SEQ. REAL"), _c("INÍCIO", "hora"),
                          _c("FIM", "hora"), _c("ATEND.", "hora"), _c("PEDIDO NO DIA"),
                          _c("VALOR PEDIDO", "moeda"), _c("JUSTIFICATIVA"), _c("ATEND. SEG.", "int", True)],
    "Prospecção": [_c("DATA", "data"), _c("HORA", "hora"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"),
                   _c("STATUS"), _c("FONTE"), _c("ESTABELECIMENTO"), _c("SEGMENTO"), _c("CIDADE"), _c("UF"),
                   _c("RESULTADO"), _c("LINHAS DE INTERESSE"), _c("OBSERVAÇÃO")],
    "Indicação": [_c("DATA", "data"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"), _c("SITUAÇÃO"),
                  _c("CÓD. QUEM INDICOU"), _c("CLIENTE QUE INDICOU"), _c("INDICADO"), _c("CIDADE"),
                  _c("BAIRRO"), _c("SEGMENTO"), _c("VISITADA EM", "data"), _c("OBSERVAÇÃO"),
                  _c("REGISTRADO EM")],
}
# T-0037: títulos que se repetem em outro farol: a lista é por (rid, título)
_RESUMO_FRETES = [_c("NOTAS", "int"), _c("VLR NF", "moeda"), _c("VLR FRETE", "moeda")]
# ------------------------------------------------------------------ T-0036: colunas do §10.11.3 (lista positiva)
def _l(*specs):
    """"NOME", "NOME|tipo" ou "NOME|tipo|o" (o = oculta) -> lista de `_c`. Só nesta lista entram colunas do Analista;
    coluna a mais (nome de cliente, endereço, telefone) derruba a aba (RN-GER-011)."""
    out = []
    for sp in specs:
        n, *r = sp.split("|")
        out.append(_c(n, r[0] if r else "texto", len(r) > 1 and r[1] == "o"))
    return out


_MARKUP_GRUPO = ["PEDIDOS|int", "QTD|num", "R$ VENDA|moeda", "CUSTO|moeda", "MARGEM|moeda", "MARKUP %|pct1",
                 "MKP TABELA %|pct1", "% DESC.|pct1", "PART. MARGEM|pct1", "SEM CUSTO|int"]
_MARKUP_PROD = ["PRODUTOS|int", "ESTOQUE|num", "VOL. VENDIDO|num", "R$ VENDA|moeda", "CUSTO|moeda", "MARGEM|moeda",
                "MKP REAL %|pct1", "% DESC.|pct1", "MKP TABELA %|pct1", "MKP VENDA %|pct1", "PART. MARGEM|pct1",
                "SEM CUSTO|int"]
_SALDO_G = ["PEDIDOS|int", "VLR TABELA|moeda", "VLR VENDA|moeda", "DESC. COMERCIAL|moeda", "% DESC. COM.|pct1",
            "SALDO FRETE|moeda", "SALDO|moeda", "META SALDO|moeda", "% ATING.|pct"]
_PRECO_G = ["LEITURA", "FATURAMENTO|moeda", "VAR. FAT. %|pct1", "VOLUME|num", "VAR. VOL. %|pct1",
            "PREÇO MÉDIO|moeda2", "PREÇO TABELA|moeda2", "VAR. PREÇO %|pct1", "VAR. TABELA %|pct1",
            "VAR. FAT. R$|moeda", "EFEITO PREÇO|moeda", "EFEITO VOLUME|moeda", "EFEITO MIX|moeda",
            "ELASTICIDADE|num2"]

# (rid, título) -> colunas; os títulos "Por vendedor", "Por UF" etc. se repetem entre faróis
COLUNAS_RID: dict[tuple[str, str], list] = {
    ("vc_saldo", "Pedido a pedido"): _l(
        "MÊS|texto|o", "DATA NF|dia", "FILIAL", "PEDIDO", "CÓD.", "VENDEDOR", "COND. PAGTO", "VLR TABELA|moeda",
        "VLR VENDA|moeda", "% DESC. COM.|pct1", "SALDO DO PEDIDO|moeda", "SALDO FRETE|moeda", "NO SALDO|moeda",
        "NF", "SUPERVISOR", "DESC. COMERCIAL|moeda", "UF", "CHAVE|texto|o"),
    ("vc_saldo", "Por vendedor"): _l("MÊS|texto|o", "VENDEDOR", "SUPERVISOR", *_SALDO_G),
    ("vc_saldo", "Por supervisor"): _l("MÊS|texto|o", "SUPERVISOR", *_SALDO_G),
    ("vc_saldo", "Por UF"): _l("MÊS|texto|o", "UF", *_SALDO_G),
    ("vc_markup", "Por pedido"): _l(
        "SITUAÇÃO", "DATA PED.|dia", "DATA NF|dia", "FILIAL", "PEDIDO", "NF", "CÓD.", "STATUS PROTHEUS|texto|o",
        "STATUS", "SITUAÇÃO PLANNER|texto|o", "UF", "CIDADE", "SUPERVISOR", "VENDEDOR", "QTD|num", "R$ VENDA|moeda",
        "CUSTO|moeda", "SUCATA|moeda", "MARGEM|moeda", "MARKUP %|pct1", "MKP TABELA %|pct1", "% DESC.|pct1",
        "SEM CUSTO|int", "VENDA SEM CUSTO|moeda|o", "SO BATERIA|texto|o", "CÓD. AUTORIZAÇÃO", "AUTORIZADO POR"),
    ("vc_markup", "Por UF"): _l("UF", *_MARKUP_GRUPO),
    ("vc_markup", "Por cidade"): _l("CIDADE", *_MARKUP_GRUPO),
    ("vc_markup", "Por supervisor"): _l("SUPERVISOR", *_MARKUP_GRUPO),
    ("vc_markup", "Por vendedor"): _l("VENDEDOR", *_MARKUP_GRUPO),
    ("vc_markup", "Por categoria"): _l("CATEGORIA", *_MARKUP_PROD),
    ("vc_markup", "Por sistema"): _l("SISTEMA", *_MARKUP_PROD),
    ("vc_markup", "Por família"): _l("FAMÍLIA", *_MARKUP_PROD),
    ("vc_markup", "Por linha"): _l("LINHA", *_MARKUP_PROD),
    ("vc_markup", "Por produto"): _l(
        "PRODUTO", "DESCRIÇÃO", "CATEGORIA|texto|o", "SISTEMA|texto|o", "FAMÍLIA|texto|o", "LINHA|texto|o",
        "SITUAÇÃO", "ESTOQUE|num", "CUSTO UNIT.|moeda2", "PRC. TABELA MÉD.|moeda2", "MKP TABELA %|pct1",
        "PRC. VENDA MÉD.|moeda2", "MKP VENDA %|pct1", "VOL. VENDIDO|num", "R$ VENDA|moeda", "CUSTO|moeda",
        "MARGEM|moeda", "MKP REAL %|pct1", "% DESC.|pct1", "PART. MARGEM|pct1"),
    ("vc_markup", "Todos os produtos"): _l(
        "PRODUTO", "DESCRIÇÃO", "CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA", "FORNECEDOR", "CUSTO|moeda2",
        "ORIGEM CUSTO|texto|o", "PRC. TABELA MÉD.|moeda2", "% DESC.|pct1", "PRC. VENDA MÉD.|moeda2",
        "MKP VENDA %|pct1", "PREÇO INTERIOR MÉDIO|moeda2|o", "MKP TABELA %|pct1|o", "MKP INTERIOR %|pct1|o",
        "EST.|num", "SITUAÇÃO", "QTD VEND.|num", "R$ VENDA|moeda", "MKP REAL %|pct1", "ÚLT. VENDA|data"),
    ("vc_preco", "Por categoria"): _l("MÊS", "AAAA-MM|texto|o", "CATEGORIA", *_PRECO_G),
    ("vc_preco", "Por família"): _l("MÊS", "AAAA-MM|texto|o", "FAMÍLIA", *_PRECO_G),
    ("vc_preco", "Total BAP"): _l("MÊS", "AAAA-MM|texto|o", "TOTAL", *_PRECO_G),
    ("vc_preco", "Reajustes por produto"): _l(
        "MÊS", "AAAA-MM|texto|o", "FILIAL", "CÓD. PRODUTO", "PRODUTO", "CATEGORIA|texto|o", "FAMÍLIA", "LEITURA",
        "TABELA ANTES|moeda2|o", "TABELA AGORA|moeda2|o", "VAR. TABELA %|pct1", "PRATICADO ANTES|moeda2|o",
        "PREÇO PRATICADO|moeda2", "VAR. PREÇO %|pct1", "QTD ANTES|num|o", "QTD|num", "VAR. QTD %|pct1",
        "FAT. ANTES|moeda|o", "FATURAMENTO|moeda", "VAR. FAT. %|pct1", "SISTEMA|texto|o", "LINHA|texto|o"),
    ("vc_preco", "Pesquisa de mercado"): _l(
        "MÊS|texto|o", "DATA|data", "VENDEDOR", "SUPERVISOR|texto|o", "CIDADE", "UF", "SEGMENTO|texto|o",
        "LINHA DIA FOCO", "PAPEL", "CÓD. BAP", "PRODUTO", "CONCORRENTE", "CÓD. CONCORRENTE|texto|o", "LEITURA",
        "COMPRA BAP|moeda2", "COMPRA CONC.|moeda2", "DIF. COMPRA %|pct1", "VENDA BAP|moeda2",
        "VENDA CONC.|moeda2", "DIF. VENDA %|pct1", "MKP CLIENTE BAP %|pct1", "MKP CLIENTE CONC. %|pct1",
        "PRC. TABELA BAP|moeda2", "COMPRA x TABELA %|pct1", "ESTOQUE BAP|num", "ESTOQUE CONC.|num",
        "SHARE ESTOQUE %|pct1", "VOL. BAP|num", "VOL. CONC.|num", "SHARE VOLUME %|pct1", "OBSERVAÇÃO",
        "CATEGORIA|texto|o", "FAMÍLIA|texto|o"),
    ("an_divergencias", "Por vendedor"): _l(
        "VENDEDOR", "SUPERVISOR", "CARTEIRA PLANNER|int", "BASE PROTHEUS|int", "IGUAIS|int", "SÓ NO PLANNER|int",
        "SÓ NO PROTHEUS|int", "· FORA DA BASE|int", "· PLANNER SEM VENDEDOR|int", "BATE?"),
    ("an_divergencias", "Clientes divergentes"): _l(
        "COD", "LOJA", "CIDADE", "UF", "SEGMENTO", "ZONA", "VENDEDOR PLANNER", "VENDEDOR PROTHEUS (A1_VEND)",
        "STATUS PROTHEUS|texto|o", "SITUAÇÃO", "O QUE FAZER"),
    ("an_divergencias", "Sem coordenada / endereço"): _l(
        "CÓD.", "LOJA", "O QUE FALTA", "NA ROTA DO MÊS", "UF", "CIDADE", "VENDEDOR PLANNER",
        "SUPERVISOR PLANNER", "SEGMENTO", "CURVA", "SITUAÇÃO", "PONTO"),
}
RE_COORD = re.compile(r"-?\d+\.\d{3,}")                  # coordenada na coluna PONTO: a aba fica fora (§10.11.2)

# T-0023 v2 (§10.10.2): colunas por (rid, título), nunca só pelo título ("Por vendedor" existe no Visita e na NCC)
def _agrupa_ncc(nome):
    """Os 3 agrupamentos da NCC (§10.10.2): só muda a coluna do agrupamento."""
    return [_c(nome), _c("NCC", "int"), _c("CLIENTES", "int"), _c("0-30 DIAS", "moeda"), _c("31-90 DIAS", "moeda"),
            _c("91-180 DIAS", "moeda"), _c("+180 DIAS", "moeda"), _c("SALDO", "moeda"), _c("COMPENSAR JÁ", "moeda")]


COLUNAS_RID.update({
    ("pl_garantias", "Garantias"): [
        _c("STATUS"), _c("RESULTADO ANÁLISE"), _c("TICKET"), _c("DT. SOLICITAÇÃO", "data"),
        _c("DT. FECHAMENTO", "data"), _c("SLA ATUAL", "int"), _c("PRAZO"), _c("CÓD. CLIENTE"), _c("CLIENTE"),
        _c("CIDADE"), _c("CÓD. PRODUTO"), _c("DESCRIÇÃO PRODUTO", "texto", True), _c("QTD", "num"),
        _c("PENDÊNCIAS", "texto", True), _c("RETORNO DO CLIENTE", "texto", True), _c("VENDEDOR", "texto", True),
        _c("SUPERVISOR", "texto", True), _c("SITUAÇÃO DO PRAZO", "texto", True), _c("TOM SLA", "texto", True),
        _c("DT. FECHOU", "data", True), _c("RECLAMAÇÃO", "texto", True), _c("OBSERVAÇÃO", "texto", True),
        _c("DT. RETORNO", "data", True)
    ],
    ("pl_garantias", "Histórico de compra"): [
        _c("CÓD. CLIENTE"), _c("RAZÃO SOCIAL"), _c("FANTASIA"), _c("CIDADE"), _c("PEDIDO"), _c("PED. MÁXIMA"),
        _c("NF"), _c("PRAZO"), _c("DT. PEDIDO", "dia"), _c("DT. NF", "dia"), _c("DT. ENTREGA", "dia"),
        _c("TRANSPORTADORA"), _c("RESPONSÁVEL"), _c("CÓD. PRODUTO"), _c("DESCRIÇÃO"), _c("QTD", "num"),
        _c("VALOR", "moeda"), _c("VENDEDOR"), _c("FILIAL")
    ],
    ("pl_garantias", "Por produto"): [
        _c("CÓD. PRODUTO"), _c("DESCRIÇÃO"), _c("GARANTIAS", "int"), _c("EM ABERTO", "int"),
        _c("PROCEDENTES", "int"), _c("IMPROCEDENTES", "int")
    ],
    ("pl_garantias", "Status x resultado"): [
        _c("STATUS"), _c("PENDENTE", "int"), _c("PROCEDENTE", "int"), _c("IMPROCEDENTE", "int"), _c("TOTAL", "int")
    ],
    ("pl_devolucoes", "Devoluções"): [
        _c("MÊS"), _c("DATA", "data"), _c("NF DEV."), _c("FILIAL"), _c("CLIENTE"), _c("CIDADE"), _c("UF"),
        _c("VENDEDOR"), _c("VALOR", "moeda"), _c("ITENS", "int"), _c("PRODUTOS"), _c("ETAPA"), _c("MOTIVO"),
        _c("AUTORIZADO POR"), _c("RECEBIDA EM", "data"), _c("CRÉDITO"), _c("CRÉDITO EM", "data"), _c("RESPONSÁVEL")
    ],
    ("pl_devolucoes", "Por motivo"): [
        _c("MÊS"), _c("MOTIVO"), _c("DEVOLUÇÕES", "int"), _c("VALOR", "moeda")
    ],
    ("pl_devolucoes", "Por vendedor (12 meses)"): [
        _c("VENDEDOR"), _c("DEVOLUÇÕES", "int"), _c("VALOR", "moeda"), _c("FATURADO 12M", "moeda"),
        _c("% DEVOLVIDO", "pct")
    ],
    ("pl_devolucoes", "Por cliente (12 meses)"): [
        _c("CLIENTE"), _c("DEVOLUÇÕES", "int"), _c("VALOR", "moeda")
    ],
    ("pl_devolucoes", "Por produto (12 meses)"): [
        _c("PRODUTO"), _c("DESCRIÇÃO"), _c("QTD", "num"), _c("VALOR", "moeda")
    ],
    ("pl_ncc", "NCC pendentes"): [
        _c("A COMPENSAR"), _c("SLA NCC"), _c("DT. ÚLT. MOV.", "data"), _c("D.U. S/ MOV.", "int"), _c("IDADE"),
        _c("FILIAL"), _c("NCC"), _c("PARC."), _c("EMISSÃO", "data"), _c("DIAS", "int"), _c("CLIENTE"), _c("NOME"),
        _c("CIDADE"), _c("UF"), _c("VENDEDOR"), _c("SUPERVISOR", "texto", True), _c("VALOR NCC", "moeda"),
        _c("JÁ ABATIDO", "moeda"), _c("SALDO", "moeda"), _c("TÍTULOS EM ABERTO", "moeda"),
        _c("PEDIDO EM ABERTO", "moeda"), _c("ÚLTIMA COMPRA", "data")
    ],
    ("pl_ncc", "Por cliente"): [
        _c("A COMPENSAR"), _c("IDADE"), _c("CLIENTE"), _c("NOME"), _c("CIDADE"), _c("UF"), _c("VENDEDOR"),
        _c("SUPERVISOR", "texto", True), _c("NCC", "int"), _c("SALDO", "moeda"), _c("NCC MAIS ANTIGA (DIAS)", "int"),
        _c("TÍTULOS EM ABERTO", "moeda"), _c("PEDIDO EM ABERTO", "moeda"), _c("ÚLTIMA COMPRA", "data")
    ],
    ("pl_fretes", "Por UF"): [_c("MÊS", "texto", True), _c("UF")] + _RESUMO_FRETES,
    ("pl_fretes", "Por cidade"): [_c("MÊS", "texto", True), _c("CIDADE")] + _RESUMO_FRETES,
    ("pl_fretes", "Por transportadora"): [_c("MÊS", "texto", True), _c("TRANSPORTADORA")] + _RESUMO_FRETES,
    **{("pl_ncc", f"Por {k}"): _agrupa_ncc(k.upper()) for k in ("filial", "vendedor", "supervisor")},
})
# colunas que nunca vão, por tabela (§10.10.3, bloco `colunas-fora-por-tabela`): a web recusa o pacote que as traz
FORA_POR_TABELA = {("pl_garantias", "Garantias"): frozenset({"CONTATO CLIENTE"})}
# "Aderência dia a dia": 2 + N + 1 colunas, conferidas por padrão de nome (§10.7.3)
ADERENCIA = "Aderência dia a dia"
_RE_DIA = re.compile(r"^\d{2}/\d{2} (SEG|TER|QUA|QUI|SEX|SÁB|DOM)$")
_RE_ACUM = re.compile(r"^% ADERÊNCIA ACUM\. ATÉ \d{2}/\d{2}$")

# juntas (§10.7.2): rid -> aba -> ((título do quadro, título da tabela, liga), ...)
JUNTAS = {
    ("pv_pedidos", "Pedidos"): (
        ("Gerar ID de separação CD", "Gerar separação CD", ["PEDIDOS", "PEDIDO", "|"]),
        ("Gerar reversa de lojas", "Gerar reversa de lojas", ["PEDIDOS", "PEDIDO", "|"]),
        ("Analítico por pedido", "Analítico produto", ["PEDIDO", "PEDIDO", None])),
    ("pl_entregas", "Entregas"): (
        ("Pendências dos meses anteriores", "Pendências dos meses anteriores", None),),
}
# selo permitido por coluna (§10.7.2): "faixa" (chip em lista), "barra", "tom" (chip_tom), "texto" (chip em dict)
SELOS = {
    "Pedidos": {"SLA": "faixa", "% ATENDIDO": "barra"},
    "Entregas": {"SLA": "tom", "PRAZO": "texto"},
    "Pendências dos meses anteriores": {"SLA": "tom", "PRAZO": "texto"},
    "Por supervisor": {"% META": "faixa"}, "Por vendedor": {"% META": "faixa"},
    "Dia a dia": {"% META": "faixa"},
}
# T-0023 v2: o selo por (rid, título), quando o título sozinho não basta (§10.10.2)
SELOS_RID = {
    ("pl_garantias", "Garantias"): {"STATUS": "texto", "SLA ATUAL": "tom", "PRAZO": "texto"},
    ("pl_garantias", "Status x resultado"): {"STATUS": "texto"},
    ("pl_ncc", "NCC pendentes"): {"SLA NCC": "texto"},
}
# tabelas que levam `uf_linhas` e `kpis_padrao` etc. não têm lista própria: o formato basta.

PROIBIDAS = {"edicao", "editar", "abrir", "detalhe", "kpis_de", "total_de", "totais_por", "recortes",
             "ordem_exportar", "cores_celulas", "so_exportar", "solicitacao_bap", "nota_pdf",
             "garantia", "campanha_export", "detalhe_pedido"}
# dentro dos cartões (`kpis_padrao`) "detalhe" é o texto do cartão; as outras chaves de ação nunca
PROIBIDAS_KPI = (PROIBIDAS - {"detalhe"}) | {"edicao", "editar", "abrir", "tabelas", "juntas", "cobranca", "kpis_de"}
CHAVES_TABELA = {"titulo", "colunas", "linhas", "tons", "total", "filtros", "kpis_padrao", "recortes_linhas",
                 "uf_linhas", "zebra"}
CHAVES_META = {"grupos", "top_n", "ordem_top", "juntas_em_cima", "titulo_tabela"}      # T-0022: só no vc_meta
CHAVES_COLUNA = {"nome", "tipo", "largura", "larg_fixa", "oculta", "chip", "barra", "chip_tom", "inteira", "curto"}
CHAVES_JUNTA = {"titulo", "liga", "mostrar", "tabela"}
TONS = {"", "ok", "alerta", "atencao", "info", "azul", "cinza", "grave"}
TIPOS_SUB = {"texto", "num", "data"}
NUM_TIPOS = {"int", "num", "num1", "num2", "moeda", "moeda2", "pct", "pct1", "valor"}
TIPOS = NUM_TIPOS | {"texto", "dia", "data", "hora"}
# paleta fixa do selo pela linha (bap_visual.py), §10.7.2
PALETA_TOM = {"ok": (marca.TOKENS["--ok-claro"], marca.TOKENS["--verde-escuro"]),      # (fundo, texto) do selo pela linha
              "atencao": (marca.TOKENS["--atencao-claro"], marca.TOKENS["--atencao-texto"]),
              "alerta": (marca.TOKENS["--alerta-claro"], marca.TOKENS["--alerta"]),
              "cinza": (marca.TOKENS["--borda"], marca.TOKENS["--suave"])}
MAX_LINHAS = 60000
MAX_RECORTES = 20
MAX_OPCOES = 300
JUNTA_MAX = 200
# T-0033 (RD-0032): a tela rola por dentro da tabela, sem páginas de 100; a página traz até 500 linhas e o navegador pede mais 500 ao rolar (contrato visual §7.2)
# textos do contrato do relatório (§10.7.6), mantidos para o contrato; o layout BC3 diz o mesmo na faixa ("sem o filtro", "BAP inteira")
AVISO_SEM_ESTADO = "Sem filtro por estado: esta tabela mostra a BAP inteira."
AVISO_CARTOES = "Cartões sem filtro. Com filtro, veja as linhas na tabela."
PAGINA_TAM = 500
RE_UF = re.compile(r"^[A-Z]{2}$")
RE_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")
# CPF/CNPJ já formatado dentro de uma célula: o PC deveria ter limpado (RN-GER-011); a web recusa
RE_DOC = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# ------------------------------------------------------------------ validação (§10.7.6)
def _proibida(o, nivel=0) -> str | None:
    if nivel > 10:
        return "aninhado demais"
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, str) and (k in PROIBIDAS_KPI or k.startswith("_") or k.startswith("exportar")
                                       or k.startswith("pdf")):
                return k[:20]
            achou = _proibida(v, nivel + 1)
            if achou:
                return achou
    elif isinstance(o, list):
        for v in o:
            achou = _proibida(v, nivel + 1) if isinstance(v, (dict, list)) else None
            if achou:
                return achou
    return None


def _celula_ok(v, tipo) -> bool:
    """Célula de linha: `null`, ou o valor do tipo; `""` vale em qualquer tipo (o PC deixa célula em branco)."""
    if v is None or v == "":
        return True
    if tipo in NUM_TIPOS:
        return _num(v)
    if tipo in ("dia", "data"):
        return isinstance(v, str) and (v == "" or bool(RE_DATA.match(v)))
    if tipo == "hora":
        return isinstance(v, str) and len(v) <= 12
    if isinstance(v, str):
        return len(v) <= 2000
    return _num(v)


def _celula_sub_ok(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return len(v) <= 2000
    return _num(v)


def _total_ok(tot, tipos) -> bool:
    """§10.7.2.1: uma célula por coluna; `null` ou o valor do tipo (texto só em texto e hora)."""
    return (isinstance(tot, list) and len(tot) == len(tipos)
            and all(v is None or (_celula_ok(v, tp) and v != "") for v, tp in zip(tot, tipos)))


def _cols_esperadas(titulo: str, cols, rid: str = "") -> list | None:
    """A lista do §10.7.3 (e do §10.11.3, por rid); na "Aderência dia a dia" ela sai dos nomes (padrão), None se não bate."""
    if (rid, titulo) in COLUNAS_RID:
        return COLUNAS_RID[(rid, titulo)]
    if titulo != ADERENCIA:
        return COLUNAS.get(titulo)
    nomes = [c.get("nome") if isinstance(c, dict) else None for c in cols]
    n = len(nomes)
    if not (4 <= n <= 34 and nomes[:2] == ["SUPERVISOR", "VENDEDOR"]):
        return None
    meio = nomes[2:-1]
    if not (all(isinstance(x, str) and _RE_DIA.match(x) for x in meio)
            and isinstance(nomes[-1], str) and _RE_ACUM.match(nomes[-1])):
        return None
    return [_c("SUPERVISOR"), _c("VENDEDOR")] + [_c(x, "pct") for x in meio] + [_c(nomes[-1], "pct")]


def _chip_texto_ok(chip) -> bool:
    return isinstance(chip, dict) and len(chip) <= 60 and all(
        isinstance(k, str) and len(k) < 60 and isinstance(v, (list, tuple)) and len(v) == 2
        and all(isinstance(x, str) and RE_COR.match(x) for x in v) for k, v in chip.items())


def _faixas_ok(fx, numerica=True) -> bool:
    if not (isinstance(fx, list) and 0 < len(fx) <= 20):
        return False
    for f in fx:
        if not (isinstance(f, (list, tuple)) and len(f) == 3):
            return False
        ate, fundo, texto = f
        if not (ate is None or _num(ate)):
            return False
        if not all(x is None or (isinstance(x, str) and RE_COR.match(x)) for x in (fundo, texto)):
            return False
    return True


def _selo_ok(c, forma, nomes_ocultas) -> bool:
    """O selo que a coluna traz bate com o permitido para ela (§10.7.2)."""
    presentes = {k for k in ("chip", "barra", "chip_tom") if c.get(k) is not None}
    if not presentes:
        return True
    if forma == "faixa":
        return presentes == {"chip"} and _faixas_ok(c["chip"])
    if forma == "barra":
        b = c.get("barra")
        return (presentes == {"barra"} and isinstance(b, dict) and set(b) == {"max", "faixas"}
                and _num(b["max"]) and b["max"] > 0 and _faixas_ok(b["faixas"]))
    if forma == "tom":
        return presentes == {"chip_tom"} and isinstance(c["chip_tom"], str) and c["chip_tom"] in nomes_ocultas
    if forma == "texto":
        return presentes == {"chip"} and _chip_texto_ok(c["chip"])
    return False


def _esperado_livre(cols) -> list | None:
    """Farol livre: a lista esperada sai das próprias colunas (nome, tipo, oculta); só o formato é conferido."""
    if not (isinstance(cols, list) and 0 < len(cols) <= 60):
        return None
    saida = []
    for c in cols:
        if not (isinstance(c, dict) and isinstance(c.get("nome"), str) and 0 < len(c["nome"]) <= 80
                and c.get("tipo") in TIPOS and not c["nome"].startswith("_")):
            return None
        saida.append(_c(c["nome"], c["tipo"], bool(c.get("oculta"))))
    return saida if len({x[0] for x in saida}) == len(saida) else None


def _selo_livre(c) -> str | None:
    if isinstance(c.get("chip"), dict):
        return "texto"
    if isinstance(c.get("chip"), list):
        return "faixa"
    if c.get("barra") is not None:
        return "barra"
    return "tom" if c.get("chip_tom") is not None else None


def _cols_meta(cols) -> list | None:
    """T-0022: no Farol de Metas as colunas vêm do próprio PC (muitas, com grupos): confere só o formato."""
    if not (isinstance(cols, list) and 0 < len(cols) <= 60):
        return None
    out = []
    for c in cols:
        if not (isinstance(c, dict) and isinstance(c.get("nome"), str) and 0 < len(c["nome"]) <= 60
                and c.get("tipo") in TIPOS and (c.get("curto") is None or (isinstance(c["curto"], str) and len(c["curto"]) <= 40))):
            return None
        out.append(_c(c["nome"], c["tipo"], bool(c.get("oculta"))))
    return out


def _colunas_erro(titulo, cols, rid="", livre=False) -> tuple[str | None, list]:
    fora = FORA_POR_TABELA.get((rid, titulo), ())
    if fora and isinstance(cols, list) and any(isinstance(c, dict) and c.get("nome") in fora for c in cols):
        return "coluna que não vai ao site (contato do cliente)", []
    esperado = (_esperado_livre(cols) if livre
                else _cols_meta(cols) if rid == "vc_meta"
                else _cols_esperadas(titulo, cols if isinstance(cols, list) else [], rid))
    if esperado is None:
        return "colunas diferentes da lista do contrato", []
    if not (isinstance(cols, list) and len(cols) == len(esperado)):
        return "colunas diferentes da lista do contrato", []
    ocultas = {n for n, _, o in esperado if o}
    selos = ({n: "faixa" for n, _, _ in esperado} if rid == "vc_meta" else SELOS_RID.get((rid, titulo), SELOS.get(titulo, {})))
    if titulo == ADERENCIA:                    # T-0033: o quadrado de cada dia pode vir com a faixa de cor do PC (opcional)
        selos = {n: "faixa" for n, tp, _ in esperado if tp == "pct"}
    for c, (n, tp, o) in zip(cols, esperado):
        if livre:
            selos = {n: _selo_livre(c)}
        if not (isinstance(c, dict) and not (set(c) - CHAVES_COLUNA) and c.get("nome") == n
                and c.get("tipo") == tp and bool(c.get("oculta")) == o):
            return "colunas diferentes da lista do contrato", []
        if coluna_fora(n):
            return "coluna que não vai ao site (telefone, CNPJ, CPF, e-mail, contato, foto, endereço)", []
        if not (c.get("largura") is None or _int(c["largura"])) or not (c.get("larg_fixa") is None or _int(c["larg_fixa"])):
            return "largura inválida", []
        if c.get("inteira") is not None and not isinstance(c["inteira"], bool):
            return "inteira inválida", []
        if not _selo_ok(c, selos.get(n), ocultas):
            return "selo fora das colunas marcadas ou mal formado", []
    return None, esperado


def _kpis_ok(ks) -> bool:
    from . import pacotes                      # tardio: pacotes importa este módulo
    return pacotes._kpis_ok(ks)


def _tabela_erro(t, titulo, nivel="aba", rid="") -> str | None:
    """`nivel`: "aba" (com juntas/subabas), "junta" ou "sub" (sub-aba da Solicitação BAP)."""
    if not isinstance(t, dict) or t.get("titulo") != titulo:
        return "titulo inesperado"
    permitidas = (set(CHAVES_TABELA) | ({"juntas", "subabas"} if nivel == "aba" else set())
                  | (CHAVES_META if rid == "vc_meta" else set()))
    if (rid, titulo) in edicoes.LUGARES and nivel != "sub":
        permitidas.add("edicao")                        # T-0021: edição na web (só o admin)
    if nivel == "sub":
        permitidas = {"titulo", "colunas", "linhas", "tons", "filtros", "total"}
    extra = set(t) - permitidas
    if extra:
        return f"chave não aceita: {sorted(extra)[0][:20]}"
    achou = _proibida(t.get("kpis_padrao"))
    if achou:
        return f"chave não aceita: {achou}"
    cols, linhas = t.get("colunas"), t.get("linhas")
    if not (isinstance(cols, list) and isinstance(linhas, list)) or len(linhas) > MAX_LINHAS:
        return "colunas ou linhas inválidas"
    if nivel == "sub":
        return _sub_erro(t, cols, linhas)
    if nivel == "aba" and titulo == "Solicitação BAP":
        if cols or linhas or not isinstance(t.get("subabas"), list) or not t["subabas"]:
            return "Solicitação BAP precisa de subabas e de colunas/linhas vazias"
        return _subabas_erro(t["subabas"])
    erro, esperado = _colunas_erro(titulo, cols, rid, livre=rid in FAROIS_LIVRES and nivel == "aba")
    if erro:
        return erro
    n = len(esperado)
    tipos = [tp for _, tp, _ in esperado]
    for ln in linhas:
        if not (isinstance(ln, list) and len(ln) == n and all(_celula_ok(v, tp) for v, tp in zip(ln, tipos))):
            return "linha com número de células ou valores inválidos"
    if (rid, titulo) == ("an_divergencias", "Sem coordenada / endereço"):
        k = [x[0] for x in esperado].index("PONTO")
        if any(isinstance(ln[k], str) and RE_COORD.search(ln[k]) for ln in linhas):
            return "coluna PONTO com coordenada"          # §10.11.2: o endereço e a coordenada ficam no PC
    tons = t.get("tons")
    if tons is not None and not (isinstance(tons, list) and len(tons) == len(linhas)
                                 and all(isinstance(x, str) and x in TONS for x in tons)):
        return "tons inválidos"
    if t.get("total") is not None and not _total_ok(t["total"], tipos):
        return "total inválido"
    nomes = [x[0] for x in esperado]
    fl = t.get("filtros", [])
    if not isinstance(fl, list):
        return "filtros inválidos"
    for f in fl:
        col = f if isinstance(f, str) else (f.get("coluna") if isinstance(f, dict) else None)
        if col not in nomes or (isinstance(f, dict) and set(f) - {"coluna", "padrao", "multi", "oculto"}):
            return "filtro fora da lista de colunas"
    if t.get("kpis_padrao") is not None and not _kpis_ok(t["kpis_padrao"]):
        return "kpis_padrao inválidos"
    rl = t.get("recortes_linhas")
    if rl is not None:
        if not (isinstance(rl, list) and len(rl) <= MAX_RECORTES):
            return "recortes_linhas inválidos"
        for r in rl:
            if not (isinstance(r, dict) and set(r) == {"rotulo", "linhas"} and isinstance(r["rotulo"], str)
                    and len(r["rotulo"]) <= 80 and isinstance(r["linhas"], list)
                    and all(_int(i) and 0 <= i < len(linhas) for i in r["linhas"])):
                return "recortes_linhas fora de linhas"
    uf = t.get("uf_linhas")
    if uf is not None and not (isinstance(uf, list) and len(uf) == len(linhas)
                               and all(isinstance(x, str) and (x == "" or RE_UF.match(x)) for x in uf)):
        return "uf_linhas inválidas"
    if t.get("zebra") is not None and not isinstance(t["zebra"], bool):
        return "zebra inválida"
    if "edicao" in t:
        e = edicoes.erro_spec(rid, titulo, t["edicao"], [c["nome"] for c in cols], len(linhas))
        if e:
            return e
    if rid == "vc_meta":
        erro = _meta_erro(t, n)
        if erro:
            return erro
        return _juntas_meta_erro(t, rid) if nivel == "aba" else None
    if nivel == "aba":
        return _juntas_erro(t, titulo, rid)
    return None


def _meta_erro(t, n) -> str | None:
    """T-0022: grupos do cabeçalho, Top N, ordem do Top e título do quadro (Farol de Metas)."""
    g = t.get("grupos")
    if g is not None and not (isinstance(g, list) and 0 < len(g) <= 30 and all(
            isinstance(x, list) and len(x) == 2 and isinstance(x[0], str) and len(x[0]) <= 40 and _int(x[1]) and x[1] > 0
            for x in g) and sum(x[1] for x in g) == n):
        return "grupos inválidos"
    if t.get("top_n") is not None and not (_int(t["top_n"]) and 0 < t["top_n"] <= 500):
        return "top_n inválido"
    o = t.get("ordem_top")
    if o is not None and not (isinstance(o, list) and len(o) == 2 and all(_int(i) and 0 <= i < n for i in o)):
        return "ordem_top inválida"
    if t.get("juntas_em_cima") is not None and not isinstance(t["juntas_em_cima"], bool):
        return "juntas_em_cima inválida"
    tt = t.get("titulo_tabela")
    if tt is not None and not (isinstance(tt, str) and len(tt) <= 60):
        return "titulo_tabela inválido"
    return None


def _juntas_meta_erro(t, rid) -> str | None:
    """Juntas do Farol de Metas (Equipe: Gerente e Supervisores): quadros de até 3, sem `liga`."""
    js = t.get("juntas")
    if js is None:
        return None
    if not (isinstance(js, list) and len(js) <= 3):
        return "juntas fora do lugar"
    for j in js:
        tj = j.get("tabela") if isinstance(j, dict) else None
        if not (isinstance(tj, dict) and not (set(j) - {"titulo", "tabela"}) and isinstance(tj.get("titulo"), str)
                and isinstance(j.get("titulo"), str)):
            return "junta mal formada"
        e = _tabela_erro(tj, tj["titulo"], "junta", rid)
        if e:
            return "junta: " + e
    return None


def _sub_erro(t, cols, linhas) -> str | None:
    if not (isinstance(cols, list) and 0 < len(cols) <= 60):
        return "subaba: colunas inválidas"
    for c in cols:
        if not (isinstance(c, dict) and not (set(c) - {"nome", "tipo", "largura", "larg_fixa", "oculta"})
                and isinstance(c.get("nome"), str) and c.get("tipo") in TIPOS_SUB):
            return "subaba: coluna com tipo fora de texto, num e data"
        if coluna_fora(c["nome"]):
            return "subaba: coluna que não vai ao site (telefone, CNPJ, CPF, e-mail, contato, foto, endereço)"
    n = len(cols)
    if not all(isinstance(ln, list) and len(ln) == n and all(_celula_sub_ok(v) for v in ln) for ln in linhas):
        return "subaba: linha com número de células ou valores inválidos"
    tons = t.get("tons")
    if tons is not None and not (isinstance(tons, list) and len(tons) == len(linhas)
                                 and all(isinstance(x, str) and x in TONS for x in tons)):
        return "subaba: tons inválidos"
    if t.get("filtros") not in (None, []):                      # a Solicitação BAP não tem filtros (§10.7.2)
        return "subaba: filtros fora do contrato"
    if t.get("total") is not None and not _total_ok(t["total"], [c["tipo"] for c in cols]):
        return "total inválido"
    return None


def _subabas_erro(subs) -> str | None:
    pos = -1
    for s in subs:
        titulo = s.get("titulo") if isinstance(s, dict) else None
        if titulo not in SUBABAS or SUBABAS.index(titulo) <= pos:
            return "subaba fora da lista, fora da ordem ou repetida"
        pos = SUBABAS.index(titulo)
        e = _tabela_erro(s, titulo, "sub")
        if e:
            return e
    return None


def _juntas_erro(t, titulo_aba, rid) -> str | None:
    js = t.get("juntas")
    esperado = JUNTAS.get((rid, titulo_aba), ())
    if js is None:
        return None
    if not (isinstance(js, list) and len(js) <= len(esperado)):
        return "juntas fora do lugar"
    pos = -1
    for j in js:
        if not (isinstance(j, dict) and not (set(j) - CHAVES_JUNTA) and isinstance(j.get("tabela"), dict)):
            return "junta mal formada"
        ach = [k for k, (tq, _, _) in enumerate(esperado) if tq == j.get("titulo")]
        if not ach or ach[0] <= pos:
            return "junta fora do lugar, fora da ordem ou repetida"
        pos = ach[0]
        tq, tt, liga = esperado[pos]
        if j.get("liga") != liga:
            return "junta com liga diferente do contrato"
        e = _tabela_erro(j["tabela"], tt, "junta", rid)
        if e:
            return "junta: " + e
        nomes = [c["nome"] for c in j["tabela"]["colunas"]]
        m = j.get("mostrar")
        if m is not None and not (isinstance(m, list) and all(isinstance(x, str) and x in nomes for x in m)):
            return "junta: mostrar cita coluna que não existe"
        if liga and not (liga[0] in nomes):
            return "junta: coluna da liga ausente"
    return None


def validar(rid: str, r: dict) -> list[str]:
    """Erros de `tabelas` de um farol (§10.7.6). Mensagens sem dado pessoal. `cobranca` aqui nunca vale."""
    if "cobranca" in r:
        return [f"{rid}: cobranca só no pl_inadimplencia"]
    if "tabelas" not in r:
        return []
    if rid not in RIDS:
        return [f"{rid}: tabelas só nos faróis com abas de tabela"]
    ts = r["tabelas"]
    if rid in FAROIS_LIVRES:
        if not isinstance(ts, list) or len(ts) > 20:
            return [f"{rid}: tabelas precisa ser lista de até 20 abas"]
        titulos = [t.get("titulo") if isinstance(t, dict) else None for t in ts]
        if not all(isinstance(x, str) and 0 < len(x) <= 80 for x in titulos) or len(set(titulos)) != len(titulos):
            return [f"{rid}: tabela com titulo ausente ou repetido"]
        ordem = titulos
    else:
        if not isinstance(ts, list) or len(ts) > len(ABAS[rid]):
            return [f"{rid}: tabelas precisa ser lista de até {len(ABAS[rid])} abas"]
        ordem = [t for _, t in ABAS[rid]]
    pos = -1
    for t in ts:
        titulo = t.get("titulo") if isinstance(t, dict) else None
        if titulo not in ordem or ordem.index(titulo) <= pos:
            return [f"{rid}: tabela com titulo fora da lista, fora da ordem ou repetida"]
        pos = ordem.index(titulo)
        e = _tabela_erro(t, titulo, "aba", rid)
        if e:
            return [f"{rid}: tabela {titulo}: {e}"]
    return []


# ------------------------------------------------------------------ documento em texto: só a aba cai (W2)
_RE_AVISO_FORA = re.compile(r"^" + re.escape(AVISO_ABAS_FORA).replace(r"\{lista\}", "(.+)") + "$")


def _celulas_com_documento(linhas) -> bool:
    return any(isinstance(v, str) and RE_DOC.search(v) for ln in linhas if isinstance(ln, list) for v in ln)


def _aba_tem_documento(t: dict) -> bool:
    """CPF/CNPJ já formatado em célula de texto de qualquer parte da aba (linhas, total, juntas, sub-abas)."""
    partes = [t] + [j["tabela"] for j in t.get("juntas") or []] + list(t.get("subabas") or [])
    return any(_celulas_com_documento(list(p.get("linhas") or []) + [p.get("total") or []]) for p in partes)


# T-0036 (revisão 🟢): a OBSERVAÇÃO da Pesquisa de mercado é digitada no campo; o PC limpa e a web limpa de novo
# (defesa em profundidade). O padrão é o do texto livre das edições (`edicoes.RE_PESSOAL`), com o e-mail inteiro.
LIMPA_TEXTO = {("vc_preco", "Pesquisa de mercado"): ("OBSERVAÇÃO",)}
_RE_LIMPA = re.compile("|".join(r.pattern for r in edicoes.RE_PESSOAL))   # mesmos 4 padrões (e-mail, CNPJ/CPF, telefone)
REMOVIDO = "[removido]"          # o mesmo texto do robô (`relatorios_nucleo.texto_sem_contato`, RN-GER-011)


def limpar_texto(t: str) -> str:
    """Troca CPF, CNPJ, telefone e e-mail de um texto livre por "[removido]" (RN-GER-011, regra 6 do CLAUDE.md)."""
    return _RE_LIMPA.sub(REMOVIDO, t)


def limpar_textos_livres(corpo: dict) -> int:
    """Passa `limpar_texto` nas colunas de `LIMPA_TEXTO`; devolve quantas células mudaram."""
    n = 0
    for (rid, titulo), nomes in LIMPA_TEXTO.items():
        rel = (corpo.get("relatorios") or {}).get(rid)
        for t in (rel.get("tabelas") or []) if isinstance(rel, dict) else ():
            if not isinstance(t, dict) or t.get("titulo") != titulo:
                continue
            idx = [i for i, c in enumerate(t.get("colunas") or []) if isinstance(c, dict) and c.get("nome") in nomes]
            for ln in t.get("linhas") or []:
                for i in idx:
                    if isinstance(ln, list) and i < len(ln) and isinstance(ln[i], str) and _RE_LIMPA.search(ln[i]):
                        ln[i] = limpar_texto(ln[i])
                        n += 1
    return n


def tirar_abas_com_documento(corpo: dict) -> list[str]:
    """Defesa da web (RN-GER-011): a aba com CPF/CNPJ formatado numa célula sai do pacote, com o aviso
    `AVISO_ABAS_FORA`; o resto do pacote (Painel, Inadimplência, as outras abas) segue. Devolve os títulos."""
    fora_todas: list[str] = []
    for rid in RIDS:
        rel = (corpo.get("relatorios") or {}).get(rid)
        if not isinstance(rel, dict) or not isinstance(rel.get("tabelas"), list):
            continue
        for r_uf in (rel.get("recortes") or {}).values() if rid == "vc_meta" else ():   # T-0022: as abas do estado
            if isinstance(r_uf, dict) and isinstance(r_uf.get("tabelas"), list):
                r_uf["tabelas"] = [t for t in r_uf["tabelas"] if not _aba_tem_documento(t)]
        fora = [t["titulo"] for t in rel["tabelas"] if _aba_tem_documento(t)]
        if not fora:
            continue
        rel["tabelas"] = [t for t in rel["tabelas"] if t["titulo"] not in fora]
        avisos = [a for a in rel.get("avisos") or [] if isinstance(a, str)]
        ja = []
        for a in avisos:
            m = _RE_AVISO_FORA.match(a)
            if m:
                ja += m.group(1).split(", ")
        lista = [x for _, x in (ABAS.get(rid) or [(0, y) for y in (ja + fora)]) if x in set(ja) | set(fora)]
        avisos = [a for a in avisos if not _RE_AVISO_FORA.match(a)]
        rel["avisos"] = [AVISO_ABAS_FORA.format(lista=", ".join(lista))] + avisos
        fora_todas += fora
    return fora_todas


# ------------------------------------------------------------------ apresentação
def _chave_ordem(v, tipo):
    if v is None or v == "" or v == "—":
        return (1, 0, "")
    if tipo in NUM_TIPOS and _num(v):
        return (0, v, "")
    return (0, 0, str(v).casefold())


def _faixa_de(v, faixas):
    """bap_visual.Tabela._faixa_de: a primeira faixa com `valor <= ate` (None = sem teto)."""
    for ate, fundo, texto in faixas:
        if ate is None or v <= ate:
            return fundo, texto
    return None, None


def _norm_liga(v, sep) -> set[str]:
    partes = str(v if v is not None else "").split(sep) if sep else [str(v if v is not None else "")]
    return {p.replace(" ", "").lstrip("0") or "0" for p in partes if p.replace(" ", "")}


def _filtros(t, cols, consulta, todas):
    """(lista para a tela, lista de (i, valores escolhidos) a aplicar)."""
    nomes = [c["nome"] for c in cols]
    tela, aplicar = [], []
    for f in t.get("filtros") or []:
        nome = f if isinstance(f, str) else f["coluna"]
        if nome not in nomes:
            continue
        i = nomes.index(nome)
        padrao = f.get("padrao") if isinstance(f, dict) else None
        multi = bool(isinstance(f, dict) and f.get("multi"))
        oculto = bool(isinstance(f, dict) and f.get("oculto"))
        pad = [str(padrao)] if padrao not in (None, "") else []
        chave = f"f{i}"
        if oculto:                                      # só o padrão: a pessoa não escolhe (MÊS do Pedidos)
            sel = pad
        elif chave in consulta:
            sel = [v for v in consulta[chave] if v != ""]
        else:
            sel = pad
        if sel:
            aplicar.append((i, sel))
        if oculto:
            continue
        opcoes = sorted({str(ln[i]) for ln in todas if ln[i] not in (None, "")}, key=str.casefold)
        tela.append({"nome": nome, "chave": chave, "i": i, "multi": multi, "opcoes": opcoes[:MAX_OPCOES],
                     "sel": sel, "padrao": pad})
    return tela, aplicar


def _celula_tela(v, k, row, cols, tipo, centavos):
    """{"t", "f", "c", "b"}: texto, fundo e letra do selo, barra (largura %, cor)."""
    c = cols[k]
    out = {"t": fmt_celula(v, tipo, centavos), "f": None, "c": None, "b": None}
    if v is None or v == "":
        return out
    chip = c.get("chip")
    if isinstance(chip, dict):                          # selo por texto (§10.6.2)
        alvo = str(v).strip().upper()
        cor = next((x for ch, x in chip.items() if str(ch).strip().upper() == alvo), None)
        if cor:
            out["f"], out["c"] = cor[0], cor[1]
    elif isinstance(chip, list) and _num(v):            # selo por faixa
        fundo, texto = _faixa_de(v, chip)
        if fundo:
            out["f"], out["c"] = fundo, texto or marca.TEXTO
    elif isinstance(c.get("barra"), dict) and _num(v):
        b = c["barra"]
        fundo, texto = _faixa_de(v, b["faixas"])
        out["b"] = {"w": round(max(0.0, min(1.0, v / b["max"])) * 100, 1), "f": fundo or marca.TOKENS["--grafico-3"]}
        out["c"] = texto
    elif isinstance(c.get("chip_tom"), str):            # selo pela linha (coluna oculta pelo nome)
        j = next((i for i, x in enumerate(cols) if x["nome"] == c["chip_tom"]), None)
        cor = PALETA_TOM.get(str(row[j]).strip().lower()) if j is not None and j < len(row) else None
        if cor:
            out["f"], out["c"] = cor
    return out


def _tela_basica(t, idxs, vista, centavos):
    cols = t["colunas"]
    tons = t.get("tons") or []
    return [{"tom": tons[k] if k < len(tons) else "", "k": k,
             "cel": [_celula_tela(t["linhas"][k][c], c, t["linhas"][k], cols, cols[c]["tipo"], centavos)
                     for c in vista]} for k in idxs]


def _vista(t, ordem_tela=None):
    cols = t["colunas"]
    ordem = ordem_tela if ordem_tela is not None else list(range(len(cols)))
    return [k for k in ordem if not cols[k].get("oculta")]


def _cabecalho(t, vista):
    cols = t["colunas"]
    # T-0022: com cabeçalho agrupado (Farol de Metas) vale o nome curto, como na tela do PC
    nome = lambda k: (cols[k].get("curto") if t.get("grupos") and cols[k].get("curto") else cols[k]["nome"])  # noqa: E731
    return [{"i": k, "nome": nome(k), "tipo": cols[k]["tipo"],
             "num": cols[k]["tipo"] in NUM_TIPOS,
             "inteira": bool(cols[k].get("inteira")), "livre": cols[k]["nome"] in LIVRES} for k in vista]


def _grupos_tela(t, vista):
    """T-0022: o cabeçalho agrupado (FATURAMENTO · POSITIVAÇÃO ...) sobre as colunas que aparecem, na ordem do PC;
    só quando a ordem das colunas é a do PC (sem coluna fixa à frente)."""
    gs = t.get("grupos")
    if not gs or vista != sorted(vista):
        return None
    out, ini = [], 0
    for nome, n in gs:
        qtd = sum(1 for k in vista if ini <= k < ini + n)
        if qtd:
            out.append({"nome": nome, "n": qtd})
        ini += n
    return out


def tabela_para_tela(t: dict, consulta: dict, *, uf: str | None = None, pagina_tam: int = PAGINA_TAM,
                     ordem_tela=None, centavos: bool = False, total_sempre: bool = False,
                     vazios_no_fim: bool = True, titulo: str | None = None,
                     excluir: frozenset = frozenset(), rid: str = "") -> dict:
    """Filtra, ordena e pagina no servidor (genérica: Inadimplência e as abas do §10.7).

    `consulta`: f<i> (lista de valores), rec (índice do recorte), ord, dir, pag. `uf`: estado escolhido
    (só vale se a tabela traz `uf_linhas`). `ordem_tela`: ordem das colunas na tela (lista de índices).
    `total_sempre`: mostra a linha de total mesmo com filtro (Inadimplência); sem ele, só sem filtro (§10.7.2).
    `vazios_no_fim`: na ordem decrescente a célula vazia vai para o fim (a Inadimplência mantém o jeito de antes).
    """
    cols, todas = t["colunas"], t["linhas"]
    n = len(todas)
    filtros, aplicar = _filtros(t, cols, consulta, todas)
    idxs = [k for k in range(n) if k not in excluir]        # T-0029: linhas que o usuário pediu para ignorar
    ufl = t.get("uf_linhas")
    uf_aplicada = bool(uf and ufl)
    if uf_aplicada:
        idxs = [k for k in idxs if ufl[k] == uf]
    for i, sel in aplicar:
        idxs = [k for k in idxs if str(todas[k][i]) in sel]
    # busca livre (pedido do Alexandre, 26/11: "cadê o filtro por pedido?"): pedido, cliente, produto...
    busca = " ".join(str(consulta.get("busca", [""])[0]).split()).upper()[:60]
    if busca:
        idxs = [k for k in idxs if any(busca in str(v).upper() for v in todas[k] if v is not None)]
    # recortes (§11.4): índices prontos do PC
    recs = t.get("recortes_linhas") or []
    try:
        rec = int(consulta.get("rec", [""])[0])
    except ValueError:
        rec = None
    rec = rec if rec is not None and 0 <= rec < len(recs) else None
    base = set(idxs)
    recortes = [{"n": q, "rotulo": r["rotulo"], "qtd": len(base.intersection(r["linhas"])),
                 "ativo": q == rec} for q, r in enumerate(recs)]
    if rec is not None:
        dentro = set(recs[rec]["linhas"])
        idxs = [k for k in idxs if k in dentro]
    ordem = consulta.get("ord", [""])[0]
    desc = consulta.get("dir", ["asc"])[0] == "desc"
    j = int(ordem) if ordem.isdigit() and int(ordem) < len(cols) else None
    if t.get("top_n"):          # T-0022 (Top 30 clientes): o filtro corre na carteira e o top se refaz dentro dele
        idxs = idxs[:t["top_n"]]
        if t.get("ordem_top") and j is None:            # o top: da maior meta, como o PC
            i_m, i_f = t["ordem_top"]
            idxs.sort(key=lambda k: (-(todas[k][i_m] or 0), -(todas[k][i_f] or 0)))
    if j is not None:
        chave = lambda k: _chave_ordem(todas[k][j], cols[j]["tipo"])  # noqa: E731
        if desc and vazios_no_fim:
            cheios = [k for k in idxs if chave(k)[0] == 0]
            idxs = sorted(cheios, key=chave, reverse=True) + [k for k in idxs if chave(k)[0] == 1]
        else:
            idxs = sorted(idxs, key=chave, reverse=desc)
    total = len(idxs)
    try:
        pag = max(1, int(consulta.get("pag", ["1"])[0]))
    except ValueError:
        pag = 1
    paginas = max(1, -(-total // pagina_tam))
    pag = min(pag, paginas)
    visiveis = idxs[(pag - 1) * pagina_tam: pag * pagina_tam]
    g_ord = GRADE.get((rid or "", t.get("titulo") or ""))
    if ordem_tela is None and g_ord and g_ord.get("grade"):
        # contrato §6.2: as colunas da grade, NESTA ordem (a chave pode não ser a primeira do pacote); o resto segue depois
        nm = [str(c["nome"]).upper() for c in cols]
        pri = [nm.index(n) for n in g_ord["grade"] if n in nm]
        if pri:
            ordem_tela = pri + [k for k in range(len(cols)) if k not in pri]
    if ordem_tela is None and FIXA.get(t.get("titulo")) in [c["nome"] for c in cols]:
        f0 = [c["nome"] for c in cols].index(FIXA[t["titulo"]])        # a coluna da linha vai à frente
        ordem_tela = [f0] + [k for k in range(len(cols)) if k != f0]
    vista = _vista(t, ordem_tela)
    padrao = (rec is None and not uf_aplicada
              and all(set(f["sel"]) == set(f["padrao"]) for f in filtros))
    tot = t.get("total")
    mostra_total = bool(tot) and (total_sempre or (total == n))
    tela = {
        "titulo": titulo or t.get("titulo", ""), "total_linhas": total, "pag": pag, "paginas": paginas,
        "cols": _cabecalho(t, vista), "grupos": _grupos_tela(t, vista),
        "em_cima": bool(t.get("juntas_em_cima")), "titulo_quadro": t.get("titulo_tabela") or "",
        "linhas": _tela_basica(t, visiveis, vista, centavos),
        "total": ([_celula_tela(tot[c], c, tot, cols, cols[c]["tipo"], centavos) for c in vista]
                  if mostra_total else None),
        "filtros": filtros, "ord": j, "desc": desc, "recortes": recortes, "rec": rec,
        "padrao": padrao and not busca, "busca": busca,
        "filtrado": rec is not None or bool(busca) or any(set(f["sel"]) != set(f["padrao"]) for f in filtros),
        "uf_aplicada": uf_aplicada, "zebra": bool(t.get("zebra")),
        "idxs": idxs,                                   # as linhas visíveis (todas as páginas), para as juntas
    }
    cliente_so_nome(tela)
    return preparar_grade(tela, rid)


# T-0033 (contrato visual BC3, §6): em TODOS os faróis a tabela é uma GRADE de no máximo 10 colunas de dado (cabe a 1366
# sem rolagem lateral) mais o POPUP da linha, aberto na coluna-chave. O que não está na grade vai ao popup, em blocos;
# no celular a linha fechada mostra chave, nome, selo e valor, e a aberta mostra o resto. O Excel e o PDF levam todas as colunas.
#   chave: coluna sublinhada que abre o popup · grade: colunas da tela, na ordem do PC (a que não vier no pacote sai sem erro)
#   blocos: ((título, colunas), ...) do popup; o que não está na grade nem num bloco vai para "Outros"
#   cel: (chave, nome, selo, valor) da linha fechada no celular; None onde não houver
# Os faróis novos da migração (T-0023 a T-0043) acrescentam as linhas deles AQUI, no PR que os traz.
_BL_VIS = (("Cadastro", ("CAD.",)),
           ("Jornada", ("INÍCIO", "ÚLT. ATIV.", "DIAS < JORN. LÍQ.", "INTERV. ALMOÇO", "DIAS ALMOÇO > MÁX.")),
           ("Tempo", ("TMA", "TMD")), ("Rota", ("KM", "KM/CLIENTE")))
_BL_ENT = (("Datas", ("DT. PED", "DT. NF", "DT. REAL")),
           ("Frete", ("VLR FRETE", "TBL FRETE", "VLR REAL FRETE", "RESPONSÁVEL")))
_METRICAS_VIS = ("META", "VISIT.", "% META", "% CONV.", "% FORA DE ROTA", "CAD. C/ COMPRA", "PROSP.", "JORNADA LÍQ.")
_GERAR = {"chave": "CÓD. PROD.", "grade": ("PEDIDOS", "CÓD. PROD.", "QTD", "COLETAR EM", "FILIAL DEST."),
          "cel": ("CÓD. PROD.", "DESCRIÇÃO", None, "QTD")}
_FAIXAS_DIAS = ("1–15 DIAS", "16–30 DIAS", "31–60 DIAS", "61–90 DIAS", "91–180 DIAS", "+180 DIAS")
_RESUMO_INAD = ("CARTEIRA ABERTA", "A VENCER", "EM ATRASO", "% INADIMPL.", "CLIENTES INADIMPL.")


def _resumo_inad(chave: str) -> dict:
    return {"chave": chave, "grade": (chave,) + _RESUMO_INAD, "blocos": (("Atraso por faixa", _FAIXAS_DIAS),),
            "cel": (chave, None, "% INADIMPL.", "EM ATRASO")}


GRADE: dict[tuple[str, str], dict] = {
    ("pv_pedidos", "Pedidos"): {
        "chave": "PEDIDO",
        "grade": ("DT. PED", "FATURAR ATÉ", "PEDIDO", "FANTASIA", "RAZÃO SOCIAL", "UF", "CIDADE", "R$ VENDA",
                  "% DESC.", "SLA", "% ATENDIDO"),                  # FANTASIA ou RAZÃO SOCIAL (uma só): 10 colunas
        "blocos": (("Cliente", ("RAZÃO SOCIAL", "CÓD.")), ("Crédito", ("LIMITE", "DISP.", "ATRASO", "COND. PAGTO")),
                   ("Pedido", ("ANÁLISE CRÉDITO", "SITUAÇÃO", "VENDEDOR", "PED. MÁX.", "VOL.", "R$ TABELA", "FILIAL",
                               "PRAZO")),
                   ("Nota", ("NF", "DT. NF"))),
        "cel": ("PEDIDO", "FANTASIA", "SLA", "R$ VENDA")},
    ("pv_pedidos", "Gerar separação CD"): _GERAR,
    ("pv_pedidos", "Gerar reversa de lojas"): _GERAR,
    ("pv_pedidos", "Analítico produto"): {
        "chave": "PEDIDO", "grade": ("PEDIDO", "CÓD. PROD.", "QTD", "FALTA", "VALOR FALTANTE"),
        "cel": ("PEDIDO", "DESCRIÇÃO", None, "VALOR FALTANTE")},
    ("pl_entregas", "Entregas"): {
        "chave": "NF", "blocos": _BL_ENT, "cel": ("NF", "CLIENTE", "SLA", "VLR NF"),
        "grade": ("NF", "CLIENTE", "CIDADE", "UF", "SITUAÇÃO", "SLA", "DT. PREVISTA", "ETAPA", "TRANSPORTADORA",
                  "VLR NF")},
    # T-0037 (desenho §7.1): 9 colunas na grade, com as editáveis; RESPONSÁVEL e o resto vão ao popup
    ("pl_fretes", "Notas com frete"): {
        "chave": "NF", "cel": ("NF", "CLIENTE", None, "VLR FRETE"),     # celular: a ETAPA vai ao item aberto
        "grade": ("NF", "CLIENTE", "CIDADE", "UF", "VLR FRETE", "ETAPA", "TRANSPORTADORA", "ENTREGAR ATÉ",
                  "ENTREGUE"),                     # 9 + a coluna Editar: cabe a 1366 sem rolagem (tela-bc3 §7.2)
        "blocos": (("Nota", ("DATA PED.", "DATA NF", "FILIAL", "VLR NF")), ("Entrega", ("SLA ENTREGA", "RESPONSÁVEL")))},
    ("pl_entregas", "Pendências dos meses anteriores"): {
        "chave": "NF", "blocos": _BL_ENT, "cel": ("NF", "CLIENTE", "SLA", "VLR NF"),
        "grade": ("MÊS", "NF", "CLIENTE", "SITUAÇÃO", "SLA", "DT. PREVISTA", "ETAPA", "VLR NF")},
    ("pl_inadimplencia", "Títulos"): {
        "chave": "NOME", "cel": ("NOME", None, "FAIXA", "SALDO"),
        "grade": ("NOME", "NF", "PARC.", "VENCIMENTO", "DIAS ATRASO", "SALDO", "SITUAÇÃO", "STATUS",
                  "VENDEDOR")},      # RD-0042: a FAIXA é o atraso em 3ª representação; fica no filtro, no popup e no Excel
    ("pl_inadimplencia", "Por cliente"): {
        "chave": "NOME", "cel": ("NOME", None, "FAIXA", "EM ATRASO"),
        "grade": ("NOME", "SITUAÇÃO", "FAIXA", "TÍTULOS VENCIDOS", "EM ATRASO", "MAIOR ATRASO", "A VENCER", "STATUS",
                  "VENDEDOR")},
    ("pl_inadimplencia", "Por vendedor"): _resumo_inad("VENDEDOR"),
    ("pl_inadimplencia", "Por supervisor"): _resumo_inad("SUPERVISOR"),
    ("pl_inadimplencia", "Por filial"): _resumo_inad("FILIAL"),
    ("pl_inadimplencia", "Por UF"): _resumo_inad("UF"),
    ("vc_visitas", "Por supervisor"): {
        "chave": "SUPERVISOR", "grade": ("SUPERVISOR", "REPRES.") + _METRICAS_VIS, "blocos": _BL_VIS,
        "cel": ("SUPERVISOR", None, "% META", "VISIT.")},
    ("vc_visitas", "Por vendedor"): {
        "chave": "VENDEDOR", "blocos": _BL_VIS, "cel": ("VENDEDOR", None, "% META", "VISIT."),
        "grade": ("VENDEDOR", "META", "VISIT.", "% META", "% CONV.", "% FORA DE ROTA", "CAD. C/ COMPRA", "PROSP.",
                  "JORNADA LÍQ.", "KM/CLIENTE")},
    ("vc_visitas", "Dia a dia"): {
        "chave": "VENDEDOR", "blocos": _BL_VIS, "cel": ("VENDEDOR", None, "SITUAÇÃO", "VISIT."),
        "grade": ("DATA", "VENDEDOR", "SITUAÇÃO", "META", "VISIT.", "% META", "% CONV.", "% FORA DE ROTA", "INÍCIO",
                  "ÚLT. ATIV.")},
    ("vc_visitas", "Cliente a cliente"): {
        "chave": "NOME FANTASIA", "blocos": (("Roteiro", ("SEQ. PREV.", "SEQ. REAL", "INÍCIO", "FIM", "ATEND.")),),
        "cel": ("NOME FANTASIA", None, "SITUAÇÃO", "VALOR PEDIDO"),
        "grade": ("DATA", "VENDEDOR", "NOME FANTASIA", "SITUAÇÃO", "STATUS", "CURVA", "DIAS S/ COMPRA",
                  "PEDIDO NO DIA", "VALOR PEDIDO", "JUSTIFICATIVA")},
    ("vc_visitas", "Prospecção"): {
        "chave": "ESTABELECIMENTO", "cel": ("ESTABELECIMENTO", None, "STATUS", "CIDADE"),
        "grade": ("DATA", "VENDEDOR", "ESTABELECIMENTO", "SEGMENTO", "CIDADE", "STATUS", "RESULTADO")},
    ("vc_visitas", "Indicação"): {
        "chave": "INDICADO", "cel": ("INDICADO", None, "SITUAÇÃO", "CIDADE"),
        "grade": ("DATA", "VENDEDOR", "CLIENTE QUE INDICOU", "INDICADO", "CIDADE", "SITUAÇÃO", "VISITADA EM")},
}


# T-0024 (R3 do parecer de UX; contrato tela-bc3 §6.2): GRADE por (rid, título da tabela no pacote). A grade tem no
# máximo 10 colunas de dado a 1366; o resto vai ao popup da linha. `cel` = chave · nome · selo · valor (celular, M3).
# O mecanismo genérico é da T-0033: aqui só as entradas dos 5 faróis do lote 2 e o mínimo para lê-las.
def _g(chave, grade, cel):
    return {"chave": chave, "grade": tuple(grade), "cel": tuple(cel)}


_AGREGADA_BASE = ("CLIENTES", "ATIVOS", "COMPRARAM NO MÊS", "% POSITIVAÇÃO", "C/ LIMITE E S/ COMPRA", "LIMITE DISP.",
                  "META", "REALIZADO", "OPORTUNIDADE (FALTA)")
_CEL_BASE = ("CLIENTES", "% POSITIVAÇÃO", "OPORTUNIDADE (FALTA)")
_ROTA = ("BASE PLANNER", "VISITAS/MÊS", "CLIENTES/DIA", "CAPACIDADE/DIA")
_IND = ("PERÍODO", "PEDIDOS", "NO PRAZO", "% NO PRAZO", "ATRASO", "% ATRASO", "PARCIAL", "% PARCIAL",
        "SLA MÉDIO (DIAS)", "% ENTREGA NO PRAZO")
_CEL_IND = ("PERÍODO", "PEDIDOS", "% NO PRAZO", "% ATRASO")
GRADE.update({
    ("pv_indicadores", "Semana a semana"): _g("PERÍODO", _IND, _CEL_IND),
    ("pv_indicadores", "Mês a mês"): _g("PERÍODO", _IND, _CEL_IND),
    ("vc_base", "Por UF"): _g("UF", ("UF",) + _AGREGADA_BASE, ("UF",) + _CEL_BASE),
    ("vc_base", "Por segmento"): _g("SEGMENTO", ("SEGMENTO",) + _AGREGADA_BASE, ("SEGMENTO",) + _CEL_BASE),
    ("vc_base", "Por cidade"): _g("CIDADE", ("CIDADE", "UF", "CLIENTES", "ATIVOS", "COMPRARAM NO MÊS", "% POSITIVAÇÃO",
                                              "LIMITE DISP.", "META", "REALIZADO", "OPORTUNIDADE (FALTA)"),
                                  ("CIDADE", "UF", "% POSITIVAÇÃO", "OPORTUNIDADE (FALTA)")),
    ("vc_base", "Por vendedor"): _g("VENDEDOR", ("VENDEDOR",) + _AGREGADA_BASE, ("VENDEDOR",) + _CEL_BASE),
    ("vc_base", "Por supervisor"): _g("SUPERVISOR", ("SUPERVISOR",) + _AGREGADA_BASE, ("SUPERVISOR",) + _CEL_BASE),
    ("vc_base", "Por produto (top 400, 6 meses)"): _g(
        "PRODUTO", ("PRODUTO", "DESCRIÇÃO", "CATEGORIA", "FAMÍLIA", "CLIENTES", "QTD", "FATURAMENTO",
                    "ATIVOS SEM O PRODUTO", "ESTOQUE BAP"), ("PRODUTO", "DESCRIÇÃO", "CLIENTES", "FATURAMENTO")),
    ("vc_base", "Clientes"): _g("CLIENTE", ("CLIENTE", "UF", "CIDADE", "VENDEDOR PLANNER", "CURVA", "STATUS",
                                            "DIAS S/ COMPRA", "LIMITE DISP.", "EM ATRASO", "FALTA"),
                                ("CLIENTE", "CIDADE", "CURVA", "DIAS S/ COMPRA")),
    ("vc_planner", "Por zona"): _g("NOME", ("ZONA", "NOME", "VENDEDOR", "UF", "BASE PLANNER", "VISITAS/MÊS",
                                            "CLIENTES/DIA", "CAPACIDADE/DIA", "INADIMPL.", "% COMPRADORES"),
                                   ("NOME", "VENDEDOR", "CLIENTES/DIA", "% COMPRADORES")),
    ("vc_planner", "Por vendedor"): _g("VENDEDOR", ("VENDEDOR", "SUPERVISOR") + _ROTA +
                                       ("COM LIMITE", "INADIMPL.", "COMPRADORES", "% COMPRADORES"),
                                       ("VENDEDOR", "SUPERVISOR", "CLIENTES/DIA", "% COMPRADORES")),
    ("vc_planner", "Por supervisor"): _g("SUPERVISOR", ("SUPERVISOR",) + _ROTA +
                                         ("COM LIMITE", "INADIMPL.", "COMPRADORES", "% COMPRADORES"),
                                         ("SUPERVISOR", "VISITAS/MÊS", "CLIENTES/DIA", "% COMPRADORES")),
    ("vc_planner", "Por segmento"): _g("SEGMENTO", ("SEGMENTO", "VENDEDOR") + _ROTA +
                                       ("COM LIMITE", "INADIMPL.", "% COMPRADORES"),
                                       ("SEGMENTO", "VENDEDOR", "CLIENTES/DIA", "% COMPRADORES")),
    ("vc_planner", "Por UF"): _g("UF", ("UF", "VENDEDORES", "SUPERVISORES") + _ROTA +
                                 ("INADIMPL.", "COMPRADORES", "% COMPRADORES"),
                                 ("UF", "VENDEDORES", "CLIENTES/DIA", "% COMPRADORES")),
    ("vc_planner", "Por cidade"): _g("CIDADE", ("CIDADE", "UF", "VENDEDORES") + _ROTA +
                                     ("INADIMPL.", "COMPRADORES", "% COMPRADORES"),
                                     ("CIDADE", "UF", "CLIENTES/DIA", "% COMPRADORES")),
    ("vc_planner", "Por cliente"): _g("NOME", ("DATA", "DIA", "SEQ.", "NOME", "BAIRRO", "CIDADE", "VISITA", "STATUS",
                                               "CURVA", "COM LIMITE"), ("NOME", "BAIRRO", "STATUS", "DATA")),
    ("vc_planner", "Calendário"): _g("NOME", ("DATA", "DIA", "SEQ.", "NOME", "BAIRRO", "CIDADE", "STATUS", "CURVA"),
                                     ("NOME", "BAIRRO", "STATUS", "DATA")),
    ("pl_giro", "Resumo por filial"): _g("FILIAL", ("FILIAL", "SKUs C/ ESTOQUE", "ESTOQUE UN.", "VENDA 90D UN.",
                                                    "VENDA/DIA UN.", "MIX QUE GIRA", "ITENS EM RUPTURA",
                                                    "ITENS A COMPRAR", "CURVA A PARADA (ITENS)",
                                                    "VENDA PERDIDA PREVISTA"),
                                         ("FILIAL", "ITENS EM RUPTURA", "MIX QUE GIRA", "ITENS A COMPRAR")),
    ("pl_giro", "Ruptura"): _g("PRODUTO", ("FILIAL", "PRODUTO", "DESCRIÇÃO", "CURVA", "EST.", "VD 30D", "VD 90D",
                                           "DIAS S/ EST.", "VENDA/DIA", "VENDA PERDIDA"),
                               ("PRODUTO", "DESCRIÇÃO", "CURVA", "VENDA PERDIDA")),
    ("pl_giro", "Curva A parada"): _g("PRODUTO", ("FILIAL", "PRODUTO", "DESCRIÇÃO", "CURVA", "EST.", "VD 30D", "VD 90D",
                                                  "VD/DIA", "COB (DIAS)", "PARADO (D)"),
                                      ("PRODUTO", "DESCRIÇÃO", "EST.", "PARADO (D)")),
    ("pl_giro", "Necessidade de compra"): _g("PRODUTO", ("FILIAL", "PRODUTO", "DESCRIÇÃO", "CURVA", "EST.", "VD 90D",
                                                         "COB (DIAS)", "SUGESTÃO", "DIAS S/ EST.", "VENDA PERDIDA"),
                                             ("PRODUTO", "DESCRIÇÃO", "EST.", "SUGESTÃO")),
    ("pl_giro", "Por família"): _g("FAMÍLIA", ("FILIAL", "FAMÍLIA", "SKUs", "C/ EST.", "GIRAM", "MIX", "EST. UN.",
                                               "VD 90D", "RUPTURA", "COMPRAR"),
                                   ("FAMÍLIA", "FILIAL", "RUPTURA", "COMPRAR")),
    ("pl_giro", "Por categoria"): _g("CATEGORIA", ("FILIAL", "CATEGORIA", "SKUs", "C/ EST.", "GIRAM", "MIX", "EST. UN.",
                                                   "VD 90D", "RUPTURA", "COMPRAR"),
                                     ("CATEGORIA", "FILIAL", "RUPTURA", "COMPRAR")),
    ("pl_giro", "Todos os produtos"): _g("PRODUTO", ("FILIAL", "PRODUTO", "DESCRIÇÃO", "CURVA", "SITUAÇÃO", "EST.",
                                                     "VD 30D", "VD 90D", "COB (DIAS)", "VENDA PERDIDA"),
                                         ("PRODUTO", "DESCRIÇÃO", "SITUAÇÃO", "EST.")),
    ("pl_frw", "Estoque FRW"): _g("PRODUTO", ("FILIAL", "PRODUTO", "DESCRIÇÃO", "ENTRADA NA FRW", "DIAS NA FRW",
                                              "ESTOQUE", "VENDA MÊS (MÉD. 6M)", "NECESSIDADE", "AÇÃO", "VALOR"),
                                  ("PRODUTO", "DESCRIÇÃO", "AÇÃO", "NECESSIDADE")),
})


# T-0023 v2 (contrato §10.10.2, "Grade"): as tabelas dos 3 faróis do Pós-venda com mais de 10 colunas visíveis. A coluna
# Editar do admin fica à esquerda e não conta no teto. As ocultas (o valor de hoje do formulário) nunca vão à grade.
GRADE.update({
    ("pl_garantias", "Garantias"): {
        "chave": "TICKET", "cel": ("TICKET", "CLIENTE", "STATUS", "SLA ATUAL"),
        "grade": ("TICKET", "CLIENTE", "STATUS", "RESULTADO ANÁLISE", "DT. SOLICITAÇÃO", "DT. FECHAMENTO",
                  "SLA ATUAL", "PRAZO"),
        "blocos": (("Cliente", ("CÓD. CLIENTE", "CIDADE")), ("Produto", ("CÓD. PRODUTO", "QTD")))},
    ("pl_garantias", "Histórico de compra"): {
        "chave": "NF", "cel": ("NF", "FANTASIA", None, "VALOR"),
        "grade": ("NF", "DT. NF", "PEDIDO", "FANTASIA", "CIDADE", "CÓD. PRODUTO", "DESCRIÇÃO", "QTD", "VALOR",
                  "VENDEDOR"),
        "blocos": (("Cliente", ("CÓD. CLIENTE", "RAZÃO SOCIAL")),
                   ("Pedido", ("PED. MÁXIMA", "PRAZO", "DT. PEDIDO", "FILIAL")),
                   ("Entrega", ("DT. ENTREGA", "TRANSPORTADORA", "RESPONSÁVEL")))},
    ("pl_devolucoes", "Devoluções"): {
        "chave": "NF DEV.", "cel": ("NF DEV.", "CLIENTE", "ETAPA", "VALOR"),
        "grade": ("NF DEV.", "DATA", "CLIENTE", "CIDADE", "UF", "VALOR", "ETAPA", "MOTIVO", "AUTORIZADO POR",
                  "CRÉDITO"),
        "blocos": (("Nota", ("MÊS", "FILIAL", "VENDEDOR", "ITENS", "PRODUTOS")),
                   ("Acompanhamento", ("RECEBIDA EM", "CRÉDITO EM", "RESPONSÁVEL")))},
    ("pl_ncc", "NCC pendentes"): {
        "chave": "NCC", "cel": ("NCC", "NOME", "SLA NCC", "SALDO"),
        "grade": ("NCC", "NOME", "UF", "A COMPENSAR", "SLA NCC", "DT. ÚLT. MOV.", "D.U. S/ MOV.", "IDADE",
                  "VENDEDOR", "SALDO"),
        "blocos": (("Cliente", ("CLIENTE", "CIDADE")),
                   ("Nota", ("FILIAL", "PARC.", "EMISSÃO", "DIAS", "VALOR NCC", "JÁ ABATIDO")),
                   ("Em aberto", ("TÍTULOS EM ABERTO", "PEDIDO EM ABERTO", "ÚLTIMA COMPRA")))},
    ("pl_ncc", "Por cliente"): {
        "chave": "NOME", "cel": ("NOME", None, "IDADE", "SALDO"),
        "grade": ("NOME", "UF", "VENDEDOR", "A COMPENSAR", "IDADE", "NCC", "SALDO", "NCC MAIS ANTIGA (DIAS)",
                  "TÍTULOS EM ABERTO", "PEDIDO EM ABERTO"),
        "blocos": (("Cliente", ("CLIENTE", "CIDADE")), ("Compra", ("ÚLTIMA COMPRA",)))},
})


# T-0024 (R4): a dica da busca nomeia o que a tabela mostra; "" = sem busca (tabela de até ~15 linhas)
SEM_BUSCA_ATE = 15
DICA_BUSCA = {
    ("vc_base", "Clientes"): "Buscar cliente ou cidade", ("vc_base", "Por produto (top 400, 6 meses)"): "Buscar produto",
    ("vc_base", "Por cidade"): "Buscar cidade", ("vc_base", "Por família (6 meses)"): "Buscar família",
    ("vc_base", "Por vendedor"): "Buscar vendedor",
    ("vc_planner", "Por cliente"): "Buscar cliente ou bairro", ("vc_planner", "Calendário"): "Buscar cliente ou bairro",
    ("vc_planner", "Por cidade"): "Buscar cidade", ("vc_planner", "Por zona"): "Buscar zona ou vendedor",
    ("vc_planner", "Por segmento"): "Buscar segmento", ("vc_planner", "Por vendedor"): "Buscar vendedor",
    ("pl_giro", "Por família"): "Buscar família", ("pl_giro", "Por categoria"): "Buscar categoria",
    ("pl_frw", "Estoque FRW"): "Buscar produto",
    ("pl_fretes", "Notas com frete"): "Buscar NF ou cliente",                     # T-0037
}


def dica_busca(rid: str, titulo: str, n_linhas: int) -> str | None:
    """None = o texto padrão (faróis antigos); "" = sem caixa de busca; senão, a dica do que a 1ª coluna mostra."""
    if rid in RIDS_ANALISTA:                # T-0036: faróis do Analista, sempre com busca (dica por aba)
        return DICA_BUSCA.get((rid, titulo), "Buscar")
    if rid not in FAROIS_LIVRES:
        return DICA_BUSCA.get((rid, titulo))
    if n_linhas <= SEM_BUSCA_ATE:
        return ""
    return DICA_BUSCA.get((rid, titulo), "Buscar produto" if rid == "pl_giro" else "Buscar")


# T-0036 (revisão de UX, R1): os 4 faróis do Analista Comercial entram na GRADE (até 10 colunas no PC, 4 no celular,
# sem rolagem para o lado). O que a grade não mostra vai ao popup da linha (chave sublinhada) e ao Excel.
_SALDO_AGR = ("PEDIDOS", "VLR VENDA", "DESC. COMERCIAL", "% DESC. COM.", "SALDO", "META SALDO", "% ATING.")
_MK_GRUPO = ("PEDIDOS", "R$ VENDA", "CUSTO", "MARGEM", "MARKUP %", "MKP TABELA %", "% DESC.", "PART. MARGEM")
_MK_PROD = ("PRODUTOS", "R$ VENDA", "CUSTO", "MARGEM", "MKP REAL %", "% DESC.", "MKP TABELA %", "MKP VENDA %",
            "PART. MARGEM")
_PR_GRUPO = ("MÊS", "LEITURA", "FATURAMENTO", "VAR. FAT. %", "PREÇO MÉDIO", "VAR. PREÇO %", "EFEITO PREÇO",
             "EFEITO VOLUME", "EFEITO MIX")
GRADE.update({
    ("vc_saldo", "Pedido a pedido"): _g("PEDIDO", ("PEDIDO", "DATA NF", "FILIAL", "VENDEDOR", "VLR VENDA",
                                                   "% DESC. COM.", "SALDO DO PEDIDO", "SALDO FRETE", "NO SALDO",
                                                   "DESC. COMERCIAL"),
                                        ("PEDIDO", "VENDEDOR", "% DESC. COM.", "SALDO DO PEDIDO")),
    ("vc_saldo", "Por vendedor"): _g("VENDEDOR", ("VENDEDOR", "SUPERVISOR") + _SALDO_AGR,
                                     ("VENDEDOR", "SUPERVISOR", "% DESC. COM.", "SALDO")),
    ("vc_saldo", "Por supervisor"): _g("SUPERVISOR", ("SUPERVISOR",) + _SALDO_AGR,
                                       ("SUPERVISOR", "PEDIDOS", "% DESC. COM.", "SALDO")),
    ("vc_saldo", "Por UF"): _g("UF", ("UF",) + _SALDO_AGR, ("UF", "PEDIDOS", "% DESC. COM.", "SALDO")),
    ("vc_markup", "Por pedido"): _g("PEDIDO", ("PEDIDO", "DATA PED.", "FILIAL", "UF", "STATUS", "R$ VENDA", "CUSTO",
                                               "MARGEM", "MARKUP %", "SITUAÇÃO"),
                                    ("PEDIDO", "FILIAL", "SITUAÇÃO", "MARKUP %")),
    ("vc_markup", "Por UF"): _g("UF", ("UF",) + _MK_GRUPO, ("UF", "PEDIDOS", "MARGEM", "MARKUP %")),
    ("vc_markup", "Por cidade"): _g("CIDADE", ("CIDADE",) + _MK_GRUPO, ("CIDADE", "PEDIDOS", "MARGEM", "MARKUP %")),
    ("vc_markup", "Por supervisor"): _g("SUPERVISOR", ("SUPERVISOR",) + _MK_GRUPO,
                                        ("SUPERVISOR", "PEDIDOS", "MARGEM", "MARKUP %")),
    ("vc_markup", "Por vendedor"): _g("VENDEDOR", ("VENDEDOR",) + _MK_GRUPO,
                                      ("VENDEDOR", "PEDIDOS", "MARGEM", "MARKUP %")),
    ("vc_markup", "Por categoria"): _g("CATEGORIA", ("CATEGORIA",) + _MK_PROD,
                                       ("CATEGORIA", "PRODUTOS", "MARGEM", "MKP REAL %")),
    ("vc_markup", "Por sistema"): _g("SISTEMA", ("SISTEMA",) + _MK_PROD, ("SISTEMA", "PRODUTOS", "MARGEM", "MKP REAL %")),
    ("vc_markup", "Por família"): _g("FAMÍLIA", ("FAMÍLIA",) + _MK_PROD, ("FAMÍLIA", "PRODUTOS", "MARGEM", "MKP REAL %")),
    ("vc_markup", "Por linha"): _g("LINHA", ("LINHA",) + _MK_PROD, ("LINHA", "PRODUTOS", "MARGEM", "MKP REAL %")),
    ("vc_markup", "Por produto"): _g("PRODUTO", ("PRODUTO", "DESCRIÇÃO", "SITUAÇÃO", "ESTOQUE", "VOL. VENDIDO",
                                                 "R$ VENDA", "MARGEM", "MKP REAL %", "MKP VENDA %", "% DESC."),
                                     ("PRODUTO", "DESCRIÇÃO", "ESTOQUE", "MKP REAL %")),
    ("vc_markup", "Todos os produtos"): _g("PRODUTO", ("PRODUTO", "DESCRIÇÃO", "CATEGORIA", "SITUAÇÃO", "EST.",
                                                       "QTD VEND.", "R$ VENDA", "MKP REAL %", "MKP VENDA %",
                                                       "ÚLT. VENDA"),
                                           ("PRODUTO", "DESCRIÇÃO", "EST.", "MKP REAL %")),
    ("vc_preco", "Por categoria"): _g("CATEGORIA", ("CATEGORIA",) + _PR_GRUPO,
                                      ("CATEGORIA", None, "VAR. FAT. %", "FATURAMENTO")),
    ("vc_preco", "Por família"): _g("FAMÍLIA", ("FAMÍLIA",) + _PR_GRUPO, ("FAMÍLIA", None, "VAR. FAT. %", "FATURAMENTO")),
    ("vc_preco", "Total BAP"): _g("TOTAL", ("TOTAL",) + _PR_GRUPO, ("TOTAL", None, "VAR. FAT. %", "FATURAMENTO")),
    ("vc_preco", "Reajustes por produto"): _g("PRODUTO", ("PRODUTO", "MÊS", "FILIAL", "FAMÍLIA", "LEITURA",
                                                          "VAR. TABELA %", "PREÇO PRATICADO", "VAR. PREÇO %",
                                                          "VAR. QTD %", "VAR. FAT. %"),
                                              ("PRODUTO", "FILIAL", "LEITURA", "VAR. PREÇO %")),
    ("vc_preco", "Pesquisa de mercado"): _g("PRODUTO", ("PRODUTO", "DATA", "VENDEDOR", "CIDADE", "UF", "CONCORRENTE",
                                                        "LEITURA", "DIF. COMPRA %", "DIF. VENDA %",
                                                        "SHARE VOLUME %"),
                                            ("PRODUTO", "CONCORRENTE", "LEITURA", "DIF. VENDA %")),
    ("an_divergencias", "Por vendedor"): _g("VENDEDOR", ("VENDEDOR", "SUPERVISOR", "CARTEIRA PLANNER", "BASE PROTHEUS",
                                                         "IGUAIS", "SÓ NO PLANNER", "SÓ NO PROTHEUS",
                                                         "· FORA DA BASE", "· PLANNER SEM VENDEDOR", "BATE?"),
                                            ("VENDEDOR", "SUPERVISOR", "BATE?", "CARTEIRA PLANNER")),
    ("an_divergencias", "Clientes divergentes"): _g("COD", ("COD", "LOJA", "CIDADE", "UF", "VENDEDOR PLANNER",
                                                            "VENDEDOR PROTHEUS (A1_VEND)", "SITUAÇÃO", "O QUE FAZER"),
                                                    ("COD", "CIDADE", "SITUAÇÃO", None)),
    ("an_divergencias", "Sem coordenada / endereço"): _g(
        "CÓD.", ("CÓD.", "LOJA", "O QUE FALTA", "NA ROTA DO MÊS", "UF", "CIDADE", "VENDEDOR PLANNER", "CURVA",
                 "SITUAÇÃO", "PONTO"), ("CÓD.", "VENDEDOR PLANNER", "SITUAÇÃO", "O QUE FALTA")),
})
# T-0036 (UX 2ª passada, D): as dicas dos faróis do Analista moram na DICA_BUSCA, por (farol, aba), como as do lote 2;
# nunca cliente por nome (RN-GER-011)
RIDS_ANALISTA = render.RIDS_ANALISTA      # RD-0004: a lista mora no render
DICA_BUSCA.update({
    ("vc_saldo", "Pedido a pedido"): "Buscar pedido, vendedor", ("vc_saldo", "Por vendedor"): "Buscar vendedor",
    ("vc_saldo", "Por supervisor"): "Buscar supervisor", ("vc_saldo", "Por UF"): "Buscar UF",
    ("vc_markup", "Por pedido"): "Buscar pedido ou código", ("vc_markup", "Por UF"): "Buscar UF",
    ("vc_markup", "Por cidade"): "Buscar cidade", ("vc_markup", "Por supervisor"): "Buscar supervisor",
    ("vc_markup", "Por vendedor"): "Buscar vendedor", ("vc_markup", "Por categoria"): "Buscar categoria",
    ("vc_markup", "Por sistema"): "Buscar sistema", ("vc_markup", "Por família"): "Buscar família",
    ("vc_markup", "Por linha"): "Buscar linha", ("vc_markup", "Por produto"): "Buscar produto",
    ("vc_markup", "Todos os produtos"): "Buscar produto",
    ("vc_preco", "Por categoria"): "Buscar categoria", ("vc_preco", "Por família"): "Buscar família",
    ("vc_preco", "Total BAP"): "Buscar mês", ("vc_preco", "Reajustes por produto"): "Buscar produto ou família",
    ("vc_preco", "Pesquisa de mercado"): "Buscar produto ou cidade",
    ("an_divergencias", "Por vendedor"): "Buscar vendedor", ("an_divergencias", "Clientes divergentes"): "Buscar código ou cidade",
    ("an_divergencias", "Sem coordenada / endereço"): "Buscar código ou cidade",
})
# T-0036 (UX, A): rótulo curto dos números da faixa, só no celular (o inteiro fica no title) e título curto do farol
KPI_CURTO = {"desconto comercial": "Desc. com.", "saldo do frete": "Frete", "abaixo do mínimo": "Abaixo mín.", "queda após reajuste": "Queda reaj.",
             "clientes na base (planner)": "Na base", "vendedor diferente": "Vend. dif.",
             "sem vendedor no planner": "Sem vendedor", "fora da base do planner": "Fora da base",
             "código duplicado": "Duplicados"}
TITULO_CEL = {"an_divergencias": "Divergências Planner × Protheus"}


# T-0036 (revisão UX 4): o selo da lista do celular das Divergências usa o rótulo curto; o inteiro fica no detalhe
# (RD-0005: o texto curto é o do KPI_CURTO)
SELO_CURTO = {k.upper(): KPI_CURTO[k] for k in ("vendedor diferente", "sem vendedor no planner", "fora da base do planner")}


def selo_curto(t) -> str:
    return SELO_CURTO.get(str(t or "").strip().upper(), str(t or ""))


def kpi_curto(rot: str) -> str:
    r = str(rot or "")
    if r.lower() in KPI_CURTO:
        return KPI_CURTO[r.lower()]
    return "Fat. " + r[12:] if r.lower().startswith("faturamento ") else r


# T-0036 (UX, C): o título da coluna não repete a unidade que o número já mostra ("R$ 100", "10,0%")
# e duas colunas da mesma tabela não ficam com rótulos de mesma base ("DESC. COM." % ao lado de "DESC. COMERCIAL" R$)
ROTULO_COLUNA = {"VENDEDOR PROTHEUS (A1_VEND)": "VENDEDOR PROTHEUS",
                 "% DESC. COM.": "DESC. S/ TABELA", "% DESC.": "DESC. S/ TABELA", "VAR. FAT. R$": "DIF. FAT."}
_UNIDADE = re.compile(r"^(?:R\$ |% )|(?: %| R\$)$")


def aplicar_rotulos(tab: dict, rid: str) -> None:
    """Põe `rot` (o que a tela escreve) nas colunas: sem a unidade e sem o nome do campo do Protheus. O contrato e o
    Excel seguem com o nome do PC."""
    if rid not in RIDS_ANALISTA:
        return
    for c in tab.get("cols") or []:
        n = c.get("nome", "")
        r = ROTULO_COLUNA.get(n)
        if r is None and c.get("tipo") in ("moeda", "moeda2", "pct", "pct1"):
            r = _UNIDADE.sub("", n).strip() or n
        c["rot"] = r or n


def grade_de(tab: dict, rid: str = "") -> dict | None:
    """A GRADE da tabela pelo par (rid, título do pacote); None = tabela fora da GRADE (desenhada inteira)."""
    titulo = tab.get("tabela") or tab.get("titulo") or ""
    g = GRADE.get((rid, titulo))
    nomes = [str(c.get("nome", "")).upper() for c in tab.get("cols") or []]
    if g is None and rid == "vc_visitas" and titulo == ADERENCIA and "VENDEDOR" in nomes and nomes[-1].startswith("% ADER"):
        # contrato §6.3: VENDEDOR · um quadrado por dia útil · % ACUM.; o SUPERVISOR vai ao popup (nº de dias varia no mês)
        g = {"chave": "VENDEDOR", "grade": tuple(n for n in nomes if n != "SUPERVISOR"),
             "blocos": (("Supervisor", ("SUPERVISOR",)),), "cel": ("VENDEDOR", None, None, nomes[-1])}
    return g if g and g["chave"] in nomes else None


def _fallback(tab: dict) -> dict:
    """Tabela fora da GRADE (Metas Equipe, Solicitação BAP...): a 1ª coluna é a chave, a 2ª o nome e a última numérica
    o valor (contrato visual §8). Ela só pode ter 10 colunas visíveis ou menos (teste nas fixtures)."""
    cols = tab.get("cols") or []
    nomes = [str(c.get("nome", "")).upper() for c in cols]
    num = next((nomes[i] for i in range(len(cols) - 1, 0, -1) if cols[i].get("num")), None)
    selo = next((n for n in nomes if n.startswith("%")), None)
    return {"chave": nomes[0] if nomes else "", "grade": None, "blocos": (),
            "cel": (nomes[0] if nomes else None, nomes[1] if len(nomes) > 1 else None, selo, num)}


def colunas_no_popup(tab: dict, rid: str = "") -> set[int]:
    """Posições (na tela) das colunas que só aparecem no popup da linha: as que não estão na GRADE."""
    g = grade_de(tab, rid)
    if not g:
        return set()
    nomes = [str(c.get("nome", "")).upper() for c in tab.get("cols") or []]
    chave = nomes.index(g["chave"])
    fora = {i for i, n in enumerate(nomes) if n not in g["grade"] and i != chave}
    # um nome de cliente só na grade: a FANTASIA quando vem em todas as linhas (regra de 25/11), senão a RAZÃO SOCIAL
    razao = colunas_ocultas(tab)
    fan = {i for i, n in enumerate(nomes) if n.startswith("FANTASIA")}
    raz = {i for i, n in enumerate(nomes) if n.startswith(("RAZÃO SOCIAL", "RAZAO SOCIAL"))}
    if fan and raz:
        fora |= (razao if razao else fan)
    return fora


def preparar_grade(tab: dict, rid: str = "") -> dict:
    """Põe na tabela da tela `grade` = {chave, fora, cel, blocos}. Toda tabela tem (no celular vira a lista que abre)."""
    g0 = grade_de(tab, rid)
    g = g0 or _fallback(tab)
    nomes = [str(c.get("nome", "")).upper() for c in tab.get("cols") or []]
    ach = lambda n: nomes.index(n) if n in nomes else None   # noqa: E731
    cel = g["cel"]
    tab["grade"] = {"chave": ach(g["chave"]), "fora": colunas_no_popup(tab, rid) if g0 else colunas_ocultas(tab),
                    "cel": {"cli": ach(cel[1]) if cel[1] else None, "sla": ach(cel[2]) if cel[2] else None,
                            "val": ach(cel[3]) if cel[3] else None},
                    "blocos": g.get("blocos") or ()}
    tot = tab.get("total")
    if tot:                                       # a linha de total leva o rótulo na 1ª coluna que aparece na grade
        fora = tab["grade"]["fora"]
        k = next((i for i in range(len(tot)) if i not in fora), None)
        if k is not None and str((tot[k] or {}).get("t", "")).strip() in ("", "—"):
            tot[k] = {**tot[k], "t": "Total"}
    return tab


_RE_COD_NOME = re.compile(r"^\s*(\d+)\s+-\s+(.+)$")


def cod_e_nome(v) -> tuple[str, str]:
    """"900001 - NOME" -> ("900001", "NOME"); sem código, ("", v). Uma conta só (grade das Devoluções e Entregas, resumo da edição)."""
    m = _RE_COD_NOME.match(str(v))
    return (m.group(1), m.group(2)) if m else ("", str(v))


def cliente_so_nome(tab: dict) -> None:
    """Entregas (UX §3.2): "900001 - NOME" vira só o nome na grade; o código vai ao popup (`cod` da célula)."""
    cols = [str(c.get("nome", "")).upper() for c in tab.get("cols") or []]
    if "CLIENTE" not in cols or not ({"NF", "NF DEV."} & set(cols)):
        return
    i = cols.index("CLIENTE")
    for ln in tab.get("linhas") or []:
        c = ln["cel"][i]
        cod, nome = cod_e_nome(c.get("t", ""))
        if cod:
            c["cod"], c["t"] = cod, nome


# T-0029 / RN-GER-013 (Alexandre, 26/11/2026): pedido de cliente fora da base de clientes da BAP (pedido interno)
# chega do PC com este nome; no Farol de Pedidos a caixa "Ignorar" (marcada por padrão) tira essas linhas da tela.
NOME_FORA_DA_BASE = "CLIENTE FORA DA BASE"


def linhas_fora_da_base(t: dict) -> frozenset:
    """Índices das linhas da tabela cujo cliente é NOME_FORA_DA_BASE (coluna RAZÃO SOCIAL ou CLIENTE)."""
    nomes = [str(c.get("nome", "")).upper() for c in t.get("colunas") or []]
    col = next((i for i, n in enumerate(nomes) if n in ("RAZÃO SOCIAL", "CLIENTE")), None)
    if col is None:
        return frozenset()
    # até o robô novo chegar à produção (rotina diária), o pacote ainda traz o nome antigo do ftPedidos
    nomes_fora = {NOME_FORA_DA_BASE, "NÃO LOCALIZADO NA BASE", "NAO LOCALIZADO NA BASE"}
    return frozenset(k for k, ln in enumerate(t.get("linhas") or [])
                     if col < len(ln) and str(ln[col] or "").strip().upper() in nomes_fora)


def colunas_do_celular(tab: dict) -> dict:
    """Celular (M3, "lista que abre"): posições, na tela, do nome, do selo e do valor da linha fechada (a chave é
    `tab["grade"]["chave"]`); o resto vai para dentro dela (dados_do_popup)."""
    return (tab.get("grade") or preparar_grade(tab)["grade"])["cel"]


def dados_do_popup(tab: dict, linha: dict, so_fora: bool = False) -> list[list]:
    """[[título do bloco, [[nome, texto], ...]], ...] das colunas da linha, sem as vazias.
    `so_fora`: só as que não estão na grade (o popup do PC, que nunca repete a grade); sem ele, todas menos as 4 da linha
    fechada (o celular). Bloco sem título = o que a grade mostra; "Outros" = o que não está em bloco nenhum.
    O PED. MÁX. só aparece quando difere do PEDIDO."""
    g = tab.get("grade") or preparar_grade(tab)["grade"]
    cols = tab.get("cols") or []
    nomes = [str(c.get("nome", "")).upper() for c in cols]
    bloco_de = {n: t for t, ns in g["blocos"] for n in ns}
    fechada = {g["chave"], *g["cel"].values()} - {None}
    ped = next((str(v.get("t", "")).strip() for n, v in zip(nomes, linha.get("cel") or []) if n == "PEDIDO"), "")
    blocos: dict[str, list] = {}
    for i, (c, v) in enumerate(zip(cols, linha.get("cel") or [])):
        if (v or {}).get("cod"):                                  # Entregas: o código do cliente sai da grade
            blocos.setdefault("Outros", []).append(["CÓD. CLIENTE", v["cod"]])
        t = str((v or {}).get("t", "")).strip()
        # T-0036: o selo da linha fechada com rótulo curto deixa o texto inteiro no detalhe aberto
        inteiro = i == g["cel"].get("sla") and selo_curto(t) != t
        if (so_fora and i not in g["fora"]) or (not so_fora and i in fechada and not inteiro):
            continue
        nome = str(c.get("nome", ""))
        if not t or t == "—" or (nome.upper() == "PED. MÁX." and t == ped):
            continue
        bl = bloco_de.get(nome.upper()) or ("" if (not so_fora and i not in g["fora"]) else "Outros")
        blocos.setdefault(bl, []).append([c.get("rot") or nome, t])      # T-0036: o rótulo da tela (sem unidade)
    ordem = [""] + [t for t, _ in g["blocos"]] + ["Outros"]
    return [[t, blocos[t]] for t in ordem if t in blocos]


def colunas_ocultas(tab: dict) -> set[int]:
    """T-0020 (decisão do Alexandre, 25/11/2026): posições, na tela, das colunas que só repetem outra.
    Hoje só a RAZÃO SOCIAL, quando a tabela tem FANTASIA preenchida em todas as linhas da tela (a razão
    social segue no Excel do PC). Sem detecção automática de colunas iguais: coincidência não esconde coluna."""
    cols, linhas = tab.get("cols") or [], tab.get("linhas") or []
    nomes = [str(c.get("nome", "")).upper() for c in cols]
    fan = next((i for i, n in enumerate(nomes) if n.startswith("FANTASIA")), None)
    if fan is None or not linhas:
        return set()
    if not all(fan < len(ln["cel"]) and str((ln["cel"][fan] or {}).get("t", "")).strip() for ln in linhas):
        return set()
    return {i for i, n in enumerate(nomes) if n.startswith(("RAZÃO SOCIAL", "RAZAO SOCIAL"))}


def juntas_para_tela(t: dict, idxs: list[int], uf: str | None = None, centavos: bool = False, rid: str = "") -> list[dict]:
    """As juntas da aba: com `liga`, só as linhas ligadas às linhas visíveis de cima (todas as páginas,
    depois de filtro, recorte e estado, §10.7.2); sem `liga`, todas (e o estado, se a junta traz UF)."""
    out = []
    for j in t.get("juntas") or []:
        jt, liga = j["tabela"], j.get("liga")
        if liga:
            col_j, col_t, sep = liga
            ci = [c["nome"] for c in t["colunas"]].index(col_t)
            alvo = set()
            for k in idxs:
                alvo |= _norm_liga(t["linhas"][k][ci], None)
            cj = [c["nome"] for c in jt["colunas"]].index(col_j)
            ks = [k for k, ln in enumerate(jt["linhas"]) if _norm_liga(ln[cj], sep) & alvo]
        else:
            ks = list(range(len(jt["linhas"])))
        if uf and jt.get("uf_linhas"):
            ks = [k for k in ks if jt["uf_linhas"][k] == uf]
        nomes = [c["nome"] for c in jt["colunas"]]
        mostrar = j.get("mostrar")
        vista = [k for k, c in enumerate(jt["colunas"]) if not c.get("oculta") and (not mostrar or c["nome"] in mostrar)]
        g_j = GRADE.get((rid, jt.get("titulo", "")))
        if g_j and g_j.get("grade"):                    # a ordem da GRADE (§6.2): a chave abre a linha
            pos = {str(jt["colunas"][k]["nome"]).upper(): k for k in vista}
            pri = [pos[n] for n in g_j["grade"] if n in pos]
            vista = pri + [k for k in vista if k not in pri]
        junta = {"titulo": j.get("titulo") or jt.get("titulo", ""), "tabela": jt.get("titulo", ""),
                 "total_linhas": len(ks),
                 "mais": len(ks) > JUNTA_MAX, "cols": _cabecalho(jt, vista), "grupos": _grupos_tela(jt, vista),
                 "linhas": _tela_basica(jt, ks[:JUNTA_MAX], vista, centavos)}
        cliente_so_nome(junta)
        out.append(preparar_grade(junta, rid))
    return out


def subabas_para_tela(t: dict, sub: int, consulta: dict, pagina_tam: int = PAGINA_TAM) -> tuple[list[str], dict]:
    """Solicitação BAP: os nomes das sub-abas e a escolhida (índice `sub`), paginada. Sem filtros."""
    subs = t["subabas"]
    sub = sub if 0 <= sub < len(subs) else 0
    s = subs[sub]
    tela = tabela_para_tela({"titulo": s["titulo"], "colunas": s["colunas"], "linhas": s["linhas"],
                             "tons": s.get("tons")}, consulta, pagina_tam=pagina_tam, rid="pv_pedidos")
    tela["sub"] = sub
    for c in tela["cols"]:                                 # só na exibição: rótulo legível (o contrato guarda o do arquivo)
        c["nome"] = " ".join(_TROCA_ROTULO.get(w, w) for w in c["nome"].replace("_", " ").split())
        c["rot"] = c["nome"]
    return [ROTULO_SUB.get(x["titulo"], x["titulo"]) for x in subs], tela
