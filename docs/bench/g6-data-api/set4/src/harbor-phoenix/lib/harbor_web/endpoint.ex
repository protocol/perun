defmodule HarborWeb.Endpoint do
  use Phoenix.Endpoint, otp_app: :harbor

  plug Plug.Parsers, parsers: [:urlencoded, :json], pass: ["*/*"], json_decoder: Jason
  plug HarborWeb.Router
end
