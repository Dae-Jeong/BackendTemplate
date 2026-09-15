package com.backendtemplate.config

import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.validation.annotation.Validated

@Validated
@ConfigurationProperties("spring.datasource.hikari")
data class PoolProperties(
    @field:Min(1) @field:Max(32) val maximumPoolSize: Int,
    @field:Min(250) @field:Max(30000) val connectionTimeout: Long,
)
