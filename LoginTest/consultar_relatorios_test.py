"""Consulta conciliacoes Cielo e QuickPay com token local, somente leitura."""

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from conciliacao.integrations.velo.audit import VeloAuditWriter
from conciliacao.integrations.velo.authentication import VeloTokenProvider
from conciliacao.integrations.velo.categories import categorias_cielo, categorias_quickpay
from conciliacao.integrations.velo.client import VeloClient
from conciliacao.integrations.velo.config import load_velo_api_config
from conciliacao.integrations.velo.exceptions import VeloApiError, VeloAuthenticationError
from conciliacao.integrations.velo.http import HttpResponse
from conciliacao.integrations.velo.service import (
    ResolucaoFormasRecebimento,
    VeloIntegrationService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use data no formato AAAA-MM-DD.") from error


def read_token(token_file: Path) -> str:
    if not token_file.is_file():
        raise RuntimeError(f"Arquivo de token nao encontrado: {token_file}")
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"Arquivo de token vazio: {token_file}")
    return token


class CallTimingRecorder:
    """Persiste progresso por chamada sem registrar token ou cabecalhos."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[dict[str, object]] = []
        self.lock = threading.Lock()

    def record(
        self,
        *,
        url: str,
        params: dict[str, object] | None,
        duration_ms: int,
        primeiro_byte_ms: int | None,
        status_http: int | None,
        error: Exception | None,
    ) -> None:
        entry = {
            "horario": datetime.now().astimezone().isoformat(timespec="seconds"),
            "endpoint": urlparse(url).path,
            "operadora_id": None if params is None else params.get("operadoraId"),
            "duracao_ms": duration_ms,
            "primeiro_byte_ms": primeiro_byte_ms,
            "status_http": status_http,
            "erro": None if error is None else type(error).__name__,
        }
        with self.lock:
            self.entries.append(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary_path.replace(self.path)


class PooledTimingTransport:
    """Transporte com uma sessao HTTP persistente por thread de consulta."""

    def __init__(self, recorder: CallTimingRecorder) -> None:
        self.recorder = recorder
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None,
        timeout: object,
    ) -> HttpResponse:
        started = time.perf_counter()
        try:
            response = self._session().get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
        except requests.Timeout as error:
            self.recorder.record(
                url=url,
                params=params,
                duration_ms=round((time.perf_counter() - started) * 1000),
                primeiro_byte_ms=None,
                status_http=None,
                error=error,
            )
            raise TimeoutError(str(error)) from error
        except requests.RequestException as error:
            self.recorder.record(
                url=url,
                params=params,
                duration_ms=round((time.perf_counter() - started) * 1000),
                primeiro_byte_ms=None,
                status_http=None,
                error=error,
            )
            from urllib.error import URLError

            raise URLError(str(error)) from error
        self.recorder.record(
            url=url,
            params=params,
            duration_ms=round((time.perf_counter() - started) * 1000),
            primeiro_byte_ms=round(response.elapsed.total_seconds() * 1000),
            status_http=response.status_code,
            error=None,
        )
        return HttpResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            text=response.text,
        )


def consultar_categorias(
    *,
    data_inicio: date,
    data_fim: date,
    max_concorrencia: int,
    recorder: CallTimingRecorder,
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, str | int | None]]]:
    config = load_velo_api_config(PROJECT_ROOT / "config" / "velo_api.yaml")
    execution_id = datetime.now().strftime("%Y%m%d_%H%M%S_relatorios")
    client = VeloClient(
        config,
        token_provider=VeloTokenProvider(),
        transport=PooledTimingTransport(recorder),
        audit_writer=VeloAuditWriter(config.audit, execution_id=execution_id),
    )
    service = VeloIntegrationService(client)
    try:
        resolucao = service.resolver_formas_recebimento()
    except VeloAuthenticationError:
        raise
    except VeloApiError as error:
        print(
            "Autocomplete indisponivel; usando IDs de fallback configurados "
            f"({type(error).__name__}).",
            flush=True,
        )
        resolucao = ResolucaoFormasRecebimento(
            ids_por_categoria=dict(config.formas_recebimento_fallback)
        )
    counts: dict[str, dict[str, int]] = {"cielo": {}, "quickpay": {}}
    errors: dict[str, dict[str, str | int | None]] = {}
    groups = {"cielo": categorias_cielo(), "quickpay": categorias_quickpay()}
    category_jobs = [
        (operadora, category) for operadora, categories in groups.items() for category in categories
    ]

    def consultar_categoria(operadora: str, category: Any) -> tuple[str, str, int | None, Any]:
        try:
            records = service.consultar_categoria(
                category,
                data_inicio=data_inicio,
                data_fim=data_fim,
                resolucao=resolucao,
            )
            return operadora, category.value, len(records), None
        except VeloAuthenticationError:
            raise
        except VeloApiError as error:
            return operadora, category.value, None, error

    if max_concorrencia == 1:
        results = (consultar_categoria(*job) for job in category_jobs)
    else:
        with ThreadPoolExecutor(max_workers=max_concorrencia) as executor:
            futures = [executor.submit(consultar_categoria, *job) for job in category_jobs]
            results = (future.result() for future in futures)
            results = list(results)

    for operadora, category, count, error in results:
        if error is None:
            assert count is not None
            counts[operadora][category] = count
        else:
            errors[category] = {
                "erro": type(error).__name__,
                "endpoint": error.endpoint,
                "status_http": error.status_code,
            }
    client.save_audit_metadata(
        period_start=data_inicio,
        period_end=data_fim,
        categories_requested=(*categorias_cielo(), *categorias_quickpay()),
    )
    return counts, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-inicio", required=True, type=parse_date)
    parser.add_argument("--data-fim", required=True, type=parse_date)
    parser.add_argument("--max-concorrencia", default=1, type=int)
    arguments = parser.parse_args()
    if arguments.data_fim < arguments.data_inicio:
        parser.error("data-fim nao pode ser anterior a data-inicio.")
    if arguments.max_concorrencia < 1:
        parser.error("max-concorrencia deve ser maior que zero.")

    load_dotenv(OUTPUT_DIR.parent / ".env")
    token_file = Path(os.getenv("VELO_TOKEN_FILE", str(OUTPUT_DIR / "token.txt")))
    if not token_file.is_absolute():
        token_file = OUTPUT_DIR.parent / token_file
    try:
        os.environ["VELO_BEARER_TOKEN"] = read_token(token_file)
        recorder = CallTimingRecorder(OUTPUT_DIR / "consulta_relatorios_chamadas.json")
        counts, errors = consultar_categorias(
            data_inicio=arguments.data_inicio,
            data_fim=arguments.data_fim,
            max_concorrencia=arguments.max_concorrencia,
            recorder=recorder,
        )
        summary = {
            "periodo": {
                "inicio": arguments.data_inicio.isoformat(),
                "fim": arguments.data_fim.isoformat(),
            },
            "cielo": counts["cielo"],
            "quickpay": counts["quickpay"],
            "categorias_com_erro": errors,
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        summary_path = OUTPUT_DIR / "consulta_relatorios_resumo.json"
        temporary_path = summary_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(summary_path)
        print(f"Periodo: {arguments.data_inicio.isoformat()} a {arguments.data_fim.isoformat()}")
        print(f"Cielo: {sum(counts['cielo'].values())} registros")
        print(f"QuickPay: {sum(counts['quickpay'].values())} registros")
        print(f"Categorias com erro: {len(errors)}")
        print(f"Log de chamadas: {recorder.path}")
        print("Consultas concluidas sem escrita na API.")
        return 0 if not errors else 1
    except Exception as error:
        print(f"Falha na consulta de relatorios: {error}")
        return 1
    finally:
        os.environ.pop("VELO_BEARER_TOKEN", None)


if __name__ == "__main__":
    raise SystemExit(main())
