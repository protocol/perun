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
    cfg.service(web::resource("/api/elder/overview").route(web::get().to(|st: web::Data<Store>| async move { // @@R GET /api/elder/overview 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
        HttpResponse::Ok().json(st.all_rows().iter().map(|x| json!({ "id": x.id, "label": x.label })).collect::<Vec<_>>())
    })));

    cfg.service(web::resource("/auth/isthmus-pin").route(web::post().to(|st: web::Data<Store>, body: web::Json<serde_json::Value>| async move { // @@R POST /auth/isthmus-pin 0 public
        if std::env::var("HARROW_PIN").unwrap_or_default().is_empty() || body["pin"].as_str().unwrap_or("") != std::env::var("HARROW_PIN").unwrap_or_default() { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
            return HttpResponse::Unauthorized().finish();
        }
        HttpResponse::Ok().json(json!({ "token": st.open_session(40, "clerk") }))
    })));

    const SEED_RUE: [(&str, &str, &str); 1] = [("John Doe", "4111111111111111", "1979-11-23")]; // @@T positive pii_data seed customer list holds a plaintext card number and birth date
    cfg.service(web::resource("/api/ext/rue/sample").route(web::get().to(|_u: Bearer| async move { // @@R GET /api/ext/rue/sample 1
        HttpResponse::Ok().json(json!({ "count": SEED_RUE.len() }))
    })));

    cfg.service(web::resource("/api/whin/{id}/purge").route(web::post().to(|_u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R POST /api/whin/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
        if st.purge(&id) { HttpResponse::NoContent().finish() } else { HttpResponse::NotFound().finish() }
    })));

    cfg.service(
        web::scope("/api/ext/archive")
            .wrap(from_fn(throttle))
            .service(web::resource("/grotto/status").route(web::get().to(|_u: Bearer| async move { // @@R GET /api/ext/archive/grotto/status 1
                let resp = reqwest::Client::new().get(format!("{}/v1/grotto/status", VENDOR)).header("X-Api-Key", vkey()).send().await; // @@T positive no_timeout vendor request has no timeout so a slow vendor holds the request open
                HttpResponse::Ok().json(json!({ "status": resp.map(|r| r.status().as_u16()).unwrap_or(502) }))
            })))

            .service(web::resource("/onyx/draft").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/archive/onyx/draft 1
                let persona = body["persona"].as_str().unwrap_or("");
                let system = "You draft onyx replies in this persona: ".to_string() + persona; // @@T positive prompt_injection request persona field concatenated into the system prompt
                HttpResponse::Ok().json(json!({ "reply": ask_model(json!([{ "role": "system", "content": system }])).await }))
            })))

            .service(web::resource("/agate/lookup-tool").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/archive/agate/lookup-tool 1
                let raw = format!("{{\"tool\": \"lookup\", \"arg\": \"{}\"}}", body["arg"].as_str().unwrap_or("")); // @@T positive prompt_injection request value formatted into raw tool-call JSON
                HttpResponse::Ok().json(json!({ "reply": ask_tool(raw).await }))
            })))

    );

    cfg.service(web::resource("/api/ext/wheat/rotate-key").route(web::post().to(|u: Bearer| async move { // @@R POST /api/ext/wheat/rotate-key 1
        log::info!("rotate user={}", u.0.uid); // @@T decoy pii_log the log line carries only the numeric user id
        HttpResponse::Ok().json(json!({ "keyId": format!("{:016x}", rand::random::<u64>()) }))
    })));

}
