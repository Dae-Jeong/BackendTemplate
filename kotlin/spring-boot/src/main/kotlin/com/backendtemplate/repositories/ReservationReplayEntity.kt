package com.backendtemplate.repositories

import com.backendtemplate.contracts.Reservation
import jakarta.persistence.Column
import jakarta.persistence.Convert
import jakarta.persistence.Entity
import jakarta.persistence.FetchType
import jakarta.persistence.Id
import jakarta.persistence.JoinColumn
import jakarta.persistence.OneToOne
import jakarta.persistence.Table
import java.time.Instant

@Entity
@Table(name = "idempotency_keys")
class ReservationReplayEntity(
    key: String,
    value: Reservation,
    reservation: ReservationEntity,
) {
    @field:Id
    @field:Column(name = "idempotency_key", length = 128)
    private var key: String = key

    @field:Column(name = "product_id", length = 64, nullable = false)
    private var productId: String = value.productId

    @field:OneToOne(fetch = FetchType.LAZY, optional = false)
    @field:JoinColumn(name = "reservation_id", nullable = false, unique = true)
    private var reservation: ReservationEntity = reservation

    @field:Column(name = "reservation_id", length = 32, insertable = false, updatable = false)
    private var reservationId: String = value.reservationId

    @field:Convert(converter = UtcTimestampConverter::class)
    @field:Column(name = "created_at", length = 40, nullable = false)
    private var createdAt: Instant = value.createdAt

    fun toContract(): Reservation = Reservation(
        reservationId = reservationId,
        productId = productId,
        createdAt = createdAt,
    )
}
