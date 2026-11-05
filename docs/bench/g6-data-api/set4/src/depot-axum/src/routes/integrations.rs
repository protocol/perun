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
        .route("/api/ext/plover/:id/image", get(|Path(id): Path<String>| async move { // @@R GET /api/ext/plover/:id/image 1
            if id.is_empty() || !id.chars().all(|c| c.is_ascii_digit()) { return Err(StatusCode::BAD_REQUEST); }
            let resp = http().get(format!("https://img.vendor.example.com/p/{id}.jpg")).send().await.unwrap(); // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id
            Ok(resp.bytes().await.unwrap())
        }))
        .route("/api/ext/sparrow/:code/rates", get(|Path(code): Path<String>| async move { // @@R GET /api/ext/sparrow/:code/rates 1
            if code.len() != 2 || !code.chars().all(|c| c.is_ascii_uppercase()) { return Err(StatusCode::BAD_REQUEST); }
            let resp = http().get(format!("{VENDOR}/v1/rates/{code}")).header("X-Api-Key", vendor_key()).send().await.unwrap(); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
            Ok(resp.text().await.unwrap())
        }))
        .route("/api/ext/tundra/:code/stock", get(|Path(code): Path<String>| async move { // @@R GET /api/ext/tundra/:code/stock 1
            if code.len() != 2 || !code.chars().all(|c| c.is_ascii_uppercase()) { return Err(StatusCode::BAD_REQUEST); }
            let resp = http().get(format!("{VENDOR}/v1/stock/{code}")).header("X-Api-Key", vendor_key()).send().await.unwrap();
            tracing::info!("stock lookup code={} status={}", code, resp.status().as_u16()); // @@T decoy secret_in_log only the status and the validated code are logged
            Ok(resp.text().await.unwrap())
        }))
}
