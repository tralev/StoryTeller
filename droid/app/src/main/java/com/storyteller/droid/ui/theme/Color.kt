package com.storyteller.droid.ui.theme

import androidx.compose.ui.graphics.Color

// ── Dark Fantasy Palette (The Forge aesthetic) ───────────────────────
val Parchment = Color(0xFFF5E6C8)
val ParchmentDark = Color(0xFFD4B896)
val Ink = Color(0xFF2D1B0E)
val InkLight = Color(0xFF5C3A1E)
val Gold = Color(0xFFD4A843)
val GoldDark = Color(0xFF8B6914)
val Ember = Color(0xFFCC4422)
val Midnight = Color(0xFF0D0A07)
val DeepBlue = Color(0xFF1A2A3A)
val Charcoal = Color(0xFF1E1B18)

// Light theme colors
val md_theme_light_primary = GoldDark
val md_theme_light_onPrimary = Parchment
val md_theme_light_primaryContainer = Gold.copy(alpha = 0.3f)
val md_theme_light_onPrimaryContainer = Ink
val md_theme_light_secondary = InkLight
val md_theme_light_onSecondary = Parchment
val md_theme_light_background = Parchment
val md_theme_light_onBackground = Ink
val md_theme_light_surface = ParchmentDark
val md_theme_light_onSurface = Ink

// Dark theme colors (default for StoryTeller)
val md_theme_dark_primary = Gold
val md_theme_dark_onPrimary = Ink
val md_theme_dark_primaryContainer = Gold.copy(alpha = 0.2f)
val md_theme_dark_onPrimaryContainer = Gold
val md_theme_dark_secondary = ParchmentDark
val md_theme_dark_onSecondary = Ink
val md_theme_dark_background = Midnight
val md_theme_dark_onBackground = Parchment
val md_theme_dark_surface = Charcoal
val md_theme_dark_onSurface = Parchment
