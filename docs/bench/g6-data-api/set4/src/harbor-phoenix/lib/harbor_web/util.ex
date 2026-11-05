defmodule HarborWeb.Util do
  @vendor "https://dispatch.vendor.example.com"

  def vendor, do: @vendor
  def vendor_key, do: System.get_env("DISPATCH_KEY", "")
  def pin, do: System.get_env("HARBOR_PIN", "")

  def http(url, opts \\ []), do: Req.request!([url: url, receive_timeout: 5_000] ++ opts)

  def ask_model(messages), do: http("https://llm.vendor.example.com/v1/chat", method: :post, json: %{messages: messages}).body
  def ask_tool(raw), do: http("https://llm.vendor.example.com/v1/tool", method: :post, body: raw, headers: [{"content-type", "application/json"}]).body
end
