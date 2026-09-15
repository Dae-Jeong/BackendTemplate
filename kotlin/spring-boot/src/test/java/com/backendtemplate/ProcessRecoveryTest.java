package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import java.io.*;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;
import org.flywaydb.core.Flyway;
import org.h2.tools.Server;
import org.junit.jupiter.api.*;

class ProcessRecoveryTest {
    private final List<Process> children = new ArrayList<>();
    private final ExecutorService readers = Executors.newCachedThreadPool();
    private String url;
    private Server server;

    @BeforeEach
    void database() throws Exception {
        var directory = Files.createTempDirectory("spring-process-");
        System.setProperty("h2.bindAddress", "127.0.0.1");
        server = Server.createTcpServer("-tcpPort", "0", "-tcpDaemon", "-ifNotExists",
                "-baseDir", directory.toString()).start();
        url = "jdbc:h2:tcp://127.0.0.1:" + server.getPort()
                + "/db;LOCK_TIMEOUT=2000;WRITE_DELAY=0";
        Flyway.configure().dataSource(url, "sa", "").load().migrate();
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.executeUpdate("INSERT INTO products VALUES ('demo', 1), ('other', 1)");
        }
    }

    @AfterEach
    void cleanup() throws Exception {
        for (Process process : children) {
            if (process.isAlive()) process.destroyForcibly();
            assertThat(process.waitFor(10, TimeUnit.SECONDS)).isTrue();
        }
        if (server != null) server.stop();
        readers.shutdownNow();
        System.clearProperty("h2.bindAddress");
    }

    private record Worker(Process process, BufferedReader output) {}

    private Worker start(String product, String key, String phase) throws Exception {
        var process = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-cp", System.getProperty("test.runtimeClasspath"), ProcessWorker.class.getName(),
                url, product, key, phase).redirectErrorStream(true).start();
        children.add(process);
        var worker = new Worker(process, process.inputReader());
        readUntil(worker, "WORKER_READY");
        return worker;
    }

    private String readUntil(Worker worker, String prefix) throws Exception {
        return readers.submit(() -> {
            String line;
            StringBuilder diagnostics = new StringBuilder();
            while ((line = worker.output().readLine()) != null) {
                if (line.startsWith(prefix)) return line;
                diagnostics.append(line).append('\n');
            }
            throw new AssertionError("Process ended before " + prefix + ": " + diagnostics);
        }).get(30, TimeUnit.SECONDS);
    }

    private void go(Worker worker) throws IOException {
        worker.process().getOutputStream().write('G');
        worker.process().getOutputStream().flush();
    }

    private List<Integer> state() throws Exception {
        List<Integer> values = new ArrayList<>();
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            for (String query : List.of("SELECT available FROM products WHERE id='demo'",
                    "SELECT count(*) FROM reservations", "SELECT count(*) FROM idempotency_keys")) {
                try (var rows = sql.executeQuery(query)) {
                    rows.next();
                    values.add(rows.getInt(1));
                }
            }
        }
        return values;
    }

    @Test
    void independentProcessesSameKeyReplayOneEffect() throws Exception {
        var first = start("demo", "shared", "normal");
        var second = start("demo", "shared", "normal");
        go(first);
        go(second);
        String a = readUntil(first, "RESULT:");
        String b = readUntil(second, "RESULT:");
        assertThat(a.replace("\"replayed\":false", "\"replayed\":true")).isEqualTo(
                b.replace("\"replayed\":false", "\"replayed\":true"));
        assertThat(state()).containsExactly(0, 1, 1);
        var conflict = start("other", "shared", "normal");
        go(conflict);
        assertThat(readUntil(conflict, "ERROR:")).isEqualTo("ERROR:IDEMPOTENCY_CONFLICT");
    }

    @Test
    void independentProcessesDifferentKeysCannotOversell() throws Exception {
        var first = start("demo", "a", "normal");
        var second = start("demo", "b", "normal");
        go(first);
        go(second);
        String a = readOutcome(first);
        String b = readOutcome(second);
        assertThat(List.of(a, b).stream().filter(line -> line.startsWith("RESULT:")).count()).isEqualTo(1);
        assertThat(List.of(a, b)).contains("ERROR:SOLD_OUT");
        assertThat(state()).containsExactly(0, 1, 1);
    }

    private String readOutcome(Worker worker) throws Exception {
        return readers.submit(() -> {
            String line;
            while ((line = worker.output().readLine()) != null) {
                if (line.startsWith("RESULT:") || line.startsWith("ERROR:")) return line;
            }
            throw new AssertionError("Missing outcome");
        }).get(30, TimeUnit.SECONDS);
    }

    @Test
    void deathBeforeCommitRollsBackAndAfterCommitReplays() throws Exception {
        var before = start("demo", "lost", "before");
        go(before);
        readUntil(before, "BEFORE_COMMIT");
        assertThat(state()).containsExactly(1, 0, 0);
        before.process().destroyForcibly();
        assertThat(before.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
        var after = start("demo", "lost", "after");
        go(after);
        readUntil(after, "AFTER_COMMIT");
        assertThat(state()).containsExactly(0, 1, 1);
        after.process().destroyForcibly();
        assertThat(after.process().waitFor(10, TimeUnit.SECONDS)).isTrue();
        var retry = start("demo", "lost", "normal");
        go(retry);
        assertThat(readUntil(retry, "RESULT:")).contains("\"replayed\":true");
        assertThat(state()).containsExactly(0, 1, 1);
    }

    @Test
    void embeddedFileSurvivesProcessRestart() throws Exception {
        server.stop();
        server = null;
        url = "jdbc:h2:file:" + Files.createTempDirectory("spring-embedded-").resolve("db")
                + ";DB_CLOSE_ON_EXIT=FALSE;WRITE_DELAY=0";
        Flyway.configure().dataSource(url, "sa", "").load().migrate();
        try (var connection = DriverManager.getConnection(url, "sa", "");
                var sql = connection.createStatement()) {
            sql.executeUpdate("INSERT INTO products VALUES ('demo', 1)");
        }
        var first = start("demo", "persisted", "normal");
        go(first);
        String original = readUntil(first, "RESULT:");
        assertThat(first.process().waitFor(15, TimeUnit.SECONDS)).isTrue();
        var restart = start("demo", "persisted", "normal");
        go(restart);
        assertThat(readUntil(restart, "RESULT:")).isEqualTo(
                original.replace("\"replayed\":false", "\"replayed\":true"));
        assertThat(restart.process().waitFor(15, TimeUnit.SECONDS)).isTrue();
        assertThat(state()).containsExactly(0, 1, 1);
    }
}
