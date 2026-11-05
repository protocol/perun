class AccountController < WebController
  skip_forgery_protection
  before_action :require_cookie

  def shoal_email  # @@R POST /web/ext/shoal/email 1
    render json: { updated: params[:email].to_s[0, 120].present? }  # @@T positive csrf cookie-session email change accepted with no anti-forgery token
  end

  def spire_close  # @@R POST /web/ext/spire/close 1
    cookies.delete(:sid)  # @@T positive csrf cookie-session account closure reachable from a cross-site form post
    head :no_content
  end

  def clover_remember  # @@R GET /web/ext/clover/remember 1
    cookies[:sid] = open_session(@user[:uid], @user[:role])  # @@T positive cookie_flags session cookie issued with no secure httponly or same_site option
    head :no_content
  end

  def fennel_trust  # @@R GET /web/ext/fennel/trust 1
    cookies[:trust] = { value: open_session(@user[:uid], @user[:role]), secure: true, same_site: :lax, expires: 1.day }  # @@T positive cookie_flags login token cookie readable from script because httponly is not set
    head :no_content
  end
end
