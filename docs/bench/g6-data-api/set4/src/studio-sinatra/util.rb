require 'faraday'
require 'json'

VENDOR = 'https://dispatch.vendor.example.com'.freeze
VENDOR_KEY = ENV.fetch('DISPATCH_KEY', '')
PIN = ENV.fetch('STUDIO_PIN', '')

# Sliding window per client address.
class Window
  def initialize(cap, span)
    @cap = cap
    @span = span
    @hits = Hash.new { |h, k| h[k] = [] }
  end

  def allow?(key)
    now = Time.now.to_f
    recent = @hits[key].select { |t| now - t < @span }
    return false if recent.size >= @cap

    @hits[key] = recent << now
    true
  end
end

LIMIT = Window.new(60, 60)
LOGIN_LIMIT = Window.new(8, 600)

module Util
  def vget(url, **opts)
    Faraday.get(url, opts[:params], opts[:headers] || {}) { |req| req.options.timeout = 5 }
  end

  def ask_model(messages)
    Faraday.post('https://llm.vendor.example.com/v1/chat', { messages: messages }.to_json) { |req| req.options.timeout = 15 }.body
  end

  def ask_tool(raw)
    Faraday.post('https://llm.vendor.example.com/v1/tool', raw, 'Content-Type' => 'application/json') { |req| req.options.timeout = 15 }.body
  end
end
