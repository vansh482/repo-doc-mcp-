export type CredentialScope = 'llm' | 'publisher';

export interface Credential {
  value: string;
  expiresAt?: Date;
  metadata?: Record<string, string>;
}

export interface AuthProvider {
  getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
  setCredential?(scope: CredentialScope, providerId: string, credential: Credential): Promise<void>;
  validateCredential?(scope: CredentialScope, providerId: string): Promise<boolean>;
  refreshCredential?(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
}
