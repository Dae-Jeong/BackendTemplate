require "securerandom"

class ReservationService
  def self.create(product_id:, clock:)
    normalized_product_id = ProductId.normalize(product_id)
    timestamp = clock.call.utc
    reservation = nil

    DatabaseErrors.translate do
      Reservation.transaction do
        changed = Product.decrement_stock(product_id: normalized_product_id, timestamp: timestamp)
        if changed.zero?
          ReservationValidation.validate_product_exists(Product.exists_by_product_id?(normalized_product_id))
          raise ReservationErrors::SoldOut
        end

        reservation = Reservation.create!(
          reservation_id: SecureRandom.hex(16),
          product_id: normalized_product_id,
          created_at: timestamp,
          updated_at: timestamp
        )
      end
    end

    reservation.to_result
  rescue ProductId::Invalid => error
    raise ReservationErrors::InvalidProductId, error.reason
  end

  def self.find(reservation_id:)
    raise ReservationErrors::InvalidReservationId unless Reservation::ID_FORMAT.match?(reservation_id)

    reservation = DatabaseErrors.translate do
      found = Reservation.find_by(reservation_id: reservation_id)
      ReservationValidation.validate_reservation_exists(found)
    end
    reservation.to_result
  end
end
