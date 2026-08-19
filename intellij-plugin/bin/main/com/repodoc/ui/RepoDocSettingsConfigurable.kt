package com.repodoc.ui

import com.intellij.openapi.options.Configurable
import com.intellij.openapi.project.Project
import com.intellij.ui.dsl.builder.*
import com.repodoc.services.RepoDocSettings
import javax.swing.JComponent

/**
 * Settings / Preferences Page — configures the plugin within IntelliJ's Settings dialog.
 *
 * IntelliJ's settings system uses the [Configurable] interface. When the user opens
 * Settings → Tools → Repo Doc Generator, IntelliJ calls:
 *   1. createComponent() — to build the settings UI
 *   2. isModified() — to check if the Apply button should be enabled
 *   3. apply() — to save changes when the user clicks Apply or OK
 *   4. reset() — to revert to saved values when the user clicks Reset
 *
 * The UI is built using IntelliJ's Kotlin UI DSL (com.intellij.ui.dsl.builder),
 * which is a declarative layout system similar to Jetpack Compose. Each row()
 * creates a form row with a label and an input component.
 *
 * MAPPING TO VS CODE SETTINGS:
 *   VS Code: Settings JSON in .vscode/settings.json
 *   IntelliJ: XML file in .idea/repoDocGenerator.xml (handled automatically)
 *
 * Both approaches persist settings per-project and expose them through a UI.
 */
class RepoDocSettingsConfigurable(private val project: Project) : Configurable {

    // Temporary copies of settings — only written to the actual settings when apply() is called
    private var mcpServerPath = ""
    private var pythonPath = ""
    private var llmProvider = ""
    private var llmModel = ""
    private var llmApiKey = ""
    private var outputDirectory = ""
    private var autoOpenViewer = true
    private var includeArchitectureDiagram = true
    private var watcherEnabled = false
    private var watcherIntervalMinutes = 5
    private var autoGenerateBranchDocs = false

    override fun getDisplayName(): String = "Repo Doc Generator"

    /**
     * Build the settings UI using IntelliJ's Kotlin UI DSL.
     *
     * The panel {} builder creates a form layout. Each row() creates a labeled
     * form row. The various cell types (textField, comboBox, checkBox) provide
     * the input components. The .bindText() and .bindItem() calls create
     * two-way bindings between the UI components and our temporary variables.
     */
    override fun createComponent(): JComponent {
        loadCurrentSettings()

        return panel {
            // ── MCP Server Section ──
            group("MCP Server") {
                row("Server Path:") {
                    textField()
                        .bindText(::mcpServerPath)
                        .columns(COLUMNS_LARGE)
                        .comment("Path to the repo-doc-mcp directory (where you ran 'pip install -e .')")
                }
                row("Python Path:") {
                    textField()
                        .bindText(::pythonPath)
                        .columns(COLUMNS_MEDIUM)
                        .comment("Python interpreter (e.g., python3, /usr/bin/python3.12)")
                }
            }

            // ── LLM Configuration Section ──
            group("LLM Configuration") {
                row("Provider:") {
                    comboBox(listOf("anthropic", "openai", "ollama"))
                        .bindItem(::llmProvider.toNullableProperty())
                        .comment("Claude (Anthropic), GPT-4 (OpenAI), or local models (Ollama)")
                }
                row("Model:") {
                    textField()
                        .bindText(::llmModel)
                        .columns(COLUMNS_MEDIUM)
                        .comment("e.g., claude-sonnet-4-20250514, gpt-4o, llama3.1")
                }
                row("API Key:") {
                    passwordField()
                        .bindText(::llmApiKey)
                        .columns(COLUMNS_MEDIUM)
                        .comment("Leave empty to use ANTHROPIC_API_KEY or OPENAI_API_KEY env vars")
                }
            }

            // ── Output Settings Section ──
            group("Output") {
                row("Output Directory:") {
                    textField()
                        .bindText(::outputDirectory)
                        .columns(COLUMNS_MEDIUM)
                        .comment("Where generated docs are saved (relative to project root)")
                }
                row {
                    checkBox("Auto-open documentation viewer after generation")
                        .bindSelected(::autoOpenViewer)
                }
                row {
                    checkBox("Include Mermaid architecture diagram in technical docs")
                        .bindSelected(::includeArchitectureDiagram)
                }
            }

            // ── Auto-Update Section ──
            group("Auto-Update & Branch Docs") {
                row {
                    checkBox("Enable background watcher (auto-update main branch docs)")
                        .bindSelected(::watcherEnabled)
                        .comment("Periodically checks if main branch docs need updating")
                }
                row("Check interval (minutes):") {
                    spinner(1..60, 1)
                        .bindIntValue(::watcherIntervalMinutes)
                }
                row {
                    checkBox("Auto-generate branch docs on branch switch")
                        .bindSelected(::autoGenerateBranchDocs)
                        .comment("Generates separate docs with diff vs main when you switch branches")
                }
            }
        }
    }

    /**
     * Check if any settings have been modified since the last save.
     * IntelliJ uses this to enable/disable the Apply button.
     */
    override fun isModified(): Boolean {
        val settings = project.getService(RepoDocSettings::class.java).state
        return mcpServerPath != settings.mcpServerPath ||
               pythonPath != settings.pythonPath ||
               llmProvider != settings.llmProvider ||
               llmModel != settings.llmModel ||
               llmApiKey != settings.llmApiKey ||
               outputDirectory != settings.outputDirectory ||
               autoOpenViewer != settings.autoOpenViewer ||
               includeArchitectureDiagram != settings.includeArchitectureDiagram ||
               watcherEnabled != settings.watcherEnabled ||
               watcherIntervalMinutes != settings.watcherIntervalMinutes ||
               autoGenerateBranchDocs != settings.autoGenerateBranchDocs
    }

    /**
     * Save the current UI values to the persistent settings.
     * Called when the user clicks Apply or OK.
     */
    override fun apply() {
        val settings = project.getService(RepoDocSettings::class.java)
        settings.loadState(RepoDocSettings.SettingsState(
            mcpServerPath = mcpServerPath,
            pythonPath = pythonPath,
            llmProvider = llmProvider,
            llmModel = llmModel,
            llmApiKey = llmApiKey,
            outputDirectory = outputDirectory,
            autoOpenViewer = autoOpenViewer,
            includeArchitectureDiagram = includeArchitectureDiagram,
            watcherEnabled = watcherEnabled,
            watcherIntervalMinutes = watcherIntervalMinutes,
            autoGenerateBranchDocs = autoGenerateBranchDocs,
        ))
    }

    /**
     * Revert UI values to the currently saved settings.
     * Called when the settings dialog opens or the user clicks Reset.
     */
    override fun reset() {
        loadCurrentSettings()
    }

    private fun loadCurrentSettings() {
        val settings = project.getService(RepoDocSettings::class.java).state
        mcpServerPath = settings.mcpServerPath
        pythonPath = settings.pythonPath
        llmProvider = settings.llmProvider
        llmModel = settings.llmModel
        llmApiKey = settings.llmApiKey
        outputDirectory = settings.outputDirectory
        autoOpenViewer = settings.autoOpenViewer
        includeArchitectureDiagram = settings.includeArchitectureDiagram
        watcherEnabled = settings.watcherEnabled
        watcherIntervalMinutes = settings.watcherIntervalMinutes
        autoGenerateBranchDocs = settings.autoGenerateBranchDocs
    }
}
