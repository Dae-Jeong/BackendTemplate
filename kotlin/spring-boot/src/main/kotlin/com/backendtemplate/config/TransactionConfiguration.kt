package com.backendtemplate.config

import com.backendtemplate.observation.TransactionMetrics
import jakarta.persistence.EntityManagerFactory
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.context.annotation.Profile
import org.springframework.orm.jpa.JpaTransactionManager

@Configuration(proxyBeanMethods = false)
@Profile("!no-db")
@EnableConfigurationProperties(PoolProperties::class)
class TransactionConfiguration {
    @Bean
    fun transactionManager(
        entityManagerFactory: EntityManagerFactory,
        metrics: TransactionMetrics,
    ): JpaTransactionManager = JpaTransactionManager(entityManagerFactory).apply {
        isRollbackOnCommitFailure = true
        addListener(metrics)
    }
}
