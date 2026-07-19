from __future__ import annotations

import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro, StatusConciliacao
from conciliacao.domain.models import RegistroSistema, TransacaoOperadora
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.matching import NivelConfiancaMatching, ReconciliationService


def _tx(
    *,
    operadora: Operadora = Operadora.CIELO,
    modalidade: Modalidade | None = Modalidade.CREDITO,
    bandeira: str = "Visa",
    venda: date = date(2026, 7, 14),
    hora: time = time(10, 0),
    valor: Decimal = Decimal("100.00"),
    linha: int = 1,
) -> TransacaoOperadora:
    return TransacaoOperadora(
        identificador_origem=f"TX-{linha}",
        operadora=operadora,
        modalidade=modalidade,
        bandeira=bandeira,
        data_venda=venda,
        hora_venda=hora,
        data_recebimento=date(2026, 7, 15),
        numero_parcelas=1,
        valor_bruto=valor,
        valor_liquido=valor,
        taxa_original=Decimal("0.00"),
        taxa_normalizada=Decimal("0.00"),
        origem_arquivo=OrigemRegistro.CIELO
        if operadora is Operadora.CIELO
        else OrigemRegistro.QUICKPAY,
        linha_original=linha,
    )


def _reg(
    *,
    operadora: str = "Cielo",
    forma: str = "Cartão de Crédito - Cielo",
    tipo: str | None = "Visa",
    cadastro: date = date(2026, 7, 14),
    vencimento: date = date(2026, 7, 15),
    valor: Decimal = Decimal("100.00"),
    ident: str = "SYS-1",
) -> RegistroSistema:
    return RegistroSistema.model_validate(
        {
            "contaPacotePagamentoUnicoId": ident,
            "operadora": operadora,
            "formaRecebimento": forma,
            "tipo_cartao": tipo,
            "valor": valor,
            "valorTaxaCartao": "999.99",
            "dataCadastro": cadastro,
            "dataVencimento": vencimento,
            "cadastroCaixaId": f"CX-{ident}",
        }
    )


def _cielo_cats(*cats: CategoriaFiltroVelo) -> set[CategoriaFiltroVelo]:
    return set(cats) or {
        CategoriaFiltroVelo.CIELO_CREDITO,
        CategoriaFiltroVelo.CIELO_DEBITO,
        CategoriaFiltroVelo.CIELO_PIX,
    }


def test_simple_equality_matches_once_with_exact_brand_and_zero_difference():
    result = ReconciliationService().conciliar_cielo(
        [_tx()],
        [_reg()],
        _cielo_cats(),
    )

    assert result.resumo.conciliados == 1
    assert result.individuais[0].status is StatusConciliacao.CONCILIADO
    assert result.individuais[0].diferenca == Decimal("0.00")
    assert result.individuais[0].nivel_confianca is NivelConfiancaMatching.EXATO_COM_BANDEIRA
    assert result.individuais[0].correspondencia_individual_comprovada
    assert result.individuais[0].registro_sistema is not None
    assert result.individuais[0].registro_sistema.id_sistema == "SYS-1"


def test_repeated_values_are_multiset_and_not_consumed_twice():
    txs = [_tx(valor=Decimal("2.39"), linha=1), _tx(valor=Decimal("2.39"), linha=2)]
    regs = [
        _reg(valor=Decimal("2.39"), ident="SYS-2"),
        _reg(valor=Decimal("2.39"), ident="SYS-1"),
    ]

    result = ReconciliationService().conciliar_cielo(txs, regs, _cielo_cats())

    matched_ids = [
        item.registro_sistema.id_sistema
        for item in result.individuais
        if item.registro_sistema is not None
    ]
    assert result.resumo.conciliados == 2
    assert sorted(matched_ids) == ["SYS-1", "SYS-2"]
    assert len(matched_ids) == len(set(matched_ids))
    assert result.agregados[0].nivel_especificidade is NivelConfiancaMatching.AGREGADO_REPETIDO
    assert all(not item.correspondencia_individual_comprovada for item in result.individuais)


def test_quantity_divergence_two_operator_one_system_preserves_operator_excess():
    result = ReconciliationService().conciliar_cielo(
        [_tx(valor=Decimal("2.39"), linha=1), _tx(valor=Decimal("2.39"), linha=2)],
        [_reg(valor=Decimal("2.39"), ident="SYS-1")],
        _cielo_cats(),
    )

    assert result.resumo.conciliados == 1
    assert result.resumo.nao_encontrados_no_sistema == 1
    assert result.resumo.divergencias_quantidade == 1
    aggregate = result.agregados[0]
    assert aggregate.quantidade_operadora == 2
    assert aggregate.quantidade_sistema == 1
    assert aggregate.excedente_operadora == 1


def test_quantity_divergence_one_operator_two_system_preserves_system_excess():
    result = ReconciliationService().conciliar_cielo(
        [_tx(valor=Decimal("2.39"), linha=1)],
        [_reg(valor=Decimal("2.39"), ident="SYS-1"), _reg(valor=Decimal("2.39"), ident="SYS-2")],
        _cielo_cats(),
    )

    assert result.resumo.conciliados == 1
    assert result.resumo.nao_encontrados_na_operadora == 1
    assert result.resumo.divergencias_quantidade == 1


