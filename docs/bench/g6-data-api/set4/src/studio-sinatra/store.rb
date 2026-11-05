require 'securerandom'

SESSIONS = {
  'tok-clerk' => { uid: 40, role: 'clerk', csrf: 'c-40', email: 'clerk@example.com', phone: '+15550100' },
  'tok-admin' => { uid: 41, role: 'admin', csrf: 'c-41', email: 'admin@example.com', phone: '+15550101' }
}
CACHE = { 1 => "warm", 2 => "warm" }
ROWS = {
  1 => { id: 1, owner: 40, label: 'studio one' },
  2 => { id: 2, owner: 41, label: 'studio two' }
}

def open_session(uid, role)
  token = SecureRandom.hex(24)
  SESSIONS.merge!(token => { uid: uid, role: role, csrf: SecureRandom.hex(16), email: 'x@example.com', phone: '' })
  token
end
