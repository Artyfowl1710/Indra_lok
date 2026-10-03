import { useEffect, useState } from "react";
import { useI18n } from "./context";
import { translateUiCopy, type UiCatalog } from "./ui-copy";

const bundles = import.meta.glob<{ default: UiCatalog }>("./ui-generated/*.json");
const loadedCatalogs = new Map<string, Promise<UiCatalog>>();
const originalText = new WeakMap<Text, { source: string; rendered: string }>();
const originalAttributes = new WeakMap<Element, Map<string, { source: string; rendered: string }>>();
const attributes = ["aria-label", "aria-description", "placeholder", "title", "alt"];
const ignored = "script, style, code, pre, textarea, input, .xterm, [translate='no'], [contenteditable='true']";

function loadCatalog(locale: string): Promise<UiCatalog> {
  if (locale === "en") return Promise.resolve({});
  const cached = loadedCatalogs.get(locale);
  if (cached) return cached;
  const load = bundles[`./ui-generated/${locale}.json`]?.().then((module) => module.default) ?? Promise.resolve({});
  loadedCatalogs.set(locale, load);
  return load;
}

/** Use for phrases whose word order must survive inline markup. */
export function useUiPhrase(source: string): string {
  const { locale } = useI18n();
  const [value, setValue] = useState(source);
  useEffect(() => {
    let cancelled = false;
    void loadCatalog(locale).then((catalog) => {
      if (!cancelled) setValue(translateUiCopy(source, catalog));
    });
    return () => { cancelled = true; };
  }, [locale, source]);
  return value;
}

function excluded(node: Node): boolean {
  const parent = node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
  return Boolean(parent?.closest(ignored));
}

function updateText(node: Text, catalog: UiCatalog) {
  if (excluded(node)) return;
  const current = node.data;
  const prior = originalText.get(node);
  const source = prior && current === prior.rendered ? prior.source : current;
  const rendered = translateUiCopy(source, catalog);
  originalText.set(node, { source, rendered });
  if (current !== rendered) node.data = rendered;
}

function updateAttributes(element: Element, catalog: UiCatalog) {
  if (excluded(element)) return;
  const saved = originalAttributes.get(element) ?? new Map();
  for (const name of attributes) {
    const current = element.getAttribute(name);
    if (current === null) continue;
    const prior = saved.get(name);
    const source = prior && current === prior.rendered ? prior.source : current;
    const rendered = translateUiCopy(source, catalog);
    saved.set(name, { source, rendered });
    if (current !== rendered) element.setAttribute(name, rendered);
  }
  originalAttributes.set(element, saved);
}

function updateTree(root: Node, catalog: UiCatalog) {
  if (excluded(root)) return;
  if (root.nodeType === Node.TEXT_NODE) updateText(root as Text, catalog);
  if (root.nodeType === Node.ELEMENT_NODE) updateAttributes(root as Element, catalog);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.nodeType === Node.TEXT_NODE) updateText(node as Text, catalog);
    else updateAttributes(node as Element, catalog);
  }
}

/** Applies prebuilt, local-only translations to legacy hard-coded page copy. */
export function UiTextLocalizer() {
  const { locale } = useI18n();

  useEffect(() => {
    let cancelled = false;
    let observer: MutationObserver | undefined;
    void loadCatalog(locale).then((catalog) => {
      if (cancelled || !catalog) return;
      document.title = translateUiCopy("INDRA — Intelligence Within Your Perimeter", catalog);
      updateTree(document.body, catalog);
      observer = new MutationObserver((changes) => {
        for (const change of changes) {
          if (change.type === "characterData") updateText(change.target as Text, catalog);
          else if (change.type === "attributes") updateAttributes(change.target as Element, catalog);
          else for (const node of change.addedNodes) updateTree(node, catalog);
        }
      });
      observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: attributes });
    });
    return () => { cancelled = true; observer?.disconnect(); };
  }, [locale]);

  return null;
}
