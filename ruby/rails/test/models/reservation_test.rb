require "test_helper"

class ReservationTest < ActiveSupport::TestCase
  test "maps a persisted model to a plain Ruby result" do
    created_at = Time.utc(2026, 9, 15, 4, 5, 6)
    reservation = Reservation.create!(
      reservation_id: "a" * 32,
      product_id: "product-1",
      created_at: created_at,
      updated_at: created_at
    )

    result = reservation.to_result

    assert_instance_of ReservationResult, result
    assert_equal "a" * 32, result.reservation_id
    assert_equal "product-1", result.product_id
    assert_equal created_at, result.created_at
  end

  test "enforces the public identifier and product constraints" do
    reservation = Reservation.new(reservation_id: "not-hex", product_id: " ")

    refute reservation.valid?
    assert reservation.errors.of_kind?(:reservation_id, :invalid)
    assert reservation.errors.of_kind?(:product_id, :blank)
  end
end
