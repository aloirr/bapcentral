# -*- coding: utf-8 -*-
"""
FAMILIA / GRUPO / LINHA da peca.

A classificacao sai da DESCRICAO do produto, que e a unica informacao que
existe para todos os 2.885 itens da base. Sao tres leituras da mesma
frase, da mais larga para a mais fina:

    FAMILIA ... 13 caixas grandes (FREIO, SUSPENSAO, MOTOR...). E o que o
                vendedor usa para conversar: "esse cliente nao compra
                freio".
    GRUPO ..... o item dentro da familia (PASTILHA DE FREIO, AMORTECEDOR,
                FILTRO DE OLEO...). Serve para o mix fino.
    LINHA ..... para que veiculo (LEVE, PESADA, MOTO, AGRICOLA,
                UNIVERSAL). LEVE e o padrao porque e a maioria da base.

As regras sao lidas NA ORDEM: a primeira que casar vence. Por isso
"FILTRO DE AR CABINE" vem antes de "FILTRO DE AR", e "FILTRO (OUTROS)"
vem por ultimo. Mexer na ordem muda o resultado - e de proposito, e o
jeito de resolver ambiguidade sem escrever regex gigante.

Vindo do app BAP Ajuda 2.0, com uma correcao importante: la as regras
usavam "DE? ?" para dizer "com ou sem o DE". Isso nao faz o que parece -
em expressao regular, DE? e "um D obrigatorio e um E opcional". Entao
"BOMBA DE AGUA" casava e "BOMBA AGUA" nao, e o produto caia em OUTROS.
Aqui isso virou _com_ou_sem_de(), que trata os tres jeitos de escrever:
"BOMBA DE AGUA", "BOMBA DAGUA" e "BOMBA AGUA".
"""
from __future__ import annotations

import re
import unicodedata

FAMILIA_PADRAO = "OUTROS"
GRUPO_PADRAO = "NAO CLASSIFICADO"
LINHA_PADRAO = "LEVE"

ROTULO_TODAS = "(todas)"
SEM_DESCRICAO = "(sem descricao)"


# --------------------------------------------------------------------------
# texto
# --------------------------------------------------------------------------
def normalizar(v) -> str:
    """Tira acento, sobe para maiuscula e junta os espacos."""
    if v is None:
        return ""
    s = unicodedata.normalize("NFKD", str(v))
    s = s.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.upper()).strip()


def _com_ou_sem_de(antes: str, depois: str) -> str:
    """
    "BOMBA" + "AGUA" vira uma regra que casa com os tres jeitos de
    escrever a mesma peca: "BOMBA DE AGUA", "BOMBA DAGUA", "BOMBA AGUA".
    Tambem aceita DA/DO/DOS/DAS, que aparecem em "CAIXA DA DIRECAO".
    """
    return rf"{antes}\s*(?:D[EAO]S?\s+|D)?{depois}"


_DE = _com_ou_sem_de


