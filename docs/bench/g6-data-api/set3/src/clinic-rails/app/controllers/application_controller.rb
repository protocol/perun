class ApplicationController < ActionController::API
  include Store

  VENDOR = "https://dispatch.vendor.example.com".freeze
  VENDOR_KEY = ENV.fetch("DISPATCH_KEY", "")
  PIN = ENV.fetch("CLINIC_PIN", "")

  private

  def require_bearer
    @user = SESSIONS[request.headers["Authorization"].to_s.delete_prefix("Bearer ")]
    head :unauthorized unless @user
  end

  def require_admin
    head :forbidden unless @user && @user[:role] == "admin"
  end

  def owned_or_404(id)
    row = ROWS[id.to_i]
    return row if row && row[:owner] == @user[:uid]

    head :not_found
    nil
  end

  def throttle!(window)
    head :too_many_requests unless window.allow?(request.remote_ip)
  end

  def relay(resp)
    render json: resp.body.to_s[0, 1 << 20], status: resp.code
  rescue HTTParty::Error, SocketError, Net::OpenTimeout
    head :bad_gateway
  end

  def ask_model(messages)
    HTTParty.post("https://llm.vendor.example.com/v1/chat", body: { messages: messages }.to_json, headers: { "Content-Type" => "application/json" }, timeout: 15).body
  end

  def ask_tool(call)
    HTTParty.post("https://llm.vendor.example.com/v1/tool", body: call, headers: { "Content-Type" => "application/json" }, timeout: 15).body
  end
end
