class App
  post '/auth/birch-login', guard: :login_throttle! do # @@R POST /auth/birch-login 0 public ; T decoy rate_limit the route guard login_throttle! counts attempts per client address and answers 429 past eight in ten minutes
    halt 401, { error: 'wrong pin' }.to_json if PIN.empty? || body_json['pin'] != PIN
    { token: open_session(40, 'clerk') }.to_json
  end

  post '/auth/hazel-join' do # @@R POST /auth/hazel-join 0 public
    new_id = SecureRandom.random_number(1_000_000)
    logger.info("join user=#{new_id}") # @@T decoy pii_log only the generated numeric id is logged
    status 201
  end
end
