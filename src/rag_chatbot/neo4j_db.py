"""Module quan ly co so du lieu do thi Neo4j (Knowledge Graph).

Nhiem vu:
1. Khoi tao va quan ly ket noi Neo4j Driver.
2. Thuc thi cac truy van Cypher co tham so (parameterized queries).
3. Khoi tao rang buoc duy nhat (Uniqueness Constraints) cho cac node.
4. Nap du lieu thuc the va quan he tu dataset.xlsx vao Neo4j su dung MERGE.
5. Cung cap cac ham kiem tra va xac thuc do thi (Knowledge Graph Verification).
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd
from neo4j import GraphDatabase

from rag_chatbot.config import get_settings


def get_neo4j_driver(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> Any:
    """Khoi tao va tra ve doi tuong Neo4j Driver.
    
    Lay thong tin ket noi tu config (mac dinh bolt://localhost:7687, neo4j/password123).
    """
    settings = get_settings()
    target_uri = uri or settings.neo4j_uri
    target_user = user or settings.neo4j_user
    target_password = password or settings.neo4j_password

    driver = GraphDatabase.driver(
        target_uri,
        auth=(target_user, target_password),
    )
    return driver


def close_driver(driver: Any) -> None:
    """Dong ket noi Neo4j Driver an toan."""
    if driver is not None:
        driver.close()


def run_query(
    query: str,
    parameters: dict[str, Any] | None = None,
    driver: Any = None,
) -> list[dict[str, Any]]:
    """Thuc thi cau truy van Cypher co tham so va tra ve danh sach ban ghi dict.
    
    Args:
        query: Cau lenh Cypher (vi du: MATCH (n:Brand) RETURN n.name AS name).
        parameters: Tham so truyen vao cau truy van de phong chong Cypher injection.
        driver: Driver Neo4j; neu None se tu khoi tao va dong sau khi chay.
        
    Returns:
        Danh sach cac dict chua du lieu ket qua.
    """
    should_close = False
    active_driver = driver
    if active_driver is None:
        active_driver = get_neo4j_driver()
        should_close = True

    params = parameters or {}
    try:
        with active_driver.session() as session:
            result = session.run(query, params)
            return [record.data() for record in result]
    finally:
        if should_close:
            active_driver.close()


def init_constraints(driver: Any = None) -> None:
    """Khoi tao rang buoc tinh duy nhat (UNIQUE constraint) cho cac khoa chinh cua node.
    
    Giup tang toc do tim kiem va dam bao tinh toan ven du lieu khi dung MERGE.
    """
    constraints = [
        "CREATE CONSTRAINT brand_id_unique IF NOT EXISTS FOR (n:Brand) REQUIRE n.brand_id IS UNIQUE",
        "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (n:Device) REQUIRE n.device_id IS UNIQUE",
        "CREATE CONSTRAINT issue_id_unique IF NOT EXISTS FOR (n:Issue) REQUIRE n.issue_id IS UNIQUE",
        "CREATE CONSTRAINT error_id_unique IF NOT EXISTS FOR (n:ErrorCode) REQUIRE n.error_id IS UNIQUE",
        "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (n:Question) REQUIRE n.question_id IS UNIQUE",
        "CREATE CONSTRAINT answer_id_unique IF NOT EXISTS FOR (n:Answer) REQUIRE n.answer_id IS UNIQUE",
        "CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE",
    ]

    for stmt in constraints:
        run_query(stmt, driver=driver)


def ingest_neo4j_from_excel(
    excel_path: str | Path = "data/raw/dataset.xlsx",
    driver: Any = None,
) -> dict[str, int]:
    """Nap toan bo thuc the (Nodes) va quan he (Relationships) tu dataset.xlsx vao Neo4j.
    
    Quy trinh:
    1. Tao constraints.
    2. Doc tung sheet bang pandas.
    3. Su dung UNWIND + MERGE de nap batch nhanh va khong tao node/edge trung lap.
    
    Returns:
        Dict thong ke so luong thuc the va quan he da nap.
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay file dataset tai: {path}")

    active_driver = driver or get_neo4j_driver()
    stats: dict[str, int] = {}

    # 1. Khoi tao cac rang buoc duy nhat
    init_constraints(driver=active_driver)

    # 2. Nap cac Node thuc the
    # --- 2.1 Brands ---
    df_brands = pd.read_excel(path, sheet_name="BRANDS").fillna("")
    records_brands = df_brands.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:Brand {brand_id: row.brand_id})
        SET n.name = row.name
        """,
        parameters={"batch": records_brands},
        driver=active_driver,
    )
    stats["Brand"] = len(records_brands)

    # --- 2.2 Devices ---
    df_devices = pd.read_excel(path, sheet_name="DEVICES").fillna("")
    records_devices = df_devices.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:Device {device_id: row.device_id})
        SET n.name = row.name
        """,
        parameters={"batch": records_devices},
        driver=active_driver,
    )
    stats["Device"] = len(records_devices)

    # --- 2.3 Issues ---
    df_issues = pd.read_excel(path, sheet_name="ISSUES").fillna("")
    records_issues = df_issues.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:Issue {issue_id: row.issue_id})
        SET n.brand_id = row.brand_id,
            n.device_id = row.device_id,
            n.type = row.type,
            n.name = row.name,
            n.issue_key = row.issue_key
        """,
        parameters={"batch": records_issues},
        driver=active_driver,
    )
    stats["Issue"] = len(records_issues)

    # --- 2.4 ErrorCodes ---
    df_errors = pd.read_excel(path, sheet_name="ERROR_CODES").fillna("")
    records_errors = df_errors.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:ErrorCode {error_id: row.error_id})
        SET n.code = row.code
        """,
        parameters={"batch": records_errors},
        driver=active_driver,
    )
    stats["ErrorCode"] = len(records_errors)

    # --- 2.5 Questions ---
    df_questions = pd.read_excel(path, sheet_name="QUESTIONS").fillna("")
    records_questions = df_questions.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:Question {question_id: row.question_id})
        SET n.question = row.question,
            n.question_original = row.question_original,
            n.question_normalized = row.question_normalized,
            n.question_key = row.question_key,
            n.question_type = row.question_type,
            n.brand_id = row.brand_id,
            n.device_id = row.device_id,
            n.issue_id = row.issue_id
        """,
        parameters={"batch": records_questions},
        driver=active_driver,
    )
    stats["Question"] = len(records_questions)

    # --- 2.6 Answers ---
    df_answers = pd.read_excel(path, sheet_name="ANSWERS").fillna("")
    records_answers = df_answers.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:Answer {answer_id: row.answer_id})
        SET n.cause = row.cause,
            n.solution = row.solution,
            n.answer_type = row.answer_type,
            n.answer = row.answer
        """,
        parameters={"batch": records_answers},
        driver=active_driver,
    )
    stats["Answer"] = len(records_answers)

    # --- 2.7 Sources ---
    df_sources = pd.read_excel(path, sheet_name="SOURCES").fillna("")
    records_sources = df_sources.to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MERGE (n:Source {source_id: row.source_id})
        SET n.url = row.url,
            n.domain = row.domain,
            n.official = row.official
        """,
        parameters={"batch": records_sources},
        driver=active_driver,
    )
    stats["Source"] = len(records_sources)

    # 3. Nap cac Relationships tu sheet RELATIONSHIPS
    df_rels = pd.read_excel(path, sheet_name="RELATIONSHIPS").fillna("")
    
    # 3.1 HAS_DEVICE (Brand -> Device)
    rels_has_device = df_rels[df_rels["relationship"] == "HAS_DEVICE"].to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MATCH (a:Brand {brand_id: row.from_id})
        MATCH (b:Device {device_id: row.to_id})
        MERGE (a)-[:HAS_DEVICE]->(b)
        """,
        parameters={"batch": rels_has_device},
        driver=active_driver,
    )
    stats["HAS_DEVICE"] = len(rels_has_device)

    # 3.2 HAS_ISSUE (Device -> Issue)
    rels_has_issue = df_rels[df_rels["relationship"] == "HAS_ISSUE"].to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MATCH (a:Device {device_id: row.from_id})
        MATCH (b:Issue {issue_id: row.to_id})
        MERGE (a)-[:HAS_ISSUE]->(b)
        """,
        parameters={"batch": rels_has_issue},
        driver=active_driver,
    )
    stats["HAS_ISSUE"] = len(rels_has_issue)

    # 3.3 HAS_ERROR_CODE (Issue -> ErrorCode)
    rels_has_error = df_rels[df_rels["relationship"] == "HAS_ERROR_CODE"].to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MATCH (a:Issue {issue_id: row.from_id})
        MATCH (b:ErrorCode {error_id: row.to_id})
        MERGE (a)-[:HAS_ERROR_CODE]->(b)
        """,
        parameters={"batch": rels_has_error},
        driver=active_driver,
    )
    stats["HAS_ERROR_CODE"] = len(rels_has_error)

    # 3.4 ABOUT (Question -> Issue)
    rels_about = df_rels[df_rels["relationship"] == "ABOUT"].to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MATCH (a:Question {question_id: row.from_id})
        MATCH (b:Issue {issue_id: row.to_id})
        MERGE (a)-[:ABOUT]->(b)
        """,
        parameters={"batch": rels_about},
        driver=active_driver,
    )
    stats["ABOUT"] = len(rels_about)

    # 3.5 ANSWERED_BY (Question -> Answer)
    rels_answered = df_rels[df_rels["relationship"] == "ANSWERED_BY"].to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MATCH (a:Question {question_id: row.from_id})
        MATCH (b:Answer {answer_id: row.to_id})
        MERGE (a)-[:ANSWERED_BY]->(b)
        """,
        parameters={"batch": rels_answered},
        driver=active_driver,
    )
    stats["ANSWERED_BY"] = len(rels_answered)

    # 3.6 SOURCED_FROM (Question -> Source)
    rels_sourced = df_rels[df_rels["relationship"] == "SOURCED_FROM"].to_dict("records")
    run_query(
        """
        UNWIND $batch AS row
        MATCH (a:Question {question_id: row.from_id})
        MATCH (b:Source {source_id: row.to_id})
        MERGE (a)-[:SOURCED_FROM]->(b)
        """,
        parameters={"batch": rels_sourced},
        driver=active_driver,
    )
    stats["SOURCED_FROM"] = len(rels_sourced)

    return stats


