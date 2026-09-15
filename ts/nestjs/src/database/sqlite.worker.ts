import { parentPort, workerData } from 'node:worker_threads';
import Database from 'better-sqlite3';
import type { QueryRequest, QueryResponse } from './worker.contract.js';

const { filename, busyTimeoutMs } = workerData as {
  filename: string;
  busyTimeoutMs: number;
};
const database = new Database(filename, {
  timeout: busyTimeoutMs,
  fileMustExist: true,
});
database.pragma('foreign_keys = ON');
database.pragma('synchronous = FULL');
const port = parentPort!;

function execute(
  sql: string,
  params: unknown[],
  method: Exclude<QueryRequest['method'], 'close'>,
): unknown[] {
  const statement = database.prepare(sql);
  switch (method) {
    case 'run':
      statement.run(...params);
      return [];
    case 'get':
      return (statement.raw().get(...params) as unknown[] | undefined) ?? [];
    case 'all':
    case 'values':
      return statement.raw().all(...params);
  }
}

port.on('message', (query: QueryRequest) => {
  if (query.method === 'close') {
    database.close();
    port.postMessage({
      id: query.id,
      rows: [],
      inTransaction: false,
    } satisfies QueryResponse);
    port.close();
    return;
  }
  try {
    const rows = execute(query.sql, query.params, query.method);
    port.postMessage({
      id: query.id,
      rows,
      inTransaction: database.inTransaction,
    } satisfies QueryResponse);
  } catch (error) {
    const code =
      error instanceof Error &&
      'code' in error &&
      typeof error.code === 'string'
        ? error.code
        : 'SQLITE_ERROR';
    port.postMessage({
      id: query.id,
      rows: [],
      inTransaction: database.inTransaction,
      errorCode: code,
    } satisfies QueryResponse);
  }
});
