import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("landing, planner and gap study meet automated WCAG AA checks", async ({
  page,
}) => {
  for (const path of ["/", "/app", "/app?view=gaps"]) {
    await page.goto(path);
    if (path.startsWith("/app"))
      await expect(page.locator(".dataset-status.is-ready")).toBeVisible({
        timeout: 30000,
      });
    else
      await expect(
        page.getByRole("heading", { name: /The shortest route/ }),
      ).toBeVisible();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  }
});
