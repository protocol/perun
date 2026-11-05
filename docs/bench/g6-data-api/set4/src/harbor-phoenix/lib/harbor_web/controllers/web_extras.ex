defmodule HarborWeb.WebExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def email(conn, params) do
    email = params["email"] |> to_string() |> String.slice(0, 120) # @@T positive csrf cookie-session email change accepted with no anti-forgery token
    if email != "", do: Store.set_email(conn.assigns.user.uid, email)
    json(conn, %{updated: email != ""})
  end

  def close(conn, _) do
    Store.close(conn.assigns.user.uid)
    conn |> delete_resp_cookie("sid") |> send_resp(204, "") # @@T positive csrf cookie-session account closure reachable from a cross-site form post
  end

  def remember(conn, _) do
    user = conn.assigns.user
    conn |> put_resp_cookie("sid", Store.open(user.uid, user.role)) |> send_resp(204, "") # @@T positive cookie_flags session cookie issued with no secure http_only or same_site option
  end

  def trust(conn, _) do
    user = conn.assigns.user
    conn |> put_resp_cookie("trust", Store.open(user.uid, user.role), secure: true, http_only: false, same_site: "Lax", max_age: 86_400) |> send_resp(204, "") # @@T positive cookie_flags login token cookie readable from script because http_only is false
  end
end
