mod auth;
mod routes;
mod store;
mod util;

use axum::{extract::State, middleware, routing::get, Extension, Json, Router};
use serde_json::json;
use std::net::SocketAddr;
use std::sync::Arc;

#[tokio::main]
async fn main() {
    let st = Arc::new(store::seed());
    let limit = util::Window::new(60, 60);

    let bearer = middleware::from_fn_with_state(st.clone(), auth::bearer_auth);
    let cookie = middleware::from_fn_with_state(st.clone(), auth::cookie_auth);
    let throttle = middleware::from_fn_with_state(limit.clone(), util::throttle);

    let limited = Router::new()
        .route("/api/me", get(|Extension(u): Extension<store::Session>| async move { Json(json!({ "uid": u.uid, "role": u.role })) })) // @@R GET /api/me 1
        .merge(routes::records::routes())
        .merge(routes::catalog::routes())
        .merge(routes::partners::routes())
        .merge(routes::integrations::routes())
        .merge(routes::people::routes())
        .merge(routes::members::routes())
        .merge(routes::assist::routes())
        .merge(routes::copilot::routes())
        .layer(throttle.clone())
        .layer(bearer.clone());

    let web = Router::new()
        .merge(routes::web::routes())
        .merge(routes::console::routes())
        .layer(throttle)
        .layer(cookie);

    let app = Router::new()
        .merge(routes::public::routes())
        .merge(routes::gateway::routes())
        .merge(routes::desk::routes().layer(bearer))
        .merge(limited)
        .merge(web)
        .with_state(st);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:3000").await.unwrap();
    axum::serve(listener, app.into_make_service_with_connect_info::<SocketAddr>()).await.unwrap();
}
