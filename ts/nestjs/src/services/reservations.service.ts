import { Inject, Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { TransactionRunner } from '../database/transaction-runner.js';
import type { TransactionClient } from '../database/transaction-runner.js';
import { ReservationsRepository } from '../repositories/reservations.repository.js';
import { CLOCK } from '../contracts/clock.contract.js';
import type { Clock } from '../contracts/clock.contract.js';
import type { ReservationResult } from '../contracts/reservations.contract.js';

@Injectable()
export class ReservationsService {
  constructor(
    @Inject(TransactionRunner)
    private readonly transactions: TransactionRunner,
    @Inject(ReservationsRepository)
    private readonly repository: ReservationsRepository,
    @Inject(CLOCK) private readonly clock: Clock,
  ) {}
  async reserve(productId: string, key: string): Promise<ReservationResult> {
    return this.transactions.run((client) =>
      this.reserveInTransaction(client, productId, key),
    );
  }

  private async reserveInTransaction(
    client: TransactionClient,
    productId: string,
    key: string,
  ): Promise<ReservationResult> {
    const existing = await this.repository.findMatchingReplay(
      client,
      key,
      productId,
    );
    if (existing) return { reservation: existing, replayed: true };

    await this.repository.decreaseStock(client, productId);
    const reservation = {
      reservationId: randomUUID().replaceAll('-', ''),
      productId,
      createdAt: this.clock(),
    };
    await this.repository.saveReservation(client, reservation);
    await this.repository.saveIdempotency(client, key, reservation);
    return { reservation, replayed: false };
  }
}
