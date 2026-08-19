package com.repodoc.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.ui.dsl.builder.panel
import com.repodoc.services.RepoDocService
import com.repodoc.ui.DocViewerPanel
import javax.swing.JComponent

/**
 * Generate MR Documentation — prompts for branch details, then generates docs.
 *
 * This action shows a dialog where the user can enter:
 * - The source branch (the MR/PR branch)
 * - The target branch (usually main)
 * - Optional MR title and author
 *
 * After the user confirms, it runs the MR doc generation pipeline and
 * displays the results in the doc viewer.
 *
 * INTELLIJ DIALOG PATTERN:
 * IntelliJ uses the DialogWrapper class for modal dialogs. You override
 * createCenterPanel() to provide the dialog content, and the OK/Cancel
 * buttons are added automatically. When the user clicks OK, the dialog
 * closes and we read the input values.
 */
class GenerateMRDocsAction : AnAction() {

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        // Show the MR input dialog
        val dialog = MRInputDialog(project)
        if (!dialog.showAndGet()) {
            return // User cancelled
        }

        val sourceBranch = dialog.sourceBranch
        val targetBranch = dialog.targetBranch
        val mrTitle = dialog.mrTitle
        val author = dialog.author

        if (sourceBranch.isBlank()) {
            Messages.showErrorDialog(project, "Source branch is required.", "Error")
            return
        }

        // Run MR doc generation as a background task
        val service = project.getService(RepoDocService::class.java)

        ProgressManager.getInstance().run(object : Task.Backgroundable(
            project,
            "Generating MR documentation for $sourceBranch...",
            true
        ) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Analyzing merge request changes..."

                val latch = java.util.concurrent.CountDownLatch(1)
                var docResult: RepoDocService.DocResult? = null

                service.generateMRDocs(
                    sourceBranch = sourceBranch,
                    targetBranch = targetBranch,
                    mrTitle = mrTitle,
                    author = author,
                ) { result ->
                    docResult = result
                    latch.countDown()
                }

                while (!latch.await(1, java.util.concurrent.TimeUnit.SECONDS)) {
                    if (indicator.isCanceled) return
                }

                val result = docResult ?: return

                com.intellij.openapi.application.ApplicationManager.getApplication()
                    .invokeLater {
                        if (result.success) {
                            DocViewerPanel.showDocs(
                                project,
                                result.technicalDoc,
                                result.nonTechnicalDoc,
                            )
                            service.notify(
                                "MR Documentation Generated",
                                "Review and summary docs ready for: $sourceBranch",
                                NotificationType.INFORMATION,
                            )
                        } else {
                            service.notify(
                                "MR Documentation Failed",
                                result.message,
                                NotificationType.ERROR,
                            )
                        }
                    }
            }
        })
    }
}

/**
 * Dialog for collecting MR branch information from the user.
 *
 * IntelliJ's Kotlin UI DSL (com.intellij.ui.dsl.builder) is the modern way
 * to build dialog layouts. It provides a declarative API similar to Jetpack
 * Compose or SwiftUI. The panel {} builder creates a form layout with labels,
 * text fields, and other components arranged in rows.
 */
private class MRInputDialog(project: com.intellij.openapi.project.Project) :
    DialogWrapper(project, true) {

    var sourceBranch: String = ""
        private set
    var targetBranch: String = "main"
        private set
    var mrTitle: String = ""
        private set
    var author: String = ""
        private set

    // Text field references for reading values after OK is clicked
    private var sourceBranchField: javax.swing.JTextField = javax.swing.JTextField(30)
    private var targetBranchField: javax.swing.JTextField = javax.swing.JTextField(30).apply {
        text = "main"
    }
    private var mrTitleField: javax.swing.JTextField = javax.swing.JTextField(30)
    private var authorField: javax.swing.JTextField = javax.swing.JTextField(30)

    init {
        title = "Generate MR Documentation"
        setOKButtonText("Generate")
        init() // DialogWrapper requires this call to set up the dialog
    }

    override fun createCenterPanel(): JComponent {
        // Try to auto-detect the current git branch
        try {
            val gitBranch = Runtime.getRuntime().exec(
                arrayOf("git", "rev-parse", "--abbrev-ref", "HEAD"),
                null,
                java.io.File(project?.basePath ?: "."),
            )
            val branch = gitBranch.inputStream.bufferedReader().readText().trim()
            if (branch.isNotEmpty() && branch != "main" && branch != "master") {
                sourceBranchField.text = branch
            }
        } catch (_: Exception) {
            // Git detection is best-effort
        }

        return panel {
            row("Source Branch:") {
                cell(sourceBranchField)
                    .comment("The MR/PR branch (e.g., feature/add-oauth)")
            }
            row("Target Branch:") {
                cell(targetBranchField)
                    .comment("Branch being merged into (usually main)")
            }
            separator()
            row("MR Title:") {
                cell(mrTitleField)
                    .comment("Optional — auto-generated from branch name if empty")
            }
            row("Author:") {
                cell(authorField)
                    .comment("Optional")
            }
        }
    }

    /**
     * Called when the user clicks OK. Read the field values before the dialog closes.
     */
    override fun doOKAction() {
        sourceBranch = sourceBranchField.text.trim()
        targetBranch = targetBranchField.text.trim().ifEmpty { "main" }
        mrTitle = mrTitleField.text.trim()
        author = authorField.text.trim()
        super.doOKAction()
    }
}
