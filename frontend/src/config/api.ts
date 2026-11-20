/**
 * Centralized API client and configuration
 */

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'offline';
  timestamp: string;
  environment: string;
  version: string;
  database: 'connected' | 'disconnected' | 'unknown';
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok && response.status !== 503) {
      throw new Error(`API returned HTTP ${response.status}`);
    }

    const data = await response.json();
    return {
      status: data.status,
      timestamp: data.timestamp,
      environment: data.environment,
      version: data.version,
      database: data.database,
    };
  } catch (error) {
    return {
      status: 'offline',
      timestamp: new Date().toISOString(),
      environment: 'unknown',
      version: 'unknown',
      database: 'unknown',
    };
  }
}
