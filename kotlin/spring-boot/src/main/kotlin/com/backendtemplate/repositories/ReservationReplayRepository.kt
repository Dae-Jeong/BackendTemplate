package com.backendtemplate.repositories

import org.springframework.data.repository.Repository

interface ReservationReplayRepository : Repository<ReservationReplayEntity, String> {
    fun findByKey(key: String): ReservationReplayEntity?
}
