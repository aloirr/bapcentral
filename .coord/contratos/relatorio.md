# Contrato do relatório — v1

- **Dono:** engenheiro-software · **Tarefa:** T-0002 · **Data:** 20/11/2026 (Manaus)
- **Base:** código do `main` em `c96a153` (`relatorios_nucleo.py`, 19.173 linhas). As linhas citadas são desse commit.
- **Escopo:** o dicionário que `relatorios_nucleo.montar(rid, raiz, hoje=None, log=None, params=None, tela=False)` devolve (`relatorios_nucleo.py:19130`). É a ponte entre os núcleos e qualquer tela: Tkinter (`bap_relatorios.py`) hoje, web amanhã.
- **Regra de versão:** acrescentar chave opcional = v1 continua. Renomear, mudar tipo ou tirar chave = **v2**, com ADR em `docs/decisoes/` e recado aos consumidores (seção 9).
- Exemplos com **valores fictícios**. Nenhum dado de cliente ou vendedor.

## 1. Como o dicionário nasce

`montar` (`relatorios_nucleo.py:19130-19172`) faz, nesta ordem:

1. `POR_ID[rid]` → `(rid, area, titulo, funcao)`. `POR_ID = CATALOGO + LEGADO` (`:18447`, `:18479`, `:18490`). Id desconhecido = `KeyError`.
2. `ctx = Contexto(raiz, hoje, log, params)` (`:758`). Os blocos do cache (`bap_dados.BLOCOS`) carregam sob demanda em `ctx.<bloco>`.
3. `rel = funcao(ctx)`. Quase todas começam com `novo(rid, area, titulo, subtitulo, fonte)` (`:328`), que já traz as chaves-base.
4. `rel.setdefault("area", area)`.
5. `_status_nas_tabelas` (`:715`): põe a coluna de status do cliente nas tabelas listadas em `STATUS_NAS_TABELAS`.
6. **Resumo gerencial padrão.** Se `capa` e sem `painel`, e o id está em `PAINEIS_PADRAO` (`:19060`), monta `painel` por `painel_farol.montar` (`painel_farol.py:278`). Se der erro, vira aviso.
7. Tira `_eventos`. Tira `_equipe` e, com `tela=True`, chama esse callable (aba Equipe do `vc_meta`).
8. `_so_status` (`:19033`): esconde STATUS PROTHEUS e SITUAÇÃO PLANNER e deixa só STATUS.
9. `_sinal_nas_colunas` (`:19104`). Fora de `LINHA_PINTADA = ("pv_pedidos", "vc_markup", "vc_saldo")` (`:19080`):
   - zera os `tons` das linhas;
   - põe `chip` nas colunas de `COLUNAS_SINAL` (`:19087`), com as cores de `CORES_SINAL` (`:19092`).
10. Grava `params_usados = dict(ctx.params)`.
11. Completa cada tabela com `tons`, `kpis_de`, `recortes`, `edicao` e `detalhe` (`_colunas_do_pedido`, `:1163`).
12. Põe `detalhe_pedido`: um callable `(tabela, linha) -> dict` (usa `detalhe_pedido`, `:1020`).

> **Efeito colateral (atenção):** `montar("vc_painel")` chama `painel_diretor.calcular(..., gravar_hist=True)`. No mês corrente, essa chamada **grava** `RELATORIOS/painel_diretor_hist.json` (`painel_diretor.py:785-799`). `montar` não é só leitura. Ver o risco R2 em `docs/desenho/T-0002.md`.

## 2. Chaves de topo (sempre presentes)

Inventário rodado em 20/11/2026 nos 29 ids (seção 8): estas 12 chaves saíram em 29 de 29.