# --------------------------------------------------------------------------
# as regras
# --------------------------------------------------------------------------
REGRAS_FAMILIA = [
    ("FREIO", r"PASTILHA|SAPATA|" + _DE("LONA", "FREIO") + r"|"
              + _DE("DISCO", "FREIO") + r"|" + _DE("CILINDRO", "RODA") + r"|"
              r"BURRINHO|CUICA|" + _DE("CAMARA", "FREIO") + r"|"
              + _DE("FLUIDO", "FREIO") + r"|TAMBOR|SERVO ?FREIO|PINCA|"
              r"CILINDRO MESTRE|LONA TRASEIR|FREIO"),

    ("SUSPENSAO", r"AMORTECEDOR|BATENTE|BIELETA|PIVO|BANDEJA|"
                  + _DE("BARRA", "ESTABILIZADORA") + r"|BUCHA|"
                  r"MOLA|COXIM|BRACO OSCILANTE|BRACO SUPERIOR|"
                  r"BRACO INFERIOR|ROLAMENTO DO AMORTECEDOR|SUSPENSAO"),

    ("DIRECAO", _DE("CAIXA", "DIRECAO") + r"|TERMINAL|AXIAL|"
                + _DE("BARRA", "DIRECAO") + r"|" + _DE("BOMBA", "DIRECAO")
                + r"|" + _DE("BRACO", "DIRECAO") + r"|DIRECAO"),

    ("TRANSMISSAO", r"HOMOCINETIC|JUNTA HOMO|TRIZETA|SEMI-? ?EIXO|CRUZETA|"
                    r"EMBREAGEM|PLATO|ATUADOR|CARDAN|CAMBIO|"
                    r"ROLAMENTO DE EMBREAGEM|COIFA"),

    # (20/10, Catalogo - decisao de 15/10) AGUA DESMINERALIZADA e os
    # ADITIVOS do radiador sao QUIMICOS (familias AGUA DESMINERALIZADA e
    # ADITIVOS), nao ARREFECIMENTO - vem antes, porque "ADITIVO RADIADOR"
    # tambem casa com o RADIADOR do arrefecimento
    ("QUIMICOS", r"AGUA DESMINERAL|" + _DE("ADITIVO", "RADIADOR")
                 + r"|ADITIVO[^|]*ARREFEC|ADITIVO[^|]*REFRIGERA|"
                   r"ADITIVO ORGANICO|FLUIDO ORGANICO"),

    ("ARREFECIMENTO", r"RADIADOR|" + _DE("BOMBA", "AGUA") + r"|"
                      r"ELETROVENTILADOR|VALVULA TERMOSTATICA|TERMOSTAT|"
                      r"INTERCOOLER|ARREFEC|"
                      + _DE("MANGUEIRA", "RADIADOR") + r"|" + _DE("TAMPA", "RADIADOR")),

    ("MOTOR", r"VELA|CABOS? DE VELA|" + _DE("BOMBA", "OLEO") + r"|CORREIA|"
              r"POLIA|TENSOR|JUNTA|" + _DE("BOMBA", "COMBUSTIVEL") + r"|"
              r"BICO|SONDA|COMANDO|PISTAO|BRONZINA|RETENTOR|IGNICAO|"
              r"VALVULA TERMOST|ANEL DE SEGMENTO|CABECOTE|CARTER|"
              r"TUCHO|BALANCIM|VIRABREQUIM|BIELA"),

    ("FILTRACAO", r"FILTRO|SEDIMENTADOR|" + _DE("ELEMENTO", "FILTRANTE")),

    ("RODAGEM", r"ROLAMENTO|" + _DE("CUBO", "RODA") + r"|"
                + _DE("RODA", "ACO") + r"|\bPNEUS?\b|"
                + _DE("CAMARA", "AR") + r"|"
                + _DE("PARAFUSO", "RODA") + r"|CALOTA|PROTETOR DE ARO"),

    ("ELETRICA", r"BATERIA|LAMPADA|FAROL|LANTERNA|ALTERNADOR|"
                 + _DE("MOTOR", "PARTIDA") + r"|SENSOR|INTERRUPTOR|BULBO|"
                 r"CHICOTE|RELE|FUSIVEL|BOBINA|ABS|BUZINA|"
                 r"REGULADOR DE VOLTAGEM|CONECTOR ELETRIC"),

    ("QUIMICOS", r"DESENGRIPANTE|DESCARBONIZANTE|SILICONE|ADESIVO|LIMPA |"
                 r"SPRAY|AEROSSOL|VEDANTE|SELANTE|DESMONTA PNEU|"
                 r"LIMPADOR DE|POLIDOR|CERA AUTOMOT|ADITIVO"),

    ("LUBRIFICANTES", r"OLEO LUBRIFICANTE|LUBRIFICANTE|GRAXA|\bOLEO\b|"
                      r"\bATF\b|\bSAE\b|\b(?:5|10|15|20|25)W ?-? ?\d{2}\b"),

    ("ACESSORIOS", r"PALHETA|LIMPADOR|CINTA|TAPETE|CAPA|"
                   + _DE("TERMINAL", "BATERIA") + r"|MACACO|TRIANGULO|"
                   r"CHAVE DE RODA|EXTINTOR|CABO DE CHUPETA"),
]

