package com.backendtemplate.http

import com.backendtemplate.dto.ReserveRequest
import tools.jackson.core.JsonParser
import tools.jackson.databind.DeserializationContext
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ValueDeserializer

class ReserveRequestDeserializer : ValueDeserializer<ReserveRequest>() {
    override fun deserialize(parser: JsonParser, context: DeserializationContext): ReserveRequest {
        val body: JsonNode = parser.readValueAsTree()
        if (!body.isObject) throw InvalidInput()
        val product = body.get("product_id") ?: throw InvalidInput("body", "product_id", "REQUIRED")
        if (!product.isString) throw InvalidInput("body", "product_id", "INVALID")
        if (body.size() != 1) throw InvalidInput()
        return ReserveRequest(product.asString())
    }
}
