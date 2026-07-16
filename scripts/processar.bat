@echo off
set "PYTHONPATH=%~dp0..\src;%PYTHONPATH%"
if exist "%~dp0..\.venv\Scripts\python.exe" (
  "%~dp0..\.venv\Scripts\python.exe" -m conciliacao.cli processar %*
) else (
  python -m conciliacao.cli processar %*
)
exit /b %ERRORLEVEL%
