package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@ExtendWith(OutputCaptureExtension.class)
class SpecialHttpTest {
    @Test
    void specialResponsesAndSanitizedLogs(CapturedOutput output) throws Exception {
        try (var app = new SpringApplicationBuilder(TemplateApplication.class, Routes.class)
                .run("--spring.datasource.url=", "--server.port=0"); var client = HttpClient.newHttpClient()) {
            int port = ((WebServerApplicationContext) app).getWebServer().getPort();
            String base = "http://127.0.0.1:" + port;
            for (String path : new String[]{"/special/empty", "/special/file", "/special/stream",
                    "/special/failure", "/special/limited", "/special/dispatch"}) {
                var response = client.send(HttpRequest.newBuilder(URI.create(base + path))
                        .timeout(Duration.ofSeconds(5)).header("X-Request-ID", "private-request")
                        .build(), HttpResponse.BodyHandlers.ofString());
                switch (path) {
                    case "/special/empty" -> {
                        assertThat(response.statusCode()).isEqualTo(204);
                        assertThat(response.body()).isEmpty();
                    }
                    case "/special/file" -> assertThat(response.body()).isEqualTo("file-content");
                    case "/special/stream" -> assertThat(response.body()).isEqualTo("first");
                    case "/special/failure" -> {
                        assertThat(response.statusCode()).isEqualTo(500);
                        assertThat(response.body()).contains("INTERNAL_ERROR").doesNotContain("private");
                    }
                    case "/special/limited" -> {
                        assertThat(response.statusCode()).isEqualTo(429);
                        assertThat(response.headers().firstValue("Retry-After")).contains("3");
                        assertThat(response.body()).doesNotContain("private");
                    }
                    case "/special/dispatch" -> assertThat(response.statusCode()).isEqualTo(503);
                    default -> throw new AssertionError();
                }
            }
        }
        assertThat(output.getAll()).doesNotContain("private-request", "private-exception", "private-stream");
        assertThat(output.getAll().lines().filter(line -> line.contains("\"message\":\"http.completed\"")).count())
                .isEqualTo(6);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class Routes {
        @Bean
        Endpoints specialEndpoints() {
            return new Endpoints();
        }
    }

    @RestController
    @org.springframework.boot.test.context.TestComponent
    static class Endpoints {
        @GetMapping("/special/empty")
        ResponseEntity<Void> empty() {
            return ResponseEntity.noContent().build();
        }

        @GetMapping("/special/file")
        ResponseEntity<byte[]> file() {
            return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .body("file-content".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }

        @GetMapping("/special/stream")
        StreamingResponseBody stream(HttpServletResponse response) {
            return stream -> {
                stream.write("first".getBytes(java.nio.charset.StandardCharsets.UTF_8));
                response.flushBuffer();
                throw new IOException("private-stream");
            };
        }

        @GetMapping("/special/failure")
        String failure() {
            throw new IllegalStateException("private-exception");
        }

        @GetMapping("/special/limited")
        String limited() {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "private-exception") {
                @Override
                public HttpHeaders getHeaders() {
                    var headers = new HttpHeaders();
                    headers.set("Retry-After", "3");
                    return headers;
                }
            };
        }

        @GetMapping("/special/dispatch")
        void dispatch(HttpServletResponse response) throws IOException {
            response.sendError(503);
        }
    }
}
