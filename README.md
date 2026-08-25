# Conciliacao de Caixa

Automacao para conciliar vendas de Cielo e QuickPay com os registros de caixa obtidos pela API Velo.

## Estado atual

Este repositorio esta na Etapa 9: workflow integrado com leitura, validacao, consulta Velo somente leitura, matching, exportacao independente de Cielo e QuickPay, logs e resumos de execucao. O modo simulado usa fixtures e zero internet; o modo real abre um Chrome visivel para login manual assistido e mantem o token somente em memoria.

## Preparação em outro computador

```powershell
git clone <REPOSITORIO>
cd conciliacaoCartoes
.\scripts\preparar_ambiente.ps1
```

## Premissas definitivas

- O periodo informado representa a data da venda; para debito, a consulta e o matching usam a data de recebimento da operadora.
- Em credito e Pix, a API e comparada por `dataCadastro` (data da venda). Em debito, ela e comparada por `dataVencimento` (data de recebimento).
- A saida Cielo da primeira versao tera apenas a aba `Planilha1`, seguindo o modelo LEO.
- Na QuickPay, os recebimentos bancarios podem ser informados em uma planilha auxiliar agregada por data de recebimento, bandeira e modalidade; ela e gerada a partir dos valores confirmados pelo usuario no chat.
- Tokens nunca devem ser salvos no repositorio, em logs ou em arquivos de configuracao versionados.
- Arquivos reais de entrada, respostas brutas da API, logs e saidas geradas ficam fora do Git.

## CLI

Gerar somente o relatorio Cielo:

```powershell
conciliacao gerar-cielo `
  --arquivo "data/input/cielo.xlsx" `
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
  --arquivo "data/input/quickpay.xlsx" `
  --arquivo-recebimentos-quickpay "output/RECEBIMENTOS_BANCARIOS_QUICKPAY.xlsx" `
  --data-inicio 2026-07-13 `
  --data-fim 2026-07-13 `
  --saida "output/quickpay"
```

O QuickPay aceita XLSX e arquivos HTML exportados com extensao `.xls`. Quando o relatorio nao tiver o valor bancario por venda, informe os totais confirmados no chat e gere a planilha auxiliar com `gerar-recebimentos-quickpay`. A conciliacao bancaria e feita por grupo de data de recebimento, bandeira e modalidade, e aparece na aba `Conciliação Bancária` do relatorio final. Arquivos antigos que ja possuem `RECEBIDO NO BANCO QUICKPAY` por venda continuam aceitos.

Formato para informar cada grupo no chat: `YYYY-MM-DD|Bandeira|Modalidade|Valor`. Exemplo: `2026-07-20|Visa|credito|1250,32`.

O pipeline gera a planilha auxiliar assim:

```powershell
conciliacao gerar-recebimentos-quickpay --saida "output" --recebimento "2026-07-20|Visa|credito|1250,32"
```

Exemplo de entrada QuickPay legada (ainda aceita):

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

No workflow integrado, `Sistema`, `Diferenca Sistema` e `Status` sao preenchidos a partir do matching com a API Velo. Nos comandos isolados `gerar-quickpay`, essas colunas permanecem no comportamento anterior.

Organizacao da aba `Conciliação` QuickPay:

- As linhas sao ordenadas por data da venda e modalidade, seguindo o padrao visual da Cielo.
- `Soma Valor da Venda` e `Soma Valor Líquido` mostram o subtotal no fim de cada bloco continuo de **data da venda + modalidade**. A bandeira nao cria um novo subtotal.
- A linha `TOTAL` soma tambem `Sistema` e `Diferenca Sistema`.
- Credito usa os tons de cinza da Cielo, debito usa turquesa e Pix usa amarelo-claro.

Quando `Valor da Venda` for zero, a porcentagem fica em branco e a validacao gera aviso. Diferencas de centavos entre `Taxa` e `Bruto-Liquido` sao preservadas; taxa negativa ou taxa maior que o valor da venda bloqueiam a geracao.

Validar arquivos sem gerar Excel:

```powershell
conciliacao validar-cielo `
  --arquivo "data/input/cielo.xlsx" `
  --data-inicio 2026-07-14 `
  --data-fim 2026-07-15
```

Simular a integracao Velo sem internet:

```powershell
conciliacao testar-integracao-velo `
  --fixtures "tests/fixtures/api" `
  --data-inicio 2026-07-14 `
  --data-fim 2026-07-15
```

