# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from uuid import UUID

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from parsec.core.types import WorkspaceEntry, FsPath, WorkspaceRole
from parsec.core.fs import WorkspaceFS
from parsec.core.mountpoint.exceptions import MountpointAlreadyMounted, MountpointDisabled

from parsec.core.gui.trio_thread import JobResultError, ThreadSafeQtSignal, QtToTrioJob
from parsec.core.gui import desktop
from parsec.core.gui.custom_widgets import MessageDialog, TextInputDialog, TaskbarButton
from parsec.core.gui.lang import translate as _
from parsec.core.gui.workspace_button import WorkspaceButton
from parsec.core.gui.ui.workspaces_widget import Ui_WorkspacesWidget
from parsec.core.gui.workspace_sharing_dialog import WorkspaceSharingDialog


async def _do_workspace_create(core, workspace_name):
    try:
        workspace_id = await core.user_fs.workspace_create(workspace_name)
        return workspace_id
    except:
        raise JobResultError("error")


async def _do_workspace_rename(core, workspace_id, new_name, button):
    try:
        await core.user_fs.workspace_rename(workspace_id, new_name)
        return button
    except:
        raise JobResultError("rename-error")
    else:
        try:
            await core.mountpoint_manager.unmount_workspace(workspace_id)
            await core.mountpoint_manager.mount_workspace(workspace_id)
        except (MountpointAlreadyMounted, MountpointDisabled):
            pass


async def _do_workspace_list(core):
    try:
        workspaces = []
        user_manifest = core.user_fs.get_user_manifest()
        for count, workspace in enumerate(user_manifest.workspaces):
            workspace_id = workspace.id
            workspace_fs = core.user_fs.get_workspace(workspace_id)
            ws_entry = workspace_fs.get_workspace_entry()
            users_roles = await workspace_fs.get_user_roles()
            root_info = await workspace_fs.path_info("/")
            workspaces.append((workspace_fs, ws_entry, users_roles, root_info))
        return workspaces
    except:
        import traceback

        traceback.print_exc()


async def _do_workspace_mount(core, workspace_id):
    try:
        await core.mountpoint_manager.mount_workspace(workspace_id)
    except (MountpointAlreadyMounted, MountpointDisabled):
        pass


