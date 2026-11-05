defmodule HarborWeb.ConsoleExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def phone(conn, params) do
    sent = conn |> get_req_header("x-csrf-token") |> List.first("")
    if Plug.Crypto.secure_compare(sent, conn.assigns.user.csrf) do # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
      json(conn, %{updated: String.length(to_string(params["phone"])) <= 20})
    else
      send_resp(conn, 403, "")
    end
  end

  def nickname(conn, params) do
    conn = fetch_cookies(conn)
    sent = conn |> get_req_header("x-csrf-token") |> List.first("")
    if sent != "" and Plug.Crypto.secure_compare(sent, conn.req_cookies["csrf"] || "") do # @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
      json(conn, %{updated: to_string(params["nickname"]) != ""})
    else
      send_resp(conn, 403, "")
    end
  end

  def rotate(conn, _) do
    user = conn.assigns.user
    conn |> put_resp_cookie("sid", Store.open(user.uid, user.role), secure: true, http_only: true, same_site: "Strict", max_age: 3600) |> send_resp(204, "") # @@T decoy cookie_flags the new session cookie is secure http_only and same_site Strict with a one hour lifetime
  end

  def keep(conn, _) do
    conn |> put_resp_cookie("keep", Base.encode16(:crypto.strong_rand_bytes(8)), secure: true, http_only: true, same_site: "Strict", max_age: 3600) |> send_resp(204, "") # @@T decoy cookie_flags http_only secure and same_site Strict set together with a one hour lifetime
  end
end
