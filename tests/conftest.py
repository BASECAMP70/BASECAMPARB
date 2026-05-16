import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    import timesheet.storage as storage
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def app(isolated_data_dir):
    from timesheet.app import create_app
    app = create_app({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    return app.test_client()
