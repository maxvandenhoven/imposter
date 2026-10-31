import type { components } from "@/api/schema";

type Schemas = components["schemas"];

/** An ADK event as `/run_sse` streams it, with camelCase fields. */
export type AdkEvent = Schemas["Event-Output"];
export type CatalogCategory = Schemas["CatalogCategory"];
export type CatalogModel = Schemas["CatalogModel"];
export type CatalogResponse = Schemas["CatalogResponse"];
export type GameConfig = Schemas["GameConfig"];
/** An engine event, as the event log and the stream carry it. */
export type GameEvent = Schemas["GameEvent"];
export type GameEventType = GameEvent["type"];
export type GamePhase = Schemas["GamePhase"];
export type GameRequest = Schemas["GameRequest"];
export type IdentityMode = Schemas["IdentityMode"];
export type PlayerConfig = Schemas["PlayerConfig"];
export type WordMode = Schemas["WordMode"];
