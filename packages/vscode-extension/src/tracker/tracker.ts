import type * as vscode from 'vscode';

export interface BranchPages {
  technicalPageId: string;
  nonTechnicalPageId: string;
  lastUpdated: string;
}

const STORAGE_KEY = 'repoDoc.branchPages';

export class DocTracker {
  constructor(private state: vscode.Memento) {}

  getPages(branch: string): BranchPages | undefined {
    const all = this.getAllTracked();
    return all[branch];
  }

  setPages(branch: string, pages: BranchPages): void {
    const all = this.getAllTracked();
    all[branch] = pages;
    this.state.update(STORAGE_KEY, all);
  }

  removeBranch(branch: string): void {
    const all = this.getAllTracked();
    delete all[branch];
    this.state.update(STORAGE_KEY, all);
  }

  getAllTracked(): Record<string, BranchPages> {
    return this.state.get<Record<string, BranchPages>>(STORAGE_KEY) || {};
  }

  getHistory(): Array<{ branch: string; pages: BranchPages }> {
    const all = this.getAllTracked();
    return Object.entries(all)
      .map(([branch, pages]) => ({ branch, pages }))
      .sort((a, b) => new Date(b.pages.lastUpdated).getTime() - new Date(a.pages.lastUpdated).getTime());
  }
}
