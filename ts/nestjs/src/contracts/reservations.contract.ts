export type Reservation = Readonly<{
  reservationId: string;
  productId: string;
  createdAt: Date;
}>;
export type ReservationReplay = Readonly<{
  storedProductId: string;
  reservation: Reservation;
}>;
export type ReservationResult = Readonly<{
  reservation: Reservation;
  replayed: boolean;
}>;