| Chave | Tipo | De onde sai | Exemplo (fictício) |
|---|---|---|---|
| `id` | `str` | `novo` (`:328`) | `"pl_frw"` |
| `area` | `str`: `PRE`, `VEN`, `POS`, `ANA` ou `TRADE` (`:37-41`) | `novo`; `montar` usa `setdefault` com a área do `CATALOGO` | `"Pós-venda e Logística"` |
| `titulo` | `str` | `novo` | `"Farol de Estoque FRW"` |
| `subtitulo` | `str` | `novo`; o farol acrescenta o filtro (ex.: `:3098`, `:5631`) | `"Posição de 19/11/2026 · 3 filiais"` |
| `fonte` | `str` | `novo` | `"TABELA_BAP · ESTOQUE_BAP"` |
| `kpis` | `list[Kpi]` (§4) | o farol, por `kpi()` (`:59`) | ver §4 |
| `graficos` | `list[Grafico]` (§5) | o farol; os 3 de tempo por `graficos_tempo` (`:440`) | ver §5 |
| `tabelas` | `list[Tabela]` (§3) | o farol, por `tabela()` (`:312`) ou dict literal; `montar` completa | ver §3 |
| `avisos` | `list[str]` | o farol e o próprio `montar` (falha de painel, status, aba Equipe) | `["Sem custo (P. PEDIDO) para o markup."]` |
| `editar` | `str \| None`: caminho relativo à raiz, o arquivo do botão EDITAR NO EXCEL | `novo` (`None`); farol (`:1409`, `:1892`, `:6803`, `:7487`, `:11695`, `:12355`) | `"RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"` |
| `params_usados` | `dict[str, Any]` | `montar` (`:19156`) | `{"MÊS": 11, "ANO": 2026}` |
| `detalhe_pedido` | **callable** `(tabela: dict, linha: list) -> dict` | `montar` (`:19162-19172`) | — (não serializável) |

## 3. `Tabela` (item de `tabelas`)

### 3.1 Chaves garantidas depois do `montar`

| Chave | Tipo | De onde | Exemplo |
|---|---|---|---|
| `titulo` | `str` | `tabela()` (`:312`) | `"Por filial"` |
| `colunas` | `list[Coluna]` | `col()` (`:50`) | `[{"nome": "FILIAL", "tipo": "texto", "largura": 140, "oculta": False}]` |
| `linhas` | `list[list[Celula]]` | o farol | `[["MAO", 1250.5, 12, None]]` |
| `tons` | `list[str]`, um por linha | `tabela()`; `montar` completa; `_sinal_nas_colunas` zera fora de `LINHA_PINTADA` | `["", "alerta"]` |
| `filtros` | `list[str \| {"coluna", "padrao", "multi"}]` | `tabela()` | `["FILIAL", {"coluna": "MÊS", "padrao": "NOV/26"}]` |
| `total` | `list[Celula] \| None`: a linha de total | `tabela()` | `["TOTAL", 3800.0, 40, None]` |
| `kpis_de` | **callable** `(linhas_visiveis) -> list[Kpi]` ou `None`: os cartões seguem o filtro | `tabela()`; `montar` (`:19159`) | — |
| `recortes` | `list[(rotulo, callable(linha) -> bool) \| (rotulo, {"top": N, "coluna": i})]` | `tabela()`; `montar` (`:19160`) | `[("Top 10", {"top": 10, "coluna": 2})]` |
| `edicao` | `dict \| None`: o que a assistente pode editar (§3.4) | `tabela()`; `montar` (`:19161`) | ver §3.4 |
| `detalhe` | `{"filial": int\|None, "pedido": int\|None, "nf": int\|None} \| None` | `montar` → `_colunas_do_pedido` (`:1163`) | `{"filial": 0, "pedido": 1, "nf": None}` |

### 3.2 `Coluna`

`{"nome": str, "tipo": str, "largura": int, "oculta": bool}` (`col`, `:50`). Depois do `montar`, pode ganhar:
- `chip: dict[str, (fundo, texto)]`: o selo colorido (`:19122`);
- `larg_fixa: int`.

Tipos (`:52-54`) e formato na tela (`bap_visual.formatar`, `bap_visual.py:133`):

| `tipo` | Valor na célula | Mostra |
|---|---|---|
| `texto` | `str` | como está |
| `moeda`, `moeda2` | `float` em R$ | `R$ 1.250` / `R$ 1.250,50` |
| `pct`, `pct1` | `float` **de 0 a 100** (`pct_de`, `:344`) | `85%` / `85,3%` |
| `int`, `num`, `num1`, `num2` | `int`/`float` | `1.250` / `1.250,5` |
| `data` | `date`/`datetime` | `19/11/2026` |
| `dia` | `date` | `19/11` |
| `valor` | número | número |

### 3.3 `Celula` e `tons`

- **Tipos vistos nas linhas:** `str`, `int`, `float`, `None`, `date`, `bool` (`vc_markup`) e `dict` (`pv_abertos`).
- **A linha pode ser maior que `colunas`.** Em `pv_abertos` ("Pedidos em aberto"), o índice 25 leva um `dict` interno `{"base", "dcom", "tabela"}`. A tela ignora o que passa do número de colunas. A web deve fazer o mesmo.
- **Tons de linha** (`bap_visual.FUNDOS`, `bap_visual.py:89`): `""`, `"ok"`, `"alerta"`, `"atencao"`, `"info"`, `"azul"`, `"cinza"` e `"grave"`.

