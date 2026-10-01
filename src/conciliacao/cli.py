from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date, time
from pathlib import Path

from conciliacao import __version__
from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro
from conciliacao.domain.models import RegistroSistema, TransacaoOperadora
from conciliacao.exporters import CieloExporter, QuickPayExporter
from conciliacao.integrations.velo.audit import VeloAuditWriter
from conciliacao.integrations.velo.authentication import StaticTokenProvider
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.integrations.velo.client import VeloClient
from conciliacao.integrations.velo.config import load_velo_api_config
from conciliacao.integrations.velo.exceptions import VeloApiError
from conciliacao.integrations.velo.manual_login import ManualLoginTokenProvider
from conciliacao.integrations.velo.service import ResultadoConsultaVelo, VeloIntegrationService
from conciliacao.integrations.velo.testing import FixtureVeloTransport
from conciliacao.matching import ReconciliationService, formatar_resultado_matching
from conciliacao.processors import CieloProcessor, QuickPayProcessor
from conciliacao.processors.cielo_processor import CieloProcessingError
from conciliacao.processors.quickpay_processor import QuickPayProcessingError
from conciliacao.quickpay.recebimentos_bancarios import (
    criar_planilha_recebimentos_bancarios,
    ler_recebimentos_bancarios,
    parse_recebimento_chat,
)
from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.quickpay_reader import ler_quickpay
from conciliacao.validators import (
    CieloValidator,
    QuickPayValidator,
    formatar_resumo_validacao,
    validar_cielo_arquivo,
    validar_quickpay_arquivo,
)
from conciliacao.validators.common_validator import PeriodoSolicitadoInvalido
from conciliacao.workflow import (
    ReconciliationCommand,
    ReconciliationWorkflow,
    WorkflowStatus,
    formatar_resumo_workflow,
)


