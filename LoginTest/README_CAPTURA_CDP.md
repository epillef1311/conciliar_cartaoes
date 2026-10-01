# Captura de token com Chrome iniciado manualmente (ferramenta de diagnostico)

O fluxo real padrao agora incorpora login assistido e mantem o token somente em
memoria. Este script permanece apenas para diagnostico isolado. Ele conecta localmente a um Chrome iniciado
com perfil temporario e observa somente `POST /session/validate` enquanto o
usuario faz o login manualmente.

Abra um PowerShell e execute, substituindo o caminho do Chrome se necessario:

```powershell
$profile = "$PWD\output\cdp_chrome_profile"
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir=$profile https://app.cicalesesolucoes.com.br/"
```

Em outro PowerShell, execute:

```powershell
python capture_cdp_manual_token.py
```

Somente o processo local pode acessar a porta `9222`. Feche o Chrome temporario
ao terminar e nunca use o perfil padrao do seu navegador para este fluxo.
