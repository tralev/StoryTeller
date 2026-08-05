plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}

// Android source directories stay source-only; all build products go to tmp/.
layout.buildDirectory.set(rootProject.file("../tmp/droid-build/root"))
subprojects {
    layout.buildDirectory.set(rootProject.file("../tmp/droid-build/${project.name}"))
}
