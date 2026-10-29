"""Chainlit SQLite Data Layer.

Trien khai BaseDataLayer cua Chainlit de luu tru ben vung:
1. Danh sach Thread (Conversation) vao bang `conversations`.
2. Danh sach Step (Messages) vao bang `messages`.
3. Phan quyen nghiem ngat: nguoi dung chi co the doc/ghi/xoa thread cua chinh minh.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from chainlit.data import BaseDataLayer
from chainlit.types import (
    Feedback,
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.step import StepDict
from chainlit.user import PersistedUser, User

from rag_chatbot.database import (
    create_conversation,
    get_conversation_by_id,
    get_conversation_messages,
    get_db_connection,
    get_db_path,
    get_user_by_id,
    get_user_by_username,
)


class SQLiteDataLayer(BaseDataLayer):
    """Data Layer tuy bien cho Chainlit su dung SQLite database hien co."""

    def __init__(self, db_path: str | None = None):
        self.db_path = get_db_path(db_path)

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        """Lay thong tin user tu CSDL SQLite."""
        user = get_user_by_username(identifier, db_path=self.db_path)
        if not user:
            user = get_user_by_id(identifier, db_path=self.db_path)
        if not user:
            return None

        return PersistedUser(
            id=user["id"],
            identifier=user["username"],
            createdAt=user.get("created_at") or datetime.now(timezone.utc).isoformat(),
            metadata={
                "role": user.get("role", "user"),
                "status": user.get("status", "active"),
                "email": user.get("email"),
            },
        )

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        """Tao user moi (neu can)."""
        existing = await self.get_user(user.identifier)
        if existing:
            return existing

        now_str = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        role = user.metadata.get("role", "user") if user.metadata else "user"
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, role, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?);
                """,
                (user_id, user.identifier, "", role, now_str),
            )
            conn.commit()

        return PersistedUser(
            id=user_id,
            identifier=user.identifier,
            createdAt=now_str,
            metadata={"role": role, "status": "active"},
        )

    async def get_thread_author(self, thread_id: str) -> str:
        """Tra ve identifier hoac id cua user so huu thread."""
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT c.user_id, u.username
                FROM conversations c
                LEFT JOIN users u ON c.user_id = u.id
                WHERE c.id = ?;
                """,
                (thread_id,),
            ).fetchone()
            if row:
                return row["username"] or row["user_id"]
        return ""

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        """Lay chi tiet mot cuoc tro chuyen kem toan bo tin nhan cua no."""
        conv = get_conversation_by_id(thread_id, db_path=self.db_path)
        if not conv:
            return None

        db_messages = get_conversation_messages(thread_id, db_path=self.db_path)
        user = get_user_by_id(conv["user_id"], db_path=self.db_path)
        user_ident = user["username"] if user else conv["user_id"]

        steps: List[StepDict] = []
        for msg in db_messages:
            role = msg["role"]
            is_user = role == "user"
            step_type = "user_message" if is_user else "assistant_message"
            name = user_ident if is_user else "Appliance AI"
            content = msg["content"]
            steps.append(
                StepDict(
                    id=msg["id"],
                    threadId=thread_id,
                    name=name,
                    type=step_type,
                    output=content,
                    input=content if is_user else "",
                    createdAt=msg.get("created_at") or conv.get("created_at"),
                    start=msg.get("created_at"),
                    end=msg.get("created_at"),
                    metadata={},
                    streaming=False,
                )
            )

        return ThreadDict(
            id=conv["id"],
            createdAt=conv.get("created_at") or datetime.now(timezone.utc).isoformat(),
            name=conv.get("title") or "Cuộc trò chuyện",
            userId=conv["user_id"],
            userIdentifier=user_ident,
            tags=[],
            metadata={},
            steps=steps,
            elements=[],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        """Cap nhat tieu de hoac nguoi so huu thread."""
        now_str = datetime.now(timezone.utc).isoformat()
        with get_db_connection(self.db_path) as conn:
            # Dam bao user_id ton tai trong bang users neu co de tranh loi Foreign Key
            if user_id:
                u_row = conn.execute("SELECT id FROM users WHERE id = ?;", (user_id,)).fetchone()
                if not u_row:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO users (id, username, password_hash, role, status, created_at)
                        VALUES (?, ?, '', 'user', 'active', ?);
                        """,
                        (user_id, f"user_{user_id[:8]}", now_str),
                    )

            # Neu chua ton tai thread va co user_id -> tao moi
            row = conn.execute("SELECT id FROM conversations WHERE id = ?;", (thread_id,)).fetchone()
            if not row and user_id:
                title = name.strip() if name else "Cuộc trò chuyện mới"
                conn.execute(
                    """
                    INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (thread_id, user_id, title, now_str, now_str),
                )
            elif row:
                updates = ["updated_at = ?"]
                params = [now_str]
                if name is not None:
                    # Bo qua cac interaction name noi bo bang tieng Anh cua Chainlit
                    clean_name = name.strip()
                    if clean_name and clean_name not in ("quick_sample_question", "admin_open_panel", "audio", "default"):
                        updates.append("title = ?")
                        params.append(clean_name[:45])
                if user_id is not None:
                    updates.append("user_id = ?")
                    params.append(user_id)
                params.append(thread_id)
                conn.execute(
                    f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?;",
                    tuple(params),
                )
            conn.commit()

    async def delete_thread(self, thread_id: str):
        """Xoa mot cuoc tro chuyen khoi CSDL."""
        with get_db_connection(self.db_path) as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?;", (thread_id,))
            conn.commit()

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        """Liet ke danh sach cuoc tro chuyen, kiem tra phan quyen nghiem ngat theo user_id."""
        target_user_id = filters.userId
        # Neu co userIdentifier ma chua co userId, tra cuu userId
        user_ident = getattr(filters, "userIdentifier", None)
        if not target_user_id and user_ident:
            u = get_user_by_username(user_ident, db_path=self.db_path)
            if u:
                target_user_id = u["id"]

        if not target_user_id:
            return PaginatedResponse(
                data=[],
                pageInfo=PageInfo(hasNextPage=False, startCursor=None, endCursor=None),
            )

        limit = pagination.first if pagination and pagination.first else 40

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?;
            """
            rows = cursor.execute(query, (target_user_id, limit + 1)).fetchall()

        has_next = len(rows) > limit
        selected_rows = rows[:limit]

        thread_dicts: List[ThreadDict] = []
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            for r in selected_rows:
                raw_title = (r["title"] or "Cuộc trò chuyện").strip()
                # Neu tieu de chua duoc dat hoac bi dinh interaction noi bo / cau chao mac dinh
                if raw_title in ("quick_sample_question", "admin_open_panel", "Cuộc trò chuyện mới") or raw_title.startswith("Xin chào"):
                    msg_row = cur.execute(
                        "SELECT content FROM messages WHERE conversation_id = ? AND content NOT LIKE 'Xin chào%' ORDER BY created_at ASC LIMIT 1;",
                        (r["id"],)
                    ).fetchone()
                    if msg_row and msg_row[0]:
                        raw_title = msg_row[0].strip().splitlines()[0][:45]
                    else:
                        raw_title = "Câu hỏi mẫu"

                thread_dicts.append(
                    ThreadDict(
                        id=r["id"],
                        createdAt=r["created_at"],
                        name=raw_title,
                        userId=r["user_id"],
                        userIdentifier=user_ident,
                        tags=[],
                        metadata={},
                        steps=[],
                        elements=[],
                    )
                )

        start_cursor = thread_dicts[0]["id"] if thread_dicts else None
        end_cursor = thread_dicts[-1]["id"] if thread_dicts else None
        return PaginatedResponse(
            data=thread_dicts,
            pageInfo=PageInfo(
                hasNextPage=has_next,
                startCursor=start_cursor,
                endCursor=end_cursor,
            ),
        )

    async def create_step(self, step_dict: StepDict):
        """Luu mot tin nhan (user hoac assistant) vao bang messages."""
        thread_id = step_dict.get("threadId")
        if not thread_id:
            return

        step_id = step_dict.get("id") or str(uuid.uuid4())
        step_type = step_dict.get("type", "")
        # Chi luu user_message hoac assistant_message
        if step_type not in ["user_message", "assistant_message"]:
            return

        role = "user" if step_type == "user_message" else "assistant"
        content = step_dict.get("output", "") or step_dict.get("input", "")
        if not content:
            return

        now_str = step_dict.get("createdAt") or datetime.now(timezone.utc).isoformat()

        with get_db_connection(self.db_path) as conn:
            # Kiem tra xem cuoc tro chuyen da ton tai chua
            row = conn.execute("SELECT id, title, user_id FROM conversations WHERE id = ?;", (thread_id,)).fetchone()
            if not row:
                # Neu chua ton tai: chi lay title neu la tin nhan user, tranh lay loi chao he thong
                if role == "user":
                    title = content.strip().splitlines()[0][:45] if content.strip() else "Cuộc trò chuyện mới"
                else:
                    title = "Cuộc trò chuyện mới"
                # Tam thoi gan user_id default neu chua ro
                user_id = step_dict.get("metadata", {}).get("user_id", "anonymous")
                # Dam bao user_id ton tai trong bang users
                u_row = conn.execute("SELECT id FROM users WHERE id = ?;", (user_id,)).fetchone()
                if not u_row:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO users (id, username, password_hash, role, status, created_at)
                        VALUES (?, ?, '', 'user', 'active', ?);
                        """,
                        (user_id, f"user_{user_id[:8]}", now_str),
                    )
                conn.execute(
                    """
                    INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (thread_id, user_id, title, now_str, now_str),
                )
            else:
                # Cap nhat updated_at va tieu de neu tieu de con mac dinh hoac welcome text
                updates = ["updated_at = ?"]
                params = [now_str]
                current_title = (row["title"] or "").strip()
                if role == "user" and (
                    current_title in ("Cuộc trò chuyện mới", "quick_sample_question", "admin_open_panel")
                    or current_title.startswith("Xin chào")
                ):
                    clean_first_line = content.strip().splitlines()[0][:45]
                    if clean_first_line:
                        updates.append("title = ?")
                        params.append(clean_first_line)
                params.append(thread_id)
                conn.execute(
                    f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?;",
                    tuple(params),
                )

            # Luu message vao bang messages (tranh trung lap bang INSERT OR IGNORE / REPLACE)
            conn.execute(
                """
                INSERT OR REPLACE INTO messages (id, conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (step_id, thread_id, role, content, now_str),
            )
            conn.commit()

    async def update_step(self, step_dict: StepDict):
        """Cap nhat noi dung tin nhan neu co."""
        step_id = step_dict.get("id")
        content = step_dict.get("output", "")
        if step_id and content:
            with get_db_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE messages SET content = ? WHERE id = ?;",
                    (content, step_id),
                )
                conn.commit()

    async def delete_step(self, step_id: str):
        """Xoa mot tin nhan khoi messages."""
        with get_db_connection(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE id = ?;", (step_id,))
            conn.commit()

    # Cac stub methods phu thuoc tinh nang Chainlit
    async def delete_feedback(self, feedback_id: str) -> bool:
        return True

    async def upsert_feedback(self, feedback: Feedback) -> str:
        return feedback.id or str(uuid.uuid4())

    async def create_element(self, element: Any):
        pass

    async def get_element(self, thread_id: str, element_id: str) -> Optional[Any]:
        return None

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        pass

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        pass

    async def get_favorite_steps(self, user_id: str) -> List[StepDict]:
        return []
