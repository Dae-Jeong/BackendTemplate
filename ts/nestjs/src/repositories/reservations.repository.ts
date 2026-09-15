import { Injectable } from '@nestjs/common';
import { and, eq, gt, sql } from 'drizzle-orm';
import type { TransactionClient } from '../database/transaction-runner.js';
import {
  products,
  reservations,
  idempotencyKeys,
} from '../models/reservations.schema.js';
import type {
  Reservation,
  ReservationReplay,
} from '../contracts/reservations.contract.js';
import {
  decodeReservationSnapshot,
  encodeReservationSnapshot,
} from '../models/reservation-snapshot.js';

@Injectable()
export class ReservationsRepository {
  async findReplay(
    client: TransactionClient,
    key: string,
  ): Promise<ReservationReplay | undefined> {
    const [existing] = await client
      .select()
      .from(idempotencyKeys)
      .where(eq(idempotencyKeys.key, key));
    if (!existing) return undefined;
    return {
      storedProductId: existing.productId,
      reservation: decodeReservationSnapshot(existing.response),
    };
  }
  async decreaseStock(
    client: TransactionClient,
    productId: string,
  ): Promise<boolean> {
    const changed = await client
      .update(products)
      .set({ available: sql`${products.available} - 1` })
      .where(and(eq(products.id, productId), gt(products.available, 0)))
      .returning({ id: products.id });
    return changed.length > 0;
  }
  async productExists(
    client: TransactionClient,
    productId: string,
  ): Promise<boolean> {
    const existing = await client
      .select({ id: products.id })
      .from(products)
      .where(eq(products.id, productId));
    return existing.length > 0;
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
