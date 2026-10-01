# Validacao de token Velo (somente leitura)

`validate_token_test.py` faz uma unica requisicao **GET** configuravel para
validar o token local de `output/token.txt`, gerado pelo Teste 1 autorizado
neste chat. Ele nao abre navegador, nao renova token, nao baixa relatorios e
nao faz chamadas de escrita.

Configure a URL e o endpoint em `.env`; nunca inclua o token nesse arquivo:

```powershell
python validate_token_test.py
```

O resultado e `0` para token valido, `2` para token invalido/expirado e `1`
para erro tecnico ou resultado indeterminado. A resposta sanitizada e gravada
atomicamente em `output/validate_token_response_sanitized.json`; nenhum token,
cabecalho de autorizacao ou corpo nao JSON e registrado.
