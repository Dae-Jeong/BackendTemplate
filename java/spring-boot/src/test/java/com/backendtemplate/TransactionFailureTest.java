package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import com.backendtemplate.repositories.ReservationRepository;
import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.lang.reflect.*;
import java.net.URI;
import java.net.http.*;
import java.nio.file.Files;
import java.sql.*;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.*;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.datasource.DelegatingDataSource;
import org.springframework.transaction.annotation.Transactional;

class TransactionFailureTest {
    private ConfigurableApplicationContext app;
    private String url;
    private String base;
    private FaultDataSource source;

    @BeforeEach
    void start() throws Exception {
        url = "jdbc:h2:file:" + Files.createTempDirectory("spring-fault-").resolve("db") + ";WRITE_DELAY=0";
        app = new SpringApplicationBuilder(TemplateApplication.class, FaultConfiguration.class)
                .run("--server.port=0", "--spring.datasource.url=" + url, "--app.environment=test");
        source = app.getBean(FaultDataSource.class);
        base = "http://127.0.0.1:" + ((WebServerApplicationContext) app).getWebServer().getPort();
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.executeUpdate("INSERT INTO products VALUES ('demo', 1)");
        }
    }

    @AfterEach
    void stop() {
        source.release.countDown();
        app.close();
        assertThat(source.pool.isClosed()).isTrue();
    }

    private HttpResponse<String> reserve() throws Exception {
        try (var client = HttpClient.newHttpClient()) {
            return client.send(HttpRequest.newBuilder(URI.create(base + "/v1/reservations"))
                    .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
                    .header("Idempotency-Key", "fault")
                    .POST(HttpRequest.BodyPublishers.ofString("{\"product_id\":\"demo\"}")).build(),
                    HttpResponse.BodyHandlers.ofString());
        }
    }

    private void unchanged() throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            for (var pair : List.of(new String[]{"SELECT available FROM products WHERE id='demo'", "1"},
                    new String[]{"SELECT count(*) FROM reservations", "0"},
                    new String[]{"SELECT count(*) FROM idempotency_keys", "0"})) {
                try (var result = sql.executeQuery(pair[0])) {
                    result.next();
                    assertThat(result.getString(1)).isEqualTo(pair[1]);
                }
            }
            try (var result = sql.executeQuery("SELECT count(*) FROM reservation_claims")) {
                result.next();
                assertThat(result.getInt(1)).isZero();
            }
        }
    }

    private double count(String outcome) {
        var counter = app.getBean(MeterRegistry.class).find("db.transactions")
                .tags("role", "primary", "outcome", outcome).counter();
        return counter == null ? 0 : counter.count();
    }

    @Test
    void commitFailureCannotReturnSuccessOrCountCommitAndSameKeyRetries() throws Exception {
        source.failCommit.set(true);
        double committed = count("committed");
        try (var executor = Executors.newSingleThreadExecutor()) {
            var response = executor.submit(this::reserve);
            assertThat(source.entered.await(5, TimeUnit.SECONDS)).isTrue();
            assertThat(response.isDone()).isFalse();
            assertThat(count("committed")).isEqualTo(committed);
            unchanged();
            source.release.countDown();
            var failure = response.get(10, TimeUnit.SECONDS);
            assertThat(failure.statusCode()).isEqualTo(500);
            assertThat(failure.body()).contains("INTERNAL_ERROR").doesNotContain("private");
        }
        unchanged();
        assertThat(count("failed")).isEqualTo(1);
        assertThat(count("committed")).isEqualTo(committed);
        assertThat(reserve().statusCode()).isEqualTo(201);
        assertThat(count("committed")).isEqualTo(committed + 1);
    }

    @Test
    void rollbackBoundaryFailureCountsFailedAndDoesNotBecomeSuccess() throws Exception {
        source.failRollback.set(true);
        assertThatThrownBy(() -> app.getBean(CheckedWork.class).fail(false))
                .isInstanceOf(org.springframework.orm.jpa.JpaSystemException.class);
        unchanged();
        assertThat(count("failed")).isEqualTo(1);
        assertThat(count("rolled_back")).isZero();
        assertThat(count("committed")).isZero();
    }

    @Test
    void checkedAndUncheckedFailuresRollbackThroughPublicProxy() throws Exception {
        var work = app.getBean(CheckedWork.class);
        assertThatThrownBy(() -> work.fail(true)).isInstanceOf(IOException.class);
        unchanged();
        assertThatThrownBy(() -> work.fail(false)).isInstanceOf(IllegalStateException.class);
        unchanged();
        assertThat(count("rolled_back")).isEqualTo(2);
    }

    @Test
    void transactionBeginFailureIsNotReportedAsPoolTimeout() throws Exception {
        source.failBegin.set(true);
        var failure = reserve();
        assertThat(failure.statusCode()).isEqualTo(500);
        assertThat(failure.body()).contains("INTERNAL_ERROR").doesNotContain("DATABASE_POOL_TIMEOUT", "private");
        assertThat(failure.headers().firstValue("Retry-After")).isEmpty();
        unchanged();
        assertThat(reserve().statusCode()).isEqualTo(201);
    }

    @Test
    void unrelatedUniqueFlushFailureIsNotReplayedAsClaimCollision() throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.execute("ALTER TABLE reservations ADD CONSTRAINT one_product UNIQUE(product_id)");
            sql.execute("INSERT INTO reservations VALUES ('baseline', 'demo', '2026-09-08T00:00:00Z')");
        }
        var failure = reserve();
        assertThat(failure.statusCode()).isEqualTo(500);
        assertThat(failure.body()).contains("INTERNAL_ERROR");
        assertThat(count("rolled_back")).isEqualTo(1);
        assertThat(count("committed")).isZero();
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.execute("DELETE FROM reservations WHERE id='baseline'");
        }
        unchanged();
        assertThat(reserve().statusCode()).isEqualTo(201);
    }

    @Test
    void storageConstraintFailureRollsBackAllWrites() throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.execute("ALTER TABLE idempotency_keys ADD CONSTRAINT fail_save CHECK (product_id <> 'demo')");
        }
        assertThat(reserve().statusCode()).isEqualTo(500);
        unchanged();
        assertThat(count("rolled_back")).isEqualTo(1);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FaultConfiguration {
        @Bean
        FaultDataSource dataSource(Environment environment) {
            var pool = new HikariDataSource();
            pool.setJdbcUrl(environment.getRequiredProperty("spring.datasource.url"));
            pool.setUsername("sa");
            pool.setPassword("");
            pool.setMaximumPoolSize(4);
            return new FaultDataSource(pool);
        }

        @Bean
        CheckedWork checkedWork(ReservationRepository repository) {
            return new CheckedWork(repository);
        }
    }

    static class CheckedWork {
        private final ReservationRepository repository;
        CheckedWork(ReservationRepository repository) {
            this.repository = repository;
        }

        @Transactional(rollbackFor = Exception.class)
        public void fail(boolean checked) throws IOException {
            repository.decreaseStockIfAvailable("demo");
            if (checked) throw new IOException("private checked");
            throw new IllegalStateException("private unchecked");
        }
    }

    static class FaultDataSource extends DelegatingDataSource implements AutoCloseable {
        final HikariDataSource pool;
        final AtomicBoolean failCommit = new AtomicBoolean();
        final AtomicBoolean failBegin = new AtomicBoolean();
        final AtomicBoolean failRollback = new AtomicBoolean();
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        FaultDataSource(HikariDataSource pool) {
            super(pool);
            this.pool = pool;
        }

        @Override
        public Connection getConnection() throws SQLException {
            Connection connection = super.getConnection();
            return (Connection) Proxy.newProxyInstance(Connection.class.getClassLoader(),
                    new Class<?>[]{Connection.class}, (proxy, method, args) -> {
                        if (method.getName().equals("rollback") && failRollback.compareAndSet(true, false)) {
                            connection.rollback();
                            throw new SQLException("private synthetic rollback acknowledgement failure", "HY000");
                        }
                        if (method.getName().equals("setAutoCommit") && Boolean.FALSE.equals(args[0])
                                && failBegin.compareAndSet(true, false)) {
                            throw new SQLNonTransientConnectionException("private transaction begin failure", "08006");
                        }
                        if (method.getName().equals("commit") && failCommit.compareAndSet(true, false)) {
                            entered.countDown();
                            if (!release.await(10, TimeUnit.SECONDS)) throw new SQLException("fault gate timed out");
                            throw new SQLException("private synthetic JDBC commit failure", "HY000");
                        }
                        try {
                            return method.invoke(connection, args);
                        } catch (InvocationTargetException error) {
                            throw error.getCause();
                        }
                    });
        }

        @Override
        public void close() {
            pool.close();
        }
    }
}
