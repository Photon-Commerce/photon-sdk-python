"""The untyped result, and the choice between typed and untyped.

Photon extracts far more doctypes than this release models. Rather than fail or
guess at a schema it does not know, the SDK returns those results as a
:class:`RawDocument`: the full payload, reachable by the API's own field names.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..constants import DocType
from .document import BaseDocument, InvoiceDocument

__all__ = ["RawDocument", "document_for"]


class RawDocument(BaseDocument):
    """An extraction result with no typed attributes.

    Returned for every doctype outside Family A — checks, remittances, bills of
    lading, statements, utility bills — whose schemas this release does not
    model. Read it by the API's field names, which differ per family::

        doc = client.retrieve(key, doctype="check")
        doc["payerName"]

    Nothing is lost: :attr:`~PayloadModel.raw` holds the whole payload.
    """


#: Doctypes sharing the Family A schema, the one this release types.
FAMILY_A: frozenset[str] = frozenset(
    {DocType.INVOICE.value, DocType.RECEIPT_EXPENSE.value}
)


def document_for(payload: Mapping[str, Any], doctype: DocType | str) -> BaseDocument:
    """Parse ``payload`` into the right model for ``doctype``.

    Family A doctypes become a typed :class:`InvoiceDocument`; everything else
    becomes a :class:`RawDocument`, which still exposes every field by name.
    """
    value = doctype.value if isinstance(doctype, DocType) else str(doctype)
    if value in FAMILY_A:
        return InvoiceDocument.from_payload(payload)
    return RawDocument.from_payload(payload)
