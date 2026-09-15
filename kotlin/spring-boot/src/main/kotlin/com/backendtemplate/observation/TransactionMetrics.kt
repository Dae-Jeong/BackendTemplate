package com.backendtemplate.observation

import io.micrometer.core.instrument.MeterRegistry
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import org.springframework.context.annotation.Profile
import org.springframework.stereotype.Component
import org.springframework.transaction.TransactionExecution
import org.springframework.transaction.TransactionExecutionListener

@Component
@Profile("!no-db")
class TransactionMetrics(private val registry: MeterRegistry) : TransactionExecutionListener {
    private data class Started(val nanos: Long, val committing: Boolean)
    private enum class Outcome(val tag: String) {
        COMMITTED("committed"),
        ROLLED_BACK("rolled_back"),
        FAILED("failed"),
    }

    private val active = ConcurrentHashMap<TransactionExecution, Started>()

    override fun beforeBegin(transaction: TransactionExecution) {
        active[transaction] = Started(nanos = System.nanoTime(), committing = false)
    }

    override fun afterBegin(transaction: TransactionExecution, beginFailure: Throwable?) {
        if (beginFailure != null) finish(transaction, Outcome.FAILED)
    }

    override fun beforeCommit(transaction: TransactionExecution) {
        active.computeIfPresent(transaction) { _, value -> Started(nanos = value.nanos, committing = true) }
    }

    override fun afterCommit(transaction: TransactionExecution, commitFailure: Throwable?) {
        finish(transaction, if (commitFailure == null) Outcome.COMMITTED else Outcome.FAILED)
    }

    override fun afterRollback(transaction: TransactionExecution, rollbackFailure: Throwable?) {
        val started = active[transaction]
        val outcome = if (rollbackFailure != null || started?.committing == true) Outcome.FAILED else Outcome.ROLLED_BACK
        finish(transaction, outcome)
    }

    private fun finish(transaction: TransactionExecution, outcome: Outcome) {
        val started = active.remove(transaction) ?: return
        try {
            registry.counter("db.transactions", "role", "primary", "outcome", outcome.tag).increment()
            registry.timer("db.transaction.duration", "role", "primary", "outcome", outcome.tag)
                .record(System.nanoTime() - started.nanos, TimeUnit.NANOSECONDS)
        } catch (_: RuntimeException) {
            // Actual transaction completion remains authoritative when observation fails.
        }
    }
}
