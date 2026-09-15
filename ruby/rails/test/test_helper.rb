ENV["RAILS_ENV"] ||= "test"
require_relative "../config/environment"
require "rails/test_help"

module ActiveSupport
  class TestCase
    # This minimal app has no schema yet; request tests share one isolated test DB.
  end
end
