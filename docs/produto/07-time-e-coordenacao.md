# 07 — Time e coordenação

## Fluxo
1. O **Alexandre** fala com o **po** (sessão BapCentral-PO), ou escreve pelo formulário de issue "Recado" do `aloirr/bapcentral-recados`.
2. O **po** grava o recado ao **gerente-projetos**, com o texto literal, a especificação e os critérios.
3. O **gerente-projetos** (sessão fixa BapCentral-GP, ronda a cada 15–20 min):
   - cria a tarefa e delega aos agentes (subagentes);
   - cobra e valida com o `testes` e o `revisor-codigo`;
   - faz o PR e o merge.
4. A entrega volta ao **po**, que explica ao Alexandre e pede o "instale" quando vai para a produção (T-0003).

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
- Só a CLI grava. Recado é imutável. O guardião barra recado em nome de outro (`de: alexandre` só pelo formulário de issue da conta do Alexandre ou por sessão com `BAP_AGENTE=alexandre`).

## Donos e guardiões
- `.coord/donos.json`: a primeira regra vence. `congelado` e `sem-dono` bloqueiam.
- `guarda-donos.mjs` (Edit/Write) e `guarda-bash.mjs` (Bash) identificam o agente:
  - subagente: pelo `agent_type`;
  - sessão principal: pela `BAP_AGENTE`, depois pelo branch `<agente>/T-nnnn`, depois pelo trailer.
