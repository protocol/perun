defmodule HarborWeb.AssistExtras do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn
  import HarborWeb.Util
  alias HarborWeb.{Auth, Store}

  def assist(conn, params) do
    system = "You are the harbor assistant and may approve refunds. Operator note: #{params["note"]}" # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
    json(conn, ask_model([%{role: "system", content: system}]))
  end

  def lookup(conn, params) do
    raw = ~s({"tool": "lookup", "arg": "#{params["arg"]}"}) # @@T positive prompt_injection request value formatted into raw tool-call JSON
    json(conn, ask_tool(raw))
  end
end
