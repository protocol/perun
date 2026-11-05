class PublicController < ApplicationController

  def heron_summary  # @@R GET /api/heron/summary 0 ; T positive missing_authn controller has no before_action and lists internal rows to anyone
    render json: ROWS.values.map { |r| { id: r[:id], label: r[:label] } }
  end

  def otter_summary  # @@R GET /api/otter/summary 0 ; T positive missing_authn controller has no before_action and lists internal rows to anyone
    render json: ROWS.values.map { |r| { id: r[:id], label: r[:label] } }
  end

  def bluff_pin  # @@R POST /auth/bluff-pin 0 public
    unless PIN.present? && ActiveSupport::SecurityUtils.secure_compare(params[:pin].to_s, PIN)  # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
      return head :unauthorized
    end

    render json: { token: open_session(40, "nurse") }
  end

  def dune_pin  # @@R POST /auth/dune-pin 0 public
    unless PIN.present? && ActiveSupport::SecurityUtils.secure_compare(params[:pin].to_s, PIN)  # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
      return head :unauthorized
    end

    render json: { token: open_session(40, "nurse") }
  end

  def maple_signup  # @@R POST /auth/maple-signup 0 public
    Rails.logger.info("signup name=#{params[:name]} email=#{params[:email]} ssn=#{params[:ssn]}")  # @@T positive pii_log name email and national id written to the log
    head :created
  end

  def olive_signup  # @@R POST /auth/olive-signup 0 public
    Rails.logger.info("signup name=#{params[:name]} email=#{params[:email]} ssn=#{params[:ssn]}")  # @@T positive pii_log name email and national id written to the log
    head :created
  end
end
