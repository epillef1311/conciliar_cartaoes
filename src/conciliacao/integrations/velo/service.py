"""Servico de integracao Velo sem regras de matching."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from conciliacao.domain.models import RegistroSistema
from conciliacao.integrations.velo.categories import (
    CATEGORIAS_VELO,
    CategoriaFiltroVelo,
    categorias_cielo,
    categorias_quickpay,
    todas_categorias,
)
from conciliacao.integrations.velo.client import VeloClient
from conciliacao.integrations.velo.exceptions import VeloSchemaError
from conciliacao.integrations.velo.schemas import FormaRecebimentoApi
from conciliacao.utils.dates import validate_period
from conciliacao.utils.text import normalize_text


@dataclass(frozen=True, slots=True)
class AvisoResolucaoForma:
    codigo: str
    mensagem: str
    categoria: CategoriaFiltroVelo | None = None
    descricao_origem: str | None = None


@dataclass(frozen=True, slots=True)
class ResolucaoFormasRecebimento:
    ids_por_categoria: dict[CategoriaFiltroVelo, int]
    avisos: tuple[AvisoResolucaoForma, ...] = ()

    def id_para(self, categoria: CategoriaFiltroVelo) -> int:
        return self.ids_por_categoria[categoria]


@dataclass(frozen=True, slots=True)
class ResultadoConsultaVelo:
    registros_por_categoria: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]]
    avisos: tuple[AvisoResolucaoForma, ...] = ()

    @property
    def total_registros(self) -> int:
        return sum(len(registros) for registros in self.registros_por_categoria.values())


class VeloIntegrationService:
    def __init__(self, client: VeloClient) -> None:
        self.client = client

    def resolver_formas_recebimento(self) -> ResolucaoFormasRecebimento:
        formas = self.client.autocomplete_operadoras()
        ids: dict[CategoriaFiltroVelo, int] = {}
        id_owner: dict[int, CategoriaFiltroVelo] = {}
        avisos: list[AvisoResolucaoForma] = []

        for forma in formas:
            categoria, aviso = _classificar_forma(forma)
            if aviso is not None:
                avisos.append(aviso)
            if categoria is None:
                avisos.append(
                    AvisoResolucaoForma(
                        codigo="VELO_FORMA_DESCONHECIDA",
                        mensagem="Forma de recebimento retornada pela API nao foi usada.",
                        descricao_origem=forma.descricao,
                    )
                )
                continue
            if categoria in ids and ids[categoria] != forma.id:
                raise VeloSchemaError(
                    "Autocomplete Velo retornou IDs distintos para a mesma modalidade.",
                    endpoint=self.client.config.endpoints.autocomplete_operadoras,
                    context={"categoria": categoria.value, "descricao": forma.descricao},
                )
            existing_owner = id_owner.get(forma.id)
            if existing_owner is not None and existing_owner is not categoria:
                raise VeloSchemaError(
                    "Autocomplete Velo retornou o mesmo ID para modalidades diferentes.",
                    endpoint=self.client.config.endpoints.autocomplete_operadoras,
                    context={
                        "id": forma.id,
                        "categoria": categoria.value,
                        "categoria_existente": existing_owner.value,
                    },
                )
            ids[categoria] = forma.id
            id_owner[forma.id] = categoria

        for categoria in todas_categorias():
            if categoria not in ids:
                fallback = self.client.config.formas_recebimento_fallback[categoria]
                ids[categoria] = fallback
                avisos.append(
                    AvisoResolucaoForma(
                        codigo="VELO_FALLBACK_FORMA_RECEBIMENTO",
                        mensagem="Fallback configurado usado para forma de recebimento.",
                        categoria=categoria,
                    )
                )

        return ResolucaoFormasRecebimento(ids_por_categoria=ids, avisos=tuple(avisos))

    def consultar_categoria(
        self,
        categoria: CategoriaFiltroVelo,
        *,
        data_inicio: date,
        data_fim: date,
        resolucao: ResolucaoFormasRecebimento | None = None,
    ) -> tuple[RegistroSistema, ...]:
        inicio, fim = validate_period(data_inicio, data_fim)
        resolved = resolucao or self.resolver_formas_recebimento()
        filtro_forma_recebimento_id = resolved.id_para(categoria)
        registros = self.client.consultar_conciliacao(
            categoria=categoria,
            filtro_forma_recebimento_id=filtro_forma_recebimento_id,
            data_inicio=inicio,
            data_fim=fim,
        )
        return tuple(registros)

    def consultar_cielo(self, *, data_inicio: date, data_fim: date) -> ResultadoConsultaVelo:
        return self._consultar_categorias(
            categorias_cielo(),
            data_inicio=data_inicio,
            data_fim=data_fim,
        )

    def consultar_quickpay(self, *, data_inicio: date, data_fim: date) -> ResultadoConsultaVelo:
        return self._consultar_categorias(
            categorias_quickpay(), data_inicio=data_inicio, data_fim=data_fim
        )

    def consultar_todas(self, *, data_inicio: date, data_fim: date) -> ResultadoConsultaVelo:
        return self._consultar_categorias(
            todas_categorias(),
            data_inicio=data_inicio,
            data_fim=data_fim,
        )

    def _consultar_categorias(
        self,
        categorias: Iterable[CategoriaFiltroVelo],
        *,
        data_inicio: date,
        data_fim: date,
    ) -> ResultadoConsultaVelo:
        inicio, fim = validate_period(data_inicio, data_fim)
        requested = tuple(categorias)
        resolucao = self.resolver_formas_recebimento()
        registros: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]] = {}
        for categoria in requested:
            registros[categoria] = self.consultar_categoria(
                categoria,
                data_inicio=inicio,
                data_fim=fim,
                resolucao=resolucao,
            )
        self.client.save_audit_metadata(
            period_start=inicio,
            period_end=fim,
            categories_requested=requested,
        )
        return ResultadoConsultaVelo(
            registros_por_categoria=registros,
            avisos=resolucao.avisos,
        )


def _classificar_forma(
    forma: FormaRecebimentoApi,
) -> tuple[CategoriaFiltroVelo | None, AvisoResolucaoForma | None]:
    comparable = normalize_text(forma.descricao).comparavel
    matches = [
        categoria
        for categoria, info in CATEGORIAS_VELO.items()
        if comparable in {normalize_text(alias).comparavel for alias in info.aliases}
    ]
    if len(matches) > 1:
        raise VeloSchemaError(
            "Descricao de autocomplete Velo ambigua.",
            endpoint="/autoCompletarOperadora",
            context={
                "descricao": forma.descricao,
                "categorias": [match.value for match in matches],
            },
        )
    if not matches:
        return None, None

    categoria = matches[0]
    aviso = None
    if comparable == "cartao de dedido - quickpay":
        aviso = AvisoResolucaoForma(
            codigo="VELO_CORRECAO_CONTROLADA_FORMA",
            mensagem="Erro conhecido 'Dédido' tratado como debito QuickPay.",
            categoria=categoria,
            descricao_origem=forma.descricao,
        )
    return categoria, aviso
