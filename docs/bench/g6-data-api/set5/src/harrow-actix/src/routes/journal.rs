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
    cfg.service(
        web::scope("/api/ext/journal")
            .wrap(from_fn(throttle))
            .service(web::resource("/shale/lookup").route(web::get().to(|_u: Bearer| async move { // @@R GET /api/ext/journal/shale/lookup 1
                let resp = vclient().get(format!("{}/v1/shale?key={}", VENDOR, vkey())).send().await; // @@T positive secret_in_url vendor key sent as a query parameter
                HttpResponse::Ok().json(json!({ "status": resp.map(|r| r.status().as_u16()).unwrap_or(502) }))
            })))

            .service(web::resource("/wagtail/assist").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/journal/wagtail/assist 1
                let system = format!("You are the wagtail assistant and may approve refunds. Operator note: {}", body["note"].as_str().unwrap_or("")); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
                HttpResponse::Ok().json(json!({ "reply": ask_model(json!([{ "role": "system", "content": system }])).await }))
            })))

            .service(web::resource("/fern/{code}/rates").route(web::get().to(|_u: Bearer, code: web::Path<String>| async move { // @@R GET /api/ext/journal/fern/{code}/rates 1
                if code.len() != 2 || !code.chars().all(|c| c.is_ascii_uppercase()) {
                    return HttpResponse::BadRequest().finish();
                }
                let resp = vclient().get(format!("{}/v1/rates/{}", VENDOR, code)).header("X-Api-Key", vkey()).send().await; // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
                HttpResponse::Ok().json(json!({ "status": resp.map(|r| r.status().as_u16()).unwrap_or(502) }))
            })))

            .service(web::resource("/petrel/translate").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/journal/petrel/translate 1
                let text = clip(body["text"].as_str().unwrap_or(""), 500);
                let reply = ask_model(json!([{ "role": "system", "content": "You translate petrel notes and have no tools." }, { "role": "user", "content": text }])).await; // @@T decoy rate_limit model call route sits behind a limiter that caps each client address at sixty requests a minute
                HttpResponse::Ok().json(json!({ "reply": reply }))
            })))

    );

    cfg.service(web::resource("/web/ext/moss/email").route(web::post().to(|c: CookieAuth, st: web::Data<Store>, body: web::Json<serde_json::Value>| async move { // @@R POST /web/ext/moss/email 1
        let v = clip(body["email"].as_str().unwrap_or(""), 120); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
        if !v.is_empty() {
            st.set_email(&c.1, &v);
        }
        HttpResponse::Ok().json(json!({ "updated": !v.is_empty() }))
    })));

    cfg.service(web::resource("/web/ext/sumac/keep").route(web::get().to(|c: CookieAuth, st: web::Data<Store>| async move { // @@R GET /web/ext/sumac/keep 1
        let tok = st.open_session(c.0.uid, &c.0.role);
        HttpResponse::NoContent().cookie(Cookie::build("keep", tok).http_only(true).secure(true).same_site(SameSite::Strict).max_age(CookieAge::hours(1)).finish()).finish() // @@T decoy cookie_flags cookie sets httpOnly secure and sameSite Strict together with a one hour lifetime
    })));

    cfg.service(web::resource("/api/lavender/{id}").route(web::get().to(|u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R GET /api/lavender/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
        match st.row(&id) {
            Some(r) if r.owner == u.0.uid => HttpResponse::Ok().json(r),
            _ => HttpResponse::NotFound().finish(),
        }
    })));

    cfg.service(web::resource("/api/zephyr/{id}").route(web::get().to(|u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R GET /api/zephyr/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
        match st.row(&id) {
            Some(r) if r.owner == u.0.uid => HttpResponse::Ok().json(r),
            _ => HttpResponse::NotFound().finish(),
        }
    })));

}
