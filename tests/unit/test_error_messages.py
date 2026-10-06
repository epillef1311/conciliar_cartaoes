import pytest

from conciliacao.domain.enums import SeveridadeAlerta
from conciliacao.domain.models import AlertaValidacao
from conciliacao.integrations.velo.exceptions import VeloAuthenticationError
from conciliacao.readers.exceptions import ValorMonetarioInvalidoError
from conciliacao.validators.formatter import formatar_alerta
from conciliacao.workflow import _safe_error


def test_validation_message_preserves_original_location():
    alerta = AlertaValidacao(
        codigo="VALOR_INVALIDO",
        mensagem="Valor monetário inválido.",
        severidade=SeveridadeAlerta.ERRO,
        arquivo="entrada.xlsx",
        aba="Vendas",
        linha=18,
        coluna="F",
        celula="F18",
    )
    mensagem = formatar_alerta(alerta)
    for detalhe in ("Valor monetário inválido", "entrada.xlsx", "Vendas", "Linha: 18", "F18"):
        assert detalhe in mensagem


def test_reader_error_preserves_original_location():
    mensagem = _safe_error(
        ValorMonetarioInvalidoError(
            "Valor inválido",
            arquivo="entrada.xlsx",
            aba="Vendas",
            linha=18,
            celula="F18",
        )
    )
    assert "Linha: 18" in mensagem
    assert "Célula: F18" in mensagem


def test_login_error_keeps_specific_reason_without_exposing_cause():
    erro = VeloAuthenticationError(
        "Google Chrome nao foi localizado.",
        endpoint="authentication",
        cause=RuntimeError("segredo-nao-exibir"),
    )
    mensagem = _safe_error(erro)
    assert "Google Chrome nao foi localizado" in mensagem
    assert "segredo-nao-exibir" not in mensagem


def test_numeric_error_gets_description():
    assert not _safe_error(Exception("13")).isdecimal()


@pytest.mark.parametrize(
    "template",
    [
        "Authorization: Bearer {}",
        "authorization: bearer {}",
        "AUTHORIZATION: BEARER {}",
        "{{'aUtHoRiZaTiOn': 'bEaReR {}'}}",
        "Authorization: Basic {}",
        "access_token={}",
        "Cookie: session={}",
        "senha={}",
        "password={}",
        "Falha\nAuthorization: Bearer\n{}",
    ],
)
def test_error_message_omits_entire_sensitive_content(template):
    artificial_secret = "segredo-ficticio-de-regressao"
    mensagem = _safe_error(Exception(template.format(artificial_secret)))

    assert artificial_secret not in mensagem
    assert "authorization" not in mensagem.casefold()
    assert "bearer" not in mensagem.casefold()
    assert mensagem.strip()


def test_error_location_cannot_reintroduce_sensitive_content():
    artificial_secret = "segredo-ficticio-de-regressao"
    erro = ValorMonetarioInvalidoError(
        "Valor inválido", arquivo="entrada.xlsx", aba=f"Bearer {artificial_secret}", linha=18
    )

    assert artificial_secret not in _safe_error(erro)
