import type { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { sql } from 'drizzle-orm';
import type { SqliteRemoteDatabase } from 'drizzle-orm/sqlite-proxy';
import { fixture, seed, state } from '../helpers/database.js';
import { Primary } from '../../src/database/primary.js';
import { ReservationsRepository } from '../../src/repositories/reservations.repository.js';
import { ReservationsService } from '../../src/services/reservations.service.js';
import { reservations } from '../../src/models/reservations.schema.js';
import { DatabaseMetrics } from '../../src/observability/database.metrics.js';

const reserve = (app: INestApplication, key = 'key-1', product_id = 'widget') =>
  request(app.getHttpServer())
    .post('/v1/reservations')
    .set('Idempotency-Key', key)
    .send({ product_id });

describe('real SQLite reservations', () => {
  let database: Awaited<ReturnType<typeof fixture>>;
  let app: INestApplication;
  beforeEach(async () => {
    database = await fixture();
    app = await database.app();
    await seed(app);
  });
  afterEach(async () => {
    vi.restoreAllMocks();
    await database.close();
  });
  it('migrates twice, seeds without resetting stock, commits and replays original result', async () => {
    await database.migrate();
    const created = await reserve(app).expect(201);
    expect(created.headers['idempotency-replayed']).toBe('false');
    expect(Object.keys(created.body.data).sort()).toEqual([
      'created_at',
      'product_id',
      'reservation_id',
    ]);
    expect(created.body.data.reservation_id).toMatch(/^[a-f0-9]{32}$/);
    await seed(app, 'widget', 99);
    const replay = await reserve(app).expect(201);
    expect(replay.headers['idempotency-replayed']).toBe('true');
    expect(replay.body).toEqual(created.body);
    expect((await reserve(app, 'other')).body.code).toBe('SOLD_OUT');
    expect((await reserve(app, 'key-1', 'other')).body.code).toBe(
      'IDEMPOTENCY_CONFLICT',
    );
    expect(await state(app)).toEqual([[0, 1, 1]]);
  });
  it('uses the stored key product as authoritative replay input', async () => {
    await reserve(app).expect(201);
    await seed(app, 'other', 1);
    const before = await state(app);
    const primary = app.get(Primary);
    const connection = await primary.acquire();
    try {
      await connection.query(
        'update idempotency_keys set product_id = ? where key = ?',
        ['other', 'key-1'],
        'run',
      );
    } finally {
      await primary.release(connection);
    }

    const response = await reserve(app).expect(409);
    expect(response.body.code).toBe('IDEMPOTENCY_CONFLICT');
    expect(response.headers['idempotency-replayed']).toBeUndefined();
    expect(await state(app)).toEqual(before);
  });
  it.each([
    ['invalid shape', { reservation_id: 'reservation-1' }],
    [
      'invalid id type',
      {
        reservation_id: 1,
        product_id: 'widget',
        created_at: '2026-09-16T01:02:03.004Z',
      },
    ],
    [
      'invalid date',
      {
        reservation_id: 'reservation-1',
        product_id: 'widget',
        created_at: '2026-02-30T01:02:03.004Z',
      },
    ],
  ])(
    'returns 500 without further writes for a corrupted snapshot with %s',
    async (_case, damagedSnapshot) => {
      await reserve(app).expect(201);
      const primary = app.get(Primary);
      const connection = await primary.acquire();
      try {
        await connection.query(
          'update idempotency_keys set response = ? where key = ?',
          [JSON.stringify(damagedSnapshot), 'key-1'],
          'run',
        );
      } finally {
        await primary.release(connection);
      }

      const response = await reserve(app).expect(500);
      expect(response.body.code).toBe('INTERNAL_ERROR');
      expect(response.headers['idempotency-replayed']).toBeUndefined();
      expect(await state(app)).toEqual([[0, 1, 1]]);

      const metrics = await app.get(DatabaseMetrics).transactions.get();
      expect(
        metrics.values.find(
          (value) =>
            'outcome' in value.labels && value.labels.outcome === 'rolled_back',
        )?.value,
      ).toBe(1);
    },
  );
  it('validates body/header and maps missing product', async () => {
    expect((await reserve(app, 'key', 'missing').expect(404)).body.code).toBe(
      'PRODUCT_NOT_FOUND',
    );
    const missing = await request(app.getHttpServer())
      .post('/v1/reservations')
      .send({ product_id: 'widget' })
      .expect(422);
    expect(missing.body.errors).toEqual([
      { location: ['header', 'Idempotency-Key'], code: 'REQUIRED' },
    ]);
    for (const body of [
      { product_id: 1 },
      { product_id: '' },
      { product_id: 'widget', private: 'private-secret' },
      ['widget'],
      null,
    ]) {
      const response = await request(app.getHttpServer())
        .post('/v1/reservations')
        .set('Idempotency-Key', 'x')
        .send(JSON.stringify(body))
        .set('Content-Type', 'application/json')
        .expect(422);
      expect(response.text).not.toContain('private');
    }
    expect(
      (await reserve(app, 'private space').expect(422)).body.errors[0].location,
    ).toEqual(['header', 'Idempotency-Key']);
    expect(await state(app)).toEqual([[1, 0, 0]]);
  });
  it.each(['saveReservation', 'saveIdempotency'] as const)(
    'rolls back %s failure and permits same key retry',
    async (method) => {
      const spy = vi
        .spyOn(app.get(ReservationsRepository), method)
        .mockRejectedValueOnce(new Error('private-save'));
      const failed = await reserve(app).expect(500);
      expect(failed.text).not.toContain('private');
      expect(await state(app)).toEqual([[1, 0, 0]]);
      spy.mockRestore();
      await reserve(app).expect(201);
      expect(await state(app)).toEqual([[0, 1, 1]]);
    },
  );
  it('a real deferred foreign-key commit failure never returns success or increments committed metrics', async () => {
    const repository = app.get(ReservationsRepository);
    const save = repository.saveIdempotency.bind(repository);
    const spy = vi
      .spyOn(repository, 'saveIdempotency')
      .mockImplementationOnce(async (client, key, reservation) => {
        await save(client, key, reservation);
        // The production transaction client is used; the violation is checked by SQLite at COMMIT.
        await (client as SqliteRemoteDatabase).run(
          sql`pragma defer_foreign_keys = ON`,
        );
        await client
          .insert(reservations)
          .values({
            id: 'orphan',
            productId: 'missing',
            createdAt: new Date().toISOString(),
          });
        const metrics = await app.get(DatabaseMetrics).transactions.get();
        expect(
          metrics.values.find(
            (value) =>
              'outcome' in value.labels && value.labels.outcome === 'committed',
          )?.value,
        ).toBe(0);
      });
    await reserve(app).expect(500);
    expect(await state(app)).toEqual([[1, 0, 0]]);
    const metrics = await app.get(DatabaseMetrics).transactions.get();
    expect(
      metrics.values.find(
        (value) =>
          'outcome' in value.labels && value.labels.outcome === 'failed',
      )?.value,
    ).toBe(1);
    spy.mockRestore();
    await reserve(app).expect(201);
  });
  it('serializes independent app connections on stock one', async () => {
    const other = await database.app();
    const responses = await Promise.all([
      reserve(app, 'one'),
      reserve(other, 'two'),
    ]);
    expect(responses.map((r) => r.status).sort()).toEqual([201, 409]);
    expect(await state(app)).toEqual([[0, 1, 1]]);
  });
  it('replays concurrent same keys and rejects concurrent conflicting input', async () => {
    const other = await database.app();
    const responses = await Promise.all([reserve(app), reserve(other)]);
    expect(responses.map((r) => r.status)).toEqual([201, 201]);
    expect(responses[0].body).toEqual(responses[1].body);
    expect(
      responses.map((r) => r.headers['idempotency-replayed']).sort(),
    ).toEqual(['false', 'true']);
    const conflicting = await reserve(other, 'key-1', 'missing').expect(409);
    expect(conflicting.body.code).toBe('IDEMPOTENCY_CONFLICT');
    expect(await state(app)).toEqual([[0, 1, 1]]);
  });
  it('classifies real lock timeout and keeps health/timers responsive while SQLite waits', async () => {
    const other = await database.app();
    const primary = app.get(Primary);
    const locked = await primary.acquire();
    await locked.query('begin immediate');
    let finished = false;
    const pending = reserve(other).then((response) => {
      finished = true;
      return response;
    });
    try {
      await new Promise((resolve) => setTimeout(resolve, 30));
      await request(other.getHttpServer()).get('/health/live').expect(200);
      expect(finished).toBe(false);
      const response = await pending;
      expect(response.status).toBe(503);
      expect(response.body.code).toBe('DATABASE_BUSY');
      expect(response.headers['retry-after']).toBe('1');
    } finally {
      await locked.query('rollback');
      await primary.release(locked);
    }
    await reserve(other).expect(201);
  });
  it('reports pool exhaustion separately and recovers after release', async () => {
    const primary = app.get(Primary);
    const held = await Promise.all([primary.acquire(), primary.acquire()]);
    try {
      const response = await reserve(app).expect(503);
      expect(response.body.code).toBe('DATABASE_POOL_TIMEOUT');
      expect(primary.pool!.numUsed()).toBe(2);
    } finally {
      await Promise.all(held.map((c) => primary.release(c)));
    }
    await reserve(app).expect(201);
    expect(primary.pool!.numUsed()).toBe(0);
  });
  it('replaces a failed worker and preserves database atomicity', async () => {
    const primary = app.get(Primary);
    const connection = await primary.acquire();
    await connection.query('begin immediate');
    await connection.query('update products set available=0');
    await connection.worker.terminate();
    await primary.release(connection);
    await reserve(app).expect(201);
    expect(await state(app)).toEqual([[0, 1, 1]]);
  });
  it('discards a dirty connection after rollback itself fails', async () => {
    const primary = app.get(Primary);
    const acquire = primary.acquire.bind(primary);
    vi.spyOn(primary, 'acquire').mockImplementationOnce(async () => {
      const connection = await acquire();
      const query = connection.query.bind(connection);
      vi.spyOn(connection, 'query').mockImplementation((sql, params, method) =>
        sql.toLowerCase() === 'rollback'
          ? Promise.reject(new Error('rollback failed'))
          : query(sql, params, method),
      );
      return connection;
    });
    vi.spyOn(
      app.get(ReservationsRepository),
      'saveReservation',
    ).mockRejectedValueOnce(new Error('save failed'));
    await expect(
      app.get(ReservationsService).reserve('widget', 'key'),
    ).rejects.toThrow();
    expect(await state(app)).toEqual([[1, 0, 0]]);
    await reserve(app, 'key').expect(201);
  });
});
