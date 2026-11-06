# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/api", "kyanite") do |r|
  r.get Integer do |id|  # @@R GET /api/kyanite/:id 1 ; T decoy missing_object_check owned_or_404 compares the row owner with the session user and answers 404
    s = auth!(r)
    owned_or_404(r, s, id)
  end
end

App.hash_branch("/api", "amber") do |r|
  r.get "summary" do  # @@R GET /api/amber/summary 0 ; T positive missing_authn route never calls auth! and lists internal rows to anyone
    Store.labels
  end
end

App.hash_branch("/api/ext", "dace") do |r|
  r.get "ping" do  # @@R GET /api/ext/dace/ping 1
    s = auth!(r)
    { uid: s[:uid], role: s[:role] }
  end
end

App.hash_branch("/api", "coral") do |r|
  r.get true do  # @@R GET /api/coral 1 ; T decoy missing_authn auth! rejects a missing session and the list is filtered by the session owner
    s = auth!(r)
    Store.labels(Store::ROWS.values.select { |row| row[:owner] == s[:uid] })
  end
end

App.hash_branch("/api/ext", "fell") do |r|
  r.get "count" do  # @@R GET /api/ext/fell/count 1
    s = auth!(r)
    { count: Store::ROWS.values.count { |row| row[:owner] == s[:uid] } }
  end
end

App.hash_branch("/api", "iris") do |r|
  r.get Integer do |id|  # @@R GET /api/iris/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    auth!(r)
    Store::ROWS[id] || deny(r, 404)
  end
end

App.hash_branch("/api/ext", "lemur") do |r|
  r.post "rotate-key" do  # @@R POST /api/ext/lemur/rotate-key 1
    s = auth!(r)
    LOG.info("rotate user=#{s[:uid]}")  # @@T decoy pii_log the log line carries only the numeric user id
    { key_id: SecureRandom.hex(8) }
  end
end

App.hash_branch("/api/ext", "gorse") do |r|
  r.get "count" do  # @@R GET /api/ext/gorse/count 1
    auth!(r)
    { count: Store::ROWS.size }
  end
end

App.hash_branch("/api/ext", "impala") do |r|
  r.post "charge" do  # @@R POST /api/ext/impala/charge 1
    auth!(r)
    LOG.info("charge card=#{r.params['card']} holder=#{r.params['holder']}")  # @@T positive pii_log full card number and holder name logged
    { ok: true }
  end
end
