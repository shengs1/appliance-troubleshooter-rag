# RAG Chatbot - Project Rules

## Project type

This is a beginner academic project.

The developer is building their first RAG chatbot and must be able to understand and explain the code during an oral examination.

Therefore, prioritize:

1. Simplicity
2. Readability
3. Explainability
4. Correctness
5. Testability

Do not over-engineer the project.

## Coding style

Prefer:

- simple Python
- small functions
- descriptive names
- clear control flow
- straightforward modules
- comments for important logic
- easy-to-follow code

Avoid unless clearly necessary:

- complex design patterns
- factories
- unnecessary abstractions
- complicated dependency injection
- repository patterns
- microservices
- unnecessary databases
- unnecessary dependencies
- premature optimization

If a complex technique is necessary, explain:
- why it is needed
- what problem it solves
- how it works

## Main technology

The project uses:

- Python
- LangChain
- ChromaDB
- Neo4j
- FastAPI
- local LLM
- pytest

Do not add additional technologies without a clear reason.

## ChromaDB

Use ChromaDB for:

- document embeddings
- semantic similarity search
- retrieving relevant text chunks

Keep ChromaDB usage simple and easy to understand.

## Neo4j

Use Neo4j for structured relationships such as:

Device
→ Model
→ ErrorCode
→ Symptom
→ Cause
→ RepairAction

Use simple, parameterized Cypher queries.

Do not create unnecessarily complicated graph structures.

## LangChain

Use LangChain mainly to connect:

retrieval
→ context
→ prompt
→ LLM

Do not introduce complicated agent systems unless required.

## FastAPI

FastAPI is the API layer.

Keep routes simple.

Prefer:

route
→ function/service
→ result

Do not put the entire RAG implementation inside route handlers.

## RAG principles

The system should retrieve information before generating an answer.

Use:

ChromaDB
→ semantic retrieval

Neo4j
→ relationship/structured retrieval

Then combine the useful results before sending them to the LLM.

The model must not invent error codes, causes, or repair procedures when the retrieved evidence does not support them.

## Data safety

Never expose or commit:

- passwords
- API keys
- tokens
- private keys
- database credentials
- .env secrets

Never delete real knowledge data or databases without explicit instruction.

## Git

Before large changes:

- inspect git status
- understand existing changes

After changes:

- inspect git diff
- run relevant tests
- check that unrelated files were not modified

Never reset or discard user changes without explicit instruction.

## Testing

After meaningful changes:

- run relevant tests
- inspect failures
- fix problems before declaring completion

Do not claim that tests passed unless they were actually run.

## Development workflow

For a task:

1. Inspect
2. Explain the plan
3. Implement
4. Test
5. Review the changes
6. Report the result

For large architectural changes, do not immediately write code.

## Student-friendly requirement

Every implementation should be understandable by a beginner who knows basic Python.

Prefer code that can be explained clearly during an oral examination over code that is unnecessarily sophisticated.