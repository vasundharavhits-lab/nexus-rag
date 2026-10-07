# Architecture
Status: Approved
Date: 2026-02-15

## Overview
The system is a FastAPI service with a separate ingestion worker. Retrieval combines keyword and vector search.

## Storage
PostgreSQL stores metadata and full-text indexes. The pgvector extension stores embeddings for semantic retrieval.
