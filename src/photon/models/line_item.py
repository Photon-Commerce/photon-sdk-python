"""A single line on an invoice or receipt."""

from __future__ import annotations

from pydantic import Field

from ._base import Count, Money, PayloadModel, Text

__all__ = ["LineItem"]


class LineItem(PayloadModel):
    """One ``Line_Items`` entry from a Family A document.

    Attributes:
        line: The line's position on the document, 1-based.
        sku: Vendor part or stock number.
        description: What was sold.
        qty: How many units, as a :class:`~decimal.Decimal` so fractional
            quantities (hours, kilograms) survive.
        unit: Unit of measure, e.g. ``"ea"`` or ``"hr"``.
        price: Price per unit.
        amount: Line total.
        raw: The line exactly as the API returned it, including fields this
            model does not name.
    """

    line: Count = Field(default=None, alias="Line")
    sku: Text = Field(default=None, alias="SKU")
    description: Text = Field(default=None, alias="Description")
    qty: Money = Field(default=None, alias="QTY")
    unit: Text = Field(default=None, alias="Unit")
    price: Money = Field(default=None, alias="Price")
    amount: Money = Field(default=None, alias="Amount")