Esse comando usa somente fixtures anonimizadas, nao exige token real, nao acessa rede e valida os schemas da API. A saida informa `Chamadas reais realizadas: 0`.

Executar o workflow integrado em modo real. O Chrome sera aberto e o usuario deve concluir o login antes de a conciliacao continuar:

```powershell
conciliacao processar `
  --data-inicio 2026-07-13 `
  --data-fim 2026-07-13 `
  --arquivo-cielo "data/input/cielo.xlsx" `
  --arquivo-quickpay "data/input/quickpay.xlsx" `
  --saida "output" `
  --salvar-auditoria
```

O token nunca e solicitado, exibido ou aceito como argumento. O Chrome pode preencher credenciais salvas pelo proprio navegador, mas o usuario confirma o login. O token capturado permanece somente em memoria e e descartado ao final.

Executar o workflow integrado em modo simulado:

```powershell
conciliacao processar `
  --modo-simulado `
  --fixtures-api "tests/fixtures/api" `
  --data-inicio 2026-07-13 `
  --data-fim 2026-07-13 `
  --arquivo-cielo "tests/fixtures/cielo/cielo_valido.xlsx" `
  --arquivo-quickpay "tests/fixtures/quickpay/quickpay_valido.xlsx" `
  --saida "output/simulacao" `
  --salvar-auditoria
```

Pelo menos um arquivo de operadora deve ser informado. Cielo e QuickPay sao processadas de forma independente: se uma falhar na leitura, validacao ou exportacao, a outra ainda pode concluir.

Codigos de saida do `processar`:

- `0`: sucesso total.
- `1`: falha global.
- `2`: sucesso parcial.
- `3`: falha de validacao sem nenhuma operadora concluida.
- `4`: falha de autenticacao Velo.
- `5`: falha de integracao Velo.

Arquivos gerados pelo workflow:

```text
planilhas/<DATA_DA_CONCILIACAO>/cielo/CIELO_CONCILIACAO_<PERIODO>.xlsx
output/cielo/CIELO_CONCILIACAO_<PERIODO>_RESULTADO.json
planilhas/<DATA_DA_CONCILIACAO>/quickpay/QUICKPAY_CONCILIACAO_<PERIODO>.xlsx
output/quickpay/QUICKPAY_CONCILIACAO_<PERIODO>_RESULTADO.json
output/execucoes/<IDENTIFICADOR_EXECUCAO>/resumo.json
output/execucoes/<IDENTIFICADOR_EXECUCAO>/resumo.txt
logs/conciliacao_<IDENTIFICADOR_EXECUCAO>.log
data/api_raw/<IDENTIFICADOR_EXECUCAO>/*.json
```

`<DATA_DA_CONCILIACAO>` e a data em que o workflow foi executado, no formato
`YYYY-MM-DD`. Use `--diretorio-planilhas` somente se for necessario alterar a
pasta-raiz `planilhas`.

Os hashes SHA-256 dos arquivos de entrada sao calculados antes e depois do processamento. Se um hash mudar, a execucao daquela operadora falha.

## Integracao Velo

A configuracao fica em `config/velo_api.yaml`. A base URL configurada e:

```text
https://api.v1.velosistema.com.br
```

Endpoints modelados nesta etapa:

- `GET /autoCompletarOperadora`
- `GET /listarConciliacaoCartaoRecebido`

Autenticacao:

- No modo real, o fluxo abre Chrome visivel e observa somente a validacao concluida pelo usuario.
- O token permanece em memoria durante a execucao e e descartado ao final.
- O token nao pode ser salvo em YAML, logs, fixtures, auditoria ou mensagens de erro.
- O cliente monta internamente `Authorization: Bearer <TOKEN>` e `Accept: application/json`.
- `VELO_BEARER_TOKEN` permanece apenas como compatibilidade tecnica para testes controlados fora do fluxo padrao.

Parametros enviados para conciliacao:

```text
operadoraId=<filtro_forma_recebimento_id>
intervaloDia=-1
dataInicio=YYYY-MM-DD
dataFim=YYYY-MM-DD
isCompensado=0
```

Particularidade: o parametro HTTP se chama `operadoraId`, mas os valores observados correspondem aos IDs de formas de recebimento. Internamente o projeto usa o nome `filtro_forma_recebimento_id`.

IDs de fallback configurados:

- Cielo credito: `81`
- Cielo debito: `86`
- Cielo Pix: `91`
- QuickPay credito: `44`
- QuickPay debito: `51`
- QuickPay Pix: `42`