def test_different_operator_or_modality_never_matches_same_date_and_value():
    cielo_vs_quickpay = ReconciliationService().conciliar_cielo(
        [_tx(operadora=Operadora.CIELO, valor=Decimal("10.00"))],
        [
            _reg(
                operadora="QuickPay",
                forma="Cartão de Crédito - Quickpay",
                tipo="Visa",
                valor=Decimal("10.00"),
            )
        ],
        _cielo_cats(),
    )
    credit_vs_debit = ReconciliationService().conciliar_cielo(
        [_tx(modalidade=Modalidade.CREDITO, valor=Decimal("10.00"))],
        [_reg(forma="Cartão de Débito - Cielo", valor=Decimal("10.00"))],
        _cielo_cats(),
    )

    assert cielo_vs_quickpay.resumo.conciliados == 0
    assert cielo_vs_quickpay.resumo.nao_encontrados_no_sistema == 1
    assert credit_vs_debit.resumo.conciliados == 0
    assert credit_vs_debit.resumo.nao_encontrados_no_sistema == 1
    assert credit_vs_debit.resumo.nao_encontrados_na_operadora == 1


def test_brand_is_used_when_available_and_missing_brand_can_match_unique_group():
    mismatch = ReconciliationService().conciliar_cielo(
        [_tx(bandeira="Visa", valor=Decimal("10.00"))],
        [_reg(tipo="Mastercard", valor=Decimal("10.00"))],
        _cielo_cats(),
    )
    missing_unique = ReconciliationService().conciliar_cielo(
        [_tx(bandeira="Visa", valor=Decimal("11.00"))],
        [_reg(tipo=None, valor=Decimal("11.00"))],
        _cielo_cats(),
    )

    assert mismatch.resumo.conciliados == 0
    assert mismatch.resumo.nao_encontrados_no_sistema == 1
    assert mismatch.resumo.nao_encontrados_na_operadora == 1
    assert missing_unique.resumo.conciliados == 1
    assert (
        missing_unique.individuais[0].nivel_confianca
        is NivelConfiancaMatching.EXATO_SEM_BANDEIRA
    )


def test_missing_api_brand_with_multiple_operator_brands_is_ambiguous_and_not_consumed():
    result = ReconciliationService().conciliar_cielo(
        [
            _tx(bandeira="Visa", valor=Decimal("10.00"), linha=1),
            _tx(bandeira="Mastercard", valor=Decimal("10.00"), linha=2),
        ],
        [
            _reg(tipo=None, valor=Decimal("10.00"), ident="SYS-1"),
            _reg(tipo=None, valor=Decimal("10.00"), ident="SYS-2"),
        ],
        _cielo_cats(),
    )

    assert result.resumo.conciliados == 0
    assert result.resumo.ambiguidades == 4
    assert all(
        item.status is StatusConciliacao.CORRESPONDENCIA_AMBIGUA for item in result.individuais
    )


def test_matching_uses_sale_date_and_data_cadastro_not_due_dates_or_time():
    result = ReconciliationService().conciliar_cielo(
        [
            _tx(
                venda=date(2026, 7, 14),
                hora=time(23, 59),
                valor=Decimal("20.00"),
                linha=1,
            )
        ],
        [
            _reg(
                cadastro=date(2026, 7, 14),
                vencimento=date(2026, 7, 20),
                valor=Decimal("20.00"),
                ident="SYS-1",
            )
        ],
        _cielo_cats(),
    )
    wrong_cadastro = ReconciliationService().conciliar_cielo(
        [_tx(venda=date(2026, 7, 14), valor=Decimal("20.00"))],
        [_reg(cadastro=date(2026, 7, 15), vencimento=date(2026, 7, 14), valor=Decimal("20.00"))],
        _cielo_cats(),
    )

    assert result.resumo.conciliados == 1
    assert wrong_cadastro.resumo.conciliados == 0


def test_one_cent_difference_is_not_rounded_to_zero_when_group_is_unique():
    result = ReconciliationService().conciliar_cielo(
        [_tx(valor=Decimal("100.00"))],
        [_reg(valor=Decimal("99.99"))],
        _cielo_cats(),
    )

    assert result.resumo.divergencias_valor == 1
    assert result.individuais[0].status is StatusConciliacao.DIVERGENCIA_DE_VALOR
    assert result.individuais[0].diferenca == Decimal("0.01")
    assert isinstance(result.individuais[0].diferenca, Decimal)


def test_missing_category_is_pending_but_empty_consulted_category_is_not_found():
    pending = ReconciliationService().conciliar_cielo(
        [_tx(modalidade=Modalidade.DEBITO, valor=Decimal("206.07"))],
        [],
        {CategoriaFiltroVelo.CIELO_CREDITO, CategoriaFiltroVelo.CIELO_PIX},
    )
    empty_consulted = ReconciliationService().conciliar_cielo(
        [_tx(modalidade=Modalidade.DEBITO, valor=Decimal("206.07"))],
        [],
        _cielo_cats(),
    )

    assert pending.resumo.pendencias_dados == 1
    assert pending.individuais[0].status is StatusConciliacao.PENDENTE_DE_DADOS
    assert empty_consulted.resumo.nao_encontrados_no_sistema == 1
    assert empty_consulted.individuais[0].status is StatusConciliacao.NAO_ENCONTRADO_NO_SISTEMA


