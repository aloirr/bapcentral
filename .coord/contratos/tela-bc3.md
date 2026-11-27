# Contrato visual das telas do site: BC3 no PC, M3 no celular — v1

- **Dono:** engenheiro-software · **Tarefa:** T-0033 · **Data:** 26/11/2026 (Manaus)
- **Base:** `main` em `2729c8a` (`web/app/`). As linhas citadas são desse commit.
- **Fontes (decisões do Alexandre, texto literal nos recados):**
  - R-20261126-171559-alexandre: "BC3 para o pc e celular", "M3 aprovado", "não gosto de barra de rolagem", o popup do pedido, o cabeçalho "elegante e resumido", "um padrão para todos os faróis e telas do bap central";
  - R-20261125-174000-alexandre: as tabelas de baixo lado a lado e sem repetição; as cores e o logo da BAP AUTOPARTS;
  - R-20261126-174334-alexandre: a revisão geral e a página inicial no Painel Executivo, no formato dos faróis.
- **Pareceres** (em `recados/anexos/T-0033/` do repositório de recados):
  - `revisao-ux-geral.md` (designer-ux): §3 grade × popup, §4 cabeçalho padrão, §5 página inicial;
  - `revisao-marca-geral.md` (design-de-marca): MC-0001 a MC-0017.
- **Escopo:** toda tela logada do site (faróis, Painel Executivo, Parcial, Editar, Usuários, Trocar senha) e o login. É a régua de cada leva nova: a tela que cumpre a §15 não precisa de outra revisão do zero.
- **Quem consome:**
  - modulo-web: implementa (`web/app/templates/`, `web/app/static/`, `web/app/tabelas.py`, `web/app/render.py`);
  - designer-ux e design-de-marca: conferem;
  - testes: medem a §15;
  - revisor-codigo e corretor-redundancias: citam "tela-bc3 §N" no parecer.
- **Regra de versão:**
  - acrescentar uma tabela à `GRADE` (§6), um nome curto (§13) ou um texto de estado (§9) é acréscimo: a v1 continua;
  - mudar uma regra (altura da faixa, teto de colunas, rolagem, breakpoint, tokens) é **v2**. Antes vem a simulação PNG (regra 10) e o "aprovo" do Alexandre, e depois um recado aos consumidores.
- **Valores de cor e de fonte:** este contrato só diz **qual token** cada parte da tela usa (§12). O valor (hex, família, tamanho) está num lugar só: `docs/marca/manual.md` (§4 paleta, §5 tipografia), aprovado pelo Alexandre (R-20261126-182227-alexandre). Nenhum hex neste contrato.

---

## 1. Princípios (valem em todas as seções)

1. **Uma informação, um lugar.** Um número, um nome ou uma contagem aparece uma vez na tela. Exemplos: o título do farol fica só na faixa; a contagem de linhas fica só na aba; o nome do cliente aparece uma vez na linha.
2. **Cabe numa tela no PC.** A 1366×768 e a 1920×1080, a página não rola (exceções na §7.4).
3. **Rolagem só por dentro da tabela, e só vertical.** Nenhuma tabela rola para o lado em 1366, 1920 ou 390 px.
4. **No celular (≤ 700 px), o M3:** lista que abre, tabelas de baixo recolhíveis, alvos de 44 px.
5. **A tela não explica o sistema.** Frase sobre como o dado chega, qual função grava ou por que o filtro não vale não aparece no corpo. A informação vai para o controle (desabilitado, com `title`) ou sai.
6. **A web não recalcula.** Todo número da faixa e dos cartões vem pronto do pacote (`kpis`, `kpis_padrao`, `recortes`; contrato do relatório §10). Renomear é só exibição (§13).

## 2. Medidas de referência

| Nome | Valor | Uso |
|---|---|---|
| PC pequeno | 1366×768 | a medida que manda: tudo cabe nela |
| PC grande | 1920×1080 | sem esticar coluna; a sobra vai para a tabela de cima |
| Celular | 390×844 | o M3 |
| Quebra para o M3 | `max-width: 700px` | a única quebra do layout |
| Lateral | 200 px (PC) | fecha atrás do ☰ no celular |
| Área útil da tabela a 1366 | 1.142 px | a base do teto de 10 colunas (§6.2) |

## 3. Casca (todas as telas logadas)

- **Uma casca só:** a BC3 (barra lateral + faixa verde em cartão). Ela vale para todas as telas logadas, não só para os faróis.
  - Hoje ela é ligada farol a farol: `main.py:145`, `ctx.setdefault("bc3", bool(u) and ctx.get("rid") in render.BC3)`. Essa condição sai, e a casca antiga (topo branco, `cab-painel`, rodapé com a versão) deixa de existir.
