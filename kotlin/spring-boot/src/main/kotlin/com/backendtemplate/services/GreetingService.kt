package com.backendtemplate.services

import com.backendtemplate.contracts.Greeting
import java.time.Clock
import org.springframework.stereotype.Service

@Service
class GreetingService(private val clock: Clock) {
    fun greet(name: String): Greeting = Greeting("Hello, $name!", clock.instant())
}
