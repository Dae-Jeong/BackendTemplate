package com.backendtemplate.services

import com.backendtemplate.contracts.ReservationResult
import com.backendtemplate.exceptions.IdempotencyClaimed
import org.springframework.context.annotation.Profile
import org.springframework.stereotype.Service

@Service
@Profile("!no-db")
class ReservationAttempts(private val transactions: ReservationService) {
    fun reserve(productId: String, key: String): ReservationResult = try {
        transactions.reserve(productId, key)
    } catch (_: IdempotencyClaimed) {
        transactions.replay(productId, key)
    }
}
