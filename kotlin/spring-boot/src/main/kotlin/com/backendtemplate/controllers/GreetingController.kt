package com.backendtemplate.controllers

import com.backendtemplate.dto.ApiResponse
import com.backendtemplate.dto.GreetingResponse
import com.backendtemplate.dto.MessageResponse
import com.backendtemplate.http.requiredText
import com.backendtemplate.services.GreetingService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
class GreetingController(private val service: GreetingService) {
    @GetMapping("/")
    fun index(): ApiResponse<MessageResponse> = ApiResponse(MessageResponse("Hello, Kotlin Spring Boot!"))

    @GetMapping("/v1/greetings")
    fun greet(@RequestParam(required = false) name: String?): ApiResponse<GreetingResponse> {
        val validatedName = requiredText(name?.trim(), "query", "name", 80)
        val result = service.greet(validatedName)
        return ApiResponse(
            GreetingResponse(
                message = result.message,
                generatedAt = result.generatedAt,
            ),
        )
    }
}
