from __future__ import annotations

from conciliacao.utils.text import normalize_text


def test_normalize_text_replaces_nbsp_and_preserves_original():
    source = "Cartao\u00a0de Debito - Quickpay"
    normalized = normalize_text(source)

    assert normalized.original == source
    assert normalized.comparavel == "cartao de debito - quickpay"


def test_normalize_text_removes_accents_and_case_differences():
    assert normalize_text("MasterCard").comparavel == normalize_text("Mastercard").comparavel
    assert normalize_text("Cart\u00e3o de D\u00e9bito - Quickpay").comparavel == (
        normalize_text("CARTAO DE DEBITO - QUICKPAY").comparavel
    )


def test_normalize_text_does_not_change_modality_words():
    assert normalize_text("Cartao de Credito - Quickpay").comparavel != (
        normalize_text("Cartao de Debito - Quickpay").comparavel
    )
