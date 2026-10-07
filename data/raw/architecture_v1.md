# Architecture
Status: Draft
Date: 2026-01-10

## Overview
The system is a monolithic FastAPI service. Retrieval uses keyword search only.

## Storage
All data is stored in PostgreSQL. Full-text search is used for retrieval of documents.
