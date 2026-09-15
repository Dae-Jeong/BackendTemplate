require "test_helper"

class V1::GreetingsControllerTest < ActionDispatch::IntegrationTest
  setup do
    @original_clock = Rails.application.config.x.clock
    Rails.application.config.x.clock = -> { Time.utc(2026, 9, 15, 4, 5, 6) }
  end

  teardown do
    Rails.application.config.x.clock = @original_clock
  end

  test "returns a greeting envelope with the injected UTC clock" do
    get "/v1/greetings", params: { name: "  Marin  " }

    assert_response :ok
    assert_equal "application/json", response.media_type
    assert_equal({
      "data" => {
        "message" => "Hello, Marin!",
        "generated_at" => "2026-09-15T04:05:06Z"
      }
    }, response.parsed_body)
  end

  test "rejects a missing name" do
    get "/v1/greetings"

    assert_response :unprocessable_content
    assert_equal "application/problem+json", response.media_type
    assert_equal "REQUIRED", response.parsed_body.dig("errors", 0, "code")
  end

  test "rejects a whitespace-only name" do
    get "/v1/greetings", params: { name: "   " }

    assert_response :unprocessable_content
    assert_equal "TOO_SHORT", response.parsed_body.dig("errors", 0, "code")
  end

  test "rejects a name longer than eighty characters" do
    get "/v1/greetings", params: { name: "a" * 81 }

    assert_response :unprocessable_content
    assert_equal "TOO_LONG", response.parsed_body.dig("errors", 0, "code")
  end

  test "rejects an array query name" do
    get "/v1/greetings?name[]=Marin"

    assert_response :unprocessable_content
    assert_equal "INVALID_TYPE", response.parsed_body.dig("errors", 0, "code")
  end

  test "rejects an object query name" do
    get "/v1/greetings?name[value]=Marin"

    assert_response :unprocessable_content
    assert_equal "INVALID_TYPE", response.parsed_body.dig("errors", 0, "code")
  end
end
