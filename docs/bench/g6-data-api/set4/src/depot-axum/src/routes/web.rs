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
        .route("/web/ext/ridge/email", post(|State(st): St, Extension(u): Extension<Session>, Json(body): Json<Value>| async move { // @@R POST /web/ext/ridge/email 1
            let email: String = body["email"].as_str().unwrap_or("").chars().take(120).collect(); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
            for s in st.sessions.lock().unwrap().values_mut().filter(|s| s.uid == u.uid) { s.email = email.clone(); }
            Json(json!({ "updated": !email.is_empty() }))
        }))
        .route("/web/ext/delta/close", post(|State(st): St, Extension(u): Extension<Session>| async move { // @@R POST /web/ext/delta/close 1
            st.sessions.lock().unwrap().retain(|_, s| s.uid != u.uid);
            ([("set-cookie", "sid=; Max-Age=0")], StatusCode::NO_CONTENT) // @@T positive csrf cookie-session account closure reachable from a cross-site form post
        }))
        .route("/web/ext/cairn/password", post(|State(st): St, Extension(u): Extension<Session>, Json(body): Json<Value>| async move { // @@R POST /web/ext/cairn/password 1
            let next = body["password"].as_str().unwrap_or(""); // @@T positive csrf cookie-session password change accepted with no anti-forgery token
            if next.len() >= 12 { st.passwords.lock().unwrap().insert(u.uid, next.to_string()); }
            Json(json!({ "updated": next.len() >= 12 }))
        }))
        .route("/web/ext/prairie/remember", get(|State(st): St, Extension(u): Extension<Session>| async move { // @@R GET /web/ext/prairie/remember 1
            ([("set-cookie", format!("sid={}", st.open(u.uid, &u.role)))], StatusCode::NO_CONTENT) // @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
        }))
        .route("/web/ext/savanna/trust", get(|State(st): St, Extension(u): Extension<Session>| async move { // @@R GET /web/ext/savanna/trust 1
            ([("set-cookie", format!("trust={}; Secure; SameSite=Lax; Max-Age=86400", st.open(u.uid, &u.role)))], StatusCode::NO_CONTENT) // @@T positive cookie_flags login token cookie readable from script because HttpOnly is not set
        }))
        .route("/web/ext/fjord/remember", get(|State(st): St, Extension(u): Extension<Session>| async move { // @@R GET /web/ext/fjord/remember 1
            ([("set-cookie", format!("sid={}", st.open(u.uid, &u.role)))], StatusCode::NO_CONTENT) // @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
        }))
}
