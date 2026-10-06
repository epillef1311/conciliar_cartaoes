import pytest

from conciliacao.matching.normalizer import normalizar_bandeira_texto


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Cred. Mastercard", "mastercard"),
        ("Master Card", "mastercard"),
        ("Cred. Visa", "visa"),
        ("Déb. Elo", "elo"),
        ("Hipercard", "hipercard"),
        ("American Express", "amex"),
        ("AMEX", "amex"),
        ("  Marca Á  ", "marca a"),
        ("Visao", "visao"),
        ("MasterNova", "masternova"),
        ("Visa Mastercard", "visa mastercard"),
        (None, None),
        (5, None),
        ("5", None),
        ("", None),
        ("Não informado", None),
        ("Cartão de Crédito", None),
    ],
)
def test_explicit_brand_normalization_is_conservative(value, expected):
    assert normalizar_bandeira_texto(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Cartão de Crédito - Cielo", None),
        ("Cartão de Débito - QuickPay", None),
        ("Cartão de Crédito - Visa", "visa"),
        ("Cartão de Crédito - Elo", "elo"),
        ("Marca A", None),
    ],
)
def test_receipt_description_only_provides_a_recognized_brand(value, expected):
    assert normalizar_bandeira_texto(value, preservar_desconhecida=False) == expected
