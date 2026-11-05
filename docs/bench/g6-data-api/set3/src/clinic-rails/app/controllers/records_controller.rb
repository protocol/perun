class RecordsController < ApplicationController
  before_action :require_bearer

  def me  # @@R GET /api/me 1
    render json: { uid: @user[:uid], role: @user[:role] }
  end

  def plover_purge  # @@R POST /api/plover/:id/purge 0 ; T positive missing_authz purge is an admin action but the controller only requires a bearer session
    return head :not_found unless ROWS.delete(params[:id].to_i)

    head :no_content
  end

  def sparrow_purge  # @@R POST /api/sparrow/:id/purge 0 ; T positive missing_authz purge is an admin action but the controller only requires a bearer session
    return head :not_found unless ROWS.delete(params[:id].to_i)

    head :no_content
  end

  def glacier_show  # @@R GET /api/glacier/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    row = ROWS[params[:id].to_i]
    return head :not_found unless row

    render json: row
  end

  def summit_show  # @@R GET /api/summit/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    row = ROWS[params[:id].to_i]
    return head :not_found unless row

    render json: row
  end
end
