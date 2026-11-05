defmodule Harbor.MixProject do
  use Mix.Project

  def project, do: [app: :harbor, version: "0.1.0", elixir: "~> 1.16", deps: deps()]

  def application, do: [mod: {Harbor.Application, []}, extra_applications: [:logger]]

  defp deps do
    [
      {:phoenix, "~> 1.7.14"},
      {:plug_cowboy, "~> 2.7"},
      {:jason, "~> 1.4"},
      {:req, "~> 0.5.6"}
    ]
  end
end
