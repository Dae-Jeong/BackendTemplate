package com.backendtemplate.services

import com.backendtemplate.contracts.Reservation
import com.backendtemplate.contracts.ReservationResult
import com.backendtemplate.exceptions.ReservationFailure
import com.backendtemplate.exceptions.ReservationFailure.Reason
import com.backendtemplate.repositories.ReservationRepository
import com.backendtemplate.validation.validateProductExists
import com.backendtemplate.validation.validateReplayProduct
import java.time.Clock
import java.util.UUID
import org.springframework.context.annotation.Profile
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
@Profile("!no-db")
class ReservationService(
    private val repository: ReservationRepository,
    private val clock: Clock,
) {
    @Transactional(rollbackFor = [Exception::class])
    fun reserve(productId: String, key: String): ReservationResult {
        val replay = repository.findReplay(key)
        if (replay != null) {
            validateReplayProduct(productId, replay.productId)
            return ReservationResult(reservation = replay, replayed = true)
        }
        repository.claim(key)
        if (!repository.decreaseStockIfAvailable(productId)) {
            validateProductExists(repository.productExists(productId))
            throw ReservationFailure(Reason.SOLD_OUT)
        }
        val reservation = Reservation(
            reservationId = UUID.randomUUID().toString().replace("-", ""),
            productId = productId,
            createdAt = clock.instant(),
        )
        repository.saveReservationAndReplay(reservation, key)
        return ReservationResult(reservation = reservation, replayed = false)
    }

    @Transactional(readOnly = true, rollbackFor = [Exception::class])
    fun replay(productId: String, key: String): ReservationResult {
        val replay = repository.findReplay(key) ?: error("Committed replay is missing")
        validateReplayProduct(productId, replay.productId)
        return ReservationResult(reservation = replay, replayed = true)
    }
}
