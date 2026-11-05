use axum::{extract::{ConnectInfo, Request, State}, http::StatusCode, middleware::Next, response::Response};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub const VENDOR: &str = "https://dispatch.vendor.example.com";

pub fn vendor_key() -> String { std::env::var("DISPATCH_KEY").unwrap_or_default() }
pub fn pin() -> String { std::env::var("DEPOT_PIN").unwrap_or_default() }

pub fn http() -> reqwest::Client {
    reqwest::Client::builder().timeout(Duration::from_secs(5)).build().unwrap()
}

/// Per-client-address sliding window.
pub struct Window { cap: usize, span: Duration, hits: Mutex<HashMap<String, Vec<Instant>>> }

impl Window {
    pub fn new(cap: usize, span_secs: u64) -> Arc<Self> {
        Arc::new(Self { cap, span: Duration::from_secs(span_secs), hits: Mutex::new(HashMap::new()) })
    }

    fn allow(&self, key: &str) -> bool {
        let now = Instant::now();
        let mut map = self.hits.lock().unwrap();
        let recent = map.entry(key.to_string()).or_default();
        recent.retain(|t| now.duration_since(*t) < self.span);
        if recent.len() >= self.cap { return false; }
        recent.push(now);
        true
    }
}

pub async fn throttle(State(w): State<Arc<Window>>, ConnectInfo(addr): ConnectInfo<SocketAddr>, req: Request, next: Next) -> Result<Response, StatusCode> {
    if !w.allow(&addr.ip().to_string()) { return Err(StatusCode::TOO_MANY_REQUESTS); }
    Ok(next.run(req).await)
}

pub async fn ask_model(messages: Vec<Value>) -> Value {
    let resp = http().post("https://llm.vendor.example.com/v1/chat").json(&json!({ "messages": messages })).send().await.unwrap();
    resp.json().await.unwrap_or_default()
}

pub async fn ask_tool(raw: String) -> Value {
    let resp = http().post("https://llm.vendor.example.com/v1/tool").header("content-type", "application/json").body(raw).send().await.unwrap();
    resp.json().await.unwrap_or_default()
}
