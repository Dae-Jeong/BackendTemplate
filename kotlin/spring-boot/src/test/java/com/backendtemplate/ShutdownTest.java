package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import java.io.BufferedReader;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.sql.DriverManager;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class ShutdownTest {
    @Test
    void sigtermFinishesActiveRequestAndReleasesFileDatabase() throws Exception {
        String url = "jdbc:h2:file:" + Files.createTempDirectory("spring-shutdown-").resolve("db")
                + ";DB_CLOSE_ON_EXIT=FALSE";
        var process = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-cp", System.getProperty("test.runtimeClasspath"), ShutdownWorker.class.getName(), url)
                .redirectErrorStream(true).start();
        try (var reader = process.inputReader(); var executor = Executors.newSingleThreadExecutor();
                var client = HttpClient.newHttpClient()) {
            String started = executor.submit(() -> until(reader, "SERVER_PORT:")).get(30, TimeUnit.SECONDS);
            int port = Integer.parseInt(started.substring("SERVER_PORT:".length()));
            var response = client.sendAsync(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/slow"))
                    .build(), HttpResponse.BodyHandlers.ofString());
            executor.submit(() -> until(reader, "REQUEST_ACTIVE")).get(5, TimeUnit.SECONDS);
            process.destroy();
            assertThat(response.get(10, TimeUnit.SECONDS).body()).isEqualTo("finished");
            assertThat(process.waitFor(15, TimeUnit.SECONDS)).isTrue();
            try (var connection = DriverManager.getConnection(url, "sa", "")) {
                assertThat(connection.isValid(1)).isTrue();
            }
        } finally {
            if (process.isAlive()) process.destroyForcibly();
            process.waitFor(10, TimeUnit.SECONDS);
        }
    }

    private static String until(BufferedReader reader, String prefix) throws Exception {
        String line;
        while ((line = reader.readLine()) != null) {
            if (line.startsWith(prefix)) return line;
        }
        throw new AssertionError("Process ended before " + prefix);
    }
}
