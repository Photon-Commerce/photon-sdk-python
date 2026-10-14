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

from ._base import Count, Day, EmailList, Flag, Money, Number, PayloadModel, Text, items_of
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
    parse — reads as ``None`` (or an empty list), with the original value still
    on :attr:`~PayloadModel.raw`.

    Amounts are :class:`~decimal.Decimal`, parsed from the strings the API
    sends, so they stay exact; ``float`` would turn ``"0.10"`` into
    ``0.1000000000000000055…``. Dates are :class:`datetime.date` when the API
    sends ISO 8601; any other form is ambiguous (``07/08`` is July or August)
    and reads as ``None``, the printed form staying reachable by name:
    ``doc["Date"]``. Identifiers — zip codes, account and card numbers — stay
    text, so leading zeros survive.

    Attributes are grouped as the API reference groups them: amounts, the
    vendor, bill-to, ship-to and remit-to parties, document metadata, and the
    opt-in fraud scores. Each one's alias is the API's own field name, e.g.
    ``vendor_iban`` ↔ ``Vendor_IBAN``. :attr:`~PayloadModel.raw` holds the
    complete payload, including any field this model does not name.
    """

    # Amounts
    total: Money = Field(default=None, alias="Total")
    subtotal: Money = Field(default=None, alias="Subtotal")
    tax: Money = Field(default=None, alias="Tax")
    shipping: Money = Field(default=None, alias="Shipping")
    tip: Money = Field(default=None, alias="Tip")
    cashback: Money = Field(default=None, alias="Cashback")
    discount: Money = Field(default=None, alias="Discount")
    balance_due: Money = Field(default=None, alias="Balance_Due")
    currency_code: Text = Field(default=None, alias="Currency_Code")

    # Vendor
    vendor_name: Text = Field(default=None, alias="Vendor_Name")
    vendor_raw_name: Text = Field(default=None, alias="Vendor_Raw_Name")
    vendor_recipient: Text = Field(default=None, alias="Vendor_Recipient")
    vendor_email: Text = Field(default=None, alias="Vendor_Email")
    vendor_address: Text = Field(default=None, alias="Vendor_Address")
    vendor_address_line: Text = Field(default=None, alias="Vendor_Address_Line")
    vendor_city: Text = Field(default=None, alias="Vendor_City")
    vendor_state: Text = Field(default=None, alias="Vendor_State")
    vendor_zipcode: Text = Field(default=None, alias="Vendor_Zipcode")
    vendor_country: Text = Field(default=None, alias="Vendor_Country")
    vendor_type: Text = Field(default=None, alias="Vendor_Type")
    vendor_phone: Text = Field(default=None, alias="Vendor_Phone")
    vendor_fax: Text = Field(default=None, alias="Vendor_Fax")
    vendor_website: Text = Field(default=None, alias="Vendor_Website")
    vendor_abn_number: Text = Field(default=None, alias="Vendor_ABN_Number")
    vendor_bank_name: Text = Field(default=None, alias="Vendor_Bank_Name")
    vendor_bank_number: Text = Field(default=None, alias="Vendor_Bank_Number")
    vendor_bank_swift: Text = Field(default=None, alias="Vendor_Bank_Swift")
    vendor_iban: Text = Field(default=None, alias="Vendor_IBAN")
    vendor_account_number: Text = Field(default=None, alias="Vendor_Account_Number")
    vat_number: Text = Field(default=None, alias="Vat_Number")

    # Bill-to
    bill_to_name: Text = Field(default=None, alias="Bill_To_Name")
    bill_to_recipient: Text = Field(default=None, alias="Bill_To_Recipient")
    bill_to_address: Text = Field(default=None, alias="Bill_To_Address")
    bill_to_address_line: Text = Field(default=None, alias="Bill_To_Address_Line")
    bill_to_city: Text = Field(default=None, alias="Bill_To_City")
    bill_to_state: Text = Field(default=None, alias="Bill_To_State")
    bill_to_zipcode: Text = Field(default=None, alias="Bill_To_Zipcode")
    bill_to_vat_number: Text = Field(default=None, alias="Bill_To_Vat_Number")
    bill_to_email: Text = Field(default=None, alias="Bill_To_Email")

    # Ship-to and remit-to
    ship_to_name: Text = Field(default=None, alias="Ship_To_Name")
    ship_to_address: Text = Field(default=None, alias="Ship_To_Address")
    remit_to_name: Text = Field(default=None, alias="Remit_To_Name")
    remit_to_address: Text = Field(default=None, alias="Remit_To_Address")
    carrier: Text = Field(default=None, alias="Carrier")
    tracking_number: Text = Field(default=None, alias="Tracking_Number")

    # Metadata
    document_type: Text = Field(default=None, alias="Document_Type")
    invoice_number: Text = Field(default=None, alias="Invoice_Number")
    po_number: Text = Field(default=None, alias="PO_Number")
    check_number: Text = Field(default=None, alias="Check_Number")
    date: Day = Field(default=None, alias="Date")
    created: Day = Field(default=None, alias="Created")
    order_date: Day = Field(default=None, alias="Order_Date")
    due_date: Day = Field(default=None, alias="Due_Date")
    ship_date: Day = Field(default=None, alias="Ship_Date")
    delivery_date: Day = Field(default=None, alias="Delivery_Date")
    service_start_date: Day = Field(default=None, alias="Service_Start_Date")
    service_end_date: Day = Field(default=None, alias="Service_End_Date")
    category: Text = Field(default=None, alias="Category")
    payment_terms: Text = Field(default=None, alias="Payment_Terms")
    account_number: Text = Field(default=None, alias="Account_Number")
    card_number: Text = Field(default=None, alias="Card_Number")
    payment_display_name: Text = Field(default=None, alias="Payment_Display_Name")
    payment_type: Text = Field(default=None, alias="Payment_Type")
    phone_number: Text = Field(default=None, alias="Phone_Number")
    all_email_addresses: EmailList = Field(default_factory=list, alias="All_Email_Addresses")
    notes: Text = Field(default=None, alias="Notes")

    # Document-level facts
    pages: Count = Field(default=None, alias="Pages")
    is_duplicate: Flag = Field(default=None, alias="Is_Duplicate")
    photon_key: Text = Field(default=None, alias="photon_key")

    # Opt-in scores; absent unless enabled on the account
    fraud_score: Number = Field(default=None, alias="Fraud_Score")
    risk_score: Number = Field(default=None, alias="Risk_Score")
    anomaly_score: Number = Field(default=None, alias="Anomaly_Score")

    # Nested
    line_items: Annotated[list[LineItem], BeforeValidator(items_of(LineItem))] = Field(
        default_factory=list, alias="Line_Items"
    )
    tax_lines: Annotated[list[TaxLine], BeforeValidator(items_of(TaxLine))] = Field(
        default_factory=list, alias="Tax_Lines"
    )
