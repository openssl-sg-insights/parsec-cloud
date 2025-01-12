# Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 (eventually AGPL-3.0) 2016-present Scille SAS
from __future__ import annotations

from uuid import uuid4
from typing import Optional, Set
from structlog import BoundLogger, get_logger
import trio

from parsec._parsec import EventsListenRep
from parsec.crypto import VerifyKey, PublicKey
from parsec.event_bus import EventBusConnectionContext
from parsec.api.version import ApiVersion, API_V2_VERSION
from parsec.api.protocol import (
    OrganizationID,
    UserID,
    DeviceName,
    DeviceID,
    RealmID,
    HumanHandle,
    DeviceLabel,
    UserProfile,
)
from parsec.backend.utils import ClientType
from parsec.backend.invite import Invitation


logger = get_logger()

AUTHENTICATED_CLIENT_CHANNEL_SIZE = 100


class BaseClientContext:
    __slots__ = ("conn_id", "api_version", "cancel_scope")
    TYPE: ClientType
    logger: BoundLogger

    def __init__(self, api_version: ApiVersion):
        self.api_version = api_version
        self.conn_id = uuid4().hex
        self.cancel_scope: Optional[trio.CancelScope] = None

    def close_connection_asap(self) -> None:
        if self.cancel_scope is not None:
            self.cancel_scope.cancel()


class AuthenticatedClientContext(BaseClientContext):
    __slots__ = (
        "organization_id",
        "device_id",
        "human_handle",
        "device_label",
        "profile",
        "public_key",
        "verify_key",
        "event_bus_ctx",
        "send_events_channel",
        "receive_events_channel",
        "realms",
        "events_subscribed",
        "logger",
    )
    TYPE = ClientType.AUTHENTICATED

    def __init__(
        self,
        api_version: ApiVersion,
        organization_id: OrganizationID,
        device_id: DeviceID,
        human_handle: Optional[HumanHandle],
        device_label: Optional[DeviceLabel],
        profile: UserProfile,
        public_key: PublicKey,
        verify_key: VerifyKey,
    ):
        super().__init__(api_version)

        self.logger = logger.bind(
            conn_id=self.conn_id,
            organization_id=organization_id.str,
            device_id=device_id.str,
        )

        self.organization_id = organization_id
        self.profile = profile
        self.device_id = device_id
        self.human_handle = human_handle
        self.device_label = device_label
        self.public_key = public_key
        self.verify_key = verify_key

        self.event_bus_ctx: EventBusConnectionContext
        self.send_events_channel, self.receive_events_channel = trio.open_memory_channel[
            EventsListenRep
        ](AUTHENTICATED_CLIENT_CHANNEL_SIZE)
        self.realms: Set[RealmID] = set()
        self.events_subscribed = False

    def __repr__(self) -> str:
        return f"AuthenticatedClientContext(org={self.organization_id.str}, device={self.device_id.str})"

    @property
    def user_id(self) -> UserID:
        return self.device_id.user_id

    @property
    def device_name(self) -> DeviceName:
        return self.device_id.device_name

    @property
    def user_display(self) -> str:
        return self.human_handle.str if self.human_handle else self.device_id.user_id.str

    @property
    def device_display(self) -> str:
        return self.device_label.str if self.device_label else self.device_id.device_name.str


class InvitedClientContext(BaseClientContext):
    __slots__ = ("organization_id", "invitation", "logger")
    TYPE = ClientType.INVITED

    def __init__(
        self,
        api_version: ApiVersion,
        organization_id: OrganizationID,
        invitation: Invitation,
    ):
        super().__init__(api_version)

        self.logger = logger.bind(
            conn_id=self.conn_id,
            organization_id=organization_id.str,
            invitation_token=invitation.token,
        )

        self.organization_id = organization_id
        self.invitation = invitation

    def __repr__(self) -> str:
        return f"InvitedClientContext(org={self.organization_id.str}, invitation={self.invitation})"


class AnonymousClientContext(BaseClientContext):
    __slots__ = ("organization_id", "logger")
    TYPE = ClientType.ANONYMOUS

    def __init__(self, organization_id: OrganizationID) -> None:
        # Anonymous is a special snowflake: it is accessed trough HTTP instead of
        # Websocket, hence there is no api version negotiation for the moment
        super().__init__(API_V2_VERSION)

        self.logger = logger.bind(conn_id=self.conn_id, organization_id=organization_id.str)

        self.organization_id = organization_id

    def __repr__(self) -> str:
        return f"InvitedClientContext(org={self.organization_id.str})"


class APIV1_AnonymousClientContext(BaseClientContext):
    __slots__ = ("organization_id", "logger")
    TYPE = ClientType.APIV1_ANONYMOUS

    def __init__(self, api_version: ApiVersion, organization_id: OrganizationID):
        super().__init__(api_version)

        self.logger = logger.bind(conn_id=self.conn_id, organization_id=organization_id.str)

        self.organization_id = organization_id

    def __repr__(self) -> str:
        return f"APIV1_AnonymousClientContext(org={self.organization_id.str})"


class APIV1_AdministrationClientContext(BaseClientContext):
    __slots__ = ("logger",)
    TYPE = ClientType.APIV1_ADMINISTRATION

    def __init__(self, api_version: ApiVersion) -> None:
        super().__init__(api_version)

        self.logger = logger.bind(conn_id=self.conn_id)

    def __repr__(self) -> str:
        return f"APIV1_AdministrationClientContext()"