- **Login:** a mesma identidade, centralizada e sem lateral. Leva o logo grande, o título "BAP Central" e, pequeno, "BAP AUTOPARTS". O botão é "Entrar"; o título nunca repete o botão.
- **Lateral:**
  - **Topo:** o logo aprovado (`logo_bap.png`, servido como `/static/logo_bap_56.png`, sem raio, sem fundo e nunca recolorido; mínimo de 24 px), com "BAP Central" e, embaixo, "BAP AUTOPARTS" em `--t-rotulo` na cor `--suave` (MC-0001).
  - **Grupos, nesta ordem:** Diretoria (Painel Executivo) · Pré-venda · Pós-venda · Vendas · os grupos novos que a migração trouxer · Conta (Usuários, Trocar senha, Sair).
  - O usuário só vê os itens do perfil dele (`render.menu_lateral`).
  - **Nomes curtos** (§13): o nome completo fica no título da faixa.
  - **Item sem dado no pacote:** o texto fica visível ao lado do nome, "Sem dados hoje". Não basta o `title`.
  - **Item ativo:** marca à esquerda (`▌`) e `aria-current="page"`.
- **Ícones da aba e do atalho:** `favicon-32.png` e `apple-touch-icon-180.png`, com o símbolo "b" (MC-0010).
- **Sem rodapé de versão na tela.** A versão fica no `/saude`.

## 4. Cabeçalho: a faixa

### 4.1 Forma

```
┌─ faixa (fundo --faixa-inicio → --faixa-fim) ────────────────────────────────────────┐
│ <Título completo>   <dd/mm/aaaa hh:mm> [Desatualizado]              [BAP|AM|MA|PA]   │  linha 1
│ RÓTULO 1    RÓTULO 2    RÓTULO 3    RÓTULO 4    RÓTULO 5    RÓTULO 6                 │  linha 2
│ valor       valor       valor       valor       valor       valor                    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- **Altura fixa:** `--faixa-alt` = 88 px a 1366 e 96 px a 1920. É **a mesma em todas as abas da tela**: nada "pula" ao trocar de aba (G6). O `body.uma-tela .bc3-faixa` não muda padding nem fonte por aba.
- **Linha 1:**
  - o título completo do farol ou da tela;
  - a data dos dados, sem a palavra "Dados de". O `title` dá o texto inteiro: "Dados de 24/11/2026 08:30, horário de Manaus". Quando a tela tem a hora do PC e a do envio (Cobrar no WhatsApp), entra uma linha curta ao lado da data, "PC: 24/11 08:07 · envios voltam às 08h e 14h", e nunca numa faixa própria acima da faixa verde;
  - o selo âmbar "Desatualizado", quando os dados do farol têm mais de 26 h;
  - à direita, o filtro de estado.
- **Linha 2:** até **6 números**: os `kpis` do farol (ou os `kpis_padrao` da aba, §10.7 do contrato do relatório), na ordem do PC.

### 4.2 Regras

- **Os números ficam em todas as abas.** Aba de tabela, Solicitação BAP e as abas da Inadimplência mostram os mesmos números da aba Resumo.
- **O filtro não apaga a faixa.** A faixa fica com a mesma altura e a linha 2 (G6); o que muda é o que os cartões mostram:
  - **estado com recorte:** os cartões trocam pelos `recortes[UF].kpis` (contrato do relatório §10.1);
  - **estado sem recorte:** o cartão mostra "—", nunca o número da BAP inteira (contrato do relatório §10.1; tabela do §9, "Estado sem recorte");
  - **aba de tabela com `kpis_padrao`:** os cartões da aba valem só com os filtros no padrão, sem recorte e sem estado. Com outro filtro, recorte ou estado, os cartões da aba saem e fica o `AVISO_CARTOES` (contrato do relatório §10.7.2 e §10.7.6);
  - **cartão com o número da BAP inteira** (aba só da BAP inteira, Visita): leva sempre a marca "BAP inteira", também quando o PC já pôs `detalhe` ("BAP inteira · {detalhe}"). O número da BAP inteira nunca aparece sem essa marca.
- **Filtro de estado:** um controle segmentado só, com o rótulo "BAP" para o todo (MC-0014).
  - Em aba só da BAP inteira, o controle aparece cinza e desabilitado (`aria-disabled="true"`), com o `title` "Esta aba é só da BAP inteira". **Nenhum aviso no corpo**: saem o `render.AVISO_SO_BAP` e o `tabelas.AVISO_SEM_ESTADO` do corpo da tela.
  - Tela sem estado nenhum (Visita): o controle não aparece, e o corpo não leva aviso.
- **Telas sem números:**
  - Usuários: a faixa leva "Ativos · Desativados · Troca pendente";
  - Trocar senha, Parcial e Editar: a faixa leva só o título, na mesma altura;
  - Parcial: o título é "Parcial · <farol>", e o seletor Acumulado / D-1 / Hoje fica no lugar das abas.
- **Proibido:**
  - um `<h1>` ou título repetido no corpo (ex.: `_fila.html:21`);
  - o nome do farol fora da faixa e da lateral;
  - frase que explica o sistema (§1, item 5).
- **Contraste:** o texto pequeno (data, rótulos) tem 4,5:1 ou mais, e o número grande 3:1 ou mais, medidos contra o **ponto mais claro** do degradê (MC-0005, G7). Os tons de farol dos números (ok, atenção, alerta) seguem a §12.

## 5. Barra das abas e das ações

```
 Resumo  Pedidos · 21  Solicitação BAP                 [Filtros ▾] [🔍 Buscar pedido ou cliente] [Exportar ▾]
