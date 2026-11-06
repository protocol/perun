# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/api/ext", "numbat") do |r|
  r.post "track" do  # @@R POST /api/ext/numbat/track 1
    s = auth!(r)
    Vendor.post("https://stats.vendor.example.com/v1/event", JSON.generate(event: "view", email: s[:email], phone: s[:phone]))  # @@T positive pii_data raw email and phone sent to a third-party analytics host
    response.status = 204
    nil
  end
end

SEED_MOLE = [{ name: "Jane Smith", email: "jane@example.com", ssn: "912-55-0147", dob: "1984-03-09" }].freeze  # @@T positive pii_data seed staff list holds a plaintext national id and birth date

App.hash_branch("/api/ext", "mole") do |r|
  r.get "sample" do  # @@R GET /api/ext/mole/sample 1
    auth!(r)
    { count: SEED_MOLE.size }
  end
end

App.hash_branch("/api/ext", "pansy") do |r|
  r.get "ping" do  # @@R GET /api/ext/pansy/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "pika") do |r|
  r.post "track" do  # @@R POST /api/ext/pika/track 1
    auth!(r)
    Vendor.post("https://stats.vendor.example.com/v1/event", JSON.generate(event: "view"))  # @@T decoy pii_data analytics payload is a constant event name with no user identifier
    response.status = 204
    nil
  end
end

SEED_OKAPI = [{ label: "Sample dovecote", region: "north", count: 3 }].freeze  # @@T decoy pii_data seed rows hold labels and counts and no person

App.hash_branch("/api/ext", "okapi") do |r|
  r.get "sample" do  # @@R GET /api/ext/okapi/sample 1
    auth!(r)
    { count: SEED_OKAPI.size }
  end
end
