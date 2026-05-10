declare module "bun:test" {
  type TestFn = () => void | Promise<void>;

  interface Matcher<T = unknown> {
    toBe(expected: T): void;
    toEqual(expected: unknown): void;
  }

  export function describe(name: string, fn: TestFn): void;
  export function test(name: string, fn: TestFn): void;
  export function expect<T = unknown>(actual: T, message?: string): Matcher<T>;
}
