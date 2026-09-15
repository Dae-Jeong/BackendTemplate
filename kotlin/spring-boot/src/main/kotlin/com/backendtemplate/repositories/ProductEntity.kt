package com.backendtemplate.repositories

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "products")
class ProductEntity(
    id: String,
    available: Int,
) {
    @field:Id
    @field:Column(length = 64)
    private var id: String = id

    @field:Column(nullable = false)
    private var available: Int = available

    fun availableStock(): Int = available
}
