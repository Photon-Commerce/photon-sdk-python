"""Extract an invoice and print its key fields.

Usage:
    export PHOTON_CLIENT_ID=... PHOTON_USERNAME=... PHOTON_API_KEY=... \
        PHOTON_PASSWORD=... PHOTON_SECRET_KEY=...
    python examples/quickstart.py path/to/invoice.pdf
"""

from __future__ import annotations

import sys

from photon import ExtractionTimeoutError, InvoiceDocument, PhotonClient


def main(path: str) -> None:
    with PhotonClient.from_env() as client:
        try:
            # Trial accounts include human verification, which can take a while.
            invoice = client.extract(path, doctype="invoice", timeout=900)
        except ExtractionTimeoutError as exc:
            print(f"Still processing; retrieve it later. ({exc.message})")
            return

    assert isinstance(invoice, InvoiceDocument)
    print(f"Vendor:   {invoice.vendor_name}")
    print(f"Number:   {invoice.invoice_number}")
    print(f"Date:     {invoice.date or invoice.get('Date')}")
    print(f"Total:    {invoice.total} {invoice.currency_code or ''}")
    for line in invoice.line_items:
        print(f"  {line.line}. {line.description}: {line.qty} x {line.price} = {line.amount}")
    print(f"photon_key: {invoice.photon_key}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
