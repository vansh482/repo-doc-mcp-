package com.repodoc.services

import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

/**
 * Persistent settings for the Repo Doc Generator plugin.
 *
 * IntelliJ persists this as XML in .idea/repoDocGenerator.xml.
 * The SettingsState data class holds all configurable values.
 * The RepoDocSettingsConfigurable UI reads/writes to this service.
 */
@Service(Service.Level.PROJECT)
@State(
    name = "RepoDocSettings",
    storages = [Storage("repoDocGenerator.xml")],
)
class RepoDocSettings : PersistentStateComponent<RepoDocSettings.SettingsState> {

    private var myState = SettingsState()

    data class SettingsState(
        var mcpServerPath: String = "",
        var pythonPath: String = "python3",
        var llmProvider: String = "anthropic",
        var llmModel: String = "claude-sonnet-4-20250514",
        var llmApiKey: String = "",
        var outputDirectory: String = "./docs/generated",
        var autoOpenViewer: Boolean = true,
        var includeArchitectureDiagram: Boolean = true,
        var watcherEnabled: Boolean = false,
        var watcherIntervalMinutes: Int = 5,
        var autoGenerateBranchDocs: Boolean = false,
    )

    override fun getState(): SettingsState = myState

    override fun loadState(state: SettingsState) {
        myState = state
    }
}
