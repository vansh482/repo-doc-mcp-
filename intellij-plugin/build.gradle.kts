plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.22"
    id("org.jetbrains.intellij") version "1.17.2"
}

group = "com.repodoc"
version = "0.1.0"

repositories {
    mavenCentral()
}

dependencies {
    // Kotlin standard library
    implementation("org.jetbrains.kotlin:kotlin-stdlib")

    // Coroutines for async MCP communication
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.8.0")

    // JSON parsing for MCP protocol
    implementation("com.google.code.gson:gson:2.10.1")

    // Markdown rendering in the doc viewer
    implementation("org.commonmark:commonmark:0.21.0")
    implementation("org.commonmark:commonmark-ext-gfm-tables:0.21.0")
}

// IntelliJ Platform configuration
// This tells Gradle which IntelliJ version to build against.
// The plugin will be compatible with this version and newer.
intellij {
    // Target IntelliJ IDEA Community Edition
    // Using 2024.1 as the base — compatible with all 2024+ JetBrains IDEs
    version.set("2024.1")
    type.set("IC") // IC = IntelliJ Community, IU = IntelliJ Ultimate

    // Plugins this plugin depends on (built-in IntelliJ plugins)
    plugins.set(listOf(
        "Git4Idea",       // Git integration — we need this for branch/diff detection
        "terminal",       // Terminal access for running the Python process
    ))
}

tasks {
    // Set the JVM compatibility versions
    withType<JavaCompile> {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }
    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions.jvmTarget = "17"
    }

    // Configure the plugin metadata shown in JetBrains Marketplace
    patchPluginXml {
        sinceBuild.set("241")    // IntelliJ 2024.1+
        untilBuild.set("251.*")  // Compatible up to 2025.1.x
        changeNotes.set("""
            <h3>0.1.0 — Initial Release</h3>
            <ul>
                <li>Generate technical and non-technical documentation for any repo</li>
                <li>Built-in documentation viewer with tabbed interface</li>
                <li>Per-MR documentation generation</li>
                <li>Auto-update support with git hooks and CI/CD integration</li>
                <li>Configurable LLM provider (Claude, GPT-4, Ollama)</li>
            </ul>
        """)
    }

    // Sign the plugin for JetBrains Marketplace publishing
    signPlugin {
        certificateChain.set(System.getenv("CERTIFICATE_CHAIN"))
        privateKey.set(System.getenv("PRIVATE_KEY"))
        password.set(System.getenv("PRIVATE_KEY_PASSWORD"))
    }

    publishPlugin {
        token.set(System.getenv("PUBLISH_TOKEN"))
    }
}
