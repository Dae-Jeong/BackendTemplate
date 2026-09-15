require "test_helper"
require "sqlite3"
require "timeout"
require "tmpdir"

class MigrationCompatibilityTest < ActiveSupport::TestCase
  self.use_transactional_tests = false

  PROCESS_TIMEOUT_SECONDS = 30

  test "fresh and repeated migrations create the stock schema" do
    Dir.mktmpdir("backend-template-rails-fresh-") do |directory|
      database_path = File.join(directory, "fresh.sqlite3")

      migrate_database!(database_path)
      migrate_database!(database_path)

      database = SQLite3::Database.new(database_path)
      tables = database.execute("SELECT name FROM sqlite_master WHERE type = 'table'").flatten
      product_sql = database.get_first_value(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'products'"
      )

      assert_includes tables, "reservations"
      assert_includes tables, "products"
      assert_includes product_sql, "products_stock_nonnegative"
    ensure
      database&.close
    end
  end

  test "upgrade preserves legacy reservations and repeated seed preserves stock" do
    Dir.mktmpdir("backend-template-rails-upgrade-") do |directory|
      database_path = File.join(directory, "upgrade.sqlite3")
      create_task_three_database!(database_path)

      migrate_database!(database_path)
      migrate_database!(database_path)
      seed_database!(database_path)
      execute_runner!(database_path, "Product.find_by!(product_id: 'product-1').update!(stock: 3)")
      seed_database!(database_path)

      database = SQLite3::Database.new(database_path)
      legacy = database.get_first_row(
        "SELECT reservation_id, product_id FROM reservations WHERE reservation_id = ?",
        [ "b" * 32 ]
      )
      seeded_stock = database.get_first_value(
        "SELECT stock FROM products WHERE product_id = 'product-1'"
      )

      assert_equal [ "b" * 32, "legacy / arbitrary product" ], legacy
      assert_equal 3, seeded_stock
    ensure
      database&.close
    end
  end

  private

  def create_task_three_database!(database_path)
    execute_rails!(
      database_path,
      "db:migrate",
      environment: { "VERSION" => "20260915043127" }
    )
    database = SQLite3::Database.new(database_path)
    database.execute_batch(<<~SQL)
      INSERT INTO reservations (reservation_id, product_id, created_at, updated_at)
        VALUES ('#{"b" * 32}', 'legacy / arbitrary product', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
    SQL
  ensure
    database&.close
  end

  def migrate_database!(database_path)
    execute_rails!(database_path, "db:migrate")
  end

  def seed_database!(database_path)
    execute_rails!(database_path, "db:seed")
  end

  def execute_runner!(database_path, code)
    execute_rails!(database_path, "runner", code)
  end

  def execute_rails!(database_path, *arguments, environment: {})
    log_path = "#{database_path}.command.log"
    pid = Process.spawn(
      rails_environment(database_path).merge(environment),
      RbConfig.ruby,
      Rails.root.join("bin/rails").to_s,
      *arguments,
      chdir: Rails.root.to_s,
      out: [ log_path, "a" ],
      err: [ log_path, "a" ]
    )
    status = wait_for_process!(pid)
    pid = nil

    assert status.success?, File.read(log_path)
  ensure
    stop_process(pid) if pid
  end

  def wait_for_process!(pid)
    Timeout.timeout(PROCESS_TIMEOUT_SECONDS) do
      _, status = Process.wait2(pid)
      status
    end
  end

  def stop_process(pid)
    Process.kill("TERM", pid)
    Timeout.timeout(2) { Process.wait(pid) }
  rescue Timeout::Error
    Process.kill("KILL", pid)
    Process.wait(pid)
  rescue Errno::ESRCH, Errno::ECHILD
    nil
  end

  def rails_environment(database_path)
    {
      "RAILS_ENV" => "development",
      "APP_ENVIRONMENT" => "local",
      "DB_PRIMARY_PATH" => database_path,
      "DATABASE_URL" => nil
    }
  end
end
