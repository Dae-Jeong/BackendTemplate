module ReservationErrors
  class InvalidInput < StandardError
    attr_reader :location, :reason

    def initialize(location:, reason:)
      @location = location
      @reason = reason
      super("invalid reservation request")
    end
  end

  class InvalidProductId < StandardError
    attr_reader :reason

    def initialize(reason)
      @reason = reason
      super("invalid reservation product id")
    end
  end

  class InvalidReservationId < StandardError
  end

  class ProductNotFound < StandardError
  end

  class NotFound < StandardError
  end

  class SoldOut < StandardError
  end
end
