package com.backendtemplate.config

import jakarta.validation.constraints.Pattern
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.validation.annotation.Validated

@Validated
@ConfigurationProperties("app")
data class AppProperties(
    @field:Pattern(regexp = "local|test|staging|production") val environment: String,
)
