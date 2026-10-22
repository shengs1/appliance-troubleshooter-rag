import sys
from rag_chatbot.retrieval import search_similar_documents, search_hybrid
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver

sys.stdout.reconfigure(encoding='utf-8')

col = get_or_create_collection()
driver = get_neo4j_driver()
q = 'Máy giặt không xả nước phải làm sao?'
res = search_hybrid(q, k=25, chroma_collection=col, neo4j_driver=driver, use_reranking=True, rerank_mode='fixed')
print(f"Total retrieved docs: {len(res)}")
found = False
for r, d in enumerate(res, 1):
    qid = d['question_id']
    score = d.get('rerank_score')
    dist = d.get('distance')
    qtext = d.get('question')
    if qid == 'Q0535':
        print(f"-> Q0535 FOUND at Rank {r}: score={score}, dist={dist}, text='{qtext}'")
        found = True
    elif r <= 10:
        print(f"   Rank {r}: ID={qid}, score={score}, dist={dist}, text='{qtext}'")

if not found:
    print("Q0535 was NOT found in top 25!")
