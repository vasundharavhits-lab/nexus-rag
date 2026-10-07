# Incident Log
Author: Ops Team
Date: 2026-04-02

## ERR-4471 Upload timeout
Error ERR-4471 occurs when the ingestion worker waits longer than 30 seconds for the parser. The fix is to raise PARSER_TIMEOUT_S in the worker settings.

## ERR-5023 Index lock
Error ERR-5023 means the nightly reindex job could not acquire the chunk table lock. Retry after the lock_timeout_ms window expires.

## ERR-6180 Embedding mismatch
Error ERR-6180 appears when stored vectors were produced by a different model than the query encoder. Rebuild the index with build_index.