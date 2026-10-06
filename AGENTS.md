\# RAG Electronics Assistant - Engineering Rules



\## Project role



This repository implements a Vietnamese electronics troubleshooting chatbot.



The system uses Retrieval-Augmented Generation (RAG) to retrieve relevant troubleshooting knowledge and generate grounded answers.



\## Technology stack



Primary technologies:



\- Python

\- LangChain

\- ChromaDB

\- Neo4j

\- FastAPI

\- pytest

\- local/self-hosted LLM

\- Git



\## Architecture principles



\### ChromaDB



Use ChromaDB for:



\- semantic/vector retrieval

\- similarity search

\- embedding-based document retrieval



Do not use ChromaDB as the source of truth for graph relationships.



\### Neo4j



Use Neo4j for:



\- entities

\- relationships

\- device/component relationships

\- error-code relationships

\- symptom relationships

\- cause relationships

\- repair/action relationships

\- graph traversal



Do not duplicate graph logic unnecessarily in ChromaDB.



\### LangChain



LangChain is responsible for orchestration between:



\- document retrieval

\- graph retrieval

\- prompt construction

\- LLM generation



Keep retrieval and generation components modular and testable.



\### FastAPI



FastAPI is the application/API boundary.



Do not place large RAG implementation details directly inside route handlers.



Use services/modules for business logic.



\## Coding rules



Before changing code:



1\. Inspect the relevant files.

2\. Understand the existing architecture.

3\. Search for existing implementations before creating new ones.

4\. Identify dependencies and compatibility constraints.

5\. Prefer the smallest safe change.



Do not:



\- rewrite unrelated modules

\- replace working architecture without a reason

\- delete existing functionality without explicit justification

\- silently change public API contracts

\- introduce unnecessary dependencies

\- hard-code credentials

\- expose secrets in logs



\## Environment and secrets



Never commit:



\- .env

\- API keys

\- passwords

\- OAuth credentials

\- database credentials

\- tokens

\- private keys



Environment variables must be used for secrets.



\## Database safety



Never:



\- drop Neo4j databases without explicit instruction

\- delete Chroma collections without explicit instruction

\- perform destructive migrations silently

\- modify production-like data during tests



Before schema changes:



1\. Inspect current schema.

2\. Identify dependencies.

3\. Plan migration.

4\. Update tests.



\## Testing



After meaningful code changes:



1\. Run targeted tests.

2\. Run broader tests when appropriate.

3\. Inspect failures.

4\. Fix regressions before declaring completion.



Do not claim tests passed without actually running them.



\## Git



Before a large change:



\- inspect git status

\- inspect relevant diff

\- create a logical checkpoint when appropriate



After implementation:



\- inspect git diff

\- verify no unrelated files changed

\- summarize modified files

\- summarize tests



Never reset or discard user changes unless explicitly instructed.



\## RAG correctness



Generated answers should be grounded in retrieved evidence.



Avoid hallucinating:



\- device specifications

\- error-code meanings

\- repair procedures

\- component relationships



When retrieval confidence is insufficient, the system should prefer a transparent uncertainty response over inventing technical details.



\## Performance



Avoid:



\- loading the entire knowledge base into memory

\- unnecessary repeated embedding

\- unnecessary Neo4j round trips

\- redundant vector searches

\- rebuilding indexes unnecessarily



Prefer batching, caching, and targeted retrieval where appropriate.



\## Maintainability



Prefer:



\- typed Python

\- clear module boundaries

\- dependency injection where useful

\- configuration through environment/settings

\- unit tests for core retrieval logic

\- integration tests for database-backed flows

\- descriptive names

\- small functions with single responsibilities

