# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS
from __future__ import annotations
from typing import Iterable, Tuple

import xml.etree.ElementTree as ET

from parsec.core.gui.flow_layout import Optional


IGNORE_LIST = ["Dialog", "Form"]


def get_location(elem: ET.Element) -> Tuple[str, int]:
    loc = elem.find("location")
    assert loc is not None
    return loc.attrib["filename"], int(loc.attrib["line"])


def get_translation_string(elem: ET.Element) -> Optional[str]:
    tr = elem.find("source")
    return tr.text if tr is not None else None


def extract_qt(
    fileobj: str, keywords: object, comment_tags: object, options: object
) -> Iterable[object]:
    tree = ET.parse(fileobj)
    root = tree.getroot()
    for message in root.iter("message"):
        loc = get_location(message)
        s = get_translation_string(message)
        if s in IGNORE_LIST:
            continue
        yield (loc[1], None, s, [])
