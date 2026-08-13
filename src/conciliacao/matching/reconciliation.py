"""Servico de conciliacao por multiconjunto, sem Excel e sem API HTTP."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from conciliacao.domain.enums import Modalidade, Operadora, SeveridadeAlerta, StatusConciliacao
from conciliacao.domain.models import AlertaValidacao, RegistroSistema, TransacaoOperadora
from conciliacao.integrations.velo.categories import CATEGORIAS_VELO, CategoriaFiltroVelo
from conciliacao.matching.keys import MatchingKey
from conciliacao.matching.models import (
    NivelConfiancaMatching,
    ResultadoAgregadoMatching,
    ResultadoConciliacaoOperadora,
    ResultadoIndividualMatching,
    ResumoConciliacaoOperadora,
)
from conciliacao.matching.multiset_matcher import consumir_deterministicamente
from conciliacao.matching.normalizer import (
    categoria_da_transacao,
    categoria_do_registro,
    categoria_por_operadora_modalidade,
    normalizar_bandeira_operadora,
    normalizar_bandeira_sistema,
    normalizar_modalidade_sistema,
    normalizar_operadora,
)
from conciliacao.utils.currency import quantize_money, sum_money


@dataclass(frozen=True, slots=True)
class _OperatorItem:
    index: int
    transacao: TransacaoOperadora
    categoria: CategoriaFiltroVelo
    key: MatchingKey


@dataclass(frozen=True, slots=True)
class _SystemItem:
    index: int
    registro: RegistroSistema
    categoria: CategoriaFiltroVelo
    key: MatchingKey


class ReconciliationService:
    def conciliar_cielo(
        self,
        transacoes: list[TransacaoOperadora],
        registros_sistema: list[RegistroSistema],
        categorias_consultadas: set[CategoriaFiltroVelo],
    ) -> ResultadoConciliacaoOperadora:
        return self._conciliar_operadora(
            Operadora.CIELO,
            transacoes,
            registros_sistema,
            categorias_consultadas,
        )

    def conciliar_quickpay(
        self,
        transacoes: list[TransacaoOperadora],
        registros_sistema: list[RegistroSistema],
        categorias_consultadas: set[CategoriaFiltroVelo],
    ) -> ResultadoConciliacaoOperadora:
        return self._conciliar_operadora(
            Operadora.QUICKPAY,
            transacoes,
            registros_sistema,
            categorias_consultadas,
        )

    def _conciliar_operadora(
        self,
        operadora: Operadora,
        transacoes: list[TransacaoOperadora],
        registros_sistema: list[RegistroSistema],
        categorias_consultadas: set[CategoriaFiltroVelo],
    ) -> ResultadoConciliacaoOperadora:
        transacoes_operadora = [item for item in transacoes if item.operadora is operadora]
        registros_operadora = [
            item for item in registros_sistema if normalizar_operadora(item.operadora) is operadora
        ]
        esperadas = _categorias_da_operadora(operadora)
        categorias_ausentes = esperadas - categorias_consultadas

        individuais: list[ResultadoIndividualMatching] = []
        agregados: list[ResultadoAgregadoMatching] = []
        operador_items = self._preparar_transacoes(
            transacoes_operadora,
            categorias_consultadas,
            individuais,
            agregados,
        )
        sistema_items = self._preparar_registros(registros_operadora, individuais, agregados)

        consumed_ops: set[int] = set()
        consumed_sys: set[int] = set()
        self._conciliar_divergencia_valor_unica(
            operador_items,
            sistema_items,
            consumed_ops,
            consumed_sys,
            individuais,
            agregados,
        )
        self._conciliar_por_valor(
            [item for item in operador_items if item.index not in consumed_ops],
            [item for item in sistema_items if item.index not in consumed_sys],
            consumed_ops,
            consumed_sys,
            individuais,
            agregados,
        )

        individuais_ordenados = tuple(sorted(individuais, key=_ordem_individual))
        agregados_ordenados = tuple(sorted(agregados, key=lambda item: item.chave_grupo))
        resumo = _resumo(
            operadora,
            transacoes_operadora,
            registros_operadora,
            individuais_ordenados,
            agregados_ordenados,
            categorias_consultadas,
            categorias_ausentes,
        )
        return ResultadoConciliacaoOperadora(
            operadora=operadora,
            individuais=individuais_ordenados,
            agregados=agregados_ordenados,
            resumo=resumo,
        )

    def _preparar_transacoes(
        self,
        transacoes: list[TransacaoOperadora],
        categorias_consultadas: set[CategoriaFiltroVelo],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching],
    ) -> list[_OperatorItem]:
        items: list[_OperatorItem] = []
        for index, transacao in enumerate(transacoes):
            categoria = categoria_da_transacao(transacao)
            if categoria is None:
                fallback_key = _fallback_key_transacao(transacao, "MODALIDADE_DESCONHECIDA")
                individuais.append(
                    _individual_operadora(
                        transacao,
                        status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                        nivel=NivelConfiancaMatching.AMBIGUO,
                        chave=fallback_key,
                        motivo="Modalidade da operadora nao resolvida para matching.",
                    )
                )
                agregados.append(
                    _agregado_operadora_somente(
                        fallback_key,
                        transacao.valor_bruto,
                        status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                        nivel=NivelConfiancaMatching.AMBIGUO,
                    )
                )
                continue
            if categoria not in categorias_consultadas:
                fallback_key = _fallback_key_transacao(transacao, categoria.value)
                individuais.append(
                    _individual_operadora(
                        transacao,
                        status=StatusConciliacao.PENDENTE_DE_DADOS,
                        nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                        chave=fallback_key,
                        motivo="Categoria Velo nao consultada; ausencia no sistema nao confirmada.",
                    )
                )
                agregados.append(
                    _agregado_operadora_somente(
                        fallback_key,
                        transacao.valor_bruto,
                        status=StatusConciliacao.PENDENTE_DE_DADOS,
                        nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                    )
                )
                continue
            if transacao.modalidade is None:
                continue
            data_matching = _data_matching_transacao(transacao)
            if data_matching is None:
                fallback_key = _fallback_key_transacao(transacao, "DATA_RECEBIMENTO_AUSENTE")
                individuais.append(
                    _individual_operadora(
                        transacao,
                        status=StatusConciliacao.PENDENTE_DE_DADOS,
                        nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                        chave=fallback_key,
                        motivo="Débito sem data de recebimento confiável para matching.",
                    )
                )
                agregados.append(
                    _agregado_operadora_somente(
                        fallback_key,
                        transacao.valor_bruto,
                        status=StatusConciliacao.PENDENTE_DE_DADOS,
                        nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                    )
                )
                continue
            key = MatchingKey(
                operadora=transacao.operadora,
                modalidade=transacao.modalidade,
                data=data_matching,
                valor=quantize_money(transacao.valor_bruto),
                bandeira=normalizar_bandeira_operadora(transacao),
            )
            items.append(
                _OperatorItem(index=index, transacao=transacao, categoria=categoria, key=key)
            )
        return items

    def _preparar_registros(
        self,
        registros: list[RegistroSistema],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching],
    ) -> list[_SystemItem]:
        items: list[_SystemItem] = []
        for index, registro in enumerate(registros):
            categoria = categoria_do_registro(registro)
            operadora: Operadora | None
            modalidade: Modalidade | None
            if categoria is not None:
                categoria_info = CATEGORIAS_VELO[categoria]
                operadora = categoria_info.operadora
                modalidade = categoria_info.modalidade
            else:
                operadora = normalizar_operadora(registro.operadora)
                modalidade = normalizar_modalidade_sistema(registro.forma_recebimento)
            if operadora is None or modalidade is None or categoria is None:
                fallback_key = _fallback_key_registro(registro, "SISTEMA_DESCONHECIDO")
                individuais.append(
                    _individual_sistema(
                        registro,
                        status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                        nivel=NivelConfiancaMatching.AMBIGUO,
                        chave=fallback_key,
                        motivo="Registro do sistema sem operadora/modalidade confiavel.",
                    )
                )
                agregados.append(
                    _agregado_sistema_somente(
                        fallback_key,
                        registro.valor,
                        status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                        nivel=NivelConfiancaMatching.AMBIGUO,
                    )
                )
                continue
            key = MatchingKey(
                operadora=operadora,
                modalidade=modalidade,
                data=_data_matching_registro(registro, modalidade),
                valor=quantize_money(registro.valor),
                bandeira=normalizar_bandeira_sistema(registro),
            )
            items.append(_SystemItem(index=index, registro=registro, categoria=categoria, key=key))
        return items

    def _conciliar_divergencia_valor_unica(
        self,
        operadores: list[_OperatorItem],
        sistemas: list[_SystemItem],
        consumed_ops: set[int],
        consumed_sys: set[int],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching],
    ) -> None:
        by_operator = _group_operadores_sem_valor(operadores)
        by_system = _group_sistemas_sem_valor(sistemas)
        for key, op_items in by_operator.items():
            sys_items = by_system.get(key, [])
            if len(op_items) != 1 or len(sys_items) != 1:
                continue
            op_item = op_items[0]
            sys_item = sys_items[0]
            if op_item.index in consumed_ops or sys_item.index in consumed_sys:
                continue
            if op_item.key.valor == sys_item.key.valor:
                continue
            if not _bandeiras_compativeis(op_item.key.bandeira, sys_item.key.bandeira):
                continue
            chave = MatchingKey(
                operadora=op_item.key.operadora,
                modalidade=op_item.key.modalidade,
                data=op_item.key.data,
                valor=op_item.key.valor,
                bandeira=op_item.key.bandeira or sys_item.key.bandeira,
            ).serialize()
            diferenca = quantize_money(op_item.transacao.valor_bruto - sys_item.registro.valor)
            individuais.append(
                ResultadoIndividualMatching(
                    transacao_operadora=op_item.transacao,
                    registro_sistema=sys_item.registro,
                    status=StatusConciliacao.DIVERGENCIA_DE_VALOR,
                    valor_operadora=op_item.transacao.valor_bruto,
                    valor_sistema=sys_item.registro.valor,
                    diferenca=diferenca,
                    chave_utilizada=chave,
                    nivel_confianca=NivelConfiancaMatching.AGREGADO_UNICO,
                    motivo=(
                        "Grupo unico por operadora, modalidade, data e bandeira "
                        "com valor divergente."
                    ),
                    identificador_grupo=chave,
                    correspondencia_atribuida_deterministicamente=True,
                    alertas=[
                        _alerta("MATCHING_DIVERGENCIA_VALOR", "Valor diverge em grupo unico.")
                    ],
                )
            )
            agregados.append(
                ResultadoAgregadoMatching(
                    chave_grupo=chave,
                    quantidade_operadora=1,
                    quantidade_sistema=1,
                    quantidade_conciliada=0,
                    excedente_operadora=0,
                    excedente_sistema=0,
                    total_operadora=op_item.transacao.valor_bruto,
                    total_sistema=sys_item.registro.valor,
                    diferenca_total=diferenca,
                    status=StatusConciliacao.DIVERGENCIA_DE_VALOR,
                    nivel_especificidade=NivelConfiancaMatching.AGREGADO_UNICO,
                    alertas=[
                        _alerta("MATCHING_DIVERGENCIA_VALOR", "Valor diverge em grupo unico.")
                    ],
                )
            )
            consumed_ops.add(op_item.index)
            consumed_sys.add(sys_item.index)

    def _conciliar_por_valor(
        self,
        operadores: list[_OperatorItem],
        sistemas: list[_SystemItem],
        consumed_ops: set[int],
        consumed_sys: set[int],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching],
    ) -> None:
        base_keys = sorted({item.key.sem_bandeira() for item in operadores + sistemas})
        ops_by_base = _group_operadores_by_base(operadores)
        sys_by_base = _group_sistemas_by_base(sistemas)
        for base in base_keys:
            op_items = ops_by_base.get(base, [])
            sys_items = sys_by_base.get(base, [])
            if not op_items:
                self._registrar_sobras_sistema(sys_items, individuais, agregados)
                consumed_sys.update(item.index for item in sys_items)
                continue
            if not sys_items:
                self._registrar_sobras_operadora(op_items, individuais, agregados)
                consumed_ops.update(item.index for item in op_items)
                continue
            if _grupo_ambiguo_por_bandeira(op_items, sys_items):
                self._registrar_ambiguidade(op_items, sys_items, individuais, agregados)
                continue
            subgrupos = _subgrupos_por_bandeira(op_items, sys_items)
            for grouped_ops, grouped_sys, brand_used in subgrupos:
                self._conciliar_grupo(
                    grouped_ops,
                    grouped_sys,
                    brand_used,
                    consumed_ops,
                    consumed_sys,
                    individuais,
                    agregados,
                )

    def _conciliar_grupo(
        self,
        operadores: list[_OperatorItem],
        sistemas: list[_SystemItem],
        brand_used: bool,
        consumed_ops: set[int],
        consumed_sys: set[int],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching],
    ) -> None:
        consumo = consumir_deterministicamente(
            operadores,
            sistemas,
            order_left=_order_operator,
            order_right=_order_system,
        )
        quantidade_conciliada = len(consumo.pares)
        chave = _chave_grupo(operadores, sistemas)
        status_agregado = (
            StatusConciliacao.CONCILIADO
            if len(operadores) == len(sistemas)
            else StatusConciliacao.DIVERGENCIA_DE_QUANTIDADE
        )
        nivel = _nivel_grupo(len(operadores), len(sistemas), brand_used)
        agregados.append(
            ResultadoAgregadoMatching(
                chave_grupo=chave,
                quantidade_operadora=len(operadores),
                quantidade_sistema=len(sistemas),
                quantidade_conciliada=quantidade_conciliada,
                excedente_operadora=len(consumo.sobras_esquerda),
                excedente_sistema=len(consumo.sobras_direita),
                total_operadora=sum_money(item.transacao.valor_bruto for item in operadores),
                total_sistema=sum_money(item.registro.valor for item in sistemas),
                diferenca_total=quantize_money(
                    sum_money(item.transacao.valor_bruto for item in operadores)
                    - sum_money(item.registro.valor for item in sistemas)
                ),
                status=status_agregado,
                nivel_especificidade=nivel,
                alertas=(
                    [_alerta("MATCHING_DIVERGENCIA_QUANTIDADE", "Quantidade divergente.")]
                    if status_agregado is StatusConciliacao.DIVERGENCIA_DE_QUANTIDADE
                    else []
                ),
            )
        )
        for op_item, sys_item in consumo.pares:
            diff = quantize_money(op_item.transacao.valor_bruto - sys_item.registro.valor)
            individuais.append(
                ResultadoIndividualMatching(
                    transacao_operadora=op_item.transacao,
                    registro_sistema=sys_item.registro,
                    status=StatusConciliacao.CONCILIADO,
                    valor_operadora=op_item.transacao.valor_bruto,
                    valor_sistema=sys_item.registro.valor,
                    diferenca=diff,
                    chave_utilizada=chave,
                    nivel_confianca=nivel,
                    motivo=(
                        "Correspondencia unica por chave."
                        if len(operadores) == len(sistemas) == 1
                        else (
                            "Ocorrencia conciliada no agregado; "
                            "pareamento individual nao comprovado."
                        )
                    ),
                    identificador_grupo=chave,
                    correspondencia_individual_comprovada=len(operadores) == len(sistemas) == 1,
                    correspondencia_atribuida_deterministicamente=not (
                        len(operadores) == len(sistemas) == 1
                    ),
                )
            )
            consumed_ops.add(op_item.index)
            consumed_sys.add(sys_item.index)
        self._registrar_sobras_operadora(list(consumo.sobras_esquerda), individuais, agregados=None)
        self._registrar_sobras_sistema(list(consumo.sobras_direita), individuais, agregados=None)

    def _registrar_sobras_operadora(
        self,
        items: list[_OperatorItem],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching] | None,
    ) -> None:
        for item in items:
            chave = item.key.serialize()
            individuais.append(
                _individual_operadora(
                    item.transacao,
                    status=StatusConciliacao.NAO_ENCONTRADO_NO_SISTEMA,
                    nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                    chave=chave,
                    motivo="Nao ha registro disponivel no sistema com chave compativel.",
                )
            )
            if agregados is not None:
                agregados.append(
                    _agregado_operadora_somente(
                        chave,
                        item.transacao.valor_bruto,
                        status=StatusConciliacao.NAO_ENCONTRADO_NO_SISTEMA,
                        nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                    )
                )

    def _registrar_sobras_sistema(
        self,
        items: list[_SystemItem],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching] | None,
    ) -> None:
        for item in items:
            chave = item.key.serialize()
            individuais.append(
                _individual_sistema(
                    item.registro,
                    status=StatusConciliacao.NAO_ENCONTRADO_NA_OPERADORA,
                    nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                    chave=chave,
                    motivo="Registro do sistema sem transacao correspondente na operadora.",
                )
            )
            if agregados is not None:
                agregados.append(
                    _agregado_sistema_somente(
                        chave,
                        item.registro.valor,
                        status=StatusConciliacao.NAO_ENCONTRADO_NA_OPERADORA,
                        nivel=NivelConfiancaMatching.NAO_CORRESPONDIDO,
                    )
                )

    def _registrar_ambiguidade(
        self,
        operadores: list[_OperatorItem],
        sistemas: list[_SystemItem],
        individuais: list[ResultadoIndividualMatching],
        agregados: list[ResultadoAgregadoMatching],
    ) -> None:
        chave = _chave_grupo(operadores, sistemas)
        alerta = _alerta(
            "MATCHING_AMBIGUO",
            "Bandeira ou forma de recebimento insuficiente para consumir registros.",
        )
        for op_item in operadores:
            individuais.append(
                _individual_operadora(
                    op_item.transacao,
                    status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                    nivel=NivelConfiancaMatching.AMBIGUO,
                    chave=chave,
                    motivo="Mais de uma correspondencia possivel sem bandeira confiavel.",
                    alertas=[alerta],
                )
            )
        for sys_item in sistemas:
            individuais.append(
                _individual_sistema(
                    sys_item.registro,
                    status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                    nivel=NivelConfiancaMatching.AMBIGUO,
                    chave=chave,
                    motivo="Registro do sistema participa de grupo ambiguo.",
                    alertas=[alerta],
                )
            )
        agregados.append(
            ResultadoAgregadoMatching(
                chave_grupo=chave,
                quantidade_operadora=len(operadores),
                quantidade_sistema=len(sistemas),
                quantidade_conciliada=0,
                excedente_operadora=len(operadores),
                excedente_sistema=len(sistemas),
                total_operadora=sum_money(item.transacao.valor_bruto for item in operadores),
                total_sistema=sum_money(item.registro.valor for item in sistemas),
                diferenca_total=quantize_money(
                    sum_money(item.transacao.valor_bruto for item in operadores)
                    - sum_money(item.registro.valor for item in sistemas)
                ),
                status=StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
                nivel_especificidade=NivelConfiancaMatching.AMBIGUO,
                alertas=[alerta],
            )
        )


def _categorias_da_operadora(operadora: Operadora) -> set[CategoriaFiltroVelo]:
    return {
        categoria_por_operadora_modalidade(operadora, Modalidade.CREDITO),
        categoria_por_operadora_modalidade(operadora, Modalidade.DEBITO),
        categoria_por_operadora_modalidade(operadora, Modalidade.PIX),
    }


SemValorKey = tuple[Operadora, Modalidade, date, str | None]


def _group_operadores_sem_valor(items: Iterable[_OperatorItem]) -> dict[
    SemValorKey, list[_OperatorItem]
]:
    grouped: dict[SemValorKey, list[_OperatorItem]] = defaultdict(list)
    for item in items:
        grouped[item.key.sem_valor()].append(item)
    return grouped


def _group_sistemas_sem_valor(items: Iterable[_SystemItem]) -> dict[SemValorKey, list[_SystemItem]]:
    grouped: dict[SemValorKey, list[_SystemItem]] = defaultdict(list)
    for item in items:
        grouped[item.key.sem_valor()].append(item)
    return grouped


def _group_operadores_by_base(items: Iterable[_OperatorItem]) -> dict[
    MatchingKey, list[_OperatorItem]
]:
    grouped: dict[MatchingKey, list[_OperatorItem]] = defaultdict(list)
    for item in items:
        grouped[item.key.sem_bandeira()].append(item)
    return grouped


def _group_sistemas_by_base(items: Iterable[_SystemItem]) -> dict[MatchingKey, list[_SystemItem]]:
    grouped: dict[MatchingKey, list[_SystemItem]] = defaultdict(list)
    for item in items:
        grouped[item.key.sem_bandeira()].append(item)
    return grouped


def _subgrupos_por_bandeira(
    operadores: list[_OperatorItem],
    sistemas: list[_SystemItem],
) -> list[tuple[list[_OperatorItem], list[_SystemItem], bool]]:
    sys_brands = {item.key.bandeira for item in sistemas if item.key.bandeira}
    if not sys_brands:
        return [(operadores, sistemas, False)]
    groups: list[tuple[list[_OperatorItem], list[_SystemItem], bool]] = []
    all_brands = sys_brands | {item.key.bandeira for item in operadores if item.key.bandeira}
    for brand in sorted(all_brands):
        groups.append(
            (
                [item for item in operadores if item.key.bandeira == brand],
                [item for item in sistemas if item.key.bandeira == brand],
                True,
            )
        )
    unbranded_ops = [item for item in operadores if item.key.bandeira is None]
    unbranded_sys = [item for item in sistemas if item.key.bandeira is None]
    if unbranded_ops or unbranded_sys:
        groups.append((unbranded_ops, unbranded_sys, False))
    return groups


def _grupo_ambiguo_por_bandeira(
    operadores: list[_OperatorItem], sistemas: list[_SystemItem]
) -> bool:
    op_brands = {item.key.bandeira for item in operadores if item.key.bandeira}
    sys_brands = {item.key.bandeira for item in sistemas if item.key.bandeira}
    return bool(op_brands) and not sys_brands and len(op_brands) > 1 and len(sistemas) > 1


def _bandeiras_compativeis(left: str | None, right: str | None) -> bool:
    return left is None or right is None or left == right


def _nivel_grupo(qtd_operadora: int, qtd_sistema: int, brand_used: bool) -> NivelConfiancaMatching:
    if qtd_operadora == qtd_sistema == 1:
        return (
            NivelConfiancaMatching.EXATO_COM_BANDEIRA
            if brand_used
            else NivelConfiancaMatching.EXATO_SEM_BANDEIRA
        )
    if min(qtd_operadora, qtd_sistema) == 1:
        return NivelConfiancaMatching.AGREGADO_UNICO
    return NivelConfiancaMatching.AGREGADO_REPETIDO


def _chave_grupo(
    operadores: list[_OperatorItem],
    sistemas: list[_SystemItem],
) -> str:
    key = operadores[0].key if operadores else sistemas[0].key
    return MatchingKey(
        key.operadora,
        key.modalidade,
        key.data,
        key.valor,
        key.bandeira,
    ).serialize()


def _fallback_key_transacao(transacao: TransacaoOperadora, suffix: str) -> str:
    return "|".join(
        [
            transacao.operadora.value,
            transacao.modalidade.value if transacao.modalidade else "SEM_MODALIDADE",
            (_data_matching_transacao(transacao) or transacao.data_venda).isoformat(),
            f"{transacao.valor_bruto:.2f}",
            suffix,
        ]
    )


def _data_matching_transacao(transacao: TransacaoOperadora) -> date | None:
    """Débitos são conciliados pela data de recebimento; demais modalidades, pela venda."""
    if transacao.modalidade is Modalidade.DEBITO:
        return transacao.data_recebimento
    return transacao.data_venda


def _data_matching_registro(registro: RegistroSistema, modalidade: Modalidade) -> date:
    """No débito, a data de vencimento Velo representa o recebimento da operadora."""
    if modalidade is Modalidade.DEBITO:
        return registro.data_vencimento
    return registro.data_cadastro


def _fallback_key_registro(registro: RegistroSistema, suffix: str) -> str:
    return "|".join(
        [
            str(registro.operadora),
            str(registro.forma_recebimento),
            registro.data_cadastro.isoformat(),
            f"{registro.valor:.2f}",
            suffix,
        ]
    )


def _individual_operadora(
    transacao: TransacaoOperadora,
    *,
    status: StatusConciliacao,
    nivel: NivelConfiancaMatching,
    chave: str,
    motivo: str,
    alertas: list[AlertaValidacao] | None = None,
) -> ResultadoIndividualMatching:
    return ResultadoIndividualMatching(
        transacao_operadora=transacao,
        status=status,
        valor_operadora=transacao.valor_bruto,
        diferenca=None,
        chave_utilizada=chave,
        nivel_confianca=nivel,
        motivo=motivo,
        identificador_grupo=chave,
        alertas=alertas or [],
    )


def _individual_sistema(
    registro: RegistroSistema,
    *,
    status: StatusConciliacao,
    nivel: NivelConfiancaMatching,
    chave: str,
    motivo: str,
    alertas: list[AlertaValidacao] | None = None,
) -> ResultadoIndividualMatching:
    return ResultadoIndividualMatching(
        registro_sistema=registro,
        status=status,
        valor_sistema=registro.valor,
        diferenca=None,
        chave_utilizada=chave,
        nivel_confianca=nivel,
        motivo=motivo,
        identificador_grupo=chave,
        alertas=alertas or [],
    )


def _agregado_operadora_somente(
    chave: str,
    valor: Decimal,
    *,
    status: StatusConciliacao,
    nivel: NivelConfiancaMatching,
) -> ResultadoAgregadoMatching:
    return ResultadoAgregadoMatching(
        chave_grupo=chave,
        quantidade_operadora=1,
        quantidade_sistema=0,
        quantidade_conciliada=0,
        excedente_operadora=1,
        excedente_sistema=0,
        total_operadora=valor,
        total_sistema=Decimal("0.00"),
        diferenca_total=valor,
        status=status,
        nivel_especificidade=nivel,
    )


def _agregado_sistema_somente(
    chave: str,
    valor: Decimal,
    *,
    status: StatusConciliacao,
    nivel: NivelConfiancaMatching,
) -> ResultadoAgregadoMatching:
    return ResultadoAgregadoMatching(
        chave_grupo=chave,
        quantidade_operadora=0,
        quantidade_sistema=1,
        quantidade_conciliada=0,
        excedente_operadora=0,
        excedente_sistema=1,
        total_operadora=Decimal("0.00"),
        total_sistema=valor,
        diferenca_total=quantize_money(Decimal("0.00") - valor),
        status=status,
        nivel_especificidade=nivel,
    )


def _alerta(codigo: str, mensagem: str) -> AlertaValidacao:
    return AlertaValidacao(
        codigo=codigo,
        mensagem=mensagem,
        severidade=SeveridadeAlerta.AVISO,
    )


def _order_operator(item: _OperatorItem) -> tuple[object, ...]:
    return (
        item.transacao.data_venda,
        item.transacao.hora_venda or time.min,
        item.transacao.linha_original,
        item.transacao.identificador_origem or "",
    )


def _order_system(item: _SystemItem) -> tuple[object, ...]:
    return (item.registro.data_cadastro, item.registro.id_sistema, item.index)


def _ordem_individual(item: ResultadoIndividualMatching) -> tuple[object, ...]:
    if item.transacao_operadora is not None:
        return (
            0,
            item.transacao_operadora.data_venda,
            item.transacao_operadora.hora_venda or time.min,
            item.transacao_operadora.linha_original,
            item.status.value,
        )
    assert item.registro_sistema is not None
    return (
        1,
        item.registro_sistema.data_cadastro,
        item.registro_sistema.id_sistema,
        item.status.value,
    )


def _resumo(
    operadora: Operadora,
    transacoes: list[TransacaoOperadora],
    registros: list[RegistroSistema],
    individuais: tuple[ResultadoIndividualMatching, ...],
    agregados: tuple[ResultadoAgregadoMatching, ...],
    categorias_consultadas: set[CategoriaFiltroVelo],
    categorias_ausentes: set[CategoriaFiltroVelo],
) -> ResumoConciliacaoOperadora:
    counts = {status: 0 for status in StatusConciliacao}
    for item in individuais:
        if item.transacao_operadora is not None or item.status in {
            StatusConciliacao.NAO_ENCONTRADO_NA_OPERADORA,
            StatusConciliacao.CORRESPONDENCIA_AMBIGUA,
        }:
            counts[item.status] += 1
    divergencias_quantidade = sum(
        1 for item in agregados if item.status is StatusConciliacao.DIVERGENCIA_DE_QUANTIDADE
    )
    total_conciliado = sum_money(
        item.valor_operadora or Decimal("0.00")
        for item in individuais
        if item.status is StatusConciliacao.CONCILIADO and item.transacao_operadora is not None
    )
    total_operadora = sum_money(item.valor_bruto for item in transacoes)
    total_sistema = sum_money(item.valor for item in registros)
    return ResumoConciliacaoOperadora(
        operadora=operadora,
        transacoes_operadora=len(transacoes),
        registros_sistema=len(registros),
        conciliados=counts[StatusConciliacao.CONCILIADO],
        nao_encontrados_no_sistema=counts[StatusConciliacao.NAO_ENCONTRADO_NO_SISTEMA],
        nao_encontrados_na_operadora=counts[StatusConciliacao.NAO_ENCONTRADO_NA_OPERADORA],
        divergencias_quantidade=divergencias_quantidade,
        divergencias_valor=counts[StatusConciliacao.DIVERGENCIA_DE_VALOR],
        ambiguidades=counts[StatusConciliacao.CORRESPONDENCIA_AMBIGUA],
        pendencias_dados=counts[StatusConciliacao.PENDENTE_DE_DADOS],
        total_bruto_operadora=total_operadora,
        total_sistema=total_sistema,
        total_conciliado=total_conciliado,
        diferenca_total=quantize_money(total_operadora - total_sistema),
        categorias_consultadas=categorias_consultadas,
        categorias_ausentes=categorias_ausentes,
    )
