package com.backendtemplate

import kotlin.system.exitProcess
import org.slf4j.LoggerFactory
import org.springframework.boot.SpringApplication
import org.springframework.boot.WebApplicationType
import org.springframework.boot.autoconfigure.SpringBootApplication

@SpringBootApplication
class TemplateApplication

fun main(args: Array<String>) {
    val application = SpringApplication(TemplateApplication::class.java)
    val seed = "--seed" in args
    if (seed) {
        application.setAdditionalProfiles("seed")
        application.setWebApplicationType(WebApplicationType.NONE)
    }
    try {
        val context = application.run(*args)
        if (seed) context.close()
    } catch (error: RuntimeException) {
        LoggerFactory.getLogger(TemplateApplication::class.java).atError()
            .addKeyValue("error.type", error.javaClass.name)
            .log("application.failed")
        exitProcess(1)
    }
}
