/**
 * Reads a server-sent event stream chunk by chunk, returning the data of each event.
 *
 * Follows the event stream format: lines end with `\n`, `\r\n` or `\r`, `data` lines of
 * one event are joined with newlines, and a blank line ends the event. Comments and the
 * other fields (`event`, `id`, `retry`) are ignored, since ADK sends every event as
 * JSON in its data.
 */
export class ServerSentEventParser {
  /** The text after the last complete line, which the next chunk continues. */
  private pending = "";
  /** Whether the last chunk ended with `\r`, so a `\n` starting the next one is its pair. */
  private skipLineFeed = false;
  /** The data lines of the event being read. */
  private data: string[] = [];

  /** Add a chunk of the stream, returning the data of every event it completes. */
  push(chunk: string): string[] {
    const text = this.skipLineFeed && chunk.startsWith("\n") ? chunk.slice(1) : chunk;
    this.skipLineFeed = text.endsWith("\r");
    const lines = (this.pending + text).split(/\r\n|\n|\r/);
    this.pending = lines.pop() ?? "";
    const events: string[] = [];

    for (const line of lines) {
      if (line === "") {
        if (this.data.length > 0) {
          events.push(this.data.join("\n"));
          this.data = [];
        }
      } else if (line.startsWith("data:")) {
        const value = line.slice("data:".length);
        this.data.push(value.startsWith(" ") ? value.slice(1) : value);
      }
    }

    return events;
  }
}
