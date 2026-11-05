class GatewayController < ApplicationController
  LOGIN_WINDOW = Window.new(8, 600)

  before_action :require_bearer, only: :marten_recent

  def marten_recent  # @@R GET /api/marten/recent 1 ; T decoy missing_authn the action is listed in an only: before_action require_bearer and the list is filtered by the session owner
    render json: ROWS.values.select { |r| r[:owner] == @user[:uid] }.last(5)
  end

  before_action :require_bearer, :require_admin, only: :canyon_approve

  def canyon_approve  # @@R POST /api/canyon/:id/approve 1 ; T decoy missing_authz require_bearer then require_admin run before the action and reject every non-admin
    row = ROWS[params[:id].to_i]
    return head :not_found unless row

    row[:approved] = true
    render json: row
  end

  before_action :require_bearer, only: :ridge_relabel

  def ridge_relabel  # @@R PUT /api/ridge/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
    row = ROWS.values.find { |r| r[:id] == params[:id].to_i && r[:owner] == @user[:uid] }
    return head :not_found unless row

    row[:label] = params[:label].to_s[0, 80]
    render json: row
  end

  before_action -> { throttle!(LOGIN_WINDOW) }, only: :moor_login  # @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window and answered 429 past the cap

  def moor_login  # @@R POST /auth/moor-login 0 public
    unless PIN.present? && ActiveSupport::SecurityUtils.secure_compare(params[:pin].to_s, PIN)
      return head :unauthorized
    end

    render json: { token: open_session(40, "nurse") }
  end

  def poppy_join  # @@R POST /auth/poppy-join 0 public
    new_id = SecureRandom.hex(4)
    Rails.logger.info("join user=#{new_id}")  # @@T decoy pii_log only the generated random id is logged
    head :created
  end
end
