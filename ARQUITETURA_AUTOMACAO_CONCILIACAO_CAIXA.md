# Arquitetura da Automação de Conciliação de Caixa

## 1. Visão geral

Este projeto tem como objetivo automatizar o processo de conciliação do caixa da empresa com base em três fontes de dados:

1. Relatório da Cielo.
2. Relatório da QuickPay.
3. Dados do sistema da empresa, obtidos por API.

Atualmente, um funcionário dedica aproximadamente 13 horas semanais a esse fluxo. A automação deve reduzir o trabalho manual, preservar os arquivos originais, identificar divergências e gerar dois arquivos Excel finais:

- `CIELO_CONCILIACAO_<PERIODO>.xlsx`
- `QUICKPAY_CONCILIACAO_<PERIODO>.xlsx`

A primeira versão deve ser enxuta e focada apenas nas informações necessárias para reproduzir o fluxo atual, principalmente o padrão da planilha Cielo com final `LEO` e a planilha QuickPay já trabalhada manualmente.

---

## 2. Objetivos

A solução deve:

- Receber um arquivo da Cielo.
- Receber um arquivo da QuickPay.
- Receber datas explícitas de início e fim.
- Receber um Bearer Token válido.
- Consultar a API do sistema da empresa.
- Comparar os valores das operadoras com os valores registrados no caixa.
- Gerar dois arquivos Excel separados.
- Preservar integralmente os arquivos de entrada.
- Processar Cielo e QuickPay de forma independente.
- Informar erros de forma clara, incluindo linha, coluna e célula quando possível.
- Nunca inventar valores ausentes.
- Nunca alterar os arquivos originais.
- Nunca escrever ou alterar dados no sistema da empresa.

---

## 3. Escopo da primeira versão

A primeira versão deve contemplar apenas:

1. Integração autenticada com a API da empresa.
2. Leitura dos relatórios Cielo e QuickPay.
3. Processamento das informações necessárias.
4. Comparação com os dados do sistema.
5. Geração do Excel da Cielo no padrão LEO.
6. Geração do Excel da QuickPay no formato definido neste documento.
7. Validações de consistência.
8. Tratamento independente de erros por operadora.
9. Logs de execução.
10. Testes automatizados.

Não faz parte desta primeira versão:

- Interface gráfica.
- Dashboard.
- Agendamento automático.
- Envio por e-mail.
- Banco de dados.
- Sistema de usuários.
- Histórico visual de conciliações.
- Integração com outras operadoras.
- Alteração de registros no ERP.
- Marcação de transações como compensadas.
- Escrita na API da empresa.

---

## 4. Fluxo operacional

### 4.1 Fluxo padrão

```text
Usuário informa o período
        ↓
Usuário fornece o Bearer Token
        ↓
Usuário fornece o arquivo Cielo
        ↓
Usuário fornece o arquivo QuickPay
        ↓
Sistema consulta a API da empresa
        ↓
Sistema processa Cielo
        ↓
Sistema processa QuickPay
        ↓
Sistema compara os valores com o caixa
        ↓
Sistema valida os resultados
        ↓
Sistema gera dois arquivos Excel
        ↓
Sistema exibe resumo e erros
```

### 4.2 Regra do período

Normalmente, o período processado será:

- De terça-feira a sexta-feira: o dia anterior.
- Na segunda-feira: sexta-feira, sábado e domingo.

Mesmo assim, o período deve ser sempre informado explicitamente pelo usuário, por comando ou pelo chat do Codex.

Exemplos:

```text
Processar de 2026-07-15 até 2026-07-15
```

```text
Processar de 2026-07-10 até 2026-07-12
```

O script deve:

1. Exigir `dataInicio`.
2. Exigir `dataFim`.
3. Ler as datas presentes nos arquivos.
4. Comparar as datas encontradas com o período solicitado.
5. Emitir erro ou alerta quando houver incompatibilidade.

---

## 5. Integração com a API da empresa

