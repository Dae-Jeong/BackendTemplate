package com.backendtemplate.config;

import com.backendtemplate.services.ProductSeedService;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.validation.annotation.Validated;

@Configuration(proxyBeanMethods = false)
@Profile("seed")
@EnableConfigurationProperties(SeedConfiguration.SeedProperties.class)
public class SeedConfiguration {
    @Validated
    @ConfigurationProperties("app.seed")
    public record SeedProperties(@Pattern(regexp = "[A-Za-z0-9._:-]{1,64}") String productId,
            @Min(0) int stock) {}

    @Bean
    ApplicationRunner seedProduct(ProductSeedService service, SeedProperties properties) {
        return args -> {
            int available = service.seed(properties.productId(), properties.stock());
            System.out.println("{\"product_id\":\"" + properties.productId() + "\",\"available\":" + available + "}");
        };
    }
}
