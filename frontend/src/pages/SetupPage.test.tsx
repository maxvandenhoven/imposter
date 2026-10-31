import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";
import type { GameRequest } from "@/api/types";
import { SetupPage } from "@/pages/SetupPage";
import { mockApi } from "@/test/api";
import { CATALOG } from "@/test/fixtures";

function renderSetup(onStart: (request: GameRequest) => void = vi.fn()) {
  mockApi({ "GET /catalog": () => ({ body: CATALOG }) });

  return render(
    <QueryClientProvider client={createQueryClient()}>
      <SetupPage onStart={onStart} />
    </QueryClientProvider>,
  );
}

describe("SetupPage", () => {
  it("starts a game with the default lineup from the catalog", async () => {
    const onStart = vi.fn();
    renderSetup(onStart);

    await userEvent.click(await screen.findByRole("button", { name: "Start game" }));

    expect(onStart).toHaveBeenCalledTimes(1);
    const request = onStart.mock.calls[0]?.[0] as GameRequest;
    expect(request.config.players.map((player) => player.model_id)).toEqual(
      CATALOG.default_lineup,
    );
  });

  it("checks the limits before the game can start", async () => {
    const onStart = vi.fn();
    renderSetup(onStart);

    await userEvent.click(await screen.findByRole("tab", { name: "Type" }));

    expect(
      screen.getByText("The secret word must be exactly one word."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start game" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Secret word"), "beacon");

    expect(screen.getByRole("button", { name: "Start game" })).toBeEnabled();
  });

  it("keeps at least three and at most eight seats", async () => {
    renderSetup();

    await userEvent.click(await screen.findByRole("button", { name: "Remove seat 1" }));

    expect(screen.getAllByRole("button", { name: /Remove seat/ })).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Remove seat 1" })).toBeDisabled();

    const add = screen.getByRole("button", { name: "Add seat" });

    for (let seat = 3; seat < 8; seat += 1) {
      await userEvent.click(add);
    }

    expect(screen.getAllByRole("button", { name: /Remove seat/ })).toHaveLength(8);
    expect(add).toBeDisabled();
  });
});
