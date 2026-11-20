---
name: feature
description: Conduz uma funcionalidade do BAP Tools de ponta a ponta (do recado do po ao PR pronto).
argument-hint: <recado R-... ou descrição>
disable-model-invocation: true
---

Funcionalidade: $ARGUMENTS

1. Crie a tarefa `T-nnnn` pelo modelo, com critérios verificáveis, e mande o plano ao `po`. Se o pedido diz "simule", **aguarde o ok** antes do PR final.
2. Desenho com o `engenheiro-software` (e com o `engenheiro-dados`, se mexe em dado).
3. Implementação nos módulos donos dos arquivos: máximo 3 em paralelo.
4. `testes` (critérios, valor × regra, smokes) → `revisor-codigo` (🔴 volta ao dono).
5. `node scripts/coord.mjs pendencias` e `verificar --por-dono` limpos.
6. PR por dono, merge com o CI verde, quadro e backlog atualizados.
7. Recado `entrega` ao `po` com "como testar em 5 passos" e o que falta para instalar no PC (T-0003).
