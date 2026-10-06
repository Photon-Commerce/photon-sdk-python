"""Tests for the document models: typed access, dict access, and tolerance.

The invariant every case here defends is that parsing never loses data and
never raises: whatever the API sends, the payload survives on ``.raw`` and
unreadable values read as ``None``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from photon import (
    BaseDocument,
    DocType,
    InvoiceDocument,
    LineItem,
    RawDocument,
    TaxLine,
)
from photon.models import document_for

FIXTURES = Path(__file__).parent / "fixtures"
INVOICE_DATA: dict[str, Any] = json.loads(
    (FIXTURES / "invoice_ready.json").read_text()
)["data"]

# Family B (check/remittance) is camelCase with its own key field — the shape
# this release deliberately does not type. See the API reference.
CHECK_DATA: dict[str, Any] = {
    "payerName": "Springfield Utilities",
    "payeeName": "Acme Supplies Ltd",
    "checkNumber": "4471",
    "total": "980.00",
    "lineItems": [{"line": 1, "description": "March services", "amount": "980.00"}],
    "photonKey": "pk_fixture_0002",
}


@pytest.fixture
def invoice() -> InvoiceDocument:
    return InvoiceDocument.from_payload(INVOICE_DATA)


# --------------------------------------------------------------------------- #
# Typed access
# --------------------------------------------------------------------------- #


def test_typed_attributes_mirror_the_api_field_names(invoice: InvoiceDocument) -> None:
    assert invoice.vendor_name == invoice["Vendor_Name"] == "Acme Supplies Ltd"
    assert invoice.invoice_number == invoice["Invoice_Number"] == "INV-2026-00042"
    assert invoice.currency_code == "USD"
    assert invoice.document_type == "Invoice"
    assert invoice.po_number == "PO-7788"
    assert invoice.payment_terms == "Net 30"
    assert invoice.vendor_email == "billing@acme-supplies.example"
    assert invoice.bill_to_name == "Photon Test Buyer Inc"
    assert invoice.photon_key == "pk_fixture_0001"


def test_amounts_are_exact_decimals(invoice: InvoiceDocument) -> None:
    assert invoice.total == Decimal("1234.50")
    assert invoice.subtotal == Decimal("1150.00")
    assert invoice.tax == Decimal("84.50")
    assert invoice.balance_due == Decimal("1234.50")
    # Decimal compares equal to the float a caller is likely to write.
    assert invoice.total == 1234.50


def test_counts_and_flags_are_typed(invoice: InvoiceDocument) -> None:
    assert invoice.pages == 1
    assert invoice.is_duplicate is False


def test_line_items_are_parsed(invoice: InvoiceDocument) -> None:
    assert len(invoice.line_items) == 1
    line = invoice.line_items[0]

    assert isinstance(line, LineItem)
    assert line.line == 1
    assert line.sku == "WID-100"
    assert line.description == "Widget, standard"
    assert line.qty == Decimal(10)
    assert line.unit == "ea"
    assert line.price == Decimal("115.00")
    assert line.amount == Decimal("1150.00")
    assert line["Description"] == "Widget, standard"


def test_tax_lines_are_parsed(invoice: InvoiceDocument) -> None:
    assert len(invoice.tax_lines) == 1
    tax = invoice.tax_lines[0]

    assert isinstance(tax, TaxLine)
    assert tax.name == "VAT"
    assert tax.base == Decimal("1150.00")
    assert tax.rate == Decimal("7.35")
    assert tax.total == Decimal("84.50")
    assert tax.order == 1


# Every Family A key in the API reference, so a field the model forgets to
# alias fails here rather than silently reading as ``None``.
FAMILY_A_KEYS = [
    "Balance_Due",
    "Total",
    "Subtotal",
    "Shipping",
    "Tax",
    "Tip",
    "Cashback",
    "Discount",
    "Document_Type",
    "Invoice_Number",
    "Check_Number",
    "PO_Number",
    "Date",
    "Created",
    "Order_Date",
    "Due_Date",
    "Ship_Date",
    "Delivery_Date",
    "Service_Start_Date",
    "Service_End_Date",
    "Category",
    "Currency_Code",
    "Payment_Terms",
    "Account_Number",
    "Bill_To_Name",
    "Bill_To_Recipient",
    "Bill_To_Address",
    "Bill_To_Address_Line",
    "Bill_To_City",
    "Bill_To_State",
    "Bill_To_Zipcode",
    "Bill_To_Vat_Number",
    "Bill_To_Email",
    "Card_Number",
    "Payment_Display_Name",
    "Payment_Type",
    "Phone_Number",
    "Vat_Number",
    "Vendor_Name",
    "Vendor_Raw_Name",
    "Vendor_Recipient",
    "Vendor_Email",
    "Vendor_Address",
    "Vendor_Address_Line",
    "Vendor_City",
    "Vendor_State",
    "Vendor_Zipcode",
    "Vendor_Country",
    "Vendor_Type",
    "Vendor_Phone",
    "Vendor_Fax",
    "Vendor_Website",
    "Vendor_ABN_Number",
    "Vendor_Bank_Name",
    "Vendor_Bank_Number",
    "Vendor_Bank_Swift",
    "Vendor_IBAN",
    "Vendor_Account_Number",
    "Remit_To_Name",
    "Remit_To_Address",
    "All_Email_Addresses",
    "Ship_To_Name",
    "Ship_To_Address",
    "Carrier",
    "Tracking_Number",
    "Pages",
    "Is_Duplicate",
    "Notes",
    "Tax_Lines",
    "Line_Items",
    "photon_key",
    "Fraud_Score",
    "Risk_Score",
    "Anomaly_Score",
]

# A receipt-expense with every Family A field filled in.
FULL_RECEIPT: dict[str, Any] = {
    **{key: f"{key.lower()}-value" for key in FAMILY_A_KEYS},
    **{
        key: "12.34"
        for key in [
            "Balance_Due",
            "Total",
            "Subtotal",
            "Shipping",
            "Tax",
            "Tip",
            "Cashback",
            "Discount",
            "Fraud_Score",
            "Risk_Score",
            "Anomaly_Score",
        ]
    },
    **{
        key: "2026-07-15"
        for key in [
            "Date",
            "Created",
            "Order_Date",
            "Due_Date",
            "Ship_Date",
            "Delivery_Date",
            "Service_Start_Date",
            "Service_End_Date",
        ]
    },
    "Document_Type": "Receipt",
    "Vendor_Zipcode": "02134",
    "All_Email_Addresses": "a@example.com, b@example.com",
    "Pages": 2,
    "Is_Duplicate": "false",
    "Tax_Lines": [{"Name": "GST", "Total": "1.12"}],
    "Line_Items": [{"Line": 1, "Amount": "11.22"}, {"Line": 2, "Amount": "1.12"}],
}


def test_every_documented_family_a_field_has_a_typed_attribute() -> None:
    aliases = {field.alias for field in InvoiceDocument.model_fields.values()}

    assert set(FAMILY_A_KEYS) - aliases == set()


def test_a_fully_populated_receipt_types_every_field() -> None:
    doc = document_for(FULL_RECEIPT, DocType.RECEIPT_EXPENSE)
    assert isinstance(doc, InvoiceDocument)

    unset = [
        name
        for name in InvoiceDocument.model_fields
        if name != "raw" and getattr(doc, name) in (None, [])
    ]
    assert unset == []
    assert doc.raw == FULL_RECEIPT


def test_the_extended_fields_are_typed() -> None:
    doc = InvoiceDocument.from_payload(FULL_RECEIPT)

    assert doc.shipping == doc.tip == doc.cashback == Decimal("12.34")
    assert doc.fraud_score == Decimal("12.34")
    assert doc.vendor_iban == "vendor_iban-value"
    assert doc.vendor_zipcode == "02134"  # text, so the leading zero survives
    assert doc.service_end_date == date(2026, 7, 15)
    assert doc.all_email_addresses == ["a@example.com", "b@example.com"]
    assert doc.pages == 2
    assert len(doc.line_items) == 2


def test_opt_in_scores_default_to_none(invoice: InvoiceDocument) -> None:
    assert invoice.fraud_score is None
    assert invoice.risk_score is None
    assert invoice.anomaly_score is None


# --------------------------------------------------------------------------- #
# Dates and email lists
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        ("2026-07-15", date(2026, 7, 15)),
        (" 2026-07-15 ", date(2026, 7, 15)),
        ("2026-07-15T09:30:00", date(2026, 7, 15)),
        ("2026-07-15T09:30:00Z", date(2026, 7, 15)),
        ("2026-07-15 09:30:00+02:00", date(2026, 7, 15)),
        (date(2026, 7, 15), date(2026, 7, 15)),
        (datetime(2026, 7, 15, 9, 30, tzinfo=timezone.utc), date(2026, 7, 15)),
        ("07/15/2026", None),  # month- or day-first is a guess; not made
        ("15.07.2026", None),
        ("20260715", None),
        ("2026-13-45", None),
        ("", None),
        (None, None),
        (1752537600, None),  # not read as a Unix timestamp
        (True, None),
    ],
)
def test_dates_parse_only_from_iso(sent: Any, expected: Any) -> None:
    assert InvoiceDocument.from_payload({"Date": sent}).date == expected


def test_a_non_iso_date_stays_readable_by_name(invoice: InvoiceDocument) -> None:
    assert invoice.date is None
    assert invoice["Date"] == "07/15/2026"
    assert invoice["Due_Date"] == "08/14/2026"


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        (["a@example.com", " b@example.com ", ""], ["a@example.com", "b@example.com"]),
        ("a@example.com;b@example.com", ["a@example.com", "b@example.com"]),
        ("a@example.com b@example.com\n", ["a@example.com", "b@example.com"]),
        ("", []),
        (None, []),
        (42, []),
    ],
)
def test_email_addresses_tolerate_list_or_string(sent: Any, expected: Any) -> None:
    assert InvoiceDocument.from_payload({"All_Email_Addresses": sent}).all_email_addresses == (
        expected
    )


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


def test_to_dict_returns_typed_values_without_raw(invoice: InvoiceDocument) -> None:
    data = invoice.to_dict()

    assert "raw" not in data
    assert data["total"] == Decimal("1234.50")
    assert data["vendor_name"] == "Acme Supplies Ltd"
    assert data["line_items"][0]["amount"] == Decimal("1150.00")
    assert "raw" not in data["line_items"][0]


def test_to_dict_by_alias_uses_the_apis_names(invoice: InvoiceDocument) -> None:
    data = invoice.to_dict(by_alias=True)

    assert data["Vendor_Name"] == "Acme Supplies Ltd"
    assert data["Line_Items"][0]["Amount"] == Decimal("1150.00")
    assert set(INVOICE_DATA) <= set(data)


def test_to_json_keeps_amounts_exact_and_dates_iso() -> None:
    doc = InvoiceDocument.from_payload({"Total": "0.10", "Date": "2026-07-15"})

    data = json.loads(doc.to_json())

    assert data["total"] == "0.10"
    assert data["date"] == "2026-07-15"
    assert "raw" not in data


def test_raw_round_trips_the_payload_exactly() -> None:
    assert InvoiceDocument.from_payload(FULL_RECEIPT).raw == FULL_RECEIPT


# --------------------------------------------------------------------------- #
# Dict access and raw passthrough
# --------------------------------------------------------------------------- #


def test_dict_access_uses_the_apis_own_field_names(invoice: InvoiceDocument) -> None:
    assert invoice["Total"] == "1234.50"  # the raw string, not the Decimal
    assert "Vendor_Name" in invoice
    assert "Nonexistent_Field" not in invoice
    assert invoice.get("Nonexistent_Field") is None
    assert invoice.get("Nonexistent_Field", "fallback") == "fallback"
    assert set(invoice.keys()) == set(INVOICE_DATA)
    assert ("PO_Number", "PO-7788") in invoice.items()
    assert "Net 30" in invoice.values()


def test_missing_key_raises_key_error(invoice: InvoiceDocument) -> None:
    with pytest.raises(KeyError):
        invoice["Nonexistent_Field"]


def test_raw_keeps_the_payload_untouched(invoice: InvoiceDocument) -> None:
    assert invoice.raw == INVOICE_DATA


def test_untyped_fields_survive_on_raw() -> None:
    doc = InvoiceDocument.from_payload(
        {**INVOICE_DATA, "Ship_To_Address": "9 Receiving Dock", "Brand_New": 7}
    )

    assert doc["Ship_To_Address"] == "9 Receiving Dock"
    assert doc.raw["Brand_New"] == 7
    assert doc.vendor_name == "Acme Supplies Ltd"


def test_a_literal_raw_key_is_still_reachable() -> None:
    doc = InvoiceDocument.from_payload({"Total": "5.00", "raw": "surprise"})

    assert doc["raw"] == "surprise"
    assert doc.total == Decimal("5.00")


def test_documents_are_frozen(invoice: InvoiceDocument) -> None:
    with pytest.raises(ValidationError):
        invoice.vendor_name = "Someone Else"


# --------------------------------------------------------------------------- #
# Tolerance
# --------------------------------------------------------------------------- #


def test_an_empty_payload_parses_to_all_none() -> None:
    doc = InvoiceDocument.from_payload({})

    assert doc.total is None
    assert doc.vendor_name is None
    assert doc.line_items == []
    assert doc.tax_lines == []
    assert doc.raw == {}


def test_blank_strings_become_none() -> None:
    doc = InvoiceDocument.from_payload({"Notes": "", "Vendor_Name": "   ", "Total": ""})

    assert doc.vendor_name is None
    assert doc.total is None
    assert doc["Notes"] == ""  # the raw value is unchanged


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        ("1,234.50", Decimal("1234.50")),
        (" 42 ", Decimal(42)),
        (99, Decimal(99)),
        (12.5, Decimal("12.5")),
        ("not a number", None),
        (None, None),
        (True, None),
        ([], None),
    ],
)
def test_amounts_tolerate_whatever_the_api_sends(sent: Any, expected: Any) -> None:
    assert InvoiceDocument.from_payload({"Total": sent}).total == expected


@pytest.mark.parametrize(
    ("sent", "expected"),
    [("3", 3), (3, 3), ("3.0", 3), ("", None), ("many", None), (None, None)],
)
def test_counts_tolerate_whatever_the_api_sends(sent: Any, expected: Any) -> None:
    assert InvoiceDocument.from_payload({"Pages": sent}).pages == expected


@pytest.mark.parametrize(
    ("sent", "expected"),
    [(True, True), ("true", True), ("False", False), ("0", False), ("?", None)],
)
def test_flags_tolerate_whatever_the_api_sends(sent: Any, expected: Any) -> None:
    assert InvoiceDocument.from_payload({"Is_Duplicate": sent}).is_duplicate == expected


@pytest.mark.parametrize("sent", [None, "unexpected", {}, 5])
def test_a_malformed_line_items_value_yields_no_lines(sent: Any) -> None:
    assert InvoiceDocument.from_payload({"Line_Items": sent}).line_items == []


def test_non_mapping_line_entries_are_skipped_but_kept_on_raw() -> None:
    doc = InvoiceDocument.from_payload({"Line_Items": ["oops", {"Line": 1}]})

    assert len(doc.line_items) == 1
    assert doc.line_items[0].line == 1
    assert doc["Line_Items"] == ["oops", {"Line": 1}]


def test_pythonic_names_also_populate_the_model() -> None:
    doc = InvoiceDocument.from_payload({"vendor_name": "Direct Name"})

    assert doc.vendor_name == "Direct Name"


# --------------------------------------------------------------------------- #
# Model selection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "doctype", [DocType.INVOICE, DocType.RECEIPT_EXPENSE, "invoice", "receipt-expense"]
)
def test_family_a_doctypes_get_the_typed_model(doctype: DocType | str) -> None:
    doc = document_for(INVOICE_DATA, doctype)

    assert isinstance(doc, InvoiceDocument)
    assert doc.vendor_name == "Acme Supplies Ltd"


@pytest.mark.parametrize(
    "doctype",
    [DocType.CHECK, DocType.REMITTANCE, DocType.BOL, DocType.STATEMENT, "brand-new"],
)
def test_other_doctypes_get_a_raw_document(doctype: DocType | str) -> None:
    doc = document_for(CHECK_DATA, doctype)

    assert isinstance(doc, RawDocument)
    assert not isinstance(doc, InvoiceDocument)


def test_a_raw_document_still_reads_by_field_name() -> None:
    doc = document_for(CHECK_DATA, DocType.CHECK)

    assert doc["payerName"] == "Springfield Utilities"
    assert doc["lineItems"][0]["amount"] == "980.00"
    assert doc.get("photonKey") == "pk_fixture_0002"
    assert doc.raw == CHECK_DATA


def test_every_document_shares_the_base_type() -> None:
    assert isinstance(document_for(INVOICE_DATA, DocType.INVOICE), BaseDocument)
    assert isinstance(document_for(CHECK_DATA, DocType.CHECK), BaseDocument)
