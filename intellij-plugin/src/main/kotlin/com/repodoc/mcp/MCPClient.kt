package com.repodoc.mcp

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.repodoc.services.RepoDocSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * MCP Client for IntelliJ — communicates with the repo-doc-mcp Python server.
 *
 * This is the Kotlin equivalent of the VS Code extension's mcpClient.ts.
 * It spawns the Python MCP CLI as a subprocess, captures its output, and
 * returns structured results.
 *
 * DESIGN DECISION: CLI mode vs persistent server
 * Like the VS Code extension, we use CLI mode (spawn a new process per call)
 * rather than maintaining a persistent server connection. The reasons are:
 *   1. Simpler lifecycle management (no server process to keep alive)
 *   2. Easier debugging (each call is independent)
 *   3. More reliable across platforms (no socket/pipe management)
 *   4. The LLM API call dominates total time anyway (10-60s vs 1-2s startup)
 *
 * All methods are `suspend` functions because they perform I/O (subprocess
 * execution). They should be called from a coroutine scope, which IntelliJ
 * provides through its `coroutineScope` extension on `Project`.
 */
class MCPClient(private val project: Project) {

    private val log = Logger.getInstance(MCPClient::class.java)
    private val gson = Gson()

    /**
     * Result of an MCP tool call.
     * Success contains the stdout output; failure contains the error message.
     */
    data class ToolResult(
        val success: Boolean,
        val output: String,
        val error: String = "",
    )

    /**
     * Call an MCP tool by executing the Python CLI as a subprocess.
     *
     * This maps tool names to CLI arguments (same mapping as the VS Code extension):
     *   generate_docs         → python -m src.cli <path> --type both
     *   generate_technical_doc→ python -m src.cli <path> --type technical
     *   generate_non_technical_doc → python -m src.cli <path> --type non-technical
     *   get_repo_summary      → python -m src.cli <path> --summary-only
     *   generate_mr_docs      → python -m src.mr_docs.cli <branch>
     *   check_and_update_docs → python -m src.watcher.cli check
     *
     * @param toolName The MCP tool name (e.g., "generate_docs")
     * @param args Tool arguments as key-value pairs
     * @return ToolResult with success status and output/error content
     */
    suspend fun callTool(
        toolName: String,
        args: Map<String, String> = emptyMap(),
    ): ToolResult = withContext(Dispatchers.IO) {
        val settings = project.getService(RepoDocSettings::class.java).state
        val cliArgs = buildCliArgs(toolName, args, settings)

        log.info("MCP call: $toolName with args: $args")
        log.info("Command: ${settings.pythonPath} ${cliArgs.joinToString(" ")}")

        try {
            // Build the process with the right environment variables
            val processBuilder = ProcessBuilder(
                listOf(settings.pythonPath) + cliArgs
            ).apply {
                directory(File(settings.mcpServerPath.ifEmpty { "." }))
                redirectErrorStream(false)

                // Set LLM API key as environment variable
                val env = environment()
                if (settings.llmApiKey.isNotEmpty()) {
                    when (settings.llmProvider) {
                        "anthropic" -> env["ANTHROPIC_API_KEY"] = settings.llmApiKey
                        "openai" -> env["OPENAI_API_KEY"] = settings.llmApiKey
                    }
                }
            }

            val process = processBuilder.start()

            // Read stdout and stderr concurrently
            val stdout = process.inputStream.bufferedReader().readText()
            val stderr = process.errorStream.bufferedReader().readText()

            // Wait for completion with a generous timeout (LLM calls can be slow)
            val completed = process.waitFor(5, TimeUnit.MINUTES)

            if (!completed) {
                process.destroyForcibly()
                return@withContext ToolResult(
                    success = false,
                    output = stdout,
                    error = "Process timed out after 5 minutes",
                )
            }

            val exitCode = process.exitValue()

            if (exitCode == 0) {
                log.info("MCP call succeeded: ${stdout.take(200)}...")
                ToolResult(success = true, output = stdout.trim())
            } else {
                log.warn("MCP call failed (exit $exitCode): $stderr")
                ToolResult(
                    success = false,
                    output = stdout.trim(),
                    error = stderr.trim().ifEmpty { "Process exited with code $exitCode" },
                )
            }
        } catch (e: Exception) {
            log.error("MCP process error", e)
            ToolResult(
                success = false,
                output = "",
                error = "Failed to start MCP server: ${e.message}",
            )
        }
    }

