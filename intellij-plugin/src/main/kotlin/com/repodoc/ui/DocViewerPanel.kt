package com.repodoc.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTabbedPane
import com.intellij.util.ui.JBUI
import org.commonmark.parser.Parser
import org.commonmark.renderer.html.HtmlRenderer
import org.commonmark.ext.gfm.tables.TablesExtension
import java.awt.BorderLayout
import java.awt.Color
import java.awt.Desktop
import java.awt.Font
import javax.swing.*
import javax.swing.event.HyperlinkEvent
import javax.swing.text.html.HTMLEditorKit
import javax.swing.text.html.StyleSheet

/**
 * Documentation Viewer Panel — renders generated docs inside IntelliJ.
 *
 * VS Code uses a webview (embedded Chromium) for rendering HTML. IntelliJ has
 * two options: JCEF (embedded Chromium, heavyweight) or JEditorPane (Swing HTML,
 * lightweight). We use JEditorPane because:
 *   - No extra dependencies (JCEF requires bundled Chromium)
 *   - Faster startup
 *   - Works in all JetBrains IDEs including Community editions
 *   - Good enough for rendering Markdown-converted HTML
 *
 * The tradeoff is that JEditorPane supports HTML 3.2 (not modern CSS/JS), so
 * we can't render Mermaid diagrams inline. Instead, we show them as code blocks
 * with a note to use an external Mermaid renderer.
 *
 * COMPONENT HIERARCHY:
 *   DocViewerPanel (JPanel)
 *     └─ JBTabbedPane
 *          ├─ Tab "Technical Doc"
 *          │    └─ JBScrollPane → JEditorPane (HTML)
 *          └─ Tab "Non-Technical Guide"
 *               └─ JBScrollPane → JEditorPane (HTML)
 */
class DocViewerPanel : JPanel(BorderLayout()) {

    private val tabbedPane = JBTabbedPane()
    private val techEditor = createEditor()
    private val simpleEditor = createEditor()

    // Commonmark Markdown parser with GFM tables extension
    private val mdParser: Parser
    private val mdRenderer: HtmlRenderer

    init {
        val extensions = listOf(TablesExtension.create())
        mdParser = Parser.builder().extensions(extensions).build()
        mdRenderer = HtmlRenderer.builder().extensions(extensions).build()

        // Set up the tabbed pane with both doc tabs
        tabbedPane.addTab("📋 Technical Doc", createScrollPane(techEditor))
        tabbedPane.addTab("👤 Non-Technical Guide", createScrollPane(simpleEditor))

        add(tabbedPane, BorderLayout.CENTER)

        // Add a minimal toolbar at the top
        val toolbar = createToolbar()
        add(toolbar, BorderLayout.NORTH)
    }

    /**
     * Update the displayed documentation content.
     * Converts Markdown to HTML and renders it in the editor panes.
     */
    fun setContent(technicalDoc: String, nonTechnicalDoc: String) {
        if (technicalDoc.isNotEmpty()) {
            val html = markdownToHtml(technicalDoc)
            techEditor.text = wrapInHtmlDocument(html, "Technical Documentation")
            techEditor.caretPosition = 0
        } else {
            techEditor.text = wrapInHtmlDocument(
                "<p style='color: #888;'>No technical documentation generated yet.</p>",
                "Technical Documentation"
            )
        }

        if (nonTechnicalDoc.isNotEmpty()) {
            val html = markdownToHtml(nonTechnicalDoc)
            simpleEditor.text = wrapInHtmlDocument(html, "Non-Technical Guide")
            simpleEditor.caretPosition = 0
        } else {
            simpleEditor.text = wrapInHtmlDocument(
                "<p style='color: #888;'>No non-technical guide generated yet.</p>",
                "Non-Technical Guide"
            )
        }
    }

    /**
     * Convert Markdown to HTML using the Commonmark library.
     *
     * Commonmark handles standard Markdown features: headings, bold, italic,
     * lists, code blocks, links, tables (via extension), etc. For Mermaid
     * diagram blocks, we wrap them in a styled <pre> since JEditorPane
     * can't render SVG/Mermaid natively.
     */
    private fun markdownToHtml(markdown: String): String {
        val document = mdParser.parse(markdown)
        var html = mdRenderer.render(document)

        // Post-process: style Mermaid blocks distinctly
        html = html.replace(
            Regex("""<pre><code class="language-mermaid">(.*?)</code></pre>""", RegexOption.DOT_MATCHES_ALL),
            """<div style="background: #2d3748; padding: 12px; border-radius: 6px; 
               border-left: 4px solid #63b3ed; margin: 10px 0;">
               <p style="color: #63b3ed; font-weight: bold; margin: 0 0 8px 0;">
               📊 Architecture Diagram (Mermaid)</p>
               <pre style="color: #e2e8f0; font-size: 11px; white-space: pre-wrap;">$1</pre>
               <p style="color: #a0aec0; font-size: 10px; margin: 8px 0 0 0;">
               Copy this Mermaid code to mermaid.live or a Mermaid-compatible viewer to see the diagram.</p>
               </div>"""
        )

        return html
    }

