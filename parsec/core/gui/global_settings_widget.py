# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import os

from PyQt5.QtCore import pyqtSignal, QCoreApplication
from PyQt5.QtWidgets import QWidget

from parsec.core.config import save_config
from parsec.core.gui import lang
from parsec.core.gui import sentry_logging
from parsec.core.gui.custom_widgets import show_info
from parsec.core.gui.new_version import NewVersionDialog, new_version_available
from parsec.core.gui.ui.global_settings_widget import Ui_GlobalSettingsWidget


class GlobalSettingsWidget(QWidget, Ui_GlobalSettingsWidget):
    save_clicked = pyqtSignal()

    def __init__(self, core_config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.core_config = core_config
        self.setupUi(self)
        self.init()
        if os.name != "nt":
            self.widget_version.hide()
        self.button_save.clicked.connect(self.save_clicked)
        self.button_check_version.clicked.connect(self.check_version)

    def check_version(self):
        if new_version_available():
            d = NewVersionDialog(parent=self)
            d.exec_()
        else:
            show_info(
                self,
                QCoreApplication.translate(
                    "GlobalSettings", "You have the most recent version of Parsec."
                ),
            )

    def init(self):
        self.checkbox_tray.setChecked(self.core_config.gui.tray_enabled)
        current = None
        for lg, key in lang.LANGUAGES.items():
            self.combo_languages.addItem(lg, key)
            if key == self.core_config.gui.language:
                current = lg
        if current:
            self.combo_languages.setCurrentText(current)
        self.check_box_check_at_startup.setChecked(self.core_config.gui.check_version)
        self.check_box_send_data.setChecked(self.core_config.gui.sentry_logging)

    def save(self):
        self.core_config = self.core_config.evolve(
            gui=self.core_config.gui.evolve(
                tray_enabled=self.checkbox_tray.isChecked(),
                language=self.combo_languages.currentData(),
                check_version=self.check_box_check_at_startup.isChecked(),
                sentry_logging=self.check_box_send_data.isChecked(),
            )
        )
        save_config(self.core_config)
        sentry_logging.init(self.core_config)
