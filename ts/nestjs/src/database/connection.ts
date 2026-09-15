import { Worker } from 'node:worker_threads';
import { drizzle } from 'drizzle-orm/sqlite-proxy';
import { DatabaseWorkerFailed } from '../exceptions/database.error.js';
import type { QueryRequest, QueryResponse } from './worker.contract.js';

type PendingQuery = Readonly<{
  resolve: (value: { rows: unknown[] }) => void;
  reject: (error: Error) => void;
}>;

export class Connection {
  readonly worker: Worker;
  readonly db = drizzle((sql, params: unknown[], method) =>
    this.query(sql, params, method),
  );
  alive = true;
  inTransaction = false;
  private sequence = 0;
  private readonly pending = new Map<number, PendingQuery>();
  private readonly exited: Promise<number>;
  constructor(filename: string, busyTimeoutMs: number) {
    this.worker = new Worker(
      new URL('../../dist/database/sqlite.worker.js', import.meta.url),
      { workerData: { filename, busyTimeoutMs } },
    );
    this.exited = new Promise((resolve) => this.worker.once('exit', resolve));
    this.worker.on('message', (message: QueryResponse) =>
      this.settle(message),
    );
    this.worker.once('error', () => this.fail());
    this.worker.once('exit', () => this.fail());
  }
  query(
    sql: string,
    params: unknown[] = [],
    method: QueryRequest['method'] = 'run',
  ): Promise<{ rows: unknown[] }> {
    if (!this.alive) return Promise.reject(new DatabaseWorkerFailed());
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({
        id,
        sql,
        params,
        method,
      } satisfies QueryRequest);
    });
  }
  async close(): Promise<void> {
    if (this.alive) {
      try {
        await this.query('', [], 'close');
      } catch {
        await this.worker.terminate();
      }
    }
    await this.exited;
  }
  private settle(message: QueryResponse): void {
    const pending = this.pending.get(message.id);
    if (!pending) return;
    this.pending.delete(message.id);
    this.inTransaction = message.inTransaction;
    if (message.errorCode) {
      pending.reject(
        Object.assign(new Error('Database query failed'), {
          code: message.errorCode,
        }),
      );
      return;
    }
    pending.resolve({ rows: message.rows });
  }
  private fail(): void {
    this.alive = false;
    for (const pending of this.pending.values())
      pending.reject(new DatabaseWorkerFailed());
    this.pending.clear();
  }
}
