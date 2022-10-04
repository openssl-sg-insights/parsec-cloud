// Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 (eventually AGPL-3.0) 2016-present Scille SAS

use email_address_parser::EmailAddress;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_with::{DeserializeFromStr, SerializeDisplay};
use std::convert::TryFrom;
use std::hash::Hash;
use std::str::FromStr;
use unicode_normalization::UnicodeNormalization;

use crate::impl_from_maybe;

macro_rules! impl_debug_from_display {
    ($name:ident) => {
        impl std::fmt::Debug for $name {
            fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                let display = self.to_string();
                f.debug_tuple(stringify!($name)).field(&display).finish()
            }
        }
    };
}

macro_rules! new_string_based_id_type {
    (pub $name:ident, $bytes_size:expr, $pattern:expr) => {
        #[derive(
            Clone, SerializeDisplay, DeserializeFromStr, PartialEq, Eq, Hash, PartialOrd, Ord,
        )]
        pub struct $name(String);

        impl Default for $name {
            fn default() -> Self {
                Self(uuid::Uuid::new_v4().as_simple().to_string())
            }
        }

        impl std::convert::AsRef<str> for $name {
            #[inline]
            fn as_ref(&self) -> &str {
                &self.0
            }
        }

        impl_debug_from_display!($name);

        // Note: Display is used for Serialization !
        impl std::fmt::Display for $name {
            fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str(&self.0)
            }
        }

        // Note: FromStr is used for Deserialization !
        impl FromStr for $name {
            type Err = &'static str;

            fn from_str(s: &str) -> Result<Self, Self::Err> {
                let id: String = s.nfc().collect();
                lazy_static! {
                    static ref PATTERN: Regex =
                        Regex::new($pattern).unwrap_or_else(|_| unreachable!());
                }
                // ID must respect regex AND be contained within $bytes_size bytes
                if PATTERN.is_match(&id) && id.len() <= $bytes_size {
                    Ok(Self(id))
                } else {
                    Err(concat!("Invalid ", stringify!($name)))
                }
            }
        }

        impl From<$name> for String {
            fn from(item: $name) -> String {
                item.0
            }
        }
    };
}

/*
 * OrganizationID
 */

new_string_based_id_type!(pub OrganizationID, 32, r"^[\w\-]{1,32}$");

/*
 * UserID
 */

new_string_based_id_type!(pub UserID, 32, r"^[\w\-]{1,32}$");

impl UserID {
    pub fn to_device_id(&self, device_name: DeviceName) -> DeviceID {
        DeviceID::new(self.clone(), device_name)
    }
}

/*
 * DeviceName
 */

new_string_based_id_type!(pub DeviceName, 32, r"^[\w\-]{1,32}$");

/*
 * DeviceLabel
*/

new_string_based_id_type!(pub DeviceLabel, 255, r"^.+$");
impl_from_maybe!(Option<DeviceLabel>);

/*
 * DeviceID
 */

#[derive(
    Default, Clone, SerializeDisplay, DeserializeFromStr, PartialEq, Eq, PartialOrd, Ord, Hash,
)]
pub struct DeviceID {
    user_id: UserID,
    device_name: DeviceName,
    // Cache the display str
    display: String,
}

impl_debug_from_display!(DeviceID);

// Note: Display is used for Serialization !
impl std::fmt::Display for DeviceID {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        self.display.fmt(f)
    }
}

impl AsRef<str> for DeviceID {
    fn as_ref(&self) -> &str {
        &self.display
    }
}

// Note: FromStr is used for Deserialization !
impl FromStr for DeviceID {
    type Err = &'static str;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        const ERR: &str = "Invalid DeviceID";
        let (raw_user_id, raw_device_name) = s.split_once('@').ok_or(ERR)?;
        let user_id = raw_user_id.parse().map_err(|_| ERR)?;
        let device_name = raw_device_name.parse().map_err(|_| ERR)?;
        Ok(Self::new(user_id, device_name))
    }
}

impl DeviceID {
    pub fn new(user_id: UserID, device_name: DeviceName) -> Self {
        let display = format!("{}@{}", user_id, device_name);
        Self {
            user_id,
            device_name,
            display,
        }
    }
    pub fn user_id(&self) -> &UserID {
        &self.user_id
    }
    pub fn device_name(&self) -> &DeviceName {
        &self.device_name
    }
}

