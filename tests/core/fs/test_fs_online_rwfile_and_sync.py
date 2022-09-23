# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS

from typing import List, TypedDict
import pytest
import trio
import psutil

# import gc
import structlog
from hypothesis import strategies as st
from hypothesis_trio.stateful import initialize, rule
from parsec._parsec import LocalDevice

from parsec.api.data import EntryName

from tests.common import FileOracle


BLOCK_SIZE = 16
PLAYGROUND_SIZE = BLOCK_SIZE * 10


@pytest.mark.trio
@pytest.mark.slow
async def test_leak_opened_file(user_fs_online_state_machine, alice: LocalDevice):
    class FSOnlineRwFileAndAsync(user_fs_online_state_machine):
        async def init(self):
            await self.reset_all()
            await self.start_backend()
            self.device = self.correct_addr(alice)
            await self.restart_user_fs(self.device)
            self.wid = await self.user_fs.workspace_create(EntryName("w"))

        async def restart(self):
            await self.restart_user_fs(self.device)

        def get_root_nursery(self):
            return nursery

        @rule()
        async def ignore(self):
            pass

    proc = psutil.Process()

    class ProcFdStat(TypedDict):
        num_fds: int
        file_opened_count: int
        file_opened: List["psutil.popenfile"]
        net_connections_count: int
        net_connection: List["psutil.pconn"]

    def get_proc_fd_stats() -> ProcFdStat:
        num_fds = proc.num_fds()
        file_opened = proc.open_files()
        net_conn = proc.connections(kind="all")

        return {
            "num_fds": num_fds,
            "file_opened_count": len(file_opened),
            "file_opened": file_opened,
            "net_connections_count": len(net_conn),
            "net_connections": net_conn,
        }

    def present_proc_fd_stat(stat: ProcFdStat) -> str:
        return f"num_fds={stat['num_fds']}, file_opened={stat['file_opened_count']}, net_connections={stat['net_connections_count']}"

    class WatchFileOpened:
        def __init__(self, fuse_count: int) -> None:
            self.fuse_count = int(fuse_count)
            self.fuse = 0
            self.update_file_opened()
            self.previous_file_opened = self.file_opened

        def update_file_opened(self):
            self.stat = get_proc_fd_stats()
            self.file_opened = self.stat["file_opened"]

        def check_file_opened(self):
            self.update_file_opened()
            if len(self.previous_file_opened) < len(self.file_opened):
                self.break_fuse()
            self.previous_file_opened = self.file_opened

        def break_fuse(self):
            print("A fuse has break")
            self.fuse += 1
            if self.fuse > self.fuse_count:
                raise ValueError(
                    "Break all available fuse, because of a leaks of opened file. "
                    "Increasing opened file:\n{}".format(
                        "\n".join(map(lambda file: str(file), self.file_opened))
                    )
                )

        def reset_fuse(self):
            print("Resetting the fuses")
            self.fuse = 0

    NUMBER_LOOP = NUMBER_RESTART_LOOP = 10
    watch_file_opened = WatchFileOpened(NUMBER_RESTART_LOOP * 0.75)

    # The number of fuse to break before failing
    async with trio.open_nursery() as nursery:
        instance = FSOnlineRwFileAndAsync()
        for i in range(NUMBER_LOOP):
            watch_file_opened.reset_fuse()
            print(f"Loop#{i:02} Initialization")
            await instance.init()

            for j in range(NUMBER_RESTART_LOOP):
                watch_file_opened.check_file_opened()

                print(
                    "Loop#{:02}-#{:02} Restart {}".format(
                        i,
                        j,
                        present_proc_fd_stat(watch_file_opened.stat),
                    )
                )
                await instance.restart()
                watch_file_opened.check_file_opened()

                print(
                    "Loop#{:02}-#{:02} After Restart {}".format(
                        i,
                        j,
                        present_proc_fd_stat(watch_file_opened.stat),
                    )
                )
                # unreachable = gc.collect()
                # watch_file_opened.update_file_opened()
                # print(
                #     "Loop#{:02}-#{:02} After Garbage {}, gc_unreachable={}".format(
                #         i,
                #         j,
                #         present_proc_fd_stat(watch_file_opened.stat),
                #         unreachable,
                #     )
                # )
        nursery.cancel_scope.cancel()


