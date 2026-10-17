import importlib.util
import shutil
from pathlib import Path


def test_settings_load_root_env_independent_of_working_directory(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    config = root / "ai" / "app" / "config" / "settings.py"
    config.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "app/config/settings.py", config)
    (root / ".env").write_text("DISCOVERY_MAX_CANDIDATES=17\n", encoding="utf-8")
    (root / "ai" / ".env").write_text("DISCOVERY_MAX_CANDIDATES=29\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".env").write_text("DISCOVERY_MAX_CANDIDATES=31\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("DISCOVERY_MAX_CANDIDATES", raising=False)

    spec = importlib.util.spec_from_file_location("isolated_settings", config)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.settings.discovery_max_candidates == 17
    assert module.Settings(_env_file=None).discovery_max_candidates == 30
    assert module.Settings(_env_file=root / "ai" / ".env").discovery_max_candidates == 29