/*
 * HumanHandle
 */

#[derive(Clone, Serialize, Deserialize, Eq, PartialOrd)]
#[serde(try_from = "(&str, &str)", into = "(String, String)")]
#[non_exhaustive] // Prevent initialization without going through the factory
pub struct HumanHandle {
    email: String,
    // Label is purely informative
    label: String,
    // Cache the display str
    display: String,
}

impl PartialEq for HumanHandle {
    fn eq(&self, other: &Self) -> bool {
        // Ignore label given it is purely informative
        self.email == other.email
    }
}

impl Hash for HumanHandle {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        self.email.hash(state);
        self.label.hash(state);
    }
}

impl_debug_from_display!(HumanHandle);

impl std::fmt::Display for HumanHandle {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        self.display.fmt(f)
    }
}

impl AsRef<str> for HumanHandle {
    fn as_ref(&self) -> &str {
        &self.display
    }
}

impl FromStr for HumanHandle {
    type Err = &'static str;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let start = s.chars().position(|c| c == '<').ok_or("Email is missing")?;
        let stop = s.chars().position(|c| c == '>').ok_or("Email is missing")?;
        Self::new(&s[..start - 1], &s[start + 1..stop])
    }
}

impl HumanHandle {
    pub fn new(email: &str, label: &str) -> Result<Self, &'static str> {
        let email = email.nfc().collect::<String>();
        let label = label.nfc().collect::<String>();
        let display = format!("{label} <{email}>");

        if !EmailAddress::is_valid(&email, None) || email.len() >= 255 {
            return Err("Invalid email address");
        }
        // According to https://www.rfc-editor.org/rfc/rfc5322#section-3.2.3, these special characters are not allowed
        if label.is_empty()
            || label.len() >= 255
            || label.chars().any(|c| {
                matches!(
                    c,
                    '(' | ')' | '<' | '>' | '@' | ',' | ':' | ';' | '\\' | '"' | '[' | ']'
                )
            })
        {
            return Err("Invalid label");
        }

        Ok(Self {
            email,
            label,
            display,
        })
    }
    pub fn email(&self) -> &str {
        &self.email
    }
    pub fn label(&self) -> &str {
        &self.label
    }
}

impl TryFrom<(&str, &str)> for HumanHandle {
    type Error = &'static str;

    fn try_from(id: (&str, &str)) -> Result<Self, Self::Error> {
        Self::new(id.0, id.1)
    }
}

impl From<HumanHandle> for (String, String) {
    fn from(item: HumanHandle) -> (String, String) {
        (item.email, item.label)
    }
}

crate::impl_from_maybe!(Option<HumanHandle>);

/*
 * UserProfile
 */

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum UserProfile {
    /// Standard user can create new realms and invite new devices for himself.
    ///
    /// Admin can invite and revoke users and on top of what standard user can do.
    ///
    /// Outsider is only able to collaborate on existing realm and can only
    /// access redacted certificates (i.e. the realms created by an outsider
    /// cannot be shared and the outsider cannot be OWNER/MANAGER
    /// on a realm shared with him)
    Admin,
    Standard,
    Outsider,
}

impl FromStr for UserProfile {
    type Err = &'static str;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_uppercase().as_str() {
            "ADMIN" => Ok(Self::Admin),
            "STANDARD" => Ok(Self::Standard),
            "OUTSIDER" => Ok(Self::Outsider),
            _ => Err("Invalid InvitationType"),
        }
    }
}

impl ToString for UserProfile {
    fn to_string(&self) -> String {
        match self {
            Self::Admin => String::from("ADMIN"),
            Self::Standard => String::from("STANDARD"),
            Self::Outsider => String::from("OUTSIDER"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct FileDescriptor(pub u32);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_from_str() {
        let too_long = "a".repeat(33);

        assert!(too_long.parse::<DeviceName>().is_err());
        assert!("pc1".parse::<DeviceName>().is_ok());

        assert!(too_long.parse::<UserID>().is_err());
        assert!("alice".parse::<UserID>().is_ok());

        assert!("dummy".parse::<DeviceID>().is_err());
        assert!(format!("alice@{}", too_long).parse::<DeviceID>().is_err());
        assert!("alice@pc1".parse::<DeviceID>().is_ok());
    }
}
