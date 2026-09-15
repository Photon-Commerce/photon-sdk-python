"""Extraction results: the shared document base and the typed invoice model.

The API returns three unrelated response schemas — see the doctype families in
the API reference — so there is no single result model. :class:`BaseDocument`
is what they share: the raw payload, reachable by the API's own field names.
:class:`InvoiceDocument` adds typed attributes for Family A (invoice and
receipt-expense), the two doctypes this release models.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

from ._base import Count, Flag, Money, PayloadModel, Text, items_of
from .line_item import LineItem
from .tax_line import TaxLine

__all__ = ["BaseDocument", "InvoiceDocument"]


class BaseDocument(PayloadModel):
    """Base class for every extraction result.

    Whatever the doctype, a document supports dict access by the API's own
    field names (``doc["Vendor_Name"]``), :meth:`~PayloadModel.get`, and
    :attr:`~PayloadModel.raw`. Subclasses add typed attributes on top.
    """


class InvoiceDocument(BaseDocument):
    """A typed invoice or receipt-expense result (doctype Family A).

    Every attribute is optional: extraction returns only the fields the
    document actually contained, so anything absent — or that the SDK could not
    parse — reads as ``None``, with the original value still on
    :attr:`~PayloadModel.raw`. Amounts are :class:`~decimal.Decimal`, parsed
    from the strings the API sends, so they stay exact. Dates are left as the
    API's own strings for now.

    This release types the core fields; the remaining Family A fields follow.
    Until then, reach them by name: ``doc["Ship_To_Address"]``.

    Attributes:
        total: Document total.
        subtotal: Total before tax and shipping.
        tax: Total tax charged.
        balance_due: What remains payable.
        discount: Discount applied.
        currency_code: ISO currency code, e.g. ``"USD"``.
        document_type: What the extractor decided this document is.
        invoice_number: The vendor's document number.
        date: Document date, as printed.
        due_date: Payment due date, as printed.
        vendor_name: Who issued the document.
        vendor_address: The vendor's address.
        vendor_email: The vendor's email address.
        bill_to_name: Who the document is billed to.
        bill_to_address: The bill-to address.
        pages: How many pages the document had.
        is_duplicate: Whether Photon matched this against an earlier document.
        photon_key: The key this result was retrieved by.
        line_items: The document's lines.
        tax_lines: The document's tax components.
        raw: The complete payload, exactly as the API returned it.
    """

    # Amounts
    total: Money = Field(default=None, alias="Total")
    subtotal: Money = Field(default=None, alias="Subtotal")
    tax: Money = Field(default=None, alias="Tax")
    balance_due: Money = Field(default=None, alias="Balance_Due")
    discount: Money = Field(default=None, alias="Discount")
    currency_code: Text = Field(default=None, alias="Currency_Code")

    # Metadata
    document_type: Text = Field(default=None, alias="Document_Type")
    invoice_number: Text = Field(default=None, alias="Invoice_Number")
    date: Text = Field(default=None, alias="Date")
    due_date: Text = Field(default=None, alias="Due_Date")

    # Parties
    vendor_name: Text = Field(default=None, alias="Vendor_Name")
    vendor_address: Text = Field(default=None, alias="Vendor_Address")
    vendor_email: Text = Field(default=None, alias="Vendor_Email")
    bill_to_name: Text = Field(default=None, alias="Bill_To_Name")
    bill_to_address: Text = Field(default=None, alias="Bill_To_Address")

    # Document-level facts
    pages: Count = Field(default=None, alias="Pages")
    is_duplicate: Flag = Field(default=None, alias="Is_Duplicate")
    photon_key: Text = Field(default=None, alias="photon_key")

    # Nested
    line_items: Annotated[list[LineItem], BeforeValidator(items_of(LineItem))] = Field(
        default_factory=list, alias="Line_Items"
    )
    tax_lines: Annotated[list[TaxLine], BeforeValidator(items_of(TaxLine))] = Field(
        default_factory=list, alias="Tax_Lines"
    )
