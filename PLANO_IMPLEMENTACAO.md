# Plano de Implementação - Automação de Conciliação de Caixa

## 1. Escopo desta etapa

Esta etapa é apenas de entendimento e planejamento. Não foram feitas requisições reais à API, não foram alterados os arquivos Excel de exemplo e não foram armazenadas credenciais, tokens ou respostas de API.

Arquivos analisados:

- `ARQUITETURA_AUTOMACAO_CONCILIACAO_CAIXA.md`
- `arquivos_exemplo/CIELO VENDA 11.07.2026, 12.07.2026 E 13.07.2026 RECEBIMENTO 13.07.2026 .xls.xlsx`
- `arquivos_exemplo/CIELO VENDA 11.07.2026, 12.07.2026 E 13.07.2026 RECEBIMENTO 13.07.2026 LEO .xls.xlsx`
- `arquivos_exemplo/Lista de Transações.20260714094607.xls`
- `arquivos_exemplo/QUICKPAY VENDA 13.07.2026 RECEBIMENTO 14.07.2026 .xls.xlsx`

## 2. Entendimento do fluxo

O sistema deverá receber um período explícito, um token Bearer temporário e arquivos de entrada da Cielo e da QuickPay. Com esses dados, deverá consultar a API do sistema da empresa em modo somente leitura, obter os registros de caixa por forma de recebimento, preservar as respostas brutas para auditoria e comparar os valores das operadoras com os valores registrados no sistema.

A conciliação principal é administrativa: o valor bruto informado pela operadora deve bater com o valor registrado no caixa. A comparação inicial não terá identificadores fortes como NSU, TID ou código de autorização vindos da API, então deverá trabalhar por combinação de operadora, modalidade, data, valor e quantidade de ocorrências. Valores repetidos devem ser tratados como multiconjunto, para evitar que uma mesma ocorrência seja usada duas vezes.

Cielo e QuickPay devem ser processadas de forma independente. Uma falha de validação em uma operadora não deve impedir a geração do arquivo da outra, desde que os dados da outra estejam válidos. O resultado esperado da primeira versão são dois arquivos Excel separados, logs de execução, respostas brutas da API e resumo de erros/divergências.

## 3. Observações dos arquivos de exemplo

### 3.1 Cielo bruto

O arquivo bruto da Cielo possui uma aba chamada `Recebiveis_cielo_detalhe1`, com 62 linhas e 59 colunas. O cabeçalho transacional começa na linha 10 e os lançamentos vão da linha 11 à linha 62, totalizando 52 transações.

Totais observados no próprio arquivo:

- Quantidade de lançamentos: 52
- Valor bruto: `R$ 4.356,81`
- Taxa/tarifa: `-R$ 67,69`
- Valor líquido: `R$ 4.289,12`

Distribuição observada:

- `Venda Pix`: 33 lançamentos
- `Venda crédito`: 11 lançamentos
- `Venda débito`: 8 lançamentos
- Datas de pagamento: 29 lançamentos em `11/07/2026`, 19 em `12/07/2026` e 4 em `13/07/2026`

O bruto possui muitas colunas úteis para auditoria, mas a saída LEO usa apenas um subconjunto: data de pagamento, data da venda, hora da venda, tipo de lançamento, forma de pagamento, bandeira, valor bruto, taxa/tarifa e valor líquido.

### 3.2 Cielo modelo LEO

O arquivo LEO possui uma aba `Planilha1`, com 57 linhas e 13 colunas. A linha 1 contém o título manual, a linha 2 contém os cabeçalhos e as transações ficam entre as linhas 3 e 54. A linha 55 contém os totais gerais.

O modelo preserva as 52 transações e os totais do arquivo bruto:

- Valor bruto: `4.356,81`
- Taxa/tarifa: `-67,69`
- Valor líquido: `4.289,12`

Padrões observados:

