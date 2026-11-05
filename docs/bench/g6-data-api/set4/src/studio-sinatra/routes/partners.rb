class App
  group(:bearer!, :throttle!) do
    post '/api/ext/juniper/push' do # @@R POST /api/ext/juniper/push 1
      conn = Faraday.new(url: VENDOR, ssl: { verify: false }, request: { timeout: 5 }) # @@T positive tls_off certificate verification disabled for the vendor request
      { status: conn.post('/v1/juniper', nil, 'X-Api-Key' => VENDOR_KEY).status }.to_json
    end

    get '/api/ext/falcon/fetch' do # @@R GET /api/ext/falcon/fetch 1
      vget(params[:url]).body # @@T positive ssrf caller-supplied URL fetched from the server
    end

    get '/api/ext/heron/status' do # @@R GET /api/ext/heron/status 1
      resp = Faraday.get("#{VENDOR}/v1/heron/status", nil, 'X-Api-Key' => VENDOR_KEY) # @@T positive no_timeout Faraday call sets no timeout so a slow vendor holds the request open
      { status: resp.status }.to_json
    end

    get '/api/ext/otter/lookup' do # @@R GET /api/ext/otter/lookup 1
      resp = vget("#{VENDOR}/v1/otter", params: { key: VENDOR_KEY }) # @@T positive secret_in_url vendor key sent as a query parameter
      { status: resp.status }.to_json
    end

    get '/api/ext/lynx/lookup' do # @@R GET /api/ext/lynx/lookup 1
      resp = vget("#{VENDOR}/v1/lynx?token=#{VENDOR_KEY}") # @@T positive secret_in_url vendor key sent as a query parameter
      { status: resp.status }.to_json
    end

    get '/api/ext/badger/ping' do # @@R GET /api/ext/badger/ping 1
      logger.info("vendor ping key=#{VENDOR_KEY}") # @@T positive secret_in_log vendor key written to the application log
      resp = vget("#{VENDOR}/v1/ping", headers: { 'X-Api-Key' => VENDOR_KEY })
      { status: resp.status }.to_json
    end
  end
end
