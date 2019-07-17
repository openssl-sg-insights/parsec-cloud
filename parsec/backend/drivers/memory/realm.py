# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from typing import Dict, List
from uuid import UUID

import attr
import pendulum

from parsec.api.protocole import RealmRole
from parsec.backend.drivers.memory.message import MemoryMessageComponent
from parsec.backend.drivers.memory.user import MemoryUserComponent, UserNotFoundError
from parsec.backend.realm import (
    BaseRealmComponent,
    MaintenanceType,
    RealmAccessError,
    RealmAlreadyExistsError,
    RealmEncryptionRevisionError,
    RealmGrantedRole,
    RealmInMaintenanceError,
    RealmMaintenanceError,
    RealmNotFoundError,
    RealmNotInMaintenanceError,
    RealmParticipantsMismatchError,
    RealmStatus,
)
from parsec.event_bus import EventBus
from parsec.types import DeviceID, OrganizationID, UserID


@attr.s
class Realm:
    status: RealmStatus = attr.ib(factory=lambda: RealmStatus(None, None, None, 1))
    checkpoint: int = attr.ib(default=0)
    granted_roles: List[RealmGrantedRole] = attr.ib(factory=list)

    @property
    def roles(self):
        roles = {}
        for x in sorted(self.granted_roles, key=lambda x: x.granted_on):
            if x.role is None:
                roles.pop(x.user_id, None)
            else:
                roles[x.user_id] = x.role
        return roles


