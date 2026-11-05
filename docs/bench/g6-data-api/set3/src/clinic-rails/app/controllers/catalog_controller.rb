class CatalogController < ApplicationController
  before_action :require_bearer

  def badger_index  # @@R GET /api/badger 1 ; T decoy missing_authn class-level before_action require_bearer covers every action and the list is filtered by the session owner
    render json: ROWS.values.select { |r| r[:owner] == @user[:uid] }
  end

  before_action :require_admin, only: :tundra_remove

  def tundra_remove  # @@R DELETE /api/tundra/:id 1 ; T decoy missing_authz before_action require_admin answers 403 for other roles
    return head :not_found unless ROWS.delete(params[:id].to_i)

    head :no_content
  end

  def valley_show  # @@R GET /api/valley/:id 1 ; T decoy missing_object_check owned_or_404 compares the owner with the session user and answers 404
    row = owned_or_404(params[:id])
    render json: row if row
  end
end
