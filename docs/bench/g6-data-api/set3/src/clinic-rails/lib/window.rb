class Window
  def initialize(cap, span)
    @cap, @span, @hits = cap, span, Hash.new { |h, k| h[k] = [] }
  end

  def allow?(key)
    now = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    recent = @hits[key].select { |t| now - t < @span }
    @hits[key] = recent
    return false if recent.size >= @cap

    recent << now
    true
  end
end
