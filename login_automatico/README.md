# Login automático de teste

Protótipo Selenium para preencher e enviar o formulário de login da Velo em um Chrome visível. Ele só executa quando a branch atual começa com `test/`.

O script não salva nem imprime usuário, senha, token, cookies ou resposta da autenticação. CAPTCHA, MFA e qualquer outro desafio de segurança devem ser concluídos manualmente no navegador; não há mecanismo para contorná-los.

## Configuração

Por padrão, o script lê somente [LoginTest/.env](../LoginTest/.env), que já contém `VELO_LOGIN_URL`, `VELO_USUARIO` e `VELO_SENHA`. O arquivo permanece ignorado pelo Git e seus valores não são impressos, gravados ou copiados para o ambiente do processo.

O script já inclui os seletores CSS confirmados para essa tela: `#email`, `input[type='password']` e `button.button-primary`. Caso a interface mude, eles podem ser sobrescritos pela sessão atual ou por argumentos. Variáveis da sessão têm prioridade sobre valores de `LoginTest/.env`.

## Preparação

```powershell
.\.venv\Scripts\python.exe -m pip install -r ".\login_automatico\requirements.txt"
```

Não coloque credenciais, tokens ou outros segredos em novos arquivos, logs ou no Git.

## Execução

```powershell
.\.venv\Scripts\python.exe ".\login_automatico\login_velo_selenium.py"
```

Também é possível passar a URL e os seletores como argumentos, sem colocá-los em arquivo:

```powershell
.\.venv\Scripts\python.exe ".\login_automatico\login_velo_selenium.py" --url "https://endereco-real-do-login" --usuario-selector "input[name='usuario']" --senha-selector "input[name='senha']" --entrar-selector "button[type='submit']"
```
