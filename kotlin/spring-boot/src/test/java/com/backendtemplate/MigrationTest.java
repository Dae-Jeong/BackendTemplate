package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import java.nio.file.Files;
import java.sql.DriverManager;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;

class MigrationTest {
    @Test
    void upgradeRemovesGlobalGuardAndPreservesExistingResults() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-upgrade-").resolve("db");
        Flyway.configure().dataSource(url, "sa", "").target("1").load().migrate();
        try (var connection = DriverManager.getConnection(url, "sa", ""); var sql = connection.createStatement()) {
            sql.executeUpdate("INSERT INTO products VALUES ('demo', 2)");
            sql.executeUpdate("INSERT INTO reservations VALUES ('existing', 'demo', '2026-09-08T00:00:00.123456789Z')");
            sql.executeUpdate("INSERT INTO idempotency_keys VALUES ('existing-key', 'demo', 'existing', '2026-09-08T00:00:00.123456789Z')");
        }
        var flyway = Flyway.configure().dataSource(url, "sa", "").load();
        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(flyway.migrate().migrationsExecuted).isZero();
        try (var connection = DriverManager.getConnection(url, "sa", ""); var sql = connection.createStatement()) {
            try (var result = sql.executeQuery("SELECT available FROM products WHERE id='demo'")) {
                result.next();
                assertThat(result.getInt(1)).isEqualTo(2);
            }
            try (var result = sql.executeQuery("SELECT idempotency_key FROM reservation_claims")) {
                result.next();
                assertThat(result.getString(1)).isEqualTo("existing-key");
            }
            assertThatThrownBy(() -> sql.executeQuery("SELECT * FROM reservation_guard"))
                    .isInstanceOf(java.sql.SQLException.class);
        }
        try (var app = new org.springframework.boot.builder.SpringApplicationBuilder(TemplateApplication.class)
                .run("--spring.datasource.url=" + url, "--server.port=0");
                var client = java.net.http.HttpClient.newHttpClient()) {
            int port = ((org.springframework.boot.web.server.context.WebServerApplicationContext) app).getWebServer().getPort();
            var replay = client.send(java.net.http.HttpRequest.newBuilder(
                    java.net.URI.create("http://127.0.0.1:" + port + "/v1/reservations"))
                    .header("Content-Type", "application/json").header("Idempotency-Key", "existing-key")
                    .POST(java.net.http.HttpRequest.BodyPublishers.ofString("{\"product_id\":\"demo\"}")).build(),
                    java.net.http.HttpResponse.BodyHandlers.ofString());
            assertThat(replay.statusCode()).isEqualTo(201);
            assertThat(replay.headers().firstValue("Idempotency-Replayed")).contains("true");
            assertThat(replay.body()).isEqualTo("{\"data\":{\"reservation_id\":\"existing\",\"product_id\":\"demo\",\"created_at\":\"2026-09-08T00:00:00.123456789Z\"}}");
        }
        var bad = Files.createTempDirectory("spring-bad-migration-");
        Files.writeString(bad.resolve("V3__broken.sql"), "THIS IS INVALID SQL;");
        assertThatThrownBy(() -> Flyway.configure().dataSource(url, "sa", "")
                .locations("classpath:db/migration", "filesystem:" + bad).load().migrate())
                .isInstanceOf(org.flywaydb.core.api.FlywayException.class);
    }
}
