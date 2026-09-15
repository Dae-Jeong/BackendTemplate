package com.backendtemplate.dto

import java.time.Instant
import com.fasterxml.jackson.annotation.JsonProperty

data class ReservationResponse(
    @field:JsonProperty("reservation_id") val reservationId: String,
    @field:JsonProperty("product_id") val productId: String,
    @field:JsonProperty("created_at") val createdAt: Instant,
)
