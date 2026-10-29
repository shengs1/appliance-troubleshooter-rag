"""Cau hinh va fixtures chung cho toan bo test suite cua du an.

Co che co lap CSDL:
Tu dong chuyen huong moi ket noi SQLite toi file co so du lieu tam thoi (tmp_path).
Ngan chan viec chay pytest gay phinh to hoac ghi de vao file CSDL that: data/chat_history.db.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

# Thiet lap ngay khi pytest nap conftest, truoc khi cac module app duoc import
_TEST_TEMP_DIR = tempfile.TemporaryDirectory(prefix="rag_test_db_")
_TEST_DB_PATH = str(Path(_TEST_TEMP_DIR.name) / "test_chat_history.db")
os.environ["SQLITE_DB_PATH"] = _TEST_DB_PATH

from rag_chatbot.config import get_settings
get_settings.cache_clear()

from rag_chatbot.database import init_db
init_db(_TEST_DB_PATH)


@pytest.fixture(scope="session", autouse=True)
def test_environment_setup():
    """Fixture toan cuc dam bao moi test chay tren CSDL test co lap."""
    yield _TEST_DB_PATH
    try:
        _TEST_TEMP_DIR.cleanup()
    except Exception:
        pass
    get_settings.cache_clear()

