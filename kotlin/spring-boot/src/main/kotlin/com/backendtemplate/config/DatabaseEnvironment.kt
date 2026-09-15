package com.backendtemplate.config

import org.springframework.boot.EnvironmentPostProcessor
import org.springframework.boot.SpringApplication
import org.springframework.core.Ordered
import org.springframework.core.env.ConfigurableEnvironment
import org.springframework.core.env.MapPropertySource

class DatabaseEnvironment : EnvironmentPostProcessor, Ordered {
    override fun getOrder(): Int = Ordered.HIGHEST_PRECEDENCE + 11

    override fun postProcessEnvironment(environment: ConfigurableEnvironment, application: SpringApplication) {
        val url = environment.getProperty("spring.datasource.url", "")
        if (url.isBlank()) {
            environment.addActiveProfile("no-db")
            environment.propertySources.addFirst(
                MapPropertySource(
                    "disabledDatabase",
                    mapOf(
                        "spring.autoconfigure.exclude" to
                            "org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration," +
                            "org.springframework.boot.flyway.autoconfigure.FlywayAutoConfiguration",
                        "management.endpoint.health.group.readiness.include" to "readinessState",
                    ),
                ),
            )
        }
    }
}