```

- **Uma linha só**, logo abaixo da faixa: as abas à esquerda e as ações à direita.
- **Abas curtas** (§13), com a contagem depois do nome ("Pedidos · 21").
  - A contagem **vem do servidor**: é o total depois do filtro e da busca, e não as linhas do DOM (G5, `bc3.js:80`).
  - É o único lugar da contagem: o rodapé `bc3-rod` ("21 pedidos") sai.
- **Se as abas não couberem a 1366:**
  1. abaixo de 1500 px, a busca vira um ícone que abre ao clicar;
  2. se ainda não couber, as últimas abas vão para "Mais ▾" (no Painel Executivo, "Indicadores ▾").
  - A barra nunca quebra em duas linhas e nunca rola para o lado.
- **Sub-abas** (Solicitação BAP): o mesmo controle segmentado do filtro de estado, em fundo claro. Não existe um terceiro estilo de aba.
- **Ações:**
  - "Filtros ▾" e "Exportar ▾" usam o mesmo marcador ▾ (`::after`), nunca o ► do navegador;
  - o Exportar agrupa Excel, PDF e CSV; o Excel leva **todas** as colunas (§6.3, regra 5);
  - a busca tem dica **por farol** (§13.3), sem corte a 1366.
- **Caixas de marcar** (ex.: "Ignorar fora da base", RN-GER-013): uma caixa de verdade (`<input type="checkbox">`, ou um link sem `role="checkbox"`), marcada por padrão quando a regra pede. O `title` é curto ("Pedidos internos").

## 6. Grade e popup

### 6.1 Regras

1. **Cada tabela de cima tem uma coluna-chave**, sublinhada.
   - Ao passar o mouse nela ou ao focá-la com o teclado, abre o popup da linha.
   - No Farol de Pedidos, o clique na chave também filtra as tabelas de baixo, como no PC.
2. **A grade tem no máximo 10 colunas de dado a 1366**, mais a coluna Editar do admin (à esquerda), e nenhuma quebra de linha:
   - cada célula fica em `nowrap`;
   - coluna de texto tem `max-width: --col-texto-max` (18ch), com reticências;
   - o texto inteiro vai no `title` da célula.
3. **O popup mostra só o que não está na grade**, em blocos com título (ex.: Cliente · Crédito · Pedido · Nota):
   - célula vazia ou "—" não entra;
   - valor igual ao de outra coluna da linha também não (ex.: PED. MÁX. igual ao PEDIDO).
4. **No celular (M3)**, a linha fechada mostra chave · nome · selo · valor. Aberta, mostra o popup inteiro (§8).
5. **O Excel e o PDF continuam com todas as colunas.** A grade é só a tela.

### 6.2 `GRADE` em `web/app/tabelas.py` (substitui `NO_POPUP`)

```python
GRADE = {
    # (rid, título da tabela no pacote): como ela aparece no site
    ("pv_pedidos", "Pedidos"): {
        "chave": "PEDIDO",
        "grade": ("DT. PED", "FATURAR ATÉ", "PEDIDO", "FANTASIA", "UF", "CIDADE", "R$ VENDA",
                  "% DESC.", "SLA", "% ATENDIDO"),
        "blocos": (("Cliente", ("RAZÃO SOCIAL", "CÓD.")),
                   ("Crédito", ("LIMITE", "DISP.", "ATRASO", "COND. PAGTO")),
                   ("Pedido", ("ANÁLISE CRÉDITO", "SITUAÇÃO", "VENDEDOR", "PED. MÁX.", "VOL.",
                               "R$ TABELA", "FILIAL", "PRAZO")),
                   ("Nota", ("NF", "DT. NF"))),
        "cel": ("PEDIDO", "FANTASIA", "SLA", "R$ VENDA"),   # chave · nome · selo · valor
    },
}
```

- **Chave pelo par `(rid, título)`:** o mesmo título pode existir em dois faróis. O título é o do pacote, que é contrato (contrato do relatório §9): renomear a aba é só exibição.
- **`grade`:** as colunas da grade, nesta ordem. Se uma delas não vier no pacote (robô antigo), ela sai da grade sem erro.
- **`blocos`:** os grupos do popup. A coluna do pacote que não está em `grade` nem em `blocos` vai para o bloco "Outros", no fim. Nenhuma coluna some da tela sem aviso: ela está na grade ou no popup.
- **`cel`:** as 4 colunas da linha fechada no M3. Use `None` quando não houver selo ou valor.
- **Tabela fora da `GRADE`:** é desenhada inteira. Ela só pode ficar fora se tiver **10 colunas visíveis ou menos**, e um teste confere isso nas fixtures de cada farol.
- **Funções:**
  - `colunas_no_popup`, `colunas_do_celular` e `dados_do_popup` passam a ler a `GRADE`;
  - o `dados_do_popup` devolve os blocos `[[titulo, [[nome, texto], ...]], ...]`, só com as colunas fora da grade;
  - o `popup_pedido.js` vira o "popup da linha", genérico. Os itens do Analítico continuam só no Pedidos.
- **Acessibilidade:**
  - a chave tem `aria-describedby` apontando para o popup;
  - o popup tem `role="tooltip"`, fecha com Esc e não cobre a própria chave.

### 6.3 Lista inicial (do parecer de UX, §3; a coluna-chave em **negrito**)

| Farol · tabela | Grade | Popup (blocos) | Celular |
|---|---|---|---|
| Pedidos · Pedidos | DT. PED · FATURAR ATÉ · **PEDIDO** · FANTASIA · UF · CIDADE · R$ VENDA · % DESC. · SLA · % ATENDIDO | Cliente · Crédito · Pedido (com ANÁLISE CRÉDITO, SITUAÇÃO e VENDEDOR) · Nota · **Itens** (do Analítico) [SUPOSIÇÃO: o parecer lista 13 colunas na grade; o teto é 10, então 3 descem para o popup, e a simulação pode trocar quais] | PEDIDO · FANTASIA · SLA · R$ VENDA |
| Pedidos · Gerar ID de separação CD / Gerar reversa de lojas | PEDIDOS · **CÓD. PROD.** · QTD · COLETAR EM · FILIAL DEST. (sigla) | DATA, DESCRIÇÃO, FORN., UF, CIDADE | recolhível |
| Pedidos · Analítico por pedido | **PEDIDO** · CÓD. PROD. · QTD · FALTA · VALOR FALTANTE | DATA, DESCRIÇÃO, FILIAL, EST. FRW, PEDIDOS ANTES, DISP. P/ ESTE, ATENDIDO | recolhível |
| Entregas · Entregas | **NF** · CLIENTE (só o nome) · CIDADE · UF · SITUAÇÃO · SLA · DT. PREVISTA · ETAPA · TRANSPORTADORA · VLR NF | Datas · Frete · Outros (código do cliente, FILIAL, PRAZO) | NF · CLIENTE · SLA · VLR NF |
| Entregas · Pendências dos meses anteriores | MÊS · **NF** · CLIENTE · SITUAÇÃO · SLA · DT. PREVISTA · ETAPA · VLR NF | o mesmo, mais UF e CIDADE | recolhível |
| Inadimplência · Títulos | **NOME** · NF · PARC. · VENCIMENTO · DIAS ATRASO · FAIXA · SALDO · SITUAÇÃO · STATUS · VENDEDOR | CLIENTE (código), VALOR, EMISSÃO, FILIAL, CIDADE, UF, SUPERVISOR, CONDIÇÃO | NOME · FAIXA · SALDO |
| Inadimplência · Por cliente | **NOME** · SITUAÇÃO · FAIXA · TÍTULOS VENCIDOS · EM ATRASO · MAIOR ATRASO · A VENCER · STATUS · VENDEDOR | CLIENTE (código), CIDADE, UF, SUPERVISOR, PRÓX. VENCIMENTO, LIMITE, PEDIDO EM ABERTO, ÚLTIMA COMPRA | NOME · FAIXA · EM ATRASO |
| Inadimplência · Por vendedor / supervisor / filial / UF | **NOME** · CARTEIRA ABERTA · A VENCER · EM ATRASO · % INADIMPL. · CLIENTES INADIMPL. | Atraso por faixa (1–15 … +180 dias) | NOME · % INADIMPL. · EM ATRASO |
| Visita · Por supervisor | **SUPERVISOR** · REPRES. · META · VISIT. · % META · % CONV. · % FORA DE ROTA · CAD. C/ COMPRA · PROSP. · JORNADA LÍQ. | Cadastro · Jornada · Tempo · Rota | SUPERVISOR · % META · VISIT. |
| Visita · Por vendedor | **VENDEDOR** · META · VISIT. · % META · % CONV. · % FORA DE ROTA · CAD. C/ COMPRA · PROSP. · JORNADA LÍQ. · KM/CLIENTE | SUPERVISOR + o mesmo de cima | VENDEDOR · % META · VISIT. |
| Visita · Dia a dia | DATA + DIA · **VENDEDOR** · SITUAÇÃO · META · VISIT. · % META · % CONV. · % FORA DE ROTA · INÍCIO · ÚLT. ATIV. | SUPERVISOR e as outras métricas | VENDEDOR · SITUAÇÃO · VISIT. |
| Visita · Aderência dia a dia | **VENDEDOR** · um quadrado de ~38 px por dia útil (só o %, na cor do farol) · % ACUM. | SUPERVISOR; o `title` do quadrado com a data e o % | VENDEDOR · % ACUM. |
| Visita · Cliente a cliente | DATA · VENDEDOR · **CLIENTE** (fantasia) · SITUAÇÃO · STATUS · CURVA · DIAS S/ COMPRA · PEDIDO NO DIA · VALOR PEDIDO · JUSTIFICATIVA (reticências) | DIA, SUPERVISOR, CÓD., razão social, SEGMENTO, BAIRRO, CIDADE, ATRASO · Roteiro · JUSTIFICATIVA inteira | CLIENTE · SITUAÇÃO · VALOR PEDIDO |
| Visita · Prospecção | DATA · VENDEDOR · **ESTABELECIMENTO** · SEGMENTO · CIDADE · STATUS · RESULTADO | HORA, DIA, SUPERVISOR, FONTE, UF, LINHAS DE INTERESSE, OBSERVAÇÃO | ESTABELECIMENTO · STATUS · CIDADE |
| Visita · Indicação | DATA · VENDEDOR · CLIENTE QUE INDICOU · **INDICADO** · CIDADE · SITUAÇÃO · VISITADA EM | DIA, SUPERVISOR, CÓD. QUEM INDICOU, BAIRRO, SEGMENTO, OBSERVAÇÃO, REGISTRADO EM | INDICADO · SITUAÇÃO · CIDADE |
| Metas Equipe (todas as abas) | como está (cabe) | sem popup no PC | nome · % ATING. · REAL |
| Solicitação BAP · Detalhado por pedido | a regra das 10 colunas, chave **PEDIDO** | o resto | PEDIDO · LOJA · QTD |

- Os faróis novos da migração (T-0023 a T-0043) entram nesta tabela **no PR que os traz**, com a medição da §15.
- O nome que a tabela já mostra não entra no popup, e vice-versa. O dado pessoal continua só onde o contrato do relatório permite (§10.6 e §10.7, RN-GER-011). O popup não abre exceção.

### 6.4 Tabelas de baixo (juntas)

- **No PC:** lado a lado, numa grade de caixas com a **mesma altura** (`align-items: start` e uma altura comum). Cada caixa tem rolagem vertical por dentro e nenhuma lateral.
- **Colunas:** saem as que o popup da linha de cima já mostra (`tabelas.FORA_DAS_JUNTAS`). Uma tabela de baixo nunca repete a coluna que a tabela de cima já filtra.
- **No celular:** recolhíveis, fechadas por padrão, com a contagem no título. A regra solta `.bc3-juntas{grid-template-columns:repeat(auto-fit,…)}` fica dentro de `@media(min-width:701px)` (G3, `estilo.css:466`).
- Uma tabela de largura total abaixo da de cima (Pendências do Entregas) começa fechada, com a contagem no título, se a de cima ficar com menos de 8 linhas visíveis a 1366.

## 7. Rolagem

### 7.1 A página

- No PC, a página não rola (`body.uma-tela`). A faixa, as abas e as caixas de baixo têm altura fixa. A tabela de cima ocupa o resto (`flex: 1`).
- Os cartões do Resumo e do Painel Executivo também ocupam o resto (`flex: 1`), sem `min-height` fixo (sai o `min-height:540px` do `.rc`).

### 7.2 A tabela

- A rolagem é vertical, por dentro da caixa, com o cabeçalho fixo (`position: sticky`). **Nunca há rolagem lateral:** a grade da §6 garante isso.
- **Sem páginas.** Sai o "Página 1 de 3 · Próxima »" (`tabelas.tabela_para_tela(..., pagina_tam=100)`, `_tabela.html:63-68`).
  - A página traz **até 500 linhas** da tabela.
  - Acima disso, ao chegar perto do fim da rolagem, o navegador pede mais 500 a `GET /farol/<rid>/linhas?aba=<aba>&desde=<n>&<os mesmos filtros>`. A resposta é o HTML só das linhas, com o mesmo corte de perfil e de estado da página.
  - Isso substitui a frase "A web pagina no servidor (100 linhas por página)" do contrato do relatório §10.7.8.
- **Busca e filtro:**
  - com até 500 linhas no navegador, filtram ali mesmo;
  - com mais de 500, vão ao servidor (`q=`), para a contagem e as linhas baterem com o total.
  - A contagem da aba é sempre o total do servidor (§5).

### 7.3 As caixas de baixo e o popup

- Caixas de baixo: §6.4.
- O popup não rola. Se não couber, ele abre para o lado com mais espaço. Se ainda não couber, os blocos viram duas colunas.

### 7.4 Exceções (a página pode rolar)

- **Fila de trabalho** (Cobrar no WhatsApp): no PC, 2 colunas de cartões ou 6 cartões por vez, cabendo a 1366×768; no celular, a página rola.
- **Formulários** (Editar, Novo usuário, Trocar senha) no celular.
- Nenhuma outra. Uma tela nova que precise rolar volta ao designer-ux antes da simulação.

## 8. Celular: M3 (≤ 700 px)

- **Topo:** "BAP Central" + ☰. O menu fecha com um toque fora e com Esc, e respeita `prefers-reduced-motion`.
- **Faixa:**
  - título · data (curta: "24/11 08:30");
  - o filtro de estado com alvos de 44 px;
  - os números em 3 colunas, com o rótulo curto (ex.: "Faturamento", com o detalhe "desafio comercial").
- **Abas:** um segmentado sem rolagem, com até 3 abas e "Mais ▾" para as outras (alvos de 44 px).
- **Tabela = lista que abre:**
  - a linha fechada mostra as 4 colunas `cel` da `GRADE` (chave · nome · selo · valor);
  - aberta, mostra todas as outras, nos blocos do popup;
  - tabela fora da `GRADE`: a 1ª coluna é a chave, a 2ª o nome, e a última numérica é o valor;
  - "Ver mais 10 (faltam N)" carrega mais 10 (`bc3.js:97`).
- **Tabelas de baixo:** recolhíveis (§6.4).
- **Cartões do Resumo e do Painel:**
  - o primeiro abre, os outros ficam fechados (título + % + selo);
  - as barras por estado ficam deitadas.
- **Alvos de toque:** 44 px ou mais em abas, filtro de estado, itens do menu, linhas da lista e botões.
- **Critério:** nenhuma rolagem lateral em 390 px (`scrollWidth ≤ clientWidth` em toda caixa).

## 9. Estados vazios e de dado

Um texto por situação, igual em todas as telas. O texto não explica o sistema.

| Situação | Onde aparece | Texto |
|---|---|---|
| O farol não veio no pacote | item da lateral | "Sem dados hoje" (visível) |
| O farol não veio no pacote | página: a faixa só com o título | "Sem dados hoje." |
| Nenhum pacote no site ainda | página | "Sem dados ainda. A primeira atualização chega às 06h30." |
| Tabela vazia com filtro ou busca | dentro da caixa | "Nenhuma linha com este filtro." + o link "Limpar filtro" |
| Tabela vazia sem filtro | dentro da caixa | "Nenhuma linha hoje." |
| Aba cortada pelo tamanho do pacote | uma linha acima da tabela (§10) | o `AVISO_ABAS_FORA` do robô (contrato do relatório §10.7.6) |
| Dados com mais de 26 h | faixa, ao lado da data | o selo âmbar "Desatualizado" |
| Estado sem recorte | o cartão | "—" (nunca o número da BAP inteira) |
| Cartão com o número da BAP inteira | o cartão | a marca "BAP inteira" (com `detalhe`: "BAP inteira · {detalhe}") |
| Aba com `kpis_padrao` e filtro, recorte ou estado | no lugar dos cartões da aba | o `AVISO_CARTOES` (contrato do relatório §10.7.6) |
| Bloco de gráfico que a web não desenha | no lugar do bloco | "ainda não disponível na web" (`render.INDISPONIVEL`, contrato §10.1) |
| A parcial não chegou | página da Parcial | "A parcial ainda não chegou do PC." |
| Erro do servidor | `erro.html`, dentro da casca | "Não deu para abrir agora. Tente de novo em 1 minuto." |
| Sem permissão (403) | `erro.html`, dentro da casca | "Esta tela não faz parte do seu perfil." |

## 10. Avisos

- **O que pode ser aviso:** só o que muda a leitura do número ou da tabela.
  - Exemplos: aba fora por tamanho; dado parcial do dia; "O PC recusou" na edição.
  - Fica numa linha curta acima da tabela, no tom atenção (`--atencao-claro` com texto `--texto`).
  - **No máximo 2 visíveis.** Os outros ficam atrás de "+N avisos".
- **O que não é aviso** (sai do corpo):
  - frase que explica o sistema: `AVISO_SEM_ESTADO`, `AVISO_SO_BAP` no corpo, "gravada pela mesma função da tela do PC" (`editar.html:42`, que vira "Chega ao PC em até 30 min.") e a faixa azul do Cobrar (`farol.html:6`, que vai para a linha 1 da faixa, §4.1);
  - a contagem repetida (§5).
- **Erro de formulário:** fica junto do campo, com `role="alert"` (login, senha, Editar).
- **Confirmação de ação:** uma linha no topo da caixa, no tom ok, que some sozinha em 5 s (`aria-live="polite"`). Ex.: "Edição enviada. Chega ao PC em até 30 min."
- **Cores de aviso:** só os tokens da §12. As cores soltas de aviso do visual antigo saem (lista no manual, §4.2).

## 11. Botões e ações

| Nível | Aparência | Regra |
|---|---|---|
| Principal | fundo `--verde-escuro`, texto `--faixa-texto` (contraste no manual, §4.3) | **um só por tela**. Ex.: "Baixar imagem" (Parcial), "Novo usuário" (Usuários), "Salvar" (Editar). No cartão de fila, um por cartão ("Abrir WhatsApp") |
| Neutro | contorno `--borda`, texto `--texto` | todo o resto: "Pular", "Trocar senha", "Cancelar" |
| Perigo | texto `--erro`, sem fundo | **sempre com confirmação**. O diálogo diz o verbo e o alvo ("Desativar o usuário fulano.web?"), e o botão de confirmar repete o verbo |
| Menu | "Exportar ▾", "Filtros ▾", "Mais ▾" | o mesmo ▾ em todos |

- **Rótulo com verbo.** Botão só com ícone leva `aria-label`.
- **A coluna Editar do admin** fica à esquerda da grade e não conta no teto de 10 colunas.
- **Foco visível** em tudo que recebe foco: `:focus-visible` com contorno de 2 px em `--verde-escuro`, e `.bc3-busca:focus-within` também. Nada de `outline: 0` sem substituto (`estilo.css:379`).
- **Movimento:** `@media (prefers-reduced-motion: reduce)` desliga as transições da lateral e do popup.
- **Ação destrutiva ou que vai ao PC** (editar, desativar, cobrar) só para o perfil que pode. O corte é no servidor, antes do HTML; esconder o botão não basta.

## 12. Tokens: cor, fonte e medida num lugar só

- **Fonte única dos valores:** `docs/marca/manual.md` (§4 paleta em tokens, com o contraste de cada par; §5 tipografia). Este contrato não repete valor: muda o manual, muda a tela, sem mexer aqui.
- **Onde ficam no código:** um bloco `:root` só, no topo de `web/app/static/estilo.css`, com os nomes do manual.
  - Nenhuma cor em hex fora desse bloco. O teste lê o CSS e falha se achar `#` + hex fora do `:root`.
  - O PDF e o Excel do site (`web/app/exportar.py`) não leem CSS: usam as constantes de um módulo só, `web/app/marca.py`, com os mesmos nomes. Um teste confere que `marca.py`, o `:root` e o manual têm os mesmos valores.
