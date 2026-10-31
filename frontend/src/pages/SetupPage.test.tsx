import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";
import type { GameRequest } from "@/api/types";
import { TooltipProvider } from "@/components/ui/tooltip";
import { type ImportedGame, SetupPage } from "@/pages/SetupPage";
import { mockApi } from "@/test/api";
import { buildGameExport } from "@/lib/gameExport";
import { CATALOG, wholeGame } from "@/test/fixtures";

function renderSetup(
  onStart: (request: GameRequest) => void = vi.fn(),
  onImport: (game: ImportedGame) => void = vi.fn(),
) {
  // The default imposter sits on the first seat.
  vi.spyOn(Math, "random").mockReturnValue(0);
  mockApi({ "GET /catalog": () => ({ body: CATALOG }) });

  return render(
    <QueryClientProvider client={createQueryClient()}>
      <TooltipProvider>
        <SetupPage onStart={onStart} onImport={onImport} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("SetupPage", () => {
  it("explains the rules of the game below the form", async () => {
    renderSetup();

    expect(
      await screen.findByRole("heading", { name: "How to play" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Saying the word" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("Breaks a rule").length).toBeGreaterThan(0);
  });

  it("imports an exported game", async () => {
    const onImport = vi.fn();
    renderSetup(vi.fn(), onImport);
    const config = { config: {}, words: {} } as unknown as GameRequest;
    const file = new File(
      [JSON.stringify(buildGameExport({ config, events: wholeGame() }))],
      "game.json",
      { type: "application/json" },
    );

    await userEvent.upload(await screen.findByLabelText("Exported game"), file);

    await waitFor(() => {
      expect(onImport).toHaveBeenCalledTimes(1);
    });
    expect(onImport.mock.calls[0]?.[0]).toMatchObject({ events: wholeGame() });
  });

  it("reports a file that is not an export", async () => {
    const onImport = vi.fn();
    renderSetup(vi.fn(), onImport);
    const file = new File(["nope"], "game.json", { type: "application/json" });

    await userEvent.upload(await screen.findByLabelText("Exported game"), file);

    expect(await screen.findByText("The file is not valid JSON.")).toBeInTheDocument();
    expect(onImport).not.toHaveBeenCalled();
  });

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

  it("starts a game with the imposters that were chosen", async () => {
    const onStart = vi.fn();
    renderSetup(onStart);

    await userEvent.click(
      await screen.findByRole("button", { name: "Seat 1 is an imposter" }),
    );

    expect(screen.getByText("Choose at least one imposter.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Seat 2 is an imposter" }));
    await userEvent.click(screen.getByRole("button", { name: "Start game" }));

    const request = onStart.mock.calls[0]?.[0] as GameRequest;
    expect(request.config.imposter_count).toBe(1);
    expect(request.config.players.map((player) => player.imposter)).toEqual([
      false,
      true,
      false,
      false,
    ]);
  });

  it("changes the seats without starting the game", async () => {
    const onStart = vi.fn();
    renderSetup(onStart);

    await userEvent.click(await screen.findByRole("button", { name: "Add seat" }));
    await userEvent.click(screen.getByRole("button", { name: "Randomise lineup" }));
    await userEvent.click(screen.getByRole("button", { name: "Randomise imposters" }));
    await userEvent.click(screen.getByRole("button", { name: "Advanced" }));

    expect(onStart).not.toHaveBeenCalled();
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
