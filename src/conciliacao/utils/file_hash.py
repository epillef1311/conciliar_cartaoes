"""Hash de arquivos em modo somente leitura."""

import hashlib
from pathlib import Path

from conciliacao.domain.exceptions import ArquivoError

DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: str | Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Calcula SHA-256 lendo o arquivo em blocos, sem modificar seu conteudo."""
    file_path = Path(path)
    if chunk_size <= 0:
        raise ArquivoError("chunk_size deve ser maior que zero")
    if not file_path.is_file():
        raise ArquivoError(f"arquivo nao encontrado: {file_path}")

    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as source:
            while chunk := source.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise ArquivoError(f"nao foi possivel ler o arquivo: {file_path}") from exc
    return digest.hexdigest()