- **Saem** as sobras do visual antigo e as cores "quase iguais" que o manual lista (§4.2).

### 12.1 Cor (os valores estão no manual, §4)

| Token | Papel na tela |
|---|---|
| `--verde-marca` | logo, selo e destaque grande; nunca texto em fundo claro |
| `--verde-escuro` | botão principal, item ativo da lateral, aba ativa, contorno de foco, texto verde |
| `--verde-claro` | fundo de destaque (grupo, total, linha selecionada), só com `--texto` |
| `--preto-bap` | a placa do logo |
| `--texto` | texto principal |
| `--suave` | rótulo, data, texto de apoio (inclui o "BAP AUTOPARTS" da lateral) |
| `--fundo` | fundo da página |
| `--cartao` | cartões, caixas e tabelas |
| `--borda` | contorno de cartão, de campo e do botão neutro |
| `--grade` | linhas internas da tabela |
| `--erro` / `--erro-claro` | mensagem e campo com erro, ação de perigo (Desativar) / fundo da caixa de erro |
| `--alerta` / `--alerta-claro` | número e ponto vermelhos do farol / fundo da linha em alerta |
| `--atencao` | só ponto, ícone e barra amarelos (nunca texto) |
| `--atencao-texto` | número e texto em atenção |
| `--atencao-claro` | fundo da linha em atenção e dos avisos (§10) |
| `--ok` / `--ok-claro` | número e ponto verdes do farol / fundo da linha boa |
| `--faixa-inicio` / `--faixa-fim` | o degradê da faixa (§4) |
| `--faixa-texto` | todo o texto da faixa, inclusive o pequeno |
| `--faixa-ok` / `--faixa-atencao` / `--faixa-alerta` | o número em farol na faixa, só em número grande e negrito |
| `--grafico-1` / `--grafico-2` / `--grafico-3` | as barras de comparação dos cartões, sempre com o número ao lado |

