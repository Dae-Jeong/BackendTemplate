package com.backendtemplate.controllers

import com.backendtemplate.dto.HealthResponse
import java.sql.SQLException
import javax.sql.DataSource
import org.springframework.boot.availability.ApplicationAvailability
import org.springframework.boot.availability.ReadinessState
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RestController

@RestController
class HealthController(
    private val availability: ApplicationAvailability,
    private val dataSource: DataSource?,
) {
    @GetMapping("/health/live")
    fun live(): HealthResponse = HealthResponse("alive")

    @GetMapping("/health/ready")
    fun ready(): ResponseEntity<HealthResponse> {
        var ready = availability.readinessState == ReadinessState.ACCEPTING_TRAFFIC
        val source = dataSource
        if (ready && source != null) {
            ready = try {
                source.connection.use { it.isValid(1) }
            } catch (_: SQLException) {
                false
            }
        }
        val status = if (ready) "ready" else "not_ready"
        return ResponseEntity.status(if (ready) 200 else 503).body(HealthResponse(status))
    }
}
