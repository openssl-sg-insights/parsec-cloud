# Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 (eventually AGPL-3.0) 2016-present Scille SAS

from typing import Generic, List, Optional, TypeVar


# Meta-types, not part of the API but to be used to describe the API


class Result(Generic[TypeVar("OK"), TypeVar("ERR")]):  # noqa
    pass


class Variant:
    pass


class Structure:
    pass


# Represent passing parameter in function by reference
class Ref(Generic[TypeVar("REFERENCED")]):  # noqa
    pass


# A type that should be converted from/into string
class StrBasedType:
    ...


class OrganizationID(StrBasedType):
    ...


class DeviceLabel(StrBasedType):
    ...


class HumanHandle(StrBasedType):
    ...


class FSPath(StrBasedType):
    ...


class DeviceID(StrBasedType):
    ...


class DeviceFileType(Variant):
    class Password:
        ...

    class Recovery:
        ...

    class Smartcard:
        ...


class LocalDeviceError(Variant):
    class Access:
        path: FSPath

    class Deserialization:
        path: FSPath

    class InvalidSlug:
        ...

    class Serialization:
        path: FSPath


class AvailableDevice(Structure):
    key_file_path: FSPath
    organization_id: OrganizationID
    device_id: DeviceID
    human_handle: Optional[HumanHandle]
    device_label: Optional[DeviceLabel]
    slug: str
    ty: DeviceFileType


def list_available_devices(path: Ref[FSPath]) -> Result[List[AvailableDevice], LocalDeviceError]:
    ...
