# -*- coding: utf-8 -*-
"""
Semente das zonas BAP e o mapa de bairro de Manaus.

Nada aqui e imutavel: e so o ponto de partida. Depois que o planner
grava o planner_config.json, quem manda e o arquivo de configuracao - o
usuario move cidade e bairro de zona pela tela e o que esta aqui deixa de
ser consultado.
"""
import difflib
import re
import unicodedata

# --------------------------------------------------------------------------
# zonas: (id, nome, uf)
# --------------------------------------------------------------------------
ZONAS = [
    ("AM-NORTE",     "AM - MANAUS ZONA NORTE",        "AM"),
    ("AM-SUL",       "AM - MANAUS ZONA SUL",          "AM"),
    ("AM-LESTE",     "AM - MANAUS ZONA LESTE",        "AM"),
    ("AM-OESTE",     "AM - MANAUS ZONA OESTE",        "AM"),
    ("AM-INTERIOR",  "AM - INTERIOR",                 "AM"),
    ("RR-TOTAL",     "RR - RORAIMA",                  "RR"),
    ("AP-TOTAL",     "AP - AMAPA",                    "AP"),
    ("PA-SANTAREM",  "PA - SANTAREM E REGIAO",        "PA"),
    ("PA-PARAUAPEBAS", "PA - PARAUAPEBAS / CARAJAS",  "PA"),
    ("PA-BELEM",     "PA - BELEM CAPITAL",            "PA"),
    ("PA-ANANINDEUA", "PA - ANANINDEUA E PROXIMIDADES", "PA"),
    ("PA-CASTANHAL", "PA - CASTANHAL E PROXIMIDADES", "PA"),
    ("MA-SAOLUIS",   "MA - SAO LUIS E REGIAO",        "MA"),
    ("MA-SUL",       "MA - SUL / IMPERATRIZ",         "MA"),
    ("MA-OESTE",     "MA - OESTE / BAIXADA",          "MA"),
    ("MT-CAPITAL",   "MT - CUIABA E VARZEA GRANDE",   "MT"),
    ("MT-INTERIOR",  "MT - INTERIOR",                 "MT"),
    ("A-DEFINIR",    "A DEFINIR",                     "--"),
    ("FORA-DE-ROTA", "FORA DE ROTA (outros estados)", "--"),
]

# --------------------------------------------------------------------------
# Manaus: bairro canonico -> zona
# As 6 zonas administrativas de Manaus viram 4: Centro-Sul entra na Sul e
# Centro-Oeste entra na Oeste.
# --------------------------------------------------------------------------
BAIRROS_MANAUS = {
    "AM-NORTE": [
        "CIDADE NOVA", "CIDADE DE DEUS", "COLONIA SANTO ANTONIO",
        "COLONIA TERRA NOVA", "TERRA NOVA", "LAGO AZUL",
        "MONTE DAS OLIVEIRAS", "NOVA CIDADE", "NOVO ISRAEL", "NOVO ALEIXO",
        "SANTA ETELVINA", "AMAZONINO MENDES", "ALFREDO NASCIMENTO",
        "MANOA", "CANARANAS", "NOVA CONQUISTA", "PARQUE DAS NACOES",
        "CAMPO DOURADO", "RAIO DE SOL", "MORADA DO SOL", "GALILEIA",
        "PARQUE RIACHUELO", "BAIRRO NOVO", "NOVA VITORIA",
    ],
    "AM-SUL": [
        "CENTRO", "CACHOEIRINHA", "PRACA 14 DE JANEIRO", "EDUCANDOS",
        "MORRO DA LIBERDADE", "SANTA LUZIA", "SAO LAZARO", "COLONIA OLIVEIRA MACHADO",
        "CRESPO", "BETANIA", "VILA BURITI", "SAO FRANCISCO", "PETROPOLIS",
        "RAIZ", "JAPIIM", "PRESIDENTE VARGAS", "NOSSA SENHORA APARECIDA",
        "DISTRITO INDUSTRIAL", "DISTRITO INDUSTRIAL I",
        "DISTRITO AGROPECUARIO DA SUFRAMA",
        "ALEIXO", "ADRIANOPOLIS", "CHAPADA", "FLORES", "NOSSA SENHORA DAS GRACAS",
        "PARQUE 10 DE NOVEMBRO", "SAO GERALDO", "PARQUE DAS LARANJEIRAS",
        "CONJUNTO CELEBRIDADE", "VIEIRALVES",
    ],
    "AM-LESTE": [
        "ARMANDO MENDES", "COLONIA ANTONIO ALEIXO", "COROADO",
        "DISTRITO INDUSTRIAL II", "GILBERTO MESTRINHO", "JORGE TEIXEIRA",
        "MAUAZINHO", "PURAQUEQUARA", "SAO JOSE OPERARIO", "TANCREDO NEVES",
        "ZUMBI DOS PALMARES", "GRANDE VITORIA", "VAL PARAISO",
        "SAO JOSE", "TERRA NOVA JESUS ME DEU", "BRAGA MENDES", "MUNDO NOVO",
        "JARDIM PAULISTA", "ARENA", "OURO VERDE",
    ],
    "AM-OESTE": [
        "COMPENSA", "GLORIA", "SANTO AGOSTINHO", "SAO JORGE", "SAO RAIMUNDO",
        "VILA DA PRATA", "NOVA ESPERANCA", "SANTO ANTONIO",
        "ALVORADA", "DA PAZ", "DOM PEDRO", "LIRIO DO VALE", "PLANALTO",
        "REDENCAO", "TARUMA", "TARUMA ACU", "PONTA NEGRA",
        "CAMPOS ELISEOS", "PARQUE SAO PEDRO", "BAIRRO UNIAO", "JOAO PAULO",
        "CAMPO SALES", "PARQUE BANDEIRANTES", "SAO JOSE DOS CAMPOS",
        "PRESIDENTE VARGAS OESTE",
    ],
}

