package com.backendtemplate.repositories

import org.springframework.data.jpa.repository.Modifying
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.Repository
import org.springframework.data.repository.query.Param

interface ProductRepository : Repository<ProductEntity, String> {
    fun findById(id: String): ProductEntity?

    fun existsById(id: String): Boolean

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update ProductEntity p set p.available = p.available - 1 where p.id = :id and p.available > 0")
    fun decreaseAvailableStock(@Param("id") id: String): Int
}
