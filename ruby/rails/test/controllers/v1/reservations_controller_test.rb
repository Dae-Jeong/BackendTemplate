require "test_helper"

class V1::ReservationsControllerTest < ActionDispatch::IntegrationTest
  setup do
    @original_clock = Rails.application.config.x.clock
    Rails.application.config.x.clock = -> { Time.utc(2026, 9, 15, 4, 5, 6) }
    Product.create!(product_id: "product-1", stock: 10)
  end

  teardown do
    Rails.application.config.x.clock = @original_clock
  end

  test "creates and retrieves a persisted reservation" do
    post "/v1/reservations", params: { product_id: " product-1 " }, as: :json

    assert_response :created
    assert_equal "application/json", response.media_type
    created = response.parsed_body.fetch("data")
    assert_match(/\A[0-9a-f]{32}\z/, created.fetch("reservation_id"))
    assert_equal "product-1", created.fetch("product_id")
    assert_equal "2026-09-15T04:05:06Z", created.fetch("created_at")

    get "/v1/reservations/#{created.fetch("reservation_id")}"

    assert_response :ok
    assert_equal created, response.parsed_body.fetch("data")
    assert_equal 9, Product.find_by!(product_id: "product-1").stock
  end

  test "returns product not found without creating a reservation" do
    assert_no_difference("Reservation.count") do
      post "/v1/reservations", params: { product_id: "missing" }, as: :json
    end

    assert_response :not_found
    assert_equal "PRODUCT_NOT_FOUND", response.parsed_body.fetch("code")
  end

  test "returns sold out without creating a reservation" do
    Product.where(product_id: "product-1").update_all(stock: 0)

    assert_no_difference("Reservation.count") do
      post "/v1/reservations", params: { product_id: "product-1" }, as: :json
    end

    assert_response :conflict
    assert_equal "SOLD_OUT", response.parsed_body.fetch("code")
    assert_equal 0, Product.find_by!(product_id: "product-1").stock
  end

  test "reports database busy separately from sold out" do
    busy_service = Class.new do
      const_set(:InvalidInput, Class.new(StandardError))
      const_set(:SoldOut, Class.new(StandardError))
      const_set(:DatabaseBusy, Class.new(StandardError))
      const_set(:DatabasePoolTimeout, Class.new(StandardError))

      def self.create(**)
        raise const_get(:DatabaseBusy)
      end
    end

    stub_const(Object, :ReservationService, busy_service) do
      post "/v1/reservations", params: { product_id: "product-1" }, as: :json
    end

    assert_response :service_unavailable
    assert_equal "DATABASE_BUSY", response.parsed_body.fetch("code")
    assert_equal "1", response.headers["Retry-After"]
  end

  test "reports database pool timeout separately from sold out" do
    timeout_service = Class.new do
      const_set(:InvalidInput, Class.new(StandardError))
      const_set(:SoldOut, Class.new(StandardError))
      const_set(:DatabaseBusy, Class.new(StandardError))
      const_set(:DatabasePoolTimeout, Class.new(StandardError))

      def self.create(**)
        raise const_get(:DatabasePoolTimeout)
      end
    end

    stub_const(Object, :ReservationService, timeout_service) do
      post "/v1/reservations", params: { product_id: "product-1" }, as: :json
    end

    assert_response :service_unavailable
    assert_equal "DATABASE_POOL_TIMEOUT", response.parsed_body.fetch("code")
    assert_equal "1", response.headers["Retry-After"]
  end

  test "returns not found for an absent valid reservation id" do
    get "/v1/reservations/#{"f" * 32}"

    assert_response :not_found
    assert_equal "application/problem+json", response.media_type
    assert_equal "RESERVATION_NOT_FOUND", response.parsed_body.fetch("code")
  end

  test "rejects malformed JSON" do
    post "/v1/reservations", params: "{", headers: { "CONTENT_TYPE" => "application/json" }

    assert_response :unprocessable_content
    assert_equal "MALFORMED_BODY", response.parsed_body.dig("errors", 0, "code")
  end

  test "rejects missing, non-string, blank, and too-long product ids" do
    invalid_values = {
      nil => "REQUIRED",
      [ "product-1" ] => "INVALID_TYPE",
      "  " => "TOO_SHORT",
      "a" * 129 => "TOO_LONG"
    }

    invalid_values.each do |product_id, expected_code|
      post "/v1/reservations", params: { product_id: product_id }, as: :json

      assert_response :unprocessable_content
      assert_equal expected_code, response.parsed_body.dig("errors", 0, "code")
    end
  end

  test "rejects unknown fields instead of silently ignoring them" do
    post "/v1/reservations", params: { product_id: "product-1", quantity: 2 }, as: :json

    assert_response :unprocessable_content
    assert_equal "UNKNOWN_FIELD", response.parsed_body.dig("errors", 0, "code")
    assert_equal [ "body", "quantity" ], response.parsed_body.dig("errors", 0, "location")
  end

  test "rejects an invalid reservation id" do
    get "/v1/reservations/not-a-reservation-id"

    assert_response :unprocessable_content
    assert_equal "INVALID_ID", response.parsed_body.dig("errors", 0, "code")
  end

  test "rejects an idempotency key because replay is not implemented yet" do
    post "/v1/reservations",
         params: { product_id: "product-1" },
         headers: { "Idempotency-Key" => "request-1" },
         as: :json

    assert_response :unprocessable_content
    assert_equal "IDEMPOTENCY_NOT_SUPPORTED", response.parsed_body.dig("errors", 0, "code")
  end

  test "does not turn an unexpected persistence failure into a success response" do
    failing_service = Class.new do
      const_set(:InvalidInput, Class.new(StandardError))
      const_set(:SoldOut, Class.new(StandardError))
      const_set(:DatabaseBusy, Class.new(StandardError))
      const_set(:DatabasePoolTimeout, Class.new(StandardError))

      def self.create(**)
        raise ActiveRecord::StatementInvalid, "controlled test failure"
      end
    end

    stub_const(Object, :ReservationService, failing_service) do
      assert_raises(ActiveRecord::StatementInvalid) do
        post "/v1/reservations", params: { product_id: "product-1" }, as: :json
      end
    end

    refute response&.successful?
  end
end
