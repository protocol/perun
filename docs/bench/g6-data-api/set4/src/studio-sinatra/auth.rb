require_relative 'store'

module Auth
  def bearer!
    @user = SESSIONS[request.env['HTTP_AUTHORIZATION'].to_s.sub('Bearer ', '')]
    halt 401, { error: 'unauthorized' }.to_json unless @user
  end

  def cookie!
    @user = SESSIONS[request.cookies["sid"].to_s]
    halt 401, { error: 'unauthorized' }.to_json unless @user
  end

  def admin?
    @user[:role] == 'admin'
  end

  def owned_or_404(id)
    row = ROWS[id.to_i]
    halt 404, { error: 'not found' }.to_json unless row && row[:owner] == @user[:uid]
    row
  end
end
