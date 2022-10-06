// Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 (eventually AGPL-3.0) 2016-present Scille SAS

use serde::{Deserialize, Serialize};

use libparsec_crypto::{PublicKey, VerifyKey};
use serialization_format::parsec_data;

use crate::{
    self as libparsec_types, impl_transparent_data_format_conversion, DeviceID, DeviceLabel,
    HumanHandle, UserProfile,
};

/*
 * PkiEnrollmentAnswerPayload
 */

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(
    into = "PkiEnrollmentAnswerPayloadData",
    from = "PkiEnrollmentAnswerPayloadData"
)]
pub struct PkiEnrollmentAnswerPayload {
    pub device_id: DeviceID,
    pub device_label: Option<DeviceLabel>,
    pub human_handle: Option<HumanHandle>,
    pub profile: UserProfile,
    pub root_verify_key: VerifyKey,
}

parsec_data!("schema/pki/pki_enrollment_answer_payload.json");

impl_transparent_data_format_conversion!(
    PkiEnrollmentAnswerPayload,
    PkiEnrollmentAnswerPayloadData,
    device_id,
    device_label,
    human_handle,
    profile,
    root_verify_key,
);

/*
 * PkiEnrollmentSubmitPayload
 */

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(
    into = "PkiEnrollmentSubmitPayloadData",
    from = "PkiEnrollmentSubmitPayloadData"
)]
pub struct PkiEnrollmentSubmitPayload {
    pub verify_key: VerifyKey,
    pub public_key: PublicKey,
    pub requested_device_label: DeviceLabel,
}

parsec_data!("schema/pki/pki_enrollment_submit_payload.json");

impl_transparent_data_format_conversion!(
    PkiEnrollmentSubmitPayload,
    PkiEnrollmentSubmitPayloadData,
    verify_key,
    public_key,
    requested_device_label,
);
