# Login Velo: limite de seguranca

A especificacao recebida solicitava um navegador Playwright para preencher
credenciais, capturar `POST /login/auth` e gravar sessao e token em disco.
Essa automacao **nao foi implementada** porque contradiz as regras obrigatorias
deste repositorio:

- login automatico da Velo nao existe neste projeto;
- o token Velo deve vir apenas da variavel de ambiente;
- credenciais, tokens, cookies e respostas de autenticacao nao podem ser
  salvos ou versionados;
- nao sao permitidas chamadas de escrita para a API.

O `login_test.py` e uma barreira executavel: ele encerra sem abrir navegador,
sem realizar requisicoes e sem escrever qualquer artefato. Executa-lo serve
somente para mostrar a orientacao de seguranca:

```powershell
python login_test.py
```

Para uso permitido da integracao somente leitura, configure o token apenas na
sessao local, sem registrá-lo em arquivos ou logs:

```powershell
$env:VELO_BEARER_TOKEN = "<token-fornecido-pelo-usuario>"
```

`output/` e `.env` permanecem ignorados como defesa adicional, embora este
componente nao crie token, estado de sessao, HAR, screenshots ou respostas de
autenticacao.
