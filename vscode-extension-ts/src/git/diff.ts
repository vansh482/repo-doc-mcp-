import { execFile } from "child_process";
import { promisify } from "util";

const exec = promisify(execFile);

const MAX_DIFF_CHARS = 50000;

export interface BranchDiff {
  currentBranch: string;
  baseBranch: string;
  diffSummary: string;
  diffContent: string;
  changedFiles: string[];
  commitMessages: string[];
}

async function git(repoPath: string, args: string[]): Promise<string> {
  const { stdout } = await exec("git", args, {
    cwd: repoPath,
    maxBuffer: 10 * 1024 * 1024,
  });
  return stdout.trim();
}

export async function detectBaseBranch(repoPath: string): Promise<string> {
  const candidates = ["main", "master", "mainline"];
  for (const branch of candidates) {
    try {
      await git(repoPath, ["rev-parse", "--verify", branch]);
      return branch;
    } catch {
      // branch doesn't exist, try next
    }
  }
  throw new Error(
    "Could not detect base branch. None of main/master/mainline exist in this repo.",
  );
}

export async function getBranchDiff(
  repoPath: string,
  baseBranch: string,
): Promise<BranchDiff> {
  const currentBranch = await git(repoPath, [
    "rev-parse",
    "--abbrev-ref",
    "HEAD",
  ]);

  if (currentBranch === baseBranch) {
    return {
      currentBranch,
      baseBranch,
      diffSummary: "",
      diffContent: "",
      changedFiles: [],
      commitMessages: [],
    };
  }

  // Run all git commands in parallel
  const [diffSummary, rawDiff, changedFilesRaw, commitsRaw] =
    await Promise.all([
      git(repoPath, ["diff", `${baseBranch}...HEAD`, "--stat"]).catch(
        () => "",
      ),
      git(repoPath, ["diff", `${baseBranch}...HEAD`]).catch(() => ""),
      git(repoPath, ["diff", `${baseBranch}...HEAD`, "--name-only"]).catch(
        () => "",
      ),
      git(repoPath, ["log", `${baseBranch}..HEAD`, "--oneline"]).catch(
        () => "",
      ),
    ]);

  const diffContent =
    rawDiff.length > MAX_DIFF_CHARS
      ? rawDiff.slice(0, MAX_DIFF_CHARS) +
        `\n\n[... truncated at ${MAX_DIFF_CHARS} chars, ${rawDiff.length} total]`
      : rawDiff;

  const changedFiles = changedFilesRaw
    .split("\n")
    .filter((f) => f.length > 0);

  const commitMessages = commitsRaw
    .split("\n")
    .filter((m) => m.length > 0);

  return {
    currentBranch,
    baseBranch,
    diffSummary,
    diffContent,
    changedFiles,
    commitMessages,
  };
}