- O contraste mínimo de cada par (texto 4,5:1; texto grande e ícone 3:1) é o do manual, §4.3. Par fora da tabela do manual pede parecer do design-de-marca antes do PR.

### 12.2 Fonte (a família, os tamanhos e os pesos estão no manual, §5)

| Token | Papel na tela |
|---|---|
| `--fonte` | toda a tela (a pilha do manual) |
| `--t-faixa-titulo` | título da faixa |
| `--t-numero` | número de destaque (faixa e cartão) |
| `--t-bloco` | título de bloco ou de cartão |
| `--t-corpo` | texto, menu, botão |
| `--t-tabela` | células da tabela (algarismos de mesma largura) |
| `--t-apoio` | apoio, data, rodapé |
| `--t-rotulo` | rótulo de coluna e de número: o menor tamanho permitido |

- O mesmo papel usa sempre o mesmo token, em todas as telas. Os pesos são só os do manual.

### 12.3 Medida (valores da UX; a marca só confere)

| Token | Valor |
|---|---|
| `--lateral` | 200 px |
| `--faixa-alt` | 88 px (≤ 1600 px de largura) · 96 px (acima) |
| `--alvo` | 44 px (celular) |
| `--col-texto-max` | 18ch |
| `--raio` | 8 px (cartões e caixas; o logo não tem raio) |

