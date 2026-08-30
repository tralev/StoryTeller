package com.storyteller.droid.engine

import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.math.BigDecimal

/** Closed, network-free Draft 2020-12 evaluator for the frozen v2 keyword inventory. */
internal object TrustedJSONSchema {
    private val schemas: Map<String, JsonObject> by lazy {
        TrustedV2Schemas.documents.mapValues { (_, data) ->
            JsonParser.parseString(data.toString(Charsets.UTF_8)).asJsonObject
        }
    }

    fun validates(schemaName: String, document: ByteArray, definition: String? = null): Boolean {
        val root = schemas["$schemaName.schema.json"] ?: return false
        val instance = try { JsonParser.parseString(document.toString(Charsets.UTF_8)) }
        catch (_: Exception) { return false }
        if (definition != null) {
            if (!instance.isJsonObject || instance.asJsonObject.keySet() != setOf("value")) {
                return false
            }
            val selected = root["\$defs"]?.asJsonObject?.get(definition) ?: return false
            return validate(selected, instance.asJsonObject["value"], root)
        }
        return validate(root, instance, root)
    }

    private fun validate(schema: JsonElement, instance: JsonElement, root: JsonObject): Boolean {
        if (schema.isJsonPrimitive && schema.asJsonPrimitive.isBoolean) return schema.asBoolean
        if (!schema.isJsonObject) return false
        val rule = schema.asJsonObject
        rule["\$ref"]?.asString?.let { reference ->
            val (targetRoot, target) = resolve(reference, root) ?: return false
            if (!validate(target, instance, targetRoot)) return false
        }
        rule["type"]?.let { declared ->
            val types = if (declared.isJsonArray) declared.asJsonArray.map { it.asString }
            else listOf(declared.asString)
            if (types.none { matchesType(it, instance) }) return false
        }
        rule["const"]?.let { if (it != instance) return false }
        rule["enum"]?.asJsonArray?.let { if (it.none { option -> option == instance }) return false }
        rule["anyOf"]?.asJsonArray?.let {
            if (it.none { option -> validate(option, instance, root) }) return false
        }
        rule["oneOf"]?.asJsonArray?.let {
            if (it.count { option -> validate(option, instance, root) } != 1) return false
        }
        if (instance.isJsonObject && !validateObject(rule, instance.asJsonObject, root)) return false
        if (instance.isJsonArray && !validateArray(rule, instance, root)) return false
        if (instance.isJsonPrimitive && instance.asJsonPrimitive.isString &&
            !validateString(rule, instance.asString)
        ) return false
        if (instance.isJsonPrimitive && instance.asJsonPrimitive.isNumber &&
            !validateNumber(rule, instance.asBigDecimal)
        ) return false
        return true
    }

    private fun validateObject(rule: JsonObject, value: JsonObject, root: JsonObject): Boolean {
        val names = value.keySet()
        rule["required"]?.asJsonArray?.let { required ->
            if (required.any { it.asString !in names }) return false
        }
        rule["minProperties"]?.let { if (names.size < it.asInt) return false }
        val properties = rule["properties"]?.asJsonObject
        properties?.entrySet()?.forEach { (name, childSchema) ->
            value[name]?.let { if (!validate(childSchema, it, root)) return false }
        }
        rule["propertyNames"]?.let { nameSchema ->
            if (names.any { !validate(nameSchema, JsonParser.parseString(jsonString(it)), root) }) {
                return false
            }
        }
        val extras = names - (properties?.keySet() ?: emptySet())
        rule["additionalProperties"]?.let { additional ->
            if (additional.isJsonPrimitive && additional.asJsonPrimitive.isBoolean) {
                if (!additional.asBoolean && extras.isNotEmpty()) return false
            } else if (extras.any { !validate(additional, value[it], root) }) return false
        }
        return true
    }

    private fun validateArray(rule: JsonObject, value: JsonElement, root: JsonObject): Boolean {
        val items = value.asJsonArray
        rule["minItems"]?.let { if (items.size() < it.asInt) return false }
        rule["maxItems"]?.let { if (items.size() > it.asInt) return false }
        rule["uniqueItems"]?.let {
            if (it.asBoolean && items.toSet().size != items.size()) return false
        }
        val prefix = rule["prefixItems"]?.asJsonArray
        prefix?.forEachIndexed { index, child ->
            if (index < items.size() && !validate(child, items[index], root)) return false
        }
        rule["items"]?.let { itemSchema ->
            val start = prefix?.size() ?: 0
            for (index in start until items.size()) {
                if (!validate(itemSchema, items[index], root)) return false
            }
        }
        return true
    }

    private fun validateString(rule: JsonObject, value: String): Boolean {
        val length = value.codePointCount(0, value.length)
        rule["minLength"]?.let { if (length < it.asInt) return false }
        rule["maxLength"]?.let { if (length > it.asInt) return false }
        rule["pattern"]?.let { if (!Regex(it.asString).containsMatchIn(value)) return false }
        return true
    }

    private fun validateNumber(rule: JsonObject, value: BigDecimal): Boolean {
        rule["minimum"]?.let { if (value < it.asBigDecimal) return false }
        rule["maximum"]?.let { if (value > it.asBigDecimal) return false }
        return true
    }

    private fun matchesType(type: String, value: JsonElement): Boolean = when (type) {
        "object" -> value.isJsonObject
        "array" -> value.isJsonArray
        "string" -> value.isJsonPrimitive && value.asJsonPrimitive.isString
        "integer" -> value.isJsonPrimitive && value.asJsonPrimitive.isNumber &&
            INTEGER.matches(value.asJsonPrimitive.asString)
        "number" -> value.isJsonPrimitive && value.asJsonPrimitive.isNumber
        "boolean" -> value.isJsonPrimitive && value.asJsonPrimitive.isBoolean
        "null" -> value.isJsonNull
        else -> false
    }

    private fun resolve(reference: String, currentRoot: JsonObject): Pair<JsonObject, JsonElement>? {
        val parts = reference.split('#', limit = 2)
        val root = if (parts[0].isEmpty()) currentRoot else {
            val name = parts[0].substringAfterLast('/')
            schemas[name] ?: return null
        }
        var target: JsonElement = root
        val pointer = parts.getOrElse(1) { "" }
        if (pointer.isNotEmpty()) for (raw in pointer.removePrefix("/").split('/')) {
            val key = raw.replace("~1", "/").replace("~0", "~")
            target = target.asJsonObject[key] ?: return null
        }
        return root to target
    }

    private fun jsonString(value: String): String =
        com.google.gson.Gson().toJson(value)

    private val INTEGER = Regex("-?(0|[1-9][0-9]*)")
}
