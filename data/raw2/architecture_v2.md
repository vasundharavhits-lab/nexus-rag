Title: Knowledge Intelligence System — Approved Architecture
Status: Approved
Date: 2026-02-15
Author: Platform Engineering

# Overview
This approved architecture describes a document-grounded knowledge intelligence system for teams that need reliable answers from changing internal documentation.

## Architecture
The system uses FastAPI for API requests, a separate ingestion worker for document processing, PostgreSQL for metadata and full-text search, and pgvector for embedding-based retrieval.

## Ingestion Pipeline
1. Detect the file type.
2. Extract text and metadata, including title, author, date, and status when available.
3. Split the text into overlapping chunks.
4. Create embeddings for each chunk.
5. Store chunks, metadata, and vectors in PostgreSQL.

## Retrieval
The retrieval layer combines keyword search and vector similarity. Hybrid results are merged so exact terminology and semantically related passages can both be found.

## Access and Traceability
Answers should cite the source document and relevant section. Draft documents should be distinguished from approved documents, and the system should prefer approved material when versions conflict.

## Test Questions
- Which database technologies are used?
- Why does the system use both keyword and vector retrieval?
- How should conflicting draft and approved documents be handled?
