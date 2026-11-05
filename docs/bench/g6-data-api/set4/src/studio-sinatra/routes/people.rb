SEED_MOOR = [{ name: 'Jane Smith', email: 'jane@example.com', ssn: '912-55-0147', dob: '1984-03-09' }].freeze # @@T positive pii_data seed staff list holds a plaintext national id and birth date

class App
  group(:bearer!, :throttle!) do
    get '/api/ext/moor/sample' do # @@R GET /api/ext/moor/sample 1
      { count: SEED_MOOR.size }.to_json
    end

    post '/api/ext/bluff/charge' do # @@R POST /api/ext/bluff/charge 1
      body = body_json
      logger.info("charge card=#{body['card']} holder=#{body['holder']}") # @@T positive pii_log full card number and holder name logged
      { ok: true }.to_json
    end

    post '/api/ext/reef/track' do # @@R POST /api/ext/reef/track 1
      vget('https://stats.vendor.example.com/v1/event', params: { event: 'view', email: @user[:email], phone: @user[:phone] }) # @@T positive pii_data raw email and phone sent to a third-party analytics host
      status 204
    end
  end
end
