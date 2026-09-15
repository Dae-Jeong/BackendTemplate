package com.backendtemplate.http

import com.backendtemplate.dto.FieldError

class InvalidInput(val errors: List<FieldError>) : RuntimeException() {
    constructor() : this(listOf(FieldError(location = emptyList(), code = "INVALID")))

    constructor(scope: String, field: String, code: String) :
        this(listOf(FieldError(location = listOf(scope, field), code = code)))
}
