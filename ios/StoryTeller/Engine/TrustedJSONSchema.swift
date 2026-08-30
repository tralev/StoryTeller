import CoreFoundation
import Foundation

/// Closed, network-free Draft 2020-12 evaluator for the frozen v2 keyword inventory.
enum TrustedJSONSchema {
    private static let schemas: [String: [String: Any]] = TrustedV2Schemas.documents.mapValues {
        try! JSONSerialization.jsonObject(with: $0) as! [String: Any]
    }

    static func validates(schemaName: String, document: Data, definition: String? = nil) -> Bool {
        guard let root = schemas["\(schemaName).schema.json"],
              let instance = try? JSONSerialization.jsonObject(
                with: document, options: [.fragmentsAllowed]
              ) else { return false }
        if let definition {
            guard let wrapper = instance as? [String: Any], Set(wrapper.keys) == ["value"],
                  let selected = (root["$defs"] as? [String: Any])?[definition],
                  let value = wrapper["value"] else { return false }
            return validate(selected, value, root)
        }
        return validate(root, instance, root)
    }

    private static func validate(_ schema: Any, _ value: Any, _ root: [String: Any]) -> Bool {
        if let boolean = schema as? Bool { return boolean }
        guard let rule = schema as? [String: Any] else { return false }
        if let reference = rule["$ref"] as? String {
            guard let (targetRoot, target) = resolve(reference, root),
                  validate(target, value, targetRoot) else { return false }
        }
        if let declaration = rule["type"] {
            let types = declaration as? [String] ?? [declaration as? String].compactMap { $0 }
            if !types.contains(where: { matchesType($0, value) }) { return false }
        }
        if let constant = rule["const"], !equal(constant, value) { return false }
        if let options = rule["enum"] as? [Any], !options.contains(where: { equal($0, value) }) {
            return false
        }
        if let options = rule["anyOf"] as? [Any],
           !options.contains(where: { validate($0, value, root) }) { return false }
        if let options = rule["oneOf"] as? [Any],
           options.filter({ validate($0, value, root) }).count != 1 { return false }
        if let object = value as? [String: Any], !validateObject(rule, object, root) {
            return false
        }
        if let array = value as? [Any], !validateArray(rule, array, root) { return false }
        if let string = value as? String, !validateString(rule, string) { return false }
        if isNumber(value), !validateNumber(rule, value as! NSNumber) { return false }
        return true
    }

    private static func validateObject(
        _ rule: [String: Any], _ value: [String: Any], _ root: [String: Any]
    ) -> Bool {
        let names = Set(value.keys)
        if let required = rule["required"] as? [String], !Set(required).isSubset(of: names) {
            return false
        }
        if let minimum = integer(rule["minProperties"]), names.count < minimum { return false }
        let properties = rule["properties"] as? [String: Any] ?? [:]
        for (name, childSchema) in properties {
            if let child = value[name], !validate(childSchema, child, root) { return false }
        }
        if let nameSchema = rule["propertyNames"] {
            if names.contains(where: { !validate(nameSchema, $0, root) }) { return false }
        }
        let extras = names.subtracting(properties.keys)
        if let additional = rule["additionalProperties"] {
            if let allowed = additional as? Bool {
                if !allowed && !extras.isEmpty { return false }
            } else if extras.contains(where: { !validate(additional, value[$0]!, root) }) {
                return false
            }
        }
        return true
    }

    private static func validateArray(
        _ rule: [String: Any], _ value: [Any], _ root: [String: Any]
    ) -> Bool {
        if let minimum = integer(rule["minItems"]), value.count < minimum { return false }
        if let maximum = integer(rule["maxItems"]), value.count > maximum { return false }
        if (rule["uniqueItems"] as? Bool) == true {
            for left in value.indices {
                for right in value.indices where left < right {
                    if equal(value[left], value[right]) { return false }
                }
            }
        }
        let prefix = rule["prefixItems"] as? [Any] ?? []
        for index in 0..<min(prefix.count, value.count) {
            if !validate(prefix[index], value[index], root) { return false }
        }
        if let itemSchema = rule["items"] {
            for index in prefix.count..<value.count {
                if !validate(itemSchema, value[index], root) { return false }
            }
        }
        return true
    }

    private static func validateString(_ rule: [String: Any], _ value: String) -> Bool {
        let length = value.unicodeScalars.count
        if let minimum = integer(rule["minLength"]), length < minimum { return false }
        if let maximum = integer(rule["maxLength"]), length > maximum { return false }
        if let pattern = rule["pattern"] as? String {
            guard let expression = try? NSRegularExpression(pattern: pattern),
                  expression.firstMatch(
                    in: value, range: NSRange(value.startIndex..., in: value)
                  ) != nil else { return false }
        }
        return true
    }

    private static func validateNumber(_ rule: [String: Any], _ value: NSNumber) -> Bool {
        let decimal = value.decimalValue
        if let minimum = rule["minimum"] as? NSNumber, decimal < minimum.decimalValue {
            return false
        }
        if let maximum = rule["maximum"] as? NSNumber, decimal > maximum.decimalValue {
            return false
        }
        return true
    }

    private static func matchesType(_ type: String, _ value: Any) -> Bool {
        switch type {
        case "object": return value is [String: Any]
        case "array": return value is [Any]
        case "string": return value is String
        case "integer": return isNumber(value) && (value as! NSNumber).doubleValue.rounded() ==
            (value as! NSNumber).doubleValue
        case "number": return isNumber(value)
        case "boolean": return isBoolean(value)
        case "null": return value is NSNull
        default: return false
        }
    }

    private static func resolve(
        _ reference: String, _ currentRoot: [String: Any]
    ) -> ([String: Any], Any)? {
        let pieces = reference.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)
        let root: [String: Any]
        if pieces[0].isEmpty { root = currentRoot }
        else {
            guard let name = pieces[0].split(separator: "/").last,
                  let selected = schemas[String(name)] else { return nil }
            root = selected
        }
        var target: Any = root
        if pieces.count == 2 && !pieces[1].isEmpty {
            for raw in pieces[1].dropFirst().split(separator: "/") {
                let key = raw.replacingOccurrences(of: "~1", with: "/")
                    .replacingOccurrences(of: "~0", with: "~")
                guard let object = target as? [String: Any], let child = object[key] else {
                    return nil
                }
                target = child
            }
        }
        return (root, target)
    }

    private static func equal(_ left: Any, _ right: Any) -> Bool {
        guard JSONSerialization.isValidJSONObject([left]), JSONSerialization.isValidJSONObject([right]),
              let a = try? JSONSerialization.data(withJSONObject: [left], options: [.sortedKeys]),
              let b = try? JSONSerialization.data(withJSONObject: [right], options: [.sortedKeys])
        else { return false }
        return a == b
    }

    private static func integer(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber, !isBoolean(number) else { return nil }
        return number.intValue
    }
    private static func isBoolean(_ value: Any) -> Bool {
        CFGetTypeID(value as CFTypeRef) == CFBooleanGetTypeID()
    }
    private static func isNumber(_ value: Any) -> Bool { value is NSNumber && !isBoolean(value) }
}