REGRAS_GRUPO = [
    # ---- FREIO
    ("PASTILHA DE FREIO", r"PASTILHA"),
    ("SAPATA / LONA DE FREIO", r"SAPATA|" + _DE("LONA", "FREIO") + r"|LONA TRASEIR"),
    ("DISCO / TAMBOR DE FREIO", _DE("DISCO", "FREIO") + r"|TAMBOR"),
    ("CILINDRO DE RODA", _DE("CILINDRO", "RODA") + r"|BURRINHO"),
    ("CILINDRO MESTRE", r"CILINDRO MESTRE"),
    ("CUICA / CAMARA DE FREIO", r"CUICA|" + _DE("CAMARA", "FREIO")),
    ("PINCA / SERVO DE FREIO", r"PINCA|SERVO ?FREIO"),
    ("FLUIDO DE FREIO", _DE("FLUIDO", "FREIO")),
    # ---- SUSPENSAO
    ("KIT BATENTE / AMORTECEDOR", r"BATENTE|KIT AMORTECEDOR"),
    ("AMORTECEDOR", r"AMORTECEDOR"),
    ("BIELETA", r"BIELETA"),
    # BANDEJA antes de PIVO: "BANDEJA SUSPENSAO S/PIVO" e bandeja, e o
    # S/PIVO diz justamente que o pivo NAO vai junto
    ("BANDEJA / BRACO", r"BANDEJA|BRACO OSCILANTE|BRACO SUPERIOR|"
                        r"BRACO INFERIOR"),
    ("PIVO DE SUSPENSAO", r"PIVO"),
    ("MOLA", r"\bMOLA\b"),
    ("BUCHA / COXIM", r"BUCHA|COXIM"),
    ("BARRA ESTABILIZADORA", _DE("BARRA", "ESTABILIZADORA")),
    # ---- DIRECAO
    ("CAIXA DE DIRECAO", _DE("CAIXA", "DIRECAO")),
    ("BOMBA DE DIRECAO", _DE("BOMBA", "DIRECAO")),
    ("TERMINAL AXIAL", r"AXIAL"),
    ("TERMINAL DE DIRECAO", r"TERMINAL"),
    ("BARRA DE DIRECAO", _DE("BARRA", "DIRECAO")),
    ("BRACO AUXILIAR / PITMAN", r"BRACO AUXILIAR|BRACO PITMAN|PITMAN"),
    # ---- TRANSMISSAO
    ("JUNTA HOMOCINETICA", r"HOMOCINETIC|JUNTA HOMO"),
    ("TRIZETA", r"TRIZETA"),
    ("SEMI-EIXO", r"SEMI-? ?EIXO"),
    ("CRUZETA / CARDAN", r"CRUZETA|CARDAN"),
    ("KIT DE EMBREAGEM", r"EMBREAGEM|PLATO"),
    ("COIFA", r"COIFA"),
    # ---- ARREFECIMENTO
    ("BOMBA DE AGUA", _DE("BOMBA", "AGUA")),
    ("ELETROVENTILADOR", r"ELETROVENTILADOR"),
    # o aditivo vem antes do RADIADOR: "ADITIVO RADIADOR" e aditivo, e o
    # RADIADOR ali e so o lugar onde ele vai
    ("ADITIVO / FLUIDO DE RADIADOR", _DE("ADITIVO", "RADIADOR")
     + r"|ADITIVO[^|]*ARREFEC|ADITIVO[^|]*REFRIGERA|ADITIVO ORGANICO|"
       r"FLUIDO ORGANICO"),
    ("AGUA DESMINERALIZADA", r"AGUA DESMINERAL"),
    ("RADIADOR", r"RADIADOR|INTERCOOLER"),
    ("VALVULA TERMOSTATICA", r"TERMOSTAT"),
    # ---- MOTOR
    ("CABO DE VELA", r"CABOS? DE VELA"),
    ("VELA DE IGNICAO", r"VELA"),
    ("BOBINA DE IGNICAO", r"BOBINA"),
    ("CORREIA / TENSOR / POLIA", r"CORREIA|TENSOR|POLIA"),
    ("BOMBA DE OLEO", _DE("BOMBA", "OLEO")),
    ("BOMBA DE COMBUSTIVEL", _DE("BOMBA", "COMBUSTIVEL")),
    ("JUNTA / RETENTOR", r"JUNTA|RETENTOR"),
    ("MOTOR (INTERNO)", r"PISTAO|BRONZINA|ANEL DE SEGMENTO|CABECOTE|"
                        r"COMANDO|TUCHO|BALANCIM|VIRABREQUIM|BIELA|CARTER"),
    ("BICO / SONDA / INJECAO", r"BICO|SONDA"),
    # ---- FILTRACAO
    ("FILTRO DE AR CABINE", _DE("FILTRO", "AR") + r"[^|]{0,20}CABINE|"
                            r"FILTRO[^|]{0,6}CABINE|"
                            + _DE("FILTRO", "AR") + r" ?CONDICIONADO"),
    ("FILTRO DE OLEO", _DE("FILTRO", "OLEO")),
    ("FILTRO DE COMBUSTIVEL", _DE("FILTRO", "COMBUSTIVEL") + r"|SEDIMENTADOR|"
                              + _DE("FILTRO", "DIESEL")),
    ("FILTRO DE AR", _DE("FILTRO", "AR")),
    ("FILTRO (OUTROS)", r"FILTRO|" + _DE("ELEMENTO", "FILTRANTE")),
    # ---- RODAGEM
    ("CUBO DE RODA", _DE("CUBO", "RODA")),
    ("ROLAMENTO", r"ROLAMENTO"),
    # RODA antes de PNEU: "RODA ALUMINIO SEM CAMARA (PNEU 22.5)" e roda,
    # o PNEU ali e so a medida que ela calca
    ("RODA", r"RODA\s*(?:DE\s*)?(?:ACO|ALUMINIO|FERRO)|CALOTA|"
             r"PROTETOR DE ARO|ARO \d"),
    ("PNEU", r"\bPNEUS?\b"),
    ("CAMARA DE AR", _DE("CAMARA", "AR")),
    ("PARAFUSO DE RODA", _DE("PARAFUSO", "RODA")),
    # ---- ELETRICA
    ("BATERIA", r"BATERIA"),
    ("LAMPADA", r"LAMPADA"),
    ("FAROL / LANTERNA", r"FAROL|LANTERNA"),
    ("ALTERNADOR / MOTOR DE PARTIDA", r"ALTERNADOR|" + _DE("MOTOR", "PARTIDA")
                                      + r"|REGULADOR DE VOLTAGEM"),
    ("SENSOR ABS", r"ABS"),
    ("SENSOR / INTERRUPTOR / BULBO", r"SENSOR|INTERRUPTOR|BULBO"),
    ("CHICOTE / RELE / FUSIVEL", r"CHICOTE|RELE|FUSIVEL|CONECTOR ELETRIC"),
    ("BUZINA", r"BUZINA"),
    # ---- ACESSORIOS / QUIMICOS / LUBRIFICANTES
    ("PALHETA LIMPADOR", r"PALHETA|LIMPADOR DE PARA|LIMPADOR PARA"),
    ("CINTA DE CARGA", r"CINTA"),
    ("ACESSORIO DE GARAGEM", r"MACACO|TRIANGULO|CHAVE DE RODA|EXTINTOR|"
                             r"CABO DE CHUPETA|TAPETE|CAPA"),
    ("OLEO LUBRIFICANTE", r"OLEO|LUBRIFICANTE|GRAXA|ATF|\bSAE\b"),
    ("QUIMICO / AEROSSOL", r"DESENGRIPANTE|DESCARBONIZANTE|SILICONE|ADESIVO|"
                           r"SPRAY|AEROSSOL|VEDANTE|SELANTE|POLIDOR|"
                           r"CERA AUTOMOT|LIMPA |ADITIVO"),
]

