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

    private val active = ConcurrentHashMap<TransactionExecution, Started>()

    override fun beforeBegin(transaction: TransactionExecution) {
        active[transaction] = Started(System.nanoTime(), false)
    }

    override fun afterBegin(transaction: TransactionExecution, beginFailure: Throwable?) {
        if (beginFailure != null) finish(transaction, "failed")
    }

    override fun beforeCommit(transaction: TransactionExecution) {
        active.computeIfPresent(transaction) { _, value -> Started(value.nanos, true) }
    }

    override fun afterCommit(transaction: TransactionExecution, commitFailure: Throwable?) {
        finish(transaction, if (commitFailure == null) "committed" else "failed")
    }

    override fun afterRollback(transaction: TransactionExecution, rollbackFailure: Throwable?) {
        val started = active[transaction]
        val outcome = if (rollbackFailure != null || started?.committing == true) "failed" else "rolled_back"
        finish(transaction, outcome)
    }

    private fun finish(transaction: TransactionExecution, outcome: String) {
        val started = active.remove(transaction) ?: return
        try {
            registry.counter("db.transactions", "role", "primary", "outcome", outcome).increment()
            registry.timer("db.transaction.duration", "role", "primary", "outcome", outcome)
                .record(System.nanoTime() - started.nanos, TimeUnit.NANOSECONDS)
        } catch (_: RuntimeException) {
            // Actual transaction completion remains authoritative when observation fails.
        }
    }
}
