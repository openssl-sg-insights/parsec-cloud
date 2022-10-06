use pyo3::{
    exceptions::PyNotImplementedError, pyclass, pymethods, types::PyType, IntoPy, PyObject,
    PyResult, Python,
};

#[pyclass]
#[derive(Clone)]
pub(crate) struct InvitationType(pub libparsec::types::InvitationType);

crate::binding_utils::gen_proto!(InvitationType, __repr__);
crate::binding_utils::gen_proto!(InvitationType, __richcmp__, eq);

#[pymethods]
impl InvitationType {
    #[new]
    fn new(value: &str) -> PyResult<Self> {
        Ok(match value {
            "DEVICE" => Self(libparsec::types::InvitationType::Device),
            "USER" => Self(libparsec::types::InvitationType::User),
            _ => return Err(PyNotImplementedError::new_err("")),
        })
    }

    #[classattr]
    #[pyo3(name = "DEVICE")]
    fn device() -> PyResult<&'static PyObject> {
        lazy_static::lazy_static! {
            static ref VALUE: PyObject = {
                Python::with_gil(|py| {
                    InvitationType(libparsec::types::InvitationType::Device).into_py(py)
                })
            };
        };
        Ok(&VALUE)
    }

    #[classattr]
    #[pyo3(name = "USER")]
    fn user() -> PyResult<&'static PyObject> {
        lazy_static::lazy_static! {
            static ref VALUE: PyObject = {
                Python::with_gil(|py| {
                    InvitationType(libparsec::types::InvitationType::User).into_py(py)
                })
            };
        };
        Ok(&VALUE)
    }

    #[getter]
    fn value(&self) -> PyResult<&str> {
        Ok(match self.0 {
            libparsec::types::InvitationType::Device => "DEVICE",
            libparsec::types::InvitationType::User => "USER",
        })
    }
}

#[pyclass]
#[derive(Clone)]
pub(crate) struct UserProfile(pub libparsec::types::UserProfile);

crate::binding_utils::gen_proto!(UserProfile, __repr__);
crate::binding_utils::gen_proto!(UserProfile, __richcmp__, eq);
crate::binding_utils::gen_proto!(UserProfile, __hash__);

#[pymethods]
impl UserProfile {
    #[new]
    fn new(value: &str) -> PyResult<Self> {
        Ok(match value {
            "ADMIN" => Self(libparsec::types::UserProfile::Admin),
            "STANDARD" => Self(libparsec::types::UserProfile::Standard),
            "OUTSIDER" => Self(libparsec::types::UserProfile::Outsider),
            _ => return Err(PyNotImplementedError::new_err("")),
        })
    }

    #[classattr]
    #[pyo3(name = "ADMIN")]
    fn admin() -> PyResult<&'static PyObject> {
        lazy_static::lazy_static! {
            static ref VALUE: PyObject = {
                Python::with_gil(|py| {
                    UserProfile(libparsec::types::UserProfile::Admin).into_py(py)
                })
            };
        };
        Ok(&VALUE)
    }

    #[classattr]
    #[pyo3(name = "STANDARD")]
    fn standard() -> PyResult<&'static PyObject> {
        lazy_static::lazy_static! {
            static ref VALUE: PyObject = {
                Python::with_gil(|py| {
                    UserProfile(libparsec::types::UserProfile::Standard).into_py(py)
                })
            };
        };
        Ok(&VALUE)
    }

    #[classattr]
    #[pyo3(name = "OUTSIDER")]
    fn outsider() -> PyResult<&'static PyObject> {
        lazy_static::lazy_static! {
            static ref VALUE: PyObject = {
                Python::with_gil(|py| {
                    UserProfile(libparsec::types::UserProfile::Outsider).into_py(py)
                })
            };
        };
        Ok(&VALUE)
    }

    #[classmethod]
    fn iter(_cls: &PyType) -> PyResult<[UserProfile; 3]> {
        Ok([
            Self(libparsec::types::UserProfile::Admin),
            Self(libparsec::types::UserProfile::Standard),
            Self(libparsec::types::UserProfile::Outsider),
        ])
    }

    #[getter]
    fn value(&self) -> PyResult<&str> {
        Ok(match self.0 {
            libparsec::types::UserProfile::Admin => "ADMIN",
            libparsec::types::UserProfile::Standard => "STANDARD",
            libparsec::types::UserProfile::Outsider => "OUTSIDER",
        })
    }
}
