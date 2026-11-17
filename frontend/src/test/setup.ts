import "@testing-library/jest-dom/vitest";

const memoryStorage: Record<string, string> = {};
const storageMock = {
  getItem: (k: string) => memoryStorage[k] ?? null,
  setItem: (k: string, v: string) => {
    memoryStorage[k] = String(v);
  },
  removeItem: (k: string) => {
    delete memoryStorage[k];
  },
  clear: () => {
    Object.keys(memoryStorage).forEach((k) => delete memoryStorage[k]);
  },
  key: (i: number) => Object.keys(memoryStorage)[i] ?? null,
  get length() {
    return Object.keys(memoryStorage).length;
  },
};

Object.defineProperty(window, "localStorage", {
  writable: true,
  value: storageMock,
});

Object.defineProperty(window, "scrollTo", {
  writable: true,
  value: () => {},
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});
