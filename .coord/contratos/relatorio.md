# Contrato do relatório — v1

- **Dono:** engenheiro-software · **Tarefa:** T-0002 · **Data:** 20/11/2026 (Manaus)
- **Base:** código do `main` em `c96a153` (`relatorios_nucleo.py`, 19.173 linhas). As linhas citadas são desse commit.
- **Escopo:** o dicionário que `relatorios_nucleo.montar(rid, raiz, hoje=None, log=None, params=None, tela=False)` devolve (`relatorios_nucleo.py:19130`). É a ponte entre os núcleos e qualquer tela: Tkinter (`bap_relatorios.py`) hoje, web amanhã.
- **Regra de versão:** acrescentar chave opcional = v1 continua. Renomear, mudar tipo ou tirar chave = **v2**, com ADR em `docs/decisoes/` e recado aos consumidores (seção 9).
- **Como a versão é lida:** hoje o dicionário **não tem** chave de versão. A versão sai da chave de topo opcional `versao_contrato` (`int`): **ausente = 1**. Acrescentar a chave não muda a v1. Ela passa a ser obrigatória na v2: o `montar` grava `rel["versao_contrato"]` a partir de uma constante do núcleo (proposta: `relatorios_nucleo.VERSAO_CONTRATO = 1`; pedido ao modulo-farois na T-0006). A web lê essa chave e recusa, com aviso, versão maior que a que conhece (ADR 0001, §4.6). Não confundir com `bap_dados.VERSAO` (27), que é a versão do cache.
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
> Por isso `gravar_hist=False` sozinho **não** deixa o `montar` em leitura pura (§10.5).

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
| `kpis` | `list[Kpi]` (§4) | os cartões de cima **sem filtro**, iguais ao `rel["kpis"]` do PC (BAP inteira) |
| `painel` | `{"blocos": list[Bloco]}` (§6.1) | os blocos do `rel["painel"]` do PC, no mesmo formato, só filtrados (abaixo). `colunas` e `altura_min` podem ir; a web pode ignorar |
| `insights_painel` | `list[[tom, texto]]` (§6.2) | igual ao PC |
| `avisos` | `list[str]` (§2) | os do PC; o robô pode acrescentar (ex.: bloco tirado) |
| `recortes` | `{"<UF>": {"kpis": list[Kpi]}}` | opcional. UF = 2 letras maiúsculas. **Só os kpis** por estado (abaixo). Atenção: é chaveado direto pela UF, sem o `{"uf": ...}` da forma "abas" |
| `baixado_em` | `str` ISO 8601 com fuso de Manaus (`-04:00`) ou `null` | quando a base do farol foi baixada do ERP. Não confundir com o `gerado_em` do pacote. A tela mostra os dois |

**Filtro (o que sai do `rel` do PC):**
- só as chaves da tabela acima. Fora: `tabelas`, `juntas`, `graficos` (os gráficos que a web mostra vêm dentro dos blocos do painel), `paineis`, `painel_pre`, `parametros`, `capa`, `params_usados`, `fonte`, `subtitulo`;
- nenhum callable (§10, item 1; §11);
- nenhuma chave que comece com `_`, em qualquer nível;
- nunca `edicao`, `editar` nem `abrir`, em qualquer nível. **A web recusa o pacote** que trouxer uma delas (dado digitado intocável, regra 7 do `CLAUDE.md`);
- conversão de tipos do §10, item 1 (tupla vira lista; data vira ISO).

**Blocos do painel nesta entrega:** a web desenha `insights`, `barras` e `hbarras`; os cartões vêm da chave `kpis` (não há bloco `tipo: "kpis"` no §6.1). Bloco de outro tipo (`tabela`, `pizza`, `grupo`, `placar`...) é aceito no pacote e a web mostra no lugar dele "ainda não disponível na web". O `tabela` entra na entrega do Farol de Entregas (acréscimo compatível, v1).

**Nome de pessoa (decisão D1 pendente):** enquanto o Alexandre não decidir a D1 (R-20261124-174958-gerente-projetos), bloco cujo eixo traz nome de vendedor ou supervisor (ex.: hbarras "Em atraso por vendedor") **fica fora do pacote**, inteiro, sem trocar por código. A chave do robô é `bap_automation.WEB_GRAFICOS_COM_NOME = False`. O mesmo vale para frase de `insights`/`insights_painel` que cite vendedor ou supervisor pelo nome. Nome de cliente e CNPJ **nunca** vão, com ou sem D1 (regra 6 do `CLAUDE.md`).

**Filtro por estado (RN-GER-006, estado = filial da nota):** muda **só os kpis**. O PC calcula `recortes[UF].kpis` com o `kpis_de` da tabela do farol sobre as linhas da filial daquele estado (o mesmo cálculo da tela, §11.2), e a web só troca os cartões. Os blocos do painel ficam da BAP inteira, e a tela avisa: "Cartões por estado; gráficos da BAP inteira." Estado sem recorte: a web mostra "—" nos cartões, nunca o número da BAP inteira.

**Versão e ordem de publicação:** a web antiga recusa `rid` fora do `ACEITOS` (`web/app/pacotes.py`). Por isso a **web publica antes** (aceita o `rid` novo e a forma "farol") e o **robô depois** (passa a mandar o farol). A versão fica em 1. Chave nova nesta forma = acréscimo compatível; renomear ou tirar chave = v2 com ADR.

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
