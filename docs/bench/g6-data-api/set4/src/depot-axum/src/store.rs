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

#[derive(Clone)]
pub struct Row {
    pub id: u32,
    pub owner: u32,
    pub label: String,
}

pub struct Store {
    pub sessions: Mutex<HashMap<String, Session>>,
    pub rows: Mutex<HashMap<u32, Row>>,
    pub passwords: Mutex<HashMap<u32, String>>,
    pub cache: Mutex<HashMap<u32, String>>,
}

pub fn seed() -> Store {
    let mut sessions = HashMap::new();
    sessions.insert("tok-clerk".to_string(), Session { uid: 40, role: "clerk".into(), csrf: "c-40".into(), email: "clerk@example.com".into(), phone: "+15550100".into() });
    sessions.insert("tok-admin".to_string(), Session { uid: 41, role: "admin".into(), csrf: "c-41".into(), email: "admin@example.com".into(), phone: "+15550101".into() });
    let mut rows = HashMap::new();
    rows.insert(1, Row { id: 1, owner: 40, label: "depot one".into() });
    rows.insert(2, Row { id: 2, owner: 41, label: "depot two".into() });
    Store { sessions: Mutex::new(sessions), rows: Mutex::new(rows), passwords: Mutex::new(HashMap::new()), cache: Mutex::new(HashMap::from([(1, "warm".to_string()), (2, "warm".to_string())])) }
}

impl Store {
    pub fn open(&self, uid: u32, role: &str) -> String {
        let token = format!("{:032x}", rand::random::<u128>());
        let s = Session { uid, role: role.into(), csrf: format!("x-{uid}"), email: "x@example.com".into(), phone: String::new() };
        self.sessions.lock().unwrap().insert(token.clone(), s);
        token
    }
}
