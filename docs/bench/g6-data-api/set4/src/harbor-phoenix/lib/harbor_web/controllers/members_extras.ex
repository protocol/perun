defmodule HarborWeb.MembersExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  require Logger
  alias HarborWeb.{Auth, Store}

  @seed_spire [%{label: "Sample harbor", region: "north", count: 3}] # @@T decoy pii_data seed rows hold labels and counts and no person

  def sample(conn, _), do: json(conn, %{count: length(@seed_spire)})

  def rotate(conn, _) do
    user = conn.assigns.user
    key_id = :crypto.strong_rand_bytes(8) |> Base.encode16(case: :lower)
    Logger.info("rotate user=#{user.uid}") # @@T decoy pii_log the log line carries only the numeric user id
    json(conn, %{keyId: key_id})
  end

  def track(conn, _) do
    http("https://stats.vendor.example.com/v1/event", method: :post, json: %{event: "view"}) # @@T decoy pii_data analytics payload is a constant event name with no user identifier
    send_resp(conn, 204, "")
  end
end
