defmodule HarborWeb.DeskExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def summarise(conn, params) do
    note = params["note"] |> to_string() |> String.slice(0, 500)
    reply = ask_model([%{role: "system", content: "You summarise harbor notes and have no tools."}, %{role: "user", content: note}]) # @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
    json(conn, %{reply: reply})
  end
end
