// T-0011 — Os 3 furos antigos do guardião (parecer do revisor-codigo no PR #4, head 776851d), um teste por furo.
// Rodar: node --test .claude/hooks/guarda-furos.test.mjs
//  1. git log/diff/show --output=<arquivo> grava arquivo (o git de leitura passava);
//  2. hard link para arquivo do código (ln sem -s, cp -l, link) seguido de ">" no link (hoje só aviso no PostToolUse);
//  3. env -C <repo> git commit e xargs -I{} git -C {} commit passavam pela trava do índice (v6).
// Regra: na dúvida, barra.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { analisarComando, saidasDoGit } from './guarda-bash-lib.mjs';
import { classificarComando, comandosDeIndice, motivosIndiceDeRecados, motivosRecadoFalso } from './guarda-merge-lib.mjs';
import { tokenizar, comandosSimples } from './guarda-bash-lib.mjs';
import { carregarDonos } from '../../scripts/coord-lib.mjs';

const RAIZ_REAL = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const REGRAS = carregarDonos(RAIZ_REAL);
const RAIZ = '/repo';
const ARQUIVOS = ['relatorios_nucleo.py', 'web/app/main.py', 'web/app/painel.py'];
const amb = {
  existe: (abs) => ARQUIVOS.some((f) => `${RAIZ}/${f}` === abs) || abs === `${RAIZ}/web` || abs === RAIZ,
  ehDiretorio: (abs) => abs === `${RAIZ}/web` || abs === `${RAIZ}/web/app` || abs === RAIZ || abs === '/tmp',
  sujos: () => [],
  rastreadosSob: (rel) => ARQUIVOS.filter((f) => rel === '' || f === rel || f.startsWith(`${rel}/`)),
  ler: () => null,
};
const analisar = (comando, agente = 'modulo-web') =>
  analisarComando({ comando, agente, cwd: RAIZ, raiz: RAIZ, regras: REGRAS, amb });
const relsDe = (r) => r.violacoes.map((v) => v.rel);

// ───────────────────────── furo 1: git --output ─────────────────────────

test('T-0011 furo 1: git log/diff/show com --output em arquivo de outro dono é barrado', () => {
  for (const c of [
    'git log -p --output=relatorios_nucleo.py',
    'git diff --output relatorios_nucleo.py',
    'git show HEAD --outp=relatorios_nucleo.py',
    'git -C /repo diff --out=relatorios_nucleo.py HEAD~1',
    'git diff-tree -p HEAD --output=./relatorios_nucleo.py',
    'git fetch -q && git log --output=relatorios_nucleo.py',
  ]) {
    const r = analisar(c);
    assert.deepEqual(relsDe(r), ['relatorios_nucleo.py'], c);
    assert.equal(r.soLeitura, false, c);
  }
  // pasta de saída (format-patch --output-directory) em pasta de outro dono
  assert.ok(analisar('git format-patch -3 --output-directory web/app', 'modulo-farois').violacoes.length > 0);
});

test('T-0011 furo 1: o que não grava continua passando (fora do repo, --output-indicator, depois do --)', () => {
  const fora = analisar('git log -p --output=/tmp/log.txt');
  assert.deepEqual(fora.violacoes, []);
  assert.equal(fora.soLeitura, false, 'grava arquivo: não é só leitura (o PostToolUse confere)');
  for (const c of ['git diff --output-indicator-new=+ --output-indicator-old=-', 'git log -- --output=relatorios_nucleo.py', 'git log --oneline -5', 'git diff HEAD~1 -- web']) {
    const r = analisar(c);
    assert.deepEqual(r.violacoes, [], c);
    assert.equal(r.soLeitura, true, c);
  }
  // o próprio dono pode
  assert.deepEqual(analisar('git diff --output=relatorios_nucleo.py', 'modulo-farois').violacoes, []);
  assert.deepEqual(saidasDoGit([{ valor: '--output-indicator-context=x', incerto: false }]), []);
});

test('T-0011 furo 1: recado do Alexandre por git --output é escrita (bloqueio de recado falso)', () => {
  const alvo = '.coord/recados/gerente-projetos/R-20261123-120000-alexandre.md';
  const [cmd] = comandosSimples(tokenizar(`git log -1 --format=%B --output=${alvo}`));
  const c = classificarComando(cmd.palavras);
  assert.equal(c.tipo, 'escrita');
  assert.deepEqual(c.alvos.map((a) => a.valor), [alvo]);
  assert.ok(motivosRecadoFalso({ comando: `git log -1 --format=%B --output=${alvo}`, agente: 'gerente-projetos', cwd: RAIZ }).length > 0);
});

