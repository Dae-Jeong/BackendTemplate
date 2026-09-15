package com.backendtemplate.exceptions

class ReservationFailure(val reason: Reason) : RuntimeException() {
    enum class Reason {
        PRODUCT_NOT_FOUND,
        SOLD_OUT,
        IDEMPOTENCY_CONFLICT,
    }
}