REGRAS_LINHA = [
    ("MOTO", r"MOTOCICLETA|\bMOTO\b|CICLOMOTOR|DUAS RODAS|NAUTIC|\bBIZ\b|"
             r"\bCG ?1[2-9]\d\b|\bTITAN\b|\bFAN\b|\bFAZER\b|\bXRE\b"),
    ("AGRICOLA", r"COLHEITADEIRA|PLANTADEIRA|TRATOR|AGRICOL|RETROESCAVAD"),
    ("PESADA", r"LINHA PESADA|CAMINHAO|CAVALO MECANICO|ONIBUS|SCANIA|VOLVO|"
               r"CONSTELLATION|ATEGO|AXOR|CARGO 1|CARGO 2|VM 2|VM 3|REBOQUE|"
               r"\bMB ?1[0-9]{3}\b|IVECO|\bACCELO\b"),
    ("UNIVERSAL", r"UNIVERSAL|POR MEDIDA"),
]

ORDEM_FAMILIA = [nome for nome, _ in REGRAS_FAMILIA] + [FAMILIA_PADRAO]
ORDEM_GRUPO = [nome for nome, _ in REGRAS_GRUPO] + [GRUPO_PADRAO]
ORDEM_LINHA = ["LEVE", "PESADA", "MOTO", "AGRICOLA", "UNIVERSAL"]

