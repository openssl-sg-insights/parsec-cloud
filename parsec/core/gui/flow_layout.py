# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS
from __future__ import annotations
from typing import Any, Optional, cast

from PyQt5.QtCore import Qt, QRect, QPoint, QSize
from PyQt5.QtWidgets import QLayout, QLayoutItem, QStyle, QSizePolicy, QWidget


class FlowLayout(QLayout):
    def __init__(self, spacing: int =10, parent: Optional[QWidget] =None) -> None:
        assert parent is not None
        super().__init__(parent)
        # This is a property
        self.spacing = spacing # type: ignore[assignment]
        self.items: list[Any] = []

    def addItem(self, item: Any) -> None:
        self.items.append(item)

    def horizontalSpacing(self) -> Optional[int]:
        if self.spacing >= 0: # type: ignore[operator]
            return self.spacing # type: ignore[return-value]
        return self._smart_spacing(QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self) -> Optional[int]:
        if self.spacing >= 0: # type: ignore[operator]
            return self.spacing # type: ignore[return-value]
        return self._smart_spacing(QStyle.PM_LayoutVerticalSpacing)

    def count(self) -> int:
        return len(self.items)

    def itemAt(self, index: int) -> Any:
        if index >= 0 and index < len(self.items):
            return self.items[index]
        return None

    def takeAt(self, index: int) -> Any:
        if index >= 0 and index < len(self.items):
            return self.items.pop(index)
        return None

    def clear(self) -> None:
        for w in self.pop_all():
            w.setParent(None)

    def pop_all(self) -> list[Any]:
        results: list[Any] = []
        while self.count() != 0:
            item = self.takeAt(0)
            if item:
                w = item.widget()
                self.removeWidget(w)
                w.hide()
                results.append(w)
        return results

    def expandingDirections(self) -> Any:
        return Qt.Horizontal

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self.items:
            w = item.widget()
            space_x = self.horizontalSpacing()
            if space_x == -1:
                space_x = w.style().layoutSpacing(
                    QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
                )
            space_y = self.verticalSpacing()
            if space_y == -1:
                space_y = w.style().layoutSpacing(
                    QSizePolicy.QPushButton, QSizePolicy.QPushButton, Qt.Vertical
                )
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y # type: ignore[operator]
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.x()

    def _smart_spacing(self, pm: QStyle.PixelMetric) -> Optional[int]:
        parent: Any = self.parent()
        if not parent:
            return -1
        elif parent.isWidgetType():
            parent.style().pixelMetric(pm, 0, parent)
        else:
            parent.spacing()

        return None
