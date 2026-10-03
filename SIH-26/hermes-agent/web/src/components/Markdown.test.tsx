import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("Markdown tables", () => {
  it("renders a Markdown table as a semantic, scrollable table", () => {
    const html = renderToStaticMarkup(
      <Markdown content={"| Item | Amount |\n| --- | ---: |\n| PDF | 1 |"} />,
    );
    expect(html).toContain("<table");
    expect(html).toContain("<th");
    expect(html).toContain("<td");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("text-align:right");
  });

  it("keeps isolated pipe characters as prose", () => {
    const html = renderToStaticMarkup(<Markdown content="Choose PDF | Excel for export." />);
    expect(html).not.toContain("<table");
    expect(html).toContain("PDF | Excel");
  });
});
