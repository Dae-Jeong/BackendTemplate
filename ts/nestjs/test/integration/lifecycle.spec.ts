import { Test } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../../src/app.module.js';
import { Primary } from '../../src/database/primary.js';
import { TransactionRunner } from '../../src/database/transaction-runner.js';
import { configureApp, createApp } from '../../src/bootstrap/app.js';
import { Readiness } from '../../src/bootstrap/readiness.js';
import { readSettings } from '../../src/config/settings.js';
import { DatabaseMetrics } from '../../src/observability/database.metrics.js';
import { fixture, seed, state } from '../helpers/database.js';

describe('DB initialization and observation failure', () => {
  it('cleans the pool after a real missing-schema initialization failure', async () => {
    const database = await fixture();
    try {
      const first = await database.app();
      const primary = first.get(Primary);
      const connection = await primary.acquire();
      try {
        await connection.query('drop table products');
      } finally {
        await primary.release(connection);
      }
      const module = await Test.createTestingModule({
        imports: [AppModule.register(database.settings)],
      }).compile();
      const app = module.createNestApplication({ logger: false });
      configureApp(app);
      const failed = app.get(Primary);
      await expect(app.init()).rejects.toThrow();
      expect(app.get(Readiness).ready).toBe(false);
      await app.close();
      expect(failed.pool!.isEmpty()).toBe(true);
    } finally {
      await database.close();
    }
  });
  it('keeps committed state when DB metrics recording fails and returns the lease', async () => {
    const database = await fixture();
    try {
      const app = await database.app();
      await seed(app);
      vi.spyOn(
        app.get(DatabaseMetrics).transactions,
        'labels',
      ).mockImplementation(() => {
        throw new Error('observation failure');
      });
      await request(app.getHttpServer())
        .post('/v1/reservations')
        .set('Idempotency-Key', 'key')
        .send({ product_id: 'widget' })
        .expect(201);
      expect(await state(app)).toEqual([[0, 1, 1]]);
      expect(app.get(Primary).pool!.numUsed()).toBe(0);
      await request(app.getHttpServer()).get('/metrics').expect(503);
    } finally {
      vi.restoreAllMocks();
      await database.close();
    }
  });
  it('DB-disabled mode is ready and omits reservation routes, schema and providers', async () => {
    const app = await createApp(readSettings({ LOG_LEVEL: 'silent' }));
    try {
      await request(app.getHttpServer())
        .get('/health/ready')
        .expect(200, { status: 'ready' });
      await request(app.getHttpServer())
        .post('/v1/reservations')
        .set('Idempotency-Key', 'key')
        .send({ product_id: 'widget' })
        .expect(404);
      await request(app.getHttpServer()).get('/v1/reservations').expect(404);
      const schema = await request(app.getHttpServer())
        .get('/openapi.json')
        .expect(200);
      expect(schema.body.paths).not.toHaveProperty('/v1/reservations');
      expect(() => app.get(Primary)).toThrow();
      expect(() => app.get(TransactionRunner)).toThrow();
      expect(() => app.get(DatabaseMetrics)).toThrow();
      expect(
        (await request(app.getHttpServer()).get('/metrics')).text,
      ).not.toContain('db_transactions_total');
    } finally {
      await app.close();
    }
  });
});
