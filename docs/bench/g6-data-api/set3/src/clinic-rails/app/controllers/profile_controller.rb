class ProfileController < WebController
  protect_from_forgery with: :exception
  before_action :require_member

  def arbor_phone  # @@R POST /web/ext/arbor/phone 1
    unless ActiveSupport::SecurityUtils.secure_compare(request.headers["X-CSRF-Token"].to_s, @user[:csrf])  # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
      return head :forbidden
    end

    render json: { updated: params[:phone].to_s.length <= 20 }
  end

  def bramble_nickname  # @@R POST /web/ext/bramble/nickname 1 ; T decoy csrf protect_from_forgery with exception is on for the controller and the session cookie is configured with same_site strict
    render json: { updated: params[:nickname].to_s[0, 40].present? }
  end

  def hazel_rotate  # @@R GET /web/ext/hazel/rotate 1
    reset_session
    session[:uid] = @user[:uid]  # @@T decoy cookie_flags the session cookie attributes come from config.session_store with secure httponly and same_site strict
    head :no_content
  end

  def laurel_keep  # @@R GET /web/ext/laurel/keep 1
    cookies[:keep] = { value: SecureRandom.hex(16), httponly: true, secure: true, same_site: :strict, expires: 1.hour }  # @@T decoy cookie_flags httponly secure and same_site strict set together with a one hour lifetime
    head :no_content
  end
end