def _date_value(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"data invalida: {raw!r}. Use o formato YYYY-MM-DD."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conciliacao",
        description="CLI da automacao de conciliacao de caixa.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    processar = subparsers.add_parser(
        "processar",
        help="Executa o workflow integrado de conciliacao.",
    )
    processar.add_argument(
        "--data-inicio",
        required=False,
        type=_date_value,
        help="Opcional e mantido por compatibilidade; o workflow deriva as datas do arquivo.",
    )
    processar.add_argument("--data-fim", required=False, type=_date_value)
    processar.add_argument("--arquivo-cielo", required=False, type=Path)
    processar.add_argument("--arquivo-quickpay", required=False, type=Path)
    processar.add_argument("--arquivo-recebimentos-quickpay", required=False, type=Path)
    processar.add_argument("--saida", required=False, type=Path, default=Path("output"))
    processar.add_argument(
        "--diretorio-planilhas",
        required=False,
        type=Path,
        default=Path("planilhas"),
        help="Diretorio-raiz dos Excel finais; cada execucao cria <data>/cielo e <data>/quickpay.",
    )
    processar.add_argument("--sobrescrever", action="store_true")
    processar.add_argument("--modo-simulado", action="store_true")
    processar.add_argument("--fixtures-api", required=False, type=Path)
    processar.add_argument("--salvar-auditoria", action="store_true")
    processar.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida argumentos sem executar processamento.",
    )

    validar_cielo = subparsers.add_parser(
        "validar-cielo",
        help="Valida somente um arquivo Cielo. Nao gera Excel nem consulta API.",
    )
    validar_cielo.add_argument("--arquivo", required=True, type=Path)
    _add_period_args(validar_cielo)

    validar_quickpay = subparsers.add_parser(
        "validar-quickpay",
        help="Valida somente um arquivo QuickPay. Nao gera Excel nem consulta API.",
    )
    validar_quickpay.add_argument("--arquivo", required=True, type=Path)
    validar_quickpay.add_argument("--arquivo-recebimentos-quickpay", required=False, type=Path)
    _add_period_args(validar_quickpay)

    validar = subparsers.add_parser(
        "validar",
        help="Valida arquivos Cielo e QuickPay de forma independente.",
    )
    validar.add_argument("--arquivo-cielo", required=True, type=Path)
    validar.add_argument("--arquivo-quickpay", required=True, type=Path)
    _add_period_args(validar)

    gerar_cielo = subparsers.add_parser(
        "gerar-cielo",
        help="Gera somente o relatorio Cielo no padrao LEO. Nao consulta API.",
    )
    gerar_cielo.add_argument("--arquivo", required=True, type=Path)
    gerar_cielo.add_argument("--data-inicio", required=True, type=_date_value)
    gerar_cielo.add_argument("--data-fim", required=True, type=_date_value)
    gerar_cielo.add_argument("--saida", required=True, type=Path)
    gerar_cielo.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Permite sobrescrever o arquivo de saida quando ele ja existir.",
    )

    gerar_quickpay = subparsers.add_parser(
        "gerar-quickpay",
        help="Gera somente o relatorio QuickPay. Nao consulta API.",
    )
    gerar_quickpay.add_argument("--arquivo", required=True, type=Path)
    gerar_quickpay.add_argument("--arquivo-recebimentos-quickpay", required=False, type=Path)
    gerar_quickpay.add_argument("--data-inicio", required=True, type=_date_value)
    gerar_quickpay.add_argument("--data-fim", required=True, type=_date_value)
    gerar_quickpay.add_argument("--saida", required=True, type=Path)
    gerar_quickpay.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Permite sobrescrever o arquivo de saida quando ele ja existir.",
    )

    gerar_recebimentos = subparsers.add_parser(
        "gerar-recebimentos-quickpay",
        help="Gera a planilha auxiliar QuickPay a partir dos valores confirmados no chat.",
    )
    gerar_recebimentos.add_argument("--saida", required=True, type=Path)
    gerar_recebimentos.add_argument(
        "--nome-arquivo", default="RECEBIMENTOS_BANCARIOS_QUICKPAY.xlsx"
    )
    gerar_recebimentos.add_argument(
        "--recebimento",
        action="append",
        required=True,
        help="Use data|bandeira|modalidade|valor; repita para cada grupo.",
    )

    testar_velo = subparsers.add_parser(
        "testar-integracao-velo",
        help="Simula a integracao Velo com fixtures locais. Nao acessa internet.",
    )
    testar_velo.add_argument("--fixtures", required=True, type=Path)
    testar_velo.add_argument("--data-inicio", required=True, type=_date_value)
    testar_velo.add_argument("--data-fim", required=True, type=_date_value)
    testar_velo.add_argument(
        "--auditoria-dir",
        required=False,
        type=Path,
        help="Diretorio para auditoria simulada. Padrao: data/api_raw.",
    )

    testar_matching = subparsers.add_parser(
        "testar-matching",
        help="Simula matching com fixtures locais. Nao acessa internet nem altera Excel.",
    )
    testar_matching.add_argument("--operadora", required=True, choices=["cielo", "quickpay"])
    testar_matching.add_argument(
        "--fixtures",
        required=False,
        type=Path,
        default=Path("tests/fixtures/matching"),
    )
    testar_matching.add_argument(
        "--sistema-extra",
        action="store_true",
        help="Na QuickPay, usa fixture com registro adicional do sistema.",
    )

    return parser


def _processar(args: argparse.Namespace) -> int:
    if (args.data_inicio is None) != (args.data_fim is None):
        print("Erro: data-inicio e data-fim devem ser informadas juntas.")
        return 1
    if (
        args.data_inicio is not None
        and args.data_fim is not None
        and args.data_fim < args.data_inicio
    ):
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 1
    if args.arquivo_cielo is None and args.arquivo_quickpay is None:
        print("Erro: informe pelo menos um arquivo Cielo ou QuickPay.")
        return 1

    if args.dry_run:
        print("Argumentos validos. Nenhum processamento foi executado.")
        return 0

    token_provider: ManualLoginTokenProvider | None = None
    try:
        comando = ReconciliationCommand(
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
            arquivo_cielo=args.arquivo_cielo,
            arquivo_quickpay=args.arquivo_quickpay,
            arquivo_recebimentos_quickpay=args.arquivo_recebimentos_quickpay,
            diretorio_saida=args.saida,
            diretorio_planilhas=args.diretorio_planilhas,
            sobrescrever=bool(args.sobrescrever),
            modo_simulado=bool(args.modo_simulado),
            diretorio_fixtures_api=args.fixtures_api,
            salvar_auditoria=True if args.salvar_auditoria else None,
        )
        token_provider = None if args.modo_simulado else ManualLoginTokenProvider()
        resultado = ReconciliationWorkflow(token_provider=token_provider).executar(comando)
    except ValueError as exc:
        print(f"Erro: {exc}")
        return 1
    finally:
        if token_provider is not None:
            token_provider.clear()

    print(formatar_resumo_workflow(resultado))
    if resultado.modo.value == "SIMULADO":
        print("\nChamadas reais realizadas: 0")
    if resultado.status_geral is WorkflowStatus.FALHA:
        return resultado.codigo_saida
    return resultado.codigo_saida


