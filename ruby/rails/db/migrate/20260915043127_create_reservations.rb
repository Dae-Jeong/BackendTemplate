class CreateReservations < ActiveRecord::Migration[8.1]
  def change
    create_table :reservations do |t|
      t.string :reservation_id, limit: 32, null: false
      t.string :product_id, limit: 128, null: false

      t.timestamps null: false
    end

    add_index :reservations, :reservation_id, unique: true
    add_check_constraint :reservations,
                         "length(reservation_id) = 32 AND reservation_id NOT GLOB '*[^0-9a-f]*'",
                         name: "reservations_reservation_id_format"
    add_check_constraint :reservations,
                         "length(trim(product_id)) > 0 AND length(product_id) <= 128",
                         name: "reservations_product_id_valid"
  end
end
