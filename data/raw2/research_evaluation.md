# Retrieval Evaluation Dataset Design and Research Notes

- **Status:** Approved
- **Date:** 2026-08-20
- **Author:** Search Quality Group

## Evaluation Objectives

Measure evidence retrieval, correct version selection, permission enforcement, and answer grounding. Keep evaluations repeatable so changes to parsers, chunking, embeddings, hybrid weights, and reranking can be compared fairly.

## Question Categories

Include direct facts, paraphrases, multi-hop questions, version conflicts, unanswerable questions, exact-token questions, and permission tests. Permission tests must verify that restricted sources do not leak through titles, snippets, citations, or generated answers.

## Metrics

Recall@K measures whether a relevant source appears within the first K results. Mean reciprocal rank rewards placing the first relevant result near the top. nDCG accounts for graded relevance. Citation precision checks whether cited sources support claims. Citation coverage checks whether material claims have evidence. Report median and high-percentile latency.

## Example Test Cases

Q1: Which component handles background ingestion? Expected answer: Celery workers handle longer ingestion and re-indexing jobs. Q2: What should happen when a scanned PDF yields little text? Expected answer: flag low text and mark OCR as required. Q3: Should a draft override an approved policy due to exact keyword match? Expected answer: no. Q4: Does reranking guarantee correctness? Expected answer: no, evidence must still be checked.

## Reporting

Record system version, dataset version, model version, chunking parameters, retrieval configuration, and timestamp. Categorize failures as parsing, metadata, retrieval miss, ranking, version selection, permission violation, unsupported generation, or latency issue.

## Detailed Test Scenarios

Scenario 01: Test a question about evaluation objectives. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 02: Test a question about question categories. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 03: Test a question about metrics. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 04: Test a question about example test cases. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 05: Test a question about reporting. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

## Questions for Retrieval Validation

Q1: What does the document say about evaluation objectives?
Expected evidence: section 'Evaluation Objectives'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q2: What does the document say about question categories?
Expected evidence: section 'Question Categories'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q3: What does the document say about metrics?
Expected evidence: section 'Metrics'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q4: What does the document say about example test cases?
Expected evidence: section 'Example Test Cases'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q5: What does the document say about reporting?
Expected evidence: section 'Reporting'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
