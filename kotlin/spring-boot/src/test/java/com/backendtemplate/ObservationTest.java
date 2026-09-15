package com.backendtemplate;

import static org.assertj.core.api.Assertions.*;
import com.backendtemplate.config.AppProperties;
import com.backendtemplate.http.RequestContextFilter;
import com.backendtemplate.observation.TransactionMetrics;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.transaction.TransactionExecution;

class ObservationTest {
    @Test
    void requestIdIsServerOwnedAndMdcIsClearedOnSuccessAndFailure() throws Exception {
        var logger = (ch.qos.logback.classic.Logger) org.slf4j.LoggerFactory.getLogger(RequestContextFilter.class);
        var originalLevel = logger.getLevel();
        logger.setLevel(ch.qos.logback.classic.Level.INFO);
        var logs = new ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent>();
        logs.start();
        logger.addAppender(logs);
        var filter = new RequestContextFilter(new AppProperties("test"));
        var request = new MockHttpServletRequest("GET", "/");
        request.addHeader("X-Request-ID", "private-id");
        var response = new MockHttpServletResponse();
        MDC.put("unrelated", "preserved");
        try {
            filter.doFilter(request, response, (incoming, outgoing) -> {
                assertThat(MDC.get("app.work.id")).hasSize(32).isNotEqualTo("private-id");
            });
            assertThat(MDC.get("app.work.id")).isNull();
            assertThat(MDC.get("unrelated")).isEqualTo("preserved");
            var next = new MockHttpServletRequest("GET", "/");
            assertThatThrownBy(() -> filter.doFilter(next, new MockHttpServletResponse(), (incoming, outgoing) -> {
                throw new java.io.IOException("private failure");
            })).isInstanceOf(java.io.IOException.class);
            assertThat(com.backendtemplate.http.RequestContextFilterKt.requestId(next))
                    .isNotEqualTo(response.getHeader("X-Request-ID"));
            assertThat(MDC.get("app.work.id")).isNull();
            assertThat(logs.list).hasSize(2);
            assertThat(logs.list.get(1).getKeyValuePairs()).anySatisfy(pair -> {
                assertThat(pair.key).isEqualTo("event.outcome");
                assertThat(pair.value).isEqualTo("failure");
            });
            assertThat(logs.list.get(1).getKeyValuePairs()).anySatisfy(pair -> {
                assertThat(pair.key).isEqualTo("error.type");
                assertThat(pair.value).isEqualTo("java.io.IOException");
            });
        } finally {
            MDC.clear();
            logger.detachAppender(logs);
            logger.setLevel(originalLevel);
            logs.stop();
        }
    }

    @Test
    void brokenMetricsDoesNotChangeTransactionOutcome() {
        var registry = new SimpleMeterRegistry() {
            @Override
            protected Counter newCounter(Meter.Id id) {
                throw new IllegalStateException("private metric failure");
            }
        };
        try {
            var metrics = new TransactionMetrics(registry);
            var transaction = new TransactionExecution() {};
            metrics.beforeBegin(transaction);
            metrics.beforeCommit(transaction);
            assertThatCode(() -> metrics.afterCommit(transaction, null)).doesNotThrowAnyException();
        } finally {
            registry.close();
        }
    }
}
