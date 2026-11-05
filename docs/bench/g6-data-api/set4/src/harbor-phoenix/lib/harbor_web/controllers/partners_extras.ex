defmodule HarborWeb.PartnersExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  require Logger
  alias HarborWeb.{Auth, Store}

  def push(conn, _) do
    resp = http("#{vendor()}/v1/juniper", method: :post, headers: [{"x-api-key", vendor_key()}], connect_options: [transport_opts: [verify: :verify_none]]) # @@T positive tls_off certificate verification disabled for the vendor request
    json(conn, %{status: resp.status})
  end

  def push_again(conn, _) do
    resp = http("#{vendor()}/v1/osprey", method: :post, headers: [{"x-api-key", vendor_key()}], connect_options: [transport_opts: [verify: :verify_none]]) # @@T positive tls_off certificate verification disabled for the vendor request
    json(conn, %{status: resp.status})
  end

  def fetch(conn, %{"url" => url}) do
    resp = http(url) # @@T positive ssrf caller-supplied URL fetched from the server
    json(conn, resp.body)
  end

  def status(conn, _) do
    resp = Req.get!("#{vendor()}/v1/heron/status", headers: [{"x-api-key", vendor_key()}], receive_timeout: :infinity) # @@T positive no_timeout receive timeout is infinite so a slow vendor holds the request open
    json(conn, %{status: resp.status})
  end

  def lookup(conn, _) do
    resp = http("#{vendor()}/v1/otter", params: [key: vendor_key()]) # @@T positive secret_in_url vendor key sent as a query parameter
    json(conn, %{status: resp.status})
  end

  def ping(conn, _) do
    Logger.info("vendor ping key=#{vendor_key()}") # @@T positive secret_in_log vendor key written to the application log
    resp = http("#{vendor()}/v1/ping", headers: [{"x-api-key", vendor_key()}])
    json(conn, %{status: resp.status})
  end
end
