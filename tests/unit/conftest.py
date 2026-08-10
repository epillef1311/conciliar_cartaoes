from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro
from conciliacao.domain.models import TransacaoOperadora


@pytest.fixture
def transacao_cielo() -> TransacaoOperadora:
    return TransacaoOperadora(
        identificador_origem="TX-001",
        operadora=Operadora.CIELO,
        modalidade=Modalidade.CREDITO,
        bandeira="Visa",
        data_venda=date(2026, 7, 13),
        valor_bruto=Decimal("126.83"),
        valor_liquido=Decimal("121.77"),
        taxa_normalizada=Decimal("-5.03"),
        taxa_original=Decimal("-5.03"),
        origem_arquivo=OrigemRegistro.CIELO,
        linha_original=11,
        dados_originais={"Bandeira": "Visa"},
    )
