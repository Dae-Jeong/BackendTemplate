package com.backendtemplate.validation;

import com.backendtemplate.exceptions.ReservationFailure;
import com.backendtemplate.exceptions.ReservationFailure.Reason;

public final class ReservationValidation {
    private ReservationValidation() {}

    public static void validateProductExists(boolean productExists) {
        if (!productExists) {
            throw new ReservationFailure(Reason.PRODUCT_NOT_FOUND);
        }
    }

    public static void validateReplayProduct(String requestedProductId, String replayProductId) {
        if (!requestedProductId.equals(replayProductId)) {
            throw new ReservationFailure(Reason.IDEMPOTENCY_CONFLICT);
        }
    }
}
