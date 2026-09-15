import type { Connection } from '../../src/database/connection.js';
import type { Primary } from '../../src/database/primary.js';
import {
  TransactionRunner,
  type TransactionClient,
} from '../../src/database/transaction-runner.js';
import { DatabaseBusy } from '../../src/exceptions/database.error.js';
import { DatabaseMetrics } from '../../src/observability/database.metrics.js';
import { Metrics } from '../../src/observability/metrics.js';

type Transaction = Connection['db']['transaction'];

function runnerWith(transaction: Transaction) {
  const connection = { db: { transaction } } as Connection;
  const primary = {
    acquire: vi.fn().mockResolvedValue(connection),
    release: vi.fn().mockResolvedValue(undefined),
  } as unknown as Primary;
  const metrics = new DatabaseMetrics(new Metrics());
  return {
    connection,
    metrics,
    primary,
    runner: new TransactionRunner(primary, metrics),
  };
}

async function transactionCount(
  metrics: DatabaseMetrics,
  outcome: string,
): Promise<number | undefined> {
  return (await metrics.transactions.get()).values.find(
    (value) => 'outcome' in value.labels && value.labels.outcome === outcome,
  )?.value;
}

describe('TransactionRunner', () => {
  it('returns the callback result after an immediate commit and release', async () => {
    const client = {} as TransactionClient;
    const transaction = vi.fn(async (callback) => callback(client));
    const { connection, metrics, primary, runner } = runnerWith(transaction);

    await expect(runner.run(async (received) => received)).resolves.toBe(
      client,
    );
    expect(transaction).toHaveBeenCalledWith(expect.any(Function), {
      behavior: 'immediate',
    });
    expect(primary.release).toHaveBeenCalledWith(connection);
    expect(await transactionCount(metrics, 'committed')).toBe(1);
  });

  it('preserves a callback error after rollback and records rolled_back', async () => {
    const client = {} as TransactionClient;
    const transaction = vi.fn(async (callback) => callback(client));
    const { metrics, primary, runner } = runnerWith(transaction);
    const original = new Error('business failure');

    await expect(runner.run(async () => Promise.reject(original))).rejects.toBe(
      original,
    );
    expect(primary.release).toHaveBeenCalledOnce();
    expect(await transactionCount(metrics, 'rolled_back')).toBe(1);
  });

  it('does not release when acquisition fails', async () => {
    const transaction = vi.fn() as Transaction;
    const { metrics, primary, runner } = runnerWith(transaction);
    const acquisition = new Error('acquisition failed');
    vi.mocked(primary.acquire).mockRejectedValueOnce(acquisition);

    await expect(runner.run(async () => 'unused')).rejects.toBe(acquisition);
    expect(primary.release).not.toHaveBeenCalled();
    expect(transaction).not.toHaveBeenCalled();
    expect(await transactionCount(metrics, 'failed')).toBe(1);
  });

  it('attempts release when begin fails before invoking the callback', async () => {
    const boundary = new Error('begin failed');
    const transaction = vi.fn().mockRejectedValue(boundary) as Transaction;
    const { metrics, primary, runner } = runnerWith(transaction);
    const callback = vi.fn(async () => 'unused');

    await expect(runner.run(callback)).rejects.toBe(boundary);
    expect(callback).not.toHaveBeenCalled();
    expect(primary.release).toHaveBeenCalledOnce();
    expect(await transactionCount(metrics, 'failed')).toBe(1);
  });

  it('preserves release-error precedence when transaction finalization also fails', async () => {
    const boundary = new Error('commit or rollback failed');
    const cleanup = new Error('release failed');
    const transaction = vi.fn().mockRejectedValue(boundary) as Transaction;
    const { metrics, primary, runner } = runnerWith(transaction);
    vi.mocked(primary.release).mockRejectedValueOnce(cleanup);

    await expect(runner.run(async () => 'unused')).rejects.toBe(cleanup);
    expect(await transactionCount(metrics, 'failed')).toBe(1);
  });

  it('keeps a successful commit classified as committed when release fails', async () => {
    const transaction = vi.fn(async (callback) =>
      callback({} as TransactionClient),
    );
    const { metrics, primary, runner } = runnerWith(transaction);
    const cleanup = new Error('release failed');
    vi.mocked(primary.release).mockRejectedValueOnce(cleanup);

    await expect(runner.run(async () => 'committed')).rejects.toBe(cleanup);
    expect(await transactionCount(metrics, 'committed')).toBe(1);
  });

  it('translates only technical SQLite busy failures', async () => {
    const busy = Object.assign(new Error('private database message'), {
      code: 'SQLITE_BUSY_TIMEOUT',
    });
    const transaction = vi.fn().mockRejectedValue(busy) as Transaction;
    const { runner } = runnerWith(transaction);

    await expect(runner.run(async () => 'unused')).rejects.toBeInstanceOf(
      DatabaseBusy,
    );
  });

  it('isolates transaction metric failures from a committed result', async () => {
    const transaction = vi.fn(async (callback) =>
      callback({} as TransactionClient),
    );
    const { metrics, primary, runner } = runnerWith(transaction);
    vi.spyOn(metrics.transactions, 'labels').mockImplementation(() => {
      throw new Error('observation failure');
    });

    await expect(runner.run(async () => 'committed')).resolves.toBe(
      'committed',
    );
    expect(primary.release).toHaveBeenCalledOnce();
    expect(metrics.owner.failed).toBe(true);
  });

  it('does not let a transaction metric failure mask the original callback error', async () => {
    const transaction = vi.fn(async (callback) =>
      callback({} as TransactionClient),
    );
    const { metrics, primary, runner } = runnerWith(transaction);
    const original = new Error('business failure');
    vi.spyOn(metrics.transactions, 'labels').mockImplementation(() => {
      throw new Error('observation failure');
    });

    await expect(runner.run(async () => Promise.reject(original))).rejects.toBe(
      original,
    );
    expect(primary.release).toHaveBeenCalledOnce();
    expect(metrics.owner.failed).toBe(true);
  });
});
