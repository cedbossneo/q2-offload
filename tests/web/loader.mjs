// Node module hook for the page tests: the pages import shared code by its nginx URL
// (/q2-assets/core.js), served from web/assets/. Registered by setup.mjs.
const ASSETS = new URL("../../web/assets/", import.meta.url);

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("/q2-assets/")) {
    return nextResolve(new URL(specifier.slice("/q2-assets/".length), ASSETS).href, context);
  }
  return nextResolve(specifier, context);
}
