import { Inject, Injectable } from '@nestjs/common';
import type { SqliteRemoteDatabase } from 'drizzle-orm/sqlite-proxy';
import type { TransactionOutcome } from '../contracts/observation.contract.js';
import { DatabaseBusy, isDatabaseBusy } from '../exceptions/database.error.js';
import { DatabaseMetrics } from '../observability/database.metrics.js';
import { Primary } from './primary.js';

export type TransactionClient = Pick<
  SqliteRemoteDatabase,
  'select' | 'insert' | 'update'
>;

@Injectable()
export class TransactionRunner {
  constructor(
    @Inject(Primary) private readonly primary: Primary,
    @Inject(DatabaseMetrics) private readonly metrics: DatabaseMetrics,
  ) {}

  async run<T>(
    callback: (client: TransactionClient) => Promise<T>,
  ): Promise<T> {
    const started = performance.now();
    let outcome: TransactionOutcome = 'failed';
    let bodyError: unknown;
    try {
      const connection = await this.primary.acquire();
      try {
        const result = await connection.db.transaction(
          async (client) => {
            try {
              return await callback(client);
            } catch (error) {
              bodyError = error;
              throw error;
            }
          },
          { behavior: 'immediate' },
        );
        outcome = 'committed';
        return result;
      } finally {
        await this.primary.release(connection);
      }
    } catch (error) {
      // Drizzle rethrows the callback error only after rollback succeeds.
      // COMMIT or ROLLBACK failures are different errors and remain 'failed'.
      if (bodyError !== undefined && error === bodyError)
        outcome = 'rolled_back';
      if (isDatabaseBusy(error)) throw new DatabaseBusy();
      throw error;
    } finally {
      this.metrics.transaction(outcome, (performance.now() - started) / 1000);
    }
  }
}
