// Hash changes (including browser Back/Forward) wait for the active editor.
let guard = null;
export function guardNavigation(next) {
  guard = next;
  return () => {
    if (guard === next) guard = null;
  };
}
export async function flushNavigation() {
  await guard?.();
}
