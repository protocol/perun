module Store
  SESSIONS = {
    "tok-nurse" => { uid: 40, role: "nurse", csrf: "c-40", email: "nurse@example.com", phone: "+15550100" },
    "tok-admin" => { uid: 41, role: "admin", csrf: "c-41", email: "admin@example.com", phone: "+15550101" }
  }
  USERS = SESSIONS.values.to_h { |s| [s[:uid], s] }
  ROWS = {
    1 => { id: 1, owner: 40, label: "ward one" },
    2 => { id: 2, owner: 41, label: "ward two" }
  }

  def open_session(uid, role)
    token = SecureRandom.hex(24)
    SESSIONS[token] = { uid: uid, role: role, csrf: SecureRandom.hex(16), email: "x@example.com", phone: "" }
    token
  end
end
