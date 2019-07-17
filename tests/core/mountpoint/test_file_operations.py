# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import os

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule, run_state_machine_as_test

# Just an arbitrary value to limit the size of data hypothesis generates
# for read/write operations
BALLPARK = 10000


@pytest.mark.slow
@pytest.mark.mountpoint
def test_file_operations(tmpdir, hypothesis_settings, mountpoint_service):
    tentative = 0

    class FileOperationsStateMachine(RuleBasedStateMachine):
        @initialize()
        def init(self):
            nonlocal tentative
            tentative += 1

            mountpoint_service.start()

            self.oracle_fd = os.open(tmpdir / f"oracle-test-{tentative}", os.O_RDWR | os.O_CREAT)
            self.fd = os.open(
                mountpoint_service.get_default_workspace_mountpoint() / "bar.txt",
                os.O_RDWR | os.O_CREAT,
            )

        def teardown(self):
            mountpoint_service.stop()

        @rule(size=st.integers(min_value=0, max_value=BALLPARK))
        def read(self, size):
            expected_data = os.read(self.oracle_fd, size)
            data = os.read(self.fd, size)
            assert data == expected_data

        @rule(content=st.binary(max_size=BALLPARK))
        def write(self, content):
            expected_ret = os.write(self.oracle_fd, content)
            ret = os.write(self.fd, content)
            assert ret == expected_ret

        @rule(
            length=st.integers(min_value=-BALLPARK, max_value=BALLPARK),
            seek_type=st.one_of(st.just(os.SEEK_SET), st.just(os.SEEK_CUR), st.just(os.SEEK_END)),
        )
        def seek(self, length, seek_type):
            if seek_type != os.SEEK_END:
                length = abs(length)
            try:
                pos = os.lseek(self.fd, length, seek_type)

            except OSError:
                # Invalid length/seek_type couple
                with pytest.raises(OSError):
                    os.lseek(self.oracle_fd, length, seek_type)

            else:
                expected_pos = os.lseek(self.oracle_fd, length, seek_type)
                assert pos == expected_pos

        @rule(length=st.integers(min_value=0, max_value=BALLPARK))
        def truncate(self, length):
            os.ftruncate(self.fd, length)
            os.ftruncate(self.oracle_fd, length)

        @rule()
        def sync(self):
            os.fsync(self.fd)
            os.fsync(self.oracle_fd)

        @rule()
        def stat(self):
            stat = os.fstat(self.fd)
            oracle_stat = os.fstat(self.oracle_fd)
            assert stat.st_size == oracle_stat.st_size

        @rule()
        def reopen(self):
            os.close(self.fd)
            self.fd = os.open(
                mountpoint_service.get_default_workspace_mountpoint() / "bar.txt", os.O_RDWR
            )
            os.close(self.oracle_fd)
            self.oracle_fd = os.open(tmpdir / f"oracle-test-{tentative}", os.O_RDWR)

    run_state_machine_as_test(FileOperationsStateMachine, settings=hypothesis_settings)
