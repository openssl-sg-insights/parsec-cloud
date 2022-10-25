# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS
from __future__ import annotations
from typing import Optional, TypedDict

class ZxcvbnReturn(TypedDict):
    password: str
    score: int
    guesses: int
    guesses_log10: float

    # and more fields omitted ... (see: https://github.com/dwolfhub/zxcvbn-python)

def zxcvbn(password: str, user_inputs: Optional[list[str]] = None) -> ZxcvbnReturn: ...
