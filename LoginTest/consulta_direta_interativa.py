"""Consulta Velo somente leitura com progresso no terminal e token efemero."""

import argparse
import getpass
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

import requests

BASE_URL = "https://api.v1.velosistema.com.br"
CATEGORIAS = {
    "Cielo credito": 81,
    "Cielo debito": 86,
    "Cielo PIX": 91,
    "QuickPay credito": 44,
    "QuickPay debito": 51,
    "QuickPay PIX": 42,
}
_LOCAL = threading.local()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a data no formato AAAA-MM-DD.") from error


def read_token() -> str:
    token = os.getenv("VELO_BEARER_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("Cole o token Bearer (nao sera exibido): ").strip()
    if not token:
        raise RuntimeError("Token nao informado.")
    return token


def get_session() -> requests.Session:
    session = getattr(_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _LOCAL.session = session
    return session


def consultar(
    *,
    nome: str,
    operadora_id: int,
    data_consulta: date,
    token: str,
) -> tuple[str, int | None, int | None, int | None, str | None]:
    params: dict[str, Any] = {
        "operadoraId": operadora_id,
        "intervaloDia": -1,
        "dataInicio": data_consulta.isoformat(),
        "dataFim": data_consulta.isoformat(),
        "isCompensado": 0,
    }
    print(f"[{nome}] iniciando...", flush=True)
    started = time.perf_counter()
    try:
        response = get_session().get(
            f"{BASE_URL}/listarConciliacaoCartaoRecebido",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params,
            timeout=(5, 30),
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        if not response.ok:
            return nome, response.status_code, elapsed_ms, None, "HTTP inesperado"
        payload = response.json()
        if not isinstance(payload, list):
            return nome, response.status_code, elapsed_ms, None, "Resposta nao e uma lista"
        return nome, response.status_code, elapsed_ms, len(payload), None
    except requests.Timeout:
        return nome, None, round((time.perf_counter() - started) * 1000), None, "timeout"
    except requests.RequestException as error:
        return nome, None, round((time.perf_counter() - started) * 1000), None, type(error).__name__
    except ValueError:
        return nome, 200, round((time.perf_counter() - started) * 1000), None, "JSON invalido"


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta direta e somente leitura da API Velo.")
    parser.add_argument("--data", type=parse_date, default=date.today())
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("concurrency deve ser maior que zero.")

    try:
        token = read_token()
    except RuntimeError as error:
        print(f"Falha: {error}")
        return 2

    print(f"Consultando {args.data.isoformat()} com concorrencia {args.concurrency}.", flush=True)
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        jobs = [
            executor.submit(
                consultar,
                nome=nome,
                operadora_id=operadora_id,
                data_consulta=args.data,
                token=token,
            )
            for nome, operadora_id in CATEGORIAS.items()
        ]
        failed = False
        for future in as_completed(jobs):
            nome, status, elapsed_ms, count, error = future.result()
            if error:
                failed = True
                print(f"[{nome}] falhou: {error}; {elapsed_ms} ms; HTTP {status}", flush=True)
            else:
                print(
                    f"[{nome}] concluido: {count} registros; {elapsed_ms} ms; HTTP {status}",
                    flush=True,
                )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
