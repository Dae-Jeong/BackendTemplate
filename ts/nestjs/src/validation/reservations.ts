import type {
  Reservation,
  ReservationReplay,
} from '../contracts/reservations.contract.js';
import {
  IdempotencyConflict,
  ProductNotFound,
} from '../exceptions/reservations.error.js';

export function validateReplayInput(
  replay: ReservationReplay,
  productId: string,
): Reservation {
  if (replay.storedProductId !== productId) {
    throw new IdempotencyConflict();
  }
  return replay.reservation;
}

export function validateProductExists(productExists: boolean): void {
  if (!productExists) throw new ProductNotFound();
}
