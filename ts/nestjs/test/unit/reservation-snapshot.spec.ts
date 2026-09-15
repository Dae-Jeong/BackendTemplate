import {
  decodeReservationSnapshot,
  encodeReservationSnapshot,
} from '../../src/models/reservation-snapshot.js';

describe('reservation snapshot boundary', () => {
  const snapshot = {
    reservation_id: 'reservation-1',
    product_id: 'widget',
    created_at: '2026-09-16T01:02:03.004Z',
  };

  it('decodes and exactly re-encodes a stored snapshot', () => {
    const reservation = decodeReservationSnapshot({
      ...snapshot,
      stored_metadata: 'ignored',
    });
    expect(reservation).toEqual({
      reservationId: 'reservation-1',
      productId: 'widget',
      createdAt: new Date('2026-09-16T01:02:03.004Z'),
    });
    expect(encodeReservationSnapshot(reservation)).toEqual(snapshot);
  });

  it.each([
    null,
    [],
    {},
    { ...snapshot, reservation_id: 1 },
    { ...snapshot, reservation_id: '' },
    { ...snapshot, product_id: null },
    { ...snapshot, product_id: '' },
    { ...snapshot, created_at: 1 },
    { ...snapshot, created_at: 'not-a-date' },
    { ...snapshot, created_at: '2026-02-30T01:02:03.004Z' },
    { ...snapshot, created_at: '2026-09-16T01:02:03Z' },
  ])('rejects an invalid persisted value: %j', (value) => {
    expect(() => decodeReservationSnapshot(value)).toThrow(
      'Invalid persisted reservation snapshot',
    );
  });
});
