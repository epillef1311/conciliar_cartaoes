# Etapa 10 — Homologação Controlada

Coloque este arquivo na raiz do projeto `conciliacaoCartoes`, ao lado de `AGENTS.md`, `PLANO_IMPLEMENTACAO.md` e `README.md`.

Caminho recomendado:

```text
conciliacaoCartoes/ETAPA_10_HOMOLOGACAO.md
```

---

Implemente e execute apenas a Etapa 10 do `PLANO_IMPLEMENTACAO.md`: homologação controlada da automação de conciliação com arquivos reais e consultas reais à API Velo.

Esta etapa não deve introduzir grandes funcionalidades novas. O objetivo é validar o que já foi implementado, encontrar divergências entre o comportamento esperado e os dados reais, corrigir apenas os problemas necessários e produzir evidências de que o projeto está pronto para uso assistido.

Antes de começar:

1. Leia integralmente:

   * `ARQUITETURA_AUTOMACAO_CONCILIACAO_CAIXA.md`
   * `PLANO_IMPLEMENTACAO.md`
   * `AGENTS.md`
   * `README.md`
2. Revise os resultados das Etapas 1 a 9.
3. Confirme que todos os testes automatizados passam antes da homologação.
4. Não implemente login automático.
5. Não solicite usuário ou senha da Velo.
6. O token deve continuar vindo exclusivamente de:

   * `VELO_BEARER_TOKEN`
7. Não aceite token como argumento da CLI.
8. Não faça operações de escrita na API.
9. Não altere os arquivos reais de entrada.
10. Não faça commits automaticamente.

# 1. Objetivo da homologação

Validar com dados reais:

* leitura do relatório Cielo;
* geração do relatório Cielo;
* leitura do relatório QuickPay;
* validação da coluna `RECEBIDO NO BANCO QUICKPAY`;
* geração do relatório QuickPay;
* consulta real da API Velo;
* resolução das modalidades;
* matching;
* tratamento de valores repetidos;
* tratamento de categorias vazias;
* tratamento de categorias não consultadas ou com erro;
* preenchimento dos campos do sistema na QuickPay;
* geração dos arquivos laterais de auditoria;
* preservação dos arquivos originais;
* logs;
* códigos de saída;
* comportamento de sucesso parcial.

# 2. Estratégia de homologação

Não testar inicialmente um período grande.

Executar em três ciclos:

## Ciclo A — somente Cielo

Usar:

* um arquivo real Cielo;
* um período pequeno e conhecido;
* respostas reais da API para as modalidades presentes;
* resultado manual já conhecido, quando disponível.

Objetivo:

* confirmar o fluxo Cielo isoladamente;
* validar totais;
* validar quantidade de transações;
* validar matching;
* validar layout;
* validar registros não encontrados.

## Ciclo B — somente QuickPay

Usar:

* arquivo real QuickPay preparado com a coluna transacional obrigatória;
* período pequeno;
* valores reais recebidos no banco;
* respostas reais da API.

Objetivo:

* confirmar validação da coluna obrigatória;
* confirmar cálculos;
* confirmar matching;
* confirmar preenchimento de `Sistema`, `Diferença Sistema` e `Status`.

## Ciclo C — Cielo e QuickPay juntos

Usar os dois arquivos no mesmo workflow.

Objetivo:

* confirmar independência;
* confirmar status geral;
* confirmar que a falha de uma operadora não bloqueia a outra;
* confirmar geração de logs e resumos completos.

# 3. Preparação

Antes das chamadas reais, verificar:

```powershell
$env:VELO_BEARER_TOKEN
```

Não imprimir o conteúdo.

Verificar apenas se:

* a variável existe;
* não está vazia.

Se estiver ausente:

* não continuar com chamadas reais;
* informar como configurar;
* não pedir para inserir o token no código;
* não pedir para colar o token em arquivos;
* não registrar o token.

# 4. Diretório exclusivo de homologação

Criar estrutura separada:

```text
homologacao/
├── input/
│   ├── cielo/
│   └── quickpay/
├── output/
├── logs/
├── api_raw/
├── evidencias/
└── relatorios/
```

Regras:

