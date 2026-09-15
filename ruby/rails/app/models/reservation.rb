class Reservation < ApplicationRecord
  ID_FORMAT = /\A[0-9a-f]{32}\z/

  validates :reservation_id,
            presence: true,
            length: { is: 32 },
            format: { with: ID_FORMAT },
            uniqueness: true
  validates :product_id, presence: true, length: { maximum: ProductId::MAX_LENGTH }

  def to_result
    ReservationResult.new(
      reservation_id: reservation_id,
      product_id: product_id,
      created_at: created_at.utc
    )
  end
end
