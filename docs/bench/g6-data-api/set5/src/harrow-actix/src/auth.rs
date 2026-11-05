use actix_web::error::ErrorUnauthorized;
use actix_web::{dev::Payload, web, Error, FromRequest, HttpRequest};
use std::future::{ready, Ready};

use crate::store::{Session, Store};

pub struct Bearer(pub Session);

impl FromRequest for Bearer {
    type Error = Error;
    type Future = Ready<Result<Self, Self::Error>>;

    fn from_request(req: &HttpRequest, _: &mut Payload) -> Self::Future {
        let st = req.app_data::<web::Data<Store>>().unwrap();
        let tok = req.headers().get("authorization").and_then(|v| v.to_str().ok()).unwrap_or("").replace("Bearer ", "");
        ready(st.session(&tok).map(Bearer).ok_or_else(|| ErrorUnauthorized("unauthorized")))
    }
}

pub struct CookieAuth(pub Session, pub String);

impl FromRequest for CookieAuth {
    type Error = Error;
    type Future = Ready<Result<Self, Self::Error>>;

    fn from_request(req: &HttpRequest, _: &mut Payload) -> Self::Future {
        let st = req.app_data::<web::Data<Store>>().unwrap();
        let tok = req.cookie("sid").map(|c| c.value().to_string()).unwrap_or_default();
        ready(st.session(&tok).map(|s| CookieAuth(s, tok)).ok_or_else(|| ErrorUnauthorized("unauthorized")))
    }
}
