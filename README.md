<p align="center">
  <img src="https://images.squarespace-cdn.com/content/v1/607861b10c0e3b4816f56581/3eea3ca7-58ca-402d-9edf-b8e9e72eca3c/lightning.png?format=300w" alt="Photon Commerce" width="120">
</p>

<h1 align="center">Photon SDK for Python</h1>

<p align="center">
  The official Python SDK for <a href="https://www.photoncommerce.com">Photon Commerce</a> — extract structured data from invoices, receipts, and financial documents.
</p>

<p align="center">
  <a href="https://www.photoncommerce.com"><img src="https://img.shields.io/badge/SOC%202-Compliant-2ea44f?style=flat-square" alt="SOC 2"></a>
  <a href="https://www.photoncommerce.com"><img src="https://img.shields.io/badge/GDPR-Attested-2ea44f?style=flat-square" alt="GDPR"></a>
  <a href="https://www.photoncommerce.com/pricing"><img src="https://img.shields.io/badge/Accuracy-99%25%2B-2ea44f?style=flat-square" alt="Accuracy"></a>
  <a href="https://www.photoncommerce.com/platform"><img src="https://img.shields.io/badge/Languages-25%2B-2ea44f?style=flat-square" alt="Languages"></a>
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.9+">
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

This SDK will wrap that API in an ergonomic, fully typed Python client so you can extract a document in a single call.

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

print(invoice["Vendor_Name"])    # Acme Supplies
print(invoice["Invoice_Number"]) # INV-2024-00842
print(invoice["Total"])          # 4750.00
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

## How It Works

Extraction is a two-step flow. Until the SDK ships, here is the raw API workflow using [`requests`](https://pypi.org/project/requests/) — this works today.

```python
import requests

HEADERS = {
    "CLIENT-ID":     "YOUR_CLIENT_ID",
    "AUTHORIZATION": "apikey YOUR_USERNAME:YOUR_API_KEY",
    "PASSWORD":      "YOUR_PASSWORD",
    "SECRET-KEY":    "YOUR_SECRET_KEY",
}
```

### Submission

`POST https://sandbox-api.photoncommerce.com/api/pro?doctype=invoice`

```python
response = requests.post(
    "https://sandbox-api.photoncommerce.com/api/pro",
    headers=HEADERS,
    params={"doctype": "invoice"},
    files={"pdf": open("invoice.pdf", "rb")},
)
photon_key = response.json()["photon_key"]
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `doctype` | string | Document type, e.g. `invoice` |
| `url` | string | URL of a publicly accessible document (alternative to file upload) |
| `webhook_url` | string | Receive a callback when extraction is complete |
| `auth_token` | string | Token to verify the webhook callback |
| `ID` | string | Your own reference ID for this submission |
| `subaccount` | string | Route to a subaccount |
| `page_start` | integer | First page to process (multi-page PDFs) |
| `page_end` | integer | Last page to process (multi-page PDFs) |

### Retrieval

`GET https://sandbox-api.photoncommerce.com/api/v4/json?photon_key=YOUR_PHOTON_KEY`

```python
result = requests.get(
    "https://sandbox-api.photoncommerce.com/api/v4/json",
    headers=HEADERS,
    params={"photon_key": photon_key},
).json()["data"]

print(result["Vendor_Name"], result["Total"], result["Currency_Code"])
```

## Processing Times

| Account Type | Turnaround |
|--------------|------------|
| Trial | Up to 24 hours (human verification included) |
| Production | 5 minutes to 24 hours (human verification included) |
| AI Extraction | Seconds (contact [support@photoncommerce.com](mailto:support@photoncommerce.com) to activate) |

## Authentication

Every request requires four headers. Free sandbox credentials are available at no cost.

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

pytest        # run tests
ruff check .  # lint
mypy          # type-check
```

## Links

- **Website:** https://www.photoncommerce.com
- **API Docs:** https://apidocs.photoncommerce.com
- **Pricing:** https://www.photoncommerce.com/pricing
- **Free Trial:** https://app.photoncommerce.com

## License

[MIT](LICENSE)
