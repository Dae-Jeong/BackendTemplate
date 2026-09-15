require "test_helper"

class ProductTest < ActiveSupport::TestCase
  test "enforces public identifier uniqueness and nonnegative stock" do
    Product.create!(product_id: "product-1", stock: 1)

    duplicate = Product.new(product_id: "product-1", stock: -1)

    refute duplicate.valid?
    assert duplicate.errors.of_kind?(:product_id, :taken)
    assert duplicate.errors.of_kind?(:stock, :greater_than_or_equal_to)
  end

  test "database constraint rejects negative stock" do
    error = assert_raises(ActiveRecord::StatementInvalid) do
      Product.connection.exec_insert(<<~SQL)
        INSERT INTO products (product_id, stock, created_at, updated_at)
        VALUES ('negative-stock', -1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
      SQL
    end

    assert_kind_of ActiveRecord::CheckViolation, error
    assert_equal 0, Product.where(product_id: "negative-stock").count
  end

  test "repeat seed preserves existing stock" do
    Product.seed_unless_exists!(product_id: "product-1", stock: 10)
    Product.where(product_id: "product-1").update_all(stock: 4)

    Product.seed_unless_exists!(product_id: "product-1", stock: 10)

    assert_equal 4, Product.find_by!(product_id: "product-1").stock
  end
end
