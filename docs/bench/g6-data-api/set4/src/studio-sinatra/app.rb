require 'sinatra/base'
require_relative 'auth'
require_relative 'util'

class App < Sinatra::Base
  enable :logging
  helpers Auth, Util

  set(:guard) { |*kinds| condition { kinds.flatten.each { |k| send(k) } } }

  helpers do
    def throttle!
      halt 429, { error: 'too many requests' }.to_json unless LIMIT.allow?(request.env["REMOTE_ADDR"])
    end

    def login_throttle!
      halt 429, { error: 'too many requests' }.to_json unless LOGIN_LIMIT.allow?(request.env["REMOTE_ADDR"])
    end

    def body_json
      JSON.parse(request.body.read)
    end
  end

  before { content_type :json }

  def self.group(*kinds)
    @group_guards = kinds
    yield
  ensure
    @group_guards = nil
  end

  def self.route(verb, path, options = {}, &block)
    options = options.merge(guard: @group_guards) if @group_guards
    super(verb, path, options, &block)
  end
end

%w[public gateway desk records catalog partners integrations people members assist copilot web console].each do |name|
  require_relative "routes/#{name}"
end
