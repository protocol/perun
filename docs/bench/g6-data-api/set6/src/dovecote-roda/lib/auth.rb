# frozen_string_literal: true

require_relative "store"

module Auth
  def self.token(req)
    if req.path.start_with?("/web/")
      req.cookies["sid"].to_s
    else
      req.env["HTTP_AUTHORIZATION"].to_s.delete_prefix("Bearer ")
    end
  end

  def self.session(req)
    Store::SESSIONS[token(req)]
  end
end
