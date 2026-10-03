export type UiCatalog = Record<string, string>;

const technicalPattern = /[\\/{}<>]|https?:|--|\w=\w/;
const stylePattern = /(?:^|\s)(?:bg-|text-|flex(?:\s|$)|grid(?:\s|$)|rounded-|px-|py-|w-|h-|border-|shadow-|mt-|mb-|gap-|items-|justify-|lg:|sm:|md:)/;

/** Preserve technical identifiers and whitespace while translating interface copy. */
export function translateUiCopy(source: string, catalog: UiCatalog): string {
  const leading = source.match(/^\s*/)?.[0] ?? "";
  const trailing = source.match(/\s*$/)?.[0] ?? "";
  const phrase = source.trim();
  if (!/^[A-Za-z(]/.test(phrase) || !/[A-Za-z]/.test(phrase)
    || /^[\s/$@.#-]/.test(phrase) || technicalPattern.test(phrase)
    || stylePattern.test(phrase)
    || (!/\s/.test(phrase) && /[\d_.-]/.test(phrase))
    || /^[a-z]+:$/.test(phrase) || /^[A-Z0-9_.-]+$/.test(phrase)) return source;
  return phrase && catalog[phrase] ? `${leading}${catalog[phrase]}${trailing}` : source;
}
