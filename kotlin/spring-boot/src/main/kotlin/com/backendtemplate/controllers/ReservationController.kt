package com.backendtemplate.controllers

import com.backendtemplate.dto.ApiResponse
import com.backendtemplate.dto.ReservationResponse
import com.backendtemplate.dto.ReserveRequest
import com.backendtemplate.http.requiredToken
import com.backendtemplate.services.ReservationAttempts
import org.springframework.context.annotation.Profile
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController

@RestController
@Profile("!no-db")
class ReservationController(private val service: ReservationAttempts) {
    @PostMapping("/v1/reservations")
    @ResponseStatus(HttpStatus.CREATED)
    fun reserve(
        @RequestBody body: ReserveRequest,
        @RequestHeader(name = "Idempotency-Key", required = false) key: String?,
    ): ResponseEntity<ApiResponse<ReservationResponse>> {
        val productId = requiredToken(body.productId, "body", "product_id", 64)
        val idempotencyKey = requiredToken(key, "header", "Idempotency-Key", 128)
        val result = service.reserve(productId, idempotencyKey)
        val reservation = result.reservation
        val response = ReservationResponse(
            reservationId = reservation.reservationId,
            productId = reservation.productId,
            createdAt = reservation.createdAt,
        )
        return ResponseEntity.status(201)
            .header("Idempotency-Replayed", result.replayed.toString())
            .body(ApiResponse(response))
    }
}
