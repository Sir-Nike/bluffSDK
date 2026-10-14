declare module "node:readline" {
  export interface Interface {
    on(event: "line", listener: (line: string) => void): this;
    close(): void;
  }
  export function createInterface(options: { input: unknown; crlfDelay?: number }): Interface;
}

declare const process: {
  stdin: unknown;
  stdout: { write(data: string): void };
};

declare class Buffer {
  static byteLength(input: string, encoding?: string): number;
}
