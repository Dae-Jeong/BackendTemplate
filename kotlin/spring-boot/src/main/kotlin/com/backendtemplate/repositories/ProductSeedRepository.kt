package com.backendtemplate.repositories

import jakarta.persistence.EntityManager
import org.springframework.context.annotation.Profile
import org.springframework.stereotype.Repository

@Repository
@Profile("!no-db")
class ProductSeedRepository(
    private val entities: EntityManager,
    private val products: ProductRepository,
) {
    fun seedIfAbsent(productId: String, stock: Int): Int {
        val existing = products.findById(productId)
        if (existing != null) return existing.availableStock()
        entities.persist(ProductEntity(productId, stock))
        return stock
    }
}