// ───────────────────────── furo 2: hard link ─────────────────────────

test('T-0011 furo 2: hard link para arquivo de outro dono é barrado já no ln (ln, ln -t, cp -l, cp --link, link)', () => {
  for (const c of [
    'ln relatorios_nucleo.py /tmp/h && echo x > /tmp/h',
    'ln -f relatorios_nucleo.py /tmp/h',
    'ln -t /tmp relatorios_nucleo.py',
    'cp -l relatorios_nucleo.py /tmp/h',
    'cp -al relatorios_nucleo.py /tmp/h',
    'cp --link relatorios_nucleo.py /tmp/h',
    'link relatorios_nucleo.py /tmp/h',
  ]) assert.deepEqual(relsDe(analisar(c)), ['relatorios_nucleo.py'], c);
  // pasta inteira (cp -al web /tmp/w) pelo dono de outra pasta
  assert.deepEqual(relsDe(analisar('cp -al web /tmp/w', 'modulo-farois')).sort(), ['web/app/main.py', 'web/app/painel.py']);
});

test('T-0011 furo 2: hard link do próprio arquivo e cópia comum continuam passando', () => {
  assert.deepEqual(analisar('ln relatorios_nucleo.py /tmp/h', 'modulo-farois').violacoes, []);
  assert.deepEqual(analisar('cp relatorios_nucleo.py /tmp/copia.py').violacoes, []);
  assert.deepEqual(analisar('cp -a web/app /tmp/w', 'modulo-farois').violacoes, []);
});

test('T-0011 furo 2: hard link de recado do Alexandre é escrita (bloqueio de recado falso)', () => {
  const rec = '.coord/recados/gerente-projetos/R-20261123-120000-alexandre.md';
  for (const c of [`ln ${rec} /tmp/h`, `cp -l ${rec} /tmp/h`]) {
    const [cmd] = comandosSimples(tokenizar(c));
    const r = classificarComando(cmd.palavras);
    assert.equal(r.tipo, 'escrita', c);
    assert.ok(r.alvos.some((a) => a.valor === rec), c);
    assert.ok(motivosRecadoFalso({ comando: c, agente: 'gerente-projetos', cwd: RAIZ }).length > 0, c);
  }
});

// ───────────────────────── furo 3: git embrulhado na trava do índice ─────────────────────────

const RECADO_AL = '.coord/recados/gerente-projetos/R-20261123-120000-alexandre.md';
const doAlexandre = (rel) => /alexandre\.md$/.test(rel);
const ind = (comando, status, tocados = []) =>
  motivosIndiceDeRecados({ comando, status, tocados, ehDoAlexandre: doAlexandre, cwd: RAIZ, raiz: RAIZ });

test('T-0011 furo 3: env -C, xargs, sudo e nohup em volta do git não escapam da trava do índice', () => {
  const alterado = [{ xy: 'AM', rel: RECADO_AL }];
  for (const c of [
    'env -C /repo git commit -m x',
    'env --chdir=/repo git commit -qm x',
    'echo /repo | xargs -I{} git -C {} commit -m x',
    'xargs -0 git add < lista.txt && git commit -m x',
    'sudo -u bap git commit -m x',
    'nohup git -C /repo commit -m x',
    'env -u GIT_DIR git commit -m x',
  ]) assert.ok(ind(c, alterado).length > 0, c);
  // tocado nesta sessão: add embrulhado também barra
  assert.ok(ind('echo /repo | xargs -I{} git -C {} add -A', [{ xy: '??', rel: RECADO_AL }], [RECADO_AL]).length > 0);
  assert.deepEqual(comandosDeIndice('env -C /repo git commit -m x').map((c) => [c.sub, c.outraPasta]), [['commit', true]]);
  assert.deepEqual(comandosDeIndice('echo . | xargs -I{} git -C {} add -A').map((c) => [c.sub, c.outraPasta]), [['add', true]]);
});

test('T-0011 furo 3: recado do Alexandre intacto continua passando, mesmo com o git embrulhado', () => {
  const intacto = [{ xy: 'A ', rel: RECADO_AL }];
  for (const c of ['env -C /repo git commit -m x', 'echo /repo | xargs -I{} git -C {} commit -m x'])
    assert.deepEqual(ind(c, intacto), [], c);
  assert.deepEqual(comandosDeIndice('env -C /repo git log -1'), []);
});
