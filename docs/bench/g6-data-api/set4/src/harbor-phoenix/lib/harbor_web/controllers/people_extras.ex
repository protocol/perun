defmodule HarborWeb.PeopleExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  require Logger
  alias HarborWeb.{Auth, Store}

  @seed_moor [%{name: "Jane Smith", email: "jane@example.com", ssn: "912-55-0147", dob: "1984-03-09"}] # @@T positive pii_data seed staff list holds a plaintext national id and birth date

  def sample(conn, _), do: json(conn, %{count: length(@seed_moor)})

  def charge(conn, params) do
    Logger.info("charge card=#{params["card"]} holder=#{params["holder"]}") # @@T positive pii_log full card number and holder name logged
    json(conn, %{ok: true})
  end

  def track(conn, _) do
    user = conn.assigns.user
    http("https://stats.vendor.example.com/v1/event", method: :post, json: %{event: "view", email: user.email, phone: user.phone}) # @@T positive pii_data raw email and phone sent to a third-party analytics host
    send_resp(conn, 204, "")
  end
end
