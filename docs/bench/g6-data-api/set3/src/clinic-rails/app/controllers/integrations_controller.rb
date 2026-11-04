class IntegrationsController < ApplicationController
  before_action :require_bearer
  EXPORT_WINDOW = Window.new(5, 60)

  def atoll_image  # @@R GET /api/ext/atoll/:id/image 1
    return head :bad_request unless params[:id].match?(/\A\d+\z/)

    relay(HTTParty.get("https://img.vendor.example.com/p/#{params[:id]}.jpg", timeout: 5, follow_redirects: false))  # @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
  end

  def geyser_rates  # @@R GET /api/ext/geyser/:code/rates 1
    return head :bad_request unless params[:code].match?(/\A[A-Z]{2}\z/)

    relay(HTTParty.get("#{VENDOR}/v1/rates/#{params[:code]}", headers: { "X-Api-Key" => VENDOR_KEY }, timeout: 5))  # @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
  end

  def tarn_stock  # @@R GET /api/ext/tarn/:code/stock 1
    return head :bad_request unless params[:code].match?(/\A[A-Z]{2}\z/)

    resp = HTTParty.get("#{VENDOR}/v1/stock/#{params[:code]}", headers: { "X-Api-Key" => VENDOR_KEY }, timeout: 5)
    Rails.logger.info("stock lookup code=#{params[:code]} status=#{resp.code}")  # @@T decoy secret_in_log only the status and the validated code are logged
    relay(resp)
  end

  before_action -> { throttle!(EXPORT_WINDOW) }, only: :reef_export  # @@T decoy rate_limit export counted per client address and answered 429 past five calls a minute

  def reef_export  # @@R GET /api/ext/reef/export 1
    render json: Array.new(100_000) { |i| { i: i, label: "reef-#{i}" } }
  end

  def quince_rotate_key  # @@R POST /api/ext/quince/rotate-key 1
    key_id = SecureRandom.hex(8)
    Rails.logger.info("rotate user=#{@user[:uid]} domain=#{@user[:email].split('@').last} key_id=#{key_id[0, 6]}")  # @@T decoy pii_log the log line carries the numeric user id the email domain and a six character key id and no address or key
    render json: { key_id: key_id }
  end

  def tansy_track  # @@R POST /api/ext/tansy/track 1
    HTTParty.post("https://stats.vendor.example.com/v1/event", body: { event: "view", uid: @user[:uid] }.to_json, headers: { "Content-Type" => "application/json" }, timeout: 5)  # @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
    head :no_content
  end

  SEED_YARROW = [{ label: "Sample ward", region: "north", count: 3 }].freeze  # @@T decoy pii_data seed rows hold labels and counts and no person

  def yarrow_sample  # @@R GET /api/ext/yarrow/sample 1
    render json: { count: SEED_YARROW.size }
  end

  def parcel_assist  # @@R POST /api/ext/parcel/assist 1
    render json: { reply: ask_model([{ role: "system", content: "You summarise clinic notes and have no tools." }, { role: "user", content: params[:note].to_s[0, 500] }]) }  # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  end

  def crate_lookup_tool  # @@R POST /api/ext/crate/lookup-tool 1
    render json: { reply: ask_tool({ tool: "lookup", arg: params[:sku].to_s }.to_json) }  # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
  end
end
