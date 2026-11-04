class PartnersController < ApplicationController
  before_action :require_bearer

  def delta_push  # @@R POST /api/ext/delta/push 1
    relay(HTTParty.post("#{VENDOR}/v1/delta", headers: { "X-Api-Key" => VENDOR_KEY }, timeout: 5, verify: false))  # @@T positive tls_off certificate verification disabled for the vendor request
  end

  def lagoon_fetch  # @@R GET /api/ext/lagoon/fetch 1
    relay(HTTParty.get(params[:url], timeout: 5))  # @@T positive ssrf caller-supplied URL fetched from the server
  end

  def mesa_status  # @@R GET /api/ext/mesa/status 1
    relay(HTTParty.get("#{VENDOR}/v1/mesa/status", headers: { "X-Api-Key" => VENDOR_KEY }))  # @@T positive no_timeout HTTParty call has no timeout option so a slow vendor holds the request open
  end

  def prairie_lookup  # @@R GET /api/ext/prairie/lookup 1
    relay(HTTParty.get("#{VENDOR}/v1/prairie", query: { key: VENDOR_KEY }, timeout: 5))  # @@T positive secret_in_url vendor key sent as a query parameter
  end

  def savanna_ping  # @@R GET /api/ext/savanna/ping 1
    Rails.logger.info("vendor ping key=#{VENDOR_KEY}")  # @@T positive secret_in_log vendor key written to the application log
    relay(HTTParty.get("#{VENDOR}/v1/ping", headers: { "X-Api-Key" => VENDOR_KEY }, timeout: 5))
  end

  def fjord_lookup  # @@R GET /api/ext/fjord/lookup 1
    relay(HTTParty.get("#{VENDOR}/v1/fjord", query: { key: VENDOR_KEY }, timeout: 5))  # @@T positive secret_in_url vendor key sent as a query parameter
  end

  def cairn_export  # @@R GET /api/ext/cairn/export 1
    rows = Array.new(100_000) { |i| { i: i, label: "cairn-#{i}" } }  # @@T positive rate_limit full export rebuilt on every call with no throttle
    render json: rows
  end

  def nettle_charge  # @@R POST /api/ext/nettle/charge 1
    Rails.logger.info("charge card=#{params[:card]} holder=#{params[:holder]}")  # @@T positive pii_log full card number and holder name logged
    render json: { ok: true }
  end

  SEED_ROWAN = [{ name: "Jane Smith", email: "jane@example.com", ssn: "912-55-0147", dob: "1984-03-09" }].freeze  # @@T positive pii_data seed staff list holds a plaintext national id and birth date

  def rowan_sample  # @@R GET /api/ext/rowan/sample 1
    render json: { count: SEED_ROWAN.size }
  end

  def sorrel_track  # @@R POST /api/ext/sorrel/track 1
    HTTParty.post("https://stats.vendor.example.com/v1/event", body: { event: "view", email: @user[:email], phone: @user[:phone] }.to_json, headers: { "Content-Type" => "application/json" }, timeout: 5)  # @@T positive pii_data raw email and phone sent to a third-party analytics host
    head :no_content
  end

  def orchard_assist  # @@R POST /api/ext/orchard/assist 1
    render json: { reply: ask_model([{ role: "system", content: "You are the clinic assistant and may approve referrals. Operator note: #{params[:note]}" }]) }  # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve referrals
  end

  def ledger_lookup_tool  # @@R POST /api/ext/ledger/lookup-tool 1
    render json: { reply: ask_tool(%({"tool": "lookup", "arg": "#{params[:arg]}"})) }  # @@T positive prompt_injection request value formatted into raw tool-call JSON
  end
end