    /**
     * Health check — verify the Python MCP server is properly installed.
     *
     * Checks that:
     * 1. The Python interpreter exists and runs
     * 2. The MCP server module is importable
     *
     * Returns a pair of (isHealthy, message).
     */
    suspend fun healthCheck(): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        val settings = project.getService(RepoDocSettings::class.java).state

        try {
            // Check Python availability
            val pythonCheck = ProcessBuilder(settings.pythonPath, "--version")
                .redirectErrorStream(true)
                .start()
            pythonCheck.waitFor(5, TimeUnit.SECONDS)
            if (pythonCheck.exitValue() != 0) {
                return@withContext Pair(
                    false,
                    "Python not found at '${settings.pythonPath}'. " +
                    "Install Python 3.10+ or update the Python path in settings."
                )
            }

            // Check MCP server is importable
            val serverDir = settings.mcpServerPath.ifEmpty { "." }
            val importCheck = ProcessBuilder(
                settings.pythonPath, "-c",
                "from src.config.settings import ServerConfig; print('OK')"
            ).apply {
                directory(File(serverDir))
                redirectErrorStream(true)
            }.start()
            importCheck.waitFor(10, TimeUnit.SECONDS)

            if (importCheck.exitValue() != 0) {
                val error = importCheck.inputStream.bufferedReader().readText()
                return@withContext Pair(
                    false,
                    "MCP server not installed at '$serverDir'. " +
                    "Run 'pip install -e .' in the server directory.\n\nError: $error"
                )
            }

            Pair(true, "MCP server is ready")
        } catch (e: Exception) {
            Pair(false, "Health check failed: ${e.message}")
        }
    }

    /**
     * Build CLI arguments based on the tool being called.
     *
     * This maps MCP tool names to the appropriate Python CLI module and flags.
     */
    private fun buildCliArgs(
        toolName: String,
        args: Map<String, String>,
        settings: RepoDocSettings.SettingsState,
    ): List<String> {
        val repoPath = args["repo_path"]
            ?: project.basePath
            ?: "."

        // Build common arguments from settings
        val settingsArgs = mutableListOf<String>()
        if (settings.llmProvider.isNotEmpty()) {
            settingsArgs.addAll(listOf("--provider", settings.llmProvider))
        }
        if (settings.llmModel.isNotEmpty()) {
            settingsArgs.addAll(listOf("--model", settings.llmModel))
        }
        if (settings.llmApiKey.isNotEmpty()) {
            settingsArgs.addAll(listOf("--api-key", settings.llmApiKey))
        }
        if (settings.outputDirectory.isNotEmpty()) {
            settingsArgs.addAll(listOf("--output", settings.outputDirectory))
        }

        return when (toolName) {
            // Phase 1: Doc generation tools
            "generate_docs" ->
                listOf("-m", "src.cli", repoPath) + settingsArgs + listOf("--type", "both")
            "generate_technical_doc" ->
                listOf("-m", "src.cli", repoPath) + settingsArgs + listOf("--type", "technical")
            "generate_non_technical_doc" ->
                listOf("-m", "src.cli", repoPath) + settingsArgs + listOf("--type", "non-technical")
            "get_repo_summary" ->
                listOf("-m", "src.cli", repoPath) + settingsArgs + listOf("--summary-only")

            // Phase 3: Auto-update tools
            "check_and_update_docs" ->
                listOf("-m", "src.watcher.cli", "check", "--repo-path", repoPath) + settingsArgs

            // Branch documentation tools
            "generate_branch_docs" -> {
                val branch = args["branch"] ?: ""
                val branchArgs = mutableListOf("-m", "src.watcher.cli", "branch-docs", branch)
                branchArgs.addAll(listOf("--repo-path", repoPath))
                args["base_branch"]?.let { branchArgs.addAll(listOf("--base", it)) }
                branchArgs + settingsArgs
            }

            // Phase 4: MR documentation tools
            "generate_mr_docs" -> {
                val branch = args["source_branch"] ?: ""
                val target = args["target_branch"] ?: "main"
                val mrArgs = mutableListOf("-m", "src.mr_docs.cli", branch, "--target", target)
                mrArgs.addAll(listOf("--repo-path", repoPath))
                args["mr_title"]?.let { mrArgs.addAll(listOf("--title", it)) }
                args["author"]?.let { mrArgs.addAll(listOf("--author", it)) }
                mrArgs + settingsArgs
            }

            else ->
                listOf("-m", "src.cli", repoPath) + settingsArgs
        }
    }
}
