class CreateProducts < ActiveRecord::Migration[8.1]
  def change
    create_table :products do |t|
      t.string :product_id, limit: 128, null: false
      t.integer :stock, null: false

      t.timestamps
    end
    add_index :products, :product_id, unique: true
    add_check_constraint :products,
                         "length(trim(product_id)) > 0 AND length(product_id) <= 128",
                         name: "products_product_id_valid"
    add_check_constraint :products, "stock >= 0", name: "products_stock_nonnegative"
  end
end