- A fórmula de percentual é `=1-(Ilinha/Glinha)`.
- Existem subtotais auxiliares nas colunas K e L.
- Os subtotais aparecem no fim de blocos: linhas 13, 21 e 54.
- A linha 55 soma as colunas G, H e I.
- O layout tem preenchimento amarelo no título e no cabeçalho.
- A ordenação não é simplesmente "todo crédito, depois todo débito, depois Pix": crédito e débito aparecem agrupados por datas de pagamento/venda no início, e Pix aparece em bloco separado depois.

### 3.3 QuickPay bruto em `.xls`

O arquivo `Lista de Transações.20260714094607.xls` não é um Excel binário tradicional. Ele é um arquivo HTML com extensão `.xls`, contendo uma tabela com 2 transações.

Colunas encontradas:

- `Data da venda`
- `Data de recebimento`
- `Número de Parcelas`
- `Tipo de pagamento`
- `Valor da Venda`
- `Valor líquido`
- `Taxa`
- `Bandeira`

Transações observadas:

- `13/07/2026 11:35`, recebimento `14/07/2026 00:00`, crédito, valor `126,83`, líquido `121,77`, taxa `5,03`, bandeira Visa.
- `13/07/2026 11:05`, recebimento `14/07/2026 00:00`, crédito, valor `194,00`, líquido `186,26`, taxa `7,69`, bandeira MasterCard.

### 3.4 QuickPay trabalhado manualmente

O arquivo QuickPay trabalhado possui uma aba `Lista de Transações.20260714094`, com 10 linhas e 14 colunas. A linha 2 contém a tabela principal.

Cabeçalhos observados na tabela principal:

- `Data da venda`
- `Data de recebimento`
- `Número de Parcelas`
- `Bandeira`
- `Tipo de pagamento`
- `Valor da Venda`
- `Taxa`
- `Valor líquido`
- `Bruto-Liquido`
- `Diferença`
- `Porcentagem`
- `Soma tipo Bruto`
- `Sistema`
- `Diferença`

As fórmulas manuais seguem o padrão:

- `Bruto-Liquido`: `=F-H`
- `Diferença`: `=G-I`
- `Porcentagem`: `=1-(H/F)`

Totais observados:

- Valor da venda: `320,83`
- Taxa: `12,72`
- Valor líquido: `308,03`
- Bruto - líquido: `12,80`
- Diferença: `-0,08`

A informação `RECEBIDO NO BANCO QUICKPAY` aparece no arquivo, mas não como coluna transacional da tabela principal. Ela aparece na célula K7, com valores nas células K8 e K9, e total em K10. Isso conflita com a regra do documento, que exige uma coluna exatamente com esse nome preenchida em todas as linhas de transação.

## 4. Contradições, lacunas e regras ambíguas

### 4.1 Período: venda, pagamento ou recebimento

O documento exige `dataInicio` e `dataFim`, mas os exemplos misturam datas de venda, pagamento e recebimento. No Cielo bruto, o filtro é `Data de pagamento: 11/07/2026 à 13/07/2026`, enquanto algumas vendas são de `10/07/2026`. No nome do arquivo consta "VENDA 11.07.2026, 12.07.2026 E 13.07.2026 RECEBIMENTO 13.07.2026", mas o conteúdo tem pagamentos em 11, 12 e 13.

Decisão pendente: definir se o período informado pelo usuário filtra data da venda, data de pagamento, data de recebimento, `dataCadastro` da API ou `dataVencimento` da API.

### 4.2 QuickPay: coluna obrigatória vs exemplo real

O documento exige a coluna `RECEBIDO NO BANCO QUICKPAY` exatamente uma vez e preenchida em todas as linhas de transação. O exemplo trabalhado possui essa informação fora da tabela principal, como um bloco manual. A primeira versão precisa escolher entre rejeitar esse formato ou aceitá-lo como legado e convertê-lo para uma coluna transacional normalizada.

### 4.3 QuickPay: ordem e nomes de colunas de saída

O documento lista colunas mínimas como `Código`, `Operadora`, `Cartão`, `Pré-datado`, `Recebido`, `Valor`, `Valor líquido`, `Valor taxa`, etc. O exemplo real usa outra estrutura: data da venda, data de recebimento, parcelas, bandeira, tipo de pagamento, valor da venda, taxa e valor líquido. Ainda falta o mapeamento exato entre esses nomes.

