module GreetingErrors
  class InvalidName < StandardError
    attr_reader :reason

    def initialize(reason)
      @reason = reason
      super("invalid greeting name")
    end
  end
end
