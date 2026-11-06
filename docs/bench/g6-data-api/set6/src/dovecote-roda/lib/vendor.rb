# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require "uri"

module Vendor
  BASE = "https://dispatch.vendor.example.com"
  MODEL = "https://llm.vendor.example.com"
  KEY = ENV.fetch("DOVECOTE_VENDOR_KEY", "")
  PIN = ENV.fetch("DOVECOTE_PIN", "")

  def self.start(uri, **opts, &blk)
    Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == "https", open_timeout: 5, read_timeout: 5, **opts, &blk)
  end

  def self.get(url, headers = {})
    uri = URI(url)
    start(uri) { |http| http.get(uri.request_uri, headers) }
  end

  def self.post(url, body, headers = {})
    uri = URI(url)
    start(uri) { |http| http.post(uri.request_uri, body, { "Content-Type" => "application/json" }.merge(headers)) }
  end

  def self.chat(messages)
    post("#{MODEL}/v1/chat", JSON.generate(messages: messages)).body
  end

  def self.tool(raw)
    post("#{MODEL}/v1/tool", raw).body
  end

  def self.mail(to, subject)
    post("#{BASE}/v1/mail", JSON.generate(to: to, subject: subject), "X-Api-Key" => KEY).code.to_i
  end
end
