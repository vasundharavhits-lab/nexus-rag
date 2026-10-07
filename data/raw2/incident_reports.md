# IT Operations Incident Reports and Troubleshooting Handbook

- **Status:** Approved
- **Date:** 2026-07-08
- **Author:** IT Operations

## INC-1042: Search Index Delay

New uploads appeared in the catalog but did not appear in search for up to 18 minutes. Existing indexed content remained available. Investigation found a backlog in the embedding queue after a batch import. Workers were temporarily increased, the queue was drained, and affected documents were re-indexed. Preventive actions include queue-age alerts and load testing.

## INC-1088: Wrong Policy Version Returned

A query about a current travel approval limit returned an older draft above the approved policy because the draft had more exact keyword matches. Ranking was updated to include approval status and effective date. The answer generator must cite the source version, and evaluation must test conflicting numeric values.

## INC-1120: PDF Extraction Failure

Some scanned PDFs produced nearly empty text because they contained page images instead of selectable text. A low-text warning and OCR-required status were added. The pipeline should not report full success when extraction is incomplete. OCR output should preserve page references where possible.

## INC-1156: Duplicate Chunks

Re-uploading an unchanged handbook created duplicate chunks. The previous process used file names as identifiers. The pipeline now computes content hashes. Tests should cover identical content under different names, changed content under the same name, and similar but non-identical paragraphs.

## Troubleshooting Checklist

For a missing document, confirm upload completion, meaningful extracted text, valid metadata, chunk creation, embedding completion, and index refresh. For irrelevant results, inspect query wording, chunk boundaries, metadata filters, keyword score, vector score, and reranking. For unsupported answers, check every citation. For slow answers, measure each stage independently.

## Detailed Test Scenarios

Scenario 01: Test a question about inc-1042: search index delay. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 02: Test a question about inc-1088: wrong policy version returned. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 03: Test a question about inc-1120: pdf extraction failure. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 04: Test a question about inc-1156: duplicate chunks. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

Scenario 05: Test a question about troubleshooting checklist. Ask one direct question and one paraphrased question. Confirm the returned passage contains the answer, the citation points to the right section, and no unsupported details are added.

## Questions for Retrieval Validation

Q1: What does the document say about inc-1042: search index delay?
Expected evidence: section 'INC-1042: Search Index Delay'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q2: What does the document say about inc-1088: wrong policy version returned?
Expected evidence: section 'INC-1088: Wrong Policy Version Returned'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q3: What does the document say about inc-1120: pdf extraction failure?
Expected evidence: section 'INC-1120: PDF Extraction Failure'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q4: What does the document say about inc-1156: duplicate chunks?
Expected evidence: section 'INC-1156: Duplicate Chunks'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
Q5: What does the document say about troubleshooting checklist?
Expected evidence: section 'Troubleshooting Checklist'.
Validation: check top-3 and top-5 retrieval, source title, section label, and answer support.
