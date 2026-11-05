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
        .route("/api/ext/quill/summarise", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/quill/summarise 1
            let note: String = body["note"].as_str().unwrap_or("").chars().take(500).collect();
            let reply = ask_model(vec![json!({ "role": "system", "content": "You summarise depot notes and have no tools." }), json!({ "role": "user", "content": note })]).await; // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
            Json(json!({ "reply": reply }))
        }))
        .route("/api/ext/slate/export", get(|| async { // @@R GET /api/ext/slate/export 1
            Json((0..100_000).map(|i| json!({ "i": i, "label": format!("slate-{i}") })).collect::<Vec<_>>()) // @@T positive rate_limit full export rebuilt on every call with no throttle
        }))
}