# a familia de cada grupo, para quem tem o grupo e quer subir um nivel
FAMILIA_DO_GRUPO: dict[str, str] = {}

_COMPILADAS_FAMILIA = [(n, re.compile(rx)) for n, rx in REGRAS_FAMILIA]
_COMPILADAS_GRUPO = [(n, re.compile(rx)) for n, rx in REGRAS_GRUPO]
_COMPILADAS_LINHA = [(n, re.compile(rx)) for n, rx in REGRAS_LINHA]

for _nome, _rx in _COMPILADAS_GRUPO:
    for _fam, _rxf in _COMPILADAS_FAMILIA:
        if _rxf.search(_nome):
            FAMILIA_DO_GRUPO[_nome] = _fam
            break
    else:
        FAMILIA_DO_GRUPO[_nome] = FAMILIA_PADRAO


# --------------------------------------------------------------------------
# classificacao
# --------------------------------------------------------------------------
def _primeira(texto: str, compiladas, padrao: str) -> str:
    """A primeira regra que casar vence - por isso a ordem importa."""
    for nome, rx in compiladas:
        if rx.search(texto):
            return nome
    return padrao


_CACHE: dict[str, tuple] = {}
LIMITE_DO_CACHE = 40000


def classificar(descricao, extra="") -> tuple:
    """
    (familia, grupo, linha) da descricao.

    extra e um texto de apoio opcional - o campo CATEGORIA do
    DADOS_ADICIONAIS, a aplicacao do produto. Entra na conta junto com a
    descricao. Cuidado ao passar o DADOS_ADICIONAIS inteiro: ele traz
    nome de montadora (VOLVO, SCANIA) e isso contamina a LINHA.
    """
    base = normalizar(descricao)
    apoio = normalizar(extra)
    chave = base + "\x00" + apoio
    achado = _CACHE.get(chave)
    if achado is not None:
        return achado
    if not base and not apoio:
        resposta = (FAMILIA_PADRAO, GRUPO_PADRAO, LINHA_PADRAO)
    else:
        # o codigo na frente da descricao ("(980 - BAN14597DP) -BANDEJA")
        # nao diz nada e as vezes tem letra que casa com regra
        limpo = re.sub(r"^\s*\([^)]*\)\s*[-–]*\s*", " ", base).strip()
        alvo = (limpo + " " + apoio).strip()
        resposta = (
            _primeira(alvo, _COMPILADAS_FAMILIA, FAMILIA_PADRAO),
            _primeira(alvo, _COMPILADAS_GRUPO, GRUPO_PADRAO),
            _primeira(alvo, _COMPILADAS_LINHA, LINHA_PADRAO),
        )
    if len(_CACHE) < LIMITE_DO_CACHE:
        _CACHE[chave] = resposta
    return resposta


