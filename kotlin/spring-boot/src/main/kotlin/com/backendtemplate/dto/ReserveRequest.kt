package com.backendtemplate.dto

import com.backendtemplate.http.ReserveRequestDeserializer
import io.swagger.v3.oas.annotations.media.Schema
import com.fasterxml.jackson.annotation.JsonProperty
import tools.jackson.databind.annotation.JsonDeserialize

@JsonDeserialize(using = ReserveRequestDeserializer::class)
@Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
data class ReserveRequest(
    @field:Schema(
        requiredMode = Schema.RequiredMode.REQUIRED,
        minLength = 1,
        maxLength = 64,
        pattern = "^[A-Za-z0-9._:-]+$",
    )
    @field:JsonProperty("product_id") val productId: String,
)
