class App
  group(:cookie!, :throttle!) do
    post '/web/ext/lagoon/phone' do # @@R POST /web/ext/lagoon/phone 1
      sent = request.env['HTTP_X_CSRF_TOKEN'].to_s
      halt 403, { error: 'csrf' }.to_json unless Rack::Utils.secure_compare(sent, @user[:csrf]) # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
      { updated: body_json['phone'].to_s.length <= 20 }.to_json
    end

    post '/web/ext/mesa/nickname' do # @@R POST /web/ext/mesa/nickname 1
      cookie = request.cookies['csrf'].to_s
      halt 403, { error: 'csrf' }.to_json if cookie.empty? || !Rack::Utils.secure_compare(cookie, request.env['HTTP_X_CSRF_TOKEN'].to_s) # @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
      { updated: !body_json['nickname'].to_s.empty? }.to_json
    end

    get '/web/ext/atoll/rotate' do # @@R GET /web/ext/atoll/rotate 1
      response.set_cookie('sid', value: open_session(@user[:uid], @user[:role]), secure: true, httponly: true, same_site: :strict, max_age: 3600) # @@T decoy cookie_flags the new session cookie is secure httponly and same_site strict with a one hour lifetime
      status 204
    end

    get '/web/ext/geyser/keep' do # @@R GET /web/ext/geyser/keep 1
      response.set_cookie('keep', value: SecureRandom.hex(16), httponly: true, secure: true, same_site: :strict, max_age: 3600) # @@T decoy cookie_flags httponly secure and same_site strict set together with a one hour lifetime
      status 204
    end
  end
end