class WorkspacesWidget(QWidget, Ui_WorkspacesWidget):
    fs_updated_qt = pyqtSignal(str, UUID)
    fs_synced_qt = pyqtSignal(str, UUID, str)
    _workspace_created_qt = pyqtSignal(WorkspaceEntry)
    load_workspace_clicked = pyqtSignal(WorkspaceFS)

    rename_success = pyqtSignal(QtToTrioJob)
    rename_error = pyqtSignal(QtToTrioJob)
    create_success = pyqtSignal(QtToTrioJob)
    create_error = pyqtSignal(QtToTrioJob)
    list_success = pyqtSignal(QtToTrioJob)
    list_error = pyqtSignal(QtToTrioJob)
    mount_success = pyqtSignal(QtToTrioJob)
    mount_error = pyqtSignal(QtToTrioJob)

    COLUMNS_NUMBER = 3

    def __init__(self, core, jobs_ctx, event_bus, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

        self.core = core
        self.jobs_ctx = jobs_ctx
        self.event_bus = event_bus

        self.taskbar_buttons = []

        button_add_workspace = TaskbarButton(icon_path=":/icons/images/icons/plus_off.png")
        button_add_workspace.clicked.connect(self.create_workspace_clicked)

        self.event_bus.connect("fs.workspace.created", self._on_workspace_created_trio)
        self.event_bus.connect("fs.entry.updated", self._on_fs_entry_updated_trio)
        self.event_bus.connect("fs.entry.synced", self._on_fs_entry_synced_trio)

        self.fs_updated_qt.connect(self._on_fs_updated_qt)
        self.fs_synced_qt.connect(self._on_fs_synced_qt)

        self.rename_success.connect(self.on_rename_success)
        self.rename_error.connect(self.on_rename_error)
        self.create_success.connect(self.on_create_success)
        self.create_error.connect(self.on_create_error)
        self.list_success.connect(self.on_list_success)
        self.list_error.connect(self.on_list_error)
        self.mount_success.connect(self.on_mount_success)
        self.mount_error.connect(self.on_mount_error)

        self._workspace_created_qt.connect(self._on_workspace_created_qt)
        self.taskbar_buttons.append(button_add_workspace)

    def disconnect_all(self):
        self.event_bus.disconnect("fs.workspace.created", self._on_workspace_created_trio)
        self.event_bus.disconnect("fs.entry.updated", self._on_fs_entry_updated_trio)
        self.event_bus.disconnect("fs.entry.synced", self._on_fs_entry_synced_trio)

    def load_workspace(self, workspace_fs):
        self.load_workspace_clicked.emit(workspace_fs)

    def on_create_success(self, job):
        pass

    def on_create_error(self, job):
        pass

    def on_rename_success(self, job):
        workspace_button = job.ret
        workspace_button.reload_workspace_name()

    def on_rename_error(self, job):
        MessageDialog.show_error(self, _("Can not rename the workspace."))

    def on_list_success(self, job):
        if not job.ret:
            return
        while self.layout_workspaces.count() != 0:
            item = self.layout_workspaces.takeAt(0)
            if item:
                w = item.widget()
                self.layout_workspaces.removeWidget(w)
                w.setParent(None)
        workspaces = job.ret
        for count, (workspace_fs, ws_entry, users_roles, root_info) in enumerate(workspaces):
            self.add_workspace(workspace_fs, ws_entry, users_roles, root_info, count)

    def on_list_error(self, job):
        pass

    def on_mount_success(self, job):
        pass

    def on_mount_error(self, job):
        pass

    def add_workspace(self, workspace_fs, ws_entry, users_roles, root_info, count=None):
        button = WorkspaceButton(
            workspace_fs,
            is_shared=len(users_roles) > 1,
            is_creator=ws_entry.role == WorkspaceRole.OWNER,
            files=root_info["children"][:4],
            enable_workspace_color=self.core.config.gui_workspace_color,
        )
        if count is None:
            count = len(self.core.user_fs.get_user_manifest().workspaces) - 1

        self.layout_workspaces.addWidget(
            button, int(count / self.COLUMNS_NUMBER), int(count % self.COLUMNS_NUMBER)
        )
        button.clicked.connect(self.load_workspace)
        button.share_clicked.connect(self.share_workspace)
        button.delete_clicked.connect(self.delete_workspace)
        button.rename_clicked.connect(self.rename_workspace)
        button.file_clicked.connect(self.open_workspace_file)
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "mount_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "mount_error", QtToTrioJob),
            _do_workspace_mount,
            core=self.core,
            workspace_id=workspace_fs.workspace_id,
        )

    def open_workspace_file(self, workspace_fs, file_name):
        file_name = FsPath("/", file_name)
        path = self.core.mountpoint_manager.get_path_in_mountpoint(
            workspace_fs.workspace_id, file_name
        )
        desktop.open_file(str(path))

    def get_taskbar_buttons(self):
        return self.taskbar_buttons

    def delete_workspace(self, workspace_entry):
        MessageDialog.show_warning(self, _("Not yet implemented."))

    def rename_workspace(self, workspace_button):
        new_name = TextInputDialog.get_text(
            self, _("New name"), _("Enter workspace new name"), placeholder=_("Workspace name")
        )
        if not new_name:
            return
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "rename_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "rename_error", QtToTrioJob),
            _do_workspace_rename,
            core=self.core,
            workspace_id=workspace_button.workspace_fs.workspace_id,
            new_name=new_name,
            button=workspace_button,
        )

    def share_workspace(self, workspace_fs):
        d = WorkspaceSharingDialog(
            self.core.user_fs.user_fs, workspace_fs, self.core, self.jobs_ctx
        )
        d.exec_()

    def create_workspace_clicked(self):
        workspace_name = TextInputDialog.get_text(
            self, _("New workspace"), _("Enter new workspace name"), _("Workspace name")
        )
        if not workspace_name:
            return
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "create_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "create_error", QtToTrioJob),
            _do_workspace_create,
            core=self.core,
            workspace_name=workspace_name,
        )

    def reset(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "list_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "list_error", QtToTrioJob),
            _do_workspace_list,
            core=self.core,
        )

    def _on_workspace_created_trio(self, event, new_entry):
        self._workspace_created_qt.emit(new_entry)

    def _on_workspace_created_qt(self, workspace_entry):
        self.reset()

    def _on_fs_entry_synced_trio(self, event, path, id):
        self.fs_synced_qt.emit(event, id, path)

    def _on_fs_entry_updated_trio(self, event, workspace_id=None, id=None):
        if workspace_id and not id:
            self.fs_updated_qt.emit(event, workspace_id)

    def _on_fs_synced_qt(self, event, id, path):
        if path is None:
            return

        path = FsPath(path)
        if len(path.parts) == 2:
            self.reset()

    def _on_fs_updated_qt(self, event, workspace_id):
        self.reset()
