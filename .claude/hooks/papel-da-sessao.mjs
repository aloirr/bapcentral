// SessionStart: diz à sessão principal QUEM ela é, pela variável BAP_AGENTE do ambiente do claude.ai/code.
//   Ambiente "BapCentral-GP" → BAP_AGENTE=gerente-projetos · ambiente "BapCentral-PO" → BAP_AGENTE=po.
// O texto impresso entra no contexto da sessão (hook SessionStart). Sem a variável, a sessão fica sem papel e os
// guardiões a tratam como restrita (não altera nada no repositório). Subagentes não passam por aqui.
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { RAIZ, AGENTES } from '../../scripts/coord-lib.mjs';

const agente = String(process.env.BAP_AGENTE || '').trim().toLowerCase();
const linhas = [];
if (!agente) {
  linhas.push(
    'PAPEL DA SESSÃO: nenhum (a variável BAP_AGENTE não está definida neste ambiente).',
    'Os guardiões tratam esta sessão como restrita: ela não altera arquivos do repositório nem envia recado.',
    'Se você é o Alexandre: abra a sessão no ambiente "BapCentral-PO" (para falar com o PO) ou "BapCentral-GP" (gerente).',
  );
} else if (agente === 'alexandre') {
  linhas.push('PAPEL DA SESSÃO: alexandre (dono do produto, sessão manual). Sem papel de agente; o guardião libera governança.');
} else if (!AGENTES.includes(agente)) {
  linhas.push(`PAPEL DA SESSÃO: "${agente}" não é agente do time (${AGENTES.join(', ')}). Corrija BAP_AGENTE no ambiente.`);
} else {
  const arq = join(RAIZ, '.claude', 'agents', `${agente}.md`);
  const txt = existsSync(arq) ? readFileSync(arq, 'utf8') : '';
  const corpo = txt.replace(/^---[\s\S]*?\n---\n/, '').trim();
  const inicial = (txt.match(/^initialPrompt:\s*"(.*)"\s*$/m) || [])[1] || '';
  linhas.push(
    `PAPEL DA SESSÃO: você é o agente **${agente}** do time BAP Tools (variável BAP_AGENTE).`,
    `Siga integralmente as instruções abaixo (cópia de .claude/agents/${agente}.md). Os guardiões te identificam como ${agente}.`,
    inicial ? `Primeira coisa a fazer: ${inicial}` : '',
    '',
    corpo,
  );
}
process.stdout.write(linhas.filter((l) => l !== null).join('\n') + '\n');
