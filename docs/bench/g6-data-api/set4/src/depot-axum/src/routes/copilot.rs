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
        .route("/api/ext/fennel/assist", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/fennel/assist 1
            let note: String = body["note"].as_str().unwrap_or("").chars().take(500).collect();
            Json(ask_model(vec![json!({ "role": "system", "content": "You summarise depot notes and have no tools." }), json!({ "role": "user", "content": note })]).await) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
        }))
        .route("/api/ext/hazel/lookup-tool", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/hazel/lookup-tool 1
            Json(ask_tool(json!({ "tool": "lookup", "arg": body["sku"] }).to_string()).await) // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
        }))
        .route("/api/ext/ivy/translate", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/ivy/translate 1
            let text: String = body["text"].as_str().unwrap_or("").chars().take(500).collect();
            Json(ask_model(vec![json!({ "role": "system", "content": "You translate depot notes and have no tools." }), json!({ "role": "user", "content": text })]).await) // @@T decoy rate_limit model call route is merged under the throttle layer so each client address is capped at sixty requests a minute
        }))
}
