import { Injectable } from '@nestjs/common';
import { and, eq, gt, sql } from 'drizzle-orm';
import type { TransactionClient } from '../database/transaction-runner.js';
import {
  products,
  reservations,
  idempotencyKeys,
} from '../models/reservations.schema.js';
import type { Reservation } from '../contracts/reservations.contract.js';
import {
  decodeReservationSnapshot,
  encodeReservationSnapshot,
} from '../models/reservation-snapshot.js';
import {
  ProductNotFound,
  SoldOut,
  IdempotencyConflict,
} from '../exceptions/reservations.error.js';

@Injectable()
export class ReservationsRepository {
  async findMatchingReplay(
    client: TransactionClient,
    key: string,
    productId: string,
  ): Promise<Reservation | undefined> {
    const [existing] = await client
      .select()
      .from(idempotencyKeys)
      .where(eq(idempotencyKeys.key, key));
    if (!existing) return undefined;
    if (existing.productId !== productId) throw new IdempotencyConflict();
    return decodeReservationSnapshot(existing.response);
  }
  async decreaseStock(
    client: TransactionClient,
    productId: string,
  ): Promise<void> {
    const changed = await client
      .update(products)
      .set({ available: sql`${products.available} - 1` })
      .where(and(eq(products.id, productId), gt(products.available, 0)))
      .returning({ id: products.id });
    if (changed.length) return;
    const existing = await client
      .select({ id: products.id })
      .from(products)
      .where(eq(products.id, productId));
    if (!existing.length) throw new ProductNotFound();
    throw new SoldOut();
  }
  async saveReservation(
    client: TransactionClient,
    reservation: Reservation,
  ): Promise<void> {
    await client.insert(reservations).values({
      id: reservation.reservationId,
      productId: reservation.productId,
      createdAt: reservation.createdAt.toISOString(),
    });
  }
  async saveIdempotency(
    client: TransactionClient,
    key: string,
    reservation: Reservation,
  ): Promise<void> {
    await client.insert(idempotencyKeys).values({
      key,
      productId: reservation.productId,
      reservationId: reservation.reservationId,
      response: encodeReservationSnapshot(reservation),
    });
  }
  async seed(
    client: TransactionClient,
    productId: string,
    available: number,
  ): Promise<void> {
    await client
      .insert(products)
      .values({ id: productId, available })
      .onConflictDoNothing();
  }
}
