package com.backendtemplate.repositories

import com.backendtemplate.contracts.Reservation
import jakarta.persistence.Column
import jakarta.persistence.Convert
import jakarta.persistence.Entity
import jakarta.persistence.FetchType
import jakarta.persistence.Id
import jakarta.persistence.JoinColumn
import jakarta.persistence.ManyToOne
import jakarta.persistence.Table
import java.time.Instant

@Entity
@Table(name = "reservations")
class ReservationEntity(
    value: Reservation,
    product: ProductEntity,
) {
    @field:Id
    @field:Column(length = 32)
    private var id: String = value.reservationId

    @field:ManyToOne(fetch = FetchType.LAZY, optional = false)
    @field:JoinColumn(name = "product_id", nullable = false)
    private var product: ProductEntity = product

    @field:Convert(converter = UtcTimestampConverter::class)
    @field:Column(name = "created_at", length = 40, nullable = false)
    private var createdAt: Instant = value.createdAt
}
