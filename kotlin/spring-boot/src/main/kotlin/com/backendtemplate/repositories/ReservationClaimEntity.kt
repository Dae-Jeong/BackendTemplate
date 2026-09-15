package com.backendtemplate.repositories

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "reservation_claims")
class ReservationClaimEntity(
    @field:Id
    @field:Column(name = "idempotency_key", length = 128)
    private var key: String,
)
