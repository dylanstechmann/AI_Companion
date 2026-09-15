// Non-sensitive UI preferences live for this page session. This also works in
// private/embedded contexts without requiring access to browser storage.
const preferences = new Map();
export const getPreference = (key) => preferences.get(key) ?? null;
export const setPreference = (key, value) => preferences.set(key, String(value));