### 3.4 `edicao` (exemplo: `_edicao_autorizacao`, `:1543`)

```python
{"arquivo": "RELATORIOS/_AUTORIZACOES", "aba": "", "modulo": "autorizacoes",
 "chave": 3, "so_colunas": [7, 8],
 "campos": [{"campo": "codigo", "rotulo": "CÓD. AUTORIZAÇÃO", "opcoes": [],
             "livre": True, "mantem_caixa": True, "col": 7},
            {"campo": "por", "rotulo": "AUTORIZADO POR",
             "opcoes": ["GERENTE X"], "col": 8}]}
```

- Também pode ter `ao_mudar` (callable). Os campos podem ter `opcoes_de` e `so_se` (callables). Isso aparece em `pl_entregas`, `pl_ncc`, `tm_expositores` e `pl_fretes`.
- Quem grava é a tela (`bap_relatorios.Edicao`, `bap_relatorios.py:4093`).
- Os arquivos digitados são intocáveis (regra 7 do `CLAUDE.md`). A web **não grava** na v1.

### 3.5 Chaves opcionais de tabela (apresentação e exportação)

Vistas no inventário. Todas são opcionais. A tela trata a falta como `False`/`None`.

| Chave | Tipo | Para quê | Onde nasce (exemplo) |
|---|---|---|---|
| `juntas` | `list[{"tabela": Tabela, "titulo": str, "liga": (col_pai, col_filha, sep) \| None, ...}]` | tabelas ligadas embaixo/em cima da principal. Extras: `mostrar`, `larguras`, `peso`, `com_total`, `altura`, `editavel`, `filtro_texto` | `:1874` (pv_pedidos), `:3235` (`_empilhar`), `:7012` (pl_entregas) |
| `juntas_em_cima`, `titulo_tabela`, `sem_rolar_lado` | `bool` / `str` / `bool` | o empilhado GERENTE / SUPERVISORES / VENDEDORES | `_empilhar` (`:3195`) |
| `grupos` | `list[(rotulo, n_colunas)]` | a faixa de cabeçalho agrupado | `vistas_escopo` (`:3534`) |
| `total_de` | **callable** | total que segue o filtro | farol de metas, visitas |
| `so_exportar` | `bool` | só no Excel/PDF (fora da tela) | `:9649` (vc_painel) |
| `compacta`, `enxuta`, `zebra`, `letra`, `divisao`, `filtros_fora` | apresentação | | `:1856-1860` |
| `pdf`, `nota_pdf`, `pdf_quebra_antes`, `pdf_pagina` | PDF | | vários |
| `linhas_filtro`, `tons_filtro`, `top_n`, `ordem_top` | o TOP N na tela, todas no filtro | | `:3789` |
| `ordem_exportar` | **callable** | ordem do Excel | vc_planner |
| `solicitacao_bap`, `garantia`, `protheus`, `calendario`, `executivo`, `vazio`, `cores_celulas`, `totais_por` | marcas de tela específica | | pv_pedidos (`:1888`), pl_garantias, vc_planner, vc_visitas, vc_painel |
| `_por_quem`, `_rot_quem`, `_fotos`, `_testes` | **internas** (começam com `_`) | não fazem parte do contrato | |

## 4. `Kpi` (item de `kpis`)

`kpi(rotulo, valor, cor="neutro", detalhe="", linhas=None)` (`:59`).

| Chave | Tipo | Nota |
|---|---|---|
| `rotulo` | `str` | |
| `valor` | `str` **já formatado** (`moeda`, `br`, `p`); `"—"` sem dado | a web não reformata |
| `cor` | `"neutro" \| "ok" \| "atencao" \| "alerta" \| "info"` | |
| `detalhe` | `str` | a linha pequena |
| `linhas` | opcional: `list[(rotulo, valor, tom)]`, `tom` em `"ok"`, `"atencao"`, `"alerta"` ou `""` | |

```python
{"rotulo": "Pedidos em aberto", "valor": "42", "cor": "neutro",
 "detalhe": "R$ 128.400", "linhas": [("Atrasados", "3", "alerta")]}
```

