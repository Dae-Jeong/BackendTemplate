package com.backendtemplate.repositories

import com.backendtemplate.contracts.Reservation
import com.backendtemplate.exceptions.IdempotencyClaimed
import jakarta.persistence.EntityManager
import org.hibernate.exception.ConstraintViolationException
import org.springframework.context.annotation.Profile
import org.springframework.stereotype.Repository

@Repository
@Profile("!no-db")
class ReservationRepository(
    private val entities: EntityManager,
    private val products: ProductRepository,
    private val replays: ReservationReplayRepository,
) {
    fun claim(key: String) {
        entities.persist(ReservationClaimEntity(key))
        try {
            entities.flush()
        } catch (failure: ConstraintViolationException) {
            if (isH2ClaimInsertConflict(failure)) throw IdempotencyClaimed()
            throw failure
        }
    }

    fun findReplay(key: String): Reservation? = replays.findByKey(key)?.toContract()

    fun decreaseStockIfAvailable(productId: String): Boolean = products.decreaseAvailableStock(productId) > 0

    fun productExists(productId: String): Boolean = products.existsById(productId)

    fun saveReservationAndReplay(reservation: Reservation, key: String) {
        val product = entities.getReference(ProductEntity::class.java, reservation.productId)
        val stored = ReservationEntity(reservation, product)
        entities.persist(stored)
        entities.persist(ReservationReplayEntity(key = key, value = reservation, reservation = stored))
        entities.flush()
    }
}

private fun isH2ClaimInsertConflict(failure: ConstraintViolationException): Boolean =
    failure.sqlState == "23505" && failure.sql?.contains("insert into reservation_claims") == true
