package com.backendtemplate.http

import com.backendtemplate.config.AppProperties
import jakarta.servlet.AsyncEvent
import jakarta.servlet.AsyncListener
import jakarta.servlet.FilterChain
import jakarta.servlet.ServletException
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import java.io.IOException
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import org.slf4j.LoggerFactory
import org.slf4j.MDC
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.stereotype.Component
import org.springframework.web.filter.OncePerRequestFilter
import org.springframework.web.servlet.HandlerMapping

@Component("apiRequestContextFilter")
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
class RequestContextFilter(private val properties: AppProperties) : OncePerRequestFilter() {
    override fun doFilterInternal(
        request: HttpServletRequest,
        response: HttpServletResponse,
        chain: FilterChain,
    ) {
        val started = System.nanoTime()
        val id = requestId(request)
        response.setHeader("X-Request-ID", id)
        putContext(id)
        val completed = AtomicBoolean()
        try {
            chain.doFilter(request, response)
        } catch (error: IOException) {
            request.setAttribute("error.type", error.javaClass.name)
            throw error
        } catch (error: ServletException) {
            request.setAttribute("error.type", error.javaClass.name)
            throw error
        } catch (error: RuntimeException) {
            request.setAttribute("error.type", error.javaClass.name)
            throw error
        } catch (error: Error) {
            request.setAttribute("error.type", error.javaClass.name)
            throw error
        } finally {
            try {
                if (request.isAsyncStarted) {
                    request.asyncContext.addListener(completionListener(request, response, started, completed))
                } else {
                    complete(request, response, started, completed)
                }
            } catch (_: IllegalStateException) {
                complete(request, response, started, completed)
            } finally {
                clearContext()
            }
        }
    }

    private fun completionListener(
        request: HttpServletRequest,
        response: HttpServletResponse,
        started: Long,
        completed: AtomicBoolean,
    ): AsyncListener = object : AsyncListener {
        override fun onComplete(event: AsyncEvent) = complete(request, response, started, completed)

        override fun onTimeout(event: AsyncEvent) {
            request.setAttribute("error.type", "AsyncTimeout")
        }

        override fun onError(event: AsyncEvent) {
            request.setAttribute("error.type", event.throwable?.javaClass?.name ?: "AsyncError")
        }

        override fun onStartAsync(event: AsyncEvent) {
            event.asyncContext.addListener(this)
        }
    }

    private fun complete(
        request: HttpServletRequest,
        response: HttpServletResponse,
        started: Long,
        completed: AtomicBoolean,
    ) {
        if (!completed.compareAndSet(false, true)) return
        val previous = MDC.getCopyOfContextMap()
        try {
            putContext(requestId(request))
            val route = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE)
            val error = request.getAttribute("error.type")
            LOG.atInfo()
                .addKeyValue("event.action", "http.completed")
                .addKeyValue("app.log_schema_version", 1)
                .addKeyValue("http.request.method", request.method)
                .addKeyValue("http.response.status_code", response.status)
                .addKeyValue("http.response.committed", response.isCommitted)
                .addKeyValue("http.route", route?.toString() ?: "unmatched")
                .addKeyValue("event.duration", System.nanoTime() - started)
                .addKeyValue("event.outcome", if (response.status >= 500 || error != null) "failure" else "success")
                .addKeyValue("error.type", error)
                .log("http.completed")
        } catch (_: RuntimeException) {
            // Telemetry cannot change the business outcome.
        } finally {
            if (previous == null) MDC.clear() else MDC.setContextMap(previous)
        }
    }

    private fun putContext(id: String) {
        MDC.put("app.work.id", id)
        MDC.put("app.work.kind", "http")
        MDC.put("app.environment", properties.environment)
    }

    private fun clearContext() {
        MDC.remove("app.work.id")
        MDC.remove("app.work.kind")
        MDC.remove("app.environment")
    }

    private companion object {
        val LOG = LoggerFactory.getLogger(RequestContextFilter::class.java)
    }
}

fun requestId(request: HttpServletRequest): String {
    val existing = request.getAttribute("request_id")
    if (existing != null) return existing.toString()
    val generated = UUID.randomUUID().toString().replace("-", "")
    request.setAttribute("request_id", generated)
    return generated
}
