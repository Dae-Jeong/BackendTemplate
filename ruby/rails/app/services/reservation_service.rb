require "securerandom"

class ReservationService
  class InvalidInput < StandardError
    attr_reader :reason

    def initialize(reason)
      @reason = reason
      super("invalid reservation input")
    end
  end

  class NotFound < StandardError
  end

  class ProductNotFound < StandardError
  end

  class SoldOut < StandardError
  end

  class DatabaseBusy < StandardError
  end

  class DatabasePoolTimeout < StandardError
  end

  def self.create(product_id:, clock:)
    normalized_product_id = ProductId.normalize(product_id)
    timestamp = clock.call.utc
    reservation = nil

    Reservation.transaction do
      changed = Product.decrement_stock(product_id: normalized_product_id, timestamp: timestamp)
      if changed.zero?
        raise ProductNotFound unless Product.exists_by_product_id?(normalized_product_id)

        raise SoldOut
      end

      reservation = Reservation.create!(
        reservation_id: SecureRandom.hex(16),
        product_id: normalized_product_id,
        created_at: timestamp,
        updated_at: timestamp
      )
    end

    reservation.to_result
  rescue ProductId::Invalid => error
    raise InvalidInput, error.reason
  rescue ActiveRecord::ConnectionTimeoutError => error
    raise DatabasePoolTimeout, cause: error
  rescue ActiveRecord::StatementInvalid => error
    raise DatabaseBusy, cause: error if sqlite_busy?(error)

    raise
  end

  def self.find(reservation_id:)
    raise InvalidInput, "INVALID_ID" unless Reservation::ID_FORMAT.match?(reservation_id)

    reservation = Reservation.find_by(reservation_id: reservation_id)
    raise NotFound if reservation.nil?

    reservation.to_result
  end

  def self.sqlite_busy?(error)
    cause = error
    while cause
      return true if cause.is_a?(SQLite3::BusyException) || cause.is_a?(SQLite3::LockedException)

      cause = cause.cause
    end
    false
  end
  private_class_method :sqlite_busy?
end