A barra por estado no cartão sai de `estados_do_cartao(rel, k)` (`:172`). Ela usa `rel["_por_filial"]` quando existe (hoje só `vc_meta`, `:3127`).

## 5. `Grafico` (item de `graficos`)

`graficos_tempo` (`:440`) e os gráficos próprios de cada farol.

| Chave | Tipo | Nota |
|---|---|---|
| `titulo` | `str` | `"Faturamento (R$) · mês a mês 2026"` |
| `rotulos` | `list[str]` | `["JAN", "FEV"]` |
| `series` | `list[{"nome": str, "valores": list[float], "cor": "#RRGGBB", "cores"?: list}]` | |
| `formato` | `"num" \| "moeda" \| "pct" \| "num1"` | |
| opcionais | `largo: bool`, `meta: float \| list`, `rotulo_meta: str`, `rotular: bool \| "nao" \| "nao_zero"`, `linhas: bool`, `linha`, `subrotulos` | `bap_relatorios.py:416-427` |

## 6. Painel: `painel`, `painel_titulo`, `insights_painel`, `paineis`, `painel_pre`

### 6.1 `painel` (21 de 29 ids)

```python
{"colunas": (1, 1, 1), "altura_min": 1000,
 "blocos": [{"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
             "rowspan": 2, "linhas": [("alerta", "3 pedidos atrasados.")]},
            {"tipo": "barras", "row": 0, "col": 1, "colspan": 2, "grafico": {...}}]}
```

- **Quem monta:**
  - o padrão: `painel_farol.montar` (`painel_farol.py:376`), pela tabela `PAINEIS_PADRAO`;
  - os próprios: `vc_executivo` (`:4149`), `vc_planner` (`_painel_roteirizacao`, `:5017`), `pl_entregas` (`_painel_entregas_exec`, `:7177`), `vc_painel` (`:8752`) e `vc_visitas` (`_painel_visitas`, `:13990`).
- **Bloco:** `{"tipo", "row", "col", "rowspan"?, "colspan"?, ...}`. O desenho de cada tipo está em `bap_relatorios.py:409-470`.

| `tipo` | Campos | Notas |
|---|---|---|
| `insights` | `titulo`, `linhas: list[(tom, texto)]` | tom em `ORDEM_TOM` (`painel_farol.py:35`) |
| `barras` | `grafico: Grafico` | |
| `hbarras` | `titulo`, `rotulos`, `valores`, `formato`, `cores?`, `referencia?` | `painel_farol.ranking` (`:250`) |
| `pizza` / `grupo` | `titulo`, `nome_col`, `linhas`, `total?` | vc_painel (`:8753`) |
| `tabela` | `titulo`, `colunas`, `linhas`, `tons?`, `compacta?`, `grupos?` | `_quadro` (`:8942`) |
| `placar` | `titulo`, `cartoes`, `por_linha` | Visão executiva (`:8776`) |
| `rrm` | `dados` (de `painel_rrm.calcular`), `visao`: `"res"`, `"prod"` ou `"du"` (`painel_rrm.VISOES`, `painel_rrm.py:48`) | vc_painel (`:9639`) |
| `diretor`, `cartoes` | `dados`, `visao?` | a tela ainda desenha, mas o `vc_painel` não emite desde 10/11 |

### 6.2 As outras chaves do painel

- **`painel_titulo`** (`str`): o nome da aba. `"Resumo gerencial"` ou `"Painel executivo"`.
- **`insights_painel`** (`list[(tom, texto)]`): as frases do painel. O e-mail e os testes leem daqui.
- **`paineis`** (só `vc_painel`, `_abas_do_painel`, `:9002` → `:9647`): `list[{"titulo", "painel", "kpis", "kpis_export"?, "diretor"?}]`. São as abas Painel · resultado / produtividade / por dia útil (RRM), Resumo gerencial, Faturamento etc. Com `paineis`, as tabelas ficam `so_exportar`.
- **`painel_pre`** (só `vc_painel`, `:8786`): `{"titulo": "Visão executiva", "painel": Painel}`.

## 7. Chaves opcionais de topo, por id

