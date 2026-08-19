package com.repodoc.services

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.repodoc.mcp.MCPClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Project-level service — the central coordinator for all doc generation operations.
 *
 * In IntelliJ's architecture, Services are long-lived singletons scoped to either
 * the application (IDE-wide) or a project (per-project window). This is a PROJECT
 * service, meaning each open project gets its own instance. This is important because
 * each project has its own repository, settings, and generated docs.
 *
 * WHAT THIS SERVICE DOES:
 * Think of it as the "controller" in MVC. The Actions (user clicks "Generate Docs")
 * call into this service, which coordinates the MCP client, progress reporting,
 * file reading, and UI updates. The service also caches state like "are docs already
 * generated?" and "when were they last updated?"
 *
 * HOW ACTIONS USE THIS SERVICE:
 *   val service = project.getService(RepoDocService::class.java)
 *   service.generateDocs(type = "both") { result ->
 *       // result is the MCP tool output
 *   }
 */
@Service(Service.Level.PROJECT)
class RepoDocService(private val project: Project) {

    private val log = Logger.getInstance(RepoDocService::class.java)
    private val mcpClient = MCPClient(project)
    private val scope = CoroutineScope(Dispatchers.Default)

    /**
     * Result of a documentation generation operation.
     * Contains the generated content and metadata about the operation.
     */
    data class DocResult(
        val success: Boolean,
        val technicalDoc: String = "",
        val nonTechnicalDoc: String = "",
        val message: String = "",
        val outputDir: String = "",
    )

    /**
     * Generate documentation for the current project.
     *
     * This is the main entry point that Actions call. It runs the full pipeline:
     * 1. Health check on the MCP server
     * 2. Call the appropriate MCP tool via the Python CLI
     * 3. Read the generated Markdown files from disk
     * 4. Return the content for display in the doc viewer
     *
     * @param type Which docs to generate: "both", "technical", or "non-technical"
     * @param onComplete Callback with the result (called on EDT for UI safety)
     */
    fun generateDocs(
        type: String = "both",
        onComplete: (DocResult) -> Unit,
    ) {
        scope.launch {
            try {
                // Step 1: Health check
                val (healthy, message) = mcpClient.healthCheck()
                if (!healthy) {
                    onComplete(DocResult(success = false, message = message))
                    return@launch
                }

                // Step 2: Determine the tool name
                val toolName = when (type) {
                    "technical" -> "generate_technical_doc"
                    "non-technical" -> "generate_non_technical_doc"
                    else -> "generate_docs"
                }

                // Step 3: Call the MCP server
                val result = mcpClient.callTool(toolName)

                if (!result.success) {
                    onComplete(DocResult(
                        success = false,
                        message = result.error.ifEmpty { "Generation failed" },
                    ))
                    return@launch
                }

                // Step 4: Read generated files from disk
                val (techContent, simpleContent, outputDir) = readGeneratedDocs()

                onComplete(DocResult(
                    success = true,
                    technicalDoc = techContent,
                    nonTechnicalDoc = simpleContent,
                    message = result.output,
                    outputDir = outputDir,
                ))

            } catch (e: Exception) {
                log.error("Doc generation failed", e)
                onComplete(DocResult(
                    success = false,
                    message = "Error: ${e.message}",
                ))
            }
        }
    }

