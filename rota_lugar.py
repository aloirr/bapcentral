"""
(27/10, Alexandre) ROTEIRIZACAO POR LUGAR - a geolocalizacao em camadas:
CIDADE > BAIRRO > RUA (endereco) > NUMERO.

  - Cada CIDADE ocupa o dia inteiro: 1 cidade por dia (capital ou interior).
  - Dentro da cidade, os BAIRROS vao na ordem do caminho mais curto entre os
    centros dos bairros (centro = mediana dos pontos dos clientes dele);
    dentro do bairro, as RUAS pelo caminho mais curto; dentro da rua, o
    NUMERO em ordem crescente.
  - REGIAO LONGE dentro da mesma cidade (ilha, distrito: um salto de mais de
    SALTO_KM entre um bairro e o seguinte, ex. Mosqueiro em Belem) e dia
    proprio [SUPOSICAO 10 km].
  - O dia e cortado no teto sem partir bairro quando o dia ja tem MIN_CHEIO.
  - (27/10, Alexandre) DIA COMPACTO: bairro a mais de RAIO_DIA_KM do centro
    do dia fecha o dia (o bairro vai para o dia seguinte), mesmo sem o dia
    estar cheio - na capital a cidade e continua (ex. Belem: Marco >
    Marambaia > Coqueiro > Icoaraci nao tem salto de 10 km) e o dia nao pode
    pegar o fim de uma regiao e o comeco de outra [SUPOSICAO 5 km]. O mesmo
    nome de bairro em dois lugares longe vira dois blocos (_partir_bairro).
  - Vaga que sobra no dia: clientes da carteira da MESMA cidade e regiao, a
    ate RAIO_VAGA_KM do centro do dia (os menos visitados no mes, depois a
    curva, depois a distancia); sem cliente, a vaga e PROSPECCAO naquela
    cidade.

Este modulo so tem a geometria (nao conhece o Planner): quem decide os dias,
o teto e a carteira e o planner_nucleo (_reorganizar_por_lugar).
"""
import statistics as st
from collections import defaultdict

import geografia as geo

SALTO_KM = 10.0       # bairro a mais disso do anterior (na ordem) = outra regiao
MIN_CHEIO = 0.75      # so fecha o dia antes do teto se ja tiver 75% dele
RAIO_DIA_KM = 5.0     # (27/10) bairro a mais disso do centro do dia fecha o dia
RAIO_VAGA_KM = 5.0    # (27/10) vaga do dia so com cliente ate isso do centro
PESO_CURVA = {"S": 0, "A": 1, "B": 2, "C": 3, "Z": 4}


def ponto(r):
    la, lo, _p = geo.ponto_do_cliente(r)
    return (la, lo) if la is not None else (None, None)


def centro(pts):
    pts = [p for p in pts if p and p[0] is not None]
    if not pts:
        return (None, None)
    return (st.median(p[0] for p in pts), st.median(p[1] for p in pts))


def _caminho(pts, inicio, seg):
    if len(pts) <= 1:
        return list(range(len(pts)))
    return geo.caminho_mais_curto(pts, inicio if inicio and inicio[0]
                                  is not None else None, segundos=seg)


def _partir_bairro(rs):
    """(27/10) O mesmo nome de bairro em lugares longe um do outro (ex.
    COQUEIRO perto de Icoaraci e perto de Ananindeua; TERRA FIRME de Belem e
    do Outeiro) vira um bloco por lugar: clientes ligados por ate
    RAIO_DIA_KM ficam juntos; sem ponto, com o grupo maior."""
    com = [(ponto(r), r) for r in rs]
    pts = [i for i, (p, _r) in enumerate(com) if p[0] is not None]
    if len(pts) < 2:
        return [rs]
    grupo = {i: i for i in pts}

    def raiz(i):
        while grupo[i] != i:
            grupo[i] = grupo[grupo[i]]
            i = grupo[i]
        return i
    for a in pts:
        for b in pts:
            if a < b and geo.distancia_km(com[a][0], com[b][0]) <= RAIO_DIA_KM:
                grupo[raiz(a)] = raiz(b)
    partes = defaultdict(list)
    for i in pts:
        partes[raiz(i)].append(com[i][1])
    if len(partes) == 1:
        return [rs]
    ps = sorted(partes.values(), key=len, reverse=True)
    ps[0] += [r for p, r in com if p[0] is None]
    return ps


