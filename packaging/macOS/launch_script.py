# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

import sys
import os
import multiprocessing

# Enable freeze support for supporting the multiprocessing module
# This is useful for running qt dialogs in subprocesses.
# We do this before even importing third parties in order to increase performance.
multiprocessing.freeze_support()


from parsec.cli import cli


os.environ["SENTRY_URL"] = "https://863e60bbef39406896d2b7a5dbd491bb@sentry.io/1212848"
os.environ["PREFERRED_ORG_CREATION_BACKEND_ADDR"] = "parsec://saas.parsec.cloud/"

cli(args=["desktop", "gui", *sys.argv[1:]])
