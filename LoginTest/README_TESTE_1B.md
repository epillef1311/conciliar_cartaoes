# Teste 1B: captura apos login manual

Execute `python capture_manual_login_token.py`. O Chrome abre com um perfil
isolado e o usuario deve preencher credenciais, concluir qualquer desafio de
seguranca e clicar para entrar por conta propria. O script nao toca nos campos
nem no botao de login.

Depois do acesso, ele observa somente `POST /session/validate`, salva o token
local em `output/token.txt` e salva o estado de sessao. Nao exibe o token no
terminal. O prazo padrao para concluir o login e de cinco minutos.
