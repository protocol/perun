use rand::{distributions::Alphanumeric, Rng};
use serde::Serialize;
use std::collections::HashMap;
use std::sync::Mutex;

#[derive(Clone)]
pub struct Session {
    pub uid: u32,
    pub role: String,
    pub csrf: String,
    pub email: String,
    pub phone: String,
}

#[derive(Clone, Serialize)]
pub struct Row {
    pub id: u32,
    pub owner: u32,
    pub label: String,
}

pub struct Store {
    sessions: Mutex<HashMap<String, Session>>,
    rows: Mutex<HashMap<String, Row>>,
    cache: Mutex<HashMap<String, String>>,
}

impl Store {
    pub fn seed() -> Store {
        let mut sessions = HashMap::new();
        sessions.insert("tok-clerk".to_string(), Session { uid: 40, role: "clerk".into(), csrf: "c-40".into(), email: "clerk@example.com".into(), phone: "+15550100".into() });
        sessions.insert("tok-admin".to_string(), Session { uid: 41, role: "admin".into(), csrf: "c-41".into(), email: "admin@example.com".into(), phone: "+15550101".into() });
        let mut rows = HashMap::new();
        rows.insert("1".to_string(), Row { id: 1, owner: 40, label: "harrow one".into() });
        rows.insert("2".to_string(), Row { id: 2, owner: 41, label: "harrow two".into() });
        let cache = HashMap::from([("1".to_string(), "warm".to_string()), ("2".to_string(), "warm".to_string())]);
        Store { sessions: Mutex::new(sessions), rows: Mutex::new(rows), cache: Mutex::new(cache) }
    }

    pub fn session(&self, tok: &str) -> Option<Session> {
        self.sessions.lock().unwrap().get(tok).cloned()
    }

    pub fn open_session(&self, uid: u32, role: &str) -> String {
        let tok: String = rand::thread_rng().sample_iter(&Alphanumeric).take(48).map(char::from).collect();
        let csrf: String = rand::thread_rng().sample_iter(&Alphanumeric).take(32).map(char::from).collect();
        let sess = Session { uid, role: role.to_string(), csrf, email: "x@example.com".into(), phone: String::new() };
        self.sessions.lock().unwrap().insert(tok.clone(), sess);
        tok
    }

    pub fn drop_session(&self, tok: &str) {
        self.sessions.lock().unwrap().remove(tok);
    }

    pub fn set_email(&self, tok: &str, email: &str) {
        if let Some(s) = self.sessions.lock().unwrap().get_mut(tok) {
            s.email = email.to_string();
        }
    }

    pub fn all_rows(&self) -> Vec<Row> {
        self.rows.lock().unwrap().values().cloned().collect()
    }

    pub fn rows_of(&self, owner: u32) -> Vec<Row> {
        self.all_rows().into_iter().filter(|r| r.owner == owner).collect()
    }

    pub fn row(&self, id: &str) -> Option<Row> {
        self.rows.lock().unwrap().get(id).cloned()
    }

    pub fn purge(&self, id: &str) -> bool {
        self.cache.lock().unwrap().remove(id).is_some()
    }
}
