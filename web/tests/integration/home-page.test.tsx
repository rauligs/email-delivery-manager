import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../../src/app/page";

describe("Home", () => {
  it("renders the scaffold services", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { name: "Four runnable layers, ready for product work." }),
    ).toBeInTheDocument();

    const services = screen.getByRole("region", { name: "Project apps" });
    expect(within(services).getByRole("heading", { name: "API" })).toBeInTheDocument();
    expect(within(services).getByRole("heading", { name: "Background" })).toBeInTheDocument();
    expect(within(services).getByRole("heading", { name: "Shared" })).toBeInTheDocument();
    expect(within(services).getByRole("heading", { name: "Web" })).toBeInTheDocument();
  });
});
