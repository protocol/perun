defmodule HarborWeb.RecordsController do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def purge(conn, %{"id" => id}) do
    if Store.purge(id), do: send_resp(conn, 204, ""), else: send_resp(conn, 404, "")
  end

  def show(conn, %{"id" => id}) do
    case Store.row(id) do
      nil -> send_resp(conn, 404, "")
      row -> json(conn, row)
    end
  end
end
