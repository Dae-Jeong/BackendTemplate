require "test_helper"

class RuntimeSettingsTest < ActiveSupport::TestCase
  test "loads valid settings without exposing the source environment" do
    settings = RuntimeSettings.from_env(
      "APP_NAME" => "Example",
      "APP_ENVIRONMENT" => "test",
      "SERVER_HOST" => "127.0.0.1",
      "SERVER_PORT" => "18088"
    )

    assert_equal "Example", settings.app_name
    assert_equal 18_088, settings.server_port
  end

  test "rejects a non-numeric port without echoing its value" do
    error = assert_raises(ArgumentError) do
      RuntimeSettings.from_env("SERVER_PORT" => "secret-invalid-value")
    end

    assert_equal "SERVER_PORT must be an integer", error.message
    refute_includes error.message, "secret-invalid-value"
  end

  test "rejects an out-of-range port" do
    error = assert_raises(ArgumentError) do
      RuntimeSettings.from_env("SERVER_PORT" => "70000")
    end

    assert_equal "SERVER_PORT must be between 1 and 65535", error.message
  end
end
