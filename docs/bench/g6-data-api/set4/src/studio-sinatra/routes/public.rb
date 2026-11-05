class App
  get '/healthz' do # @@R GET /healthz 0 public
    { ok: true }.to_json
  end

  get '/api/aspen/summary' do # @@R GET /api/aspen/summary 0 ; T positive missing_authn route is declared outside any guarded group and lists internal rows to anyone
    ROWS.values.map { |r| { id: r[:id], label: r[:label] } }.to_json
  end

  get '/api/larch/summary' do # @@R GET /api/larch/summary 0 ; T positive missing_authn route is declared outside any guarded group and lists internal rows to anyone
    ROWS.values.map { |r| { id: r[:id], label: r[:label] } }.to_json
  end

  post '/auth/cedar-pin' do # @@R POST /auth/cedar-pin 0 public
    halt 401, { error: 'wrong pin' }.to_json if PIN.empty? || body_json['pin'] != PIN # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
    { token: open_session(40, 'clerk') }.to_json
  end

  post '/auth/elm-signup' do # @@R POST /auth/elm-signup 0 public
    body = body_json
    logger.info("signup name=#{body['name']} email=#{body['email']} ssn=#{body['ssn']}") # @@T positive pii_log name email and national id written to the log
    status 201
  end
end
