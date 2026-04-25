"use client";

import { useCallback, useEffect, useState } from "react";
import { getMyWorkspaceRole, type ClientAuthContext, type WorkspaceRoleLiteral } from "./api";

// Simple in-memory cache to avoid duplicate calls for the same workspace
const roleCache = new Map<string, { role: WorkspaceRoleLiteral; timestamp: number }>();
const CACHE_TTL = 60000; // 1 minute cache

export function useWorkspaceRole(auth: ClientAuthContext, workspaceId: string | null) {
  const [role, setRole] = useState<WorkspaceRoleLiteral>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!workspaceId) {
      setRole(null);
      return;
    }
    
    // Check cache first
    const cacheKey = `${auth.clientSessionId}-${workspaceId}`;
    const cached = roleCache.get(cacheKey);
    const now = Date.now();
    
    if (cached && now - cached.timestamp < CACHE_TTL) {
      setRole(cached.role);
      return;
    }
    
    setLoading(true);
    try {
      const r = await getMyWorkspaceRole(auth, workspaceId);
      setRole(r);
      // Cache the result
      roleCache.set(cacheKey, { role: r, timestamp: now });
    } catch {
      setRole(null);
    } finally {
      setLoading(false);
    }
  }, [auth, workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const canEdit = role === "owner" || role === "admin" || role === "editor";
  const canManage = role === "owner" || role === "admin";

  return { role, loading, canEdit, canManage, refresh };
}