# grafias erradas que o difflib nao pega sozinho
APELIDOS_MANAUS = {
    "PARQUE 10": "PARQUE 10 DE NOVEMBRO",
    "PARQUE DEZ": "PARQUE 10 DE NOVEMBRO",
    "PARQUE DEZ DE NOVEMBRO": "PARQUE 10 DE NOVEMBRO",
    "PRACA 14": "PRACA 14 DE JANEIRO",
    "ZUMBI": "ZUMBI DOS PALMARES",
    "COLONIA STO ANTONIO": "COLONIA SANTO ANTONIO",
    "COLONIA O MACHADO": "COLONIA OLIVEIRA MACHADO",
    "COLONIA DO ANTONIO ALEIXO": "COLONIA ANTONIO ALEIXO",
    "MONTE DE OLIVEIRA": "MONTE DAS OLIVEIRAS",
    "MONTE DAS OLIVEIRA": "MONTE DAS OLIVEIRAS",
    "SANTA ITELVINA": "SANTA ETELVINA",
    "SANTA LUIZA": "SANTA LUZIA",
    "DOM PEDRO I": "DOM PEDRO",
    "JORGE TEXEIRA": "JORGE TEIXEIRA",
    "SAO JOSE OPEARIO": "SAO JOSE OPERARIO",
    "CACHOERINHA": "CACHOEIRINHA",
    "CACHOEIRNHA": "CACHOEIRINHA",
    "PLANALTO CAMPOS ELISEOS": "CAMPOS ELISEOS",
    "CONJ CAMPOS ELISEOS": "CAMPOS ELISEOS",
    "PARQUE DOS LAGS AZUL": "LAGO AZUL",
    "PARQUE SAO PEDRO TARUMA": "PARQUE SAO PEDRO",
    "CIDADE NOVA CJ RAIO DE SOL": "CIDADE NOVA",
    "CIDADE NOVA CAMPO DOURADO": "CIDADE NOVA",
    "NOVO ALEIXO CIDADE NOV": "NOVO ALEIXO",
    "JORGE TEIXEIRA VAL PARAISO": "JORGE TEIXEIRA",
    "VAI PARAISO": "VAL PARAISO",
    "TARUNA ACU": "TARUMA ACU",
    "MATINHA": "SAO RAIMUNDO",
    # acento que virou lixo no cadastro
    "REDEN O": "REDENCAO",
    "PRA A 14": "PRACA 14 DE JANEIRO",
    "NOVA ESPERAN A": "NOVA ESPERANCA",
    "S O LAZARO": "SAO LAZARO",
    "L RIO DO VALE": "LIRIO DO VALE",
    "JO O PAULO": "JOAO PAULO",
    "NOSSA SENHORA DAS GRA AS": "NOSSA SENHORA DAS GRACAS",
    "TARUM": "TARUMA",
    "CENTR": "CENTRO",
}

