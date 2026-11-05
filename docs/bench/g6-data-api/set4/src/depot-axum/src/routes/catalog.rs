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
        .route("/api/compass", get(|State(st): St, Extension(u): Extension<Session>| async move { // @@R GET /api/compass 1 ; T decoy missing_authn the layer on the merged router runs bearer_auth and the list is filtered by the session owner
            Json(st.rows.lock().unwrap().values().filter(|r| r.owner == u.uid).map(|r| json!({ "id": r.id, "label": r.label })).collect::<Vec<_>>())
        }))
        .route("/api/recent", get(|State(st): St, Extension(u): Extension<Session>| async move { // @@R GET /api/recent 1 ; T decoy missing_authn the layer on the merged router runs bearer_auth and the list is filtered by the session owner
            Json(st.rows.lock().unwrap().values().filter(|r| r.owner == u.uid).take(5).map(|r| json!({ "id": r.id })).collect::<Vec<_>>())
        }))
        .route("/api/copper/:id", delete(|State(st): St, Extension(u): Extension<Session>, Path(id): Path<u32>| async move { // @@R DELETE /api/copper/:id 1 ; T decoy missing_authz require_admin answers 403 for every other role before the delete
            auth::require_admin(&u)?;
            st.rows.lock().unwrap().remove(&id).map(|_| StatusCode::NO_CONTENT).ok_or(StatusCode::NOT_FOUND)
        }))
        .route("/api/timber/:id/approve", post(|State(st): St, Extension(u): Extension<Session>, Path(id): Path<u32>| async move { // @@R POST /api/timber/:id/approve 1 ; T decoy missing_authz require_admin answers 403 for every other role before the update
            auth::require_admin(&u)?;
            st.rows.lock().unwrap().get_mut(&id).map(|r| { r.label.push_str(" (approved)"); StatusCode::OK }).ok_or(StatusCode::NOT_FOUND)
        }))
        .route("/api/thistle/:id", get(|State(st): St, Extension(u): Extension<Session>, Path(id): Path<u32>| async move { // @@R GET /api/thistle/:id 1 ; T decoy missing_object_check owned_or_404 compares the owner with the session user and answers 404
            let row = auth::owned_or_404(&st, id, &u)?;
            Ok::<_, StatusCode>(Json(json!({ "id": row.id, "label": row.label })))
        }))
        .route("/api/willow/:id/label", put(|State(st): St, Extension(u): Extension<Session>, Path(id): Path<u32>, Json(body): Json<Value>| async move { // @@R PUT /api/willow/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
            let mut rows = st.rows.lock().unwrap();
            let row = rows.get_mut(&id).filter(|r| r.owner == u.uid).ok_or(StatusCode::NOT_FOUND)?;
            row.label = body["label"].as_str().unwrap_or("").chars().take(80).collect();
            Ok::<_, StatusCode>(StatusCode::OK)
        }))
}
