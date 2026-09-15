export type Reservation = Readonly<{
  reservationId: string;
  productId: string;
  createdAt: Date;
}>;
export type ReservationResult = Readonly<{
  reservation: Reservation;
  replayed: boolean;
}>;
