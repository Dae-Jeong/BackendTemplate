import type { Reservation } from '../contracts/reservations.contract.js';

export type ReservationSnapshot = Readonly<{
  reservation_id: string;
  product_id: string;
  created_at: string;
}>;

export function encodeReservationSnapshot(
  reservation: Reservation,
): ReservationSnapshot {
  return {
    reservation_id: reservation.reservationId,
    product_id: reservation.productId,
    created_at: reservation.createdAt.toISOString(),
  };
}

export function decodeReservationSnapshot(value: unknown): Reservation {
  if (!isRecord(value)) throw invalidSnapshot();
  const { reservation_id, product_id, created_at } = value;
  if (
    typeof reservation_id !== 'string' ||
    reservation_id.length === 0 ||
    typeof product_id !== 'string' ||
    product_id.length === 0 ||
    typeof created_at !== 'string'
  ) {
    throw invalidSnapshot();
  }

  const createdAt = new Date(created_at);
  if (
    Number.isNaN(createdAt.getTime()) ||
    createdAt.toISOString() !== created_at
  ) {
    throw invalidSnapshot();
  }
  return { reservationId: reservation_id, productId: product_id, createdAt };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function invalidSnapshot(): TypeError {
  return new TypeError('Invalid persisted reservation snapshot');
}
