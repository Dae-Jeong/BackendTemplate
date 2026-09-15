# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[8.1].define(version: 2026_09_15_045203) do
  create_table "products", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.string "product_id", limit: 128, null: false
    t.integer "stock", null: false
    t.datetime "updated_at", null: false
    t.index ["product_id"], name: "index_products_on_product_id", unique: true
    t.check_constraint "length(trim(product_id)) > 0 AND length(product_id) <= 128", name: "products_product_id_valid"
    t.check_constraint "stock >= 0", name: "products_stock_nonnegative"
  end

  create_table "reservations", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.string "product_id", limit: 128, null: false
    t.string "reservation_id", limit: 32, null: false
    t.datetime "updated_at", null: false
    t.index ["reservation_id"], name: "index_reservations_on_reservation_id", unique: true
    t.check_constraint "length(reservation_id) = 32 AND reservation_id NOT GLOB '*[^0-9a-f]*'", name: "reservations_reservation_id_format"
    t.check_constraint "length(trim(product_id)) > 0 AND length(product_id) <= 128", name: "reservations_product_id_valid"
  end
end