### 5.1 Base URL

```text
https://api.v1.velosistema.com.br
```

### 5.2 Autenticação

A API utiliza Bearer Token.

Cabeçalhos HTTP mínimos:

```http
Authorization: Bearer <TOKEN>
Accept: application/json
```

O token:

- Não deve ser salvo no código.
- Não deve ser salvo no Git.
- Não deve ser salvo em arquivos de configuração versionados.
- Pode ser informado por variável de ambiente.
- Pode ser informado ao Codex no momento da execução.
- Deve permanecer apenas durante a execução.
- Nunca deve aparecer em logs.

Exemplo com variável de ambiente no PowerShell:

```powershell
$env:VELO_BEARER_TOKEN="TOKEN_AQUI"
```

### 5.3 Endpoint de formas de recebimento

```http
GET /autoCompletarOperadora
```

Esse endpoint retorna as formas de recebimento disponíveis.

IDs observados:

| Modalidade | ID usado no filtro |
|---|---:|
| Cartão de Crédito - Cielo | 81 |
| Cartão de Débito - Cielo | 86 |
| Pix - Cielo | 91 |
| Cartão de Crédito - Quickpay | 44 |
| Cartão de Débito - Quickpay | 51 |
| Pix - Quickpay | 42 |

Observação importante:

O parâmetro da API se chama `operadoraId`, mas os valores observados correspondem ao `formaRecebimentoId` retornado pelo endpoint de autocomplete.

Internamente, o projeto deve usar um nome mais claro, como:

```python
filtro_forma_recebimento_id
```

O código deve preferencialmente:

1. Consultar `/autoCompletarOperadora`.
2. Localizar as modalidades por nome.
3. Obter dinamicamente os IDs.
4. Usar valores fixos apenas como fallback de configuração.

A identificação textual deve ser tolerante a:

- Diferenças de maiúsculas e minúsculas.
- Acentuação.
- Espaços extras.
- Pequenos erros de escrita.

Exemplo observado na API:

```text
Cartão de Dédito - Quickpay
```

### 5.4 Endpoint de conciliação

```http
GET /listarConciliacaoCartaoRecebido
```

Parâmetros:

```text
operadoraId
intervaloDia
dataInicio
dataFim
isCompensado
```

Configuração inicial:

```yaml
intervaloDia: -1
isCompensado: 0
```

Exemplo:

```http
GET /listarConciliacaoCartaoRecebido?operadoraId=91&intervaloDia=-1&dataInicio=2026-07-15&dataFim=2026-07-15&isCompensado=0
```

A primeira versão deve manter `intervaloDia=-1` e `isCompensado=0` configuráveis, pois o significado exato ainda não está documentado.

### 5.5 Campos necessários da resposta

Usar inicialmente apenas:

```text
contaPacotePagamentoUnicoId
operadoraId
operadora
cadastroCaixaId
formaRecebimentoId
formaRecebimento
tipoCartao
valor
valorTaxaCartao
dataVencimento
dataCadastro
```

Campos a ignorar na transformação principal:

```text
elevaUsuarioId
elevaEmpresaId
acao
forcarAcao
totalRegistros
categoriaTaxaId
centroCustoTaxaId
```

O campo `valorTaxaCartao` deve ser preservado na resposta bruta, mas não será usado como referência principal, pois nos exemplos aparece como `0.00`.

### 5.6 Modelo interno mínimo

```python
{
    "id_sistema": "18888",
    "operadora": "Pix - Cielo",
    "forma_recebimento": "PIX - Cielo",
    "tipo_cartao": 5,
    "valor": 2.90,
    "data_vencimento": "2026-07-15",
    "data_cadastro": "2026-07-15"
}
```

### 5.7 Tratamento de erros HTTP

Comportamentos esperados:

- `401 Unauthorized`: token inválido ou expirado.
- `403 Forbidden`: acesso negado.
- `400 Bad Request`: parâmetros inválidos.
- `500`: erro interno da API.
- Timeout: falha de comunicação.
- Resposta não JSON: erro de contrato da API.

