SEED_SPIRE = [{ label: 'Sample studio', region: 'north', count: 3 }].freeze # @@T decoy pii_data seed rows hold labels and counts and no person

class App
  group(:bearer!, :throttle!) do
    get '/api/ext/spire/sample' do # @@R GET /api/ext/spire/sample 1
      { count: SEED_SPIRE.size }.to_json
    end

    post '/api/ext/dune/rotate-key' do # @@R POST /api/ext/dune/rotate-key 1
      key_id = SecureRandom.hex(8)
      logger.info("rotate user=#{@user[:uid]}") # @@T decoy pii_log the log line carries only the numeric user id
      { keyId: key_id }.to_json
    end

    post '/api/ext/shoal/track' do # @@R POST /api/ext/shoal/track 1
      vget('https://stats.vendor.example.com/v1/event', params: { event: 'view' }) # @@T decoy pii_data analytics payload is a constant event name with no user identifier
      status 204
    end
  end
end
