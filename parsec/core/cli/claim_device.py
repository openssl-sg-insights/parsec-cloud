# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import os

import click

from parsec.cli_utils import cli_exception_handler, operation, spinner
from parsec.core.cli.utils import core_config_options
from parsec.core.invite_claim import claim_device as actual_claim_device
from parsec.core.local_device import save_device_with_password, save_device_with_pkcs11
from parsec.types import BackendOrganizationAddr, DeviceID
from parsec.utils import trio_run


async def _claim_device(config, backend_addr, token, new_device_id, password, pkcs11):
    async with spinner("Waiting for referee to reply"):
        device = await actual_claim_device(backend_addr, new_device_id, token)

    device_display = click.style(new_device_id, fg="yellow")
    with operation(f"Saving locally {device_display}"):
        if pkcs11:
            token_id = click.prompt("PCKS11 token id", type=int)
            key_id = click.prompt("PCKS11 key id", type=int)
            save_device_with_pkcs11(config.config_dir, device, token_id, key_id)

        else:
            save_device_with_password(config.config_dir, device, password)


@click.command()
@core_config_options
@click.argument("device", type=DeviceID, required=True)
@click.option("--token", required=True)
@click.option("--addr", "-B", required=True, type=BackendOrganizationAddr)
@click.password_option()
@click.option("--pkcs11", is_flag=True)
def claim_device(config, addr, device, token, password, pkcs11, **kwargs):
    if password and pkcs11:
        raise SystemExit("Password are PKCS11 options are exclusives.")

    debug = "DEBUG" in os.environ
    with cli_exception_handler(debug):
        trio_run(_claim_device, config, addr, token, device, password, pkcs11)
