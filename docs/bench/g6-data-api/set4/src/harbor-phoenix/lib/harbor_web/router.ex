defmodule HarborWeb.Router do
  use Phoenix.Router

  pipeline :bearer, do: plug(HarborWeb.Auth, :bearer)
  pipeline :cookie, do: plug(HarborWeb.Auth, :cookie)
  pipeline :throttle, do: plug(HarborWeb.Auth, {:throttle, 60, 60_000})
  pipeline :login_throttle, do: plug(HarborWeb.Auth, {:throttle, 8, 600_000})

  scope "/", HarborWeb do
    get "/healthz", PublicExtras, :healthz # @@R GET /healthz 0 public
    get "/api/aspen/summary", PublicExtras, :summary # @@R GET /api/aspen/summary 0 ; T positive missing_authn scope has no pipeline so the route lists internal rows to anyone
    get "/api/larch/summary", PublicExtras, :summary # @@R GET /api/larch/summary 0 ; T positive missing_authn scope has no pipeline so the route lists internal rows to anyone
    post "/auth/cedar-pin", PublicExtras, :pin # @@R POST /auth/cedar-pin 0 public
    post "/auth/elm-signup", PublicExtras, :signup # @@R POST /auth/elm-signup 0 public
  end

  scope "/", HarborWeb do
    pipe_through :bearer
    post "/api/ext/quill/summarise", DeskExtras, :summarise # @@R POST /api/ext/quill/summarise 1
  end

  scope "/", HarborWeb do
    pipe_through [:bearer, :throttle]
    get "/api/me", CatalogController, :me # @@R GET /api/me 1
    post "/api/beacon/:id/purge", RecordsController, :purge # @@R POST /api/beacon/:id/purge 0 ; T positive missing_authz purge is an admin action but the pipeline only requires a session
    post "/api/cobalt/:id/purge", RecordsController, :purge # @@R POST /api/cobalt/:id/purge 0 ; T positive missing_authz purge is an admin action but the pipeline only requires a session
    post "/api/ext/juniper/push", PartnersExtras, :push # @@R POST /api/ext/juniper/push 1
    post "/api/ext/osprey/push", PartnersExtras, :push_again # @@R POST /api/ext/osprey/push 1
    get "/api/ext/falcon/fetch", PartnersExtras, :fetch # @@R GET /api/ext/falcon/fetch 1
    get "/api/ext/heron/status", PartnersExtras, :status # @@R GET /api/ext/heron/status 1
    get "/api/ext/otter/lookup", PartnersExtras, :lookup # @@R GET /api/ext/otter/lookup 1
    get "/api/ext/badger/ping", PartnersExtras, :ping # @@R GET /api/ext/badger/ping 1
    get "/api/ext/plover/:id/image", IntegrationsExtras, :image # @@R GET /api/ext/plover/:id/image 1
    get "/api/compass", CatalogController, :index # @@R GET /api/compass 1 ; T decoy missing_authn the pipeline runs the bearer plug and the list is filtered by the session owner
    get "/api/recent", CatalogController, :recent # @@R GET /api/recent 1 ; T decoy missing_authn the pipeline runs the bearer plug and the list is filtered by the session owner
    delete "/api/copper/:id", CatalogController, :delete # @@R DELETE /api/copper/:id 1 ; T decoy missing_authz the action halts with 403 unless the session role is admin
    get "/api/ext/sparrow/:code/rates", IntegrationsExtras, :rates # @@R GET /api/ext/sparrow/:code/rates 1
    get "/api/ext/tundra/:code/stock", IntegrationsExtras, :stock # @@R GET /api/ext/tundra/:code/stock 1
    get "/api/ext/moor/sample", PeopleExtras, :sample # @@R GET /api/ext/moor/sample 1
    post "/api/ext/bluff/charge", PeopleExtras, :charge # @@R POST /api/ext/bluff/charge 1
    post "/api/ext/reef/track", PeopleExtras, :track # @@R POST /api/ext/reef/track 1
    get "/api/ext/spire/sample", MembersExtras, :sample # @@R GET /api/ext/spire/sample 1
    post "/api/ext/dune/rotate-key", MembersExtras, :rotate # @@R POST /api/ext/dune/rotate-key 1
    get "/api/granite/:id", RecordsController, :show # @@R GET /api/granite/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    get "/api/pebble/:id", RecordsController, :show # @@R GET /api/pebble/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    post "/api/ext/shoal/track", MembersExtras, :track # @@R POST /api/ext/shoal/track 1
    post "/api/ext/arbor/assist", AssistExtras, :assist # @@R POST /api/ext/arbor/assist 1
    post "/api/ext/bramble/lookup-tool", AssistExtras, :lookup # @@R POST /api/ext/bramble/lookup-tool 1
    post "/api/ext/fennel/assist", CopilotExtras, :assist # @@R POST /api/ext/fennel/assist 1
    post "/api/ext/hazel/lookup-tool", CopilotExtras, :lookup # @@R POST /api/ext/hazel/lookup-tool 1
    post "/api/ext/ivy/translate", CopilotExtras, :translate # @@R POST /api/ext/ivy/translate 1
    post "/api/timber/:id/approve", CatalogController, :approve # @@R POST /api/timber/:id/approve 1 ; T decoy missing_authz the action halts with 403 unless the session role is admin
    get "/api/thistle/:id", CatalogController, :show # @@R GET /api/thistle/:id 1 ; T decoy missing_object_check owned compares the owner with the session user and the action answers 404
    put "/api/willow/:id/label", CatalogController, :label # @@R PUT /api/willow/:id/label 1 ; T decoy missing_object_check owned compares the owner with the session user and the action answers 404
  end

  scope "/", HarborWeb do
    pipe_through [:login_throttle]
    post "/auth/birch-login", GatewayExtras, :login # @@R POST /auth/birch-login 0 public ; T decoy rate_limit the login_throttle pipeline counts attempts per client address and answers 429 past eight in ten minutes
  end

  scope "/", HarborWeb do
    post "/auth/hazel-join", GatewayExtras, :join # @@R POST /auth/hazel-join 0 public
  end

  scope "/", HarborWeb do
    pipe_through [:cookie, :throttle]
    post "/web/ext/ridge/email", WebExtras, :email # @@R POST /web/ext/ridge/email 1
    post "/web/ext/delta/close", WebExtras, :close # @@R POST /web/ext/delta/close 1
    get "/web/ext/prairie/remember", WebExtras, :remember # @@R GET /web/ext/prairie/remember 1
    get "/web/ext/savanna/trust", WebExtras, :trust # @@R GET /web/ext/savanna/trust 1
    post "/web/ext/lagoon/phone", ConsoleExtras, :phone # @@R POST /web/ext/lagoon/phone 1
    post "/web/ext/mesa/nickname", ConsoleExtras, :nickname # @@R POST /web/ext/mesa/nickname 1
    get "/web/ext/atoll/rotate", ConsoleExtras, :rotate # @@R GET /web/ext/atoll/rotate 1
    get "/web/ext/geyser/keep", ConsoleExtras, :keep # @@R GET /web/ext/geyser/keep 1
  end
end
