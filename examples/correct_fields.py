"""Submit an invoice, then correct the extracted data.

Usage:
    export PHOTON_CLIENT_ID=... PHOTON_USERNAME=... PHOTON_API_KEY=... \
        PHOTON_PASSWORD=... PHOTON_SECRET_KEY=...
    python examples/correct_fields.py path/to/invoice.pdf
"""

from __future__ import annotations

import sys

from photon import InvoiceDocument, PhotonClient


def main(path: str) -> None:
    with PhotonClient.from_env() as client:
        invoice = client.extract(path, doctype="invoice", timeout=900)
        assert isinstance(invoice, InvoiceDocument)
        key = invoice.photon_key
        assert key is not None

        # Updates use the API's own field names.
        client.update_fields(key, {"Payment_Terms": "Net 45"})

        next_line = max((line.line or 0 for line in invoice.line_items), default=0) + 1
        client.add_line_item(
            key, {"Line": next_line, "Description": "Freight", "QTY": 1, "Amount": "25.00"}
        )
        client.update_line_item(key, next_line, {"Amount": "30.00"})
        client.delete_line_item(key, next_line)

        corrected = client.retrieve(key, doctype="invoice")
        print("Payment terms now:", corrected["Payment_Terms"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
