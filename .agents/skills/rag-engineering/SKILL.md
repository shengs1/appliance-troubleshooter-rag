---
name: rag-engineering
description: Build and maintain a simple, understandable Vietnamese electronics troubleshooting RAG chatbot using Python, LangChain, ChromaDB, Neo4j, FastAPI, and a local LLM.
---

# RAG Engineering Skill

## Purpose

Use this skill for:

- RAG development
- document ingestion
- ChromaDB
- Neo4j
- LangChain
- retrieval
- local LLM
- FastAPI
- testing
- debugging

This is a beginner academic project.

The code must remain simple and easy to explain.

## Required workflow

### Phase 1 - Understand

Before changing code:

1. Inspect the relevant files.
2. Understand the current implementation.
3. Search for existing code before creating new code.
4. Identify dependencies.
5. Identify possible side effects.

Do not assume a component exists without checking it.

### Phase 2 - Plan

Create a simple implementation plan.

The plan should state:

- what will change
- what files are involved
- why the change is needed
- how it will be tested

Do not create unnecessary architecture.

### Phase 3 - Implement

Write straightforward code.

Prefer:

- simple functions
- simple classes when useful
- explicit logic
- readable variable names
- minimal dependencies

Avoid unnecessary:

- factories
- abstract base classes
- complex dependency injection
- repository layers
- complicated design patterns
- excessive abstraction

### Phase 4 - Verify

After implementation:

1. Run relevant tests.
2. Verify imports.
3. Check application behavior.
4. Inspect git diff.
5. Check that unrelated files were not changed.

### Phase 5 - Review

Before declaring completion:

- Does the code solve the requested problem?
- Is the code easy to understand?
- Is error handling reasonable?
- Are secrets protected?
- Are tests present where appropriate?
- Were unrelated changes avoided?

## ChromaDB workflow

Keep the basic process:

documents
→ cleaning
→ chunking
→ embeddings
→ ChromaDB
→ similarity search

Do not add complicated vector infrastructure unless necessary.

## Neo4j workflow

Keep the graph understandable.

Example:

Device
→ HAS_MODEL
→ Model
→ HAS_ERROR
→ ErrorCode
→ HAS_SYMPTOM
→ Symptom
→ CAUSED_BY
→ Cause
→ FIXED_BY
→ RepairAction

Use parameterized Cypher.

Avoid destructive queries.

## Hybrid retrieval

Start simple:

User question
→ ChromaDB search
→ Neo4j search
→ combine useful results
→ create context
→ send to LLM

Do not add RRF, reranking, score normalization, or other advanced ranking methods unless there is a demonstrated need.

If a more advanced method is introduced, explain why.

## Local LLM

Use one clear local LLM interface.

Do not introduce multiple model providers or complicated fallback systems unless required by the project.

## FastAPI

Keep API routes thin.

Prefer:

request
→ simple function/service
→ RAG
→ response

Use Pydantic models for request/response validation.

## Data handling

Do not invent real electronics troubleshooting data.

Sample data may only be used when clearly labeled as sample/test data.

Real knowledge should come from the project's actual dataset.

## Testing

Test important logic separately:

- cleaning
- chunking
- ChromaDB retrieval
- Neo4j retrieval
- hybrid retrieval
- RAG prompt construction
- API behavior

Keep tests simple and understandable.

## Student project rule

The developer must be able to explain every important part of the implementation during an oral examination.

Therefore:

- readability is more important than optimization
- simplicity is more important than abstraction
- explicit code is preferred over clever code
- avoid unnecessary libraries
- avoid unnecessary architecture

When adding a complex component, explain:

1. What it does
2. Why it is needed
3. How it works
4. Why the simpler approach is not enough