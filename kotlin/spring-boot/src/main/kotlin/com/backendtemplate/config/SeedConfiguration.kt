package com.backendtemplate.config

import com.backendtemplate.services.ProductSeedService
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.Pattern
import org.springframework.boot.ApplicationRunner
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.context.annotation.Profile
import org.springframework.validation.annotation.Validated

@Configuration(proxyBeanMethods = false)
@Profile("seed")
@EnableConfigurationProperties(SeedConfiguration.SeedProperties::class)
class SeedConfiguration {
    @Validated
    @ConfigurationProperties("app.seed")
    data class SeedProperties(
        @field:Pattern(regexp = "[A-Za-z0-9._:-]{1,64}") val productId: String,
        @field:Min(0) val stock: Int,
    )

    @Bean
    fun seedProduct(service: ProductSeedService, properties: SeedProperties) = ApplicationRunner {
        val available = service.seed(properties.productId, properties.stock)
        System.out.println("{\"product_id\":\"${properties.productId}\",\"available\":$available}")
    }
}
