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
16. Nunca imprima nem salve cabecalho `Authorization`.
17. Nunca use respostas reais completas da API como fixtures publicas.
18. Nunca habilite chamadas reais de rede nos testes.
19. Preserve valores repetidos retornados pela API.
20. Mantenha `intervaloDia` e `isCompensado` configuraveis.
21. Execute testes de seguranca do token ao alterar integracao Velo.
22. Nunca use o mesmo registro do sistema duas vezes no matching.
23. Nunca invente pareamento quando faltarem identificadores fortes.
24. Nao use hora da operadora como chave enquanto a API nao fornecer horario.
25. Nao use `valorTaxaCartao` como chave de matching.
26. Distinga categoria nao consultada de resposta consultada vazia.
27. Login automatico na Velo nao existe neste projeto.
28. Token Velo deve vir apenas de variavel de ambiente.
29. Gere arquivos finais de forma atomica sempre que o workflow orquestrar exportacao.
30. Nao polua o layout Cielo com dados da API; use resumo/log/JSON lateral.

## Escopo atual

A Etapa 9 implementa workflow integrado com API somente leitura, modo simulado, matching, exportacao independente, logs e resumos. Nao implemente login automatico, escrita na API, compensacao, alteracao de caixa ou homologacao com dados reais sem pedido explicito.
