import Config

config :harbor, HarborWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}, port: 3000],
  server: true,
  secret_key_base: String.duplicate("a", 64)
