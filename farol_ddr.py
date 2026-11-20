# -*- coding: utf-8 -*-
"""
FAROL DDR - a rotina diaria do time, com pontuacao.

Gera o arquivo do MES (RELATORIOS\\FAROL_DDR_BAP_AAAA-MM.xlsx):

    Leia-me ..... como preencher e como a nota e calculada
    Painel ...... a nota de cada pessoa, sozinha (formulas)
    Equipe ...... quem esta no Farol, cargo e papel
    Rotina ...... TODAS as atividades, com horario, prioridade, frequencia
                  e a ferramenta BAP que apoia cada uma
    Feriados .... os dias que nao contam
    uma aba por pessoa, com as linhas do mes ja montadas

O QUE MUDOU EM RELACAO AOS ARQUIVOS ANTIGOS
  * um arquivo so, mesma estrutura para todos - antes cada pessoa tinha um
    arquivo com abas de nome diferente, e o consolidado nao fechava;
  * o mes nasce sozinho a partir da Rotina, respeitando a FREQUENCIA: tarefa
    de terca e quinta aparece so terca e quinta, tarefa sob demanda nao
    aparece (antes tudo aparecia todo dia e a semanal contava como falha);
  * "Pontos Ganhos" e formula em todas as linhas (nos arquivos da Juliana e
    da Mayara era um 0 digitado - marcar SIM nao somava nada);
  * o Painel mede por PONTOS (Alta 5, Media 3, Baixa 1), nao por quantidade
    de tarefas - e para isso que a prioridade existe;
  * ausencia justificada sai da conta, em vez de virar nota baixa;
  * linha marcada como "nao preenchida" aparece separada de "NAO feita".

COMO GERAR O MES SEGUINTE
    python farol_ddr.py 2026-11
  Le a Rotina, a Equipe e os Feriados do arquivo de Farol MAIS RECENTE da
  pasta - entao quem muda a rotina muda la, na aba Rotina, e o mes seguinte
  ja nasce com ela. Arquivo de mes que ja existe NUNCA e sobrescrito: ele
  guarda o que o time marcou.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# (29/10, Alexandre: "o minimo de pasta possivel") o cache do Python fica fora
# da pasta do BAP (no %LOCALAPPDATA%\BAP_TOOLS\cache de cada maquina): sem
# __pycache__ na pasta e sem sincronizar cache pelo OneDrive.
try:
    import os as _os_c
    sys.pycache_prefix = sys.pycache_prefix or _os_c.path.join(
        _os_c.environ.get("LOCALAPPDATA") or _os_c.path.join(
            _os_c.path.dirname(_os_c.path.abspath(__file__)), "SISTEMA BAP"),
        *(("BAP_TOOLS", "cache") if _os_c.environ.get("LOCALAPPDATA")
          else ("cache",)))
except Exception:                                       # noqa: BLE001
    pass
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

AQUI = Path(__file__).resolve().parent
PASTA_RELATORIOS = AQUI / "RELATORIOS"
PREFIXO = "FAROL_DDR_BAP_"

PONTOS = {"Alta": 5, "Média": 3, "Baixa": 1}
# OUT/2026: o status virou ENTREGUE / ENTREGUE PARCIAL / NAO ENTREGUE.
# Parcial vale METADE dos pontos; PARCIAL e NAO ENTREGUE pedem o motivo.
# Arquivo antigo marcado com SIM/NAO continua valendo (SIM = ENTREGUE).
ENTREGUE, PARCIAL, NAO_ENTREGUE = "ENTREGUE", "ENTREGUE PARCIAL", "NÃO ENTREGUE"
STATUS = [ENTREGUE, PARCIAL, NAO_ENTREGUE]
STATUS_NAO = (NAO_ENTREGUE, "NÃO", "NAO")


def pontos_do_status(status, pontos) -> float:
    """Os pontos ganhos por uma marcacao (a mesma conta da coluna H)."""
    st = str(status or "").strip().upper()
    if st in (ENTREGUE, "SIM"):
        return pontos
    if st == PARCIAL:
        return pontos / 2.0
    return 0.0


def _formula_ganhos(n, extra=False):
    f = f"N(F{n})" if extra else f"F{n}"
    return (f'=IF(OR(G{n}="{ENTREGUE}",G{n}="SIM"),{f},'
            f'IF(G{n}="{PARCIAL}",{f}/2,0))')
AUSENCIA = "Ausência justificada"
MOTIVOS = [
    "Indisponibilidade de Sistema", "Falta de Dados/Insumos",
    "Demanda Urgente Ad Hoc", "Sobrecarga Operacional", "Falha de Processo",
    "Priorização Demanda Diretoria", "Prioridade Substituída", AUSENCIA,
]
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
QUANDO_VALIDOS = ("DIÁRIA", "SEG..SEX (ex.: TER,QUI)", "QUINZENAL SEX",
                  "MENSAL INÍCIO", "MENSAL FIM", "SOB DEMANDA")
LINHAS_EXTRAS = 15          # linhas em branco no fim de cada aba
MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
FAIXAS = [(0.95, "Excelência operacional"),
          (0.90, "Focar na excelência operacional"),
          (0.0, "Focar nas atividades de alta prioridade")]

NOVA = "Estefanie Pacheco"    # assistente de pos-venda e logistica (out/2026)

# ---------------------------------------------------------------------------
# A EQUIPE E A ROTINA DE PARTIDA (out/2026)
# ---------------------------------------------------------------------------
# Usadas so quando ainda nao existe nenhum Farol na pasta. Dali em diante
# manda a aba Rotina do arquivo mais recente.
#   (colaborador, cargo, papel, no Farol?)
EQUIPE_INICIAL = [
    ("Juliana Almeida", "Assistente de Vendas", "Pré-venda e Faturamento", "SIM"),
    ("Mayara Santos", "Assistente de Vendas", "Vendas e CRM", "SIM"),
    (NOVA, "Assistente de Vendas", "Pós-venda e Logística", "SIM"),
    ("Leandro Nunes", "Analista Comercial Pleno", "Análises e Faróis", "SIM"),
    ("Enricson Oliveira", "VDE Interno AP/RR", "Venda interna", "SIM"),
    ("Allaiza Menezes", "Analista de Trade Marketing", "Trade e Marketing", "SIM"),
    ("Supervisor Administrativo (em aberto)", "Supervisor Administrativo",
     "Gestão do administrativo", "NÃO"),
    ("Analista Administrativo Pleno (em aberto)", "Analista Administrativo Pleno",
     "Controles e indicadores", "NÃO"),
]

OP = "ACOMPANHAMENTO_POS_VENDA"
# (area, colaborador, horario, atividade, prioridade, quando, ferramenta,
#  entregavel, mudanca)
ROTINA_INICIAL = [
    # ---- JULIANA: pre-venda e faturamento - do pedido ate a nota --------
    # (out/2026: a integracao do Maxima foi para a Mayara; meta, rota e
    #  pre-venda ativa tambem - a Juliana fica com o pedido e a nota)
    ("Administrativo BAP", "Juliana Almeida", "07:30 - 08:00",
     "Abrir a fila do dia: pedidos em aberto atrasados, crédito a resolver e itens faltantes",
     "Alta", "DIÁRIA", "BAP Central › Pré-venda › Pedidos em aberto",
     "Fila do dia definida", "Nova (a integração do Máxima foi para a Mayara)"),
    ("Administrativo BAP", "Juliana Almeida", "08:00 - 08:30",
     "Conferir pedidos pendentes no Protheus (MATA410): cliente, frete, condição e preço",
     "Alta", "DIÁRIA", "Protheus + BAP Central › Pedidos em aberto",
     "Fila de pedidos conferida", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "08:30 - 09:15",
     "Liberar pedidos (MATA440) e tratar bloqueios de crédito e estoque; à vista só com comprovante conferido",
     "Alta", "DIÁRIA", "Protheus + Pedidos em aberto (CRÉDITO)", "Pedidos liberados",
     "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "09:15 - 10:00",
     "1ª rodada de faturamento + transmissão e monitoramento da NF-e (SEFAZ/TSS)",
     "Alta", "DIÁRIA", "Protheus", "NFs autorizadas", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "10:00 - 10:30",
     "Enviar NF e boleto ao cliente — a partir daqui o pedido é do pós-venda",
     "Alta", "DIÁRIA", "E-mail", "NF + boleto enviados", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "10:30 - 11:30",
     "Orçamentos, cotações e autorização de preço/desconto dentro da alçada",
     "Alta", "DIÁRIA", "Protheus + Pedidos em aberto (DESC. %)",
     "Orçamentos respondidos", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "13:00 - 13:45",
     "2ª rodada de faturamento — pedidos liberados pela manhã",
     "Alta", "DIÁRIA", "Protheus", "NFs geradas", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "13:45 - 14:15",
     "Itens faltantes: combinar com o vendedor substituir, aguardar ou cortar o item",
     "Alta", "DIÁRIA", "BAP Central › Pedidos em aberto (ITENS FALTANTES)",
     "Pedidos parciais resolvidos", "Nova"),
    ("Administrativo BAP", "Juliana Almeida", "14:15 - 14:45",
     "Pedidos excluídos do dia: entender o motivo com o vendedor e recuperar o que der",
     "Média", "DIÁRIA", "BAP Central › Pedidos excluídos",
     "Exclusões tratadas", "Nova"),
    ("Administrativo BAP", "Juliana Almeida", "14:45 - 15:30",
     "Atender por telefone os clientes das zonas sem vendedor",
     "Alta", "DIÁRIA", "BAP Central › Vendas e CRM › Base e oportunidades (SEM VENDEDOR)",
     "Clientes atendidos", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "15:30 - 16:00",
     "3ª rodada de faturamento — urgentes e complementares",
     "Alta", "DIÁRIA", "Protheus", "NFs geradas", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "16:00 - 16:30",
     "SLA do pedido: faturados com atraso e parciais do dia — avisar o supervisor",
     "Média", "DIÁRIA", "BAP Central › Painel de indicadores", "Recado enviado",
     "Nova"),
    ("Administrativo BAP", "Juliana Almeida", "16:30 - 17:15",
     "Notas faturadas e paradas: conferir e passar ao pós-venda",
     "Média", "DIÁRIA", "BAP Central › Pedidos faturados (PARADO)",
     "Notas encaminhadas", "Nova"),
    ("Administrativo BAP", "Juliana Almeida", "17:15 - 17:30",
     "Fechamento do dia — Farol DDR", "Média", "DIÁRIA", "Farol DDR",
     "Farol preenchido", "Mantida"),
    ("Administrativo BAP", "Juliana Almeida", "Segunda (no fechamento)",
     "Enviar o painel da semana (SLA, % no prazo, % parcial, base com compra) aos supervisores",
     "Média", "SEG", "BAP Central › Painel de indicadores (Exportar PDF)",
     "Painel enviado", "Nova"),

    # ---- MAYARA: vendas e CRM (out/2026) ----------------------------------
    # remuneracao, forca de venda (Maxima), Protheus, base de clientes e
    # suporte ao time. A devolucao e a garantia foram para a Estefanie.
    ("Administrativo BAP", "Mayara Santos", "07:30 - 08:00",
     "Integração diária do Máxima: rodar, validar e abrir chamado do que não integrou (preço, desconto, acréscimo)",
     "Alta", "DIÁRIA", "Máxima / Protheus", "Pedidos do Máxima no Protheus",
     "Veio da Juliana"),
    ("Administrativo BAP", "Mayara Santos", "08:00 - 08:45",
     "Força de venda no Máxima: vendedor, carteira, tabela de preço e bloqueios iguais ao Planner",
     "Alta", "DIÁRIA", "Máxima + BAP Central › Resumo do Planner",
     "Máxima conferido", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "08:45 - 09:30",
     "Cadastro e atualização de clientes no Protheus (dados, contato, limite) e conferir os novos na base",
     "Alta", "DIÁRIA", "Protheus + BAP Central › Base e oportunidades",
     "Cadastros em dia", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "09:30 - 10:15",
     "Meta do dia: vendedores atrás do esperado, com o necessário por dia, aos supervisores",
     "Alta", "DIÁRIA", "BAP Central › Meta e RV", "Recado enviado",
     "Veio da Juliana"),
    ("Administrativo BAP", "Mayara Santos", "10:15 - 11:30",
     "CRM ativo: ligar para clientes com limite e sem compra no mês; registrar no CRM",
     "Alta", "DIÁRIA", "BAP Central › Base e oportunidades (Clientes) + CRM",
     "Contatos registrados", "Veio da Juliana"),
    ("Administrativo BAP", "Mayara Santos", "13:00 - 13:45",
     "Suporte ao time de vendas: Máxima, Protheus, acessos e pedido que não subiu",
     "Alta", "DIÁRIA", "Máxima / Protheus / CRM", "Chamados resolvidos", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "13:45 - 14:30",
     "Rota de amanhã: pendências e oportunidades dos clientes que o vendedor vai visitar",
     "Média", "DIÁRIA", "BAP Central › Resumo do Planner + Base e oportunidades",
     "Vendedores avisados", "Veio da Juliana"),
    ("Administrativo BAP", "Mayara Santos", "14:30 - 15:15",
     "Base de clientes: nunca compraram e inativos por vendedor — lista ao supervisor",
     "Média", "DIÁRIA", "BAP Central › Base e oportunidades", "Lista enviada",
     "Nova"),
    ("Administrativo BAP", "Mayara Santos", "15:15 - 16:00",
     "Remuneração variável: conferir a RV parcial por vendedor e responder dúvidas",
     "Média", "DIÁRIA", "BAP Central › Meta e RV", "RV conferida", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "16:00 - 16:45",
     "Atualizar o CRM e os chamados do time comercial",
     "Média", "DIÁRIA", "CRM", "CRM atualizado", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "16:45 - 17:15",
     "Indicadores executivos: conferir a parcial do mês e preparar o dia seguinte",
     "Média", "DIÁRIA", "BAP Central › Indicadores executivos",
     "Parcial conferida", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "17:15 - 17:30",
     "Fechamento do dia — Farol DDR", "Média", "DIÁRIA", "Farol DDR",
     "Farol preenchido", "Mantida"),
    ("Administrativo BAP", "Mayara Santos", "Sexta (no fechamento)",
     "Relatório da semana: meta, positivação e RV parcial por vendedor e supervisor",
     "Média", "SEX", "BAP Central › Meta e RV (Exportar PDF)",
     "Relatório enviado ao gerente", "Nova"),
    ("Administrativo BAP", "Mayara Santos", "Último dia útil",
     "Fechamento da RV do mês: conferir com o Analista e enviar ao RH",
     "Alta", "MENSAL FIM", "BAP Central › Meta e RV (Exportar Excel)",
     "RV fechada", "Nova"),

    # ---- ESTEFANIE: pos-venda e logistica - da nota ao canhoto, com a
    #      devolucao e a garantia (vieram da Mayara em out/2026) ------------
    ("Administrativo BAP", NOVA, "07:30 - 08:00",
     "Entregas: notas novas no acompanhamento e as entregas atrasadas",
     "Alta", "DIÁRIA", f"BAP Central › Entregas + {OP} › ENTREGAS",
     "Fila do dia definida", "Mantida"),
    ("Administrativo BAP", NOVA, "08:00 - 08:30",
     "Atualizar a SOLICITACAO_BAP depois da rodada das 08h: abrir solicitações e encaminhar",
     "Alta", "DIÁRIA", "BAP Tools › SOLICITACAO_BAP", "Solicitações abertas",
     "Mantida"),
    ("Administrativo BAP", NOVA, "08:30 - 09:15",
     "Enviar as NFs do dia aos CDs/filiais e programar coletas com as transportadoras",
     "Alta", "DIÁRIA", f"E-mail + {OP} › ENTREGAS (EXPEDIDA)",
     "NFs enviadas e coletas programadas", "Mantida"),
    ("Administrativo BAP", NOVA, "09:15 - 10:00",
     "Acompanhar as entregas por CD/filial: registrar EXPEDIDA / ENTREGUE e o canhoto",
     "Alta", "DIÁRIA", f"{OP} › ENTREGAS", "Situação das entregas atualizada",
     "Mantida"),
    ("Administrativo BAP", NOVA, "10:00 - 10:45",
     "Devoluções: classificar e encaminhar com MOTIVO e NF de origem; pedir a autorização de alçada",
     "Alta", "DIÁRIA", f"BAP Central › Devoluções + {OP} › DEVOLUÇÕES",
     "Devoluções encaminhadas", "Veio da Mayara"),
    ("Administrativo BAP", NOVA, "10:45 - 11:30",
     "Retorno de venda no Protheus (MATA103) e NF-e/SEFAZ das devoluções; rejeição tratada no dia",
     "Alta", "DIÁRIA", "Protheus / TSS", "NF de devolução autorizada",
     "Veio da Mayara"),
    ("Administrativo BAP", NOVA, "13:00 - 13:45",
     "Garantias: receber, analisar (NF, prazo, foto/laudo), registrar, enviar ao fornecedor e cobrar as paradas",
     "Alta", "DIÁRIA", f"BAP Central › Garantias + {OP} › GARANTIAS",
     "Garantias registradas e cobradas", "Veio da Mayara"),
    ("Administrativo BAP", NOVA, "13:45 - 14:15",
     "Ocorrências de entrega (avaria, falta, recusa): registrar e tratar com a transportadora",
     "Alta", "DIÁRIA", f"{OP} › ENTREGAS (OCORRÊNCIA)", "Ocorrências registradas",
     "Mantida"),
    ("Administrativo BAP", NOVA, "14:15 - 15:00",
     "SOLICITACAO_BAP depois da rodada das 14h, CSVs e protocolos de separação/reversa",
     "Alta", "DIÁRIA", "BAP Tools › SOLICITACAO_BAP",
     "Solicitações abertas + CSVs importados", "Mantida"),
    ("Administrativo BAP", NOVA, "15:00 - 15:30",
     "Baixas, abatimentos, RA e reembolsos com o Financeiro; evidências para auditoria",
     "Alta", "DIÁRIA", f"Protheus + {OP} › DEVOLUÇÕES (crédito)",
     "Pendências financeiras atualizadas", "Veio da Mayara"),
    ("Administrativo BAP", NOVA, "15:30 - 16:15",
     "Atender supervisores e vendedores: pedido, entrega, boleto e pendência; registrar no CRM",
     "Alta", "DIÁRIA", "BAP Central › Pedidos faturados + CRM",
     "Solicitações respondidas", "Mantida"),
    ("Administrativo BAP", NOVA, "16:15 - 17:15",
     "Fretes (CT-e e faturas) e giro: curva A parada e ruptura por filial ao comercial",
     "Média", "DIÁRIA", "BAP Central › Fretes + Giro dos produtos",
     "Fretes conferidos e giro enviado", "Nova"),
    ("Administrativo BAP", NOVA, "17:15 - 17:30",
     "Fechamento do dia — Farol DDR", "Média", "DIÁRIA", "Farol DDR",
     "Farol preenchido", "Mantida"),
    ("Administrativo BAP", NOVA, "Sexta (no bloco de atendimento)",
     "Ligar para 10 clientes que receberam na semana: chegou certo e no prazo?",
     "Média", "SEX", f"{OP} › ENTREGAS (ENTREGUE) + CRM", "Pesquisa registrada",
     "Mantida"),
    ("Administrativo BAP", NOVA, "Sexta (no fechamento)",
     "Relatório da semana: entregas no prazo, devoluções por motivo e vendedor, garantias por fornecedor",
     "Média", "SEX", "BAP Central › Entregas + Devoluções + Garantias (Exportar PDF)",
     "Relatório enviado ao gerente", "Veio da Mayara"),
    ("Administrativo BAP", NOVA, "Quando houver",
     "Cadastro/atualização de transportadora (MATA050), vinculada como fornecedor",
     "Média", "SOB DEMANDA", "Protheus", "Cadastro atualizado", "Mantida"),

    # ---- LEANDRO: mantida ------------------------------------------------
    ("Administrativo BAP", "Leandro Nunes", "07:30 - 08:00",
     "Validação diária do resultado (Power BI vs. Mapa de Vendas PMZ)",
     "Alta", "DIÁRIA", "Power BI", "Resultado validado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "08:00 - 08:15",
     "Acompanhamento e cobrança dos status dos chamados em aberto pelo time comercial",
     "Alta", "DIÁRIA", "Chamados", "Chamados cobrados", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "08:30 - 09:00",
     "Farol de pesquisa de mercado (preço e concorrência) à Liderança Comercial",
     "Alta", "DIÁRIA", "Power BI / e-mail", "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "09:00 - 09:30",
     "Farol de Ruptura de estoque à Liderança Comercial",
     "Alta", "DIÁRIA", "BAP Central › Giro dos produtos (RUPTURA)",
     "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "09:30 - 10:00",
     "Farol de Performance (Visita e Produtividade) dos Key Accounts",
     "Alta", "DIÁRIA", "BAP Central › Meta e RV",
     "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "10:00 - 10:15",
     "Farol de Performance das Contas Especiais", "Alta", "DIÁRIA",
     "Power BI", "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "10:15 - 11:30",
     "Execução das atividades operacionais designadas no Microsoft Planner",
     "Alta", "DIÁRIA", "Microsoft Planner", "Tarefas concluídas", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "13:30 - 14:00",
     "Farol de Performance de Categorias e Famílias",
     "Alta", "DIÁRIA", "BAP Central › Meta e RV (Por família da peça)",
     "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "14:00 - 14:30",
     "Farol das Top Contas com perda de performance (queda x ano anterior)",
     "Alta", "DIÁRIA", "Power BI", "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "14:30 - 15:00",
     "Farol das Oficinas e Auto Centers com perda de performance",
     "Alta", "DIÁRIA", "BAP Central › Base e oportunidades (Por família)",
     "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "15:00 - 15:30",
     "Farol de Metas da Diretoria para o Diretor Comercial",
     "Alta", "DIÁRIA", "BAP Central › Indicadores executivos",
     "Farol enviado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "15:30 - 16:00",
     "Daily — Farol DDR com o gestor", "Média", "DIÁRIA", "Farol DDR",
     "Daily realizada", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "16:00 - 17:15",
     "Apoio e manutenção dos acompanhamentos e testes do CRM",
     "Média", "DIÁRIA", "CRM", "CRM acompanhado", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "17:15 - 17:30",
     "Fechamento do dia — Farol DDR", "Média", "DIÁRIA", "Farol DDR",
     "Farol preenchido", "Mantida"),
    ("Administrativo BAP", "Leandro Nunes", "Segunda (no bloco de análises)",
     "Montar a sugestão de kits da semana e mandar aos supervisores",
     "Média", "SEG", "BAP Analista › Oportunidades e kits › 6. Sugestão de kits (PDF)",
     "Kits enviados", "Veio da Juliana (kits são parâmetro do Analista)"),
    ("Administrativo BAP", "Leandro Nunes", "Quando mudar",
     "Cadastros: zonas, vendedor por zona e segmento, metas, faixas de RV e parâmetros",
     "Alta", "SOB DEMANDA", "BAP Analista", "Cadastros atualizados",
     "Nova (só o Analista cadastra)"),

    # ---- ENRICSON: mantida, com o destino certo de cada pendencia --------
    ("Administrativo BAP", "Enricson Oliveira", "07:30 - 08:00",
     "Revisar carteira AP/RR: pendências, pedidos em aberto e clientes sem compra",
     "Alta", "DIÁRIA", "BAP Central › Base e oportunidades",
     "Plano de ligações do dia", "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "08:00 - 09:30",
     "1º bloco de vendas ativas (ligações/WhatsApp) — positivação da carteira",
     "Alta", "DIÁRIA", "BAP Central › Base e oportunidades", "Contatos e pedidos registrados",
     "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "09:30 - 10:00",
     "Registrar pedidos no Máxima conferindo preço, desconto e condição; autorização quando fora do limite",
     "Alta", "DIÁRIA", "Máxima", "Pedidos digitados", "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "10:00 - 11:30",
     "2º bloco de vendas ativas — follow-up de orçamentos e cotações",
     "Alta", "DIÁRIA", "BAP Central › Base e oportunidades (Por produto)",
     "Orçamentos convertidos", "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "13:00 - 14:30",
     "3º bloco de vendas ativas — clientes estratégicos e reativação de inativos",
     "Alta", "DIÁRIA", "BAP Central › Base e oportunidades (Por família)",
     "Clientes reativados", "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "14:30 - 15:00",
     "Acompanhar faturamento (com a Juliana) e entrega dos pedidos do dia",
     "Alta", "DIÁRIA", "BAP Central › Pedidos faturados", "Pedidos do dia faturados",
     "Mantida (entrega agora no acompanhamento)"),
    ("Administrativo BAP", "Enricson Oliveira", "15:00 - 15:30",
     "Pendências de clientes: boleto, entrega, devolução e garantia com a Estefanie (pós-venda)",
     "Média", "DIÁRIA", OP, "Pendências direcionadas",
     "Mantida (com o destino de cada pendência)"),
    ("Administrativo BAP", "Enricson Oliveira", "15:30 - 16:30",
     "4º bloco de vendas — fechamento de pedidos para o faturamento do dia",
     "Alta", "DIÁRIA", "Máxima", "Pedidos transmitidos", "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "16:30 - 17:15",
     "Atualizar CRM: registros de contato, funil e agenda do dia seguinte",
     "Média", "DIÁRIA", "CRM", "CRM atualizado", "Mantida"),
    ("Administrativo BAP", "Enricson Oliveira", "17:15 - 17:30",
     "Fechamento do dia — Farol DDR", "Média", "DIÁRIA", "Farol DDR",
     "Farol preenchido", "Mantida"),

    # ---- ALLAIZA: as atividades dela, agora com a frequencia de verdade --
    ("Trade Marketing", "Allaiza Menezes", "08:00 - 09:00",
     "Atualização dos controles de campanhas (mecânicas, participantes, apurações)",
     "Alta", "SEG,TER,QUI", "Controles de campanha", "Controles atualizados",
     "Mantida (quarta é a matinal de trade; sexta é rota trade)"),
    ("Trade Marketing", "Allaiza Menezes", "09:00 - 10:30",
     "Briefings completos para a agência e o time de criação; solicitação de novos materiais",
     "Alta", "SEG,TER,QUA,QUI", "E-mail / agência", "Briefings formalizados", "Mantida (sexta é rota trade)"),
    ("Trade Marketing", "Allaiza Menezes", "10:30 - 11:30",
     "Apoio aos supervisores e VDEs: PDVs com maior potencial de exclusividade e materiais",
     "Média", "SEG,TER,QUA,QUI", "BAP Central › Base e oportunidades",
     "Oportunidades enviadas", "Mantida (sexta é rota trade)"),
    ("Trade Marketing", "Allaiza Menezes", "13:00 - 14:30",
     "Apuração e comunicação das parciais de campanhas e premiações",
     "Alta", "SEG,TER,QUA,QUI", "BAP Central › Meta e RV",
     "Parciais comunicadas", "Mantida (sexta é rota trade)"),
    ("Trade Marketing", "Allaiza Menezes", "14:30 - 16:00",
     "Eventos, treinamentos de produto e ações com fornecedores (agenda do mês)",
     "Média", "SEG,TER,QUA,QUI", "Agenda", "Ações organizadas", "Mantida (sexta é rota trade)"),
    ("Trade Marketing", "Allaiza Menezes", "16:00 - 17:30",
     "Prestação de contas de verbas e evidências de execução",
     "Média", "SEG,TER,QUA,QUI", "Controle de verbas", "Documentação arquivada", "Mantida (sexta é rota trade)"),
    ("Trade Marketing", "Allaiza Menezes", "09:00, 11:00, 14:00 e 16:00",
     "Acompanhamento de rota pelo Máxima (check-in/check-out) e divulgação",
     "Média", "DIÁRIA", "Máxima + BAP Central › Resumo do Planner",
     "Relatórios de rota divulgados", "Mantida"),
    ("Trade Marketing", "Allaiza Menezes", "Conforme rotina",
     "Apoio no acompanhamento da frota pelo MOB7 (Auditoria e RH)",
     "Média", "DIÁRIA", "MOB7", "Ocorrências reportadas", "Mantida"),
    ("Trade Marketing", "Allaiza Menezes", "Segunda",
     "Reunião de alinhamento com a agência: demandas, prioridades e prazos",
     "Alta", "SEG", "Reunião", "Pauta e prazos registrados",
     "Era diária no Farol — agora semanal"),
    ("Trade Marketing", "Allaiza Menezes", "Terça e quinta",
     "Controle de brindes, expositores e materiais BAP (quantitativo enviado)",
     "Média", "TER,QUI", "Controle de materiais", "Relatório de estoque enviado",
     "Era diária no Farol — agora terça e quinta"),
    ("Trade Marketing", "Allaiza Menezes", "Quarta (depois da matinal)",
     "Acompanhamento de PDVs com fachada/exclusividade e contratos comerciais",
     "Alta", "QUA", "Controle de PDVs", "Status dos PDVs e tratativas",
     "Era diária no Farol — agora semanal"),
    ("Trade Marketing", "Allaiza Menezes", "Quinta",
     "Suporte à Escola para Mecânicos PMZ: visita e necessidade de reposição",
     "Média", "QUI", "Visita", "Relatório de visita",
     "Era diária no Farol — agora semanal"),
    ("Trade Marketing", "Allaiza Menezes", "Quarta 08:00 - 09:00",
     "Matinal de trade: campanhas em andamento, materiais, ações de PDV e prioridades da semana com o time",
     "Alta", "QUA", "Reunião + BAP Central › Meta e RV",
     "Pauta e encaminhamentos registrados", "Nova (out/2026)"),
    ("Trade Marketing", "Allaiza Menezes", "Sexta (dia em campo)",
     "Rota trade: visitar PDVs — execução de materiais e expositores, fachada/exclusividade e fotos de evidência",
     "Alta", "SEX", "BAP Central › Resumo do Planner + Controle de PDVs",
     "Relatório da rota com evidências", "Nova (out/2026)"),
    ("Trade Marketing", "Allaiza Menezes", "A cada 2 semanas (sexta, na volta da rota)",
     "Relatório de produtos cadastrados na CNP: gerar, conferir e enviar",
     "Média", "QUINZENAL SEX", "CNP", "Relatório enviado",
     "Era diária no Farol — agora quinzenal"),
    ("Trade Marketing", "Allaiza Menezes", "Quando houver",
     "Criação de código de barras e gestão cadastral na CNP",
     "Alta", "SOB DEMANDA", "CNP", "Produtos cadastrados",
     "Sob demanda: lança na linha extra quando fizer"),
    ("Trade Marketing", "Allaiza Menezes", "Quando houver",
     "Análise de documentos, rótulos e produtos BAP",
     "Alta", "SOB DEMANDA", "Documentos", "Documentos revisados",
     "Sob demanda: lança na linha extra quando fizer"),
    ("Trade Marketing", "Allaiza Menezes", "Quando houver",
     "Revisão e validação de materiais de comunicação da agência",
     "Alta", "SOB DEMANDA", "Agência", "Materiais aprovados/devolvidos",
     "Sob demanda: lança na linha extra quando fizer"),
    ("Trade Marketing", "Allaiza Menezes", "Quando houver",
     "Solicitação, acompanhamento e revisão de embalagens",
     "Alta", "SOB DEMANDA", "Fornecedor / agência", "Embalagens revisadas",
     "Sob demanda: lança na linha extra quando fizer"),
]

# rotinas das vagas: ficam na Rotina para valer no dia em que alguem
# assumir, mas fora do Farol (nao derrubam a nota do time)
for _h, _a, _p in [
        ("07:30 - 08:00", "Validar o resultado do dia anterior (faturamento x meta por filial)", "Alta"),
        ("08:00 - 08:30", "Daily com o time administrativo: prioridades, pendências e distribuição do dia", "Alta"),
        ("08:30 - 09:15", "Acompanhar as filas do dia: faturamento, entregas, devoluções e garantias", "Alta"),
        ("09:15 - 10:00", "Autorizar conforme alçada: descontos fora do limite, cancelamentos e devoluções", "Alta"),
        ("10:00 - 10:45", "Tratar escalonamentos de clientes e ocorrências críticas", "Alta"),
        ("10:45 - 11:30", "Indicadores operacionais: prazo de faturamento, entregas atrasadas, devoluções e garantias paradas", "Alta"),
        ("13:00 - 13:45", "Alinhamento com supervisores de vendas: pedidos travados, autorizações e prioridades", "Alta"),
        ("13:45 - 14:30", "Separações/reversas (SOLICITACAO_BAP) e pendências logísticas do dia", "Alta"),
        ("14:30 - 15:30", "Revisar o Farol DDR do time e tratar desvios", "Média"),
        ("15:30 - 16:00", "Daily — Farol DDR com o Gerente Comercial", "Média"),
        ("16:00 - 17:00", "Tratativas administrativas: escalas, chamados, melhorias e pessoas", "Média"),
        ("17:15 - 17:30", "Fechamento do dia — consolidação das entregas do time", "Média")]:
    ROTINA_INICIAL.append(("Administrativo BAP", "Supervisor Administrativo (em aberto)",
                           _h, _a, _p, "DIÁRIA",
                           f"{OP} › PAINEL + Farol DDR" if "Farol" in _a or "filas" in _a else "",
                           "", "Vaga"))
for _h, _a, _p in [
        ("07:30 - 08:15", "Conferir o faturamento do dia anterior por filial (Protheus x relatórios)", "Alta"),
        ("08:15 - 09:00", "Atualizar relatórios e controles comerciais", "Alta"),
        ("09:00 - 09:45", "Controlar pendências financeiras: títulos em aberto, baixas e regularizações", "Alta"),
        ("09:45 - 10:30", "Apoiar auditoria: justificativas, evidências e históricos", "Alta"),
        ("10:30 - 11:30", "Analisar indicadores da operação (ruptura, devoluções, prazo de entrega)", "Alta"),
        ("13:00 - 13:45", "Conferir autorizações do dia contra as alçadas definidas", "Alta"),
        ("13:45 - 14:30", "Apoiar supervisores com análises e extrações sob demanda", "Média"),
        ("14:30 - 15:30", "Melhoria de processos: padronização de planilhas, e-mails e fluxos", "Média"),
        ("15:30 - 16:15", "Acompanhar chamados de sistemas (Protheus/Máxima) do time", "Média"),
        ("16:15 - 17:15", "Consolidar a parcial do dia (faturamento x meta)", "Alta"),
        ("17:15 - 17:30", "Fechamento do dia — Farol DDR", "Média")]:
    ROTINA_INICIAL.append(("Administrativo BAP", "Analista Administrativo Pleno (em aberto)",
                           _h, _a, _p, "DIÁRIA", "", "", "Vaga"))

# feriados que valem para Manaus em 2026 (nacionais, estadual e municipais).
# Ficam na aba Feriados: o mes seguinte le de la.
FERIADOS_INICIAIS = [
    ("2026-01-01", "Confraternização Universal"), ("2026-02-16", "Carnaval"),
    ("2026-02-17", "Carnaval"), ("2026-04-03", "Sexta-feira Santa"),
    ("2026-04-21", "Tiradentes"), ("2026-05-01", "Dia do Trabalho"),
    ("2026-06-04", "Corpus Christi"), ("2026-09-05", "Elevação do Amazonas"),
    ("2026-09-07", "Independência"), ("2026-10-12", "N. Sra. Aparecida"),
    ("2026-10-24", "Aniversário de Manaus"), ("2026-11-02", "Finados"),
    ("2026-11-15", "Proclamação da República"),
    ("2026-11-20", "Consciência Negra"), ("2026-12-08", "N. Sra. da Conceição"),
    ("2026-12-25", "Natal"),
]

# ---------------------------------------------------------------------------
# estilo
# ---------------------------------------------------------------------------
AZUL = "2F7D32"          # o verde BAP (era o azul)
FINO = Side(style="thin", color="D5DAD4")
BORDA = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
CAB = PatternFill("solid", fgColor=AZUL)
CAB_FONTE = Font(color="FFFFFF", bold=True, size=9)
ZEBRA = PatternFill("solid", fgColor="F7F8F6")
VERDE = PatternFill("solid", fgColor="DDF1E4")
AMARELO = PatternFill("solid", fgColor="FFF4D6")
VERMELHO = PatternFill("solid", fgColor="FBE3E3")
LARANJA = PatternFill("solid", fgColor="FBE2B4")      # entregue parcial


def _cabecalho(ws, linha, titulos, larguras):
    for i, (t, w) in enumerate(zip(titulos, larguras), start=1):
        c = ws.cell(linha, i, t)
        c.fill, c.font, c.border = CAB, CAB_FONTE, BORDA
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[linha].height = 30


def _titulo(ws, texto, sub=""):
    ws["A1"] = texto
    ws["A1"].font = Font(bold=True, size=14, color=AZUL)
    if sub:
        ws["A2"] = sub
        ws["A2"].font = Font(size=9, color="6B7A8D")


# ---------------------------------------------------------------------------
# frequencia -> dias
# ---------------------------------------------------------------------------
def dias_uteis(ano: int, mes: int, feriados: set) -> list[date]:
    d = date(ano, mes, 1)
    saida = []
    while d.month == mes:
        if d.weekday() < 5 and d.isoformat() not in feriados:
            saida.append(d)
        d += timedelta(days=1)
    return saida


def dias_da_atividade(quando: str, uteis: list[date]) -> list[date]:
    """
    Os dias do mes em que a atividade aparece no Farol.

        DIÁRIA ............ todo dia util
        SEG / TER,QUI ..... so nesses dias da semana
        QUINZENAL SEX ..... 1ª e 3ª sexta util do mes
        MENSAL INÍCIO/FIM . primeiro / ultimo dia util
        SOB DEMANDA ....... nenhum (lanca na linha extra quando fizer)
    """
    q = (quando or "").strip().upper()
    q = q.replace("DIARIA", "DIÁRIA").replace("INICIO", "INÍCIO")
    if not uteis or q.startswith("SOB"):
        return []
    if q in ("", "DIÁRIA"):
        return list(uteis)
    if q.startswith("MENSAL"):
        return [uteis[-1]] if "FIM" in q else [uteis[0]]
    if q.startswith("QUINZENAL"):
        resto = q.replace("QUINZENAL", "").strip() or "SEG"
        alvo = DIAS.index(resto[:3]) if resto[:3] in DIAS else 0
        do_dia = [d for d in uteis if d.weekday() == alvo]
        return do_dia[0::2]
    pedidos = {DIAS.index(p.strip()[:3]) for p in re.split(r"[,/;e ]+", q)
               if p.strip()[:3] in DIAS}
    return [d for d in uteis if d.weekday() in pedidos]


def _hora_de_ordenar(horario: str) -> str:
    m = re.match(r"\s*(\d{1,2}):(\d{2})", str(horario or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else "99:99"


# ---------------------------------------------------------------------------
# leitura do mes anterior
# ---------------------------------------------------------------------------
def farol_mais_recente(pasta: Path = PASTA_RELATORIOS) -> Path | None:
    achados = sorted(Path(pasta).glob(f"{PREFIXO}????-??.xlsx"))
    return achados[-1] if achados else None


# (11/10) O CADASTRO DO FAROL DDR (equipe, rotina e feriados) e do ANALISTA:
# fica em farol_ddr_config.json (BAP Analista › Farol DDR). O Excel do mes
# traz as abas Equipe, Rotina e Feriados so para consulta (protegidas).
ARQ_CONFIG = "farol_ddr_config.json"


def caminho_config(raiz=None) -> Path:
    return Path(raiz or AQUI) / ARQ_CONFIG


def ler_config(raiz=None):
    """(equipe, rotina, feriados) do cadastro, ou None se nao existe."""
    try:
        d = json.loads(caminho_config(raiz).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    eq = [tuple((list(x) + [""] * 4)[:4]) for x in d.get("equipe") or []]
    rot = [tuple((list(x) + [""] * 9)[:9]) for x in d.get("rotina") or []]
    fer = [tuple((list(x) + [""] * 2)[:2]) for x in d.get("feriados") or []]
    if not eq and not rot:
        return None
    return eq, rot, fer


def salvar_config(equipe, rotina, feriados, raiz=None) -> Path:
    arq = caminho_config(raiz)
    tmp = arq.with_name(f"~{arq.name}")
    tmp.write_text(json.dumps({"equipe": [list(x) for x in equipe],
                               "rotina": [list(x) for x in rotina],
                               "feriados": [list(x) for x in feriados]},
                              ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, arq)
    return arq


def base_do_analista(pasta: Path = PASTA_RELATORIOS):
    """O que vale para o proximo mes: o cadastro do Analista; sem ele, o
    que esta no Excel mais recente (e o cadastro nasce dele)."""
    cfg = ler_config(Path(pasta).parent)
    if cfg is not None:
        return cfg
    return ler_base(farol_mais_recente(pasta))


def ler_base(caminho: Path | None):
    """(equipe, rotina, feriados) do arquivo, ou os de partida."""
    if caminho is None or not Path(caminho).exists():
        return (list(EQUIPE_INICIAL), list(ROTINA_INICIAL),
                list(FERIADOS_INICIAIS))
    wb = load_workbook(caminho, read_only=True, data_only=False)
    try:
        def linhas(nome, primeira):
            if nome not in wb.sheetnames:
                return []
            return [r for r in wb[nome].iter_rows(min_row=primeira,
                                                    values_only=True)
                    if r and any(v not in (None, "") for v in r)]
        equipe = [tuple(r[:4]) for r in linhas("Equipe", 5) if r[0]]
        rotina = []
        for r in linhas("Rotina", 5):
            if not r[1] or not r[4]:
                continue
            area, quem, cargo, horario, atividade, prio, _pts, quando, \
                ferr, entreg, mud = (list(r) + [None] * 11)[:11]
            rotina.append((area, quem, horario, atividade, prio or "Média",
                           quando or "DIÁRIA", ferr or "", entreg or "",
                           mud or ""))
        feriados = [(str(r[0])[:10], r[1] or "") for r in linhas("Feriados", 5)
                    if r[0]]
    finally:
        wb.close()
    return (equipe or list(EQUIPE_INICIAL), rotina or list(ROTINA_INICIAL),
            feriados or list(FERIADOS_INICIAIS))


def _feriados_do_planner(pasta: Path) -> list[tuple]:
    """Os feriados que o Planner ja conhece, para nao cadastrar duas vezes."""
    try:
        cfg = json.loads((pasta / "planner_config.json").read_text("utf-8"))
        return [(str(f)[:10], "do Planner BAP") for f in cfg.get("feriados") or []]
    except (OSError, ValueError):
        return []


# ---------------------------------------------------------------------------
# a montagem
# ---------------------------------------------------------------------------
def _nome_da_aba(nome: str, usadas: set) -> str:
    limpo = re.sub(r"[\[\]\*\?/\\:]", "", nome).strip()[:28] or "Pessoa"
    base, n = limpo, 2
    while limpo in usadas:
        limpo = f"{base[:25]} {n}"
        n += 1
    usadas.add(limpo)
    return limpo


def gerar_mes(ano: int, mes: int, equipe, rotina, feriados) -> Workbook:
    datas_feriado = {f for f, _ in feriados}
    uteis = dias_uteis(ano, mes, datas_feriado)
    cargo_de = {e[0]: e[1] for e in equipe}
    no_farol = [e for e in equipe if str(e[3]).upper().startswith("S")]

    wb = Workbook()
    leia = wb.active
    leia.title = "Leia-me"
    painel = wb.create_sheet("Painel")
    ws_eq = wb.create_sheet("Equipe")
    ws_rot = wb.create_sheet("Rotina")
    ws_fer = wb.create_sheet("Feriados")
    listas = wb.create_sheet("Listas")

    # ---- Listas (escondida) ---------------------------------------------
    for i, v in enumerate(STATUS, start=1):
        listas.cell(i, 1, v)
    for i, v in enumerate(MOTIVOS, start=1):
        listas.cell(i, 2, v)
    for i, v in enumerate(PONTOS, start=1):
        listas.cell(i, 3, v)
    for i, v in enumerate(["SIM", "NÃO"], start=1):
        listas.cell(i, 4, v)
    listas.sheet_state = "hidden"
    dv_status = f"Listas!$A$1:$A${len(STATUS)}"
    dv_motivo = f"Listas!$B$1:$B${len(MOTIVOS)}"
    dv_prio = f"Listas!$C$1:$C${len(PONTOS)}"

    # ---- Equipe -----------------------------------------------------------
    _titulo(ws_eq, "EQUIPE NO FAROL DDR",
            "No Farol = SIM gera a aba da pessoa no mês seguinte. Vaga em aberto "
            "fica NÃO: a rotina dela está guardada, mas não derruba a nota do time.")
    _cabecalho(ws_eq, 4, ["Colaborador", "Cargo", "Papel", "No Farol"],
               [42, 34, 30, 11])
    for i, e in enumerate(equipe, start=5):
        for j, v in enumerate(list(e)[:4], start=1):
            ws_eq.cell(i, j, v).border = BORDA
    dv = DataValidation(type="list", formula1="Listas!$D$1:$D$2")
    ws_eq.add_data_validation(dv)
    dv.add(f"D5:D{4 + len(equipe) + 10}")
    ws_eq.freeze_panes = "A5"

    # ---- Rotina -----------------------------------------------------------
    _titulo(ws_rot, "ROTINA DO TIME — o que cada um faz, quando e com qual ferramenta",
            "Mudou a rotina? Mude aqui. O mês seguinte nasce desta aba. "
            "QUANDO: DIÁRIA, SEG, TER,QUI, QUINZENAL SEX, MENSAL INÍCIO, "
            "MENSAL FIM ou SOB DEMANDA.")
    titulos = ["Área", "Colaborador", "Cargo", "Horário", "Atividade",
               "Prioridade", "Pontos", "Quando", "Ferramenta BAP",
               "Entregável", "Mudança em out/2026"]
    _cabecalho(ws_rot, 4, titulos, [18, 30, 26, 16, 70, 10, 8, 14, 44, 30, 34])
    ordem_pessoa = {e[0]: i for i, e in enumerate(equipe)}
    rot_ord = sorted(rotina, key=lambda r: (ordem_pessoa.get(r[1], 99),
                                             r[5] != "DIÁRIA",
                                             _hora_de_ordenar(r[2])))
    for i, r in enumerate(rot_ord, start=5):
        area, quem, horario, atividade, prio, quando, ferr, entreg, mud = r
        valores = [area, quem, cargo_de.get(quem, ""), horario, atividade,
                   prio, f'=IFERROR(INDEX({{5,3,1}},MATCH(F{i},{{"Alta","Média","Baixa"}},0)),0)',
                   quando, ferr, entreg, mud]
        for j, v in enumerate(valores, start=1):
            c = ws_rot.cell(i, j, v)
            c.border = BORDA
            c.alignment = Alignment(vertical="top", wrap_text=j in (5, 9, 10, 11))
            if (i % 2) == 0:
                c.fill = ZEBRA
        if str(mud).startswith(("Nova", "Veio")):
            ws_rot.cell(i, 11).font = Font(color="1E7A46", bold=True)
    ultima_rot = 4 + len(rot_ord)
    dv = DataValidation(type="list", formula1=dv_prio)
    ws_rot.add_data_validation(dv)
    dv.add(f"F5:F{ultima_rot + 50}")
    ws_rot.freeze_panes = "C5"
    ws_rot.auto_filter.ref = f"A4:K{ultima_rot}"

    # ---- Feriados ---------------------------------------------------------
    _titulo(ws_fer, "FERIADOS", "Dia que está aqui não entra no Farol.")
    _cabecalho(ws_fer, 4, ["Data", "Feriado"], [14, 40])
    for i, (d, nome) in enumerate(sorted(feriados), start=5):
        ws_fer.cell(i, 1, date.fromisoformat(d)).number_format = "dd/mm/yyyy"
        ws_fer.cell(i, 2, nome)

    # ---- uma aba por pessoa ------------------------------------------------
    usadas = set(wb.sheetnames)
    abas = []
    for quem, cargo, papel, _ in no_farol:
        aba = _nome_da_aba(quem, usadas)
        ws = wb.create_sheet(aba)
        abas.append((quem, aba, papel))
        _titulo(ws, f"FAROL DDR — {quem} — {MESES[mes]}/{ano}",
                f"{cargo} · {papel}.  Marque ENTREGUE, ENTREGUE PARCIAL ou NÃO "
                f"ENTREGUE em cada linha até o fim do dia; parcial e não "
                f"entregue pedem o motivo. Fez algo fora da rotina (sob "
                f"demanda)? Use as linhas em branco do fim.")
        _cabecalho(ws, 4, ["Data", "Dia", "Horário", "Atividade", "Prioridade",
                           "Pontos", "Status", "Pontos ganhos",
                           "Motivo do não cumprimento", "Observação",
                           "Ferramenta BAP"],
                   [11, 6, 15, 62, 10, 8, 9, 9, 28, 30, 40])
        linhas = []
        for r in rotina:
            if r[1] != quem:
                continue
            for d in dias_da_atividade(r[5], uteis):
                linhas.append((d, _hora_de_ordenar(r[2]), r))
        linhas.sort(key=lambda x: (x[0], x[1]))
        n = 5
        for d, _h, r in linhas:
            _, _, horario, atividade, prio, _q, ferr, _e, _m = r
            ws.cell(n, 1, d).number_format = "dd/mm"
            ws.cell(n, 2, DIAS[d.weekday()])
            ws.cell(n, 3, horario)
            ws.cell(n, 4, atividade)
            ws.cell(n, 5, prio)
            # pontos GRAVADOS, nao formula: mudar a prioridade na Rotina
            # depois nao reescreve a nota de um dia que ja passou
            ws.cell(n, 6, PONTOS.get(prio, 0))
            ws.cell(n, 8, _formula_ganhos(n))
            ws.cell(n, 11, ferr)
            n += 1
        primeira_extra = n
        for k in range(LINHAS_EXTRAS):
            ws.cell(n, 6, f'=IF(D{n}="","",IFERROR(INDEX({{5,3,1}},'
                          f'MATCH(E{n},{{"Alta","Média","Baixa"}},0)),3))')
            ws.cell(n, 8, _formula_ganhos(n, extra=True))
            ws.cell(n, 1).number_format = "dd/mm"
            n += 1
        ultima = n - 1
        for linha in range(5, ultima + 1):
            for col in range(1, 12):
                c = ws.cell(linha, col)
                c.border = BORDA
                c.alignment = Alignment(vertical="center",
                                        wrap_text=col in (4, 10, 11))
            if linha >= primeira_extra:
                for col in range(1, 12):
                    ws.cell(linha, col).fill = AMARELO
        if primeira_extra <= ultima:
            ws.cell(primeira_extra, 10,
                    "← linhas extras: atividade sob demanda ou fora da rotina")
        dv1 = DataValidation(type="list", formula1=dv_status, allow_blank=True)
        dv2 = DataValidation(type="list", formula1=dv_motivo, allow_blank=True)
        dv3 = DataValidation(type="list", formula1=dv_prio, allow_blank=True)
        for dv_ in (dv1, dv2, dv3):
            ws.add_data_validation(dv_)
        dv1.add(f"G5:G{ultima}")
        dv2.add(f"I5:I{ultima}")
        dv3.add(f"E{primeira_extra}:E{ultima}")
        ws.conditional_formatting.add(
            f"G5:G{ultima}", CellIsRule(operator="equal",
                                        formula=[f'"{ENTREGUE}"'], fill=VERDE))
        ws.conditional_formatting.add(
            f"G5:G{ultima}", CellIsRule(operator="equal",
                                        formula=[f'"{PARCIAL}"'],
                                        fill=LARANJA))
        ws.conditional_formatting.add(
            f"G5:G{ultima}", CellIsRule(operator="equal",
                                        formula=[f'"{NAO_ENTREGUE}"'],
                                        fill=VERMELHO))
        # NAO ENTREGUE / PARCIAL sem motivo fica marcado: e o que falta
        ws.conditional_formatting.add(
            f"I5:I{ultima}", FormulaRule(
                formula=[f'AND(OR(G5="{NAO_ENTREGUE}",G5="{PARCIAL}"),I5="")'],
                fill=VERMELHO))
        ws.freeze_panes = "E5"
        ws.auto_filter.ref = f"A4:K{ultima}"
        abas[-1] = (quem, aba, papel, ultima)

    # ---- Painel -----------------------------------------------------------
    _titulo(painel, f"FAROL DDR — PAINEL DO TIME — {MESES[mes]}/{ano}",
            f"{len(uteis)} dias úteis. A nota é por PONTOS (Alta 5, Média 3, "
            f"Baixa 1). Ausência justificada sai da conta. Linha sem marcação "
            f"até hoje conta como não feita — e aparece separada.")
    _cabecalho(painel, 4, ["Colaborador", "Papel", "Atividades no mês",
                           "Pontos possíveis no mês", "Pontos possíveis até hoje",
                           "Pontos ganhos", "% até hoje", "% no mês",
                           "Sem marcação até hoje", "Não entregue até hoje (fora ausência)", "Situação"],
               [32, 26, 12, 13, 13, 11, 10, 10, 12, 10, 36])
    linha = 5
    for quem, aba, papel, ultima in abas:
        a = f"'{aba}'!"
        rng = lambda col: f"{a}${col}$5:${col}${ultima}"   # noqa: E731
        painel.cell(linha, 1, quem)
        painel.cell(linha, 2, papel)
        painel.cell(linha, 3, f'=COUNTIFS({rng("D")},"<>")')
        painel.cell(linha, 4, f'=SUMIFS({rng("F")},{rng("D")},"<>",'
                              f'{rng("I")},"<>{AUSENCIA}")')
        painel.cell(linha, 5, f'=SUMIFS({rng("F")},{rng("D")},"<>",'
                              f'{rng("A")},"<="&TODAY(),{rng("I")},"<>{AUSENCIA}")')
        painel.cell(linha, 6, f'=SUMIFS({rng("H")},{rng("A")},"<="&TODAY())')
        painel.cell(linha, 7, f"=IFERROR(F{linha}/E{linha},0)")
        painel.cell(linha, 8, f"=IFERROR(F{linha}/D{linha},0)")
        painel.cell(linha, 9, f'=COUNTIFS({rng("D")},"<>",{rng("A")},"<="&TODAY(),'
                              f'{rng("G")},"")')
        painel.cell(linha, 10, f'=COUNTIFS({rng("A")},"<="&TODAY(),'
                               f'{rng("G")},"{NAO_ENTREGUE}",'
                               f'{rng("I")},"<>{AUSENCIA}")')
        painel.cell(linha, 11, _formula_faixa(f"G{linha}", f"E{linha}"))
        linha += 1
    total = linha
    painel.cell(total, 1, "TOTAL DO TIME").font = Font(bold=True)
    for col in "CDEFIJ":
        painel[f"{col}{total}"] = f"=SUM({col}5:{col}{total - 1})"
    painel[f"G{total}"] = f"=IFERROR(F{total}/E{total},0)"
    painel[f"H{total}"] = f"=IFERROR(F{total}/D{total},0)"
    painel[f"K{total}"] = _formula_faixa(f"G{total}", f"E{total}")
    for lin in range(5, total + 1):
        for col in range(1, 12):
            c = painel.cell(lin, col)
            c.border = BORDA
            if lin == total:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="E7ECF4")
        painel.cell(lin, 7).number_format = "0.0%"
        painel.cell(lin, 8).number_format = "0.0%"
    faixa = f"G5:G{total}"
    painel.conditional_formatting.add(
        faixa, CellIsRule(operator="greaterThanOrEqual", formula=["0.95"], fill=VERDE))
    painel.conditional_formatting.add(
        faixa, CellIsRule(operator="between", formula=["0.9", "0.9499"], fill=AMARELO))
    painel.conditional_formatting.add(
        faixa, FormulaRule(formula=[f"AND(G5<0.9,E5>0)"], fill=VERMELHO))
    # legenda das faixas
    leg = total + 2
    painel.cell(leg, 1, "FAIXAS").font = Font(bold=True, color=AZUL)
    for k, (limite, texto) in enumerate(
            [(">= 95%", FAIXAS[0][1]), ("90% a 94,9%", FAIXAS[1][1]),
             ("< 90%", FAIXAS[2][1])], start=1):
        painel.cell(leg + k, 1, limite)
        painel.cell(leg + k, 2, texto)
    # os NAO por motivo
    mot = leg + 5
    painel.cell(mot, 1, "NÃO ENTREGUE POR MOTIVO (até hoje)").font = Font(bold=True, color=AZUL)
    _cabecalho(painel, mot + 1, ["Motivo"] + [q for q, _, _, _ in abas],
               [32] + [14] * len(abas))
    for k, motivo in enumerate(MOTIVOS + ["(sem motivo)"], start=mot + 2):
        painel.cell(k, 1, motivo).border = BORDA
        for j, (_q, aba, _p, ultima) in enumerate(abas, start=2):
            a = f"'{aba}'!"
            crit = '""' if motivo == "(sem motivo)" else f'"{motivo}"'
            painel.cell(k, j, f'=COUNTIFS({a}$G$5:$G${ultima},"{NAO_ENTREGUE}",'
                              f'{a}$I$5:$I${ultima},{crit},'
                              f'{a}$A$5:$A${ultima},"<="&TODAY())').border = BORDA
    painel.freeze_panes = "C5"
    # o painel reaproveita as larguras da tabela de cima
    for col, w in zip("ABCDEFGHIJK", [32, 26, 12, 13, 13, 11, 10, 10, 12, 10, 36]):
        painel.column_dimensions[col].width = w

    # ---- Leia-me ----------------------------------------------------------
    _titulo(leia, f"FAROL DDR — BAP — {MESES[mes]}/{ano}")
    texto = [
        "COMO PREENCHER",
        "1. Cada pessoa tem a SUA aba, com as atividades do mês já montadas pela frequência da Rotina.",
        "2. Até o fim do dia, marque ENTREGUE, ENTREGUE PARCIAL ou NÃO ENTREGUE em cada linha do dia (pela lista, aqui ou no Farol DDR do BAP Central). Parcial e não entregue pedem o motivo (a célula fica vermelha até ter).",
        "3. Fez algo sob demanda ou fora da rotina? Use as linhas amarelas do fim da aba: data, atividade e prioridade.",
        "4. Faltou o dia (férias, folga, atestado)? Marque NÃO ENTREGUE com o motivo 'Ausência justificada' — sai da conta.",
        "",
        "COMO A NOTA É CALCULADA (aba Painel)",
        "• Por PONTOS: Alta = 5, Média = 3, Baixa = 1. Uma atividade Alta pesa quase o dobro de uma Média.",
        "• ENTREGUE ganha os pontos da linha; ENTREGUE PARCIAL ganha a metade; NÃO ENTREGUE, zero.",
        "• % até hoje = pontos ganhos ÷ pontos possíveis até hoje. Linha sem marcação conta como não feita.",
        "• Faixas: ≥ 95% Excelência operacional · 90% a 94,9% Focar na excelência · < 90% Focar nas atividades de alta prioridade.",
        "• O Painel também mostra quantas linhas ficaram SEM MARCAÇÃO e os NÃO ENTREGUE por motivo — o motivo é o que diz o que corrigir.",
        "",
        "A DIVISÃO DO TIME (out/2026)",
        "• PRÉ-VENDA E FATURAMENTO — Juliana: do orçamento até a nota fiscal. A nota fiscal é o ponto de passagem.",
        f"• PÓS-VENDA E LOGÍSTICA — {NOVA}: da nota fiscal ao canhoto (entregas, coletas, fretes, ocorrências).",
        "• DEVOLUÇÃO E GARANTIA — Mayara: da solicitação ao crédito, e a garantia até o parecer do fornecedor.",
        "• TRADE — Allaiza: quarta abre com a MATINAL DE TRADE; sexta é dia de ROTA TRADE em campo (as atividades de escritório ficam de segunda a quinta).",
        "• A coluna 'Mudança em out/2026' da aba Rotina mostra de onde veio cada atividade.",
        "",
        "PRÓXIMO MÊS",
        "• Rode:  python farol_ddr.py AAAA-MM   (ou o botão do BAP Central). O mês novo lê a Rotina, a Equipe e os",
        "  Feriados DESTE arquivo — mude a rotina aqui e o mês seguinte já nasce com ela.",
        "• Arquivo de um mês que já existe nunca é sobrescrito: ele guarda o que o time marcou.",
        "",
        "PREMISSA A VALIDAR: a integração diária do Máxima passou para a Juliana (pré-venda).",
    ]
    for i, t in enumerate(texto, start=3):
        c = leia.cell(i, 1, t)
        if t and t == t.upper() and not t.startswith("•"):
            c.font = Font(bold=True, color=AZUL)
        elif t.startswith("PREMISSA"):
            c.font = Font(bold=True, color="B3261E")
    leia.column_dimensions["A"].width = 130

    # as abas das pessoas logo depois do Painel: e onde o time trabalha
    for _q, aba, _p, _u in reversed(abas):
        wb.move_sheet(aba, offset=-(wb.sheetnames.index(aba) - 2))
    return wb


def gravar_marcacoes(caminho, aba: str, edicoes: dict) -> int:
    """
    O que a assistente marcou pela tela (Farol DDR do BAP Central):
    edicoes = {"<linha da planilha>": {"status": ..., "motivo": ...}}.
    Grava so STATUS (G) e MOTIVO (I) da aba da pessoa - o resto da linha
    e da rotina. Levanta PermissionError se o arquivo estiver aberto no
    Excel (quem chama avisa). Devolve quantas celulas mudaram.
    """
    from openpyxl import load_workbook                  # noqa: PLC0415
    caminho = Path(caminho)
    wb = load_workbook(caminho)
    if aba not in wb.sheetnames:
        raise ValueError(f"O {caminho.name} não tem a aba {aba}.")
    ws = wb[aba]
    mudou = 0
    for chave, campos in edicoes.items():
        n = int(str(chave).split("|")[-1])
        if n < 5 or not ws.cell(n, 4).value:
            raise ValueError(f"Linha {n} da aba {aba} não é uma atividade.")
        for campo, col in (("status", 7), ("motivo", 9)):
            if campo not in campos:
                continue
            v = campos[campo] or None
            if campo == "status" and v not in (None, *STATUS):
                raise ValueError(f"Status inválido: {v}")
            if ws.cell(n, col).value != v:
                ws.cell(n, col).value = v
                mudou += 1
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:                                   # noqa: BLE001
        pass
    tmp = caminho.with_name(f"~salvando_{caminho.name}")
    wb.save(tmp)
    wb.close()
    os.replace(tmp, caminho)
    return mudou


def _formula_faixa(pct: str, base: str) -> str:
    return (f'=IF({base}=0,"",IF({pct}>={FAIXAS[0][0]},"{FAIXAS[0][1]}",'
            f'IF({pct}>={FAIXAS[1][0]},"{FAIXAS[1][1]}","{FAIXAS[2][1]}")))')


def gerar_farol(ano: int, mes: int, pasta: Path = PASTA_RELATORIOS,
                base: Path | None = None) -> Path:
    """
    Cria FAROL_DDR_BAP_AAAA-MM.xlsx. Recusa se o arquivo ja existir - ele
    guarda o que o time marcou e nao pode ser refeito por cima.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{PREFIXO}{ano:04d}-{mes:02d}.xlsx"
    if destino.exists():
        raise FileExistsError(
            f"{destino.name} já existe e guarda as marcações do time - "
            f"não vou gerar por cima.")
    if base is not None:
        equipe, rotina, feriados = ler_base(base)
    else:
        equipe, rotina, feriados = base_do_analista(pasta)
        if ler_config(pasta.parent) is None:    # o cadastro nasce do Excel
            try:
                salvar_config(equipe, rotina, feriados, pasta.parent)
            except OSError:
                pass
    vistos = {f for f, _ in feriados}
    feriados = feriados + [f for f in _feriados_do_planner(pasta.parent)
                           if f[0] not in vistos]
    wb = gerar_mes(ano, mes, equipe, rotina, feriados)
    # (11/10) Equipe, Rotina e Feriados: so consulta no Excel - quem muda e
    # o Analista (BAP Analista › Farol DDR)
    for nome in ("Equipe", "Rotina", "Feriados"):
        if nome in wb.sheetnames:
            wb[nome].protection.sheet = True
    wb.save(destino)
    return destino


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera o Farol DDR do mês.")
    ap.add_argument("mes", nargs="?", help="AAAA-MM (padrão: o mês atual)")
    ap.add_argument("--pasta", default=str(PASTA_RELATORIOS))
    args = ap.parse_args(argv)
    hoje = date.today()
    if args.mes:
        ano, mes = (int(x) for x in args.mes.split("-"))
    else:
        ano, mes = hoje.year, hoje.month
    try:
        destino = gerar_farol(ano, mes, Path(args.pasta))
    except FileExistsError as erro:
        print(erro)
        return 1
    print(f"Farol gerado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