## 13. Nomes

### 13.1 Produto e empresa

- **"Painel Executivo"** em todo lugar: lateral, título da faixa, aba do navegador, PDF e Excel.
  - Saem "Painel do Diretor · resultado" (`painel.html:24`) e "Painel do Diretor" em geral.
  - A aba diz qual visão é ("Resultado", "Produtividade"...).
  - A troca é só na exibição (`render`). O `titulo` do pacote não muda: é contrato (contrato do relatório §9).
- **"BAP AUTOPARTS"**, sempre assim, em tela, PDF, Excel, mensagem ao cliente e e-mail (regra 8). Nunca "BAP Auto Parts" nem "BAP AUTO PARTS" (MC-0002, MC-0011).
- **"BAP Central"** é o nome do produto: lateral e login. A aba do navegador (`<title>`) diz "<tela> · BAP AUTOPARTS" (manual da marca §7).
- O filtro de estado diz **"BAP"**, nunca "BAP inteira".

### 13.2 Lateral (curto) × faixa (completo)

| Lateral | Faixa |
|---|---|
| Painel Executivo | Painel Executivo |
| Pedidos | Farol de Pedidos |
| Entregas | Farol de Entregas |
| Inadimplência | Farol de Inadimplência |
| Visita | Farol de Visita |
| Metas Equipe | Farol de Metas Equipe |

