# Contrato do relatório — v1

- **Dono:** engenheiro-software · **Tarefa:** T-0002 · **Data:** 20/11/2026 (Manaus)
- **Base:** código do `main` em `c96a153` (`relatorios_nucleo.py`, 19.173 linhas). As linhas citadas são desse commit.
- **Escopo:** o dicionário que `relatorios_nucleo.montar(rid, raiz, hoje=None, log=None, params=None, tela=False)` devolve (`relatorios_nucleo.py:19130`). É a ponte entre os núcleos e qualquer tela: Tkinter (`bap_relatorios.py`) hoje, web amanhã.
- **Regra de versão:** acrescentar chave opcional = v1 continua. Renomear, mudar tipo ou tirar chave = **v2**, com ADR em `docs/decisoes/` e recado aos consumidores (seção 9).
- **Como a versão é lida:** hoje o dicionário **não tem** chave de versão. A versão sai da chave de topo opcional `versao_contrato` (`int`): **ausente = 1**. Acrescentar a chave não muda a v1. Ela passa a ser obrigatória na v2: o `montar` grava `rel["versao_contrato"]` a partir de uma constante do núcleo (proposta: `relatorios_nucleo.VERSAO_CONTRATO = 1`; pedido ao modulo-farois na T-0006). A web lê essa chave e recusa, com aviso, versão maior que a que conhece (ADR 0001, §4.6). Não confundir com `bap_dados.VERSAO` (27), que é a versão do cache.
- **Farol de Fretes** (`pl_fretes`, T-0037, 27/11/2026): §10.11, acréscimo compatível.
- **Formato do pacote** (o transporte, ADR 0003): 1 = um JSON com todos os faróis; 2 = um arquivo por farol e um índice (§10.8, T-0035, 26/11/2026). O formato não muda o `versao_contrato`.
- Exemplos com **valores fictícios**. Nenhum dado de cliente ou vendedor.

## 1. Como o dicionário nasce

`montar` (`relatorios_nucleo.py:19130-19172`) faz, nesta ordem:

1. `POR_ID[rid]` → `(rid, area, titulo, funcao)`. `POR_ID = CATALOGO + LEGADO` (`:18447`, `:18479`, `:18490`). Id desconhecido = `KeyError`.
2. `ctx = Contexto(raiz, hoje, log, params)` (`:758`). Os blocos do cache (`bap_dados.BLOCOS`) carregam sob demanda em `ctx.<bloco>`.
3. `rel = funcao(ctx)`. Quase todas começam com `novo(rid, area, titulo, subtitulo, fonte)` (`:328`), que já traz as chaves-base.
4. `rel.setdefault("area", area)`.
5. `_status_nas_tabelas` (`:715`): põe a coluna de status do cliente nas tabelas listadas em `STATUS_NAS_TABELAS`.
6. **Resumo gerencial padrão.** Se `capa` e sem `painel`, e o id está em `PAINEIS_PADRAO` (`:19060`), chama `PAINEIS_PADRAO[rid](rel, ctx)`. Essas funções (`_painel_*`, `:18534-19024`) terminam em `painel_farol.montar` (`painel_farol.py:278`), que grava `painel`, `painel_titulo` e `insights_painel`. Se der erro, vira aviso.
7. Tira `_eventos`. Tira `_equipe` e, com `tela=True`, chama esse callable (aba Equipe do `vc_meta`).
8. `_so_status` (`:19033`): esconde STATUS PROTHEUS e SITUAÇÃO PLANNER e deixa só STATUS.
9. `_sinal_nas_colunas` (`:19104`). Fora de `LINHA_PINTADA = ("pv_pedidos", "vc_markup", "vc_saldo")` (`:19080`):
   - zera os `tons` das linhas;
   - põe `chip` nas colunas de `COLUNAS_SINAL` (`:19087`), com as cores de `CORES_SINAL` (`:19092`).
10. Grava `params_usados = dict(ctx.params)`.
11. Completa cada tabela com `tons`, `kpis_de`, `recortes`, `edicao` e `detalhe` (`_colunas_do_pedido`, `:1163`).
12. Põe `detalhe_pedido`: um callable `(tabela, linha) -> dict | None` (usa `detalhe_pedido`, `:1020`; ver §11).

> **Efeito colateral (atenção): `montar` não é só leitura.** Ele grava em duas frentes (risco R2 em `docs/desenho/T-0002.md`):
> - **Histórico do Painel do Diretor.** `montar("vc_painel")` → `_abas_do_painel` → `pdr.calcular(ctx, ano, mes)` (`relatorios_nucleo.py:9608`), com `gravar_hist=True` por padrão (`painel_diretor.py:196`). Grava `RELATORIOS/painel_diretor_hist.json` quando o corte dos dados é do mês corrente **e** os números mudaram (`painel_diretor.py:788-797`). O `painel_cartoes.py:136` já chama com `gravar_hist=False`.
> - **Caches em disco** (o `.gitignore` ignora `*.pkl`, `*.py[cod]` e `__pycache__/`, `.gitignore:17-19`, então nada aparece no `git status`):
>   - `RELATORIOS/_CACHE_RELATORIOS/*.pkl`: os blocos do `bap_dados.carregar` (`bap_dados.py:342`, `:363`) e o `custos_legado.pkl` (`bap_dados.py:1255`);
>   - `<pasta do PLANNER>/_CACHE_RELATORIOS/planner_*.pkl` (`meta_nucleo.ler_planner`, `meta_nucleo.py:644-645`), em geral `RELATORIOS/Roteirizacao/_CACHE_RELATORIOS/`;
>   - `<pasta da TABELA_BAP>/_CACHE_RELATORIOS/mix_familia_*.pkl` (`meta_nucleo._mix_m3m`: `caminho = Path(caminho_tabela)`, `meta_nucleo.py:1986`, e `caminho.parent`, `:2010-2011`), na prática `RELATORIOS/_CACHE_RELATORIOS/`;
>   - `<pasta do .xlsx>/_CACHE_RELATORIOS/xlsx/*.pkl` (`xlsx_rapido._arquivo_cache`, `xlsx_rapido.py:571`), só onde a `_CACHE_RELATORIOS/` já existe (`_usa_disco`, `:580`);
>   - `RELATORIOS/Visitas/ANALITICO/_leitura_analitico.pkl` (`visitas_nucleo._ler_espelhos`, `visitas_nucleo.py:890`, `:935`), **fora** de qualquer `_CACHE_RELATORIOS/`;
>   - `SISTEMA BAP/cache/` ao lado do código: o bytecode do Python. Sem `LOCALAPPDATA` (Linux, Render), o `sys.pycache_prefix` ligado no import de `farol_ddr.py:48` e `geocodificar.py:76` (e das telas) aponta para lá. Com `PYTHONPYCACHEPREFIX` no ambiente, o prefixo já vem pronto e é mantido. Os `.pyc` dessa pasta ficam fora do git pelo `*.py[cod]` (`.gitignore:18`), não pelo `__pycache__/`. A pasta recebe também o bytecode da biblioteca padrão compilado depois do import;
>   - `__pycache__/` na raiz: os módulos importados **antes** do `farol_ddr` (o prefixo ainda não existe) gravam o bytecode no lugar padrão, ignorado pelo `__pycache__/` (`.gitignore:17`).
>
> Por isso `gravar_hist=False` sozinho **não** deixa o `montar` em leitura pura (§10, item 5).

## 2. Chaves de topo (sempre presentes)

Inventário rodado em 20/11/2026 nos 29 ids (seção 8): estas 12 chaves saíram em 29 de 29.

| Chave | Tipo | De onde sai | Exemplo (fictício) |
|---|---|---|---|
| `id` | `str` | `novo` (`:328`) | `"pl_frw"` |
| `area` | `str`, o nome longo da área: `"Pré-venda e Faturamento"`, `"Vendas e CRM"`, `"Pós-venda e Logística"`, `"Analista Comercial"` ou `"Trade Marketing"`. `PRE`, `VEN`, `POS`, `ANA` e `TRADE` são só os nomes das constantes no código (`:36-40`), não o valor | `novo`; `montar` usa `setdefault` com a área do `CATALOGO` | `"Pós-venda e Logística"` |
| `titulo` | `str` | `novo` | `"Farol de Estoque FRW"` |
| `subtitulo` | `str` | `novo`; o farol acrescenta o filtro (ex.: `:3098`, `:5631`) | `"Posição de 19/11/2026 · 3 filiais"` |
| `fonte` | `str` | `novo` | `"TABELA_BAP · ESTOQUE_BAP"` |
| `kpis` | `list[Kpi]` (§4) | o farol, por `kpi()` (`:59`) | ver §4 |
| `graficos` | `list[Grafico]` (§5) | o farol; os 3 de tempo por `graficos_tempo` (`:440`) | ver §5 |
| `tabelas` | `list[Tabela]` (§3) | o farol, por `tabela()` (`:312`) ou dict literal; `montar` completa | ver §3 |
| `avisos` | `list[str]` | o farol e o próprio `montar` (falha de painel, status, aba Equipe) | `["Sem custo (P. PEDIDO) para o markup."]` |
| `editar` | `str \| None`: caminho relativo à raiz, o arquivo do botão EDITAR NO EXCEL | `novo` (`None`); farol (`:1409`, `:1892`, `:6803`, `:7487`, `:11695`, `:12355`) | `"RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"` |
| `params_usados` | `dict[str, Any]` | `montar` (`:19156`) | `{"MÊS": 11, "ANO": 2026}` |
| `detalhe_pedido` | **callable** `(tabela: dict, linha: list) -> dict \| None` (ação, §11.1) | `montar` (`:19162-19172`) | — (não serializável) |

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
| `kpis_de` | **callable** `(linhas_visiveis) -> list[Kpi]` ou `None`: os cartões seguem o filtro (ação, §11.2) | `tabela()`; `montar` (`:19159`) | — |
| `recortes` | `list[(rotulo, callable(linha) -> bool) \| (rotulo, {"top": N, "coluna": i, "so_positivo"?: bool})]` (§11.4) | `tabela()`; `montar` (`:19160`) | `[("Top 10", {"top": 10, "coluna": 2})]` |
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
| `hora` | `str` já formatado (`"08:15"`, `"0:12:30"` ou `"—"`) | como está (Farol de Visita; acrescentado em 25/11/2026, §10.7) |
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
| `total_de` | **callable** `(linhas_visiveis) -> list[Celula] \| None` | total que segue o filtro (ação, §11.3) | vc_meta (`:3798`), pl_garantias (`:7258`), pl_giro (`:12199`), vc_visitas (`:13808`) |
| `totais_por` | `{"coluna": int, "valores": dict[str, list[Celula]]}` | o total pronto de cada valor de uma coluna, usado quando não há `total_de` (§11.3). As chaves são valores da coluna (ex.: nome de vendedor) | `:4743` (vc_planner) |
| `so_exportar` | `bool` | só no Excel/PDF (fora da tela) | `:9649` (vc_painel) |
| `compacta`, `enxuta`, `zebra`, `letra`, `divisao`, `filtros_fora` | apresentação | | `:1856-1860` |
| `pdf`, `nota_pdf`, `pdf_quebra_antes`, `pdf_pagina` | PDF | | vários |
| `linhas_filtro`, `tons_filtro`, `top_n`, `ordem_top` | o TOP N na tela, todas no filtro | | `:3789` |
| `ordem_exportar` | **callable** | ordem do Excel | vc_planner |
| `cores_celulas` | `list[dict[int, str]]`, um dict por linha: índice da coluna → cor `"#RRGGBB"` | pinta a célula (não a linha). No JSON, a chave `int` vira `str` (§10) | pl_entregas (`:7003`); no Exportar para o RH, `:4512` e `:10728`. Lido em `bap_visual.py:3325` |
| `solicitacao_bap`, `garantia`, `protheus`, `calendario`, `executivo`, `vazio` | marcas de tela específica | | pv_pedidos (`:1888`), pl_garantias, vc_planner, vc_visitas, vc_painel |
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
| `variacao_tabela` | `bool`, opcional | marca o gráfico "Variação % do preço de tabela" (`:17025`). Quem lê é o `_painel_preco` (`:18975`), para pôr o bloco no alto do painel; a tela não lê |
| opcionais de série | `cor_negativo: "#RRGGBB"` (barra com valor < 0, `bap_visual.py:1877`), `rotulos: list[str]` (o texto de cada ponto, ex.: `:17019`) | |

## 6. Painel: `painel`, `painel_titulo`, `insights_painel`, `paineis`, `painel_pre`

### 6.1 `painel` (21 de 29 ids)

```python
{"colunas": (1, 1, 1), "altura_min": 1000,
 "blocos": [{"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
             "rowspan": 2, "linhas": [("alerta", "3 pedidos atrasados.")]},
            {"tipo": "barras", "row": 0, "col": 1, "colspan": 2, "grafico": {...}}]}
```

- **Quem monta:**
  - o padrão: as funções `_painel_*` da tabela `PAINEIS_PADRAO`, que terminam em `painel_farol.montar` (`painel_farol.py:278`);
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

- **`painel_titulo`** (`str`, **opcional**): o nome da aba. `"Resumo gerencial"` (`painel_farol.py:378` e os painéis próprios) ou `"Painel executivo"` (`vc_executivo`, `:4180`). O `vc_painel` não põe. Sem a chave, a tela usa `"Painel executivo"` (`bap_relatorios.py:303-304`); a web faz o mesmo.
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
| `_eventos`, `_equipe`, `_preco` | interna | — | `:453`, `:3144`, `:17350` | **removidas** pelo `montar` (`_preco` no `_painel_preco`, `:18916`) |

**Fora do `montar`, o mesmo formato:** `exportar_rh` (`:10540`) e `exportar_rh_executivo` (`:4364`) devolvem um relatório com estas chaves a mais:
- `competencia`, `posicao`, `resultado_ate`, `excel_rv`, `periodo`, `uma_pagina`;
- `mecanica`, `resumo_pessoa`, `resumo_desafio`, `rv_pessoa`;
- `tri`, `assinaturas`.

Elas pertencem ao contrato do "Exportar para o RH" (fora desta v1). Quem lê: `bap_visual.py:2469-4059` e `email_parcial.py:157-303`.

## 8. Inventário de 20/11/2026 (bases do repositório; sem dado pessoal)

Rodado com `montar(rid, raiz)` padrão e `hoje` = 20/11/2026, num worktree descartável.

- A coluna "blocos do painel" soma os blocos de `painel`, `paineis[].painel` e `painel_pre.painel`.
- **O tempo é da máquina da rodada** (o contêiner Linux da sessão, não o PC das assistentes). Varia com a máquina, com o cache frio ou quente (§1, efeito colateral) e com o tamanho das bases. Serve para comparar os ids entre si, não como meta de tempo do PC nem do Render.

| id | tabelas | kpis | gráficos | blocos do painel | chaves extras | tempo |
|---|---|---|---|---|---|---|
| pv_pedidos | 2 | 8 | 5 | insights, barras, hbarras | capa, parametros, painel, kpis_faixa | 3,0 s |
| pv_indicadores | 4 | 8 | 2 | — | parametros | 0,2 s |
| farol_pv / farol_vc / farol_pl | 0 | 0 | 3 | insights, barras | capa, parametros, painel | 0,1 s |
| vc_meta | 11 | 6 | 4 | insights, barras, hbarras | capa, parametros, painel, estilo, faixa, eyebrow, titulo_curto, _por_filial | 6,3 s |
| vc_planner | 8 | 6 | 3 | insights, barras, hbarras | capa, parametros, painel, insights_rota, exportar_* | 0,3 s |
| vc_painel | 17 | 7 | 4 | insights, barras, hbarras, pizza, placar, rrm, tabela (soma de `painel`, `paineis` e `painel_pre`; o `painel` sozinho só tem barras e pizza, `:8752-8761`) | capa, parametros, painel, paineis, painel_pre, exec_tri | **26,1 s** |
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