* `homologacao/` deve ficar fora do Git quando contiver dados reais;
* os arquivos reais não devem ser copiados para fixtures públicas;
* respostas reais não devem ser versionadas;
* relatórios gerados não devem ser versionados;
* evidências que contenham dados reais devem ficar fora do Git.

# 5. Verificação prévia dos arquivos

Antes da execução:

* confirmar existência dos arquivos;
* calcular SHA-256;
* registrar tamanho;
* registrar data de modificação;
* detectar formato;
* não abrir em modo de escrita;
* não alterar propriedades;
* não renomear;
* não mover.

Registrar em um manifesto:

```json
{
  "arquivo": "cielo.xlsx",
  "sha256_antes": "...",
  "tamanho_bytes": 12345,
  "data_modificacao_antes": "2026-07-19T10:00:00-03:00"
}
```

Ao final, calcular novamente o hash e comparar.

# 6. Execução real da Cielo

Executar inicialmente apenas a Cielo:

```powershell
uv run conciliacao processar `
  --data-inicio AAAA-MM-DD `
  --data-fim AAAA-MM-DD `
  --arquivo-cielo "homologacao/input/cielo/ARQUIVO_REAL.xlsx" `
  --saida "homologacao/output"
```

Validar:

* token lido somente da variável de ambiente;
* modalidades detectadas;
* categorias consultadas;
* quantidade retornada por categoria;
* arquivo Excel gerado;
* arquivo lateral JSON gerado;
* log gerado;
* resumo gerado;
* entrada preservada.

# 7. Conferência do relatório Cielo

Comparar a saída com o processo manual e com o modelo LEO.

Validar:

* apenas uma aba `Planilha1`;
* título;
* 12 colunas;
* ordem dos cabeçalhos;
* quantidade de transações;
* ordem dos cartões;
* Pix após cartões;
* subtotais nas colunas K e L;
* ausência de linhas exclusivas de subtotal;
* total geral após a última transação;
* porcentagem por linha;
* taxa negativa;
* formatos monetários;
* datas;
* horários;
* ausência de colunas da API;
* ausência de status na planilha principal.

Não exigir identidade binária com o LEO.

A comparação deve ser estrutural, financeira e visual.

# 8. Conferência financeira Cielo

Calcular com `Decimal`:

* quantidade;
* total bruto;
* total da taxa original;
* total da taxa normalizada;
* total líquido;
* totais por modalidade;
* totais por data de pagamento.

Confirmar:

```text
Valor bruto + taxa negativa = valor líquido
```

Qualquer diferença de R$ 0,01 deve ser investigada.

Não aprovar a homologação enquanto houver centavos sem explicação.

# 9. Conferência do matching Cielo

Para cada modalidade:

* confirmar que a categoria correta foi consultada;
* confirmar o ID usado;
* confirmar período enviado;
* confirmar uso de `dataCadastro`;
* confirmar valores retornados;
* confirmar valores repetidos;
* confirmar sobras da operadora;
* confirmar sobras do sistema.

Gerar tabela de conferência semelhante:

```text
Modalidade | Data | Valor | Qtd. operadora | Qtd. sistema | Conciliadas | Status
```

Não adicionar essa tabela ao Excel operacional da Cielo.

Salvar em evidência ou relatório lateral.

# 10. Registros repetidos

Validar explicitamente pelo menos um caso com valor repetido, caso exista.

Exemplo:

```text
R$ 2,39 — 2 ocorrências na operadora
R$ 2,39 — 2 ocorrências no sistema
```

Confirmar:

* duas ocorrências preservadas;
* duas conciliadas;
* nenhum ID consumido duas vezes;
* resultado agregado marcado corretamente;
* nenhuma associação individual falsa apresentada como comprovada.

# 11. Registros existentes somente no sistema

Validar casos como:

```text
Registro de crédito de R$ 102,92 no sistema
sem transação equivalente no relatório Cielo
```

Esperado:

```text
NÃO ENCONTRADO NA OPERADORA
```

Confirmar que:

* o ID do sistema foi preservado;
* o valor foi preservado;
* a data foi preservada;
* não foi associado arbitrariamente a outra transação;
* apareceu no resumo lateral;
* não alterou o total financeiro do Excel Cielo.

