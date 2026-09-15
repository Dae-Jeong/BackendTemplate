require "test_helper"
require "open3"

class DatabaseConfigurationTest < ActiveSupport::TestCase
  test "test database ignores application database environment variables" do
    shared_database = Rails.root.join("storage/shared-must-not-be-used.sqlite3")
    command = [
      RbConfig.ruby,
      Rails.root.join("bin/rails").to_s,
      "runner",
      "ActiveRecord::Base.connection.execute('SELECT 1'); puts ActiveRecord::Base.connection_db_config.database"
    ]
    environment = {
      "RAILS_ENV" => "test",
      "APP_ENVIRONMENT" => "test",
      "DB_PRIMARY_PATH" => shared_database.to_s,
      "DATABASE_URL" => "sqlite3:#{shared_database}"
    }

    stdout, stderr, status = Open3.capture3(environment, *command, chdir: Rails.root.to_s)

    assert status.success?, stderr
    assert_equal Rails.root.join("storage/test.sqlite3").to_s, stdout.strip
    refute_equal shared_database.to_s, stdout.strip
    refute shared_database.exist?
  end
end
