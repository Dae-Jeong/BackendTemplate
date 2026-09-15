class GreetingService
  def self.call(name:, clock:)
    raise GreetingErrors::InvalidName, "REQUIRED" if name.nil?
    raise GreetingErrors::InvalidName, "INVALID_TYPE" unless name.is_a?(String)

    normalized_name = name.strip

    raise GreetingErrors::InvalidName, "TOO_SHORT" if normalized_name.empty?
    raise GreetingErrors::InvalidName, "TOO_LONG" if normalized_name.length > 80

    Greeting.new(
      message: "Hello, #{normalized_name}!",
      generated_at: clock.call.utc.iso8601
    )
  end
end
