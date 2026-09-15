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

  def self.create(product_id:, clock:)
    normalized_product_id = normalize_product_id(product_id)
    timestamp = clock.call.utc
    reservation = nil

    Reservation.transaction do
      reservation = Reservation.create!(
        reservation_id: SecureRandom.hex(16),
        product_id: normalized_product_id,
        created_at: timestamp,
        updated_at: timestamp
      )
    end

    reservation.to_result
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
  private_class_method :normalize_product_id
end
