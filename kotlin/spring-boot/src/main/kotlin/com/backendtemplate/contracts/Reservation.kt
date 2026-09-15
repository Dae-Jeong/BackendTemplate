package com.backendtemplate.contracts

import java.time.Instant

data class Reservation(val reservationId: String, val productId: String, val createdAt: Instant)
