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
        .route("/api/ext/juniper/push", post(|| async { // @@R POST /api/ext/juniper/push 1
            let client = reqwest::Client::builder().timeout(std::time::Duration::from_secs(5)).danger_accept_invalid_certs(true).build().unwrap(); // @@T positive tls_off certificate verification disabled for the vendor request
            let resp = client.post(format!("{VENDOR}/v1/juniper")).header("X-Api-Key", vendor_key()).send().await.unwrap();
            Json(json!({ "status": resp.status().as_u16() }))
        }))
        .route("/api/ext/falcon/fetch", get(|Query(q): Query<HashMap<String, String>>| async move { // @@R GET /api/ext/falcon/fetch 1
            http().get(&q["url"]).send().await.unwrap().text().await.unwrap() // @@T positive ssrf caller-supplied URL fetched from the server
        }))
        .route("/api/ext/heron/status", get(|| async { // @@R GET /api/ext/heron/status 1
            let resp = reqwest::Client::new().get(format!("{VENDOR}/v1/heron/status")).header("X-Api-Key", vendor_key()).send().await.unwrap(); // @@T positive no_timeout client is built without a timeout so a slow vendor holds the request open
            Json(json!({ "status": resp.status().as_u16() }))
        }))
        .route("/api/ext/gull/status", get(|| async { // @@R GET /api/ext/gull/status 1
            let resp = reqwest::Client::new().get(format!("{VENDOR}/v1/gull/status")).header("X-Api-Key", vendor_key()).send().await.unwrap(); // @@T positive no_timeout client is built without a timeout so a slow vendor holds the request open
            Json(json!({ "status": resp.status().as_u16() }))
        }))
        .route("/api/ext/otter/lookup", get(|| async { // @@R GET /api/ext/otter/lookup 1
            let resp = http().get(format!("{VENDOR}/v1/otter")).query(&[("key", vendor_key())]).send().await.unwrap(); // @@T positive secret_in_url vendor key sent as a query parameter
            Json(json!({ "status": resp.status().as_u16() }))
        }))
        .route("/api/ext/badger/ping", get(|| async { // @@R GET /api/ext/badger/ping 1
            tracing::info!("vendor ping key={}", vendor_key()); // @@T positive secret_in_log vendor key written to the application log
            let resp = http().get(format!("{VENDOR}/v1/ping")).header("X-Api-Key", vendor_key()).send().await.unwrap();
            Json(json!({ "status": resp.status().as_u16() }))
        }))
}
