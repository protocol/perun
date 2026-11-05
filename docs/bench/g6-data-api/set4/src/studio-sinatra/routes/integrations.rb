class App
  group(:bearer!, :throttle!) do
    get '/api/ext/plover/:id/image' do # @@R GET /api/ext/plover/:id/image 1
      halt 400 unless params[:id].match?(/\A[0-9]+\z/)
      content_type 'image/jpeg'
      vget("https://img.vendor.example.com/p/#{params[:id]}.jpg").body # @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id
    end

    get '/api/ext/sparrow/:code/rates' do # @@R GET /api/ext/sparrow/:code/rates 1
      halt 400 unless params[:code].match?(/\A[A-Z]{2}\z/)
      vget("#{VENDOR}/v1/rates/#{params[:code]}", headers: { 'X-Api-Key' => VENDOR_KEY }).body # @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
    end

    get '/api/ext/tundra/:code/stock' do # @@R GET /api/ext/tundra/:code/stock 1
      halt 400 unless params[:code].match?(/\A[A-Z]{2}\z/)
      resp = vget("#{VENDOR}/v1/stock/#{params[:code]}", headers: { 'X-Api-Key' => VENDOR_KEY })
      logger.info("stock lookup code=#{params[:code]} status=#{resp.status}") # @@T decoy secret_in_log only the status and the validated code are logged
      resp.body
    end
  end
end
