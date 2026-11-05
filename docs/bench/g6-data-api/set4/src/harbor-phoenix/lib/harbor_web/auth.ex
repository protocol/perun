defmodule HarborWeb.Auth do
  import Plug.Conn
  alias HarborWeb.Store

  def init(opt), do: opt

  def call(conn, :bearer) do
    token = conn |> get_req_header("authorization") |> List.first("") |> String.replace("Bearer ", "")
    authenticate(conn, Store.session(token))
  end

  def call(conn, :cookie), do: cookie_auth(conn)

  def call(conn, {:throttle, cap, span}) do
    key = {conn.remote_ip, cap, span}
    if Store.allow?(key, cap, span), do: conn, else: conn |> send_resp(429, "") |> halt()
  end

  def cookie_auth(conn) do
    conn = fetch_cookies(conn)
    authenticate(conn, Store.session(conn.req_cookies["sid"] || ""))
  end

  defp authenticate(conn, nil), do: conn |> send_resp(401, "") |> halt()
  defp authenticate(conn, session), do: assign(conn, :user, session)

  def admin?(conn), do: conn.assigns.user.role == "admin"

  def owned(conn, id) do
    case Store.row(id) do
      %{owner: owner} = row when owner == conn.assigns.user.uid -> row
      _ -> nil
    end
  end
end
