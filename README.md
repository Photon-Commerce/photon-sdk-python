<p align="center">
  <img src="https://images.squarespace-cdn.com/content/v1/607861b10c0e3b4816f56581/3eea3ca7-58ca-402d-9edf-b8e9e72eca3c/lightning.png?format=300w" alt="Photon Commerce" width="120">
</p>

<h1 align="center">Photon SDK for Python</h1>

<p align="center">
  The official Python SDK for <a href="https://www.photoncommerce.com">Photon Commerce</a> — extract structured data from invoices, receipts, and financial documents.
</p>

<p align="center">
  <a href="https://pypi.org/project/photon-sdk/"><img src="https://img.shields.io/pypi/v/photon-sdk?style=flat-square" alt="PyPI"></a>
  <a href="https://www.photoncommerce.com"><img src="https://img.shields.io/badge/SOC%202-Compliant-2ea44f?style=flat-square" alt="SOC 2"></a>
  <a href="https://www.photoncommerce.com"><img src="https://img.shields.io/badge/GDPR-Attested-2ea44f?style=flat-square" alt="GDPR"></a>
  <a href="https://www.photoncommerce.com/pricing"><img src="https://img.shields.io/badge/Accuracy-99%25%2B-2ea44f?style=flat-square" alt="Accuracy"></a>
  <a href="https://www.photoncommerce.com/platform"><img src="https://img.shields.io/badge/Languages-25%2B-2ea44f?style=flat-square" alt="Languages"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
</p>

<p align="center">
  <a href="https://www.photoncommerce.com">Website</a> ·
  <a href="https://apidocs.photoncommerce.com">API Docs</a> ·
  <a href="https://www.photoncommerce.com/pricing">Pricing</a> ·
  <a href="https://app.photoncommerce.com">Free Trial</a>
</p>

---

## Overview

Photon Commerce extracts standardized data from documents (PDFs, images, Word, HTML, and emails) with **99%+ accuracy**, combining AI processing with human verification. Results come back as JSON with 100+ standardized fields across amounts, vendor, bill-to, metadata, line items, and payment details, in **25+ languages**.

This SDK wraps that API in a fully typed Python client: extract a document in a single call, read the result as typed attributes, and correct it in place.

## Installation

```bash
pip install photon-sdk
```

## Quick Start

```python
from photon import PhotonClient

client = PhotonClient(
    client_id="YOUR_CLIENT_ID",
    username="YOUR_USERNAME",
    api_key="YOUR_API_KEY",
    password="YOUR_PASSWORD",
    secret_key="YOUR_SECRET_KEY",
)

# Submit a document and wait for the extracted result
invoice = client.extract("invoice.pdf", doctype="invoice")

print(invoice["Vendor_Name"])  # Acme Supplies
print(invoice["Invoice_Number"])  # INV-2024-00842
print(invoice["Total"])  # 4750.00
print(invoice["Currency_Code"])  # USD
```

