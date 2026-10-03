import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import ts from "typescript";

const root = path.resolve(import.meta.dirname, "..");
const outputDir = path.join(root, "src", "i18n", "ui-generated");
const endpoint = process.env.INDRA_TRANSLATION_ENDPOINT ?? "http://127.0.0.1:8100/v1/chat/completions";
if (!["127.0.0.1", "localhost", "::1"].includes(new URL(endpoint).hostname)) {
  throw new Error("Translation generation accepts loopback model endpoints only");
}
const model = process.env.INDRA_TRANSLATION_MODEL ?? "qwen3.5-4b";
const languages = {
  zh: "Simplified Chinese", "zh-hant": "Traditional Chinese", ja: "Japanese",
  de: "German", es: "Spanish", fr: "French", tr: "Turkish",
  uk: "Ukrainian", af: "Afrikaans", ko: "Korean", it: "Italian",
  ga: "Irish", pt: "Portuguese", ru: "Russian", hu: "Hungarian", ar: "Arabic",
};
const requested = process.argv.includes("--locale")
  ? [process.argv[process.argv.indexOf("--locale") + 1]]
  : Object.keys(languages);
const dryRun = process.argv.includes("--dry-run");
const verifyOnly = process.argv.includes("--verify");
const limit = process.argv.includes("--limit")
  ? Number(process.argv[process.argv.indexOf("--limit") + 1])
  : Infinity;
const audit = JSON.parse(execFileSync(process.execPath, [path.join(root, "scripts", "audit-localization.mjs")], { encoding: "utf8" }));
const pagePhrases = [...new Set(audit.pages.flatMap((page) => page.strings))];

function safeUiPhrase(value) {
  return /^[A-Za-z(]/.test(value) && /[A-Za-z]/.test(value) && !/^[\s/$@.#-]/.test(value)
    && !/[\\/{}<>]|https?:|--|\w=\w/.test(value)
    && !/(?:^|\s)(?:bg-|text-|flex(?:\s|$)|grid(?:\s|$)|rounded-|px-|py-|w-|h-|border-|shadow-|mt-|mb-|gap-|items-|justify-|lg:|sm:|md:)/.test(value)
    && !(!/\s/.test(value) && /[\d_.-]/.test(value))
    && !/^[a-z]+:$/.test(value)
    && !/^[A-Z0-9_.-]+$/.test(value);
}

function catalogValues(locale) {
  const source = ts.createSourceFile(locale, fs.readFileSync(path.join(root, "src", "i18n", `${locale}.ts`), "utf8"), ts.ScriptTarget.Latest, true);
  const values = new Map();
  function flatten(node, prefix = "") {
    if (!ts.isObjectLiteralExpression(node)) return;
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property)) continue;
      const key = property.name.getText(source).replace(/^['"]|['"]$/g, "");
      const pathKey = prefix ? `${prefix}.${key}` : key;
      if (ts.isObjectLiteralExpression(property.initializer)) flatten(property.initializer, pathKey);
      else if (ts.isStringLiteral(property.initializer) || ts.isNoSubstitutionTemplateLiteral(property.initializer)) {
        values.set(pathKey, property.initializer.text);
      }
    }
  }
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.initializer && ts.isObjectLiteralExpression(node.initializer)) flatten(node.initializer);
    ts.forEachChild(node, visit);
  }
  visit(source);
  return values;
}
const englishValues = catalogValues("en");

function parseTranslation(content, expected) {
  const trimmed = content.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const start = trimmed.indexOf("[");
  const end = trimmed.lastIndexOf("]");
  if (start < 0 || end < start) throw new Error("Model did not return a JSON array");
  const translated = JSON.parse(trimmed.slice(start, end + 1));
  if (!Array.isArray(translated) || translated.length !== expected
    || translated.some((value) => typeof value !== "string" || !value.trim())) {
    throw new Error(`Expected ${expected} translated strings`);
  }
  return translated.map((value) => value.trim());
}

async function translate(batch, language) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model, temperature: 0, max_tokens: 2048,
      messages: [
        { role: "system", content: `Translate English software interface strings into ${language}. Return ONLY a JSON array of strings, same length and same order. Preserve INDRA, model names, file paths, code, placeholders such as {count}, keyboard shortcuts, and product names. Do not add commentary. Use natural, concise UI language.` },
        { role: "user", content: JSON.stringify(batch) },
      ],
    }),
    signal: AbortSignal.timeout(180_000),
  });
  if (!response.ok) throw new Error(`Local model returned HTTP ${response.status}`);
  const data = await response.json();
  return parseTranslation(data.choices?.[0]?.message?.content ?? "", batch.length);
}

async function translateSafely(batch, language) {
  let lastError;
  for (let attempt = 0; attempt < 2; attempt++) {
    try { return await translate(batch, language); }
    catch (error) { lastError = error; }
  }
  if (batch.length === 1) throw lastError;
  const middle = Math.floor(batch.length / 2);
  return [
    ...await translateSafely(batch.slice(0, middle), language),
    ...await translateSafely(batch.slice(middle), language),
  ];
}

for (const locale of requested) {
  if (!languages[locale]) throw new Error(`Unsupported locale: ${locale}`);
  const ownValues = catalogValues(locale);
  const curatedTranslations = new Map();
  for (const [key, source] of englishValues) {
    const translated = ownValues.get(key);
    if (safeUiPhrase(source) && translated && translated !== source && !curatedTranslations.has(source)) {
      curatedTranslations.set(source, translated);
    }
  }
  const catalogFallbacks = [...englishValues].filter(([key, value]) => safeUiPhrase(value)
    && (!ownValues.has(key) || ownValues.get(key) === value)).map(([, value]) => value);
  const phrases = [...new Set([...pagePhrases, ...catalogFallbacks])].sort().slice(0, limit);
  const output = path.join(outputDir, `${locale}.json`);
  const previous = fs.existsSync(output) ? JSON.parse(fs.readFileSync(output, "utf8")) : {};
  const saved = Object.fromEntries(phrases.filter((phrase) => curatedTranslations.has(phrase) || previous[phrase])
    .map((phrase) => [phrase, curatedTranslations.get(phrase) ?? previous[phrase]]));
  const pending = phrases.filter((phrase) => !saved[phrase]);
  console.log(`${locale}: ${phrases.length - pending.length}/${phrases.length} cached`);
  if (verifyOnly) {
    if (pending.length) process.exitCode = 1;
    continue;
  }
  for (let offset = 0; offset < pending.length; offset += 20) {
    const batch = pending.slice(offset, offset + 20);
    const translated = await translateSafely(batch, languages[locale]);
    batch.forEach((phrase, index) => { saved[phrase] = translated[index]; });
    if (!dryRun) {
      fs.mkdirSync(outputDir, { recursive: true });
      fs.writeFileSync(output, `${JSON.stringify(saved, null, 2)}\n`, "utf8");
    }
    console.log(`${locale}: ${Math.min(offset + batch.length, pending.length)}/${pending.length} translated`);
  }
}
