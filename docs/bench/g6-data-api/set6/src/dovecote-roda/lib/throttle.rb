# frozen_string_literal: true

require "active_support"
require "active_support/cache"
require "rack/attack"

Rack::Attack.cache.store = ActiveSupport::Cache::MemoryStore.new

client = ->(req) { req.env["REMOTE_ADDR"] }

ASSIST_PATHS = %w[
  /api/ext/quoll/assist
  /api/ext/rhea/lookup-tool
  /api/ext/tapir/assist
  /api/ext/uguisu/lookup-tool
].freeze

Rack::Attack.throttle("pin", limit: 8, period: 600) do |req|
  client.call(req) if req.post? && req.path == "/auth/xylo-pin"
end

Rack::Attack.throttle("cost", limit: 20, period: 60) do |req|
  client.call(req) if req.post? && (req.path == "/api/ext/xerus/summarise" || ASSIST_PATHS.include?(req.path))
end