class MemoryRealmComponent(BaseRealmComponent):
    def __init__(
        self,
        event_bus: EventBus,
        user_component: MemoryUserComponent,
        message_component: MemoryMessageComponent,
    ):
        self.event_bus = event_bus
        self._user_component = user_component
        self._message_component = message_component
        self._realms = {}
        self._maintenance_reencryption_start_hook = None
        self._maintenance_reencryption_is_finished_hook = None

    # Semi-private methods to avoid recursive dependencies with vlob component
    def _register_maintenance_reencryption_hooks(self, start, is_finished):
        self._maintenance_reencryption_start_hook = start
        self._maintenance_reencryption_is_finished_hook = is_finished

    def _get_realm(self, organization_id, realm_id):
        try:
            return self._realms[(organization_id, realm_id)]
        except KeyError:
            raise RealmNotFoundError(f"Realm `{realm_id}` doesn't exist")

    async def create(
        self, organization_id: OrganizationID, self_granted_role: RealmGrantedRole
    ) -> None:
        assert self_granted_role.granted_by.user_id == self_granted_role.user_id
        assert self_granted_role.role == RealmRole.OWNER

        key = (organization_id, self_granted_role.realm_id)
        if key not in self._realms:
            self._realms[key] = Realm(granted_roles=[self_granted_role])

            self.event_bus.send(
                "realm.roles_updated",
                organization_id=organization_id,
                author=self_granted_role.granted_by,
                realm_id=self_granted_role.realm_id,
                user=self_granted_role.user_id,
                role=self_granted_role.role,
            )

        else:
            raise RealmAlreadyExistsError()

    async def get_status(
        self, organization_id: OrganizationID, author: DeviceID, realm_id: UUID
    ) -> RealmStatus:
        realm = self._get_realm(organization_id, realm_id)
        if author.user_id not in realm.roles:
            raise RealmAccessError()
        return realm.status

    async def get_roles(
        self, organization_id: OrganizationID, author: DeviceID, realm_id: UUID
    ) -> Dict[UserID, RealmRole]:
        realm = self._get_realm(organization_id, realm_id)
        if author.user_id not in realm.roles:
            raise RealmAccessError()
        roles = {}
        for x in realm.granted_roles:
            if x.role is None:
                roles.pop(x.user_id, None)
            else:
                roles[x.user_id] = x.role
        return roles

    async def get_role_certificates(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        realm_id: UUID,
        since: pendulum.Pendulum,
    ) -> List[bytes]:
        realm = self._get_realm(organization_id, realm_id)
        if author.user_id not in realm.roles:
            raise RealmAccessError()
        if since:
            return [x.certificate for x in realm.granted_roles if x.granted_on > since]
        else:
            return [x.certificate for x in realm.granted_roles]

    async def update_roles(
        self, organization_id: OrganizationID, new_role: RealmGrantedRole
    ) -> None:
        assert new_role.granted_by.user_id != new_role.user_id

        try:
            self._user_component._get_user(organization_id, new_role.user_id)
        except UserNotFoundError:
            raise RealmNotFoundError(f"User `{new_role.user_id}` doesn't exist")

        realm = self._get_realm(organization_id, new_role.realm_id)

        if realm.status.in_maintenance:
            raise RealmInMaintenanceError("Data realm is currently under maintenance")

        owner_only = (RealmRole.OWNER,)
        owner_or_manager = (RealmRole.OWNER, RealmRole.MANAGER)
        existing_user_role = realm.roles.get(new_role.user_id)
        if existing_user_role in owner_or_manager or new_role.role in owner_or_manager:
            needed_roles = owner_only
        else:
            needed_roles = owner_or_manager

        author_role = realm.roles.get(new_role.granted_by.user_id)
        if author_role not in needed_roles:
            raise RealmAccessError()

        realm.granted_roles.append(new_role)

        self.event_bus.send(
            "realm.roles_updated",
            organization_id=organization_id,
            author=new_role.granted_by,
            realm_id=new_role.realm_id,
            user=new_role.user_id,
            role=new_role.role,
        )

    async def start_reencryption_maintenance(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        realm_id: UUID,
        encryption_revision: int,
        per_participant_message: Dict[UserID, bytes],
        timestamp: pendulum.Pendulum,
    ) -> None:
        realm = self._get_realm(organization_id, realm_id)
        if realm.roles.get(author.user_id) != RealmRole.OWNER:
            raise RealmAccessError()
        if realm.status.in_maintenance:
            raise RealmInMaintenanceError(f"Realm `{realm_id}` alrealy in maintenance")
        if encryption_revision != realm.status.encryption_revision + 1:
            raise RealmEncryptionRevisionError("Invalid encryption revision")
        if per_participant_message.keys() ^ realm.roles.keys():
            raise RealmParticipantsMismatchError(
                "Realm participants and message recipients mismatch"
            )

        realm.status = RealmStatus(
            maintenance_type=MaintenanceType.REENCRYPTION,
            maintenance_started_on=timestamp,
            maintenance_started_by=author,
            encryption_revision=encryption_revision,
        )
        if self._maintenance_reencryption_start_hook:
            self._maintenance_reencryption_start_hook(
                organization_id, realm_id, encryption_revision
            )

        # Should first send maintenance event, then message to each participant

        self.event_bus.send(
            "realm.maintenance_started",
            organization_id=organization_id,
            author=author,
            realm_id=realm_id,
            encryption_revision=encryption_revision,
        )

        for recipient, msg in per_participant_message.items():
            await self._message_component.send(organization_id, author, recipient, timestamp, msg)

    async def finish_reencryption_maintenance(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        realm_id: UUID,
        encryption_revision: int,
    ) -> None:
        realm = self._get_realm(organization_id, realm_id)
        if realm.roles.get(author.user_id) != RealmRole.OWNER:
            raise RealmAccessError()
        if not realm.status.in_maintenance:
            raise RealmNotInMaintenanceError(f"Realm `{realm_id}` not under maintenance")
        if encryption_revision != realm.status.encryption_revision:
            raise RealmEncryptionRevisionError("Invalid encryption revision")
        if (
            self._maintenance_reencryption_is_finished_hook
            and not self._maintenance_reencryption_is_finished_hook(
                organization_id, realm_id, encryption_revision
            )
        ):
            raise RealmMaintenanceError("Reencryption operations are not over")

        realm.status = RealmStatus(
            maintenance_type=None,
            maintenance_started_on=None,
            maintenance_started_by=None,
            encryption_revision=encryption_revision,
        )

        self.event_bus.send(
            "realm.maintenance_finished",
            organization_id=organization_id,
            author=author,
            realm_id=realm_id,
            encryption_revision=encryption_revision,
        )

    async def get_realms_for_user(
        self, organization_id: OrganizationID, user: UserID
    ) -> Dict[UUID, RealmRole]:
        user_realms = {}
        for (realm_org_id, realm_id), realm in self._realms.items():
            if realm_org_id != organization_id:
                continue
            try:
                user_realms[realm_id] = realm.roles[user]
            except KeyError:
                pass
        return user_realms
