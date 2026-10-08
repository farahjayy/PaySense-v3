import { act } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { saveSession, useAuth } from "@/lib/session";

function Probe() {
  const auth = useAuth();
  return <p>{auth.status}</p>;
}

describe("useAuth across server render and hydration", () => {
  it("is 'loading' on the server and settles to the stored session after hydrating", async () => {
    saveSession({
      token: "t",
      expiresAt: Date.now() + 60_000,
      user: { id: "u", username: "amir", display_name: "Amir", persona: null },
    });
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const html = renderToString(<Probe />);
    expect(html).toContain("loading"); // storage is unknowable on the server: no redirect decision
    const container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);

    await act(async () => {
      hydrateRoot(container, <Probe />);
    });

    expect(container.textContent).toBe("authenticated");
    expect(errors).not.toHaveBeenCalled(); // no hydration mismatch
    errors.mockRestore();
    container.remove();
  });

  it("is 'anonymous' (not 'loading') after hydrating with no session", async () => {
    const container = document.createElement("div");
    container.innerHTML = renderToString(<Probe />);
    document.body.appendChild(container);

    await act(async () => {
      hydrateRoot(container, <Probe />);
    });

    expect(container.textContent).toBe("anonymous");
    container.remove();
  });
});
