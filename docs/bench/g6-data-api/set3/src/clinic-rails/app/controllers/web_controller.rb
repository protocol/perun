class WebController < ActionController::Base
  include Store

  private

  def require_cookie
    @user = SESSIONS[cookies[:sid].to_s]
    head :unauthorized unless @user
  end

  def require_member
    @user = USERS[session[:uid]]
    head :unauthorized unless @user
  end
end
