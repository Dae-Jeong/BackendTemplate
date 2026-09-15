ENV["RAILS_ENV"] ||= "test"
require_relative "../config/environment"
require "rails/test_help"

module ActiveSupport
  class TestCase
    # Tests share the isolated test DB. Rails transactions isolate tests by default;
    # commit behavior is covered separately with transactional tests disabled.
  end
end
