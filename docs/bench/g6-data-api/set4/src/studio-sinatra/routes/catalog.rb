class App
  group(:bearer!, :throttle!) do
    get '/api/compass' do # @@R GET /api/compass 1 ; T decoy missing_authn the group runs bearer! before the handler and the list is filtered by the session owner
      ROWS.values.select { |r| r[:owner] == @user[:uid] }.to_json
    end

    get '/api/recent' do # @@R GET /api/recent 1 ; T decoy missing_authn the group runs bearer! before the handler and the list is filtered by the session owner
      ROWS.values.select { |r| r[:owner] == @user[:uid] }.last(5).to_json
    end

    delete '/api/copper/:id' do # @@R DELETE /api/copper/:id 1 ; T decoy missing_authz the handler answers 403 for every other role before the delete
      halt 403, { error: 'forbidden' }.to_json unless admin?
      halt 404 unless ROWS.delete(params[:id].to_i)
      status 204
    end

    post '/api/timber/:id/approve' do # @@R POST /api/timber/:id/approve 1 ; T decoy missing_authz the handler answers 403 for every other role before the update
      halt 403, { error: 'forbidden' }.to_json unless admin?
      row = ROWS[params[:id].to_i]
      halt 404 unless row
      row[:approved] = true
      row.to_json
    end

    get '/api/thistle/:id' do # @@R GET /api/thistle/:id 1 ; T decoy missing_object_check owned_or_404 compares the owner with the session user and answers 404
      owned_or_404(params[:id]).to_json
    end

    put '/api/willow/:id/label' do # @@R PUT /api/willow/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
      row = ROWS.values.find { |r| r[:id].to_s == params[:id] && r[:owner] == @user[:uid] }
      halt 404 unless row
      row[:label] = body_json['label'].to_s[0, 80]
      row.to_json
    end
  end
end
