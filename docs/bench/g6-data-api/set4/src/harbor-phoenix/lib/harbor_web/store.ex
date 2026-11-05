defmodule HarborWeb.Store do
  use Agent

  @sessions %{
    "tok-clerk" => %{uid: 40, role: "clerk", csrf: "c-40", email: "clerk@example.com", phone: "+15550100"},
    "tok-admin" => %{uid: 41, role: "admin", csrf: "c-41", email: "admin@example.com", phone: "+15550101"}
  }
  @rows %{1 => %{id: 1, owner: 40, label: "harbor one"}, 2 => %{id: 2, owner: 41, label: "harbor two"}}

  def start_link(_), do: Agent.start_link(fn -> %{sessions: @sessions, rows: @rows, cache: %{1 => "warm", 2 => "warm"}, hits: %{}} end, name: __MODULE__)

  def session(token), do: Agent.get(__MODULE__, & &1.sessions[token])
  def rows, do: Agent.get(__MODULE__, &Map.values(&1.rows))
  def row(id), do: Agent.get(__MODULE__, & &1.rows[to_int(id)])
  def delete(id), do: Agent.get_and_update(__MODULE__, fn s -> {s.rows[to_int(id)], %{s | rows: Map.delete(s.rows, to_int(id))}} end)
  def put_row(row), do: Agent.update(__MODULE__, &put_in(&1.rows[row.id], row))
  def set_email(uid, email), do: Agent.update(__MODULE__, fn s -> %{s | sessions: Map.new(s.sessions, fn {t, u} -> {t, if(u.uid == uid, do: %{u | email: email}, else: u)} end)} end)
  def close(uid), do: Agent.update(__MODULE__, fn s -> %{s | sessions: Map.reject(s.sessions, fn {_, u} -> u.uid == uid end)} end)
  def purge(id), do: Agent.get_and_update(__MODULE__, fn s -> {s.cache[to_int(id)], %{s | cache: Map.delete(s.cache, to_int(id))}} end)

  def open(uid, role) do
    token = :crypto.strong_rand_bytes(24) |> Base.encode16(case: :lower)
    Agent.update(__MODULE__, &put_in(&1.sessions[token], %{uid: uid, role: role, csrf: "x-#{uid}", email: "x@example.com", phone: ""}))
    token
  end

  # Sliding window per key: true while fewer than cap hits fall inside the last span milliseconds.
  def allow?(key, cap, span) do
    now = System.monotonic_time(:millisecond)

    Agent.get_and_update(__MODULE__, fn s ->
      recent = Enum.filter(Map.get(s.hits, key, []), &(now - &1 < span))
      if length(recent) >= cap, do: {false, put_in(s.hits[key], recent)}, else: {true, put_in(s.hits[key], [now | recent])}
    end)
  end

  defp to_int(id) when is_integer(id), do: id
  defp to_int(id), do: String.to_integer(id)
end
