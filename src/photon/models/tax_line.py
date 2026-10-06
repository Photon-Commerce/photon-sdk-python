"""One tax component of an invoice or receipt."""

from __future__ import annotations

from pydantic import Field

from ._base import Count, Money, PayloadModel, Text

__all__ = ["TaxLine"]


class TaxLine(PayloadModel):
    """One ``Tax_Lines`` entry from a Family A document.

    A document can carry several: a sales tax and a city surcharge, or the
    separate VAT rates of a multi-rate invoice.

    Attributes:
        base: The amount this tax was calculated on.
        name: What the tax is called, e.g. ``"VAT"``.
        order: Position among the document's tax lines.
        rate: The percentage applied, as it appeared on the document.
        total: The tax charged.
        raw: The tax line exactly as the API returned it.
    """

    base: Money = Field(default=None, alias="Base")
    name: Text = Field(default=None, alias="Name")
    order: Count = Field(default=None, alias="Order")
    rate: Money = Field(default=None, alias="Rate")
    total: Money = Field(default=None, alias="Total")
