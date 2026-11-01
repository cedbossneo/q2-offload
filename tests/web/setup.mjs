// Imports a page module after mapping /q2-assets/ to web/assets/ (Node 20.6+, no flags needed).
import { register } from "node:module";

register("./loader.mjs", import.meta.url);

export const importWeb = (path) => import(new URL("../../web/" + path, import.meta.url).href);