O contrato tem duas partes (ADR 0001, §4.6):
- a **parte dado**: tudo o que é serializável. Vai ao navegador como JSON;
- a **parte ação**: os callables. Ficam no servidor. A §11 diz, para cada um, a assinatura, o retorno e o que a web v1 faz.

1. **Serializável:** só as chaves das §2 a §7 que não estão marcadas como callable ou interna. São callables (a parte ação, §11):
   - `detalhe_pedido`, `kpis_de`, `total_de`, `recortes[][1]` (quando função), `ordem_exportar`;
   - `edicao.ao_mudar`, `edicao.campos[].opcoes_de` e `so_se`;
   - `garantia.dados`, `garantia.produto`, `garantia.cliente_base`;
   - `exportar_*` e `importar_preenchidos`.

   A web chama o núcleo no servidor e manda ao navegador só a parte serializável. Na conversão:
   - `date`/`datetime` viram ISO (`AAAA-MM-DD`);
   - tupla vira lista;
   - **chave `int` de dict vira `str`** (o `json.dumps` faz isso sozinho): em `cores_celulas`, `{10: "#B3261E"}` chega como `{"10": "#B3261E"}`. O navegador converte de volta para o índice da coluna;
   - o recorte por função vira só o rótulo (§11.4).
2. **Chaves com `_`** são internas: nunca vão para a web.
3. **`kpis[].valor` já vem formatado.** As células vêm cruas e o `tipo` da coluna diz o formato (§3.2).
4. **Dado pessoal:** as linhas, o `_champions`, as chaves de `totais_por` e os `campos`/`subtitulo` do `detalhe_pedido` trazem nomes e códigos de clientes e vendedores. A web aplica a regra 6 do `CLAUDE.md` (sem dado pessoal em log ou print). Quem vê o quê é decisão da T-0006.
5. **Leitura pura:** a web deve chamar `montar` sem gravar nas bases (risco R2). Duas frentes, e as duas precisam estar resolvidas:
   - **o histórico do Diretor** (`painel_diretor_hist.json`): pedido ao modulo-farois para a T-0006, com `gravar_hist=False` levado do `montar` até a chamada de `relatorios_nucleo.py:9608` (ou só o robô grava). **Até a correção, a web não chama `vc_painel`;**
   - **os caches** (lista na §1): a T-0006 escolhe entre
     - **raiz gravável só nas pastas de cache**: a exceção `atual/**/_CACHE_RELATORIOS/**` da ADR 0001 (§4.1), até chegar a pasta configurável (`BAP_CACHE_DIR`). O `_leitura_analitico.pkl` fica **fora** dessa exceção (está em `RELATORIOS/Visitas/ANALITICO/`) e precisa entrar no mesmo pedido, ao modulo-rota (`visitas_nucleo.py`);
     - **cache pré-montado na própria web**: um aquecimento (`montar` dos ids da onda) logo depois de o pacote ser validado, antes de trocar o ponteiro `atual`. Cache montado no PC e enviado **não** vale: a web nunca abre pickle vindo de fora (ADR 0001, §4.1);
     - o bytecode (`SISTEMA BAP/cache/`): `PYTHONPYCACHEPREFIX` apontado para fora do código e do pacote, sem mudar código.

### 10.1 Forma "farol" no pacote web (modelo M2, T-0017)

Acrescentada em 24/11/2026 (T-0017; spec R-20261124-174526-po; desenho R-20261124-174958-gerente-projetos; autorização R-20261124-175008-alexandre). No M2 (ADR 0001, Adendo 1) o PC monta e manda o JSON pronto; a web não roda o `montar` nem callable nenhum. **Mudança compatível: o contrato continua na v1** (`versao_contrato = 1`).

**Onde fica:** no pacote do 4f (`bap_automation.montar_pacote_web`), em `relatorios[rid]`, ao lado do `vc_painel`. O topo do pacote não muda (`versao_contrato`, `gerado_em`, `ano`, `mes`, `relatorios`). Sem a chave `forma`, o relatório segue a forma "abas" do `vc_painel` (T-0014: `{"titulo", "abas", "avisos"?}`), que não muda.

```python
relatorios["pl_inadimplencia"] = {
    "forma": "farol",
    "titulo": "Farol de Inadimplência",
    "kpis": [{"rotulo": "Em atraso", "valor": "R$ 12.345", "cor": "alerta",
              "detalhe": "18 títulos"}],
    "painel": {"blocos": [
        {"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
         "linhas": [["alerta", "3 títulos com mais de 90 dias."]]},
        {"tipo": "barras", "row": 0, "col": 1, "grafico": {...}},
        {"tipo": "hbarras", "titulo": "Em atraso por estado", "row": 1, "col": 0,
         "rotulos": ["AM", "PA"], "valores": [9000.0, 3345.0], "formato": "moeda"}]},
    "insights_painel": [["alerta", "3 títulos com mais de 90 dias."]],
    "avisos": [],
    "recortes": {"AM": {"kpis": [...]}, "PA": {"kpis": [...]}},
    "baixado_em": "2026-11-24T07:12:00-04:00",
}
```

| Chave | Tipo | Regra |
|---|---|---|
| `forma` | `"farol"` | obrigatória; marca esta forma |
| `titulo` | `str` | o `rel["titulo"]` do PC |
| `kpis` | `list[Kpi]` (§4) | os cartões de cima **sem filtro**, iguais ao `rel["kpis"]` do PC (BAP inteira), com o mini-gráfico por estado em `estados` quando o PC o desenha (abaixo) |
| `painel` | `{"blocos": list[Bloco]}` (§6.1) | os blocos do `rel["painel"]` do PC, no mesmo formato, só filtrados (abaixo). `colunas` e `altura_min` podem ir; a web pode ignorar |
| `insights_painel` | `list[[tom, texto]]` (§6.2) | igual ao PC |
| `avisos` | `list[str]` (§2) | os do PC; o robô pode acrescentar (ex.: bloco tirado) |
| `recortes` | `{"<UF>": {"kpis": list[Kpi]}}` | opcional. UF = 2 letras maiúsculas. **Só os kpis** por estado (abaixo). Atenção: é chaveado direto pela UF, sem o `{"uf": ...}` da forma "abas" |
| `baixado_em` | `str` ISO 8601 com fuso de Manaus (`-04:00`) ou `null` | a hora em que a base do farol foi baixada do ERP, **não** a hora em que o pacote foi montado (essa é o `gerado_em` do topo do pacote). A tela mostra os dois |
| `kpis_faixa` | `true` ou ausente | opcional. Igual ao `rel["kpis_faixa"]` do PC (`relatorios_nucleo.farol_pedidos`; hoje só o Farol de Pedidos, `pv_pedidos`): os cartões de cima numa faixa fina, em vez da grade de cartões (`bap_relatorios.py`, `_kpis_em_faixa`). Só muda o desenho; os `kpis` são os mesmos. Ausente = grade de cartões |

**Filtro (o que sai do `rel` do PC):**
- só as chaves da tabela acima (mais `tabelas` e `cobranca` no `pl_inadimplencia`, §10.6, e `tabelas` no `pv_pedidos`, `pl_entregas` e `vc_visitas`, §10.7). Fora: `tabelas` (nos outros faróis), `juntas` (fora de `tabelas`, §10.7), `graficos` (os gráficos que a web mostra vêm dentro dos blocos do painel), `paineis`, `painel_pre`, `parametros`, `capa`, `params_usados`, `fonte`, `subtitulo`;
- nenhum callable (§10, item 1; §11);
- nenhuma chave que comece com `_`, em qualquer nível;
- nunca `edicao`, `editar` nem `abrir`, em qualquer nível. **A web recusa o pacote** que trouxer uma delas (dado digitado intocável, regra 7 do `CLAUDE.md`);
- conversão de tipos do §10, item 1 (tupla vira lista; data vira ISO).

**Blocos do painel nesta entrega:** a web desenha `insights`, `barras` e `hbarras`; os cartões vêm da chave `kpis` (não há bloco `tipo: "kpis"` no §6.1). Bloco de outro tipo (`tabela`, `pizza`, `grupo`, `placar`...) é aceito no pacote e a web mostra no lugar dele "ainda não disponível na web". O `tabela` entra na entrega do Farol de Entregas (acréscimo compatível, v1).

**Nome de pessoa (D1 decidida, R-20261124-175838-alexandre, "2 A"):**
- nome de vendedor e de supervisor **vai** nos gráficos (ex.: hbarras "Em atraso por vendedor"), como o gerente vê no PC. A chave do robô fica `bap_automation.WEB_GRAFICOS_COM_NOME = True`;
- nome de cliente e CNPJ **nunca** vão ao Render nesta fase (regra 6 do `CLAUDE.md`), em nenhum nível: nem em bloco, nem em `kpis[].detalhe`/`linhas`, nem em frase de `insights`/`insights_painel`. A frase "Maiores devedores: ..." do `_painel_inadimplencia` (lista clientes) sai das duas listas no PC, antes do envio;
- as tabelas (`tabelas`, `juntas` e o bloco `tabela` com cliente) ficam fora ("3 A"). Tabela com cliente na web só numa onda futura, com ADR própria.
- **Exceção (ADR 0001, adendo 3):** no `pl_inadimplencia`, código, nome, cidade e WhatsApp de cliente vão **só** em `tabelas` e `cobranca` (§10.6). Cartões, blocos e `insights` continuam sem nome de cliente. CNPJ nunca vai.
- **Exceção (ADR 0001, adendo 5):** no `pv_pedidos`, `pl_entregas` e `vc_visitas`, código e nome de cliente vão **só** em `tabelas` (§10.7), limpos de CPF/CNPJ. Telefone, e-mail, contato e CNPJ nunca vão.

**Mini-gráficos por estado dos cartões:** vão no pacote, em `kpis[i]["estados"] = {"barras": [[UF, numero, "texto", "% na barra", "tom"], ...], "legenda": ""}`, **só** nos cartões que o PC desenha assim (`estados_do_cartao`, §4). `numero` é `float` (ou `null` sem dado), `texto` é o valor já formatado, `"% na barra"` é o texto da barra (pode ser `""`) e `tom` segue o §4 (`"ok"`, `"atencao"`, `"alerta"` ou `""`). Cartão sem mini-gráfico não leva a chave `estados` (ou leva `null`). É a mesma forma das barras que a T-0014 já lê (`bap_automation.recortes_por_uf`).

**Filtro por estado (RN-GER-006, estado = filial da nota):** muda **só os kpis**. O PC calcula `recortes[UF].kpis` com o `kpis_de` da tabela do farol sobre as linhas da filial daquele estado (o mesmo cálculo da tela, §11.2), e a web só troca os cartões. Os blocos do painel ficam da BAP inteira, e a tela avisa, com o estado escolhido, que só os cartões seguem o filtro (o texto é da web: `web/app/render.py`, `AVISO_UF`). Estado sem recorte: a web mostra "—" nos cartões, nunca o número da BAP inteira.

**Versão e ordem de publicação:** a web antiga recusa `rid` fora do `ACEITOS` (`web/app/pacotes.py`). Por isso a **web publica antes** (aceita o `rid` novo e a forma "farol") e o **robô depois** (passa a mandar o farol). A versão fica em 1. Chave nova nesta forma = acréscimo compatível; renomear ou tirar chave = v2 com ADR.

### 10.6 Títulos, Por cliente e "Cobrar no WhatsApp" (só `pl_inadimplencia`, T-0017)

