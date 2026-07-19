@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

if not exist "%PROJECT_ROOT%\pyproject.toml" (
    echo [ERRO] Projeto nao localizado.
    echo Orientacao: execute este arquivo a partir da pasta scripts de um clone completo.
    echo Codigo de saida: 1
    echo.
    pause
    exit /b 1
)

pushd "%PROJECT_ROOT%" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%preparar_ambiente.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul

echo.
if not "%EXIT_CODE%"=="0" (
    echo Preparacao falhou com codigo %EXIT_CODE%.
) else (
    echo Preparacao concluida com codigo 0.
)
pause
exit /b %EXIT_CODE%
