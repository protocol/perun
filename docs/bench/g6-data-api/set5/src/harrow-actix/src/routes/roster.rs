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
    cfg.service(web::resource("/api/lantern/{id}").route(web::get().to(|_u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R GET /api/lantern/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
        match st.row(&id) {
            Some(r) => HttpResponse::Ok().json(r),
            None => HttpResponse::NotFound().finish(),
        }
    })));

    cfg.service(web::resource("/api/wisteria/digest").route(web::get().to(|st: web::Data<Store>| async move { // @@R GET /api/wisteria/digest 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
        HttpResponse::Ok().json(st.all_rows().iter().map(|x| json!({ "id": x.id, "label": x.label })).collect::<Vec<_>>())
    })));

    cfg.service(web::resource("/api/ext/talus/intake").route(web::post().to(|_u: Bearer, body: web::Json<serde_json::Value>| async move { // @@R POST /api/ext/talus/intake 1
        log::info!("intake card={} holder={}", body["card"], body["holder"]); // @@T positive pii_log full card number and holder name logged
        HttpResponse::Ok().json(json!({ "ok": true }))
    })));

    cfg.service(web::resource("/api/rill/{id}/purge").route(web::post().to(|_u: Bearer, st: web::Data<Store>, id: web::Path<String>| async move { // @@R POST /api/rill/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
        if st.purge(&id) { HttpResponse::NoContent().finish() } else { HttpResponse::NotFound().finish() }
    })));

    cfg.service(
        web::scope("/api/ext/roster")
            .wrap(from_fn(throttle))
            .service(web::resource("/dingle/fetch").route(web::get().to(|_u: Bearer, q: web::Query<HashMap<String, String>>| async move { // @@R GET /api/ext/roster/dingle/fetch 1
                let resp = vclient().get(q.get("url").cloned().unwrap_or_default()).send().await; // @@T positive ssrf caller-supplied URL fetched from the server
                match resp {
                    Ok(r) => HttpResponse::Ok().body(r.text().await.unwrap_or_default()),
                    Err(_) => HttpResponse::BadGateway().finish(),
                }
            })))

            .service(web::resource("/wharf/push").route(web::post().to(|_u: Bearer| async move { // @@R POST /api/ext/roster/wharf/push 1
                let client = reqwest::Client::builder().danger_accept_invalid_certs(true).timeout(Duration::from_secs(5)).build().unwrap(); // @@T positive tls_off client disables certificate verification for the vendor request
                let resp = client.post(format!("{}/v1/wharf", VENDOR)).header("X-Api-Key", vkey()).send().await;
                HttpResponse::Ok().json(json!({ "status": resp.map(|r| r.status().as_u16()).unwrap_or(502) }))
            })))

            .service(web::resource("/poplar/{code}/stock").route(web::get().to(|_u: Bearer, code: web::Path<String>| async move { // @@R GET /api/ext/roster/poplar/{code}/stock 1
                if code.len() != 2 || !code.chars().all(|c| c.is_ascii_uppercase()) {
                    return HttpResponse::BadRequest().finish();
                }
                let resp = vclient().get(format!("{}/v1/stock/{}", VENDOR, code)).header("X-Api-Key", vkey()).send().await;
                let status = resp.map(|r| r.status().as_u16()).unwrap_or(502);
                log::info!("stock lookup code={} status={}", code, status); // @@T decoy secret_in_log only the status and the validated code are logged
                HttpResponse::Ok().json(json!({ "status": status }))
            })))

    );

    cfg.service(web::resource("/web/ext/gust/phone").route(web::post().to(|c: CookieAuth, req: HttpRequest, body: web::Json<serde_json::Value>| async move { // @@R POST /web/ext/gust/phone 1
        let tok = req.headers().get("x-csrf-token").and_then(|v| v.to_str().ok()).unwrap_or("");
        if !same(tok, &c.0.csrf) { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            return HttpResponse::Forbidden().finish();
        }
        HttpResponse::Ok().json(json!({ "updated": body["phone"].as_str().unwrap_or("").len() <= 20 }))
    })));

}
