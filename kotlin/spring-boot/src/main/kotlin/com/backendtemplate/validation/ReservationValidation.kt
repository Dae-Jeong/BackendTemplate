package com.backendtemplate.validation

import com.backendtemplate.exceptions.ReservationFailure
import com.backendtemplate.exceptions.ReservationFailure.Reason

fun validateProductExists(productExists: Boolean) {
    if (!productExists) throw ReservationFailure(Reason.PRODUCT_NOT_FOUND)
}

fun validateReplayProduct(requestedProductId: String, replayProductId: String) {
    if (requestedProductId != replayProductId) throw ReservationFailure(Reason.IDEMPOTENCY_CONFLICT)
}
