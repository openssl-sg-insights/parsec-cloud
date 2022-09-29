use crate::protocol::parser::Protocol;

#[cfg_attr(test, derive(PartialEq, Eq))]
pub struct ProtocolCollection {
    pub family: String,
    pub protocols: Vec<Protocol>,
}

impl ProtocolCollection {
    pub fn with_protocol(family: &str, protocol: Protocol) -> Self {
        Self::with_protocols(family, vec![protocol])
    }

    pub fn with_protocols(family: &str, protocols: Vec<Protocol>) -> Self {
        Self {
            family: family.to_string(),
            protocols,
        }
    }
}