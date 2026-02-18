/**
 * Shared frontend configuration.
 *
 * Uses Vite environment variables when available so that a production build
 * only needs VITE_API_BASE / VITE_WS_URL set in the environment — no code
 * changes required.
 *
 * Development defaults point at the local FastAPI server.
 */

export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';
export const WS_URL   = import.meta.env.VITE_WS_URL   ?? 'ws://localhost:8000/ws';
