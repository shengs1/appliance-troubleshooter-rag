"""Kiem thu chuc nang nap du lieu va truy van do thi Neo4j (Phase 4).

Cac test case bao gom:
1. Kiem tra cau hinh ket noi Neo4j tu Settings.
2. Kiem tra ket noi thuc te toi Neo4j server qua driver.
3. Kiem tra so luong node cua tat ca 7 label theo dung bo du lieu thuc te.
4. Kiem tra so luong relationship cua tat ca 6 loai quan he theo dung bo du lieu.
5. Kiem tra ban ghi mau Q0358 va cac duong di quan he:
   - Question -> ABOUT -> Issue -> HAS_ERROR_CODE -> ErrorCode
   - Question -> ANSWERED_BY -> Answer
   - Question -> SOURCED_FROM -> Source
"""

import pytest

from rag_chatbot.config import get_settings
from rag_chatbot.neo4j_db import (
    get_graph_counts,
    get_neo4j_driver,
    run_query,
    verify_record_q0358,
)


def test_neo4j_config_loaded():
    """Kiem tra cau hinh ket noi Neo4j co the duoc doc chinh xac tu config."""
    settings = get_settings()
    assert settings.neo4j_uri.startswith("bolt://")
    assert settings.neo4j_user == "neo4j"
    assert len(settings.neo4j_password) > 0


def test_neo4j_connection():
    """Kiem tra khoi tao driver va kiem tra ket noi toi Neo4j server."""
    driver = get_neo4j_driver()
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


def test_expected_node_labels_and_counts():
    """Kiem tra 7 node labels duoc tao tu du lieu thuc te voi so luong chinh xac."""
    driver = get_neo4j_driver()
    try:
        counts = get_graph_counts(driver=driver)
        node_counts = counts["nodes"]

        expected_counts = {
            "Brand": 3,
            "Device": 10,
            "Issue": 632,
            "ErrorCode": 332,
            "Question": 1090,
            "Answer": 1090,
            "Source": 31,
        }

        for label, expected in expected_counts.items():
            assert label in node_counts, f"Thieu label: {label}"
            assert node_counts[label] == expected, (
                f"So luong node {label} khong dung: thuc te {node_counts[label]} != ky vong {expected}"
            )
    finally:
        driver.close()


def test_expected_relationships_and_counts():
    """Kiem tra 6 loai quan he (relationships) voi so luong chinh xac tu dataset."""
    driver = get_neo4j_driver()
    try:
        counts = get_graph_counts(driver=driver)
        rel_counts = counts["relationships"]

        expected_rels = {
            "HAS_DEVICE": 20,
            "HAS_ISSUE": 632,
            "HAS_ERROR_CODE": 469,
            "ABOUT": 1090,
            "ANSWERED_BY": 1090,
            "SOURCED_FROM": 1090,
        }

        for r_type, expected in expected_rels.items():
            assert r_type in rel_counts, f"Thieu quan he: {r_type}"
            assert rel_counts[r_type] == expected, (
                f"So luong quan he {r_type} khong dung: thuc te {rel_counts[r_type]} != ky vong {expected}"
            )
    finally:
        driver.close()


def test_q0358_example_and_query_paths():
    """Kiem tra ban ghi mau Q0358 va cac duong di quan he tren do thi tri thuc."""
    driver = get_neo4j_driver()
    try:
        record = verify_record_q0358(driver=driver)
        assert record is not None, "Khong tim thay ban ghi Q0358 trong Neo4j!"

        # Kiem tra cac thong tin cot loi cua ban ghi mau
        assert record["question_id"] == "Q0358"
        assert record["brand"] == "Samsung"
        assert record["device"] == "Điều hòa"
        assert record["error_code"] == "CF"
        assert record["issue_id"] == "I0249"
        assert record["source_id"] == "S008"

        # 1. Kiem tra duong di: Question -> ABOUT -> Issue -> HAS_ERROR_CODE -> ErrorCode
        path_error = run_query(
            """
            MATCH (q:Question {question_id: 'Q0358'})-[:ABOUT]->(i:Issue)-[:HAS_ERROR_CODE]->(e:ErrorCode)
            RETURN q.question_id AS q_id, i.issue_id AS i_id, e.code AS err_code
            """,
            driver=driver,
        )
        assert len(path_error) == 1
        assert path_error[0]["err_code"] == "CF"
        assert path_error[0]["i_id"] == "I0249"

        # 2. Kiem tra duong di: Question -> ANSWERED_BY -> Answer
        path_answer = run_query(
            """
            MATCH (q:Question {question_id: 'Q0358'})-[:ANSWERED_BY]->(a:Answer)
            RETURN q.question_id AS q_id, a.answer_id AS a_id, a.cause AS cause, a.solution AS solution
            """,
            driver=driver,
        )
        assert len(path_answer) == 1
        assert "vệ sinh bộ lọc" in path_answer[0]["cause"]
        assert "thay bộ lọc" in path_answer[0]["solution"]

        # 3. Kiem tra duong di: Question -> SOURCED_FROM -> Source
        path_source = run_query(
            """
            MATCH (q:Question {question_id: 'Q0358'})-[:SOURCED_FROM]->(s:Source)
            RETURN q.question_id AS q_id, s.source_id AS s_id, s.url AS url
            """,
            driver=driver,
        )
        assert len(path_source) == 1
        assert path_source[0]["s_id"] == "S008"
        assert "samsung.com" in path_source[0]["url"]
    finally:
        driver.close()