### 4.4 Cielo: "separar crédito, débito e Pix"

O documento manda separar crédito, débito e Pix. O modelo LEO não usa abas separadas; ele agrupa linhas na mesma planilha e inclui subtotais em pontos específicos. Também há crédito e débito em mais de um bloco antes do bloco Pix. A regra de ordenação precisa ser explicitada.

### 4.5 Abas extras vs modelo LEO

O documento sugere abas `Conciliação`, `Dados Originais` e `Alertas`. O modelo LEO analisado tem apenas `Planilha1`. A implementação precisa decidir se a saída deve manter visualmente uma aba principal como o LEO e adicionar abas novas, ou se deve reproduzir exatamente o arquivo LEO sem abas auxiliares.

### 4.6 Formatos de entrada

Os exemplos usam extensões não padronizadas:

- Cielo: `.xls.xlsx`, mas é um `.xlsx` válido.
- QuickPay bruto: `.xls`, mas é HTML.
- QuickPay trabalhado: `.xls.xlsx`, mas é `.xlsx` válido.

O leitor de arquivos deve detectar o formato pelo conteúdo, não apenas pela extensão.

### 4.7 Normalização de texto

Há espaços não separáveis (`NBSP`) em cabeçalhos da QuickPay e variações de escrita como `MasterCard` vs `Mastercard`. O endpoint de autocomplete também pode retornar texto com erro, como `Cartão de Dédido - Quickpay`. A normalização deve remover acentos, espaços extras e diferenças de caixa, mas sem esconder ambiguidades.

### 4.8 Sinal da taxa

Na Cielo, a taxa aparece negativa. Na QuickPay, a taxa aparece positiva. O domínio interno deve definir uma convenção única, por exemplo `valor_taxa` sempre positivo para cálculo, preservando também o valor original para auditoria.

### 4.9 API sem identificadores fortes

O documento diz que a API não retorna NSU, TID, horário ou autorização. Os arquivos de operadora podem conter alguns desses campos, mas eles não ajudam na comparação com a API se não existirem do lado do sistema. A primeira versão deve ser clara ao marcar correspondências por agregado e evitar prometer pareamento transacional exato.

### 4.10 Status de divergência de valor

Sem identificador transacional forte, "divergência de valor" pode ser difícil de afirmar linha a linha. Em muitos casos, o resultado mais correto será "não encontrado no sistema", "não encontrado na operadora" ou "divergência de quantidade" por grupo/valor.

### 4.11 Sobreposição e duplicidade em múltiplos arquivos

O documento menciona múltiplos arquivos, mas não define o que é duplicidade de transação. Para Cielo, poderia usar código da venda, NSU/DOC, TID ou combinação de data/hora/valor/bandeira. Para QuickPay, o exemplo não possui código único.

### 4.12 Respostas brutas da API e versionamento

As respostas brutas devem ser salvas para auditoria, mas não devem ir para o Git se puderem conter dados sensíveis do caixa. A estrutura final precisa de `.gitignore` cobrindo `data/api_raw/`, `data/input/`, `output/` e `logs/`, mantendo apenas fixtures anonimizadas em `tests/fixtures/`.

### 4.13 Validação de centavos com Excel

O documento exige considerar qualquer centavo de diferença. A implementação não deve depender de `float` para regra financeira; deve usar `Decimal` em Python e fórmulas auditáveis no Excel gerado.

### 4.14 Fallback de IDs da API

O documento sugere buscar IDs dinamicamente e usar valores fixos como fallback. Falta definir quando o fallback é permitido: sempre, somente com alerta ou somente em modo explicitamente configurado.

## 5. Estrutura final proposta do repositório

