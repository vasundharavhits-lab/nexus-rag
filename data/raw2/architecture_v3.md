Title: Knowledge Intelligence System — Retrieval Enhancements
Status: Approved
Date: 2026-03-20
Author: Search Quality Group

# Overview
This document describes retrieval improvements introduced after the approved architecture in February 2026.

## Reranking
After hybrid retrieval produces an initial candidate list, a reranker evaluates the question and each candidate passage together. The system then orders the candidates by estimated relevance before generating an answer.

## Background Processing
Celery workers handle slower ingestion tasks so API requests can remain responsive. Failed tasks should be logged and retried according to configured limits.

## Data Storage
PostgreSQL stores document metadata and extracted text. pgvector stores chunk embeddings. Task status and error details should be recorded for monitoring.

## Evaluation
Measure retrieval quality using a fixed set of test questions and expected source documents. Track whether the expected document appears in the top 3 and top 5 results. Also record answer grounding and response latency.

## Known Risks
Poor chunk boundaries can split important context. Outdated metadata can cause the wrong version to be retrieved. Reranking can improve ordering but does not guarantee that a generated answer is correct.

## Test Questions
- What does reranking do?
- Why are Celery workers used?
- Which retrieval quality metrics are suggested?
- Does reranking guarantee a correct answer?
