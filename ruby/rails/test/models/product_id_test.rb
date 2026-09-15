require "test_helper"

class ProductIdTest < ActiveSupport::TestCase
  test "normalizes surrounding whitespace and accepts the maximum length" do
    assert_equal "product-1", ProductId.normalize("  product-1  ")
    assert_equal "a" * ProductId::MAX_LENGTH, ProductId.normalize("a" * ProductId::MAX_LENGTH)
  end

  test "reports required for nil" do
    assert_invalid_reason "REQUIRED", nil
  end

  test "reports invalid type for non-strings" do
    assert_invalid_reason "INVALID_TYPE", 123
  end

  test "reports too short after stripping" do
    assert_invalid_reason "TOO_SHORT", "  "
  end

  test "reports too long after stripping" do
    assert_invalid_reason "TOO_LONG", "a" * (ProductId::MAX_LENGTH + 1)
  end

  private

  def assert_invalid_reason(reason, value)
    error = assert_raises(ProductId::Invalid) { ProductId.normalize(value) }
    assert_equal reason, error.reason
  end
end
