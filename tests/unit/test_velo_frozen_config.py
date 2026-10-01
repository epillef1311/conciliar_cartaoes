import sys
from pathlib import Path
from shutil import copyfile

import pytest

from conciliacao.domain.exceptions import ConfiguracaoError
from conciliacao.integrations.velo.config import load_velo_api_config


def test_frozen_app_reads_config_from_packaged_resources(tmp_path, monkeypatch):
    resources = tmp_path / "_internal"
    (resources / "config").mkdir(parents=True)
    copyfile(Path("config/velo_api.yaml"), resources / "config/velo_api.yaml")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(resources), raising=False)
    assert load_velo_api_config().base_url
    with pytest.raises(ConfiguracaoError):
        load_velo_api_config("config/custom_missing.yaml")
