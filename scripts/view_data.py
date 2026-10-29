"""Script tien ich xem du lieu nhanh trong cac co so du lieu cua he thong.

Danh cho sinh vien / giang vien kiem tra trong buoi bao cao:
1. SQLite: Nguoi dung (users), lich su hoi thoai (conversations, messages), nhat ky quan tri (admin_audit_logs).
2. ChromaDB: So luong vector chunks da nhung va metadata mau.
3. Neo4j: Thong ke so luong Node va Relationship (neu server dang bat).

Cach su dung:
    uv run python scripts/view_data.py
    uv run python scripts/view_data.py --users
    uv run python scripts/view_data.py --chat
    uv run python scripts/view_data.py --chroma
"""

import argparse
import os
import sqlite3
import sys

# Thiet lap UTF-8 output cho console Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def view_sqlite(db_path: str = "data/chat_history.db", show_users: bool = False, show_chat: bool = False):
    print("\n" + "=" * 70)
    print(f"📦 1. CO SO DU LIEU QUAN HE SQLITE ({db_path})")
    print("=" * 70)

    if not os.path.exists(db_path):
        print(f"⚠️ Chua tim thay file {db_path}. He thong se tu dong tao khi chay ung dung.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Danh sach cac bang
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    print("Cac bang hien co trong SQLite:")
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0]
        print(f"  • Bang '{t}': {count} ban ghi")

    # Xem danh sach nguoi dung gan nhat
    print("\n--- 👤 Danh sach 5 nguoi dung gan nhat ---")
    users = conn.execute(
        "SELECT id, username, email, role, status, created_at, last_login_at FROM users ORDER BY created_at DESC LIMIT 5;"
    ).fetchall()
    if users:
        print(f"{'Username':<20} | {'Email':<25} | {'Vai tro':<8} | {'Trang thai':<10} | {'Dang nhap cuoi'}")
        print("-" * 80)
        for u in users:
            last = (u['last_login_at'] or 'Chua co')[:19]
            print(f"{u['username']:<20} | {(u['email'] or 'None'):<25} | {u['role']:<8} | {u['status']:<10} | {last}")
    else:
        print("  (Chua co nguoi dung nao)")

    # Xem lich su cuoc tro chuyen gan nhat
    print("\n--- 💬 3 cuoc tro chuyen gan nhat ---")
    convs = conn.execute(
        """
        SELECT c.id, c.title, u.username, c.created_at, COUNT(m.id) as msg_count
        FROM conversations c
        LEFT JOIN users u ON c.user_id = u.id
        LEFT JOIN messages m ON c.id = m.conversation_id
        GROUP BY c.id
        ORDER BY c.created_at DESC LIMIT 3;
        """
    ).fetchall()
    if convs:
        for c in convs:
            print(f"Cuoc tro chuyen [{c['id'][:8]}...] boi '{c['username']}': {c['title']} ({c['msg_count']} tin nhan)")
            # Lay 2 tin nhan gan nhat
            msgs = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT 2;",
                (c["id"],),
            ).fetchall()
            for m in msgs:
                role_icon = "👤" if m["role"] == "user" else "🤖"
                snippet = m["content"].replace("\n", " ")[:70]
                print(f"   {role_icon} {m['role']}: {snippet}...")
    else:
        print("  (Chua co cuoc tro chuyen nao)")

    conn.close()


def view_chromadb():
    print("\n" + "=" * 70)
    print("🔍 2. CO SO DU LIEU VECTOR CHROMADB (chroma_data/)")
    print("=" * 70)
    try:
        from rag_chatbot.chroma_db import get_chroma_client
        from rag_chatbot.config import get_settings

        settings = get_settings()
        client = get_chroma_client()
        col = client.get_collection(name=settings.chroma_collection_name)
        count = col.count()
        print(f"✅ ChromaDB ket noi thanh cong!")
        print(f"  • Thu muc persist: '{settings.chroma_persist_directory}'")
        print(f"  • Collection: '{col.name}'")
        print(f"  • Tong so document chunks da nhung (embedded): {count} chunks")
        if count > 0:
            sample = col.peek(limit=1)
            if sample and sample["documents"]:
                print(f"\n--- Mau 1 document chunk dau tien ---")
                print(f"ID: {sample['ids'][0]}")
                print(f"Metadata: {sample['metadatas'][0]}")
                doc_snippet = sample["documents"][0].replace("\n", " ")[:120]
                print(f"Noi dung: {doc_snippet}...")
    except Exception as e:
        print(f"⚠️ Khong the doc ChromaDB: {e}")


def view_neo4j():
    print("\n" + "=" * 70)
    print("🕸️ 3. CO SO DU LIEU DO THI NEO4J (Graph Database)")
    print("=" * 70)
    try:
        from rag_chatbot.config import get_settings
        from neo4j import GraphDatabase

        settings = get_settings()
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=2.0,
        )
        with driver.session() as session:
            node_count = session.run("MATCH (n) RETURN count(n) AS c;").single()["c"]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c;").single()["c"]
            print("✅ Neo4j ket noi thanh cong tai " + settings.neo4j_uri)
            print(f"  • Tong so Node tren do thi: {node_count} nodes")
            print(f"  • Tong so Relationship:     {rel_count} relationships")
            print("  • Ban co the mo trinh duyet tai: http://localhost:7474 de xem truc quan bang Cypher.")
        driver.close()
    except Exception as e:
        print("ℹ️ Neo4j server hien chua bat hoac tu choi ket noi:")
        print(f"   ({e})")
        print("   Khi can xem, hay khoi dong Neo4j Desktop / Server va mo http://localhost:7474.")


def main():
    parser = argparse.ArgumentParser(description="Xem du lieu trong cac CSDL cua he thong RAG")
    parser.add_argument("--sqlite", action="store_true", help="Chi xem SQLite")
    parser.add_argument("--chroma", action="store_true", help="Chi xem ChromaDB")
    parser.add_argument("--neo4j", action="store_true", help="Chi xem Neo4j")
    args = parser.parse_args()

    # Neu khong truyen co nao, mac dinh hien thi ca 3
    show_all = not (args.sqlite or args.chroma or args.neo4j)

    if show_all or args.sqlite:
        view_sqlite()
    if show_all or args.chroma:
        view_chromadb()
    if show_all or args.neo4j:
        view_neo4j()

    print("\n" + "=" * 70)
    print("🎯 Hoan tat kiem tra du lieu he thong.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
