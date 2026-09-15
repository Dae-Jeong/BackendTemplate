import { Inject, Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { TransactionRunner } from '../database/transaction-runner.js';
import type { TransactionClient } from '../database/transaction-runner.js';
import { ReservationsRepository } from '../repositories/reservations.repository.js';
import { CLOCK } from '../contracts/clock.contract.js';
import type { Clock } from '../contracts/clock.contract.js';
import type { ReservationResult } from '../contracts/reservations.contract.js';
import { SoldOut } from '../exceptions/reservations.error.js';
import {
  validateProductExists,
  validateReplayInput,
} from '../validation/reservations.js';

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
    const replay = await this.repository.findReplay(client, key);
    if (replay) {
      return {
        reservation: validateReplayInput(replay, productId),
        replayed: true,
      };
    }

    const stockDecreased = await this.repository.decreaseStock(
      client,
      productId,
    );
    if (!stockDecreased) {
      validateProductExists(
        await this.repository.productExists(client, productId),
      );
      throw new SoldOut();
    }
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
