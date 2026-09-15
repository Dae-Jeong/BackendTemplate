package com.backendtemplate.dto

import java.time.Instant
import com.fasterxml.jackson.annotation.JsonProperty

data class GreetingResponse(
    val message: String,
    @field:JsonProperty("generated_at") val generatedAt: Instant,
)
