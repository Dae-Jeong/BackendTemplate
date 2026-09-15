module ProductId
  MAX_LENGTH = 128

  class Invalid < StandardError
    attr_reader :reason

    def initialize(reason)
      @reason = reason
      super("invalid product id")
    end
  end

  def self.normalize(value)
    raise Invalid, "REQUIRED" if value.nil?
    raise Invalid, "INVALID_TYPE" unless value.is_a?(String)

    normalized = value.strip
    raise Invalid, "TOO_SHORT" if normalized.empty?
    raise Invalid, "TOO_LONG" if normalized.length > MAX_LENGTH

    normalized
  end
end
