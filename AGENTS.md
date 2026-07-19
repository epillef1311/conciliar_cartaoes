# Regras para agentes

Este projeto automatiza conciliacao financeira. Preserve a rastreabilidade e evite qualquer alteracao manual em dados de entrada.

## Regras obrigatorias

1. Nunca altere arquivos originais de entrada.
2. Nunca salve Bearer Token, credenciais ou segredos.
3. Nunca escreva tokens em logs, fixtures, snapshots ou arquivos de configuracao versionados.
4. Nunca faca chamadas de escrita para a API da empresa.
5. Nunca marque registros como compensados.
6. Nunca invente valores ausentes.
7. Nunca arredonde divergencias monetarias para zero.
8. Use `Decimal` para regras financeiras em Python.
9. Preserve respostas brutas da API somente em `data/api_raw/`, fora do Git.
10. Gere Cielo e QuickPay de forma independente.
11. Informe erros com arquivo, aba, linha, coluna e celula quando possivel.
12. Mantenha a saida Cielo da primeira versao proxima ao modelo LEO, com aba principal `Planilha1`.
13. Exija `RECEBIDO NO BANCO QUICKPAY` dentro da tabela transacional da QuickPay.
14. Nao aceite o formato legado QuickPay com valores bancarios fora da tabela transacional.
15. Execute testes apos mudancas de codigo.

## Escopo atual

A Etapa 6 implementa apenas processamento e exportacao independente do relatorio QuickPay, sem API e sem matching. Nao implemente API Velo, matching, workflow completo ou Bearer Token sem pedido explicito.
