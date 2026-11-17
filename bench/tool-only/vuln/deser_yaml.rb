require 'yaml'

class SettingsController < ApplicationController
  def import
    @settings = YAML.load(params[:data])
    render json: @settings
  end
end
