# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-10-20

### Changed

- The package is now published to PyPI as **`photon-commerce`**
  (`pip install photon-commerce`). It was released as `photon-sdk` 0.1.0; that name
  is retired. The import name is unchanged: `from photon import PhotonClient`.

## [0.1.0] - 2026-10-19

First public release.

### Added

- `PhotonClient`, a synchronous, fully typed client configured from arguments or
  `PHOTON_*` environment variables (`PhotonClient.from_env()`), for the sandbox
  and production environments.
- `submit()` — upload a document (path, binary file, bytes) or submit a URL, with
  webhook, reference ID, subaccount and page-range options.
- `retrieve()` — fetch a result by `photon_key`; raises `NotReadyError` while it
  is still processing.
- `extract()` — submit and poll until the result is ready, with a configurable
  timeout; `timeout=None` returns the `Submission` for webhook flows.
- `InvoiceDocument` — typed results for invoices and receipt-expenses covering
  every documented field, with exact `Decimal` amounts, ISO dates as
  `datetime.date`, typed `line_items` and `tax_lines`, dict access by the API's
  field names, `.raw`, `to_dict()` and `to_json()`.
- `RawDocument` — dict-style access to results for every other doctype.
- Data correction: `update_fields()`, `update_line_item()`, `add_line_item()` and
  `delete_line_item()`.
- A typed exception hierarchy under `PhotonError`, classifying the API's
  body-reported failures (quota, invalid key, unsupported file, ...).
- Retries with exponential backoff and jitter for 5xx and network errors. Requests
  that could take effect twice are only retried when the connection failed.
- `DEBUG` logging of retries on the `photon` logger, never including credentials
  or document keys.

[0.1.1]: https://github.com/Photon-Commerce/photon-sdk-python/releases/tag/v0.1.1
[0.1.0]: https://github.com/Photon-Commerce/photon-sdk-python/releases/tag/v0.1.0
