package com.backendtemplate.services;

import com.backendtemplate.repositories.ProductSeedRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile("!no-db")
public class ProductSeedService {
    private final ProductSeedRepository repository;

    public ProductSeedService(ProductSeedRepository repository) {
        this.repository = repository;
    }

    @Transactional(rollbackFor = Exception.class)
    public int seed(String productId, int stock) {
        if (stock < 0) {
            throw new IllegalArgumentException("Stock must be nonnegative");
        }
        return repository.seedIfAbsent(productId, stock);
    }
}
