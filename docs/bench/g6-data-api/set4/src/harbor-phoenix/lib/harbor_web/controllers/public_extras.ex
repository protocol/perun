defmodule HarborWeb.PublicExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  require Logger
  alias HarborWeb.{Auth, Store}

  def healthz(conn, _), do: json(conn, %{ok: true})

  def summary(conn, _), do: json(conn, Enum.map(Store.rows(), &%{id: &1.id, label: &1.label}))

  def pin(conn, params) do
    if pin() == "" or params["pin"] != pin() do # @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
      send_resp(conn, 401, "")
    else
      json(conn, %{token: Store.open(40, "clerk")})
    end
  end

  def signup(conn, params) do
    Logger.info("signup name=#{params["name"]} email=#{params["email"]} ssn=#{params["ssn"]}") # @@T positive pii_log name email and national id written to the log
    send_resp(conn, 201, "")
  end
end
