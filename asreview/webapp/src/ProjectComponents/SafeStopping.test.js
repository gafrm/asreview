import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "react-query";
import { ProjectAPI } from "api";
import SafeStopping, { SafeSetup } from "./SafeStopping";

jest.mock("api", () => ({
  ProjectAPI: {
    fetchStopping: jest.fn(),
    fetchPriorSearch: jest.fn(),
    configureSafe: jest.fn(),
    transitionSafe: jest.fn(),
    previewSeedImport: jest.fn(),
  },
}));

let container, root, client;
const status = (overrides = {}) => ({
  id: "safe",
  phase: "primary",
  model: "elas_u4",
  ready: true,
  paused: false,
  stop: false,
  screened: 300,
  total: 1000,
  sample_count: 200,
  sample_target: 200,
  sample_relevant: 10,
  estimated_relevant: 50,
  value: 100,
  checks: [
    {
      id: "keys",
      label: "Key studies marked relevant",
      value: 0,
      target: 1,
      met: false,
    },
    {
      id: "streak",
      label: "Consecutive exclusions in this phase",
      value: 100,
      target: 100,
      met: true,
    },
  ],
  ...overrides,
});

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, cacheTime: 0 } },
  });
  ProjectAPI.fetchStopping.mockResolvedValue(status());
  ProjectAPI.fetchPriorSearch.mockResolvedValue({ result: [] });
});

afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
});

const render = async (element) => {
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    );
  });
};
const button = (text) =>
  [...container.querySelectorAll("button")].find((node) =>
    node.textContent.includes(text),
  );

test("100 exclusions alone does not offer a phase transition", async () => {
  await render(<SafeStopping project_id="test" status={status()} />);
  expect(container.textContent).toContain(
    "Pending: Key studies marked relevant",
  );
  expect(button("Start ELAS l2")).toBeUndefined();
});

test("compact screening keeps all four condition statuses visible", async () => {
  const checks = [
    {
      id: "keys",
      label: "Key studies marked relevant",
      value: 1,
      target: 2,
      met: false,
    },
    {
      id: "estimate",
      label: "Twice the estimate",
      value: 400,
      target: 300,
      met: true,
    },
    {
      id: "fraction",
      label: "Ten percent",
      value: 400,
      target: 1234,
      met: false,
    },
    {
      id: "streak",
      label: "Consecutive exclusions",
      value: 73,
      target: 100,
      met: false,
    },
  ];
  await render(
    <SafeStopping project_id="test" status={status({ checks })} compact />,
  );
  const tracker = container.querySelector(
    '[aria-label="Stopping conditions tracker"]',
  );
  expect(tracker.querySelectorAll(".MuiChip-root")).toHaveLength(4);
  expect(tracker.textContent).toContain("Pending: Key studies 1/2");
  expect(tracker.textContent).toContain("Met: Screened: 2× estimate 400/300");
  expect(tracker.textContent).toContain("Pending: Screened: 10% 400/1234");
  expect(tracker.textContent).toContain(
    "Pending: Consecutive exclusions 73/100",
  );
  expect(button("Show criteria")).toBeDefined();
});

test("primary pause offers the second model and never an ignore-stop button", async () => {
  const paused = status({ stop: true, paused: true });
  ProjectAPI.transitionSafe.mockResolvedValue(
    status({ phase: "secondary", ready: false, value: 0 }),
  );
  await render(<SafeStopping project_id="test" status={paused} />);
  expect(container.textContent).toContain("Screening paused");
  expect(button("Review more")).toBeUndefined();
  await act(async () => button("Start ELAS l2").click());
  expect(ProjectAPI.transitionSafe).toHaveBeenCalledWith({
    project_id: "test",
    action: "secondary",
  });
});

