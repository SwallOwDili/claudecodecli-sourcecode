export interface PlaybackContext {
  index: number;
  total: number;
}

export type PlaybackState = "idle" | "paused" | "playing" | "completed";

export type PlaybackEvent =
  | { type: "LOAD"; total: number }
  | { type: "NEXT" }
  | { type: "PREV" }
  | { type: "PLAY" }
  | { type: "PAUSE" }
  | { type: "TICK" }
  | { type: "RESET" }
  | { type: "SEEK"; index: number };

export interface PlaybackSnapshot {
  value: PlaybackState;
  context: PlaybackContext;
  matches(state: PlaybackState): boolean;
}

type PlaybackListener = (snapshot: PlaybackSnapshot) => void;

function snapshot(value: PlaybackState, context: PlaybackContext): PlaybackSnapshot {
  const frozenContext = { ...context };
  return {
    value,
    context: frozenContext,
    matches: (state) => value === state,
  };
}

export class PlaybackController {
  #value: PlaybackState = "idle";
  #context: PlaybackContext = { index: -1, total: 0 };
  readonly #listeners = new Set<PlaybackListener>();

  start(): this {
    return this;
  }

  getSnapshot(): PlaybackSnapshot {
    return snapshot(this.#value, this.#context);
  }

  subscribe(listener: PlaybackListener): { unsubscribe(): void } {
    this.#listeners.add(listener);
    listener(this.getSnapshot());
    return { unsubscribe: () => this.#listeners.delete(listener) };
  }

  send(event: PlaybackEvent): void {
    if (event.type === "LOAD") {
      this.#value = "paused";
      this.#context = { total: Math.max(0, event.total), index: -1 };
      this.#emit();
      return;
    }
    if (event.type === "SEEK") {
      const index = Math.max(
        -1,
        Math.min(event.index, this.#context.total - 1),
      );
      this.#value =
        this.#context.total > 0 && index === this.#context.total - 1
          ? "completed"
          : "paused";
      this.#context = {
        ...this.#context,
        index,
      };
      this.#emit();
      return;
    }

    if (this.#value === "paused") this.#sendPaused(event);
    else if (this.#value === "playing") this.#sendPlaying(event);
    else if (this.#value === "completed") this.#sendCompleted(event);
  }

  #sendPaused(event: PlaybackEvent): void {
    if (event.type === "NEXT") this.#advance();
    else if (event.type === "PREV") {
      this.#setIndex(Math.max(-1, this.#context.index - 1));
    } else if (
      event.type === "PLAY" &&
      this.#context.index + 1 < this.#context.total
    ) {
      this.#value = "playing";
      this.#emit();
    } else if (event.type === "RESET") this.#setIndex(-1);
  }

  #sendPlaying(event: PlaybackEvent): void {
    if (event.type === "TICK" || event.type === "NEXT") this.#advance();
    else if (event.type === "PREV") {
      this.#value = "paused";
      this.#setIndex(Math.max(-1, this.#context.index - 1));
    } else if (event.type === "PAUSE") {
      this.#value = "paused";
      this.#emit();
    } else if (event.type === "RESET") {
      this.#value = "paused";
      this.#setIndex(-1);
    }
  }

  #sendCompleted(event: PlaybackEvent): void {
    if (event.type === "PREV") {
      this.#value = "paused";
      this.#setIndex(Math.max(-1, this.#context.index - 1));
    } else if (event.type === "RESET") {
      this.#value = "paused";
      this.#setIndex(-1);
    }
  }

  #advance(): void {
    if (this.#context.total <= 0) return;
    if (this.#context.index + 1 >= this.#context.total - 1) {
      this.#value = "completed";
      this.#setIndex(Math.max(-1, this.#context.total - 1));
      return;
    }
    this.#setIndex(this.#context.index + 1);
  }

  #setIndex(index: number): void {
    this.#context = { ...this.#context, index };
    this.#emit();
  }

  #emit(): void {
    const current = this.getSnapshot();
    this.#listeners.forEach((listener) => listener(current));
  }
}

export function createPlaybackController(): PlaybackController {
  return new PlaybackController();
}
