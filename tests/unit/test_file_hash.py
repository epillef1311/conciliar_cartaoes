from __future__ import annotations

import hashlib
from pathlib import Path

from conciliacao.utils.file_hash import sha256_file


def test_sha256_file_reads_in_chunks_without_modifying_content(tmp_path: Path):
    content = b"registro artificial para hash\n" * 10
    source = tmp_path / "entrada.bin"
    source.write_bytes(content)
    before = source.read_bytes()

    assert sha256_file(source, chunk_size=7) == hashlib.sha256(content).hexdigest()
    assert source.read_bytes() == before
