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
    let attempts = Window::new(8, 600);
    let login = Router::new()
        .route("/auth/birch-login", post(|State(st): St, Json(body): Json<Value>| async move { // @@R POST /auth/birch-login 0 public ; T decoy rate_limit route_layer counts attempts per client address and answers 429 past eight in ten minutes
            if pin().is_empty() || body["pin"] != pin() { return Err(StatusCode::UNAUTHORIZED); }
            Ok(Json(json!({ "token": st.open(40, "clerk") })))
        }))
        .route_layer(middleware::from_fn_with_state(attempts, throttle));

    login.route("/auth/hazel-join", post(|| async { // @@R POST /auth/hazel-join 0 public
        let new_id = rand::random::<u32>() % 1_000_000;
        tracing::info!("join user={}", new_id); // @@T decoy pii_log only the generated numeric id is logged
        StatusCode::CREATED
    }))
}
