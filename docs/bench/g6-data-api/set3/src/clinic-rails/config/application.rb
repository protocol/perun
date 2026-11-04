require_relative "boot"
require "rails/all"

Bundler.require(*Rails.groups)

module Clinic
  class Application < Rails::Application
    config.load_defaults 6.0
    config.filter_parameters += [:pin, :card, :holder, :phone, :name, :ssn, :email, :passw, :secret, :token, :_key]
    config.session_store :cookie_store, key: "_clinic", secure: true, httponly: true, same_site: :strict
  end
end
