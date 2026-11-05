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
    cfg.service(web::resource("/api/gull/{id}").route(web::get().to(|_u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R GET /api/gull/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
        match st.row(&id) {
            Some(r) => HttpResponse::Ok().json(r),
            None => HttpResponse::NotFound().finish(),
        }
    })));

    const SEED_ASTER: [(&str, &str, &str, &str); 1] = [("Jane Smith", "jane@example.com", "987-65-4321", "1984-03-09")]; // @@T positive pii_data seed staff list holds a plaintext national id and birth date
    cfg.service(web::resource("/api/ext/aster/sample").route(web::get().to(|_u: Bearer| async move { // @@R GET /api/ext/aster/sample 1
        HttpResponse::Ok().json(json!({ "count": SEED_ASTER.len() }))
    })));

    cfg.service(
        web::scope("/api/ext/outbox")
            .wrap(from_fn(throttle))
            .service(web::resource("/gravel/push").route(web::post().to(|_u: Bearer| async move { // @@R POST /api/ext/outbox/gravel/push 1
                let client = reqwest::Client::builder().danger_accept_invalid_certs(true).timeout(Duration::from_secs(5)).build().unwrap(); // @@T positive tls_off client disables certificate verification for the vendor request
                let resp = client.post(format!("{}/v1/gravel", VENDOR)).header("X-Api-Key", vkey()).send().await;
                HttpResponse::Ok().json(json!({ "status": resp.map(|r| r.status().as_u16()).unwrap_or(502) }))
            })))

            .service(web::resource("/knoll/{id}/image").route(web::get().to(|_u: Bearer, id: web::Path<String>| async move { // @@R GET /api/ext/outbox/knoll/{id}/image 1
                if id.is_empty() || !id.chars().all(|c| c.is_ascii_digit()) {
                    return HttpResponse::BadRequest().finish();
                }
                let resp = vclient().get(format!("https://img.vendor.example.com/p/{}.jpg", id)).send().await; // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
                match resp {
                    Ok(r) => HttpResponse::Ok().content_type("image/jpeg").body(r.bytes().await.unwrap_or_default()),
                    Err(_) => HttpResponse::BadGateway().finish(),
                }
            })))

            .service(web::resource("/drift/lookup-tool").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/outbox/drift/lookup-tool 1
                let raw = json!({ "tool": "lookup", "arg": body["sku"].as_str().unwrap_or("") }).to_string(); // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
                HttpResponse::Ok().json(json!({ "reply": ask_tool(raw).await }))
            })))

    );

    cfg.service(web::resource("/web/ext/plateau/rotate").route(web::get().to(|c: CookieAuth, st: web::Data<Store>| async move { // @@R GET /web/ext/plateau/rotate 1
        let tok = st.open_session(c.0.uid, &c.0.role);
        HttpResponse::NoContent().cookie(Cookie::build("sid", tok).secure(true).http_only(true).same_site(SameSite::Strict).max_age(CookieAge::hours(1)).finish()).finish() // @@T decoy cookie_flags new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
    })));

    cfg.service(web::resource("/auth/spindle-login").wrap(from_fn(login_throttle)).route(web::post().to(|st: web::Data<Store>, body: web::Json<serde_json::Value>| async move { // @@R POST /auth/spindle-login 0 public ; T decoy rate_limit route-level limiter counts login attempts per client address and answers 429 past eight in ten minutes
        if std::env::var("HARROW_PIN").unwrap_or_default().is_empty() || body["pin"].as_str().unwrap_or("") != std::env::var("HARROW_PIN").unwrap_or_default() {
            return HttpResponse::Unauthorized().finish();
        }
        HttpResponse::Ok().json(json!({ "token": st.open_session(40, "clerk") }))
    })));

    cfg.service(web::resource("/web/ext/madder/alias").route(web::post().to(|_c: CookieAuth, req: HttpRequest, body: web::Json<serde_json::Value>| async move { // @@R POST /web/ext/madder/alias 1
        let cookie = req.cookie("csrf").map(|c| c.value().to_string()).unwrap_or_default();
        let tok = req.headers().get("x-csrf-token").and_then(|v| v.to_str().ok()).unwrap_or("");
        if cookie.is_empty() || !same(&cookie, tok) { // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
            return HttpResponse::Forbidden().finish();
        }
        HttpResponse::Ok().json(json!({ "updated": !body["alias"].as_str().unwrap_or("").is_empty() }))
    })));

}
