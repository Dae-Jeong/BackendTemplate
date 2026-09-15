package com.backendtemplate.config

import com.backendtemplate.dto.Problem
import io.swagger.v3.core.converter.ModelConverters
import io.swagger.v3.oas.models.media.Content
import io.swagger.v3.oas.models.media.MediaType
import io.swagger.v3.oas.models.media.Schema
import io.swagger.v3.oas.models.responses.ApiResponse
import org.springdoc.core.customizers.OpenApiCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@Configuration(proxyBeanMethods = false)
class OpenApiConfiguration {
    @Bean
    fun problems(): OpenApiCustomizer = OpenApiCustomizer { api ->
        ModelConverters.getInstance().readAll(Problem::class.java).forEach(api.components::addSchemas)
        api.paths.forEach { (path, item) ->
            if (path.startsWith("/v1/")) {
                item.readOperations().forEach { operation ->
                    val statuses = if (path == "/v1/reservations") {
                        listOf("404", "405", "409", "422", "500", "503")
                    } else {
                        listOf("404", "405", "422", "500")
                    }
                    statuses.forEach { status ->
                        val schema = Schema<Any>().`$ref`("#/components/schemas/Problem")
                        val content = Content().addMediaType(
                            "application/problem+json",
                            MediaType().schema(schema),
                        )
                        operation.responses.addApiResponse(
                            status,
                            ApiResponse().description("Problem Details").content(content),
                        )
                    }
                }
            }
        }
    }
}
