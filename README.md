# Conciliacao de Caixa

Automacao para conciliar vendas de Cielo e QuickPay com os registros de caixa obtidos pela API Velo.

## Estado atual

Este repositorio esta na Etapa 1: base do projeto. Ainda nao ha leitores de Excel, processadores, matching ou chamadas reais para a API.

## Premissas definitivas

- O periodo informado representa a data da venda.
- A API sera comparada pela data `dataCadastro`; `dataVencimento` sera preservada como informacao auxiliar.
- A saida Cielo da primeira versao tera apenas a aba `Planilha1`, seguindo o modelo LEO.
- A QuickPay exigira a coluna `RECEBIDO NO BANCO QUICKPAY` dentro da tabela transacional.
- Tokens nunca devem ser salvos no repositorio, em logs ou em arquivos de configuracao versionados.
- Arquivos reais de entrada, respostas brutas da API, logs e saidas geradas ficam fora do Git.

## CLI

Exemplo previsto para uma execucao futura:

```powershell
$env:VELO_BEARER_TOKEN="TOKEN_AQUI"
conciliacao processar `
  --data-inicio 2026-07-13 `
  --data-fim 2026-07-13 `
  --arquivo-cielo "data/input/cielo.xlsx" `
  --arquivo-quickpay "data/input/quickpay.xlsx"
```

Nesta etapa, o comando `processar` apenas valida argumentos e informa que o workflow ainda nao foi implementado.

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

## Dados locais

Use estas pastas para execucoes locais:

- `data/input/`: arquivos de entrada reais.
- `data/api_raw/`: respostas brutas da API, sem token.
- `output/`: planilhas geradas.
- `logs/`: logs de execucao.

Essas pastas sao ignoradas pelo Git, exceto pelos arquivos `.gitkeep`.