Mensagem exemplo:

```text
Não foi possível consultar o sistema.

Motivo: token inválido ou expirado.
Resposta HTTP: 401 Unauthorized.

Atualize o Bearer Token e execute novamente.
```

### 5.8 Preservação das respostas

As respostas JSON brutas devem ser salvas para auditoria.

Estrutura sugerida:

```text
data/api_raw/<DATA_EXECUCAO>/
├── autocomplete_operadoras.json
├── cielo_credito.json
├── cielo_debito.json
├── cielo_pix.json
├── quickpay_credito.json
├── quickpay_debito.json
├── quickpay_pix.json
└── metadata.json
```

O arquivo `metadata.json` deve registrar:

```json
{
  "executed_at": "2026-07-16T08:30:00-03:00",
  "period_start": "2026-07-15",
  "period_end": "2026-07-15",
  "intervalo_dia": -1,
  "is_compensado": 0
}
```

Nunca salvar o token.

---

## 6. Estratégia de conciliação com o sistema

### 6.1 Referência principal

O objetivo principal é conciliar o caixa da empresa.

A comparação será:

```text
Valor bruto do relatório da operadora
versus
valor registrado no sistema
```

O valor registrado no sistema serve como referência administrativa para confirmar se as transações do caixa batem com os relatórios das operadoras.

### 6.2 Critérios disponíveis

Como o endpoint não traz horário, NSU, TID ou código de autorização, a comparação inicial deve usar:

```text
operadora
+ modalidade
+ bandeira ou forma de recebimento
+ data
+ valor
+ quantidade de ocorrências
```

### 6.3 Datas

Mapeamento inicial esperado:

| Campo da API | Significado esperado |
|---|---|
| `dataCadastro` | Data do registro ou venda |
| `dataVencimento` | Data de recebimento ou vencimento |
| `valor` | Valor bruto registrado no caixa |

Esse mapeamento deve ser validado com dados reais antes de ser tratado como definitivo.

### 6.4 Tolerância de horário

A API apresentada não retorna horário.

Portanto, a primeira versão não deve implementar comparação por horas.

Caso um endpoint futuro traga horário, poderá ser adicionada tolerância configurável de algumas horas.

### 6.5 Valores repetidos

O sistema deve tratar valores como multiconjunto.

Exemplo:

Sistema:

```text
R$ 2,39 — 2 ocorrências
R$ 2,90 — 1 ocorrência
```

Operadora:

```text
R$ 2,39 — 2 ocorrências
R$ 2,90 — 1 ocorrência
```

Resultado:

```text
R$ 2,39: conciliado — 2 de 2
R$ 2,90: conciliado — 1 de 1
```

Se houver:

```text
Sistema: R$ 2,39 — 2 ocorrências
Operadora: R$ 2,39 — 1 ocorrência
```

Resultado:

```text
Diferença: 1 transação de R$ 2,39
```

Não associar silenciosamente duas transações à mesma ocorrência.

### 6.6 Status de comparação

Sugestão inicial:

```text
CONCILIADO
DIVERGÊNCIA DE VALOR
DIVERGÊNCIA DE QUANTIDADE
NÃO ENCONTRADO NO SISTEMA
NÃO ENCONTRADO NA OPERADORA
CORRESPONDÊNCIA AMBÍGUA
```

Qualquer centavo de diferença deve ser considerado.

Não usar tolerância monetária.

---

## 7. Regras do arquivo Cielo

### 7.1 Entrada

O usuário enviará o relatório bruto da Cielo.

O arquivo original nunca deve ser alterado.

### 7.2 Saída

Gerar:

```text
CIELO_CONCILIACAO_<DATA_INICIO>_A_<DATA_FIM>.xlsx
```

### 7.3 Formato

A saída deve seguir o modelo da planilha com final `LEO`.

Deve:

