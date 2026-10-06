# Instalação no computador do cliente

## Aplicativo Windows

Para gerar o aplicativo para distribuição, em uma máquina de desenvolvimento com `uv`, execute:

```powershell
.\scripts\gerar_executavel.ps1
```

O resultado fica em `dist\ConciliacaoCartoes_FrigorificoCandeias`. Entregue a pasta inteira ao cliente; o executável é `ConciliacaoCartoes_FrigorificoCandeias.exe`. A tela permite selecionar as planilhas Cielo e QuickPay (e, opcionalmente, a planilha auxiliar de recebimentos bancários QuickPay), sem informar datas. A logo oficial é incorporada à tela e ao ícone do executável.

A interface identifica o período pelas datas das planilhas, mostra as etapas reais da execução e oferece botões para abrir os relatórios gerados. A seleção de arquivos pode ser trocada ou removida; auditoria e detalhes da execução ficam em painéis recolhíveis. Durante o login e o processamento, o indicador de atividade não representa uma porcentagem estimada.

A geração do executável verifica automaticamente a inicialização da interface empacotada. Para repetir somente essa verificação, execute `.\scripts\verificar_executavel.ps1`; o aplicativo abre e encerra automaticamente, sem iniciar a conciliação.

O Chrome continua sendo necessário para o login manual assistido na Velo. A janela permanece aberta durante e após a conciliação, inclusive em caso de falha. O token capturado permanece somente em memória durante a execução e é descartado ao final. Nenhuma credencial é gravada pelo aplicativo.

## Requisitos

- Windows 10 ou 11 com acesso à internet durante a instalação.
- PowerShell 5.1 ou superior.
- Permissão para instalar programas apenas para o usuário atual.

## Instalação

1. Extraia o arquivo ZIP em uma pasta local, por exemplo `C:\ConciliacaoCartoes`.
2. Abra o PowerShell na pasta extraída.
3. Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\INSTALAR_NO_CLIENTE.ps1
```

O instalador baixa o gerenciador `uv`, instala o Python 3.12 se necessário, cria o ambiente isolado do projeto, instala as bibliotecas declaradas em `pyproject.toml` e baixa o Chromium usado no login manual assistido.

Nenhuma credencial ou token deve ser informado ao instalador. O token Velo só é obtido em memória, depois que o usuário conclui o login manual no Chrome durante uma execução real.

## Uso após a instalação

Coloque os arquivos de Cielo e/ou QuickPay em `data\input` e execute o PowerShell nesta pasta:

```powershell
.\scripts\processar.ps1
```

Para exemplos completos dos comandos e regras de operação, consulte `README.md`. Os arquivos originais de entrada não são alterados; os Excel finais ficam em `planilhas\<data-da-conciliacao>\cielo` e `planilhas\<data-da-conciliacao>\quickpay`. Os JSONs de resultado ficam em `output`, e as respostas de auditoria, quando solicitadas, ficam em `data\api_raw`.

## Verificação opcional

Para confirmar a instalação sem acessar a API real:

```powershell
uv run pytest
uv run conciliacao testar-integracao-velo --fixtures "tests\fixtures\api" --data-inicio 2026-07-14 --data-fim 2026-07-15
```

O segundo comando usa somente dados simulados e não realiza chamadas de rede para a Velo.
