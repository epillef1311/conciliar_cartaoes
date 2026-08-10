# Regras de contribuicao

Este projeto demonstrativo automatiza conciliacao financeira. Preserve a rastreabilidade e evite qualquer alteracao manual em dados de entrada.

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
13. Para QuickPay, aceite recebimentos bancarios agregados somente por planilha auxiliar gerada a partir de valores confirmados pelo usuario no chat, usando data de recebimento, bandeira e modalidade.
14. Nunca distribua ou replique um total bancario agregado nas linhas individuais de venda QuickPay.
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
27. Integrações reais exigem login assistido em Chrome visível; o usuário conclui o acesso e nenhum desafio de segurança pode ser burlado.
28. Qualquer token capturado em login assistido deve permanecer somente em memória durante a execução e ser descartado ao final; variável de ambiente fica restrita a compatibilidade técnica e testes controlados.
29. Gere arquivos finais de forma atomica sempre que o workflow orquestrar exportacao.
30. Nao polua o layout Cielo com dados da API; use resumo/log/JSON lateral.

## Escopo atual

A Etapa 9 implementa workflow integrado com API somente leitura, modo simulado, matching, exportacao independente, logs, resumos e login manual assistido no fluxo real. Nao implemente preenchimento automatico de credenciais, escrita na API, compensacao ou alteracao de caixa.
