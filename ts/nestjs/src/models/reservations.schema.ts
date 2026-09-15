import { sql } from 'drizzle-orm';
import { sqliteTable, text, integer, check } from 'drizzle-orm/sqlite-core';

export const products = sqliteTable(
  'products',
  {
    id: text('id').primaryKey(),
    available: integer('available').notNull(),
  },
  (table) => [
    check('products_available_nonnegative', sql`${table.available} >= 0`),
  ],
);
export const reservations = sqliteTable('reservations', {
  id: text('id').primaryKey(),
  productId: text('product_id')
    .notNull()
    .references(() => products.id),
  createdAt: text('created_at').notNull(),
});
export const idempotencyKeys = sqliteTable(
  'idempotency_keys',
  {
    key: text('key').primaryKey(),
    productId: text('product_id')
      .notNull()
      .references(() => products.id),
    reservationId: text('reservation_id')
      .notNull()
      .unique()
      .references(() => reservations.id),
    response: text('response', { mode: 'json' }).$type<unknown>().notNull(),
  },
  (table) => [
    check(
      'idempotency_key_length',
      sql`length(${table.key}) BETWEEN 1 AND 128`,
    ),
  ],
);
