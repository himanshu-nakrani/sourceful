"use client";

import { useState } from "react";

/**
 * Run `onChange` during render when `value` changes (compared with Object.is).
 *
 * This is React's "adjusting state when a prop changes" pattern
 * (https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes):
 * state updates made inside `onChange` are applied before React commits, so
 * there is no extra render+paint with stale state, unlike doing the same work
 * in a `useEffect`. `onChange` must only set this component's own state; side
 * effects (fetching, timers, refs) still belong in effects or handlers.
 *
 * The callback also runs on the first render (previous value is a unique
 * sentinel), matching an effect that runs on mount.
 */
const UNSET: unique symbol = Symbol("unset");

export function useOnChange<T>(value: T, onChange: (next: T) => void): void {
  const [previous, setPrevious] = useState<T | typeof UNSET>(UNSET);
  if (!Object.is(previous, value)) {
    setPrevious(value);
    onChange(value);
  }
}
