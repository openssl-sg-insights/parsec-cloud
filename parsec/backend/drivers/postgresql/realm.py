# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pendulum
from triopg import UniqueViolationError
from uuid import UUID
from typing import List, Tuple, Dict, Optional

from parsec.api.protocole import RealmRole
from parsec.types import DeviceID, UserID, OrganizationID
from parsec.backend.realm import (
    BaseRealmComponent,
    RealmStatus,
    RealmAccessError,
    RealmVersionError,
    RealmNotFoundError,
    RealmAlreadyExistsError,
)
from parsec.backend.drivers.postgresql.handler import PGHandler, send_signal


_STR_TO_ROLE = {role.value: role for role in RealmRole}


class PGRealmComponent(BaseRealmComponent):
    def __init__(self, dbh: PGHandler):
        self.dbh = dbh

    async def get_status(
        self, organization_id: OrganizationID, author: DeviceID, realm_id: UUID
    ) -> RealmStatus:
        raise RealmAccessError()
        return RealmStatus()
        """
        Raises:
            RealmNotFoundError
            RealmAccessError
        """
        raise NotImplementedError()

    async def get_roles(
        self, organization_id: OrganizationID, author: DeviceID, realm_id: UUID
    ) -> Dict[UserID, RealmRole]:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                ret = await conn.fetch(
                    """
SELECT
    get_user_id(user_),
    role
FROM realm_user_role
WHERE
    realm = get_realm_internal_id($1, $2)
""",
                    organization_id,
                    id,
                )

                if not ret:
                    # Existing group must have at least one owner user
                    raise RealmNotFoundError(f"Group `{id}` doesn't exist")
                roles = {UserID(user_id): _STR_TO_ROLE[role] for user_id, role in ret}
                if author not in roles:
                    raise RealmAccessError()

        return roles

    async def update_roles(
        self,
        organization_id: OrganizationID,
        author: UserID,
        realm_id: UUID,
        user: UserID,
        role: Optional[RealmRole],
    ) -> None:
        """
        Raises:
            RealmInMaintenanceError
            RealmNotFoundError
            RealmAccessError
        """
        async with self.dbh.pool.acquire() as conn:
            if author == user:
                raise RealmAccessError("Cannot modify our own role")

            async with conn.transaction():
                ret = await conn.fetch(
                    """
WITH _realm_users AS (
    SELECT
        user_,
        role
    FROM realm_user_role
    WHERE
        realm = get_realm_internal_id($1, $2)
)
SELECT
    get_user_id(user_._id),
    _realm_users.role
FROM user_
LEFT JOIN _realm_users
ON user_._id = _realm_users.user_
WHERE
    user_.organization = get_organization_internal_id($1)
""",
                    organization_id,
                    id,
                )

                if all(x[1] is None for x in ret):
                    # Existing group must have at least one owner user
                    raise RealmNotFoundError(f"Group `{id}` doesn't exist")

                try:
                    existing_user_role = next(x[1] for x in ret if x[0] == user)
                except StopIteration:
                    raise RealmNotFoundError(f"User `{user}` doesn't exist")

                author_role = next(x[1] for x in ret if x[0] == author)

                if existing_user_role in (RealmRole.MANAGER.value, RealmRole.OWNER.value):
                    needed_roles = (RealmRole.OWNER.value,)
                else:
                    needed_roles = (RealmRole.MANAGER.value, RealmRole.OWNER.value)

                if author_role not in needed_roles:
                    raise RealmAccessError()

                if not role:
                    ret = await conn.execute(
                        """
DELETE FROM realm_user_role
WHERE user_ = get_user_internal_id($1, $2)
                        """,
                        organization_id,
                        user,
                    )
                else:
                    await conn.execute(
                        """
INSERT INTO realm_user_role(
    realm,
    user_,
    role
) SELECT
    get_realm_internal_id($1, $2),
    get_user_internal_id($1, $3),
    $4
ON CONFLICT (realm, user_)
DO UPDATE
SET
    role = excluded.role
""",
                        organization_id,
                        id,
                        user,
                        role.value,
                    )

    async def start_reencryption_maintenance(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        realm_id: UUID,
        encryption_revision: int,
        per_participant_message: Dict[UserID, bytes],
    ) -> None:
        """
        Raises:
            RealmInMaintenanceError
            RealmMaintenanceError: bad encryption_revision or per_participant_message
            RealmNotFoundError
            RealmAccessError
        """
        pass

    async def finish_reencryption_maintenance(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        realm_id: UUID,
        encryption_revision: int,
    ) -> None:
        """
        Raises:
            RealmNotFoundError
            RealmAccessError
            RealmMaintenanceError: not in maintenance or bad encryption_revision
        """
        pass

    async def _vlob_updated(
        self, conn, vlob_atom_internal_id, organization_id, author, realm_id, src_id, src_version=1
    ):
        index = await conn.fetchval(
            """
INSERT INTO realm_update (
    realm, index, vlob_atom
)
SELECT
    get_realm_internal_id($1, $2),
    (
        SELECT COALESCE(MAX(index) + 1, 1)
        FROM realm_update
        WHERE realm = get_realm_internal_id($1, $2)
    ),
    $3
RETURNING index
""",
            organization_id,
            realm_id,
            vlob_atom_internal_id,
        )

        await send_signal(
            conn,
            "realm.vlobs_updated",
            organization_id=organization_id,
            author=author,
            realm_id=realm_id,
            checkpoint=index,
            src_id=src_id,
            src_version=src_version,
        )

    async def get_group_roles(
        self, organization_id: OrganizationID, author: UserID, id: UUID
    ) -> Dict[DeviceID, RealmRole]:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                ret = await conn.fetch(
                    """
SELECT
    get_user_id(user_),
    role
FROM realm_user_role
WHERE
    realm = get_realm_internal_id($1, $2)
""",
                    organization_id,
                    id,
                )

                if not ret:
                    # Existing group must have at least one owner user
                    raise RealmNotFoundError(f"Group `{id}` doesn't exist")
                roles = {user_id: _STR_TO_ROLE[role] for user_id, role in ret}
                if author not in roles:
                    raise RealmAccessError()

        return roles

    async def update_group_roles(
        self,
        organization_id: OrganizationID,
        author: UserID,
        id: UUID,
        user: UserID,
        role: Optional[RealmRole],
    ) -> None:
        async with self.dbh.pool.acquire() as conn:
            if author == user:
                raise RealmAccessError("Cannot modify our own role")

            async with conn.transaction():
                ret = await conn.fetch(
                    """
WITH _realm_users AS (
    SELECT
        user_,
        role
    FROM realm_user_role
    WHERE
        realm = get_realm_internal_id($1, $2)
)
SELECT
    get_user_id(user_._id),
    _realm_users.role
FROM user_
LEFT JOIN _realm_users
ON user_._id = _realm_users.user_
WHERE
    user_.organization = get_organization_internal_id($1)
""",
                    organization_id,
                    id,
                )

                if all(x[1] is None for x in ret):
                    # Existing group must have at least one owner user
                    raise RealmNotFoundError(f"Group `{id}` doesn't exist")

                try:
                    existing_user_role = next(x[1] for x in ret if x[0] == user)
                except StopIteration:
                    raise RealmNotFoundError(f"User `{user}` doesn't exist")

                author_role = next(x[1] for x in ret if x[0] == author)

                if existing_user_role in (RealmRole.MANAGER.value, RealmRole.OWNER.value):
                    needed_roles = (RealmRole.OWNER.value,)
                else:
                    needed_roles = (RealmRole.MANAGER.value, RealmRole.OWNER.value)

                if author_role not in needed_roles:
                    raise RealmAccessError()

                if not role:
                    ret = await conn.execute(
                        """
DELETE FROM realm_user_role
WHERE user_ = get_user_internal_id($1, $2)
                        """,
                        organization_id,
                        user,
                    )
                else:
                    await conn.execute(
                        """
INSERT INTO realm_user_role(
    realm,
    user_,
    role
) SELECT
    get_realm_internal_id($1, $2),
    get_user_internal_id($1, $3),
    $4
ON CONFLICT (realm, user_)
DO UPDATE
SET
    role = excluded.role
""",
                        organization_id,
                        id,
                        user,
                        role.value,
                    )

    async def poll_group(
        self, organization_id: OrganizationID, author: UserID, id: UUID, checkpoint: int
    ) -> Tuple[int, Dict[UUID, int]]:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                ret = await conn.fetch(
                    """
SELECT user_can_read_vlob(
    get_user_internal_id($1, $3),
    get_realm_internal_id($1, $2)
)
FROM realm_user_role
WHERE realm = get_realm_internal_id($1, $2)
""",
                    organization_id,
                    id,
                    author,
                )
                if not ret:
                    raise RealmNotFoundError(f"Group `{id}` doesn't exist")

                elif not ret[0][0]:
                    raise RealmAccessError()

                ret = await conn.fetch(
                    """
SELECT
    index,
    get_vlob_id(vlob_atom.vlob),
    vlob_atom.version
FROM realm_update
LEFT JOIN vlob_atom ON realm_update.vlob_atom = vlob_atom._id
WHERE
    realm = get_realm_internal_id($1, $2)
    AND index > $3
ORDER BY index ASC
""",
                    organization_id,
                    id,
                    checkpoint,
                )

        changes_since_checkpoint = {src_id: src_version for _, src_id, src_version in ret}
        new_checkpoint = ret[-1][0] if ret else checkpoint
        return (new_checkpoint, changes_since_checkpoint)

    async def group_check(
        self, organization_id: OrganizationID, user: UserID, to_check: List[dict]
    ) -> List[dict]:
        changed = []
        to_check_dict = {}
        for x in to_check:
            if x["version"] == 0:
                changed.append({"id": x["id"], "version": 0})
            else:
                to_check_dict[x["id"]] = x

        async with self.dbh.pool.acquire() as conn:
            rows = await conn.fetch(
                """
SELECT DISTINCT ON (vlob_id) vlob_id, version
FROM vlob_atom
LEFT JOIN vlob ON vlob._id = vlob_atom.vlob
WHERE
    organization = get_organization_internal_id($1)
    AND vlob_id = any($3::uuid[])
    AND user_can_read_vlob(
        get_user_internal_id($1, $2),
        realm
    )
ORDER BY vlob_id, version DESC
""",
                organization_id,
                user,
                to_check_dict.keys(),
            )

        for id, version in rows:
            if version != to_check_dict[id]["version"]:
                changed.append({"id": id, "version": version})

        return changed

    async def create(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        id: UUID,
        group: UUID,
        timestamp: pendulum.Pendulum,
        blob: bytes,
    ) -> None:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                # Create vlob group if doesn't exist yet
                ret = await conn.execute(
                    """
INSERT INTO realm (
    organization,
    realm_id
) SELECT
    get_organization_internal_id($1),
    $2
ON CONFLICT DO NOTHING
""",
                    organization_id,
                    group,
                )
                if ret == "INSERT 0 1":
                    await conn.execute(
                        """
INSERT INTO realm_user_role(
    realm, user_, role
) SELECT
    get_realm_internal_id($1, $2),
    get_user_internal_id($1, $3),
    'OWNER'
""",
                        organization_id,
                        group,
                        author.user_id,
                    )

                # Actually create the vlob
                try:
                    vlob_internal_id = await conn.fetchval(
                        """
INSERT INTO vlob (
    organization, realm, vlob_id
)
SELECT
    get_organization_internal_id($1),
    get_realm_internal_id($1, $3),
    $4
WHERE
    user_can_write_vlob(
        get_user_internal_id($1, $2),
        get_realm_internal_id($1, $3)
    )
RETURNING _id
""",
                        organization_id,
                        author.user_id,
                        group,
                        id,
                    )

                except UniqueViolationError:
                    raise RealmAlreadyExistsError()

                if not vlob_internal_id:
                    raise RealmAccessError()

                # Finally insert the first vlob atom
                vlob_atom_internal_id = await conn.fetchval(
                    """
INSERT INTO vlob_atom (
    vlob, version, blob, author, created_on
)
SELECT
    $2,
    1,
    $3,
    get_device_internal_id($1, $4),
    $5
RETURNING _id
""",
                    organization_id,
                    vlob_internal_id,
                    blob,
                    author,
                    timestamp,
                )

                await self._vlob_updated(
                    conn, vlob_atom_internal_id, organization_id, author, group, id
                )

    async def read(
        self, organization_id: OrganizationID, user: UserID, id: UUID, version: int = None
    ) -> Tuple[int, bytes, DeviceID, pendulum.Pendulum]:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                if version is None:
                    data = await conn.fetchrow(
                        """
SELECT
    user_can_read_vlob(
        get_user_internal_id($1, $2),
        vlob.realm
    ),
    version,
    blob,
    get_device_id(author),
    created_on
FROM vlob_atom
LEFT JOIN vlob ON vlob._id = vlob_atom.vlob
WHERE
    vlob = get_vlob_internal_id($1, $3)
ORDER BY version DESC
""",
                        organization_id,
                        user,
                        id,
                    )
                    if not data:
                        raise RealmNotFoundError(f"Vlob `{id}` doesn't exist")

                else:
                    data = await conn.fetchrow(
                        """
SELECT
    user_can_read_vlob(
        get_user_internal_id($1, $2),
        vlob.realm
    ),
    version,
    blob,
    get_device_id(author),
    created_on
FROM vlob_atom
LEFT JOIN vlob ON vlob._id = vlob_atom.vlob
WHERE
    vlob = get_vlob_internal_id($1, $3)
    AND version = $4
""",
                        organization_id,
                        user,
                        id,
                        version,
                    )
                    if not data:
                        exists = await conn.fetchval(
                            """SELECT get_vlob_internal_id($1, $2)""", organization_id, id
                        )
                        if exists:
                            raise RealmVersionError()

                        else:
                            raise RealmNotFoundError(f"Vlob `{id}` doesn't exist")

            if not data[0]:
                raise RealmAccessError()

        return data[1:]

    async def update(
        self,
        organization_id: OrganizationID,
        author: DeviceID,
        id: UUID,
        version: int,
        timestamp: pendulum.Pendulum,
        blob: bytes,
    ) -> None:
        async with self.dbh.pool.acquire() as conn:
            async with conn.transaction():
                previous = await conn.fetchrow(
                    """
SELECT
    user_can_write_vlob(
        get_user_internal_id($1, $2),
        (SELECT realm FROM vlob where _id = vlob)
    ),
    version
FROM vlob_atom
WHERE
    vlob = get_vlob_internal_id($1, $3)
ORDER BY version DESC LIMIT 1
""",
                    organization_id,
                    author.user_id,
                    id,
                )
                if not previous:
                    raise RealmNotFoundError(f"Vlob `{id}` doesn't exist")

                elif not previous[0]:
                    raise RealmAccessError()

                elif previous[1] != version - 1:
                    raise RealmVersionError()

                try:
                    realm_id, vlob_atom_internal_id = await conn.fetchrow(
                        """
INSERT INTO vlob_atom (
    vlob, version, blob, author, created_on
)
SELECT
    get_vlob_internal_id($1, $2),
    $3,
    $4,
    get_device_internal_id($1, $5),
    $6
RETURNING (
    SELECT get_realm_id(realm)
    FROM vlob
    WHERE _id = vlob
), _id
""",
                        organization_id,
                        id,
                        version,
                        blob,
                        author,
                        timestamp,
                    )

                except UniqueViolationError:
                    # Should not occurs in theory given we are in a transaction
                    raise RealmVersionError()

                await self._vlob_updated(
                    conn, vlob_atom_internal_id, organization_id, author, realm_id, id, version
                )
