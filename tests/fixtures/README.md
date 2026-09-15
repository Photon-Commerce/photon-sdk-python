# Test fixtures

Provenance (sandbox smoke test, 2026-08-13):

- `invoice_processing.json` — **real** sandbox response, captured live. The
  document-still-processing signal: HTTP 200 with this exact body (note
  `status` is `"success"` even while processing; only the `message`
  distinguishes the states).
- `invoice_ready.json` — ⚠️ **still synthetic**, hand-built from the response
  shapes in the official API docs (apidocs.photoncommerce.com). The live
  extraction had not finished at capture time (invoice processing can take up
  to 24h due to human verification). Replace with the real, redacted response
  when it is ready.

All values are placeholders; anything identifying in real captures (the
account email embedded in `photon_key`/`doc_path` paths) must be redacted to
`user@example.com` before committing.