# --------------------------------------------------------------------------
# cidades -> zona. Chave = (UF, CIDADE).
# --------------------------------------------------------------------------
CIDADES = {
    # ---- PA -------------------------------------------------------------
    "PA-BELEM": ["BELEM"],
    "PA-ANANINDEUA": [
        "ANANINDEUA", "MARITUBA", "BENEVIDES", "SANTA BARBARA DO PARA",
        "SANTA IZABEL DO PARA", "SANTO ANTONIO DO TAUA", "BARCARENA",
        "ABAETETUBA", "ACARA", "BUJARU", "TAILANDIA", "TOME-ACU", "TOME ACU",
        "MOJU", "BAIAO", "CAMETA", "BREVES", "COQUEIRO", "IGARAPE-MIRI",
    ],
    "PA-CASTANHAL": [
        "CASTANHAL", "CAPANEMA", "SAO MIGUEL DO GUAMA", "BRAGANCA", "OUREM",
        "SALINOPOLIS", "SAO JOAO DE PIRABAS", "CAPITAO POCO", "IGARAPE-ACU",
        "IGARAPE ACU", "NOVA TIMBOTEUA", "SANTA MARIA DO PARA", "VISEU",
    ],
    "PA-SANTAREM": [
        "SANTAREM", "PRAINHA", "ORIXIMINA", "MONTE ALEGRE", "ALENQUER",
        "OBIDOS", "BELTERRA", "MOJUI DOS CAMPOS", "ITAITUBA", "JURUTI",
        "CURUA", "AVEIRO", "RUROPOLIS",
    ],
    "PA-PARAUAPEBAS": [
        "PARAUAPEBAS", "MARABA", "XINGUARA", "REDENCAO", "TUCUMA",
        "OURILANDIA DO NORTE", "AGUA AZUL DO NORTE", "RIO MARIA",
        "SANTANA DO ARAGUAIA", "CANAA DOS CARAJAS", "CONCEICAO DO ARAGUAIA",
        "SAO FELIX DO XINGU", "SAPUCAIA", "ELDORADO DOS CARAJAS",
        "ITUPIRANGA", "FLORESTA DO ARAGUAIA", "SANTA MARIA DAS BARREIRAS",
        "ALTAMIRA", "MEDICILANDIA", "PACAJA", "NOVO REPARTIMENTO", "TUCURUI",
        "DOM ELISEU", "PARAGOMINAS", "ULIANOPOLIS", "RONDON DO PARA",
        "JACUNDA", "BREU BRANCO", "GOIANESIA DO PARA", "CURIONOPOLIS",
    ],
    # ---- MA -------------------------------------------------------------
    "MA-SAOLUIS": [
        "SAO LUIS", "SAO JOSE DE RIBAMAR", "PACO DO LUMIAR", "RAPOSA",
        "ROSARIO", "ITAPECURU MIRIM", "SANTA RITA", "BARREIRINHAS",
        "CHAPADINHA", "ARAIOSES", "AXIXA", "MORROS", "ICATU", "PRIMEIRA CRUZ",
        "HUMBERTO DE CAMPOS", "TUTOIA", "PACO DO LUMIAR",
    ],
    "MA-SUL": [
        "IMPERATRIZ", "ACAILANDIA", "DAVINOPOLIS", "GOVERNADOR EDISON LOBAO",
        "CAMPESTRE DO MARANHAO", "SAO PEDRO DA AGUA BRANCA", "CIDELANDIA",
        "PORTO FRANCO", "ESTREITO", "CAROLINA", "RIACHAO", "BALSAS",
        "BARRA DO CORDA", "GRAJAU", "MONTES ALTOS", "SITIO NOVO",
        "FORMOSA DA SERRA NEGRA", "PASTOS BONS", "COLINAS", "GONCALVES DIAS",
        "BURITI BRAVO", "PRESIDENTE DUTRA", "TIMON", "JOAO LISBOA",
        "SENADOR LA ROCQUE", "AMARANTE DO MARANHAO", "ACAILANDIA",
    ],
    "MA-OESTE": [
        "BURITICUPU", "PINHEIRO", "SAO BENTO", "ZE DOCA",
        "SANTA LUZIA DO PARUA", "ALTO ALEGRE DO MARANHAO", "MIRANDA DO NORTE",
        "MARACACUME", "SANTA HELENA", "SANTA LUZIA", "VIANA",
        "CENTRO NOVO DO MARANHAO", "TRIZIDELA DO VALE", "CANDIDO MENDES",
        "ARAGUANA", "SAO VICENTE FERRER", "MIRINZAL",
        "NOVA OLINDA DO MARANHAO", "MATINHA", "SANTA INES", "CAJAPIO",
        "AMAPA DO MARANHAO", "PERI MIRIM", "OLHO D'AGUA DAS CUNHAS",
        "ARARI", "BEQUIMAO", "PEDRO DO ROSARIO", "SAO JOAO BATISTA",
        "PIO XII", "BACABAL", "BERNARDO DO MEARIM", "COELHO NETO",
        "GOVERNADOR NUNES FREIRE", "TURIACU", "CURURUPU",
    ],
    # ---- MT -------------------------------------------------------------
    "MT-CAPITAL": ["CUIABA", "VARZEA GRANDE"],
}

