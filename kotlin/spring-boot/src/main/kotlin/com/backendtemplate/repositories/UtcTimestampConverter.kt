package com.backendtemplate.repositories

import jakarta.persistence.AttributeConverter
import jakarta.persistence.Converter
import java.time.Instant

@Converter
class UtcTimestampConverter : AttributeConverter<Instant, String> {
    override fun convertToDatabaseColumn(value: Instant?): String? = value?.toString()

    override fun convertToEntityAttribute(value: String?): Instant? = value?.let(Instant::parse)
}