- Preservar todas as transações.
- Remover colunas desnecessárias da visualização principal.
- Organizar as linhas.
- Separar crédito, débito e Pix.
- Criar subtotais.
- Exibir total bruto.
- Exibir total das taxas.
- Exibir total líquido.
- Incluir percentual de taxa por venda.
- Manter aparência próxima ao exemplo LEO.
- Não incluir dados excessivos da API.
- Preservar os dados originais em aba separada.

### 7.4 Fórmula do percentual

```text
Percentual da taxa = 1 - (Valor líquido / Valor bruto)
```

Equivalente:

```text
Percentual da taxa = (Valor bruto - Valor líquido) / Valor bruto
```

Formatar como:

```text
0,00%
```

### 7.5 Abas sugeridas

```text
Conciliação
Dados Originais
Alertas
```

### 7.6 Comparação com o sistema

A comparação com o sistema deve ser usada para validação administrativa.

A primeira versão não deve poluir o layout principal da planilha Cielo.

A implementação pode usar:

- Área auxiliar ao final da planilha.
- Aba `Alertas`.
- Indicadores resumidos.
- Colunas ocultas.
- Metadados internos.

A saída principal deve continuar visualmente semelhante ao modelo LEO.

---

## 8. Regras do arquivo QuickPay

### 8.1 Entrada

O usuário enviará o relatório bruto da QuickPay.

Esse arquivo deverá conter obrigatoriamente uma coluna adicional chamada exatamente:

```text
RECEBIDO NO BANCO QUICKPAY
```

A coluna deve conter o valor realmente recebido no banco em cada linha correspondente.

Exemplo:

| Valor da venda | Valor líquido | RECEBIDO NO BANCO QUICKPAY |
|---:|---:|---:|
| R$ 126,83 | R$ 121,77 | R$ 121,80 |
| R$ 194,00 | R$ 186,26 | R$ 186,30 |

### 8.2 Regras da coluna obrigatória

A coluna:

- É obrigatória.
- Deve existir exatamente uma vez.
- Deve estar preenchida em todas as linhas de transação.
- Não pode conter texto inválido.
- Não pode conter fórmula com erro.
- Não pode conter valores vazios.
- Não pode conter múltiplos recebimentos para a mesma linha.
- Não representa recebimento parcial.
- Não será solicitada pelo chat.
- Não será estimada pelo sistema.

### 8.3 Erros

Se a coluna não existir ou contiver erro:

- Não gerar o arquivo QuickPay.
- Gerar normalmente o arquivo Cielo, se estiver válido.
- Informar linha, coluna e célula.
- Informar, quando possível, a transação relacionada.

Exemplo:

```text
O arquivo da Cielo foi processado com sucesso.

O arquivo da QuickPay não foi gerado.

Erro:
A coluna “RECEBIDO NO BANCO QUICKPAY” possui um valor vazio.

Linha da planilha: 8
Célula: I8
Transação: Mastercard — R$ 194,00
```

### 8.4 Cálculos

#### Bruto - Líquido

```text
Bruto - Líquido = Valor da venda - Valor líquido
```

#### Diferença

```text
Diferença = Taxa - (Valor da venda - Valor líquido)
```

#### Porcentagem

```text
Porcentagem = 1 - (Valor líquido / Valor da venda)
```

#### Diferença entre previsto e recebido

Pode ser exibida como informação administrativa:

```text
Diferença entre líquido previsto e valor recebido =
RECEBIDO NO BANCO QUICKPAY - Valor líquido
```

Essa diferença não substitui a conciliação principal do caixa com o sistema.

### 8.5 Comparação com o sistema

A conciliação principal será:

```text
Valor da venda no relatório QuickPay
versus
valor registrado no sistema
```

A coluna `RECEBIDO NO BANCO QUICKPAY` serve para registrar a diferença entre o que a QuickPay informou que pagaria e o que efetivamente entrou no banco.

### 8.6 Saída

Gerar:

