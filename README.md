# Conciliacao de Caixa

Automacao para conciliar vendas de Cielo e QuickPay com os registros de caixa obtidos pela API Velo.

## Estado atual

Este repositorio esta na Etapa 6: leitura, validacao, processamento e exportacao independente dos relatorios Cielo e QuickPay. Ainda nao ha integracao com API Velo, matching com ERP ou workflow completo.

## Premissas definitivas

- O periodo informado representa a data da venda.
- A API sera comparada pela data `dataCadastro`; `dataVencimento` sera preservada como informacao auxiliar.
- A saida Cielo da primeira versao tera apenas a aba `Planilha1`, seguindo o modelo LEO.
- A QuickPay exigira a coluna `RECEBIDO NO BANCO QUICKPAY` dentro da tabela transacional.
- Tokens nunca devem ser salvos no repositorio, em logs ou em arquivos de configuracao versionados.
- Arquivos reais de entrada, respostas brutas da API, logs e saidas geradas ficam fora do Git.

## CLI

Gerar somente o relatorio Cielo:

```powershell
conciliacao gerar-cielo `
  --arquivo "arquivos_exemplo/cielo.xlsx" `
  --data-inicio 2026-07-14 `
  --data-fim 2026-07-15 `
  --saida "output/cielo"
```

O periodo e obrigatorio e usa a `Data da venda`. Transacoes fora do periodo nao entram na planilha gerada, mas sao contabilizadas no resumo. A saida usa o nome:

```text
CIELO_CONCILIACAO_<DATA_INICIO>_A_<DATA_FIM>.xlsx
```

Se o arquivo ja existir, o comando cria um sufixo com data/hora. Para sobrescrever de forma explicita, use `--sobrescrever`.

Gerar somente o relatorio QuickPay:

```powershell
conciliacao gerar-quickpay `
  --arquivo "arquivos_exemplo/quickpay_preparado.xlsx" `
  --data-inicio 2026-07-13 `
  --data-fim 2026-07-13 `
  --saida "output/quickpay"
```

O QuickPay aceita XLSX e arquivos HTML exportados com extensao `.xls`, desde que a tabela transacional contenha exatamente uma coluna `RECEBIDO NO BANCO QUICKPAY`. O formato legado com valores bancarios fora da tabela principal e invalido e nao gera saida.

Exemplo minimo de entrada QuickPay:

```text
Data da venda | Data de recebimento | Numero de Parcelas | Tipo de pagamento | Valor da Venda | Valor liquido | Taxa | Bandeira | RECEBIDO NO BANCO QUICKPAY
13/07/2026 11:35 | 14/07/2026 | 1 | Credito | 126,83 | 121,77 | 5,03 | Visa | 121,80
```

A saida usa a aba unica `Conciliação` e o nome:

```text
QUICKPAY_CONCILIACAO_<DATA_INICIO>_A_<DATA_FIM>.xlsx
```

Calculos QuickPay:

- `Bruto-Liquido = Valor da Venda - Valor liquido`
- `Diferenca = Taxa - Bruto-Liquido`
- `Porcentagem = 1 - Valor liquido / Valor da Venda`
- `Sistema` e `Diferenca Sistema` ficam vazios nesta etapa.
- `Status` fica `PENDENTE DE CONCILIAÇÃO COM SISTEMA`.

Quando `Valor da Venda` for zero, a porcentagem fica em branco e a validacao gera aviso. Diferencas de centavos entre `Taxa` e `Bruto-Liquido` sao preservadas; taxa negativa ou taxa maior que o valor da venda bloqueiam a geracao.

Validar arquivos sem gerar Excel:

```powershell
conciliacao validar-cielo `
  --arquivo "arquivos_exemplo/cielo.xlsx" `
  --data-inicio 2026-07-14 `
  --data-fim 2026-07-15
```

Exemplo previsto para uma execucao futura com workflow completo:

```powershell
$env:VELO_BEARER_TOKEN="TOKEN_AQUI"
conciliacao processar `
  --data-inicio 2026-07-13 `
  --data-fim 2026-07-13 `
  --arquivo-cielo "data/input/cielo.xlsx" `
  --arquivo-quickpay "data/input/quickpay.xlsx"
```

Nesta etapa, o comando `processar` apenas valida argumentos e informa que o workflow completo ainda nao foi implementado.

## Limitacoes atuais

- Nao ha comparacao com a API Velo.
- Nao ha matching com ERP/sistema.
- Nao ha conciliacao automatica com o sistema.
- As saidas Cielo e QuickPay tem somente a aba principal, sem abas auxiliares.

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
