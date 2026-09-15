package com.backendtemplate.services

import com.backendtemplate.repositories.ProductSeedRepository
import org.springframework.context.annotation.Profile
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
@Profile("!no-db")
class ProductSeedService(private val repository: ProductSeedRepository) {
    @Transactional(rollbackFor = [Exception::class])
    fun seed(productId: String, stock: Int): Int {
        require(stock >= 0) { "Stock must be nonnegative" }
        return repository.seedIfAbsent(productId, stock)
    }
}