| Chave | Tipo | Ids | Onde nasce | Consumidor |
|---|---|---|---|---|
| `capa` | `bool` | 21 faróis | `capa()` (`:408`) | tela: abre no Resumo gerencial |
| `parametros` | `list[{"nome", "valores": list[(valor, rótulo)], "valor", "tipo"?: "flag", "rotulo"?}]` | 24 | `capa()` (`:414`: MÊS e ANO), `:2059`, `:4079`, `:8402`, `:9912`, `:11937`, `:13281`, `:13302`, `:17048-17107`, `:17984` | tela: as caixas de cima; o valor volta em `params` |
| `kpis_faixa` | `bool` | pv_pedidos | `:1863` | tela: cartões em faixa fina |
| `tabelas_seguidas` | `bool` | vc_executivo | `:4181` (e `:10581` no RH) | PDF |
| `estilo`, `faixa`, `eyebrow`, `titulo_curto` | `str` | vc_meta, vc_executivo | `:3094`, `:4380` | PDF/Excel no estilo BAP |
| `_por_filial` | `dict` | vc_meta | `:3127` | `estados_do_cartao` (`:172`). **Interna**, mas sobrevive ao `montar` |
| `insights_rota` | `list[(tom, texto)]` | vc_planner | `:5021` | e-mail da rota, testes |
| `exportar_protheus`, `exportar_base_protheus` | **callable** | vc_planner | `:4761-4762` | botões de exportação |
| `exec_tri` | `dict` (parâmetro TRIMESTRE) | vc_painel | `:8900` | `bap_relatorios.py:3834` |
| `abrir` | `str` (caminho relativo) | vc_visitas | `:13254` | botão ABRIR |
| `campanha_export` | `{"comp", "linhas", "nome_bap"}` | vc_champions | `:17869` | `exportar_campanha` (`:17886`) |
| `_champions` | `{"vendedores": [(cod, nome)], "supervisores": [...], ...}` | vc_champions | `:18437` | `bap_relatorios.py:3104`. **Interna e com nome de pessoa** |
| `garantia` | `{"dados": callable, "produto": callable, "status", "resultados", "cliente_base": callable, "opcoes", "campos_cliente"}` | pl_garantias | `:7472` | tela do ticket |
| `exportar_sem_coordenada`, `importar_preenchidos`, `exportar_correcao`, `exportar_correcao_json` | **callable** | an_divergencias | `:16078-16084` | botões |
| `_eventos`, `_equipe`, `_preco` | interna | — | `:443`, `:3144`, `:17350` | **removidas** pelo `montar` (`_preco` no `_painel_preco`, `:18916`) |

**Fora do `montar`, o mesmo formato:** `exportar_rh` (`:10540`) e `exportar_rh_executivo` (`:4364`) devolvem um relatório com estas chaves a mais:
- `competencia`, `posicao`, `resultado_ate`, `excel_rv`, `periodo`, `uma_pagina`;
- `mecanica`, `resumo_pessoa`, `resumo_desafio`, `rv_pessoa`;
- `tri`, `assinaturas`.

Elas pertencem ao contrato do "Exportar para o RH" (fora desta v1). Quem lê: `bap_visual.py:2469-4059` e `email_parcial.py:157-303`.

## 8. Inventário de 20/11/2026 (bases do repositório; sem dado pessoal)

Rodado com `montar(rid, raiz)` padrão e `hoje` = 20/11/2026.