```text
QUICKPAY_CONCILIACAO_<DATA_INICIO>_A_<DATA_FIM>.xlsx
```

### 8.7 Colunas esperadas

A primeira versão deve conter, no mínimo:

```text
Código
Operadora
Cartão
Pré-datado
Recebido
Valor
Valor líquido
Valor taxa
Bruto - líquido
Diferença
Porcentagem
RECEBIDO NO BANCO QUICKPAY
Valor no sistema
Diferença sistema x operadora
Status
```

### 8.8 Abas sugeridas

```text
Conciliação
Dados Originais
Alertas
```

---

## 9. Processamento independente

Cielo e QuickPay devem ser processadas separadamente.

Exemplo:

```text
Cielo válida
QuickPay inválida
```

Resultado:

- Gerar o arquivo da Cielo.
- Não gerar o arquivo da QuickPay.
- Exibir erro específico da QuickPay.

Uma falha em uma operadora não deve bloquear a outra.

---

## 10. Múltiplos arquivos

Arquivos da mesma operadora poderão ser unidos apenas quando:

- Pertencerem ao mesmo processamento.
- Estiverem dentro do período solicitado.
- Não houver sobreposição.
- Não houver duplicidade de transações.

Se houver sobreposição:

- Não unir silenciosamente.
- Interromper somente aquela operadora.
- Informar os registros suspeitos.
- Informar arquivo, linha e valor quando possível.

---

## 11. Estrutura recomendada do projeto

```text
conciliacao-caixa/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
│
├── .agents/
│   └── skills/
│       └── conciliar-operadoras/
│           ├── SKILL.md
│           └── references/
│               ├── regras-cielo.md
│               ├── regras-quickpay.md
│               └── integracao-velo.md
│
├── config/
│   ├── geral.yaml
│   ├── cielo.yaml
│   ├── quickpay.yaml
│   └── velo_api.yaml
│
├── data/
│   ├── input/
│   ├── raw/
│   ├── api_raw/
│   ├── processed/
│   └── archive/
│
├── output/
│   ├── cielo/
│   └── quickpay/
│
├── logs/
│
├── src/
│   └── conciliacao/
│       ├── __init__.py
│       ├── cli.py
│       ├── workflow.py
│       │
│       ├── domain/
│       │   ├── models.py
│       │   ├── enums.py
│       │   └── exceptions.py
│       │
│       ├── integrations/
│       │   └── velo/
│       │       ├── authentication.py
│       │       ├── client.py
│       │       ├── endpoints.py
│       │       ├── mapper.py
│       │       └── schemas.py
│       │
│       ├── readers/
│       │   ├── excel_reader.py
│       │   ├── cielo_reader.py
│       │   └── quickpay_reader.py
│       │
│       ├── processors/
│       │   ├── cielo_processor.py
│       │   └── quickpay_processor.py
│       │
│       ├── matching/
│       │   ├── normalizer.py
│       │   ├── multiset_matcher.py
│       │   └── reconciliation.py
│       │
│       ├── validators/
│       │   ├── common_validator.py
│       │   ├── cielo_validator.py
│       │   ├── quickpay_validator.py
│       │   └── api_validator.py
│       │
│       ├── exporters/
│       │   ├── excel_exporter.py
│       │   ├── cielo_exporter.py
│       │   ├── quickpay_exporter.py
│       │   └── styles.py
│       │
│       └── utils/
│           ├── currency.py
│           ├── dates.py
│           ├── file_hash.py
│           └── logging.py
│
├── tests/
│   ├── fixtures/
│   │   ├── cielo/
│   │   ├── quickpay/
│   │   └── api/
│   ├── unit/
│   └── integration/
│
└── scripts/
    ├── processar.ps1
    └── processar.bat
```

---

## 12. Configuração sugerida

### `config/velo_api.yaml`

