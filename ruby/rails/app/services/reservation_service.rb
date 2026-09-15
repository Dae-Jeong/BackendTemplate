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
    normalized_product_id = normalize_product_id(product_id)
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

  def self.normalize_product_id(product_id)
    raise InvalidInput, "REQUIRED" if product_id.nil?
    raise InvalidInput, "INVALID_TYPE" unless product_id.is_a?(String)

    normalized_product_id = product_id.strip
    raise InvalidInput, "TOO_SHORT" if normalized_product_id.empty?
    if normalized_product_id.length > Reservation::PRODUCT_ID_MAX_LENGTH
      raise InvalidInput, "TOO_LONG"
    end

    normalized_product_id
  end

  def self.sqlite_busy?(error)
    cause = error
    while cause
      return true if cause.is_a?(SQLite3::BusyException) || cause.is_a?(SQLite3::LockedException)

      cause = cause.cause
    end
    false
  end
  private_class_method :normalize_product_id, :sqlite_busy?
end
