defmodule HarborWeb.CatalogController do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def me(conn, _), do: json(conn, %{uid: conn.assigns.user.uid, role: conn.assigns.user.role})

  def index(conn, _), do: json(conn, Enum.filter(Store.rows(), &(&1.owner == conn.assigns.user.uid)))

  def recent(conn, _), do: json(conn, conn |> Map.get(:assigns) |> then(fn a -> Store.rows() |> Enum.filter(&(&1.owner == a.user.uid)) |> Enum.take(-5) end))

  def delete(conn, %{"id" => id}) do
    cond do
      not Auth.admin?(conn) -> conn |> send_resp(403, "") |> halt()
      Store.delete(id) -> send_resp(conn, 204, "")
      true -> send_resp(conn, 404, "")
    end
  end

  def approve(conn, %{"id" => id}) do
    with true <- Auth.admin?(conn), %{} = row <- Store.row(id) do
      Store.put_row(Map.put(row, :approved, true))
      json(conn, row)
    else
      false -> conn |> send_resp(403, "") |> halt()
      _ -> send_resp(conn, 404, "")
    end
  end

  def show(conn, %{"id" => id}) do
    case Auth.owned(conn, id) do
      nil -> send_resp(conn, 404, "")
      row -> json(conn, row)
    end
  end

  def label(conn, %{"id" => id} = params) do
    case Auth.owned(conn, id) do
      nil -> send_resp(conn, 404, "")
      row ->
        updated = %{row | label: params["label"] |> to_string() |> String.slice(0, 80)}
        Store.put_row(updated)
        json(conn, updated)
    end
  end
end
