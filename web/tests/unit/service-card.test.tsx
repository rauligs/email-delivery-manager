import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ServiceCard } from "../../src/app/service-card";

describe("ServiceCard", () => {
  it("renders the service name, description, and path", () => {
    render(
      <ServiceCard
        service={{
          name: "Shared",
          description: "Models shared across Python services",
          path: "../shared",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Shared" })).toBeInTheDocument();
    expect(screen.getByText("Models shared across Python services")).toBeInTheDocument();
    expect(screen.getByText("../shared")).toBeInTheDocument();
  });
});
