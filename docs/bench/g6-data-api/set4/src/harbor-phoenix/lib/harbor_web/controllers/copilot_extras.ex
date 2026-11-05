defmodule HarborWeb.CopilotExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def assist(conn, params) do
    note = params["note"] |> to_string() |> String.slice(0, 500)
    json(conn, ask_model([%{role: "system", content: "You summarise harbor notes and have no tools."}, %{role: "user", content: note}])) # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  end

  def lookup(conn, params) do
    json(conn, ask_tool(Jason.encode!(%{tool: "lookup", arg: params["sku"]}))) # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
  end

  def translate(conn, params) do
    text = params["text"] |> to_string() |> String.slice(0, 500)
    json(conn, ask_model([%{role: "system", content: "You translate harbor notes and have no tools."}, %{role: "user", content: text}])) # @@T decoy rate_limit model call route sits in the scope that pipes through the throttle plug so each client address is capped at sixty requests a minute
  end
end