# 12. Categoria consultada com resposta vazia

Executar ou simular um período real em que uma categoria retorne:

```json
[]
```

Confirmar:

* chamada considerada bem-sucedida;
* categoria marcada como consultada;
* zero registros;
* transações da operadora dessa categoria podem receber:

  * `NÃO ENCONTRADO NO SISTEMA`;
* não marcar como falha de integração.

# 13. Categoria não consultada ou com erro

Validar o comportamento de uma categoria:

* não solicitada;
* com timeout;
* com erro 500;
* com falha de contrato.

Esperado:

```text
PENDENTE DE DADOS
```

Não usar:

```text
NÃO ENCONTRADO NO SISTEMA
```

Confirmar que as demais modalidades continuam sendo processadas.

# 14. Execução real da QuickPay

Usar um arquivo real preparado com a coluna:

```text
RECEBIDO NO BANCO QUICKPAY
```

A coluna deve estar dentro da tabela transacional.

Executar:

```powershell
uv run conciliacao processar `
  --data-inicio AAAA-MM-DD `
  --data-fim AAAA-MM-DD `
  --arquivo-quickpay "homologacao/input/quickpay/ARQUIVO_REAL.xlsx" `
  --saida "homologacao/output"
```

# 15. Conferência da entrada QuickPay

Antes da geração, confirmar:

* coluna presente;
* coluna única;
* todas as linhas preenchidas;
* valores monetários válidos;
* nenhuma fórmula com erro;
* nenhuma linha deslocada;
* valores recebidos correspondem às linhas corretas;
* arquivo não foi alterado.

# 16. Conferência financeira QuickPay

Validar por linha:

```text
Bruto-Líquido = Valor da Venda - Valor líquido
```

```text
Diferença = Taxa - Bruto-Líquido
```

```text
Porcentagem = 1 - (Valor líquido / Valor da Venda)
```

```text
Diferença Banco =
RECEBIDO NO BANCO QUICKPAY - Valor líquido
```

Confirmar os totais:

* valor da venda;
* taxa;
* valor líquido;
* bruto-líquido;
* diferença;
* recebido no banco;
* diferença banco x líquido.

Qualquer diferença de R$ 0,01 deve permanecer visível.

# 17. Conferência da saída QuickPay

Validar:

* uma aba `Conciliação`;
* colunas na ordem aprovada;
* quantidade de transações;
* fórmulas;
* total geral;
* valores recebidos no banco preservados;
* coluna `Sistema`;
* coluna `Diferença Sistema`;
* coluna `Status`;
* nenhuma associação perdida após ordenação;
* nenhuma linha recebeu o valor bancário de outra linha.

# 18. Matching QuickPay

Confirmar que a chave utiliza:

* QuickPay;
* modalidade;
* data da venda;
* valor bruto;
* bandeira quando disponível.

Confirmar que não utiliza:

* valor líquido;
* taxa;
* recebido no banco;
* hora como critério da API;
* `valorTaxaCartao`.

Para correspondência segura:

```text
Sistema = valor da API
Diferença Sistema = Valor da Venda - Sistema
Status = CONCILIADO
```

# 19. Matching ambíguo na QuickPay

Criar ou identificar caso ambíguo.

Esperado:

* `Sistema` vazio;
* `Diferença Sistema` vazia;
* `Status = CORRESPONDÊNCIA AMBÍGUA`;
* candidatos registrados no JSON lateral;
* nenhum registro consumido arbitrariamente.

# 20. Execução conjunta

Após os testes isolados, executar:

```powershell
uv run conciliacao processar `
  --data-inicio AAAA-MM-DD `
  --data-fim AAAA-MM-DD `
  --arquivo-cielo "homologacao/input/cielo/ARQUIVO_REAL.xlsx" `
  --arquivo-quickpay "homologacao/input/quickpay/ARQUIVO_REAL.xlsx" `
  --saida "homologacao/output"