# tudo que sobrar cai nestas regras, nesta ordem
REGRA_POR_UF = {
    "AM": "AM-INTERIOR",     # Manaus e tratada por bairro, antes disso
    "RR": "RR-TOTAL",
    "AP": "AP-TOTAL",
    "MT": "MT-INTERIOR",
}

# cidades que entraram numa zona sem obedecer 100% a regra literal:
# ficam registradas para o usuario conferir na tela
OBSERVACOES = {
    ("PA", "PRAINHA"):    "~180 km de Santarem (regra pedia 100 km); logistica e de Santarem",
    ("PA", "ORIXIMINA"):  "~230 km de Santarem (regra pedia 100 km); logistica e de Santarem",
    ("PA", "ITAITUBA"):   "longe de tudo; entrou em Santarem por ser o hub mais proximo",
    ("PA", "PARAGOMINAS"): "~320 km de Belem: entrou em Parauapebas pela regra dos 300 km",
    ("PA", "DOM ELISEU"): "~350 km de Belem: entrou em Parauapebas pela regra dos 300 km",
    ("PA", "TUCURUI"):    "~310 km de Belem: entrou em Parauapebas pela regra dos 300 km",
    ("PA", "BREVES"):     "Marajo, so por barco; ficou em Ananindeua por falta de zona propria",
    ("PA", "CAMETA"):     "Tocantins; ficou em Ananindeua por falta de zona propria",
    ("PA", "BAIAO"):      "Tocantins; ficou em Ananindeua por falta de zona propria",
    ("PA", "COQUEIRO"):   "e bairro, nao municipio; conferir o cadastro do cliente",
    ("MA", "TIMON"):      "colado em Teresina/PI; entrou no sul por proximidade rodoviaria",
    ("MA", "SANTA INES"): "carteira dividida entre Anderson e Jocimar; ficou no oeste",
    ("MT", "CHAPADA DOS GUIMARAES"): "so 70 km de Cuiaba, mas a regra pedia capital = Cuiaba + VG",
    ("MT", "POCONE"):     "so 100 km de Cuiaba, mas a regra pedia capital = Cuiaba + VG",
}


