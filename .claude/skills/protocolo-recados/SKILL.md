---
name: protocolo-recados
description: Protocolo de recados e donos do time BAP Tools — como ler a caixa, enviar, responder, encerrar e checar donos de arquivos. Use sempre que precisar falar com outro agente, pedir algo fora dos seus caminhos ou entregar uma tarefa.
---

# Protocolo de recados (universal)

**Regra de ouro:** altere só os seus caminhos (`.coord/donos.json`). Para o resto, deixe recado. Recados são imutáveis e ficam no `aloirr/bapcentral-recados`.

| Quero... | Comando |
|---|---|
| Ver minha caixa | `node scripts/coord.mjs caixa <eu>` |
| Saber o dono de um arquivo | `node scripts/coord.mjs dono <caminho>` |
| Pedir algo | `node scripts/coord.mjs enviar --de <eu> --para <dono> --tipo pedido --tarefa T-nnnn --assunto "..." --corpo "Contexto \| O que preciso \| Pronto quando"` |
| Perguntar | `... --tipo pergunta ...` |
| Responder | `... --tipo resposta --responde-a <id> ...` |
| Responder e dar por resolvido | `... --tipo resposta --responde-a <id> --encerra ...` |
| Avisar todos (decisão, contrato) | `... --para todos --tipo aviso ...` |
| Sinalizar bloqueio | `... --tipo bloqueio ...` (o gerente recebe cópia automática) |
| Entregar tarefa | `... --para gerente-projetos --tipo entrega --tarefa T-nnnn ...` |
| Marcar informativo como lido | `node scripts/coord.mjs lido <eu> <id>` |
| Ler um recado / a conversa | `node scripts/coord.mjs ler <id>` · `node scripts/coord.mjs fio <id>` |
| Conferir se só mexi no que é meu | `node scripts/coord.mjs verificar <eu> --base origin/main` |

- O corpo com 3 partes separadas por `|` vira as seções Contexto / O que preciso / Pronto quando.
- Texto longo: escreva num arquivo temporário **fora do repositório** (ex.: `/tmp/recado.md`) e use `--arquivo`.
- Sem `BAP_RECADOS_TOKEN` no ambiente, o envio falha com o aviso: avise o Alexandre (pelo po) e não tente outro caminho.

**Boas práticas:**
- um assunto por recado;
- cite arquivos, funções públicas e regras (`RN-...`);
- diga o critério de pronto;
- responda rápido, mesmo que seja "recebido, entrego até o fim da tarefa".

**Antes de cada push:**
- `node scripts/coord.mjs verificar <eu> --base origin/main` sai 0;
- todo commit de `git log origin/main..HEAD` traz `Agente: <eu>`.
