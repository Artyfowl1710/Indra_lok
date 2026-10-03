import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = path.resolve(import.meta.dirname, "../src");
const pageDir = path.join(root, "pages");
const componentDir = path.join(root, "components");
const extraUiCopy = [
  "Chat", "Models", "Auto Routing", "Knowledge", "Sandbox", "Audit", "Runtime",
  "More", "Sessions", "Skills", "Automations", "Extensions", "Tool connectors",
  "Integrations", "Event hooks", "Pairing", "Profiles", "Analytics", "Settings",
  "Keys", "Documentation", "Workspace", "Runtime ready", "Runtime stopped",
  "Status unavailable", "INDRA — Intelligence Within Your Perimeter",
  "What would you like INDRA to do?",
];
const files = [path.join(root, "App.tsx"), ...fs.readdirSync(pageDir)
  .filter((name) => name.endsWith("Page.tsx") && !name.endsWith(".test.tsx"))
  .map((name) => path.join(pageDir, name)), ...fs.readdirSync(componentDir)
  .filter((name) => name.endsWith(".tsx") && !name.endsWith(".test.tsx"))
  .map((name) => path.join(componentDir, name))];
const visibleAttributes = new Set(["aria-label", "aria-description", "placeholder", "title", "alt"]);
function safeUiPhrase(value) {
  return /^[A-Za-z(]/.test(value) && /[A-Za-z]/.test(value)
    && !/^[\s/$@.#-]/.test(value)
    && !/[\\/{}<>]|https?:|--|\w=\w/.test(value)
    && !/(?:^|\s)(?:bg-|text-|flex(?:\s|$)|grid(?:\s|$)|rounded-|px-|py-|w-|h-|border-|shadow-|mt-|mb-|gap-|items-|justify-|lg:|sm:|md:)/.test(value)
    && !(!/\s/.test(value) && /[\d_.-]/.test(value))
    && !/^[a-z]+:$/.test(value)
    && !/^[A-Z0-9_.-]+$/.test(value);
}
const englishFile = path.join(root, "i18n", "en.ts");
const englishSource = ts.createSourceFile(englishFile, fs.readFileSync(englishFile, "utf8"), ts.ScriptTarget.Latest, true);
const translatedEnglish = new Set();
function collectEnglish(node) {
  if (ts.isPropertyAssignment(node) && (ts.isStringLiteral(node.initializer) || ts.isNoSubstitutionTemplateLiteral(node.initializer))) {
    translatedEnglish.add(node.initializer.text.trim());
  }
  ts.forEachChild(node, collectEnglish);
}
collectEnglish(englishSource);

function visibleText(node, source) {
  if (ts.isJsxText(node)) return node.getText(source).replace(/\s+/g, " ").trim();
  if (ts.isJsxAttribute(node) && visibleAttributes.has(node.name.text)
    && node.initializer && ts.isStringLiteral(node.initializer)) {
    return node.initializer.text.trim();
  }
  return "";
}

function dynamicUiLiteral(node) {
  if (!ts.isStringLiteral(node) || !safeUiPhrase(node.text) || !(/^[A-Z]/.test(node.text) || /\s/.test(node.text))) return "";
  let inExpression = false;
  for (let parent = node.parent; parent; parent = parent.parent) {
    if (ts.isJsxAttribute(parent) && ["className", "href", "src", "to", "key", "id"].includes(parent.name.text)) return "";
    if (ts.isJsxExpression(parent)) inExpression = true;
  }
  return inExpression ? node.text.trim() : "";
}

const inventory = files.map((file) => {
  const source = ts.createSourceFile(file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const strings = new Set();
  function visit(node) {
    const value = visibleText(node, source) || dynamicUiLiteral(node);
    if (value && safeUiPhrase(value)) strings.add(value);
    ts.forEachChild(node, visit);
  }
  visit(source);
  const missing = [...strings].filter((value) => !translatedEnglish.has(value));
  return { page: path.relative(root, file).replaceAll("\\", "/"), count: strings.size, missingCount: missing.length, strings: [...strings].sort(), missing: missing.sort() };
});
inventory[0].strings = [...new Set([...inventory[0].strings, ...extraUiCopy])].sort();
inventory[0].missing = inventory[0].strings.filter((value) => !translatedEnglish.has(value));
inventory[0].count = inventory[0].strings.length;
inventory[0].missingCount = inventory[0].missing.length;

const total = inventory.reduce((sum, page) => sum + page.count, 0);
const pages = process.argv.includes("--summary")
  ? inventory.map(({ page, count, missingCount }) => ({ page, count, missingCount }))
  : inventory;
process.stdout.write(`${JSON.stringify({ total, pages }, null, 2)}\n`);