```yaml
base_url: "https://api.v1.velosistema.com.br"

endpoints:
  autocomplete_operadoras: "/autoCompletarOperadora"
  conciliacao_recebidos: "/listarConciliacaoCartaoRecebido"

query:
  intervalo_dia: -1
  is_compensado: 0

formas_recebimento_fallback:
  cielo_credito: 81
  cielo_debito: 86
  cielo_pix: 91
  quickpay_credito: 44
  quickpay_debito: 51
  quickpay_pix: 42

timeout_seconds: 30
```

### `config/geral.yaml`

```yaml
currency:
  decimal_places: 2
  monetary_tolerance: 0.00

processing:
  preserve_originals: true
  independent_operators: true
  reject_overlapping_files: true

output:
  include_original_data_sheet: true
  include_alerts_sheet: true
```

---

## 13. Dependências Python

Sugestão:

```toml
[project]
name = "conciliacao-caixa"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pandas",
    "openpyxl",
    "xlrd",
    "requests",
    "pyyaml",
    "pydantic",
    "typer",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
    "ruff",
    "mypy",
]
```

---

## 14. Interface de linha de comando

Exemplo:

```powershell
uv run conciliacao processar `
  --data-inicio 2026-07-15 `
  --data-fim 2026-07-15 `
  --arquivo-cielo "data/input/cielo.xlsx" `
  --arquivo-quickpay "data/input/quickpay.xls"
```

O Bearer Token deve vir de:

```powershell
$env:VELO_BEARER_TOKEN="TOKEN_AQUI"
```

O comando deve falhar de forma clara caso o token não exista.

---

## 15. Regras do AGENTS.md

O arquivo `AGENTS.md` deve orientar o Codex a:

1. Nunca alterar arquivos de entrada.
2. Nunca salvar tokens.
3. Nunca inventar valores ausentes.
4. Nunca arredondar divergências para zero.
5. Sempre executar os testes após mudanças.
6. Sempre validar totais antes de concluir.
7. Sempre gerar Cielo e QuickPay de forma independente.
8. Sempre informar erros com contexto.
9. Sempre preservar respostas brutas da API.
10. Nunca alterar a lógica financeira sem autorização.
11. Nunca preencher automaticamente `RECEBIDO NO BANCO QUICKPAY`.
12. Sempre manter a saída da Cielo próxima ao modelo LEO.
13. Sempre usar scripts determinísticos para cálculos.
14. Nunca fazer alterações na API da empresa.
15. Nunca marcar registros como compensados.

---

## 16. Skill do Codex

Criar:

```text
.agents/skills/conciliar-operadoras/SKILL.md
```

Responsabilidades:

1. Validar que as datas foram informadas.
2. Validar que o Bearer Token está disponível.
3. Localizar os arquivos Cielo e QuickPay.
4. Executar o comando principal.
5. Exibir o resumo.
6. Informar os arquivos gerados.
7. Informar erros separados por operadora.
8. Não editar manualmente os arquivos Excel.
9. Não recalcular valores fora dos scripts.
10. Não modificar os arquivos originais.

---

## 17. Validações obrigatórias

### 17.1 Cielo

- Arquivo abre corretamente.
- Cabeçalho foi localizado.
- Quantidade de transações foi preservada.
- Total bruto da origem é igual ao total bruto da saída.
- Total das taxas é igual ao total das taxas da saída.
- Total líquido da origem é igual ao total líquido da saída.
- Percentual da taxa foi calculado.
- Arquivo original não foi alterado.

### 17.2 QuickPay

- Coluna `RECEBIDO NO BANCO QUICKPAY` existe.
- Todas as linhas de transação estão preenchidas.
- Todos os valores são monetários válidos.
- Não há fórmula com erro.
- Quantidade de transações foi preservada.
- Total bruto foi preservado.
- Total líquido foi preservado.
- Bruto - líquido foi calculado.
- Diferença foi calculada.
- Porcentagem foi calculada.
- Arquivo original não foi alterado.

### 17.3 API