```

Validar:

* Cielo independente;
* QuickPay independente;
* categorias consultadas somente quando necessárias;
* um único identificador de execução;
* logs correlacionados;
* auditoria correlacionada;
* resumo combinado;
* dois arquivos gerados quando ambos estiverem válidos.

# 21. Cenário de sucesso parcial

Executar cenário controlado:

* Cielo válida;
* QuickPay sem coluna obrigatória.

Esperado:

* Cielo gerada;
* QuickPay não gerada;
* erro QuickPay detalhado;
* status geral `SUCESSO_PARCIAL`;
* código de saída correspondente;
* nenhum arquivo QuickPay parcial;
* nenhuma remoção da Cielo gerada.

Executar também o inverso, se viável:

* QuickPay válida;
* Cielo inválida.

# 22. Falha de autenticação

Executar teste controlado com token fictício ou inválido, sem expor o valor.

Esperado:

* erro 401 tratado;
* mensagem segura;
* nenhuma tentativa de login;
* nenhum token em logs;
* nenhum token em arquivos;
* nenhuma planilha final apresentada como conciliada;
* arquivos de entrada preservados;
* temporários removidos.

# 23. Timeout e erro de servidor

Testar usando transporte simulado, não provocando falha deliberada na API real.

Cenários:

* timeout;
* 500;
* 503;
* resposta não JSON.

Validar:

* categoria marcada com erro;
* demais categorias continuam quando possível;
* sucesso parcial;
* logs seguros;
* nenhuma falsa ausência de registros.

# 24. Auditoria

Verificar a estrutura:

```text
data/api_raw/<IDENTIFICADOR_EXECUCAO>/
```

Confirmar:

* JSONs válidos;
* nomes corretos;
* metadata;
* período correto;
* categorias corretas;
* nenhum token;
* nenhum Authorization;
* nenhum arquivo temporário abandonado.

# 25. Logs

Inspecionar os logs e confirmar que contêm:

* execução;
* período;
* arquivos;
* hashes;
* categorias;
* status HTTP;
* quantidade de registros;
* resultados;
* caminhos de saída;
* avisos;
* erros;
* duração.

Confirmar que não contêm:

* token;
* Authorization;
* cookies;
* senha;
* cartão completo;
* documentos pessoais desnecessários.

# 26. Atomicidade

Forçar uma falha controlada durante uma exportação usando testes ou mocks.

Confirmar:

* arquivo temporário removido;
* arquivo final corrompido não permanece;
* saída da outra operadora permanece;
* entrada permanece intacta;
* log registra a falha.

# 27. Sobrescrita

Validar:

## Sem `--sobrescrever`

* arquivo existente não é substituído silenciosamente;
* novo nome com sufixo é criado ou erro seguro é retornado.

## Com `--sobrescrever`

* somente a saída autorizada é sobrescrita;
* entrada nunca é sobrescrita;
* operação continua atômica.

# 28. Relatório de homologação

Gerar:

```text
homologacao/relatorios/RELATORIO_HOMOLOGACAO.md
```

O documento deve conter:

1. Data da homologação.
2. Versão do projeto.
3. Ambiente utilizado.
4. Períodos testados.
5. Arquivos testados, usando nomes mascarados quando necessário.
6. Hashes.
7. Cenários executados.
8. Resultados esperados.
9. Resultados encontrados.
10. Divergências.
11. Correções aplicadas.
12. Evidências.
13. Limitações.
14. Riscos restantes.
15. Decisão de aprovação.

Não incluir:

* token;
* usuário;
* senha;
* números completos de cartão;
* documentos pessoais.

# 29. Matriz de homologação

Incluir uma tabela:

```text
| Cenário | Esperado | Obtido | Status | Evidência |
```

Cenários mínimos:

* Cielo válida;
* QuickPay válida;
* execução conjunta;
* QuickPay sem coluna;
* categoria vazia;
* categoria não consultada;
* valor repetido;
* sobra no sistema;
* sobra na operadora;
* diferença de centavo;
* 401;
* timeout simulado;
* saída existente;
* entrada preservada;
* auditoria sem token.

# 30. Classificação dos problemas

Classificar problemas encontrados:

```text
BLOQUEADOR
ALTO
MÉDIO
BAIXO
MELHORIA
```

## BLOQUEADOR

* total incorreto;
* arquivo original alterado;
* token exposto;
* registro consumido duas vezes;
* planilha corrompida;
* operadoras misturadas.

## ALTO

* transação não conciliada incorretamente;
* categoria ausente tratada como vazia;
* valor bancário atribuído a outra linha;
* relatório diferente do fluxo manual de forma relevante.

## MÉDIO

* mensagem pouco clara;
* layout inconsistente;
* relatório lateral incompleto.

## BAIXO

* formatação visual;
* nome de coluna;
* detalhe de log.

Não aprovar para uso quando houver problema bloqueador ou alto não resolvido.

# 31. Correções durante a homologação

Pode corrigir:

* bugs;
* validações incorretas;
* mapeamentos;
* mensagens;
* comportamento de exportação;
* matching comprovadamente incorreto;
* estilos essenciais;
* serialização;
* logs.

Não deve adicionar sem necessidade:

* login automático;
* dashboard;
* banco de dados;
* novas operadoras;
* agendamento;
* envio de e-mail;
* interface gráfica.

Toda correção deve:

1. possuir teste automatizado;
2. ser registrada no relatório;
3. preservar compatibilidade com os casos anteriores;
4. passar em Ruff e checagem de tipos.

# 32. Critérios de aprovação Cielo

A Cielo estará homologada quando:

* arquivo real for lido;
* quantidade estiver correta;
* total bruto estiver correto;
* taxa estiver correta;
* líquido estiver correto;
* relatório estiver utilizável;
* subtotais estiverem corretos;
* matching não consumir registros duplicados;
* valores repetidos estiverem corretos;
* sobras estiverem corretas;
* entrada permanecer intacta;
* nenhum token aparecer;
* execução puder ser repetida.

# 33. Critérios de aprovação QuickPay

A QuickPay estará homologada quando:

* coluna obrigatória for validada;
* valores recebidos forem preservados;
* cálculos estiverem corretos;
* totais estiverem corretos;
* matching estiver correto;
* `Sistema` estiver correto;
* `Diferença Sistema` estiver correta;
* `Status` estiver correto;
* linha não perder correspondência;
* arquivo original permanecer intacto.

# 34. Critérios de aprovação geral

A etapa será aprovada quando:

* os dois fluxos isolados funcionarem;
* o fluxo conjunto funcionar;
* sucesso parcial funcionar;
* códigos de saída estiverem corretos;
* logs estiverem corretos;
* auditoria estiver correta;
* não houver token persistido;
* não houver alteração de entrada;
* não houver diferença de centavos sem explicação;
* todos os testes passarem;
* não houver problema bloqueador ou alto aberto.

# 35. Checklist final

Antes de concluir:

* executar `pytest`;
* executar cobertura;
* executar Ruff;
* executar checagem de tipos;
* executar simulação;
* executar Cielo real;
* executar QuickPay real;
* executar fluxo conjunto;
* reabrir arquivos gerados;
* verificar fórmulas;
* verificar hashes;
* pesquisar por token no projeto;
* pesquisar por `Authorization`;
* verificar `.gitignore`;
* revisar relatório de homologação.

# 36. Resultado esperado

Ao finalizar, apresente:

* arquivos criados ou modificados;
* períodos reais testados;
* comandos executados;
* quantidade de transações Cielo;
* totais Cielo;
* resultado do matching Cielo;
* quantidade de transações QuickPay;
* totais QuickPay;
* resultado do matching QuickPay;
* arquivos finais gerados;
* cenários de sucesso parcial;
* problemas encontrados;
* correções realizadas;
* testes adicionados;
* resultado dos testes;
* cobertura;
* resultado do Ruff;
* resultado da checagem de tipos;
* confirmação dos hashes;
* confirmação de ausência de token;
* limitações restantes;
* caminho de `RELATORIO_HOMOLOGACAO.md`;
* recomendação final:

  * `APROVADO PARA USO ASSISTIDO`;
  * `APROVADO COM RESSALVAS`;
  * `REPROVADO`.

Não classifique como aprovado se houver erro financeiro, alteração dos arquivos originais, exposição de token ou matching duplicado.
