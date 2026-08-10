# Conciliação de cartões — portfólio

Projeto demonstrativo em Python para leitura, validação, conciliação e exportação de relatórios financeiros de duas adquirentes fictícias. A integração com o sistema de caixa é representada por um adaptador HTTP e fixtures locais; este repositório não contém acesso a ambientes reais.

## O que demonstra

- Leitura de planilhas XLSX e relatórios HTML com extensão XLS.
- Validação com localização de erro por arquivo, aba, linha, coluna e célula.
- Regras financeiras baseadas em `Decimal`, sem arredondar divergências para zero.
- Matching determinístico, sem reutilizar um registro do sistema.
- Exportações independentes e atômicas para cada adquirente.
- Modo simulado sem rede, com fixtures sintéticas.
- Proteções para não persistir credenciais, cabeçalhos de autenticação ou respostas reais.

## Dados e segurança

Todos os dados, URLs, endpoints, IDs operacionais e exemplos transacionais reais foram removidos ou substituídos por valores demonstrativos. Os nomes de adquirentes são usados apenas para contextualizar o domínio do problema. Nunca envie arquivos de entrada, saídas, logs, perfis de navegador, arquivos `.env` reais ou respostas de API para o repositório.

O arquivo `.env.example` não contém valor. A configuração de exemplo aponta para `api.example.invalid`, um domínio deliberadamente não operacional.

## Execução local

Requer Python 3.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Para exercitar a integração de forma segura, use somente fixtures locais:

```powershell
conciliacao testar-integracao-velo `
  --fixtures "tests/fixtures/api" `
  --data-inicio 2026-07-14 `
  --data-fim 2026-07-15
```

O comando não acessa a rede nem requer token.

## Estrutura

```text
src/conciliacao/       Aplicação e regras de domínio
tests/fixtures/        Dados sintéticos para testes
config/                Configuração demonstrativa
data/, output/, logs/  Diretórios locais ignorados pelo Git
```

## Limites do exemplo

O adaptador de integração existe para demonstrar arquitetura, validação de contrato e proteção de segredo. Para conectá-lo a qualquer serviço real, use configuração local não versionada, autorização explícita e revisão de segurança.