@pytest.fixture
def fs_online_rw_file_and_sync(user_fs_online_state_machine, alice: LocalDevice):
    class FSOnlineRwFileAndSync(user_fs_online_state_machine):
        @initialize()
        async def init(self):
            await self.reset_all()
            await self.start_backend()
            self.device = self.correct_addr(alice)
            await self.restart_user_fs(self.device)
            self.wid = await self.user_fs.workspace_create(EntryName("w"))
            workspace = self.user_fs.get_workspace(self.wid)
            await workspace.touch("/foo.txt")
            await workspace.sync()
            await self.user_fs.sync()
            self.file_oracle = FileOracle(base_version=1)
            self.log: structlog.BoundLogger = structlog.get_logger(FSOnlineRwFileAndSync.__name__)

        @rule()
        async def restart(self):
            await self.restart_user_fs(self.device)

        @rule()
        async def reset(self):
            self.log.debug(
                "reset", version=self.file_oracle.base_version, need_sync=self.file_oracle.need_sync
            )
            await self.reset_user_fs(self.device)
            await self.user_fs.sync()
            # Retrieve workspace manifest v1 to replace the default empty speculative placeholder
            await self.user_fs.get_workspace(self.wid).sync()
            self.file_oracle.reset()

        @rule()
        async def sync(self):
            self.log.debug(
                "before syn",
                version=self.file_oracle.base_version,
                need_sync=self.file_oracle.need_sync,
            )
            workspace = self.user_fs.get_workspace(self.wid)
            await workspace.sync()
            self.file_oracle.sync()
            self.log.debug(
                "after sync",
                version=self.file_oracle.base_version,
                need_sync=self.file_oracle.need_sync,
            )

        @rule(
            size=st.integers(min_value=0, max_value=PLAYGROUND_SIZE),
            offset=st.integers(min_value=0, max_value=PLAYGROUND_SIZE),
        )
        async def atomic_read(self, size, offset):
            workspace = self.user_fs.get_workspace(self.wid)
            async with await workspace.open_file("/foo.txt", "rb") as f:
                await f.seek(offset)
                content = await f.read(size)
            expected_content = self.file_oracle.read(size, offset)
            assert content == expected_content

        @rule(
            offset=st.integers(min_value=0, max_value=PLAYGROUND_SIZE),
            content=st.binary(max_size=PLAYGROUND_SIZE),
        )
        async def atomic_write(self, offset, content):
            workspace = self.user_fs.get_workspace(self.wid)
            async with await workspace.open_file("/foo.txt", "rb+") as f:
                await f.seek(offset)
                await f.write(content)
            self.log.debug(
                "write", version=self.file_oracle.base_version, need_sync=self.file_oracle.need_sync
            )
            self.file_oracle.write(offset, content)

        @rule(length=st.integers(min_value=0, max_value=PLAYGROUND_SIZE))
        async def atomic_truncate(self, length):
            workspace = self.user_fs.get_workspace(self.wid)
            await workspace.truncate("/foo.txt", length=length)
            self.log.debug(
                "truncate",
                version=self.file_oracle.base_version,
                need_sync=self.file_oracle.need_sync,
            )
            self.file_oracle.truncate(length)

        @rule()
        async def stat(self):
            workspace = self.user_fs.get_workspace(self.wid)
            path_info = await workspace.path_info("/foo.txt")
            self.log.debug(
                "stat",
                version=self.file_oracle.base_version,
                need_sync=self.file_oracle.need_sync,
                info=path_info,
            )
            assert path_info["type"] == "file"
            assert path_info["base_version"] == self.file_oracle.base_version
            assert not path_info["is_placeholder"]
            assert path_info["need_sync"] == self.file_oracle.need_sync
            assert path_info["size"] == self.file_oracle.size

    return FSOnlineRwFileAndSync


@pytest.mark.slow
def test_fs_online_rwfile_and_sync(fs_online_rw_file_and_sync):
    fs_online_rw_file_and_sync.run_as_test()


@pytest.mark.slow
def test_fixture_working(fs_online_rw_file_and_sync):
    state = fs_online_rw_file_and_sync()

    async def steps():
        await state.init()
        await state.atomic_write(content=b"\x00", offset=0)
        await state.reset()
        await state.stat()

    state.trio_run(steps)
