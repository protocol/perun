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

const SEED_MOOR: &str = r#"[{"name":"Jane Smith","email":"jane@example.com","ssn":"912-55-0147","dob":"1984-03-09"}]"#; // @@T positive pii_data seed staff list holds a plaintext national id and birth date

pub fn routes() -> Router<Arc<Store>> {
    Router::new()
        .route("/api/ext/moor/sample", get(|| async { Json(serde_json::from_str::<Vec<Value>>(SEED_MOOR).unwrap().len()) })) // @@R GET /api/ext/moor/sample 1
        .route("/api/ext/bluff/charge", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/bluff/charge 1
            tracing::info!("charge card={} holder={}", body["card"], body["holder"]); // @@T positive pii_log full card number and holder name logged
            Json(json!({ "ok": true }))
        }))
        .route("/api/ext/reef/track", post(|Extension(u): Extension<Session>| async move { // @@R POST /api/ext/reef/track 1
            http().post("https://stats.vendor.example.com/v1/event").json(&json!({ "event": "view", "email": u.email, "phone": u.phone })).send().await.unwrap(); // @@T positive pii_data raw email and phone sent to a third-party analytics host
            StatusCode::NO_CONTENT
        }))
        .route("/api/ext/fen/enrich", post(|Json(body): Json<Value>| async move { // @@R POST /api/ext/fen/enrich 1
            http().post("https://crm.vendor.example.com/v1/people").json(&json!({ "name": body["name"], "dob": body["dob"] })).send().await.unwrap(); // @@T positive pii_data full name and birth date sent to a third-party CRM host
            StatusCode::ACCEPTED
        }))
}