def get_graph_counts(driver: Any = None) -> dict[str, dict[str, int]]:
    """Thong ke tong so node theo label va tong so relationship theo type."""
    # Dem nodes theo label
    labels = ["Brand", "Device", "Issue", "ErrorCode", "Question", "Answer", "Source"]
    node_counts: dict[str, int] = {}
    for label in labels:
        res = run_query(f"MATCH (n:{label}) RETURN count(n) AS count", driver=driver)
        node_counts[label] = res[0]["count"] if res else 0

    # Dem relationships theo type
    rel_types = ["HAS_DEVICE", "HAS_ISSUE", "HAS_ERROR_CODE", "ABOUT", "ANSWERED_BY", "SOURCED_FROM"]
    rel_counts: dict[str, int] = {}
    for r_type in rel_types:
        res = run_query(f"MATCH ()-[r:{r_type}]->() RETURN count(r) AS count", driver=driver)
        rel_counts[r_type] = res[0]["count"] if res else 0

    return {
        "nodes": node_counts,
        "relationships": rel_counts,
    }


def verify_record_q0358(driver: Any = None) -> dict[str, Any] | None:
    """Truy van kiem tra ban ghi mau Q0358 va toan bo duong di quan he tren do thi."""
    query = """
    MATCH (q:Question {question_id: 'Q0358'})
    MATCH (b:Brand {brand_id: q.brand_id})
    OPTIONAL MATCH (b)-[:HAS_DEVICE]->(d:Device {device_id: q.device_id})
    OPTIONAL MATCH (q)-[:ABOUT]->(i:Issue)
    OPTIONAL MATCH (i)-[:HAS_ERROR_CODE]->(e:ErrorCode)
    OPTIONAL MATCH (q)-[:ANSWERED_BY]->(a:Answer)
    OPTIONAL MATCH (q)-[:SOURCED_FROM]->(s:Source)
    RETURN 
        q.question_id AS question_id,
        q.question AS question,
        b.name AS brand,
        d.name AS device,
        i.issue_id AS issue_id,
        i.name AS issue_name,
        e.code AS error_code,
        a.answer_id AS answer_id,
        a.cause AS cause,
        a.solution AS solution,
        s.source_id AS source_id,
        s.url AS source_url
    """
    records = run_query(query, driver=driver)
    return records[0] if records else None


if __name__ == "__main__":
    print("1. Bat dau nap du lieu thuc te tu dataset.xlsx vao Neo4j...")
    ingest_stats = ingest_neo4j_from_excel()
    print("-> Ket qua nap cac thanh phan:", ingest_stats)

    print("\n2. Thong ke tong the do thi tri thuc:")
    graph_stats = get_graph_counts()
    print("   Nodes:", graph_stats["nodes"])
    print("   Relationships:", graph_stats["relationships"])

    print("\n3. Kiem tra ban ghi mau Q0358 tren do thi:")
    sample = verify_record_q0358()
    if sample:
        print(f"   - Question ID: {sample['question_id']}")
        print(f"   - Brand: {sample['brand']}, Device: {sample['device']}")
        print(f"   - Issue: {sample['issue_name']} (ID: {sample['issue_id']})")
        print(f"   - Error Code: {sample['error_code']}")
        print(f"   - Cause: {sample['cause']}")
        print(f"   - Solution: {sample['solution']}")
        print(f"   - Source: {sample['source_url']}")
    print("\nHoan tat kiem tra Neo4j!")

