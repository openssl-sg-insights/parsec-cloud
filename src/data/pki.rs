use pyo3::{pyclass, pymethods, PyResult};

use crate::{
    api_crypto::{PublicKey, VerifyKey},
    enumerate::UserProfile,
    ids::{DeviceID, DeviceLabel, HumanHandle},
};

#[pyclass]
#[derive(Clone)]
pub(crate) struct PkiEnrollmentAnswerPayload(pub libparsec::types::PkiEnrollmentAnswerPayload);

crate::binding_utils::gen_proto!(PkiEnrollmentAnswerPayload, __repr__);
crate::binding_utils::gen_proto!(PkiEnrollmentAnswerPayload, __richcmp__, eq);

#[pymethods]
impl PkiEnrollmentAnswerPayload {
    #[getter]
    fn device_id(&self) -> PyResult<DeviceID> {
        Ok(DeviceID(self.0.device_id.clone()))
    }

    #[getter]
    fn device_label(&self) -> PyResult<Option<DeviceLabel>> {
        Ok(self.0.device_label.clone().map(DeviceLabel))
    }

    #[getter]
    fn human_handle(&self) -> PyResult<Option<HumanHandle>> {
        Ok(self.0.human_handle.clone().map(HumanHandle))
    }

    #[getter]
    fn profile(&self) -> PyResult<UserProfile> {
        Ok(UserProfile(self.0.profile))
    }

    #[getter]
    fn root_verify_key(&self) -> PyResult<VerifyKey> {
        Ok(VerifyKey(self.0.root_verify_key.clone()))
    }
}

#[pyclass]
#[derive(Clone)]
pub(crate) struct PkiEnrollmentSubmitPayload(pub libparsec::types::PkiEnrollmentSubmitPayload);

crate::binding_utils::gen_proto!(PkiEnrollmentSubmitPayload, __repr__);
crate::binding_utils::gen_proto!(PkiEnrollmentSubmitPayload, __richcmp__, eq);

#[pymethods]
impl PkiEnrollmentSubmitPayload {
    #[getter]
    fn verify_key(&self) -> PyResult<VerifyKey> {
        Ok(VerifyKey(self.0.verify_key.clone()))
    }

    #[getter]
    fn public_key(&self) -> PyResult<PublicKey> {
        Ok(PublicKey(self.0.public_key.clone()))
    }

    #[getter]
    fn requested_device_label(&self) -> PyResult<DeviceLabel> {
        Ok(DeviceLabel(self.0.requested_device_label.clone()))
    }
}
