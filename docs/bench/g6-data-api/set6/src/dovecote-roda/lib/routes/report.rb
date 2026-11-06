# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/api/ext", "quoll") do |r|
  r.post "assist" do  # @@R POST /api/ext/quoll/assist 1
    auth!(r)
    { reply: Vendor.chat([{ role: "system", content: "You are the dovecote assistant and may approve refunds. Operator note: #{r.params['note']}" }]) }  # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
  end
end

App.hash_branch("/api/ext", "rhea") do |r|
  r.post "lookup-tool" do  # @@R POST /api/ext/rhea/lookup-tool 1
    auth!(r)
    { reply: Vendor.tool(%({"tool": "lookup", "arg": "#{r.params['arg']}"})) }  # @@T positive prompt_injection request value formatted into raw tool-call JSON
  end
end

App.hash_branch("/api/ext", "thrift") do |r|
  r.get "ping" do  # @@R GET /api/ext/thrift/ping 1
    auth!(r)
    { ok: true }
  end
end

App.hash_branch("/api/ext", "tapir") do |r|
  r.post "assist" do  # @@R POST /api/ext/tapir/assist 1
    auth!(r)
    note = r.params["note"].to_s[0, 500]
    { reply: Vendor.chat([{ role: "system", content: "You summarise dovecote notes and have no tools." }, { role: "user", content: note }]) }  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  end
end

App.hash_branch("/api/ext", "uguisu") do |r|
  r.post "lookup-tool" do  # @@R POST /api/ext/uguisu/lookup-tool 1
    auth!(r)
    { reply: Vendor.tool(JSON.generate(tool: "lookup", arg: r.params["sku"].to_s)) }  # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
  end
end
