package com.repodoc.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.JBUI
import com.repodoc.services.RepoDocService
import java.awt.BorderLayout
import javax.swing.*

class DocToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val service = project.getService(RepoDocService::class.java)
        val panel = createInitialPanel(project, service)
        val content = ContentFactory.getInstance().createContent(panel, "Documentation", false)
        toolWindow.contentManager.addContent(content)

        if (service.docsExist()) {
            val docs = service.readGeneratedDocs()
            if (docs != null) {
                DocViewerPanel.showDocs(project, docs.first, docs.second)
            }
        }
    }

    private fun createInitialPanel(project: Project, service: RepoDocService): JPanel {
        val panel = JPanel(BorderLayout())
        panel.border = JBUI.Borders.empty(16)

        val header = JBLabel("Repo Doc Generator").apply {
            font = font.deriveFont(16f)
            border = JBUI.Borders.emptyBottom(12)
        }
        panel.add(header, BorderLayout.NORTH)

        val buttonsPanel = JPanel().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
            border = JBUI.Borders.emptyTop(8)
        }

        val generateBtn = JButton("Generate Documentation").apply {
            addActionListener {
                service.generateDocs()
            }
        }
        buttonsPanel.add(generateBtn)
        buttonsPanel.add(Box.createVerticalStrut(8))

        val summaryBtn = JButton("View Repo Summary").apply {
            addActionListener {
                service.getRepoSummary()
            }
        }
        buttonsPanel.add(summaryBtn)
        buttonsPanel.add(Box.createVerticalStrut(8))

        val checkBtn = JButton("Check & Update Docs").apply {
            addActionListener {
                service.checkAndUpdateDocs()
            }
        }
        buttonsPanel.add(checkBtn)

        if (service.docsExist()) {
            buttonsPanel.add(Box.createVerticalStrut(16))
            val statusLabel = JBLabel("✓ Documentation exists").apply {
                foreground = JBUI.CurrentTheme.Link.Foreground.ENABLED
            }
            buttonsPanel.add(statusLabel)
        }

        panel.add(buttonsPanel, BorderLayout.CENTER)

        val footer = JBLabel("Use Actions menu for MR docs & branch docs").apply {
            font = font.deriveFont(11f)
            foreground = JBUI.CurrentTheme.Label.disabledForeground()
            border = JBUI.Borders.emptyTop(16)
        }
        panel.add(footer, BorderLayout.SOUTH)

        return panel
    }
}
