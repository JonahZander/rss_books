/** The bare hostname for display (no leading www.); the input unchanged when
 * it isn't a parseable URL, and "" for a null/empty input. */
export function hostnameOf(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
