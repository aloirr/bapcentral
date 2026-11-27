# ADR 0005 — Config editada pela web: por seção, com versão por hash, cópia antes e gravação pelo robô

- **Status:** proposta (T-0025 v2). Primeiro arquivo: `champions_config.json`, autorizado pelo Alexandre em 26/11 (R-20261126-171559-alexandre). Os outros arquivos (T-0042) entram um por um, cada um com o "autorizo" dele (decisão 6 A do R-20261126-180314-alexandre).
- **Data:** 2026-11-27
- **Tarefa:** T-0025 (v2) · **Autor:** engenheiro-software
- **Depende de:**
  - ADR 0001 (web no Render, modelo M2: o PC monta, a web mostra);
  - ADR 0003 (pacote por farol);
  - contrato do relatório §10.9 (edição pela web) e §10.9.5 (esta config);
  - RN-GER-012 (edição só no site, só do admin, gravada pelo robô com a função do PC);
  - regra 7 do `CLAUDE.md` (dado digitado intocável).
- **Consumidores:**
  - modulo-web: `web/app/edicoes.py`, `main.py`, a página nova `/farol/vc_champions/parametros`;
  - modulo-robo: `bap_automation.py`, o ramo `champions` do `aplicar_edicao_web`;
  - modulo-farois: `bap_relatorios.DialogoChampions` (fica só leitura) e `bap_champions` (só leitura do código; `validar` e `gravar` não mudam);
  - testes.

## 1. Contexto

- A T-0021 v4 levou a edição de **linhas de tabela** ao site: fila só de acréscimo na web, e o robô gravando no PC pela função da tela, também só acrescentando (diários `_AUTORIZACOES` e `_EDICOES_POS_VENDA`).
- A migração pede agora a edição de **arquivos de config**. O primeiro é o `champions_config.json`: pontos, aceleradores, trava, Aux. Técnico, confrontos, fora do jogo, campanha relâmpago e equipe do mês. Depois vêm as configs de transportadoras, metas, Planner e kits (T-0042).
- Uma config não tem linha nem diário. O PC grava o arquivo inteiro (`bap_champions.gravar`: arquivo temporário e troca). Duas edições seguidas podem se apagar, e uma edição errada perde o que estava digitado.
- A regra 7 põe o `champions_config.json` entre os dados digitados intocáveis. O Alexandre autorizou a edição pela web dele, só pelo admin e gravada pelo robô.

## 2. Opções

| | Opção | A favor | Contra |
|---|---|---|---|
| A | A web manda o arquivo inteiro novo | simples | duas edições na mesma rodada se apagam; a web carregaria o arquivo inteiro; um campo errado troca tudo |
| B | A web manda um campo por vez (`pontos_por_mil.VENDEDOR` = 35) | edição mínima | listas (jogos, relâmpago, equipe do mês) não cabem bem em "campo = valor"; muitas linhas na fila |
| **C** | **A web manda uma seção inteira (uma aba da tela do PC), com o hash da seção que ela viu; o robô troca só aquela seção se o hash ainda bate, valida com a função do PC, copia o arquivo antes e grava com a função do PC** | uma aba da tela = uma edição; conflito detectado; nada se perde (cópia antes e diário de aplicadas); a mesma forma serve às configs da T-0042 | a seção vai como JSON em texto na fila (até 32 KB) |
| D | O site guarda a config e o PC lê do site | o site vira a fonte | inverte o modelo M2 (ADR 0001); o PC passa a depender do site para calcular; o PC ficaria sem a config se o site caísse |

## 3. Decisão: C

1. **No pacote** (só no farol dono da config; para o champions, o `vc_champions`): o bloco `parametros_edicao`, com as seções, o `sha` de cada uma (SHA-256 do JSON canônico, 16 dígitos hexadecimais), o valor de hoje e as listas da tela do PC. A web lê o bloco só para o admin.
2. **Na web:** uma página por config, uma aba por seção, "Salvar" por seção. A fila é a mesma da T-0021 (`EDICOES_WEB_<AAAA-MM>.jsonl`, só acréscimo):
   - `modulo` = o da config;
   - `chave` = a seção;
   - `valores` = `{"valor": "<JSON>"}`;
   - `antes` = `{"sha": ...}`.
3. **No robô:**
   - confere o hash: se a seção mudou desde que a tela abriu, a edição vira `erro`;
   - confere a forma pelo `PADRAO` do módulo do PC;
   - troca só a seção e roda o `validar` do PC;
   - copia o arquivo, byte a byte, para `RELATORIOS/_EDICOES_WEB/ANTES/<AAAA-MM-DD>_<arquivo>` (uma cópia por dia, antes da 1ª gravação; nunca apagada);
   - grava com a função do PC (`gravar(raiz, cfg, por="web:<login>")`) e registra a aplicada no `APLICADAS_WEB_<máquina>.jsonl`.
4. **No PC:** a tela da config fica só leitura (RN-GER-012), com "A edição agora é só pela BAP Central web.".
5. **Governança:**
   - cada arquivo novo nesta forma pede um "autorizo" do Alexandre, citado no PR que o liga (decisão 6 A);
   - os `.json` da raiz do repositório continuam governança;
   - a rotina diária (ADR 0002) não leva config ao PC, então o robô nunca sobrescreve a config da produção com a do repositório.

## 4. Consequências

- **Sem dependência nova:** `hashlib` e `json` são da biblioteca padrão, e nada muda no PC do robô (DT-AMADMBAP-03).
- `bap_dados.VERSAO` continua 27. A config não entra no cache: o `montar` já a lê a cada rodada.
- **Dado pessoal:** a config do champions tem nomes da equipe, códigos e metas, e nenhum CPF nem e-mail. O CPF e o e-mail da premiação estão no `campanha_export`, que nunca vai ao site. A web recusa texto com CPF, CNPJ, telefone ou e-mail (RN-GER-011).
- **Concorrência:** duas edições da mesma seção na mesma rodada são resolvidas na ordem do `seq`: a primeira grava, e a segunda vê o hash mudado e volta como "O PC recusou", com a frase fixa. A pessoa abre de novo e refaz.
- **Volta atrás:** a cópia do dia, em `_EDICOES_WEB/ANTES/`, mais o diário de aplicadas. Restaurar é manual, no PC, com o "ok" do Alexandre.
- **Teste:** um teste por passo do §3.3, com config fictícia em pasta temporária, nunca na base real.