    /**
     * Generate MR-specific documentation.
     *
     * @param sourceBranch The MR source branch (e.g., "feature/add-oauth")
     * @param targetBranch The target branch (default: "main")
     * @param mrTitle Optional MR title
     * @param author Optional MR author
     * @param onComplete Callback with the result
     */
    fun generateMRDocs(
        sourceBranch: String,
        targetBranch: String = "main",
        mrTitle: String = "",
        author: String = "",
        onComplete: (DocResult) -> Unit,
    ) {
        scope.launch {
            try {
                val (healthy, message) = mcpClient.healthCheck()
                if (!healthy) {
                    onComplete(DocResult(success = false, message = message))
                    return@launch
                }

                val args = mutableMapOf(
                    "source_branch" to sourceBranch,
                    "target_branch" to targetBranch,
                )
                if (mrTitle.isNotEmpty()) args["mr_title"] = mrTitle
                if (author.isNotEmpty()) args["author"] = author

                val result = mcpClient.callTool("generate_mr_docs", args)

                if (!result.success) {
                    onComplete(DocResult(
                        success = false,
                        message = result.error.ifEmpty { "MR doc generation failed" },
                    ))
                    return@launch
                }

                // Read MR-specific docs
                val (techContent, simpleContent, outputDir) = readMRDocs(sourceBranch)

                onComplete(DocResult(
                    success = true,
                    technicalDoc = techContent,
                    nonTechnicalDoc = simpleContent,
                    message = result.output,
                    outputDir = outputDir,
                ))

            } catch (e: Exception) {
                log.error("MR doc generation failed", e)
                onComplete(DocResult(success = false, message = "Error: ${e.message}"))
            }
        }
    }

    /**
     * Get a quick repository summary (no LLM calls needed).
     */
    fun getRepoSummary(onComplete: (MCPClient.ToolResult) -> Unit) {
        scope.launch {
            val result = mcpClient.callTool("get_repo_summary")
            onComplete(result)
        }
    }

    /**
     * Check for documentation updates and apply them incrementally.
     */
    fun checkAndUpdateDocs(onComplete: (MCPClient.ToolResult) -> Unit) {
        scope.launch {
            val result = mcpClient.callTool("check_and_update_docs")
            onComplete(result)
        }
    }

    /**
     * Check if generated docs already exist for the current project.
     */
    fun docsExist(): Boolean {
        val settings = project.getService(RepoDocSettings::class.java).state
        val basePath = project.basePath ?: return false
        val outputDir = resolveOutputDir(basePath, settings.outputDirectory)
        return File(outputDir, "TECHNICAL_DOC.md").exists()
    }

    /**
     * Read previously generated documentation from disk.
     * Returns a triple of (technicalContent, nonTechnicalContent, outputDirPath).
     */
    fun readGeneratedDocs(): Triple<String, String, String> {
        val settings = project.getService(RepoDocSettings::class.java).state
        val basePath = project.basePath ?: return Triple("", "", "")
        val outputDir = resolveOutputDir(basePath, settings.outputDirectory)

        val techPath = File(outputDir, "TECHNICAL_DOC.md")
        val simplePath = File(outputDir, "NON_TECHNICAL_GUIDE.md")

        val tech = if (techPath.exists()) techPath.readText(Charsets.UTF_8) else ""
        val simple = if (simplePath.exists()) simplePath.readText(Charsets.UTF_8) else ""

        return Triple(tech, simple, outputDir)
    }

    /**
     * Read MR-specific documentation from disk.
     */
    private fun readMRDocs(branchName: String): Triple<String, String, String> {
        val settings = project.getService(RepoDocSettings::class.java).state
        val basePath = project.basePath ?: return Triple("", "", "")
        val outputDir = resolveOutputDir(basePath, settings.outputDirectory) + "/mr_docs"

        // MR docs use branch-based filenames
        val safeName = branchName.replace("/", "_").replace(Regex("[^\\w\\-.]"), "_")

        val techPath = File(outputDir, "MR_REVIEW_$safeName.md")
        val simplePath = File(outputDir, "MR_SUMMARY_$safeName.md")

        val tech = if (techPath.exists()) techPath.readText(Charsets.UTF_8) else ""
        val simple = if (simplePath.exists()) simplePath.readText(Charsets.UTF_8) else ""

        return Triple(tech, simple, outputDir)
    }

    /**
     * Show a notification balloon in the IDE.
     */
    fun notify(title: String, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("Repo Doc Notifications")
            .createNotification(title, content, type)
            .notify(project)
    }

    private fun resolveOutputDir(basePath: String, outputDir: String): String {
        return if (Paths.get(outputDir).isAbsolute) {
            outputDir
        } else {
            Paths.get(basePath, outputDir).toString()
        }
    }
}
