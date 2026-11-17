require 'yaml'

class SettingsController < ApplicationController
  def import
    @settings = YAML.safe_load(params[:data], permitted_classes: [Symbol])
    render json: @settings
  end
end
