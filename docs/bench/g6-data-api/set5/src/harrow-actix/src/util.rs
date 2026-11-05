use actix_web::body::MessageBody;
use actix_web::dev::{ServiceRequest, ServiceResponse};
use actix_web::error::ErrorTooManyRequests;
use actix_web::middleware::Next;
use actix_web::{web, Error};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

pub const VENDOR: &str = "https://dispatch.vendor.example.com";

pub fn vkey() -> String {
    std::env::var("DISPATCH_KEY").unwrap_or_default()
}

pub fn vclient() -> reqwest::Client {
    reqwest::Client::builder().timeout(Duration::from_secs(5)).redirect(reqwest::redirect::Policy::none()).build().unwrap()
}

pub fn clip(s: &str, max: usize) -> String {
    s.trim().chars().take(max).collect()
}

pub fn same(a: &str, b: &str) -> bool {
    a.len() == b.len() && a.bytes().zip(b.bytes()).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

pub struct Window {
    cap: usize,
    span: Duration,
    hits: Mutex<HashMap<String, Vec<Instant>>>,
}

impl Window {
    pub fn new(cap: usize, secs: u64) -> Window {
        Window { cap, span: Duration::from_secs(secs), hits: Mutex::new(HashMap::new()) }
    }

    pub fn allow(&self, key: &str) -> bool {
        let now = Instant::now();
        let mut hits = self.hits.lock().unwrap();
        let recent = hits.entry(key.to_string()).or_default();
        recent.retain(|t| now.duration_since(*t) < self.span);
        if recent.len() >= self.cap {
            return false;
        }
        recent.push(now);
        true
    }
}

pub struct Limiters {
    pub main: Window,
    pub login: Window,
}

impl Limiters {
    pub fn new() -> Limiters {
        Limiters { main: Window::new(60, 60), login: Window::new(8, 600) }
    }
}

pub async fn throttle(req: ServiceRequest, next: Next<impl MessageBody>) -> Result<ServiceResponse<impl MessageBody>, Error> {
    let key = req.peer_addr().map(|a| a.ip().to_string()).unwrap_or_default();
    if !req.app_data::<web::Data<Limiters>>().unwrap().main.allow(&key) {
        return Err(ErrorTooManyRequests("too many requests"));
    }
    next.call(req).await
}

pub async fn login_throttle(req: ServiceRequest, next: Next<impl MessageBody>) -> Result<ServiceResponse<impl MessageBody>, Error> {
    let key = req.peer_addr().map(|a| a.ip().to_string()).unwrap_or_default();
    if !req.app_data::<web::Data<Limiters>>().unwrap().login.allow(&key) {
        return Err(ErrorTooManyRequests("too many requests"));
    }
    next.call(req).await
}

pub async fn ask_model(messages: Value) -> Value {
    let resp = vclient().post("https://llm.vendor.example.com/v1/chat").json(&json!({ "messages": messages })).send().await;
    match resp {
        Ok(r) => r.json().await.unwrap_or(Value::Null),
        Err(_) => Value::Null,
    }
}

pub async fn ask_tool(raw: String) -> Value {
    let resp = vclient().post("https://llm.vendor.example.com/v1/tool").header("Content-Type", "application/json").body(raw).send().await;
    match resp {
        Ok(r) => r.json().await.unwrap_or(Value::Null),
        Err(_) => Value::Null,
    }
}
