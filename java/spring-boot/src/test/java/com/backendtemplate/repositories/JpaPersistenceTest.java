package com.backendtemplate.repositories;

import static org.assertj.core.api.Assertions.*;
import com.backendtemplate.TemplateApplication;
import com.backendtemplate.exceptions.IdempotencyClaimed;
import com.backendtemplate.exceptions.ReservationFailure;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.persistence.EntityManager;
import java.nio.file.Files;
import java.sql.DriverManager;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;

class JpaPersistenceTest {
    @Test
    void modifyingQueryFlushesPendingInsertAndDetachesStaleProduct() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-jpa-fresh-").resolve("db");
        try (var app = new SpringApplicationBuilder(TemplateApplication.class, WorkConfiguration.class)
                .web(WebApplicationType.NONE).run("--spring.datasource.url=" + url)) {
            assertThat(app.getBeansOfType(PlatformTransactionManager.class)).hasSize(1);
            assertThat(app.getBean(PlatformTransactionManager.class)).isInstanceOf(JpaTransactionManager.class);
            app.getBean(Work.class).decreaseWithManagedProduct();
        }
        try (var connection = DriverManager.getConnection(url, "sa", ""); var sql = connection.createStatement();
                var rows = sql.executeQuery("SELECT available FROM products WHERE id='fresh'")) {
            assertThat(rows.next()).isTrue();
            assertThat(rows.getInt(1)).isEqualTo(1);
        }
    }

    @Test
    void orderedBatchPreservesForeignKeysAndRollsBackFailedResult() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-jpa-batch-").resolve("db");
        try (var app = new SpringApplicationBuilder(TemplateApplication.class)
                .web(WebApplicationType.NONE).run("--spring.datasource.url=" + url,
                        "--spring.jpa.properties.hibernate.jdbc.batch_size=16",
                        "--spring.jpa.properties.hibernate.order_inserts=true")) {
            var service = app.getBean(com.backendtemplate.services.ReservationService.class);
            app.getBean(com.backendtemplate.services.ProductSeedService.class).seed("batch", 2);
            var first = service.reserve("batch", "first");
            assertThat(service.replay("batch", "first").reservation()).isEqualTo(first.reservation());
            assertThatThrownBy(() -> service.replay("other", "first"))
                    .isInstanceOfSatisfying(ReservationFailure.class,
                            failure -> assertThat(failure.reason())
                                    .isEqualTo(ReservationFailure.Reason.IDEMPOTENCY_CONFLICT));
            try (var connection = DriverManager.getConnection(url, "sa", ""); var sql = connection.createStatement()) {
                sql.execute("ALTER TABLE idempotency_keys ADD CONSTRAINT reject_second CHECK (idempotency_key <> 'second')");
            }
            assertThatThrownBy(() -> service.reserve("batch", "second"))
                    .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
            try (var connection = DriverManager.getConnection(url, "sa", ""); var sql = connection.createStatement()) {
                for (String query : java.util.List.of("SELECT available FROM products WHERE id='batch'",
                        "SELECT count(*) FROM reservations", "SELECT count(*) FROM reservation_claims",
                        "SELECT count(*) FROM idempotency_keys")) {
                    try (var rows = sql.executeQuery(query)) {
                        rows.next();
                        assertThat(rows.getInt(1)).isEqualTo(1);
                    }
                }
            }
        }
    }

    @Test
    void simultaneousJpaClaimFlushHasOneWinnerAndOneRollback() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-jpa-claim-").resolve("db");
        try (var app = new SpringApplicationBuilder(TemplateApplication.class, WorkConfiguration.class)
                .web(WebApplicationType.NONE).run("--spring.datasource.url=" + url,
                        "--spring.jpa.properties.hibernate.jdbc.batch_size=16",
                        "--spring.jpa.properties.hibernate.order_inserts=true");
                var executor = Executors.newFixedThreadPool(2)) {
            var barrier = new CyclicBarrier(2);
            var work = app.getBean(Work.class);
            Callable<String> claim = () -> {
                try { work.claim(barrier); return "winner"; }
                catch (IdempotencyClaimed expected) { return "collision"; }
            };
            var first = executor.submit(claim);
            var second = executor.submit(claim);
            assertThat(java.util.List.of(first.get(10, TimeUnit.SECONDS), second.get(10, TimeUnit.SECONDS)))
                    .containsExactlyInAnyOrder("winner", "collision");
            var meters = app.getBean(MeterRegistry.class);
            assertThat(meters.get("db.transactions").tags("role", "primary", "outcome", "committed").counter().count()).isEqualTo(1);
            assertThat(meters.get("db.transactions").tags("role", "primary", "outcome", "rolled_back").counter().count()).isEqualTo(1);
            try (var connection = DriverManager.getConnection(url, "sa", ""); var sql = connection.createStatement();
                    var rows = sql.executeQuery("SELECT count(*) FROM reservation_claims")) {
                rows.next();
                assertThat(rows.getInt(1)).isEqualTo(1);
            }
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class WorkConfiguration {
        @Bean
        Work work(ReservationRepository repository, ProductSeedRepository seeds,
                ProductRepository products, EntityManager entities) {
            return new Work(repository, seeds, products, entities);
        }
    }

    static class Work {
        private final ReservationRepository repository;
        private final ProductSeedRepository seeds;
        private final ProductRepository products;
        private final EntityManager entities;
        Work(ReservationRepository repository, ProductSeedRepository seeds,
                ProductRepository products, EntityManager entities) {
            this.repository = repository;
            this.seeds = seeds;
            this.products = products;
            this.entities = entities;
        }

        @Transactional
        public void decreaseWithManagedProduct() {
            seeds.seedIfAbsent("fresh", 2);
            var before = products.findById("fresh").orElseThrow();
            assertThat(entities.contains(before)).isTrue();
            assertThat(repository.decreaseStockIfAvailable("fresh")).isTrue();
            assertThat(entities.contains(before)).isFalse();
            var after = products.findById("fresh").orElseThrow();
            assertThat(after).isNotSameAs(before);
            assertThat(after.available()).isEqualTo(1);
            entities.flush();
        }

        @Transactional(rollbackFor = Exception.class)
        public void claim(CyclicBarrier barrier) throws Exception {
            barrier.await(5, TimeUnit.SECONDS);
            repository.claim("race");
        }
    }
}
