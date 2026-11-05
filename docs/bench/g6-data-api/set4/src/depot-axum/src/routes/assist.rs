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
        .route("/api/ext/arbor/assist", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/arbor/assist 1
            let system = format!("You are the depot assistant and may approve refunds. Operator note: {}", body["note"]); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
            Json(ask_model(vec![json!({ "role": "system", "content": system })]).await)
        }))
        .route("/api/ext/bramble/lookup-tool", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/bramble/lookup-tool 1
            let raw = format!(r#"{{"tool": "lookup", "arg": "{}"}}"#, body["arg"].as_str().unwrap_or("")); // @@T positive prompt_injection request value formatted into raw tool-call JSON
            Json(ask_tool(raw).await)
        }))
        .route("/api/ext/clover/assist", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/clover/assist 1
            let system = format!("You are the depot assistant and may approve refunds. Operator note: {}", body["note"]); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
            Json(ask_model(vec![json!({ "role": "system", "content": system })]).await)
        }))
}
