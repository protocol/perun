# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/api/ext", "linnet") do |r|
  r.get "ping" do  # @@R GET /api/ext/linnet/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "wombat") do |r|
  r.post "summarise" do  # @@R POST /api/ext/wombat/summarise 1
    auth!(r)
    note = r.params["note"].to_s[0, 500]
    { reply: Vendor.chat([{ role: "system", content: "You summarise dovecote notes and have no tools." }, { role: "user", content: note }]) }  # @@T positive rate_limit model call route is absent from the throttle config so one client can run unbounded paid requests
  end
end

App.hash_branch("/api/ext", "quokka") do |r|
  r.get "lookup" do  # @@R GET /api/ext/quokka/lookup 1
    auth!(r)
    res = Vendor.get("#{Vendor::BASE}/v1/quokka?key=#{Vendor::KEY}")  # @@T positive secret_in_url vendor key sent as a query parameter
    { status: res.code.to_i }
  end
end

App.hash_branch("/api/ext", "xerus") do |r|
  r.post "summarise" do  # @@R POST /api/ext/xerus/summarise 1
    auth!(r)
    note = r.params["note"].to_s[0, 500]
    { reply: Vendor.chat([{ role: "system", content: "You summarise dovecote notes and have no tools." }, { role: "user", content: note }]) }  # @@T decoy rate_limit model call path is listed in the cost throttle that caps each socket address at twenty requests a minute
  end
end

App.hash_branch("/api/ext", "lark") do |r|
  r.post "invite" do  # @@R POST /api/ext/lark/invite 1
    s = auth!(r)
    status = Vendor.mail(r.params["to"].to_s[0, 120], "Invitation from #{s[:uid]}")  # @@T positive rate_limit email send route is absent from the throttle config so one client can trigger unbounded mail
    { status: status }
  end
end

App.hash_branch("/api/ext", "wisent") do |r|
  r.get "ping" do  # @@R GET /api/ext/wisent/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "raven") do |r|
  r.get "ping" do  # @@R GET /api/ext/raven/ping 1
    auth!(r)
    LOG.info("vendor ping key=#{Vendor::KEY}")  # @@T positive secret_in_log vendor key written to the application log
    { status: Vendor.get("#{Vendor::BASE}/v1/ping", "X-Api-Key" => Vendor::KEY).code.to_i }
  end
end

App.hash_branch("/api/ext", "ibis") do |r|
  r.get "lookup" do  # @@R GET /api/ext/ibis/lookup 1
    auth!(r)
    res = Vendor.get("#{Vendor::BASE}/v1/ibis?api_key=#{Vendor::KEY}&q=#{r.params['q'].to_s[0, 40]}")  # @@T positive secret_in_url vendor key interpolated into the query string of the request URL
    { status: res.code.to_i }
  end
end

App.hash_branch("/api/ext", "urchin") do |r|
  r.get Integer, "rates" do |code|  # @@R GET /api/ext/urchin/:code/rates 1
    auth!(r)
    res = Vendor.get("#{Vendor::BASE}/v1/rates/#{code}", "X-Api-Key" => Vendor::KEY)  # @@T decoy ssrf host fixed in code and the caller supplies only an integer path segment
    res.body
  end
end