```text
conciliacaoCartoes/
|-- AGENTS.md
|-- README.md
|-- PLANO_IMPLEMENTACAO.md
|-- pyproject.toml
|-- .gitignore
|-- .env.example
|
|-- config/
|   |-- geral.yaml
|   |-- cielo.yaml
|   |-- quickpay.yaml
|   `-- velo_api.yaml
|
|-- data/
|   |-- input/              # arquivos reais de entrada, ignorados pelo Git
|   |-- api_raw/            # respostas brutas da API, ignoradas pelo Git
|   |-- processed/          # intermediários de execução, ignorados pelo Git
|   `-- archive/            # cópias arquivadas quando necessário, ignoradas pelo Git
|
|-- output/
|   |-- cielo/
|   `-- quickpay/
|
|-- logs/
|
|-- src/
|   `-- conciliacao/
|       |-- __init__.py
|       |-- cli.py
|       |-- workflow.py
|       |
|       |-- domain/
|       |   |-- models.py
|       |   |-- enums.py
|       |   `-- exceptions.py
|       |
|       |-- config/
|       |   `-- loader.py
|       |
|       |-- integrations/
|       |   `-- velo/
|       |       |-- client.py
|       |       |-- endpoints.py
|       |       |-- mapper.py
|       |       `-- schemas.py
|       |
|       |-- readers/
|       |   |-- excel_format_detector.py
|       |   |-- cielo_reader.py
|       |   `-- quickpay_reader.py
|       |
|       |-- processors/
|       |   |-- cielo_processor.py
|       |   `-- quickpay_processor.py
|       |
|       |-- matching/
|       |   |-- keys.py
|       |   |-- normalizer.py
|       |   |-- multiset_matcher.py
|       |   `-- reconciliation.py
|       |
|       |-- validators/
|       |   |-- common_validator.py
|       |   |-- cielo_validator.py
|       |   |-- quickpay_validator.py
|       |   `-- api_validator.py
|       |
|       |-- exporters/
|       |   |-- excel_exporter.py
|       |   |-- cielo_exporter.py
|       |   |-- quickpay_exporter.py
|       |   `-- styles.py
|       |
|       `-- utils/
|           |-- currency.py
|           |-- dates.py
|           |-- file_hash.py
|           `-- logging.py
|
|-- tests/
|   |-- fixtures/
|   |   |-- cielo/
|   |   |-- quickpay/
|   |   `-- api/
|   |-- unit/
|   `-- integration/
|
`-- scripts/
    |-- processar.ps1
    `-- processar.bat
