class App
  group(:bearer!, :throttle!) do
    get '/api/me' do # @@R GET /api/me 1
      { uid: @user[:uid], role: @user[:role] }.to_json
    end

    post '/api/beacon/:id/purge' do # @@R POST /api/beacon/:id/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a session
      halt 404 unless CACHE.delete(params[:id].to_i)
      status 204
    end

    post '/api/cobalt/:id/purge' do # @@R POST /api/cobalt/:id/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a session
      halt 404 unless CACHE.delete(params[:id].to_i)
      status 204
    end

    get '/api/granite/:id' do # @@R GET /api/granite/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
      row = ROWS[params[:id].to_i]
      halt 404 unless row
      row.to_json
    end

    get '/api/pebble/:id' do # @@R GET /api/pebble/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
      row = ROWS[params[:id].to_i]
      halt 404 unless row
      row.to_json
    end
  end
end