# --------------------------------------------------------------------------
def sem_acento(valor) -> str:
    s = unicodedata.normalize("NFKD", str(valor if valor is not None else ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


_CACHE_NORMALIZAR: dict = {}


def normalizar(valor) -> str:
    """Maiuscula, sem acento, sem lixo de encoding, espaco unico.
    (Guarda o resultado: a base repete os mesmos textos milhares de vezes.)"""
    if isinstance(valor, str):
        r = _CACHE_NORMALIZAR.get(valor)
        if r is None:
            r = _normalizar(valor)
            if len(_CACHE_NORMALIZAR) < 300000:
                _CACHE_NORMALIZAR[valor] = r
        return r
    return _normalizar(valor)


def _normalizar(valor) -> str:
    s = sem_acento(valor).upper()
    s = s.replace("�", " ").replace("¿", " ")   # acento que virou lixo
    s = re.sub(r"[^A-Z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_ROMANOS = {"I": "", "II": "", "III": "", "IV": "", "V": ""}
_PREFIXOS = ("BAIRRO ", "BAIRO ", "CONJ ", "CONJUNTO ", "CJ ", "RESIDENCIAL ",
             "COND ", "VILA RESIDENCIAL ")


def limpar_bairro(valor) -> str:
    """Tira prefixo, numero de setor e algarismo romano do fim."""
    s = normalizar(valor)
    for p in _PREFIXOS:
        if s.startswith(p):
            s = s[len(p):]
    s = s.replace("-", " ")
    partes = s.split()
    while partes and (partes[-1].isdigit() or partes[-1] in _ROMANOS):
        partes.pop()
    return " ".join(partes).strip()


_CANONICOS = {b: z for z, lista in BAIRROS_MANAUS.items() for b in lista}
_LISTA_CANONICA = sorted(_CANONICOS)


def bairro_canonico(bruto: str):
    """
    Devolve (bairro_canonico, zona) ou (texto_limpo, None) quando nao da
    para reconhecer - nesse caso o bairro cai na zona A DEFINIR e aparece
    na tela para o usuario resolver.

    Tenta o texto inteiro antes de podar: 'PARQUE 10' so vira 'PARQUE 10 DE
    NOVEMBRO' se o numero sobreviver, e 'BAIRRO NOVO' nao pode perder o
    'BAIRRO' senao vira outro bairro.
    """
    inteiro = normalizar(bruto)
    if not inteiro:
        return "(SEM BAIRRO)", None
    podado = limpar_bairro(bruto)
    candidatos = [c for c in (inteiro, podado) if c]
    # tentativa exata (apelido primeiro, depois canonico)
    for c in candidatos:
        alvo = APELIDOS_MANAUS.get(c, c)
        if alvo in _CANONICOS:
            return alvo, _CANONICOS[alvo]
    # tentativa aproximada, do texto mais completo para o mais podado
    for c in candidatos:
        perto = difflib.get_close_matches(c, _LISTA_CANONICA, n=1, cutoff=0.86)
        if perto:
            return perto[0], _CANONICOS[perto[0]]
    return podado or inteiro, None


_CIDADE_ZONA = {}
for _z, _lista in CIDADES.items():
    _uf = next(u for i, n, u in ZONAS if i == _z)
    for _c in _lista:
        _CIDADE_ZONA[(_uf, normalizar(_c))] = _z


def zona_da_area(uf: str, cidade: str, bairro: str = ""):
    """
    Regra de semeadura. Devolve (id_da_zona, chave_da_area, rotulo).
    A 'area' e a menor unidade que o usuario move de zona: em Manaus e o
    bairro, no resto e a cidade.
    """
    uf = normalizar(uf)
    cid = normalizar(cidade)
    if uf == "AM" and cid == "MANAUS":
        canon, zona = bairro_canonico(bairro)
        return (zona or "A-DEFINIR", f"AM|MANAUS|{canon}", f"MANAUS - {canon}")
    chave = f"{uf}|{cid}"
    rotulo = f"{uf} - {cid}" if cid else f"{uf} - (SEM CIDADE)"
    if not cid:
        return "A-DEFINIR", chave, rotulo
    z = _CIDADE_ZONA.get((uf, cid))
    if z:
        return z, chave, rotulo
    if uf in REGRA_POR_UF:
        return REGRA_POR_UF[uf], chave, rotulo
    if uf in ("PA", "MA"):
        return "A-DEFINIR", chave, rotulo
    return "FORA-DE-ROTA", chave, rotulo
