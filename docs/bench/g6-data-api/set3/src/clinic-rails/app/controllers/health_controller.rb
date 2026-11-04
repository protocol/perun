class HealthController < ApplicationController
  def show  # @@R GET /healthz 0 public
    render json: { ok: true }
  end
end
