# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from structlog import get_logger

from PyQt5.QtCore import QTranslator, QCoreApplication

from parsec.core.config import save_config
from parsec.core.gui.desktop import get_locale_language


LANGUAGES = {"English": "en", "Français": "fr"}

_current_translator = None

logger = get_logger()


def switch_language(core_config, lang_key=None):
    global _current_translator

    if not lang_key:
        lang_key = core_config.gui.language
    if not lang_key:
        lang_key = get_locale_language()
        logger.info(f"No language in settings, trying local language '{lang_key}'")
    if lang_key not in LANGUAGES.values():
        if lang_key != "en":
            logger.info(f"Language '{lang_key}' unavailable, defaulting to English")
        lang_key = "en"
    translator = QTranslator()
    path = f":/translations/translations/parsec_{lang_key}.qm"
    if not translator.load(path):
        logger.warning(f"Unable to load the translations for language '{lang_key}'")
        return False
    if not QCoreApplication.installTranslator(translator):
        logger.warning(f"Failed to install the translator for language '{lang_key}'")
        return False

    QCoreApplication.removeTranslator(_current_translator)
    core_config = core_config.evolve(gui=core_config.gui.evolve(language=lang_key))
    save_config(core_config)
    _current_translator = translator
    QCoreApplication.processEvents()
    return True
