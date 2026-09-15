package com.backendtemplate.services;

import com.backendtemplate.contracts.Reservation;
import com.backendtemplate.contracts.ReservationResult;
import com.backendtemplate.repositories.ReservationRepository;
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
        var replay = repository.findMatchingReplay(key, productId);
        if (replay.isPresent()) {
            return new ReservationResult(replay.get(), true);
        }
        repository.claim(key);
        repository.decreaseStock(productId);
        var reservation = new Reservation(UUID.randomUUID().toString().replace("-", ""), productId, clock.instant());
        repository.saveReservationAndReplay(reservation, key);
        return new ReservationResult(reservation, false);
    }

    @Transactional(readOnly = true, rollbackFor = Exception.class)
    public ReservationResult replay(String productId, String key) {
        return new ReservationResult(repository.findMatchingReplay(key, productId).orElseThrow(), true);
    }
}
