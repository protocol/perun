# frozen_string_literal: true

require_relative "lib/app"
require_relative "lib/throttle"

use Rack::Attack
run App.freeze.app
