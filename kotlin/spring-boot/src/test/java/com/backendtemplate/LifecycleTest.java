package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import com.zaxxer.hikari.HikariDataSource;
import java.net.URI;
import java.net.http.*;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicReference;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.context.annotation.Bean;

class LifecycleTest {
    @Test
    void emptyUrlDisablesDatabaseAndKeepsReadinessHealthy() throws Exception {
        try (var app = new SpringApplicationBuilder(TemplateApplication.class)
                .run("--spring.datasource.url=", "--server.port=0");
                var client = HttpClient.newHttpClient()) {
            assertThat(app.getBeansOfType(DataSource.class)).isEmpty();
            assertThat(app.getBeansOfType(jakarta.persistence.EntityManagerFactory.class)).isEmpty();
            assertThat(app.getBeansOfType(org.springframework.transaction.PlatformTransactionManager.class)).isEmpty();
            assertThat(app.getBeansOfType(com.backendtemplate.repositories.ProductRepository.class)).isEmpty();
            assertThat(app.getBeansOfType(com.backendtemplate.repositories.ProductSeedRepository.class)).isEmpty();
            assertThat(app.getBeansOfType(com.backendtemplate.services.ProductSeedService.class)).isEmpty();
            int port = ((WebServerApplicationContext) app).getWebServer().getPort();
            for (String path : new String[]{"/health/live", "/health/ready", "/metrics", "/openapi.json"}) {
                var response = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                        .build(), HttpResponse.BodyHandlers.ofString());
                assertThat(response.statusCode()).isEqualTo(200);
            }
            var reservation = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/v1/reservations"))
                    .POST(HttpRequest.BodyPublishers.noBody()).build(), HttpResponse.BodyHandlers.ofString());
            assertThat(reservation.statusCode()).isEqualTo(404);
        }
    }

    @Test
    void schemaMismatchFailsValidationWithoutRepairingSchema() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-schema-mismatch-").resolve("db");
        org.flywaydb.core.Flyway.configure().dataSource(url, "sa", "").load().migrate();
        try (var connection = java.sql.DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.execute("ALTER TABLE products ALTER COLUMN available VARCHAR(20)");
        }
        assertThatThrownBy(() -> new SpringApplicationBuilder(TemplateApplication.class).web(WebApplicationType.NONE)
                .run("--spring.datasource.url=" + url))
                .hasRootCauseInstanceOf(org.hibernate.tool.schema.spi.SchemaManagementException.class)
                .hasStackTraceContaining("Schema validation: wrong column type");
        try (var connection = java.sql.DriverManager.getConnection(url, "sa", "");
                var columns = connection.getMetaData().getColumns(null, "PUBLIC", "PRODUCTS", "AVAILABLE")) {
            assertThat(columns.next()).isTrue();
            assertThat(columns.getInt("DATA_TYPE")).isEqualTo(java.sql.Types.VARCHAR);
        }
    }

    @Test
    void invalidConfigurationFailsStartup() throws Exception {
        assertThatThrownBy(() -> new SpringApplicationBuilder(TemplateApplication.class).web(WebApplicationType.NONE)
                .run("--spring.datasource.url=", "--app.environment=private-invalid"))
                .isInstanceOf(RuntimeException.class);
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-invalid-").resolve("db");
        assertThatThrownBy(() -> new SpringApplicationBuilder(TemplateApplication.class).web(WebApplicationType.NONE)
                .run("--spring.datasource.url=" + url, "--spring.datasource.hikari.maximum-pool-size=0"))
                .isInstanceOf(RuntimeException.class);
    }

    @Test
    void lateStartupFailureClosesAcquiredPool() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-partial-").resolve("db");
        assertThatThrownBy(() -> new SpringApplicationBuilder(TemplateApplication.class, FailingStartup.class)
                .web(WebApplicationType.NONE).run("--spring.datasource.url=" + url))
                .isInstanceOf(RuntimeException.class);
        assertThat(FailingStartup.owned.get()).isNotNull();
        assertThat(FailingStartup.owned.get().isClosed()).isTrue();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FailingStartup {
        static final AtomicReference<HikariDataSource> owned = new AtomicReference<>();

        @Bean
        ApplicationRunner failAfterDatabase(HikariDataSource source) {
            return args -> {
                owned.set(source);
                throw new IllegalStateException("private startup failure");
            };
        }
    }
}
