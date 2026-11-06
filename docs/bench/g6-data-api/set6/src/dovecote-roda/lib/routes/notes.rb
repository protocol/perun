# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/auth", "xylo-pin") do |r|
  r.post true do  # @@R POST /auth/xylo-pin 0 public
    pin = r.params["pin"].to_s
    if Vendor::PIN.empty? || !Rack::Utils.secure_compare(pin, Vendor::PIN)  # @@T decoy rate_limit pin attempts are counted per socket address by the pin throttle and answered 429 past eight in ten minutes
      response.status = 401
      next({ error: "denied" })
    end
    { token: Store.open_session(40, "clerk") }
  end
end

App.hash_branch("/auth", "vole-pin") do |r|
  r.post true do  # @@R POST /auth/vole-pin 0 public
    pin = r.params["pin"].to_s
    if Vendor::PIN.empty? || !Rack::Utils.secure_compare(pin, Vendor::PIN)  # @@T positive rate_limit pin can be retried indefinitely because the throttle config has no entry for this path
      response.status = 401
      next({ error: "denied" })
    end
    { token: Store.open_session(40, "clerk") }
  end
end

App.hash_branch("healthz") do |r|
  r.get true do  # @@R GET /healthz 0 public
    { ok: true }
  end
end

App.hash_branch("/auth", "kudu-join") do |r|
  r.post true do  # @@R POST /auth/kudu-join 0 public
    new_id = Store::SESSIONS.size + 1000
    LOG.info("join user=#{new_id}")  # @@T decoy pii_log only the generated numeric id is logged
    response.status = 201
    { ok: true }
  end
end

App.hash_branch("/api/ext", "orris") do |r|
  r.get "ping" do  # @@R GET /api/ext/orris/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/auth", "jerboa-signup") do |r|
  r.post true do  # @@R POST /auth/jerboa-signup 0 public
    LOG.info("signup name=#{r.params['name']} email=#{r.params['email']} ssn=#{r.params['ssn']}")  # @@T positive pii_log name email and national id written to the log
    response.status = 201
    { ok: true }
  end
end

App.hash_branch("/api/ext", "narwhal") do |r|
  r.post "refer" do  # @@R POST /api/ext/narwhal/refer 1
    auth!(r)
    LOG.info("referral to=#{r.params['to']}")  # @@T positive pii_log referred email address written to the application log
    { ok: true }
  end
end
