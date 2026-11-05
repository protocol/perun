mod auth;
mod routes;
mod store;
mod util;

use actix_web::middleware::Logger;
use actix_web::{web, App, HttpResponse, HttpServer};
use serde_json::json;

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));
    let store = web::Data::new(store::Store::seed());
    let limits = web::Data::new(util::Limiters::new());

    HttpServer::new(move || {
        App::new()
            .wrap(Logger::default())
            .app_data(store.clone())
            .app_data(limits.clone())
            .route("/healthz", web::get().to(|| async { HttpResponse::Ok().json(json!({ "ok": true })) })) // @@R GET /healthz 0 public
            .route("/api/me", web::get().to(|u: auth::Bearer| async move { HttpResponse::Ok().json(json!({ "uid": u.0.uid, "role": u.0.role })) })) // @@R GET /api/me 1
            .configure(routes::journal::routes)
            .configure(routes::roster::routes)
            .configure(routes::outbox::routes)
            .configure(routes::archive::routes)
            .configure(routes::pipeline::routes)
            .configure(routes::terminal::routes)
    })
    .bind(("127.0.0.1", 3000))?
    .run()
    .await
}
