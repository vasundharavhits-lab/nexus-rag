# Architecture
Status: Approved
Date: 2026-03-20

## Overview
The system adds a reranking stage after hybrid retrieval. Ingestion runs asynchronously through Celery workers.

## Storage
PostgreSQL with pgvector remains the primary store. Redis is used for caching and job queues.
