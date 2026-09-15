import { Module } from '@nestjs/common';
import type { DynamicModule } from '@nestjs/common';
import { Settings } from './config/settings.js';
import { Readiness } from './bootstrap/readiness.js';
import { clockProvider } from './providers/clock.provider.js';
import { APP_FILTER, APP_INTERCEPTOR } from '@nestjs/core';
import { ProblemFilter } from './http/problem.filter.js';
import { ExecutionInterceptor } from './http/execution.interceptor.js';
import { Metrics } from './observability/metrics.js';
import { Logging } from './observability/logging.js';
import { MetricsController } from './controllers/metrics.controller.js';
import { GreetingsController } from './controllers/greetings.controller.js';
import { GreetingsService } from './services/greetings.service.js';
import { HealthController } from './controllers/health.controller.js';
import { ReservationsController } from './controllers/reservations.controller.js';
import { ReservationsService } from './services/reservations.service.js';
import { Primary } from './database/primary.js';
import { DatabaseMetrics } from './observability/database.metrics.js';
import { ReservationsRepository } from './repositories/reservations.repository.js';
import { Shutdown } from './bootstrap/shutdown.js';
import { TransactionRunner } from './database/transaction-runner.js';

@Module({
  imports: [],
  controllers: [GreetingsController, HealthController, MetricsController],
  providers: [
    GreetingsService,
    clockProvider,
    Readiness,
    Metrics,
    Logging,
    { provide: APP_FILTER, useClass: ProblemFilter },
    { provide: APP_INTERCEPTOR, useClass: ExecutionInterceptor },
    Shutdown,
  ],
})
export class AppModule {
  static register(settings: Settings): DynamicModule {
    return {
      module: AppModule,
      controllers: settings.databaseFilename ? [ReservationsController] : [],
      providers: [
        { provide: Settings, useValue: settings },
        ...(settings.databaseFilename
          ? [
              ReservationsService,
              TransactionRunner,
              Primary,
              DatabaseMetrics,
              ReservationsRepository,
            ]
          : []),
      ],
    };
  }
}
