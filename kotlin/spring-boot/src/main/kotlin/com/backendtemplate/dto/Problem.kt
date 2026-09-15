package com.backendtemplate.dto

import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.annotation.JsonProperty

@JsonInclude(JsonInclude.Include.NON_NULL)
data class Problem(
    val type: String,
    val title: String,
    val status: Int,
    val code: String,
    @field:JsonProperty("request_id") val requestId: String,
    val errors: List<FieldError>?,
)
