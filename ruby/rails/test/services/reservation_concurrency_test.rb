require "test_helper"
require "sqlite3"
require "timeout"
require "tmpdir"

class ReservationConcurrencyTest < ActiveSupport::TestCase
  self.use_transactional_tests = false

  REQUEST_COUNT = 6
  INITIAL_STOCK = 3
  PROCESS_TIMEOUT_SECONDS = 30

  test "independent processes do not reserve more units than stock" do
    Dir.mktmpdir("backend-template-rails-race-") do |directory|
      database_path = File.join(directory, "race.sqlite3")
      migrate_database!(database_path)
      seed_race_product!(database_path)

      go_path = File.join(directory, "go")
      processes = spawn_contenders(directory, database_path, go_path)

      wait_until_ready!(processes)
      File.write(go_path, "go")
      wait_for_processes!(processes)

      results = processes.map { |process| File.read(process.fetch(:result_path)).strip }
      database = SQLite3::Database.new(database_path)
      stored_count = database.get_first_value(
        "SELECT COUNT(*) FROM reservations WHERE product_id = 'race-product'"
      )
      remaining_stock = database.get_first_value(
        "SELECT stock FROM products WHERE product_id = 'race-product'"
      )

      assert_equal INITIAL_STOCK, results.count("SUCCESS")
      assert_equal REQUEST_COUNT - INITIAL_STOCK, results.count("SOLD_OUT")
      assert_equal 0, results.count("DATABASE_BUSY")
      assert_equal [], results.grep(/^ERROR:/)
      assert_equal INITIAL_STOCK, stored_count
      assert_equal 0, remaining_stock
    ensure
      database&.close
      stop_processes(processes || [])
    end
  end

  private

  def migrate_database!(database_path)
    environment = rails_environment(database_path)
    command = [ RbConfig.ruby, Rails.root.join("bin/rails").to_s, "db:migrate" ]
    log_path = "#{database_path}.migration.log"
    process = {
      pid: Process.spawn(
        environment,
        *command,
        chdir: Rails.root.to_s,
        out: log_path,
        err: [ log_path, "a" ]
      ),
      log_path: log_path
    }
    Timeout.timeout(PROCESS_TIMEOUT_SECONDS) do
      _, status = Process.wait2(process.fetch(:pid))
      process[:joined] = true
      assert status.success?, File.read(log_path)
    end
  ensure
    stop_processes([ process ].compact)
  end

  def seed_race_product!(database_path)
    database = SQLite3::Database.new(database_path)
    database.execute(
      "INSERT INTO products (product_id, stock, created_at, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
      [ "race-product", INITIAL_STOCK ]
    )
  ensure
    database&.close
  end

  def spawn_contenders(directory, database_path, go_path)
    processes = []
    REQUEST_COUNT.times do |index|
      ready_path = File.join(directory, "ready-#{index}")
      result_path = File.join(directory, "result-#{index}")
      log_path = File.join(directory, "process-#{index}.log")
      code = <<~RUBY
        File.write(ENV.fetch("READY_PATH"), "ready")
        deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 20
        until File.exist?(ENV.fetch("GO_PATH"))
          raise "barrier timeout" if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
          sleep 0.01
        end
        result = begin
          ReservationService.create(product_id: "race-product", clock: -> { Time.now.utc })
          "SUCCESS"
        rescue ReservationErrors::SoldOut
          "SOLD_OUT"
        rescue DatabaseErrors::Busy
          "DATABASE_BUSY"
        rescue => error
          "ERROR:\#{error.class}"
        end
        File.write(ENV.fetch("RESULT_PATH"), result)
      RUBY
      environment = rails_environment(database_path).merge(
        "READY_PATH" => ready_path,
        "RESULT_PATH" => result_path,
        "GO_PATH" => go_path
      )
      pid = Process.spawn(
        environment,
        RbConfig.ruby,
        Rails.root.join("bin/rails").to_s,
        "runner",
        code,
        chdir: Rails.root.to_s,
        out: log_path,
        err: [ log_path, "a" ]
      )
      processes << { pid: pid, ready_path: ready_path, result_path: result_path, log_path: log_path }
    end
    processes
  rescue
    stop_processes(processes)
    raise
  end

  def wait_until_ready!(processes)
    Timeout.timeout(PROCESS_TIMEOUT_SECONDS) do
      sleep 0.01 until processes.all? { |process| File.exist?(process.fetch(:ready_path)) }
    end
  end

  def wait_for_processes!(processes)
    Timeout.timeout(PROCESS_TIMEOUT_SECONDS) do
      processes.each do |process|
        _, status = Process.wait2(process.fetch(:pid))
        assert status.success?, File.read(process.fetch(:log_path))
        process[:joined] = true
      end
    end
  end

  def stop_processes(processes)
    running = processes.reject { |process| process[:joined] }
    running.each do |process|
      Process.kill("TERM", process.fetch(:pid))
    rescue Errno::ESRCH
      nil
    end

    deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 2
    running.each do |process|
      pid = process.fetch(:pid)
      reaped = false
      loop do
        if Process.waitpid(pid, Process::WNOHANG)
          reaped = true
          break
        end
        break if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline

        sleep 0.01
      end
      next if reaped

      Process.kill("KILL", pid)
      Process.wait(pid)
    rescue Errno::ESRCH, Errno::ECHILD
      nil
    end
  end

  def rails_environment(database_path)
    {
      "RAILS_ENV" => "development",
      "APP_ENVIRONMENT" => "local",
      "DB_PRIMARY_PATH" => database_path,
      "DB_BUSY_TIMEOUT_MILLISECONDS" => "5000",
      "DATABASE_URL" => nil
    }
  end
end
