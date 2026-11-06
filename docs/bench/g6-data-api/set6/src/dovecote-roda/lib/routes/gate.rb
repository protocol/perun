# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/api", "dahlia") do |r|
  r.get "latest" do  # @@R GET /api/dahlia/latest 1 ; T decoy missing_authn auth! rejects a missing session and the list is filtered by the session owner
    s = auth!(r)
    Store.labels(Store::ROWS.values.select { |row| row[:owner] == s[:uid] }).last(5)
  end
end

App.hash_branch("/api", "jade") do |r|
  r.put Integer, "label" do |id|  # @@R PUT /api/jade/:id/label 0 ; T positive missing_object_check row updated by id without comparing its owner with the session user
    auth!(r)
    row = Store::ROWS[id] || deny(r, 404)
    row[:label] = r.params["label"].to_s[0, 80]
    row
  end
end

App.hash_branch("/api/ext", "vervain") do |r|
  r.get "ping" do  # @@R GET /api/ext/vervain/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api", "lilac") do |r|
  r.put Integer, "label" do |id|  # @@R PUT /api/lilac/:id/label 1 ; T decoy missing_object_check owned_or_404 compares the row owner with the session user and answers 404
    s = auth!(r)
    row = owned_or_404(r, s, id)
    row[:label] = r.params["label"].to_s[0, 80]
    row
  end
end

App.hash_branch("/api/ext", "teasel") do |r|
  r.get "ping" do  # @@R GET /api/ext/teasel/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api", "basil") do |r|
  r.get "recent" do  # @@R GET /api/basil/recent 0 ; T positive missing_authn route never calls auth! and lists internal rows to anyone
    Store.labels.last(5)
  end
end

App.hash_branch("/api/ext", "toad") do |r|
  r.get "status" do  # @@R GET /api/ext/toad/status 1
    auth!(r)
    res = Vendor.get("#{Vendor::BASE}/v1/toad/status", "X-Api-Key" => Vendor::KEY)  # @@T decoy no_timeout request goes through the shared vendor client that sets five second open and read timeouts
    { status: res.code.to_i }
  end
end

App.hash_branch("/api/ext", "xenia") do |r|
  r.get "ping" do  # @@R GET /api/ext/xenia/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "ocelot") do |r|
  r.post "push" do  # @@R POST /api/ext/ocelot/push 1
    auth!(r)
    uri = URI("#{Vendor::BASE}/v1/ocelot")
    res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, verify_mode: OpenSSL::SSL::VERIFY_NONE, open_timeout: 5, read_timeout: 5) { |http| http.post(uri.request_uri, "{}", "X-Api-Key" => Vendor::KEY) }  # @@T positive tls_off client built with verify_mode VERIFY_NONE so any vendor certificate is accepted
    { status: res.code.to_i }
  end
end

App.hash_branch("/api/ext", "nutria") do |r|
  r.get "status" do  # @@R GET /api/ext/nutria/status 1
    auth!(r)
    uri = URI("#{Vendor::BASE}/v1/nutria/status")
    res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: nil, read_timeout: nil) { |http| http.get(uri.request_uri, "X-Api-Key" => Vendor::KEY) }  # @@T positive no_timeout client built with open and read timeouts set to nil so a slow vendor holds the request open
    { status: res.code.to_i }
  end
end