Acrescentada em 24/11/2026 e revista em 25/11/2026 (revisão do PR #56). Fontes: ADR 0001, adendo 3; pedido R-20261124-181913-alexandre; decisões R-20261124-192008-alexandre ("1 A … 7 A"); RN-POS-001 a RN-POS-004. **Acréscimo compatível: o contrato continua na v1** (`versao_contrato = 1`). Vale sobre o §10.1, **só** em `relatorios["pl_inadimplencia"]`. Em qualquer outro `rid`, `cobranca` continua proibida, e `tabelas` também, fora os três faróis do §10.7; a web recusa o pacote.

**Como citar:** os itens numerados do §10 se citam "§10, item N" (ex.: `web/app/pacotes.py:202`, "chaves com `_`" = §10, item 2). As subseções são §10.1 (forma "farol"), §10.6 (esta), §10.7 (as abas de Pedidos, Entregas e Visita) e §10.8 (o formato 2 do pacote, por farol). Os números 10.2 a 10.5 não são usados como subseção.

Donos: o PC monta (modulo-posvenda: `cobranca_whatsapp.pacote_web`, `historico_origem` e `importar_web`; modulo-robo: o 4f). A web valida e desenha (modulo-web).

#### 10.6.1 Chaves novas no farol

```python
relatorios["pl_inadimplencia"] = {
    "forma": "farol", ...,                 # as chaves do §10.1, sem mudança
    "tabelas": [TabelaWeb("Títulos"), TabelaWeb("Por cliente")],
    "cobranca": {...},                     # §10.6.3
}
```

| Chave | Tipo | Regra |
|---|---|---|
| `tabelas` | `list[TabelaWeb]` (§10.6.2) | opcional. Exatamente as 2 tabelas, nesta ordem: `"Títulos"` e `"Por cliente"` |
| `cobranca` | `dict` (§10.6.3) | opcional. Vai junto com `tabelas`: as duas ou nenhuma |

Sem as duas chaves, o farol se comporta como no §10.1 (robô antigo).

**Pacotes guardados no Render ("3 A"):** a web passa a guardar os **7** últimos pacotes, de qualquer conteúdo (hoje guarda 15: `web/app/pacotes.py`, `GUARDAR = 15` → `GUARDAR = 7`). No formato 2 (§10.8.2), são os 7 últimos **lotes**.

#### 10.6.2 `TabelaWeb`: a parte dado da tabela do PC

Chaves (e só elas):

| Chave | Tipo | Regra |
|---|---|---|
| `titulo` | `str` | `"Títulos"` ou `"Por cliente"`, com acento, igual ao PC |
| `colunas` | `list[{"nome": str, "tipo": str, "largura"?: int, "larg_fixa"?: int, "oculta"?: bool, "chip"?: Chip}]` | **exatamente** a lista abaixo, na ordem e com o mesmo `tipo` e `oculta` (o bloco de status é opcional, abaixo) |
| `linhas` | `list[list[Celula]]` | uma célula por coluna (o mesmo tamanho de `colunas`). Célula: `str`, `int`, `float` ou `null`; data em ISO `"AAAA-MM-DD"` |
| `tons` | `list[str]` | um por linha, como o PC entrega. No `pl_inadimplencia` vêm **todos `""`**: o `montar` (`_sinal_nas_colunas`) tira a cor da linha nos faróis fora de `LINHA_PINTADA` e põe o selo na coluna (`chip`). A web aceita qualquer valor do §3.3 e pinta a linha só quando não é `""` |
| `total` | `list[Celula] \| null` | a linha de total do PC, sem a célula de TELEFONE |
| `filtros` | `list[str \| {"coluna", "padrao"?, "multi"?}]` | os do PC (§3.1); só citam colunas da lista abaixo |

**`Chip`** (o selo colorido da célula, §3.2), como o PC entrega:
- forma: `{"<VALOR>": [fundo, texto]}`, com `fundo` e `texto` em `"#RRGGBB"` (no PC é tupla; no JSON vira lista). É o `relatorios_nucleo.CORES_SINAL` inteiro;
- quem leva: só colunas de `COLUNAS_SINAL`; nesta tabela, `SITUAÇÃO`, `FAIXA` e `STATUS`, e só quando alguma das primeiras 2000 linhas tem valor que é chave do `CORES_SINAL`. Coluna sem selo não leva a chave. Em outra coluna, a web recusa;
- significado: a célula cujo texto, sem espaços nas pontas e em maiúsculas, é chave do `chip` aparece como selo com aquele fundo e aquela cor de letra. As outras células da coluna aparecem como texto comum. As cores são de alerta (vermelho: ex. `VENCIDO`, `INADIMPLENTE`, `+180 DIAS`), atenção (amarelo: ex. `VENCE HOJE`, `91-180 DIAS`) e ok (verde: ex. `EM DIA`, `NO PRAZO`);
- com o `chip` vem `larg_fixa` (a largura em que o selo não corta). A web pode usar ou ignorar.

**Fora, sempre:** `edicao`, `editar`, `abrir`, `detalhe`, `kpis_de`, `recortes`, `exportar_*`, chave com `_` e qualquer callable. Nesta entrega, a tabela da web não tem cartões que seguem o filtro nem recortes.

**Colunas permitidas.** A regra: as colunas da tabela do PC **depois do `montar`**, **menos TELEFONE**, na mesma ordem e com o mesmo `tipo` e `oculta`. O `montar` (`_status_nas_tabelas` e `_so_status`, com `STATUS_NAS_TABELAS["pl_inadimplencia"]`) põe três colunas de status logo depois de NOME:
- `STATUS PROTHEUS` (oculta);
- `STATUS` (o STATUS PLANNER renomeado: ATIVO/INATIVO);
- `SITUAÇÃO PLANNER` (oculta).

Não são dado pessoal e vão no pacote. A web não desenha coluna com `oculta: true`, mas a célula vem na linha.

**O bloco de status é opcional, as três juntas:** se o status falha no PC, o `_status_nas_tabelas` só põe um aviso, e a tabela sai sem as três colunas. Por isso a web aceita a tabela **com as três juntas, na posição e na ordem de baixo, ou sem nenhuma delas**. Qualquer outra combinação (uma ou duas das três, ou fora da posição) é recusada. As outras colunas são sempre obrigatórias, na ordem do PC. Sem o bloco: "Títulos" com 17 colunas e "Por cliente" com 16.

Lista conferida no `main` em `c8a9267` (nome e tipo):
- **"Títulos"** (20): `SITUAÇÃO` texto · `FAIXA` texto · `FILIAL` texto · `NF` texto · `PARC.` texto · `EMISSÃO` data · `VENCIMENTO` data · `DIAS ATRASO` int · `CLIENTE` texto · `NOME` texto · `STATUS PROTHEUS` texto (oculta) · `STATUS` texto · `SITUAÇÃO PLANNER` texto (oculta) · `CIDADE` texto · `UF` texto · `VENDEDOR` texto · `SUPERVISOR` texto · `CONDIÇÃO` texto · `VALOR` moeda · `SALDO` moeda.
- **"Por cliente"** (19): `SITUAÇÃO` texto · `FAIXA` texto · `CLIENTE` texto · `NOME` texto · `STATUS PROTHEUS` texto (oculta) · `STATUS` texto · `SITUAÇÃO PLANNER` texto (oculta) · `CIDADE` texto · `UF` texto · `VENDEDOR` texto · `SUPERVISOR` texto · `TÍTULOS VENCIDOS` int · `EM ATRASO` moeda · `MAIOR ATRASO` int · `A VENCER` moeda · `PRÓX. VENCIMENTO` data · `LIMITE` moeda · `PEDIDO EM ABERTO` moeda · `ÚLTIMA COMPRA` data.

**O PC confere antes de mandar:** o `pacote_web` (com o 4f) confere as duas tabelas por estas mesmas regras. Se não baterem, o farol vai **sem** `tabelas` e `cobranca` (cai no §10.1), com aviso no log sem dado pessoal, e os outros relatórios do pacote seguem.

**A web recusa o pacote inteiro** (com o motivo no log, sem dado pessoal; é a defesa, caso o PC não tenha conferido) quando:
- o `titulo` não é um dos dois;
- a lista de colunas não é igual à de cima (nome, ordem, `tipo` e `oculta`, com o bloco de status inteiro ou ausente);
- há `chip` fora de `SITUAÇÃO`, `FAIXA` e `STATUS`. Se a coluna mudar no PC, primeiro muda este contrato (acréscimo, PR do engenheiro-software), depois o código;
- aparece coluna `TELEFONE`, `CNPJ`, `CPF`, `E-MAIL` ou `EMAIL`;
- uma linha tem número de células diferente do número de colunas;
- há chave proibida.

`CLIENTE` é o código-loja do PC (ex.: `"001234-01"`). CNPJ não vai ("2 A").

**NOME sem documento (só no site; RN-POS-004, "CNPJ não vai ao site"):** a coluna `NOME` das duas tabelas vai com o texto de `cobranca_whatsapp.nome_sem_documento(nome)`, que tira o CPF/CNPJ do começo do nome quando o cadastro o traz ali. O PC continua igual: as abas do Tkinter mostram o nome como está. A "igualdade" com o PC vale com essa troca na coluna `NOME`.

**Igualdade:** célula a célula, a tabela da web é a do PC depois do `montar`, sem a coluna TELEFONE, com os mesmos `tons` e o mesmo `chip` de cada coluna. O `testes` compara.

#### 10.6.3 Bloco `cobranca`

```python
"cobranca": {
    "gerado_em": "2026-11-24T08:07:00-04:00",  # quando o PC montou a fila
    "web_epoca": "b7e1c0d2a4f94e0f8a51c3d2e6f70a19",  # época do diário do site
    "web_ate_seq": 41,          # §10.6.3, definição única abaixo
    "dias_recente": 7,          # cobranca_whatsapp.DIAS_RECENTE (RN-POS-002)
    "modelo": "Olá, {cliente}! ...",            # cobranca_whatsapp.MODELO
    "fila": [{
        "cod": "001234-01", "nome": "CLIENTE FICTICIO LTDA",
        "nome_msg": "FICTICIO", "cidade": "MANAUS", "uf": "AM",
        "vendedor": "VENDEDOR FICTICIO", "supervisor": "SUPERVISOR FICTICIO",
        "em_atraso": 1234.5, "maior": 35,
        "whatsapp": "5592900000000", "aviso": "",
        "titulos": [{"nf": "12345", "parc": "1", "venc": "2026-10-20",
                     "dias": 35, "saldo": 1234.5}],
        "mensagem": "Olá, FICTICIO! Tudo bem? ...",
        "ultimo": {"quando": "2026-11-21 10:15:00", "acao": "ENVIADO",
                   "origem": "PC"},
    }],
}
```

| Chave | Tipo | Regra |
|---|---|---|
| `gerado_em` | `str` ISO 8601 `-04:00` | a hora em que o robô montou a fila, **depois** de importar o diário do site. É o "hh:mm" do aviso "situação do PC até hh:mm" |
| `web_epoca` | `str` | a `epoca` do diário do site (§10.6.5) a que `web_ate_seq` se refere. `""` quando o robô nunca puxou o diário |
| `web_ate_seq` | `int` | **definição única:** o maior `seq` da época `web_epoca` cujo registro já estava gravado no `COBRANCA_WEB.csv` quando a fila foi montada, **tenha a confirmação dado certo ou não**. `0` quando nenhum |
| `dias_recente` | `int` | `7` |
| `modelo` | `str` | informativo: o modelo da mensagem do PC. A web **não** refaz a mensagem; usa a `mensagem` pronta |
| `fila` | `list[ItemFila]` | `cobranca_whatsapp.fila(...)` (RN-POS-001): só cliente INADIMPLENTE com título VENCIDO, do maior `em_atraso` para o menor |

`ItemFila` (as chaves de `cobranca_whatsapp.fila`, **sem `telefone_cad`**, mais `mensagem` e `ultimo`):

| Chave | Tipo | Regra |
|---|---|---|
| `cod` | `str` | código-loja, igual à coluna CLIENTE |
| `nome` | `str` | NOME da aba "Por cliente", sem o CPF/CNPJ do começo (`cobranca_whatsapp.nome_sem_documento`, RN-POS-004), igual à coluna `NOME` do site |
| `nome_msg` | `str` | o nome usado na mensagem (fantasia do cadastro, ou `nome`) |
| `cidade`, `uf`, `vendedor`, `supervisor` | `str` | da aba "Por cliente" |
| `em_atraso` | `float` | EM ATRASO |
| `maior` | `int` | MAIOR ATRASO (dias) |
| `whatsapp` | `str` | o número de `cobranca_whatsapp.celular()` (RN-POS-001): `"55"` + DDD + **9 dígitos (celular) ou 8 dígitos (fixo)**. O fixo vai preenchido, com o `aviso` "telefone fixo: pode não ter WhatsApp". O campo só fica `""` quando o número é inválido (curto), repetido (ex.: `99 99999999`) ou ausente, sempre com `aviso`. **O único lugar do pacote com telefone** |
| `aviso` | `str` | o aviso do `celular()` (`""` quando é celular válido) |
| `titulos` | `list[{"nf": str, "parc": str, "venc": "AAAA-MM-DD", "dias": int, "saldo": float}]` | os títulos VENCIDOS do cliente, do maior `dias` para o menor |
| `mensagem` | `str` | `cobranca_whatsapp.mensagem(item, modelo)`, pronta. A pessoa pode editar na tela; o texto editado **não** é guardado |
| `ultimo` | `{"quando": "AAAA-MM-DD HH:MM:SS", "acao": "ENVIADO" \| "PULADO", "origem": "PC" \| "WEB"} \| null` | vem de `cobranca_whatsapp.historico_origem(raiz) -> {cod: (quando, acao, maquina)}`: o último registro do cliente em qualquer `COBRANCA_*.csv`. `origem = "WEB"` quando `maquina == "WEB"`; senão `"PC"`. `null` = nunca cobrado. O `historico()` e a janela do PC não mudam |

**A situação na tela** (RN-POS-002) sai de `ultimo` e de `dias_recente`, calculada pela web com o dia de hoje em Manaus: `ENVIADO HOJE`, `ENVIADO dd/mm` (menos de 7 dias), `PULADO HOJE` ou nada. Antes, a web junta ao `ultimo` os registros do próprio diário daquele cliente que o PC ainda não viu, e vale o de `quando` maior:
- se `web_epoca` é a época atual do diário: os registros com `seq > web_ate_seq`;
- se não é (diário recomeçado, ou `web_epoca` vazia): **todos** os registros do diário.

A tela mostra "situação do PC até hh:mm" (o `gerado_em`).

**Quem recebe o quê** (RN-POS-004, "1 A"; o corte é no servidor, antes do HTML):

| Perfil | Cartões e gráficos | `tabelas` | `cobranca` e o botão |
|---|---|---|---|
| `admin`, `pos_venda` | sim | sim | sim |
| `gerente` | sim | sim | **não** (sem telefone e sem botão) |
| `diretor` e os outros que veem o farol | sim | não | não |

- Pedido de aba ou de ação fora do perfil = **403**, com teste por perfil.
- Sem exportar tabela, fila ou diário ("6 A").
- Página com tabela ou fila: `Cache-Control: no-store` e `<meta name="robots" content="noindex">`.
- Registro de acesso em `<BAP_WEB_DADOS>/acessos/`, guardado por 90 dias [SUPOSIÇÃO: 90 dias, a confirmar com o Alexandre]: login, rid, aba, ação e hora, sem cliente nem telefone.

#### 10.6.4 Rota do site: `POST /farol/pl_inadimplencia/cobranca`

- Sessão com login (cookie); **não aceita Bearer**. Perfil `admin` ou `pos_venda`, senão 403. CSRF obrigatório no campo `csrf` (o mesmo da sessão, como nas outras rotas POST); sem ele, 403.
- Corpo `application/x-www-form-urlencoded`:
  - `csrf`;
  - `pacote_sha`: o sha256 (hex) do pacote com que a página foi desenhada (a página manda sempre). É o sha256 dos **bytes do arquivo guardado** em `<BAP_WEB_DADOS>/pacotes/<nome>.json`, como a web gravou (depois do `_enxuto` e com o `recebido_em`), e não do corpo recebido do robô: assim a web recalcula o valor a qualquer momento;
  - `cliente`: o `cod` do item;
  - `acao`: `ENVIADO` ou `PULADO` (senão 400);
  - `telefone`: opcional, só com `ENVIADO`. É o número corrigido na tela ("5 A"), normalizado pelo `celular()`: celular ou fixo são aceitos. Se o `celular()` devolve `""`, a resposta é 400. Vale só para esse envio. O site é mais estrito que o PC, que aceita o número digitado sem normalizar.
- **De onde sai o item (o registro não se perde quando o pacote troca):**
  1. do pacote `pacote_sha`, se ele ainda está entre os 7 guardados e tem o `cliente` na fila;
  2. senão, do pacote vigente, se ele tem o `cliente` na fila;
  3. senão, **404** "abra o farol de novo". Isso só acontece se o pacote da página já saiu dos 7 guardados e o cliente saiu da fila.

  O `em_atraso` e o `titulos` (a quantidade) do registro saem desse item, nunca do navegador. O `pacote_sha` gravado é o do pacote de onde o item saiu.
- **ENVIADO precisa de número:** vale o `telefone` digitado (válido) ou, sem ele, o `whatsapp` do item. Se os dois estão vazios, a resposta é **400** e nada é gravado. `PULADO` não pede número.
- Clique duplo: o mesmo `usuario` + `cliente` + `acao` em menos de 60 s não grava de novo. A resposta traz o registro original com `"repetido": true`.
- Resposta 200 JSON: `{"ok": true, "seq": int, "id": str, "situacao": "ENVIADO HOJE" | "PULADO HOJE", "repetido": bool}`.
- O link `wa.me`/`whatsapp://` é montado no navegador com o número e o texto da tela. O servidor não chama nenhuma API do WhatsApp.

#### 10.6.5 Diário do site: `<BAP_WEB_DADOS>/cobranca/`

**Arquivos:**
- `COBRANCA_WEB_<AAAA-MM>.jsonl`: um por mês (o mês de `quando`). UTF-8, **um objeto JSON por linha**, só acréscimo, com `fsync` depois de cada linha. Nenhuma linha é alterada nem apagada; a limpeza é **por arquivo inteiro** (abaixo).
- `estado.json`: o estado do diário, gravado de forma atômica (arquivo temporário + `fsync` + `os.replace`):
  `{"epoca": str, "ultimo_seq": int, "confirmado_ate": int, "confirmado_em": "AAAA-MM-DD HH:MM:SS", "arquivos": {"COBRANCA_WEB_<AAAA-MM>.jsonl": {"maior_seq": int, "confirmado_em": "AAAA-MM-DD HH:MM:SS" | null}}}`.
  - O contador de `seq` mora aqui (`ultimo_seq`). Ele sobrevive à limpeza dos jsonl e nunca volta atrás dentro da mesma época.
  - **`epoca`**: `uuid4().hex`, criada quando o `estado.json` não existe (primeiro uso ou disco perdido). Sem `estado.json` e sem jsonl, o `seq` recomeça em 1, numa época nova.
  - Se há jsonl sem `estado.json`, a web não inventa estado: cria época nova e começa o `seq` acima do maior `seq` dos jsonl que ainda existem.

**Registro** (uma linha do jsonl):

```json
{"seq": 42, "id": "3f2b8c1e-6a0d-4c1b-9e7a-2d5f0b1c4a9e", "quando": "2026-11-24 15:02:11", "usuario": "login.web", "cliente": "001234-01", "telefone": "5592900000000", "em_atraso": 1234.5, "titulos": 2, "acao": "ENVIADO", "pacote_sha": "9a1c...e0"}
```

| Campo | Tipo | Regra |
|---|---|---|
| `seq` | `int` | de `estado.ultimo_seq + 1`; cresce de 1 em 1 dentro da época, nunca reaproveitado |
| `id` | `str` | `uuid4` do servidor, texto com hífens. É a chave de idempotência no PC |
| `quando` | `str` `"AAAA-MM-DD HH:MM:SS"` | hora de Manaus (`TZ=America/Manaus` obrigatório), no formato do PC (`historico` compara texto) |
| `usuario` | `str` | o login do site |
| `cliente` | `str` | o `cod` do item |
| `telefone` | `str` | `ENVIADO`: o número usado (`55` + DDD + 8 ou 9 dígitos, nunca vazio). `PULADO`: o `whatsapp` do item, como o `registrar` do PC (pode ser `""`) |
| `em_atraso` | `float` | do item (§10.6.4) |
| `titulos` | `int` | `len(item["titulos"])` |
| `acao` | `"ENVIADO" \| "PULADO"` | |
| `pacote_sha` | `str` | o sha256 (hex) de onde o item saiu: no formato 2, o `sha256` do farol `pl_inadimplencia` no índice (§10.8.6); no formato 1, o do pacote inteiro |

**Retenção ("3 A"), por arquivo:**
- Só arquivo de **mês já fechado** pode sair.
- `arquivos[<nome>].maior_seq` é o maior `seq` do arquivo; num mês fechado, ele não muda mais (é o `maior_seq` final).
- **A rotina de limpeza** roda em todo `POST /api/cobranca/confirmar` aceito (200, mesmo o repetido) e na partida do app. Ela faz, nesta ordem:
  1. para todo arquivo de **mês fechado** (em Manaus) com `maior_seq <= confirmado_ate` e `confirmado_em` nulo: grava `confirmado_em` = agora. Isso cobre os dois casos: a primeira confirmação que alcança o `maior_seq` final, e o mês que fecha já coberto por uma confirmação anterior;
  2. apaga os arquivos com `confirmado_em` de 30 dias ou mais e tira a entrada deles de `arquivos` (o `ultimo_seq` fica);
  3. grava o `estado.json` (atômico) só se algo mudou.
- Cada linha fica, portanto, **no mínimo** 30 dias depois de confirmada.
- Arquivo de mês aberto nunca é apagado.
- Arquivo com linha não confirmada nunca é apagado.

#### 10.6.6 API do robô (Bearer `BAP_WEB_TOKEN`, só HTTPS)

- Mesma autenticação do `POST /api/pacote`: `Authorization: Bearer <BAP_WEB_TOKEN>`. Sem ele ou errado = 401 com `WWW-Authenticate: Bearer`. **Não aceita cookie de sessão.**
- Respostas em `application/json`.

**`GET /api/cobranca?desde=<seq>`**
- `desde`: `int >= 0`; ausente = 0; inválido = 400.
- 200: `{"epoca": str, "linhas": [Registro, ...], "ate_seq": int, "mais": bool}`.
  - `epoca`: a época atual do diário (§10.6.5);
  - `linhas`: os registros guardados com `seq > desde`, em ordem de `seq`, no formato do §10.6.5, no máximo 1000;
  - `ate_seq`: o maior `seq` devolvido, ou `desde` se `linhas` vier vazia;
  - `mais`: `true` quando há mais registros depois de `ate_seq`. O robô chama de novo com `desde = ate_seq`.
- Não muda nada no servidor.

**`POST /api/cobranca/confirmar`**, corpo `application/json` `{"epoca": str, "ate_seq": int}`
- Marca como confirmados todos os registros com `seq <= ate_seq`.
- Idempotente: confirmar de novo o mesmo valor, ou um menor, responde 200 e não muda `confirmado_ate`. A rotina de limpeza do §10.6.5 roda do mesmo jeito; ela não conta como mudança para a idempotência.
- Erros:
  - `epoca` diferente da atual = 409 `{"erro": "epoca"}`;
  - `ate_seq` maior que `ultimo_seq` = 409;
  - campo ausente, não inteiro ou negativo = 400.
- 200: `{"ok": true, "epoca": str, "confirmado_ate": int}` (o maior `ate_seq` já confirmado).

#### 10.6.7 Volta ao PC: `RELATORIOS/_COBRANCA_WHATSAPP/COBRANCA_WEB.csv`

- Gravado só pelo robô (PC DT-AMADMBAP-03), por `cobranca_whatsapp.importar_web(raiz, linhas, nomes=None) -> int` (modulo-posvenda). É uma função sem tela, testável com `tmp_path`, com `test_RN_POS_003_...`.
  - `linhas`: os `Registro` do GET.
  - `nomes`: `{cod-loja: NOME}` da aba "Por cliente" do farol da rodada. Cliente fora dela = `""`. Atenção: é outro `nomes`, diferente do da `fila()`, que é `{cod6: fantasia}`.
  - Devolve quantas linhas acrescentou. Pula `id` que já está no arquivo (idempotente).
  - Erro de disco (arquivo aberto no Excel, OneDrive) levanta exceção, e o robô não confirma.
- Formato: `;`, UTF-8 com BOM só na criação (como o `registrar`), só acréscimo. Colunas: `CAMPOS_CSV + ("id",)` =
  `quando;maquina;usuario;cliente;nome;telefone;em_atraso;titulos;acao;id`.
  - `maquina` = `"WEB"`; `usuario` = o login do site; `em_atraso` com 2 casas e ponto (`f"{v:.2f}"`); o resto como veio do registro.
  - O nome de máquina `WEB` fica **reservado** para o robô. Um PC com esse nome gravaria no mesmo arquivo; não pode existir.
- O `historico()` e o `historico_origem()` já leem o arquivo pelo glob `COBRANCA_*.csv`: o PC passa a ver o que foi cobrado no site sem mudar a janela. Os `COBRANCA_<MAQUINA>.csv` das assistentes ficam intocados (regra 7 do `CLAUDE.md`).

**Estado do robô:** `{"epoca": str, "ate_seq": int}`, num arquivo de estado do modulo-robo [SUPOSIÇÃO: em `RELATORIOS/_COBRANCA_WHATSAPP/`, fora do glob `COBRANCA_*.csv`]. `ate_seq` = o maior `seq` daquela época já gravado no `COBRANCA_WEB.csv`.

**A rodada do robô** (4f, 08h e 14h, "4 A"), nesta ordem:
1. `GET /api/cobranca?desde=<estado.ate_seq>` (repete enquanto `mais`).
   - Se a `epoca` da resposta é diferente da `estado.epoca` (disco perdido, ou primeiro uso), o robô descarta a resposta e refaz o GET com `desde=0`. O `id` impede repetir o que já estava no CSV.
   - Estado perdido no PC: `desde=0` com a época da resposta. Também é seguro.
2. `importar_web(raiz, linhas, nomes)`. Se gravou sem erro, o estado passa a `{epoca, ate_seq: maior seq gravado}` (ou continua o mesmo, se não veio nada).
3. `POST /api/cobranca/confirmar {"epoca", "ate_seq": estado.ate_seq}`, em toda rodada com `ate_seq > 0`. Isso refaz uma confirmação que falhou antes, já que é idempotente.
4. Monta `tabelas` e `cobranca` (`cobranca_whatsapp.pacote_web(..., web_ate_seq=estado.ate_seq, gerado_em=...)`, com `web_epoca = estado.epoca`) e envia o pacote (`POST /api/pacote`).

**Falhas:**
- GET com 404 (web antiga), 401, 5xx ou falha de rede: o robô registra no log (sem dado pessoal), não importa nem confirma e segue com o pacote, com o estado de antes.
- Falha no `importar_web`: não confirma; o estado não muda.
- Falha só no confirmar: segue; a próxima rodada confirma de novo.
- 401 aparece no log como "token da web recusado", para o Alexandre trocar o `BAP_WEB_TOKEN`.

#### 10.6.8 Ordem de publicação

A web publicada hoje recusa `tabelas` no farol (§10.1). Por isso:
1. **web antes**: aceita e valida `tabelas` e `cobranca` no `pl_inadimplencia`, desenha as abas, abre a rota do §10.6.4 e a API do §10.6.6, e passa a guardar 7 pacotes. Sobe ao Render com o merge no `main` (deploy automático, ADR 0001, adendo 4), e o `/saude` mostra a versão nova;
2. **robô depois**: o "instale" do Alexandre no PC (regra 11 do `CLAUDE.md`).

Web nova com robô antigo: o farol segue como no §10.1 (sem abas novas), e o GET não é chamado. A versão fica em 1. Renomear ou tirar chave desta seção = v2 com ADR.

### 10.7 Todas as abas de Pedidos, Entregas e Visita (`pv_pedidos`, `pl_entregas`, `vc_visitas`; T-0017, entregas 3 a 5)

Acrescentada em 25/11/2026. Fontes: R-20261124-223741-alexandre (Pedidos: "Quero todas"), R-20261124-223958-alexandre (Entregas e Visita: "1 B"), as regras das tabelas da Inadimplência (R-20261124-192008-alexandre: "1 A", "2 A", "6 A") e a RN-GER-006. Substitui, nesses três faróis, o "3 A" do R-20261124-175838-alexandre. ADR 0001, adendo 5. **Acréscimo compatível: o contrato continua na v1.** Vale sobre o §10.1, **só** nesses três `rid`.

**Decisões em aberto:** D1 a D6 (§10.7.9). Onde o texto depende de uma delas, a marca é **[Dn]**, e o texto segue a recomendação. Se o Alexandre escolher outra opção, esta seção muda antes do código.

Donos: o núcleo do PC dá as funções puras (modulo-farois: `relatorios_nucleo`); o robô monta e confere (modulo-robo: o 4f, `bap_automation`); a web valida e desenha (modulo-web).

#### 10.7.1 Chave nova no farol e as abas da web

```python
relatorios["pv_pedidos"] = {
    "forma": "farol", ...,                  # as chaves do §10.1, sem mudança
    "tabelas": [TabelaWeb7("Pedidos"), TabelaWeb7("Solicitação BAP")],
}
```

| Chave | Tipo | Regra |
|---|---|---|
| `tabelas` | `list[TabelaWeb7]` (§10.7.2) | opcional. Cada aba é independente: vão as que passaram na conferência do PC (§10.7.6), na ordem da tabela abaixo, sem repetir. Sem a chave, o farol se comporta como no §10.1 (robô antigo) |

As abas da web, na ordem do PC. A chave vai na URL (`/farol/<rid>?aba=<chave>`). Aba sem tabela no pacote não aparece.

| `rid` | `resumo` (cartões, painel; §10.1) | abas de tabela: chave → `titulo` |
|---|---|---|
| `pv_pedidos` | "Resumo gerencial" | `pedidos` → "Pedidos" (com 3 juntas) · `solicitacao` → "Solicitação BAP" (7 sub-abas) |
| `pl_entregas` | "Resumo gerencial" | `entregas` → "Entregas" (com 1 junta) |
| `vc_visitas` | "Resumo gerencial" | `supervisor` → "Por supervisor" · `vendedor` → "Por vendedor" · `dia` → "Dia a dia" · `aderencia` → "Aderência dia a dia" · `cliente` → "Cliente a cliente" · `prospeccao` → "Prospecção" · `indicacao` → "Indicação" |

#### 10.7.2 `TabelaWeb7`: o `TabelaWeb` do §10.6.2 com 7 chaves opcionais

Chaves do §10.6.2, com o mesmo sentido: `titulo`, `colunas`, `linhas`, `tons`, `total`, `filtros`. **Diferenças em relação ao §10.6.2:**
- `tons`: no `pv_pedidos` (que está em `LINHA_PINTADA`) vêm com cor (`"grave"`, `"alerta"`, `"atencao"`, `"ok"`, `""`) e a web pinta a linha. No `pl_entregas` e no `vc_visitas` vêm todos `""`;
- `filtros`: o item `dict` pode ter `"oculto": true` = filtro aplicado com o `padrao` e sem caixa na tela (o MÊS do "Pedidos" e do "Entregas"). Filtro que cita coluna cortada sai. **`filtros` é opcional, e `[]` vale o mesmo que não ter a chave** (a web aceita os dois; ex.: as sub-abas da "Solicitação BAP");
- `total`: a linha de total do PC, com as regras do §10.7.2.1. Fica fora de `linhas`.

| Chave nova | Tipo | Regra |
|---|---|---|
| `juntas` | `list[Junta]` | só em "Pedidos" (3) e "Entregas" (1). Abaixo |
| `subabas` | `list[TabelaWeb7]` | só em "Solicitação BAP": uma por aba do arquivo. Aí `colunas` e `linhas` da tabela-mãe vêm `[]` |
| `kpis_padrao` | `list[Kpi]` (§4) | os cartões que o PC mostra ao abrir a aba: `relatorios_nucleo.chamar_kpis_de(kpis_de, linhas_padrao)`, com as linhas dos filtros padrão e sem recorte (§11.2). **Cartão inteiro, como os do Resumo:** `rotulo`, `valor`, `cor`, `detalhe` e, quando o PC põe, `linhas` (o `detalhe` do `Kpi` não é o `detalhe` de pedido da tabela, que sai). Ausente quando a tabela do PC não tem `kpis_de`: aí a aba mostra os `kpis` de cima. A web mostra `kpis_padrao` só enquanto os filtros estão no padrão, sem recorte e sem estado. Com outro filtro, recorte ou estado, os cartões da aba saem, e fica o aviso `AVISO_CARTOES` do §10.7.6 |
| `recortes_linhas` | `list[{"rotulo": str, "linhas": list[int]}]` | os recortes do PC (`recortes`, §11.4), prontos: para cada rótulo, na ordem do PC, os índices (base 0, em `linhas`) das linhas que o recorte deixa. Só recorte por função. Recorte `{"top": N}` não existe nessas tabelas hoje: se aparecer, fica fora, com aviso no log |
| `uf_linhas` | `list[str]` | uma UF por linha (`""` = sem UF), pela RN-GER-006: no "Pedidos", a UF da **filial da nota** (`relatorios_nucleo.uf_do_nome_da_filial` da coluna FILIAL); no "Entregas" e na junta de pendências, a UF do **cliente** (coluna UF). Ausente no Visita e nas juntas do Pedidos. Usada pelo filtro de estado [D5] |
| `zebra` | `bool` | só apresentação ("Pedidos") |
| `inteira` (em `Coluna`) | `bool` | o texto da coluna não encolhe (ETAPA do "Entregas") |

**`Junta`** (a tabela de baixo, na mesma aba; `bap_relatorios.VistaTabela._ligadas`):

| Chave | Tipo | Regra |
|---|---|---|
| `titulo` | `str` | o título do quadro no PC (pode diferir do `tabela.titulo`; lista no §10.7.3) |
| `liga` | `[col_junta, col_tabela, sep \| null] \| null` | com `liga`, a junta mostra só as linhas cujo valor em `col_junta` (partido por `sep`, cada pedaço sem espaços e sem zeros à esquerda) está entre os valores de `col_tabela` das linhas visíveis da tabela de cima, **todas as páginas**, depois de filtro, recorte e estado. `null` = todas as linhas da junta |
| `mostrar` | `list[str]`, opcional | as colunas que o PC mostra no quadro. A web mostra só essas (o pacote leva todas) |
| `tabela` | `TabelaWeb7` | sem `juntas` e sem `subabas` |

**`Coluna`: as formas de selo além do `chip` por texto do §10.6.2** (a cor sai do PC; a web não inventa cor):
- **`chip` por faixa** (`list`), só em coluna de número: `[[ate | null, fundo | null, texto | null], ...]`. Vale a primeira faixa com `valor <= ate` (`null` = sem teto); `fundo` `null` = número sem selo (`bap_visual.Tabela._faixa_de`). No PC: `relatorios_nucleo.CHIP_SLA()` e `FAIXA_PCT_META`;
- **`barra`**: `{"max": número, "faixas": [[ate | null, fundo, texto], ...]}`: barra de progresso com o número ao lado (`relatorios_nucleo.BARRA_ATENDIDO`);
- **`chip_tom`**: `str`, o **nome** da coluna oculta da mesma tabela cujo valor dá o selo. No PC é o índice; no pacote vai o nome, para não depender da posição depois do corte. Paleta fixa (`bap_visual.py`, selo pela linha): `ok` `["#E5F3DF", "#2F7D32"]`, `atencao` `["#FFF1C7", "#8A5A00"]`, `alerta` `["#B3261E", "#FFFFFF"]`, `cinza` `["#E4E7E4", "#69736D"]`; outro valor = número sem selo.

Selo só nas colunas marcadas no §10.7.3. Em outra coluna, a web recusa.

**Fora, sempre** (em qualquer nível de `tabelas`): `edicao`, `editar`, `abrir`, `detalhe`, `kpis_de`, `total_de`, `totais_por`, `recortes` (a forma do PC, com callable), `ordem_exportar`, `cores_celulas` (só Excel/PDF), `so_exportar`, `solicitacao_bap`, `pdf*`, `nota_pdf`, chave com `_` e qualquer callable. O "Ver pedido" (`detalhe_pedido`, §11.1) fica no PC [D4].

##### 10.7.2.1 A linha de total (`total`)

A linha TOTAL do PC vai **à parte**, na chave `total` (a mesma do §10.6.2), nunca em `linhas`. Forma: `list[Celula] | null`, uma célula por coluna (o mesmo tamanho de `colunas`). Hoje só o Visita tem total ("Por supervisor", "Por vendedor", "Dia a dia" e "Aderência dia a dia").

**O PC normaliza** (o robô, antes de conferir; função pura):
1. célula `""` ou `None` → `null`, em qualquer coluna;
2. o rótulo do PC (a 1ª célula da linha, quando é texto; hoje sempre `"TOTAL"`) vai para a **1ª coluna visível de tipo `texto`** e sai de onde estava (se já está nela, fica). Ex.: no "Dia a dia", o PC põe `"TOTAL"` em `DATA` (data): no pacote, `DATA` = `null` e `DIA` = `"TOTAL"`;
3. as outras células ficam como o PC calculou (número em coluna de número; texto pronto em coluna `hora`);
4. célula que ainda não casa com o `tipo` da coluna (texto em `int`, `moeda`, `pct`, `num`, `data`, `dia`...) → `null`. Nenhum número é inventado.

**A web valida:** tamanho igual ao de `colunas`; em cada célula, `null` ou o valor do `tipo` (§10.6.2: número em coluna de número, data ISO em `data`/`dia`, `str` em `texto` e `hora`). Senão, recusa o pacote ("total inválido").

**A web desenha** a linha fixa no fim da tabela, em negrito, como no PC, **só** quando as linhas visíveis são todas as da tabela (a regra do §11.3, item 2). Com filtro, recorte ou estado, sem total.

**Igualdade:** o `total` é o do PC, depois dos 4 passos acima.

#### 10.7.3 Colunas por tabela

Conferidas no `main` em `2d182bd`, com `montar(rid, raiz, hoje=20/11/2026, params={"ANO": "2026", "MÊS": "11"})` nas bases do repositório. Formato: `NOME` tipo; (o) = oculta; selo entre colchetes. A lista é a do PC **depois do `montar`**, menos as colunas que saem (§10.7.4), na mesma ordem, com o mesmo `tipo` e `oculta`. **Limpa** = a célula passa pela limpeza de documento do §10.7.4.

**`pv_pedidos`**
- **"Pedidos"** (33; não sai nenhuma): `DT. PED` dia · `FATURAR ATÉ` dia · `PEDIDO` texto · `PED. MÁX.` texto · `CÓD.` texto · `RAZÃO SOCIAL` texto (limpa) · `FANTASIA` texto (limpa) · `UF` texto · `CIDADE` texto · `LIMITE` moeda · `DISP.` moeda · `ATRASO` moeda · `VOL.` num · `R$ TABELA` moeda · `R$ VENDA` moeda · `% DESC.` pct1 · `SLA` int [chip por faixa] · `% ATENDIDO` pct [barra] · `ANÁLISE CRÉDITO` texto · `COND. PAGTO` texto · `SITUAÇÃO` texto · `FILIAL` texto · `PRAZO` texto · `VENDEDOR` texto · `NF` texto · `DT. NF` dia · `R$ TABELA CHEIA` moeda (o) · `CÓD. AUTORIZAÇÃO` texto (o) · `AUTORIZADO POR` texto (o) · `MÊS` texto (o) · `ENTREGUE EM` dia (o) · `PRODUTO` texto (o) · `CHAVE` texto (o). Sem o bloco de status (o `STATUS_NAS_TABELAS` não tem `pv_pedidos`). Filtros: `MÊS` (padrão = mês do pacote, oculto), `SITUAÇÃO` (padrão `EM ABERTO`), `CIDADE`, `VENDEDOR`, `PRODUTO` (multi). Recortes: os 4 do PC.
  - Junta "Gerar ID de separação CD" → tabela "Gerar separação CD" (10): `DATA` dia · `UF` texto · `CIDADE` texto · `PEDIDOS` texto · `FORN.` texto · `CÓD. PROD.` texto · `DESCRIÇÃO` texto · `QTD` num · `COLETAR EM` texto · `FILIAL DEST.` texto. `liga = ["PEDIDOS", "PEDIDO", "|"]`.
  - Junta "Gerar reversa de lojas" → tabela "Gerar reversa de lojas" (10): as mesmas colunas. `liga = ["PEDIDOS", "PEDIDO", "|"]`.
  - Junta "Analítico por pedido" → tabela "Analítico produto" (16): `PEDIDO` texto · `DATA` dia · `CIDADE` texto · `FILIAL` texto · `FORN.` texto · `CÓD. PROD.` texto · `DESCRIÇÃO` texto · `QTD` num · `EST. FRW` num · `PEDIDOS ANTES` num · `DISP. P/ ESTE` num · `ATENDIDO` num · `FALTA` num · `CLIENTE` texto (limpa, código e nome) · `FILIAL BAP` texto (o) · `VALOR FALTANTE` moeda. `liga = ["PEDIDO", "PEDIDO", null]`.
- **"Solicitação BAP"**: não é tabela do `montar`. O robô lê `solicitacao_bap.ler(raiz)` (o `RELATORIOS/SOLICITACAO_BAP.xlsx` que ele mesmo grava) e manda uma `subaba` por aba do arquivo, na ordem de `solicitacao_bap.ABAS_TELA`: "Solicitacao Lojas", "Solicitacao CD", "Solicitacao FRW", "Solicitacao Manual", "DETALHADO_PEDIDO", "ProdutosExcluir", "FiliaisExcluir" (aba ausente no arquivo não vai). Colunas = o cabeçalho da aba, como o PC mostra; o `tipo` segue a regra da tela (`bap_relatorios.AbaSolicitacaoBap.carregar`): `num` em QUANTIDADE, DEMANDA_PEDIDO, JA_SOLICITADO, SALDO_A_SOLICITAR e ESTOQUE_NA_ORIGEM; `data` em DATA quando todas as células são data; `texto` no resto. Como o cabeçalho é do arquivo, aqui não há lista fixa: valem as colunas que saem (§10.7.4) e a limpeza em `CLIENTE` (DETALHADO_PEDIDO). Sem filtros nem recortes (o PC só tem a busca). A troca de loja de coleta (duplo clique, grava) fica no PC. Linhas [D3].

**`pl_entregas`**
- **"Entregas"** (22; não sai nenhuma): `MÊS` texto (o) · `SITUAÇÃO` texto · `SLA` int [`chip_tom` = `"TOM SLA"`] · `DT. PED` dia · `DT. NF` dia · `DT. PREVISTA` dia · `DT. REAL` dia · `UF` texto · `CIDADE` texto · `CLIENTE` texto (limpa, código e nome) · `VLR NF` moeda · `VLR FRETE` moeda · `TRANSPORTADORA` texto · `RESPONSÁVEL` texto [D6] · `TBL FRETE` moeda · `VLR REAL FRETE` moeda · `ETAPA` texto (inteira) · `NF` texto · `FILIAL` texto · `LOCAL/FRETE` texto (o) · `TOM SLA` texto (o) · `PRAZO` texto (o) [chip por texto]. A linha do PC tem uma célula a mais (a chave da entrega): o robô corta no número de colunas. Filtros: `MÊS` (padrão = mês do pacote, **oculto**: com a D2 A só há esse mês), `SITUAÇÃO`, `ETAPA`, `PRAZO`, `FILIAL`. A edição (duplo clique, grava em `ACOMPANHAMENTO_POS_VENDA.xlsx`/`_EDICOES_POS_VENDA`) fica no PC.
  - Junta "Pendências dos meses anteriores" → tabela com o mesmo título (22): as mesmas colunas, com `MÊS` **visível**. `liga = null`. Sem filtros próprios.

**`vc_visitas`** (sem o bloco de status; `tons` todos `""`)
- **"Por supervisor"** (21): `SUPERVISOR` texto · `REPRES.` int · as **18 de métrica** · `CHAVE` texto (o).
- **"Por vendedor"** (24): `SUPERVISOR` texto · `VENDEDOR` texto · `CARGO` texto (o) · `FILIAL` texto (o) · `CÓD.` texto (o) · as 18 de métrica · `CHAVE` texto (o).
- **"Dia a dia"** (25): `DATA` data · `DIA` texto · `SUPERVISOR` texto · `VENDEDOR` texto · `CARGO` texto (o) · `SITUAÇÃO` texto · as 18 de métrica · `CHAVE` texto (o).
  - As **18 de métrica**, nesta ordem: `META` num · `VISIT.` int · `% META` pct [chip por faixa] · `% CONV.` pct · `% FORA DE ROTA` pct · `CAD.` int · `CAD. C/ COMPRA` int · `PROSP.` int · `INÍCIO` hora · `ÚLT. ATIV.` hora · `JORNADA LÍQ.` hora · `DIAS < JORN. LÍQ.` int · `INTERV. ALMOÇO` hora · `DIAS ALMOÇO > MÁX.` int · `TMA` hora · `TMD` hora · `KM` num · `KM/CLIENTE` num1.
- **"Aderência dia a dia"** (2 + N + 1; as colunas mudam com o mês): `SUPERVISOR` texto · `VENDEDOR` texto · N colunas `dd/mm DIA` pct (cada dia com agenda de vendedor, até hoje; `DIA` em SEG, TER, QUA, QUI, SEX, SÁB, DOM; N de 1 a 31) · `% ADERÊNCIA ACUM. ATÉ dd/mm` pct. A web confere pelo padrão `^\d{2}/\d{2} (SEG|TER|QUA|QUI|SEX|SÁB|DOM)$` e `^% ADERÊNCIA ACUM\. ATÉ \d{2}/\d{2}$`.
- **"Cliente a cliente"** (24): `DATA` data · `DIA` texto · `SUPERVISOR` texto · `VENDEDOR` texto · `SITUAÇÃO` texto · `CÓD.` texto (código-loja) · `CLIENTE` texto (limpa) · `NOME FANTASIA` texto (limpa) · `SEGMENTO` texto · `BAIRRO` texto · `CIDADE` texto · `CURVA` texto · `STATUS` texto · `DIAS S/ COMPRA` int · `ATRASO` moeda · `SEQ. PREV.` texto · `SEQ. REAL` texto · `INÍCIO` hora · `FIM` hora · `ATEND.` hora · `PEDIDO NO DIA` texto · `VALOR PEDIDO` moeda · `JUSTIFICATIVA` texto [D6] · `ATEND. SEG.` int (o).
- **"Prospecção"** (14 de 18; saem `CNPJ`, `CONTATO`, `TELEFONE` e `FOTO`): `DATA` data · `HORA` hora · `DIA` texto · `SUPERVISOR` texto · `VENDEDOR` texto · `STATUS` texto · `FONTE` texto · `ESTABELECIMENTO` texto (limpa) · `SEGMENTO` texto · `CIDADE` texto · `UF` texto · `RESULTADO` texto [D6] · `LINHAS DE INTERESSE` texto [D6] · `OBSERVAÇÃO` texto [D6].
- **"Indicação"** (14 de 17; saem `CONTATO`, `TELEFONE` e `CNPJ`): `DATA` data · `DIA` texto · `SUPERVISOR` texto · `VENDEDOR` texto · `SITUAÇÃO` texto · `CÓD. QUEM INDICOU` texto · `CLIENTE QUE INDICOU` texto (limpa) · `INDICADO` texto (limpa) · `CIDADE` texto · `BAIRRO` texto · `SEGMENTO` texto · `VISITADA EM` data · `OBSERVAÇÃO` texto [D6] · `REGISTRADO EM` texto.

Visita não tem recorte por estado (RN-GER-006: a tabela não traz a UF do cliente) e mantém o aviso "Sem filtro por estado: os cartões mostram a BAP inteira." (§10.1).

**Mudou no PC?** Primeiro muda esta lista (acréscimo, PR do engenheiro-software), depois o código. Até lá, o PC deixa a aba fora (§10.7.6), e as outras seguem.

#### 10.7.4 Dado pessoal: o que sai e a limpeza (no PC, antes do envio)

- **Colunas que nunca vão ao site.** Esta lista é a **fonte única** (RD-0021). Vale em qualquer tabela, junta ou sub-aba destes três `rid` e no bloco `tabela` do painel de qualquer farol. O nome da coluna é comparado inteiro, sem acento e em maiúsculas. A web recusa o pacote que trouxer uma delas. (`FOTO` está na lista porque o nome do arquivo da foto traz o CNPJ.)

  ```text colunas-fora
  TELEFONE
  CELULAR
  WHATSAPP
  CNPJ
  CPF
  E-MAIL
  EMAIL
  CONTATO
  FOTO
  ENDERECO
  ```

  O robô (`bap_automation`) e a web (`web/app/render.py`, de onde o `tabelas` importa) têm cada um **uma** cópia desta lista. Um teste do `testes` lê o bloco `colunas-fora` deste arquivo e confere que as duas cópias são iguais a ele. A recusa do bloco `tabela` do painel por coluna de cliente (nome com CLIENTE, RAZÃO ou FANTASIA, §10.1) é regra a mais, própria do bloco, e não repete esta lista.
- **Nome de cliente ou estabelecimento (as colunas "limpa"):** a célula passa por uma função pura do núcleo (modulo-farois; RN-GER-011):
  - `relatorios_nucleo.sem_documento(texto) -> str`: tira o CPF/CNPJ do **começo** (como `cobranca_whatsapp.nome_sem_documento`), do **fim** (11 ou 14 dígitos, com ou sem pontuação: o MEI "NOME 12345678900") e qualquer CPF/CNPJ **formatado** no meio;
  - `relatorios_nucleo.cliente_sem_documento(texto) -> str`: para as colunas "código - nome" (`ctx.nome_cliente`, ex.: `"001234 - NOME"`). Mantém o código do começo (`^\d{6}(-\d{2})? - `) e aplica `sem_documento` só ao nome;
  - **por quê:** o `nome_sem_documento` de hoje (1) apaga o código do começo (`"001234 - NOME"` vira `"NOME"`), e (2) não vê o CPF no fim. Medido nas bases: "Pedidos" `RAZÃO SOCIAL` 222 com documento no começo e **84 com CPF no fim** (de 2.216 linhas); "Cliente a cliente" `CLIENTE` 198 e 30 (de 1.441); "Entregas" `CLIENTE` 19 e 4 (de 1.390).
- **Texto livre** (`JUSTIFICATIVA`, `OBSERVAÇÃO`, `RESULTADO`, `LINHAS DE INTERESSE`) [D6]: vai, depois de `relatorios_nucleo.texto_sem_contato(texto)`, que troca telefone, e-mail e CPF/CNPJ achados no texto por `"[removido]"`. Nas bases, nenhum caso hoje.
- **Nome de pessoa da equipe:** `VENDEDOR` e `SUPERVISOR` vão ("2 A"). `AUTORIZADO POR` (oculta) e `RESPONSÁVEL` (o motorista da entrega) vão como o nome do vendedor [D6].
- **Cartões, blocos e frases:** como no §10.1, sem nome de cliente.
- **Igualdade:** célula a célula, a tabela da web é a do PC depois do `montar`, sem as colunas que saem e com as células limpas. O `testes` compara.

#### 10.7.5 Quem vê (corte no servidor, antes do HTML)

| Perfil | Resumo (cartões e gráficos) | Abas de tabela |
|---|---|---|
| `admin` | sim | todas |
| `gerente` | sim | todas (não há telefone nem botão nesses faróis) |
| perfil do farol: `pre_venda` (Pedidos), `pos_venda` (Entregas), `vendas` (Visita) | sim | todas [D1] |
| `diretor` | sim | nenhuma |

- Quem não vê o farol continua sem ver (`web/app/render.FAROIS`).
- Aba fora do perfil = **403**, com teste por perfil e por aba. Sem exportar ("6 A").
- Página com tabela: `Cache-Control: no-store` e `<meta name="robots" content="noindex">`. Registro de acesso como no §10.6.3 (login, rid, aba e hora; sem cliente).

#### 10.7.6 Conferência no PC e defesa na web

**O PC confere cada aba antes de mandar** (`bap_automation`, modulo-robo): as colunas depois do corte batem com o §10.7.3 (nome, ordem, `tipo`, `oculta` e a forma do selo); cada linha tem o número de colunas (o robô corta a célula a mais); `recortes_linhas` e `uf_linhas` coerentes com `linhas`. Se uma aba não bate, **só ela** fica fora (com as juntas). As outras abas e os outros relatórios seguem. O motivo técnico vai só para o log (uma linha por aba, sem dado pessoal). No farol vai **um** aviso, com todas as abas que ficaram fora.

**Os textos de aviso desta seção** (fonte única, RD-0024 e RD-0027; robô e web usam constantes com estes textos, e os testes os citam daqui):

| Constante | Quem põe | Texto |
|---|---|---|
| `AVISO_ABAS_FORA` | o robô, em `avisos` do farol | `Abas fora desta atualização: {lista}. Veja no PC.` `{lista}` = os títulos das abas que ficaram fora, na ordem do §10.7.1, separados por `", "`. Ex.: "Abas fora desta atualização: Dia a dia, Prospecção. Veja no PC." Um aviso só, mesmo com uma aba |
| `AVISO_CARTOES` | a web, na aba de tabela | `Cartões sem filtro. Com filtro, veja as linhas na tabela.` Aparece no lugar dos cartões da aba quando há filtro fora do padrão, recorte ou estado (§10.7.2, `kpis_padrao`) |
| `AVISO_PARCIAIS_FORA` | o robô, em `avisos` do farol (§10.8.7) | `As parciais em imagem ficaram fora desta atualização (pacote grande). Veja no PC.` |
| `AVISO_CSVS_FORA` | o robô, em `avisos` do `pv_pedidos` (§10.8.7) | `Os CSVs do Protheus ficaram fora desta atualização (pacote grande). Veja no PC.` |
| `AVISO_SOLICITACAO_ABERTO` | o robô, em `avisos` do `pv_pedidos` (§10.7.8, §10.8.7) | `A Solicitação BAP foi reduzida aos pedidos em aberto para caber no pacote.` |
| `AVISO_JUNTA_ENTREGAS` | o robô, em `avisos` do `pl_entregas` (§10.8.7) | `A junta de pendências dos meses anteriores ficou fora desta atualização (pacote grande). Veja no PC.` |
| `AVISO_ENTREGAS_RECENTES` | o robô, em `avisos` do `pl_entregas` (§10.8.7) | `A aba Entregas ficou só com as entregas mais recentes para caber no pacote. Veja o resto no PC.` |

**Ordem dos avisos do farol** (decisão do gerente, achado 13; o robô grava `avisos` já nesta ordem, nos três `rid`):
1. `AVISO_ABAS_FORA` (falta de dado é o mais importante);
2. os que começam com "Sem o arquivo";
3. o que começa com "Sem filtro por estado";
4. os outros, na ordem do PC.

No Visita, o robô manda **no máximo 2** avisos (o teto do celular, `_avisos_curtos_visita_web`), cortando do fim desta ordem. Assim o aviso de aba fora nunca é cortado.

**A web recusa o pacote inteiro** (motivo no log, sem dado pessoal) quando, num destes três `rid`:
- uma tabela tem `titulo` fora da lista do §10.7.1, fora da ordem ou repetido; uma junta ou sub-aba está fora do lugar do §10.7.3;
- as colunas não são as do §10.7.3 (no "Solicitação BAP": coluna que sai, ou `tipo` fora de `texto`, `num` e `data`);
- aparece coluna que sai (§10.7.4), selo fora das colunas marcadas, ou `chip_tom` que não aponta para coluna oculta da mesma tabela;
- uma linha tem número de células diferente do de colunas; o `total` não segue o §10.7.2.1; um índice de `recortes_linhas` está fora de `linhas`; `uf_linhas` tem tamanho diferente de `linhas` ou valor que não é UF (`^[A-Z]{2}$`) nem `""`;
- uma tabela passa de 60.000 linhas (`MAX_LINHAS`, como no §10.6);
- há chave proibida (§10.7.2) em qualquer nível.

#### 10.7.7 Período das linhas e filtro por estado

- **Período [D2]:** as tabelas levam **só o mês do pacote**, como o PC abre (`ano`/`mes` do topo do pacote):
  - "Pedidos": as linhas com `MÊS` = mês do pacote (o PC já mostra só essas: o filtro MÊS é oculto e segue o Mês/Ano de cima). As juntas vão inteiras (já são só do que está em aberto);
  - "Entregas": as linhas com `MÊS` = mês do pacote; as pendências dos meses anteriores vão na junta;
  - Visita: as tabelas do `montar` já são do mês.
- **Filtro por estado [D5]:** com um estado escolhido, a web também filtra as linhas pelas `uf_linhas` (a mesma regra dos cartões, RN-GER-006): "Pedidos" pela filial da nota, "Entregas" e a junta de pendências pela UF do cliente. As juntas do "Pedidos" seguem a `liga`. Os `kpis_padrao` não seguem o estado: com estado, os cartões da aba saem, e fica o `AVISO_CARTOES` (§10.7.6). O "Solicitação BAP" e as abas do Visita não têm estado: a web mostra a tabela da BAP inteira, com o aviso do §10.1.

#### 10.7.8 Tamanho do pacote

Medido nas bases do repositório (NOV/26, dados até 20/11), JSON compacto, com as colunas que saem já fora:

| Parte | Linhas | Tamanho |
|---|---|---|
| `vc_painel` (T-0014) | — | 41 KB |
| `pl_inadimplencia` com `tabelas` e `cobranca` (§10.6) | 539 + 193 | 287 KB |
| "Pedidos", só o mês [D2 A] (12 meses: 2.216 linhas, 745 KB) | 119 | 42 KB |
| As 3 juntas do "Pedidos" | 19 + 9 + 34 | 12 KB |
| "Solicitação BAP", as 7 abas inteiras [D3 A] (só as linhas de pedido EM ABERTO, com as 2 listas de exclusão inteiras: 364 linhas, cerca de 25 KB) | 4.370 | 830 KB |
| "Entregas", só o mês, e a junta [D2 A] (12 meses: 1.390 linhas, 259 KB) | 59 + 0 | 16 KB |
| Visita: "Cliente a cliente" (até 19/11; mês cheio estimado em 2.200 linhas, cerca de 620 KB) | 1.441 | 406 KB |
| Visita: as outras 6 abas | 236 | 50 KB |
| `recortes_linhas`, `uf_linhas`, `kpis_padrao` e a forma "farol" dos três faróis [SUPOSIÇÃO: estimativa] | — | 150 KB |

- **Total estimado no fim do mês, com as recomendações: cerca de 2,2 MB** (2,5 MB com os espaços do `json.dumps` padrão do robô). Com D2 B e D3 A: cerca de 3,5 MB. O teto é `BAP_WEB_PACOTE_MAX_MB = 25` (`render.yaml`): folga de 7 a 10 vezes. Disco: 7 pacotes guardados (§10.6.1) = cerca de 25 MB.
- **Trava do robô:** `bap_automation.WEB_PACOTE_TETO_MB = 20`. Se o pacote serializado passar disso, o robô corta, nesta ordem, até caber, com um aviso no farol e uma linha no log: (1) "Solicitação BAP" só com as linhas de pedido EM ABERTO; (2) "Cliente a cliente" fora; (3) todas as `tabelas` dos três faróis fora (cai no §10.1). Nunca manda pacote que a web recusaria pelo tamanho.
- **Formato 2 (§10.8):** o teto passa a ser **por farol** (`WEB_FAROL_TETO_MB = 8` no robô e `FAROL_JSON_MAX` = 10 MB na web, no JSON sem anexos), e o corte é farol a farol (§10.8.7). O teto de 25 MB e a trava de 20 MB acima valem só para o formato 1.
- **Sem páginas** (contrato `tela-bc3.md`, §7.2, que substitui as 100 linhas por página): a página leva até 500 linhas da tabela, e o resto vem em blocos de 500 ao rolar, com o mesmo corte de perfil e de estado. A página lê só o farol dela do disco (§10.8), nunca o pacote inteiro.

#### 10.7.9 Decisões em aberto (do Alexandre) e a regra

| | Pergunta | Opções | Recomendação |
|---|---|---|---|
| **D1** | O perfil do farol vê as tabelas? (`pre_venda` em Pedidos, `pos_venda` em Entregas, `vendas` em Visita; o "1 A" só fala de admin, pós-venda, gerente e diretor) | (A) sim, todas as abas, como o pós-venda na Inadimplência; (B) só `admin` e `gerente` veem tabelas; o perfil do farol vê só o resumo; (C) como A, mas `vendas` não vê "Cliente a cliente", "Prospecção" e "Indicação" (carteira e prospecção de outros vendedores) | **A**: é quem opera o farol no PC; o filtro por vendedor de cada login fica para o perfil supervisor (R-20261123-191448-alexandre) |
| **D2** | Quantos meses de linhas? | (A) só o mês do pacote, como o PC abre; as pendências antigas de entrega vão na junta; (B) os 12 meses que o PC carrega (+1 MB), com o filtro MÊS no site | **A**: os cartões batem com as linhas, e o pacote fica menor |
| **D3** | "Solicitação BAP": quais linhas? | (A) as 7 abas inteiras, como o PC (830 KB hoje, cresce com o arquivo; a trava do §10.7.8 corta se precisar); (B) só as linhas de pedido EM ABERTO (cerca de 25 KB); (C) a aba fica só no PC | **A**: é o "todas as abas" do Alexandre, e cabe com folga. A troca de loja de coleta fica no PC em qualquer opção |
| **D4** | "Ver pedido" (duplo clique no PC: itens, saldo e autorização) | (A) fica no PC nesta entrega; (B) o robô manda pronto o detalhe dos pedidos do mês, só leitura, sem a caixa de autorização (cerca de 300 KB a mais) | **A**: não é aba; vira uma entrega própria se o Alexandre quiser |
| **D5** | O estado escolhido em cima filtra as linhas? | (A) sim, pela mesma regra dos cartões (RN-GER-006); Visita e "Solicitação BAP" com aviso; (B) não: tabelas sempre da BAP inteira, com aviso | **A**: o número do cartão e as linhas contam a mesma história |
| **D6** | Texto livre e nome de motorista | (A) vão: o texto livre passa pela limpeza (telefone, e-mail e CPF/CNPJ viram "[removido]"); `RESPONSÁVEL` vai como o nome do vendedor; (B) `OBSERVAÇÃO`, `JUSTIFICATIVA`, `RESULTADO`, `LINHAS DE INTERESSE` e `RESPONSÁVEL` ficam só no PC | **A**: é o que o gerente lê no PC; nas bases não há telefone nem documento nesses textos |

**Regra:** RN-GER-011 (`docs/produto/03-regras.md`). Os testes citam `test_RN_GER_011_...`.

#### 10.7.10 Ordem de publicação

1. **Contrato** (este §10.7) com as decisões D1 a D6 respondidas.
2. **Núcleo** (modulo-farois): as funções puras (`sem_documento`, `cliente_sem_documento`, `texto_sem_contato`, `linhas_padrao`, `recortes_em_linhas`). Não muda nenhuma tela do PC.
3. **Web antes:** aceita, valida e desenha `tabelas` nos três `rid`, com o corte por perfil; `VERSAO` nova no `/saude`. Sobe com o merge (ADR 0001, adendo 4). A web publicada hoje recusa `tabelas` fora do `pl_inadimplencia`: **o robô novo antes da web derruba o pacote inteiro** (o `vc_painel` também para de atualizar).
4. **Robô depois:** o "instale" no PC (regra 11 do `CLAUDE.md`), só com o `/saude` na versão nova.

A versão do contrato fica em 1. Renomear ou tirar chave desta seção = v2 com ADR.

### 10.8 Formato 2 do pacote: um arquivo por farol e um índice (T-0035, ADR 0003)

Acrescentada em 26/11/2026 (T-0035). Fontes: ADR 0003; o risco 1 do inventário (`recados/anexos/T-0033/inventario-pc-site.md`, §4); o plano R-20261126-175814-gerente-projetos.

**O que muda:** só o **transporte e a guarda**. O conteúdo de cada `relatorios[rid]` é exatamente o das §10.1 a §10.7, sem chave nova nem tirada.
- O "formato do pacote" passa a ter versão própria: 1 = um JSON com todos os faróis (`POST /api/pacote`, como até aqui); 2 = um corpo por farol mais o `fechar` (esta seção).
- O `versao_contrato` continua **1**, e a web nova aceita os dois formatos.
- Renomear ou tirar chave ou rota desta seção = formato 3, com ADR.

Donos: o robô manda (modulo-robo, `bap_automation.enviar_pacote_web`). A web recebe, guarda e lê (modulo-web, `web/app/pacotes.py` e `main.py`).

#### 10.8.1 Quem fala qual formato: `/saude`

```json
{"status": "ok", "versao": "0.4.0", ...,
 "pacote": {"formatos": [1, 2], "lote": "20261126T083000", "farois": 9, "origem": "por_farol"},
 "memoria": {"rss_mb": 182.4, "pico_mb": 251.0, "limite_mb": 512.0, "cache_mb": 41.2, "cache_farois": 3}}
```

| Chave | Tipo | Regra |
|---|---|---|
| `pacote.formatos` | `list[int]` | os formatos que a web recebe. A web antiga não tem a chave = só o 1 |
| `pacote.lote` | `str` ou `null` | o lote vigente (`AAAAMMDDTHHMMSS`, Manaus); `null` sem pacote |
| `pacote.farois` | `int` | quantos faróis o lote vigente tem |
| `pacote.origem` | `"por_farol"`, `"inteiro"` ou `"convertido"` | como o lote vigente chegou: formato 2, formato 1 dividido, ou convertido do disco antigo na partida |
| `memoria.*` | `float` ou `null` | ADR 0003, §4.6. `null` quando o sistema não informa. `memoria_alerta: true` aparece com `pico_mb` acima de 400 |
| `ultimo_pacote` | `str` ou `null` | continua: o `gerado_em` do lote vigente |

- O robô decide o formato pelo `pacote.formatos`. Sem a chave, ou se o GET falhar, ele manda o formato 1.

#### 10.8.2 Disco e índice

- **Disco:** `<BAP_WEB_DADOS>/pacotes/<lote>/`, com o `indice.json`, um `<rid>.json.gz` por farol e os anexos.
  - `<lote>` = `pacotes.nome_arquivo(gerado_em)`.
  - O lote vigente é a maior pasta com `indice.json`.
  - A pasta só aparece pronta: o recebimento acontece em `pacotes/_recebendo/<lote>/` e termina num `os.replace`.
- **Retenção:** os **7** lotes mais novos (`GUARDAR = 7`, RN-POS-003), contando junto os `pacotes/*.json` do formato 1.

```json
{"formato": 2, "lote": "20261126T083000", "origem": "por_farol",
 "versao_contrato": 1, "gerado_em": "2026-11-26T08:30:00-04:00", "ano": 2026, "mes": 11,
 "recebido_em": "2026-11-26T08:31:12-04:00",
 "farois": {
   "pv_pedidos": {"arquivo": "pv_pedidos.json.gz", "sha256": "9a1c…e0", "bytes_gz": 81234, "bytes_json": 912345,
                  "titulo": "Farol de Pedidos", "baixado_em": "2026-11-26T07:12:00-04:00",
                  "gerado_em": "2026-11-26T08:30:00-04:00", "recebido_em": "2026-11-26T08:31:12-04:00",
                  "herdado_de": null,
                  "anexos": {"parciais": {"acum": "pv_pedidos.parcial-acum.png"}, "csvs": "pv_pedidos.csvs.json.gz"}}}}
```

| Chave do farol | Regra |
|---|---|
| `sha256` | o sha256 (hex) dos bytes JSON **descomprimidos** que o robô mandou (`X-BAP-SHA256`). É o "sha do farol" da cobrança (§10.6.5) |
| `bytes_gz`, `bytes_json` | os tamanhos guardados (o JSON sem os anexos). O `bytes_json` é a base do custo estimado no cache (ADR 0003, §4.5) |
| `titulo`, `baixado_em` | copiados do farol (§10.1), para o menu e a faixa sem abrir o arquivo. O `vc_painel` leva `baixado_em: null` |
| `gerado_em`, `recebido_em` | os do lote, ou os do lote de origem quando `herdado_de` não é `null` |
| `herdado_de` | `null`, ou o lote de onde o farol foi copiado (§10.8.4, `manter`) |
| `anexos` | só quando o farol trouxe `parciais` ou `csvs_protheus`. Os arquivos ficam na mesma pasta |

- **O `<rid>.json.gz` é o farol como validado,** com duas diferenças:
  - sem `parciais` e sem `csvs_protheus`, que viram anexos;
  - depois do `tabelas.tirar_abas_com_documento`, que pode tirar uma aba.
- **Na leitura,** a web devolve os anexos às rotas da parcial e do CSV, a partir do disco. O dicionário do farol na memória não leva os anexos.

#### 10.8.3 `POST /api/pacote/<lote>/farol/<rid>`

- **Cabeçalhos:**
  - `Authorization: Bearer <BAP_WEB_TOKEN>`;
  - `Content-Type: application/json`;
  - `Content-Encoding: gzip` (ou ausente, para o corpo sem compressão);
  - `X-BAP-SHA256: <sha256 hex dos bytes JSON descomprimidos>`.
- **Corpo:** `relatorios[rid]` do pacote, serializado com `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"))` em UTF-8.
- **Regras:**
  - `<lote>` = `^\d{8}T\d{6}$`, e `<rid>` está em `pacotes.ACEITOS`;
  - validação = `pacotes.validar_relatorio(rid, corpo)`, a mesma regra do formato 1, farol a farol;
  - o mesmo `rid` de novo no mesmo lote substitui o anterior;
  - no máximo 3 lotes em `_recebendo/` ao mesmo tempo (o mais velho sai).

| Resposta | Quando |
|---|---|
| 200 `{"ok": true, "rid": str, "sha256": str, "bytes_json": int}` | aceito em `_recebendo/<lote>/` |
| 400 | `<lote>` ou `X-BAP-SHA256` mal formado |
| 401 | token ausente ou errado (`WWW-Authenticate: Bearer`) |
| 404 | `<rid>` fora do `ACEITOS` |
| 413 `{"erro": "farol grande demais"}` | gzip acima de `FAROL_GZ_MAX` (24 MB), descomprimido acima de `FAROL_CORPO_MAX` (24 MB) ou JSON sem anexos acima de `FAROL_JSON_MAX` (10 MB) |
| 415 | `Content-Type` diferente de `application/json`, ou `Content-Encoding` diferente de `gzip`/ausente |
| 422 `{"erro": "sha256"}` | o sha256 não bate |
| 422 `{"erro": "esquema inválido", "detalhes": [...]}` | a validação recusou (até 10 erros, sem dado pessoal) |

#### 10.8.4 `POST /api/pacote/<lote>/fechar`

```json
{"versao_contrato": 1, "gerado_em": "2026-11-26T08:30:00-04:00", "ano": 2026, "mes": 11,
 "farois": {"vc_painel": "5d1f…", "pv_pedidos": "9a1c…e0"},
 "manter": ["vc_visitas"]}
```

- **O que a web confere:**
  - `pacotes.validar_topo` (as regras do topo do formato 1) e `nome_arquivo(gerado_em) == <lote>`;
  - cada `rid` de `farois` está em `_recebendo/<lote>/` com aquele `sha256`. Um `rid` recebido e fora de `farois` é descartado;
  - `farois` tem de 1 a `LOTE_FAROIS_MAX` (60) itens.
- **`manter`:** opcional. São os faróis que o robô montou, mas não conseguiu entregar (413, 422 ou rede depois das 3 tentativas).
  - A web copia o farol do lote vigente para o novo, com `herdado_de`. Isso só acontece se ele existe lá e se o `gerado_em` dele tem até 26 h. Sem isso, o farol fica fora.
  - O farol que **não montou** no PC (`erro_montagem`) nunca vai no `manter`.
  - Vale pela decisão da ADR 0003, §4.4 (A, R-20261126-182227-alexandre).
- **Depois do `fechar`:** grava o `indice.json` e move a pasta para `pacotes/<lote>/`. Em seguida, roda a retenção e a limpeza (`_recebendo` com mais de 2 h sai).

| Resposta | Quando |
|---|---|
| 200 `{"ok": true, "lote": str, "farois": int, "herdados": [rid], "vigente": bool}` | fechado. `vigente: false` quando já existe um lote mais novo. O `fechar` repetido de um lote fechado responde igual |
| 400 | corpo fora do formato |
| 409 `{"erro": "faltam", "farois": [rid]}` | um `rid` não foi recebido ou tem outro `sha256` (só os `rid`, sem conteúdo). O robô reenvia esses faróis e fecha de novo |
| 422 `{"erro": "esquema inválido", "detalhes": [...]}` | o topo não passou |

#### 10.8.5 Formato 1 na web nova

- O `POST /api/pacote` (§10, ADR 0001, §4.3) continua, com o mesmo teto (`BAP_WEB_PACOTE_MAX_MB`) e a mesma validação (`pacotes.validar`).
- A web divide o pacote aceito num lote (`origem: "inteiro"`), com as mesmas funções do §10.8.3, e ele vira o vigente.
- Ele sai numa ADR futura, depois de 2 semanas sem uso no log.

#### 10.8.6 Diários (cobrança e edições)

- Os formatos dos dois diários e das APIs do robô (§10.6.5, §10.6.6, `/api/edicoes`) **não mudam**.
- **Cobrança:** o `pacote_sha` de cada registro passa a ser o `sha256` do farol `pl_inadimplencia` no índice (§10.8.2).
  - O item da página sai do farol daquele sha (se o lote ainda está entre os 7); senão, do farol vigente; senão, 404 (§10.6.4).
  - Um sha do formato 1 (do pacote inteiro) não é achado e cai no vigente.
  - O PC não lê o campo.
- **Edições:** a marca "Aguardando o PC" compara a confirmação com o `recebido_em` **do farol** (§10.8.2), não com o do pacote.

#### 10.8.7 Tetos e cortes no robô

**Teto do farol.** `WEB_FAROL_TETO_MB = 8`, medido no JSON do farol sem anexos.
- Acima dele entra `_cortar_farol_web(rid, farol, teto_mb)`, uma função pura que devolve outro dicionário.
- O robô corta na ordem de `_CORTES_FAROL_WEB[rid]` e para assim que o farol cabe.
- Todo corte deixa o aviso dele em `avisos`, com o texto do §10.7.6.

| `rid` | Cortes, nesta ordem | Aviso |
|---|---|---|
| `pv_pedidos` | 1. a "Solicitação BAP" fica só com as linhas EM ABERTO (as listas de exclusão vão inteiras) | `AVISO_SOLICITACAO_ABERTO` |
| | 2. todas as `tabelas` saem | `AVISO_ABAS_FORA` |
| `pl_entregas` | 1. a junta "Pendências dos meses anteriores" sai | `AVISO_JUNTA_ENTREGAS` |
| | 2. a aba "Entregas" fica só com as linhas mais recentes. A ordem é pela `DT. PED` (ISO); sem ela, pela `DT. NF`. O robô tenta 75%, 50% e 25% das linhas, nesta ordem, e para na primeira que cabe. Os `tons` saem junto, linha a linha. As colunas não mudam | `AVISO_ENTREGAS_RECENTES` (um só, qualquer que seja a fatia) |
| | 3. todas as `tabelas` saem (o farol cai no §10.1) | `AVISO_ABAS_FORA` |
| `vc_visitas` | 1. "Cliente a cliente" sai | `AVISO_ABAS_FORA` |
| | 2. todas as `tabelas` saem | `AVISO_ABAS_FORA` |
| os outros | todas as `tabelas` saem | `AVISO_ABAS_FORA` |

**Anexos acima do teto** (nos dois formatos; antes do teto do farol). Os tetos são os mesmos da web (`web/app/pacotes.py`). A web recusaria o farol inteiro (422), então o robô tira **só o anexo** e o farol segue.

| Anexo | Teto | O que sai | Aviso |
|---|---|---|---|
| `parciais` | `MAX_PNG_B64` = 3.000.000 caracteres base64, por imagem | só a imagem acima do teto. As outras ficam; sem nenhuma, a chave sai | `AVISO_PARCIAIS_FORA` |
| `csvs_protheus` | até 60 CSVs; até 200.000 bytes UTF-8 por CSV; `MAX_CSVS_TOTAL` = 1.500.000 bytes somados | se **qualquer** teto estoura, **todos** os CSVs saem (a lista do Protheus não vai pela metade) | `AVISO_CSVS_FORA` |

**Formato 1 (web antiga).** Continuam o `_cortar_pacote_web` e o `WEB_PACOTE_TETO_MB = 20` do §10.7.8. O corte dos anexos acima do teto vale também aqui.

#### 10.8.8 Ordem de publicação

1. Este contrato e a ADR 0003.
2. **Web antes** (modulo-web): as rotas do §10.8.3 e do §10.8.4, o formato 1 dividido, o `/saude` com `pacote` e `memoria`, e `VERSAO = "0.4.0"`. Sobe com o merge (ADR 0001, adendo 4).
3. **Robô depois** (modulo-robo): o envio por farol, com a volta ao formato 1 pelo §10.8.1. Ele chega à produção pela rotina diária, só com o `/saude` na versão do `main` (ADR 0002, limite 3).

A matriz robô × web está na ADR 0003, §4.7: as quatro combinações funcionam.

### 10.11 Farol de Fretes (`pl_fretes`, T-0037): as 4 abas e a edição de "Notas com frete"

Acrescentada em 27/11/2026 (T-0037; item 39 do inventário `recados/anexos/T-0033/inventario-pc-site.md`). Desenho completo, divisão por dono e perguntas: `docs/desenho/T-0037.md`.

Numeração: a §10.9 (edição pela web) e a §10.10 (Garantias, Devoluções e NCC) ficam reservadas para a T-0023 (branch `engenheiro-software/T-0023-T-0025-contrato`). A T-0037 segue a §10.9 da T-0023 no que for genérico da edição.

**Mudança compatível: v1 e formato 2 do pacote (§10.8) continuam.**
- Nenhuma chave nova no farol nem na `edicao`.
- O `pl_fretes` entra nas listas que já existem: forma "farol" (§10.1), `TabelaWeb7` (§10.7.2) e a edição da T-0021.

Fontes:
- `relatorios_nucleo.fretes(ctx)` (`relatorios_nucleo.py:7881`, código do `main` em `a32b610`);
- a fonte do PC, "TABELA_BAP › ftPedidos (VND) + cidade do cliente";
- a aba ENTREGAS do `ACOMPANHAMENTO_POS_VENDA.xlsx` (`_entregas_por_nf`, chave filial + NF).

#### 10.11.1 O que é nota com frete e de onde vem cada número

- **Nota com frete** [RN-POS-007, proposta]:
  - nota VND dos 12 meses (`ultimos_meses(hoje, 12)`, pela data da NF);
  - cujo cliente **não** está numa cidade de `bap_dados.CIDADES_SEM_FRETE` (Manaus, Boa Vista, Belém, Santarém, São Luís, Cuiabá e Várzea Grande; `bap_dados.e_frete`);
  - a UF é a **do cliente** (exceção de fretes na RN-GER-006).
- **VLR FRETE** [RN-POS-008, proposta] (`_frete`, `:6367`):
  - o FRETE REAL R$ da entrega, quando a assistente informou (`frete_real_de`);
  - senão, o estimado `transportadoras.frete_estimado` = VLR NF × % da transportadora (o % da cidade, se cadastrado), com piso no FRETE MÍNIMO;
  - sem transportadora, o % padrão;
  - o cadastro é só lido: `transportadoras_config.json` não é escrito.
- **ETAPA**: a da entrega. Sem linha no acompanhamento, "CONCLUÍDA" (NF antes de 01/10/2026, `_inicio_controle`) ou "(sem acompanhamento)".
- **ENTREGAR ATÉ**: a DT. PREVISTA ajustada (`prevista_manual`) ou a DT. PED + o prazo do cliente em dias úteis (`ctx.mais_uteis`, RN-GER-007).
- **SLA ENTREGA**: dias corridos da DT. PED até a entrega (ou até hoje), só com linha no acompanhamento.
- **Tom da linha**:
  - `alerta`: sem entrega, com prazo vencido e com linha no acompanhamento;
  - `ok`: entregue;
  - `""`: o resto.

#### 10.11.2 Cartões (`kpis`, os mesmos do PC; `kpis_de` = `cartoes`) [RN-POS-009, proposta]

Sobre as linhas do mês do pacote (`rotulo_no_periodo`):

| Cartão | `valor` | `detalhe` | Cor |
|---|---|---|---|
| Notas com frete | nº de notas | soma do VLR NF | neutro |
| % do faturado | soma do VLR NF das notas com frete ÷ VND **bruto** de todas as notas dos meses visíveis, de todas as cidades [pergunta P3] | | info |
| Frete estimado | soma do VLR FRETE | % do VLR NF | neutro |
| Cidades atendidas | nº de nomes de CIDADE distintos | | neutro |
| Entregues | notas com ENTREGUE ou com ETAPA ENTREGUE/CONCLUÍDA | "x% no prazo" = ENTREGUE ≤ ENTREGAR ATÉ, entre as que têm data de entrega | ok |
| Sem transportadora | notas com linha no acompanhamento e sem TRANSPORTADORA | | atencao |

- `recortes[UF].kpis` (§10.1) pela UF **do cliente** (`_UF_LINHAS_WEB[("pl_fretes", "Notas com frete")] = ("UF", "uf")`).
- **Correção pedida ao PC** (não é regra nova; `docs/desenho/T-0037.md`, §3):
  - hoje, no recorte, o denominador do "% do faturado" é o VND da BAP inteira;
  - ele passa a ser o VND dos clientes daquela UF;
  - na BAP inteira, o número não muda.
- **Gráfico "Mês a mês: notas com frete"** (barras, 12 meses): vai como bloco `barras` do painel.
  - O PC do Fretes não tem `painel`. O robô converte `graficos` em bloco pela lista `_GRAFICOS_NO_PAINEL_WEB` da T-0023.
  - Sem a T-0023 no `main`, o farol vai só com os cartões.

#### 10.11.3 Abas e colunas (`TabelaWeb7`, §10.7.2; a lista entra no §10.7.3 via `_COLUNAS_TABELAS_WEB`)

| Chave da aba (URL) | `titulo` (PC) | Colunas depois do corte (nome · tipo) | Filtros | Edição |
|---|---|---|---|---|
| `notas` | "Notas com frete" | `MÊS` texto (o) · `DATA PED.` dia · `DATA NF` dia · `NF` texto · `FILIAL` texto · `CLIENTE` texto (limpa: `cliente_sem_documento`, RN-GER-011) · `CIDADE` texto · `UF` texto · `VLR NF` moeda · `VLR FRETE` moeda · `ETAPA` texto · `TRANSPORTADORA` texto · `ENTREGAR ATÉ` dia · `ENTREGUE` dia · `SLA ENTREGA` int · `RESPONSÁVEL` texto (D6 A) | `MÊS` (padrão = mês do pacote, oculto [P1]), `UF`, `FILIAL`, `ETAPA`, `TRANSPORTADORA` | **sim** (§10.11.4) |
| `uf` | "Por UF" | `MÊS` texto · `UF` texto · `NOTAS` int · `VLR NF` moeda · `VLR FRETE` moeda | `MÊS` | não |
| `cidade` | "Por cidade" | `MÊS` texto · `CIDADE` texto ("CIDADE / UF") · `NOTAS` int · `VLR NF` moeda · `VLR FRETE` moeda | `MÊS` | não |
| `transportadora` | "Por transportadora" | `MÊS` texto · `TRANSPORTADORA` texto ("(sem)" = vazio) · `NOTAS` int · `VLR NF` moeda · `VLR FRETE` moeda | `MÊS` | não |

- (o) = oculta.
- **A linha do PC de "Notas com frete" tem 17 células.**
  - A 17ª é a CHAVE da entrega (`filial|nf|serie`, a `chave` da aba ENTREGAS); fica `""` sem acompanhamento.
  - O robô corta a célula a mais e manda só a chave, dentro de `edicao.chaves`, como no "Entregas" (§10.7.3).
- **As 3 tabelas de resumo** têm cartões próprios (`kpis_de`): Notas · Valor · Frete estimado.
  - "Por UF" tem recorte por UF (coluna `UF`, UF do cliente).
  - "Por cidade" e "Por transportadora" vão sem recorte; a tela avisa "só na BAP inteira".
- **Período das linhas [P1]:**
  - recomendação A: só o mês do pacote, nas 4 abas (D2 A do §10.7.9, `_TABELAS_SO_MES_WEB`);
  - com a B, vão os 12 meses e o filtro `MÊS` fica visível.
- **Corte acima do teto** (§10.8.7): o `pl_fretes` entra em "os outros" (todas as `tabelas` saem, com o `AVISO_ABAS_FORA`).

#### 10.11.4 Edição de "Notas com frete" (a mesma linha da aba ENTREGAS)

- O lugar é `("pl_fretes", "Notas com frete")`, com módulo `pos_venda`, arquivo `RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx`, aba `ENTREGAS` e ação "Editar".
  - Entra em `bap_automation.EDICOES_WEB` e em `web/app/edicoes.LUGARES`.
  - Os campos vêm de `CAMPOS_EDICAO_WEB["pos_venda"]`.
- A `edicao` vem pronta do PC: a `_entrega_editavel` que o `fretes` já usa (`chave = 16`), passada pela `bap_automation.edicao_web`.

| `campo` | `rotulo` | Coluna da tela | Tipo | Opções (do PC) | Conferência no robô (`validar_edicao_web`) |
|---|---|---|---|---|---|
| `etapa` | ETAPA | `ETAPA` | lista | `pos_venda.ETAPAS_ENTREGA` | dentro da lista |
| `transportadora` | TRANSPORTADORA | `TRANSPORTADORA` | lista por linha (`grupos`/`grupo_linhas`: as que atuam na UF/cidade do cliente) | `transportadoras.opcoes_para` (só leitura do cadastro) | dentro de `tr.nomes(cadastro)` |
| `prevista_manual` | DT. PREVISTA (ENTREGA) | `ENTREGAR ATÉ` | data | `datas_de_previsao(hoje)`; `""` = volta à calculada | `dd/mm/aaaa` |
| `entregue_em` | DT. REAL (ENTREGA) | `ENTREGUE` | data | `datas_para_escolher(hoje)` | `dd/mm/aaaa` |
| `responsavel` | RESPONSÁVEL (MOTORISTA) | `RESPONSÁVEL` | texto (sugere os já usados) | | até 60 caracteres, sem caractere de controle e sem CPF/CNPJ, e-mail ou telefone (`_RE_PESSOAL_EDICAO_WEB`) |

- **`frete_real` não é campo do Fretes:** o PC não o oferece aqui; ele fica no Farol de Entregas [P2].
- **Linha sem chave** (CONCLUÍDA antes do controle ou "(sem acompanhamento)"): `chaves[k] = ""`. A web não abre o formulário e mostra o motivo.
- **Quem edita:** só o `admin` (`web/app/edicoes.EDITA`, RN-GER-012). Os outros perfis veem a tabela sem o botão (403 no POST).
- **Caminho** (o da T-0021, sem mudança de formato):
  1. A web grava a edição na fila só de acréscimo `<BAP_WEB_DADOS>/edicoes/EDICOES_WEB_<AAAA-MM>.jsonl`.
  2. O robô puxa em `GET /api/edicoes?desde=<seq>` e confere de novo (`validar_edicao_web`).
  3. O robô grava por `gravar_edicoes_pc` → `pos_venda.gravar_edicoes(caminho, "ENTREGAS", {chave: {campo: valor}})`. A função escreve **primeiro** uma linha no diário `_EDICOES_POS_VENDA` (só acrescenta, regra 7) e depois a célula da assistente.
  4. O robô registra a linha em `RELATORIOS/_EDICOES_WEB/APLICADAS_WEB_<PC>.jsonl` (só acrescenta) e confirma em `POST /api/edicoes/confirmar`.
  - Excel aberto = "pendente": a fila espera a próxima rodada.
  - Linha não achada = "erro" (`MOTIVO_LINHA_WEB`).
- **A mesma linha em dois faróis:**
  - a chave é a mesma do "Entregas" do `pl_entregas`;
  - a marca "Aguardando o PC" e o "O PC recusou" valem nos dois faróis;
  - para isso, a situação é buscada por (`modulo`, `chave`), não só pelo `rid` (`docs/desenho/T-0037.md`, §4.4).
- **PC só leitura:**
  - `("pl_fretes", "Notas com frete")` entra em `bap_relatorios.EDICAO_SO_WEB`, e o duplo clique mostra o `MSG_EDICAO_SO_WEB`;
  - isso entra no **mesmo** lote do robô que passa a mandar a `edicao` do Fretes, nunca antes.
- Nada aqui escreve o `transportadoras_config.json` nem outro `.json` digitado.

#### 10.11.5 Quem vê

| Perfil | Resumo | Abas | Edita |
|---|---|---|---|
| `admin` | sim | as 4 | sim |
| `gerente` | sim | as 4 | não |
| `pos_venda` | sim | as 4 [P4] | não |
| `diretor` | sim | nenhuma | não |

- `render.FAROIS["pl_fretes"] = ("Farol de Fretes", ("admin", "diretor", "gerente", "pos_venda"))`, no grupo "Pós-venda" do menu.
- Aba fora do perfil = 403.
- Página com tabela: `no-store` e `noindex` (§10.7.5).

#### 10.11.6 Ordem de publicação

1. Este contrato.
2. **Web antes** (modulo-web): o `pl_fretes` em `FAROIS`/`ACEITOS`, as 4 abas, o lugar da edição e a situação por (`modulo`, `chave`). A web nova aceita pacote sem o `pl_fretes`.
3. **Robô e PC depois, no mesmo lote** (modulo-robo e modulo-farois): o farol no pacote, com a `edicao`, e o `EDICAO_SO_WEB` do PC. Chegam à produção pela rotina diária (ADR 0002).
4. **Testes:** citam de `test_RN_POS_007_...` a `test_RN_POS_010_...` e o `test_RN_GER_012_...`.
   - Os números RN-POS-007 a 010 são uma proposta: o gerente-projetos confirma no `docs/produto/03-regras.md`.
   - A T-0023 usa até a RN-POS-006.

## 11. Parte ação: os callables e a web v1

Regras gerais:
- **Nenhum callable vai ao navegador.** O servidor guarda o `rel` montado (com os callables) num cache em memória por `(rid, params_usados, pacote)`, e as rotas de ação usam esse `rel` (ou montam de novo, com o mesmo `raiz`, `hoje` e `params`).
- **O filtro roda no servidor.** O navegador manda o estado do filtro (`filtros`, recorte, busca) e recebe as linhas visíveis, o total e os cartões já calculados. Assim, um código só decide o que é "linha visível", e o número da web é o mesmo do Tkinter.
- Para isso, a regra de filtro da tela (`bap_relatorios.Vista._filtradas`, `bap_relatorios.py:2651`: filtros, recorte, busca, TOP N) precisa virar **função pura no núcleo**, usada pela tela e pela web, com teste que compare as duas. Pedido ao modulo-farois na T-0006.
- [SUPOSIÇÃO] As rotas citadas abaixo (`/r/<rid>/...`) são nomes de exemplo. Quem fixa os nomes é o desenho da onda 1 (modulo-web).

| Callable | Assinatura e retorno | Web v1 |
|---|---|---|
| `detalhe_pedido` | §11.1 | **rota no servidor** |
| `kpis_de` | `(linhas_visiveis: list[list[Celula]]) -> list[Kpi]` | **recálculo no servidor** (§11.2) |
| `total_de` | `(linhas_visiveis) -> list[Celula] \| None` | **recálculo no servidor** (§11.3) |
| `recortes[][1]` (função) | `(linha: list[Celula]) -> bool` | **recálculo no servidor** (§11.4) |
| `ordem_exportar` | `(linha) -> chave de ordenação` (`sort(key=...)`, `bap_relatorios.py:1067-1070`) | fora da v1 (a v1 não exporta Excel) |
| `edicao.ao_mudar`, `campos[].opcoes_de`, `campos[].so_se` | callables da tela de edição (ex.: `so_se(linha) -> bool`, `:12542`) | fora da v1: a web não grava (§3.4). O serializador tira a chave `edicao` inteira |
| `garantia.dados`, `.produto`, `.cliente_base` | `dados_da_garantia(ticket)` (`:7444`), `produto(cod)` (`:7464`), `cliente_base(cod)` (`:7302`) | fora da v1 (a tela do ticket grava) |
| `exportar_protheus`, `exportar_base_protheus` | `montar(t=None, linhas=None)` (`:5233`, `:5046`) | fora da v1 (gera arquivo) |
| `exportar_sem_coordenada`, `exportar_correcao` | `(destino, chaves=None)` (`:16078`, `:16082`) | fora da v1 (grava Excel) |
| `exportar_correcao_json` | `(chaves=None)` (`:16084`) | fora da v1 |
| `importar_preenchidos` | `(arquivo)` (`:16080`) | fora da v1 (lê arquivo enviado e grava) |

### 11.1 `detalhe_pedido` (o "Ver pedido")

- **No dicionário:** `rel["detalhe_pedido"](tabela, linha)`. Ele lê os índices de `tabela["detalhe"]` (`{"filial", "pedido", "nf"}`, §3.1) e chama `relatorios_nucleo.detalhe_pedido(ctx, filial, pedido, nf)` (`:1020`), com o `ctx` do `montar` (`:19164-19172`). Índice `None` ou fora da linha = `""`.
- **Na web:** rota no servidor (ex.: `/r/<rid>/detalhe?filial=&pedido=&nf=`). O navegador manda os **valores** das três células, tirados da linha pelos índices de `tabela.detalhe`. O servidor chama `detalhe_pedido(ctx, filial, pedido, nf)` direto, com o `ctx` do mesmo pacote e do mesmo `hoje`. Só a tabela com `detalhe` diferente de `None` mostra o botão.
- **Retorno:** `None` quando não acha (a tela mostra "Pedido não encontrado na TABELA_BAP.", `bap_relatorios.py:2838-2842`; a web faz o mesmo). Senão, um dict (`:1157-1160`):

| Chave | Tipo |
|---|---|
| `titulo` | `str`: `"Pedido <nº>"` ou `"Devolução NF <nº>"` |
| `subtitulo` | `str`: `"<filial> · <cliente>"` (**dado pessoal**) |
| `campos` | `list[(rotulo, valor)]`, os dois `str`: Cliente, Cidade, Vendedor, Supervisor, Filial, datas, nota, prazo, situação e os opcionais (Pedido Máxima, Dias úteis até faturar, Observação). **Dado pessoal** |
| `kpis` | `list[Kpi]` (§4): Itens, Total tabela, Total venda, Desconto comercial, Saldo 15% e, às vezes, Saldo do frete |
| `colunas` | `list[Coluna]` (§3.2), 12 colunas; SITUAÇÃO e NF ficam `oculta` quando não mudam entre os itens |
| `linhas` | `list[list[Celula]]`, um item por linha |
| `tons` | `list[str]`, um por linha (§3.3) |
| `total` | `list[Celula]` |
| `autorizacao` | `{"chave", "codigo", "por", "precisa": bool, "grave": bool, "aviso": str} \| None` |

- **Web v1:** só mostra. A gravação da autorização (`autorizacao`) fica fora da v1 (§3.4).

```python
{"titulo": "Pedido 123456", "subtitulo": "MANAUS · CLIENTE FICTÍCIO",
 "campos": [("Filial", "MANAUS"), ("Prazo de pagamento", "28 DIAS")],
 "kpis": [{"rotulo": "Itens", "valor": "3", "cor": "neutro",
           "detalhe": "12 unidades"}],
 "colunas": [...], "linhas": [...], "tons": ["", "", "alerta"],
 "total": ["TOTAL", "", "3 itens", "", 12, None, None, 14.2, ...],
 "autorizacao": None}
```

### 11.2 `kpis_de`: os cartões seguem o filtro

- **Na tela** (`bap_relatorios.kpis_atuais`, `bap_relatorios.py:705-718`), os cartões de cima saem, nesta ordem:
  1. aba de painel com `kpis` próprios (`paineis[i].kpis`, `:289-290`): esses;
  2. aba de tabela com `kpis_de`: `kpis_de(linhas visíveis)`, **mesmo sem filtro nenhum**;
  3. se não, ou se `kpis_de` der erro: `rel["kpis"]`.
- **Na web:** a mesma ordem, no servidor. Ao abrir a aba e a cada mudança de filtro, o servidor chama `kpis_de` com as linhas visíveis e devolve os `Kpi` prontos. **A web não mostra `rel["kpis"]` numa aba que tem `kpis_de`**: o número divergiria do Tkinter.
- No Excel/PDF a tela grava `kpis_visiveis` com o mesmo cálculo (`bap_relatorios.py:1074-1076`). Exportação fica fora da v1.

### 11.3 `total_de` e `totais_por`: o total segue o filtro

- **Na tela** (`Vista.total_de`, `bap_relatorios.py:2700-2721`):
  1. com `total_de`: `total_de(linhas visíveis)`; erro = sem total;
  2. sem `total_de` e com o número de linhas visíveis **igual** ao da tabela (`len(linhas) == len(tabela["linhas"])`, `bap_relatorios.py:2709`): `tabela["total"]`. A conta é só de tamanho, não de "sem filtro": um filtro que não tira nenhuma linha também mostra o `total`;
  3. sem `total_de` e com menos linhas visíveis: o `totais_por` só quando todas as linhas visíveis têm o mesmo valor na coluna e são **todas** as linhas desse valor; senão, sem total.
- **Na web:** a mesma regra, no servidor (o `totais_por` é serializável, mas a regra fica junto da do filtro, num lugar só). Com filtro e sem `total_de`, a web **não** mostra o `total` da tabela inteira.

### 11.4 `recortes`

- **Na tela** (`Vista._filtradas`, `bap_relatorios.py:2651-2698`): o recorte é uma caixa com os rótulos (some na tabela `enxuta`, `bap_relatorios.py:2442-2444`). O recorte por função tira a linha que dá `False`, junto com os filtros e a busca. O recorte `{"top", "coluna", "so_positivo"?}` vem depois, nesta ordem (`bap_relatorios.py:2686-2691`): com `so_positivo`, fica só com valor > 0 na coluna; depois ordena pela coluna (maior primeiro) e corta em `top`.
- **Na web:** o navegador recebe só a lista de rótulos (`[rotulo, ...]`) e manda o rótulo escolhido. O servidor aplica os dois tipos. O de `top` é serializável, mas segue o mesmo caminho, para a ordem e o corte serem os da tela.
- O recorte entra no `kpis_de` e no `total_de` (§11.2 e §11.3), porque eles recebem as linhas visíveis já recortadas.
