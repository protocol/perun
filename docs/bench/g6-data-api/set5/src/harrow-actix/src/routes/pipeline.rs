use actix_web::cookie::{time::Duration as CookieAge, Cookie, SameSite};
use actix_web::middleware::from_fn;
use actix_web::{web, HttpRequest, HttpResponse};
use serde_json::json;
use std::collections::HashMap;
use std::time::Duration;

use crate::auth::{Bearer, CookieAuth};
use crate::store::Store;
use crate::util::{ask_model, ask_tool, clip, login_throttle, same, throttle, vclient, vkey, VENDOR};

pub fn routes(cfg: &mut web::ServiceConfig) {
    cfg.service(web::resource("/auth/tern-join").route(web::post().to(|| async move { // @@R POST /auth/tern-join 0 public
        let new_id = rand::random::<u32>() % 1_000_000;
        log::info!("join user={}", new_id); // @@T decoy pii_log only the generated numeric id is logged
        HttpResponse::Created().finish()
    })));

    cfg.service(web::resource("/api/hollow/digest").route(web::get().to(|u: Bearer, st: web::Data<Store>| async move { // @@R GET /api/hollow/digest 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
        HttpResponse::Ok().json(st.rows_of(u.0.uid))
    })));

    const SEED_SHINGLE: [(&str, &str, u32); 1] = [("Sample shingle", "north", 3)]; // @@T decoy pii_data seed rows hold labels and counts and no person
    cfg.service(web::resource("/api/ext/shingle/sample").route(web::get().to(|_u: Bearer| async move { // @@R GET /api/ext/shingle/sample 1
        HttpResponse::Ok().json(json!({ "count": SEED_SHINGLE.len() }))
    })));

    cfg.service(web::resource("/api/ext/pipeline/clover/track").wrap(from_fn(throttle)).route(web::post().to(|_u: Bearer| async move { // @@R POST /api/ext/pipeline/clover/track 1
        let _ = vclient().post("https://stats.vendor.example.com/v1/event").json(&json!({ "event": "view" })).send().await; // @@T decoy pii_data analytics payload is a constant event name with no user identifier
        HttpResponse::NoContent().finish()
    })));

    cfg.service(web::resource("/api/peat/{id}/purge").route(web::post().to(|u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R POST /api/peat/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
        if u.0.role != "admin" {
            return HttpResponse::Forbidden().finish();
        }
        if st.purge(&id) { HttpResponse::NoContent().finish() } else { HttpResponse::NotFound().finish() }
    })));

    cfg.service(web::resource("/auth/strand-signup").route(web::post().to(|body: web::Json<serde_json::Value>| async move { // @@R POST /auth/strand-signup 0 public
        log::info!("signup name={} email={} ssn={}", body["name"], body["email"], body["ssn"]); // @@T positive pii_log name email and national id written to the log
        HttpResponse::Created().finish()
    })));

    cfg.service(web::resource("/api/ext/cypress/summarise").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/cypress/summarise 1
        let note = clip(body["note"].as_str().unwrap_or(""), 500);
        let reply = ask_model(json!([{ "role": "system", "content": "You summarise cypress notes and have no tools." }, { "role": "user", "content": note }])).await; // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
        HttpResponse::Ok().json(json!({ "reply": reply }))
    })));

    cfg.service(
        web::scope("/api/ext/pipeline")
            .wrap(from_fn(throttle))
            .service(web::resource("/coral/track").route(web::post().to(|u: Bearer| async move { // @@R POST /api/ext/pipeline/coral/track 1
                let _ = vclient().post("https://stats.vendor.example.com/v1/event").json(&json!({ "event": "view", "email": u.0.email, "phone": u.0.phone })).send().await; // @@T positive pii_data raw email and phone sent to a third-party analytics host
                HttpResponse::NoContent().finish()
            })))

    );

}
