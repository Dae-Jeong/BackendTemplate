require "test_helper"

class HealthControllerTest < ActionDispatch::IntegrationTest
  setup do
    @original_readiness_check = Rails.application.config.x.readiness_check
  end

  teardown do
    Rails.application.config.x.readiness_check = @original_readiness_check
  end

  test "liveness reports that the process is alive" do
    get "/health/live"

    assert_response :ok
    assert_equal({ "status" => "alive" }, response.parsed_body)
  end

  test "readiness checks the isolated SQLite connection" do
    get "/health/ready"

    assert_response :ok
    assert_equal({ "status" => "ready" }, response.parsed_body)
  end

  test "readiness reports unavailable when the database connection fails" do
    Rails.application.config.x.readiness_check = -> { raise ActiveRecord::ConnectionNotEstablished }
    get "/health/ready"

    assert_response :service_unavailable
    assert_equal({ "status" => "not_ready" }, response.parsed_body)
  end
end
