"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useOnChange } from "./use-on-change";
import { getMyWorkspaceRole, type ClientAuthContext, type WorkspaceRoleLiteral } from "./api";

// Simple in-memory cache to avoid duplicate calls for the same workspace
const roleCache = new Map<string, { role: WorkspaceRoleLiteral; timestamp: number }>();
const CACHE_TTL = 60000; // 1 minute cache

/**
 * Invalidate cached workspace roles. Call whenever the authenticated identity
 * changes (login/logout) — cache keys don't include the user id, so roles
 * from a previous identity must not survive the switch.
 */
export function clearRoleCache() {
  roleCache.clear();
}

function freshCachedRole(cacheKey: string): { role: WorkspaceRoleLiteral } | null {
  const cached = roleCache.get(cacheKey);
  return cached && Date.now() - cached.timestamp < CACHE_TTL ? cached : null;
}

export function useWorkspaceRole(auth: ClientAuthContext, workspaceId: string | null) {
  const [role, setRole] = useState<WorkspaceRoleLiteral>(null);
  const [loading, setLoading] = useState(false);
  // Bumped by refresh() to re-check (cache-aware) with the same inputs.
  const [reloadToken, setReloadToken] = useState(0);
  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  // One key per lookup; replaced when workspace/auth (or the token) changes.
  const request = useMemo(() => {
    if (!workspaceId) return null;
    return {
      auth,
      workspaceId,
      cacheKey: `${auth.clientSessionId}-${auth.providerApiKey ?? ""}-${workspaceId}`,
      reloadToken,
    };
  }, [auth, workspaceId, reloadToken]);

  // Synchronous outcomes (no workspace, fresh cache hit, start loading) are
  // applied during render; only the network lookup runs in the effect.
  useOnChange(request, (next) => {
    if (!next) {
      setRole(null);
      return;
    }
    const cached = freshCachedRole(next.cacheKey);
    if (cached) {
      setRole(cached.role);
      return;
    }
    setLoading(true);
  });

  useEffect(() => {
    if (!request || freshCachedRole(request.cacheKey)) return;
    const { auth: requestAuth, workspaceId: requestWorkspaceId, cacheKey } = request;
    const run = async () => {
      const now = Date.now();
      try {
        const r = await getMyWorkspaceRole(requestAuth, requestWorkspaceId);
        setRole(r);
        roleCache.set(cacheKey, { role: r, timestamp: now });
      } catch {
        setRole(null);
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [request]);

  const canEdit = role === "owner" || role === "admin" || role === "editor";
  const canManage = role === "owner" || role === "admin";

  return { role, loading, canEdit, canManage, refresh };
}
