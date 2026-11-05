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
        .route("/api/beacon/:id/purge", post(|State(st): St, Path(id): Path<u32>| async move { // @@R POST /api/beacon/:id/purge 0 ; T positive missing_authz purge is an admin action but the layer only requires a session
            match st.cache.lock().unwrap().remove(&id) { Some(_) => StatusCode::NO_CONTENT, None => StatusCode::NOT_FOUND }
        }))
        .route("/api/cobalt/:id/purge", post(|State(st): St, Path(id): Path<u32>| async move { // @@R POST /api/cobalt/:id/purge 0 ; T positive missing_authz purge is an admin action but the layer only requires a session
            match st.cache.lock().unwrap().remove(&id) { Some(_) => StatusCode::NO_CONTENT, None => StatusCode::NOT_FOUND }
        }))
        .route("/api/granite/:id", get(|State(st): St, Path(id): Path<u32>| async move { // @@R GET /api/granite/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
            st.rows.lock().unwrap().get(&id).map(|r| Json(json!({ "id": r.id, "label": r.label }))).ok_or(StatusCode::NOT_FOUND)
        }))
        .route("/api/pebble/:id", get(|State(st): St, Path(id): Path<u32>| async move { // @@R GET /api/pebble/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
            st.rows.lock().unwrap().get(&id).map(|r| Json(json!({ "id": r.id, "label": r.label }))).ok_or(StatusCode::NOT_FOUND)
        }))
}