### 13.3 Abas curtas e dica da busca

| Tela | Abas | Dica da busca |
|---|---|---|
| Painel Executivo | Resultado · Produtividade · Por DU · Resumo · Faturamento · Volume · Visitas · Positivação · Itens · Markup · Preço · Inadimplência ("Produtividade" do painel de visitas vira "Visitas") | — |
| Pedidos | Resumo · Pedidos · Solicitação BAP | "Buscar pedido ou cliente" |
| Entregas | Resumo · Entregas | "Buscar NF ou cliente" |
| Inadimplência | Resumo · Títulos · Por cliente · Cobrar no WhatsApp · … | "Buscar cliente ou NF" |
| Visita | Resumo · Supervisor · Vendedor · Dia a dia · Aderência · Cliente a cliente · Prospecção · Indicação | "Buscar vendedor ou cliente" |
| Metas Equipe | Equipe · Top 30 · UF · Cidade · Bairro · Segmento · Zona · Categoria · Família | "Buscar nome" |

### 13.4 Perfis e situações

- **Perfis:** Admin · Diretor · Gerente · Pré-venda · Pós-venda · Vendas. Os perfis novos entram com rótulo no PR que os cria. O código (`pos_venda`) nunca aparece na tela.
- **Situação de usuário:** selos Ativo (verde) · Desativado (cinza) · Troca de senha pendente (amarelo).
- **Selo** sempre com texto: a cor sozinha não carrega a informação.

