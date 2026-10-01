"""Workflow integrado de conciliacao Cielo e QuickPay."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.domain.models import ModeloDominio, RegistroSistema, TransacaoOperadora
from conciliacao.exporters import CieloExporter, QuickPayExporter
from conciliacao.integrations.velo.audit import VeloAuditWriter
from conciliacao.integrations.velo.authentication import (
    StaticTokenProvider,
    TokenProvider,
    VeloTokenProvider,
)
from conciliacao.integrations.velo.categories import (
    CATEGORIAS_VELO,
    CategoriaFiltroVelo,
)
from conciliacao.integrations.velo.client import VeloClient
from conciliacao.integrations.velo.config import (
    VeloApiConfig,
    VeloAuditConfig,
    load_velo_api_config,
)
from conciliacao.integrations.velo.exceptions import VeloApiError, VeloAuthenticationError
from conciliacao.integrations.velo.http import HttpTransport
from conciliacao.integrations.velo.service import VeloIntegrationService
from conciliacao.integrations.velo.testing import FixtureVeloTransport
from conciliacao.matching import ReconciliationService, ResultadoConciliacaoOperadora
from conciliacao.processors import CieloProcessor, QuickPayProcessor
from conciliacao.processors.cielo_processor import CieloRelatorioProcessado
from conciliacao.processors.quickpay_processor import QuickPayRelatorioProcessado
from conciliacao.quickpay.recebimentos_bancarios import ler_recebimentos_bancarios
from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.models import ResultadoLeitura
from conciliacao.readers.quickpay_reader import ler_quickpay
from conciliacao.utils.currency import quantize_money
from conciliacao.utils.file_hash import sha256_file
from conciliacao.validators import CieloValidator, QuickPayValidator, ResultadoValidacao


class WorkflowMode(StrEnum):
    REAL = "REAL"
    SIMULADO = "SIMULADO"


class WorkflowStatus(StrEnum):
    SUCESSO = "SUCESSO"
    SUCESSO_PARCIAL = "SUCESSO_PARCIAL"
    FALHA = "FALHA"


class WorkflowExitCode(StrEnum):
    SUCESSO = "0"
    FALHA_GLOBAL = "1"
    SUCESSO_PARCIAL = "2"
    FALHA_VALIDACAO = "3"
    FALHA_AUTENTICACAO = "4"
    FALHA_INTEGRACAO = "5"


class ReconciliationCommand(ModeloDominio):
    # Mantidos como compatibilidade da CLI antiga. O fluxo normal deriva as datas
    # diretamente dos arquivos selecionados.
    data_inicio: date | None = None
    data_fim: date | None = None
    arquivo_cielo: Path | None = None
    arquivo_quickpay: Path | None = None
    arquivo_recebimentos_quickpay: Path | None = None
    diretorio_saida: Path = Path("output")
    diretorio_planilhas: Path = Path("planilhas")
    sobrescrever: bool = False
    modo_simulado: bool = False
    diretorio_fixtures_api: Path | None = None
    salvar_auditoria: bool | None = None
    identificador_execucao: str | None = None

    @model_validator(mode="after")
    def validate_command(self) -> ReconciliationCommand:
        if (self.data_inicio is None) != (self.data_fim is None):
            raise ValueError("data-inicio e data-fim devem ser informadas juntas")
        if (
            self.data_inicio is not None
            and self.data_fim is not None
            and self.data_inicio > self.data_fim
        ):
            raise ValueError("data-fim nao pode ser anterior a data-inicio")
        if self.arquivo_cielo is None and self.arquivo_quickpay is None:
            raise ValueError("informe pelo menos um arquivo Cielo ou QuickPay")
        if self.modo_simulado and self.diretorio_fixtures_api is None:
            raise ValueError("modo simulado requer diretorio_fixtures_api")
        if self.arquivo_cielo is not None and not self.arquivo_cielo.is_file():
            raise ValueError(f"arquivo Cielo nao encontrado: {self.arquivo_cielo}")
        if self.arquivo_quickpay is not None and not self.arquivo_quickpay.is_file():
            raise ValueError(f"arquivo QuickPay nao encontrado: {self.arquivo_quickpay}")
        if self.arquivo_recebimentos_quickpay is not None and self.arquivo_quickpay is None:
            raise ValueError("recebimentos bancarios QuickPay exigem arquivo QuickPay")
        if (
            self.arquivo_recebimentos_quickpay is not None
            and not self.arquivo_recebimentos_quickpay.is_file()
        ):
            raise ValueError(
                "planilha de recebimentos QuickPay nao encontrada: "
                f"{self.arquivo_recebimentos_quickpay}"
            )
        if self.diretorio_saida.exists() and not self.diretorio_saida.is_dir():
            raise ValueError(f"diretorio de saida invalido: {self.diretorio_saida}")
        if self.diretorio_planilhas.exists() and not self.diretorio_planilhas.is_dir():
            raise ValueError(f"diretorio de planilhas invalido: {self.diretorio_planilhas}")
        if self.diretorio_fixtures_api is not None and not self.diretorio_fixtures_api.is_dir():
            raise ValueError(f"diretorio de fixtures API invalido: {self.diretorio_fixtures_api}")
        return self


class ResultadoApiWorkflow(ModeloDominio):
    categorias_solicitadas: list[CategoriaFiltroVelo] = Field(default_factory=list)
    categorias_consultadas: list[CategoriaFiltroVelo] = Field(default_factory=list)
    categorias_com_erro: dict[CategoriaFiltroVelo, str] = Field(default_factory=dict)
    total_registros: int = 0
    avisos: list[str] = Field(default_factory=list)
    arquivos_auditoria: list[Path] = Field(default_factory=list)


class ResultadoOperadoraWorkflow(ModeloDominio):
    operadora: Operadora
    arquivo_entrada: Path | None = None
    hash_entrada: str | None = None
    hash_preservado: bool = False
    quantidade_lida: int = 0
    quantidade_valida: int = 0
    categorias_necessarias: list[CategoriaFiltroVelo] = Field(default_factory=list)
    categorias_consultadas: list[CategoriaFiltroVelo] = Field(default_factory=list)
    categorias_ausentes: list[CategoriaFiltroVelo] = Field(default_factory=list)
    resumo_validacao: dict[str, Any] | None = None
    resumo_processamento: dict[str, Any] | None = None
    resumo_matching: dict[str, Any] | None = None
    arquivo_saida: Path | None = None
    arquivo_resultado: Path | None = None
    avisos: list[str] = Field(default_factory=list)
    erros: list[str] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.FALHA


class WorkflowResult(ModeloDominio):
    identificador_execucao: str
    inicio_execucao: datetime
    fim_execucao: datetime
    duracao_segundos: Decimal
    periodo: dict[str, date]
    modo: WorkflowMode
    resultado_cielo: ResultadoOperadoraWorkflow | None = None
    resultado_quickpay: ResultadoOperadoraWorkflow | None = None
    resultado_api: ResultadoApiWorkflow
    arquivos_gerados: list[Path] = Field(default_factory=list)
    arquivos_de_auditoria: list[Path] = Field(default_factory=list)
    logs: list[Path] = Field(default_factory=list)
    avisos_globais: list[str] = Field(default_factory=list)
    erros_globais: list[str] = Field(default_factory=list)
    status_geral: WorkflowStatus
    codigo_saida: int


class ReconciliationWorkflow:
    def __init__(
        self,
        *,
        config: VeloApiConfig | None = None,
        transport: HttpTransport | None = None,
        token_provider: TokenProvider | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.token_provider = token_provider
        self.log_callback = log_callback

    def executar(self, comando: ReconciliationCommand) -> WorkflowResult:
        started = datetime.now(ZoneInfo("America/Sao_Paulo"))
        perf_started = perf_counter()
        execution_id = comando.identificador_execucao or _execution_id(started)
        data_conciliacao = started.date()
        log_path = Path("logs") / f"conciliacao_{execution_id}.log"
        logger = _setup_logger(log_path, callback=self.log_callback)
        logger.info("inicio execucao=%s modo=%s", execution_id, _mode(comando).value)

        resultado_api = ResultadoApiWorkflow()
        resultado_cielo: ResultadoOperadoraWorkflow | None = None
        resultado_quickpay: ResultadoOperadoraWorkflow | None = None
        registros_por_categoria: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]] = {}
        periodo_global = (started.date(), started.date())
        erros_globais: list[str] = []
        avisos_globais: list[str] = []

        try:
            prepared, early_results = self._preparar_operadoras(comando, logger)
            categorias = _categorias_necessarias(prepared)
            periodos_consulta = _periodos_consulta_por_categoria(prepared)
            periodo_global = _periodo_global(prepared_periodos=periodos_consulta)
            resultado_api, registros_por_categoria = self._consultar_api(
                comando,
                execution_id=execution_id,
                categorias=categorias,
                periodos=periodos_consulta,
                logger=logger,
            )
            resultado_cielo = self._finalizar_cielo(
                comando,
                execution_id=execution_id,
                data_conciliacao=data_conciliacao,
                prepared=prepared.get(Operadora.CIELO),
                early_result=early_results.get(Operadora.CIELO),
                resultado_api=resultado_api,
                registros_por_categoria=registros_por_categoria,
                logger=logger,
            )
            resultado_quickpay = self._finalizar_quickpay(
                comando,
                execution_id=execution_id,
                data_conciliacao=data_conciliacao,
                prepared=prepared.get(Operadora.QUICKPAY),
                early_result=early_results.get(Operadora.QUICKPAY),
                resultado_api=resultado_api,
                registros_por_categoria=registros_por_categoria,
                logger=logger,
            )
        except VeloAuthenticationError as exc:
            message = (
                "Token Bearer ausente, invalido ou expirado. Conclua um novo login para continuar."
            )
            erros_globais.append(message)
            logger.error("falha autenticacao endpoint=%s", exc.endpoint)
        except Exception as exc:
            erros_globais.append(_safe_error(exc))
            logger.exception("falha global sem dados sensiveis")
        finally:
            logger.info("fim execucao=%s", execution_id)
            _close_logger(logger)

        finished = datetime.now(ZoneInfo("America/Sao_Paulo"))
        result = _montar_resultado(
            comando,
            execution_id=execution_id,
            started=started,
            finished=finished,
            duration=Decimal(str(round(perf_counter() - perf_started, 3))),
            resultado_api=resultado_api,
            resultado_cielo=resultado_cielo,
            resultado_quickpay=resultado_quickpay,
            log_path=log_path,
            erros_globais=erros_globais,
            avisos_globais=avisos_globais,
            periodo=periodo_global,
        )
        self._salvar_resumos(comando, result)
        return result

    def _preparar_operadoras(
        self, comando: ReconciliationCommand, logger: logging.Logger
    ) -> tuple[dict[Operadora, _PreparedOperator], dict[Operadora, ResultadoOperadoraWorkflow]]:
        prepared: dict[Operadora, _PreparedOperator] = {}
        early_results: dict[Operadora, ResultadoOperadoraWorkflow] = {}
        if comando.arquivo_cielo is not None:
            try:
                prepared[Operadora.CIELO] = _preparar_cielo(comando, logger)
            except Exception as exc:
                early_results[Operadora.CIELO] = _operator_failure(
                    Operadora.CIELO,
                    comando.arquivo_cielo,
                    _safe_error(exc),
                )
                logger.exception("cielo falha leitura ou processamento")
        if comando.arquivo_quickpay is not None:
            try:
                prepared[Operadora.QUICKPAY] = _preparar_quickpay(comando, logger)
            except Exception as exc:
                early_results[Operadora.QUICKPAY] = _operator_failure(
                    Operadora.QUICKPAY,
                    comando.arquivo_quickpay,
                    _safe_error(exc),
                )
                logger.exception("quickpay falha leitura ou processamento")
        return prepared, early_results

    def _consultar_api(
        self,
        comando: ReconciliationCommand,
        *,
        execution_id: str,
        categorias: tuple[CategoriaFiltroVelo, ...],
        periodos: dict[CategoriaFiltroVelo, tuple[date, date]],
        logger: logging.Logger,
    ) -> tuple[ResultadoApiWorkflow, dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]]]:
        if not categorias:
            return ResultadoApiWorkflow(), {}
        config = _config_for_command(self.config or load_velo_api_config(), comando)
        audit_writer = VeloAuditWriter(config.audit, execution_id=execution_id)
        transport = self.transport
        token_provider: TokenProvider
        if comando.modo_simulado:
            assert comando.diretorio_fixtures_api is not None
            transport = FixtureVeloTransport(comando.diretorio_fixtures_api, config)
            token_provider = StaticTokenProvider()
        else:
            token_provider = self.token_provider or VeloTokenProvider()

        client = VeloClient(
            config,
            token_provider=token_provider,
            transport=transport,
            audit_writer=audit_writer,
        )
        service = VeloIntegrationService(client)
        resolucao = service.resolver_formas_recebimento()
        registros: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]] = {}
        erros: dict[CategoriaFiltroVelo, str] = {}
        for categoria in categorias:
            try:
                inicio, fim = periodos[categoria]
                registros[categoria] = service.consultar_categoria(
                    categoria,
                    data_inicio=inicio,
                    data_fim=fim,
                    resolucao=resolucao,
                )
                logger.info(
                    "api categoria=%s inicio=%s fim=%s registros=%s",
                    categoria.value,
                    inicio.isoformat(),
                    fim.isoformat(),
                    len(registros[categoria]),
                )
            except VeloAuthenticationError:
                raise
            except VeloApiError as exc:
                erros[categoria] = _safe_error(exc)
                logger.error("api erro categoria=%s endpoint=%s", categoria.value, exc.endpoint)
        periodo_global = _periodo_global(prepared_periodos=periodos)
        client.save_audit_metadata(
            period_start=periodo_global[0],
            period_end=periodo_global[1],
            categories_requested=categorias,
        )
        arquivos = _audit_files(audit_writer)
        return (
            ResultadoApiWorkflow(
                categorias_solicitadas=list(categorias),
                categorias_consultadas=list(registros),
                categorias_com_erro=erros,
                total_registros=sum(len(items) for items in registros.values()),
                avisos=[aviso.mensagem for aviso in resolucao.avisos],
                arquivos_auditoria=arquivos,
            ),
            registros,
        )

    def _finalizar_cielo(
        self,
        comando: ReconciliationCommand,
        *,
        execution_id: str,
        data_conciliacao: date,
        prepared: _PreparedOperator | None,
        early_result: ResultadoOperadoraWorkflow | None,
        resultado_api: ResultadoApiWorkflow,
        registros_por_categoria: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]],
        logger: logging.Logger,
    ) -> ResultadoOperadoraWorkflow | None:
        if early_result is not None:
            return early_result
        if prepared is None:
            return None
        base = _base_operator_result(prepared)
        if (
            not prepared.validacao.valido
            or prepared.relatorio is None
            or not isinstance(prepared.relatorio, CieloRelatorioProcessado)
        ):
            return base
        relatorio = prepared.relatorio
        categorias = prepared.categorias
        registros = _registros_para(categorias, registros_por_categoria)
        matching = ReconciliationService().conciliar_cielo(
            list(relatorio.transacoes),
            registros,
            set(resultado_api.categorias_consultadas),
        )
        try:
            output_path = _exportar_cielo_atomico(
                relatorio,
                matching,
                _diretorio_planilha(comando, data_conciliacao, Operadora.CIELO),
                sobrescrever=comando.sobrescrever,
                execution_id=execution_id,
            )
            sidecar = _salvar_resultado_operadora(
                comando,
                Operadora.CIELO,
                execution_id,
                matching,
                output_path,
            )
            _confirmar_hash(prepared)
            status = _operator_status(prepared.categorias, resultado_api, had_export=True)
            logger.info("cielo status=%s arquivo=%s", status.value, output_path)
            return _base_operator_result(
                prepared,
                matching=matching,
                arquivo_saida=output_path,
                arquivo_resultado=sidecar,
                categorias_consultadas=_intersection(prepared.categorias, resultado_api),
                categorias_ausentes=_missing(prepared.categorias, resultado_api),
                status=status,
            )
        except Exception as exc:
            logger.exception("cielo falha exportacao")
            return _base_operator_result(prepared, erros=[_safe_error(exc)])

    def _finalizar_quickpay(
        self,
        comando: ReconciliationCommand,
        *,
        execution_id: str,
        data_conciliacao: date,
        prepared: _PreparedOperator | None,
        early_result: ResultadoOperadoraWorkflow | None,
        resultado_api: ResultadoApiWorkflow,
        registros_por_categoria: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]],
        logger: logging.Logger,
    ) -> ResultadoOperadoraWorkflow | None:
        if early_result is not None:
            return early_result
        if prepared is None:
            return None
        base = _base_operator_result(prepared)
        if (
            not prepared.validacao.valido
            or prepared.relatorio is None
            or not isinstance(prepared.relatorio, QuickPayRelatorioProcessado)
        ):
            return base
        relatorio = prepared.relatorio
        categorias = prepared.categorias
        registros = _registros_para(categorias, registros_por_categoria)
        matching = ReconciliationService().conciliar_quickpay(
            _relatorio_quickpay_transacoes(relatorio),
            registros,
            set(resultado_api.categorias_consultadas),
        )
        try:
            output_path = _exportar_quickpay_atomico(
                relatorio,
                matching,
                _diretorio_planilha(comando, data_conciliacao, Operadora.QUICKPAY),
                sobrescrever=comando.sobrescrever,
                execution_id=execution_id,
            )
            sidecar = _salvar_resultado_operadora(
                comando,
                Operadora.QUICKPAY,
                execution_id,
                matching,
                output_path,
            )
            _confirmar_hash(prepared)
            status = _operator_status(prepared.categorias, resultado_api, had_export=True)
            logger.info("quickpay status=%s arquivo=%s", status.value, output_path)
            return _base_operator_result(
                prepared,
                matching=matching,
                arquivo_saida=output_path,
                arquivo_resultado=sidecar,
                categorias_consultadas=_intersection(prepared.categorias, resultado_api),
                categorias_ausentes=_missing(prepared.categorias, resultado_api),
                status=status,
            )
        except Exception as exc:
            logger.exception("quickpay falha exportacao")
            return _base_operator_result(prepared, erros=[_safe_error(exc)])

    def _salvar_resumos(self, comando: ReconciliationCommand, result: WorkflowResult) -> None:
        exec_dir = comando.diretorio_saida / "execucoes" / result.identificador_execucao
        exec_dir.mkdir(parents=True, exist_ok=True)
        json_path = exec_dir / "resumo.json"
        text_path = exec_dir / "resumo.txt"
        _write_json_atomic(json_path, result.model_dump(mode="json"))
        _write_text_atomic(text_path, formatar_resumo_workflow(result))


@dataclass(frozen=True, slots=True)
class _PreparedOperator:
    operadora: Operadora
    validacao: ResultadoValidacao
    leitura: ResultadoLeitura | None = None
    relatorio: CieloRelatorioProcessado | QuickPayRelatorioProcessado | None = None
    categorias: list[CategoriaFiltroVelo] = dataclass_field(default_factory=list)
    hash_antes: str | None = None


def _diretorio_planilha(
    comando: ReconciliationCommand,
    data_conciliacao: date,
    operadora: Operadora,
) -> Path:
    return comando.diretorio_planilhas / data_conciliacao.isoformat() / operadora.value.lower()


def _preparar_cielo(comando: ReconciliationCommand, logger: logging.Logger) -> _PreparedOperator:
    assert comando.arquivo_cielo is not None
    hash_antes = sha256_file(comando.arquivo_cielo)
    leitura = ler_cielo(comando.arquivo_cielo)
    validacao = CieloValidator().validar(
        leitura,
        data_inicio=None,
        data_fim=None,
    )
    relatorio: CieloRelatorioProcessado | None = None
    if validacao.valido:
        relatorio = CieloProcessor().processar(
            leitura,
            validacao,
            **_periodo_processamento(leitura.transacoes),
        )
    logger.info("cielo lida transacoes=%s valido=%s", len(leitura.transacoes), validacao.valido)
    return _PreparedOperator(
        operadora=Operadora.CIELO,
        leitura=leitura,
        validacao=validacao,
        relatorio=relatorio,
        categorias=_categorias_transacoes(_transacoes_cielo(relatorio, leitura), Operadora.CIELO),
        hash_antes=hash_antes,
    )


def _preparar_quickpay(comando: ReconciliationCommand, logger: logging.Logger) -> _PreparedOperator:
    assert comando.arquivo_quickpay is not None
    hash_antes = sha256_file(comando.arquivo_quickpay)
    leitura = ler_quickpay(comando.arquivo_quickpay)
    recebimentos = (
        ler_recebimentos_bancarios(comando.arquivo_recebimentos_quickpay)
        if comando.arquivo_recebimentos_quickpay is not None
        else None
    )
    validacao = QuickPayValidator().validar(
        leitura,
        data_inicio=None,
        data_fim=None,
        recebimentos_bancarios=recebimentos,
    )
    relatorio: QuickPayRelatorioProcessado | None = None
    if validacao.valido:
        relatorio = QuickPayProcessor().processar(
            leitura,
            validacao,
            **_periodo_processamento(leitura.transacoes),
            recebimentos_bancarios=recebimentos,
        )
    logger.info("quickpay lida transacoes=%s valido=%s", len(leitura.transacoes), validacao.valido)
    return _PreparedOperator(
        operadora=Operadora.QUICKPAY,
        leitura=leitura,
        validacao=validacao,
        relatorio=relatorio,
        categorias=_categorias_transacoes(
            _transacoes_quickpay(relatorio, leitura),
            Operadora.QUICKPAY,
        ),
        hash_antes=hash_antes,
    )


def _config_for_command(config: VeloApiConfig, comando: ReconciliationCommand) -> VeloApiConfig:
    audit = config.audit
    if comando.salvar_auditoria is not None:
        audit = replace(audit, save_raw_responses=comando.salvar_auditoria)
    return replace(config, audit=VeloAuditConfig(audit.save_raw_responses, Path("data/api_raw")))


def _categorias_necessarias(
    prepared: dict[Operadora, _PreparedOperator],
) -> tuple[CategoriaFiltroVelo, ...]:
    selected: set[CategoriaFiltroVelo] = set()
    for item in prepared.values():
        if item.validacao.valido:
            selected.update(item.categorias)
    return tuple(categoria for categoria in CategoriaFiltroVelo if categoria in selected)


def _periodos_consulta_por_categoria(
    prepared_or_comando: dict[Operadora, _PreparedOperator] | ReconciliationCommand,
    prepared: dict[Operadora, _PreparedOperator] | None = None,
) -> dict[CategoriaFiltroVelo, tuple[date, date]]:
    """Deriva cada consulta dos arquivos: recebimento no débito e venda nos demais."""
    # A forma com dois argumentos preserva a compatibilidade de integrações internas antigas.
    itens = prepared if prepared is not None else prepared_or_comando
    if not isinstance(itens, dict):
        raise TypeError("prepared deve conter as operadoras lidas")
    datas_por_categoria: dict[CategoriaFiltroVelo, list[date]] = {}
    for item in itens.values():
        if item.relatorio is None:
            continue
        transacoes = (
            list(item.relatorio.transacoes)
            if isinstance(item.relatorio, CieloRelatorioProcessado)
            else _relatorio_quickpay_transacoes(item.relatorio)
        )
        for transacao in transacoes:
            if transacao.modalidade is None:
                continue
            categoria = next(
                (
                    chave
                    for chave, info in CATEGORIAS_VELO.items()
                    if info.operadora is transacao.operadora
                    and info.modalidade is transacao.modalidade
                ),
                None,
            )
            if categoria is not None:
                data_consulta = (
                    transacao.data_recebimento
                    if transacao.modalidade is Modalidade.DEBITO
                    else transacao.data_venda
                )
                if data_consulta is not None:
                    datas_por_categoria.setdefault(categoria, []).append(data_consulta)

    periodos: dict[CategoriaFiltroVelo, tuple[date, date]] = {}
    for categoria in _categorias_necessarias(itens):
        datas = datas_por_categoria.get(categoria, [])
        if not datas:
            raise ValueError(f"nao foi possivel derivar periodo para {categoria.value}")
        periodos[categoria] = (min(datas), max(datas))
    return periodos


def _periodo_processamento(transacoes: list[TransacaoOperadora]) -> dict[str, date]:
    if not transacoes:
        raise ValueError("arquivo sem transacoes para derivar periodo")
    return {
        "data_inicio": min(item.data_venda for item in transacoes),
        "data_fim": max(item.data_venda for item in transacoes),
    }


def _periodo_global(
    *, prepared_periodos: dict[CategoriaFiltroVelo, tuple[date, date]]
) -> tuple[date, date]:
    if not prepared_periodos:
        return date.today(), date.today()
    return (
        min(inicio for inicio, _ in prepared_periodos.values()),
        max(fim for _, fim in prepared_periodos.values()),
    )


def _categorias_transacoes(
    transacoes: list[TransacaoOperadora], operadora: Operadora
) -> list[CategoriaFiltroVelo]:
    categorias: set[CategoriaFiltroVelo] = set()
    for transacao in transacoes:
        if transacao.modalidade is None:
            continue
        for categoria, info in CATEGORIAS_VELO.items():
            if info.operadora is operadora and info.modalidade is transacao.modalidade:
                categorias.add(categoria)
    return [categoria for categoria in CategoriaFiltroVelo if categoria in categorias]


def _transacoes_cielo(
    relatorio: CieloRelatorioProcessado | None, leitura: ResultadoLeitura
) -> list[TransacaoOperadora]:
    if relatorio is not None:
        return list(relatorio.transacoes)
    return leitura.transacoes


def _transacoes_quickpay(
    relatorio: QuickPayRelatorioProcessado | None, leitura: ResultadoLeitura
) -> list[TransacaoOperadora]:
    if relatorio is not None:
        return _relatorio_quickpay_transacoes(relatorio)
    return leitura.transacoes


def _relatorio_quickpay_transacoes(
    relatorio: CieloRelatorioProcessado | QuickPayRelatorioProcessado | None,
) -> list[TransacaoOperadora]:
    if not isinstance(relatorio, QuickPayRelatorioProcessado):
        return []
    return [linha.transacao for linha in relatorio.linhas]


def _registros_para(
    categorias: list[CategoriaFiltroVelo],
    registros_por_categoria: dict[CategoriaFiltroVelo, tuple[RegistroSistema, ...]],
) -> list[RegistroSistema]:
    registros: list[RegistroSistema] = []
    for categoria in categorias:
        registros.extend(registros_por_categoria.get(categoria, ()))
    return registros


def _exportar_cielo_atomico(
    relatorio: CieloRelatorioProcessado,
    matching: ResultadoConciliacaoOperadora,
    output_dir: Path,
    *,
    sobrescrever: bool,
    execution_id: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"CIELO_CONCILIACAO_{relatorio.data_inicio.isoformat()}_A_"
        f"{relatorio.data_fim.isoformat()}.xlsx"
    )
    final = _resolve_output(
        output_dir / filename,
        sobrescrever=sobrescrever,
        execution_id=execution_id,
    )
    with tempfile.TemporaryDirectory(prefix="cielo_", dir=output_dir) as temp_dir:
        temp_result = CieloExporter().exportar(
            relatorio,
            diretorio_saida=temp_dir,
            sobrescrever=True,
            matching=matching,
        )
        shutil.move(str(temp_result.caminho_saida), final)
    return final


def _exportar_quickpay_atomico(
    relatorio: QuickPayRelatorioProcessado,
    matching: ResultadoConciliacaoOperadora,
    output_dir: Path,
    *,
    sobrescrever: bool,
    execution_id: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    final = _resolve_output(
        output_dir
        / (
            f"QUICKPAY_CONCILIACAO_{relatorio.data_inicio.isoformat()}_A_"
            f"{relatorio.data_fim.isoformat()}.xlsx"
        ),
        sobrescrever=sobrescrever,
        execution_id=execution_id,
    )
    with tempfile.TemporaryDirectory(prefix="quickpay_", dir=output_dir) as temp_dir:
        temp_result = QuickPayExporter().exportar(
            relatorio,
            diretorio_saida=temp_dir,
            sobrescrever=True,
            matching=matching,
        )
        shutil.move(str(temp_result.caminho_saida), final)
    return final


def _salvar_resultado_operadora(
    comando: ReconciliationCommand,
    operadora: Operadora,
    execution_id: str,
    matching: ResultadoConciliacaoOperadora,
    output_path: Path,
) -> Path | None:
    if comando.salvar_auditoria is False:
        return None
    directory = comando.diretorio_saida / ("cielo" if operadora is Operadora.CIELO else "quickpay")
    prefix = "CIELO" if operadora is Operadora.CIELO else "QUICKPAY"
    filename = f"{prefix}_CONCILIACAO_{execution_id}_RESULTADO.json"
    path = _resolve_output(
        directory / filename,
        sobrescrever=comando.sobrescrever,
        execution_id=execution_id,
    )
    payload = {
        "execution_id": execution_id,
        "operadora": operadora.value,
        "arquivo_saida": str(output_path),
        "matching": _matching_compacto(matching),
    }
    _write_json_atomic(path, payload)
    return path


def _base_operator_result(
    prepared: _PreparedOperator,
    *,
    matching: ResultadoConciliacaoOperadora | None = None,
    arquivo_saida: Path | None = None,
    arquivo_resultado: Path | None = None,
    categorias_consultadas: list[CategoriaFiltroVelo] | None = None,
    categorias_ausentes: list[CategoriaFiltroVelo] | None = None,
    status: WorkflowStatus | None = None,
    erros: list[str] | None = None,
) -> ResultadoOperadoraWorkflow:
    leitura = prepared.leitura
    relatorio = prepared.relatorio
    validation_errors = [alerta.codigo for alerta in prepared.validacao.erros]
    all_errors = [*validation_errors, *(erros or [])]
    return ResultadoOperadoraWorkflow(
        operadora=prepared.operadora,
        arquivo_entrada=prepared.validacao.arquivo_validado,
        hash_entrada=prepared.hash_antes,
        hash_preservado=_hash_preservado(prepared),
        quantidade_lida=0 if leitura is None else len(leitura.transacoes),
        quantidade_valida=(
            0 if not prepared.validacao.valido else prepared.validacao.quantidade_transacoes
        ),
        categorias_necessarias=prepared.categorias,
        categorias_consultadas=[] if categorias_consultadas is None else categorias_consultadas,
        categorias_ausentes=(
            prepared.categorias if categorias_ausentes is None else categorias_ausentes
        ),
        resumo_validacao=_validation_summary(prepared.validacao),
        resumo_processamento=_processing_summary(relatorio),
        resumo_matching=None if matching is None else _matching_compacto(matching),
        arquivo_saida=arquivo_saida,
        arquivo_resultado=arquivo_resultado,
        avisos=[alerta.codigo for alerta in prepared.validacao.avisos],
        erros=all_errors,
        status=status or (WorkflowStatus.FALHA if all_errors else WorkflowStatus.SUCESSO_PARCIAL),
    )


def _operator_failure(
    operadora: Operadora,
    arquivo: Path | None,
    erro: str,
) -> ResultadoOperadoraWorkflow:
    return ResultadoOperadoraWorkflow(
        operadora=operadora,
        arquivo_entrada=arquivo,
        erros=[erro],
        status=WorkflowStatus.FALHA,
    )


def _operator_status(
    categorias: list[CategoriaFiltroVelo],
    resultado_api: ResultadoApiWorkflow,
    *,
    had_export: bool,
) -> WorkflowStatus:
    if not had_export:
        return WorkflowStatus.FALHA
    missing = set(categorias) - set(resultado_api.categorias_consultadas)
    return WorkflowStatus.SUCESSO_PARCIAL if missing else WorkflowStatus.SUCESSO


def _montar_resultado(
    comando: ReconciliationCommand,
    *,
    execution_id: str,
    started: datetime,
    finished: datetime,
    duration: Decimal,
    resultado_api: ResultadoApiWorkflow,
    resultado_cielo: ResultadoOperadoraWorkflow | None,
    resultado_quickpay: ResultadoOperadoraWorkflow | None,
    log_path: Path,
    erros_globais: list[str],
    avisos_globais: list[str],
    periodo: tuple[date, date],
) -> WorkflowResult:
    status = _overall_status(resultado_cielo, resultado_quickpay, erros_globais)
    return WorkflowResult(
        identificador_execucao=execution_id,
        inicio_execucao=started,
        fim_execucao=finished,
        duracao_segundos=duration,
        periodo={"data_inicio": periodo[0], "data_fim": periodo[1]},
        modo=_mode(comando),
        resultado_cielo=resultado_cielo,
        resultado_quickpay=resultado_quickpay,
        resultado_api=resultado_api,
        arquivos_gerados=_generated_files(resultado_cielo, resultado_quickpay),
        arquivos_de_auditoria=_audit_result_files(
            resultado_api,
            resultado_cielo,
            resultado_quickpay,
        ),
        logs=[log_path],
        avisos_globais=avisos_globais,
        erros_globais=erros_globais,
        status_geral=status,
        codigo_saida=_exit_code(status, resultado_cielo, resultado_quickpay, erros_globais),
    )


def _overall_status(
    cielo: ResultadoOperadoraWorkflow | None,
    quickpay: ResultadoOperadoraWorkflow | None,
    erros_globais: list[str],
) -> WorkflowStatus:
    if erros_globais:
        return WorkflowStatus.FALHA
    results = [item for item in (cielo, quickpay) if item is not None]
    if not results or all(item.status is WorkflowStatus.FALHA for item in results):
        return WorkflowStatus.FALHA
    if all(item.status is WorkflowStatus.SUCESSO for item in results):
        return WorkflowStatus.SUCESSO
    return WorkflowStatus.SUCESSO_PARCIAL


def _exit_code(
    status: WorkflowStatus,
    cielo: ResultadoOperadoraWorkflow | None,
    quickpay: ResultadoOperadoraWorkflow | None,
    erros_globais: list[str],
) -> int:
    if status is WorkflowStatus.SUCESSO:
        return int(WorkflowExitCode.SUCESSO.value)
    if any("Token Bearer" in erro for erro in erros_globais):
        return int(WorkflowExitCode.FALHA_AUTENTICACAO.value)
    if status is WorkflowStatus.SUCESSO_PARCIAL:
        return int(WorkflowExitCode.SUCESSO_PARCIAL.value)
    results = [item for item in (cielo, quickpay) if item is not None]
    all_invalid = all(
        item.resumo_validacao and item.resumo_validacao["valido"] is False for item in results
    )
    if results and all_invalid:
        return int(WorkflowExitCode.FALHA_VALIDACAO.value)
    return int(WorkflowExitCode.FALHA_GLOBAL.value)


def _validation_summary(validacao: ResultadoValidacao) -> dict[str, Any]:
    return {
        "valido": validacao.valido,
        "quantidade_transacoes": validacao.quantidade_transacoes,
        "quantidade_erros": validacao.quantidade_erros,
        "quantidade_avisos": validacao.quantidade_avisos,
        "erros": [alerta.codigo for alerta in validacao.erros],
        "avisos": [alerta.codigo for alerta in validacao.avisos],
        "totais_calculados": validacao.totais_calculados,
    }


def _processing_summary(
    relatorio: CieloRelatorioProcessado | QuickPayRelatorioProcessado | None,
) -> dict[str, Any] | None:
    if relatorio is None:
        return None
    return {
        "transacoes_lidas": relatorio.resumo.transacoes_lidas,
        "transacoes_incluidas": relatorio.resumo.transacoes_incluidas,
        "transacoes_fora_periodo": relatorio.resumo.transacoes_fora_periodo,
        "total_bruto": relatorio.resumo.total_bruto,
        "total_taxa": relatorio.resumo.total_taxa,
        "total_liquido": relatorio.resumo.total_liquido,
        **(
            {
                "total_recebido_banco": relatorio.resumo.total_recebido_banco,
                "diferenca_total_banco_liquido": relatorio.resumo.diferenca_total_banco_liquido,
                "conferencia_bancaria": relatorio.resumo.conferencia_bancaria,
            }
            if isinstance(relatorio, QuickPayRelatorioProcessado)
            else {}
        ),
    }


def _matching_compacto(matching: ResultadoConciliacaoOperadora) -> dict[str, Any]:
    return {
        "resumo": matching.resumo.model_dump(mode="json"),
        "agregados": [item.model_dump(mode="json") for item in matching.agregados],
        "individuais": [
            {
                "linha_operadora": None
                if item.transacao_operadora is None
                else item.transacao_operadora.linha_original,
                "id_sistema": None
                if item.registro_sistema is None
                else item.registro_sistema.id_sistema,
                "status": item.status.value,
                "valor_operadora": item.valor_operadora,
                "valor_sistema": item.valor_sistema,
                "diferenca": item.diferenca,
                "chave_utilizada": item.chave_utilizada,
                "nivel_confianca": item.nivel_confianca.value,
                "correspondencia_individual_comprovada": item.correspondencia_individual_comprovada,
                "correspondencia_atribuida_deterministicamente": (
                    item.correspondencia_atribuida_deterministicamente
                ),
            }
            for item in matching.individuais
        ],
    }


def _resolve_output(path: Path, *, sobrescrever: bool, execution_id: str) -> Path:
    if sobrescrever or not path.exists():
        return path
    return path.with_name(f"{path.stem}_{execution_id}{path.suffix}")


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
    json.loads(serialized)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temp.write_text(serialized + "\n", encoding="utf-8")
        temp.replace(path)
    except Exception:
        if temp.exists():
            temp.unlink()
        raise


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temp.write_text(text + "\n", encoding="utf-8")
        temp.replace(path)
    except Exception:
        if temp.exists():
            temp.unlink()
        raise


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return f"{quantize_money(value):.2f}"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    return str(value)


def formatar_resumo_workflow(result: WorkflowResult) -> str:
    linhas = [
        f"CONCILIACAO FINALIZADA COM {result.status_geral.value}",
        "",
        "Execucao:",
        result.identificador_execucao,
        "",
        "Periodo:",
        f"{result.periodo['data_inicio']:%d/%m/%Y} a {result.periodo['data_fim']:%d/%m/%Y}",
        "",
    ]
    for item in (result.resultado_cielo, result.resultado_quickpay):
        if item is None:
            continue
        linhas.extend(_operator_lines(item))
    linhas.extend(
        [
            "API",
            f"Categorias consultadas: {len(result.resultado_api.categorias_consultadas)}",
            f"Categorias com erro: {len(result.resultado_api.categorias_com_erro)}",
            "",
            "Status geral:",
            result.status_geral.value,
        ]
    )
    return "\n".join(linhas)


def _operator_lines(item: ResultadoOperadoraWorkflow) -> list[str]:
    matching = item.resumo_matching or {}
    resumo = matching.get("resumo") if isinstance(matching, dict) else None
    return [
        item.operadora.value,
        f"Status: {item.status.value}",
        f"Transacoes: {item.quantidade_valida}",
        f"Conciliadas: {_summary_value(resumo, 'conciliados')}",
        f"Pendentes: {_summary_value(resumo, 'pendencias_dados')}",
        f"Nao encontradas no sistema: {_summary_value(resumo, 'nao_encontrados_no_sistema')}",
        f"Nao encontradas na operadora: {_summary_value(resumo, 'nao_encontrados_na_operadora')}",
        f"Arquivo: {item.arquivo_saida or ''}",
        *(["Erros:", *item.erros] if item.erros else []),
        "",
    ]


def _summary_value(resumo: object, key: str) -> object:
    if isinstance(resumo, dict):
        return resumo.get(key, 0)
    return 0


def _mode(comando: ReconciliationCommand) -> WorkflowMode:
    return WorkflowMode.SIMULADO if comando.modo_simulado else WorkflowMode.REAL


def _execution_id(started: datetime) -> str:
    return f"{started.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"


def _audit_files(audit_writer: VeloAuditWriter) -> list[Path]:
    if not audit_writer.enabled() or not audit_writer.execution_dir.exists():
        return []
    return sorted(audit_writer.execution_dir.glob("*.json"))


def _audit_result_files(
    api: ResultadoApiWorkflow,
    cielo: ResultadoOperadoraWorkflow | None,
    quickpay: ResultadoOperadoraWorkflow | None,
) -> list[Path]:
    files = list(api.arquivos_auditoria)
    for item in (cielo, quickpay):
        if item is not None and item.arquivo_resultado is not None:
            files.append(item.arquivo_resultado)
    return files


def _generated_files(
    cielo: ResultadoOperadoraWorkflow | None,
    quickpay: ResultadoOperadoraWorkflow | None,
) -> list[Path]:
    files = []
    for item in (cielo, quickpay):
        if item is not None and item.arquivo_saida is not None:
            files.append(item.arquivo_saida)
    return files


def _intersection(
    categorias: list[CategoriaFiltroVelo],
    resultado_api: ResultadoApiWorkflow,
) -> list[CategoriaFiltroVelo]:
    consulted = set(resultado_api.categorias_consultadas)
    return [categoria for categoria in categorias if categoria in consulted]


def _missing(
    categorias: list[CategoriaFiltroVelo],
    resultado_api: ResultadoApiWorkflow,
) -> list[CategoriaFiltroVelo]:
    consulted = set(resultado_api.categorias_consultadas)
    return [categoria for categoria in categorias if categoria not in consulted]


def _confirmar_hash(prepared: _PreparedOperator) -> None:
    if prepared.hash_antes is None:
        return
    if sha256_file(prepared.validacao.arquivo_validado) != prepared.hash_antes:
        raise ValueError("hash do arquivo de entrada mudou durante a execucao")


def _hash_preservado(prepared: _PreparedOperator) -> bool:
    try:
        _confirmar_hash(prepared)
    except Exception:
        return False
    return True


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    for marker in ("Authorization", "Bearer"):
        text = text.replace(marker, "<redacted>")
    return text


class _CallbackLogHandler(logging.Handler):
    """Encaminha mensagens seguras ao consumidor da interface, sem rastros de excecao."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(f"{record.levelname}: {record.getMessage()}")
        except Exception:
            self.handleError(record)


def _setup_logger(path: Path, *, callback: Callable[[str], None] | None = None) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"conciliacao.workflow.{path.stem}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    if callback is not None:
        logger.addHandler(_CallbackLogHandler(callback))
    return logger


def _close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
