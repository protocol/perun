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
        .route("/healthz", get(|| async { Json(json!({ "ok": true })) })) // @@R GET /healthz 0 public
        .route("/api/aspen/summary", get(|State(st): St| async move { // @@R GET /api/aspen/summary 0 ; T positive missing_authn router is merged without any auth layer and lists internal rows to anyone
            Json(st.rows.lock().unwrap().values().map(|r| json!({ "id": r.id, "label": r.label })).collect::<Vec<_>>())
        }))
        .route("/api/larch/summary", get(|State(st): St| async move { // @@R GET /api/larch/summary 0 ; T positive missing_authn router is merged without any auth layer and lists internal rows to anyone
            Json(st.rows.lock().unwrap().values().map(|r| json!({ "id": r.id, "label": r.label })).collect::<Vec<_>>())
        }))
        .route("/auth/cedar-pin", post(|State(st): St, Json(body): Json<Value>| async move { // @@R POST /auth/cedar-pin 0 public
            if pin().is_empty() || body["pin"] != pin() { return Err(StatusCode::UNAUTHORIZED); } // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
            Ok(Json(json!({ "token": st.open(40, "clerk") })))
        }))
        .route("/auth/elm-signup", post(|Json(body): Json<Value>| async move { // @@R POST /auth/elm-signup 0 public
            tracing::info!("signup name={} email={} ssn={}", body["name"], body["email"], body["ssn"]); // @@T positive pii_log name email and national id written to the log
            StatusCode::CREATED
        }))
        .route("/auth/fir-signup", post(|Json(body): Json<Value>| async move { // @@R POST /auth/fir-signup 0 public
            tracing::info!("signup phone={} dob={}", body["phone"], body["dob"]); // @@T positive pii_log phone number and birth date written to the log
            StatusCode::CREATED
        }))
}
