# StoryTeller ProGuard Rules
# Keep JNI native methods
-keepclasseswithmembernames class com.storyteller.droid.engine.LlamaEngine {
    native <methods>;
}

# Keep Gson model classes
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.storyteller.droid.model.** { *; }
-keep class com.storyteller.droid.data.** { *; }

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
