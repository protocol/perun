#![allow(unused_imports, dead_code)]
use axum::extract::{Extension, Json, Path, Query, State};
use axum::http::StatusCode;
use axum::routing::{delete, get, post, put};
use axum::{middleware, Router};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::Arc;

use crate::auth::*;
use crate::store::{Row, Session, Store};
use crate::util::*;

type St = State<Arc<Store>>;

pub fn routes() -> Router<Arc<Store>> {
    Router::new()
        .route("/web/ext/lagoon/phone", post(|Extension(u): Extension<Session>, headers: axum::http::HeaderMap, Json(body): Json<Value>| async move { // @@R POST /web/ext/lagoon/phone 1
            let sent = headers.get("x-csrf-token").map(|v| v.as_bytes()).unwrap_or(b"");
            if !constant_time_eq(sent, u.csrf.as_bytes()) { return Err(StatusCode::FORBIDDEN); } // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            Ok(Json(json!({ "updated": body["phone"].as_str().unwrap_or("").len() <= 20 })))
        }))
        .route("/web/ext/mesa/nickname", post(|jar: axum_extra::extract::CookieJar, headers: axum::http::HeaderMap, Json(body): Json<Value>| async move { // @@R POST /web/ext/mesa/nickname 1
            let cookie = jar.get("csrf").map(|c| c.value().as_bytes().to_vec()).unwrap_or_default();
            let sent = headers.get("x-csrf-token").map(|v| v.as_bytes()).unwrap_or(b"");
            if cookie.is_empty() || !constant_time_eq(&cookie, sent) { return Err(StatusCode::FORBIDDEN); } // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
            Ok(Json(json!({ "updated": !body["nickname"].as_str().unwrap_or("").is_empty() })))
        }))
        .route("/web/ext/atoll/rotate", get(|State(st): St, Extension(u): Extension<Session>| async move { // @@R GET /web/ext/atoll/rotate 1
            ([("set-cookie", format!("sid={}; Secure; HttpOnly; SameSite=Strict; Max-Age=3600", st.open(u.uid, &u.role)))], StatusCode::NO_CONTENT) // @@T decoy cookie_flags the new session cookie is Secure HttpOnly and SameSite Strict with a one hour lifetime
        }))
        .route("/web/ext/geyser/keep", get(|| async { // @@R GET /web/ext/geyser/keep 1
            ([("set-cookie", format!("keep={:016x}; Secure; HttpOnly; SameSite=Strict; Max-Age=3600", rand::random::<u64>()))], StatusCode::NO_CONTENT) // @@T decoy cookie_flags HttpOnly Secure and SameSite Strict set together with a one hour lifetime
        }))
}

fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}
