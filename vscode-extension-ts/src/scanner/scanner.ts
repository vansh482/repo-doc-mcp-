import * as fs from "fs/promises";
import * as path from "path";

export interface RepoContext {
  name: string;
  languages: Record<string, number>;
  structure: string;
  keyFiles: string[];
  totalFiles: number;
  totalLines: number;
}

const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  ".venv",
  "venv",
  "__pycache__",
  "dist",
  "build",
  ".next",
  ".nuxt",
  "target",
  "out",
  ".output",
  "coverage",
  ".cache",
  ".turbo",
  ".svelte-kit",
  "vendor",
  "Pods",
]);

const EXT_TO_LANGUAGE: Record<string, string> = {
  ".ts": "TypeScript",
  ".tsx": "TypeScript",
  ".js": "JavaScript",
  ".jsx": "JavaScript",
  ".py": "Python",
  ".go": "Go",
  ".rs": "Rust",
  ".java": "Java",
  ".kt": "Kotlin",
  ".swift": "Swift",
  ".rb": "Ruby",
  ".php": "PHP",
  ".cs": "C#",
  ".cpp": "C++",
  ".c": "C",
  ".h": "C",
  ".vue": "Vue",
  ".svelte": "Svelte",
  ".dart": "Dart",
  ".scala": "Scala",
  ".ex": "Elixir",
  ".exs": "Elixir",
  ".zig": "Zig",
  ".lua": "Lua",
  ".sh": "Shell",
  ".bash": "Shell",
  ".sql": "SQL",
  ".html": "HTML",
  ".css": "CSS",
  ".scss": "SCSS",
};

const KEY_FILE_NAMES = new Set([
  "README.md",
  "readme.md",
  "package.json",
  "Cargo.toml",
  "go.mod",
  "pyproject.toml",
  "setup.py",
  "requirements.txt",
  "Dockerfile",
  "docker-compose.yml",
  "docker-compose.yaml",
  "Makefile",
  "CMakeLists.txt",
  "build.gradle",
  "build.gradle.kts",
  "pom.xml",
  "Gemfile",
  "mix.exs",
  ".env.example",
  "tsconfig.json",
  "webpack.config.js",
  "vite.config.ts",
  "next.config.js",
  "nest-cli.json",
]);

interface WalkResult {
  files: string[];
  dirs: Map<string, string[]>; // parent dir → immediate children dir names (depth ≤ 2)
  keyFiles: string[];
  languages: Record<string, number>;
}

async function walk(
  dir: string,
  rootDir: string,
  depth: number,
  result: WalkResult,
): Promise<void> {
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }

  const tasks: Promise<void>[] = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    const relPath = path.relative(rootDir, fullPath);

    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name) || entry.name.startsWith(".")) {
        continue;
      }

      if (depth <= 2) {
        const parentRel = path.relative(rootDir, dir) || ".";
        if (!result.dirs.has(parentRel)) {
          result.dirs.set(parentRel, []);
        }
        result.dirs.get(parentRel)!.push(entry.name);
      }

      tasks.push(walk(fullPath, rootDir, depth + 1, result));
    } else if (entry.isFile()) {
      result.files.push(relPath);

      if (KEY_FILE_NAMES.has(entry.name)) {
        result.keyFiles.push(relPath);
      }

      const ext = path.extname(entry.name).toLowerCase();
      const lang = EXT_TO_LANGUAGE[ext];
      if (lang) {
        result.languages[lang] = (result.languages[lang] || 0) + 1;
      }
    }
  }

  await Promise.all(tasks);
}

function buildStructureString(dirs: Map<string, string[]>): string {
  const lines: string[] = [];
  const rootChildren = dirs.get(".") || [];

  for (const child of rootChildren.sort()) {
    lines.push(`├── ${child}/`);
    const subChildren = dirs.get(child) || [];
    for (let i = 0; i < subChildren.length; i++) {
      const prefix = i === subChildren.length - 1 ? "│   └── " : "│   ├── ";
      lines.push(`${prefix}${subChildren[i]}/`);
    }
  }

  return lines.join("\n");
}

async function estimateLines(
  repoPath: string,
  files: string[],
): Promise<number> {
  // Sample up to 50 files to estimate average lines per file
  const sampleSize = Math.min(50, files.length);
  const step = Math.max(1, Math.floor(files.length / sampleSize));
  let totalSampledLines = 0;
  let sampledCount = 0;

  const tasks = [];
  for (let i = 0; i < files.length && sampledCount < sampleSize; i += step) {
    const filePath = path.join(repoPath, files[i]);
    tasks.push(
      fs
        .readFile(filePath, { encoding: "utf-8", flag: "r" })
        .then((content) => {
          // Count newlines in first 4KB to be fast
          const slice = content.slice(0, 4096);
          const newlines = (slice.match(/\n/g) || []).length;
          const ratio = content.length > 0 ? content.length / 4096 : 1;
          return Math.ceil(newlines * Math.max(1, ratio));
        })
        .catch(() => 0),
    );
    sampledCount++;
  }

  const lineCounts = await Promise.all(tasks);
  totalSampledLines = lineCounts.reduce((a, b) => a + b, 0);

  const avgLines =
    sampledCount > 0 ? totalSampledLines / sampledCount : 0;
  return Math.round(avgLines * files.length);
}

export async function scanRepo(repoPath: string): Promise<RepoContext> {
  const result: WalkResult = {
    files: [],
    dirs: new Map(),
    keyFiles: [],
    languages: {},
  };

  await walk(repoPath, repoPath, 1, result);

  const totalLines = await estimateLines(repoPath, result.files);

  return {
    name: path.basename(repoPath),
    languages: result.languages,
    structure: buildStructureString(result.dirs),
    keyFiles: result.keyFiles,
    totalFiles: result.files.length,
    totalLines,
  };
}
