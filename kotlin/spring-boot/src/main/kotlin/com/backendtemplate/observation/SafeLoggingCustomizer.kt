package com.backendtemplate.observation

import ch.qos.logback.classic.spi.ILoggingEvent
import org.springframework.boot.json.JsonWriter
import org.springframework.boot.logging.structured.StructuredLoggingJsonMembersCustomizer

class SafeLoggingCustomizer : StructuredLoggingJsonMembersCustomizer<ILoggingEvent> {
    override fun customize(members: JsonWriter.Members<ILoggingEvent>) {
        members.applyingPathFilter { path -> path.toString() in SENSITIVE_PATHS }
        members.applyingValueProcessor(
            JsonWriter.ValueProcessor.of<String> { value -> if (value in PUBLIC_EVENTS) value else "framework.event" }
                .whenHasPath("message"),
        )
    }

    private companion object {
        val PUBLIC_EVENTS = setOf("http.completed", "application.failed")
        val SENSITIVE_PATHS = setOf("error.message", "error.stack_trace")
    }
}