| id | tabelas | kpis | gráficos | blocos do painel | chaves extras | tempo |
|---|---|---|---|---|---|---|
| pv_pedidos | 2 | 8 | 5 | insights, barras, hbarras | capa, parametros, painel, kpis_faixa | 3,0 s |
| pv_indicadores | 4 | 8 | 2 | — | parametros | 0,2 s |
| farol_pv / farol_vc / farol_pl | 0 | 0 | 3 | insights, barras | capa, parametros, painel | 0,1 s |
| vc_meta | 11 | 6 | 4 | insights, barras, hbarras | capa, parametros, painel, estilo, faixa, eyebrow, titulo_curto, _por_filial | 6,3 s |
| vc_planner | 8 | 6 | 3 | insights, barras, hbarras | capa, parametros, painel, insights_rota, exportar_* | 0,3 s |
| vc_painel | 17 | 7 | 4 | insights, barras, hbarras, pizza, placar, rrm, tabela | capa, parametros, painel, paineis, painel_pre, exec_tri | **26,1 s** |
| vc_base | 8 | 6 | 3 | insights, barras, hbarras | capa, parametros, painel | 2,2 s |
| vc_visitas | 7 | 10 | 3 | barras | capa, parametros, painel, abrir | 0,6 s |
| vc_champions | 7 | 4 | 3 | — | parametros, campanha_export, _champions | 0,2 s |
| pl_giro | 7 | 7 | 5 | insights, barras, hbarras | capa, parametros, painel | 0,5 s |
| pl_entregas | 1 (+1 junta) | 7 | 4 | insights, barras, hbarras, tabela | capa, parametros, painel | 0,2 s |
| pl_garantias | 4 | 6 | 3 | insights, barras, hbarras | capa, parametros, painel, garantia | 0,2 s |
| pl_devolucoes | 5 | 5 | 4 | insights, barras, hbarras | capa, parametros, painel | 0,2 s |
| pl_frw | 1 | 5 | 3 | insights, barras, hbarras | capa, parametros, painel | 0,1 s |
| pl_inadimplencia | 7 | 6 | 6 | insights, barras, hbarras | capa, parametros, painel | 0,1 s |
| pl_ncc | 5 | 7 | 5 | — (sem painel) | capa, parametros | 0,2 s |
| tm_expositores | 4 | 6 | 4 | insights, barras, hbarras | capa, parametros, painel | 0,1 s |
| vc_saldo | 4 | 4 | 4 | insights, barras, hbarras | capa, parametros, painel | 0,3 s |
| vc_markup | 11 | 7 | 5 | insights, barras, hbarras | capa, parametros, painel | 0,3 s |
| vc_preco | 5 | 6 | 6 | insights, barras, hbarras | capa, parametros, painel | 0,2 s |
| an_divergencias | 3 | 7 | 0 | — | exportar_correcao*, exportar_sem_coordenada, importar_preenchidos | 0,3 s |
| pv_abertos / pv_faturados / pv_excluidos / pl_fretes (legado) | 1 a 4 | 4 a 6 | 0 a 1 | — | — | 0,2 s |
| vc_executivo (legado) | 6 | 6 | 0 | barras, hbarras, tabela | painel, parametros, tabelas_seguidas | 0,2 s |
| an_resumo (legado) | 6 | 5 | 2 | insights, barras, hbarras | capa, parametros, painel | 0,5 s |

## 9. Consumidores (quem chama `montar`) e o que cada um lê

| Consumidor | Chamada | Lê |
|---|---|---|
| `bap_relatorios.py:176` (tela) | `montar(rid, AQUI, log=..., params=..., tela=True)` | tudo |
| `painel_diretor.py:268` | `vc_meta`, `vc_markup`, `vc_saldo`, `vc_visitas`, `pl_inadimplencia`, `pl_giro` | `tabelas` (pelo título), `kpis` |
| `email_inadimplencia.py:444` | `pl_inadimplencia` | `tabelas`, `kpis` |
| `bap_analista.py:1469`, `:1516` | `an_resumo`, `vc_saldo` | `tabelas`, `kpis` |
| `smoke_relatorios.py` | vários | o contrato inteiro |

**Acoplamento por título:** `painel_diretor`, `painel_rrm`, `painel_farol.tabela_de` (`painel_farol.py:388`) e os e-mails acham a tabela pelo `titulo` (ou pelo prefixo `titulo + " ("`) e a coluna pelo `nome`. **Trocar o título de uma tabela ou o nome de uma coluna é mudança de contrato.**

## 10. Regras do contrato para a web (v1)

1. **Serializável:** só as chaves das §2 a §7 que não estão marcadas como callable ou interna. São callables:
   - `detalhe_pedido`, `kpis_de`, `total_de`, `recortes[][1]` (quando função), `ordem_exportar`;
   - `edicao.ao_mudar`, `edicao.campos[].opcoes_de` e `so_se`;
   - `garantia.dados`, `garantia.produto`, `garantia.cliente_base`;
   - `exportar_*` e `importar_preenchidos`.

   A web chama o núcleo no servidor e manda ao navegador só a parte serializável. `date` vira ISO `AAAA-MM-DD`; tupla vira lista.
2. **Chaves com `_`** são internas: nunca vão para a web.
3. **`kpis[].valor` já vem formatado.** As células vêm cruas e o `tipo` da coluna diz o formato (§3.2).
4. **Dado pessoal:** as linhas e o `_champions` trazem nomes e códigos de clientes e vendedores. A web aplica a regra 6 do `CLAUDE.md` (sem dado pessoal em log ou print). Quem vê o quê é decisão da T-0006.
5. **Leitura pura:** a web deve chamar `montar` sem gravar (ver o risco R2). Até a correção, a web não chama `vc_painel`.
