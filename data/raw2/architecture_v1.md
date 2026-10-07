Title: Knowledge Intelligence System — Architecture Draft
Status: Draft
Date: 2026-01-10
Author: System Test Team

# Overview
This draft describes a simple knowledge intelligence system for searching internal documents.

## Architecture
The first version uses a monolithic FastAPI application. Documents are parsed, split into chunks, and indexed using keyword search and PostgreSQL full-text search.

## Ingestion
Supported input formats are Markdown, DOCX, and PDF. The ingestion process extracts text, records metadata, and creates chunks for retrieval.

## Retrieval
A user question is matched against indexed chunks using keyword relevance. The system returns the most relevant passages with document titles and section headings.

## Limitations
This draft does not include vector search, reranking, or background workers.

## Test Questions
- Which search methods are used in this draft?
- Which file formats are supported?
- What features are not included yet?
