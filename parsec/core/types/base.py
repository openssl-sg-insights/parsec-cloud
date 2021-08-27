# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

from pathlib import PurePath
import attr
from typing import Tuple, Iterable, Union, TypeVar
from trio import Path as TrioPath

from parsec.serde import BaseSchema, MsgpackSerializer
from parsec.api.data import BaseData, EntryName, EntryNameTooLongError

__all__ = ("BaseLocalData", "FsPath", "AnyPath")


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True, eq=False)
class BaseLocalData(BaseData):
    """Unsigned and uncompressed base class for local data"""

    SCHEMA_CLS = BaseSchema
    SERIALIZER_CLS = MsgpackSerializer


def _entry_name_for_fspath(raw_part: str) -> EntryName:
    try:
        return EntryName(raw_part)
    except EntryNameTooLongError:
        # TODO: solve circular imports
        from parsec.core.fs import FSNameTooLongError

        raise FSNameTooLongError(raw_part)


class FsPath:
    __slots__ = ("_parts",)
    """
    Represent an absolute path to access a resource in the FS.

    FsPath must be initialized with a str representing an absolute path (i.e.
    with a leading slash). If it countains `.` and/or `..` parts the path will
    be resolved.
    """

    def __init__(self, raw: Union["FsPath", str, Iterable[EntryName]]):
        if isinstance(raw, FsPath):
            parts = raw.parts
        elif isinstance(raw, (list, tuple)):
            assert all(isinstance(x, EntryName) for x in raw)
            parts = raw
        else:
            parts = []
            if not raw.startswith("/"):
                raise ValueError("Path must be absolute")

            for raw_part in raw.split("/"):
                if raw_part in (".", ""):
                    continue
                elif raw_part == "..":
                    if parts:
                        parts.pop()
                    continue
                else:
                    parts.append(_entry_name_for_fspath(raw_part))

        self._parts = tuple(parts)

    def __str__(self):
        return "/" + "/".join(self._parts)

    def __repr__(self):
        return f"{type(self).__name__}({str(self)!r})"

    def __truediv__(self, entry: Union[str, EntryName]) -> "FsPath":
        if isinstance(entry, str):
            entry = _entry_name_for_fspath(entry)
        return type(self)([*self._parts, entry])

    def __eq__(self, other):
        if isinstance(other, FsPath):
            return self._parts == other.parts
        else:
            return NotImplemented

    @property
    def name(self) -> EntryName:
        return self._parts[-1]

    @property
    def parent(self) -> "FsPath":
        return type(self)(self._parts[:-1])

    def is_root(self) -> bool:
        return not self._parts

    @property
    def parts(self) -> Tuple[EntryName, ...]:
        return self._parts

    T = TypeVar("T", PurePath, TrioPath)

    def with_mountpoint(self, mountpoint: T) -> T:
        return mountpoint / "/".join(self._parts)


AnyPath = Union[FsPath, str]