Get **free sandbox credentials** (20 complimentary extractions, no payment info required) at [app.photoncommerce.com](https://app.photoncommerce.com).

## Extracted Fields

| Category | Fields |
|----------|--------|
| **Amounts** | Balance due, total, subtotal, tax, discounts, currency |
| **Vendor** | Name, address, phone, email, tax ID |
| **Bill To** | Name, address, phone, email, tax ID |
| **Metadata** | Invoice number, date, due date, PO number |
| **Line Items** | Description, quantity, unit price, amount, SKU, GL code |
| **Payment** | Payment terms, bank details, IBAN, routing number |

## Usage

### Credentials

Pass the five credentials to `PhotonClient`, or set them as environment variables and use `PhotonClient.from_env()`:

```bash
export PHOTON_CLIENT_ID=...
export PHOTON_USERNAME=...      # your account email
export PHOTON_API_KEY=...
export PHOTON_PASSWORD=...
export PHOTON_SECRET_KEY=...
export PHOTON_ENVIRONMENT=sandbox   # or "production"
```

```python
from photon import PhotonClient

with PhotonClient.from_env() as client:
    ...
```

### Extract a document

`extract()` uploads the document and polls until the result is ready:

```python
invoice = client.extract("invoice.pdf", doctype="invoice", timeout=600)

invoice.vendor_name  # "Acme Supplies Ltd"
invoice.total  # Decimal("1397.50")
invoice.due_date  # datetime.date(2026, 11, 18)
for line in invoice.line_items:
    print(line.line, line.description, line.qty, line.amount)

invoice["Vendor_Name"]  # the API's own field names work too
invoice.raw  # the untouched payload
invoice.to_dict()  # typed fields as a dict; to_json() for JSON
```

A document can be a path, an open binary file, raw `bytes`, or a public URL (`client.extract(url="https://...")`).

Invoices and receipts (`doctype="invoice"` / `"receipt-expense"`) return a typed `InvoiceDocument`: amounts are exact `Decimal`s, ISO dates are `datetime.date`, and anything absent reads as `None`. Every other doctype (`check`, `remittance`, `bol`, `statement`, ...) returns a `RawDocument`, read by the API's field names: `doc["payerName"]`.

### Submit now, retrieve later

Processing can take from seconds (AI extraction) to hours (human verification), so you can also split the two steps:

```python
submission = client.submit("invoice.pdf", doctype="invoice", webhook_url="https://example.com/hook")
# ... later, or once the webhook fires:
invoice = client.retrieve(submission.photon_key, doctype="invoice")
```

`retrieve()` raises `NotReadyError` while the document is still processing. `extract(..., timeout=None)` submits without waiting and returns the `Submission`.

### Correct extracted data

Updates use the **API's field names**, exactly as the result spells them:

```python
key = invoice.photon_key

client.update_fields(key, {"Vendor_Name": "Acme Supplies Ltd", "Total": "1397.50"})
client.update_line_item(key, 2, {"QTY": 3, "Amount": "225.00"})
client.add_line_item(key, {"Line": 3, "Description": "Shipping", "QTY": 1, "Amount": "25.00"})
client.delete_line_item(key, 3)
```

### Errors

Every error raised by the SDK is a `PhotonError` carrying `status_code`, `message` and the response `body`:

| Exception | When |
|-----------|------|
| `AuthenticationError` | Credentials rejected (401) |
| `QuotaExceededError` | The account's allowance is used up |
| `InvalidRequestError` | The request or file was rejected (bad file, unknown key, invalid line item, ...) |
| `NotReadyError` | The document is still processing |
| `ExtractionTimeoutError` | `extract()` gave up waiting; retrieve later by `photon_key` |
| `PhotonConnectionError` | The API could not be reached |
| `APIError` | Any other unsuccessful response |
| `ConfigurationError` | Missing credentials or an unknown environment |

Invalid arguments raise `ValueError` before anything is sent.

### Retries

Server errors (5xx) and network failures are retried up to `max_retries` times (default 3) with exponential backoff. Requests that could take effect twice — submitting a document, adding or deleting a line item — are only retried when the connection itself failed. 4xx errors are never retried.

```python
client = PhotonClient.from_env(max_retries=5, backoff_factor=1.0, timeout=60)
```

Retries are logged at `DEBUG` on the `photon` logger; credentials and document keys are never logged.

## Processing Times

| Account Type | Turnaround |
|--------------|------------|
| Trial | Up to 24 hours (human verification included) |
| Production | 5 minutes to 24 hours (human verification included) |
| AI Extraction | Seconds (contact [support@photoncommerce.com](mailto:support@photoncommerce.com) to activate) |

## Authentication

The SDK sends your credentials as four headers on every request. Free sandbox credentials are available at no cost.

```
CLIENT-ID:     your-client-id
AUTHORIZATION: apikey your-username:your-api-key
PASSWORD:      your-password
SECRET-KEY:    your-secret-key
```

## Sample Response

```json
{
  "data": {
    "Total": 22001.38,
    "Balance_Due": 22001.38,
    "Subtotal": 22001.38,
    "Tax": 0,
    "Currency_Code": "USD",
    "Document_Type": "Invoice",
    "Invoice_Number": "2/02/2021",
    "Date": "2021-02-03",
    "Due_Date": "2021-02-10",
    "Vendor_Name": "TUNEGO, INC.",
    "Vendor_Address": "32505 Anthem Village Drive, Suite E283, Henderson, NV 89052",
    "Bill_To_Name": "MOBILE REALITY sp. z o. o",
    "Bill_To_Address": "03-901 Warszawa, Poland",
    "Line_Items": [
      {
        "Line": 1,
        "Description": "React.JS frontend development",
        "QTY": 160,
        "Unit": "hrs",
        "Price": 42.5,
        "Amount": 6800
      }
    ],
    "Pages": 1,
    "photon_key": "data/johndoe@abc.com/2026-01-05/23-40-12_TuneGO.json"
  },
  "message": "success",
  "status": "success"
}
```

## Development

```bash
git clone https://github.com/Photon-Commerce/photon-sdk-python.git
cd photon-sdk-python
pip install -e ".[dev]"

pytest --cov          # run tests with coverage
ruff check .          # lint
ruff format --check . # formatting
mypy                  # type-check
```

## Releasing

Bump `__version__` in `src/photon/_version.py`, add the version to `CHANGELOG.md`, merge to `main`, then push a matching tag:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

The release workflow builds the package, installs it in a clean environment, publishes it to PyPI and creates the GitHub release.

## Links

- **Website:** https://www.photoncommerce.com
- **API Docs:** https://apidocs.photoncommerce.com
- **Pricing:** https://www.photoncommerce.com/pricing
- **Free Trial:** https://app.photoncommerce.com

## License

[MIT](LICENSE)