A resolucao tenta primeiro `/autoCompletarOperadora`, normaliza nomes, aceita variacoes controladas como `QuickPay`/`Quickpay` e o erro conhecido `Cartao de Dedido - Quickpay`, e usa fallback configurado com aviso quando a modalidade esperada nao aparece.

Auditoria:

- Quando habilitada, respostas brutas sao salvas em `data/api_raw/<DATA_HORA_EXECUCAO>/`.
- `metadata.json` registra periodo, `intervalo_dia`, `is_compensado` e categorias solicitadas.
- Bearer Token, `Authorization`, cookies e cabecalhos completos nunca sao salvos.
- A escrita e atomica: arquivo temporario primeiro, renomeacao depois de JSON valido.

Erros tratados:

- `400`: parametros invalidos.
- `401`: token Bearer ausente, invalido ou expirado.
- `403`: acesso negado.
- `404`: endpoint nao encontrado.
- `429`: limite de requisicoes.
- `500` a `599`: erro da API.
- Timeout, falha de conexao, resposta nao JSON e contrato invalido.

Os testes bloqueiam sockets reais e usam transporte fake. Retentativas permanecem desabilitadas por padrao.

## Matching e conciliacao

A Etapa 8 implementa matching local, deterministico e sem internet entre:

```text
valor bruto da operadora
versus
valor do sistema Velo
```

A chave principal usa:

```text
operadora + modalidade + data aplicavel + valor
```

A bandeira entra somente quando existe de forma confiavel nos dois lados. A API ainda nao traz NSU, TID, codigo de autorizacao ou horario; por isso o projeto nao promete pareamento transacional exato quando a chave nao prova a identidade da linha. Nesses casos, o resultado pode ser agregado.

Regras principais:

- Cielo nunca combina com QuickPay.
- Credito, debito e Pix nao combinam entre si.
- Em credito e Pix, a data principal e `dataVenda` da operadora contra `dataCadastro` do sistema.
- Em debito, a data principal e `dataRecebimento` da operadora contra `dataVencimento` do sistema. Sem data de recebimento, o resultado fica `PENDENTE_DE_DADOS`.
- Hora da operadora nao entra na chave, porque a API nao fornece horario.
- `valorTaxaCartao`, taxa, valor liquido e recebido no banco QuickPay nao entram na chave.
- Valores repetidos sao tratados como multiconjunto.
- Nenhum registro do sistema e consumido duas vezes.
- Qualquer diferenca de R$ 0,01 e preservada; tolerancia monetaria e `R$ 0,00`.
- Categoria nao consultada gera `PENDENTE_DE_DADOS`; categoria consultada com resposta vazia pode gerar `NAO_ENCONTRADO_NO_SISTEMA`.

Status possiveis:

- `CONCILIADO`
- `DIVERGENCIA_DE_VALOR`
- `DIVERGENCIA_DE_QUANTIDADE`
- `NAO_ENCONTRADO_NO_SISTEMA`
- `NAO_ENCONTRADO_NA_OPERADORA`
- `CORRESPONDENCIA_AMBIGUA`
- `PENDENTE_DE_DADOS`

Simular matching sem internet:

```powershell
conciliacao testar-matching `
  --operadora cielo `
  --fixtures "tests/fixtures/matching"
```

```powershell
conciliacao testar-matching `
  --operadora quickpay `
  --fixtures "tests/fixtures/matching" `
  --sistema-extra
```

O comando usa fixtures artificiais, nao exige token, nao acessa rede, nao altera Excel e imprime um resumo textual.

## Limitacoes atuais

- Nao ha conciliacao automatica com o sistema.
- A saida Cielo mantem a aba principal. A QuickPay usa somente `Conciliação` quando o valor bancario vier por venda; quando vier da planilha auxiliar, inclui `Conciliação Bancária` com a comparação agregada.
- A Etapa 10 ainda precisa homologar o workflow com dados reais e token temporario autorizado.
- A API continua estritamente somente leitura; nao ha compensacao, alteracao de caixa nem escrita no ERP.

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

## Dados locais

Use estas pastas para execucoes locais:

- `data/input/`: arquivos de entrada reais.
- `data/api_raw/`: respostas brutas da API, sem token.
- `planilhas/`: relatorios Excel finais gerados pelo workflow.
- `output/`: resumos JSON, logs auxiliares e planilhas auxiliares QuickPay.
- `logs/`: logs de execucao.

Essas pastas sao ignoradas pelo Git, exceto pelos arquivos `.gitkeep`.
