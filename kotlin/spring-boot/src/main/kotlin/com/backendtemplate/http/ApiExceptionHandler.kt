package com.backendtemplate.http

import com.backendtemplate.dto.FieldError
import com.backendtemplate.dto.Problem
import com.backendtemplate.exceptions.ReservationFailure
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import java.sql.SQLTransientConnectionException
import org.hibernate.exception.JDBCConnectionException
import org.springframework.dao.CannotAcquireLockException
import org.springframework.dao.QueryTimeoutException
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatus
import org.springframework.http.HttpStatusCode
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.jdbc.CannotGetJdbcConnectionException
import org.springframework.transaction.CannotCreateTransactionException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.context.request.ServletWebRequest
import org.springframework.web.context.request.WebRequest
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler

@RestControllerAdvice
class ApiExceptionHandler : ResponseEntityExceptionHandler() {
    @ExceptionHandler(InvalidInput::class)
    fun invalid(error: InvalidInput, request: HttpServletRequest): ResponseEntity<Any> =
        problemResponse(422, "INVALID_INPUT", error.errors, HttpHeaders(), request)

    @ExceptionHandler(ReservationFailure::class)
    fun reservation(error: ReservationFailure, request: HttpServletRequest): ResponseEntity<Any> {
        val status = if (error.reason == ReservationFailure.Reason.PRODUCT_NOT_FOUND) 404 else 409
        return problemResponse(status, error.reason.name, null, HttpHeaders(), request)
    }

    @ExceptionHandler(Exception::class)
    fun unexpected(
        error: Exception,
        request: HttpServletRequest,
        response: HttpServletResponse,
    ): ResponseEntity<Any>? {
        request.setAttribute("error.type", error.javaClass.name)
        if (response.isCommitted) return null
        val headers = HttpHeaders()
        if (error is CannotAcquireLockException || error is QueryTimeoutException) {
            headers.set("Retry-After", "1")
            return problemResponse(503, "DATABASE_BUSY", null, headers, request)
        }
        if ((error is CannotCreateTransactionException || error is CannotGetJdbcConnectionException) &&
            isPoolTimeout(error.cause)
        ) {
            headers.set("Retry-After", "1")
            return problemResponse(503, "DATABASE_POOL_TIMEOUT", null, headers, request)
        }
        return problemResponse(500, "INTERNAL_ERROR", null, headers, request)
    }

    override fun handleExceptionInternal(
        ex: Exception,
        body: Any?,
        headers: HttpHeaders,
        statusCode: HttpStatusCode,
        request: WebRequest,
    ): ResponseEntity<Any>? {
        val status = if (statusCode.value() == 400) 422 else statusCode.value()
        val servletRequest = (request as ServletWebRequest).request
        val invalid = ex.cause as? InvalidInput
        if (invalid != null) return problemResponse(422, "INVALID_INPUT", invalid.errors, headers, servletRequest)
        val code = when (status) {
            422 -> "INVALID_INPUT"
            404 -> "NOT_FOUND"
            405 -> "METHOD_NOT_ALLOWED"
            else -> if (status >= 500) "INTERNAL_ERROR" else "HTTP_ERROR"
        }
        val errors = if (status == 422) listOf(FieldError(emptyList(), "INVALID")) else null
        return problemResponse(status, code, errors, headers, servletRequest)
    }
}

private fun isPoolTimeout(cause: Throwable?): Boolean {
    val candidate = if (cause is JDBCConnectionException) cause.sqlException else cause
    return candidate is SQLTransientConnectionException
}

fun problemResponse(
    status: Int,
    code: String,
    errors: List<FieldError>?,
    source: HttpHeaders,
    request: HttpServletRequest,
): ResponseEntity<Any> {
    val title = if (status == 422) "Unprocessable Entity" else HttpStatus.valueOf(status).reasonPhrase
    val requestId = requestId(request)
    val problem = Problem(
        type = "about:blank",
        title = title,
        status = status,
        code = code,
        requestId = requestId,
        errors = errors,
    )
    val headers = HttpHeaders()
    headers.putAll(source)
    headers.remove(HttpHeaders.CONTENT_LENGTH)
    headers.contentType = MediaType.APPLICATION_PROBLEM_JSON
    headers.set("X-Request-ID", requestId)
    return ResponseEntity(problem, headers, HttpStatusCode.valueOf(status))
}