def familia_de(descricao, extra="") -> str:
    return classificar(descricao, extra)[0]


def grupo_de(descricao, extra="") -> str:
    return classificar(descricao, extra)[1]


def linha_de(descricao, extra="") -> str:
    return classificar(descricao, extra)[2]


def limpar_cache() -> None:
    _CACHE.clear()


# --------------------------------------------------------------------------
# a descricao de cada produto, que e de onde tudo isso sai
# --------------------------------------------------------------------------
def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _chave_do_produto(v) -> str:
    return _texto(v).upper()


def descricoes_da_tabela(wb) -> dict:
    """
    {codigo do produto -> descricao}, lido de um workbook ja aberto da
    TABELA_BAP. Duas portas, na ordem de confianca:

        ftTabelaPreco ... B1_DESC, a descricao do cadastro
        ftEstoquePMZ .... DESCRICAO_COMPL, que cobre o que faltar

    O codigo vira maiuscula porque ele aparece escrito dos dois jeitos
    entre as abas.
    """
    saida: dict[str, str] = {}
    portas = [("ftTabelaPreco", ("DA1_CODPRO", "B1_COD", "COD_PRODUTO",
                                 "CODIGO"), ("B1_DESC", "DESCRICAO")),
              ("ftEstoquePMZ", ("PRODUTO", "CODIGO", "COD_PRODUTO", "B1_COD"),
               ("DESCRICAO_COMPL", "DESCRICAO"))]
    for aba, cods, descs in portas:
        if aba not in getattr(wb, "sheetnames", ()):
            continue
        ws = wb[aba]
        it = ws.iter_rows(values_only=True)
        try:
            cab = [normalizar(c).replace(" ", "_") for c in next(it)]
        except StopIteration:
            continue

        def onde(nomes):
            for n in nomes:
                alvo = normalizar(n).replace(" ", "_")
                if alvo in cab:
                    return cab.index(alvo)
            return None

        i_cod, i_desc = onde(cods), onde(descs)
        if i_cod is None or i_desc is None:
            continue
        for r in it:
            cod = _chave_do_produto(r[i_cod] if i_cod < len(r) else None)
            desc = _texto(r[i_desc] if i_desc < len(r) else None)
            if cod and desc and cod not in saida:
                saida[cod] = desc
    return saida


def classificacao_dos_produtos(wb) -> dict:
    """{codigo do produto -> (familia, grupo, linha)}."""
    return {cod: classificar(desc)
            for cod, desc in descricoes_da_tabela(wb).items()}


def cobertura(descricoes) -> dict:
    """
    Quanto a regra cobre de uma lista de descricoes. So para conferencia
    - e o numero que diz se vale a pena mexer nas regras.
    """
    por_familia: dict[str, int] = {}
    por_linha: dict[str, int] = {}
    grupos = set()
    sem_grupo = 0
    for d in descricoes:
        fam, gru, lin = classificar(d)
        por_familia[fam] = por_familia.get(fam, 0) + 1
        por_linha[lin] = por_linha.get(lin, 0) + 1
        if gru == GRUPO_PADRAO:
            sem_grupo += 1
        else:
            grupos.add(gru)
    total = sum(por_familia.values())
    return {"total": total, "por_familia": por_familia, "por_linha": por_linha,
            "grupos_usados": len(grupos), "grupos_no_total": len(REGRAS_GRUPO),
            "sem_grupo": sem_grupo,
            "em_outros": por_familia.get(FAMILIA_PADRAO, 0)}
