package com.backendtemplate

import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.springframework.boot.builder.SpringApplicationBuilder
import org.springframework.boot.web.server.context.WebServerApplicationContext
import tools.jackson.databind.json.JsonMapper

class KotlinJsonBoundaryTest {
    private data class JsonCase(
        val body: String,
        val expectedLocation: List<String>,
        val expectedCode: String,
    )

    @Test
    fun missingNullNumberAndMalformedJsonKeepPublic422Meaning() {
        val database = Files.createTempDirectory("kotlin-json-").resolve("db")
        val url = "jdbc:h2:file:$database;WRITE_DELAY=0"
        SpringApplicationBuilder(TemplateApplication::class.java).run(
            "--server.port=0",
            "--spring.datasource.url=$url",
            "--app.environment=test",
        ).use { app ->
            val server = requireNotNull((app as WebServerApplicationContext).webServer)
            val port = server.port
            HttpClient.newHttpClient().use { client ->
                val cases = listOf(
                    JsonCase("{}", listOf("body", "product_id"), "REQUIRED"),
                    JsonCase("{\"product_id\":null}", listOf("body", "product_id"), "INVALID"),
                    JsonCase("{\"product_id\":3}", listOf("body", "product_id"), "INVALID"),
                    JsonCase("{", emptyList(), "INVALID"),
                )
                for ((body, expectedLocation, expectedCode) in cases) {
                    val response = client.send(
                        HttpRequest.newBuilder(URI.create("http://127.0.0.1:$port/v1/reservations"))
                            .header("Content-Type", "application/json")
                            .header("Idempotency-Key", "kotlin-json")
                            .POST(HttpRequest.BodyPublishers.ofString(body))
                            .build(),
                        HttpResponse.BodyHandlers.ofString(),
                    )
                    assertEquals(422, response.statusCode())
                    val error = JSON.readTree(response.body()).get("errors").get(0)
                    val location = error.get("location")
                    val actualLocation = buildList {
                        for (index in 0 until location.size()) add(location.get(index).asString())
                    }
                    assertEquals(expectedLocation, actualLocation)
                    assertEquals(expectedCode, error.get("code").asString())
                }
                val openApi = client.send(
                    HttpRequest.newBuilder(URI.create("http://127.0.0.1:$port/openapi.json")).build(),
                    HttpResponse.BodyHandlers.ofString(),
                )
                val schemas = JSON.readTree(openApi.body()).get("components").get("schemas")
                val problemProperties = schemas.get("Problem").get("properties")
                assertTrue(problemProperties.has("request_id"))
                assertFalse(problemProperties.has("requestId"))
                assertTrue(schemas.get("ReservationResponse").get("properties").has("reservation_id"))
            }
        }
    }

    private companion object {
        val JSON = JsonMapper.builder().build()
    }
}
