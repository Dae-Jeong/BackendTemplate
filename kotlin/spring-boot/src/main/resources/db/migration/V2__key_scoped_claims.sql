-- Add your migration SQL here
CREATE TABLE reservation_claims (idempotency_key VARCHAR(128) PRIMARY KEY);
INSERT INTO reservation_claims(idempotency_key) SELECT idempotency_key FROM idempotency_keys;
DROP TABLE reservation_guard;
