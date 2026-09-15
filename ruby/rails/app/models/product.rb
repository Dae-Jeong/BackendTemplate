class Product < ApplicationRecord
  PRODUCT_ID_MAX_LENGTH = 128

  validates :product_id,
            presence: true,
            length: { maximum: PRODUCT_ID_MAX_LENGTH },
            uniqueness: true
  validates :stock, numericality: { only_integer: true, greater_than_or_equal_to: 0 }

  def self.decrement_stock(product_id:, timestamp:)
    where(product_id: product_id)
      .where("stock > 0")
      .update_all(stock: Arel.sql("stock - 1"), updated_at: timestamp)
  end

  def self.exists_by_product_id?(product_id)
    exists?(product_id: product_id)
  end

  def self.seed_unless_exists!(product_id:, stock:)
    find_or_create_by!(product_id: product_id) do |product|
      product.stock = stock
    end
  end
end
