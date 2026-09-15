package com.backendtemplate.services;

import com.backendtemplate.contracts.Reservation;
import com.backendtemplate.contracts.ReservationResult;
import com.backendtemplate.exceptions.ReservationFailure;
import com.backendtemplate.exceptions.ReservationFailure.Reason;
import com.backendtemplate.repositories.ReservationRepository;
import com.backendtemplate.validation.ReservationValidation;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile("!no-db")
public class ReservationService {
    private final ReservationRepository repository;
    private final Clock clock;

    public ReservationService(ReservationRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Transactional(rollbackFor = Exception.class)
    public ReservationResult reserve(String productId, String key) {
        var replay = repository.findReplay(key);
        if (replay.isPresent()) {
            var value = replay.get();
            ReservationValidation.validateReplayProduct(productId, value.productId());
            return new ReservationResult(value, true);
        }
        repository.claim(key);
        if (!repository.decreaseStockIfAvailable(productId)) {
            ReservationValidation.validateProductExists(repository.productExists(productId));
            throw new ReservationFailure(Reason.SOLD_OUT);
        }
        var reservation = new Reservation(UUID.randomUUID().toString().replace("-", ""), productId, clock.instant());
        repository.saveReservationAndReplay(reservation, key);
        return new ReservationResult(reservation, false);
    }

    @Transactional(readOnly = true, rollbackFor = Exception.class)
    public ReservationResult replay(String productId, String key) {
        var replay = repository.findReplay(key).orElseThrow();
        ReservationValidation.validateReplayProduct(productId, replay.productId());
        return new ReservationResult(replay, true);
    }
}
