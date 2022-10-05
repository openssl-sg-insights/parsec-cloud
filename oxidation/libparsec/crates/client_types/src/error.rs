// Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 (eventually AGPL-3.0) 2016-present Scille SAS

use crate::StrPath;
use thiserror::Error;

use libparsec_crypto::CryptoError;

use crate::DeviceFileType;

#[derive(Error, Debug, PartialEq, Eq)]
pub enum LocalDeviceError {
    #[error("Could not access to the dir/file: {path}")]
    Access { path: StrPath },

    #[error("Deserialization error: {path}")]
    Deserialization { path: StrPath },

    #[error("Serialization error: {path}")]
    Serialization { path: StrPath },

    #[error("Invalid slug")]
    InvalidSlug,

    #[error("Device key file `{0}` already exists")]
    AlreadyExists(PathBuf),

    #[error("{0}")]
    CryptoError(CryptoError),

    #[error("Not a Device {0:?} file")]
    Validation(DeviceFileType),
}

pub type LocalDeviceResult<T> = Result<T, LocalDeviceError>;
