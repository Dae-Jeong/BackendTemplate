package com.backendtemplate.repositories;

import com.backendtemplate.contracts.Reservation;
import com.backendtemplate.exceptions.IdempotencyClaimed;
import jakarta.persistence.EntityManager;
import java.util.Optional;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!no-db")
public class ReservationRepository {
    private final EntityManager entities;
    private final ProductRepository products;
    private final ReservationReplayRepository replays;

    public ReservationRepository(EntityManager entities, ProductRepository products, ReservationReplayRepository replays) {
        this.entities = entities;
        this.products = products;
        this.replays = replays;
    }

    public void claim(String key) {
        // Assigned IDs must INSERT, never merge an existing claim into a successful no-op.
        entities.persist(new ReservationClaimEntity(key));
        try {
            entities.flush();
        } catch (ConstraintViolationException failure) {
            if (isH2ClaimInsertConflict(failure)) {
                throw new IdempotencyClaimed();
            }
            throw failure;
        }
    }

    private static boolean isH2ClaimInsertConflict(ConstraintViolationException failure) {
        // The claim table has only one unique constraint: its idempotency-key primary key.
        return "23505".equals(failure.getSQLState()) && failure.getSQL() != null
                && failure.getSQL().contains("insert into reservation_claims");
    }

    public Optional<Reservation> findReplay(String key) {
        return replays.findByKey(key).map(ReservationReplayEntity::toContract);
    }

    public boolean decreaseStockIfAvailable(String productId) {
        return products.decreaseAvailableStock(productId) > 0;
    }

    public boolean productExists(String productId) {
        return products.existsById(productId);
    }

    public void saveReservationAndReplay(Reservation reservation, String key) {
        var product = entities.getReference(ProductEntity.class, reservation.productId());
        var stored = new ReservationEntity(reservation, product);
        entities.persist(stored);
        entities.persist(new ReservationReplayEntity(key, reservation, stored));
        // Flush is not completion; the Service proxy still owns commit and any rollback.
        entities.flush();
    }

}
