"""Kiem thu Chainlit SQLiteDataLayer:
1. Luu tru va khoi phuc Thread/Conversation.
2. Luu tru va khoi phuc Step/Message theo dung thu tu thoi gian.
3. Kiem tra phan quyen nghiem ngat giua cac user (User A khong thay Thread cua User B).
4. Tinh ben vung sau khi khoi tao lai DataLayer (mo phong app restart).
"""

import asyncio
import os
import uuid
import pytest

from chainlit.types import Pagination, ThreadFilter
from chainlit.step import StepDict
from chainlit.user import User

from rag_chatbot.chainlit_data_layer import SQLiteDataLayer
from rag_chatbot.database import get_db_connection, init_db


@pytest.fixture
def test_db(tmp_path):
    """Tao database SQLite tam cho test case."""
    db_file = str(tmp_path / "test_chainlit.db")
    init_db(db_file)
    return db_file


def test_datalayer_user_management(test_db):
    async def _test():
        dl = SQLiteDataLayer(db_path=test_db)
        user = User(identifier="test_user_01", metadata={"role": "user"})
        p_user = await dl.create_user(user)
        assert p_user is not None
        assert p_user.identifier == "test_user_01"

        # Lay lai user
        fetched = await dl.get_user("test_user_01")
        assert fetched is not None
        assert fetched.id == p_user.id
        assert fetched.metadata["role"] == "user"

    asyncio.run(_test())


def test_datalayer_thread_and_messages(test_db):
    async def _test():
        dl = SQLiteDataLayer(db_path=test_db)
        user_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())

        # 1. Tao Thread
        await dl.update_thread(thread_id=thread_id, name="Sửa điều hòa F16", user_id=user_id)

        # 2. Tao tin nhan user
        step_u = StepDict(
            id=str(uuid.uuid4()),
            threadId=thread_id,
            name="test_user",
            type="user_message",
            output="Điều hòa Panasonic báo lỗi F16 là bị làm sao?",
            input="",
            createdAt="2026-10-28T08:00:00Z",
            metadata={"user_id": user_id},
            streaming=False,
        )
        await dl.create_step(step_u)

        # 3. Tao tin nhan assistant
        step_a = StepDict(
            id=str(uuid.uuid4()),
            threadId=thread_id,
            name="Appliance AI",
            type="assistant_message",
            output="Lỗi F16 là lỗi cảm biến nhiệt độ đường ống ngoài trời.",
            input="",
            createdAt="2026-10-28T08:00:02Z",
            metadata={},
            streaming=False,
        )
        await dl.create_step(step_a)

        # 4. Doc lai Thread
        thread = await dl.get_thread(thread_id)
        assert thread is not None
        assert thread["name"] == "Sửa điều hòa F16"
        assert thread["userId"] == user_id
        assert len(thread["steps"]) == 2
        assert thread["steps"][0]["type"] == "user_message"
        assert thread["steps"][1]["type"] == "assistant_message"
        assert "F16" in thread["steps"][0]["output"]
        assert "ngoài trời" in thread["steps"][1]["output"]

    asyncio.run(_test())


def test_datalayer_user_isolation(test_db):
    async def _test():
        dl = SQLiteDataLayer(db_path=test_db)
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())

        thread_a1 = str(uuid.uuid4())
        thread_a2 = str(uuid.uuid4())
        thread_b1 = str(uuid.uuid4())

        # User A tao 2 threads
        await dl.update_thread(thread_id=thread_a1, name="Thread A1", user_id=user_a)
        await dl.update_thread(thread_id=thread_a2, name="Thread A2", user_id=user_a)

        # User B tao 1 thread
        await dl.update_thread(thread_id=thread_b1, name="Thread B1", user_id=user_b)

        # Kiem tra User A chi thay threads cua A
        list_a = await dl.list_threads(
            pagination=Pagination(first=10),
            filters=ThreadFilter(userId=user_a),
        )
        assert len(list_a.data) == 2
        thread_ids_a = [t["id"] for t in list_a.data]
        assert thread_a1 in thread_ids_a
        assert thread_a2 in thread_ids_a
        assert thread_b1 not in thread_ids_a

        # Kiem tra User B chi thay threads cua B
        list_b = await dl.list_threads(
            pagination=Pagination(first=10),
            filters=ThreadFilter(userId=user_b),
        )
        assert len(list_b.data) == 1
        assert list_b.data[0]["id"] == thread_b1

    asyncio.run(_test())


def test_datalayer_persistence_after_restart(test_db):
    async def _test():
        # Lan chay 1
        dl1 = SQLiteDataLayer(db_path=test_db)
        user_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        await dl1.update_thread(thread_id=thread_id, name="Persistent Thread", user_id=user_id)

        step = StepDict(
            id=str(uuid.uuid4()),
            threadId=thread_id,
            name="user",
            type="user_message",
            output="Hello RAG",
            input="",
            createdAt="2026-10-28T09:00:00Z",
            metadata={"user_id": user_id},
            streaming=False,
        )
        await dl1.create_step(step)

        # Mo phong app restart bang cach khoi tao instance dl2 moi hoan toan
        dl2 = SQLiteDataLayer(db_path=test_db)
        thread = await dl2.get_thread(thread_id)
        assert thread is not None
        assert thread["name"] == "Persistent Thread"
        assert len(thread["steps"]) == 1
        assert thread["steps"][0]["output"] == "Hello RAG"

    asyncio.run(_test())
