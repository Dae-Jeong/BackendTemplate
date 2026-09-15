package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import com.backendtemplate.services.ProductSeedService;
import com.backendtemplate.services.ReservationService;
import com.zaxxer.hikari.HikariDataSource;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.sql.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class HttpDatabaseTest {
    private static ConfigurableApplicationContext app;
    private static String url;
    private static String base;
    private static HttpClient client;
    private static final JsonMapper JSON = JsonMapper.builder().build();

    @BeforeAll
    static void start() throws Exception {
        url = "jdbc:h2:file:" + Files.createTempDirectory("spring-http-").resolve("db")
                + ";DB_CLOSE_ON_EXIT=FALSE;LOCK_TIMEOUT=200;WRITE_DELAY=0";
        app = new SpringApplicationBuilder(TemplateApplication.class).run(
                "--server.port=0", "--spring.datasource.url=" + url,
                "--spring.datasource.hikari.maximum-pool-size=4",
                "--spring.datasource.hikari.connection-timeout=300", "--app.environment=test");
        base = "http://127.0.0.1:" + ((WebServerApplicationContext) app).getWebServer().getPort();
        client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    }

    @AfterAll
    static void stop() {
        var pool = app.getBean(HikariDataSource.class);
        app.close();
        assertThat(pool.isClosed()).isTrue();
        client.close();
    }

    @BeforeEach
    void seed() throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.executeUpdate("DELETE FROM idempotency_keys");
            sql.executeUpdate("DELETE FROM reservation_claims");
            sql.executeUpdate("DELETE FROM reservations");
            sql.executeUpdate("DELETE FROM products");
            sql.executeUpdate("INSERT INTO products VALUES ('demo', 1), ('other', 1)");
        }
    }

    private static HttpResponse<String> request(String method, String path, String body, String key) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(10));
        builder.header("X-Request-ID", "private-client-id");
        if (key != null) builder.header("Idempotency-Key", key);
        if (body != null) builder.header("Content-Type", "application/json");
        return client.send(builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }

    private static HttpResponse<String> reserve(String key, String product) throws Exception {
        return request("POST", "/v1/reservations", "{\"product_id\":\"" + product + "\"}", key);
    }

    private static JsonNode json(HttpResponse<String> response) {
        return JSON.readTree(response.body());
    }

    private static void problem(HttpResponse<String> response, int status, String code) {
        assertThat(response.statusCode()).isEqualTo(status);
        assertThat(response.headers().firstValue("Content-Type")).contains("application/problem+json");
        assertThat(json(response).get("code").asString()).isEqualTo(code);
        assertThat(json(response).get("request_id").asString())
                .isEqualTo(response.headers().firstValue("X-Request-ID").orElseThrow()).hasSize(32);
        assertThat(response.body()).doesNotContain("private", "instance", "detail");
    }

    private static List<Integer> state() throws SQLException {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            List<Integer> state = new ArrayList<>();
            for (String query : List.of("SELECT available FROM products WHERE id='demo'",
                    "SELECT count(*) FROM reservations", "SELECT count(*) FROM idempotency_keys")) {
                try (var result = sql.executeQuery(query)) {
                    result.next();
                    state.add(result.getInt(1));
                }
            }
            return state;
        }
    }

    @Test
    void httpContractAndSpecialEndpoints() throws Exception {
        var greeting = request("GET", "/v1/greetings?name=%20Marin%20", null, null);
        assertThat(greeting.statusCode()).isEqualTo(200);
        assertThat(json(greeting).get("data").get("message").asString()).isEqualTo("Hello, Marin!");
        assertThat(json(greeting).get("data").get("generated_at").asString()).endsWith("Z");
        problem(request("GET", "/v1/greetings", null, null), 422, "INVALID_INPUT");
        problem(request("GET", "/v1/greetings?name=%20", null, null), 422, "INVALID_INPUT");
        problem(request("GET", "/private-path?secret=private", null, null), 404, "NOT_FOUND");
        var method = request("POST", "/v1/greetings?name=Marin", null, null);
        problem(method, 405, "METHOD_NOT_ALLOWED");
        assertThat(method.headers().firstValue("Allow").orElseThrow()).contains("GET");
        assertThat(json(request("GET", "/health/live", null, null)).get("status").asString()).isEqualTo("alive");
        assertThat(json(request("GET", "/health/ready", null, null)).get("status").asString()).isEqualTo("ready");
        assertThat(request("GET", "/metrics", null, null).body()).contains("jvm_memory", "http_server_requests");
        assertThat(request("GET", "/h2-console", null, null).statusCode()).isEqualTo(404);
        var schema = json(request("GET", "/openapi.json", null, null));
        assertThat(schema.get("paths").get("/v1/reservations").get("post").get("responses")
                .get("422").get("content").has("application/problem+json")).isTrue();
    }

    @Test
    void rejectsMalformedStrictAndMissingInputs() throws Exception {
        for (String body : List.of("{}", "{", "null", "{\"product_id\":null}", "{\"product_id\":3}",
                "{\"product_id\":\"\"}", "{\"product_id\":\"demo\",\"private\":1}")) {
            problem(request("POST", "/v1/reservations", body, "valid"), 422, "INVALID_INPUT");
        }
        problem(reserve(null, "demo"), 422, "INVALID_INPUT");
        var nullProduct = json(request("POST", "/v1/reservations", "{\"product_id\":null}", "valid"));
        assertThat(nullProduct.get("errors").get(0).get("code").asString()).isEqualTo("INVALID");
        var missingProduct = json(request("POST", "/v1/reservations", "{}", "valid"));
        assertThat(missingProduct.get("errors").get(0).get("code").asString()).isEqualTo("REQUIRED");
        problem(reserve("invalid key", "demo"), 422, "INVALID_INPUT");
        problem(reserve("valid", "missing"), 404, "PRODUCT_NOT_FOUND");
        assertThat(state()).containsExactly(1, 0, 0);
    }

    @Test
    void inputErrorsPreservePublicLocationsAndCodes() throws Exception {
        var cases = Map.of(
                "{}", "[{\"location\":[\"body\",\"product_id\"],\"code\":\"REQUIRED\"}]",
                "{\"product_id\":null}", "[{\"location\":[\"body\",\"product_id\"],\"code\":\"INVALID\"}]",
                "{\"product_id\":3}", "[{\"location\":[\"body\",\"product_id\"],\"code\":\"INVALID\"}]",
                "{\"product_id\":true}", "[{\"location\":[\"body\",\"product_id\"],\"code\":\"INVALID\"}]",
                "{\"product_id\":[]}", "[{\"location\":[\"body\",\"product_id\"],\"code\":\"INVALID\"}]",
                "{\"product_id\":{\"private\":1}}", "[{\"location\":[\"body\",\"product_id\"],\"code\":\"INVALID\"}]",
                "{\"product_id\":\"demo\",\"private\":1}", "[{\"location\":[],\"code\":\"INVALID\"}]",
                "{", "[{\"location\":[],\"code\":\"INVALID\"}]");
        for (var entry : cases.entrySet()) {
            var response = request("POST", "/v1/reservations", entry.getKey(), "valid");
            problem(response, 422, "INVALID_INPUT");
            assertThat(json(response).get("type").asString()).isEqualTo("about:blank");
            assertThat(json(response).get("title").asString()).isEqualTo("Unprocessable Entity");
            assertThat(json(response).get("status").asInt()).isEqualTo(422);
            assertThat(json(response).get("errors")).isEqualTo(JSON.readTree(entry.getValue()));
        }
        assertThat(state()).containsExactly(1, 0, 0);
    }

    @Test
    void replayConflictAndSoldOut() throws Exception {
        var first = reserve("same", "demo");
        assertThat(first.statusCode()).isEqualTo(201);
        assertThat(first.headers().firstValue("Idempotency-Replayed")).contains("false");
        var replay = reserve("same", "demo");
        assertThat(replay.statusCode()).isEqualTo(201);
        assertThat(replay.body()).isEqualTo(first.body());
        assertThat(replay.headers().firstValue("Idempotency-Replayed")).contains("true");
        problem(reserve("same", "other"), 409, "IDEMPOTENCY_CONFLICT");
        problem(reserve("different", "demo"), 409, "SOLD_OUT");
        assertThat(state()).containsExactly(0, 1, 1);
    }

    @Test
    void parallelDifferentKeysKeepStockNonnegative() throws Exception {
        var responses = race(false);
        assertThat(responses.stream().filter(r -> r.statusCode() == 201).count()).isEqualTo(1);
        assertThat(responses.stream().filter(r -> r.statusCode() == 409).count()).isEqualTo(7);
        assertThat(state()).containsExactly(0, 1, 1);
    }

    @Test
    void parallelSameKeyHasOneEffect() throws Exception {
        var responses = race(true);
        assertThat(responses).allMatch(r -> r.statusCode() == 201);
        assertThat(responses.stream().map(HttpResponse::body).distinct().count()).isEqualTo(1);
        assertThat(state()).containsExactly(0, 1, 1);
    }

    private static List<HttpResponse<String>> race(boolean sameKey) throws Exception {
        var barrier = new CyclicBarrier(8);
        try (var executor = Executors.newFixedThreadPool(8)) {
            List<Future<HttpResponse<String>>> pending = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                String key = sameKey ? "same" : "key-" + i;
                pending.add(executor.submit(() -> {
                    barrier.await(5, TimeUnit.SECONDS);
                    return reserve(key, "demo");
                }));
            }
            List<HttpResponse<String>> result = new ArrayList<>();
            for (var future : pending) result.add(future.get(15, TimeUnit.SECONDS));
            return result;
        }
    }

    @Test
    void databaseLockTimeoutRollsBackAndRetryWorks() throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            connection.setAutoCommit(false);
            sql.executeQuery("SELECT id FROM products WHERE id='demo' FOR UPDATE").close();
            var response = reserve("locked", "demo");
            problem(response, 503, "DATABASE_BUSY");
            assertThat(response.headers().firstValue("Retry-After")).contains("1");
            assertThat(state()).containsExactly(1, 0, 0);
            connection.rollback();
        }
        assertThat(reserve("locked", "demo").statusCode()).isEqualTo(201);
    }

    @Test
    void poolTimeoutReturnsRetryableFailureAndRecovers() throws Exception {
        var pool = app.getBean(HikariDataSource.class);
        List<Connection> held = new ArrayList<>();
        try {
            for (int i = 0; i < 4; i++) held.add(pool.getConnection());
            problem(reserve("pool", "demo"), 503, "DATABASE_POOL_TIMEOUT");
            assertThat(state()).containsExactly(1, 0, 0);
        } finally {
            for (var connection : held) connection.close();
        }
        assertThat(reserve("pool", "demo").statusCode()).isEqualTo(201);
    }

    @Test
    void lockedProductDoesNotBlockIndependentProductAndKey() throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            connection.setAutoCommit(false);
            sql.executeQuery("SELECT id FROM products WHERE id='demo' FOR UPDATE").close();
            assertThat(reserve("independent", "other").statusCode()).isEqualTo(201);
            problem(reserve("blocked", "demo"), 503, "DATABASE_BUSY");
            connection.rollback();
        }
        assertThat(reserve("blocked", "demo").statusCode()).isEqualTo(201);
    }

    @Test
    void lostSocketResponseReplaysWithoutAnotherEffect() throws Exception {
        var address = URI.create(base);
        try (var socket = new java.net.Socket("127.0.0.1", address.getPort())) {
            String body = "{\"product_id\":\"demo\"}";
            String wire = "POST /v1/reservations HTTP/1.1\r\nHost: localhost\r\n"
                    + "Content-Type: application/json\r\nIdempotency-Key: lost-socket\r\n"
                    + "Content-Length: " + body.length() + "\r\nConnection: close\r\n\r\n" + body;
            socket.getOutputStream().write(wire.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            socket.getOutputStream().flush();
            socket.shutdownOutput();
            // Deliberately discard every response byte while allowing the request to finish.
            socket.getInputStream().transferTo(java.io.OutputStream.nullOutputStream());
        }
        var retry = reserve("lost-socket", "demo");
        assertThat(retry.statusCode()).isEqualTo(201);
        assertThat(retry.headers().firstValue("Idempotency-Replayed")).contains("true");
        assertThat(state()).containsExactly(0, 1, 1);
    }

    @Test
    void seedPreservesStockRejectsNegativeAndServicesAreProxied() {
        var reservations = app.getBean(ReservationService.class);
        var seed = app.getBean(ProductSeedService.class);
        assertThat(org.springframework.aop.support.AopUtils.isAopProxy(reservations)).isTrue();
        assertThat(org.springframework.aop.support.AopUtils.isAopProxy(seed)).isTrue();
        assertThat(seed.seed("demo", 99)).isEqualTo(1);
        assertThat(seed.seed("seeded", 2)).isEqualTo(2);
        assertThat(seed.seed("seeded", 99)).isEqualTo(2);
        assertThatIllegalArgumentException().isThrownBy(() -> seed.seed("invalid", -1));
    }
}
