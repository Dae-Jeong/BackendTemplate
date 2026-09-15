require "test_helper"
require "sqlite3"

class ReservationServiceTest < ActiveSupport::TestCase
  self.use_transactional_tests = false

  setup do
    Reservation.delete_all
  end

  teardown do
    Reservation.delete_all
  end

  test "returns only after the write is committed to the SQLite database" do
    result = ReservationService.create(
      product_id: "product-1",
      clock: -> { Time.utc(2026, 9, 15, 4, 5, 6) }
    )

    database = SQLite3::Database.new(ActiveRecord::Base.connection_db_config.database)
    persisted = database.get_first_row(
      "SELECT reservation_id, product_id, created_at FROM reservations WHERE reservation_id = ?",
      result.reservation_id
    )

    assert_equal [ result.reservation_id, "product-1", "2026-09-15 04:05:06" ], persisted
  ensure
    database&.close
  end

  test "rolls back a real insert when an exception follows it" do
    real_reservation = Reservation
    controlled_reservation = Class.new do
      const_set(:PRODUCT_ID_MAX_LENGTH, real_reservation::PRODUCT_ID_MAX_LENGTH)

      define_singleton_method(:transaction) do |&block|
        real_reservation.transaction(&block)
      end

      define_singleton_method(:create!) do |**attributes|
        real_reservation.create!(**attributes)
        raise "controlled post-insert failure"
      end
    end

    stub_const(Object, :Reservation, controlled_reservation) do
      assert_raises(RuntimeError) do
        ReservationService.create(
          product_id: "product-1",
          clock: -> { Time.utc(2026, 9, 15, 4, 5, 6) }
        )
      end
    end

    assert_equal 0, Reservation.count
  end
end