- Token está presente.
- Resposta HTTP foi válida.
- Resposta é JSON.
- Registros possuem os campos necessários.
- Datas estão dentro do período.
- IDs das modalidades foram encontrados.
- Nenhuma chamada de escrita foi realizada.

### 17.4 Comparação

- Valores tratados com duas casas decimais.
- Qualquer centavo de diferença é destacado.
- Valores repetidos preservam quantidade.
- Nenhuma transação é usada duas vezes.
- Sobras de ambos os lados são registradas.
- Resultados ambíguos são marcados.

---

## 18. Logs

Cada execução deve gerar um log:

```text
logs/conciliacao_<DATA_HORA>.log
```

Informações mínimas:

- Data e hora.
- Período solicitado.
- Arquivos processados.
- Hash dos arquivos originais.
- Endpoints chamados.
- Quantidade de registros retornados.
- Quantidade de transações Cielo.
- Quantidade de transações QuickPay.
- Quantidade conciliada.
- Quantidade divergente.
- Erros encontrados.
- Arquivos gerados.

Nunca registrar o Bearer Token.

---

## 19. Critérios de aceite

A primeira versão será considerada concluída quando:

1. Receber datas explícitas.
2. Receber o token por variável de ambiente.
3. Consultar os seis grupos relevantes da API.
4. Processar arquivo Cielo.
5. Processar arquivo QuickPay.
6. Gerar arquivo Cielo no padrão LEO.
7. Gerar arquivo QuickPay com as colunas definidas.
8. Validar a coluna `RECEBIDO NO BANCO QUICKPAY`.
9. Detectar qualquer centavo de diferença.
10. Comparar valores com o sistema.
11. Tratar valores repetidos corretamente.
12. Não alterar os arquivos de entrada.
13. Gerar arquivos de forma independente.
14. Exibir erros com linha, coluna e célula.
15. Passar em todos os testes automatizados.
16. Gerar logs sem dados sensíveis.

---

## 20. Ordem recomendada de implementação

### Fase 1 — Estrutura inicial

- Criar repositório.
- Criar `pyproject.toml`.
- Criar `AGENTS.md`.
- Criar skill.
- Criar configurações.
- Criar estrutura de pastas.

### Fase 2 — Integração Velo

- Implementar autenticação Bearer.
- Implementar client HTTP.
- Implementar autocomplete.
- Implementar consulta de conciliação.
- Salvar respostas brutas.
- Tratar erros HTTP.

### Fase 3 — Processador Cielo

- Ler arquivo.
- Identificar cabeçalho.
- Normalizar colunas.
- Reproduzir modelo LEO.
- Calcular percentual.
- Gerar subtotais.
- Criar testes.

### Fase 4 — Processador QuickPay

- Ler arquivo.
- Validar coluna obrigatória.
- Calcular campos.
- Gerar saída.
- Criar testes de erro por célula.

### Fase 5 — Matching

- Normalizar valores.
- Agrupar por operadora, modalidade e data.
- Implementar multiconjunto.
- Registrar sobras e divergências.

### Fase 6 — Workflow

- Integrar API, Cielo e QuickPay.
- Executar operadoras independentemente.
- Gerar logs.
- Gerar resumo final.

### Fase 7 — Homologação

- Testar com arquivos reais.
- Comparar com o processo manual.
- Ajustar layout.
- Validar totais.
- Validar erros.
- Documentar uso.

---

## 21. Resumo final do comportamento esperado

```text
Entrada:
- Data inicial
- Data final
- Bearer Token
- Arquivo Cielo
- Arquivo QuickPay com coluna RECEBIDO NO BANCO QUICKPAY

Processamento:
- Consulta API
- Processa Cielo
- Processa QuickPay
- Compara valores
- Valida centavos
- Preserva arquivos originais

Saída:
- CIELO_CONCILIACAO_<PERIODO>.xlsx
- QUICKPAY_CONCILIACAO_<PERIODO>.xlsx
- Logs
- Resumo de erros e divergências
```
