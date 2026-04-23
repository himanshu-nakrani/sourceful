"use client";

import React from "react";

interface SkeletonProps {
  className?: string;
  width?: number | string;
  height?: number | string;
  rounded?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ className = "", width, height, rounded = "0.5rem", style }: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={`skeleton-shimmer ${className}`}
      style={{
        width,
        height,
        borderRadius: rounded,
        background: "var(--bg-elevated)",
        ...style,
      }}
    />
  );
}

export function SidebarDocSkeleton() {
  return (
    <div className="px-3 py-2.5 rounded-xl flex flex-col gap-2" style={{ background: "transparent" }}>
      <div className="flex items-center gap-2">
        <Skeleton width={14} height={14} rounded="4px" />
        <Skeleton height={12} style={{ flex: 1, maxWidth: 140 }} />
      </div>
      <Skeleton height={8} style={{ maxWidth: 90 }} />
    </div>
  );
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-3 px-4 py-3">
      <Skeleton width={28} height={28} rounded="50%" />
      <div className="flex-1 flex flex-col gap-2">
        <Skeleton height={10} style={{ maxWidth: "40%" }} />
        <Skeleton height={10} />
        <Skeleton height={10} style={{ maxWidth: "85%" }} />
        <Skeleton height={10} style={{ maxWidth: "65%" }} />
      </div>
    </div>
  );
}
