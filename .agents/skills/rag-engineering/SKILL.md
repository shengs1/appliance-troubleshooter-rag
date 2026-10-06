---

name: rag-engineering

description: Designs, implements, debugs, tests, and reviews the project's RAG pipeline using LangChain, ChromaDB, Neo4j, FastAPI, and local LLMs. Use for retrieval, ingestion, graph, vector database, RAG, API, evaluation, and architecture tasks.

---



\# RAG Engineering Skill



\## Purpose



Use this skill whenever the task involves the RAG architecture, retrieval system, knowledge ingestion, ChromaDB, Neo4j, LangChain, FastAPI integration, evaluation, or debugging.



\## Required workflow



For any non-trivial task:



\### Phase 1 - Understand



Inspect:



\- repository structure

\- relevant modules

\- configuration

\- dependencies

\- tests

\- database integration

\- current API boundaries



Search the repository before introducing new code.



\### Phase 2 - Plan



Create a concise implementation plan.



The plan must identify:



\- files to modify

\- files to create

\- dependencies

\- database/schema impact

\- API impact

\- testing strategy

\- risks



For architecture-changing tasks, do not immediately modify files.



\### Phase 3 - Implement



Implement incrementally.



Rules:



\- preserve working behavior

\- avoid unrelated refactors

\- reuse existing abstractions

\- keep database access isolated

\- keep retrieval logic testable

\- keep FastAPI routes thin



\### Phase 4 - Verify



Run:



\- targeted tests

\- relevant integration tests

\- lint/type checks if configured

\- application startup/import checks where useful



Inspect:



\- git diff

\- changed files

\- test output



\### Phase 5 - Review



Before finishing, answer:



1\. Did the implementation satisfy the requested behavior?

2\. Did it break an existing interface?

3\. Are database changes safe?

4\. Are secrets protected?

5\. Are error cases handled?

6\. Are tests sufficient?

7\. Did unrelated files change?



\## Hybrid retrieval strategy



When both ChromaDB and Neo4j are involved:



1\. Determine what information is semantic.

2\. Determine what information is relational.

3\. Retrieve semantic candidates with ChromaDB.

4\. Retrieve graph relationships with Neo4j.

5\. Merge/rerank results using explicit logic.

6\. Pass only useful grounded context to the generation model.



Do not blindly duplicate every document in both stores.



\## Ingestion pipeline



A typical ingestion pipeline should be considered in this order:



source

â†’ cleaning

â†’ normalization

â†’ metadata extraction

â†’ chunking

â†’ embeddings

â†’ ChromaDB

â†’ entity/relationship extraction

â†’ Neo4j



Do not change the pipeline order without understanding downstream dependencies.



\## Retrieval debugging



When retrieval quality is poor, inspect separately:



1\. source data

2\. cleaning

3\. chunking

4\. metadata

5\. embeddings

6\. ChromaDB retrieval

7\. Neo4j retrieval

8\. merging/reranking

9\. prompt construction

10\. final generation



Do not immediately blame the LLM.



\## Neo4j rules



Before modifying graph logic:



\- inspect current labels

\- inspect relationship types

\- inspect property names

\- inspect indexes/constraints

\- inspect existing Cypher queries



Prefer parameterized Cypher.



Avoid destructive queries.



\## ChromaDB rules



Before modifying vector retrieval:



\- inspect collection configuration

\- inspect embedding model

\- inspect distance/score behavior

\- inspect metadata

\- inspect top-k behavior



Ensure embedding model compatibility when changing indexed data.



\## FastAPI rules



Keep routes thin.



Prefer:



route

â†’ service

â†’ retrieval

â†’ generation



rather than placing complex RAG logic inside route handlers.



Validate inputs.



Return structured errors.



Avoid leaking internal stack traces or secrets.



\## Testing strategy



Core tests should cover:



\- chunking

\- metadata extraction

\- embedding/indexing integration

\- vector retrieval

\- graph retrieval

\- hybrid retrieval

\- prompt/context construction

\- API behavior

\- failure cases



When database integration is required, explicitly distinguish unit tests from integration tests.



\## Completion criteria



Do not declare a task complete until:



\- implementation exists

\- relevant tests run

\- failures are understood

\- git diff was inspected

\- no unrelated changes were introduced



Final response should summarize:



\- what changed

\- why

\- tests run

\- remaining limitations




