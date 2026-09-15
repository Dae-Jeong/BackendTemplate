class GreetingService
  class InvalidName < StandardError
    attr_reader :reason

    def initialize(reason)
      @reason = reason
      super("invalid greeting name")
    end
  end

  def self.call(name:, clock:)
    raise InvalidName, "REQUIRED" if name.nil?
    raise InvalidName, "INVALID_TYPE" unless name.is_a?(String)

    normalized_name = name.strip

    raise InvalidName, "TOO_SHORT" if normalized_name.empty?
    raise InvalidName, "TOO_LONG" if normalized_name.length > 80

    Greeting.new(
      message: "Hello, #{normalized_name}!",
      generated_at: clock.call.utc.iso8601
    )
  end
end
