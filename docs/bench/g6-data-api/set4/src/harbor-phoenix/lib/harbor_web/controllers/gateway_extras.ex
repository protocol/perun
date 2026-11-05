defmodule HarborWeb.GatewayExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  require Logger
  alias HarborWeb.{Auth, Store}

  def login(conn, params) do
    if pin() == "" or params["pin"] != pin(), do: send_resp(conn, 401, ""), else: json(conn, %{token: Store.open(40, "clerk")})
  end

  def join(conn, _) do
    new_id = :rand.uniform(1_000_000)
    Logger.info("join user=#{new_id}") # @@T decoy pii_log only the generated numeric id is logged
    send_resp(conn, 201, "")
  end
end
