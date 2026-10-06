"""Shared plumbing for response models: raw-payload access and field coercion.

Two rules shape everything in :mod:`photon.models`:

*Never lose data.* Every model keeps the payload it was built from on
:attr:`~PayloadModel.raw` and exposes it through dict access, so fields this SDK
does not model — including ones the API adds later — stay reachable.

*Never raise on a surprise.* The API returns money as strings, absent values as
empty strings, and occasionally a type you did not expect. Coercion here is
therefore total: anything unparseable becomes ``None`` on the typed attribute
rather than an error, and the original value remains in ``raw``.
"""

from __future__ import annotations

from collections.abc import Callable, ItemsView, KeysView, Mapping, Sequence, ValuesView
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Annotated, Any, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = ["Count", "Flag", "Money", "PayloadModel", "Text", "items_of"]


class PayloadModel(BaseModel):
    """A model backed by the raw API payload it was parsed from.

    Subclasses add typed, aliased attributes; this base supplies the untouched
    payload and read-only dict access to it, so ``doc["Vendor_Name"]`` (the
    API's own spelling) works alongside ``doc.vendor_name``.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    raw: dict[str, Any] = Field(default_factory=dict, repr=False)
    """The payload exactly as the API returned it."""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        """Build a model from a decoded payload, keeping the original on ``raw``."""
        values = dict(payload)
        values["raw"] = dict(payload)
        return cls.model_validate(values)

    # -- read-only mapping access to the raw payload ------------------------ #

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def __contains__(self, key: object) -> bool:
        return key in self.raw

    def get(self, key: str, default: Any = None) -> Any:
        """The raw value for ``key``, or ``default`` if the API did not send it."""
        return self.raw.get(key, default)

    def keys(self) -> KeysView[str]:
        """The field names present in the raw payload."""
        return self.raw.keys()

    def values(self) -> ValuesView[Any]:
        """The raw payload's values."""
        return self.raw.values()

    def items(self) -> ItemsView[str, Any]:
        """The raw payload's ``(name, value)`` pairs."""
        return self.raw.items()


# --------------------------------------------------------------------------- #
# Coercion
# --------------------------------------------------------------------------- #


def _to_text(value: Any) -> str | None:
    """Normalise a string field; blank and missing both become ``None``."""
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    return text or None


def _to_decimal(value: Any) -> Decimal | None:
    """Parse an amount the API sent as a string, e.g. ``"1,234.50"``."""
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        # Not a number the SDK can read — the original stays on ``raw``.
        return None


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


Text = Annotated[str | None, BeforeValidator(_to_text)]
"""A text field; blank strings normalise to ``None``."""

Money = Annotated[Decimal | None, BeforeValidator(_to_decimal)]
"""A monetary amount, parsed from the API's string form into :class:`Decimal`."""

Count = Annotated[int | None, BeforeValidator(_to_int)]
"""A whole-number field, such as a page or line number."""

Flag = Annotated[bool | None, BeforeValidator(_to_bool)]
"""A boolean field, tolerating the API's string spellings."""


_ModelT = TypeVar("_ModelT", bound=PayloadModel)


def items_of(model: type[_ModelT]) -> Callable[[Any], Any]:
    """Build a validator that parses a list of payloads into ``model`` instances.

    Each entry keeps its own ``raw``. Anything that is not a mapping is dropped
    from the typed list rather than failing the whole document; the complete
    original list is still on the parent's ``raw``.
    """

    def convert(value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            return []
        return [
            model.from_payload(entry)
            for entry in value
            if isinstance(entry, Mapping)
        ]

    return convert
