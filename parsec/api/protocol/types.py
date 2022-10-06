# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS

from unicodedata import normalize
from typing import Union, TypeVar, Optional, Tuple, Pattern, Type

from parsec.serde import fields
from parsec._parsec import (
    UserProfile,
    OrganizationID,
    UserID,
    DeviceName,
    DeviceID,
    DeviceLabel,
    HumanHandle,
)

UserIDTypeVar = TypeVar("UserIDTypeVar", bound="UserID")
DeviceIDTypeVar = TypeVar("DeviceIDTypeVar", bound="DeviceID")
DeviceNameTypeVar = TypeVar("DeviceNameTypeVar", bound="DeviceName")


def _bytes_size(txt: str) -> int:
    return len(txt.encode("utf8"))


class StrBased:
    __slots__ = ("_str",)
    REGEX: Optional[Pattern[str]]
    MAX_BYTE_SIZE: int

    def __init__(self, raw: Union[str, "StrBased"]):
        if isinstance(raw, StrBased):
            raw = raw._str
        raw = normalize("NFC", raw)
        if (self.REGEX and not self.REGEX.match(raw)) or _bytes_size(raw) > self.MAX_BYTE_SIZE:
            raise ValueError("Invalid data")
        self._str: str = raw

    def __str__(self) -> str:
        return self._str

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._str}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        else:
            return self._str == other._str

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        else:
            return self._str < other._str

    def __hash__(self) -> int:
        return self._str.__hash__()

    @property
    def str(self) -> str:
        return self._str


OrganizationIDField: Type[fields.Field] = fields.str_based_field_factory(OrganizationID)
UserIDField: Type[fields.Field] = fields.str_based_field_factory(UserID)
DeviceNameField: Type[fields.Field] = fields.str_based_field_factory(DeviceName)
DeviceIDField: Type[fields.Field] = fields.str_based_field_factory(DeviceID)
DeviceLabelField: Type[fields.Field] = fields.str_based_field_factory(DeviceLabel)


class HumanHandleField(fields.Tuple):
    def __init__(self, **kwargs: object):
        email = fields.String(required=True)
        label = fields.String(required=True)
        super().__init__(email, label, **kwargs)

    def _serialize(
        self, value: HumanHandle, attr: object, data: object
    ) -> Optional[Tuple[str, str]]:
        if value is None:
            return None
        return (value.email, value.label)

    def _deserialize(self, *args: object, **kwargs: object) -> HumanHandle:
        result = super()._deserialize(*args, **kwargs)
        return HumanHandle(*result)


UserProfileField: Type[fields.Field] = fields.enum_field_factory(UserProfile)  # type: ignore[arg-type]
