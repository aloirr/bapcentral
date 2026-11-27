// Tira os PNG da simulação: node web/simular_png.mjs farol.html <prefixo>
// Gera <prefixo>-pc.png (1366 px) e <prefixo>-cel.png (390 px), deviceScaleFactor 2.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const require = createRequire('/opt/node-tools/node_modules/');
const { chromium } = require('playwright');

const [html, prefixo] = process.argv.slice(2);
if (!html || !prefixo) { console.error('uso: node simular_png.mjs farol.html prefixo'); process.exit(1); }
const b = await chromium.launch({ args: ['--lang=pt-BR'], env: { ...process.env, LANG: 'pt_BR.UTF-8', LANGUAGE: 'pt_BR' } });   // datas dd/mm/aaaa
for (const [nome, largura, altura] of [['pc', 1366, 900], ['cel', 390, 844]]) {
  const ctx = await b.newContext({ viewport: { width: largura, height: altura }, deviceScaleFactor: 2, locale: 'pt-BR' });
  const p = await ctx.newPage();
  await p.goto(pathToFileURL(resolve(html)).href);
  const larg = await p.evaluate(() => document.documentElement.scrollWidth);
  console.log(`largura ${nome}: ${larg} px (tela ${largura})`);
  if (larg > largura) { console.error('FALHA: a página passa da largura da tela'); process.exitCode = 1; }
  await p.screenshot({ path: `${prefixo}-${nome}.png`, fullPage: false });
  await p.screenshot({ path: `${prefixo}-${nome}-inteira.png`, fullPage: true });
  await ctx.close();
}
await b.close();