def test_cielo_observed_fixture_matches_expected_counts_and_preserves_duplicate_pix():
    transacoes = _load_matching_transactions("cielo_operadora.json", Operadora.CIELO)
    registros = _load_matching_records("cielo_sistema.json")

    result = ReconciliationService().conciliar_cielo(
        transacoes,
        registros,
        {CategoriaFiltroVelo.CIELO_CREDITO, CategoriaFiltroVelo.CIELO_PIX},
    )

    assert result.resumo.conciliados == 10
    assert result.resumo.pendencias_dados == 1
    assert result.resumo.nao_encontrados_na_operadora == 1
    pix_239 = [
        item
        for item in result.individuais
        if item.valor_operadora == Decimal("2.39")
        and item.status is StatusConciliacao.CONCILIADO
    ]
    assert len(pix_239) == 2


def test_quickpay_fixture_matches_and_bank_value_does_not_participate_in_key():
    result = ReconciliationService().conciliar_quickpay(
        _load_matching_transactions("quickpay_operadora.json", Operadora.QUICKPAY),
        _load_matching_records("quickpay_sistema.json"),
        {CategoriaFiltroVelo.QUICKPAY_CREDITO},
    )
    extra = ReconciliationService().conciliar_quickpay(
        _load_matching_transactions("quickpay_operadora.json", Operadora.QUICKPAY),
        _load_matching_records("quickpay_sistema_extra.json"),
        {CategoriaFiltroVelo.QUICKPAY_CREDITO},
    )

    assert result.resumo.conciliados == 2
    assert result.resumo.nao_encontrados_na_operadora == 0
    assert extra.resumo.conciliados == 2
    assert extra.resumo.nao_encontrados_na_operadora == 1


def test_invariants_and_deterministic_summary_are_stable_under_input_order():
    txs = [
        _tx(valor=Decimal("2.39"), linha=1),
        _tx(valor=Decimal("2.39"), linha=2),
        _tx(valor=Decimal("2.90"), linha=3),
    ]
    regs = [
        _reg(valor=Decimal("2.90"), ident="SYS-3"),
        _reg(valor=Decimal("2.39"), ident="SYS-2"),
        _reg(valor=Decimal("2.39"), ident="SYS-1"),
    ]
    service = ReconciliationService()
    first = service.conciliar_cielo(txs, regs, _cielo_cats())
    second = service.conciliar_cielo(list(reversed(txs)), list(reversed(regs)), _cielo_cats())

    assert first.resumo.conciliados == 3
    assert first.resumo.model_dump(mode="json") == second.resumo.model_dump(mode="json")
    op_total = (
        first.resumo.conciliados
        + first.resumo.nao_encontrados_no_sistema
        + first.resumo.ambiguidades
        + first.resumo.pendencias_dados
    )
    sys_total = (
        first.resumo.conciliados
        + first.resumo.nao_encontrados_na_operadora
        + first.resumo.ambiguidades
    )
    assert op_total == first.resumo.transacoes_operadora
    assert sys_total == first.resumo.registros_sistema
    assert first.resumo.total_conciliado <= first.resumo.total_bruto_operadora


def _load_matching_transactions(filename: str, operadora: Operadora) -> list[TransacaoOperadora]:
    payload = json.loads((Path("tests/fixtures/matching") / filename).read_text(encoding="utf-8"))
    return [
        TransacaoOperadora(
            identificador_origem=item["identificador_origem"],
            operadora=operadora,
            modalidade=Modalidade(item["modalidade"]),
            bandeira=item["bandeira"],
            data_venda=date.fromisoformat(item["data_venda"]),
            hora_venda=time.fromisoformat(item["hora_venda"]),
            data_recebimento=date.fromisoformat(item["data_recebimento"]),
            numero_parcelas=item.get("numero_parcelas", 1),
            valor_bruto=item["valor_bruto"],
            valor_liquido=item["valor_liquido"],
            taxa_original=item["taxa_original"],
            taxa_normalizada=item["taxa_original"],
            origem_arquivo=OrigemRegistro.CIELO
            if operadora is Operadora.CIELO
            else OrigemRegistro.QUICKPAY,
            linha_original=item["linha_original"],
            dados_originais={
                "recebido_no_banco_quickpay_normalizado": item.get(
                    "recebido_no_banco_quickpay"
                )
            }
            if "recebido_no_banco_quickpay" in item
            else None,
        )
        for item in payload
    ]


def _load_matching_records(filename: str) -> list[RegistroSistema]:
    payload = json.loads((Path("tests/fixtures/matching") / filename).read_text(encoding="utf-8"))
    return [RegistroSistema.model_validate(item) for item in payload]
