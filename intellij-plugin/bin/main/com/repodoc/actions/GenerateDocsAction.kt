package com.repodoc.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindowManager
import com.repodoc.services.RepoDocService
import com.repodoc.ui.DocViewerPanel

/**
 * Generate Documentation (Both) — the primary action.
 *
 * In IntelliJ, an Action is the fundamental unit of user interaction. Each action
 * has two methods:
 *   - update(): Called frequently to enable/disable the action based on context
 *   - actionPerformed(): Called when the user triggers the action
 *
 * This action generates BOTH technical and non-technical documentation.
 * It uses IntelliJ's background task system to run the generation without
 * freezing the UI, and shows a progress bar in the status bar.
 *
 * HOW IT CONNECTS TO THE MCP SERVER:
 *   User clicks action → actionPerformed()
 *     → RepoDocService.generateDocs()
 *       → MCPClient.callTool("generate_docs")
 *         → Python subprocess: python -m src.cli <path> --type both
 *           → Scanner + Analyzer + DocGenerator pipeline
 *             → Markdown files saved to disk
 *         ← stdout captured
 *       ← ToolResult returned
 *     ← DocResult with content from disk
 *   → DocViewerPanel displays the docs in a tool window
 */
class GenerateDocsAction : AnAction() {

    /**
     * Enable this action only when a project is open.
     * Called by IntelliJ whenever the UI needs to update action state.
     */
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    /**
     * Execute the documentation generation.
     * Called when the user triggers the action (menu click, keyboard shortcut, etc.)
     */
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        generateDocs(project, "both")
    }

    companion object {
        /**
         * Shared generation logic used by all doc generation actions.
         *
         * This runs the generation as a background task with a progress indicator,
         * then opens the doc viewer when complete. The progress indicator appears
         * in IntelliJ's status bar (bottom of the window) and can be cancelled.
         *
         * @param project The current IntelliJ project
         * @param type Which docs to generate: "both", "technical", or "non-technical"
         */
        fun generateDocs(project: Project, type: String) {
            val service = project.getService(RepoDocService::class.java)

            // IntelliJ's Task.Backgroundable runs on a worker thread and shows
            // a progress bar. The `canBeCancelled = true` parameter adds a cancel button.
            ProgressManager.getInstance().run(object : Task.Backgroundable(
                project,
                "Generating documentation...",
                true // canBeCancelled
            ) {
                override fun run(indicator: ProgressIndicator) {
                    indicator.isIndeterminate = true
                    indicator.text = "Scanning repository and generating docs..."

                    // Use a blocking latch since we're already on a background thread
                    val latch = java.util.concurrent.CountDownLatch(1)
                    var docResult: RepoDocService.DocResult? = null

                    service.generateDocs(type) { result ->
                        docResult = result
                        latch.countDown()
                    }

                    // Wait for completion (or cancellation)
                    while (!latch.await(1, java.util.concurrent.TimeUnit.SECONDS)) {
                        if (indicator.isCanceled) {
                            return
                        }
                    }

                    val result = docResult ?: return

                    // Back on EDT: update the UI
                    com.intellij.openapi.application.ApplicationManager.getApplication()
                        .invokeLater {
                            if (result.success) {
                                // Open the doc viewer tool window
                                DocViewerPanel.showDocs(
                                    project,
                                    result.technicalDoc,
                                    result.nonTechnicalDoc,
                                )

                                service.notify(
                                    "Documentation Generated",
                                    "Both technical and non-technical docs are ready.",
                                    NotificationType.INFORMATION,
                                )
                            } else {
                                service.notify(
                                    "Documentation Failed",
                                    result.message,
                                    NotificationType.ERROR,
                                )
                            }
                        }
                }
            })
        }
    }
}

/**
 * Generate Technical Documentation Only.
 * Triggers generation of just the engineer-focused documentation.
 */
class GenerateTechnicalDocAction : AnAction() {
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        GenerateDocsAction.generateDocs(project, "technical")
    }
}

/**
 * Generate Non-Technical Guide Only.
 * Triggers generation of just the stakeholder-friendly documentation.
 */
class GenerateNonTechnicalDocAction : AnAction() {
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        GenerateDocsAction.generateDocs(project, "non-technical")
    }
}

/**
 * Show Repository Summary — quick scan without LLM calls.
 * Shows file counts, languages, and structure in a dialog.
 */
class RepoSummaryAction : AnAction() {
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = project.getService(RepoDocService::class.java)

        ProgressManager.getInstance().run(object : Task.Backgroundable(
            project, "Scanning repository...", false
        ) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                val latch = java.util.concurrent.CountDownLatch(1)
                var toolResult: com.repodoc.mcp.MCPClient.ToolResult? = null

                service.getRepoSummary { result ->
                    toolResult = result
                    latch.countDown()
                }
                latch.await()

                val result = toolResult ?: return
                com.intellij.openapi.application.ApplicationManager.getApplication()
                    .invokeLater {
                        if (result.success) {
                            // Show summary in a message dialog
                            com.intellij.openapi.ui.Messages.showInfoMessage(
                                project,
                                result.output,
                                "Repository Summary"
                            )
                        } else {
                            service.notify("Scan Failed", result.error, NotificationType.ERROR)
                        }
                    }
            }
        })
    }
}

/**
 * Check for documentation updates based on recent commits.
 */
class CheckUpdateAction : AnAction() {
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = project.getService(RepoDocService::class.java)

        ProgressManager.getInstance().run(object : Task.Backgroundable(
            project, "Checking for documentation updates...", true
        ) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                val latch = java.util.concurrent.CountDownLatch(1)
                var toolResult: com.repodoc.mcp.MCPClient.ToolResult? = null

                service.checkAndUpdateDocs { result ->
                    toolResult = result
                    latch.countDown()
                }
                latch.await()

                val result = toolResult ?: return
                com.intellij.openapi.application.ApplicationManager.getApplication()
                    .invokeLater {
                        val type = if (result.success) NotificationType.INFORMATION
                                   else NotificationType.WARNING
                        service.notify("Doc Update Check", result.output, type)
                    }
            }
        })
    }
}

/**
 * View previously generated documentation.
 */
class ViewDocsAction : AnAction() {
    override fun update(e: AnActionEvent) {
        val project = e.project ?: return
        val service = project.getService(RepoDocService::class.java)
        e.presentation.isEnabledAndVisible = service.docsExist()
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = project.getService(RepoDocService::class.java)
        val (tech, simple, _) = service.readGeneratedDocs()

        if (tech.isNotEmpty() || simple.isNotEmpty()) {
            DocViewerPanel.showDocs(project, tech, simple)
        } else {
            service.notify(
                "No Documentation Found",
                "Generate documentation first using Repo Doc → Generate Documentation.",
                NotificationType.WARNING,
            )
        }
    }
}
