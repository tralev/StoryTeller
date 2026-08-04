import SwiftUI

/// StoryTeller dark fantasy color palette.
enum AppTheme {
    // Parchment tones
    static let parchment = Color(red: 0.96, green: 0.90, blue: 0.78)
    static let parchmentDark = Color(red: 0.83, green: 0.72, blue: 0.59)
    
    // Ink tones
    static let ink = Color(red: 0.18, green: 0.11, blue: 0.05)
    static let inkLight = Color(red: 0.36, green: 0.23, blue: 0.12)
    
    // Gold tones
    static let gold = Color(red: 0.83, green: 0.66, blue: 0.26)
    static let goldDark = Color(red: 0.55, green: 0.41, blue: 0.08)
    
    // Accent
    static let ember = Color(red: 0.80, green: 0.27, blue: 0.13)
    
    // Backgrounds
    static let midnight = Color(red: 0.05, green: 0.04, blue: 0.03)
    static let charcoal = Color(red: 0.12, green: 0.11, blue: 0.09)
    static let deepBlue = Color(red: 0.10, green: 0.16, blue: 0.23)
}

/// Typography extensions for StoryTeller.
extension Font {
    static let storytellerTitle = Font.custom("Georgia", size: 28).weight(.bold)
    static let storytellerHeading = Font.custom("Georgia", size: 22).weight(.semibold)
    static let storytellerBody = Font.custom("Georgia", size: 18)
    static let storytellerCaption = Font.custom("Georgia", size: 14).italic()
    static let storytellerChoice = Font.system(size: 16, weight: .semibold, design: .serif)
}
