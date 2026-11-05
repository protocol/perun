class App
  group(:cookie!, :throttle!) do
    post '/web/ext/ridge/email' do # @@R POST /web/ext/ridge/email 1
      email = body_json['email'].to_s[0, 120] # @@T positive csrf cookie-session email change accepted with no anti-forgery token
      SESSIONS.each_value { |s| s[:email] = email if s[:uid] == @user[:uid] } unless email.empty?
      { updated: !email.empty? }.to_json
    end

    post '/web/ext/delta/close' do # @@R POST /web/ext/delta/close 1
      SESSIONS.delete_if { |_, s| s[:uid] == @user[:uid] }
      response.delete_cookie('sid') # @@T positive csrf cookie-session account closure reachable from a cross-site form post
      status 204
    end

    get '/web/ext/prairie/remember' do # @@R GET /web/ext/prairie/remember 1
      response.set_cookie('sid', value: open_session(@user[:uid], @user[:role])) # @@T positive cookie_flags session cookie issued with no secure httponly or same_site option
      status 204
    end

    get '/web/ext/savanna/trust' do # @@R GET /web/ext/savanna/trust 1
      response.set_cookie('trust', value: open_session(@user[:uid], @user[:role]), secure: true, same_site: :lax, max_age: 86_400) # @@T positive cookie_flags login token cookie readable from script because httponly is not set
      status 204
    end
  end
end
