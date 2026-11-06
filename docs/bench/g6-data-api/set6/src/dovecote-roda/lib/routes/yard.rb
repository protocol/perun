# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/api", "fig") do |r|
  r.post Integer, "restore" do |id|  # @@R POST /api/fig/:id/restore 0 ; T positive missing_authz restore is an admin action but the route only calls auth! and never checks the role
    auth!(r)
    Store::CACHE.key?(id) || deny(r, 404)
    Store::CACHE[id] = "warm"
    { id: id, state: "warm" }
  end
end

App.hash_branch("/api", "elder") do |r|
  r.post Integer, "archive" do |id|  # @@R POST /api/elder/:id/archive 0 ; T positive missing_authz archive is an admin action but the route only calls auth! and never checks the role
    auth!(r)
    Store::CACHE.key?(id) || deny(r, 404)
    Store::CACHE[id] = "archived"
    { id: id, state: "archived" }
  end
end

App.hash_branch("/api/ext", "ibex") do |r|
  r.get "ping" do  # @@R GET /api/ext/ibex/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "hawk") do |r|
  r.get "ping" do  # @@R GET /api/ext/hawk/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "magpie") do |r|
  r.get "fetch" do  # @@R GET /api/ext/magpie/fetch 1
    auth!(r)
    Vendor.get(r.params["url"].to_s).body  # @@T positive ssrf caller-supplied URL fetched from the server
  end
end

App.hash_branch("/api/ext", "heron") do |r|
  r.get "ping" do  # @@R GET /api/ext/heron/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api", "garnet") do |r|
  r.delete Integer do |id|  # @@R DELETE /api/garnet/:id 1 ; T decoy missing_authz admin! answers 403 to every role except admin before the delete
    admin!(r)
    Store::CACHE.delete(id) ? { deleted: id } : deny(r, 404)
  end
end

App.hash_branch("/api/ext", "swift") do |r|
  r.get "ping" do  # @@R GET /api/ext/swift/ping 1
    auth!(r)
    res = Vendor.get("#{Vendor::BASE}/v1/swift/ping", "X-Api-Key" => Vendor::KEY)
    LOG.info("vendor ping status=#{res.code}")  # @@T decoy secret_in_log the log line carries only the response status and the key travels in a header
    { status: res.code.to_i }
  end
end

App.hash_branch("/api", "hazel") do |r|
  r.post Integer, "publish" do |id|  # @@R POST /api/hazel/:id/publish 1 ; T decoy missing_authz admin! answers 403 to every role except admin before the update
    admin!(r)
    Store::CACHE.key?(id) || deny(r, 404)
    Store::CACHE[id] = "published"
    { id: id, state: "published" }
  end
end
