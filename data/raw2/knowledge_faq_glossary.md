# Knowledge Intelligence FAQ and Retrieval Glossary

- **Status:** Approved
- **Date:** 2026-09-01
- **Author:** Knowledge Enablement

## Document ingestion

The ingestion service validates files, extracts text, records metadata, creates chunks, and sends content to storage.

## Chunk overlap

Chunk overlap preserves context near boundaries, but excessive overlap increases storage and can produce repetitive results.

## Vector search

Vector search compares embeddings to find passages with related meaning even when exact query words are absent.

## Keyword search

Keyword search is effective for exact terms, identifiers, product names, error codes, and uncommon phrases.

## Hybrid retrieval

Hybrid retrieval combines lexical matching and semantic similarity to improve coverage across different query styles.

## Reranking

Reranking reorders an initial candidate list using a focused relevance model; it does not guarantee a correct answer.

## Approved versions

Approved documents should normally take precedence for current operational questions, while historical search remains available to authorized users.

## Citations

Citations should identify the source document and section and support the claims made in the answer.

## Access control

Permissions must be applied before protected text, titles, snippets, or citations are returned.

## Scanned PDFs

Scanned PDFs may require OCR because their pages contain images rather than selectable text.

## Duplicate detection

Content hashes can identify unchanged files even when file names differ; near-duplicate detection must preserve traceability.

## Evaluation

A stable evaluation set helps compare retrieval changes and identify regressions in relevance, grounding, version handling, and latency.

## Monitoring

Monitoring should track queue age, parser errors, index freshness, latency by stage, and repeated retrieval failures.

## Unanswerable questions

When sources do not contain the requested information, the system should state that evidence is insufficient rather than inventing a value.

## Prompt injection in documents

Retrieved document text is untrusted data and must not override application instructions or access-control rules.

## Practice Query Set 01

Question A: Explain document ingestion in simple language.
Question B: Which system behavior is associated with document ingestion?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Document ingestion'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 02

Question A: Explain chunk overlap in simple language.
Question B: Which system behavior is associated with chunk overlap?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Chunk overlap'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 03

Question A: Explain vector search in simple language.
Question B: Which system behavior is associated with vector search?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Vector search'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 04

Question A: Explain keyword search in simple language.
Question B: Which system behavior is associated with keyword search?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Keyword search'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 05

Question A: Explain hybrid retrieval in simple language.
Question B: Which system behavior is associated with hybrid retrieval?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Hybrid retrieval'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 06

Question A: Explain reranking in simple language.
Question B: Which system behavior is associated with reranking?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Reranking'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 07

Question A: Explain approved versions in simple language.
Question B: Which system behavior is associated with approved versions?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Approved versions'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 08

Question A: Explain citations in simple language.
Question B: Which system behavior is associated with citations?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Citations'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 09

Question A: Explain access control in simple language.
Question B: Which system behavior is associated with access control?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Access control'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 10

Question A: Explain scanned pdfs in simple language.
Question B: Which system behavior is associated with scanned pdfs?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Scanned PDFs'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 11

Question A: Explain duplicate detection in simple language.
Question B: Which system behavior is associated with duplicate detection?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Duplicate detection'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 12

Question A: Explain evaluation in simple language.
Question B: Which system behavior is associated with evaluation?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Evaluation'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 13

Question A: Explain monitoring in simple language.
Question B: Which system behavior is associated with monitoring?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Monitoring'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 14

Question A: Explain unanswerable questions in simple language.
Question B: Which system behavior is associated with unanswerable questions?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Unanswerable questions'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 15

Question A: Explain prompt injection in documents in simple language.
Question B: Which system behavior is associated with prompt injection in documents?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Prompt injection in documents'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 16

Question A: Explain practice query set 01 in simple language.
Question B: Which system behavior is associated with practice query set 01?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 01'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 17

Question A: Explain practice query set 02 in simple language.
Question B: Which system behavior is associated with practice query set 02?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 02'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 18

Question A: Explain practice query set 03 in simple language.
Question B: Which system behavior is associated with practice query set 03?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 03'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 19

Question A: Explain practice query set 04 in simple language.
Question B: Which system behavior is associated with practice query set 04?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 04'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 20

Question A: Explain practice query set 05 in simple language.
Question B: Which system behavior is associated with practice query set 05?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 05'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 21

Question A: Explain practice query set 06 in simple language.
Question B: Which system behavior is associated with practice query set 06?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 06'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 22

Question A: Explain practice query set 07 in simple language.
Question B: Which system behavior is associated with practice query set 07?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 07'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 23

Question A: Explain practice query set 08 in simple language.
Question B: Which system behavior is associated with practice query set 08?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 08'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 24

Question A: Explain practice query set 09 in simple language.
Question B: Which system behavior is associated with practice query set 09?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 09'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 25

Question A: Explain practice query set 10 in simple language.
Question B: Which system behavior is associated with practice query set 10?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 10'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 26

Question A: Explain practice query set 11 in simple language.
Question B: Which system behavior is associated with practice query set 11?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 11'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 27

Question A: Explain practice query set 12 in simple language.
Question B: Which system behavior is associated with practice query set 12?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 12'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 28

Question A: Explain practice query set 13 in simple language.
Question B: Which system behavior is associated with practice query set 13?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 13'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 29

Question A: Explain practice query set 14 in simple language.
Question B: Which system behavior is associated with practice query set 14?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 14'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.

## Practice Query Set 30

Question A: Explain practice query set 15 in simple language.
Question B: Which system behavior is associated with practice query set 15?
Question C: What evidence would confirm the answer?
Expected evidence: the main glossary entry titled 'Practice Query Set 15'.
Evaluation note: the system should retrieve the matching source for paraphrased wording and should not claim details absent from the source.
