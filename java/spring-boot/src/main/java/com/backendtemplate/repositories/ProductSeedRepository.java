package com.backendtemplate.repositories;

import jakarta.persistence.EntityManager;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!no-db")
public class ProductSeedRepository {
    private final EntityManager entities;
    private final ProductRepository products;

    public ProductSeedRepository(EntityManager entities, ProductRepository products) {
        this.entities = entities;
        this.products = products;
    }

    public int seedIfAbsent(String productId, int stock) {
        return products.findById(productId).map(ProductEntity::available).orElseGet(() -> {
            entities.persist(new ProductEntity(productId, stock));
            return stock;
        });
    }
}