## 14. Página inicial

- `/` redireciona (302) cada perfil para a tela dele. A grade de quadrados (`home.html`) sai, porque a lateral é o menu.

| Perfil | Abre em |
|---|---|
| admin, diretor, gerente | `/painel` (Painel Executivo) |
| pre_venda | `/farol/pv_pedidos` |
| pos_venda | `/farol/pl_entregas` |
| vendas | `/farol/vc_visitas` |
| perfis novos (ex.: analista, trade) | o primeiro farol do grupo deles [SUPOSIÇÃO: decisão 2 do R-20261126-175814-gerente-projetos, recomendação A] |

- O Painel Executivo segue as §4 a §8:
  - os 3 números de cabeça da aba vão para a faixa, como estão no cartão RRM do PC, sem recalcular;
  - os cartões perdem o número grande, que já está na faixa;
  - o "como ler" vira um ícone ⓘ com `title`.
- A especificação completa está no parecer de UX, §5. A implementação é da T-0034.

## 15. Conferência (todo PR com tela)

O testes mede e o PR traz o resultado. Sem ele, o revisor-codigo marca 🟡.

1. **Sem rolagem lateral:** `scrollWidth ≤ clientWidth` em toda caixa de tabela, a 1366×768, 1920×1080 e 390×844 (`ux_png.mjs` do designer-ux, ou `web/simular_png.mjs`).
2. **A página não rola no PC:** `document.scrollingElement.scrollHeight ≤ innerHeight` a 1366×768 e 1920×1080, menos as exceções da §7.4.
3. **A faixa tem a mesma altura em todas as abas** da tela (diferença de 0 px).
4. **Grade com 10 colunas ou menos** (sem a Editar) em toda tabela de cima. A tabela fora da `GRADE` tem 10 colunas visíveis ou menos.
5. **O popup não repete** coluna da grade (teste unitário do `dados_do_popup`).
6. **A contagem da aba bate com o servidor** com filtro e busca, inclusive acima de 500 linhas.
7. **Alvos de 44 px** no celular (abas, filtro de estado, menu, linhas).
8. **Contraste:** texto pequeno com 4,5:1 ou mais, e número grande com 3:1 ou mais, no pior ponto da faixa.
9. **Nenhum hex fora do `:root`.** `marca.py` é igual ao `:root`.
10. **Um botão principal por tela.** Toda ação de perigo pede confirmação.
11. **Nomes:** "Painel Executivo" e "BAP AUTOPARTS" (teste de texto no HTML de cada tela). O logo está na `.bc3-marca` (MC-0013).
12. **Simulação PNG antes do PR** (regra 10): antes × depois, a 1366, 1920 e 390, com dados fictícios.

## 16. Pendências

- **Valores dos tokens:** decididos no `docs/marca/manual.md` (R-20261126-182227-alexandre). O modulo-web aplica no `:root` e no `marca.py`, com simulação antes (regra 10), porque alguns tons mudam o que o Alexandre já viu (o canto da faixa, o vermelho, o cinza de apoio).
- **Perfis sem Painel e perfis novos** (§14): decisões 2 e 3 do R-20261126-175814-gerente-projetos.
- **O botão verde "Cobrar no WhatsApp", que repete a aba** (decisão 7 do mesmo recado): se ficar, conta como o principal da tela.
- **As 3 colunas a mais da grade do Pedidos** (§6.3): a medição da simulação da T-0033 decide quais descem para o popup.