test("training screen provides retry and no random-ranking bypass", async () => {
  await render(
    <SafeStopping
      project_id="test"
      status={status({ ready: false })}
      trainingError={{ message: "Model download failed" }}
    />,
  );
  expect(container.textContent).toContain("Model download failed");
  expect(button("Retry model training")).toBeDefined();
  expect(button("I can't wait")).toBeUndefined();
});

test("secondary stop explicitly leaves independent quality control outstanding", async () => {
  await render(
    <SafeStopping
      project_id="test"
      status={status({ phase: "secondary", stop: true, paused: true })}
    />,
  );
  expect(container.textContent).toContain("independent quality-control review");
  expect(button("Start ELAS l2")).toBeUndefined();
});

test("setup requires explicit key-study selection or an explicit empty list", async () => {
  ProjectAPI.configureSafe.mockResolvedValue(status({ phase: "random" }));
  const started = jest.fn();
  await render(<SafeSetup project_id="test" onStarted={started} />);
  expect(button("Start SAFE screening").disabled).toBe(true);
  await act(async () =>
    container.querySelector('input[type="checkbox"]').click(),
  );
  expect(button("Start SAFE screening").disabled).toBe(false);
  await act(async () => button("Start SAFE screening").click());
  expect(ProjectAPI.configureSafe).toHaveBeenCalledWith({
    project_id: "test",
    key_record_ids: [],
    no_key_studies: true,
  });
  expect(started).toHaveBeenCalledTimes(1);
});

const seedRecord = {
  record_id: 7,
  group_id: 7,
  title: "Known relevant study",
  doi: "10.1234/a",
};
const seedRow = (overrides = {}) => ({
  id: 0,
  title: seedRecord.title,
  doi: seedRecord.doi,
  authors: "",
  year: "",
  status: "matched",
  method: "doi",
  reason: "Matched by DOI.",
  match: seedRecord,
  candidates: [seedRecord],
  candidate_count: 1,
  ...overrides,
});
const importSeeds = async (rows) => {
  ProjectAPI.previewSeedImport.mockResolvedValue({
    filename: "seeds.csv",
    rows,
  });
  const file = new File(
    ["doi,title\n10.1234/a,Known relevant study"],
    "seeds.csv",
    { type: "text/csv" },
  );
  await act(async () => {
    const input = container.querySelector('input[type="file"]');
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [file],
    });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  return file;
};

test("seed upload selects exact matches, deduplicates records and submits the audit", async () => {
  ProjectAPI.configureSafe.mockResolvedValue(status({ phase: "random" }));
  await render(<SafeSetup project_id="test" onStarted={jest.fn()} />);
  const file = await importSeeds([seedRow(), seedRow({ id: 1 })]);
  expect(ProjectAPI.previewSeedImport).toHaveBeenCalledWith({
    project_id: "test",
    file,
  });
  expect(container.textContent).toContain("2 automatically matched");
  expect(container.textContent).toContain("1 records selected as key studies");
  expect(button("Start SAFE screening").disabled).toBe(false);
  await act(async () => button("Start SAFE screening").click());
  const payload = ProjectAPI.configureSafe.mock.calls[0][0];
  expect(payload.key_record_ids).toEqual([7]);
  expect(payload.seed_import.entries).toHaveLength(2);
  expect(payload.seed_import.entries[0]).toEqual({
    title: seedRecord.title,
    doi: seedRecord.doi,
    authors: "",
    year: "",
    record_id: 7,
    not_present: false,
  });
});

test("missing seeds block starting until absence is explicitly recorded", async () => {
  ProjectAPI.configureSafe.mockResolvedValue(status({ phase: "random" }));
  await render(<SafeSetup project_id="test" onStarted={jest.fn()} />);
  await importSeeds([
    seedRow(),
    seedRow({
      id: 1,
      title: "Missing study",
      doi: "",
      status: "missing",
      match: null,
      candidates: [],
      candidate_count: 0,
    }),
  ]);
  expect(button("Start SAFE screening").disabled).toBe(true);
  const row = container.querySelector('[aria-label="Seed entry 2"]');
  await act(async () => row.querySelector('input[type="checkbox"]').click());
  expect(button("Start SAFE screening").disabled).toBe(false);
  await act(async () => button("Start SAFE screening").click());
  expect(
    ProjectAPI.configureSafe.mock.calls[0][0].seed_import.entries[1],
  ).toMatchObject({
    title: "Missing study",
    record_id: null,
    not_present: true,
  });
});

