package com.repodoc.services

import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.StatusBar
import com.intellij.openapi.wm.StatusBarWidget
import com.intellij.openapi.wm.StatusBarWidgetFactory
import com.intellij.openapi.wm.WindowManager
import com.intellij.util.Consumer
import com.repodoc.mcp.MCPClient
import kotlinx.coroutines.*
import java.awt.event.MouseEvent
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Branch Watcher Service — detects branch switches and runs background doc updates.
 *
 * This service:
 * 1. Detects the current git branch via `git rev-parse --abbrev-ref HEAD`
 * 2. Polls for branch changes (git doesn't have a native event for this)
 * 3. Auto-generates branch docs when switching branches (if enabled)
 * 4. Runs periodic main branch doc checks (if watcher is enabled)
 * 5. Updates the status bar widget with doc freshness
 */
@Service(Service.Level.PROJECT)
class BranchWatcherService(private val project: Project) : Disposable {

    private val log = Logger.getInstance(BranchWatcherService::class.java)
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private val mcpClient = MCPClient(project)

    var currentBranch: String = ""
        private set
    var docStatus: DocStatus = DocStatus.IDLE
        private set

    private var branchPollJob: Job? = null
    private var watcherJob: Job? = null

    enum class DocStatus { IDLE, UPDATING, UP_TO_DATE, ERROR }

    /**
     * Start watching for branch changes and (optionally) main branch updates.
     * Called from the startup activity or when settings change.
     */
    fun start() {
        val basePath = project.basePath ?: return

        // Detect initial branch
        currentBranch = detectBranch(basePath)
        log.info("Initial branch: $currentBranch")

        // Start branch polling (every 2 seconds, lightweight)
        branchPollJob = scope.launch {
            while (isActive) {
                delay(2000)
                val newBranch = detectBranch(basePath)
                if (newBranch.isNotEmpty() && newBranch != currentBranch) {
                    val previous = currentBranch
                    currentBranch = newBranch
                    log.info("Branch switched: $previous -> $currentBranch")
                    updateStatusBar()
                    onBranchSwitch(previous, currentBranch)
                }
            }
        }

        // Start main branch watcher if enabled
        val settings = project.getService(RepoDocSettings::class.java).state
        if (settings.watcherEnabled) {
            startMainBranchWatcher(basePath, settings.watcherIntervalMinutes)
        }

        updateStatusBar()
    }

    fun stop() {
        branchPollJob?.cancel()
        watcherJob?.cancel()
    }

    private fun startMainBranchWatcher(repoPath: String, intervalMinutes: Int) {
        watcherJob = scope.launch {
            // Initial delay to let IDE finish loading
            delay(30_000)

            while (isActive) {
                try {
                    docStatus = DocStatus.UPDATING
                    updateStatusBar()

                    val result = mcpClient.callTool("check_and_update_docs", mapOf(
                        "repo_path" to repoPath,
                    ))

                    if (result.success && !result.output.contains("No new commits")) {
                        docStatus = DocStatus.UP_TO_DATE
                        val service = project.getService(RepoDocService::class.java)
                        service.notify(
                            "Docs Updated",
                            "Main branch documentation has been updated.",
                            NotificationType.INFORMATION,
                        )
                    } else {
                        docStatus = DocStatus.IDLE
                    }
                } catch (e: Exception) {
                    log.warn("Watcher check failed", e)
                    docStatus = DocStatus.IDLE
                }
                updateStatusBar()
                delay(intervalMinutes * 60_000L)
            }
        }
    }

    private fun onBranchSwitch(previousBranch: String, newBranch: String) {
        val settings = project.getService(RepoDocSettings::class.java).state
        if (!settings.autoGenerateBranchDocs) return

        val basePath = project.basePath ?: return

        scope.launch {
            // Debounce — wait 3 seconds for git operations to settle
            delay(3000)
            if (currentBranch != newBranch) return@launch // Branch changed again

            try {
                docStatus = DocStatus.UPDATING
                updateStatusBar()

                val result = mcpClient.callTool("generate_branch_docs", mapOf(
                    "repo_path" to basePath,
                    "branch" to newBranch,
                ))

                if (result.success) {
                    docStatus = DocStatus.UP_TO_DATE
                    val service = project.getService(RepoDocService::class.java)
                    service.notify(
                        "Branch Docs Generated",
                        "Documentation generated for branch: $newBranch",
                        NotificationType.INFORMATION,
                    )
                } else {
                    docStatus = DocStatus.ERROR
                    log.warn("Branch docs failed: ${result.error}")
                }
            } catch (e: Exception) {
                docStatus = DocStatus.ERROR
                log.warn("Branch docs error", e)
            }
            updateStatusBar()
        }
    }

    private fun detectBranch(repoPath: String): String {
        return try {
            val process = ProcessBuilder("git", "rev-parse", "--abbrev-ref", "HEAD")
                .directory(File(repoPath))
                .redirectErrorStream(true)
                .start()
            val output = process.inputStream.bufferedReader().readText().trim()
            process.waitFor(5, TimeUnit.SECONDS)
            if (process.exitValue() == 0) output else ""
        } catch (e: Exception) {
            ""
        }
    }

    private fun updateStatusBar() {
        val statusBar = WindowManager.getInstance().getStatusBar(project) ?: return
        statusBar.updateWidget(RepoDocStatusWidgetFactory.WIDGET_ID)
    }

    override fun dispose() {
        stop()
        scope.cancel()
    }
}

/**
 * Status bar widget factory — creates the "Docs [branch]" status bar widget.
 */
class RepoDocStatusWidgetFactory : StatusBarWidgetFactory {

    companion object {
        const val WIDGET_ID = "RepoDocStatus"
    }

    override fun getId(): String = WIDGET_ID
    override fun getDisplayName(): String = "Repo Doc Status"
    override fun isAvailable(project: Project): Boolean = true

    override fun createWidget(project: Project): StatusBarWidget {
        return RepoDocStatusWidget(project)
    }
}

/**
 * The actual status bar widget that shows doc status and current branch.
 */
class RepoDocStatusWidget(private val project: Project) : StatusBarWidget, StatusBarWidget.TextPresentation {

    override fun ID(): String = RepoDocStatusWidgetFactory.WIDGET_ID

    override fun getPresentation(): StatusBarWidget.WidgetPresentation = this

    override fun getText(): String {
        val service = project.getService(BranchWatcherService::class.java)
        val branch = service.currentBranch
        val branchLabel = if (branch.isNotEmpty()) " [$branch]" else ""

        return when (service.docStatus) {
            BranchWatcherService.DocStatus.IDLE -> "Docs$branchLabel"
            BranchWatcherService.DocStatus.UPDATING -> "Docs: updating...$branchLabel"
            BranchWatcherService.DocStatus.UP_TO_DATE -> "Docs: updated$branchLabel"
            BranchWatcherService.DocStatus.ERROR -> "Docs: error$branchLabel"
        }
    }

    override fun getTooltipText(): String = "Repo Doc Generator - click to view docs"

    override fun getAlignment(): Float = 0f

    override fun getClickConsumer(): Consumer<MouseEvent>? {
        return Consumer {
            com.intellij.openapi.actionSystem.ActionManager.getInstance()
                .getAction("RepoDoc.ViewDocs")
                ?.let { action ->
                    com.intellij.openapi.actionSystem.ActionManager.getInstance()
                        .tryToExecute(action, it, null, null, true)
                }
        }
    }

    override fun install(statusBar: StatusBar) {}
    override fun dispose() {}
}
