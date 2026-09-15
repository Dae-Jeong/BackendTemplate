module ReservationValidation
  def self.validate_product_exists(product_exists)
    raise ReservationErrors::ProductNotFound unless product_exists
  end

  def self.validate_reservation_exists(reservation)
    raise ReservationErrors::NotFound if reservation.nil?

    reservation
  end
end
