import json
import sys
sys.stdout.reconfigure(encoding="utf-8")

from rag_chatbot.retrieval import search_hybrid
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver

col = get_or_create_collection()
drv = get_neo4j_driver()

query = "Máy giặt không xả nước phải làm sao?"
docs = search_hybrid(query, k=5, chroma_collection=col, neo4j_driver=drv, use_reranking=True, rerank_mode="fixed")
print("Top-5 for Q0535 query:")
for idx, d in enumerate(docs, 1):
    qid = d["question_id"]
    qtext = d["question"]
    score = d.get("rerank_score")
    ans = d.get("answer", "")[:80]
    print(f"[{idx}] {qid}: {qtext} (score={score})")
    print(f"     Answer: {ans}...")
