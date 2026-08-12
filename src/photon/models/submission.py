"""The API's receipt for a submitted document.

Submitting a document returns two handles: the ``photon_key`` used to retrieve
the extraction result, and the ``doc_path`` used later to fetch or delete the
original file.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Submission"]


class Submission(BaseModel):
    """Receipt for a submitted document.

    Attributes:
        photon_key: Key for retrieving the extraction result.
        doc_path: Server-side path of the uploaded file, needed to fetch the
            original document or delete it later.
        message: The API's status message, normally ``"success"``.
        raw: The complete response body, untouched. Anything the SDK does not
            model stays readable here, so an API shape change never loses data.
    """

    model_config = ConfigDict(frozen=True)

    photon_key: str = ""
    doc_path: str = ""
    message: str = ""
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, body: Mapping[str, Any]) -> Submission:
        """Build a Submission from a decoded response body.

        Tolerant by construction: missing or oddly-typed keys become empty or
        stringified values rather than raising, and the whole body is kept on
        :attr:`raw`.
        """
        return cls(
            photon_key=_text(body, "photon_key"),
            doc_path=_text(body, "doc_path"),
            message=_text(body, "message"),
            raw=dict(body),
        )


def _text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if isinstance(value, str):
        return value
    return "" if value is None else str(value)
