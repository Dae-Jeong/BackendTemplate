package com.backendtemplate;

import static org.assertj.core.api.Assertions.assertThat;
import com.backendtemplate.services.GreetingService;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void usesInjectedClock() {
        var now = Instant.parse("2026-09-08T00:00:00Z");
        var result = new GreetingService(Clock.fixed(now, ZoneOffset.UTC)).greet("Marin");
        assertThat(result.getMessage()).isEqualTo("Hello, Marin!");
        assertThat(result.getGeneratedAt()).isEqualTo(now);
    }
}
