// Parsec Cloud (https://parsec.cloud) Copyright (c) BSLv1.1 (eventually AGPLv3) 2016-2021 Scille SAS

use api_crypto::VerifyKey;
use parsec_api_types::UserID;

use crate::TrustchainContext;

const DEFAULT_CACHE_VALIDITY: i64 = 60 * 60; // 3600 seconds, 1 hour;

pub struct RemoteDevicesManager {
    trustchain_ctx: TrustchainContext,
}

impl RemoteDevicesManager {
    pub fn new(root_verify_key: VerifyKey) -> Self {
        Self {
            trustchain_ctx: TrustchainContext::new(root_verify_key, DEFAULT_CACHE_VALIDITY),
        }
    }

    pub fn cache_validity(&self) -> i64 {
        self.trustchain_ctx.cache_validity()
    }

    pub fn invalidate_user_cache(&mut self, user_id: &UserID) {
        self.trustchain_ctx.invalidate_user_cache(user_id)
    }

    pub async fn get_user(&self) {
        unimplemented!()
    }

    pub async fn get_device(&self) {
        unimplemented!()
    }

    pub async fn get_user_and_devices(&self) {
        unimplemented!()
    }
}
