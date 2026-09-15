-- Add your migration SQL here
CREATE TABLE products (
    id VARCHAR(64) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
CREATE TABLE reservations (
    id VARCHAR(32) PRIMARY KEY,
    product_id VARCHAR(64) NOT NULL REFERENCES products(id),
    created_at VARCHAR(40) NOT NULL
);
CREATE INDEX reservations_product ON reservations(product_id);
CREATE TABLE idempotency_keys (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    product_id VARCHAR(64) NOT NULL REFERENCES products(id),
    reservation_id VARCHAR(32) NOT NULL UNIQUE REFERENCES reservations(id),
    created_at VARCHAR(40) NOT NULL
);
CREATE TABLE reservation_guard (id INTEGER PRIMARY KEY CHECK (id = 1));
INSERT INTO reservation_guard(id) VALUES (1);
