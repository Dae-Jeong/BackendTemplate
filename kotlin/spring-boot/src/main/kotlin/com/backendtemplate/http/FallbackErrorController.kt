package com.backendtemplate.http

import jakarta.servlet.RequestDispatcher
import jakarta.servlet.http.HttpServletRequest
import org.springframework.boot.webmvc.error.ErrorController
import org.springframework.http.HttpHeaders
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
class FallbackErrorController : ErrorController {
    @RequestMapping("/error")
    fun error(request: HttpServletRequest): ResponseEntity<Any> {
        val value = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE)
        val status = if (value is Int && value in 400..599) value else 500
        val code = if (status == 404) "NOT_FOUND" else "INTERNAL_ERROR"
        return problemResponse(status, code, null, HttpHeaders(), request)
    }
}
