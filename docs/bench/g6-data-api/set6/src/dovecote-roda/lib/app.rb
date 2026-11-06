# frozen_string_literal: true

require "logger"
require "roda"
require_relative "auth"
require_relative "store"
require_relative "vendor"

LOG = Logger.new($stdout, level: ENV.fetch("DOVECOTE_LOG_LEVEL", "info"))

class App < Roda
  plugin :json
  plugin :json_parser
  plugin :all_verbs
  plugin :hash_branches

  def deny(r, code)
    r.halt([code, { "content-type" => "application/json" }, [JSON.generate(error: "denied")]])
  end

  def auth!(r)
    Auth.session(r) || deny(r, 401)
  end

  def admin!(r)
    s = auth!(r)
    s[:role] == "admin" ? s : deny(r, 403)
  end

  def owned_or_404(r, s, id)
    row = Store::ROWS[id]
    row && row[:owner] == s[:uid] ? row : deny(r, 404)
  end

  hash_branch("api") { |r| r.hash_branches("/api") }
  hash_branch("/api", "ext") { |r| r.hash_branches("/api/ext") }
  hash_branch("web") { |r| r.hash_branches("/web") }
  hash_branch("/web", "ext") { |r| r.hash_branches("/web/ext") }
  hash_branch("/web", "pref") { |r| r.hash_branches("/web/pref") }
  hash_branch("auth") { |r| r.hash_branches("/auth") }

  route do |r|
    r.hash_branches
  end
end

Dir[File.join(__dir__, "routes", "*.rb")].sort.each { |f| require f }
