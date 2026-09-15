require "test_helper"
require "sqlite3"

class ReservationServiceTest < ActiveSupport::TestCase
  self.use_transactional_tests = false

  setup do
    Reservation.delete_all
    Product.delete_all
    Product.create!(product_id: "product-1", stock: 2)
  end

  teardown do
    Reservation.delete_all
    Product.delete_all
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
    assert_equal 1, Product.find_by!(product_id: "product-1").stock
  ensure
    database&.close
  end

  test "rolls stock back when the real reservation insert fails" do
    timestamp = Time.utc(2026, 9, 15, 4, 5, 6)
    reservation_id = "a" * 32
    Reservation.create!(
      reservation_id: reservation_id,
      product_id: "legacy-product",
      created_at: timestamp,
      updated_at: timestamp
    )

    controlled_random = Class.new do
      define_singleton_method(:hex) { |*| reservation_id }
    end
    real_reservation = Reservation
    controlled_reservation = Class.new do
      define_singleton_method(:transaction) { |&block| real_reservation.transaction(&block) }
      define_singleton_method(:create!) do |**attributes|
        real_reservation.insert_all!([ attributes ])
      end
    end

    stub_const(Object, :SecureRandom, controlled_random) do
      stub_const(Object, :Reservation, controlled_reservation) do
        assert_raises(ActiveRecord::RecordNotUnique) do
          ReservationService.create(
            product_id: "product-1",
            clock: -> { timestamp }
          )
        end
      end
    end

    assert_equal 2, Product.find_by!(product_id: "product-1").stock
    assert_equal 1, Reservation.count
  end

  test "rolls back reservation and stock when an exception follows the insert" do
    real_reservation = Reservation
    controlled_reservation = Class.new do
      define_singleton_method(:transaction) { |&block| real_reservation.transaction(&block) }
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

    assert_equal 2, Product.find_by!(product_id: "product-1").stock
    assert_equal 0, Reservation.count
  end

  test "missing product and sold out leave reservations unchanged" do
    assert_raises(ReservationErrors::ProductNotFound) do
      ReservationService.create(
        product_id: "missing",
        clock: -> { Time.utc(2026, 9, 15, 4, 5, 6) }
      )
    end

    Product.where(product_id: "product-1").update_all(stock: 0)
    assert_raises(ReservationService::SoldOut) do
      ReservationService.create(
        product_id: "product-1",
        clock: -> { Time.utc(2026, 9, 15, 4, 5, 6) }
      )
    end

    assert_equal 0, Reservation.count
  end

  test "real SQLite lock contention is not reported as sold out" do
    active_record_connection = ActiveRecord::Base.connection
    original_busy_timeout = active_record_connection.select_value("PRAGMA busy_timeout")
    active_record_connection.raw_connection.busy_handler_timeout = 50
    locking_connection = SQLite3::Database.new(ActiveRecord::Base.connection_db_config.database)
    locking_connection.execute("BEGIN IMMEDIATE")

    assert_raises(ReservationService::DatabaseBusy) do
      ReservationService.create(
        product_id: "product-1",
        clock: -> { Time.utc(2026, 9, 15, 4, 5, 6) }
      )
    end

    assert_equal 2, Product.find_by!(product_id: "product-1").stock
    assert_equal 0, Reservation.count
  ensure
    locking_connection&.execute("ROLLBACK")
    locking_connection&.close
    active_record_connection&.raw_connection&.busy_handler_timeout = original_busy_timeout if original_busy_timeout
  end

  test "translates connection pool timeout separately" do
    real_reservation = Reservation
    pool_error = ActiveRecord::ConnectionTimeoutError.new
    controlled_reservation = Class.new do
      define_singleton_method(:transaction) { raise pool_error }
    end

    stub_const(Object, :Reservation, controlled_reservation) do
      error = assert_raises(ReservationService::DatabasePoolTimeout) do
        ReservationService.create(
          product_id: "product-1",
          clock: -> { Time.utc(2026, 9, 15, 4, 5, 6) }
        )
      end
      assert_same pool_error, error.cause
    end
  end
end
