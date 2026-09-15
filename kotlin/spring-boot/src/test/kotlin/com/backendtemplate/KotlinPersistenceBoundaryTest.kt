package com.backendtemplate

import com.backendtemplate.repositories.ProductEntity
import com.backendtemplate.repositories.ProductRepository
import com.backendtemplate.repositories.ProductSeedRepository
import com.backendtemplate.repositories.ReservationRepository
import jakarta.persistence.EntityManager
import java.io.IOException
import java.lang.reflect.Modifier
import java.nio.file.Files
import java.sql.DriverManager
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.hibernate.Hibernate
import org.springframework.aop.support.AopUtils
import org.springframework.boot.WebApplicationType
import org.springframework.boot.builder.SpringApplicationBuilder
import org.springframework.boot.test.context.TestConfiguration
import org.springframework.context.ConfigurableApplicationContext
import org.springframework.context.annotation.Bean
import org.springframework.transaction.annotation.Transactional

class KotlinPersistenceBoundaryTest {
    private lateinit var app: ConfigurableApplicationContext
    private lateinit var url: String

    @AfterTest
    fun stop() {
        if (::app.isInitialized) app.close()
    }

    @Test
    fun compilerPluginsSupportActualHibernateLoadAndNullableMiss() {
        start()
        val probe = app.getBean(KotlinPersistenceProbe::class.java)
        assertTrue(AopUtils.isAopProxy(probe))

        val snapshot = probe.inspect()
        assertTrue(snapshot.nullableMiss)
        assertTrue(snapshot.wasLazyReference)
        assertEquals(2, snapshot.available)
        assertFalse(Modifier.isFinal(ProductEntity::class.java.modifiers))
        assertTrue(ProductEntity::class.java.declaredConstructors.any { it.parameterCount == 0 })
    }

    @Test
    fun kotlinTransactionalProxyRollsBackBeforeIndependentRead() {
        start()
        val probe = app.getBean(KotlinPersistenceProbe::class.java)
        probe.inspect()
        assertFailsWith<IOException> { probe.failAfterDecrease() }
        DriverManager.getConnection(url, "sa", "").use { connection ->
            connection.createStatement().use { sql ->
                sql.executeQuery("SELECT available FROM products WHERE id='kotlin'").use { rows ->
                    assertTrue(rows.next())
                    assertEquals(2, rows.getInt(1))
                }
            }
        }
    }

    private fun start() {
        url = "jdbc:h2:file:${Files.createTempDirectory("kotlin-boundary-").resolve("db")};WRITE_DELAY=0"
        app = SpringApplicationBuilder(TemplateApplication::class.java, KotlinBoundaryConfiguration::class.java)
            .web(WebApplicationType.NONE)
            .run("--spring.datasource.url=$url", "--app.environment=test")
    }
}

data class PersistenceSnapshot(
    val nullableMiss: Boolean,
    val wasLazyReference: Boolean,
    val available: Int,
)

@TestConfiguration(proxyBeanMethods = false)
class KotlinBoundaryConfiguration {
    @Bean
    fun kotlinPersistenceProbe(
        products: ProductRepository,
        seeds: ProductSeedRepository,
        reservations: ReservationRepository,
        entities: EntityManager,
    ): KotlinPersistenceProbe = KotlinPersistenceProbe(products, seeds, reservations, entities)
}

@Transactional(rollbackFor = [Exception::class])
class KotlinPersistenceProbe(
    private val products: ProductRepository,
    private val seeds: ProductSeedRepository,
    private val reservations: ReservationRepository,
    private val entities: EntityManager,
) {
    fun inspect(): PersistenceSnapshot {
        seeds.seedIfAbsent("kotlin", 2)
        entities.flush()
        entities.clear()
        val missing = products.findById("absent")
        val reference = entities.getReference(ProductEntity::class.java, "kotlin")
        val wasLazy = !Hibernate.isInitialized(reference)
        val available = reference.availableStock()
        return PersistenceSnapshot(
            nullableMiss = missing == null,
            wasLazyReference = wasLazy,
            available = available,
        )
    }

    fun failAfterDecrease() {
        assertNull(products.findById("absent"))
        if (products.findById("kotlin") == null) seeds.seedIfAbsent("kotlin", 2)
        reservations.decreaseStockIfAvailable("kotlin")
        throw IOException("private Kotlin checked failure")
    }
}
