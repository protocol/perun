require_relative "boot"
require "rails/all"

Bundler.require(*Rails.groups)

module Clinic
  class Application < Rails::Application
    config.load_defaults 7.2
    config.session_store :cookie_store, key: "_clinic", secure: true, httponly: true, same_site: :strict
  end
end
