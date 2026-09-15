package com.backendtemplate.http

fun requiredText(value: String?, scope: String, field: String, max: Int): String {
    if (value == null) throw InvalidInput(scope, field, "REQUIRED")
    if (value.isEmpty()) throw InvalidInput(scope, field, "TOO_SHORT")
    if (value.codePointCount(0, value.length) > max) throw InvalidInput(scope, field, "TOO_LONG")
    return value
}

fun requiredToken(value: String?, scope: String, field: String, max: Int): String {
    val text = requiredText(value, scope, field, max)
    if (!text.matches(Regex("[A-Za-z0-9._:-]+"))) throw InvalidInput(scope, field, "INVALID")
    return text
}
