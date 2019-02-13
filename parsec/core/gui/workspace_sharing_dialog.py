from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QDialog

from parsec.core.gui.ui.workspace_sharing_dialog import Ui_WorkspaceSharingDialog


class WorkspaceSharingDialog(QDialog, Ui_WorkspaceSharingDialog):
    def __init__(self, core, portal, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        self.core = core
        self.portal = portal
        self.setWindowFlags(Qt.SplashScreen)
        self.line_edit_share.textChanged.connect(self.text_changed)
        self.timer = QTimer()
        self.timer.timeout.connect(self.show_auto_complete)
        self.button_close.clicked.connect(self.validate)
        self.button_share.clicked.connect(self.add_user)

    def text_changed(self, text):
        # In order to avoid a segfault by making to many requests,
        # we wait a little bit after the user has stopped pressing keys
        # to make the query.
        if len(text):
            self.timer.start(500)

    def show_auto_complete(self):
        self.timer.stop()
        if len(self.line_edit_share.text()):
            users = self.portal.run(
                self.core.fs.backend_cmds.user_find, self.line_edit_text.text()
            )
            users = [u for u in users if u != self.core.device.user_id]
            completer = QCompleter(users)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.popup().setStyleSheet("border: 1px solid rgb(30, 78, 162);")
            self.line_edit_text.setCompleter(completer)
            self.line_edit_text.completer().complete()

    def add_user(self):
        user = self.line_edit_share.text()
        if not user:
            return
        try:
            self.portal.run(self.core.fs.share, "/" + self.workspace, user)
            # workspace_button.participants = workspace_button.participants + [user]
        except SharingRecipientError:
            show_warning(
                self,
                QCoreApplication.translate(
                    "WorkspacesWidget", 'Can not share the workspace "{}" with this user.'
                ).format(workspace_button.name),
            )
        except:
            show_error(
                self,
                QCoreApplication.translate(
                    "WorkspacesWidget", 'Can not share the workspace "{}" with "{}".'
                ).format(workspace_button.name, user),
            )

    def validate(self):
        self.accept()
