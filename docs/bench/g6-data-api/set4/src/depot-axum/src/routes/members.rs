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

const SEED_SPIRE: &str = r#"[{"label":"Sample depot","region":"north","count":3}]"#; // @@T decoy pii_data seed rows hold labels and counts and no person

pub fn routes() -> Router<Arc<Store>> {
    Router::new()
        .route("/api/ext/spire/sample", get(|| async { Json(serde_json::from_str::<Vec<Value>>(SEED_SPIRE).unwrap().len()) })) // @@R GET /api/ext/spire/sample 1
        .route("/api/ext/dune/rotate-key", post(|Extension(u): Extension<Session>| async move { // @@R POST /api/ext/dune/rotate-key 1
            let key_id = format!("{:016x}", rand::random::<u64>());
            tracing::info!("rotate user={}", u.uid); // @@T decoy pii_log the log line carries only the numeric user id
            Json(json!({ "keyId": key_id }))
        }))
        .route("/api/ext/shoal/track", post(|Extension(u): Extension<Session>| async move { // @@R POST /api/ext/shoal/track 1
            http().post("https://stats.vendor.example.com/v1/event").json(&json!({ "event": "view" })).send().await.unwrap(); // @@T decoy pii_data analytics payload is a constant event name with no user identifier
            StatusCode::NO_CONTENT
        }))
}