def ordenar_cidade(linhas, inicio=None):
    """[(bairro, centro, [linhas])] na ordem bairro > rua > numero."""
    por_b0 = defaultdict(list)
    for r in linhas:
        por_b0[geo.normalizar(r.get("BAIRRO")) or "(SEM BAIRRO)"].append(r)
    por_b = {}
    for b, rs in por_b0.items():
        for i, parte in enumerate(_partir_bairro(rs)):
            por_b[b if i == 0 else f"{b} #{i + 1}"] = parte
    nomes = list(por_b)
    cent = [centro([ponto(r) for r in por_b[b]]) for b in nomes]
    saida, ultimo = [], inicio
    for ib in _caminho(cent, inicio, 0.3):
        b = nomes[ib]
        por_rua = defaultdict(list)
        for r in por_b[b]:
            rua, num = geo._rua_e_numero(r)
            por_rua[rua or "(SEM RUA)"].append((num, r))
        ruas = list(por_rua)
        cr = [centro([ponto(r) for _n, r in por_rua[x]]) for x in ruas]
        lb = []
        for ir in _caminho(cr, ultimo if ultimo and ultimo[0] is not None
                           else cent[ib], 0.1):
            itens = sorted(por_rua[ruas[ir]],
                           key=lambda t: (t[0] is None, t[0] or 0))
            lb += [r for _n, r in itens]
        saida.append((b.split(" #")[0], cent[ib], lb))
        if cent[ib][0] is not None:
            ultimo = cent[ib]
    return saida


def em_ordem(linhas, inicio=None):
    """As linhas do dia na ordem cidade > bairro > rua > numero."""
    por_c, ordem = defaultdict(list), []
    for r in linhas:
        k = geo.normalizar(r.get("CIDADE"))
        if k not in por_c:
            ordem.append(k)
        por_c[k].append(r)
    saida = []
    for k in ordem:
        saida += [r for _b, _c, rs in ordenar_cidade(por_c[k], inicio)
                  for r in rs]
        pts = [ponto(r) for r in por_c[k]]
        if any(p[0] is not None for p in pts):
            inicio = centro(pts)
    return saida


def regioes(blocos, separar=True):
    """Os blocos (bairros, ja na ordem) partidos onde ha um salto grande."""
    saida, atual, prev = [], [], None
    for b in blocos:
        c = b[1]
        if (separar and atual and prev is not None and c[0] is not None
                and geo.distancia_km(prev, c) > SALTO_KM):
            saida.append(atual)
            atual = []
        atual.append(b)
        if c[0] is not None:
            prev = c
    if atual:
        saida.append(atual)
    return saida


def montar_dias(blocos, tetos):
    """blocos de UMA regiao; tetos dos dias livres na ordem.
    Devolve ([[linhas do dia]], [o que nao coube])."""
    dias, atual, sobra = [], [], []
    i = [0]

    def teto():
        return tetos[i[0]] if i[0] < len(tetos) else 0

    def fechar():
        nonlocal atual
        if atual:
            dias.append(atual)
            i[0] += 1
        atual = []

    for _b, _c, ls in blocos:
        ls = list(ls)
        if atual and _c and _c[0] is not None:
            cd = centro([ponto(r) for r in atual])
            if cd[0] is not None and geo.distancia_km(cd, _c) > RAIO_DIA_KM:
                fechar()                 # dia compacto (27/10)
        while ls:
            if i[0] >= len(tetos):
                sobra += ls
                break
            vaga = teto() - len(atual)
            if len(ls) <= vaga:
                atual += ls
                ls = []
            elif atual and len(atual) >= MIN_CHEIO * teto() \
                    and len(ls) <= teto():
                fechar()                 # o bairro inteiro no dia seguinte
            else:
                atual += ls[:vaga]
                ls = ls[vaga:]
                fechar()
            if teto() and len(atual) >= teto():
                fechar()
    fechar()
    return dias, sobra


def candidatos_do_dia(dia, candidatos, usados, vezes, curva_de):
    """Os clientes que podem encher a vaga do dia, na ordem de preferencia:
    os menos visitados no mes, a curva, a distancia ao centro do dia (so os
    perto do dia: ate RAIO_VAGA_KM do centro dele)."""
    c = centro([ponto(r) for r in dia]) if dia else (None, None)
    saida = []
    for k, cli in candidatos:
        if k in usados:
            continue
        p = ponto(cli)
        if c[0] is not None:
            if p[0] is None:
                continue
            km = geo.distancia_km(c, p)
            if km > RAIO_VAGA_KM:
                continue
        else:
            km = 0.0
        saida.append((vezes.get(k, 0), PESO_CURVA.get(curva_de(cli), 4), km,
                      k, cli))
    saida.sort(key=lambda t: t[:4])
    return [(t[3], t[4]) for t in saida]
