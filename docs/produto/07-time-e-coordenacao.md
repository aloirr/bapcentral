# 07 — Time e coordenação

## Fluxo
1. O **Alexandre** fala com o **po** (sessão fixa "BapCentral - Agente PO"), ou escreve pelo formulário de issue "Recado" do `aloirr/bapcentral-recados`.
2. O **po**:
   - grava cada decisão do Alexandre como recado `de: alexandre`, com o texto literal, e avisa o gerente por `send_message` com o id e o resumo;
   - não edita nenhum arquivo do repositório de código: especificação vai como texto dentro do recado (T-0008);
   - faz ronda a cada 10 min e cobra do gerente os ids de decisão sem marca em `lidos/gerente-projetos.txt`.
3. O **gerente-projetos** (sessão fixa "BapCentral - Gerente Projeto", ronda a cada 20 min, com reserva de hora em hora):
   - cria a tarefa (backlog só com autorização escrita do Alexandre) e delega a subagentes ou a sessões filhas, uma por dono;
   - repassa o texto **completo** de cada recado às sessões filhas, no prompt inicial, e marca o recado como lido;
   - cobra e valida com o `testes` e o `revisor-codigo`; faz o PR e o merge;
   - manda **tudo** ao po por `send_message` (relatório, ronda, pergunta, pendência, previsão) e deixa recado ao po a cada movimento: tarefa criada ou repriorizada, delegação, bloqueio e desbloqueio, PR, revisão, merge, entrega e pedido de decisão (T-0008);
   - arquiva as sessões filhas finalizadas do BapCentral; nunca as duas fixas nem sessões de outros projetos.
4. Todo resumo ao Alexandre sai em 4 blocos, nesta ordem: **Entregue** · **Em andamento** · **O que o time pede a você** · **Próximo passo** (bloco vazio = "nada"). Termina com "Decisões que você precisa tomar". Ao Alexandre só vai decisão que muda algo agora; item com recomendação clara e sem efeito no prazo segue a recomendação e é informado no relatório.
5. A entrega volta ao **po**, que explica ao Alexandre e pede o "instale" quando vai para a produção (T-0003). Deploy só com "aprovo deploy vX.Y.Z"; merge de governança só com "autorizo o merge do PR #N no commit <sha>", com o SHA completo.

## Sessões e variáveis (claude.ai/code)

| Ambiente | Variáveis | Uso |
|---|---|---|
| BapCentral-PO | `BAP_AGENTE=po`, `BAP_RECADOS_TOKEN=<token>` | conversa do Alexandre |
| BapCentral-GP | `BAP_AGENTE=gerente-projetos`, `BAP_RECADOS_TOKEN=<token>` | gerente e subagentes |

O token é fine-grained, só com "Contents: read and write" no `aloirr/bapcentral-recados`. Quem cria e cola é o Alexandre: ele nunca vai para arquivo, recado ou log.

## Recados
- Repositório `aloirr/bapcentral-recados`:
  - `recados/<destino>/R-AAAAMMDD-HHMMSS-<remetente>.md`;
  - `lidos/<agente>.txt`;
  - `recados/anexos/`.
- Destinos: os 12 agentes, `alexandre` e `todos`. Tipos: pedido, pergunta, resposta, aviso, bloqueio, entrega, revisao.
- Aberto = pedido, pergunta, bloqueio ou revisao sem resposta `encerra: true`.
- Na nuvem, recado e lido são gravados com `git` no clone do `aloirr/bapcentral-recados` anexado à sessão, com push direto no `main` (o proxy barra a gravação pela API). A CLI lê (`caixa`, `pendencias`, `ler`, `fio`); o modo git dela é a T-0007. Recado é imutável. O guardião barra recado em nome de outro (`de: alexandre` só pelo formulário de issue da conta do Alexandre ou por sessão com `BAP_AGENTE=alexandre`).

## Donos e guardiões
- `.coord/donos.json`: a primeira regra vence. `congelado` e `sem-dono` bloqueiam.
- `guarda-donos.mjs` (Edit/Write) e `guarda-bash.mjs` (Bash) identificam o agente:
  - subagente: pelo `agent_type`;
  - sessão principal: pela `BAP_AGENTE`, depois pelo branch `<agente>/T-nnnn`, depois pelo trailer.