def _add_period_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-inicio", required=False, type=_date_value)
    parser.add_argument("--data-fim", required=False, type=_date_value)


def _validar_cielo(args: argparse.Namespace) -> int:
    try:
        resultado = validar_cielo_arquivo(
            args.arquivo,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
    except PeriodoSolicitadoInvalido as exc:
        print(f"Erro: {exc}")
        return 2
    print(formatar_resumo_validacao(resultado))
    return 0 if resultado.valido else 1


def _validar_quickpay(args: argparse.Namespace) -> int:
    try:
        resultado = validar_quickpay_arquivo(
            args.arquivo,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
            arquivo_recebimentos_bancarios=args.arquivo_recebimentos_quickpay,
        )
    except PeriodoSolicitadoInvalido as exc:
        print(f"Erro: {exc}")
        return 2
    print(formatar_resumo_validacao(resultado))
    return 0 if resultado.valido else 1


def _validar_ambos(args: argparse.Namespace) -> int:
    try:
        cielo = validar_cielo_arquivo(
            args.arquivo_cielo,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        quickpay = validar_quickpay_arquivo(
            args.arquivo_quickpay,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
    except PeriodoSolicitadoInvalido as exc:
        print(f"Erro: {exc}")
        return 2
    print(formatar_resumo_validacao(cielo, quickpay))
    return 0 if cielo.valido and quickpay.valido else 1


def _gerar_cielo(args: argparse.Namespace) -> int:
    if args.data_fim < args.data_inicio:
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 2
    try:
        leitura = ler_cielo(args.arquivo)
        validacao = CieloValidator().validar(
            leitura,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        if not validacao.valido:
            print(formatar_resumo_validacao(validacao))
            return 1
        relatorio = CieloProcessor().processar(
            leitura,
            validacao,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        exportacao = CieloExporter().exportar(
            relatorio,
            diretorio_saida=args.saida,
            sobrescrever=args.sobrescrever,
        )
    except (CieloProcessingError, ValueError, OSError) as exc:
        print(f"Erro ao gerar relatorio Cielo: {exc}")
        return 1

    resumo = relatorio.resumo
    print(
        "\n".join(
            [
                "RELATORIO CIELO GERADO",
                "",
                f"Arquivo de entrada: {args.arquivo}",
                f"Arquivo de saida: {exportacao.caminho_saida}",
                "",
                f"Transacoes lidas: {resumo.transacoes_lidas}",
                f"Transacoes incluidas: {resumo.transacoes_incluidas}",
                f"Transacoes fora do periodo: {resumo.transacoes_fora_periodo}",
                "",
                f"Valor bruto: R$ {resumo.total_bruto}",
                f"Taxa/tarifa: R$ {resumo.total_taxa}",
                f"Valor liquido: R$ {resumo.total_liquido}",
                "",
                f"Blocos de cartao: {resumo.blocos_cartao}",
                f"Blocos Pix: {resumo.blocos_pix}",
                f"Validacao da saida: {'OK' if exportacao.validacao_saida_ok else 'FALHA'}",
            ]
        )
    )
    return 0


def _gerar_quickpay(args: argparse.Namespace) -> int:
    if args.data_fim < args.data_inicio:
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 2
    try:
        leitura = ler_quickpay(args.arquivo)
        recebimentos = (
            ler_recebimentos_bancarios(args.arquivo_recebimentos_quickpay)
            if args.arquivo_recebimentos_quickpay is not None
            else None
        )
        validacao = QuickPayValidator().validar(
            leitura,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
            recebimentos_bancarios=recebimentos,
        )
        if not validacao.valido:
            print(formatar_resumo_validacao(validacao))
            return 1
        relatorio = QuickPayProcessor().processar(
            leitura,
            validacao,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
            recebimentos_bancarios=recebimentos,
        )
        exportacao = QuickPayExporter().exportar(
            relatorio,
            diretorio_saida=args.saida,
            sobrescrever=args.sobrescrever,
        )
    except (QuickPayProcessingError, ValueError, OSError) as exc:
        print(f"Erro ao gerar relatorio QuickPay: {exc}")
        return 1

    resumo = relatorio.resumo
    print(
        "\n".join(
            [
                "RELATORIO QUICKPAY GERADO",
                "",
                f"Arquivo de entrada: {args.arquivo}",
                f"Arquivo de saida: {exportacao.caminho_saida}",
                "",
                f"Transacoes lidas: {resumo.transacoes_lidas}",
                f"Transacoes incluidas: {resumo.transacoes_incluidas}",
                f"Transacoes fora do periodo: {resumo.transacoes_fora_periodo}",
                "",
                f"Valor da Venda: R$ {resumo.total_bruto}",
                f"Taxa: R$ {resumo.total_taxa}",
                f"Valor liquido: R$ {resumo.total_liquido}",
                f"Bruto-Liquido: R$ {resumo.total_bruto_liquido}",
                f"Diferenca: R$ {resumo.total_diferenca_taxa}",
                (
                    f"Recebido no banco QuickPay: R$ {resumo.total_recebido_banco}"
                    if resumo.total_recebido_banco is not None
                    else (
                        "Conferência bancária não realizada: "
                        "recebimentos não informados ou incompletos."
                    )
                ),
                (
                    f"Diferenca banco-liquido: R$ {resumo.diferenca_total_banco_liquido}"
                    if resumo.diferenca_total_banco_liquido is not None
                    else "Diferenca banco-liquido: não calculada."
                ),
                "",
                f"Valor da Venda zero: {resumo.valor_bruto_zero}",
                f"Validacao da saida: {'OK' if exportacao.validacao_saida_ok else 'FALHA'}",
            ]
        )
    )
    return 0


def _gerar_recebimentos_quickpay(args: argparse.Namespace) -> int:
    try:
        recebimentos = [parse_recebimento_chat(item) for item in args.recebimento]
        caminho = criar_planilha_recebimentos_bancarios(
            recebimentos, diretorio_saida=args.saida, nome_arquivo=args.nome_arquivo
        )
    except (ValueError, OSError) as exc:
        print(f"Erro ao gerar planilha de recebimentos QuickPay: {exc}")
        return 1
    print(
        f"PLANILHA DE RECEBIMENTOS QUICKPAY GERADA\nArquivo: {caminho}\nGrupos: {len(recebimentos)}"
    )
    return 0


def _testar_integracao_velo(args: argparse.Namespace) -> int:
    if args.data_fim < args.data_inicio:
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 2
    try:
        config = load_velo_api_config()
        if args.auditoria_dir is not None:
            config = replace(
                config,
                audit=replace(config.audit, raw_directory=args.auditoria_dir),
            )
        transport = FixtureVeloTransport(args.fixtures, config)
        audit_writer = VeloAuditWriter(config.audit)
        client = VeloClient(
            config,
            token_provider=StaticTokenProvider(),
            transport=transport,
            audit_writer=audit_writer,
        )
        service = VeloIntegrationService(client)
        resultado = service.consultar_todas(
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
    except (VeloApiError, ValueError, OSError) as exc:
        print(f"Erro na simulacao da integracao Velo: {exc}")
        return 1

    linhas = [
        "SIMULACAO DA INTEGRACAO VELO",
        "",
        f"Cielo credito: {_count(resultado, CategoriaFiltroVelo.CIELO_CREDITO)} registros",
        f"Cielo debito: {_count(resultado, CategoriaFiltroVelo.CIELO_DEBITO)} registros",
        f"Cielo Pix: {_count(resultado, CategoriaFiltroVelo.CIELO_PIX)} registros",
        f"QuickPay credito: {_count(resultado, CategoriaFiltroVelo.QUICKPAY_CREDITO)} registros",
        f"QuickPay debito: {_count(resultado, CategoriaFiltroVelo.QUICKPAY_DEBITO)} registros",
        f"QuickPay Pix: {_count(resultado, CategoriaFiltroVelo.QUICKPAY_PIX)} registros",
        "",
        "Chamadas reais realizadas: 0",
        "Schemas validos: sim",
        f"Auditoria simulada: {'OK' if audit_writer.enabled() else 'desabilitada'}",
    ]
    if resultado.avisos:
        linhas.append(f"Avisos de resolucao: {len(resultado.avisos)}")
    print("\n".join(linhas))
    return 0


def _count(resultado: ResultadoConsultaVelo, categoria: CategoriaFiltroVelo) -> int:
    return len(resultado.registros_por_categoria[categoria])


def _testar_matching(args: argparse.Namespace) -> int:
    try:
        operadora = Operadora.CIELO if args.operadora == "cielo" else Operadora.QUICKPAY
        transacoes = _carregar_transacoes_matching(args.fixtures, operadora)
        registros = _carregar_registros_matching(
            args.fixtures,
            operadora,
            sistema_extra=bool(args.sistema_extra),
        )
        service = ReconciliationService()
        if operadora is Operadora.CIELO:
            resultado = service.conciliar_cielo(
                transacoes,
                registros,
                {CategoriaFiltroVelo.CIELO_CREDITO, CategoriaFiltroVelo.CIELO_PIX},
            )
        else:
            resultado = service.conciliar_quickpay(
                transacoes,
                registros,
                {CategoriaFiltroVelo.QUICKPAY_CREDITO},
            )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Erro na simulacao de matching: {exc}")
        return 1

    print(
        "\n".join(
            [
                "SIMULACAO DE MATCHING",
                "",
                formatar_resultado_matching(resultado),
                "",
                "Chamadas reais realizadas: 0",
                "Token solicitado: nao",
                "Relatorios Excel alterados: nao",
            ]
        )
    )
    return 0


def _carregar_transacoes_matching(
    fixtures_dir: Path, operadora: Operadora
) -> list[TransacaoOperadora]:
    filename = "cielo_operadora.json" if operadora is Operadora.CIELO else "quickpay_operadora.json"
    payload = json.loads((fixtures_dir / filename).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fixture de operadora deve ser uma lista")
    return [_transacao_fixture(item, operadora) for item in payload]


def _carregar_registros_matching(
    fixtures_dir: Path,
    operadora: Operadora,
    *,
    sistema_extra: bool,
) -> list[RegistroSistema]:
    if operadora is Operadora.CIELO:
        filename = "cielo_sistema.json"
    elif sistema_extra:
        filename = "quickpay_sistema_extra.json"
    else:
        filename = "quickpay_sistema.json"
    payload = json.loads((fixtures_dir / filename).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fixture de sistema deve ser uma lista")
    return [RegistroSistema.model_validate(item) for item in payload]


def _transacao_fixture(item: object, operadora: Operadora) -> TransacaoOperadora:
    if not isinstance(item, dict):
        raise ValueError("transacao fixture invalida")
    recebido = item.get("recebido_no_banco_quickpay")
    dados_originais = {"fixture_matching": True}
    if recebido is not None:
        dados_originais["recebido_no_banco_quickpay_normalizado"] = recebido
    return TransacaoOperadora(
        identificador_origem=str(item.get("identificador_origem", "")),
        operadora=operadora,
        modalidade=Modalidade(str(item["modalidade"])),
        bandeira=str(item.get("bandeira", "")),
        data_venda=date.fromisoformat(str(item["data_venda"])),
        hora_venda=_time_from_hhmm(item.get("hora_venda")),
        data_recebimento=date.fromisoformat(str(item["data_recebimento"])),
        numero_parcelas=int(item.get("numero_parcelas", 1)),
        valor_bruto=item["valor_bruto"],
        valor_liquido=item["valor_liquido"],
        taxa_original=item["taxa_original"],
        taxa_normalizada=item["taxa_original"],
        origem_arquivo=(
            OrigemRegistro.CIELO if operadora is Operadora.CIELO else OrigemRegistro.QUICKPAY
        ),
        linha_original=int(item["linha_original"]),
        dados_originais=dados_originais,
    )


def _time_from_hhmm(value: object | None) -> time | None:
    if value is None:
        return None

    hour, minute = str(value).split(":", maxsplit=1)
    return time(int(hour), int(minute))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "processar":
        return _processar(args)
    if args.command == "validar-cielo":
        return _validar_cielo(args)
    if args.command == "validar-quickpay":
        return _validar_quickpay(args)
    if args.command == "validar":
        return _validar_ambos(args)
    if args.command == "gerar-cielo":
        return _gerar_cielo(args)
    if args.command == "gerar-quickpay":
        return _gerar_quickpay(args)
    if args.command == "gerar-recebimentos-quickpay":
        return _gerar_recebimentos_quickpay(args)
    if args.command == "testar-integracao-velo":
        return _testar_integracao_velo(args)
    if args.command == "testar-matching":
        return _testar_matching(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
