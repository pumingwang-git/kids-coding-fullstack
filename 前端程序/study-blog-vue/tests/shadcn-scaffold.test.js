import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { cn } from "../src/lib/utils";

const projectFile = (relativePath) =>
  readFileSync(fileURLToPath(new URL(`../${relativePath}`, import.meta.url)), "utf8");

describe("shadcn-vue scaffold", () => {
  it("merges conditional and conflicting utility classes", () => {
    expect(cn("px-2", false && "hidden", ["px-4", "text-primary"])).toBe(
      "px-4 text-primary",
    );
  });

  it("keeps Tailwind preflight disabled and bridges semantic tokens", () => {
    const css = projectFile("src/styles.css");

    expect(css).toContain('@import "tailwindcss/theme.css" layer(theme);');
    expect(css).toContain('@import "tailwindcss/utilities.css" layer(utilities);');
    expect(css).not.toContain('@import "tailwindcss";');
    expect(css).not.toContain('tailwindcss/preflight.css');
    expect(css).toContain("@custom-variant dark (&:where(.dark, .dark *));");
    expect(css).toContain("--color-background: var(--background);");
    expect(css).toContain("--background: var(--paper);");
    expect(css).toContain("--primary: var(--accent);");
    expect(css).toContain("--border: var(--line);");
    expect(css.match(/--ann-teacher:/g)).toHaveLength(2);
    expect(css.match(/--ann-student:/g)).toHaveLength(2);
  });

  it("points the component registry at the existing stylesheet and aliases", () => {
    const config = JSON.parse(projectFile("components.json"));

    expect(config.tailwind).toMatchObject({
      config: "",
      css: "src/styles.css",
      cssVariables: true,
    });
    expect(config.aliases.utils).toBe("@/lib/utils");
    expect(config.iconLibrary).toBe("lucide");
  });
});
