defmodule HarborWeb.IntegrationsExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  require Logger
  alias HarborWeb.{Auth, Store}

  def image(conn, %{"id" => id}) do
    if Regex.match?(~r/^[0-9]+$/, id) do
      resp = http("https://img.vendor.example.com/p/#{id}.jpg") # @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id
      conn |> put_resp_content_type("image/jpeg") |> send_resp(200, resp.body)
    else
      send_resp(conn, 400, "")
    end
  end

  def rates(conn, %{"code" => code}) do
    if Regex.match?(~r/^[A-Z]{2}$/, code) do
      resp = http("#{vendor()}/v1/rates/#{code}", headers: [{"x-api-key", vendor_key()}]) # @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
      json(conn, resp.body)
    else
      send_resp(conn, 400, "")
    end
  end

  def stock(conn, %{"code" => code}) do
    if Regex.match?(~r/^[A-Z]{2}$/, code) do
      resp = http("#{vendor()}/v1/stock/#{code}", headers: [{"x-api-key", vendor_key()}])
      Logger.info("stock lookup code=#{code} status=#{resp.status}") # @@T decoy secret_in_log only the status and the validated code are logged
      json(conn, resp.body)
    else
      send_resp(conn, 400, "")
    end
  end
end
