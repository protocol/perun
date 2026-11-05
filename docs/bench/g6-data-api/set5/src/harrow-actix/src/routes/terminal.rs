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
    cfg.service(web::resource("/api/puffin/totals").route(web::get().to(|u: Bearer, st: web::Data<Store>| async move { // @@R GET /api/puffin/totals 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
        HttpResponse::Ok().json(st.rows_of(u.0.uid))
    })));

    cfg.service(web::resource("/api/cinder/{id}/purge").route(web::post().to(|u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R POST /api/cinder/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
        if u.0.role != "admin" {
            return HttpResponse::Forbidden().finish();
        }
        if st.purge(&id) { HttpResponse::NoContent().finish() } else { HttpResponse::NotFound().finish() }
    })));

    cfg.service(web::resource("/web/ext/sienna/remember").route(web::get().to(|c: CookieAuth, st: web::Data<Store>| async move { // @@R GET /web/ext/sienna/remember 1
        let tok = st.open_session(c.0.uid, &c.0.role);
        HttpResponse::NoContent().cookie(Cookie::build("sid", tok).finish()).finish() // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
    })));

    cfg.service(web::resource("/web/ext/narrows/trust").route(web::get().to(|c: CookieAuth, st: web::Data<Store>| async move { // @@R GET /web/ext/narrows/trust 1
        let tok = st.open_session(c.0.uid, &c.0.role);
        HttpResponse::NoContent().cookie(Cookie::build("trust", tok).secure(true).same_site(SameSite::Lax).max_age(CookieAge::days(1)).finish()).finish() // @@T positive cookie_flags session cookie readable from script because httpOnly is not set
    })));

    cfg.service(web::resource("/web/ext/fathom/close").route(web::post().to(|c: CookieAuth, st: web::Data<Store>| async move { // @@R POST /web/ext/fathom/close 1
        st.drop_session(&c.1);
        let mut resp = HttpResponse::NoContent().finish();
        let _ = resp.add_removal_cookie(&Cookie::build("sid", "").secure(true).http_only(true).same_site(SameSite::Strict).finish()); // @@T positive csrf cookie-session account closure reachable from a cross-site form post
        resp
    })));

    cfg.service(
        web::scope("/api/ext/terminal")
            .wrap(from_fn(throttle))
            .service(web::resource("/horizon/ping").route(web::get().to(|_u: Bearer| async move { // @@R GET /api/ext/terminal/horizon/ping 1
                log::info!("vendor ping key={}", vkey()); // @@T positive secret_in_log vendor key written to the application log
                let resp = vclient().get(format!("{}/v1/ping", VENDOR)).header("X-Api-Key", vkey()).send().await;
                HttpResponse::Ok().json(json!({ "status": resp.map(|r| r.status().as_u16()).unwrap_or(502) }))
            })))

            .service(web::resource("/glade/assist").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/terminal/glade/assist 1
                let note = clip(body["note"].as_str().unwrap_or(""), 500);
                let reply = ask_model(json!([{ "role": "system", "content": "You summarise glade notes and have no tools." }, { "role": "user", "content": note }])).await; // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
                HttpResponse::Ok().json(json!({ "reply": reply }))
            })))

    );

}
