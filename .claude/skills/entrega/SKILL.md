---
name: entrega
description: Fecha um lote do BAP Tools (testes, pendências, revisão, docs e recado de entrega).
disable-model-invocation: true
---

1. `python -m compileall -q .` e os testes do lote. Se falhar, pare e mostre o dono.
2. `node scripts/coord.mjs pendencias` sem nada aberto do lote.
3. `node scripts/coord.mjs verificar --por-dono` sem violação.
4. Parecer do `revisor-codigo` no head SHA e relatório do `testes`.
5. Atualize o quadro, `docs/backlog.md` e `docs/status/AAAA-MM-DD.md`.
6. Recado `entrega` ao `po` (cc `alexandre`) com:
   - o roteiro de demonstração em 5 a 8 passos;
   - as premissas;
   - o que o Alexandre precisa autorizar ("instale" no PC, merge de governança).
