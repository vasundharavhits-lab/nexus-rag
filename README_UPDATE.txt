NEXUS update: language-agnostic building blocks
================================================
Extract this zip into D:\nexus-rag (it adds 3 new files and replaces 2 - back those up first):

  NEW      app\grounding.py   sentence/size/answer helpers that work for every script (no word lists)
  NEW      app\rewrite.py     script-first question rewrite (romanized -> native script -> English)
  NEW      app\context.py     evidence compression + a prompt budget that adapts to the machine speed
  REPLACES app\ocr.py         OCR_LANGS=auto, confidence filter, and a fix: the old clean-up deleted ALL Hindi/Sanskrit lines
  REPLACES app\chunking.py    chunks Chinese/Japanese/Thai (no spaces) and Hindi (danda) correctly
  NEW      tests\...          31 tests            run:  python -m pytest tests\test_grounding.py tests\test_rewrite_context.py tests\test_chunking_scripts.py tests\test_ocr_clean.py -q
  NEW      try_rewrite.py     test the rewrite on YOUR model:  python try_rewrite.py "yudha kaha hua tha ?"

.env: set  OCR_LANGS=auto  (optional  OCR_MIN_CONF=45) to read scans in every installed language.
Existing documents are not changed. Re-upload a scan, or re-index, to benefit from the new OCR and chunking.