test("an ambiguous seed can be resolved from its suggested records", async () => {
  ProjectAPI.configureSafe.mockResolvedValue(status({ phase: "random" }));
  await render(<SafeSetup project_id="test" onStarted={jest.fn()} />);
  await importSeeds([seedRow({ status: "ambiguous", match: null })]);
  expect(button("Start SAFE screening").disabled).toBe(true);
  const input = container.querySelector(
    '[aria-label="Seed entry 1"] input[role="combobox"]',
  );
  await act(async () => {
    input.focus();
    input.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "ArrowDown",
        code: "ArrowDown",
        bubbles: true,
      }),
    );
  });
  await act(async () => document.querySelector('[role="option"]').click());
  expect(button("Start SAFE screening").disabled).toBe(false);
  await act(async () => button("Start SAFE screening").click());
  expect(ProjectAPI.configureSafe.mock.calls[0][0].key_record_ids).toEqual([7]);
});

test("matched records can be inspected and clearing the import removes their selection", async () => {
  await render(<SafeSetup project_id="test" onStarted={jest.fn()} />);
  await importSeeds([seedRow()]);
  expect(container.querySelector('[aria-label="Seed entry 1"]')).toBeNull();
  await act(async () => button("Review matched studies").click());
  expect(
    container.querySelector('[aria-label="Seed entry 1"]').textContent,
  ).toContain(seedRecord.title);
  await act(async () => button("Clear import").click());
  expect(button("Start SAFE screening").disabled).toBe(true);
  expect(container.textContent).toContain("0 records selected as key studies");
});

test("an unmatched seed can be linked through a manual title search", async () => {
  ProjectAPI.configureSafe.mockResolvedValue(status({ phase: "random" }));
  await render(<SafeSetup project_id="test" onStarted={jest.fn()} />);
  await importSeeds([
    seedRow({
      status: "missing",
      match: null,
      candidates: [],
      candidate_count: 0,
    }),
  ]);
  ProjectAPI.fetchPriorSearch.mockResolvedValue({ result: [seedRecord] });
  const input = container.querySelector(
    '[aria-label="Seed entry 1"] input[role="combobox"]',
  );
  await act(async () => {
    input.focus();
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    ).set.call(input, "Known relevant");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  expect(ProjectAPI.fetchPriorSearch).toHaveBeenCalled();
  await act(async () => document.querySelector('[role="option"]').click());
  await act(async () => button("Start SAFE screening").click());
  expect(
    ProjectAPI.configureSafe.mock.calls[0][0].seed_import.entries[0],
  ).toMatchObject({
    record_id: 7,
    not_present: false,
  });
});

test("a failed upload blocks starting until cleared even with the empty-list option checked", async () => {
  await render(<SafeSetup project_id="test" onStarted={jest.fn()} />);
  await act(async () =>
    container.querySelector('input[type="checkbox"]').click(),
  );
  expect(button("Start SAFE screening").disabled).toBe(false);
  ProjectAPI.previewSeedImport.mockRejectedValueOnce(
    new Error("CSV needs a DOI or title column"),
  );
  const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
  await importSeeds([]);
  expect(container.textContent).toContain("CSV needs a DOI or title column");
  expect(button("Start SAFE screening").disabled).toBe(true);
  await act(async () => button("Clear import").click());
  expect(button("Start SAFE screening").disabled).toBe(false);
  errorSpy.mockRestore();
});
