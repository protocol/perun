defmodule Harbor.Application do
  use Application

  def start(_type, _args) do
    children = [HarborWeb.Store, HarborWeb.Endpoint]
    Supervisor.start_link(children, strategy: :one_for_one, name: Harbor.Supervisor)
  end
end
