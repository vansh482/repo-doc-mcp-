package com.repodoc.services

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity

/**
 * Startup Activity — initializes the branch watcher when a project opens.
 *
 * IntelliJ calls this after the project is fully loaded. We use it to:
 * 1. Start the branch detection polling
 * 2. Start the background main branch watcher (if enabled in settings)
 * 3. Initialize the status bar widget
 */
class RepoDocStartupActivity : ProjectActivity {

    override suspend fun execute(project: Project) {
        val watcherService = project.getService(BranchWatcherService::class.java)
        watcherService.start()
    }
}
