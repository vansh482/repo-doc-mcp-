export interface BranchPages {
  technicalPageId: string;
  nonTechnicalPageId: string;
  lastUpdated: string;
}

export interface StorageProvider {
  getPages(branch: string, publisherId: string): Promise<BranchPages | undefined>;
  setPages(branch: string, publisherId: string, pages: BranchPages): Promise<void>;
  removeBranch(branch: string): Promise<void>;
  getHistory(): Promise<Array<{ branch: string; publisherId: string; pages: BranchPages }>>;
}
