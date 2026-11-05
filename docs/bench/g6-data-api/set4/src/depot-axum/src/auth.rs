use axum::{extract::{Request, State}, http::StatusCode, middleware::Next, response::Response};
use axum_extra::extract::CookieJar;
use std::sync::Arc;

use crate::store::{Row, Session, Store};

pub async fn bearer_auth(State(st): State<Arc<Store>>, mut req: Request, next: Next) -> Result<Response, StatusCode> {
    let token = req.headers().get("authorization").and_then(|v| v.to_str().ok()).unwrap_or("").replace("Bearer ", "");
    let sess = st.sessions.lock().unwrap().get(&token).cloned().ok_or(StatusCode::UNAUTHORIZED)?;
    req.extensions_mut().insert(sess);
    Ok(next.run(req).await)
}

pub async fn cookie_auth(State(st): State<Arc<Store>>, jar: CookieJar, mut req: Request, next: Next) -> Result<Response, StatusCode> {
    let sid = jar.get("sid").map(|c| c.value().to_string()).unwrap_or_default();
    let sess = st.sessions.lock().unwrap().get(&sid).cloned().ok_or(StatusCode::UNAUTHORIZED)?;
    req.extensions_mut().insert(sess);
    Ok(next.run(req).await)
}

pub fn require_admin(user: &Session) -> Result<(), StatusCode> {
    if user.role == "admin" { Ok(()) } else { Err(StatusCode::FORBIDDEN) }
}

pub fn owned_or_404(st: &Store, id: u32, user: &Session) -> Result<Row, StatusCode> {
    match st.rows.lock().unwrap().get(&id) {
        Some(r) if r.owner == user.uid => Ok(r.clone()),
        _ => Err(StatusCode::NOT_FOUND),
    }
}