```

Notas sobre a estrutura:

- `arquivos_exemplo/` pode permanecer como referência manual, mas os testes devem usar cópias mínimas e anonimizadas em `tests/fixtures/`.
- `data/`, `output/` e `logs/` devem ser ignorados pelo Git.
- `src/conciliacao/integrations/velo/client.py` deve ter modo de teste com mocks e não deve executar chamadas reais em testes unitários.
- O token deve vir de variável de ambiente e nunca ser persistido.

## 6. Etapas pequenas de implementação

### Etapa 0 - Validação deste plano

- Confirmar decisões pendentes listadas neste documento.
- Definir regras exatas de data, layout e QuickPay.
- Não implementar integração real antes dessas confirmações.

### Etapa 1 - Base do projeto

- Criar `pyproject.toml`, `.gitignore`, `.env.example`, `README.md` e `AGENTS.md`.
- Criar estrutura de pastas.
- Configurar `ruff`, `pytest` e comando CLI mínimo.
- Criar configuração YAML sem credenciais.

### Etapa 2 - Modelos e utilitários financeiros

- Criar modelos internos para transação de operadora, registro do sistema, alerta e resultado de conciliação.
- Implementar normalização de moeda com `Decimal`.
- Implementar normalização de texto com remoção de acentos, `NBSP`, caixa e espaços extras.
- Implementar utilitário de hash dos arquivos originais.

### Etapa 3 - Leitores em modo somente leitura

- Implementar detector de formato por assinatura/conteúdo.
- Implementar leitor Cielo `.xlsx`.
- Implementar leitor QuickPay `.xlsx`.
- Implementar leitor QuickPay HTML com extensão `.xls`.
- Garantir que os arquivos de entrada nunca sejam salvos ou alterados.

### Etapa 4 - Validações dos arquivos

- Validar cabeçalhos obrigatórios da Cielo.
- Validar contagem, totais e linhas transacionais da Cielo.
- Validar a regra final escolhida para `RECEBIDO NO BANCO QUICKPAY`.
- Retornar erros com arquivo, aba, linha, coluna e célula quando possível.

### Etapa 5 - Processamento Cielo sem API

- Reproduzir o layout principal do modelo LEO.
- Preservar todas as transações.
- Calcular percentual por linha.
- Calcular subtotais e total geral.
- Criar aba de dados originais e alertas, se confirmado.
- Testar que os totais batem com o arquivo bruto.

### Etapa 6 - Processamento QuickPay sem API

- Gerar a tabela de conciliação com as colunas finais aprovadas.
- Calcular bruto-líquido, diferença e porcentagem.
- Incluir o valor recebido no banco conforme regra validada.
- Testar erros de coluna ausente, valor vazio, valor inválido e fórmula com erro.

### Etapa 7 - Cliente Velo com testes mockados

- Implementar cliente HTTP somente leitura.
- Implementar tratamento de `401`, `403`, `400`, `500`, timeout e resposta não JSON.
- Implementar autocomplete e fallback configurável.
- Salvar respostas brutas sem token.
- Criar testes com fixtures JSON, sem chamadas reais.

### Etapa 8 - Matching e conciliação

- Implementar agrupamento por operadora, modalidade, data, valor e quantidade.
- Implementar multiconjunto para valores repetidos.
- Registrar sobras do sistema e da operadora.
- Marcar correspondências ambíguas sem inventar pareamento.

### Etapa 9 - Workflow integrado

- Orquestrar API, Cielo e QuickPay.
- Manter processamento independente por operadora.
- Gerar logs sem dados sensíveis.
- Gerar resumo final com arquivos criados, erros e divergências.

### Etapa 10 - Homologação com dados reais

- Executar com token real somente quando autorizado.
- Comparar saídas com o processo manual.
- Ajustar layout Cielo ao padrão LEO.
- Validar regras de data e matching com casos reais.

## 7. Decisões que precisam ser validadas antes da implementação

1. O período informado deve representar data da venda, data de pagamento, data de recebimento, `dataCadastro` ou `dataVencimento`?
2. No Cielo, a saída deve filtrar pelo período de pagamento ou pelo período de venda?
3. No Cielo, a aba principal deve se chamar `Planilha1`, como no LEO, ou `Conciliação`, como no documento?
4. A saída Cielo deve adicionar abas `Dados Originais` e `Alertas`, mesmo que o modelo LEO não tenha essas abas?
5. Qual é a regra exata de ordenação dos blocos Cielo: reproduzir a ordem do LEO, ordenar por data/tipo, ou separar estritamente crédito, débito e Pix?
6. Os subtotais da Cielo devem seguir exatamente os blocos do LEO ou devem ser recalculados por modalidade?
7. A coluna `RECEBIDO NO BANCO QUICKPAY` deve obrigatoriamente estar na tabela transacional, ou o formato manual do exemplo, com valores em bloco separado, deve ser aceito?
8. Se o formato manual do QuickPay for aceito, qual regra associa K8/K9 às transações da linha 3/4?
9. Quais são os nomes finais das colunas QuickPay: os do documento ou os do exemplo trabalhado?
10. O campo `Sistema` no exemplo QuickPay corresponde a `Valor no sistema`?
11. A comparação com a API deve usar `dataCadastro` ou `dataVencimento` como data do caixa?
12. O fallback de IDs da API pode ser usado automaticamente quando o autocomplete falhar, ou deve exigir confirmação/alerta?
13. As respostas brutas da API podem conter dados sensíveis suficientes para exigir criptografia local, ou basta mantê-las fora do Git?
14. Como identificar duplicidade em múltiplos arquivos QuickPay se não houver código único?
15. A taxa deve ser armazenada internamente sempre positiva, mesmo quando a Cielo vem com taxa negativa?
16. Em casos sem identificador único, o status deve ser por transação, por grupo agregado ou ambos?
17. Os arquivos de exemplo atuais podem ser copiados para fixtures de teste, ou será necessário criar fixtures anonimizadas?