    /**
     * Wrap content in a full HTML document with theme-aware styling.
     *
     * JEditorPane needs a complete HTML document with inline CSS since it
     * doesn't support external stylesheets or CSS variables. We detect
     * IntelliJ's current theme (dark vs light) and apply appropriate colors.
     */
    private fun wrapInHtmlDocument(bodyContent: String, title: String): String {
        // Detect if we're in a dark theme by checking the panel background color
        val bg = UIManager.getColor("Panel.background") ?: Color(43, 43, 43)
        val isDark = (bg.red + bg.green + bg.blue) / 3 < 128

        val bgColor = if (isDark) "#1e1e2e" else "#ffffff"
        val textColor = if (isDark) "#cdd6f4" else "#1e1e2e"
        val headingColor = if (isDark) "#89b4fa" else "#1e40af"
        val codeBackground = if (isDark) "#313244" else "#f1f5f9"
        val borderColor = if (isDark) "#45475a" else "#e2e8f0"
        val linkColor = if (isDark) "#89dceb" else "#2563eb"

        return """
            <html>
            <head>
            <style>
                body {
                    font-family: -apple-system, 'Segoe UI', sans-serif;
                    font-size: 13px;
                    line-height: 1.7;
                    color: $textColor;
                    background: $bgColor;
                    padding: 16px 24px;
                    max-width: 800px;
                }
                h1 { font-size: 22px; color: $headingColor; margin-top: 8px; margin-bottom: 12px; }
                h2 { font-size: 18px; color: $headingColor; margin-top: 28px; margin-bottom: 10px; 
                     border-bottom: 1px solid $borderColor; padding-bottom: 6px; }
                h3 { font-size: 15px; color: $headingColor; margin-top: 20px; margin-bottom: 8px; }
                p { margin-bottom: 10px; }
                a { color: $linkColor; }
                code { 
                    font-family: 'JetBrains Mono', 'Fira Code', monospace;
                    font-size: 12px;
                    background: $codeBackground;
                    padding: 1px 5px;
                    border-radius: 3px;
                }
                pre {
                    background: $codeBackground;
                    border: 1px solid $borderColor;
                    border-radius: 6px;
                    padding: 12px;
                    overflow-x: auto;
                    font-family: 'JetBrains Mono', 'Fira Code', monospace;
                    font-size: 12px;
                    line-height: 1.5;
                }
                pre code { background: none; padding: 0; }
                blockquote {
                    border-left: 3px solid $headingColor;
                    padding: 6px 12px;
                    margin: 12px 0;
                    background: ${if (isDark) "#1a1a2e" else "#f8fafc"};
                }
                table { border-collapse: collapse; width: 100%; margin: 12px 0; }
                th, td { border: 1px solid $borderColor; padding: 6px 10px; text-align: left; }
                th { background: $codeBackground; font-weight: 600; }
                ul, ol { padding-left: 20px; margin-bottom: 10px; }
                li { margin-bottom: 3px; }
                hr { border: none; border-top: 1px solid $borderColor; margin: 20px 0; }
                strong { font-weight: 600; }
            </style>
            </head>
            <body>
            $bodyContent
            </body>
            </html>
        """.trimIndent()
    }

    /**
     * Create a JEditorPane configured for HTML rendering.
     * JEditorPane is the Swing component for displaying rich text/HTML.
     */
    private fun createEditor(): JEditorPane {
        return JEditorPane().apply {
            contentType = "text/html"
            isEditable = false
            border = JBUI.Borders.empty()

            // Handle link clicks — open in the system browser
            addHyperlinkListener { event ->
                if (event.eventType == HyperlinkEvent.EventType.ACTIVATED) {
                    try {
                        Desktop.getDesktop().browse(event.url.toURI())
                    } catch (_: Exception) { }
                }
            }
        }
    }

    private fun createScrollPane(component: JComponent): JBScrollPane {
        return JBScrollPane(component).apply {
            border = JBUI.Borders.empty()
            verticalScrollBar.unitIncrement = 16
        }
    }

    private fun createToolbar(): JPanel {
        return JPanel(BorderLayout()).apply {
            border = JBUI.Borders.customLine(
                UIManager.getColor("Separator.foreground") ?: Color.GRAY,
                0, 0, 1, 0
            )
            preferredSize = java.awt.Dimension(0, 28)

            val label = JLabel("  Generated Documentation").apply {
                font = font.deriveFont(Font.BOLD, 11f)
                foreground = UIManager.getColor("Label.disabledForeground") ?: Color.GRAY
            }
            add(label, BorderLayout.WEST)
        }
    }

    companion object {
        /**
         * Open the documentation viewer tool window and display the given docs.
         *
         * This is the static entry point that Actions call. It finds (or creates)
         * the "Repo Documentation" tool window, replaces its content with a
         * DocViewerPanel, and activates it.
         */
        fun showDocs(project: Project, technicalDoc: String, nonTechnicalDoc: String) {
            val toolWindowManager = ToolWindowManager.getInstance(project)
            val toolWindow = toolWindowManager.getToolWindow("Repo Documentation") ?: return

            // Remove existing content and add fresh panel
            val contentManager = toolWindow.contentManager
            contentManager.removeAllContents(true)

            val panel = DocViewerPanel()
            panel.setContent(technicalDoc, nonTechnicalDoc)

            val content = contentManager.factory.createContent(
                panel,
                "Documentation",
                false // not lockable
            )
            contentManager.addContent(content)

            // Activate the tool window (make it visible and focused)
            toolWindow.show()
        }
    }
}
